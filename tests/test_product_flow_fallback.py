import json
import tempfile
import unittest
from queue import Queue
from pathlib import Path
from unittest import mock

from core.product_manager import ProductManager
from ui.main_window import MainWindow


ROOT = Path(__file__).resolve().parents[1]


class ProductFlowFallbackRetirementTests(unittest.TestCase):
    """Only authenticated policy failures may use truthful local motion."""

    @staticmethod
    def _write_probable_mp4(path, marker):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = b"\x00\x00\x00\x18ftypisom" + bytes(str(marker), "utf-8") + (b"\x00" * (70 * 1024))
        path.write_bytes(payload)
        return path

    def _make_job(self, root, job_id):
        manager = ProductManager(Path(root))
        folder = manager.root / job_id
        (folder / "generated").mkdir(parents=True)
        (folder / "videos" / ".working").mkdir(parents=True)
        generated_images = []
        for index in range(1, 4):
            image = folder / "generated" / f"selling_image_{index:02d}.png"
            image.write_bytes(f"canonical-image-{index}".encode("utf-8"))
            generated_images.append(str(image.relative_to(folder)))
        manifest = {
            "id": job_id,
            "product_name": "สินค้าทดสอบ Product worker",
            "generated_images": generated_images,
            "flow_shot_prompts": ["shot one", "shot two", "shot three"],
            "flow_clips": {},
            "flow_local_motion_clips": {},
            "video_ai_provider": "flow",
            "flow_target_clip_count": 3,
            "flow_source_image_map": {"1": 1, "2": 2, "3": 3},
            "flow_source_variant_map": {"1": 1, "2": 1, "3": 1},
        }
        (folder / "job.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8",
        )
        (folder / "ai_request.json").write_text(
            json.dumps({"schema_version": 7}), encoding="utf-8",
        )
        return manager, folder

    def _window(self, manager, bridge):
        window = MainWindow.__new__(MainWindow)
        window.products = manager
        window.bridge = bridge
        window.events = Queue()
        window.cfg = {"ffmpeg_path": "", "video_effect_enabled": False, "logo_file": ""}
        window._write_console = lambda *_args, **_kwargs: None
        window._product_progress_event = lambda *_args, **_kwargs: None
        window._ensure_flow_extension = lambda *_args, **_kwargs: None
        window._video_render_settings = lambda: {
            "width": 360,
            "height": 640,
            "fps": 24,
            "crf": 23,
            "transition_sec": 0.25,
        }
        return window

    def _run_worker_with_fake_renderers(self, window, job_id, rendered_sources):
        def render_local(source_image, target, **_kwargs):
            checkpoint = window.products.get_job(Path(target).parents[2].name)
            slot = str(int(Path(target).stem.rsplit("_", 1)[-1]))
            self.assertEqual(checkpoint["flow_policy_fallbacks"][slot]["status"], "render_pending")
            rendered_sources.append(Path(source_image).resolve())
            self._write_probable_mp4(target, f"local-{slot}")
            return {"source_type": "product_local_motion_policy_fallback"}

        def compose(_clips, target, **_kwargs):
            self._write_probable_mp4(target, "joined")
            return {"output": str(target)}

        with (
            mock.patch("ui.main_window.ProductImageVideoComposer") as local_composer,
            mock.patch("ui.main_window.MultiFlowComposer") as multi_composer,
        ):
            local_composer.return_value.render_motion_segment.side_effect = render_local
            multi_composer.return_value.compose.side_effect = compose
            return window._multi_flow_worker(
                job_id,
                emit_event=False,
                raise_errors=True,
            )

    def test_product_flow_pipeline_never_uses_local_motion(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        pipeline = source.split("def _product_pipeline_worker", 1)[1].split(
            "def _selected_product_job", 1
        )[0]
        worker = source.split("def _multi_flow_worker", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("_multi_flow_worker", pipeline)
        self.assertLess(pipeline.index("_multi_flow_worker"), pipeline.index("SubtitleVideoRenderer"))
        self.assertNotIn("_compose_product_image_fallback", pipeline)
        self.assertIn('getattr(exc, "flow_policy_terminal", False)', worker)
        self.assertNotIn("mark_flow_policy_fallback", worker)
        self.assertNotIn("_render_product_policy_fallback_segment", worker)
        self.assertNotIn("reassign_flow_shot_source", worker)
        self.assertNotIn("advance_flow_policy_prompt", worker)
        self.assertIn("FlowVideoReviewError", worker)
        self.assertLess(
            worker.index("ProductManager.flow_local_fallback_checkpoint(current, shot_index)"),
            worker.index("self._ensure_flow_extension"),
        )

    def test_product_manager_keeps_local_checkpoint_separate_from_real_flow(self):
        source = (ROOT / "core" / "product_manager.py").read_text(encoding="utf-8")
        self.assertIn("def mark_flow_policy_fallback(", source)
        self.assertIn("def attach_flow_local_motion_clip(", source)
        self.assertIn('"flow_local_motion_clips"', source)
        self.assertIn('"flow_segment_provenance"', source)
        self.assertIn('"flow_remote_clip_count"', source)
        self.assertIn('"flow_local_motion_clip_count"', source)

    def test_authenticated_policy_terminal_pauses_without_local_render(self):
        class RecordingBridge:
            REQUIRED_EXTENSION_VERSION = "test-compatible"

            def __init__(self):
                self.commands = []
                self.inspected_shot = 0

            def queue_extension_command(self, action, _job_id, shot_index):
                shot_index = int(shot_index)
                self.commands.append((action, shot_index))
                if action == "inspect_flow":
                    self.inspected_shot = shot_index

            def clear_flow_progress(self, *_args, **_kwargs):
                return None

            def extension_status(self):
                step = "generation_in_progress" if self.inspected_shot == 1 else "checkpoint_missing"
                return {"clients": [{
                    "version": self.REQUIRED_EXTENSION_VERSION,
                    "flow_job_id": "JOB-PRODUCT-WORKER",
                    "flow_shot_index": self.inspected_shot,
                    "flow_step": step,
                }]}

        with tempfile.TemporaryDirectory() as temp:
            manager, folder = self._make_job(Path(temp), "JOB-PRODUCT-WORKER")
            bridge = RecordingBridge()
            window = self._window(manager, bridge)
            rendered_sources = []

            def wait_flow(_job_id, shot_index, **_kwargs):
                if int(shot_index) == 1:
                    error = RuntimeError("FLOW_POLICY_BLOCKED • authenticated policy card")
                    error.flow_policy_terminal = True
                    error.policy_failure_category = "policy"
                    error.failure_card_fingerprint = "POLICY-CARD-ONE"
                    error.flow_run_id = "FLOW-RUN-ONE"
                    raise error

            def wait_download(_job_id, shot_index, **_kwargs):
                return self._write_probable_mp4(
                    folder / f"download-shot-{int(shot_index)}.mp4",
                    f"remote-{int(shot_index)}",
                )

            window._wait_flow_step = wait_flow
            window._wait_download = wait_download
            with self.assertRaisesRegex(RuntimeError, "FLOW_REPAIR_REVIEW"):
                self._run_worker_with_fake_renderers(window, "JOB-PRODUCT-WORKER", rendered_sources)
            saved = manager.get_job("JOB-PRODUCT-WORKER")
            self.assertEqual(rendered_sources, [])
            self.assertFalse(saved.get("flow_local_motion_clips"))
            self.assertFalse(saved.get("flow_policy_fallbacks"))
            self.assertTrue(all(shot == 1 for _, shot in bridge.commands))
            self.assertNotIn("open_flow", [action for action, _ in bridge.commands])
            self.assertNotIn("download_flow_result", [action for action, _ in bridge.commands])

    def test_restart_from_render_pending_never_touches_flow(self):
        class NoFlowBridge:
            REQUIRED_EXTENSION_VERSION = "test-compatible"

            def __init__(self):
                self.commands = []

            def queue_extension_command(self, action, _job_id, shot_index):
                self.commands.append((action, int(shot_index)))

            def clear_flow_progress(self, *_args, **_kwargs):
                raise AssertionError("render_pending resume must not clear or mutate Flow")

            def extension_status(self):
                raise AssertionError("render_pending resume must not inspect Flow")

        with tempfile.TemporaryDirectory() as temp:
            manager, folder = self._make_job(Path(temp), "JOB-PRODUCT-RESUME")
            manager.mark_flow_policy_fallback(
                "JOB-PRODUCT-RESUME",
                1,
                1,
                "FLOW_POLICY_BLOCKED • saved before crash",
                category="policy",
                fingerprint="POLICY-CARD-RESUME",
                flow_run_id="FLOW-RUN-RESUME",
            )
            for shot in (2, 3):
                source = self._write_probable_mp4(folder / f"preexisting-shot-{shot}.mp4", f"remote-{shot}")
                manager.attach_flow_clip("JOB-PRODUCT-RESUME", shot, source)

            resumed_manager = ProductManager(Path(temp))
            bridge = NoFlowBridge()
            window = self._window(resumed_manager, bridge)
            window._ensure_flow_extension = mock.Mock(
                side_effect=AssertionError("render_pending resume must not ensure Flow"),
            )
            rendered_sources = []
            with self.assertRaisesRegex(RuntimeError, "FLOW_REPAIR_REVIEW"):
                self._run_worker_with_fake_renderers(window, "JOB-PRODUCT-RESUME", rendered_sources)
            saved = resumed_manager.get_job("JOB-PRODUCT-RESUME")
            self.assertEqual(rendered_sources, [])
            self.assertEqual(bridge.commands, [])
            window._ensure_flow_extension.assert_not_called()
            self.assertEqual(len(saved["flow_policy_fallback_history"]), 1)
            self.assertEqual(saved["flow_policy_fallbacks"]["1"]["status"], "render_pending")
            self.assertEqual(len(saved["flow_clips"]), 2)


if __name__ == "__main__":
    unittest.main()
