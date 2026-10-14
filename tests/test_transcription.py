import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import tempfile
import threading
import unittest
import numpy as np
import soundfile as sf
from transcription import (decode_notes, build_score, validate_score, simplify_monophonic,
                           read_audio, check_cancel, ConversionCancelled, FRAME_HOP, SAMPLE_RATE)

ROOT = Path(__file__).resolve().parents[1]

class TranscriptionTests(unittest.TestCase):
    def test_existing_library_compatible(self):
        files = list((ROOT / '曲库/曲谱').glob('*.json'))
        self.assertGreaterEqual(len(files), 110)
        for path in files:
            validate_score(json.loads(path.read_text(encoding='utf-8-sig')))

    def test_decode_repeated_note_and_rest(self):
        frames = np.zeros((150, 88), dtype=np.float32)
        onsets = np.zeros_like(frames)
        frames[10:60, 39] = 0.8
        frames[100:130, 43] = 0.7
        onsets[10, 39] = onsets[35, 39] = onsets[100, 43] = 0.9
        notes = decode_notes(frames, onsets, 2)
        self.assertEqual([n['pitch'] for n in notes], [60, 60, 64])
        self.assertAlmostEqual(notes[0]['start'], 10 * FRAME_HOP / SAMPLE_RATE, places=5)
        self.assertGreater(notes[2]['start'] - notes[1]['start'] - notes[1]['duration'], 0.4)

    def test_silence_has_no_notes(self):
        empty = np.zeros((100, 88))
        self.assertEqual(decode_notes(empty, empty, 1), [])
        with self.assertRaises(ValueError):
            build_score([], 'silent', 1, 'silent.wav')

    def test_monophonic_does_not_mutate_source(self):
        notes = [dict(pitch=60, start=0.0, duration=1., velocity=90, track=0, channel=0),
                 dict(pitch=64, start=0.5, duration=0.3, velocity=90, track=0, channel=0)]
        result = simplify_monophonic(notes)
        self.assertEqual(result[0]['duration'], 0.5)
        self.assertEqual(notes[0]['duration'], 1.)

    def test_weak_attack_does_not_break_stronger_sustain(self):
        notes = [dict(pitch=60, start=0., duration=1., velocity=90, track=0, channel=0),
                 dict(pitch=72, start=0.4, duration=0.2, velocity=40, track=0, channel=0)]
        result = simplify_monophonic(notes)
        self.assertEqual([n['pitch'] for n in result], [60])
        self.assertEqual(result[0]['duration'], 1.)

    def test_polyphonic_mode_retains_chord(self):
        notes = [dict(pitch=p, start=0., duration=1., velocity=90, track=0, channel=0) for p in [60,64,67]]
        self.assertEqual(len(build_score(notes, 'chord', 2, 'chord.wav', False)['notes']), 3)
        self.assertEqual(len(build_score(notes, 'chord', 2, 'chord.wav', True)['notes']), 1)

    def test_nonfinite_time_rejected(self):
        note = dict(pitch=60, start=float('nan'), duration=1., velocity=90, track=0, channel=0)
        with self.assertRaises(ValueError):
            build_score([note], 'bad', 1, 'bad.wav', False)

    def test_antiphase_stereo_and_resampling(self):
        with tempfile.TemporaryDirectory() as folder:
            t = np.arange(48000) / 48000
            left = 0.1 * np.sin(2 * np.pi * 440 * t)
            path = Path(folder) / '反相.wav'
            sf.write(path, np.column_stack([left, -left]), 48000)
            audio, duration = read_audio(path)
            self.assertEqual(len(audio), 22050)
            self.assertEqual(duration, 1.)
            self.assertGreater(float(np.max(np.abs(audio))), 0.8)

    def test_cancel_prevents_processing(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(ConversionCancelled):
            check_cancel(event)

if __name__ == '__main__':
    unittest.main()
