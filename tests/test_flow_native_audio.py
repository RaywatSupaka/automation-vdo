import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.flow_native_audio import saved_story_clips, compose_native


class NativeAudioTests(unittest.TestCase):
    def test_saved_order_and_local_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ("a.mp4", "b.mp4"):
                (folder / name).touch()
            job = {"scene_count": 2, "flow_clips": {"1": "a.mp4"}, "flow_fallback_clips": {"2": "b.mp4"}}
            self.assertEqual(saved_story_clips(folder, job), [folder / "a.mp4", folder / "b.mp4"])

    def test_missing_scene_never_generates(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "ฉาก 1"):
                saved_story_clips(directory, {"scene_count": 2})

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "job"
            folder.mkdir()
            (folder.parent / "outside.mp4").touch()
            with self.assertRaises(ValueError):
                saved_story_clips(folder, {"scene_count": 1, "flow_clips": {"1": "../outside.mp4"}})

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "final.mp4"
            output.write_bytes(b"original")
            with self.assertRaises(ValueError):
                compose_native([], output)
            self.assertEqual(output.read_bytes(), b"original")

    @patch("core.flow_native_audio.inspect_clips")
    def test_silent_scene_requires_consent(self, probe):
        probe.return_value = [{"path": "a.mp4", "duration": 2, "has_audio": False}]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "ไม่มีแทร็กเสียง"):
                compose_native(["a.mp4"], Path(directory) / "out.mp4")

    def test_empty_input(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                compose_native([], Path(directory) / "out.mp4")

if __name__ == "__main__":
    unittest.main()
