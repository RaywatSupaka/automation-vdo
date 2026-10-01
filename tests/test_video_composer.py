import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs
from core.config import load_config
from core.story_video import StoryVideoComposer
from core.video_composer import MultiFlowComposer
from PIL import Image


class MultiFlowComposerTests(unittest.TestCase):
    def test_story_local_policy_fallback_renders_real_motion_clip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "face-free-scene.png"
            Image.new("RGB", (180, 320), "navy").save(image)
            output = root / "local-motion.mp4"
            composer = StoryVideoComposer(load_config().get("ffmpeg_path", ""))

            plan = composer.render_scene_motion_clip(
                image, output, duration=2, width=360, height=640,
                fps=24, crf=23, motion_strength=0.5,
            )

            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1024)
            self.assertEqual(plan["source_type"], "story_local_motion_fallback")
            self.assertEqual((plan["width"], plan["height"], plan["fps"]), (360, 640, 24))
            self.assertAlmostEqual(plan["duration"], 2.0, delta=0.15)

    def test_landscape_flow_clips_fill_vertical_frame_without_black_letterbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            composer = MultiFlowComposer(load_config().get("ffmpeg_path", ""))
            clips = []
            for index in (1, 2):
                clip = root / f"landscape-{index}.mp4"
                subprocess.run([
                    str(composer.ffmpeg), "-y", "-f", "lavfi",
                    "-i", "color=c=yellow:s=640x360:r=24:d=0.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
                ], capture_output=True, check=True, timeout=60, **hidden_process_kwargs())
                clips.append(clip)
            output = root / "vertical.mp4"
            composer.compose(clips, output, width=360, height=640, fps=24, transition_sec=0)
            frame = root / "frame.png"
            subprocess.run([
                str(composer.ffmpeg), "-y", "-ss", "0.2", "-i", str(output),
                "-frames:v", "1", str(frame),
            ], capture_output=True, check=True, timeout=60, **hidden_process_kwargs())
            with Image.open(frame) as opened:
                red, green, blue = opened.convert("RGB").getpixel((4, 4))
            self.assertGreater(red, 180)
            self.assertGreater(green, 150)
            self.assertLess(blue, 80)

    def test_crossfade_output_keeps_requested_video_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            composer = MultiFlowComposer(load_config().get("ffmpeg_path", ""))
            clips = []
            for index, color in enumerate(("red", "green", "blue"), 1):
                clip = root / f"flow-{index}.mp4"
                command = [
                    str(composer.ffmpeg), "-y", "-f", "lavfi",
                    "-i", f"color=c={color}:s=360x640:r=24:d=0.8",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
                ]
                subprocess.run(command, capture_output=True, check=True, timeout=60, **hidden_process_kwargs())
                clips.append(clip)

            output = root / "joined.mp4"
            plan = composer.compose(clips, output, width=360, height=640, fps=24, crf=18, transition_sec=0.22)
            self.assertEqual(plan["clip_count"], 3)
            self.assertEqual(plan["fps"], 24)
            self.assertGreater(plan["transition_sec"], 0)
            self.assertAlmostEqual(plan["duration"], 2.4, delta=0.15)
            probe = subprocess.run(
                [str(composer.ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate", "-of", "json", str(output)],
                capture_output=True, text=True, encoding="utf-8", check=True, timeout=60,
                **hidden_process_kwargs(),
            )
            stream = json.loads(probe.stdout)["streams"][0]
            self.assertEqual(stream["codec_name"], "h264")
            self.assertEqual(stream["profile"], "High")
            self.assertEqual(stream["pix_fmt"], "yuv420p")
            self.assertEqual((stream["width"], stream["height"]), (360, 640))
            self.assertEqual(stream["avg_frame_rate"], "24/1")


if __name__ == "__main__":
    unittest.main()
