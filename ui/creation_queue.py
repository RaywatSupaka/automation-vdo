"""Desktop adapters for the shared creation FIFO. No browser gestures here."""
import copy
import json
import re
import time
from datetime import datetime
from pathlib import Path

from core.creation_queue import clean_settings
from core.ai_web_models import normalize_ai_web_model
from core.job_file_guard import app_guard, uses_job_files


REMOTE_TERMINAL_STEPS = {"", "complete", "completed", "cancelled", "error", "generation_complete",
                         "generation_failed", "attachment_failed", "credit_exhausted", "checkpoint_missing",
                         "checkpoint_mismatch", "project_open_failed", "wrong_output_type"}


def _editor_settings(settings):
    """Only fields read by the compact editor, never the full execution config."""
    fields = {
        'audio_choices': ('mode', 'subtitle', 'music', 'sfx', 'allow_silent', 'keep_video_audio', 'video_audio_volume', 'generated_music_version'),
        'flow_settings': ('model', 'video_type', 'resolution', 'duration', 'display'),
        'ai_cover_options': ('enabled', 'headline', 'scene_index'),
        'green_options': ('enabled', 'opacity', 'fit'),
        'generated_music_options': ('version', 'enabled', 'mood', 'frequency'),
        'product_script_options': ('version', 'style', 'genre', 'ending_cta'),
        'story_structure_options': ('version', 'structure'),
        'creative_context': ('kind', 'product_short'),
    }
    def pick(value, keys):
        return {key: value[key] for key in keys if key in value and type(value[key]) in (str, int, float, bool, type(None))}
    result = {name: pick(settings[name], keys) for name, keys in fields.items() if isinstance(settings.get(name), dict)}
    if 'green_options' in result:
        result['green_options']['clips'] = [pick(clip, ('file', 'color', 'similarity', 'blend'))
            for clip in settings['green_options'].get('clips', []) if isinstance(clip, dict)][:3]
    result.update(pick(settings, ('subtitle_enabled', 'fictional_ai_characters_confirmed')))
    return result


class CreationQueueMixin:
    def _job_delete_reason(self, job_id, allow_queued_job_ids=()):
        """Exact target and proven references only; never cancel to permit delete."""
        guard = app_guard(self)
        active = set()
        for name in ('_product_pipeline_job_id', '_story_pipeline_job_id',
                     '_manual_multi_flow_job_id', '_story_render_active', '_subtitle_render_active'):
            active.update(guard.references(getattr(self, name, '')))
        for key, worker in dict(getattr(self, '_story_scene_threads', {}) or {}).items():
            if worker is not None and worker.is_alive():
                active.update(guard.references(key))
        native = getattr(self, '_native_audio_worker', None)
        if native is not None and native.is_alive():
            active.update(guard.references(getattr(self, '_native_audio_state', {})))
        for ident in active:
            if job_id in guard.job_references(ident):
                return f'งาน {ident} ยังใช้ไฟล์นี้อยู่ • รอให้งานหยุดก่อนลบ'
        presenter = getattr(self, '_presenter_worker', None)
        if presenter is not None and presenter.is_alive():
            ident = (getattr(self, '_presenter_progress', {}) or {}).get('id')
            if ident and job_id in guard.references(self.presenters.get(ident)):
                return 'ตัวละครที่กำลังสร้างยังใช้ไฟล์อ้างอิงนี้อยู่'
        queue = getattr(self, 'story_queue', None)
        if queue is not None:
            for row in queue.snapshot().get('items', []):
                if row.get('status') not in {'queued', 'running'}:
                    continue
                if row.get('status') == 'queued' and row.get('job_id') == job_id and job_id in allow_queued_job_ids:
                    continue  # Explicit permanent deletion removes this exact parked row.
                targets = guard.references(row)
                for ident in tuple(targets):
                    targets.update(guard.job_references(ident))
                if job_id in targets:
                    return 'คิวสร้างคลิปยังอ้างถึงงานนี้ • นำออกจากคิวก่อนลบไฟล์'
        bridge = getattr(self, 'bridge', None)
        if bridge is not None:
            covers = getattr(bridge, 'ai_covers', None)
            if covers is not None:
                for row in covers.active():
                    targets = guard.references(row)
                    for ident in tuple(targets):
                        targets.update(guard.job_references(ident))
                    if job_id in targets:
                        return 'ปก AI ที่กำลังทำอยู่ยังใช้ไฟล์นี้'
            pending = getattr(bridge, 'pending_job_commands', None)
            if callable(pending) and pending([job_id]):
                return 'Extension ยังมีคำสั่งของงานนี้ที่ไม่ได้ยืนยันจบ'
            # Disconnection is not proof that a previously reported run ended.
            state = bridge.extension_status()
            for client in state.get('clients', []):
                for scope in ('ai', 'flow'):
                    ident = str(client.get(f'{scope}_job_id') or '')
                    if client.get(f'{scope}_step', '') not in REMOTE_TERMINAL_STEPS:
                        if ident and job_id in guard.job_references(ident):
                            return f'หน้า AI/Flow ยังรายงานว่า {ident} ใช้ไฟล์นี้อยู่'
        return ''

    def _creation_queue_tick(self):
        if getattr(self, 'membership', None) and not self.membership.allowed():
            return  # Do not fail/dequeue a row merely because Login is required.
        if getattr(self, "_app_update_pending", False):
            return
        try:
            self._start_next_story_queue_item()
        except Exception as exc:
            item = self.story_queue.running_item()
            if item:
                self.story_queue.fail_item(item["queue_id"], str(exc))
            self.story_queue.pause("dispatch_error")
            self._creation_dispatch_item = None
            self._desktop_set_notice("error", f"พักคิว • {exc}")
            self._write_console(f"CREATION QUEUE • DISPATCH ERROR • {exc}", "error")

    def _creation_workers_alive(self):
        # Cancel clears the Story UI before a per-scene Flow/voice worker may
        # exit. Keep its lane owned until then; stale finished entries are inert.
        scene_workers = tuple(dict(getattr(self, "_story_scene_threads", {}) or {}).values())
        return any(worker is not None and worker.is_alive() for worker in (
            getattr(self, "_creation_product_worker", None), getattr(self, "_creation_story_worker", None),
            getattr(self, "_presenter_worker", None),
            getattr(self, "_native_audio_worker", None),
            *scene_workers,
        ))

    def _creation_remote_busy_jobs(self):
        bridge = getattr(self, "bridge", None)
        if bridge is None:
            return set()
        state = bridge.extension_status()
        if not isinstance(state, dict) or not state.get("connected"):
            return set()
        busy = set()
        for client in state.get("clients", []):
            if not isinstance(client, dict):
                continue
            for scope in ("ai", "flow"):
                ident = str(client.get(f"{scope}_job_id") or "")
                step = str(client.get(f"{scope}_step") or "")
                if not ident or step in REMOTE_TERMINAL_STEPS:
                    continue
                # A completed Job's unowned login notification is not a run.
                # Never expire real/unknown generation solely because it is old.
                passive = step in {"user_action_resolved", "package_loaded", "package_ready"}
                unowned = not client.get(f"{scope}_run_id") and not client.get(f"{scope}_tab_id")
                if passive and unowned:
                    try:
                        manager = self.products if ident.startswith("JOB-") else self.stories
                        job = manager.get_job(ident) if ident.startswith("JOB-") else manager.get(ident)
                        terminal = job.get("automation_status") if ident.startswith("JOB-") else job.get("status")
                        if terminal in {"completed", "ready", "cancelled", "error", "failed"}:
                            continue
                    except Exception:
                        pass  # Unknown ownership remains blocked, not guessed idle.
                busy.add(ident)
        return busy

    def _creation_cancel_remote_queue_jobs(self, items, locally_cancelled_job=""):
        owned = {str(item.get("job_id") or "") for item in items
                 if item.get("status") in {"queued", "running", "failed"} and item.get("job_id")}
        owned.discard(locally_cancelled_job)
        bridge = getattr(self, "bridge", None)
        if not owned or bridge is None:
            return
        state = bridge.extension_status()
        if not isinstance(state, dict) or not state.get("connected"):
            return
        commands = set()
        for client in state.get("clients", []):
            if not isinstance(client, dict):
                continue
            if str(client.get("version") or "") != str(bridge.REQUIRED_EXTENSION_VERSION):
                continue
            def current_owner(scope):
                try:
                    updated = datetime.fromisoformat(str(client.get(f"{scope}_updated_at") or "")).timestamp()
                    age = time.time() - updated
                    return (0 <= age <= 90 and int(client.get(f"{scope}_tab_id") or 0) > 0
                            and str(client.get(f"{scope}_step") or "") not in REMOTE_TERMINAL_STEPS
                            and bool(re.fullmatch(r"RUN-[A-Za-z0-9_-]+", str(client.get(f"{scope}_run_id") or ""))))
                except (TypeError, ValueError):
                    return False
            flow_job = str(client.get("flow_job_id") or "")
            ai_job = str(client.get("ai_job_id") or "")
            if flow_job in owned and current_owner("flow"):
                try:
                    shot = int(client.get("flow_shot_index") or 0)
                except (TypeError, ValueError):
                    shot = 0  # Invalid telemetry cannot authorize a browser command.
                # Long-video Story jobs support 18–50 scenes. Keep Product's
                # existing range; every command still needs this fresh owner.
                max_shot = 50 if flow_job.startswith("STORY-") else 15
                if 1 <= shot <= max_shot:
                    commands.add(("stop_flow_generation", flow_job, shot, str(client.get("flow_run_id") or "")))
            if ai_job in owned and current_owner("ai"):
                commands.add(("cancel_story_chatgpt", ai_job, 0, str(client.get("ai_run_id") or "")))
        affected = {command[1] for command in commands}
        for job_id in sorted(affected):
            # An orphan has no local cancellation callback. Persist intent
            # before asking its browser to stop so a late AI result is rejected.
            if job_id.startswith("JOB-"):
                self.products.set_automation_state(job_id, "cancelled", "cancelled")
            else:
                self.stories.mark_cancelled(job_id, "user_cancel")
        for action, job_id, shot, run_id in sorted(commands):
            bridge.queue_extension_command(action, job_id, shot, run_id=run_id)
        for job_id in sorted(affected):
            # Explicit cancellation retires only registered automation tabs.
            # The established close ACK clears stale Bridge status afterward.
            bridge.queue_extension_command("close_automation_browser", job_id)
        if owned.intersection(self._creation_remote_busy_jobs()) - affected:
            self._desktop_set_notice("warning", "ยกเลิกคิวแล้ว • ยังยืนยันเจ้าของงานบนเว็บบางงานไม่ได้ จึงยังไม่ได้สั่งหยุดหน้าเว็บนั้น • ตรวจ Chrome ก่อนทำต่อ")

    def _creation_idle_reason(self, ignore_remote_jobs=()):
        covers = getattr(getattr(self, 'bridge', None), 'ai_covers', None)
        from core.ai_cover import AICovers
        if isinstance(covers, AICovers) and covers.active():
            return 'กำลังสร้างปก AI • รอให้เสร็จหรือยกเลิกปกในคลังวิดีโอก่อน'
        if self._creation_workers_alive():
            return "งานเดิมยังทำงานหรือกำลังยกเลิก • รอให้หยุดก่อน"
        if getattr(self, "_manual_multi_flow_job_id", ""):
            return "มี Google Flow ที่เริ่มเองกำลังทำงาน • หยุดงานนั้นก่อน"
        if self._creation_remote_busy_jobs() - set(ignore_remote_jobs):
            return "หน้า AI/Flow ยังรายงานว่ามีงานค้าง • ตรวจหรือยกเลิกงานเดิมก่อน"
        for scope, manager_name in (("product", "products"), ("story", "stories")):
            job_id = str(getattr(self, f"_{scope}_pipeline_job_id", "") or "")
            if not job_id:
                continue
            event = getattr(self, f"_{scope}_cancel_event", None)
            if event is not None and event.is_set():
                return "กำลังยืนยันการยกเลิกงานเดิม • รอให้หยุดก่อน"
            worker = getattr(self, f"_creation_{scope}_worker", None)
            if worker is not None and not worker.is_alive():
                continue
            try:
                manager = getattr(self, manager_name)
                job = manager.get_job(job_id) if scope == "product" else manager.get(job_id)
                status = str(job.get("automation_status") if scope == "product" else job.get("status"))
                if status in {"completed", "ready", "failed", "error", "cancelled", "idle"}:
                    continue
            except Exception:
                pass
            return "มีงานปัจจุบันอยู่ • ยกเลิกหรือรอให้งานจบก่อน"
        if getattr(self, "_story_render_active", None) or getattr(self, "_subtitle_render_active", None):
            return "กำลังประกอบวิดีโอหรือคำบรรยาย • รอให้เสร็จก่อน"
        return ""

    def _creation_clear_idle_references(self):
        """Release UI references only after the caller has checked live ownership."""
        for key in ("_creation_tick_after", "_story_monitor_after"):
            timer = getattr(self, key, None)
            if timer is not None:
                try:
                    self.root.after_cancel(timer)
                except Exception:
                    pass
                setattr(self, key, None)
        self._creation_dispatch_item = None
        self._product_pipeline_job_id = ""
        self._story_pipeline_job_id = ""
        self._product_cancel_event = None
        self._story_cancel_event = None
        self._product_verification_job = ""
        self._product_web_action = {}
        # Keep browser-close gates, command/run receipts, attachment terminals,
        # voice request IDs and all Job checkpoints. They are recovery proof.

    def _creation_existing_job(self, job_id):
        if not re.fullmatch(r"(?:JOB|STORY)-[A-Za-z0-9-]+", str(job_id or "")):
            raise ValueError("Job ID ไม่ถูกต้อง")
        mode = "product" if job_id.startswith("JOB-") else "story"
        manager = self.products if mode == "product" else self.stories
        root = Path(manager.root).resolve()
        path = (root / job_id / "job.json").resolve()
        if root not in path.parents:
            raise ValueError("ตำแหน่ง Job ไม่ถูกต้อง")
        job = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(job, dict) or str(job.get("id") or "") != job_id:
            raise ValueError("ข้อมูล Job ไม่ถูกต้อง")
        return mode, job

    @staticmethod
    def _creation_job_recoverable(mode, job):
        from ui.story_recovery import pending_short, stopped_short
        if mode == 'story' and stopped_short(job):
            return pending_short(job)
        return not (job.get("cancel_requested") or job.get("job_type") == "drama_episode"
                    or job.get("series_id") or job.get("status") in {"cancelled", "deleted"}
                    or job.get("automation_status") in {"cancelled", "completed"}
                    or (mode == "story" and job.get("status") == "ready" and job.get("video_status") == "ready"))

    def _creation_recoverable_jobs(self, items, limit=30):
        # A small cached inventory avoids list_jobs(), whose legacy read path
        # can repair/update manifests. Only an explicit action binds a Job.
        now = time.monotonic()
        cache = getattr(self, "_creation_recovery_inventory", None)
        if not isinstance(cache, dict) or now - cache.get("at", 0) > 10:
            rows = []
            for mode, manager_name, pattern in (("product", "products", "JOB-*"), ("story", "stories", "STORY-*")):
                manager = getattr(self, manager_name, None)
                try:
                    paths = Path(manager.root).glob(f"{pattern}/job.json")
                    for path in paths:
                        try:
                            _, job = self._creation_existing_job(path.parent.name)
                            if self._creation_job_recoverable(mode, job):
                                rows.append({"job_id": job["id"], "mode": mode,
                                             "long_video": bool(job.get("long_video")),
                                             "title": str(job.get("product_name") or job.get("video_title") or job.get("topic") or job["id"])[:200],
                                             "status": str(job.get("automation_status") or job.get("status") or ""),
                                             "updated_at": str(job.get("updated_at") or "")})
                        except (OSError, ValueError, TypeError):
                            continue
                except (OSError, TypeError, AttributeError):
                    continue
            cache = {"at": now, "items": sorted(rows, key=lambda row: row["updated_at"], reverse=True)}
            self._creation_recovery_inventory = cache
        unavailable = {str(item.get("job_id") or "") for item in items}
        unavailable.update(self.story_queue.dismissed_creation_jobs())
        unavailable.update(ident for ident, control in self.story_queue.product_job_controls().items()
                           if control.get('trashed'))
        unavailable.update(self._creation_remote_busy_jobs())
        unavailable.update(str(getattr(self, f"_{scope}_pipeline_job_id", "") or "") for scope in ("product", "story"))
        rows = [dict(row) for row in cache["items"] if row["job_id"] not in unavailable]
        return rows if limit is None else rows[:limit]

    def _creation_remove_old_entries(self, payload):
        if payload.get('confirmed') is not True:
            raise ValueError('กรุณายืนยันการลบรายการงานเก่า • ไฟล์งานจะไม่ถูกลบ')
        queue_ids, job_ids = payload.get('queue_ids', []), payload.get('job_ids', [])
        for values, pattern in ((queue_ids, r'(?:CQ|SQ)-[A-Za-z0-9-]+'),
                                (job_ids, r'(?:JOB|STORY)-[A-Za-z0-9-]+')):
            if not isinstance(values, list) or len(values) > 2000 or any(
                    not isinstance(value, str) or not re.fullmatch(pattern, value) for value in values):
                raise ValueError('รายการที่ต้องการลบไม่ถูกต้อง')
        queue_ids, job_ids = list(dict.fromkeys(queue_ids)), list(dict.fromkeys(job_ids))
        if not queue_ids and not job_ids:
            raise ValueError('ไม่มีรายการงานเก่าที่เลือกไว้')
        queue = self.story_queue
        with queue._lock, queue._store.locked():
            reason = self._creation_idle_reason()
            if reason:
                raise ValueError(reason)
            snapshot = queue.snapshot()
            rows = [row for row in snapshot['items'] if row.get('queue_id') in queue_ids]
            targets = set(job_ids) | {row['job_id'] for row in rows if row.get('job_id')}
            bridge = getattr(self, 'bridge', None)
            if bridge is not None and bridge.pending_job_commands(list(targets)):
                raise ValueError('ยังมีคำสั่งของงานนี้รอยืนยัน • รอหรือยกเลิกงานก่อนลบรายการ')
            if bridge is not None:
                # Losing the bridge heartbeat does not prove a provider stopped.
                for client in bridge.extension_status().get('clients', []):
                    for scope in ('ai', 'flow'):
                        if client.get(f'{scope}_job_id') in targets and str(client.get(f'{scope}_step') or '') not in REMOTE_TERMINAL_STEPS:
                            raise ValueError('ยังยืนยันว่าเว็บหยุดงานนี้ไม่ได้ • ตรวจหรือยกเลิกงานก่อนลบรายการ')
            for ident in job_ids:
                mode, job = self._creation_existing_job(ident)
                if not self._creation_job_recoverable(mode, job):
                    raise ValueError('งานเก่าเปลี่ยนสถานะแล้ว • ตรวจรายการอีกครั้งก่อนลบ')
            removed = queue.remove_old_entries(queue_ids, job_ids)
        self._creation_recovery_inventory = None
        self._write_console(f'CREATION QUEUE • REMOVE OLD • {removed} รายการ • เก็บไฟล์เดิม', 'log')
        return {'ok': True, 'removed': removed, 'creation_queue': self._creation_queue_state()}

    def _creation_resume_existing_jobs(self, job_ids):
        if not isinstance(job_ids, list) or not 1 <= len(job_ids) <= 10:
            raise ValueError("เลือกงานเดิม 1–10 งาน")
        entries = []
        for job_id in dict.fromkeys(map(str, job_ids)):
            mode, job = self._creation_existing_job(job_id)
            if not self._creation_job_recoverable(mode, job):
                raise ValueError("งานนี้เสร็จแล้ว ถูกยกเลิก หรือเป็น EP ละคร • ใช้หน้าจัดการงานเดิม")
            if self.story_queue.item_for_job(job_id):
                raise ValueError("งานนี้อยู่ในคิวแล้ว • ใช้ปุ่มทำต่อของรายการเดิม")
            provider = str(job.get("image_ai_provider") or "chatgpt")
            model = normalize_ai_web_model(provider, job.get("ai_web_model"))
            settings = self._creation_capture_settings({"provider": provider, "ai_web_model": model, "job_id": job_id})
            settings.update(clean_settings(job))
            settings.update(provider=provider, ai_web_model=model,
                            subtitle_enabled=(job.get("audio_choices") or {}).get("subtitle", bool(job.get("subtitle_requested", settings.get("subtitle_enabled", True))) if mode == "product" else (job.get("render_options") or {}).get("subtitle_enabled", True)))
            entries.append({"mode": mode, "job_id": job_id,
                            "topic": str(job.get("product_name") or job.get("topic") or job_id),
                            "link": str(job.get("product_url") or "") if mode == "product" else "",
                            "provider": provider, "ai_web_model": model, "settings": settings,
                            "scene_count": int(job.get("scene_count") or 10),
                            "visual_style": str(job.get("visual_style") or "auto"),
                            "visual_style_custom": str(job.get("visual_style_custom") or ""),
                            "video_generation_mode": str(job.get("video_generation_mode") or "image_motion")})
        return self.story_queue.enqueue_existing_jobs(entries)

    def _creation_capture_settings(self, payload=None):
        payload = payload or {}
        from core.product_runtime_snapshot import prepared_product_runtime
        saved_product = prepared_product_runtime(getattr(self, 'products', None), payload)
        if saved_product is not None:
            return saved_product
        from core.storytelling import validate_settings, native_acting
        telling = validate_settings(payload.get('storytelling_options'), payload.get('video_generation_mode', 'image_motion'), payload.get('audio_choices'))
        if telling:
            payload = {**payload, 'actor_dialogue': native_acting(telling)}
        if payload.get('actor_dialogue') is True and not payload.get('job_id') and not telling:
            from core.story_performance import conversation_audio, validate_option
            validate_option(True, payload.get('video_generation_mode', 'image_motion'), payload.get('audio_choices'),
                            telling)
            payload = {**payload, 'audio_choices': conversation_audio(payload.get('audio_choices')), 'subtitle': False}
        options = self._product_pipeline_options(queued=False)
        if payload.get('creative_context'):
            options['creative_context'] = copy.deepcopy(payload['creative_context'])
        from core.product_script import product_script_options
        script_options = product_script_options(payload.get('product_script_options'), product=bool(
            (payload.get('creative_context') or {}).get('kind') == 'product_story'
            and (payload.get('creative_context') or {}).get('product_short') is True))
        if script_options is not None:
            options['product_script_options'] = script_options
        if payload.get('story_structure_options') is not None:
            from core.creative_brief import story_structure_options
            if payload.get('long_video') or payload.get('creative_context') or payload.get('flow_smoke_test'):
                raise ValueError('โครงเรื่อง Shorts ใช้กับเรื่องเล่า Shorts ใหม่เท่านั้น')
            options['story_structure_options'] = story_structure_options(payload['story_structure_options'])
        if payload.get('generated_music_options') is not None:
            from core.generated_music import validate_options
            options['generated_music_options'] = validate_options(payload['generated_music_options'],
                payload.get('video_generation_mode', 'image_motion'), payload.get('audio_choices'))
        options.pop("audio_choices", None)
        options['actor_dialogue'] = payload.get('actor_dialogue', False)
        if telling:
            options['storytelling_options'] = telling
        from core.flow_settings import snapshot_flow
        options["flow_settings"] = snapshot_flow(payload, self.cfg.get("flow_defaults"))
        from core.ai_cover import ai_cover_options
        options['ai_cover_options'] = ai_cover_options(payload.get('ai_cover_options'))
        from ui.video_intro import capture_intro
        options['intro_options'] = capture_intro(self, payload.get('intro_options'))
        from core.green_screen import GreenLibrary
        from core.config import ROOT
        options['green_options'] = GreenLibrary(ROOT,self.cfg.get('ffmpeg_path','')).validate(payload.get('green_options'))
        options["fictional_ai_characters_confirmed"] = payload.get("fictional_ai_characters_confirmed") is True
        options["presenter"] = {"enabled": False}
        if "presenter" in payload:
            options["presenter"] = self._presenter_selection(payload["presenter"])
        provider = str(payload.get("provider") or options["provider"])
        options.update(provider=provider, ai_web_model=normalize_ai_web_model(provider, payload.get("ai_web_model") or options.get("ai_web_model")))
        if "subtitle" in payload:
            options["subtitle_enabled"] = bool(payload["subtitle"])
        options["finish_config"] = {
            key: value for key, value in self.cfg.items()
            if key.startswith(("subtitle_", "audio_", "logo_", "video_")) or key == "ffmpeg_path"
        }
        options["finish_config"]["subtitle_auto_after_voice"] = options["subtitle_enabled"]
        if "audio_choices" in payload:
            from core.media_audio import audio_choices, product_audio_options
            choices = audio_choices(payload["audio_choices"], payload.get("video_generation_mode", "flow"))
            if choices["music"]:
                mode = self._background_mode_key(self.audio_background_mode.get())
                options["audio"]["background_files"] = self._selected_audio_files("background", self.audio_background_file.get(), mode)
                if options["audio"].get("music_track_count") is not None and not options["audio"]["background_files"]:
                    raise ValueError("เลือกเพลงอย่างน้อยหนึ่งเพลงในหน้าตกแต่งคลิปก่อนเปิดเพลงพื้นหลัง")
            if choices["sfx"]:
                mode = self._sfx_mode_key(self.audio_sfx_mode.get())
                options["audio"]["sfx_files"] = self._selected_audio_files("sfx", self.audio_sfx_file.get(), mode)
                options["audio"]["sfx_mode"] = mode
            options = product_audio_options(options, choices)
        # Capture only NEW jobs. Existing rows and prepared products keep their
        # saved contract, even when execution happens after an upgrade.
        if not payload.get('job_id') and not payload.get('queue_id'):
            options['speech_delivery_version'] = 1
            options['product_editorial_version'] = 1
        return clean_settings(options)

    def _creation_settings(self, job_id=""):
        item = self.story_queue.item_for_job(job_id) if job_id else self.story_queue.running_item()
        if not item or item.get("status") != "running":
            if job_id and job_id.startswith('STORY-'):
                try:
                    saved = self.stories.get(job_id).get('product_runtime_snapshot')
                except (ValueError, OSError):
                    saved = None
                if isinstance(saved, dict):
                    return clean_settings(copy.deepcopy(saved))
            return {}
        return copy.deepcopy(item.get("settings") or {})

    def _creation_pipeline_options(self, options):
        item = self.story_queue.running_item()
        dispatch = getattr(self, "_creation_dispatch_item", None)
        if item and dispatch and item["queue_id"] == dispatch["queue_id"]:
            options.update(copy.deepcopy(item.get("settings") or {}))
            options["queue_id"] = item["queue_id"]
            options["queue_attempt"] = int(item.get("attempt") or 0)
        return options

    def _creation_preflight(self, item):
        settings = item.get("settings") or {}
        job_id = str(item.get("job_id") or "")
        job = {}
        if job_id:
            job = self.products.get_job(job_id) if item.get("mode") == "product" else self.stories.get(job_id)
        voice_ready = job.get("voice_status") == "ready"
        reference = str(settings.get("voice_reference_id", self.voice_reference_id.get()) or "")
        reference_file = str(settings.get("voice_reference_file", self.voice_reference_file.get()) or "")
        if item.get('mode') == 'drama':
            series_options = item.get('render_options') or {}
            reference = str(series_options.get('primary_voice_reference_id') or reference)
            frozen_file = str(series_options.get('primary_voice_reference_file') or '')
            if frozen_file:
                target = Path(frozen_file)
                if not target.is_absolute():
                    target = self.drama_series.folder_path(str(item.get('series_id') or '')) / target
                reference_file = str(target)
        choice = job.get("audio_choices") or settings.get("audio_choices") or (item.get("render_options") or {}).get("audio_choices") or {}
        mode = choice.get("mode", "api")
        if mode == "api" and not voice_ready and (not self.voice_api_key.get().strip() or (not reference and not Path(reference_file).is_file())):
            raise ValueError("พักคิว • กรุณาตั้งค่า AI Voice และเลือกเสียงต้นแบบก่อนเริ่ม")
        if (item.get("mode") == "product" or mode == "flow_original") and mode != "none" and choice.get("subtitle", settings.get("subtitle_enabled")) and job.get("subtitle_status") != "ready" and not self._subtitle_store().load():
            raise ValueError("พักคิว • กรุณาเชื่อมต่อ Subtitle ก่อนเริ่ม")
        extension, compatible = self._compatible_extension()
        if extension.get("connected") and not compatible:
            raise ValueError(f"พักคิว • ต้องอัปเดต Extension เป็น {self.bridge.REQUIRED_EXTENSION_VERSION}")

    def _creation_prepare_dispatch(self, item):
        try:
            self._creation_preflight(item)
        except Exception as exc:
            self.story_queue._update(item["queue_id"], status="queued", error=str(exc))
            self.story_queue.pause("preflight")
            self._desktop_set_notice("warning", str(exc))
            self._write_console(f"CREATION QUEUE • {item['queue_id']} • WAITING • {exc}", "error")
            return False
        self._creation_dispatch_item = dict(item)
        self._write_console(f"CREATION QUEUE • {item['queue_id']} • START • {item.get('mode', 'story')} • attempt {item.get('attempt', 0)}", "success")
        return True

    def _creation_cover_gate(self, job_id, item=None):
        """Hold completion/cleanup without turning a cover failure into a render retry."""
        from core.ai_cover import AICovers
        covers = getattr(getattr(self, 'bridge', None), 'ai_covers', None)
        if not isinstance(covers, AICovers):
            return True  # Legacy isolated adapters do not run provider covers.
        try:
            result = covers.completion(job_id)
        except Exception as exc:
            result = dict(ready=False, waiting=False,
                          message='ตรวจผลปกไม่ได้ • เก็บวิดีโอและพักคิวไว้ • ' + str(exc)[:250])
        if result['ready']:
            return True
        message = result['message']
        # A queued cover has not reached the provider. A connected Extension
        # with the wrong protocol version cannot claim it, so a periodic queue
        # tick would otherwise report "working" forever. Keep the exact request
        # and final video, and make the dependency visible before any Send.
        if result.get('phase') == 'queued':
            extension, compatible = self._compatible_extension()
            if extension.get('connected') and not compatible:
                result = {**result, 'waiting': False}
                message = (f"พักคิว • Extension รุ่นไม่ตรง • ต้องใช้รุ่น "
                           f"{self.bridge.REQUIRED_EXTENSION_VERSION} ก่อนสร้างปก AI • "
                           "คำขอปกและวิดีโอเดิมยังอยู่ • เมื่อเชื่อมต่อรุ่นที่ถูกต้องแล้วกดเริ่มคิวต่อ")
        item = item or self.story_queue.item_for_job(job_id)
        if item and item.get('status') in {'running', 'queued'}:
            # Keep Job/options/attempt/receipts. Do not release_running(), which
            # clears job_id and could regenerate the entire video on resume.
            self.story_queue._update(item['queue_id'],
                status='running' if result.get('waiting') else 'queued',
                error=message, finished_at='')
            if result.get('waiting'):
                self._schedule_next_story_queue_item(1000)
            else:
                self.story_queue.pause('ai_cover_needs_attention')
            self._creation_dispatch_item = None
        self.status.set(message)
        if not result.get('waiting'):
            self._desktop_set_notice('warning', message)
        return False

    def _creation_restore_final(self, item):
        job_id = str(item.get("job_id") or "")
        if not job_id:
            return False
        product = item.get("mode") == "product"
        manager = self.products if product else self.stories
        job = manager.get_job(job_id) if product else manager.get(job_id)
        terminal = job.get("automation_status") == "completed" if product else job.get("status") == "ready"
        if not terminal or job.get("video_status") != "ready":
            return False
        target = manager.root / job_id / str(job.get("video_path") or "")
        if not target.is_file() or target.stat().st_size <= 0:
            return False
        if not self._creation_cover_gate(job_id, item):
            return True  # This tick is consumed by cover wait/review, not a new render.
        if job.get('series_id'):
            self.drama_series.mark_episode_ready(
                {**job, '_folder': str(manager.root / job_id)}, target)
        self.story_queue._update(item["queue_id"], status="completed", error="", output_path=str(target), finished_at=self.story_queue._now())
        self._write_console(f"CREATION QUEUE • {item['queue_id']} • {job_id} • ใช้ไฟล์ Final ที่บันทึกสำเร็จแล้ว", "success")
        self._creation_dispatch_item = None
        self._schedule_next_story_queue_item(500)
        return True

    @uses_job_files(lambda app, item: item)
    def _creation_start_product(self, item):
        if not self._creation_prepare_dispatch(item):
            return
        settings = item.get("settings") or {}
        self.product_link.set("" if item.get("job_id") else str(item.get("link") or ""))
        self.image_ai_provider.set("Gemini Web" if item.get("provider") == "gemini" else "ChatGPT Web")
        self._set_ai_web_model(item.get("provider"), item.get("ai_web_model"))
        self.subtitle_auto.set(bool(settings.get("subtitle_enabled", True)))
        self._desktop_select_product(str(item.get("job_id") or ""))
        self._create_product_and_run(str(item.get("job_id") or ""))
        if not self._product_pipeline_job_id:
            self.story_queue._update(item["queue_id"], status="queued", error="เริ่มงานไม่ได้ • ตรวจการตั้งค่าแล้วทำต่อ")
            self.story_queue.pause("start_failed")
            self._creation_dispatch_item = None

    def _creation_attach_product(self, options, job_id, cancel_event):
        queue_id = options.get("queue_id")
        if not queue_id:
            return
        # Bind the imported Job even if cancellation just won the race, so a
        # later Retry does not create another Job for the same queue item.
        item = self.story_queue.bind_job(queue_id, options.get("queue_attempt"), job_id)
        if cancel_event.is_set() or not item or item.get("status") != "running":
            from core.cancellable_process import OperationCancelled
            raise OperationCancelled("คิวรอบนี้ถูกยกเลิกแล้ว")

    def _creation_product_terminal(self, job_id, status, message="", output=""):
        item = self.story_queue.item_for_job(job_id)
        if not item and (not job_id or job_id == "กำลังสร้าง Job"):
            running = self.story_queue.running_item()
            dispatch = getattr(self, "_creation_dispatch_item", None) or {}
            if running and running["queue_id"] == dispatch.get("queue_id"):
                item = running
                job_id = str(item.get("job_id") or "")
        if not item or item.get("mode") != "product" or item.get("status") != "running":
            return False
        if item.get("cancel_requested"):
            status, message = "cancelled", "ผู้ใช้ยกเลิกคิวทั้งหมด • เก็บ Job และไฟล์เดิมไว้"
        if status == "completed":
            if not self._creation_cover_gate(job_id, item):
                return True
            target = Path(output)
            if not target.is_file() or target.stat().st_size <= 0:
                status, message = "failed", "ไม่พบไฟล์ Final ที่พร้อมใช้งาน"
        self.story_queue._update(item["queue_id"], status=status, error=str(message)[:1500],
                                 output_path=str(output), finished_at=self.story_queue._now())
        self._creation_dispatch_item = None
        self._write_console(f"CREATION QUEUE • {item['queue_id']} • {job_id or '-'} • {status.upper()} • {message}", "success" if status == "completed" else "error")
        if status == "failed":
            # A terminal bad input can be skipped. Unknown/remote failures may
            # still be rendering: pause rather than opening another Flow job.
            bad_input = not job_id and any(word in str(message) for word in ("ลิงก์", "URL", "url", "ไม่พบสินค้า"))
            if not bad_input:
                self.story_queue.pause("job_needs_attention")
        elif status == "cancelled":
            self.story_queue.pause("user_cancel")
        self._schedule_next_story_queue_item(500)
        return True

    def _creation_story_failure(self, item, message):
        if not item:
            return
        self._creation_dispatch_item = None
        from core.product_editorial import queue_safe_failure
        try:
            editorial_only = queue_safe_failure(self.stories.get(item.get('job_id')), message)
        except Exception:
            editorial_only = False
        if editorial_only:
            self._write_console(f"CREATION QUEUE • {item['queue_id']} • ตรวจบทเฉพาะงานนี้ • {message}", "error")
            self._schedule_next_story_queue_item(2200)
            return
        # Existing bounded per-job recovery gets its chance first. A terminal
        # unknown browser/credit failure must not cascade through all items.
        self.story_queue.pause("job_needs_attention")
        self._write_console(f"CREATION QUEUE • {item['queue_id']} • PAUSED • {message}", "error")

    def _creation_queue_state(self):
        snapshot = self.story_queue.snapshot()
        rows = []
        for item in snapshot["items"]:
            # Avoid sending frozen render config/paths/secrets on every poll.
            rows.append({key: item.get(key) for key in (
                "queue_id", "mode", "topic", "link", "order", "status", "job_id", "error",
                "provider", "ai_web_model", "scene_count", "visual_style", "attempt", "created_at",
                "cancel_requested", "finished_at", "video_generation_mode",
            )} | {"subtitle": bool((item.get("settings") or {}).get("subtitle_enabled", True)),
                  "long_video": bool(item.get('long_video')),
                  "settings": _editor_settings(item.get('settings') or {})})
        busy_reason = self._creation_idle_reason()
        old_jobs = self._creation_recoverable_jobs(snapshot['items'], limit=None)
        old_queue_ids = [row['queue_id'] for row in snapshot['items']
                         if row.get('status') in {'failed', 'cancelled'}
                         and row.get('mode') != 'drama' and not row.get('series_id')]
        return {**{key: value for key, value in snapshot.items() if key != "items"}, "items": rows,
                "unfinished_count": sum(i.get("status") in {"queued", "running", "failed"} and not i.get("cancel_requested") for i in snapshot["items"]),
                "cancelable_count": sum(i.get("status") in {"queued", "running", "failed"} and not i.get("cancel_requested") for i in snapshot["items"]),
                "can_clear_stuck_state": not bool(busy_reason), "stuck_state_blocked_reason": busy_reason,
                "recoverable_jobs": old_jobs[:30], 'recoverable_job_count': len(old_jobs),
                'removable_old_queue_ids': old_queue_ids,
                'removable_old_job_ids': [row['job_id'] for row in old_jobs],
                'can_remove_old_entries': not bool(busy_reason)}

    @uses_job_files(lambda app, action, payload: (payload, [row for row in app.story_queue.snapshot().get('items', [])
        if row.get('queue_id') == payload.get('queue_id') or (action in {'creation_start', 'story_queue_resume', 'creation_start_series', 'creation_resume_unfinished', 'creation_resume_jobs'}
            and row.get('status') in {'queued', 'running', 'failed'})]), serialize=True)
    def _creation_queue_action(self, action, payload):
        if action == 'creation_remove_old':
            return self._creation_remove_old_entries(payload)
        if action in {'creation_enqueue', 'enqueue_story_batch'}:
            context = payload.get('creative_context') or {}
            if context.get('kind') == 'product_story' and context.get('source_product_id'):
                self.story_queue.require_not_trashed(context['source_product_id'])
        if action=='creation_enqueue' and (payload.get('creative_context') or {}).get('kind')=='product_story':
            selected_video = 'meta_ai' if payload.get('video_generation_mode') == 'meta_ai' or payload.get('video_provider') == 'meta_ai' else 'google_flow'
            payload={**payload,'mode':'story','video_generation_mode':selected_video}
        if action in {"creation_enqueue", "enqueue_story_batch"}:
            mode = "story" if action == "enqueue_story_batch" else str(payload.get("mode") or "product")
            values = payload.get("topics") if action == "enqueue_story_batch" else payload.get("values")
            main_image = self._resolve_desktop_reference_image(payload.get("main_image")) if mode == "story" else ""
            options = self._creation_capture_settings(payload)
            if mode == "story":
                # Story's established finisher always renders its narration captions.
                options["subtitle_enabled"] = (options.get("audio_choices") or {}).get("subtitle", True)
            result = self.story_queue.enqueue(
                mode, values, settings=options, request_id=str(payload.get("request_id") or ""),
                queue_only=payload.get("queue_only") is True,
                flow_smoke_test=payload.get("flow_smoke_test") is True,
                provider=options["provider"], ai_web_model=options["ai_web_model"],
                main_image=main_image, story_text=payload.get("story_text", ""),
                scene_count=payload.get("scene_count", 10), video_generation_mode=payload.get("video_generation_mode", "image_motion"),
                visual_style=payload.get("visual_style", "auto"), visual_style_custom=payload.get("visual_style_custom", ""),
            )
            self._write_console(f"CREATION QUEUE • ADD • {len(result['items'])} รายการ • ซ้ำ {result['duplicates']} • {result['batch_id']}", "success")
            self._schedule_next_story_queue_item(200)
            return {"ok": True, "queued": len(result["items"]), "duplicates": result["duplicates"],
                    "batch_id": result["batch_id"], "paused": result["paused"]}
        queue_id = str(payload.get("queue_id") or "")
        if action == "creation_start_series":
            series_id = str(payload.get("series_id") or "")
            series = self.drama_series.get(series_id)
            snapshot = self.story_queue.snapshot()
            running = self.story_queue.running_item()
            if running and running.get("series_id") == series_id and snapshot.get("run_series_id") == series_id and not running.get("cancel_requested"):
                return {"ok": True, "already_running": True}
            reason = self._creation_idle_reason()
            if reason:
                raise ValueError(reason)
            remaining = sorted((ep for ep in series.get("episodes", []) if ep.get("status") != "completed"),
                               key=lambda ep: int(ep.get("episode_no") or 0))
            if series.get("status") == "cancelled" or not remaining or remaining[0].get("status") != "queued":
                raise ValueError("ตอนแรกที่ยังไม่เสร็จต้องกู้คืนหรือตรวจสอบก่อน • ไม่ข้ามไปสร้างตอนถัดไป")
            self.story_queue.resume(series_id=series_id)
            self._creation_clear_idle_references()
            self._schedule_next_story_queue_item(200)
        elif action in {"creation_start", "story_queue_resume"}:
            running = self.story_queue.running_item()
            if running and running.get("cancel_requested"):
                raise ValueError("กำลังยกเลิกงานเดิม • รอให้หยุดก่อนเริ่มคิว")
            self.story_queue.resume()
            self._schedule_next_story_queue_item(200)
        elif action in {"creation_resume_unfinished", "creation_resume_jobs", "creation_clear_stuck_state"}:
            reason = self._creation_idle_reason()
            if reason:
                raise ValueError(reason)
            if action == "creation_resume_unfinished":
                self.story_queue.resume_unfinished(allow_orphan_running=True)
            elif action == "creation_resume_jobs":
                self._creation_resume_existing_jobs(payload.get("job_ids"))
                self.story_queue.resume()
            else:
                self.story_queue.clear_stuck_state()
                self._desktop_set_notice("success", "ล้างสถานะคิวและหน้าจอที่ค้างแล้ว • เก็บ Job รูป เสียง คลิป และหลักฐานการส่งเดิมครบ • คิวยังพักอยู่")
            self._creation_clear_idle_references()
            self._creation_recovery_inventory = None
            if action != "creation_clear_stuck_state":
                self._schedule_next_story_queue_item(200)
        elif action == "creation_cancel_all":
            before = self.story_queue.snapshot()["items"]
            running = self.story_queue.running_item()
            scope = "product" if running and running.get("mode") == "product" else "story"
            active_job = str(getattr(self, f"_{scope}_pipeline_job_id", "") or "")
            dispatch = getattr(self, "_creation_dispatch_item", None) or {}
            owns_active = bool(running and active_job and (running.get("job_id") == active_job
                               or (not running.get("job_id") and dispatch.get("queue_id") == running["queue_id"])))
            self.story_queue.cancel_all(active_queue_id=running["queue_id"] if owns_active else "")
            if owns_active:
                if scope == "product":
                    self._cancel_product_pipeline()
                else:
                    self._cancel_story_pipeline()
            elif not self._creation_workers_alive():
                self._creation_dispatch_item = None
            self._creation_cancel_remote_queue_jobs(before, active_job if owns_active else "")
            self._creation_recovery_inventory = None
        elif action in {"creation_pause", "story_queue_pause"}:
            self.story_queue.pause("user")
        elif action == "creation_move":
            self.story_queue.move(queue_id, int(payload.get("direction") or 0))
        elif action == "creation_remove":
            self.story_queue.remove(queue_id)
        elif action == "creation_retry":
            reason = self._creation_idle_reason()
            if reason:
                raise ValueError(reason)
            self.story_queue.retry(queue_id)
            self.story_queue.resume()
            self._creation_clear_idle_references()
            self._schedule_next_story_queue_item(200)
        elif action == "creation_edit":
            row = next(x for x in self.story_queue.snapshot()['items'] if x['queue_id'] == queue_id)
            if 'ai_cover_options' in payload:
                from core.ai_cover import ai_cover_options
                if not isinstance(payload['ai_cover_options'], dict):
                    raise ValueError('ค่าปกของรายการคิวไม่ถูกต้อง')
                # Partial modal edits must not clear a hidden legacy headline.
                # An explicitly supplied empty string remains an intentional clear.
                payload = {**payload, 'ai_cover_options': ai_cover_options({
                    **((row.get('settings') or {}).get('ai_cover_options') or {}), **payload['ai_cover_options']})}
            if payload.get('use_current_settings') and 'actor_dialogue' not in payload:
                row = next(x for x in self.story_queue.snapshot()['items'] if x['queue_id'] == queue_id)
                payload = {**payload, 'actor_dialogue': (row.get('settings') or {}).get('actor_dialogue', False),
                           **({'storytelling_options': copy.deepcopy(row['settings']['storytelling_options'])} if (row.get('settings') or {}).get('storytelling_options') else {}),
                           'video_generation_mode': row.get('video_generation_mode', 'image_motion')}
            preserved = None
            if "audio_choices" in payload and not payload.get("use_current_settings"):
                from core.media_audio import audio_choices
                row = next(x for x in self.story_queue.snapshot()["items"] if x["queue_id"] == queue_id)
                preserved = copy.deepcopy(row.get("settings") or {})
                preserved["audio_choices"] = audio_choices(payload["audio_choices"], row.get("video_generation_mode", "flow"))
                preserved["subtitle_enabled"] = preserved["audio_choices"]["subtitle"]
                if "fictional_ai_characters_confirmed" in payload:
                    preserved["fictional_ai_characters_confirmed"] = payload["fictional_ai_characters_confirmed"] is True
            if "flow_settings" in payload and not payload.get("use_current_settings"):
                from core.flow_settings import flow_settings
                if preserved is None:
                    row = next(x for x in self.story_queue.snapshot()["items"] if x["queue_id"] == queue_id)
                    preserved = copy.deepcopy(row.get("settings") or {})
                preserved["flow_settings"] = flow_settings(payload["flow_settings"])
            if 'ai_cover_options' in payload and not payload.get('use_current_settings'):
                from core.ai_cover import ai_cover_options
                if preserved is None:
                    row = next(x for x in self.story_queue.snapshot()['items'] if x['queue_id'] == queue_id)
                    preserved = copy.deepcopy(row.get('settings') or {})
                preserved['ai_cover_options'] = ai_cover_options(payload['ai_cover_options'])
            if 'green_options' in payload and not payload.get('use_current_settings'):
                from core.green_screen import green_options
                if row.get('mode') not in {'product', 'story'} or row.get('long_video'):
                    raise ValueError('รายการนี้ไม่รองรับการแก้กรีนสกรีน')
                if not isinstance(payload['green_options'], dict):
                    raise ValueError('ค่ากรีนสกรีนของรายการคิวไม่ถูกต้อง')
                if preserved is None:
                    preserved = copy.deepcopy(row.get('settings') or {})
                preserved['green_options'] = green_options({
                    **(preserved.get('green_options') or {}), **payload['green_options']})
            for field in ('generated_music_options', 'story_structure_options', 'product_script_options'):
                if field in payload and not payload.get('use_current_settings'):
                    if preserved is None:
                        row = next(x for x in self.story_queue.snapshot()['items'] if x['queue_id'] == queue_id)
                        preserved = copy.deepcopy(row.get('settings') or {})
                    preserved[field] = copy.deepcopy(payload[field])
            if preserved is not None:
                from core.generated_music import validate_options
                preserved['generated_music_options'] = validate_options(preserved.get('generated_music_options'),
                    row.get('video_generation_mode', 'image_motion'), preserved.get('audio_choices'))
                if preserved['generated_music_options'] is None:
                    preserved.pop('generated_music_options')
            self.story_queue.edit(queue_id, payload.get("value"),
                                  settings=self._creation_capture_settings(payload) if payload.get("use_current_settings") else preserved,
                                  provider=payload.get("provider"), scene_count=payload.get("scene_count"), visual_style=payload.get("visual_style"))
        elif action == "creation_cancel_current":
            self.story_queue.pause("user_cancel")
            if self._product_pipeline_job_id:
                self._cancel_product_pipeline()
            elif self._story_pipeline_job_id:
                self._cancel_story_pipeline()
            else:
                running = self.story_queue.running_item()
                if running:
                    self.story_queue._update(running["queue_id"], status="cancelled", error="ผู้ใช้ยกเลิกรายการ", finished_at=self.story_queue._now())
        else:
            raise ValueError("คำสั่งคิวไม่ถูกต้อง")
        self._write_console(f"CREATION QUEUE • {action} • {queue_id or '-'}", "log")
        return {"ok": True, "creation_queue": self._creation_queue_state()}
