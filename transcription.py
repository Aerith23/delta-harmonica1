"""Local Basic Pitch ONNX inference and harmonica-score-v1 export.

The neural network is Spotify's pretrained model. Windowing and decoding
below are implemented here; they are not a copy of the Basic Pitch library.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import math
import os
import sys
import tempfile
import uuid

SAMPLE_RATE = 22050
FRAME_HOP = 256
WINDOW_SAMPLES = 43844
OVERLAP_FRAMES = 30
WINDOW_HOP = WINDOW_SAMPLES - OVERLAP_FRAMES * FRAME_HOP
MAX_SECONDS = 12 * 60


class ConversionCancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ConversionCancelled('转换已取消')


def decode_notes(frames, onsets, duration, minimum=0.08):
    """Decode held-note activations; repeated onset peaks split repeated notes."""
    import numpy as np
    from scipy.signal import find_peaks
    step = FRAME_HOP / SAMPLE_RATE
    notes = []
    for column in range(88):
        energy = frames[:, column]
        active = energy >= 0.30
        # Bridge only very short activation holes, never musical rests.
        for i in range(1, len(active) - 1):
            if not active[i] and active[i-1] and active[i+1]:
                active[i] = True
        changes = np.diff(np.r_[False, active, False].astype(np.int8))
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        peaks, _ = find_peaks(np.r_[0, onsets[:, column], 0], height=0.45,
                             distance=max(1, round(minimum / step)))
        peaks = peaks - 1
        for left, right in zip(starts, ends):
            # Do not create fragments from weak onset detections inside a sustain.
            split = [int(p) for p in peaks if left < p < right
                     and p - left >= minimum / step and right - p >= minimum / step
                     and (onsets[p, column] >= 0.8 or energy[p] >
                          float(np.mean(energy[max(left, p-8):p])) + 0.12)]
            boundaries = [int(left)] + split + [int(right)]
            previous = boundaries[0]
            for end in boundaries[1:]:
                if (end - previous) * step < minimum:
                    continue
                start_seconds = previous * step
                end_seconds = min(float(duration), end * step)
                if end_seconds - start_seconds >= minimum:
                    amplitude = float(np.mean(energy[previous:end]))
                    notes.append(dict(pitch=int(column + 21), start=round(start_seconds, 6),
                                      duration=round(end_seconds - start_seconds, 6),
                                      velocity=max(1, min(127, round(amplitude * 127))),
                                      track=0, channel=0))
                previous = end
    return sorted(notes, key=lambda n: (n['start'], -n['pitch']))


def simplify_monophonic(notes):
    """Heuristic single voice, no claim to identify a singer or instrument.

    Near-simultaneous attacks are grouped. Strength, register and continuity
    select one note; overlaps are truncated without shifting note onsets.
    """
    ordered = sorted((dict(n) for n in notes), key=lambda n: (n['start'], -n['pitch']))
    groups = []
    for note in ordered:
        if not groups or note['start'] - groups[-1][0]['start'] > 0.035:
            groups.append([note])
        else:
            groups[-1].append(note)
    result = []
    previous_pitch = 72
    for group in groups:
        def rank(note):
            return (note['velocity'] / 127 + min(note['duration'], 0.8) * 0.15
                    - abs(note['pitch'] - 72) * 0.008
                    - min(abs(note['pitch'] - previous_pitch), 24) * 0.012)
        note = max(group, key=rank)
        # A weak accompaniment attack must not replace a stronger held melody.
        if (result and result[-1]['start'] + result[-1]['duration'] > note['start'] + 0.08
            and note['velocity'] < 0.7 * result[-1]['velocity']):
            continue
        if result and result[-1]['start'] + result[-1]['duration'] > note['start']:
            result[-1]['duration'] = round(note['start'] - result[-1]['start'], 6)
            if result[-1]['duration'] <= 0:
                result.pop()
        result.append(note)
        previous_pitch = note['pitch']
    return result


def validate_score(score):
    if score.get('format') != 'harmonica-score-v1' or not isinstance(score.get('notes'), list):
        raise ValueError('不支持的曲谱格式')
    for note in score['notes']:
        for field in ('pitch', 'velocity', 'track', 'channel'):
            if type(note[field]) is not int:
                raise ValueError(f'{field} 必须是整数')
        if not 0 <= note['pitch'] <= 127 or not 0 <= note['velocity'] <= 127:
            raise ValueError('音高或力度超出 MIDI 范围')
        if note['track'] < 0 or not 0 <= note['channel'] <= 15:
            raise ValueError('音轨或通道无效')
        if not math.isfinite(note['start']) or note['start'] < 0:
            raise ValueError('起始时间必须为非负秒数')
        if not math.isfinite(note['duration']) or note['duration'] <= 0:
            raise ValueError('时长必须为正秒数')


def build_score(notes, title, duration, source_name, monophonic=True):
    if not notes:
        raise ValueError('未识别到稳定音符。请尝试更清晰的独奏或器乐片段。')
    prepared = simplify_monophonic(notes) if monophonic else [dict(n) for n in notes]
    score = dict(format='harmonica-score-v1', title=title, tracks={'0': '音频识别'},
                 notes=prepared, length=round(duration, 6),
                 studio=dict(speed=1.0, legato=90.0, breath_ms=60, auto_adapt=True, track_id=None),
                 pinned=False, import_source_kind='audio',
                 source_info=dict(file=source_name, engine='Basic Pitch ONNX',
                                  decoder='delta-harmonica-v1', raw_note_count=len(notes),
                                  monophonic=bool(monophonic)))
    validate_score(score)
    return score


def read_audio(path, cancel=None):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    info = sf.info(str(path))
    if info.frames <= 0 or info.samplerate <= 0 or info.channels <= 0:
        raise ValueError('录音文件为空或格式损坏')
    if info.duration > MAX_SECONDS:
        raise ValueError('单次支持最长 12 分钟录音，请先录制较短片段')
    chunks = []
    divisor = math.gcd(info.samplerate, SAMPLE_RATE)
    with sf.SoundFile(str(path)) as handle:
        while True:
            check_cancel(cancel)
            block = handle.read(info.samplerate * 10, dtype='float32', always_2d=True)
            if not len(block):
                break
            mono = block.mean(axis=1)
            # Opposite-phase stereo must not turn audible audio into silence.
            if info.channels > 1:
                power = (block * block).mean(axis=0)
                if (mono * mono).mean() < 0.05 * power.max():
                    mono = block[:, int(power.argmax())]
            chunks.append(resample_poly(mono, SAMPLE_RATE // divisor,
                                         info.samplerate // divisor).astype(np.float32))
    audio = np.concatenate(chunks)
    if not np.all(np.isfinite(audio)):
        raise ValueError('音频含无效采样值')
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-5:
        raise ValueError('录音没有可识别的声音')
    audio = audio / max(peak, 1e-5) * 0.9
    return audio, float(info.duration)


def infer_audio(audio, model_path, cancel=None, progress=None):
    import numpy as np
    import onnxruntime as ort
    progress = progress or (lambda value, message: None)
    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
    session = ort.InferenceSession(str(model_path), sess_options=options,
                                   providers=['CPUExecutionProvider'])
    pad = OVERLAP_FRAMES * FRAME_HOP // 2
    padded = np.pad(audio, (pad, 0))
    total_frames = math.ceil(len(audio) / FRAME_HOP) + 1
    frames = np.zeros((total_frames, 88), dtype=np.float32)
    onsets = np.zeros_like(frames)
    counts = np.zeros(total_frames, dtype=np.float32)
    offsets = list(range(0, len(padded), WINDOW_HOP))
    for index, offset in enumerate(offsets):
        check_cancel(cancel)
        window = padded[offset:offset + WINDOW_SAMPLES]
        window = np.pad(window, (0, WINDOW_SAMPLES - len(window)))
        result = session.run(['StatefulPartitionedCall:1', 'StatefulPartitionedCall:2'],
                             {'serving_default_input_2:0': window.reshape(1, -1, 1).astype(np.float32)})
        # Discard unreliable overlap edges; map to the original audio time grid.
        note, onset = result[0][0], result[1][0]
        for local in range(OVERLAP_FRAMES // 2, len(note) - OVERLAP_FRAMES // 2):
            position = round((offset - pad) / FRAME_HOP + local)
            if 0 <= position < total_frames:
                frames[position] += note[local]
                onsets[position] += onset[local]
                counts[position] += 1
        progress(15 + 65 * (index + 1) / len(offsets), f'识别音符 {index + 1}/{len(offsets)}')
    divisor = np.maximum(counts, 1)[:, None]
    return frames / divisor, onsets / divisor


def model_location():
    directory = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return directory / 'models' / 'basic_pitch.onnx'


def convert_recording(source, destination, monophonic=True, cancel=None, progress=None):
    source, destination = Path(source), Path(destination)
    progress = progress or (lambda value, message: None)
    check_cancel(cancel)
    model = model_location()
    if not model.is_file():
        raise RuntimeError('缺少本地转谱模型。请运行 scripts/setup_model.py，或使用完整的新版本程序。')
    try:
        progress(3, '正在读取录音')
        audio, duration = read_audio(source, cancel)
        progress(12, '正在加载本地音符模型')
        frames, onsets = infer_audio(audio, model, cancel, progress)
    except ImportError as exc:
        raise RuntimeError('缺少转谱依赖，请使用启动源码.cmd，或在项目 .venv 中安装 requirements.txt') from exc
    check_cancel(cancel)
    progress(85, '正在整理音符与曲谱')
    notes = decode_notes(frames, onsets, duration)
    score = build_score(notes, source.stem, duration, source.name, monophonic)
    with source.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    score['import_source_sha256'] = digest
    check_cancel(cancel)
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / (source.stem + '.json')
    if output.exists():
        output = destination / (source.stem + '_' + uuid.uuid4().hex[:8] + '.json')
    fd, temporary = tempfile.mkstemp(prefix='.transcribe-', suffix='.tmp', dir=destination)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(score, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
        check_cancel(cancel)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    progress(100, '转换完成')
    return dict(path=str(output), notes=len(score['notes']), raw_notes=len(notes), seconds=duration)
