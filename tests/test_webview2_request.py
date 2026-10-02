"""No-replay contract for the isolated one-shot WebView2 request."""

import json
import tempfile
import unittest
from pathlib import Path

from desktop.webview2_request import OneShotRunner, RequestJournal, preflight, url_kind


URL = "https://chatgpt.com/c/WEB:36-test-conversation"
BASE = {"origin": "https://chatgpt.com", "url": URL, "ready": "complete",
        "composer_count": 1, "draft_length": 0, "attachments": 0,
        "busy": False, "login_visible": False, "user_count": 1,
        "assistant_count": 1}


class FakeProvider:
    def __init__(self, *, click=True, accepted=True):
        self.click = click
        self.accepted = accepted
        self.clicked = 0

    def evaluate(self, script):
        if "login_visible:" in script:
            return json.dumps(BASE)
        if "document.execCommand('insertText'" in script:
            return json.dumps({"ok": True})
        if "send_count:sends.length" in script:
            return json.dumps({"ok": True})
        if "sends[0].click()" in script:
            self.clicked += 1
            if not self.click:
                raise TimeoutError("click outcome unknown")
            return json.dumps({"clicked": True})
        if "latest_user_matches:" in script:
            return json.dumps({"origin": "https://chatgpt.com", "url": URL,
                               "latest_user_matches": self.accepted,
                               "user_count": 2 if self.accepted else 1,
                               "assistant_count": 2, "assistant_text": "คำตอบทดสอบ",
                               "busy": False})
        raise AssertionError("unknown script")


class WebView2RequestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.journal = RequestJournal(Path(self.temporary.name) / "receipt.json")

    def test_completed_request_stores_identity_and_hashes_without_prompt_or_answer(self):
        provider = FakeProvider()
        runner = OneShotRunner(provider, self.journal, sleep=lambda _: None)
        row = runner.run("ช่วยเล่าเรื่องสั้น", job_id="LAB-1", run_id="RUN-1")
        self.assertEqual(row["phase"], "completed")
        self.assertEqual(provider.clicked, 1)
        self.assertEqual(runner.answer, "คำตอบทดสอบ")
        saved = self.journal.path.read_text(encoding="utf-8")
        self.assertNotIn("ช่วยเล่าเรื่องสั้น", saved)
        self.assertNotIn("คำตอบทดสอบ", saved)
        self.assertIn("prompt_sha256", saved)

    def test_unknown_click_is_review_and_never_replayed(self):
        provider = FakeProvider(click=False)
        runner = OneShotRunner(provider, self.journal, sleep=lambda _: None)
        self.assertEqual(runner.run("ช่วยเล่าเรื่องสั้น")["phase"], "needs_review")
        self.assertEqual(provider.clicked, 1)
        with self.assertRaises(RuntimeError):
            runner.run("ช่วยเล่าเรื่องใหม่")
        self.assertEqual(provider.clicked, 1)

    def test_login_and_foreign_draft_block_before_receipt_and_send(self):
        self.assertIn("เข้าสู่ระบบ", preflight({**BASE, "login_visible": True}))
        self.assertIn("งานเดิม", preflight({**BASE, "draft_length": 4}))
        self.assertEqual(self.journal.read(), {})

    def test_receipt_owner_and_phase_are_immutable(self):
        row = self.journal.start("คำขอหนึ่ง", job_id="STORY-1", run_id="RUN-1", scene_index=3,
                                 baseline=BASE)
        with self.assertRaises(RuntimeError):
            self.journal.start("คำขอสอง")
        with self.assertRaises(RuntimeError):
            self.journal.transition("WV2-WRONG", {"prepared"}, "dispatching")
        self.journal.transition(row["request_id"], {"prepared"}, "dispatching")
        with self.assertRaises(RuntimeError):
            self.journal.transition(row["request_id"], {"prepared"}, "completed")

    def test_colon_conversation_route_is_owned_but_other_route_is_not(self):
        self.assertEqual(url_kind(URL), "conversation")
        self.assertEqual(url_kind("https://chatgpt.com/"), "root")
        self.assertEqual(url_kind("https://chatgpt.com/g/example"), "other")
        self.assertEqual(url_kind("https://example.com/c/WEB:1"), "other")

    def test_root_request_accepts_new_colon_conversation_without_resend(self):
        class RootProvider(FakeProvider):
            def evaluate(self, script):
                if "login_visible:" in script:
                    return json.dumps({**BASE, "url": "https://chatgpt.com/", "user_count": 0,
                                       "assistant_count": 0})
                return super().evaluate(script)

        provider = RootProvider()
        row = OneShotRunner(provider, self.journal, sleep=lambda _: None).run("คำขอทดสอบใหม่")
        self.assertEqual(row["phase"], "completed")
        self.assertEqual(provider.clicked, 1)


if __name__ == "__main__":
    unittest.main()
