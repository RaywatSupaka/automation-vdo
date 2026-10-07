import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.story_manager import StoryManager
from core.story_receipt_recovery import (legacy_first_image_receipt_proof,
    pending_story_image_target, confirmed_first_image_pre_send)


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


class FirstImagePreSendTests(unittest.TestCase):
    def test_527_main_world_draft_preflight_has_no_click_and_keeps_prepared_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / 'logs' / 'extension_trace.jsonl'
            path.parent.mkdir(parents=True)
            common = {'job_id': 'STORY-TEST', 'service': 'chatgpt', 'version': '0.15.527',
                      'run_id': 'RUN-EXACT', 'client_id': 'a' * 32, 'tab_id': 42,
                      'page_url': 'https://chatgpt.com/'}
            def row(sequence, action, second, **fields):
                return common | {'sequence': sequence, 'action': action,
                                 'at': f'2026-10-07T17:55:{second:02d}'} | fields
            rows = [row(1, 'analysis_saved', 46),
                    row(2, 'generating_images', 48, message='กำลังสร้างภาพผ่านหน้า ChatGPT Web 1/6'),
                    row(3, 'waiting_for_composer', 50), row(4, 'image_tool_selected', 56),
                    row(5, 'image_prompt_ready', 58,
                        detail={'scene_index': 1, 'attempt': 1, 'composer_matches': True}),
                    row(6, 'image_attempt_result', 59,
                        message='ภาพ 1 • ครั้ง 1 • STORY_IMAGE_RECEIPT_REVIEW • non_retryable_error • ไม่มีข้อความตอบกลับ'),
                    row(7, 'error', 59,
                        message='STORY_IMAGE_RECEIPT_REVIEW • CHATGPT_IMAGE_RESULT_SEND_NOT_STARTED',
                        detail={'gesture_phase': 'not_started', 'preflight_reason': 'draft_mismatch'})]
            def proof(items):
                path.write_text('\n'.join(json.dumps(item, ensure_ascii=False) for item in items), encoding='utf-8')
                return confirmed_first_image_pre_send(folder, 'STORY-TEST', 'chatgpt')
            self.assertEqual(proof(rows)['source_run_id'], 'RUN-EXACT')
            for changed in (rows[:6] + [rows[6] | {'detail': {'gesture_phase': 'mousePressed',
                                                              'preflight_reason': 'draft_mismatch'}}],
                            rows[:6] + [rows[6] | {'detail': {'gesture_phase': 'not_started',
                                                              'preflight_reason': 'unknown'}}],
                            rows[:5] + [rows[5] | {'sequence': 8}] + rows[6:],
                            rows + [row(8, 'image_sent', 59)]):
                with self.subTest(changed=changed[-1]['action']):
                    self.assertIsNone(proof(changed))

    def test_526_format_preflight_and_restored_draft_remain_pre_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / 'logs' / 'extension_trace.jsonl'
            path.parent.mkdir(parents=True)
            base = {'job_id': 'STORY-TEST', 'service': 'chatgpt', 'version': '0.15.526',
                    'run_id': 'RUN-EXACT', 'client_id': 'a' * 32, 'tab_id': 42,
                    'page_url': 'https://chatgpt.com/'}
            def row(sequence, action, second, **fields):
                return base | {'sequence': sequence, 'action': action,
                               'at': f'2026-10-07T17:33:{second:02d}'} | fields
            rows = [row(1, 'analysis_saved', 20),
                    row(2, 'generating_images', 22, message='กำลังสร้างภาพผ่านหน้า ChatGPT Web 1/6'),
                    row(3, 'waiting_for_composer', 23), row(4, 'image_tool_selected', 25),
                    row(5, 'image_prompt_ready', 27,
                        detail={'scene_index': 1, 'attempt': 1, 'composer_matches': True}),
                    row(6, 'image_attempt_result', 28,
                        message='ภาพ 1 • ครั้ง 1 • AI_SEND_NOT_READY • non_retryable_error • ไม่มีข้อความตอบกลับ'),
                    row(7, 'error', 28, message='AI_RESPONSE_FORMAT_NOT_READY • ยังไม่ได้กดส่ง'),
                    row(8, 'error', 57, tab_id=0, page_url='',
                        message='AI_WEB_WAIT_REVIEW • แท็บงานใหม่มีร่างข้อความที่ยืนยันเจ้าของไม่ได้'),
                    row(9, 'story_bootstrap_review', 58, tab_id=43, page_url='')]
            def proof(items):
                path.write_text('\n'.join(json.dumps(item, ensure_ascii=False) for item in items), encoding='utf-8')
                return confirmed_first_image_pre_send(folder, 'STORY-TEST', 'chatgpt')
            result = proof(rows)
            self.assertEqual(result['source_run_id'], 'RUN-EXACT')
            self.assertEqual(result['trace_sequence'], 7)
            self.assertEqual(result['created_after_ms'], int(datetime.fromisoformat(rows[1]['at']).timestamp() * 1000))
            for changed in (rows[:5] + [rows[5] | {'action': 'image_sent'}] + rows[6:],
                            rows[:4] + [rows[4] | {'detail': {'scene_index': 1, 'attempt': 1,
                                                             'composer_matches': False}}] + rows[5:],
                            rows[:6] + [rows[6] | {'message': 'AI_SEND_DISPATCHED_UNCONFIRMED'}] + rows[7:],
                            rows + [row(10, 'image_sent', 59)],
                            rows + [row(10, 'image_prompt_ready', 59)]):
                with self.subTest(changed=changed[-1]['action']):
                    self.assertIsNone(proof(changed))

    def test_521_draft_preflight_skips_old_chat_scan_only_without_later_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / 'logs' / 'extension_trace.jsonl'
            path.parent.mkdir(parents=True)
            common = {'job_id': 'STORY-TEST', 'service': 'chatgpt', 'version': '0.15.521',
                      'run_id': 'RUN-OLD', 'client_id': 'a' * 32, 'tab_id': 42,
                      'at': '2026-10-07T16:24:12',
                      'page_url': 'https://chatgpt.com/c/12345678-1234-1234-1234-123456789abc'}
            rows = [common | {'sequence': 1, 'action': 'analysis_saved'},
                    common | {'sequence': 2, 'action': 'generating_images', 'message': 'กำลังสร้างภาพผ่านหน้า ChatGPT Web 1/6'},
                    common | {'sequence': 3, 'action': 'waiting_for_composer'},
                    common | {'sequence': 4, 'action': 'image_attempt_result',
                              'message': 'ภาพ 1 • ครั้ง 1 • AI_SEND_NOT_READY • non_retryable_error • ไม่มีข้อความตอบกลับ'},
                    common | {'sequence': 5, 'action': 'error',
                              'detail': {'gesture_phase': 'not_started', 'preflight_reason': 'chatgpt_image_tool',
                                         'dispatch_completed': False}},
                    common | {'sequence': 1, 'run_id': 'RUN-NEW', 'version': '0.15.522', 'action': 'analysis_saved'}]
            def proof(value):
                path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in value), encoding='utf-8')
                return confirmed_first_image_pre_send(folder, 'STORY-TEST', 'chatgpt')
            self.assertEqual(proof(rows)['source_run_id'], 'RUN-OLD')
            safe_later = rows + [common | {'sequence': 2, 'run_id': 'RUN-NEW', 'version': '0.15.523',
                                          'action': 'generating_images', 'message': 'กำลังสร้างภาพผ่านหน้า ChatGPT Web 1/6'},
                                 common | {'sequence': 3, 'run_id': 'RUN-NEW', 'version': '0.15.523',
                                           'action': 'error', 'message': 'CHATGPT_IMAGE_RESULT_WRONG_CONVERSATION'}]
            self.assertEqual(proof(safe_later)['source_run_id'], 'RUN-OLD')
            later_base = common | {'version': '0.15.524', 'run_id': 'RUN-LATER',
                                   'page_url': 'https://chatgpt.com/'}
            safe_retry = safe_later + [
                later_base | {'sequence': 4, 'at': '2026-10-07T17:13:37', 'action': 'generating_images',
                              'message': 'กำลังสร้างภาพผ่านหน้า ChatGPT Web 1/6'},
                later_base | {'sequence': 5, 'at': '2026-10-07T17:13:37', 'action': 'receipt_pre_send_recovered'},
                later_base | {'sequence': 6, 'at': '2026-10-07T17:13:38', 'action': 'waiting_for_composer'},
                later_base | {'sequence': 7, 'at': '2026-10-07T17:13:39', 'action': 'image_tool_selected'},
                later_base | {'sequence': 8, 'at': '2026-10-07T17:13:41', 'action': 'image_attempt_result',
                              'message': 'ภาพ 1 • ครั้ง 1 • AI_SEND_NOT_READY • non_retryable_error • ไม่มีข้อความตอบกลับ'},
                later_base | {'sequence': 9, 'at': '2026-10-07T17:13:42', 'action': 'error',
                              'detail': {'gesture_phase': 'not_started', 'preflight_reason': 'chatgpt_image_tool',
                                         'dispatch_completed': False}},
                later_base | {'sequence': 1, 'run_id': 'RUN-NEWEST', 'action': 'analysis_saved'}]
            self.assertEqual(proof(safe_retry)['source_run_id'], 'RUN-LATER')
            for changed in (rows + [common | {'sequence': 2, 'run_id': 'RUN-NEW', 'action': 'image_prompt_ready'}],
                            rows[:2] + [common | {'sequence': 3, 'action': 'generating_images'}] + rows[2:],
                            rows[:4] + [rows[4] | {'detail': {'dispatch_completed': True}}] + rows[5:],
                            safe_later + [common | {'sequence': 4, 'run_id': 'RUN-NEW', 'action': 'image_attempt_result'}],
                            safe_retry + [later_base | {'sequence': 2, 'run_id': 'RUN-NEWEST',
                                                        'action': 'image_prompt_ready'}]):
                self.assertIsNone(proof(changed))


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
