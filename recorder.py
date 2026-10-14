"""Windows output capture. No device is opened until start() is called."""
from __future__ import annotations

from array import array
from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import queue
import threading
import time
import uuid
import wave


@dataclass(frozen=True)
class OutputDevice:
    index: int
    name: str
    channels: int
    rate: int
    default: bool = False


def list_outputs() -> list[OutputDevice]:
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        try:
            default = int(audio.get_default_wasapi_loopback()["index"])
        except (OSError, ValueError):
            default = -1
        return [OutputDevice(int(d["index"]), d["name"].replace(" [Loopback]", ""),
                             int(d["maxInputChannels"]), int(d["defaultSampleRate"]),
                             int(d["index"]) == default)
                for d in audio.get_loopback_device_info_generator()
                if d["maxInputChannels"] > 0]


class LeadingSilenceGate:
    """PCM16 gate: trim only the leading silence, never internal rests.

    Threshold uses peak amplitude across ALL channels. Alignment stays on
    complete interleaved frames, including when only one channel has sound.
    """
    def __init__(self, channels: int, threshold_db: float = -60):
        if channels < 1 or not -96 <= threshold_db <= 0:
            raise ValueError("Invalid channels or threshold")
        self.channels = channels
        self.threshold = max(1, math.ceil(32768 * 10 ** (threshold_db / 20)))
        self.triggered = False
        self.skipped_frames = 0

    def feed(self, data: bytes) -> tuple[bytes, float]:
        if len(data) % (2 * self.channels):
            raise ValueError("Incomplete PCM frame")
        samples = array("h", data)
        peak = max((abs(s) for s in samples), default=0)
        db = 20 * math.log10(peak / 32768) if peak else -96.0
        if self.triggered:
            return data, max(-96.0, db)
        for i, sample in enumerate(samples):
            if abs(sample) >= self.threshold:
                frame = i // self.channels
                self.skipped_frames += frame
                self.triggered = True
                return data[frame * self.channels * 2:], max(-96.0, db)
        self.skipped_frames += len(samples) // self.channels
        return b"", max(-96.0, db)


class Recorder:
    def __init__(self):
        self.events: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._status = dict(state="idle", seconds=0.0, peak=-96.0,
                            skipped=0.0, bytes=0, updated=0.0)

    @property
    def busy(self):
        return self._thread is not None and self._thread.is_alive()

    def snapshot(self):
        with self._lock:
            value = dict(self._status)
        if time.monotonic() - value["updated"] > 0.3:
            value["peak"] = -96.0
        return value

    def _update(self, **values):
        with self._lock:
            self._status.update(values)

    def start(self, device: OutputDevice, folder: Path, threshold_db=-60):
        if self.busy:
            raise RuntimeError("录音尚未停止")
        self._stop.clear()
        self._update(state="opening", seconds=0.0, peak=-96.0,
                     skipped=0.0, bytes=0, updated=0.0)
        self._thread = threading.Thread(target=self._record,
                                        args=(device, Path(folder), threshold_db),
                                        name="wasapi-recorder", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _record(self, device, folder, threshold_db):
        stream = audio = writer = None
        partial = final = None
        error = None
        frames = 0
        gate = LeadingSilenceGate(device.channels, threshold_db)
        chunks = queue.Queue(maxsize=256)
        overflow = threading.Event()
        started_at = None
        waiting_at = time.monotonic()
        try:
            import pyaudiowpatch as pa
            folder.mkdir(parents=True, exist_ok=True)
            audio = pa.PyAudio()
            # Device indices can change after Windows changes audio devices.
            info = audio.get_device_info_by_index(device.index)
            if (not info.get("isLoopbackDevice") or
                info["name"].replace(" [Loopback]", "") != device.name or
                int(info["maxInputChannels"]) != device.channels or
                int(info["defaultSampleRate"]) != device.rate):
                raise RuntimeError("输出设备已变化，请刷新设备列表后重试")

            def receive(data, frame_count, time_info, flags):
                if self._stop.is_set():
                    return None, pa.paComplete
                if flags & pa.paInputOverflow:
                    overflow.set()
                try:
                    chunks.put_nowait(data)
                except queue.Full:
                    overflow.set()
                return None, pa.paContinue

            if self._stop.is_set():
                return
            stream = audio.open(format=pa.paInt16, channels=device.channels,
                                rate=device.rate, input=True,
                                input_device_index=device.index,
                                frames_per_buffer=max(128, device.rate // 100),
                                stream_callback=receive, start=False)
            stream.start_stream()
            waiting_at = time.monotonic()
            self._update(state="waiting")
            while True:
                if overflow.is_set():
                    raise RuntimeError("录音数据发生丢失，已停止并保留已录部分。请关闭高负载程序后重试")
                try:
                    data = chunks.get(timeout=0.05)
                except queue.Empty:
                    if self._stop.is_set():
                        break
                    if not stream.is_active():
                        raise RuntimeError("音频设备已停止，可能已断开。请刷新设备后重试")
                    if not gate.triggered:
                        self._update(skipped=time.monotonic() - waiting_at)
                    continue
                output, db = gate.feed(data)
                if output:
                    if writer is None:
                        started_at = time.monotonic()
                        name = datetime.now().strftime("录音_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
                        final = folder / (name + ".wav")
                        partial = folder / (name + ".partial.wav")
                        writer = wave.open(str(partial), "wb")
                        writer.setnchannels(device.channels)
                        writer.setsampwidth(2)
                        writer.setframerate(device.rate)
                        self._update(state="recording", skipped=max(0, started_at - waiting_at))
                    writer.writeframesraw(output)
                    frames += len(output) // (device.channels * 2)
                self._update(peak=db, updated=time.monotonic(), seconds=frames / device.rate,
                             bytes=frames * device.channels * 2)
                if frames * device.channels * 2 >= 3_500_000_000:
                    self.events.put(("notice", "已接近 WAV 大小限制，自动停止并保存"))
                    self._stop.set()
        except Exception as exc:
            error = str(exc)
        finally:
            for obj, method in [(stream, "stop_stream"), (stream, "close"), (audio, "terminate")]:
                if obj is not None:
                    try:
                        getattr(obj, method)()
                    except Exception as exc:
                        error = error or str(exc)
            saved = None
            if writer is not None:
                try:
                    writer.close()
                    partial.replace(final)
                    saved = str(final)
                except Exception as exc:
                    error = f"保存失败：{exc}；临时文件：{partial}"
            self._update(state="idle", peak=-96.0)
            self.events.put(("finished", dict(path=saved, error=error,
                                             seconds=frames / device.rate)))
