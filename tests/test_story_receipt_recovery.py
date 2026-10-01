import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.story_manager import StoryManager
from core.story_receipt_recovery import legacy_first_image_receipt_proof, pending_story_image_target


class CompletedReferenceRequestTests(unittest.TestCase):
    def test_confirmed_missing_reference_is_not_an_unknown_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            job = {'id': 'STORY-REF', 'image_ai_provider': 'chatgpt'}
            common = {'job_id': job['id'], 'service': 'chatgpt', 'client_id': 'client',
                      'run_id': 'RUN-1', 'tab_id': 42,
                      'page_url': 'https://chatgpt.com/c/12345678-1234-1234-1234-123456789abc'}
            ready = common | {'action': 'image_prompt_ready', 'detail': {'scene_index': 14}}
            answer = common | {'action': 'image_attempt_result',
                               'message': 'ภาพ 14 • ครั้ง 1 • CHATGPT_NO_IMAGE • reference_required • ต้องมีรูปอ้างอิง'}
            terminal = common | {'action': 'error',
                                 'message': 'ผิดพลาด: STORY_REFERENCE_REQUIRED • ChatGPT Web ขอภาพอ้างอิงเพิ่มสำหรับฉาก 14'}
            self.assertIsNone(pending_story_image_target(folder, job, [ready, answer, terminal]))
            self.assertTrue(pending_story_image_target(folder, job, [ready, answer]))
            self.assertTrue(pending_story_image_target(folder, job, [ready, answer,
                terminal | {'run_id': 'RUN-OTHER'}]))
            self.assertTrue(pending_story_image_target(folder, job, [ready, answer, terminal,
                ready | {'run_id': 'RUN-2', 'tab_id': 43}]))


class LegacyReceiptProofTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manager = StoryManager(self.root)
        self.job = self.manager.create("แม่น้ำยามเช้า", scene_count=6, image_ai_provider="gemini")
        self.folder = self.manager._folder(self.job["id"])
        self.path = self.folder / "logs" / "extension_trace.jsonl"
        common = {"at": "2026-09-06T23:41:03", "job_id": self.job["id"], "service": "gemini",
                  "version": "0.15.259", "run_id": "RUN-LEGACY", "tab_id": 42,
                  "client_id": "a" * 32}
        self.rows = [common | {"sequence": 19, "action": "analysis_saved", "message": "บันทึกแล้ว"},
                     common | {"sequence": 20, "action": "generating_images", "message": "กำลังสร้างภาพผ่านหน้า Gemini Web 1/6"},
                     common | {"sequence": 21, "action": "error", "message": "ผิดพลาด: STORY_IMAGE_RECEIPT_REVIEW • ภาพฉาก 1 • ยังยืนยันการบันทึกหลักฐานภาพไม่ได้ • เก็บฉากเดิมไว้ ไม่สร้างภาพซ้ำ"}]

    def write(self, rows=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in (self.rows if rows is None else rows)), encoding="utf-8")

    def proof(self):
        return legacy_first_image_receipt_proof(self.folder, self.job["id"], "gemini")

    def test_exact_adjacent_failure_proves_first_image_was_not_submitted(self):
        self.write()
        before = self.path.read_bytes()
        proof = self.proof()["1"]
        self.assertEqual(proof["run_id"], "RUN-LEGACY")
        self.assertEqual(proof["created_after_ms"], int(datetime.fromisoformat(self.rows[0]["at"]).timestamp() * 1000))
        self.assertEqual(proof["created_before_ms"] - proof["created_after_ms"], 999)
        self.assertEqual(self.path.read_bytes(), before)

    def test_later_audit_send_result_or_unrecognized_action_invalidates_proof(self):
        for action in ("image_prompt_ready", "ai_send_dispatched", "ai_send_accepted", "image_attempt_result",
                       "complete", "receipt_pre_send_recovered", "unknown"):
            with self.subTest(action=action):
                self.write(self.rows + [self.rows[-1] | {"sequence": 22, "action": action}])
                self.assertEqual(self.proof(), {})

    def test_wrong_identity_version_time_or_scene_cannot_prove_no_send(self):
        for field, value in (("version", "0.15.258"), ("run_id", "RUN-OTHER"), ("tab_id", 0),
                             ("client_id", "b" * 32), ("job_id", "STORY-OTHER"), ("service", "chatgpt"),
                             ("sequence", 24), ("at", "2026-09-06T23:41:15"),
                             ("message", self.rows[-1]["message"].replace("ฉาก 1", "ฉาก 2"))):
            with self.subTest(field=field):
                rows = copy.deepcopy(self.rows)
                rows[-1][field] = value
                self.write(rows)
                self.assertEqual(self.proof(), {})

    def test_nonadjacent_or_partial_trace_never_proves_no_send(self):
        for rows in (self.rows[1:], self.rows[:2], list(reversed(self.rows)),
                     [self.rows[0], self.rows[0] | {"sequence": 19}, *self.rows[1:]]):
            self.write(rows)
            self.assertEqual(self.proof(), {})
        self.path.write_text('{"truncated":', encoding="utf-8")
        self.assertEqual(self.proof(), {})

    def test_existing_scene_file_prevents_migration(self):
        self.write()
        generated = self.folder / "generated" / "scene_01.png"
        generated.parent.mkdir(exist_ok=True)
        generated.write_bytes(b"saved-image")
        self.assertEqual(self.proof(), {})

    def test_prior_image_attempt_or_oversized_trace_prevents_migration(self):
        for action in ("image_prompt_ready", "image_attempt_result", "complete"):
            with self.subTest(action=action):
                self.write([self.rows[0] | {"sequence": 18, "action": action}, *self.rows])
                self.assertEqual(self.proof(), {})
        self.path.write_text(" " * (4 * 1024 * 1024 + 1), encoding="utf-8")
        self.assertEqual(self.proof(), {})

    def test_package_requires_valid_saved_plan_and_keeps_it_unchanged(self):
        self.write()
        self.assertNotIn("image_receipt_pre_send_proof", self.manager.plugin_request(self.job["id"]))
        analysis = {"job_id": self.job["id"], "video_title": "แม่น้ำ", "video_description": "เรื่องเดิม",
                    "narration_script": "แม่น้ำไหล", "scene_prompts": [f"A river angle {i}" for i in range(6)],
                    "scene_narrations": ["แม่น้ำไหล"] * 6, "scene_durations": [4] * 6,
                    "story_entities": [], "scene_entities": [[] for _ in range(6)]}
        self.manager.save_analysis_checkpoint(self.job["id"], analysis)
        saved = self.folder / "prompts" / "ai_analysis_checkpoint.json"
        before = saved.read_bytes()
        package = self.manager.plugin_request(self.job["id"])
        self.assertEqual(package["image_receipt_pre_send_proof"]["1"]["run_id"], "RUN-LEGACY")
        self.assertEqual(saved.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
