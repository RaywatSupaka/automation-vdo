import threading
import uuid
from datetime import datetime
from pathlib import Path

from core.ai_web_models import normalize_ai_web_model
from core.story_styles import normalize_story_style
from core.drama_options import drama_render_options
from core.atomic_json import AtomicJsonFile, runtime_backup_path


_STORY_QUEUE_LOCK = threading.RLock()


class StoryBatchQueue:
    """Persistent first-in-first-out queue for one-click Story Shorts batches."""

    MAX_BATCH_SIZE = 10
    MAX_ACTIVE_ITEMS = 30
    TERMINAL_STATES = {"completed", "failed", "cancelled"}

    def __init__(self, root):
        self.path = Path(root) / "workspace" / "story_batch_queue.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _STORY_QUEUE_LOCK
        self._store = AtomicJsonFile(
            self.path,
            backup_path=runtime_backup_path(root, self.path),
        )
        if not self.path.is_file():
            self._store.write({"version": 1, "paused": False, "pause_reason": "", "items": []})

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec="seconds")

    def _load(self):
        data = self._store.read_unlocked({"version": 1, "paused": False, "pause_reason": "", "items": []})
        if not isinstance(data, dict):
            raise ValueError("ไฟล์คิว Story ไม่ใช่ JSON object")
        data["version"] = 1
        data["paused"] = bool(data.get("paused", False))
        data["pause_reason"] = str(data.get("pause_reason") or "")
        data["items"] = [dict(item) for item in (data.get("items") or []) if isinstance(item, dict)]
        return data

    def _save(self, data):
        self._store.write_unlocked(data)

    def snapshot(self):
        with self._lock, self._store.locked():
            data = self._load()
        items = data["items"]
        counts = {state: sum(item.get("status") == state for item in items) for state in ("queued", "running", "completed", "failed", "cancelled")}
        return {
            "paused": data["paused"],
            "pause_reason": data["pause_reason"],
            "run_series_id": str(data.get("run_series_id") or ""),
            "items": items,
            "counts": counts,
            "active_count": counts["queued"] + counts["running"],
            "total_count": len(items),
        }

    def enqueue_batch(self, topics, story_text="", provider="chatgpt", scene_count=10, main_image="", video_generation_mode="image_motion", ai_web_model="", visual_style="auto", visual_style_custom="", long_video=None):
        visual_style, visual_style_custom = normalize_story_style(visual_style, visual_style_custom)
        cleaned = [str(topic or "").strip() for topic in list(topics or [])]
        cleaned = [topic for topic in cleaned if topic]
        if not cleaned:
            raise ValueError("กรุณาใส่หัวข้ออย่างน้อย 1 รายการ")
        if len(cleaned) > self.MAX_BATCH_SIZE:
            raise ValueError(f"เพิ่มได้สูงสุดครั้งละ {self.MAX_BATCH_SIZE} คลิป")
        provider = str(provider or "chatgpt").strip().lower()
        if provider not in {"chatgpt", "gemini"}:
            raise ValueError("ผู้สร้างภาพไม่ถูกต้อง")
        ai_web_model = normalize_ai_web_model(provider, ai_web_model)
        video_generation_mode = str(video_generation_mode or "image_motion").strip().lower()
        if video_generation_mode not in {"image_motion", "google_flow", "meta_ai"}:
            raise ValueError("โหมดสร้างวิดีโอ Story ไม่ถูกต้อง")
        from core.long_video import long_video_settings, require_meta_landscape_available
        long_options = long_video_settings({**dict(long_video), 'video_generation_mode': video_generation_mode}) if long_video is not None else None
        if video_generation_mode == 'meta_ai' and not long_options:
            raise ValueError('คิว Story Shorts นี้ยังไม่รองรับ Meta AI')
        if long_options and video_generation_mode == 'meta_ai':
            require_meta_landscape_available()
        scene_count = long_options['scene_count'] if long_options else max(6, min(15, int(scene_count or 10)))
        main_image = str(main_image or "").strip()
        if main_image and not Path(main_image).is_file():
            raise ValueError("ไม่พบรูปหลักที่เลือก")
        with self._lock, self._store.locked():
            data = self._load()
            active_count = sum(item.get("status") in {"queued", "running"} for item in data["items"])
            if active_count + len(cleaned) > self.MAX_ACTIVE_ITEMS:
                raise ValueError(f"คิวที่ยังไม่เสร็จรองรับรวมสูงสุด {self.MAX_ACTIVE_ITEMS} คลิป")
            batch_id = f"BATCH-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4].upper()}"
            start_order = max([int(item.get("order") or 0) for item in data["items"]] or [0])
            created = []
            for offset, topic in enumerate(cleaned, 1):
                item = {
                    **({'long_video': long_options} if long_options else {}),
                    "queue_id": f"SQ-{uuid.uuid4().hex[:8].upper()}",
                    "batch_id": batch_id,
                    "order": start_order + offset,
                    "topic": topic,
                    "story_text": str(story_text or "").strip(),
                    "provider": provider,
                    "ai_web_model": ai_web_model,
                    "scene_count": scene_count,
                    "main_image": main_image,
                    "video_generation_mode": video_generation_mode,
                    "visual_style": visual_style,
                    "visual_style_custom": visual_style_custom,
                    "status": "queued",
                    "job_id": "",
                    "error": "",
                    "created_at": self._now(),
                    "started_at": "",
                    "finished_at": "",
                }
                data["items"].append(item)
                created.append(dict(item))
            # Enqueue is intentionally separate from execution.  A batch must
            # stay parked until the user explicitly presses "start all".
            # If a clip is already running, it may finish safely, then the
            # newly paused queue stops before claiming the next item.
            data["paused"] = True
            data["pause_reason"] = "awaiting_user_start"
            self._save(data)
        return {"batch_id": batch_id, "items": created}

    def enqueue_drama_series(self, series_id, title, episode_count, provider="chatgpt", scene_count=10, ai_web_model="", render_options=None, preserve_state=False):
        series_id = str(series_id or "").strip()
        title = str(title or "").strip()
        if not series_id.startswith("SERIES-"):
            raise ValueError("Series ID ไม่ถูกต้อง")
        episode_count = max(1, min(20, int(episode_count or 1)))
        provider = str(provider or "chatgpt").strip().lower()
        if provider not in {"chatgpt", "gemini"}:
            raise ValueError("ผู้สร้างภาพไม่ถูกต้อง")
        ai_web_model = normalize_ai_web_model(provider, ai_web_model)
        scene_count = max(6, min(15, int(scene_count or 10)))
        with self._lock, self._store.locked():
            data = self._load()
            active_count = sum(item.get("status") in {"queued", "running"} for item in data["items"])
            if active_count + episode_count > self.MAX_ACTIVE_ITEMS:
                raise ValueError(f"คิวที่ยังไม่เสร็จรองรับรวมสูงสุด {self.MAX_ACTIVE_ITEMS} คลิป")
            batch_id = f"DRAMA-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4].upper()}"
            start_order = max([int(item.get("order") or 0) for item in data["items"]] or [0])
            created = []
            for episode_no in range(1, episode_count + 1):
                item = {
                    "queue_id": f"SQ-{uuid.uuid4().hex[:8].upper()}",
                    "batch_id": batch_id,
                    "mode": "drama",
                    **({"render_options": drama_render_options(render_options)} if render_options is not None else {}),
                    "series_id": series_id,
                    "episode_no": episode_no,
                    "episode_count": episode_count,
                    "order": start_order + episode_no,
                    "topic": f"{title} • EP {episode_no}",
                    "story_text": "",
                    "provider": provider,
                    "ai_web_model": ai_web_model,
                    "scene_count": scene_count,
                    "main_image": "",
                    "status": "queued",
                    "job_id": "",
                    "error": "",
                    "created_at": self._now(),
                    "started_at": "",
                    "finished_at": "",
                }
                data["items"].append(item)
                created.append(dict(item))
            if not preserve_state or not active_count:
                data["paused"] = True
                data["pause_reason"] = "awaiting_user_start"
            self._save(data)
        return {"batch_id": batch_id, "items": created}

    def enqueue_drama_episode(
        self, series_id, title, episode_no, episode_count, provider="chatgpt", scene_count=10, priority=False, ai_web_model=""
    ):
        """Queue one appended episode while preserving its real EP number."""
        series_id = str(series_id or "").strip()
        title = str(title or "").strip()
        if not series_id.startswith("SERIES-"):
            raise ValueError("Series ID ไม่ถูกต้อง")
        episode_no = max(1, min(20, int(episode_no or 1)))
        episode_count = max(episode_no, min(20, int(episode_count or episode_no)))
        provider = str(provider or "chatgpt").strip().lower()
        if provider not in {"chatgpt", "gemini"}:
            raise ValueError("ผู้สร้างภาพไม่ถูกต้อง")
        ai_web_model = normalize_ai_web_model(provider, ai_web_model)
        scene_count = max(6, min(15, int(scene_count or 10)))
        with self._lock, self._store.locked():
            data = self._load()
            active = [item for item in data["items"] if item.get("status") in {"queued", "running"}]
            if len(active) >= self.MAX_ACTIVE_ITEMS:
                raise ValueError(f"คิวที่ยังไม่เสร็จรองรับรวมสูงสุด {self.MAX_ACTIVE_ITEMS} คลิป")
            if any(item.get("series_id") == series_id and int(item.get("episode_no") or 0) == episode_no for item in active):
                raise ValueError(f"EP {episode_no} อยู่ในคิวแล้ว")
            batch_id = f"DRAMA-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4].upper()}"
            order = max([int(item.get("order") or 0) for item in data["items"]] or [0]) + 1
            item = {
                "queue_id": f"SQ-{uuid.uuid4().hex[:8].upper()}",
                "batch_id": batch_id,
                "mode": "drama",
                "series_id": series_id,
                "episode_no": episode_no,
                "episode_count": episode_count,
                "order": order,
                "topic": f"{title} • EP {episode_no}",
                "story_text": "",
                "provider": provider,
                "ai_web_model": ai_web_model,
                "scene_count": scene_count,
                "main_image": "",
                "status": "queued",
                "job_id": "",
                "error": "",
                "created_at": self._now(),
                "started_at": "",
                "finished_at": "",
            }
            if priority:
                insert_at = next(
                    (
                        index for index, queued in enumerate(data["items"])
                        if queued.get("status") == "queued"
                        and queued.get("series_id") == series_id
                        and int(queued.get("episode_no") or 0) > episode_no
                    ),
                    len(data["items"]),
                )
                data["items"].insert(insert_at, item)
                for index, queued in enumerate(data["items"], 1):
                    queued["order"] = index
            else:
                data["items"].append(item)
            data["paused"] = True
            data["pause_reason"] = "awaiting_user_start"
            self._save(data)
        return {"batch_id": batch_id, "items": [dict(item)]}

    @staticmethod
    def _pending_candidate(data):
        scope = str(data.get("run_series_id") or "")
        if scope:
            rows = [entry for entry in data["items"] if entry.get("mode") == "drama" and entry.get("series_id") == scope]
            completed = {int(entry.get("episode_no") or 0) for entry in rows if entry.get("status") == "completed"}
            remaining = sorted((entry for entry in rows
                if int(entry.get("episode_no") or 0) not in completed), key=lambda entry: int(entry.get("episode_no") or 0))
            return remaining[0] if remaining and remaining[0].get("status") == "queued" else None
        return next((entry for entry in data["items"] if entry.get("status") == "queued"), None)

    def next_queued_item(self):
        with self._lock, self._store.locked():
            item = self._pending_candidate(self._load())
            return dict(item) if item else None

    def claim_next(self):
        with self._lock, self._store.locked():
            data = self._load()
            if data["paused"] or any(item.get("status") == "running" for item in data["items"]):
                return None
            item = self._pending_candidate(data)
            if not item:
                if data.get("run_series_id"):
                    data.update(paused=True, pause_reason="series_scope_stopped")
                    self._save(data)
                return None
            item.update({"status": "running", "started_at": self._now(), "error": ""})
            self._save(data)
            return dict(item)

    def running_item(self):
        with self._lock, self._store.locked():
            data = self._load()
            item = next((item for item in data["items"] if item.get("status") == "running"), None)
            return dict(item) if item else None

    def attach_job(self, queue_id, job_id):
        return self._update(queue_id, job_id=str(job_id or ""))

    def mark_completed_by_job(self, job_id, output_path=""):
        return self._update_by_job(job_id, status="completed", output_path=str(output_path or ""), error="", finished_at=self._now())

    def mark_failed_by_job(self, job_id, error):
        return self._update_by_job(job_id, status="failed", error=str(error or "ไม่ทราบข้อผิดพลาด")[:1500], finished_at=self._now())

    def mark_cancelled_by_job(self, job_id):
        return self._update_by_job(job_id, status="cancelled", error="ผู้ใช้ยกเลิกงาน", finished_at=self._now())

    def release_running(self, queue_id, error=""):
        return self._update(queue_id, status="queued", job_id="", error=str(error or "")[:1500], started_at="")

    def fail_item(self, queue_id, error):
        return self._update(queue_id, status="failed", error=str(error or "ไม่ทราบข้อผิดพลาด")[:1500], finished_at=self._now())

    def pause(self, reason="user"):
        with self._lock, self._store.locked():
            data = self._load()
            data["paused"] = True
            data["pause_reason"] = str(reason or "user")
            self._save(data)
        return self.snapshot()

    def resume(self, series_id=""):
        with self._lock, self._store.locked():
            data = self._load()
            series_id = str(series_id or "").strip()
            if series_id:
                if not series_id.startswith("SERIES-"):
                    raise ValueError("Series ID ไม่ถูกต้อง")
                if any(item.get("status") == "running" for item in data["items"]):
                    raise ValueError("มีงานกำลังทำอยู่ • รอให้จบก่อนเลือกซีรีส์")
                if not any(item.get("mode") == "drama" and item.get("series_id") == series_id
                           and item.get("status") == "queued" for item in data["items"]):
                    raise ValueError("ไม่มีตอนที่รอคิวในซีรีส์นี้")
            data["run_series_id"] = series_id
            data["paused"] = False
            data["pause_reason"] = ""
            self._save(data)
        return self.snapshot()

    def clear_finished(self):
        with self._lock, self._store.locked():
            data = self._load()
            removed = sum(item.get("status") in self.TERMINAL_STATES for item in data["items"])
            data["items"] = [item for item in data["items"] if item.get("status") not in self.TERMINAL_STATES]
            self._save(data)
        return removed

    def cancel_drama_series(self, series_id, reason="ผู้ใช้ยกเลิกคิวซีรีส์"):
        """Cancel unfinished queue rows for one Drama series without deleting outputs."""
        series_id = str(series_id or "").strip()
        if not series_id.startswith("SERIES-"):
            raise ValueError("Series ID ไม่ถูกต้อง")
        reason = str(reason or "ผู้ใช้ยกเลิกคิวซีรีส์")[:500]
        with self._lock, self._store.locked():
            data = self._load()
            cancelled = []
            running_job_ids = []
            cancelled_at = self._now()
            for item in data["items"]:
                if item.get("mode") != "drama" or item.get("series_id") != series_id:
                    continue
                if item.get("status") not in {"queued", "running", "failed"}:
                    continue
                if item.get("status") == "running" and item.get("job_id"):
                    running_job_ids.append(str(item["job_id"]))
                previous_error = str(item.get("error") or "").strip()
                if previous_error and previous_error != reason:
                    item["previous_error"] = previous_error
                item.update({
                    "status": "cancelled",
                    "error": reason,
                    "cancel_reason": reason,
                    "cancelled_at": cancelled_at,
                    "finished_at": cancelled_at,
                })
                cancelled.append(dict(item))
            if cancelled:
                remaining_active = any(
                    item.get("status") in {"queued", "running"}
                    for item in data["items"]
                )
                if not remaining_active:
                    data["paused"] = True
                    data["pause_reason"] = "awaiting_user_start"
                self._save(data)
        return {
            "series_id": series_id,
            "cancelled": len(cancelled),
            "running_job_ids": running_job_ids,
            "items": cancelled,
        }

    def _update(self, queue_id, **changes):
        with self._lock, self._store.locked():
            data = self._load()
            item = next((item for item in data["items"] if item.get("queue_id") == queue_id), None)
            if not item:
                return None
            item.update(changes)
            self._save(data)
            return dict(item)

    def _update_by_job(self, job_id, **changes):
        with self._lock, self._store.locked():
            data = self._load()
            item = next((item for item in data["items"] if item.get("job_id") == str(job_id or "")), None)
            if not item:
                return None
            item.update(changes)
            self._save(data)
            return dict(item)
