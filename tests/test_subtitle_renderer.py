import tempfile
import re
import json
import subprocess
import unittest
from pathlib import Path

from fontTools.ttLib import TTFont

from core.product_manager import ProductManager
from core.subtitle_renderer import SubtitleVideoRenderer


class SubtitleRendererTests(unittest.TestCase):
    def test_escapes_windows_drive_for_ffmpeg_filter(self):
        escaped = SubtitleVideoRenderer._filter_path(Path("C:/Smart Post/subtitle.srt"))
        self.assertIn("C\\:/", escaped)

    def test_converts_rgb_and_opacity_to_ass_color(self):
        self.assertEqual(SubtitleVideoRenderer._ass_color("#FF0000"), "&H000000FF")
        self.assertEqual(SubtitleVideoRenderer._ass_color("#000000", 0.5), "&H80000000")
        with self.assertRaises(ValueError):
            SubtitleVideoRenderer._ass_color("red")

    def test_builds_real_animated_ass_from_srt(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = folder / "subtitle.srt"
            target = folder / "animated.ass"
            source.write_text("1\n00:00:00,000 --> 00:00:01,500\nบรรยากาศดี\n", encoding="utf-8")
            renderer = object.__new__(SubtitleVideoRenderer)
            renderer._animated_ass(
                source, target, "Prompt", 22, "#FFFFFF", "#FACC15", "#000000", 3,
                True, "#000000", 0.5, "bottom", 72, "wordPop",
            )
            result = target.read_text(encoding="utf-8-sig")
            self.assertIn("\\fscx76", result)
            self.assertIn("Dialogue:", result)
            self.assertIn("บรรยากาศดี", result)
            self.assertIn("PlayResX: 720", result)
            self.assertIn("PlayResY: 1280", result)
            self.assertIn("Style: SmartPost,Prompt,22,", result)
            self.assertIn(r"\xbord8.5\ybord4", result)

    def test_background_box_uses_independent_padding_without_scaling_thai_text(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = folder / "subtitle.srt"
            target = folder / "animated.ass"
            source.write_text("1\n00:00:00,000 --> 00:00:01,500\nหลังรอบนี้\n", encoding="utf-8")
            renderer = object.__new__(SubtitleVideoRenderer)
            renderer._animated_ass(
                source, target, "Kanit", 22, "#FFFFFF", "#FACC15", "#000000", 2,
                True, "#000000", 1.0, "center", 0, "none",
                letter_spacing=0, position_y_percent=90, font_embedded_bold=True,
            )
            result = target.read_text(encoding="utf-8-sig")
            self.assertIn("Style: SmartPost,Kanit,22,", result)
            self.assertIn(r"\xbord8.5\ybord4", result)
            self.assertIn(r"\pos(360,1152)", result)
            self.assertIn(",0,0,0,0,100,100,0.0,0,3,", result)

    def test_thai_mark_font_moves_tone_marks_without_scaling_the_line(self):
        source = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "smartsubai" / "Kanit-Bold.ttf"
        adjusted = SubtitleVideoRenderer._thai_mark_font(source, 14)
        self.assertTrue(adjusted.is_file())
        self.assertNotEqual(adjusted.resolve(), source.resolve())
        source_font = TTFont(str(source))
        adjusted_font = TTFont(str(adjusted))
        glyph = source_font.getBestCmap()[0x0E49]
        source_y = source_font["glyf"][glyph].yMin
        adjusted_y = adjusted_font["glyf"][glyph].yMin
        self.assertGreater(adjusted_y, source_y)

    def test_karaoke_splits_syllables_without_orphan_marks(self):
        result = SubtitleVideoRenderer._karaoke_text("บรรยากาศ", 1.5)
        self.assertIn("บรร", result)
        self.assertIn("กาศ", result)
        visible = re.sub(r"\{[^}]+\}", "", result)
        self.assertEqual(visible, "บรรยากาศ")

    def test_preview_video_matches_final_encoding_contract(self):
        font = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "smartsubai" / "Kanit-Bold.ttf"
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "preview.mp4"
            renderer = SubtitleVideoRenderer("")
            renderer.render_preview_video(
                target,
                text="นี่คือพรีวิวข้อความภาษาไทย",
                font_path=str(font),
                font_name="Kanit",
                font_size=48,
                thai_mark_gap=14,
                background_enabled=True,
                background_opacity=1.0,
                position_y_percent=72,
                animation="wordPop",
            )
            result = subprocess.run(
                [str(renderer.ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,pix_fmt,width,height,r_frame_rate", "-of", "json", str(target)],
                capture_output=True, text=True, check=True,
            )
            stream = json.loads(result.stdout)["streams"][0]
            self.assertEqual(stream["codec_name"], "h264")
            self.assertEqual(stream["pix_fmt"], "yuv420p")
            self.assertEqual((stream["width"], stream["height"]), (720, 1280))
            self.assertEqual(stream["r_frame_rate"], "30/1")

    def test_product_job_promotes_subtitled_video(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "สินค้า", "product_url": "https://shopee.co.th/product/12/34"})
            folder = manager.root / job["id"]
            source = folder / "videos" / "source.mp4"
            output = folder / "videos" / "final_with_subtitles.mp4"
            subtitle = folder / "captions" / "subtitle.srt"
            source.write_bytes(b"video-source")
            output.write_bytes(b"video-output")
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nทดสอบ\n", encoding="utf-8")
            style = {"font_path": "assets/fonts/user/test.ttf", "font_size": 30}
            saved = manager.save_subtitled_video(job["id"], output, source, subtitle, style)
            self.assertEqual(saved["subtitle_video_status"], "ready")
            self.assertEqual(saved["video_path"], "videos\\final_with_subtitles.mp4")
            self.assertEqual(saved["video_without_subtitle_path"], "videos\\source.mp4")
            self.assertEqual(saved["video_without_audio_mix_path"], "videos\\final_with_subtitles.mp4")
            self.assertEqual(saved["subtitle_style"], style)
            rerender = manager.mark_subtitle_video_needs_render(job["id"])
            self.assertEqual(rerender["subtitle_video_status"], "needs_render")


if __name__ == "__main__":
    unittest.main()
