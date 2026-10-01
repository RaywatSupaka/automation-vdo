"""Exercise actual UI cancellation methods without launching the GUI or jobs."""
import ast
from pathlib import Path
import queue
import threading
import types
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / "ui" / "main_window.py"
METHODS = {"_finish_story_cancel", "_handle_story_cancelled", "_story_worker"}


class Cancelled(Exception):
    pass


def instance():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in METHODS]
    scope = {"OperationCancelled": Cancelled, "COLORS": {"text": "white"}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), scope)
    event = threading.Event()
    obj = types.SimpleNamespace(
        _story_pipeline_job_id="STORY-A", _story_cancel_event=event,
        _story_render_active="STORY-A", _story_popup_terminal=False,
        _story_progress_dialog=None, stories=Mock(), story_queue=Mock(), log=Mock(),
        story_status=Mock(), status=Mock(), _story_progress_message=Mock(),
        _story_progress_detail=Mock(), _refresh=Mock(), _close_automation_browser=Mock(),
        _park_drama_checkpoint_for_recovery=Mock(), events=queue.Queue(),
    )
    obj.stories.get.return_value = {"status": "cancelled"}
    for name in METHODS:
        setattr(obj, name, types.MethodType(scope[name], obj))
    return obj


class StoryCancelOwnershipTests(unittest.TestCase):
    def test_delayed_cancel_cannot_clear_new_job(self):
        app = instance()
        event = app._story_cancel_event
        event.set()
        app._story_pipeline_job_id = "STORY-B"
        app._story_render_active = "STORY-B"
        self.assertFalse(app._finish_story_cancel("STORY-A", event))
        self.assertEqual(app._story_render_active, "STORY-B")
        app._close_automation_browser.assert_not_called()
        app.stories.get.assert_not_called()

    def test_old_event_cannot_cancel_same_job_resumed(self):
        app = instance()
        old_event = threading.Event()
        old_event.set()
        self.assertFalse(app._finish_story_cancel("STORY-A", old_event))
        self.assertFalse(app._handle_story_cancelled({"job_id": "STORY-A", "cancel_event": old_event}))
        self.assertFalse(app._story_cancel_event.is_set())
        app.story_queue.mark_cancelled_by_job.assert_not_called()

    def test_non_cancelled_event_is_not_terminal(self):
        app = instance()
        self.assertFalse(app._finish_story_cancel("STORY-A", app._story_cancel_event))
        app._refresh.assert_not_called()

    def test_current_cancel_finishes_once_and_retains_files(self):
        app = instance()
        event = app._story_cancel_event
        event.set()
        self.assertTrue(app._finish_story_cancel("STORY-A", event))
        self.assertFalse(app._finish_story_cancel("STORY-A", event))
        self.assertEqual(app._story_pipeline_job_id, "")
        self.assertIsNone(app._story_render_active)
        self.assertIsNone(app._story_cancel_event)
        app._close_automation_browser.assert_called_once()
        app._refresh.assert_called_once()
        app.stories.mark_cancelled.assert_not_called()

    def test_current_browser_cancellation_sets_its_event(self):
        app = instance()
        event = app._story_cancel_event
        self.assertTrue(app._handle_story_cancelled({"job_id": "STORY-A", "cancel_event": event}))
        self.assertTrue(event.is_set())
        app.story_queue.mark_cancelled_by_job.assert_called_once_with("STORY-A")

    def test_legacy_unowned_notification_cannot_mutate_job(self):
        app = instance()
        for payload in ("STORY-A", None, {"job_id": "STORY-A"}):
            self.assertFalse(app._handle_story_cancelled(payload))
        app.story_queue.mark_cancelled_by_job.assert_not_called()
        app._close_automation_browser.assert_not_called()

    def test_worker_reports_original_event_even_after_resume(self):
        app = instance()
        original_event = app._story_cancel_event
        original_event.set()
        app._story_cancel_event = threading.Event()
        def work():
            raise Cancelled()
        app._story_worker("STORY-A", work, original_event)
        kind, payload = app.events.get_nowait()
        self.assertEqual(kind, "story_cancelled")
        self.assertIs(payload["cancel_event"], original_event)
        self.assertFalse(app._handle_story_cancelled(payload))
        self.assertFalse(app._story_cancel_event.is_set())


if __name__ == "__main__":
    unittest.main()
