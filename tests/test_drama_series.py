import json
import base64
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from core.drama_series import DramaSeriesManager
from core.story_manager import StoryManager


class DramaSeriesTests(unittest.TestCase):
    @staticmethod
    def _encoded_scene(color):
        buffer = BytesIO()
        Image.new("RGB", (180, 320), color).save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def test_episode_two_reuses_character_and_previous_episode_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            portrait = root / "portrait.png"
            Image.new("RGB", (180, 320), "#345678").save(portrait)
            manager = DramaSeriesManager(root)
            series = manager.create(
                "ร้านกาแฟแห่งคำสัญญา",
                "คนสองคนกลับมาเจอกันอีกครั้ง",
                3,
                8,
                "chatgpt",
                [{"name": "นที", "role": "ตัวละครหลัก", "description": "ชายผมดำ เสื้อเชิ้ตสีครีม", "image": str(portrait), "voice_reference_id": "preset:male"}],
            )
            first = manager.episode_context(series["id"], 1)
            self.assertEqual(first["episode_no"], 1)
            self.assertEqual(len(first["source_images"]), 1)
            self.assertEqual(first["characters"][0]["voice_reference_id"], "preset:male")

            story_folder = root / "story-result"
            (story_folder / "generated").mkdir(parents=True)
            Image.new("RGB", (180, 320), "#995533").save(story_folder / "generated" / "scene_01.png")
            Image.new("RGB", (180, 320), "#225577").save(story_folder / "generated" / "scene_08.png")
            story = {
                "id": "STORY-TEST",
                "series_id": series["id"],
                "episode_no": 1,
                "video_title": "EP หนึ่ง",
                "episode_summary": "นทีกลับมาที่ร้านเก่า",
                "next_episode_hook": "พบจดหมายปริศนา",
                "visual_bible": {"palette": "warm"},
                "continuity_state": {"prop": "sealed letter"},
                "generated_images": ["generated/scene_01.png", "generated/scene_08.png"],
                "_folder": str(story_folder),
            }
            manager.update_from_story(story)
            second = manager.episode_context(series["id"], 2)
            self.assertIn("นทีกลับมาที่ร้านเก่า", second["story_text"])
            self.assertIn("พบจดหมายปริศนา", second["story_text"])
            self.assertEqual(second["visual_bible"], {"palette": "warm"})
            self.assertEqual(len(second["source_images"]), 3)

    def test_drama_story_request_locks_character_and_ep_continuity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            portrait = root / "portrait.png"
            Image.new("RGB", (180, 320), "#334455").save(portrait)
            stories = StoryManager(root)
            job = stories.create(
                "ความลับในคืนฝนตก • EP 2",
                "ให้ต่อจากจดหมายที่พบ",
                scene_count=6,
                image_ai_provider="gemini",
                job_type="drama_episode",
                source_images=[str(portrait)],
                series_context={
                    "series_id": "SERIES-20260828-ABCDEF",
                    "series_title": "ความลับในคืนฝนตก",
                    "episode_no": 2,
                    "episode_count": 4,
                    "characters": [
                        {"name": "พริม", "role": "ตัวละครหลัก", "description": "ผมยาว เสื้อกันฝนสีแดง"},
                        {"name": "ชายแปลกหน้า", "role": "ตัวละครร่วม", "description": "ชายผู้ส่งกุญแจ"},
                    ],
                    "previous_episode_summary": "พริมพบกุญแจ",
                    "previous_episode_hook": "มีคนเคาะประตู",
                },
            )
            folder = stories.root / job["id"]
            prompt = (folder / "prompts" / "chatgpt_request.txt").read_text(encoding="utf-8")
            request = json.loads((folder / "ai_request.json").read_text(encoding="utf-8"))
            self.assertEqual(job["job_type"], "drama_episode")
            self.assertEqual(job["episode_no"], 2)
            self.assertIn("CHARACTER BIBLE", prompt)
            self.assertIn("ห้ามเปลี่ยนคน", prompt)
            self.assertIn("พริมพบกุญแจ", prompt)
            self.assertEqual(request["story_mode"], "drama_episode")
            self.assertIn("continuity_state", request["required_fields"])
            self.assertIn("dialogue_turns", request["required_fields"])

            result = stories.apply_ai_result({
                "job_id": job["id"],
                "video_title": "ความลับในคืนฝนตก EP สอง",
                "video_description": "พริมต้องตัดสินใจเปิดประตู",
                "episode_title": "เสียงเคาะประตู",
                "episode_summary": "พริมพบผู้ส่งกุญแจ",
                "next_episode_hook": "กล่องที่ล็อกไว้เริ่มมีเสียง",
                "narration_script": "พริมถามว่า ใครอยู่หน้าประตู ชายแปลกหน้าตอบว่า ผมนำความจริงมาให้",
                "visual_bible": {"wardrobe": "เสื้อกันฝนสีแดง"},
                "story_entities": [
                    {"id": "prim", "name": "พริม", "aliases": [], "visual_identity": "ผมยาว เสื้อกันฝนสีแดง"},
                    {"id": "stranger", "name": "ชายแปลกหน้า", "aliases": [], "visual_identity": "ชายผู้ส่งกุญแจ"},
                ],
                "scene_entities": [["prim", "stranger"] for _ in range(6)],
                "continuity_state": {"key": "อยู่ในมือพริม"},
                "dialogue_turns": [
                    {"speaker": "พริม", "text": "ใครอยู่หน้าประตู", "emotion": "fearful", "pause_after": 0.5},
                    {"speaker": "ชายแปลกหน้า", "text": "ผมนำความจริงมาให้", "emotion": "normal", "pause_after": 0.4},
                ],
                "scene_narrations": [f"ฉาก {number}" for number in range(1, 7)],
                "scene_prompts": [f"พริมกับชายแปลกหน้าที่หน้าประตู ฉาก {number}" for number in range(1, 7)],
                "scene_durations": [4] * 6,
                "generated_images": [self._encoded_scene((number * 30, 40, 80)) for number in range(1, 7)],
            })
            self.assertEqual(result["episode_summary"], "พริมพบผู้ส่งกุญแจ")
            self.assertEqual(result["continuity_state"]["key"], "อยู่ในมือพริม")
            self.assertGreaterEqual(len(result["dialogue_turns"]), 2)
            self.assertIn("กดหัวใจ", result["dialogue_turns"][-1]["text"])

    def test_completed_series_can_append_one_open_ended_episode(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            series = manager.create(
                "ร้านกาแฟแห่งคำสัญญา", "มินกับนทีช่วยกันเปิดร้าน", 1, 8, "chatgpt",
                [{"name": "มิน", "description": "หญิงไทยผมประบ่า เสื้อสีน้ำเงิน"}],
            )
            manager.mark_episode_ready({
                "series_id": series["id"], "episode_no": 1,
                "episode_summary": "ทั้งคู่เปิดร้านสำเร็จ", "next_episode_hook": "มีจดหมายมาถึงร้าน",
            })
            appended = manager.append_episode(
                series["id"], "หนึ่งปีต่อมา ลูกค้าคนหนึ่งนำความลับกลับมา", "gemini", 6,
            )
            self.assertEqual(appended["episode"]["episode_no"], 2)
            self.assertTrue(appended["episode"]["open_ended"])
            context = manager.episode_context(series["id"], 2)
            self.assertEqual(context["provider"], "gemini")
            self.assertEqual(context["scene_count"], 6)
            self.assertTrue(context["open_ended"])
            self.assertIn("ทั้งคู่เปิดร้านสำเร็จ", context["story_text"])
            self.assertIn("หนึ่งปีต่อมา", context["story_text"])

    def test_cannot_append_while_existing_episode_is_unfinished(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            series = manager.create("เรื่องทดสอบ", "", 1, 6, "chatgpt", [{"name": "เอ"}])
            with self.assertRaisesRegex(ValueError, "EP 1"):
                manager.append_episode(series["id"])

    def test_successful_checkpoint_retry_clears_stale_episode_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            series = manager.create("เรื่องทดสอบ", "", 1, 6, "chatgpt", [{"name": "เอ"}])
            manager.mark_episode_failed(series["id"], 1, "Gemini Web timeout")
            manager.mark_episode_ready({
                "series_id": series["id"], "episode_no": 1,
                "episode_summary": "กู้จาก checkpoint สำเร็จ",
            }, "final.mp4")
            completed = manager.get(series["id"])["episodes"][0]
            self.assertEqual(completed["status"], "completed")
            self.assertNotIn("error", completed)

    def test_failed_episode_can_be_reset_inside_same_series_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            series = manager.create("เรื่องทดสอบ", "", 2, 6, "chatgpt", [{"name": "เอ"}])
            manager.mark_episode_failed(series["id"], 1, "เปิดเว็บไม่สำเร็จ")
            snapshot = manager.snapshot()
            self.assertEqual(snapshot["active_count"], 0)
            self.assertEqual(snapshot["needs_attention_count"], 1)
            reset = manager.reset_episode_for_retry(series["id"], 1)
            self.assertEqual(reset["series"]["id"], series["id"])
            self.assertEqual(reset["episode"]["status"], "queued")
            self.assertEqual(reset["episode"]["retry_count"], 1)
            self.assertIn("เปิดเว็บไม่สำเร็จ", reset["episode"]["previous_error"])

    def test_cancel_series_keeps_completed_episode_and_prevents_late_error_resurrection(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            series = manager.create("เรื่องเก่า", "", 3, 6, "chatgpt", [{"name": "เอ"}])
            manager.mark_episode_ready({"series_id": series["id"], "episode_no": 1}, "ep1.mp4")
            manager.mark_episode_failed(series["id"], 2, "เว็บตอบกลับไม่สำเร็จ")
            result = manager.cancel_series(series["id"])
            self.assertEqual(result["cancelled"], 2)
            current = manager.get(series["id"])
            self.assertEqual(current["status"], "cancelled")
            self.assertEqual([item["status"] for item in current["episodes"]], ["completed", "cancelled", "cancelled"])
            manager.mark_episode_failed(series["id"], 2, "ผลลัพธ์มาถึงช้า")
            self.assertEqual(manager.get(series["id"])["status"], "cancelled")
            self.assertEqual(manager.get(series["id"])["episodes"][1]["status"], "cancelled")

    def test_next_episode_defaults_to_last_successful_image_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            series = manager.create("เรื่องทดสอบ", "", 1, 6, "chatgpt", [{"name": "เอ"}])
            manager.mark_episode_ready({
                "series_id": series["id"], "episode_no": 1,
                "image_ai_provider": "gemini", "episode_summary": "จบตอนแรก",
            })
            appended = manager.append_episode(series["id"])
            self.assertEqual(appended["series"]["last_successful_provider"], "gemini")
            self.assertEqual(manager.episode_context(series["id"], 2)["provider"], "gemini")

    def test_plot_board_and_cover_theme_are_locked_into_every_episode(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            board = [
                {"summary": "นทีพบจดหมาย", "hook": "เสียงเคาะประตู"},
                {"summary": "เปิดเผยเจ้าของจดหมาย", "hook": "ปิดเรื่อง"},
            ]
            series = manager.create(
                "จดหมายคืนฝนตก", "ความลับจากอดีต", 2, 8, "gemini",
                [{"name": "นที", "description": "ชายผมดำ"}],
                plot_board=board, cover_theme="thriller",
            )
            self.assertEqual(series["cover_theme"], "thriller")
            self.assertEqual(series["episodes"][0]["planned_summary"], "นทีพบจดหมาย")
            context = manager.episode_context(series["id"], 2)
            self.assertEqual(context["planned_episode"]["summary"], "เปิดเผยเจ้าของจดหมาย")
            self.assertEqual(context["cover_theme"], "thriller")
            self.assertIn("พล็อตที่อนุมัติ", context["story_text"])

    def test_episode_summary_tracks_validation_timing_and_retry_totals(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            series = manager.create("เรื่องทดสอบ", "", 1, 6, "chatgpt", [{"name": "เอ"}])
            manager.attach_story_job(series["id"], 1, "STORY-ONE")
            completed = manager.mark_episode_ready({
                "id": "STORY-ONE",
                "series_id": series["id"], "episode_no": 1,
                "episode_summary": "จบครบ", "auto_recovery_total": 2,
                "continuity_validation": {"status": "passed", "score": 94, "warnings": []},
            }, "final.mp4")
            episode = completed["episodes"][0]
            self.assertEqual(episode["automation_retry_count"], 2)
            self.assertEqual(episode["continuity_validation"]["score"], 94)
            self.assertGreaterEqual(episode["duration_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
