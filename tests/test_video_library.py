import json
import shutil
import tempfile
import unittest
from pathlib import Path

from core.product_manager import ProductManager
from core.video_library import VideoLibrary
from core.workspace_cleaner import WorkspaceCleaner


class VideoLibraryTests(unittest.TestCase):
    def _job(self, root, section, job_id, relative, **extra):
        folder = Path(root) / "workspace" / section / job_id
        (folder / "videos").mkdir(parents=True)
        video = folder / relative
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"main-video")
        manifest = {
            "id": job_id,
            "status": "ready",
            "video_status": "ready",
            "video_path": relative,
            "created_at": "2026-08-26T10:00:00",
            "updated_at": "2026-08-26T11:00:00",
            **extra,
        }
        (folder / "job.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return folder, video

    def test_lists_only_current_main_product_and_story_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            product, product_video = self._job(temp, "products", "JOB-ONE", "videos/product_complete.mp4", product_name="สินค้า A")
            story, story_video = self._job(temp, "stories", "STORY-ONE", "videos/story_short_complete.mp4", video_title="เรื่อง A")
            (product / "videos" / "flow_shot_01.mp4").write_bytes(b"intermediate")
            (story / "videos" / "story_with_subtitles.mp4").write_bytes(b"intermediate")

            items = VideoLibrary(temp).list_items()
            self.assertEqual(len(items), 2)
            self.assertEqual({Path(item["path"]) for item in items}, {product_video, story_video})
            self.assertEqual({item["title"] for item in items}, {"สินค้า A", "เรื่อง A"})

    def test_prefers_completed_audio_mix_as_the_main_output(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, base_video = self._job(temp, "products", "JOB-AUDIO", "videos/base.mp4", product_name="สินค้าเสียงพร้อม")
            final_video = folder / "videos" / "final_with_audio.mp4"
            final_video.write_bytes(b"final-audio-video")
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({
                "audio_mix_status": "ready",
                "audio_mix_path": "videos/final_with_audio.mp4",
            })
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            item = VideoLibrary(temp).list_items()[0]
            self.assertEqual(Path(item["path"]), final_video)
            self.assertEqual(item["file_name"], "final_with_audio.mp4")
            self.assertNotEqual(Path(item["path"]), base_video)

    def test_product_item_detail_separates_caption_hashtags_and_affiliate_link(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _ = self._job(temp, "products", "JOB-DETAIL", "videos/final.mp4", product_name="คอกแมวพับได้")
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({
                "posting_product_url": "https://s.shopee.co.th/example",
                "generated_images": ["generated/selling_01.png"],
            })
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            captions = folder / "captions"
            captions.mkdir()
            (captions / "caption.txt").write_text("พับเก็บง่ายและระบายอากาศได้ดี", encoding="utf-8")
            (captions / "hashtags.txt").write_text("#คอกแมว #ของใช้สัตว์เลี้ยง", encoding="utf-8")
            generated = folder / "generated"
            generated.mkdir()
            (generated / "selling_01.png").write_bytes(b"image")

            detail = VideoLibrary(temp).item_detail("product:JOB-DETAIL")

            self.assertEqual(detail["title"], "คอกแมวพับได้")
            self.assertEqual(detail["description"], "พับเก็บง่ายและระบายอากาศได้ดี")
            self.assertEqual(detail["hashtags"], "#คอกแมว #ของใช้สัตว์เลี้ยง")
            self.assertEqual(detail["affiliate_link"], "https://s.shopee.co.th/example")
            self.assertTrue(detail["preview_path"].endswith("selling_01.png"))

    def test_item_detail_can_reuse_a_preloaded_library_row_without_rescanning(self):
        with tempfile.TemporaryDirectory() as temp:
            self._job(temp, "products", "JOB-FAST", "videos/final.mp4", product_name="งานพร้อม")

            class CountingLibrary(VideoLibrary):
                def __init__(self, root):
                    super().__init__(root)
                    self.list_calls = 0

                def list_items(self):
                    self.list_calls += 1
                    return super().list_items()

            library = CountingLibrary(temp)
            item = library.list_items()[0]
            detail = library.item_detail(item["item_id"], preloaded_item=item)

            self.assertEqual(detail["title"], "งานพร้อม")
            self.assertEqual(library.list_calls, 1)

    def test_story_item_detail_extracts_hashtags_from_description(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _ = self._job(temp, "stories", "STORY-DETAIL", "videos/final.mp4")
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({
                "video_title": "เรื่องลึกลับหน้าบ้าน",
                "video_description": "คืนหนึ่งมีเสียงประหลาดหน้าบ้าน #เรื่องเล่า #เรื่องลึกลับ",
            })
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            detail = VideoLibrary(temp).item_detail("story:STORY-DETAIL")

            self.assertEqual(detail["title"], "เรื่องลึกลับหน้าบ้าน")
            self.assertEqual(detail["description"], "คืนหนึ่งมีเสียงประหลาดหน้าบ้าน")
            self.assertEqual(detail["hashtags"], "#เรื่องเล่า #เรื่องลึกลับ")
            self.assertEqual(detail["affiliate_link"], "")

    def test_story_post_editor_updates_copy_only_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, video = self._job(
                temp, "stories", "STORY-POST", "videos/final.mp4",
                video_title="ทำไมตัวละครจึงแพ้", video_description="ความยาวเป้าหมาย 300 วินาที จำนวน 38 ภาพ",
                long_video={"version": 2},
            )
            original_manifest = (folder / "job.json").read_bytes()
            original_video = video.read_bytes()
            library = VideoLibrary(temp)
            before = library.item_detail("story:STORY-POST")
            saved = library.save_post_metadata(
                "story:STORY-POST", "เหตุใดการต่อสู้ครั้งนี้จึงพลิกความคาดหมาย? มาดูคำตอบในคลิป",
                "#วิเคราะห์ตัวละคร #เรื่องเล่า #คลิปยาว", before["post_revision"])
            self.assertNotIn("ความยาวเป้าหมาย", saved["post_text"])
            self.assertIn("#วิเคราะห์ตัวละคร", saved["post_text"])
            restarted = VideoLibrary(temp).item_detail("story:STORY-POST")
            self.assertEqual(saved["post_text"], restarted["post_text"])
            self.assertEqual((folder / "job.json").read_bytes(), original_manifest)
            self.assertEqual(video.read_bytes(), original_video)
            with self.assertRaisesRegex(ValueError, "เปลี่ยนไปแล้ว"):
                library.save_post_metadata("story:STORY-POST", "ข้อความอีกอัน", "#หนึ่ง #สอง #สาม", before["post_revision"])
            with self.assertRaises(ValueError):
                library.save_post_metadata("story:STORY-POST", "จำนวน 50 ภาพ", "#หนึ่ง #สอง #สาม", saved["post_revision"])

    def test_post_editor_does_not_change_product_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            self._job(temp, "products", "JOB-POST", "videos/final.mp4", product_name="สินค้า")
            library = VideoLibrary(temp)
            detail = library.item_detail("product:JOB-POST")
            with self.assertRaisesRegex(ValueError, "เรื่องเล่า"):
                library.save_post_metadata("product:JOB-POST", "คำอธิบาย", "#สินค้า #รีวิว #คลิป", detail["post_revision"])

    def test_drama_episode_is_labelled_as_ai_drama_in_library(self):
        with tempfile.TemporaryDirectory() as temp:
            self._job(
                temp, "stories", "STORY-DRAMA", "videos/story_short_complete.mp4",
                video_title="ร้านกาแฟแก้วสุดท้าย", job_type="drama_episode",
            )
            item = VideoLibrary(temp).list_items()[0]
            self.assertEqual(item["kind"], "story")
            self.assertEqual(item["kind_label"], "ละครสั้น AI")

    def test_drama_detail_exposes_dedicated_shorts_cover_before_scene_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _ = self._job(
                temp, "stories", "STORY-COVER", "videos/story_short_complete.mp4",
                video_title="ร้านกาแฟ EP 2", job_type="drama_episode",
                cover_path="covers/episode_cover.jpg",
                generated_images=["generated/scene_01.png"],
            )
            cover = folder / "covers" / "episode_cover.jpg"
            cover.parent.mkdir()
            cover.write_bytes(b"dedicated-cover")
            scene = folder / "generated" / "scene_01.png"
            scene.parent.mkdir()
            scene.write_bytes(b"scene-preview")

            detail = VideoLibrary(temp).item_detail("story:STORY-COVER")

            self.assertEqual(Path(detail["cover_path"]), cover)
            self.assertEqual(Path(detail["preview_path"]), scene)

    def test_cover_path_cannot_escape_job_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _ = self._job(
                temp, "stories", "STORY-COVER-SAFE", "videos/story_short_complete.mp4",
                cover_path="../outside.jpg",
            )
            outside = folder.parent / "outside.jpg"
            outside.write_bytes(b"outside")

            detail = VideoLibrary(temp).item_detail("story:STORY-COVER-SAFE")

            self.assertEqual(detail["cover_path"], "")

    def test_ignores_missing_outside_or_non_ready_video(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _ = self._job(temp, "products", "JOB-MISSING", "videos/missing.mp4")
            (folder / "videos" / "missing.mp4").unlink()
            self._job(temp, "stories", "STORY-OUTSIDE", "videos/main.mp4")
            manifest_path = Path(temp) / "workspace" / "stories" / "STORY-OUTSIDE" / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["video_path"] = "../outside.mp4"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(VideoLibrary(temp).list_items(), [])

    def test_delete_recycles_only_main_video_and_preserves_project_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, video = self._job(temp, "stories", "STORY-DELETE", "videos/story_short_complete.mp4", video_title="เรื่องลบ")
            intermediate = folder / "videos" / "story_short_final.mp4"
            intermediate.write_bytes(b"keep-me")
            image = folder / "generated" / "scene_01.png"
            image.parent.mkdir(); image.write_bytes(b"image")
            recycled = []

            def recycle(path):
                recycled.append(Path(path))
                Path(path).unlink()

            library = VideoLibrary(temp, recycler=recycle)
            item = library.list_items()[0]
            deleted = library.delete_item(item["item_id"])
            manifest = json.loads((folder / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(recycled, [video])
            self.assertEqual(deleted["title"], "เรื่องลบ")
            self.assertFalse(video.exists())
            self.assertTrue(intermediate.exists())
            self.assertTrue(image.exists())
            self.assertEqual(manifest["video_status"], "deleted")
            self.assertEqual(manifest["video_path"], "")
            self.assertEqual(library.list_items(), [])

    def test_delete_job_renders_recycles_all_videos_but_preserves_project_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, main_video = self._job(
                temp,
                "products",
                "JOB-CLEAR",
                "videos/final_with_audio.mp4",
                product_name="สินค้าทดสอบเคลียร์",
                audio_mix_status="ready",
                audio_mix_path="videos/final_with_audio.mp4",
                flow_clips={"1": "videos/flow_shot_01.mp4"},
                flow_clip_count=1,
            )
            flow_clip = folder / "videos" / "flow_shot_01.mp4"
            flow_clip.write_bytes(b"flow")
            nested = folder / "videos" / "drafts" / "preview.webm"
            nested.parent.mkdir()
            nested.write_bytes(b"preview")
            image = folder / "generated" / "selling_image_01.png"
            image.parent.mkdir()
            image.write_bytes(b"image")
            voice = folder / "audio" / "voiceover.mp3"
            voice.parent.mkdir()
            voice.write_bytes(b"voice")
            recycled = []

            def recycle(path):
                recycled.append(Path(path))
                Path(path).unlink()

            library = VideoLibrary(temp, recycler=recycle)
            summary = library.rendered_summary("product:JOB-CLEAR")
            self.assertEqual(summary["file_count"], 3)
            result = library.delete_job_renders("product:JOB-CLEAR")
            manifest = json.loads((folder / "job.json").read_text(encoding="utf-8"))

            self.assertEqual(result["deleted_count"], 3)
            self.assertEqual(set(recycled), {main_video, flow_clip, nested})
            self.assertFalse(main_video.exists())
            self.assertFalse(flow_clip.exists())
            self.assertFalse(nested.exists())
            self.assertTrue(image.exists())
            self.assertTrue(voice.exists())
            self.assertEqual(manifest["video_status"], "deleted")
            self.assertEqual(manifest["video_path"], "")
            self.assertEqual(manifest["audio_mix_path"], "")
            self.assertEqual(manifest["audio_mix_status"], "not_rendered")
            self.assertEqual(manifest["flow_clips"], {})

    def test_delete_all_renders_covers_product_and_story_projects(self):
        with tempfile.TemporaryDirectory() as temp:
            _product, product_video = self._job(temp, "products", "JOB-ALL", "videos/product.mp4")
            _story, story_video = self._job(temp, "stories", "STORY-ALL", "videos/story.mp4")

            def recycle(path):
                Path(path).unlink()

            result = VideoLibrary(temp, recycler=recycle).delete_all_renders()
            self.assertEqual(result["job_count"], 2)
            self.assertEqual(result["deleted_count"], 2)
            self.assertFalse(product_video.exists())
            self.assertFalse(story_video.exists())

    def test_delete_project_recycles_entire_folder_and_removes_job_record(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, video = self._job(temp, "products", "JOB-WHOLE", "videos/final.mp4", product_name="สินค้าลบทั้งงาน")
            image = folder / "generated" / "selling_01.png"
            image.parent.mkdir()
            image.write_bytes(b"image")
            voice = folder / "audio" / "voice.mp3"
            voice.parent.mkdir()
            voice.write_bytes(b"voice")
            recycled = []

            def recycle(path):
                path = Path(path)
                recycled.append(path)
                shutil.rmtree(path)

            library = VideoLibrary(temp, recycler=recycle)
            summary = library.project_summary("product:JOB-WHOLE")
            self.assertEqual(summary["job_count"], 1)
            self.assertEqual(summary["file_count"], 4)
            self.assertTrue(video.exists())

            result = library.delete_project("product:JOB-WHOLE")

            self.assertEqual(recycled, [folder])
            self.assertEqual(result["deleted_count"], 1)
            self.assertEqual(result["deleted_projects"], ["JOB-WHOLE"])
            self.assertEqual(result["deleted_file_count"], 4)
            self.assertFalse(folder.exists())
            self.assertEqual(library.project_summary()["job_count"], 0)

    def test_delete_completed_projects_leaves_incomplete_job_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            completed_product, _ = self._job(temp, "products", "JOB-DONE", "videos/product.mp4")
            completed_story, _ = self._job(temp, "stories", "STORY-DONE", "videos/story.mp4")
            incomplete, _ = self._job(temp, "products", "JOB-WORKING", "videos/draft.mp4")
            incomplete_manifest_path = incomplete / "job.json"
            incomplete_manifest = json.loads(incomplete_manifest_path.read_text(encoding="utf-8"))
            incomplete_manifest.update({"status": "draft", "video_status": "missing", "automation_status": "running", "pipeline_stage": "images"})
            incomplete_manifest_path.write_text(json.dumps(incomplete_manifest, ensure_ascii=False), encoding="utf-8")
            recycled = []

            def recycle(path):
                path = Path(path)
                recycled.append(path)
                shutil.rmtree(path)

            library = VideoLibrary(temp, recycler=recycle)
            completed_summary = library.project_summary(completed_only=True)
            self.assertEqual(completed_summary["job_count"], 2)

            result = library.delete_completed_projects()

            self.assertEqual(result["deleted_count"], 2)
            self.assertEqual(set(recycled), {completed_product, completed_story})
            self.assertFalse(completed_product.exists())
            self.assertFalse(completed_story.exists())
            self.assertTrue(incomplete.exists())
            remaining = library.project_summary()
            self.assertEqual(remaining["job_count"], 1)
            self.assertEqual(remaining["groups"][0]["job_id"], "JOB-WORKING")

    def test_project_summary_tolerates_malformed_deleted_render_count(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _ = self._job(temp, "products", "JOB-MALFORMED", "videos/draft.mp4")
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"status": "draft", "video_status": "missing", "rendered_files_deleted_count": "unknown"})
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            summary = VideoLibrary(temp).project_summary()

            self.assertEqual(summary["job_count"], 1)
            self.assertFalse(summary["groups"][0]["completed"])

    def test_delete_all_product_projects_removes_products_but_keeps_stories(self):
        with tempfile.TemporaryDirectory() as temp:
            product_one, _ = self._job(temp, "products", "JOB-ONE", "videos/one.mp4")
            product_two, _ = self._job(temp, "products", "JOB-TWO", "videos/two.mp4")
            story, _ = self._job(temp, "stories", "STORY-KEEP", "videos/story.mp4")
            recycled = []

            def recycle(path):
                path = Path(path)
                recycled.append(path)
                shutil.rmtree(path)

            library = VideoLibrary(temp, recycler=recycle)
            product_summary = library.project_summary(kind="product")
            self.assertEqual(product_summary["job_count"], 2)

            result = library.delete_all_projects(kind="product")

            self.assertEqual(result["deleted_count"], 2)
            self.assertEqual(set(recycled), {product_one, product_two})
            self.assertFalse(product_one.exists())
            self.assertFalse(product_two.exists())
            self.assertTrue(story.exists())
            self.assertEqual(library.project_summary(kind="product")["job_count"], 0)
            self.assertEqual(library.project_summary(kind="story")["job_count"], 1)

    def test_delete_project_reports_the_real_recycle_error(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _ = self._job(temp, "products", "JOB-LOCKED", "videos/locked.mp4")

            def recycle(_path):
                raise OSError("ไฟล์กำลังถูกใช้งาน (รหัส 32)")

            result = VideoLibrary(temp, recycler=recycle).delete_all_projects(kind="product")

            self.assertEqual(result["deleted_count"], 0)
            self.assertEqual(result["failed_count"], 1)
            self.assertEqual(result["failed_projects"], ["JOB-LOCKED"])
            self.assertEqual(result["failures"][0]["job_id"], "JOB-LOCKED")
            self.assertIn("รหัส 32", result["failures"][0]["error"])
            self.assertTrue(folder.exists())

    def test_delete_project_repairs_access_denied_source_and_retries_once(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _ = self._job(temp, "products", "JOB-ACL", "videos/acl.mp4")
            calls = []

            def recycle(path):
                calls.append("recycle")
                if calls.count("recycle") == 1:
                    raise OSError("สิทธิ์ของโฟลเดอร์ต้นทางปฏิเสธการลบ (รหัส 120)")
                shutil.rmtree(path)

            library = VideoLibrary(temp, recycler=recycle)

            def repair(container):
                calls.append(("repair", Path(container)))

            library._repair_delete_container_acl = repair
            result = library.delete_all_projects(kind="product")

            self.assertEqual(result["deleted_count"], 1)
            self.assertEqual(result["failed_count"], 0)
            self.assertEqual(calls[0], "recycle")
            self.assertEqual(calls[1], ("repair", Path(temp).resolve() / "workspace" / "products"))
            self.assertEqual(calls[2], "recycle")
            self.assertFalse(folder.exists())

    def test_delete_project_stages_contents_when_the_job_folder_is_locked(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, video = self._job(temp, "products", "JOB-STAGED", "videos/staged.mp4")
            calls = []

            def recycle(path):
                path = Path(path)
                calls.append(path)
                if path == folder:
                    raise OSError("สิทธิ์ของโฟลเดอร์ต้นทางปฏิเสธการลบ (รหัส 120)")
                shutil.rmtree(path)

            library = VideoLibrary(temp, recycler=recycle)
            library._repair_delete_container_acl = lambda _container: None
            result = library.delete_all_projects(kind="product")

            self.assertEqual(result["deleted_count"], 1)
            self.assertEqual(result["failed_count"], 0)
            self.assertFalse(folder.exists())
            self.assertFalse(video.exists())
            self.assertEqual(calls[0], folder)
            self.assertEqual(calls[1], folder)
            self.assertEqual(calls[2].name, folder.name)
            self.assertTrue(calls[2].parent.name.startswith(".smartpost-recycle-"))

    def test_delete_project_copies_before_purging_when_moved_objects_stay_locked(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, video = self._job(temp, "products", "JOB-COPIED", "videos/copied.mp4")
            calls = []

            def recycle(path):
                path = Path(path)
                calls.append(path)
                if len(calls) <= 3:
                    raise OSError("สิทธิ์ของโฟลเดอร์ต้นทางปฏิเสธการลบ (รหัส 120)")
                shutil.rmtree(path)

            library = VideoLibrary(temp, recycler=recycle)
            library._repair_delete_container_acl = lambda _container: None
            result = library.delete_all_projects(kind="product")

            self.assertEqual(result["deleted_count"], 1)
            self.assertEqual(result["failed_count"], 0)
            self.assertFalse(folder.exists())
            self.assertFalse(video.exists())
            self.assertEqual(len(calls), 4)
            self.assertEqual(calls[3].name, folder.name)
            self.assertTrue(calls[3].parent.name.startswith(".smartpost-copy-recycle-"))

    def test_library_exposes_truthful_hybrid_source_breakdown_for_product_and_story(self):
        with tempfile.TemporaryDirectory() as temp:
            product, _ = self._job(
                temp, "products", "JOB-HYBRID", "videos/product_final.mp4",
                product_name="สินค้าผสม",
                video_source_type="google_flow_hybrid_composite",
                flow_target_clip_count=3,
                flow_clips={"1": "videos/flow_01.mp4", "3": "videos/flow_03.mp4"},
                flow_local_motion_clips={"2": "videos/product_local_motion_02.mp4"},
            )
            for name in ("flow_01.mp4", "flow_03.mp4", "product_local_motion_02.mp4"):
                (product / "videos" / name).write_bytes(name.encode())

            story, _ = self._job(
                temp, "stories", "STORY-HYBRID", "videos/story_final.mp4",
                video_title="เรื่องผสม",
                video_generation_mode="google_flow",
                video_source_type="google_flow_story_hybrid_fallback",
                scene_count=4,
                flow_clips={
                    "1": "videos/flow_scene_01.mp4",
                    "2": "videos/flow_scene_02.mp4",
                    "4": "videos/flow_scene_04.mp4",
                },
                flow_fallback_clips={"3": "videos/local_motion_scene_03.mp4"},
            )
            for name in ("flow_scene_01.mp4", "flow_scene_02.mp4", "flow_scene_04.mp4", "local_motion_scene_03.mp4"):
                (story / "videos" / name).write_bytes(name.encode())

            library = VideoLibrary(temp)
            product_item = library.item_detail("product:JOB-HYBRID")
            story_item = library.item_detail("story:STORY-HYBRID")

            self.assertEqual(product_item["video_source_type"], "google_flow_hybrid_composite")
            self.assertEqual(product_item["source_breakdown"], {"remote": 2, "local": 1, "total": 3, "target": 3})
            self.assertEqual(product_item["video_source_label"], "Hybrid • Google Flow 2 + Local Motion 1 / 3 ช็อต")
            self.assertEqual(story_item["video_source_type"], "google_flow_story_hybrid_fallback")
            self.assertEqual(story_item["source_breakdown"], {"remote": 3, "local": 1, "total": 4, "target": 4})
            self.assertEqual(story_item["video_source_label"], "Hybrid • Google Flow 3 + Local Motion 1 / 4 ฉาก")

    def test_incomplete_hybrid_label_uses_target_not_current_total_as_denominator(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _ = self._job(
                temp, "products", "JOB-HYBRID-PARTIAL", "videos/product_final.mp4",
                product_name="สินค้าผสมยังไม่ครบ",
                video_source_type="google_flow_hybrid_composite",
                flow_target_clip_count=3,
                flow_clips={"1": "videos/flow_01.mp4"},
                flow_local_motion_clips={"2": "videos/product_local_motion_02.mp4"},
            )
            (folder / "videos" / "flow_01.mp4").write_bytes(b"flow")
            (folder / "videos" / "product_local_motion_02.mp4").write_bytes(b"local")

            item = VideoLibrary(temp).item_detail("product:JOB-HYBRID-PARTIAL")

            self.assertEqual(item["source_breakdown"], {"remote": 1, "local": 1, "total": 2, "target": 3})
            self.assertEqual(item["video_source_label"], "Hybrid • Google Flow 1 + Local Motion 1 / 3 ช็อต")

    def test_delete_final_after_auto_cleanup_resets_policy_fallback_without_flow_resubmit(self):
        class ValidFinal:
            @staticmethod
            def validate(_path, _manifest=None):
                return {
                    "valid": True,
                    "has_video": True,
                    "has_audio": True,
                    "duration": 15.0,
                    "width": 1080,
                    "height": 1920,
                    "video_codec": "h264",
                    "audio_codec": "aac",
                }

        with tempfile.TemporaryDirectory() as temp:
            history = [{
                "shot_index": 2,
                "failure_code": "FLOW_POLICY_BLOCKED",
                "failure_card_fingerprint": "policy-card-2",
                "flow_run_id": "flow-run-2",
            }]
            folder, final = self._job(
                temp, "products", "JOB-FINAL-ONLY-DELETE", "videos/final.mp4",
                product_name="สินค้าลบ Final",
                status="ready_for_phone",
                automation_status="completed",
                readiness={"ready": True, "missing": []},
                video_ai_provider="flow",
                video_source_type="google_flow_hybrid_composite",
                generated_images=[
                    "generated/selling_image_01.png",
                    "generated/selling_image_02.png",
                    "generated/selling_image_03.png",
                ],
                flow_target_clip_count=3,
                flow_clips={"1": "videos/flow_01.mp4", "3": "videos/flow_03.mp4"},
                flow_remote_clip_count=2,
                flow_local_motion_clips={"2": "videos/product_local_motion_02.mp4"},
                flow_local_motion_clip_count=1,
                flow_segment_count=3,
                flow_policy_fallbacks={
                    "2": {
                        "shot_index": 2,
                        "source_image_index": 2,
                        "source_image": "generated/selling_image_02.png",
                        "failure_code": "FLOW_POLICY_BLOCKED",
                        "policy_category": "policy",
                        "failure_card_fingerprint": "policy-card-2",
                        "flow_run_id": "flow-run-2",
                        "status": "ready",
                        "clip_path": "videos/product_local_motion_02.mp4",
                        "render_plan": {"output": "videos/product_local_motion_02.mp4"},
                    },
                },
                flow_policy_fallback_history=history,
                flow_failed_source_images={
                    "2": {
                        "failure_code": "FLOW_POLICY_BLOCKED",
                        "output_slot": 2,
                        "fallback": "product_local_motion_policy_fallback",
                    },
                },
                flow_segment_provenance={
                    "1": {"source_type": "google_flow", "clip_path": "videos/flow_01.mp4"},
                    "2": {"source_type": "product_local_motion_policy_fallback", "clip_path": "videos/product_local_motion_02.mp4"},
                    "3": {"source_type": "google_flow", "clip_path": "videos/flow_03.mp4"},
                },
            )
            for name in ("flow_01.mp4", "product_local_motion_02.mp4", "flow_03.mp4"):
                (folder / "videos" / name).write_bytes(name.encode())
            generated = folder / "generated"
            generated.mkdir()
            originals = []
            for index in range(1, 4):
                image = generated / f"selling_image_{index:02d}.png"
                image.write_bytes(f"image-{index}".encode())
                originals.append(image)

            cleaner = WorkspaceCleaner(
                temp,
                recycler=lambda path: Path(path).unlink(),
                validator=ValidFinal(),
            )
            cleaned = cleaner.cleanup_completed_job("JOB-FINAL-ONLY-DELETE")
            self.assertEqual(cleaned["failed_count"], 0)
            after_cleanup = json.loads((folder / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(after_cleanup["flow_policy_fallbacks"]["2"]["status"], "finalized")
            self.assertNotIn("clip_path", after_cleanup["flow_policy_fallbacks"]["2"])

            library = VideoLibrary(temp, recycler=lambda path: Path(path).unlink())
            library.delete_item("product:JOB-FINAL-ONLY-DELETE")
            saved = json.loads((folder / "job.json").read_text(encoding="utf-8"))

            fallback = saved["flow_policy_fallbacks"]["2"]
            self.assertFalse(final.exists())
            self.assertEqual(fallback["status"], "render_pending")
            self.assertEqual(fallback["failure_code"], "FLOW_POLICY_BLOCKED")
            self.assertEqual(fallback["failure_card_fingerprint"], "policy-card-2")
            self.assertEqual(fallback["flow_run_id"], "flow-run-2")
            self.assertNotIn("clip_path", fallback)
            self.assertNotIn("render_plan", fallback)
            self.assertNotIn("retained_in_final", fallback)
            self.assertEqual(saved["flow_policy_fallback_history"], history)
            self.assertEqual(saved["flow_failed_source_images"]["2"]["failure_code"], "FLOW_POLICY_BLOCKED")
            self.assertEqual(saved["flow_segment_provenance"], {})
            self.assertEqual(saved["flow_remote_clip_count"], 0)
            self.assertEqual(saved["flow_local_motion_clip_count"], 0)
            self.assertEqual(saved["flow_segment_count"], 0)
            self.assertEqual(saved["video_source_type"], "google_flow_pending")
            self.assertTrue(all(path.is_file() for path in originals))
            with self.assertRaisesRegex(ValueError, "ห้ามส่งเข้า Google Flow ซ้ำ"):
                ProductManager(temp).flow_package("JOB-FINAL-ONLY-DELETE", 2)

    def test_render_cleanup_keeps_product_policy_decision_but_resets_local_clip(self):
        with tempfile.TemporaryDirectory() as temp:
            history = [{"shot_index": 2, "failure_code": "FLOW_POLICY_BLOCKED", "fingerprint": "card-2"}]
            folder, _ = self._job(
                temp, "products", "JOB-HYBRID-CLEAN", "videos/final.mp4",
                product_name="สินค้ารอสร้างใหม่",
                video_ai_provider="flow",
                video_source_type="google_flow_hybrid_composite",
                flow_target_clip_count=2,
                flow_required_clip_count=2,
                flow_clips={"1": "videos/flow_01.mp4"},
                flow_local_motion_clips={"2": "videos/product_local_motion_02.mp4"},
                flow_policy_fallbacks={
                    "2": {
                        "failure_code": "FLOW_POLICY_BLOCKED",
                        "failure_card_fingerprint": "card-2",
                        "status": "ready",
                        "clip_path": "videos/product_local_motion_02.mp4",
                        "render_plan": {"output": "videos/product_local_motion_02.mp4"},
                    },
                },
                flow_policy_fallback_history=history,
                flow_segment_provenance={
                    "1": {"source_type": "google_flow", "clip_path": "videos/flow_01.mp4"},
                    "2": {"source_type": "product_local_motion_policy_fallback", "clip_path": "videos/product_local_motion_02.mp4"},
                },
                flow_remote_clip_count=1,
                flow_local_motion_clip_count=1,
                flow_segment_count=2,
            )
            (folder / "videos" / "flow_01.mp4").write_bytes(b"flow")
            (folder / "videos" / "product_local_motion_02.mp4").write_bytes(b"local")
            original = folder / "generated" / "selling_image_02.png"
            original.parent.mkdir()
            original.write_bytes(b"original-image")

            VideoLibrary(temp, recycler=lambda path: Path(path).unlink()).delete_job_renders("product:JOB-HYBRID-CLEAN")
            saved = json.loads((folder / "job.json").read_text(encoding="utf-8"))

            self.assertEqual(saved["flow_clips"], {})
            self.assertEqual(saved["flow_local_motion_clips"], {})
            self.assertEqual(saved["flow_segment_provenance"], {})
            self.assertEqual(saved["flow_remote_clip_count"], 0)
            self.assertEqual(saved["flow_local_motion_clip_count"], 0)
            self.assertEqual(saved["flow_segment_count"], 0)
            self.assertEqual(saved["video_source_type"], "google_flow_pending")
            self.assertEqual(saved["flow_policy_fallbacks"]["2"]["status"], "render_pending")
            self.assertNotIn("clip_path", saved["flow_policy_fallbacks"]["2"])
            self.assertNotIn("render_plan", saved["flow_policy_fallbacks"]["2"])
            self.assertEqual(saved["flow_policy_fallback_history"], history)
            self.assertTrue(original.is_file())

    def test_render_cleanup_clears_story_fallback_clip_metadata_but_keeps_policy_history(self):
        with tempfile.TemporaryDirectory() as temp:
            policy_history = {"2": [{"failure_code": "FLOW_POLICY_BLOCKED", "failure_card_fingerprint": "story-card"}]}
            folder, _ = self._job(
                temp, "stories", "STORY-HYBRID-CLEAN", "videos/final.mp4",
                video_title="เรื่องรอประกอบใหม่",
                video_generation_mode="google_flow",
                video_source_type="google_flow_story_hybrid_fallback",
                scene_count=2,
                flow_clips={"1": "videos/flow_scene_01.mp4"},
                flow_fallback_clips={"2": "videos/local_motion_scene_02.mp4"},
                flow_fallback_metadata={"2": {"source_type": "story_local_motion_fallback", "image_path": "generated/scene_02.png"}},
                flow_policy_failure_history=policy_history,
                flow_prompt_retries={"2": {"status": "local_motion_fallback_ready", "fallback_clip_path": "videos/local_motion_scene_02.mp4", "fallback_saved_at": "now"}},
                flow_clip_count=1,
                flow_fallback_count=1,
                flow_scene_count=2,
            )
            (folder / "videos" / "flow_scene_01.mp4").write_bytes(b"flow")
            (folder / "videos" / "local_motion_scene_02.mp4").write_bytes(b"local")
            original = folder / "generated" / "scene_02.png"
            original.parent.mkdir()
            original.write_bytes(b"original-scene")

            VideoLibrary(temp, recycler=lambda path: Path(path).unlink()).delete_job_renders("story:STORY-HYBRID-CLEAN")
            saved = json.loads((folder / "job.json").read_text(encoding="utf-8"))

            self.assertEqual(saved["flow_clips"], {})
            self.assertEqual(saved["flow_fallback_clips"], {})
            self.assertEqual(saved["flow_fallback_metadata"], {})
            self.assertEqual(saved["flow_clip_count"], 0)
            self.assertEqual(saved["flow_fallback_count"], 0)
            self.assertEqual(saved["flow_scene_count"], 0)
            self.assertEqual(saved["video_source_type"], "google_flow_pending")
            self.assertEqual(saved["flow_policy_failure_history"], policy_history)
            self.assertEqual(saved["flow_prompt_retries"]["2"]["status"], "local_motion_fallback_pending")
            self.assertNotIn("fallback_clip_path", saved["flow_prompt_retries"]["2"])
            self.assertNotIn("fallback_saved_at", saved["flow_prompt_retries"]["2"])
            self.assertTrue(original.is_file())


if __name__ == "__main__":
    unittest.main()
