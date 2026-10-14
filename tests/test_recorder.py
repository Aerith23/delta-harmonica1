import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from array import array
import unittest
from recorder import LeadingSilenceGate


def pcm(values):
    return array("h", values).tobytes()


class GateTests(unittest.TestCase):
    def test_all_silence_never_starts(self):
        gate = LeadingSilenceGate(2)
        for _ in range(100):
            self.assertEqual(gate.feed(pcm([0] * 960))[0], b"")
        self.assertFalse(gate.triggered)
        self.assertEqual(gate.skipped_frames, 48000)

    def test_trim_inside_chunk_aligned_to_right_channel(self):
        gate = LeadingSilenceGate(2)
        out, _ = gate.feed(pcm([0, 0, 0, 0, 0, 200, 200, 200]))
        self.assertEqual(out, pcm([0, 200, 200, 200]))
        self.assertEqual(gate.skipped_frames, 2)

    def test_internal_silence_and_repeated_notes_preserved(self):
        gate = LeadingSilenceGate(1)
        source = [pcm([0, 100, 100]), pcm([0] * 1000), pcm([100, 0])]
        out = b"".join(gate.feed(c)[0] for c in source)
        self.assertEqual(out, pcm([100, 100] + [0] * 1000 + [100, 0]))

    def test_low_noise_does_not_trigger(self):
        gate = LeadingSilenceGate(1, -60)
        self.assertEqual(gate.feed(pcm([1, -10, 20, -20]))[0], b"")
        self.assertEqual(gate.feed(pcm([-100]))[0], pcm([-100]))

    def test_full_scale_negative_and_multichannel(self):
        gate = LeadingSilenceGate(6)
        data = pcm([0] * 11 + [-32768])
        out, peak = gate.feed(data)
        self.assertEqual(out, data[12:])
        self.assertEqual(peak, 0)

    def test_incomplete_frame_rejected(self):
        with self.assertRaises(ValueError):
            LeadingSilenceGate(2).feed(b"\x00\x00")

    def test_threshold_edge(self):
        gate = LeadingSilenceGate(1, -60)
        self.assertEqual(gate.feed(pcm([32]))[0], b"")
        self.assertEqual(gate.feed(pcm([33]))[0], pcm([33]))


if __name__ == "__main__":
    unittest.main()
