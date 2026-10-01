import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageStat

from core.config import load_config
from core.story_video import StoryVideoComposer


class StoryVideoTests(unittest.TestCase):
    def test_every_story_scene_is_visible_instead_of_black_after_first(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            colors = ("red", "green", "blue", "orange", "purple", "cyan")
            images = []
            for index, color in enumerate(colors):
                path = root / f"scene-{index}.png"
                Image.new("RGB", (360, 640), color).save(path)
                images.append(path)
            composer = StoryVideoComposer(load_config().get("ffmpeg_path", ""))
            video = root / "story.mp4"
            plan = composer.compose(images, video, [1.2] * len(images), width=360, height=640, fps=24)
            self.assertEqual(plan["fps"], 24)
            self.assertGreater(plan["transition_sec"], 0)
            self.assertEqual(plan["scene_count"], 6)
            self.assertEqual(plan["visual_segment_count"], 6)
            probe = subprocess.run(
                [str(composer.ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,profile,pix_fmt", "-of", "json", str(video)],
                capture_output=True, text=True, encoding="utf-8", check=True, timeout=60,
            )
            stream = json.loads(probe.stdout)["streams"][0]
            self.assertEqual(stream["codec_name"], "h264")
            self.assertEqual(stream["pix_fmt"], "yuv420p")
            self.assertEqual(stream["profile"], "High")
            for index in range(6):
                frame = root / f"frame-{index}.png"
                subprocess.run([str(composer.ffmpeg), "-y", "-ss", str(index * 1.2 + 0.6), "-i", str(video), "-frames:v", "1", "-update", "1", str(frame)], capture_output=True, check=True, timeout=60)
                mean = ImageStat.Stat(Image.open(frame).convert("RGB")).mean
                self.assertGreater(max(mean), 25, f"scene {index + 1} rendered black")


if __name__ == "__main__":
    unittest.main()
