import base64
import json
import logging
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from PIL import Image

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.story_manager import StoryManager
from core.story_finisher import _subtitle_script
from core.story_script import clean_dialogue_turn_text, spoken_script_for_job


class StoryModeTests(unittest.TestCase):
    def test_story_voice_queue_checkpoint_survives_status_poll_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create("เรื่องทดสอบคิวเสียง", scene_count=6)

            saved = manager.save_voice_checkpoint(
                job["id"], external_job_id="TTS-SAVED-ONE",
                reference_id="custom:voice-one", status="queued",
            )
            reloaded = manager.get(job["id"])

            self.assertEqual(saved["voice_status"], "queued")
            self.assertEqual(reloaded["voice_job_id"], "TTS-SAVED-ONE")
            self.assertEqual(reloaded["voice_reference_id"], "custom:voice-one")

    def test_story_voice_terminal_retry_revision_is_persisted_before_resubmit(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create("เรื่องทดสอบคิวเสียงหาย", scene_count=6)
            manager.save_voice_checkpoint(
                job["id"], external_job_id="TTS-BROKEN",
                reference_id="custom:voice-one", status="queued",
            )

            updated = manager.prepare_voice_resubmit(
                job["id"], "TTS-BROKEN",
                "[Errno 2] No such file or directory: temporary.wav",
            )

            self.assertEqual(updated["voice_resubmit_count"], 1)
            self.assertEqual(updated["voice_job_id"], "")
            self.assertEqual(updated["voice_status"], "resubmitting")
            self.assertEqual(updated["voice_resubmit_history"][-1]["failed_job_id"], "TTS-BROKEN")
            with self.assertRaisesRegex(ValueError, "ครบจำนวนที่ปลอดภัย"):
                manager.prepare_voice_resubmit(job["id"], "TTS-BROKEN-AGAIN", "ยังผิดพลาด")

    def test_drama_voice_script_never_reads_production_speaker_labels(self):
        job = {
            "job_type": "drama_episode",
            "narration_script": "ผู้บรรยาย: ฝนตก ทองดี: เข้ามาหลบก่อน",
            "character_bible": [{"name": "ทองดี"}],
            "dialogue_turns": [
                {"speaker": "ผู้บรรยาย", "text": "ผู้บรรยาย: ฝนตก", "pause_after": 0.4},
                {"speaker": "ทองดี", "text": "ทองดี: เข้ามาหลบก่อน", "pause_after": 0.5},
            ],
        }
        script = spoken_script_for_job(job, include_pauses=True)
        self.assertEqual(script, "ฝนตก [pause:0.4] เข้ามาหลบก่อน [pause:0.5]")
        self.assertNotIn("ผู้บรรยาย", script)
        self.assertNotIn("ทองดี:", script)
        self.assertEqual(clean_dialogue_turn_text(job["dialogue_turns"][0]), "ฝนตก")

    def test_drama_ai_result_persists_clean_spoken_script_without_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = StoryManager(root)
            job = manager.create(
                "คืนฝนตก", scene_count=6, job_type="drama_episode",
                series_context={
                    "series_id": "SERIES-TEST",
                    "characters": [{"name": "ทองดี", "description": "สุนัขสีน้ำตาล"}],
                },
            )
            image = root / "scene.png"
            Image.new("RGB", (864, 1536), "navy").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            result = manager.apply_ai_result({
                "job_id": job["id"],
                "video_title": "คืนฝนตก",
                "video_description": "ละครสั้นอบอุ่น",
                "narration_script": "ผู้บรรยาย: ฝนตก ทองดี: เข้ามาหลบก่อน",
                "dialogue_turns": [
                    {"speaker": "ผู้บรรยาย", "text": "ผู้บรรยาย: ฝนตก", "pause_after": 0.4},
                    {"speaker": "ทองดี", "text": "ทองดี: เข้ามาหลบก่อน", "pause_after": 0.5},
                ],
                "visual_bible": {"tone": "อบอุ่น"},
                "story_entities": [{"id": "thongdee", "name": "ทองดี", "aliases": [], "visual_identity": "สุนัขสีน้ำตาล"}],
                "scene_entities": [["thongdee"] for _ in range(6)],
                "scene_prompts": [f"ทองดีอยู่ในฉาก {index}" for index in range(6)],
                "scene_narrations": [f"ฉาก {index}" for index in range(6)],
                "scene_durations": [4] * 6,
                "generated_images": [encoded] * 6,
            })
            self.assertTrue(result["narration_script"].startswith("ฝนตก เข้ามาหลบก่อน"))
            self.assertIn("กดหัวใจ", result["narration_script"])
            self.assertEqual(result["dialogue_turns"][0]["text"], "ฝนตก")
            self.assertNotIn("ผู้บรรยาย", (manager.root / job["id"] / "captions" / "narration_script.txt").read_text(encoding="utf-8"))

    def test_drama_subtitles_use_spoken_turn_text_without_speaker_labels(self):
        text, source = _subtitle_script({
            "job_type": "drama_episode",
            "narration_script": "มิน: สวัสดี นที: สวัสดีครับ",
            "dialogue_turns": [
                {"speaker": "มิน", "text": "สวัสดี"},
                {"speaker": "นที", "text": "สวัสดีครับ"},
            ],
        })
        self.assertEqual(text, "สวัสดี สวัสดีครับ")
        self.assertEqual(source, "exact_drama_dialogue_turns")
        self.assertNotIn("มิน:", text)

    def test_story_subtitles_use_same_thai_reading_as_voice(self):
        text, source = _subtitle_script({
            "job_type": "story_short",
            "narration_script": "Doctor Doom Supreme มีพลังเหนือใคร",
        })

        self.assertEqual(text, "ด็อกเตอร์ ดูม ซูพรีม มีพลังเหนือใคร")
        self.assertEqual(source, "exact_chatgpt_narration_script")

    def test_story_job_accepts_topic_or_text_and_keeps_mode_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = StoryManager(root)
            with self.assertRaises(ValueError):
                manager.create()
            main = root / "main.png"
            Image.new("RGB", (32, 48), "navy").save(main)
            job = manager.create("แมวหลงทาง", "แมวออกตามหาเจ้าของ", main, 6)
            self.assertTrue(job["id"].startswith("STORY-"))
            self.assertEqual(job["job_type"], "story_short")
            self.assertEqual(job["video_source_type"], "story_image_sequence")
            package = manager.plugin_request(job["id"])
            self.assertEqual(package["mode"], "story")
            self.assertIn("video_title", package["prompt"])
            self.assertIn("ห้ามเหลือตัวอักษร A-Z", package["prompt"])
            self.assertIn("ด็อกเตอร์ ดูม ซูพรีม", package["prompt"])
            self.assertEqual(package["request"]["image_count"], 6)

            encoded = base64.b64encode(main.read_bytes()).decode()
            result = manager.apply_ai_result({
                "job_id": job["id"],
                "video_title": "คืนที่แมวไม่ยอมแพ้",
                "video_description": "เรื่องสั้นอบอุ่นหัวใจ #เรื่องเล่า",
                "narration_script": "คืนนั้น เจ้าแมวตัวเล็กออกเดินทางตามหาเจ้าของ",
                "visual_bible": {"character": "แมวสีขาวปลอกคอสีน้ำเงิน"},
                "story_entities": [], "scene_entities": [[] for _ in range(6)],
                "scene_prompts": [f"ฉากต่อเนื่อง {index}" for index in range(6)],
                "scene_narrations": [f"เหตุการณ์ตอนที่ {index}" for index in range(6)],
                "scene_durations": [4] * 6,
                "generated_images": [encoded] * 6,
            })
            self.assertEqual(result["ai_status"], "ready")
            self.assertEqual(len(result["generated_images"]), 6)
            self.assertTrue(result["image_generation_via_chatgpt_web"])
            self.assertFalse(result["image_generation_via_gemini_web"])
            self.assertIn("กดหัวใจ", result["narration_script"])
            self.assertIn("คอมเมนต์", result["narration_script"])
            self.assertEqual((manager.root / job["id"] / "captions" / "video_title.txt").read_text(encoding="utf-8"), "คืนที่แมวไม่ยอมแพ้")

            covered = manager.ensure_story_cover(job["id"])
            cover = manager.root / job["id"] / covered["cover_path"]
            self.assertTrue(cover.is_file())
            self.assertEqual(covered["cover_status"], "ready")
            self.assertEqual(covered["cover_size"], [1080, 1920])
            with Image.open(cover) as opened:
                self.assertEqual(opened.size, (1080, 1920))

            gemini_job = manager.create("เรื่องจาก Gemini", scene_count=6, image_ai_provider="gemini")
            self.assertEqual(gemini_job["image_ai_provider"], "gemini")
            self.assertEqual(manager.plugin_request(gemini_job["id"])["job"]["image_ai_provider"], "gemini")

    def test_story_bridge_package_and_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            products = ProductManager(root)
            stories = StoryManager(root)
            job = stories.create("ตำนานป่าลึกลับ", "", scene_count=6)
            bridge = LocalBridge("127.0.0.1", 0, products, logging.getLogger("story-bridge"), stories=stories).start()
            port = bridge.server.server_address[1]
            try:
                package = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stories/{job['id']}/chatgpt-package"))["package"]
                self.assertEqual(package["mode"], "story")
                self.assertEqual(package["image_urls"], [])
                command = bridge.queue_extension_command("open_story_chatgpt", job["id"])
                self.assertEqual(command["action"], "open_story_chatgpt")
                cancelled = bridge.queue_extension_command("cancel_story_chatgpt", job["id"])
                self.assertEqual(cancelled["action"], "cancel_story_chatgpt")
                image = root / "scene.png"
                Image.new("RGB", (32, 48), "purple").save(image)
                encoded = base64.b64encode(image.read_bytes()).decode()
                payload = json.dumps({
                    "job_id": job["id"], "video_title": "ชื่อคลิป", "video_description": "คำอธิบาย",
                    "run_id": command["run_id"],
                    "narration_script": "กาลครั้งหนึ่งมีป่าลึกลับ", "scene_prompts": [f"ฉาก {i}" for i in range(6)],
                    "story_entities": [], "scene_entities": [[] for _ in range(6)],
                    "scene_narrations": [f"ตอน {i}" for i in range(6)], "scene_durations": [3] * 6,
                    "generated_images": [encoded] * 6,
                }).encode()
                request = urllib.request.Request(f"http://127.0.0.1:{port}/api/stories/result", data=payload, headers={"Content-Type": "application/json"}, method="POST")
                saved = json.load(urllib.request.urlopen(request))["job"]
                self.assertEqual(saved["status"], "ready_to_render")
                self.assertEqual(saved["video_source_type"], "story_image_sequence")
            finally:
                bridge.stop()

    def test_story_google_flow_package_bridge_and_clip_checkpoints(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            products = ProductManager(root)
            stories = StoryManager(root)
            job = stories.create(
                "หมาตัวเล็กช่วยคนจากไฟไหม้", scene_count=6,
                video_generation_mode="google_flow",
            )
            image = root / "scene.png"
            Image.new("RGB", (64, 96), "orange").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            saved = stories.apply_ai_result({
                "job_id": job["id"], "video_title": "ฮีโร่ตัวเล็ก", "video_description": "เรื่องสั้น",
                "narration_script": "หมาตัวเล็กวิ่งฝ่าควันเพื่อช่วยทุกคน",
                "story_entities": [], "scene_entities": [[] for _ in range(6)],
                "scene_prompts": [f"ฉากไฟไหม้ต่อเนื่อง {index}" for index in range(1, 7)],
                "scene_narrations": [f"เหตุการณ์ฉาก {index}" for index in range(1, 7)],
                "scene_durations": [4] * 6, "generated_images": [encoded] * 6,
            })
            self.assertEqual(saved["video_generation_mode"], "google_flow")
            self.assertEqual(saved["video_source_type"], "google_flow_pending")
            package = stories.flow_package(job["id"], 2)
            self.assertEqual(package["shot_index"], 2)
            self.assertEqual(package["shot_count"], 6)
            self.assertIn("SCENE 2 OF 6", package["video_prompt"])
            self.assertEqual(len(package["image_files"]), 1)
            unverified_fallback = root / "unverified-fallback.mp4"
            unverified_fallback.write_bytes(b"unverified-local-motion" * 100)
            with self.assertRaisesRegex(ValueError, "action=local_motion_fallback"):
                stories.attach_flow_fallback_clip(job["id"], 3, unverified_fallback)

            bridge = LocalBridge("127.0.0.1", 0, products, logging.getLogger("story-flow-bridge"), stories=stories).start()
            port = bridge.server.server_address[1]
            try:
                bridged = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/jobs/{job['id']}/flow-package?shot_index=2"
                ))["package"]
                self.assertEqual(bridged["mode"], "story")
                self.assertEqual(len(bridged["image_urls"]), 1)
                self.assertGreater(len(urllib.request.urlopen(bridged["image_urls"][0]).read()), 50)
                command = bridge.queue_extension_command("open_flow", job["id"], 2)
                self.assertEqual(command["shot_index"], 2)
            finally:
                bridge.stop()

            first_clip = root / "first.mp4"
            second_clip = root / "second.mp4"
            first_clip.write_bytes(b"first-story-flow-video" * 100)
            second_clip.write_bytes(b"second-story-flow-video" * 100)
            checkpoint = stories.attach_flow_clip(job["id"], 1, first_clip)
            self.assertEqual(checkpoint["flow_clip_count"], 1)
            self.assertEqual(checkpoint["video_status"], "collecting_clips")
            with self.assertRaisesRegex(ValueError, "ซ้ำกับฉาก 1"):
                stories.attach_flow_clip(job["id"], 2, first_clip)
            checkpoint = stories.attach_flow_clip(job["id"], 2, second_clip)
            self.assertEqual(checkpoint["flow_clip_count"], 2)

    def test_story_flow_reframes_harm_sensitive_scene_without_changing_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create("หมาช่วยหลวงตา", scene_count=6, video_generation_mode="google_flow")
            image = root / "scene.png"
            Image.new("RGB", (64, 96), "brown").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            stories.apply_ai_result({
                "job_id": job["id"],
                "video_title": "หมาช่วยหลวงตา",
                "video_description": "เรื่องอบอุ่น",
                "narration_script": "หมาเข้าไปดูหลวงตา",
                "story_entities": [], "scene_entities": [[] for _ in range(6)],
                "scene_prompts": ["an elderly monk collapsed unconscious on the wooden floor"] * 6,
                "scene_narrations": ["พบหลวงตานอนแน่นิ่งอยู่บนพื้นไม้"] * 6,
                "scene_durations": [5] * 6,
                "generated_images": [encoded] * 6,
            })

            package = stories.flow_package(job["id"], 1)

            self.assertNotIn("collapsed unconscious", package["video_prompt"].lower())
            self.assertNotIn("นอนแน่นิ่ง", package["video_prompt"])
            self.assertIn("resting weakly but safely", package["video_prompt"])
            self.assertIn("family-friendly wellness-check", package["video_prompt"])
            for blocked in ("blood", "violence", "threat", "distress"):
                self.assertNotIn(blocked, package["video_prompt"].lower())
            self.assertEqual(package["warnings"], ["flow_prompt_safety_reframed"])
            self.assertEqual(package["image_files"], ["generated\\scene_01.png"])

    def test_story_flow_first_structured_policy_terminal_requests_local_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create(
                "Elon Musk กับอนาคตพลังงาน",
                scene_count=6,
                video_generation_mode="google_flow",
            )

            def encoded_image(name, color):
                path = root / name
                Image.new("RGB", (64, 96), color).save(path)
                return base64.b64encode(path.read_bytes()).decode()

            first_images = [
                encoded_image(f"original-{index}.png", color)
                for index, color in enumerate(("red", "green", "blue", "orange", "purple", "navy"), 1)
            ]
            prompts = [f"cinematic environment foreground city block {index}" for index in range(1, 7)]
            prompts[3] = (
                "Elon Musk standing on a balcony, foreground solar arrays, "
                "midground wind turbines, background city energy storage"
            )
            base_result = {
                "job_id": job["id"],
                "video_title": "Elon Musk กับศูนย์พลังงานอนาคต",
                "video_description": "เรื่องเล่าจากข้อมูลผู้ใช้",
                "narration_script": "เขามองไปยังโครงสร้างพลังงานที่อยู่ตรงหน้า",
                "story_entities": [], "scene_entities": [[] for _ in range(6)],
                "visual_bible": {
                    "locations": "future energy center with solar arrays and wind turbines",
                    "tone": "hopeful blue-gold",
                    "lighting": "sunrise",
                },
                "scene_prompts": prompts,
                "scene_narrations": [f"เหตุการณ์ฉาก {index}" for index in range(1, 7)],
                "scene_durations": [4] * 6,
                "generated_images": first_images,
            }
            stories.apply_ai_result(base_result)
            original_package = stories.flow_package(job["id"], 4)
            folder = stories.root / job["id"]
            canonical = folder / "generated" / "scene_04.png"
            original_image_hash = stories._sha256_file(canonical)

            first = stories.register_flow_policy_failure(
                job["id"], 4, "FLOW_POLICY_BLOCKED: celebrity face",
                flow_run_id="RUN-ORIGINAL", failure_card_fingerprint="CARD-SAME-TEXT",
            )

            self.assertEqual(first["action"], "local_motion_fallback")
            self.assertEqual(first["attempt"], 1)
            first_record = first["record"]
            self.assertEqual(first_record["prompt_sha256"], stories._sha256_text(original_package["video_prompt"]))
            self.assertEqual(len(first_record["image_sha256"]), 64)
            self.assertTrue(canonical.is_file())
            self.assertEqual(stories._sha256_file(canonical), original_image_hash)
            checkpoint = stories.plugin_request(job["id"])
            self.assertIn("generated\\scene_04.png", checkpoint["checkpoint_images"])
            self.assertEqual(first["job"]["flow_prompt_retries"], {})
            self.assertEqual(first["job"]["flow_prompt_profiles"], {})
            with self.assertRaisesRegex(ValueError, "FLOW_POLICY_LOCAL_FALLBACK_CHECKPOINT"):
                stories.flow_package(job["id"], 4)
            rejected_real_clip = root / "rejected-real-flow.mp4"
            rejected_real_clip.write_bytes(b"must-not-supersede-policy" * 100)
            with self.assertRaisesRegex(ValueError, "ห้ามใช้คลิป Google Flow ทับ"):
                stories.attach_flow_clip(job["id"], 4, rejected_real_clip)

            duplicate = stories.register_flow_policy_failure(
                job["id"], 4, "same terminal status delivered again",
                flow_run_id="RUN-ORIGINAL", failure_card_fingerprint="CARD-SAME-TEXT",
            )
            self.assertEqual(duplicate["attempt"], 1)
            self.assertEqual(duplicate["action"], "duplicate_policy_event")
            self.assertEqual(duplicate["duplicate_reason"], "same_run_and_failure_card")
            self.assertEqual(
                len(stories.get(job["id"])["flow_policy_failure_history"]["4"]), 1,
            )

            same_pair_new_run = stories.register_flow_policy_failure(
                job["id"], 4, "FLOW_POLICY_BLOCKED: public figure likeness",
                flow_run_id="RUN-OTHER", failure_card_fingerprint="CARD-OTHER",
            )
            self.assertEqual(same_pair_new_run["action"], "duplicate_policy_event")
            self.assertEqual(same_pair_new_run["duplicate_reason"], "same_image_and_prompt")
            history = stories.get(job["id"])["flow_policy_failure_history"]["4"]
            self.assertEqual(len(history), 1)
            self.assertTrue(canonical.is_file())

    def test_story_flow_hybrid_checkpoint_keeps_real_and_local_sources_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create(
                "ทดสอบ Flow hybrid",
                scene_count=6,
                video_generation_mode="google_flow",
            )
            image = root / "scene.png"
            Image.new("RGB", (64, 96), "teal").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            stories.apply_ai_result({
                "job_id": job["id"],
                "video_title": "เรื่องทดสอบ",
                "video_description": "ทดสอบแหล่งที่มา",
                "narration_script": "เรื่องทดสอบเดินไปทีละฉาก",
                "story_entities": [], "scene_entities": [[] for _ in range(6)],
                "scene_prompts": [f"ฉาก {index}" for index in range(1, 7)],
                "scene_narrations": [f"เหตุการณ์ {index}" for index in range(1, 7)],
                "scene_durations": [4] * 6,
                "generated_images": [encoded] * 6,
            })

            for shot_index in (1, 2, 3, 5, 6):
                clip = root / f"flow-{shot_index}.mp4"
                clip.write_bytes((f"real-flow-{shot_index}-".encode()) * 100)
                stories.attach_flow_clip(job["id"], shot_index, clip)
            stories.register_flow_policy_failure(
                job["id"], 4, "FLOW_POLICY_BLOCKED: terminal policy card",
                flow_run_id="RUN-HYBRID-4", failure_card_fingerprint="CARD-HYBRID-4",
            )
            fallback = root / "local-motion-4.mp4"
            fallback.write_bytes(b"local-motion-scene-4-" * 100)
            checkpoint = stories.attach_flow_fallback_clip(
                job["id"], 4, fallback, "second distinct policy denial",
            )

            self.assertEqual(checkpoint["flow_clip_count"], 5)
            self.assertEqual(checkpoint["flow_fallback_count"], 1)
            self.assertEqual(checkpoint["flow_scene_count"], 6)
            self.assertEqual(checkpoint["video_status"], "clips_ready")
            self.assertNotIn("4", checkpoint["flow_clips"])
            self.assertIn("4", checkpoint["flow_fallback_clips"])
            self.assertEqual(
                checkpoint["flow_fallback_metadata"]["4"]["source_type"],
                "story_local_motion_fallback",
            )

            folder = stories.root / job["id"]
            final = folder / "videos" / "hybrid-final.mp4"
            final.write_bytes(b"hybrid-final-video" * 100)
            plan = {
                "source_type": "google_flow_story_hybrid_fallback",
                "flow_clip_count": 5,
                "flow_fallback_count": 1,
                "flow_fallback_scenes": [4],
            }
            with mock.patch.object(
                stories, "_ensure_completion_cover", side_effect=lambda value, **kwargs: stories.get(value),
            ):
                saved = stories.save_video(job["id"], final, plan)
            self.assertEqual(saved["status"], "ready")
            self.assertEqual(saved["video_source_type"], "google_flow_story_hybrid_fallback")
            self.assertEqual(saved["render_plan"]["flow_clip_count"], 5)
            self.assertEqual(saved["render_plan"]["flow_fallback_count"], 1)

    def test_drama_footage_does_not_hide_story_flow_hybrid_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create(
                "ละครทดสอบแหล่งที่มา",
                scene_count=6,
                job_type="drama_episode",
                video_generation_mode="google_flow",
            )
            folder = stories.root / job["id"]
            current = stories.get(job["id"])
            current["generated_images"] = []
            for index in range(1, 7):
                scene = folder / "generated" / f"scene_{index:02d}.png"
                Image.new("RGB", (64, 96), (index * 20, 30, 80)).save(scene)
                current["generated_images"].append(str(scene.relative_to(folder)))
            stories._save(current)
            for index in (1, 2, 3, 5, 6):
                clip = root / f"drama-flow-{index}.mp4"
                clip.write_bytes((f"drama-flow-{index}-".encode()) * 100)
                stories.attach_flow_clip(job["id"], index, clip)
            stories.register_flow_policy_failure(
                job["id"], 4, "FLOW_POLICY_BLOCKED: drama terminal policy card",
                flow_run_id="RUN-DRAMA-4", failure_card_fingerprint="CARD-DRAMA-4",
            )
            fallback = root / "drama-local-motion-4.mp4"
            fallback.write_bytes(b"drama-local-motion-4-" * 100)
            stories.attach_flow_fallback_clip(job["id"], 4, fallback, "policy terminal")
            final = folder / "videos" / "drama-hybrid-final.mp4"
            final.write_bytes(b"drama-hybrid-final" * 100)
            plan = {
                "source_type": "google_flow_story_hybrid_fallback",
                "flow_clip_count": 5,
                "flow_fallback_count": 1,
                "flow_fallback_scenes": [4],
                "footage_count": 1,
            }
            with mock.patch.object(
                stories, "_ensure_completion_cover", side_effect=lambda value, **kwargs: stories.get(value),
            ):
                saved = stories.save_video(job["id"], final, plan)
            self.assertEqual(saved["video_source_type"], "google_flow_story_hybrid_fallback")
            self.assertEqual(saved["video_content_mix_type"], "drama_mixed_media")

    def test_google_flow_job_rejects_motion_fallback_and_stays_checkpointed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create(
                "เรื่องที่ Flow ปฏิเสธโดยไม่หักเครดิต",
                scene_count=6,
                video_generation_mode="google_flow",
            )
            reason = "Google Flow สร้างไม่สำเร็จและไม่ได้หักเครดิต"
            folder = stories.root / job["id"]
            scene = folder / "generated" / "scene_01.png"
            Image.new("RGB", (180, 320), "navy").save(scene)
            with_scene = stories.get(job["id"])
            with_scene["generated_images"] = [str(scene.relative_to(folder))]
            stories._save(with_scene)
            output = folder / "videos" / "story_short_final.mp4"
            output.write_bytes(b"fallback-motion-video" * 100)
            with self.assertRaisesRegex(ValueError, "คลิปจริงเพียง 0/6"):
                stories.save_video(job["id"], output, {
                    "source_type": "story_image_sequence_fallback",
                    "flow_fallback_used": True,
                    "flow_fallback_reason": reason,
                })
            saved = stories.get(job["id"])
            self.assertNotEqual(saved["status"], "ready")
            self.assertEqual(saved["video_source_type"], "google_flow_pending")

    def test_legacy_story_motion_fallback_can_be_reopened_without_deleting_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create("กู้ Story Flow รุ่นเก่า", scene_count=6, video_generation_mode="google_flow")
            folder = stories.root / job["id"]
            fallback = folder / "videos" / "story_short_complete.mp4"
            fallback.write_bytes(b"legacy-motion-fallback" * 100)
            legacy = stories.get(job["id"])
            legacy.update({
                "status": "ready",
                "video_status": "ready",
                "video_source_type": "story_image_sequence_fallback",
                "video_path": str(fallback.relative_to(folder)),
                "render_plan": {"source_type": "story_image_sequence_fallback"},
            })
            stories._save(legacy)

            reopened = stories.reopen_google_flow_checkpoint(job["id"], "ใช้ Flow จริง")

            self.assertTrue(fallback.is_file())
            self.assertEqual(reopened["status"], "error")
            self.assertEqual(reopened["video_status"], "waiting_flow")
            self.assertEqual(reopened["video_source_type"], "google_flow_pending")
            self.assertEqual(reopened["video_path"], "")
            self.assertEqual(reopened["rejected_fallback_video_path"], str(fallback.relative_to(folder)))

    def test_story_image_checkpoint_survives_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = StoryManager(root)
            job = manager.create("นกน้อยส่งจดหมาย", scene_count=6)
            image = root / "checkpoint.png"
            Image.new("RGB", (32, 48), "orange").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            saved = manager.save_partial_image(job["id"], 1, encoded)
            self.assertEqual(saved["partial_image_count"], 1)
            self.assertTrue((manager.root / job["id"] / "generated" / "scene_01.png").is_file())
            package = manager.plugin_request(job["id"])
            self.assertEqual(package["checkpoint_images"], ["generated\\scene_01.png"] if "\\" in str(Path("generated") / "scene_01.png") else ["generated/scene_01.png"])

    def test_story_analysis_checkpoint_survives_provider_failover(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create("โลกิทำลายอนาคต", scene_count=6, image_ai_provider="gemini")
            # This historical checkpoint predates the optional identity fields.
            job.pop("story_content_contract")
            manager._save(job)
            analysis = {
                "job_id": job["id"],
                "video_title": "โลกิผู้เหลือเพียงคนเดียว",
                "video_description": "เรื่องเล่าจักรวาลคู่ขนาน",
                "narration_script": "โลกิเคยคิดว่าการหยุดเหล่าฮีโร่คือชัยชนะ",
                "visual_bible": {"tone": "จักรวาลมืด"},
                "scene_prompts": [f"ภาพฉากต่อเนื่อง {index}" for index in range(1, 7)],
                "scene_narrations": [f"เรื่องเล่าฉาก {index}" for index in range(1, 7)],
                "scene_durations": [4] * 6,
                "analysis_provider": "gemini",
            }
            saved = manager.save_analysis_checkpoint(job["id"], analysis)
            self.assertEqual(saved["analysis_status"], "ready")
            self.assertEqual(saved["video_title"], analysis["video_title"])
            switched = manager.set_image_ai_provider(job["id"], "chatgpt", "Gemini ไม่ส่งภาพ")
            self.assertEqual(switched["image_ai_provider"], "chatgpt")
            self.assertEqual(switched["provider_failover_count"], 1)
            package = manager.plugin_request(job["id"])
            self.assertEqual(package["analysis_checkpoint"]["video_title"], analysis["video_title"])
            self.assertEqual(package["job"]["image_ai_provider"], "chatgpt")

    def test_story_checkpoint_rejects_reencoded_source_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main = root / "main.jpg"
            Image.new("RGB", (96, 128), "navy").save(main, quality=88)
            manager = StoryManager(root)
            job = manager.create("เรื่องที่มีรูปอ้างอิง", main_image=main, scene_count=6)
            with Image.open(main) as source:
                converted = root / "source-preview.png"
                source.convert("RGB").save(converted)
            encoded = base64.b64encode(converted.read_bytes()).decode()
            with self.assertRaisesRegex(ValueError, "รูปอ้างอิงเดิม"):
                manager.save_partial_image(job["id"], 1, encoded)
            self.assertFalse((manager.root / job["id"] / "generated" / "scene_01.png").exists())

    def test_eight_of_ten_checkpoints_are_kept_for_exact_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = StoryManager(root)
            job = manager.create("เรื่องที่สะดุดหลังภาพที่แปด", scene_count=10)
            image = root / "checkpoint.png"
            Image.new("RGB", (32, 48), "teal").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            for index in range(1, 9):
                manager.save_partial_image(job["id"], index, encoded)
            package = manager.plugin_request(job["id"])
            self.assertEqual(len(package["checkpoint_images"]), 8)
            self.assertTrue(package["checkpoint_images"][0].endswith("scene_01.png"))
            self.assertTrue(package["checkpoint_images"][-1].endswith("scene_08.png"))
            recovering = manager.mark_recovering(job["id"], "chatgpt", "connection lost")
            self.assertEqual(recovering["auto_recovery_attempts"], 1)
            self.assertEqual(recovering["partial_image_count"], 8)

    def test_cancelled_story_rejects_late_browser_result(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create("เรื่องที่ยกเลิก", scene_count=6)
            cancelled = manager.mark_cancelled(job["id"], "chatgpt")
            self.assertTrue(cancelled["cancel_requested"])
            self.assertEqual(cancelled["status"], "cancelled")
            with self.assertRaisesRegex(ValueError, "ยกเลิก"):
                manager.apply_ai_result({"job_id": job["id"]})

    def test_failed_story_records_stage_and_error_without_overriding_cancel(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create("เรื่องที่เว็บส่งไม่สำเร็จ", scene_count=6)
            failed = manager.mark_failed(job["id"], "chatgpt", "ChatGPT ยังสร้างภาพก่อนหน้า")
            self.assertEqual(failed["status"], "error")
            self.assertEqual(failed["video_status"], "error")
            self.assertEqual(failed["pipeline_stage"], "chatgpt")
            self.assertIn("สร้างภาพก่อนหน้า", failed["last_error"])

            running = manager.mark_running(job["id"], "voice")
            self.assertNotIn("last_error", running)
            manager.mark_failed(job["id"], "voice", "เสียงผิดพลาด")

            manager.mark_cancelled(job["id"], "chatgpt")
            still_cancelled = manager.mark_failed(job["id"], "chatgpt", "ผลมาช้า")
            self.assertEqual(still_cancelled["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
