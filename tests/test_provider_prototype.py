"""Safety contracts for the isolated WebView2 provider lab."""

import json
import tempfile
import unittest
from pathlib import Path

from desktop.provider_prototype import TraceWriter, bounded_snapshot, profile_path


class ProviderPrototypeTests(unittest.TestCase):
    def test_profiles_are_stable_and_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            self.assertEqual(profile_path(base, "chatgpt"), (base / "profile-chatgpt").resolve())
            self.assertNotEqual(profile_path(base, "chatgpt"), profile_path(base, "smoke"))
            with self.assertRaises(ValueError):
                profile_path(base, "../Chrome/User Data")

    def test_probe_result_keeps_only_bounded_page_signals(self):
        raw = {
            "origin": "https://chatgpt.com", "ready": "complete",
            "composer_visible": True, "send_enabled": True,
            "file_inputs": 1, "user_turns": 100000, "assistant_turns": -1,
            "images": "3", "prompt": "private story", "token": "private token",
            "url": "https://chatgpt.com/c/private-conversation",
        }
        self.assertEqual(bounded_snapshot(raw, "chatgpt"), {
            "page": "provider", "ready": "complete", "composer_visible": True,
            "send_enabled": True, "file_inputs": 1, "user_turns": 1000,
            "assistant_turns": 0, "images": 0,
        })
        self.assertEqual(bounded_snapshot({**raw, "origin": "https://example.com"}, "chatgpt"), {
            "page": "other_origin", "ready": "unknown",
        })

    def test_trace_does_not_write_prompt_token_or_conversation_url(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            writer = TraceWriter(path, "chatgpt", "test-session")
            writer.write("snapshot", {
                "origin": "https://chatgpt.com", "ready": "complete",
                "prompt": "private story", "token": "private token",
                "url": "https://chatgpt.com/c/private-conversation",
            })
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("private story", content)
            self.assertNotIn("private token", content)
            self.assertNotIn("private-conversation", content)
            self.assertEqual(json.loads(content)["snapshot"]["page"], "provider")

    def test_auth_redirect_is_distinct_from_provider_page(self):
        result = bounded_snapshot({"origin": "https://auth.openai.com", "ready": "complete"}, "chatgpt")
        self.assertEqual(result["page"], "auth")


if __name__ == "__main__":
    unittest.main()
