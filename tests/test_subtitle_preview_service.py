import tempfile
import threading
import time
import unittest
from pathlib import Path

from core.subtitle_preview import SubtitlePreviewService


class FakeRenderer:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def render_preview_image(self, target, text, **settings):
        self.calls.append(text)
        self.started.set()
        if not self.release.wait(4): raise TimeoutError("test gate")
        target.write_bytes(b"png")

    def render_preview_video(self, target, text, **settings):
        target.write_bytes(b"mp4")


class SubtitlePreviewServiceTests(unittest.TestCase):
    def wait_idle(self, service):
        until = time.monotonic() + 5
        while service.running and time.monotonic() < until: time.sleep(.01)
        self.assertFalse(service.running)

    def test_burst_renders_only_current_and_latest_then_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            renderer = FakeRenderer()
            service = SubtitlePreviewService(temp, renderer=renderer)
            service.request("first", {})
            self.assertTrue(renderer.started.wait(2))
            for index in range(30): service.request(f"value-{index}", {})
            renderer.release.set()
            self.wait_idle(service)
            self.assertEqual(renderer.calls, ["first", "value-29"])
            state = service.snapshot()
            self.assertFalse(state["preview_busy"])
            self.assertEqual(state["preview_token"], state["preview_ready_token"])
            service.request("first", {})
            self.assertEqual(renderer.calls, ["first", "value-29"])
            self.assertFalse(service.snapshot()["preview_busy"])

    def test_keeps_previous_media_and_token_during_render(self):
        with tempfile.TemporaryDirectory() as temp:
            renderer = FakeRenderer(); renderer.release.set()
            service = SubtitlePreviewService(temp, renderer=renderer)
            service.request("first", {}); self.wait_idle(service)
            before = service.snapshot()
            item = before["preview_url"].split("item_id=")[1].split("&")[0]
            old_path = service.media(item, "video")
            renderer.release.clear(); renderer.started.clear()
            service.request("second", {})
            self.assertTrue(renderer.started.wait(2))
            self.assertTrue(service.snapshot()["preview_busy"])
            self.assertEqual(service.snapshot()["preview_video_url"], before["preview_video_url"])
            self.assertTrue(old_path.is_file())
            with self.assertRaises((ValueError, FileNotFoundError)):
                service.media("__subtitle_preview__:../private", "video")
            renderer.release.set(); self.wait_idle(service)
            self.assertEqual(service.media(item, "video"), old_path)
            from ui.main_window import MainWindow
            window = object.__new__(MainWindow)
            window._subtitle_preview_service = service
            self.assertEqual(Path(window._desktop_media_path({"item_id": item, "kind": "video"})), old_path)

    def test_failure_reports_error_and_can_retry_same_style(self):
        class BrokenRenderer(FakeRenderer):
            def render_preview_video(self, *args, **kwargs): raise RuntimeError("encode failed")
        with tempfile.TemporaryDirectory() as temp:
            renderer = BrokenRenderer(); renderer.release.set()
            service = SubtitlePreviewService(temp, renderer=renderer)
            first = service.request("text", {}); self.wait_idle(service)
            self.assertEqual(service.snapshot()["preview_error"], "encode failed")
            self.assertFalse(service.snapshot()["preview_busy"])
            self.assertGreater(service.request("text", {}), first)
            self.wait_idle(service)


if __name__ == "__main__": unittest.main()
