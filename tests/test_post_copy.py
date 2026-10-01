import tempfile
import unittest
from pathlib import Path

from core.post_copy import hashtags, long_video_post_copy, post_ready_description
from core.story_manager import StoryManager


class PostCopyTests(unittest.TestCase):
    def test_long_video_keeps_audience_copy_and_topic_tags(self):
        description, tags = long_video_post_copy({
            "video_description": "ใครจะเป็นฝ่ายชนะเมื่อสองโลกมาพบกัน? #ข้ามจักรวาล",
            "hashtags": ["#ข้ามจักรวาล", "#โกโจ", "#ริก"],
        }, "โกโจพบกับริก")
        self.assertEqual(description, "ใครจะเป็นฝ่ายชนะเมื่อสองโลกมาพบกัน?")
        self.assertEqual(tags, "#ข้ามจักรวาล #โกโจ #ริก")

    def test_production_summary_is_not_published_and_missing_tags_are_filled(self):
        self.assertFalse(post_ready_description("ความยาวเป้าหมาย 300 วินาที จำนวน 38 ภาพ แบ่งเป็น 4 ชุด"))
        description, tags = long_video_post_copy({
            "video_description": "ความยาวเป้าหมาย 300 วินาที จำนวน 38 ภาพ แบ่งเป็น 4 ชุด",
            "hashtags": ["#วิเคราะห์"],
            "story_entities": [{"name": "โกโจ"}],
        }, "โกโจจะชนะได้อย่างไร")
        self.assertTrue(post_ready_description(description))
        self.assertIn("โกโจ", description)
        self.assertIn("#วิเคราะห์", tags)
        self.assertTrue(3 <= len(tags.split()) <= 6)

    def test_editor_tags_reject_invalid_or_wrong_count(self):
        self.assertEqual(hashtags("เรื่องเล่า #ตัวละคร #คลิปยาว", strict=True),
                         "#เรื่องเล่า #ตัวละคร #คลิปยาว")
        for bad in ("#เดียว", "#หนึ่ง #สอง #สาม #สี่ #ห้า #หก #เจ็ด", "#หนึ่ง #สอง #ผิด#ซ้อน"):
            with self.assertRaises(ValueError):
                hashtags(bad, strict=True)

    def test_new_long_job_requests_post_copy_and_tags_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create("เรื่องทดสอบคลิปยาว", long_video={"version": 2, "scene_count": 18})
            prompt = (Path(temp) / "workspace" / "stories" / job["id"] / "prompts" / "chatgpt_request.txt").read_text(encoding="utf-8")
            self.assertIn("คำอธิบายพร้อมโพสต์สำหรับผู้ชม", prompt)
            self.assertIn("ห้ามใส่เวลาเป้าหมาย", prompt)
            self.assertIn("hashtags เป็น array", prompt)
