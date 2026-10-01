import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from core.audio_mixer import AudioMixer
from core.product_manager import ProductManager
from core.subtitle_styles import SUBTITLE_ANIMATIONS, SUBTITLE_THEMES, random_animation, random_theme


class AudioMixerTests(unittest.TestCase):
    def test_random_music_plan_uses_smooth_8_to_12_second_cuts_without_adjacent_repeat(self):
        tracks = [
            {"file": f"music-{index}.mp3", "duration": 90 + index * 5}
            for index in range(1, 5)
        ]
        first = AudioMixer.build_music_plan(60, tracks, seed="DRAMA-1", max_segment_sec=12)
        second = AudioMixer.build_music_plan(60, tracks, seed="DRAMA-1", max_segment_sec=12)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 6)
        self.assertAlmostEqual(first[-1]["timeline_end"], 60, places=2)
        self.assertTrue(all(8 <= item["duration"] <= 12 for item in first))
        self.assertTrue(any(item["offset"] > 0 for item in first))
        self.assertTrue(all(left["file"] != right["file"] for left, right in zip(first, first[1:])))
        exposure = {}
        for item in first:
            exposure[item["file"]] = exposure.get(item["file"], 0) + item["duration"]
        self.assertLessEqual(max(exposure.values()) / sum(exposure.values()), 0.35)

    def test_audio_mix_v2_renders_one_second_crossfades_and_voice_ducking(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            mixer = AudioMixer()
            source = folder / "source.mp4"
            output = folder / "mixed.mp4"
            subprocess.run([
                str(mixer.ffmpeg), "-y", "-f", "lavfi", "-i", "color=c=black:s=320x568:r=24:d=25",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=25", "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
            ], check=True, capture_output=True)
            music = []
            for index, frequency in enumerate((180, 240, 320), 1):
                target = folder / f"music-{index}.wav"
                subprocess.run([
                    str(mixer.ffmpeg), "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=32",
                    "-c:a", "pcm_s16le", str(target),
                ], check=True, capture_output=True)
                music.append(target)
            plan = mixer.render(
                source, output, background_files=music, background_mode="auto",
                background_volume=.12, music_segment_max_sec=12, music_duck_ratio=.38,
                seed="DRAMA-AUDIO-V2",
            )
            self.assertTrue(output.is_file())
            self.assertEqual(plan["audio_mix_version"], 2)
            self.assertEqual(plan["music_unique_tracks"], 3)
            self.assertEqual(len(plan["music_plan"]), 3)
            self.assertTrue(all(8 <= item["duration"] <= 12 for item in plan["music_plan"]))
            self.assertEqual(plan["music_crossfade_sec"], 1.0)
            self.assertEqual(plan["music_warnings"], [])

    def test_locked_final_uses_fresh_windows_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            rendered = folder / ".final.mixing.mp4"
            final = folder / "final.mp4"
            rendered.write_bytes(b"new-video")
            final.write_bytes(b"locked-old-video")
            real_replace = __import__("os").replace

            def replace_with_locked_final(source, destination):
                if Path(destination) == final:
                    raise PermissionError(5, "Access is denied", str(destination))
                return real_replace(source, destination)

            with patch("core.audio_mixer.os.replace", side_effect=replace_with_locked_final):
                published = AudioMixer._replace_rendered_output(rendered, final, retries=2, delay=0)
            self.assertEqual(published.name, "final_windows.mp4")
            self.assertEqual(published.read_bytes(), b"new-video")
            self.assertEqual(final.read_bytes(), b"locked-old-video")

    def test_sfx_plan_is_sparse_and_capped(self):
        files = [Path("pop.mp3"), Path("click.mp3")]
        events = AudioMixer.build_sfx_events(range(1, 50), 50, files, min_interval=6, max_count=6, seed="job")
        self.assertLessEqual(len(events), 6)
        self.assertTrue(all(right["time"] - left["time"] >= 6 for left, right in zip(events, events[1:])))

    def test_reads_srt_cue_times(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "subtitle.srt"
            path.write_text("1\n00:00:01,500 --> 00:00:02,000\nทดสอบ\n\n2\n00:00:08,000 --> 00:00:09,000\nต่อไป\n", encoding="utf-8")
            self.assertEqual(AudioMixer.cue_times(path), [1.5, 8.0])

    def test_smartsub_theme_and_animation_catalogs_are_selectable(self):
        self.assertGreaterEqual(len(SUBTITLE_THEMES), 10)
        self.assertGreaterEqual(len(SUBTITLE_ANIMATIONS), 8)
        self.assertIn(random_theme()[0], SUBTITLE_THEMES)
        self.assertIn(random_animation(), SUBTITLE_ANIMATIONS)

    def test_product_job_saves_audio_plan_with_path_objects(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "สินค้า", "product_url": "https://shopee.co.th/product/1/2"})
            folder = manager.root / job["id"]
            source = folder / "videos" / "source.mp4"
            output = folder / "videos" / "final_with_audio.mp4"
            source.write_bytes(b"source")
            output.write_bytes(b"output")
            saved = manager.save_audio_mix_result(job["id"], output, source, {}, {"output": output, "music_plan": [{"file": Path("music.mp3")} ]})
            self.assertEqual(saved["audio_mix_status"], "ready")
            self.assertIsInstance(saved["audio_mix_plan"]["output"], str)


if __name__ == "__main__":
    unittest.main()
