"""Real-model end-to-end check with synthesized notes; never plays audio."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import tempfile
import threading
import numpy as np
import soundfile as sf
from transcription import convert_recording, validate_score, ConversionCancelled

def run():
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        audio = []
        sr = 48000
        for pitch in [60, 64, 67]:
            t = np.arange(sr) / sr
            hz = 440 * 2 ** ((pitch - 69) / 12)
            envelope = np.minimum(t / 0.02, 1) * np.minimum((1-t) / 0.06, 1)
            tone = envelope * (0.25 * np.sin(2*np.pi*hz*t) + 0.08 * np.sin(4*np.pi*hz*t))
            audio.extend([tone, np.zeros(sr // 4)])
        source = folder / '测试旋律.wav'
        sf.write(source, np.concatenate(audio), sr)
        result = convert_recording(source, folder / '曲谱')
        score = json.loads(Path(result['path']).read_text(encoding='utf-8'))
        validate_score(score)
        pitches = [n['pitch'] for n in score['notes']]
        assert pitches == [60,64,67], pitches
        assert all(n['start'] + n['duration'] <= 3.751 for n in score['notes'])
        duplicate = convert_recording(source, folder / '曲谱')
        assert duplicate['path'] != result['path'] and Path(result['path']).exists()
        cancelled = threading.Event(); cancelled.set()
        try:
            convert_recording(source, folder / 'cancelled', cancel=cancelled)
            raise AssertionError('Cancellation failed')
        except ConversionCancelled:
            assert not (folder / 'cancelled').exists()
        silent = folder / 'silent.wav'; sf.write(silent, np.zeros(sr), sr)
        try:
            convert_recording(silent, folder / 'silence')
            raise AssertionError('Silent input accepted')
        except ValueError:
            assert not (folder / 'silence').exists()
        if len(sys.argv) == 2:
            import subprocess
            output = folder / 'frozen-output'
            proc = subprocess.run([sys.argv[1], '--convert', str(source), str(output)], timeout=60)
            assert proc.returncode == 0, proc.returncode
            files = list(output.glob('*.json'))
            assert len(files) == 1, files
            packaged = json.loads(files[0].read_text(encoding='utf-8'))
            validate_score(packaged)
            assert [n['pitch'] for n in packaged['notes']] == [60,64,67]
            print('PACKAGED_EXE_CONVERSION_OK')
        print(json.dumps(dict(pitches=pitches, notes=result['notes'], seconds=result['seconds'],
                              collision_safe=True, cancelled_no_file=True, silence_no_file=True), indent=2))

if __name__ == '__main__':
    run()
