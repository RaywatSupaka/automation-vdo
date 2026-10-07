"""One durable FIFO for Product, Story Shorts and existing Drama entries.

Uses the existing queue file in place: no second scheduler/store and no copied
Jobs. Credentials are resolved at execution time, never persisted here.
"""
import copy
import hashlib
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from core.ai_web_models import normalize_ai_web_model
from core.story_queue import StoryBatchQueue
from core.story_styles import normalize_story_style


OPTION_KEYS = {
    "product_editorial_version",
    "speech_delivery_version",
    "meta_prompt_version",
    "long_source_audio_version",
    "actor_dialogue",
    "storytelling_options",
    "story_structure_options",
    "generated_music_options",
    "creative_context",
    "product_script_options",
    "intro_options",
    "green_options",
    "ai_cover_options",
    "flow_settings",
    "fictional_ai_characters_confirmed",
    "provider", "ai_web_model", "video_provider", "voice_reference_id", "voice_reference_file",
    "voice", "subtitle_enabled", "subtitle_language", "subtitle_syllables", "subtitle_style",
    "audio_enabled", "audio_settings", "audio", "render", "finish_config", "presenter", "audio_choices",
}
SECRET_WORDS = ("token", "credential", "api_key", "password", "cookie", "secret", "authorization", "sot", "sod")


def clean_settings(options):
    def clean(value):
        if isinstance(value, dict):
            return {str(k): clean(v) for k, v in value.items()
                    if not any(word in str(k).lower() for word in SECRET_WORDS)}
        if isinstance(value, (tuple, list)):
            return [clean(v) for v in value]
        if isinstance(value, Path):
            return str(value)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ValueError("ค่าที่บันทึกในคิวไม่รองรับ")
    result = clean({k: v for k, v in dict(options or {}).items() if k in OPTION_KEYS})
    if 'speech_delivery_version' in result:
        from core.speech_delivery import version
        result['speech_delivery_version'] = version(result['speech_delivery_version'])
    if 'product_editorial_version' in result:
        from core.product_editorial import version
        result['product_editorial_version'] = version(result['product_editorial_version'])
    if 'long_source_audio_version' in result:
        from core.long_video import source_audio_version
        result['long_source_audio_version'] = source_audio_version(result['long_source_audio_version'])
    if result.get('storytelling_options') is not None:
        from core.storytelling import storytelling_options
        result['storytelling_options'] = storytelling_options(result['storytelling_options'])
    if result.get('story_structure_options') is not None:
        from core.creative_brief import story_structure_options
        result['story_structure_options'] = story_structure_options(result['story_structure_options'])
    if result.get('generated_music_options') is not None:
        from core.generated_music import normalize_options
        result['generated_music_options'] = normalize_options(result['generated_music_options'])
    if isinstance(result.get('audio_choices'), dict) and not (result.get('generated_music_options') or {}).get('enabled'):
        result['audio_choices'].pop('generated_music_version', None)
    if 'product_script_options' in result:
        from core.product_script import product_script_options
        result['product_script_options'] = product_script_options(result['product_script_options'])
    if 'intro_options' in result:
        from core.video_intro import intro_options
        result['intro_options'] = intro_options(result['intro_options'])
    if 'meta_prompt_version' in result:
        from core.meta_prompt import meta_prompt_version
        result['meta_prompt_version'] = meta_prompt_version(result['meta_prompt_version'])
    if 'green_options' in result:
        from core.green_screen import green_options
        result['green_options'] = green_options(result['green_options'])
    if 'ai_cover_options' in result:
        from core.ai_cover import ai_cover_options
        result['ai_cover_options'] = ai_cover_options(result['ai_cover_options'])
    if "flow_settings" in result:
        from core.flow_settings import flow_settings
        result["flow_settings"] = flow_settings(result["flow_settings"])
    return result


class CreationQueue(StoryBatchQueue):
    def dismissed_creation_jobs(self):
        with self._lock, self._store.locked():
            return copy.deepcopy(self._load().get('dismissed_creation_jobs', {}))

    def remove_old_entries(self, queue_ids, job_ids):
        """Remove explicit stale rows and dismiss orphan suggestions atomically.

        No Job, media, provider receipt, queue pause state or scheduler mutation.
        The adapter validates orphan manifests and live ownership first.
        """
        ids, jobs = set(queue_ids), set(job_ids)
        with self._lock, self._store.locked():
            data = self._load()
            rows = [row for row in data['items'] if row.get('queue_id') in ids]
            if len(rows) != len(ids):
                raise ValueError('รายการคิวเปลี่ยนแล้ว • ตรวจรายการอีกครั้งก่อนลบ')
            if any(row.get('status') not in {'failed', 'cancelled'} or row.get('mode') == 'drama'
                   or row.get('series_id') for row in rows):
                raise ValueError('ลบได้เฉพาะงานค้างที่หยุดแล้ว • ไม่รวมงานรอทำ กำลังทำ สำเร็จ และละคร')
            if any(row.get('job_id') in jobs for row in data['items']):
                raise ValueError('งานเก่านี้ถูกนำเข้าคิวแล้ว • ตรวจรายการอีกครั้งก่อนลบ')
            bound_jobs = {row['job_id'] for row in rows if row.get('job_id')}
            if any(row.get('job_id') in bound_jobs and row.get('queue_id') not in ids
                   for row in data['items']):
                raise ValueError('งานนี้มีรายการอื่นในคิว • ตรวจรายการก่อนลบ')
            dismissed = data.setdefault('dismissed_creation_jobs', {})
            for ident in jobs | bound_jobs:
                dismissed[ident] = {'removed_at': self._now()}
            data['items'] = [row for row in data['items'] if row.get('queue_id') not in ids]
            self._save(data)
            return len(rows) + len(jobs)

    def dismiss_story_jobs(self, job_ids):
        """Explicit UI dismissal, unlike completion callbacks, includes queued/failed rows."""
        ids = set(job_ids)
        with self._lock, self._store.locked():
            data = self._load()
            for item in data['items']:
                if (item.get('job_id') in ids and item.get('mode', 'story') == 'story'
                        and item.get('status') in {'queued', 'running', 'failed'}):
                    item.update(status='cancelled', cancel_requested=True,
                                error='ผู้ใช้ล้างรายการทำต่อ Story Shorts', finished_at=self._now())
            self._save(data)

    def product_job_controls(self):
        with self._lock, self._store.locked():
            from core.product_job_deletion import controls
            return {**copy.deepcopy(self._load().get('product_job_controls', {})), **controls(self.path.parent.parent)}

    def require_not_trashed(self, job_id):
        from core.product_job_deletion import assert_job_available
        assert_job_available(self.path.parent.parent, job_id)
        if self.product_job_controls().get(str(job_id), {}).get('trashed'):
            raise ValueError('งานนี้อยู่ในถังขยะ • กู้คืนงานก่อนทำต่อ')

    def manage_product_jobs(self, job_ids, operation):
        """One durable commit for visibility and queue exclusion; never touch media.

        Caller validates product ownership and local/browser inactivity under this
        same queue lock. A restored job remains cancelled until explicit Resume.
        """
        if operation not in {'hide', 'show', 'trash', 'restore'}:
            raise ValueError('คำสั่งจัดการงานไม่ถูกต้อง')
        with self._lock, self._store.locked():
            from core.product_job_deletion import assert_job_available
            for ident in job_ids:
                assert_job_available(self.path.parent.parent, ident)
            data = self._load()
            controls = data.setdefault('product_job_controls', {})
            rows = [i for i in data['items'] if i.get('job_id') in job_ids]
            if any(i.get('status') == 'running' for i in rows):
                raise ValueError('งานยังอยู่ระหว่างทำงาน • หยุดงานก่อนจัดการ')
            for ident in job_ids:
                record = controls.setdefault(ident, {})
                if operation in {'hide', 'show'}:
                    if record.get('trashed'):
                        raise ValueError('งานนี้อยู่ในถังขยะ • กู้คืนก่อน')
                    record['hidden'] = operation == 'hide'
                else:
                    record.update(trashed=operation == 'trash', hidden=False)
                record['updated_at'] = self._now()
            if operation == 'trash':
                for item in rows:
                    item.update(status='cancelled', cancel_requested=True,
                                finished_at=self._now(), error='ย้ายงานลงถังขยะ • ไฟล์เดิมยังอยู่')
            self._save(data)
            return copy.deepcopy(controls)

    def _load(self):
        data = super()._load()
        from core.product_job_deletion import controls as permanent_controls
        deleted = permanent_controls(self.path.parent.parent)
        data['items'] = [item for item in data['items'] if item.get('job_id') not in deleted]
        # Late callbacks can update queue status, never erase the independent
        # tombstone or admit this job again. Restoration does not auto-requeue.
        controls = data.get('product_job_controls', {})
        for item in data['items']:
            if controls.get(item.get('job_id'), {}).get('trashed'):
                item.update(status='cancelled', cancel_requested=True)
        return data

    def recover_on_startup(self):
        with self._lock, self._store.locked():
            data = self._load()
            for item in data["items"]:
                if item.get("status") in {"queued", "running"} and item.get("cancel_requested"):
                    item.update(status="cancelled", finished_at=self._now())
                elif item.get("status") == "running":
                    # Keep the bound Job/checkpoints. Never create another Job
                    # merely because the app stopped before a completion event.
                    item.update(status="queued", error="เปิดโปรแกรมใหม่ • รอกดทำต่อจาก Checkpoint")
            data.update(paused=True, pause_reason="startup_review")
            self._save(data)

    @staticmethod
    def _fingerprint(item):
        body = {key: item.get(key) for key in (
            "mode", "topic", "link", "story_text", "provider", "ai_web_model", "scene_count",
            "main_image", "video_generation_mode", "visual_style", "visual_style_custom", "settings", "long_video", "flow_smoke_test",
        )}
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def enqueue(self, mode, values, *, settings=None, request_id="", **story):
        if mode not in {"product", "story"} or not isinstance(values, list):
            raise ValueError("รูปแบบคิวไม่ถูกต้อง")
        values = [str(value or "").strip() for value in values if str(value or "").strip()]
        if not 1 <= len(values) <= self.MAX_BATCH_SIZE:
            raise ValueError(f"เพิ่มได้ครั้งละ 1–{self.MAX_BATCH_SIZE} รายการ")
        settings = clean_settings(settings)
        provider = str(story.get("provider") or settings.get("provider") or "chatgpt")
        if provider not in {"chatgpt", "gemini"}:
            raise ValueError("ผู้สร้างภาพไม่ถูกต้อง")
        model = normalize_ai_web_model(provider, story.get("ai_web_model") or settings.get("ai_web_model"))
        style, custom = normalize_story_style(story.get("visual_style", "auto"), story.get("visual_style_custom", ""))
        video_mode = str(story.get("video_generation_mode") or "image_motion")
        if video_mode not in {"image_motion", "google_flow", "meta_ai"}:
            raise ValueError("โหมดวิดีโอไม่ถูกต้อง")
        from core.story_performance import validate_option
        from core.storytelling import validate_settings, native_acting
        telling = validate_settings(settings.get('storytelling_options'), video_mode, settings.get('audio_choices'))
        if telling:
            if mode != 'story' or story.get('long_video') or settings.get('creative_context') or story.get('flow_smoke_test'):
                raise ValueError('รูปแบบการเล่าใช้กับเรื่องเล่า Shorts เท่านั้น')
            settings['actor_dialogue'] = native_acting(telling)
        acting = validate_option(settings.get('actor_dialogue', False), video_mode, settings.get('audio_choices'),
                                 settings.get('storytelling_options'))
        if acting and (mode != 'story' or story.get('long_video') or settings.get('creative_context')):
            raise ValueError('ตัวละครพูดเองใช้กับเรื่องเล่า Shorts เท่านั้น')
        if acting and not settings.get('audio_choices'):
            from core.media_audio import audio_choices
            settings['audio_choices'] = audio_choices({'mode': 'none' if telling and telling['mode'] == 'visual' else 'flow_original',
                                                       'subtitle': False}, video_mode)
        if acting and not telling:
            from core.story_performance import conversation_audio
            settings['audio_choices'] = conversation_audio(settings['audio_choices'])
            settings['subtitle_enabled'] = False
        from core.long_video import long_video_settings
        long_options = long_video_settings({**dict(story["long_video"]), 'video_generation_mode': video_mode}) if mode == "story" and story.get("long_video") is not None else None
        if long_options and long_options['version'] == 2 and video_mode in {'google_flow', 'meta_ai'}:
            settings.setdefault('long_source_audio_version', 1)
        if video_mode == 'meta_ai':
            from core.meta_prompt import CURRENT_META_PROMPT_VERSION
            settings.setdefault('meta_prompt_version', CURRENT_META_PROMPT_VERSION)
            from core.media_audio import audio_choices
            audio_choices(settings.get('audio_choices') or {'mode': 'api'}, 'meta_ai')
            if long_options:
                from core.long_video import require_meta_landscape_available
                require_meta_landscape_available()
        scene_count = long_options["scene_count"] if long_options else int(story.get("scene_count") or 10)
        smoke=story.get('flow_smoke_test') is True
        product_short=(settings.get('creative_context') or {}).get('product_short') is True
        from core.product_script import product_script_options
        product_script_options(settings.get('product_script_options'), product=bool(
            product_short and mode == 'story' and not long_options and not smoke
            and (settings.get('creative_context') or {}).get('kind') == 'product_story'))
        if product_short:
            if mode!='story' or long_options or smoke:raise ValueError('รูปแบบคลิปสินค้าไม่ถูกต้อง')
            from core.product_scene_settings import product_scene_count
            scene_count=product_scene_count(story.get('scene_count'))
        if smoke:
            if mode!='story' or long_options or video_mode!='google_flow':
                raise ValueError('ทดสอบ Flow ต้องใช้ Story Google Flow')
            scene_count=1
        if not long_options and not smoke and not product_short and not 6 <= scene_count <= 15:
            raise ValueError("จำนวนฉากต้องอยู่ระหว่าง 6–15")
        image = str(story.get("main_image") or "")
        if image and not Path(image).is_file():
            raise ValueError("ไม่พบรูปอ้างอิงที่เลือก")
        candidates = []
        for value in values:
            if len(value) > (4000 if mode == "product" else 2000):
                raise ValueError("ลิงก์หรือหัวข้อยาวเกินไป")
            if mode == "product":
                parsed = urlsplit(value)
                if parsed.scheme != "https" or parsed.hostname not in {"shopee.co.th", "www.shopee.co.th", "s.shopee.co.th"} or parsed.username or parsed.password:
                    raise ValueError("กรุณาใช้ลิงก์ https ของ Shopee ประเทศไทย")
            item = {
                **({"long_video": long_options} if long_options else {}),
                **({'flow_smoke_test':True} if smoke else {}),
                "mode": mode, "topic": value, "link": value if mode == "product" else "",
                "provider": provider, "ai_web_model": model,
                "story_text": str(story.get("story_text") or "")[:20000],
                "scene_count": scene_count, "main_image": image,
                "video_generation_mode": video_mode, "visual_style": style, "visual_style_custom": custom,
                "settings": copy.deepcopy(settings),
            }
            item["settings"].update(provider=provider, ai_web_model=model)
            candidates.append(item)
        with self._lock, self._store.locked():
            data = self._load()
            existing = [i for i in data["items"] if i.get("status") in {"queued", "running"}]
            if request_id and any(i.get("request_id") == request_id for i in data["items"]):
                return {"items": [], "duplicates": len(values), "batch_id": "", "paused": data["paused"]}
            seen = {self._fingerprint(i) for i in existing}
            unique = []
            for item in candidates:
                fingerprint = self._fingerprint(item)
                if fingerprint not in seen:
                    unique.append(item)
                    seen.add(fingerprint)
            if len(existing) + len(unique) > self.MAX_ACTIVE_ITEMS:
                raise ValueError(f"คิวที่ยังไม่เสร็จรองรับรวม {self.MAX_ACTIVE_ITEMS} รายการ")
            batch = f"BATCH-{uuid.uuid4().hex[:12].upper()}"
            order = max((int(i.get("order") or 0) for i in data["items"]), default=0)
            for offset, item in enumerate(unique, 1):
                item.update(queue_id=f"CQ-{uuid.uuid4().hex[:12].upper()}", batch_id=batch,
                            order=order + offset, request_id=str(request_id)[:100], status="queued", job_id="",
                            error="", created_at=self._now(), started_at="", finished_at="", attempt=0)
                data["items"].append(item)
            if not existing or story.get("queue_only") is True:
                data.update(paused=True, pause_reason="awaiting_user_start")
            # Adding to a running queue does not pause or reorder it.
            self._save(data)
            return {"items": copy.deepcopy(unique), "duplicates": len(values) - len(unique),
                    "batch_id": batch, "paused": data["paused"]}

    def enqueue_batch(self, topics, story_text="", provider="chatgpt", scene_count=10, main_image="",
                      video_generation_mode="image_motion", ai_web_model="", visual_style="auto", visual_style_custom="", **kwargs):
        return self.enqueue("story", topics, story_text=story_text, provider=provider, scene_count=scene_count,
                            main_image=main_image, video_generation_mode=video_generation_mode, ai_web_model=ai_web_model,
                            visual_style=visual_style, visual_style_custom=visual_style_custom, **kwargs)

    def get_item(self, queue_id):
        return next((i for i in self.snapshot()["items"] if i.get("queue_id") == queue_id), None)

    def item_for_job(self, job_id):
        if not job_id:
            return None
        matches = [i for i in self.snapshot()["items"] if i.get("job_id") == job_id]
        return next((i for i in matches if i.get("status") == "running"), matches[-1] if matches else None)

    def claim_next(self):
        with self._lock, self._store.locked():
            data = self._load()
            cancelled = False
            for item in data["items"]:
                if item.get("status") == "queued" and item.get("cancel_requested"):
                    item.update(status="cancelled", finished_at=self._now())
                    cancelled = True
            if cancelled:
                self._save(data)
            item = super().claim_next()
            if item:
                item = self._update(item["queue_id"], attempt=int(item.get("attempt") or 0) + 1)
            return item

    def bind_job(self, queue_id, attempt, job_id):
        with self._lock, self._store.locked():
            item = self.get_item(queue_id)
            if not item or item.get("status") not in {"running", "cancelled"} or item.get("attempt") != attempt:
                return None
            if item.get("job_id") and item["job_id"] != job_id:
                return None
            return self._update(queue_id, job_id=str(job_id))

    def retry(self, queue_id):
        with self._lock, self._store.locked():
            item = self.get_item(queue_id)
            self.require_not_trashed((item or {}).get('job_id'))
            if not item or item.get("status") not in {"failed", "cancelled"} or item.get("mode") == "drama":
                raise ValueError("รายการนี้ยังทำต่อจากคิวไม่ได้")
            if self.snapshot()["active_count"] >= self.MAX_ACTIVE_ITEMS:
                raise ValueError(f"คิวที่ยังไม่เสร็จรองรับรวม {self.MAX_ACTIVE_ITEMS} รายการ")
            return self._update(queue_id, status="queued", error="", started_at="", finished_at="",
                                cancel_requested=False, previous_error=str(item.get("error") or ""))

    def claim_failed_story_for_direct_resume(self, job_id):
        """Bind a direct checkpoint retry to its failed queue row before work starts."""
        with self._lock, self._store.locked():
            data = self._load()
            matches = [item for item in data["items"] if item.get("job_id") == str(job_id or "")]
            item = matches[-1] if matches else None
            if not item or item.get("status") != "failed" or item.get("mode") != "story":
                return None
            if item.get("cancel_requested") or any(
                row.get("status") == "running" and row.get("queue_id") != item.get("queue_id")
                for row in data["items"]
            ):
                raise ValueError("คิวนี้ถูกยกเลิกหรือมีงานอื่นกำลังทำอยู่")
            self.require_not_trashed(job_id)
            item.update(status="running", previous_error=str(item.get("error") or ""),
                        error="", started_at=self._now(), finished_at="")
            self._save(data)
            return dict(item)

    def resume_unfinished(self, *, allow_orphan_running=False):
        """Explicit recovery keeps every existing Job binding and frozen option."""
        with self._lock, self._store.locked():
            data = self._load()
            if any(i.get("status") == "running" for i in data["items"]) and not allow_orphan_running:
                raise ValueError("รอให้งานปัจจุบันหยุดก่อนทำต่อคิวเดิม")
            if data["pause_reason"].startswith("drama_failure:"):
                raise ValueError("กรุณากู้ EP ที่ค้างจากหน้าซีรีส์ก่อนทำต่อคิว")
            for item in data["items"]:
                if item.get("status") == "running" and item.get("cancel_requested"):
                    item.update(status="cancelled", finished_at=self._now())
            recoverable = [i for i in data["items"] if i.get("mode") != "drama"
                           and i.get("status") in {"failed", "running"} and not i.get("cancel_requested")]
            queued = sum(i.get("status") == "queued" for i in data["items"])
            if queued + len(recoverable) > self.MAX_ACTIVE_ITEMS:
                raise ValueError(f"คิวที่ยังไม่เสร็จรองรับรวม {self.MAX_ACTIVE_ITEMS} รายการ • เลือกทำต่อทีละรายการ")
            for item in recoverable:
                if item.get("error"):
                    item["previous_error"] = item["error"]
                item.update(status="queued", error="", started_at="", finished_at="", cancel_requested=False)
            data.update(paused=False, pause_reason="", run_series_id="")
            self._save(data)
            return {"requeued": len(recoverable), "queued": queued + len(recoverable)}

    def enqueue_existing_jobs(self, items):
        """Bind explicitly selected existing Jobs; never import or create a Job."""
        with self._lock, self._store.locked():
            data = self._load()
            existing = {str(i.get("job_id") or "") for i in data["items"]}
            additions = []
            for raw in items:
                item = copy.deepcopy(raw)
                job_id = str(item.get("job_id") or "")
                self.require_not_trashed(job_id)
                if item.get("mode") not in {"product", "story"} or not job_id:
                    raise ValueError("งานเดิมที่เลือกไม่ถูกต้อง")
                if job_id in existing:
                    continue
                existing.add(job_id)
                item["settings"] = clean_settings(item.get("settings"))
                additions.append(item)
            active = sum(i.get("status") in {"queued", "running"} for i in data["items"])
            if active + len(additions) > self.MAX_ACTIVE_ITEMS:
                raise ValueError(f"คิวที่ยังไม่เสร็จรองรับรวม {self.MAX_ACTIVE_ITEMS} รายการ")
            order = max((int(i.get("order") or 0) for i in data["items"]), default=0)
            for offset, item in enumerate(additions, 1):
                item.update(queue_id=f"CQ-{uuid.uuid4().hex[:12].upper()}", batch_id="existing_jobs",
                            order=order + offset, status="queued", error="", created_at=self._now(),
                            started_at="", finished_at="", attempt=0, cancel_requested=False)
                data["items"].append(item)
            self._save(data)
            return copy.deepcopy(additions)

    def cancel_all(self, *, active_queue_id=""):
        """Pause admission first; a live row retains ownership until it stops."""
        with self._lock, self._store.locked():
            data = self._load()
            data.update(paused=True, pause_reason="user_cancel_all")
            changed = 0
            for item in data["items"]:
                if item.get("status") not in {"queued", "running", "failed"}:
                    continue
                if not item.get("cancel_requested"):
                    changed += 1
                if item.get("error"):
                    item["previous_error"] = item["error"]
                live = item.get("queue_id") == active_queue_id and item.get("status") == "running"
                item.update(cancel_requested=True, error="ผู้ใช้ยกเลิกคิวทั้งหมด • เก็บ Job และไฟล์เดิมไว้",
                            status="running" if live else "cancelled",
                            finished_at="" if live else self._now())
            self._save(data)
            return {"cancelled": changed, "cancellation_pending": bool(active_queue_id)}

    def clear_stuck_state(self):
        """Caller must prove no worker owns these rows. No Job/media is touched."""
        with self._lock, self._store.locked():
            data = self._load()
            recovered = 0
            for item in data["items"]:
                if item.get("status") == "running":
                    item.update(status="cancelled" if item.get("cancel_requested") else "queued",
                                started_at="", finished_at=self._now() if item.get("cancel_requested") else "")
                    recovered += 1
                if item.get("status") == "queued" and item.get("error"):
                    item["previous_error"] = item["error"]
                    item["error"] = ""
            data.update(paused=True, pause_reason="state_cleared")
            self._save(data)
            return {"recovered": recovered}

    def edit(self, queue_id, value, *, settings=None, provider=None, scene_count=None, visual_style=None):
        with self._lock, self._store.locked():
            item = self.get_item(queue_id)
            if not item or item.get("status") != "queued" or item.get("job_id") or item.get("mode") == "drama":
                raise ValueError("แก้ไขได้เฉพาะรายการที่ยังไม่เริ่มสร้าง Job")
            value = str(value or "").strip()
            if not value or len(value) > 4000:
                raise ValueError("กรุณาระบุลิงก์หรือหัวข้อ")
            if item.get("mode") == "product":
                parsed = urlsplit(value)
                if parsed.scheme != "https" or parsed.hostname not in {"shopee.co.th", "www.shopee.co.th", "s.shopee.co.th"} or parsed.username or parsed.password:
                    raise ValueError("ลิงก์ Shopee ไม่ถูกต้อง")
                item["link"] = value
            item["topic"] = value
            if settings is not None:
                from core.story_performance import validate_option
                validate_option(settings.get('actor_dialogue', False), item.get('video_generation_mode'),
                                settings.get('audio_choices'), settings.get('storytelling_options'))
                previous = item.get('settings') or {}
                updated = clean_settings(settings)
                updated.pop('speech_delivery_version', None)
                updated.pop('product_editorial_version', None)
                if 'product_editorial_version' in previous:
                    updated['product_editorial_version'] = previous['product_editorial_version']
                if 'speech_delivery_version' in previous:
                    updated['speech_delivery_version'] = previous['speech_delivery_version']
                # Audio-contract capture belongs to enqueue, never a title or
                # form edit. Missing legacy markers must remain absent too.
                updated.pop('long_source_audio_version', None)
                if 'long_source_audio_version' in previous:
                    updated['long_source_audio_version'] = previous['long_source_audio_version']
                # Missing fields keep the saved brief; explicit style edits on
                # unstarted rows are now exposed by the compact catalog picker.
                if previous.get('product_script_options') is not None:
                    for key in ('creative_context', 'product_script_options'):
                        if key not in updated:
                            updated[key] = copy.deepcopy(previous.get(key))
                if 'story_structure_options' not in updated and previous.get('story_structure_options') is not None:
                    updated['story_structure_options'] = copy.deepcopy(previous['story_structure_options'])
                if 'generated_music_options' not in updated and previous.get('generated_music_options') is not None:
                    updated['generated_music_options'] = copy.deepcopy(previous['generated_music_options'])
                if previous.get('storytelling_options') is not None:
                    from core.storytelling import validate_settings
                    updated['storytelling_options'] = copy.deepcopy(previous['storytelling_options'])
                    updated['actor_dialogue'] = previous.get('actor_dialogue', False)
                    validate_settings(updated['storytelling_options'], item.get('video_generation_mode'), updated.get('audio_choices'))
                from core.product_script import product_script_options
                context = updated.get('creative_context') or {}
                product_script_options(updated.get('product_script_options'), product=bool(
                    item.get('mode') == 'story' and context.get('kind') == 'product_story'
                    and context.get('product_short') is True))
                item["settings"] = updated
                item["settings"].update(provider=item.get("provider"), ai_web_model=item.get("ai_web_model"))
            if provider is not None and provider != item.get("provider"):
                if provider not in {"chatgpt", "gemini"}:
                    raise ValueError("ผู้สร้างภาพไม่ถูกต้อง")
                item["provider"] = provider
                item["ai_web_model"] = normalize_ai_web_model(provider, "auto")
                item.setdefault("settings", {}).update(provider=provider, ai_web_model=item["ai_web_model"])
            if scene_count is not None:
                product_short=((item.get('settings') or {}).get('creative_context') or {}).get('product_short') is True
                if item.get('long_video'):
                    from core.long_video import long_video_settings
                    item['long_video'] = long_video_settings({**item['long_video'], 'scene_count': scene_count})
                    scene_count = item['long_video']['scene_count']
                elif product_short:
                    from core.product_scene_settings import product_scene_count
                    scene_count=product_scene_count(scene_count)
                if not item.get('long_video') and not product_short and not 6 <= int(scene_count) <= 15:
                    raise ValueError("จำนวนฉากต้องอยู่ระหว่าง 6–15")
                item["scene_count"] = int(scene_count)
            if visual_style is not None:
                item["visual_style"], item["visual_style_custom"] = normalize_story_style(visual_style, item.get("visual_style_custom", ""))
            if any(other.get("queue_id") != queue_id and other.get("status") in {"queued", "running"}
                   and self._fingerprint(other) == self._fingerprint(item) for other in self.snapshot()["items"]):
                raise ValueError("รายการเดียวกันอยู่ในคิวแล้ว")
            return self._update(queue_id, **{k: v for k, v in item.items() if k != "queue_id"})

    def move(self, queue_id, direction):
        if direction not in {-1, 1}:
            raise ValueError("ทิศทางไม่ถูกต้อง")
        with self._lock, self._store.locked():
            data = self._load()
            candidates = [n for n, item in enumerate(data["items"]) if item.get("status") == "queued"]
            position = next((p for p, n in enumerate(candidates) if data["items"][n].get("queue_id") == queue_id), None)
            if position is None or data["items"][candidates[position]].get("mode") == "drama":
                raise ValueError("ย้ายได้เฉพาะคิวที่ยังไม่เริ่ม และไม่ใช่ EP ละคร")
            target = position + direction
            if 0 <= target < len(candidates):
                # Pop/insert preserves the relative ordering of other items,
                # including dependent Drama episodes (a swap would not).
                index, destination = candidates[position], candidates[target]
                item = data["items"].pop(index)
                data["items"].insert(destination, item)
                for order, item in enumerate(data["items"], 1):
                    item["order"] = order
                self._save(data)

    def remove(self, queue_id):
        with self._lock, self._store.locked():
            data = self._load()
            item = next((i for i in data["items"] if i.get("queue_id") == queue_id), None)
            if not item or item.get("status") == "running" or item.get("mode") == "drama":
                raise ValueError("นำรายการนี้ออกไม่ได้ ใช้ปุ่มยกเลิกงานปัจจุบันหรือจัดการซีรีส์")
            if item.get('job_id'):
                data.setdefault('dismissed_creation_jobs', {})[item['job_id']] = {'removed_at': self._now()}
            data["items"].remove(item)
            self._save(data)
            return True

    def _update_by_job(self, job_id, **changes):
        with self._lock, self._store.locked():
            item = self.item_for_job(job_id)
            if item and item.get("cancel_requested") and changes.get("status") in self.TERMINAL_STATES:
                changes.update(status="cancelled", error="ผู้ใช้ยกเลิกคิวทั้งหมด • เก็บ Job และไฟล์เดิมไว้")
            # Keep the established Drama recovery contract: a manually repaired
            # failed EP can finish and unblock its dependent episodes.
            if item and item.get("mode") == "drama":
                if item.get("status") != "running" and not (
                        item.get("status") == "failed" and changes.get("status") == "completed"):
                    return None
                return self._update(item["queue_id"], **changes)
            if not item or item.get("status") != "running":
                return None
            return self._update(item["queue_id"], **changes)
