import json
import logging
import inspect
import tempfile
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.story_manager import StoryManager
from core.story_queue import StoryBatchQueue
from core.video_library import VideoLibrary
from ui.main_window import MainWindow


ROOT = Path(__file__).resolve().parents[1]


class HybridInformationArchitectureTests(unittest.TestCase):
    def test_long_video_is_directly_available_in_create_sidebar(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        navigation = html.split('<nav class="navigation"', 1)[1].split("</nav>", 1)[0]
        create = navigation.split('<p class="nav-label">สร้าง</p>', 1)[1].split(
            '<p class="nav-label">งานและผลงาน</p>', 1
        )[0]
        self.assertEqual(create.count('data-page="longvideo"'), 1)
        self.assertIn('<strong>คลิปยาว</strong>', create)
        self.assertLess(create.index('data-page="story"'), create.index('data-page="longvideo"'))
        self.assertLess(create.index('data-page="longvideo"'), create.index('data-page="drama"'))
        self.assertIn('<section class="page" data-view="longvideo">', html)
        self.assertIn('id="create-longvideo"', html)
        self.assertIn('id="new-job-menu"', html)  # Keep the existing shortcut.
        self.assertNotIn('/desktop/flow_smoke.js', html)
        self.assertNotIn('ทดสอบ AI → Flow', html)

    def test_full_state_prepares_product_rows_before_library_response(self):
        source = inspect.getsource(MainWindow._desktop_state_payload)
        self.assertIn(
            "product_preparations = self._desktop_product_preparations(stories)",
            source,
        )
        fake = SimpleNamespace(
            products=SimpleNamespace(story_source_preparations=lambda: [
                {"id": "JOB-AVAILABLE"}, {"id": "JOB-LINKED"}, {"id": "JOB-QUEUED"},
            ]),
            story_queue=SimpleNamespace(snapshot=lambda: {"items": [{
                "settings": {"creative_context": {
                    "kind": "product_story", "source_product_id": "JOB-QUEUED",
                }},
            }]}),
        )
        stories = [{"product_story": {"product_id": "JOB-LINKED"}}]
        self.assertEqual(
            MainWindow._desktop_product_preparations(fake, stories),
            [{"id": "JOB-AVAILABLE"}],
        )

    def test_compact_state_and_video_range_routes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            web_root = root / "web_ui"
            web_root.mkdir()
            (web_root / "index.html").write_text("<!doctype html>", encoding="utf-8")
            video = root / "sample.mp4"
            video.write_bytes(bytes(range(100)))
            calls = []

            def desktop_state(mode="full"):
                calls.append(mode)
                return {"partial": mode == "compact", "mode": mode}

            bridge = LocalBridge(
                "127.0.0.1",
                0,
                ProductManager(root),
                logging.getLogger("compact-state-test"),
                desktop_state=desktop_state,
                desktop_media=lambda item_id, kind: video if item_id == "video" and kind == "video" else "",
                desktop_web_root=web_root,
            ).start()
            port = bridge.server.server_address[1]
            try:
                compact = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/desktop/state?mode=compact"))
                self.assertTrue(compact["partial"])
                self.assertEqual(compact["mode"], "compact")
                full = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/desktop/state"))
                self.assertFalse(full["partial"])
                self.assertEqual(calls, ["compact", "full"])

                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/desktop/media?item_id=video&kind=video",
                    headers={"Range": "bytes=10-19"},
                )
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.headers.get("Accept-Ranges"), "bytes")
                    self.assertEqual(response.headers.get("Content-Range"), "bytes 10-19/100")
                    self.assertEqual(response.read(), bytes(range(10, 20)))
            finally:
                bridge.stop()

    def test_video_library_exposes_story_and_drama_as_distinct_content_kinds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for job_id, job_type, series_id, episode_no in (
                ("STORY-ONE", "story_short", "", 0),
                ("STORY-DRAMA", "drama_episode", "SERIES-ONE", 2),
            ):
                folder = root / "workspace" / "stories" / job_id
                (folder / "videos").mkdir(parents=True)
                (folder / "videos" / "story_short_complete.mp4").write_bytes(b"video")
                (folder / "job.json").write_text(json.dumps({
                    "id": job_id,
                    "job_type": job_type,
                    "series_id": series_id,
                    "series_title": "แมวฮีโร่" if series_id else "",
                    "episode_no": episode_no,
                    "topic": job_id,
                    "status": "ready",
                    "video_status": "ready",
                    "video_path": "videos/story_short_complete.mp4",
                    "updated_at": "2026-09-02T10:00:00",
                }, ensure_ascii=False), encoding="utf-8")
            items = {item["job_id"]: item for item in VideoLibrary(root).list_items()}
            self.assertEqual(items["STORY-ONE"]["content_kind"], "story")
            self.assertEqual(items["STORY-DRAMA"]["content_kind"], "drama")
            self.assertEqual(items["STORY-DRAMA"]["series_id"], "SERIES-ONE")
            self.assertEqual(items["STORY-DRAMA"]["episode_no"], 2)

    def test_product_preview_and_embedded_video_resolve_to_different_media(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "workspace" / "products" / "JOB-MEDIA"
            image = folder / "generated" / "selling_image_01.png"
            video = folder / "videos" / "final_with_audio.mp4"
            image.parent.mkdir(parents=True)
            video.parent.mkdir(parents=True)
            image.write_bytes(b"preview-image")
            video.write_bytes(b"final-video")
            (folder / "job.json").write_text(json.dumps({
                "id": "JOB-MEDIA",
                "status": "ready",
                "video_status": "ready",
                "video_path": "videos/final_with_audio.mp4",
                "generated_images": ["generated/selling_image_01.png"],
                "product_name": "สินค้า Test",
                "created_at": "2026-09-03T21:00:00",
                "updated_at": "2026-09-03T21:01:00",
            }, ensure_ascii=False), encoding="utf-8")

            window = MainWindow.__new__(MainWindow)
            window.products = ProductManager(root)
            window.video_library = VideoLibrary(root)

            preview_target = MainWindow._desktop_media_path(window, {
                "item_id": "product:JOB-MEDIA", "kind": "preview",
            })
            video_target = MainWindow._desktop_media_path(window, {
                "item_id": "product:JOB-MEDIA", "kind": "video",
            })

            self.assertEqual(Path(preview_target), image.resolve())
            self.assertEqual(Path(video_target), video.resolve())
            self.assertNotEqual(preview_target, video_target)

    def test_dismiss_story_job_cancels_recovery_row_without_deleting_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create(topic="งานเก่าที่ผู้ใช้ไม่ต้องการทำต่อ")
            checkpoint = stories.root / job["id"] / "generated" / "scene_01.png"
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_bytes(b"checkpoint")

            story_queue = StoryBatchQueue(root)
            queued = story_queue.enqueue_batch(["งานเก่าที่ผู้ใช้ไม่ต้องการทำต่อ"])["items"][0]
            story_queue.attach_job(queued["queue_id"], job["id"])

            window = MainWindow.__new__(MainWindow)
            window.stories = stories
            window.story_queue = story_queue
            window._manual_multi_flow_job_id = ""
            window._story_pipeline_job_id = ""
            window._desktop_set_notice = lambda *_args: None
            window._write_console = lambda *_args: None

            result = MainWindow._desktop_execute_action(
                window, "dismiss_story_job", {"job_id": job["id"]}
            )
            self.assertTrue(result["ok"])
            self.assertEqual(stories.get(job["id"])["status"], "cancelled")
            queue_item = next(
                item for item in story_queue.snapshot()["items"]
                if item.get("job_id") == job["id"]
            )
            self.assertEqual(queue_item["status"], "cancelled")
            self.assertTrue(checkpoint.is_file())

    def test_hybrid_ui_uses_light_heartbeat_and_single_owner_views(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        manifest = json.loads((ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8"))

        self.assertIn("?mode=compact", script)
        self.assertIn("const interval = active ? 1000 : 5000", script)
        self.assertIn("if (String(job.job_type || 'story_short') !== 'story_short')", script)
        self.assertIn("status === 'video_deleted'", script)
        self.assertNotIn('id="product-table"', html)
        product_continue = (ROOT / "web_ui" / "product_continue.js").read_text(encoding="utf-8")
        self.assertIn("data-product-continue", product_continue)
        self.assertIn("renderProductContinue", product_continue)
        self.assertNotIn('id="story-queue-panel"', html)
        self.assertNotIn('function renderStoryQueue(', script)
        self.assertEqual(html.count('id="creation-list"'), 1)
        self.assertIn('class="story-queue-link"', html)
        self.assertIn("data-dismiss-story", script)
        self.assertIn("dismiss_story_job", script)
        self.assertIn('data-filter="drama"', html)
        self.assertIn("item.content_kind", script)
        self.assertIn("library-series-group", script)
        self.assertIn("aspect-ratio:9/16", styles)
        self.assertIn('class="detail-video"', script)
        self.assertIn("item.video_url", script)
        self.assertIn('data-page="settings"', html)
        self.assertNotIn('class="nav-item" data-page="video"', html)
        self.assertEqual(manifest["name"], "SmartFlow AI")
        self.assertEqual(manifest["action"]["default_title"], "SmartFlow AI")
        self.assertEqual(manifest["icons"]["128"], "icons/icon128.png")


if __name__ == "__main__":
    unittest.main()
