import json
import logging
import tempfile
import unittest
from pathlib import Path

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


ROOT = Path(__file__).resolve().parents[1]


class RetiredVideoProviderTests(unittest.TestCase):
    def test_new_meta_adapter_does_not_restore_retired_meta_controller(self):
        manifest = json.loads((ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], LocalBridge.REQUIRED_EXTENSION_VERSION)
        serialized = json.dumps(manifest).lower()
        self.assertIn('https://www.meta.ai/*', manifest['host_permissions'])
        self.assertNotIn("meta.js", serialized)
        self.assertFalse((ROOT / "browser_extension" / "meta.js").exists())

        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8").lower()
        self.assertNotIn("meta.ai", background)
        self.assertIn("open_meta_video", background)
        self.assertNotIn('command.action === "open_meta"', background)
        self.assertNotIn("resume_meta", background)
        self.assertNotIn("inspect_meta", background)

    def test_hybrid_ui_no_longer_exposes_retired_provider(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8").lower()
        app = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8").lower()
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8").lower()
        self.assertNotIn('value="meta"', html)
        self.assertNotIn("open-meta", html)
        self.assertNotIn("meta.ai", html)
        self.assertNotIn("'open-meta'", app)
        self.assertNotIn('"https://www.meta.ai/"', engine)
        self.assertNotIn("stop_meta_generation", engine)
        self.assertNotIn('provider in {"flow", "meta"}', engine)
        self.assertIn('"google flow": "flow"', engine)

    def test_bridge_rejects_retired_commands(self):
        bridge = LocalBridge("127.0.0.1", 0, object(), logging.getLogger("provider-retirement-test"))
        for action in ("open_meta", "resume_meta", "inspect_meta", "download_meta_result"):
            with self.assertRaisesRegex(ValueError, "คำสั่ง Extension ไม่ถูกต้อง"):
                bridge.queue_extension_command(action, "JOB-LEGACY", 1)

    def test_legacy_pending_job_migrates_to_flow_without_deleting_files(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            folder = manager.root / "JOB-LEGACY"
            (folder / "images").mkdir(parents=True)
            preserved = folder / "images" / "reference.png"
            preserved.write_bytes(b"preserve-me")
            manifest = {
                "id": "JOB-LEGACY",
                "video_ai_provider": "meta",
                "video_source_type": "meta_pending",
                "video_status": "waiting_flow",
                "flow_video_status": "waiting_generation",
                "automation_status": "error",
                "automation_error": "Meta AI Vibes quota exhausted",
                "legacy_video_ai_provider": "meta",
                "automation_failure_history": [
                    {"stage": "flow", "error": "Meta AI Vibes generation failed"},
                ],
            }
            (folder / "job.json").write_text(json.dumps(manifest), encoding="utf-8")

            migrated = manager.get_job("JOB-LEGACY")
            self.assertEqual(migrated["video_ai_provider"], "flow")
            self.assertEqual(migrated["video_source_type"], "google_flow_pending")
            self.assertEqual(migrated["automation_status"], "idle")
            self.assertEqual(migrated["automation_error"], "")
            self.assertNotIn("legacy_video_ai_provider", migrated)
            self.assertNotIn("Meta AI", json.dumps(migrated, ensure_ascii=False))
            self.assertNotIn("Vibes", json.dumps(migrated, ensure_ascii=False))
            self.assertEqual(preserved.read_bytes(), b"preserve-me")
            with self.assertRaisesRegex(ValueError, "Google Flow หรือ Meta AI"):
                manager.set_video_ai_provider("JOB-LEGACY", "meta")

    def test_legacy_clip_job_keeps_files_but_hides_retired_provider_history(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            folder = manager.root / "JOB-LEGACY-CLIP"
            (folder / "videos").mkdir(parents=True)
            clip = folder / "videos" / "flow_shot_01.mp4"
            clip.write_bytes(b"preserve-clip")
            manifest = {
                "id": "JOB-LEGACY-CLIP",
                "video_ai_provider": "flow",
                "legacy_video_ai_provider": "meta",
                "video_source_type": "meta_clips",
                "automation_status": "error",
                "automation_error": "Meta AI Vibes จำกัดสิทธิ์บัญชีชั่วคราว",
                "automation_failure_history": [
                    {"stage": "flow", "error": "หน้า Meta AI Vibes ทำงานไม่สำเร็จ"},
                ],
            }
            (folder / "job.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            migrated = manager.get_job("JOB-LEGACY-CLIP")
            serialized = json.dumps(migrated, ensure_ascii=False)
            self.assertEqual(migrated["video_ai_provider"], "flow")
            self.assertEqual(migrated["video_source_type"], "google_flow_clips")
            self.assertEqual(migrated["automation_status"], "idle")
            self.assertNotIn("Meta AI", serialized)
            self.assertNotIn("Vibes", serialized)
            self.assertEqual(clip.read_bytes(), b"preserve-clip")

    def test_google_flow_credit_exhaustion_pauses_at_checkpoint(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("function creditExhausted", flow)
        self.assertIn('report("credit_exhausted"', flow)
        self.assertIn('step == "credit_exhausted"', engine)
        self.assertIn("ทำต่อด้วยบัญชี Google Flow ใหม่", engine)
        self.assertIn("flow_credit_exhausted", engine)


if __name__ == "__main__":
    unittest.main()
