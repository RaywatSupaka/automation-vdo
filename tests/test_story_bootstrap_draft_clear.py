"""Only an exact failed Story bootstrap trace may target an authorized draft."""
import json
import logging
import tempfile
import unittest
from pathlib import Path

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.story_manager import StoryManager


class StoryBootstrapDraftClearTests(unittest.TestCase):
    def test_exact_failed_job_run_and_tab_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stories = StoryManager(root)
            products = ProductManager(root)
            job = stories.create("offline fixture", scene_count=2)
            bridge = LocalBridge("127.0.0.1", 0, products,
                                 logging.getLogger("bootstrap-clear-test"), stories=stories)
            run = "RUN-BOOTSTRAP"
            tab = 87654321
            def command(**changes):
                return bridge.queue_extension_command("clear_story_bootstrap_draft", job["id"],
                                                      run_id=changes.get("run_id", run),
                                                      target_tab_id=changes.get("tab_id", tab))

            with self.assertRaisesRegex(ValueError, "งานยังไม่หยุด"):
                command()
            stories.mark_failed(job["id"], reason="AI_WEB_WAIT_REVIEW")
            with self.assertRaisesRegex(ValueError, "ไม่มีหลักฐานร่าง"):
                command()
            trace = stories.root / job["id"] / "logs" / "extension_trace.jsonl"
            trace.parent.mkdir(parents=True, exist_ok=True)
            review = {"action": "story_bootstrap_review", "job_id": job["id"],
                      "run_id": run, "tab_id": tab, "detail": {"reason": "draft_present"}}
            trace.write_text(json.dumps(review) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ไม่มีหลักฐานร่าง"):
                command(tab_id=tab + 1)
            with self.assertRaisesRegex(ValueError, "ไม่มีหลักฐานร่าง"):
                command(run_id="RUN-FOREIGN")
            accepted = {"action": "ai_send_accepted", "job_id": job["id"], "run_id": run}
            trace.write_text(json.dumps(review) + "\n" + json.dumps(accepted) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ไม่มีหลักฐานร่าง"):
                command()
            trace.write_text(json.dumps(review) + "\n", encoding="utf-8")
            result = command()
            self.assertEqual(result["target_tab_id"], tab)
            self.assertEqual(result["run_id"], run)
            self.assertEqual(result["provider"], "chatgpt")


if __name__ == "__main__":
    unittest.main()
