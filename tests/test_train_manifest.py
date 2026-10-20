"""Check data validation and WER math without GPU or model downloads."""

import csv
import tempfile
import unittest
from pathlib import Path

from train_uyghur_asr import error_rates, read_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def test_manifest_and_speaker_leakage(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            (root / "a.wav").write_bytes(b"dummy")
            (root / "b.wav").write_bytes(b"dummy")
            manifest = root / "labels.csv"
            with manifest.open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerows([
                    ["audio", "text", "split", "speaker_id"],
                    ["a.wav", "  سالام  ", "train", "speaker-1"],
                    ["b.wav", "ياخشىمۇسىز", "validation", "speaker-2"],
                ])
            rows = read_manifest(manifest)
            self.assertEqual(rows[0].text, "سالام")
            self.assertEqual(len(rows), 2)
            content = manifest.read_text(encoding="utf-8").replace("speaker-2", "speaker-1")
            manifest.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "相同说话人"):
                read_manifest(manifest)

    def test_error_rates(self):
        wer, cer = error_rates(["a b"], ["a c"])
        self.assertEqual(wer, 0.5)
        self.assertAlmostEqual(cer, 1 / 3)


if __name__ == "__main__":
    unittest.main()
