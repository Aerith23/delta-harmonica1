"""Manual integration check: plays a quiet test tone through default output."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from array import array
import json
import math
import tempfile
import time
import wave
import pyaudiowpatch as pa
from recorder import Recorder, list_outputs


def wait_for(predicate, seconds=8):
    end = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() > end:
            raise AssertionError("Timeout waiting for recorder")
        time.sleep(0.02)


def run():
    device = next(d for d in list_outputs() if d.default)
    report = {"device": device.name}
    with tempfile.TemporaryDirectory(prefix="harmonica-check-") as folder:
        recorder = Recorder()
        try:
            recorder.start(device, Path(folder))
            wait_for(lambda: recorder.snapshot()["state"] == "waiting" or not recorder.busy)
            time.sleep(0.3)
            report["wait_state"] = recorder.snapshot()["state"]
            with pa.PyAudio() as audio:
                index = audio.get_host_api_info_by_type(pa.paWASAPI)["defaultOutputDevice"]
                out = audio.open(format=pa.paInt16, channels=device.channels,
                                 rate=device.rate, output=True, output_device_index=index)
                try:
                    for duration, frequency in [(0.4, 0), (0.5, 440), (0.35, 0), (0.5, 660), (0.15, 0)]:
                        samples = array("h")
                        for i in range(round(duration * device.rate)):
                            value = round(3500 * math.sin(2 * math.pi * frequency * i / device.rate)) if frequency else 0
                            samples.extend([value] * device.channels)
                        out.write(samples.tobytes())
                finally:
                    out.stop_stream()
                    out.close()
            time.sleep(0.2)
        finally:
            recorder.stop()
            wait_for(lambda: not recorder.busy)
        kind, result = recorder.events.get(timeout=2)
        assert kind == "finished" and not result["error"], result
        assert result["path"], result
        with wave.open(result["path"], "rb") as wav:
            report["wav_channels"] = wav.getnchannels()
            report["wav_rate"] = wav.getframerate()
            report["wav_seconds"] = wav.getnframes() / wav.getframerate()
            samples = array("h", wav.readframes(wav.getnframes()))
        report["peak"] = max(abs(v) for v in samples)
        assert report["peak"] > 100, report
        assert report["wav_seconds"] > 1.2, report
        # Verify the rest between the two tones remains inside the WAV.
        window = device.rate // 20 * device.channels
        silent = [max(abs(v) for v in samples[i:i + window]) < 33
                  for i in range(0, len(samples) - window + 1, window)]
        assert any(silent[3:-3]), "Internal pause lost or background audio present"
        report["internal_pause_preserved"] = True
        report["leading_silence_trimmed"] = max(abs(v) for v in samples[:device.channels]) >= 33
        assert report["leading_silence_trimmed"], report
        # A second session stopped during silence must create no file.
        recorder.start(device, Path(folder))
        wait_for(lambda: recorder.snapshot()["state"] == "waiting" or not recorder.busy)
        time.sleep(0.35)
        recorder.stop()
        wait_for(lambda: not recorder.busy)
        _, result = recorder.events.get(timeout=2)
        report["silent_session_no_file"] = result["path"] is None and result["error"] is None
        assert report["silent_session_no_file"], result
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run()
