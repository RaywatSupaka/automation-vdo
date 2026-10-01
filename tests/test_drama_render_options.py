import tempfile
import unittest
from pathlib import Path
from core.drama_options import drama_render_options
from core.drama_series import DramaSeriesManager
from core.story_queue import StoryBatchQueue


class DramaRenderOptionsTests(unittest.TestCase):
    def test_settings_survive_series_reload_and_queue_without_form_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = DramaSeriesManager(Path(tmp))
            settings = {"video_generation_mode":"google_flow", "subtitle_enabled":False, "tail_seconds":1}
            series = manager.create("test", episode_count=2, characters=[{"name":"A"}], render_options=settings)
            queue = StoryBatchQueue(Path(tmp) / "queue.json")
            result = queue.enqueue_drama_series(series["id"], "test", 2, render_options=series["render_options"])
            settings["subtitle_enabled"] = True
            context = DramaSeriesManager(Path(tmp)).episode_context(series["id"], 1)
            self.assertFalse(context["render_options"]["subtitle_enabled"])
            self.assertEqual(context["video_generation_mode"], "google_flow")
            self.assertEqual(len(result["items"]), 2)
            self.assertFalse(result["items"][1]["render_options"]["subtitle_enabled"])
            self.assertTrue(queue.snapshot()["paused"])
            queue.resume()
            second = manager.create("second", episode_count=1, characters=[{"name":"A"}], render_options={})
            queue.enqueue_drama_series(second["id"], "second", 1, render_options={}, preserve_state=True)
            self.assertFalse(queue.snapshot()["paused"], "adding pending work must not pause current series")

    def test_old_series_keeps_legacy_settings_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = DramaSeriesManager(Path(tmp))
            series = manager.create("legacy", characters=[{"name":"A"}])
            self.assertNotIn("render_options", series)
            self.assertNotIn("render_options", manager.episode_context(series["id"], 1))

    def test_options_validate_instead_of_silently_coercing(self):
        for value in ({"tail_seconds":float("nan")},{"tail_seconds":3},{"subtitle_enabled":"false"},
                      {"video_generation_mode":"other"},{"timing_mode":"other"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                drama_render_options(value)
