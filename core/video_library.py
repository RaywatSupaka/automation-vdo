import ctypes
import os
import re
import shutil
import subprocess
import time
import uuid
import base64
import io
import hashlib
import json
from datetime import datetime
from pathlib import Path

from core.atomic_json import AtomicJsonFile, JsonPersistenceError, runtime_backup_path
from core.clip_cover import image_choices, cover_settings, compose_cover, normalize_cover
from core.job_file_guard import guard_for
from PIL import Image


class VideoLibrary:
    """Expose only the current, user-facing output video of each job."""

    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

    def __init__(self, root, recycler=None, logger=None):
        self.root = Path(root).resolve()
        self.workspace = self.root / "workspace"
        self._recycler = recycler or self._recycle_file
        self._logger = logger
        self.file_guard = guard_for(self.root)

    def _manifest_store(self, manifest_path):
        manifest_path = Path(manifest_path)
        return AtomicJsonFile(
            manifest_path,
            backup_path=runtime_backup_path(self.root, manifest_path),
        )

    def list_items(self):
        items = []
        for kind, manifest_path, manifest in self._manifests():
            try:
                item = self._item(kind, manifest_path, manifest)
                if item:
                    items.append(item)
            except (OSError, ValueError):
                continue
        return sorted(items, key=lambda item: item["updated_at"], reverse=True)

    def item_detail(self, item_id, preloaded_item=None):
        """Return posting metadata and a visual preview for one finished video."""
        requested = str(item_id)
        item = dict(preloaded_item) if isinstance(preloaded_item, dict) and str(preloaded_item.get("item_id")) == requested else None
        if item is None:
            # Resolve one finished job directly, not a full-library scan per thumbnail.
            match = re.fullmatch(r"(product|story):([A-Za-z0-9_-]+)", requested)
            if match:
                kind, job_id = match.groups()
                section = (self.workspace / ("products" if kind == "product" else "stories")).resolve()
                candidate = (section / job_id / "job.json").resolve()
                if section in candidate.parents and candidate.is_file():
                    manifest = self._manifest_store(candidate).read()
                    if not isinstance(manifest, dict):
                        raise ValueError("อ่านข้อมูลรายละเอียดผลงานไม่สำเร็จ")
                    item = self._item(kind, candidate, manifest)
                    if item and item["item_id"] != requested:
                        item = None
        if not item:
            raise ValueError("ไม่พบวิดีโอผลงาน หรือไฟล์ถูกลบไปแล้ว")
        manifest_path = Path(item["manifest_path"]).resolve()
        job_folder = manifest_path.parent.resolve()
        try:
            manifest = self._manifest_store(manifest_path).read()
            if not isinstance(manifest, dict):
                raise ValueError("manifest is not an object")
        except (OSError, ValueError, JsonPersistenceError) as exc:
            raise ValueError("อ่านข้อมูลรายละเอียดผลงานไม่สำเร็จ") from exc

        def read_text(relative):
            path = (job_folder / relative).resolve()
            if job_folder not in path.parents or not path.is_file():
                return ""
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                return ""

        title = str(item.get("title") or "").strip()
        if item["kind"] == "product":
            description = (
                read_text("captions/caption.txt")
                or str(manifest.get("caption") or "").strip()
                or str(manifest.get("video_description") or manifest.get("description") or "").strip()
            )
            hashtags = read_text("captions/hashtags.txt") or self._normalise_hashtags(manifest.get("hashtags"))
            affiliate_link = str(
                manifest.get("posting_product_url")
                or manifest.get("affiliate_url")
                or manifest.get("product_url")
                or ""
            ).strip()
        else:
            title = read_text("captions/video_title.txt") or title
            description = (
                read_text("captions/video_description.txt")
                or str(manifest.get("video_description") or manifest.get("description") or manifest.get("topic") or "").strip()
            )
            hashtags = read_text("captions/hashtags.txt") or self._normalise_hashtags(manifest.get("hashtags"))
            affiliate_link = str(manifest.get("source_url") or manifest.get("reference_url") or "").strip()

            override_path = job_folder / "captions" / "post_metadata.json"
            override = self._manifest_store(override_path).peek(default={})
            if isinstance(override, dict) and override.get("job_id") == item["job_id"]:
                if isinstance(override.get("description"), str):
                    description = override["description"].strip()
                if isinstance(override.get("hashtags"), str):
                    hashtags = override["hashtags"].strip()

        if not hashtags:
            extracted = re.findall(r"(?<!\w)#[^\s#]+", description)
            hashtags = " ".join(dict.fromkeys(tag.rstrip(".,!?;:") for tag in extracted if tag.strip("#")))
        if hashtags:
            for hashtag in hashtags.split():
                description = description.replace(hashtag, "")
            description = re.sub(r"[ \t]{2,}", " ", description)
            description = re.sub(r"\n{3,}", "\n\n", description).strip()

        cover_path = self._detail_cover_path(job_folder, manifest)
        preview_path = self._detail_preview_path(job_folder, manifest)
        post_parts = [title, description, hashtags]
        if affiliate_link:
            post_parts.append(affiliate_link)
        post_revision = hashlib.sha256(json.dumps(
            [description, hashtags], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        return {
            **item,
            "job_folder": str(job_folder),
            "title": title,
            "description": description,
            "hashtags": hashtags,
            "affiliate_link": affiliate_link,
            "cover_path": str(cover_path) if cover_path else "",
            "cover_revision": str(manifest.get("cover_revision") or ""),
            'ai_cover_state': manifest.get('ai_cover_state') or {},
            "preview_path": str(preview_path) if preview_path else "",
            "post_text": "\n\n".join(part for part in post_parts if part).strip(),
            "post_revision": post_revision,
        }

    def save_post_metadata(self, item_id, description, tags, revision):
        """Override only public-facing Story copy, keeping render and AI receipts intact."""
        from core.post_copy import hashtags as clean_hashtags, post_ready_description

        item_id = str(item_id or "")
        if not item_id.startswith("story:"):
            raise ValueError("ตัวแก้ข้อความโพสต์นี้ใช้กับงานเรื่องเล่าเท่านั้น")
        description = str(description or "").strip()
        if not post_ready_description(description):
            raise ValueError("คำอธิบายโพสต์ต้องไม่ว่าง ยาวไม่เกิน 1,800 ตัวอักษร และไม่ใช่สรุปขั้นตอนผลิต")
        tags = clean_hashtags(tags, strict=True)
        initial = self.item_detail(item_id)
        target = Path(initial["job_folder"]) / "captions" / "post_metadata.json"
        store = self._manifest_store(target)
        with store.locked():
            current = self.item_detail(item_id)
            if current["post_revision"] != str(revision or ""):
                raise ValueError("ข้อความโพสต์เปลี่ยนไปแล้ว กรุณาเปิดหน้ารายละเอียดใหม่")
            store.write_unlocked({
                "version": 1,
                "job_id": current["job_id"],
                "description": description,
                "hashtags": tags,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
        return self.item_detail(item_id)

    @staticmethod
    def _normalise_hashtags(value):
        if isinstance(value, (list, tuple, set)):
            parts = [str(part or "").strip() for part in value]
        else:
            parts = str(value or "").replace(",", " ").split()
        tags = []
        for part in parts:
            if not part:
                continue
            tag = part if part.startswith("#") else f"#{part}"
            if tag not in tags:
                tags.append(tag)
        return " ".join(tags)

    def cover_editor(self, item_id):
        detail = self.item_detail(item_id)
        folder = Path(detail["job_folder"])
        manifest = self._manifest_store(detail["manifest_path"]).read()
        choices = image_choices(folder, manifest)
        if not choices:
            raise ValueError("ไม่พบภาพฉากเดิมสำหรับแก้ปก • ไม่มีการสร้างภาพซ้ำ")
        thumbnails = []
        for index, path in choices:
            try:
                with Image.open(path) as opened:
                    image = opened.convert("RGB")
                    image.thumbnail((180, 180))
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=75)
                thumbnails.append({"index": index, "url": "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")})
            except (OSError, ValueError):
                continue
        return {"item_id": item_id, "title": detail["title"],
                'ai_cover_state': manifest.get('ai_cover_state') or {},
                "settings": cover_settings(manifest, choices), "images": thumbnails,
                "revision": str(manifest.get("cover_revision") or manifest.get("cover_path") or ""),
                "aspect_ratio": "16:9" if manifest.get("long_video") else "9:16"}

    def thumbnail(self, item_id):
        """On-demand derived cache only; originals and covers are never overwritten."""
        detail = self.item_detail(item_id)
        source = Path(detail.get("cover_path") or detail.get("preview_path") or "")
        if Path(detail["job_folder"]).resolve() not in source.resolve().parents or not source.is_file():
            raise FileNotFoundError("ไม่มีภาพตัวอย่างของคลิปนี้")
        stamp = source.stat()
        key = hashlib.sha256(f"{source}|{stamp.st_mtime_ns}|{stamp.st_size}|library-v1".encode()).hexdigest()
        folder = self.workspace / ".cache" / "library-thumbnails"
        target = folder / f"{key}.jpg"
        if target.is_file():
            return str(target)
        with Image.open(source) as opened:
            image = opened.convert("RGB")
            image.thumbnail((400, 240), Image.Resampling.LANCZOS)
            folder.mkdir(parents=True, exist_ok=True)
            temporary = folder / f"{key}.{uuid.uuid4().hex}.tmp"
            image.save(temporary, format="JPEG", quality=82)
            temporary.replace(target)
        return str(target)

    def compose_library_cover(self, item_id, settings, revision, *, save=False):
        detail = self.item_detail(item_id)
        folder = Path(detail["job_folder"])
        store = self._manifest_store(detail["manifest_path"])
        if not isinstance(settings, dict) or not isinstance(settings.get("headline"), str):
            raise ValueError("กรุณาระบุข้อความปก")
        if not settings["headline"].strip() or len(settings["headline"].strip()) > 60:
            raise ValueError("ข้อความปกต้องมี 1–60 ตัวอักษร")
        if settings.get("theme") not in ("bold", "mystery", "product", "romance") or settings.get("position") not in ("top", "center", "bottom"):
            raise ValueError("รูปแบบปกไม่ถูกต้อง")
        selected_settings = normalize_cover(settings)
        with store.locked():
            manifest = store.read()
            current_revision = str(manifest.get("cover_revision") or manifest.get("cover_path") or "")
            if current_revision != str(revision):
                raise ValueError("ปกถูกแก้ไขจากหน้าต่างอื่นแล้ว กรุณาปิดและเปิดหน้าปกใหม่")
            if manifest.get("video_status") != "ready":
                raise ValueError("งานกำลังเปลี่ยนสถานะ กรุณารอวิดีโอเสร็จก่อนแก้ปก")
            if not save:
                return {"preview": compose_cover(self.root, folder, manifest, selected_settings, preview=True)}
            changed = compose_cover(self.root, folder, manifest, selected_settings)
            history = list(manifest.get("cover_history") or [])
            if manifest.get("cover_path"):
                history.append({"path": manifest["cover_path"], "settings": manifest.get("cover_settings") or {}})
            manifest.update(changed)
            manifest["cover_history"] = history[-30:]
            # Do not touch video_status, updated_at, narration, receipts or queue state.
            store.write(manifest)
        return {"revision": changed["cover_revision"], "cover_path": changed["cover_path"]}

    @staticmethod
    def _detail_cover_path(job_folder, manifest):
        """Return the dedicated Shorts cover when the pipeline created one."""
        relative = str(manifest.get("cover_path") or "").strip()
        if not relative:
            return None
        path = (job_folder / relative).resolve()
        if (
            job_folder in path.parents
            and path.is_file()
            and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ):
            return path
        return None

    @staticmethod
    def _detail_preview_path(job_folder, manifest):
        candidates = []
        for key in ("generated_images", "source_images"):
            value = manifest.get(key) or []
            if isinstance(value, str):
                value = [value]
            candidates.extend(value)
        candidates.extend((manifest.get("main_image"), manifest.get("source_image")))
        for relative in candidates:
            relative = str(relative or "").strip()
            if not relative:
                continue
            path = (job_folder / relative).resolve()
            if job_folder in path.parents and path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                return path
        for folder_name in ("generated", "original", "source"):
            folder = job_folder / folder_name
            if not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    return path.resolve()
        return None

    @staticmethod
    def _count(value, default=0):
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return max(0, int(default or 0))

    @classmethod
    def _video_source_summary(cls, kind, manifest):
        """Return one truthful, provider-neutral source breakdown for the UI."""
        plan = manifest.get("render_plan") or {}
        if not isinstance(plan, dict):
            plan = {}
        source_type = str(
            manifest.get("video_source_type") or plan.get("source_type") or ""
        ).strip()
        from core.scene_video_plan import enabled as planned_video
        sources = plan.get('scene_video_sources')
        if kind == 'story' and planned_video(manifest) and isinstance(sources, list) and sources:
            # The completion gate verifies this ordered provenance before
            # accepting Final. Historical provider maps may contain alternates.
            flow = sum(row.get('provider') == 'google_flow' for row in sources)
            meta = sum(row.get('provider') == 'meta_ai' for row in sources)
            local = sum(row.get('provider') == 'local' for row in sources)
            target = cls._count(manifest.get('scene_count'), len(sources))
            labels = ([f'Google Flow {flow}'] if flow else []) + ([f'Meta AI {meta}'] if meta else []) + ([f'Local Motion {local}'] if local else [])
            return {'video_source_type': source_type,
                    'video_plan_summary': {'completed': len(sources), 'flow': flow, 'meta': meta,
                                           'local': local, 'pending': max(0, target - len(sources))},
                    'video_source_label': ' + '.join(labels) + f' / {target} ฉาก',
                    'source_remote_count': flow + meta, 'source_flow_count': flow,
                    'source_meta_count': meta, 'source_local_count': local,
                    'source_total_count': len(sources), 'source_target_count': target,
                    'source_breakdown': {'remote': flow + meta, 'flow': flow, 'meta': meta,
                                         'local': local, 'total': len(sources), 'target': target}}
        meta_map = {
            str(key): str(value or '').strip()
            for key, value in (manifest.get('meta_clips') or {}).items()
            if str(value or '').strip()
        }
        meta_count = max(len(meta_map), cls._count(manifest.get('meta_clip_count') or plan.get('meta_clip_count')))
        selected_meta = (source_type.startswith('meta_ai')
                         or (kind == 'story' and manifest.get('video_generation_mode') == 'meta_ai')
                         or (kind == 'product' and manifest.get('video_ai_provider') == 'meta_ai'))

        remote_map = manifest.get("flow_clips")
        remote_map = {
            str(key): str(value or "").strip()
            for key, value in (remote_map or {}).items()
            if str(value or "").strip()
        }
        if kind == "product":
            local_map = manifest.get("flow_local_motion_clips")
            local_count_value = manifest.get("flow_local_motion_clip_count")
            target = cls._count(
                manifest.get("flow_required_clip_count")
                or manifest.get("flow_target_clip_count")
                or len(manifest.get("generated_images") or manifest.get("source_images") or [])
            )
            unit = "ช็อต"
        else:
            local_map = manifest.get("flow_fallback_clips")
            local_count_value = manifest.get("flow_fallback_count")
            target = cls._count(manifest.get("scene_count"))
            unit = "ฉาก"
        local_map = {
            str(key): str(value or "").strip()
            for key, value in (local_map or {}).items()
            if str(value or "").strip()
        }

        # Final-only cleanup may intentionally remove intermediate clip files
        # while retaining their provenance counters on the accepted Final.
        remote_count = max(
            len(remote_map),
            cls._count(
                manifest.get("flow_remote_clip_count")
                or manifest.get("flow_clip_count")
                or plan.get("flow_remote_clip_count")
                or plan.get("flow_clip_count")
            ),
        )
        local_count = max(
            len(local_map),
            cls._count(
                local_count_value
                or plan.get("flow_local_motion_clip_count")
                or plan.get("flow_fallback_count")
            ),
        )
        mapped_slots = set(remote_map) | set(local_map)
        declared_total = (
            manifest.get("flow_segment_count") if kind == "product"
            else manifest.get("flow_scene_count")
        )
        total_count = max(
            len(mapped_slots),
            cls._count(declared_total or plan.get("scene_source_count")),
            remote_count + local_count,
        )
        if selected_meta:
            # A provider switch retains historical Flow files. They must not
            # inflate the selected Meta source count or label on this Final.
            remote_count, local_count = meta_count, 0
            total_count = max(len(meta_map), meta_count, cls._count(plan.get('scene_source_count')))
        if not target and (remote_count or local_count or "google_flow" in source_type):
            target = total_count

        hybrid = bool(not selected_meta and (local_count or "hybrid" in source_type))
        if selected_meta:
            label = f"Meta AI {meta_count}/{target or meta_count} {unit}"
        elif hybrid:
            label = (
                f"Hybrid • Google Flow {remote_count} + Local Motion {local_count}"
                f" / {target or total_count} {unit}"
            )
        elif remote_count or "google_flow" in source_type or source_type.startswith("flow_"):
            label = f"Google Flow {remote_count}/{target or remote_count} {unit}"
        elif kind == "story" and source_type in {"story_image_sequence", "drama_mixed_media"}:
            label = f"Motion ในเครื่อง{f' • {target} {unit}' if target else ''}"
        elif kind == "product" and source_type == "manual_uploaded_video":
            label = "วิดีโอจากไฟล์"
        else:
            label = "วิดีโอ Final"

        return {
            "video_source_type": source_type,
            "video_source_label": label,
            "source_remote_count": remote_count,
            "source_meta_count": meta_count,
            "source_local_count": local_count,
            "source_total_count": total_count,
            "source_target_count": target,
            "source_breakdown": {
                "remote": remote_count,
                "local": local_count,
                "total": total_count,
                "target": target,
            },
        }

    def rendered_summary(self, item_id=""):
        """Describe video render files without mutating them."""
        groups = self._render_groups(item_id)
        return {
            "job_count": len(groups),
            "file_count": sum(len(group["paths"]) for group in groups),
            "size_bytes": sum(group["size_bytes"] for group in groups),
            "groups": groups,
        }

    def project_summary(self, item_id="", completed_only=False, kind=""):
        """Describe complete job folders, including projects with deleted renders."""
        groups = self._project_groups(item_id=item_id, completed_only=completed_only, kind=kind)
        return {
            "job_count": len(groups),
            "file_count": sum(group["file_count"] for group in groups),
            "size_bytes": sum(group["size_bytes"] for group in groups),
            "groups": groups,
        }

    def delete_job_renders(self, item_id):
        summary = self.rendered_summary(item_id)
        if not summary["groups"]:
            raise ValueError("ไม่พบหัวข้อที่เลือก")
        if not summary["file_count"]:
            raise ValueError("หัวข้อนี้ไม่มีไฟล์วิดีโอที่เรนเดอร์แล้ว")
        return self._delete_groups(summary["groups"])

    def delete_all_renders(self):
        summary = self.rendered_summary()
        if not summary["file_count"]:
            raise ValueError("ไม่มีไฟล์วิดีโอที่เรนเดอร์ให้เคลียร์")
        return self._delete_groups(summary["groups"])

    def delete_project(self, item_id):
        summary = self.project_summary(item_id=item_id)
        if not summary["groups"]:
            raise ValueError("ไม่พบโปรเจกต์ที่เลือก")
        return self._delete_project_groups(summary["groups"])

    def delete_completed_projects(self):
        summary = self.project_summary(completed_only=True)
        if not summary["groups"]:
            raise ValueError("ไม่มีโปรเจกต์ที่ทำเสร็จแล้วให้ลบ")
        return self._delete_project_groups(summary["groups"])

    def delete_all_projects(self, kind=""):
        summary = self.project_summary(kind=kind)
        if not summary["groups"]:
            raise ValueError("ไม่มีโปรเจกต์ให้ลบ")
        return self._delete_project_groups(summary["groups"])

    def delete_item(self, item_id):
        job_id = self.file_guard.job_id(item_id)
        with self.file_guard.deletion(job_id):
            return self._delete_item_claimed(item_id)

    def _delete_item_claimed(self, item_id):
        item = next((row for row in self.list_items() if row["item_id"] == str(item_id)), None)
        if not item:
            raise ValueError("ไม่พบวิดีโอผลงาน หรือไฟล์ถูกลบไปแล้ว")
        path = Path(item["path"])
        self._guarded_recycle(path)
        if path.exists():
            raise OSError("Windows ยังไม่ได้ย้ายไฟล์ไปถังรีไซเคิล")

        manifest_path = Path(item["manifest_path"])
        # Apply the same checkpoint cleanup used by bulk render deletion.
        # After Final-only cleanup, the local clip path is already gone and
        # the authenticated policy decision points at the retained Final.
        self._update_manifest_after_render_delete(manifest_path, [path])
        store = self._manifest_store(manifest_path)
        relative = str(item["relative_path"])

        def update_manifest(manifest):
            manifest.update({
                "video_path": "",
                "video_status": "deleted",
                "status": "video_deleted",
                "deleted_video_path": relative,
                "deleted_video_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
            return manifest

        store.update(update_manifest)
        return item

    def _manifests(self):
        for kind, folder, pattern in (
            ("product", self.workspace / "products", "JOB-*/job.json"),
            ("story", self.workspace / "stories", "STORY-*/job.json"),
        ):
            for job_folder in folder.glob(pattern.split('/')[0]):
                manifest_path = job_folder / pattern.split('/')[-1]
                if not manifest_path.is_file() and not runtime_backup_path(self.root, manifest_path).is_file():
                    continue
                try:
                    manifest = self._manifest_store(manifest_path).peek()
                    if isinstance(manifest, dict):
                        yield kind, manifest_path.resolve(), manifest
                except (OSError, ValueError, JsonPersistenceError):
                    continue

    def _render_groups(self, item_id=""):
        requested = str(item_id or "").strip()
        groups = []
        found_requested = not requested
        for kind, manifest_path, manifest in self._manifests():
            job_id = str(manifest.get("id") or manifest_path.parent.name)
            current_id = f"{kind}:{job_id}"
            if requested and current_id != requested:
                continue
            found_requested = True
            job_folder = manifest_path.parent.resolve()
            videos_folder = (job_folder / "videos").resolve()
            paths = []
            if videos_folder.is_dir():
                for candidate in videos_folder.rglob("*"):
                    try:
                        resolved = candidate.resolve()
                        if (
                            candidate.is_file()
                            and videos_folder in resolved.parents
                            and resolved.suffix.lower() in self.VIDEO_EXTENSIONS
                        ):
                            paths.append(resolved)
                    except OSError:
                        continue
            paths = sorted(set(paths), key=lambda path: path.name.lower())
            if not paths and not requested:
                continue
            title = str(
                manifest.get("video_title")
                or manifest.get("product_name")
                or manifest.get("topic")
                or job_id
            ).strip()
            groups.append({
                "item_id": current_id,
                "aspect_ratio": '16:9' if manifest.get('long_video') else '9:16',
                "kind": kind,
                "job_id": job_id,
                "title": title,
                "manifest_path": str(manifest_path),
                "folder": str(job_folder),
                "paths": [str(path) for path in paths],
                "size_bytes": sum(path.stat().st_size for path in paths),
            })
        if requested and not found_requested:
            raise ValueError("ไม่พบหัวข้อที่เลือก")
        return groups

    def _project_groups(self, item_id="", completed_only=False, kind=""):
        requested = str(item_id or "").strip()
        requested_kind = str(kind or "").strip().lower()
        if requested_kind and requested_kind not in {"product", "story"}:
            raise ValueError("ประเภทโปรเจกต์ไม่ถูกต้อง")
        groups = []
        found_requested = not requested
        for current_kind, manifest_path, manifest in self._manifests():
            if requested_kind and current_kind != requested_kind:
                continue
            job_id = str(manifest.get("id") or manifest_path.parent.name)
            current_id = f"{current_kind}:{job_id}"
            if requested and current_id != requested:
                continue
            found_requested = True
            if completed_only and not self._project_is_completed(manifest):
                continue
            job_folder = manifest_path.parent.resolve()
            expected_parent = (self.workspace / ("products" if current_kind == "product" else "stories")).resolve()
            if job_folder.parent != expected_parent:
                continue
            file_count = 0
            size_bytes = 0
            for candidate in job_folder.rglob("*"):
                try:
                    resolved = candidate.resolve()
                    if candidate.is_file() and job_folder in resolved.parents:
                        file_count += 1
                        size_bytes += candidate.stat().st_size
                except OSError:
                    continue
            title = str(
                manifest.get("video_title")
                or manifest.get("product_name")
                or manifest.get("topic")
                or job_id
            ).strip()
            groups.append({
                "item_id": current_id,
                "kind": current_kind,
                "content_kind": (
                    "product" if current_kind == "product"
                    else "drama" if manifest.get("job_type") == "drama_episode"
                    else "story"
                ),
                "kind_label": (
                    "สินค้า Affiliate" if current_kind == "product"
                    else "ละครสั้น AI" if manifest.get("job_type") == "drama_episode"
                    else "คลิปยาว" if manifest.get('long_video') else "Story Shorts"
                ),
                "job_id": job_id,
                "title": title,
                "status": str(manifest.get("video_status") or manifest.get("status") or "—"),
                "created_at": str(manifest.get("created_at") or ""),
                "updated_at": str(manifest.get("updated_at") or ""),
                "folder": str(job_folder),
                "manifest_path": str(manifest_path),
                "file_count": file_count,
                "size_bytes": size_bytes,
                "completed": self._project_is_completed(manifest),
                **self._video_source_summary(current_kind, manifest),
            })
        if requested and not found_requested:
            raise ValueError("ไม่พบโปรเจกต์ที่เลือก")
        return sorted(
            groups,
            key=lambda group: (group["created_at"] or group["updated_at"], group["job_id"]),
            reverse=True,
        )

    @staticmethod
    def _project_is_completed(manifest):
        try:
            deleted_render_count = int(manifest.get("rendered_files_deleted_count") or 0)
        except (TypeError, ValueError):
            deleted_render_count = 0
        video_status = str(manifest.get("video_status") or "").strip().lower()
        automation_status = str(manifest.get("automation_status") or "").strip().lower()
        pipeline_stage = str(manifest.get("pipeline_stage") or "").strip().lower()
        status = str(manifest.get("status") or "").strip().lower()
        return bool(
            video_status in {"ready", "deleted"}
            or automation_status == "completed"
            or pipeline_stage == "complete"
            or status in {"ready", "ready_for_phone", "posted", "video_deleted"}
            or deleted_render_count > 0
        )

    def _delete_groups(self, groups):
        result = dict(job_count=0, deleted_count=0, failed_count=0,
                      deleted_paths=[], failed_paths=[], skipped_count=0, skipped_projects=[], failures=[])
        for group in groups:
            try:
                with self.file_guard.deletion(group['job_id']):
                    row = self._delete_groups_claimed([group])
                for key in ('job_count', 'deleted_count', 'failed_count'):
                    result[key] += row[key]
                for key in ('deleted_paths', 'failed_paths'):
                    result[key].extend(row[key])
            except ValueError as exc:
                result['skipped_count'] += 1
                result['skipped_projects'].append(group['job_id'])
                result['failures'].append({'job_id': group['job_id'], 'error': str(exc)})
        return result

    def _guarded_recycle(self, path):
        job_id = self.file_guard.job_id(path)
        claim = getattr(self.file_guard.local, 'deletion', None)
        self.file_guard.recheck(claim, job_id)
        return self._recycler(path)

    def _delete_groups_claimed(self, groups):
        deleted_paths = []
        failed_paths = []
        updated_jobs = []
        for group in groups:
            removed_for_job = []
            for value in group["paths"]:
                path = Path(value).resolve()
                try:
                    self._guarded_recycle(path)
                except Exception:
                    if path.exists():
                        failed_paths.append(str(path))
                        continue
                if path.exists():
                    failed_paths.append(str(path))
                else:
                    deleted_paths.append(str(path))
                    removed_for_job.append(path)
            if removed_for_job:
                self._update_manifest_after_render_delete(Path(group["manifest_path"]), removed_for_job)
                updated_jobs.append(group["job_id"])
        return {
            "job_count": len(set(updated_jobs)),
            "deleted_count": len(deleted_paths),
            "failed_count": len(failed_paths),
            "deleted_paths": deleted_paths,
            "failed_paths": failed_paths,
        }

    def _delete_project_groups(self, groups):
        result = dict(deleted_count=0, failed_count=0, deleted_size_bytes=0, deleted_file_count=0,
                      deleted_projects=[], failed_projects=[], failures=[], pending_empty_folders=[],
                      skipped_count=0, skipped_projects=[])
        for group in groups:
            try:
                with self.file_guard.deletion(group['job_id']):
                    row = self._delete_project_groups_claimed([group])
                for key in ('deleted_count', 'failed_count', 'deleted_size_bytes', 'deleted_file_count'):
                    result[key] += row[key]
                for key in ('deleted_projects', 'failed_projects', 'failures', 'pending_empty_folders'):
                    result[key].extend(row[key])
            except ValueError as exc:
                result['skipped_count'] += 1
                result['skipped_projects'].append(group['job_id'])
                result['failures'].append({'job_id': group['job_id'], 'error': str(exc)})
        return result

    def _delete_project_groups_claimed(self, groups):
        deleted_projects = []
        failed_projects = []
        failures = []
        pending_empty_folders = []
        deleted_size_bytes = 0
        deleted_file_count = 0
        for group in groups:
            folder = Path(group["folder"]).resolve()
            expected_parent = (self.workspace / ("products" if group["kind"] == "product" else "stories")).resolve()
            if folder.parent != expected_parent or not folder.is_dir():
                failed_projects.append(group["job_id"])
                failures.append({
                    "job_id": group["job_id"],
                    "folder": str(folder),
                    "error": "ไม่พบโฟลเดอร์โปรเจกต์ หรือพาธอยู่นอกพื้นที่งานที่อนุญาต",
                })
                continue
            try:
                recycle_result = self._recycle_project_folder(folder, expected_parent)
            except Exception as exc:
                if folder.exists():
                    failed_projects.append(group["job_id"])
                    failures.append({
                        "job_id": group["job_id"],
                        "folder": str(folder),
                        "error": str(exc) or type(exc).__name__,
                    })
                    continue
            if folder.exists() and any(folder.iterdir()):
                failed_projects.append(group["job_id"])
                failures.append({
                    "job_id": group["job_id"],
                    "folder": str(folder),
                    "error": "Windows ยังไม่ได้ย้ายโฟลเดอร์ลงถังขยะ อาจมีไฟล์กำลังถูกใช้งาน",
                })
            else:
                deleted_projects.append(group["job_id"])
                deleted_size_bytes += int(group.get("size_bytes") or 0)
                deleted_file_count += int(group.get("file_count") or 0)
                if recycle_result.get("empty_folder_pending"):
                    pending_empty_folders.append(str(folder))
        if self._logger:
            if failures:
                details = "; ".join(f"{row['job_id']}: {row['error']}" for row in failures)
                self._logger.error(
                    "state=PROJECT_DELETE result=partial deleted=%s failed=%s errors=%s",
                    len(deleted_projects),
                    len(failures),
                    details,
                )
            else:
                self._logger.info(
                    "state=PROJECT_DELETE result=completed deleted=%s files=%s",
                    len(deleted_projects),
                    deleted_file_count,
                )
        return {
            "deleted_count": len(deleted_projects),
            "failed_count": len(failed_projects),
            "deleted_projects": deleted_projects,
            "failed_projects": failed_projects,
            "failures": failures,
            "pending_empty_folders": pending_empty_folders,
            "deleted_size_bytes": deleted_size_bytes,
            "deleted_file_count": deleted_file_count,
        }

    def _recycle_project_folder(self, folder, expected_parent):
        try:
            self._guarded_recycle(folder)
            return {"empty_folder_pending": False}
        except Exception as exc:
            if not folder.exists():
                return {"empty_folder_pending": False}
            if not self._is_source_access_denied(exc):
                raise

        self._repair_delete_container_acl(expected_parent)
        try:
            self._guarded_recycle(folder)
            return {"empty_folder_pending": False}
        except Exception as exc:
            if not folder.exists():
                return {"empty_folder_pending": False}
            if not self._is_source_access_denied(exc):
                raise
        return self._recycle_locked_project_contents(folder, expected_parent)

    def _recycle_locked_project_contents(self, folder, expected_parent):
        """Preserve a locked project's contents in Recycle Bin via a clean staging folder."""
        folder = Path(folder).resolve()
        expected_parent = Path(expected_parent).resolve()
        if folder.parent != expected_parent or not folder.is_dir():
            raise ValueError("ไม่อนุญาตให้ย้ายข้อมูลนอกโฟลเดอร์โปรเจกต์")
        self.file_guard.recheck(getattr(self.file_guard.local, 'deletion', None), self.file_guard.job_id(folder))
        stage_parent = expected_parent / f".smartpost-recycle-{uuid.uuid4().hex}"
        staged_folder = stage_parent / folder.name
        staged_folder.mkdir(parents=True)
        moved = []
        try:
            for child in list(folder.iterdir()):
                destination = staged_folder / child.name
                os.replace(child, destination)
                moved.append((child, destination))
            self._recycler(staged_folder)
            if staged_folder.exists():
                raise OSError("Windows ยังไม่ได้ย้ายข้อมูลโปรเจกต์จากพื้นที่พักลงถังขยะ")
        except Exception as exc:
            if staged_folder.exists():
                for original, staged in reversed(moved):
                    if staged.exists() and not original.exists():
                        os.replace(staged, original)
            try:
                staged_folder.rmdir()
                stage_parent.rmdir()
            except OSError:
                pass
            if self._is_source_access_denied(exc):
                return self._recycle_clean_copy_and_purge(folder, expected_parent)
            raise

        try:
            stage_parent.rmdir()
        except OSError:
            pass
        try:
            folder.rmdir()
        except OSError:
            self._schedule_delete_on_reboot(folder)
        pending = folder.exists()
        if self._logger:
            self._logger.info(
                "state=PROJECT_DELETE_FALLBACK result=completed folder=%s empty_folder_pending=%s",
                folder,
                pending,
            )
        return {"empty_folder_pending": pending}

    def _recycle_clean_copy_and_purge(self, folder, expected_parent):
        """Back up a handle-locked project to Recycle Bin before purging its originals."""
        folder = Path(folder).resolve()
        expected_parent = Path(expected_parent).resolve()
        if folder.parent != expected_parent or not folder.is_dir():
            raise ValueError("ไม่อนุญาตให้สำรองข้อมูลนอกโฟลเดอร์โปรเจกต์")
        stage_parent = expected_parent / f".smartpost-copy-recycle-{uuid.uuid4().hex}"
        staged_folder = stage_parent / folder.name

        def inventory(root):
            rows = []
            for candidate in root.rglob("*"):
                if candidate.is_file():
                    rows.append((str(candidate.relative_to(root)), candidate.stat().st_size))
            return sorted(rows)

        try:
            shutil.copytree(folder, staged_folder, copy_function=shutil.copy2)
            source_inventory = inventory(folder)
            staged_inventory = inventory(staged_folder)
            if source_inventory != staged_inventory:
                raise OSError("สำเนาสำรองก่อนลบมีจำนวนไฟล์หรือขนาดไม่ตรงกับต้นฉบับ")
            self._recycler(staged_folder)
            if staged_folder.exists():
                raise OSError("Windows ยังไม่ได้ย้ายสำเนาโปรเจกต์ลงถังขยะ")
        except Exception:
            shutil.rmtree(stage_parent, ignore_errors=True)
            raise

        try:
            stage_parent.rmdir()
        except OSError:
            pass
        try:
            shutil.rmtree(folder)
        except OSError:
            pass

        pending_paths = []
        if folder.exists():
            remaining = sorted(folder.rglob("*"), key=lambda path: len(path.parts), reverse=True)
            for path in remaining:
                if self._schedule_delete_on_reboot(path):
                    pending_paths.append(str(path))
            if self._schedule_delete_on_reboot(folder):
                pending_paths.append(str(folder))
        if self._logger:
            self._logger.info(
                "state=PROJECT_DELETE_COPY_FALLBACK result=completed folder=%s pending_paths=%s",
                folder,
                len(pending_paths),
            )
        return {
            "empty_folder_pending": folder.exists() and not any(folder.iterdir()),
            "pending_cleanup_paths": pending_paths,
        }

    @staticmethod
    def _schedule_delete_on_reboot(folder):
        if os.name != "nt" or not Path(folder).exists():
            return False
        return bool(ctypes.windll.kernel32.MoveFileExW(str(Path(folder).resolve()), None, 0x4))

    @staticmethod
    def _is_source_access_denied(exc):
        message = str(exc or "").lower()
        return "รหัส 120" in message or "code 120" in message or "de_accessdeniedsrc" in message

    def _repair_delete_container_acl(self, container):
        """Remove only an inherited Everyone/Delete-Child deny from a job container."""
        if os.name != "nt":
            raise OSError("ซ่อมสิทธิ์โฟลเดอร์อัตโนมัติได้เฉพาะ Windows")
        container = Path(container).resolve()
        allowed = {
            (self.workspace / "products").resolve(),
            (self.workspace / "stories").resolve(),
        }
        if container not in allowed or not container.is_dir():
            raise ValueError("ไม่อนุญาตให้แก้สิทธิ์นอกโฟลเดอร์เก็บโปรเจกต์")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        commands = (
            ("icacls.exe", str(container), "/inheritance:d"),
            ("icacls.exe", str(container), "/remove:d", "*S-1-1-0"),
        )
        for command in commands:
            completed = subprocess.run(
                command,
                capture_output=True,
                creationflags=creationflags,
                check=False,
            )
            if completed.returncode != 0:
                raise OSError(f"Windows ซ่อมสิทธิ์โฟลเดอร์ไม่สำเร็จ (icacls {completed.returncode})")
        if self._logger:
            self._logger.info("state=PROJECT_DELETE_ACL result=repaired folder=%s", container)

    def _update_manifest_after_render_delete(self, manifest_path, deleted_paths):
        manifest_path = Path(manifest_path).resolve()
        job_folder = manifest_path.parent.resolve()
        store = self._manifest_store(manifest_path)
        removed = {str(Path(path).resolve()).casefold() for path in deleted_paths}

        def update_manifest(manifest):
            def was_removed(value):
                value = str(value or "").strip()
                if not value:
                    return False
                try:
                    return str((job_folder / value).resolve()).casefold() in removed
                except OSError:
                    return False

            cleared_keys = set()
            for key, value in list(manifest.items()):
                if key.endswith("_path") and was_removed(value):
                    manifest[key] = ""
                    cleared_keys.add(key)

            flow_clips_before = dict(manifest.get("flow_clips") or {})
            removed_remote_slots = {
                str(key) for key, value in flow_clips_before.items() if was_removed(value)
            }
            flow_clips = {
                str(key): value for key, value in flow_clips_before.items()
                if not was_removed(value)
            }
            manifest["flow_clips"] = flow_clips
            manifest["flow_clip_count"] = len(flow_clips)
            is_story = job_folder.parent.name.casefold() == "stories"
            final_only_removed = (
                "video_path" in cleared_keys
                and str(manifest.get("cleanup_status") or "").strip().lower() == "final_only"
            )

            if is_story:
                fallback_before = dict(manifest.get("flow_fallback_clips") or {})
                removed_local_slots = {
                    str(key) for key, value in fallback_before.items() if was_removed(value)
                }
                fallback_clips = {
                    str(key): value for key, value in fallback_before.items()
                    if not was_removed(value)
                }
                manifest["flow_fallback_clips"] = fallback_clips

                metadata = dict(manifest.get("flow_fallback_metadata") or {})
                for key in removed_local_slots:
                    metadata.pop(key, None)
                manifest["flow_fallback_metadata"] = metadata

                prompt_retries = dict(manifest.get("flow_prompt_retries") or {})
                for key in removed_local_slots:
                    retry = prompt_retries.get(key)
                    if not isinstance(retry, dict):
                        continue
                    retry = dict(retry)
                    retry.pop("fallback_clip_path", None)
                    retry.pop("fallback_saved_at", None)
                    retry["status"] = "local_motion_fallback_pending"
                    prompt_retries[key] = retry
                if "flow_prompt_retries" in manifest or prompt_retries:
                    manifest["flow_prompt_retries"] = prompt_retries

                superseded = dict(manifest.get("superseded_flow_fallback_clips") or {})
                manifest["superseded_flow_fallback_clips"] = {
                    str(key): value for key, value in superseded.items()
                    if not was_removed(value)
                }
                source_slots = set(flow_clips) | set(fallback_clips)
                target_count = self._count(manifest.get("scene_count"))
                all_sources_ready = bool(target_count) and all(
                    str(index) in source_slots for index in range(1, target_count + 1)
                )
                manifest["flow_fallback_count"] = len(fallback_clips)
                manifest["flow_scene_count"] = len(source_slots)
                manifest["flow_video_status"] = (
                    "ready" if all_sources_ready
                    else "waiting_downloads" if source_slots or manifest.get("flow_policy_failure_history")
                    else "not_generated"
                )
                if str(manifest.get("video_generation_mode") or "") == "google_flow":
                    manifest["video_source_type"] = (
                        "google_flow_story_hybrid_clips" if fallback_clips
                        else "google_flow_story_clips" if flow_clips
                        else "google_flow_pending"
                    )
            else:
                local_before = dict(manifest.get("flow_local_motion_clips") or {})
                removed_local_slots = {
                    str(key) for key, value in local_before.items() if was_removed(value)
                }
                local_clips = {
                    str(key): value for key, value in local_before.items()
                    if not was_removed(value)
                }
                manifest["flow_local_motion_clips"] = local_clips

                # Keep the authenticated denial itself so resume can rebuild
                # Local Motion without resubmitting the rejected image. Only
                # rendered-file references and ready state are invalidated.
                fallbacks = dict(manifest.get("flow_policy_fallbacks") or {})
                reset_fallback_slots = set(removed_local_slots)
                reset_fallback_slots.update(
                    str(key) for key, fallback in fallbacks.items()
                    if isinstance(fallback, dict) and (
                        was_removed(fallback.get("clip_path"))
                        or was_removed(fallback.get("retained_in_final"))
                        or (
                            final_only_removed
                            and str(fallback.get("status") or "").strip().lower() == "finalized"
                        )
                    )
                )
                for key in reset_fallback_slots:
                    fallback = fallbacks.get(key)
                    if not isinstance(fallback, dict):
                        continue
                    fallback = dict(fallback)
                    fallback.pop("clip_path", None)
                    fallback.pop("render_plan", None)
                    fallback.pop("retained_in_final", None)
                    fallback["status"] = "render_pending"
                    fallbacks[key] = fallback
                manifest["flow_policy_fallbacks"] = fallbacks

                removed_slots = removed_remote_slots | removed_local_slots
                provenance = dict(manifest.get("flow_segment_provenance") or {})
                provenance = {
                    str(key): value for key, value in provenance.items()
                    if str(key) not in removed_slots
                    and not (isinstance(value, dict) and was_removed(value.get("clip_path")))
                    and not (isinstance(value, dict) and was_removed(value.get("retained_in_final")))
                }
                manifest["flow_segment_provenance"] = provenance
                source_slots = set(flow_clips) | set(local_clips)
                target_count = self._count(
                    manifest.get("flow_required_clip_count")
                    or manifest.get("flow_target_clip_count")
                )
                all_sources_ready = bool(target_count) and all(
                    str(index) in source_slots for index in range(1, target_count + 1)
                )
                manifest["flow_remote_clip_count"] = len(flow_clips)
                manifest["flow_local_motion_clip_count"] = len(local_clips)
                manifest["flow_segment_count"] = len(source_slots)
                manifest["flow_video_status"] = (
                    "ready" if all_sources_ready
                    else "waiting_downloads" if source_slots or fallbacks
                    else "not_generated"
                )
                if "google_flow" in str(manifest.get("video_source_type") or "") or str(manifest.get("video_ai_provider") or "") == "flow":
                    manifest["video_source_type"] = (
                        "google_flow_hybrid_clips" if local_clips
                        else "google_flow_clips" if flow_clips
                        else "google_flow_pending"
                    )
            if "subtitle_video_path" in cleared_keys:
                manifest["subtitle_video_status"] = "not_rendered"
            if "audio_mix_path" in cleared_keys:
                manifest["audio_mix_status"] = "not_rendered"
            if "video_path" in cleared_keys or not str(manifest.get("video_path") or "").strip():
                manifest["video_status"] = "deleted"
                manifest["status"] = "video_deleted"
                readiness = dict(manifest.get("readiness") or {})
                missing = list(readiness.get("missing") or [])
                if "video" not in missing:
                    missing.append("video")
                readiness.update({"ready": False, "missing": missing})
                manifest["readiness"] = readiness
            manifest.update({
                "rendered_files_deleted_count": int(manifest.get("rendered_files_deleted_count") or 0) + len(deleted_paths),
                "rendered_files_deleted_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
            return manifest

        store.update(update_manifest)

    def _item(self, kind, manifest_path, manifest):
        job_id = str(manifest.get("id") or manifest_path.parent.name)
        if manifest.get("video_status") != "ready":
            return None
        job_folder = manifest_path.parent.resolve()
        videos_folder = (job_folder / "videos").resolve()

        # Prefer the most complete user-facing render. video_path should point
        # to it, but an interrupted run can persist the final audio/subtitle
        # output immediately before the final manifest promotion.
        candidates = []
        green = manifest.get('green_result') or {}
        if (green.get('enabled') and manifest.get('video_path')
                and green.get('output') == str((job_folder/manifest['video_path']).resolve())):
            candidates.append(manifest['video_path'])
        if manifest.get("audio_mix_status") == "ready":
            candidates.append(manifest.get("audio_mix_path"))
        if manifest.get("subtitle_video_status") == "ready":
            candidates.append(manifest.get("subtitle_video_path"))
        candidates.append(manifest.get("video_path"))

        relative = ""
        path = None
        for candidate in candidates:
            candidate = str(candidate or "").strip()
            if not candidate:
                continue
            resolved = (job_folder / candidate).resolve()
            if videos_folder in resolved.parents and resolved.suffix.lower() in self.VIDEO_EXTENSIONS and resolved.is_file():
                relative = candidate
                path = resolved
                break
        if path is None:
            return None
        title = str(
            manifest.get("video_title")
            or manifest.get("product_name")
            or manifest.get("topic")
            or job_id
        ).strip()
        updated = str(manifest.get("updated_at") or manifest.get("created_at") or "")
        try:
            episode_no = int(manifest.get("episode_no") or 0)
        except (TypeError, ValueError):
            episode_no = 0
        return {
            "item_id": f"{kind}:{job_id}",
            "aspect_ratio": '16:9' if manifest.get('long_video') else '9:16',
            "kind": kind,
            "content_kind": (
                "product" if kind == "product" or manifest.get('product_story')
                else "drama" if manifest.get("job_type") == "drama_episode"
                else "story"
            ),
            "kind_label": (
                "เรื่องเล่าสินค้า Shorts" if manifest.get('product_story') else "วิดีโอสินค้า" if kind == "product"
                else "ละครสั้น AI" if manifest.get("job_type") == "drama_episode"
                else "คลิปยาว" if manifest.get('long_video') else "เรื่องเล่า Shorts"
            ),
            "job_id": job_id,
            "series_id": str(manifest.get("series_id") or ""),
            "series_title": str(manifest.get("series_title") or ""),
            "episode_no": episode_no,
            "title": title,
            "file_name": path.name,
            "cover_path": str(self._detail_cover_path(job_folder, manifest) or ""),
            "preview_path": str(self._detail_preview_path(job_folder, manifest) or ""),
            "cover_revision": str(manifest.get("cover_revision") or ""),
            'ai_cover_state': manifest.get('ai_cover_state') or {},
            "duration_seconds": manifest.get("duration_seconds") or 0,
            "path": str(path),
            "folder": str(path.parent),
            "relative_path": relative,
            "manifest_path": str(manifest_path.resolve()),
            "updated_at": updated,
            "size_bytes": path.stat().st_size,
            **self._video_source_summary(kind, manifest),
            "flow_remote_clip_count": int(manifest.get("flow_remote_clip_count") or manifest.get("flow_clip_count") or 0),
            "flow_local_motion_clip_count": int(manifest.get("flow_local_motion_clip_count") or 0),
            "flow_segment_count": int(manifest.get("flow_segment_count") or 0),
            "flow_segment_provenance": dict(manifest.get("flow_segment_provenance") or {}),
        }

    @classmethod
    def _recycle_file(cls, path):
        cls._recycle_path(path)

    @staticmethod
    def _recycle_path(path):
        path = Path(path).resolve()
        if not path.exists() or not (path.is_file() or path.is_dir()):
            raise ValueError("ไม่พบไฟล์หรือโฟลเดอร์")
        if os.name != "nt":
            raise OSError("การลบแบบกู้คืนได้รองรับเฉพาะ Windows")

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", ctypes.c_int),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        # The UI runs deletion in a worker thread. Initialising COM in that
        # thread and retaining a real double-NUL buffer makes the legacy Shell
        # recycle operation reliable on Windows 10/11.
        ole32 = ctypes.windll.ole32
        coinit_result = ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        should_uninitialize = coinit_result in (0, 1)  # S_OK / S_FALSE
        last_error = "Windows ยังไม่ได้ย้ายโฟลเดอร์ลงถังขยะ"
        try:
            for attempt, retry_delay in enumerate((0.0, 0.25, 0.75), start=1):
                if retry_delay:
                    time.sleep(retry_delay)
                source = ctypes.create_unicode_buffer(str(path) + "\0\0")
                operation = SHFILEOPSTRUCTW()
                operation.wFunc = 3  # FO_DELETE
                operation.pFrom = ctypes.cast(source, ctypes.c_wchar_p)
                operation.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO, NOCONFIRMATION, SILENT, NOERRORUI
                result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
                if result == 0 and not operation.fAnyOperationsAborted:
                    deadline = time.monotonic() + 1.0
                    while path.exists() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    if not path.exists():
                        return
                    last_error = "Windows แจ้งว่าดำเนินการแล้ว แต่โฟลเดอร์ยังถูกใช้งานอยู่"
                elif operation.fAnyOperationsAborted:
                    last_error = f"Windows ยกเลิกการย้ายลงถังขยะ (รหัส {result})"
                elif result in (5, 32):
                    last_error = f"ไฟล์กำลังถูกใช้งานหรือไม่มีสิทธิ์ลบ (รหัส {result})"
                elif result == 120:
                    last_error = "สิทธิ์ของโฟลเดอร์ต้นทางปฏิเสธการลบ (รหัส 120)"
                else:
                    last_error = f"ย้ายไฟล์ไปถังรีไซเคิลไม่สำเร็จ (รหัส {result})"
            raise OSError(f"{last_error} หลังลองอัตโนมัติ {attempt} ครั้ง")
        finally:
            if should_uninitialize:
                ole32.CoUninitialize()
