import base64
from core.flow_settings import flow_settings
from core.media_audio import flow_audio_instruction
from core import story_performance, storytelling
from core.product_script import (product_script_options as normalize_product_script, story_first_review,
                                 authored_product_script, short_film_ad, script_instruction, validate_film_plan, creative_product_script, validate_creative_plan)
import binascii
import copy
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

from core.workspace_cleaner import working_video_folder
from core.ai_web_models import normalize_ai_web_model
from core.atomic_json import AtomicJsonFile, JsonPersistenceError, runtime_backup_path
from core.flow_fallback import FLOW_ATTACHMENT_UNCONFIRMED, validated_attachment_failure_evidence

from PIL import Image, ImageChops, ImageOps, ImageStat

from core.drama_media import DramaContinuityValidator, DramaCoverRenderer, StoryCoverRenderer
from core.clip_cover import COVER_PROMPT, normalize_cover, ensure_cover
from core.story_script import clean_dialogue_turn_text, spoken_script_for_job
from core.thai_tts import prepare_thai_tts_script
from core.story_styles import normalize_story_style, story_render_instruction, story_style_instruction
from core.story_receipt_recovery import legacy_first_image_receipt_proof
from core.story_image_result_recovery import completed_image_result_proofs
from core.story_content import (
    STORY_VISUAL_DEPICTION_INSTRUCTION, requested_story_names, story_source_aliases,
    story_content_instruction, validate_story_content,
)
from core.studio_review import voice_review, voice_locked, validate_user_notes


_STORY_MANIFEST_LOCK = threading.RLock()


def _lock_narrated_drama_cast(manifest, result):
    """Keep the user's saved cast and voice IDs authoritative in new narrator mode."""
    if (manifest.get('job_type') != 'drama_episode' or manifest.get('auto_cast_pending')
            or (manifest.get('storytelling_options') or {}).get('mode') != 'narrator'):
        return result
    locked = manifest.get('character_bible') or []
    if not locked:
        return result
    generated = result.get('character_bible')
    names = [str(row.get('name') or '').strip() for row in locked]
    if generated is not None:
        proposed = [str(row.get('name') or '').strip() for row in generated if isinstance(row, dict)] if isinstance(generated, list) else []
        if len(proposed) != len(names) or set(proposed) != set(names):
            raise ValueError('DRAMA_CAST_REVIEW • AI เปลี่ยนตัวละครที่ล็อกไว้กับซีรีส์')
    allowed = set(names) | {'ผู้บรรยาย'}
    groups = list(result.get('scene_dialogue_turns') or []) + [result.get('dialogue_turns') or []]
    for group in groups:
        if not isinstance(group, list):
            continue
        if any(not isinstance(turn, dict) or str(turn.get('speaker') or '').strip() not in allowed
               for turn in group):
            raise ValueError('DRAMA_CAST_REVIEW • ผู้พูดไม่ตรงตัวละครของซีรีส์')
    result['character_bible'] = copy.deepcopy(locked)
    return result


class StoryManager:
    """Own Story Shorts jobs separately from Shopee product/Google Flow jobs."""

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

    def __init__(self, root):
        self.project_root = Path(root)
        self.root = self.project_root / "workspace" / "stories"
        self.root.mkdir(parents=True, exist_ok=True)
        self._manifest_lock = _STORY_MANIFEST_LOCK

    @staticmethod
    def _normalise_dialogue_speaker(value, character_names):
        """Keep AI speaker drift from discarding an otherwise complete episode.

        Speaker names are production metadata and are never read aloud.  Match
        harmless variants such as ``แอน``/``คุณแอน`` first.  A genuinely new
        speaker is routed through the narrator/default voice so the existing
        Character Bible remains authoritative instead of inventing a new
        character or regenerating every image.
        """
        original = str(value or "ผู้บรรยาย").strip().rstrip(" :：").strip()
        if original.lower() in {"narrator", "narration", "voice over", "voiceover"}:
            return "ผู้บรรยาย", None
        if original == "ผู้บรรยาย":
            return original, None
        if original in character_names:
            return original, None

        def key(name):
            compact = "".join(str(name or "").strip().lower().split()).rstrip(" :：")
            for prefix in ("คุณ", "พี่", "น้อง", "นาย", "นางสาว", "นาง"):
                if compact.startswith(prefix) and len(compact) > len(prefix):
                    return compact[len(prefix):]
            return compact

        original_key = key(original)
        matched = next((name for name in character_names if key(name) == original_key), None)
        if matched:
            return matched, {"from": original, "to": matched, "reason": "matched_character_alias"}
        return "ผู้บรรยาย", {"from": original, "to": "ผู้บรรยาย", "reason": "supporting_speaker_not_in_bible"}

    def create(
        self,
        topic="",
        story_text="",
        main_image="",
        scene_count=None,
        image_ai_provider="chatgpt",
        ai_web_model="",
        *,
        video_generation_mode="image_motion",
        job_type="story_short",
        source_images=None,
        source_footage=None,
        series_context=None,
        visual_style="auto",
        visual_style_custom="",
        long_video=None,
        long_source_audio_version=None,
        flow_smoke_test=False,
        cast_creation=False,
        product_short=False,
        actor_dialogue=False,
        storytelling_options=None,
        meta_prompt_version=None,
        product_script_options=None,
        story_structure_options=None,
        generated_music_options=None,
        meta_scene_sequence=False,
    ):
        topic = str(topic or "").strip()
        story_text = str(story_text or "").strip()
        if not topic and not story_text:
            raise ValueError("กรุณาใส่หัวข้อหรือเรื่องเล่าอย่างน้อยหนึ่งอย่าง")
        from core.long_video import long_video_settings, require_meta_landscape_available
        long_options = long_video_settings({**dict(long_video), 'video_generation_mode': video_generation_mode}) if long_video is not None else None
        from core.long_video import source_audio_version
        # None is a NEW direct job. Queue dispatch passes its captured version,
        # including explicit 0 for historical rows that have no audio contract.
        long_source_audio_version = source_audio_version(
            1 if long_source_audio_version is None else long_source_audio_version)
        if not long_options or long_options['version'] != 2 or video_generation_mode not in {'google_flow', 'meta_ai'}:
            long_source_audio_version = 0
        script_options = normalize_product_script(product_script_options, product=product_short is True)
        from core.creative_brief import story_structure_options as normalize_structure
        structure_options = normalize_structure(story_structure_options)
        if structure_options is not None and (long_options or product_short or cast_creation or flow_smoke_test or job_type != 'story_short'):
            raise ValueError('โครงเรื่องใหม่นี้ใช้กับ Shorts เท่านั้น')
        from core.generated_music import normalize_options as normalize_generated_music
        generated_music_options = normalize_generated_music(generated_music_options)
        requested_scene_count = scene_count
        scene_count = long_options['scene_count'] if long_options else max(6, min(15, int(scene_count or 10)))
        if product_short:
            if long_options or flow_smoke_test or cast_creation or job_type != 'story_short':
                raise ValueError('รูปแบบคลิปสินค้าไม่ถูกต้อง')
            from core.product_scene_settings import product_scene_count
            scene_count=product_scene_count(requested_scene_count)
        if flow_smoke_test:
            if long_options or video_generation_mode != 'google_flow' or job_type != 'story_short':
                raise ValueError('ทดสอบ Flow ต้องเป็นคลิปสั้น Google Flow เท่านั้น')
            scene_count = 1
        image_ai_provider = self._image_ai_provider(image_ai_provider)
        if cast_creation:
            if flow_smoke_test or long_options or video_generation_mode!='image_motion':raise ValueError('งานภาพบุคคลไม่สร้างวิดีโอ')
            scene_count=1
        ai_web_model = normalize_ai_web_model(image_ai_provider, ai_web_model)
        video_generation_mode = self._video_generation_mode(video_generation_mode)
        if video_generation_mode == 'meta_ai' and long_options:
            require_meta_landscape_available()
        if video_generation_mode == 'meta_ai':
            from core.meta_prompt import meta_prompt_version as validate_meta_version, CURRENT_META_PROMPT_VERSION
            meta_prompt_version = validate_meta_version(CURRENT_META_PROMPT_VERSION if meta_prompt_version is None else meta_prompt_version)
        storytelling_options = storytelling.validate_settings(storytelling_options, video_generation_mode, drama=job_type == 'drama_episode')
        if storytelling_options is not None:
            if long_options or product_short or cast_creation or flow_smoke_test:
                raise ValueError('รูปแบบการเล่านี้ใช้กับ Shorts และละครสั้นเท่านั้น')
            actor_dialogue = storytelling.native_acting(storytelling_options)
        story_performance.validate_option(actor_dialogue, video_generation_mode,
                                          storytelling_options=storytelling_options,
                                          drama=job_type == 'drama_episode')
        if actor_dialogue and (long_options or product_short or cast_creation or (job_type != 'story_short' and storytelling_options is None)):
            raise ValueError('ตัวละครพูดเองรุ่นนี้ใช้กับเรื่องเล่า Shorts เท่านั้น')
        visual_style, visual_style_custom = normalize_story_style(visual_style, visual_style_custom)
        job_id = f"STORY-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        folder = self.root / job_id
        for name in ("source", "footage", "generated", "prompts", "captions", "audio", "videos", "covers"):
            (folder / name).mkdir(parents=True, exist_ok=True)
        saved_source_images = []
        if str(main_image or "").strip():
            source = Path(main_image)
            if not source.is_file() or source.suffix.lower() not in self.IMAGE_EXTENSIONS:
                raise ValueError("รูปหลักต้องเป็น PNG, JPG หรือ WEBP")
            target = folder / "source" / f"main{source.suffix.lower()}"
            shutil.copy2(source, target)
            saved_source_images.append(str(target.relative_to(folder)))
        for index, value in enumerate(list(source_images or [])[:6], 1):
            source = Path(str(value or ""))
            if not source.is_file() or source.suffix.lower() not in self.IMAGE_EXTENSIONS:
                raise ValueError(f"รูปอ้างอิงที่ {index} ต้องเป็น PNG, JPG หรือ WEBP")
            target = folder / "source" / f"reference_{index:02d}{source.suffix.lower()}"
            if target.resolve() != source.resolve():
                shutil.copy2(source, target)
            relative = str(target.relative_to(folder))
            if relative not in saved_source_images:
                saved_source_images.append(relative)
        job_type = "drama_episode" if str(job_type or "") == "drama_episode" else "story_short"
        series_context = dict(series_context or {}) if job_type == "drama_episode" else {}
        saved_footage = []
        for index, value in enumerate(list(source_footage or [])[:6], 1):
            source = Path(str(value or ""))
            if not source.is_file() or source.suffix.lower() not in self.VIDEO_EXTENSIONS:
                raise ValueError(f"ฟุตเทจที่ {index} ไม่ใช่ไฟล์วิดีโอที่รองรับ")
            target = folder / "footage" / f"footage_{index:02d}{source.suffix.lower()}"
            shutil.copy2(source, target)
            saved_footage.append(str(target.relative_to(folder)))
        now = datetime.now().isoformat(timespec="seconds")
        manifest = {
            **({'meta_prompt_version': meta_prompt_version} if video_generation_mode == 'meta_ai' else {}),
            **({'actor_dialogue': True, 'actor_dialogue_version': 3 if storytelling_options else 2,
                'audio_choices': {'mode': 'none' if (storytelling_options or {}).get('mode') == 'visual' else 'flow_original',
                                  'subtitle': False, 'music': False, 'sfx': False}} if actor_dialogue else {}),
            **({'storytelling_options': storytelling_options} if storytelling_options is not None else {}),
            **({'story_structure_options': structure_options} if structure_options is not None else {}),
            **({'generated_music_options': generated_music_options} if generated_music_options is not None else {}),
            **({'product_short':True, 'product_presentation_version':1} if product_short else {}),
            **({'product_script_options':script_options} if script_options is not None else {}),
            **({'cast_creation':True} if cast_creation else {}),
            **({'flow_smoke_test': True} if flow_smoke_test else {}),
            **({'long_video': long_options, 'aspect_ratio': '16:9'} if long_options else {}),
            **({'long_source_audio_version': long_source_audio_version} if long_source_audio_version else {}),
            "id": job_id,
            "job_type": job_type,
            "topic": topic,
            "story_input": story_text,
            "scene_count": scene_count,
            "source_images": saved_source_images,
            "source_footage": saved_footage,
            "status": "waiting_chatgpt",
            "ai_status": "request_ready",
            "video_status": "waiting_story_images",
            "video_source_type": "meta_ai_pending" if video_generation_mode == "meta_ai" else "google_flow_pending" if video_generation_mode == "google_flow" else "story_image_sequence",
            "video_generation_mode": video_generation_mode,
            # Long v2 finishes image chapters before the video pass. Legacy
            # Flow/Shorts jobs keep their per-scene handoff unchanged.
            "scene_pipeline_version": 1 if video_generation_mode == "google_flow"
                and not (long_options and long_options['version'] == 2) else 0,
            "visual_style": visual_style,
            "visual_style_custom": visual_style_custom,
            "story_content_contract": {"version": 1},
            "flow_clips": {},
            "flow_clip_count": 0,
            "flow_fallback_clips": {},
            "flow_fallback_metadata": {},
            "flow_fallback_count": 0,
            "flow_policy_attempts": {},
            "flow_policy_failure_history": {},
            "flow_prompt_profiles": {},
            "flow_prompt_retries": {},
            "image_ai_provider": image_ai_provider,
            "ai_web_model": ai_web_model,
            "auto_recovery_total": 0,
            "created_at": now,
            "updated_at": now,
        }
        from core.meta_scene_sequence import eligible as meta_sequence_eligible
        if meta_scene_sequence is True and meta_sequence_eligible(manifest):
            manifest['meta_scene_sequence_version'] = 1
        if series_context:
            manifest.update({
                "series_id": str(series_context.get("series_id") or ""),
                "series_title": str(series_context.get("series_title") or ""),
                "episode_no": int(series_context.get("episode_no") or 1),
                "episode_count": int(series_context.get("episode_count") or 1),
                "character_bible": list(series_context.get("characters") or []),
                "auto_cast_pending": bool(series_context.get('auto_cast_pending')),
                "primary_voice_reference_id": str(series_context.get('primary_voice_reference_id') or ''),
                "primary_voice_reference_file": str(series_context.get('primary_voice_reference_file') or ''),
                "previous_visual_bible": series_context.get("visual_bible") or {},
                "previous_continuity_state": series_context.get("continuity_state") or {},
                "previous_episode_summary": str(series_context.get("previous_episode_summary") or ""),
                "previous_episode_hook": str(series_context.get("previous_episode_hook") or ""),
                "continuation_prompt": str(series_context.get("continuation_prompt") or ""),
                "open_ended": bool(series_context.get("open_ended")),
                "plot_board": list(series_context.get("plot_board") or []),
                "planned_episode": dict(series_context.get("planned_episode") or {}),
                "cover_theme": str(series_context.get("cover_theme") or "cinematic"),
            })
        self._save(manifest)
        self._write_request(folder, manifest)
        return manifest

    def list_jobs(self):
        jobs = []
        for folder in self.root.glob("STORY-*"):
            path = folder / "job.json"
            if not path.is_file() and not runtime_backup_path(self.project_root, path).is_file():
                continue
            try:
                value = self._manifest_store(path).peek()
                if isinstance(value, dict):
                    jobs.append(value)
            except (OSError, ValueError, JsonPersistenceError):
                continue
        return sorted(jobs, key=lambda item: item.get("created_at", ""), reverse=True)

    def get(self, job_id):
        from core.product_job_deletion import assert_job_available
        assert_job_available(self.project_root, job_id)
        folder = self._folder(job_id)
        path = folder / "job.json"
        if not path.is_file() and not runtime_backup_path(self.project_root, path).is_file():
            raise ValueError("ไม่พบ Story Job")
        with self._manifest_lock:
            try:
                value = self._manifest_store(path).read()
            except (OSError, ValueError, JsonPersistenceError) as exc:
                raise ValueError("Story manifest ว่างเปล่าหรือเสียหาย") from exc
            if not isinstance(value, dict):
                raise ValueError("Story manifest ว่างเปล่าหรือเสียหาย")
            return value

    def set_video_generation_mode(self, job_id, provider, expected_revision):
        """Change this saved job's video route while retaining every scene file and receipt."""
        provider = str(provider or '').strip().lower()
        if provider not in {'google_flow', 'meta_ai'}:
            raise ValueError('ผู้สร้างวิดีโอต้องเป็น Google Flow หรือ Meta AI')
        store = self._manifest_store(self._folder(job_id) / 'job.json')
        with self._manifest_lock, store.locked():
            job = store.read_unlocked()
            from core.scene_video_plan import enabled as has_video_plan
            if has_video_plan(job):
                raise ValueError('งานนี้ใช้แผนวิดีโอรายฉากแล้ว • เปลี่ยนเฉพาะฉากที่เหลือจากรายละเอียดงาน')
            if int(job.get('revision') or 0) != int(expected_revision):
                raise ValueError('งานเปลี่ยนระหว่างแก้ไข กรุณาเปิดรายละเอียดใหม่ก่อนบันทึก')
            if job.get('status') in {'running', 'recovering', 'cancelled', 'canceled', 'deleted'} or job.get('cancel_requested'):
                raise ValueError('งานกำลังทำงานหรือถูกยกเลิก • เปลี่ยนผู้สร้างวิดีโอไม่ได้')
            if job.get('video_status') in {'ready', 'complete', 'completed'} or any(job.get(key) for key in ('video_path', 'final_path', 'final_video_path')):
                raise ValueError('คลิปนี้เสร็จแล้ว • เปลี่ยนผู้สร้างจากงานที่ยังไม่เสร็จเท่านั้น')
            # Old interrupted jobs may still say ready_to_render while Meta
            # has an owned Send/download in its separate receipt ledger.
            # Read the atomically-replaced primary without taking the receipt
            # lock under the manifest lock (Meta event uses the reverse order).
            receipt_path = self._folder(job_id) / 'prompts' / 'meta_video_receipts.json'
            if receipt_path.is_file():
                try:
                    receipts = json.loads(receipt_path.read_text(encoding='utf-8'))
                    scenes = receipts.get('scenes') if isinstance(receipts, dict) else None
                    if not isinstance(scenes, dict):
                        raise ValueError('bad receipt ledger')
                except (OSError, ValueError) as exc:
                    raise ValueError('ใบรับงาน Meta อ่านไม่ได้ • ยังไม่เปลี่ยนผู้สร้างวิดีโอ') from exc
                active_stages = {'uploading', 'ready_to_send', 'send_intent', 'submitted',
                                 'generating', 'download_intent', 'downloading'}
                for index, receipt in scenes.items():
                    if not isinstance(receipt, dict):
                        raise ValueError('ใบรับงาน Meta ไม่ครบ • ยังไม่เปลี่ยนผู้สร้างวิดีโอ')
                    stage = str(receipt.get('stage') or '')
                    choice = receipt.get('choice') if isinstance(receipt.get('choice'), dict) else {}
                    choice_stage = str(choice.get('stage') or '')
                    uncertain = stage == 'needs_attention' and not receipt.get('retry_exhausted') and str(receipt.get('resume_stage') or '') in active_stages
                    if stage in active_stages or choice_stage == 'send_intent' or uncertain:
                        raise ValueError(f'ฉาก {index} ยังมีคำขอ Meta ที่กำลังทำหรือยังไม่ยืนยัน • ยังไม่เปลี่ยนผู้สร้างวิดีโอ')
            if job.get('long_video') and provider == 'meta_ai':
                from core.long_video import require_meta_landscape_available
                require_meta_landscape_available()
                from core.long_video import validate_landscape_image
                folder = self._folder(job_id).resolve()
                saved = list(dict.fromkeys(str(value) for value in
                    [*(job.get('generated_images') or []), *(job.get('partial_generated_images') or [])]))
                digests = dict(job.get('partial_image_sha256') or {})
                for position, relative in enumerate(saved, 1):
                    image = (folder / relative).resolve()
                    match = re.search(r'scene_(\d+)\.', Path(relative).name, re.I)
                    index = int(match.group(1)) if match else position
                    if not image.is_relative_to(folder) or not image.is_file():
                        raise ValueError(f'ภาพฉาก {index} ที่บันทึกไว้ไม่พร้อม • ยังไม่เปลี่ยนผู้สร้างวิดีโอ')
                    payload = image.read_bytes()
                    if digests.get(str(index)) and hashlib.sha256(payload).hexdigest() != digests[str(index)]:
                        raise ValueError(f'ภาพฉาก {index} ไม่ตรง Checkpoint เดิม • ยังไม่เปลี่ยนผู้สร้างวิดีโอ')
                    try:
                        validate_landscape_image(payload, require_16_9=True)
                    except (OSError, ValueError) as exc:
                        raise ValueError(f'ภาพฉาก {index} ยังไม่ใกล้เคียง 16:9 สำหรับ Meta • ยังไม่เปลี่ยนผู้สร้างวิดีโอ') from exc
            from core.media_audio import audio_choices
            choices = audio_choices(job.get('audio_choices'), provider)
            from core.storytelling import validate_settings
            telling = validate_settings(job.get('storytelling_options'), provider, choices,
                drama=job.get('job_type') == 'drama_episode', generated_music_options=job.get('generated_music_options'))
            if job.get('actor_dialogue'):
                from core.story_performance import validate_option
                validate_option(True, provider, choices, telling,
                                drama=job.get('job_type') == 'drama_episode', music_job=job)
            previous = str(job.get('video_generation_mode') or 'image_motion')
            if previous != provider:
                history = list(job.get('video_provider_history') or [])
                history.append({'from': previous, 'to': provider,
                    'at': datetime.now().isoformat(timespec='seconds'),
                    'revision': int(job.get('revision') or 0),
                    'kept_flow_scenes': len(dict(job.get('flow_clips') or {})),
                    'kept_meta_scenes': len(dict(job.get('meta_clips') or {}))})
                job['video_provider_history'] = history[-30:]
                job['video_generation_mode'] = provider
                if job.get('long_video'):
                    job['long_video'] = {**job['long_video'], 'video_generation_mode': provider}
                job['video_source_type'] = 'meta_ai_pending' if provider == 'meta_ai' else 'google_flow_pending'
                job['video_status'] = 'waiting_video'
                job['scene_pipeline_version'] = 0
                if provider == 'meta_ai':
                    from core.meta_prompt import CURRENT_META_PROMPT_VERSION
                    job['meta_prompt_version'] = CURRENT_META_PROMPT_VERSION
                if choices is not None:
                    job['audio_choices'] = choices
                if telling is not None:
                    job['storytelling_options'] = telling
                job['revision'] = int(job.get('revision') or 0) + 1
                job['updated_at'] = datetime.now().isoformat(timespec='seconds')
                store.write_unlocked(job)
            return job

    def save_pronunciation_notes(self, job_id, notes, expected_revision):
        """User corrections only; never invalidate paid voice or image checkpoints."""
        notes = validate_user_notes(notes)
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            job = store.read_unlocked()
            if int(job.get("revision") or 0) != int(expected_revision):
                raise ValueError("งานเปลี่ยนระหว่างแก้ไข กรุณาเปิดรายละเอียดใหม่ก่อนบันทึก")
            if voice_locked(job):
                raise ValueError("มีคำขอเสียงหรือไฟล์เสียงแล้ว ไม่แก้ทับงานที่จ่ายแล้ว")
            if job.get("status") in {"running", "recovering", "cancelled", "deleted"}:
                raise ValueError("ต้องหยุดงานก่อนแก้คำอ่าน และงานต้องไม่ถูกยกเลิก")
            job["user_pronunciation_notes"] = notes
            job["voice_review_issues"] = voice_review(job)["issues"]
            job["updated_at"] = datetime.now().isoformat(timespec="seconds")
            job["revision"] = int(job.get("revision") or 0) + 1
            store.write_unlocked(job)
            return job

    @staticmethod
    def _scene_prompt_overrides(job):
        overrides = job.get("scene_prompt_overrides", {})
        count = int(job.get("scene_count") or 0)
        if not isinstance(overrides, dict):
            raise ValueError("ข้อมูลคำสั่งภาพที่ผู้ใช้แก้ไขไม่ถูกต้อง")
        for key, value in overrides.items():
            if (not isinstance(key, str) or not re.fullmatch(r"[1-9][0-9]*", key)
                    or not 1 <= int(key) <= count or not isinstance(value, str)
                    or not value.strip() or len(value) > 12000):
                raise ValueError("ข้อมูลคำสั่งภาพที่ผู้ใช้แก้ไขไม่ถูกต้อง")
        return dict(overrides)

    @classmethod
    def _assert_scene_prompt_overrides(cls, job, prompts):
        for key, prompt in cls._scene_prompt_overrides(job).items():
            index = int(key) - 1
            if index >= len(prompts) or prompts[index] != prompt:
                raise ValueError(f"STORY_SCENE_PROMPT_STALE: ฉาก {key} มีคำสั่งภาพที่ผู้ใช้แก้ไขแล้ว ไม่รับข้อมูลเก่าทับ")

    @staticmethod
    def _scene_prompt_edit_has_media(folder, job, index):
        """Check only this scene's committed media and canonical local paths."""
        for field in ("flow_clips", "flow_fallback_clips", "story_image_fallbacks"):
            rows = job.get(field) or {}
            if not isinstance(rows, dict) or rows.get(str(index)):
                return True
        for field in ("generated_images", "partial_generated_images"):
            rows = job.get(field) or []
            if not isinstance(rows, list):
                return True
            for position, relative in enumerate(rows, 1):
                if not isinstance(relative, str):
                    return True
                name = Path(relative.replace("\\", "/")).name
                match = re.fullmatch(r"scene_0*([1-9][0-9]*)\.(?:png|jpe?g|webp)", name, re.I)
                if (match and int(match[1]) == index) or (not match and relative and (
                        len(rows) != int(job.get("scene_count") or 0) or position == index)):
                    return True
        for parent, prefix, suffixes in (
            (folder / "generated", "scene", r"png|jpe?g|webp"),
            (folder / "videos", "flow_scene", r"mp4|webm|mov|mkv|avi"),
            (folder / "videos", "local_motion_scene", r"mp4|webm|mov|mkv|avi"),
            (folder / "videos" / ".working", "flow_scene", r"mp4|webm|mov|mkv|avi"),
            (folder / "videos" / ".working", "local_motion_scene", r"mp4|webm|mov|mkv|avi"),
        ):
            if not parent.is_dir():
                continue
            pattern = re.compile(rf"{prefix}_0*{index}\.(?:{suffixes})(?:\.partial)?", re.I)
            if any(path.is_file() and pattern.fullmatch(path.name) for path in parent.iterdir()):
                return True
        return False

    def save_scene_prompt(self, job_id, index, prompt, expected_revision):
        """Save one explicit user edit without rerunning, clearing or invalidating work."""
        if type(index) is not int:
            raise ValueError("ลำดับฉากต้องเป็นจำนวนเต็ม")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000:
            raise ValueError("คำสั่งภาพต้องเป็นข้อความ 1–12000 ตัวอักษร")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("กรุณาเปิดรายละเอียดล่าสุดก่อนแก้คำสั่งภาพ")
        prompt = prompt.strip()
        folder = self._folder(job_id)
        store = self._manifest_store(folder / "job.json")
        with self._manifest_lock, store.locked():
            job = store.read_unlocked()
            if int(job.get("revision") or 0) != expected_revision:
                raise ValueError("งานเปลี่ยนระหว่างแก้ไข กรุณาเปิดรายละเอียดใหม่ก่อนบันทึก")
            count = int(job.get("scene_count") or 0)
            if not 1 <= index <= count:
                raise ValueError("ลำดับฉากไม่ถูกต้อง")
            if (str(job.get("status") or "").strip().lower() in {
                    "active", "running", "recovering", "cancelled", "canceled", "deleted",
                } or job.get("cancel_requested") or job.get("active") is True):
                raise ValueError("ต้องหยุดงานก่อนแก้คำสั่งภาพ และงานต้องไม่ถูกยกเลิก")
            audio = folder / "audio"
            has_audio = audio.is_dir() and any(path.is_file() and (
                path.suffix.lower() in {".mp3", ".wav", ".mp4", ".m4a", ".aac", ".ogg", ".flac"}
                or (path.name == "batch.json" and ".tts_chunks" in path.parts)
            ) for path in audio.rglob("*"))
            if voice_locked(job) or has_audio:
                raise ValueError("มีคำขอเสียงหรือไฟล์เสียงแล้ว ไม่แก้ภาพของงานที่จ่ายแล้ว")
            has_final = any(job.get(key) for key in ("video_path", "final_path", "final_video_path"))
            if not has_final:
                videos = folder / "videos"
                has_final = videos.is_dir() and any(path.is_file() and path.suffix.lower() in self.VIDEO_EXTENSIONS
                    and re.match(r"(?:story_short_complete|story_final|final(?:_with_audio)?)(?:\.|_)", path.name, re.I)
                    for path in videos.iterdir())
            if has_final or str(job.get("video_status") or "").lower() in {"ready", "complete", "completed"}:
                raise ValueError("มีวิดีโอ Final แล้ว ไม่แก้ภาพของงานที่สำเร็จ")
            if self._scene_prompt_edit_has_media(folder, job, index):
                raise ValueError(f"ฉาก {index} มีภาพหรือคลิปแล้ว จึงไม่แก้ทับคำสั่งภาพ")
            prompts = job.get("scene_prompts")
            if (not isinstance(prompts, list) or len(prompts) != count
                    or any(not isinstance(value, str) or not value.strip() for value in prompts)):
                raise ValueError("ต้องมีแผนคำสั่งภาพครบทุกฉากก่อนแก้ไข")
            if len(prompts[index - 1]) > 12000:
                raise ValueError("คำสั่งภาพเดิมยาวเกินขอบเขตที่บันทึกประวัติการแก้ไขได้")
            self._assert_scene_prompt_overrides(job, prompts)
            revised_prompts = list(prompts)
            revised_prompts[index - 1] = prompt
            revised_content = {**job, "scene_prompts": revised_prompts}
            # The automatic binding audit belongs to the original saved plan.
            # A reviewed edit has its own exact old/new revision history below.
            revised_content.pop("story_content_name_repair", None)
            validate_story_content(job, revised_content)
            if prompt == prompts[index - 1]:
                return job
            history = job.get("scene_prompt_edit_history", [])
            if not isinstance(history, list):
                raise ValueError("ประวัติแก้คำสั่งภาพไม่ถูกต้อง")
            now = datetime.now().isoformat(timespec="seconds")
            revision = expected_revision + 1
            overrides = self._scene_prompt_overrides(job)
            overrides[str(index)] = prompt
            if job.get("story_content_name_repair"):
                job["story_content_name_repair_history"] = job.pop("story_content_name_repair")
            job.update({
                "scene_prompts": revised_prompts, "scene_prompt_overrides": overrides,
                "scene_prompt_override_revision": revision,
                "scene_prompt_edit_history": history[-19:] + [{
                    "scene_index": index, "old_prompt": prompts[index - 1], "new_prompt": prompt,
                    "revision": revision, "at": now,
                }],
                "revision": revision, "updated_at": now,
            })
            store.write_unlocked(job)
            return job

    @staticmethod
    def _validated_analysis_checkpoint(job, value):
        """Validate reusable text and supply render-only defaults in memory.

        Optional export metadata must not turn a saved plan into another paid
        browser request. Never repair identities or rewrite scene descriptions.
        """
        if not isinstance(value, dict) or value.get("job_id") != job.get("id"):
            raise ValueError("ผลวิเคราะห์เดิมไม่ใช่ข้อมูลของ Job นี้")
        result = story_performance.validate_plan(job, copy.deepcopy(value))
        validate_film_plan(job, result)
        validate_creative_plan(job, result)
        from core.creative_brief import validate_brief
        validate_brief(job, result)
        count = int(job.get("scene_count") or 0)
        if count < 1:
            raise ValueError("จำนวนฉากของงานเดิมไม่ถูกต้อง")
        for key in ("video_title", "narration_script"):
            if key == 'narration_script' and storytelling.visual_only(job):
                continue
            if not isinstance(result.get(key), str) or not result[key].strip():
                raise ValueError("ผลวิเคราะห์เดิมยังไม่มีชื่อคลิปหรือบทพากย์")
        for key in ("scene_prompts", "scene_narrations"):
            values = result.get(key)
            if (not isinstance(values, list) or len(values) != count
                    or any(not isinstance(item, str) or not item.strip() for item in values)):
                raise ValueError(f"ผลวิเคราะห์เดิมมี {key} ไม่ครบ {count} ฉาก")
        # These defaults already exist at final-result/render boundaries. They
        # are package values only; the original checkpoint remains untouched.
        if not result.get("video_description"):
            result["video_description"] = result["video_title"]
        if result.get("visual_bible") is None or result.get("visual_bible") == "":
            result["visual_bible"] = {}
        if result.get("scene_durations") is None or result.get("scene_durations") == []:
            result["scene_durations"] = [5.0] * count
        if not isinstance(result["scene_durations"], list) or len(result["scene_durations"]) != count:
            raise ValueError("ผลวิเคราะห์เดิมมีระยะเวลาฉากไม่ครบ")
        validate_story_content(job, result)
        from core.product_editorial import assert_approved
        assert_approved(job, result)
        return result

    def load_analysis_checkpoint(self, job_id):
        """Read one validated saved plan without changing any project file."""
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            return self._load_analysis_checkpoint_locked(self.get(job_id))

    def _load_analysis_checkpoint_locked(self, job):
        path = self._folder(job["id"]) / "prompts" / "ai_analysis_checkpoint.json"
        overrides = self._scene_prompt_overrides(job)
        try:
            if path.is_file():
                # A corrupt/wrong-job explicit checkpoint is not permission to
                # fall back to another plan, Chrome cache, or a new master.
                value = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, dict) or value.get("job_id") != job["id"]:
                    raise ValueError("ไฟล์ผลวิเคราะห์ไม่ตรงกับ Job")
            else:
                fields = (
                    "product_film_plan",
                    "cover",
                    "video_title", "video_description", "narration_script", "visual_bible",
                    "pronunciation_notes", "scene_prompts", "scene_narrations", "scene_durations",
                    "story_entities", "scene_entities", "story_content_name_repair", "warnings", "creative_brief",
                    "episode_title", "episode_summary", "next_episode_hook", "continuity_state",
                    "dialogue_turns", "speaker_corrections", "character_bible", "scene_dialogue_turns",
                )
                has_plan = (bool(job.get("scene_prompts")) or bool(job.get("narration_script"))
                            or bool(overrides))
                if not has_plan:
                    return None
                value = {key: copy.deepcopy(job[key]) for key in fields if key in job}
                if job.get('meta_prompt_version') == 5 and 'flow_shot_prompts' in job:
                    value['flow_shot_prompts'] = copy.deepcopy(job['flow_shot_prompts'])
                value["job_id"] = job["id"]
            if overrides:
                prompts = self._strings(value.get("scene_prompts"))
                if len(prompts) != int(job.get("scene_count") or 0):
                    raise ValueError("ผลวิเคราะห์เดิมมีแผนฉากไม่ครบ")
                for key, prompt in overrides.items():
                    prompts[int(key) - 1] = prompt
                value = {**value, "scene_prompts": prompts}
                value.pop("story_content_name_repair", None)
            return self._validated_analysis_checkpoint(job, value)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"STORY_ANALYSIS_CHECKPOINT_REVIEW • ตรวจแผนเดิมก่อนทำต่อ • {exc}") from exc

    def plugin_request(self, job_id):
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            return self._plugin_request_locked(job_id)

    def record_scene_recovery(self, body):
        from core.story_prompt_recovery import record_recovery
        job_id = str(body.get('job_id') or '')
        with self._manifest_lock:
            return record_recovery(self._folder(job_id), self.get(job_id), body)

    def _plugin_request_locked(self, job_id):
        folder = self._folder(job_id)
        job = self.get(job_id)
        from core.ai_web_resume import ai_web_resume_target
        resume_target = ai_web_resume_target(folder, job)
        if not (resume_target and resume_target.get('stage') == 'analysis' and (folder / 'ai_request.json').is_file()):
            self._write_request(folder, job)
        request = json.loads((folder / "ai_request.json").read_text(encoding="utf-8"))
        prompt = (folder / request["prompt_file"]).read_text(encoding="utf-8")
        checkpoints = [
            str(path.relative_to(folder))
            for path in sorted((folder / "generated").glob("scene_*.png"))
            if path.is_file()
        ]
        analysis_checkpoint = self._load_analysis_checkpoint_locked(job)
        overrides = self._scene_prompt_overrides(job)
        package = {
            "mode": "story",
            "browser_recovery": {"version": 1, "check_after_ms": 60000,
                                 "confirmed_failure": "refresh_retry_fresh",
                                 "image_post_refresh_redo": {"version": 1,
                                     "stable_check_ms": 30000, "min_stable_samples": 3}},
            "scene_repair": {"enabled": True, "max_rounds": 2},
            "job": job,
            "request": request,
            "prompt": prompt,
            "checkpoint_images": checkpoints,
            "analysis_checkpoint": analysis_checkpoint,
            "ai_resume": resume_target,
        }
        from core.product_editorial import enabled as editorial_enabled
        if editorial_enabled(job):
            package['product_editorial_state'] = copy.deepcopy(job.get('product_editorial_state') or {})
            state = package['product_editorial_state']
            if state.get('status') == 'needs_repair' and state.get('phase') == 'sending':
                package['ai_resume'] = {'required': True, 'stage': 'analysis', 'provider': state['provider'],
                                       'request': state['request'], 'conversation_url': state['conversation_url']}
                package['reuse_analysis'] = True
        if (job.get('long_video') or {}).get('version') == 2:
            package['long_video_plan'] = self.long_video_plan(job_id)
        if analysis_checkpoint and not checkpoints:
            package["image_receipt_pre_send_proof"] = legacy_first_image_receipt_proof(
                folder, job_id, str(job.get("image_ai_provider") or "chatgpt"))
        if overrides:
            package.update(reuse_analysis=True, scene_prompt_overrides=overrides,
                           scene_prompt_override_revision=job.get("scene_prompt_override_revision"))
        package['image_receipt_result_proof'] = completed_image_result_proofs(
            folder, job_id, str(job.get('image_ai_provider') or 'chatgpt'))
        return package

    def long_video_plan(self, job_id):
        """Read the durable ten-scene plan without opening a provider tab."""
        job = self.get(job_id)
        if (job.get('long_video') or {}).get('version') != 2:
            return None
        store = self._manifest_store(self._folder(job_id) / 'prompts' / 'long_video_plan.json')
        plan = store.read(default=None)
        if plan is None:
            return {'version': 2, 'job_id': job_id, 'outline': None, 'chapters': []}
        if not isinstance(plan, dict) or plan.get('version') != 2 or plan.get('job_id') != job_id:
            raise ValueError('แผนคลิปยาวที่บันทึกไว้ไม่ตรงงาน')
        from core.long_video import validate_outline, validate_chapter, chapter_ranges
        count = int(job['scene_count'])
        if plan.get('outline') is not None:
            validate_outline(plan['outline'], job_id, count)
        chapters = plan.get('chapters')
        if not isinstance(chapters, list):
            raise ValueError('รายการชุดภาพคลิปยาวไม่ถูกต้อง')
        for index, chapter in enumerate(chapters, 1):
            validate_chapter(chapter, job_id, count, index)
        pending = plan.get('pending_request')
        if pending is not None:
            self._validate_long_video_pending_request(pending, job_id, plan)
            if pending['provider'] != str(job.get('image_ai_provider') or 'chatgpt') \
                    or (pending['stage'] == 'chapter' and pending['chapter_index'] > len(chapter_ranges(count))):
                raise ValueError('คำขอคลิปยาวที่ค้างไม่ตรงงาน')
        return plan

    @staticmethod
    def _validate_long_video_pending_request(pending, job_id, plan):
        if not isinstance(pending, dict) or set(pending) != {'stage', 'chapter_index', 'provider', 'request'}:
            raise ValueError('คำขอคลิปยาวที่ค้างไม่ถูกต้อง')
        stage, index = pending['stage'], pending['chapter_index']
        if pending['provider'] not in {'chatgpt', 'gemini'} or not isinstance(pending['request'], str) \
                or not pending['request'].strip() or len(pending['request']) > 100000 \
                or job_id not in pending['request']:
            raise ValueError('คำขอคลิปยาวที่ค้างไม่ตรงงาน')
        chapters = plan.get('chapters') or []
        if stage == 'outline' and index == 0 and plan.get('outline') is None:
            return pending
        if stage == 'chapter' and type(index) is int and index == len(chapters) + 1 \
                and plan.get('outline') is not None:
            return pending
        raise ValueError('ขั้นคำขอคลิปยาวที่ค้างไม่ตรง Checkpoint')

    def save_long_video_plan_step(self, job_id, *, outline=None, chapter=None, chapter_index=0,
                                  pending_request=None, clear_pending=False):
        """Append only an owned, validated plan step; a replay must match exactly."""
        from core.long_video import validate_outline, validate_chapter, chapter_ranges
        folder = self._folder(job_id)
        store = self._manifest_store(folder / 'prompts' / 'long_video_plan.json')
        with self._manifest_lock, store.locked():
            job = self.get(job_id)
            if (job.get('long_video') or {}).get('version') != 2 or job.get('cancel_requested'):
                raise ValueError('งานนี้ไม่ได้เปิดแผนคลิปยาวแบบชุดภาพ')
            count = int(job['scene_count'])
            saved = store.read_unlocked(default={'version': 2, 'job_id': job_id, 'outline': None, 'chapters': []})
            if not isinstance(saved, dict) or saved.get('job_id') != job_id or saved.get('version') != 2:
                raise ValueError('แผนคลิปยาวที่บันทึกไว้ไม่ตรงงาน')
            if pending_request is not None:
                if not isinstance(pending_request, dict) \
                        or pending_request.get('provider') != str(job.get('image_ai_provider') or 'chatgpt'):
                    raise ValueError('ผู้ให้บริการคำขอคลิปยาวไม่ตรงงาน')
                saved['pending_request'] = self._validate_long_video_pending_request(pending_request, job_id, saved)
                if saved['pending_request']['stage'] == 'chapter' \
                        and saved['pending_request']['chapter_index'] > len(chapter_ranges(count)):
                    raise ValueError('ชุดคำขอคลิปยาวเกินจำนวนฉาก')
            if clear_pending and outline is None and chapter is None:
                raise ValueError('ล้างคำขอที่ค้างได้หลังบันทึกโครงเรื่องหรือบทชุดนั้นเท่านั้น')
            if outline is not None:
                incoming = validate_outline(outline, job_id, count)
                if saved.get('outline') is not None and saved['outline'] != incoming:
                    raise ValueError('โครงเรื่องเดิมเปลี่ยนแล้ว • ไม่เขียนทับ')
                if clear_pending and (saved.get('pending_request') or {}).get('stage') not in {None, 'outline'}:
                    raise ValueError('คำขอที่ค้างไม่ใช่โครงเรื่องนี้')
                saved['outline'] = incoming
            if chapter is not None:
                index = int(chapter_index)
                incoming = validate_chapter(chapter, job_id, count, index)
                if saved.get('outline') is None:
                    raise ValueError('ต้องบันทึกโครงเรื่องก่อนชุดภาพ')
                known_ids = {entity['id'] for entity in saved['outline']['story_entities']}
                if any(entity_id not in known_ids for scene in incoming['scene_entities'] for entity_id in scene):
                    raise ValueError('บทชุดภาพอ้างตัวละครที่ไม่มีในโครงเรื่อง')
                chapters = saved.get('chapters')
                if not isinstance(chapters, list) or index > len(chapters) + 1 or index > len(chapter_ranges(count)):
                    raise ValueError('ชุดภาพต้องบันทึกตามลำดับ')
                if clear_pending and saved.get('pending_request') \
                        and (saved['pending_request']['stage'] != 'chapter'
                             or saved['pending_request']['chapter_index'] != index):
                    raise ValueError('คำขอที่ค้างไม่ใช่บทชุดนี้')
                if index <= len(chapters):
                    if chapters[index - 1] != incoming:
                        raise ValueError('บทชุดภาพเดิมเปลี่ยนแล้ว • ไม่เขียนทับ')
                else:
                    chapters.append(incoming)
            if clear_pending:
                saved.pop('pending_request', None)
            store.write_unlocked(saved)
            return copy.deepcopy(saved)

    def save_analysis_checkpoint(self, job_id, result, editorial_request_id=''):
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            return self._save_analysis_checkpoint_locked(job_id, result, editorial_request_id)

    def _save_analysis_checkpoint_locked(self, job_id, result, editorial_request_id=''):
        """Persist validated AI text before the slower image-generation stage.

        Browser local storage is not a durable project record.  Saving this
        compact checkpoint means a provider/tab failure can continue with the
        same title, narration and scene plan without asking the model again.
        """
        folder = self._folder(job_id)
        manifest = self.get(job_id)
        if manifest.get("cancel_requested") or manifest.get("status") == "cancelled":
            raise ValueError("Story Job นี้ถูกผู้ใช้ยกเลิกแล้ว")
        result = story_performance.validate_plan(manifest, dict(result or {}))
        from core.speech_delivery import validate_speakers
        validate_speakers(manifest, result)
        from core.creative_brief import validate_brief
        creative_brief = validate_brief(manifest, result)
        if manifest.get('auto_cast_pending'):
            from core.drama_series import generated_drama_cast
            result['character_bible'] = generated_drama_cast(result.get('character_bible'))
        result = _lock_narrated_drama_cast(manifest, result)
        validate_film_plan(manifest, result)
        validate_creative_plan(manifest, result)
        count = int(manifest.get("scene_count") or 0)
        prompts = self._strings(result.get("scene_prompts"))
        narrations = self._strings(result.get("scene_narrations"))
        if len(prompts) != count:
            raise ValueError(f"AI Web ต้องส่ง scene_prompts จำนวน {count} รายการ")
        if len(narrations) != count:
            raise ValueError(f"AI Web ต้องส่ง scene_narrations จำนวน {count} รายการ")
        self._assert_scene_prompt_overrides(manifest, prompts)
        title = str(result.get("video_title") or result.get("title") or "").strip()
        narration = str(result.get("narration_script") or "").strip()
        if not title or (not narration and not storytelling.visual_only(manifest)):
            raise ValueError("ผลวิเคราะห์ Story ยังไม่มีชื่อคลิปหรือบทพากย์")
        content_identity = validate_story_content(manifest, result)
        allowed_keys = {
            "product_editorial_review",
            "creative_brief",
            "product_film_plan",
            "character_bible",
            "cover",
            "job_id", "video_title", "video_description", "episode_title",
            "episode_summary", "next_episode_hook", "narration_script",
            "visual_bible", "continuity_state", "dialogue_turns",
            "scene_narrations", "scene_prompts", "scene_durations", "scene_dialogue_turns", "warnings",
            "speaker_corrections", "pronunciation_notes", "flow_shot_prompts",
        }
        checkpoint = {key: value for key, value in result.items() if key in allowed_keys}
        if "cover" in result:
            checkpoint["cover"] = normalize_cover(result["cover"])
        checkpoint.update({
            "job_id": str(job_id),
            "video_title": title,
            "narration_script": narration,
            "scene_prompts": prompts,
            "scene_narrations": narrations,
        })
        checkpoint.update(content_identity)
        from core.product_editorial import accept, enabled as editorial_enabled
        if not accept(manifest, checkpoint, editorial_request_id):
            self._save(manifest)
            return manifest
        # Use the same required-plan validation as both resume entry points;
        # optional export defaults are deliberately not written to this file.
        self._validated_analysis_checkpoint(manifest, checkpoint)
        target = folder / "prompts" / "ai_analysis_checkpoint.json"
        if not self._scene_prompt_overrides(manifest):
            temporary = target.with_suffix(".json.partial")
            temporary.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(target)
        manifest.update({
            "analysis_status": "ready",
            "cover": normalize_cover(result.get("cover") or manifest.get("cover")),
            "analysis_provider": str(result.get("analysis_provider") or manifest.get("image_ai_provider") or "chatgpt"),
            "video_title": title,
            "video_description": str(result.get("video_description") or "").strip(),
            "narration_script": narration,
            "visual_bible": result.get("visual_bible") or {},
            "pronunciation_notes": result.get("pronunciation_notes") if isinstance(result.get("pronunciation_notes"), dict) else {},
            "scene_prompts": prompts,
            "scene_narrations": narrations,
            "scene_durations": list(result.get("scene_durations") or []),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        if short_film_ad(manifest):
            manifest['product_film_plan'] = copy.deepcopy(result['product_film_plan'])
        if manifest.get('meta_prompt_version') == 5:
            motion = result.get('flow_shot_prompts')
            if (isinstance(motion, list) and len(motion) == count
                    and all(isinstance(value, str) and value.strip() for value in motion)):
                manifest['flow_shot_prompts'] = copy.deepcopy(motion)
        if creative_brief is not None:
            manifest['creative_brief'] = creative_brief
        if story_performance.enabled(manifest):
            manifest.update({key: result[key] for key in ('character_bible', 'scene_dialogue_turns', 'dialogue_turns')})
        elif manifest.get('auto_cast_pending'):
            manifest['character_bible'] = copy.deepcopy(result['character_bible'])
        manifest["voice_review_issues"] = voice_review(manifest)["issues"]
        manifest.update(content_identity)
        if editorial_enabled(manifest):
            for key in ('product_editorial_review', 'dialogue_turns', 'scene_dialogue_turns'):
                if key in checkpoint:
                    manifest[key] = copy.deepcopy(checkpoint[key])
        self._save(manifest)
        return manifest

    def mark_editorial_sending(self, job_id, request_id, provider, conversation_url):
        from core.product_editorial import mark_sending, response
        store = self._manifest_store(self._folder(job_id) / 'job.json')
        with self._manifest_lock, store.locked():
            job = self.get(job_id)
            if job.get('cancel_requested') or job.get('status') == 'cancelled':
                raise ValueError('งานถูกยกเลิกแล้ว')
            mark_sending(job, request_id, provider, conversation_url)
            self._save(job)
            return response(job)

    def set_image_ai_provider(self, job_id, provider, reason=""):
        provider = self._image_ai_provider(provider)
        manifest = self.get(job_id)
        previous = self._image_ai_provider(manifest.get("image_ai_provider") or "chatgpt")
        if previous != provider:
            history = list(manifest.get("provider_failover_history") or [])[-9:]
            history.append({
                "from": previous,
                "to": provider,
                "reason": str(reason or "")[:500],
                "at": datetime.now().isoformat(timespec="seconds"),
            })
            manifest["provider_failover_history"] = history
            manifest["provider_failover_count"] = int(manifest.get("provider_failover_count") or 0) + 1
        manifest.update({
            "image_ai_provider": provider,
            "ai_web_model": normalize_ai_web_model(provider, manifest.get("ai_web_model")),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save(manifest)
        return manifest

    def save_refused_image_fallback(self, job_id, index, source_index, response_excerpt, receipt_proof=None):
        """Reuse an acknowledged illustration locally; never retry a refused AI request."""
        folder = self._folder(job_id)
        store = self._manifest_store(folder / "job.json")
        with self._manifest_lock, store.locked():
            job = self.get(job_id)
            if job.get("cancel_requested") or job.get("status") == "cancelled":
                raise ValueError("Story Job นี้ถูกผู้ใช้ยกเลิกแล้ว")
            if job.get("video_generation_mode") != "image_motion" or job.get("job_type") == "drama_episode":
                raise ValueError("การใช้ภาพสำรองนี้รองรับเฉพาะ Story โหมดภาพเคลื่อนไหวในโปรแกรม")
            index, source_index = int(index), int(source_index)
            if not 1 <= source_index < index <= int(job.get("scene_count") or 0):
                raise ValueError("ลำดับภาพสำรองไม่ถูกต้อง หรือยังไม่มีภาพสำเร็จก่อนหน้า")
            excerpt = str(response_excerpt or "").strip()[:1200]
            legacy_refusal_proof = (isinstance(receipt_proof, dict)
                and set(receipt_proof) == {'original_run_id', 'review_revision', 'created_at'}
                and isinstance(receipt_proof.get('original_run_id'), str)
                and bool(re.fullmatch(r'RUN-[A-Za-z0-9_-]{1,96}', receipt_proof['original_run_id']))
                and type(receipt_proof.get('review_revision')) is int and receipt_proof['review_revision'] >= 0
                and type(receipt_proof.get('created_at')) in {int, float}
                and 0 < receipt_proof['created_at'] <= time.time() * 1000 + 60000)
            if not excerpt and not legacy_refusal_proof:
                raise ValueError("ไม่มีหลักฐานคำตอบปฏิเสธภาพ")
            fallbacks = dict(job.get("story_image_fallbacks") or {})
            if str(source_index) in fallbacks:
                raise ValueError("ห้ามใช้ภาพสำรองเป็นต้นทางซ้ำต่อกัน")
            source = folder / "generated" / f"scene_{source_index:02d}.png"
            target = folder / "generated" / f"scene_{index:02d}.png"
            checkpoints = {str(p).replace('\\', '/') for p in job.get("partial_generated_images", [])}
            if source.relative_to(folder).as_posix() not in checkpoints or not source.is_file():
                raise ValueError("ภาพต้นทางยังไม่ได้บันทึกสำเร็จ")
            payload = source.read_bytes()
            with Image.open(BytesIO(payload)) as image:
                image.verify()
            digest = hashlib.sha256(payload).hexdigest()
            prompt_digest = hashlib.sha256(str((job.get("scene_prompts") or [])[index - 1]).encode('utf-8')).hexdigest()
            previous = fallbacks.get(str(index))
            if previous:
                if (previous.get("source_index") != source_index or previous.get("image_sha256") != digest
                        or previous.get("scene_prompt_sha256") != prompt_digest
                        or previous.get("provider") != job.get("image_ai_provider")):
                    raise ValueError("ข้อมูลภาพสำรองไม่ตรงกับจุดบันทึกเดิม")
            elif target.exists():
                raise ValueError("ฉากนี้มีไฟล์ภาพแล้ว • ไม่เขียนทับภาพที่มีอยู่")
            metadata = previous or {"scene_index": index, "source_index": source_index,
                "reason": "STORY_IMAGE_REFUSED", "policy": "reuse_saved_local_v1",
                "image_sha256": digest, "response_excerpt": excerpt,
                "response_excerpt_available": bool(excerpt),
                "provider": job.get("image_ai_provider"), "scene_prompt_sha256": prompt_digest,
                "scene_prompt_override_revision": job.get("scene_prompt_override_revision", 0),
                "receipt_proof": {key: (receipt_proof or {}).get(key) for key in ('original_run_id', 'review_revision', 'created_at')},
                "created_at": datetime.now().isoformat(timespec="seconds"), "status": "pending"}
            # Persist intent first. Resume may finish this copy, never generate a replacement.
            fallbacks[str(index)] = metadata
            job["story_image_fallbacks"] = fallbacks
            self._save(job)
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError("ไฟล์ภาพสำรองเปลี่ยนไป • หยุดเพื่อไม่เขียนทับ")
            if not target.exists():
                temporary = target.with_suffix('.png.fallback.partial')
                temporary.write_bytes(payload)
                temporary.replace(target)
            metadata["status"] = "ready"
            job.update(partial_generated_images=[str(p.relative_to(folder)) for p in sorted((folder / "generated").glob("scene_*.png")) if p.is_file()],
                       story_image_fallback_count=len(fallbacks),
                       image_fallback_notice=f"ใช้ภาพสำเร็จก่อนหน้าประกอบ {len(fallbacks)} ฉาก • ไม่ได้สร้างภาพใหม่ในฉากที่ถูกปฏิเสธ")
            job["partial_image_count"] = len(job["partial_generated_images"])
            if (job.get("long_video") or {}).get("version") == 2:
                digests = dict(job.get("partial_image_sha256") or {})
                digests[str(index)] = digest
                job["partial_image_sha256"] = digests
            self._save(job)
            return {"ok": True, "image": "data:image/png;base64," + base64.b64encode(payload).decode("ascii"), "metadata": metadata}

    def save_partial_image(self, job_id, index, encoded):
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            return self._save_partial_image_locked(job_id, index, encoded)

    def _save_partial_image_locked(self, job_id, index, encoded):
        folder = self._folder(job_id)
        manifest = self.get(job_id)
        from core.product_editorial import assert_approved
        assert_approved(manifest)
        if manifest.get("cancel_requested") or manifest.get("status") == "cancelled":
            raise ValueError("Story Job นี้ถูกผู้ใช้ยกเลิกแล้ว")
        index = int(index or 0)
        count = int(manifest.get("scene_count") or 0)
        if str(index) in dict(manifest.get("story_image_fallbacks") or {}):
            raise ValueError("ฉากนี้เป็นภาพสำรองที่บันทึกไว้ • ห้ามเขียนทับด้วยผลภาพใหม่")
        if index < 1 or index > count:
            raise ValueError("ลำดับรูปฉากไม่ถูกต้อง")
        raw = str(encoded or "")
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        try:
            payload = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("ข้อมูลรูปฉากไม่ถูกต้อง") from None
        if len(payload) < 100:
            raise ValueError("ข้อมูลรูปฉากว่างเปล่า")
        if manifest.get('long_video'):
            from core.long_video import validate_landscape_image
            validate_landscape_image(payload, require_16_9=manifest.get('video_generation_mode') == 'meta_ai')
        if self._matches_source_image(payload, folder, manifest.get("source_images") or []):
            raise ValueError("AI Web ส่งรูปอ้างอิงเดิมกลับมา ไม่ใช่รูปฉากที่สร้างใหม่")
        target = folder / "generated" / f"scene_{index:02d}.png"
        digest = hashlib.sha256(payload).hexdigest()
        digests = dict(manifest.get("partial_image_sha256") or {})
        # A delayed upload from a retired browser attempt must not replace a
        # saved scene. Explicit discard remains the only replacement workflow.
        if target.is_file():
            if target.read_bytes() != payload or (digests.get(str(index)) and digests[str(index)] != digest):
                raise ValueError(f"ภาพฉาก {index} เปลี่ยนจาก Checkpoint เดิม • ต้องลบจุดบันทึกฉากนี้ก่อน")
        if any(entry.get("source_index") == index for entry in dict(manifest.get("story_image_fallbacks") or {}).values()):
            if target.is_file() and target.read_bytes() == payload:
                return manifest
            raise ValueError("ภาพนี้เป็นต้นทางภาพสำรองแล้ว • ไม่เขียนทับ Checkpoint")
        temporary = target.with_suffix(".png.partial")
        temporary.write_bytes(payload)
        temporary.replace(target)
        checkpoints = [str(path.relative_to(folder)) for path in sorted((folder / "generated").glob("scene_*.png")) if path.is_file()]
        manifest.update({
            "partial_generated_images": checkpoints,
            "partial_image_count": len(checkpoints),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        if (manifest.get("long_video") or {}).get("version") == 2:
            digests[str(index)] = digest
            manifest["partial_image_sha256"] = digests
        self._save(manifest)
        return manifest

    def discard_partial_image(self, job_id, index, reason=""):
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            return self._discard_partial_image_locked(job_id, index, reason)

    def _discard_partial_image_locked(self, job_id, index, reason=""):
        """Remove one invalid checkpoint while preserving the rest of the Job."""
        folder = self._folder(job_id)
        manifest = self.get(job_id)
        index = int(index or 0)
        count = int(manifest.get("scene_count") or 0)
        fallback_map = dict(manifest.get("story_image_fallbacks") or {})
        if str(index) in fallback_map or any(entry.get("source_index") == index for entry in fallback_map.values()):
            raise ValueError("ภาพนี้มีจุดบันทึกภาพสำรองอ้างอิงอยู่ • ไม่ลบไฟล์")
        if index < 1 or index > count:
            raise ValueError("ลำดับรูปฉากไม่ถูกต้อง")
        target = folder / "generated" / f"scene_{index:02d}.png"
        target.unlink(missing_ok=True)
        checkpoints = [str(path.relative_to(folder)) for path in sorted((folder / "generated").glob("scene_*.png")) if path.is_file()]
        manifest.update({
            "partial_generated_images": checkpoints,
            "partial_image_count": len(checkpoints),
            "last_checkpoint_error": str(reason or "ลบ checkpoint ที่ไม่ผ่านการตรวจ")[:1000],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        if (manifest.get("long_video") or {}).get("version") == 2:
            digests = dict(manifest.get("partial_image_sha256") or {})
            digests.pop(str(index), None)
            manifest["partial_image_sha256"] = digests
        self._save(manifest)
        return manifest

    @staticmethod
    def _matches_source_image(payload, folder, source_images):
        """Detect a re-encoded upload preview that was mistaken for AI output."""
        try:
            with Image.open(BytesIO(payload)) as opened:
                candidate = ImageOps.exif_transpose(opened).convert("RGB")
                candidate_ratio = candidate.width / max(1, candidate.height)
                candidate = candidate.resize((64, 64), Image.Resampling.LANCZOS)
        except Exception as exc:
            raise ValueError("ไฟล์รูปฉากเปิดอ่านไม่ได้") from exc
        for relative in source_images:
            source = folder / str(relative)
            if not source.is_file():
                continue
            try:
                with Image.open(source) as opened:
                    reference = ImageOps.exif_transpose(opened).convert("RGB")
                    reference_ratio = reference.width / max(1, reference.height)
                    if abs(candidate_ratio - reference_ratio) > 0.01:
                        continue
                    reference = reference.resize((64, 64), Image.Resampling.LANCZOS)
                difference = ImageChops.difference(candidate, reference)
                mean_difference = sum(ImageStat.Stat(difference).mean) / 3
                if mean_difference <= 1.5:
                    return True
            except OSError:
                continue
        return False

    def apply_ai_result(self, result):
        job_id = str((result or {}).get("job_id") or "")
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            return self._apply_ai_result_locked(result)

    def _apply_ai_result_locked(self, result):
        result = dict(result or {})
        job_id = str(result.get("job_id") or "")
        folder = self._folder(job_id)
        manifest = self.get(job_id)
        from core.product_editorial import assert_approved, enabled as editorial_enabled
        assert_approved(manifest, result)
        if manifest.get("cancel_requested") or manifest.get("status") == "cancelled":
            raise ValueError("Story Job นี้ถูกผู้ใช้ยกเลิกแล้ว")
        count = int(manifest["scene_count"])
        result = story_performance.validate_plan(manifest, result)
        from core.speech_delivery import validate_speakers
        validate_speakers(manifest, result)
        from core.creative_brief import validate_brief
        creative_brief = validate_brief(manifest, result)
        if manifest.get('auto_cast_pending'):
            from core.drama_series import generated_drama_cast
            result['character_bible'] = generated_drama_cast(result.get('character_bible') or manifest.get('character_bible'))
        result = _lock_narrated_drama_cast(manifest, result)
        if story_performance.enabled(manifest):
            manifest.update({key: result[key] for key in ('character_bible', 'scene_dialogue_turns')})
        elif manifest.get('auto_cast_pending'):
            manifest['character_bible'] = copy.deepcopy(result['character_bible'])
        prompts = self._strings(result.get("scene_prompts"))
        narrations = self._strings(result.get("scene_narrations"))
        images = list(result.get("generated_images") or [])
        compact_images = ((manifest.get("long_video") or {}).get("version") == 2
                          and result.get("image_checkpoint_mode") == "saved_scene_files_v1")
        if len(prompts) != count:
            raise ValueError(f"ChatGPT ต้องส่ง scene_prompts จำนวน {count} รายการ")
        if compact_images and images:
            raise ValueError("ผลคลิปยาวแบบ Checkpoint ห้ามส่งรูปซ้ำในผลรวม")
        if not compact_images and len(images) != count:
            raise ValueError(f"ChatGPT ต้องสร้างรูปเรื่องเล่าจำนวน {count} รูป")
        if narrations and len(narrations) != count:
            raise ValueError(f"scene_narrations ต้องมี {count} รายการ")
        self._assert_scene_prompt_overrides(manifest, prompts)
        title = str(result.get("video_title") or result.get("title") or manifest.get("topic") or "เรื่องเล่า Shorts").strip()
        description = str(result.get("video_description") or result.get("description") or "").strip()
        post_hashtags = ""
        if (manifest.get('long_video') or {}).get('version') == 2:
            plan = self.long_video_plan(job_id)
            outline = plan.get('outline') or {}
            if outline:
                from core.post_copy import long_video_post_copy
                description, post_hashtags = long_video_post_copy(outline, manifest.get('topic'))
        narration = str(result.get("narration_script") or "").strip()
        if not narration and narrations and not storytelling.visual_only(manifest):
            narration = " ".join(narrations)
        if not narration and not storytelling.visual_only(manifest):
            raise ValueError("ChatGPT ไม่ได้ส่งบทพากย์เรื่องเล่า")
        content_identity = validate_story_content(manifest, result)
        narration_before_cta = narration
        validate_film_plan(manifest, result)
        validate_creative_plan(manifest, result)
        if editorial_enabled(manifest) or manifest.get('storytelling_options') or manifest.get('flow_smoke_test') or manifest.get('cast_creation') or story_performance.enabled(manifest) or authored_product_script(manifest):
            cta_added = False
        else:
            narration, narrations, cta_added = self._ensure_engagement_cta(narration, narrations, manifest.get("topic"))
        dialogue_turns = []
        speaker_corrections = []
        character_names = [
            str(character.get("name") or "").strip()
            for character in (manifest.get("character_bible") or [])
            if isinstance(character, dict) and str(character.get("name") or "").strip()
        ]
        for raw_turn in list(result.get("dialogue_turns") or [])[:120]:
            if not isinstance(raw_turn, dict):
                continue
            raw_speaker = str(raw_turn.get("speaker") or "ผู้บรรยาย")
            speaker, correction = self._normalise_dialogue_speaker(raw_speaker, character_names)
            if manifest.get("job_type") != "drama_episode":
                correction = None
            if correction:
                speaker_corrections.append(correction)
            text = clean_dialogue_turn_text(raw_turn, character_names)
            if not text:
                continue
            try:
                pause_after = max(0.2, min(2.0, float(raw_turn.get("pause_after") or 0.35)))
            except (TypeError, ValueError):
                pause_after = 0.35
            dialogue_turns.append({
                "speaker": speaker,
                "text": text,
                "emotion": "normal",
                "pause_after": pause_after,
            })
        if cta_added and dialogue_turns:
            cta_text = narration[len(narration_before_cta):].strip()
            if cta_text:
                dialogue_turns.append({"speaker": "ผู้บรรยาย", "text": cta_text, "emotion": "normal", "pause_after": 0.4})
        if story_performance.enabled(manifest):
            dialogue_turns = result['dialogue_turns']
        if manifest.get("job_type") == "drama_episode" and dialogue_turns:
            narration = spoken_script_for_job({
                "job_type": "drama_episode",
                "character_bible": manifest.get("character_bible") or [],
                "dialogue_turns": dialogue_turns,
            })
        fallback_map = dict(manifest.get("story_image_fallbacks") or {})
        reported_fallbacks = result.get("story_image_fallbacks") or {}
        if reported_fallbacks != fallback_map:
            raise ValueError("หลักฐานภาพสำรองไม่ตรงกับโปรแกรม • ไม่เขียนทับภาพเดิม")
        if fallback_map and not compact_images:
            if manifest.get("video_generation_mode") != "image_motion" or manifest.get("job_type") == "drama_episode":
                raise ValueError("ภาพสำรองใช้ประกอบในโปรแกรมเท่านั้น ห้ามส่งต่อ Flow")
            # Validate every payload BEFORE writing any scene, preserving all successful files.
            for number, encoded in enumerate(images, 1):
                raw = str(encoded or "").split(',', 1)[-1]
                try:
                    incoming = base64.b64decode(raw, validate=True)
                except (ValueError, binascii.Error):
                    raise ValueError("ข้อมูลภาพฉากไม่ถูกต้อง") from None
                current = folder / 'generated' / f'scene_{number:02d}.png'
                if current.is_file() and current.read_bytes() != incoming:
                    raise ValueError(f"ภาพฉาก {number} ไม่ตรงกับ Checkpoint เดิม")
                metadata = fallback_map.get(str(number))
                if metadata and (metadata.get('status') != 'ready' or metadata.get('policy') != 'reuse_saved_local_v1'
                                 or hashlib.sha256(incoming).hexdigest() != metadata.get('image_sha256') or not current.is_file()):
                    raise ValueError("ภาพสำรองยังไม่พร้อม หรือข้อมูลไม่ตรงกับไฟล์ที่บันทึก")
        saved_images = []
        if manifest.get('long_video'):
            from core.long_video import validate_landscape_image
            if not compact_images:
                for encoded in images:
                    validate_landscape_image(base64.b64decode(str(encoded).split(',', 1)[-1], validate=True),
                                             require_16_9=manifest.get('video_generation_mode') == 'meta_ai')
        if compact_images:
            digests = dict(manifest.get("partial_image_sha256") or {})
            checkpoints = {str(path).replace('\\', '/') for path in (manifest.get("partial_generated_images") or [])}
            for index in range(1, count + 1):
                relative = f"generated/scene_{index:02d}.png"
                target = folder / relative
                if relative not in checkpoints or not target.is_file():
                    raise ValueError(f"ยังไม่มี Checkpoint ภาพฉาก {index} • ไม่รับผลรวม")
                payload = target.read_bytes()
                if not digests.get(str(index)) or hashlib.sha256(payload).hexdigest() != digests[str(index)]:
                    raise ValueError(f"Checkpoint ภาพฉาก {index} เปลี่ยนไป • ไม่รับผลรวม")
                metadata = fallback_map.get(str(index))
                if metadata and (metadata.get("status") != "ready" or metadata.get("policy") != "reuse_saved_local_v1"
                                 or metadata.get("image_sha256") != digests[str(index)]):
                    raise ValueError(f"หลักฐานภาพสำรองฉาก {index} ไม่ตรงกับ Checkpoint")
                validate_landscape_image(payload, require_16_9=manifest.get('video_generation_mode') == 'meta_ai')
                saved_images.append(relative)
        for index, encoded in enumerate(images, 1):
            raw = str(encoded or "")
            if raw.startswith("data:"):
                raw = raw.split(",", 1)[-1]
            try:
                payload = base64.b64decode(raw, validate=True)
            except (ValueError, binascii.Error):
                raise ValueError(f"ข้อมูลรูปฉากที่ {index} ไม่ถูกต้อง") from None
            if len(payload) < 100:
                raise ValueError(f"รูปฉากที่ {index} ว่างเปล่า")
            target = folder / "generated" / f"scene_{index:02d}.png"
            if not (fallback_map and target.is_file()):
                target.write_bytes(payload)
            saved_images.append(str(target.relative_to(folder)))
        durations = []
        for value in list(result.get("scene_durations") or [])[:count]:
            try:
                durations.append(max(2.0, min(30.0 if manifest.get('long_video') else 12.0, float(value))))
            except (TypeError, ValueError):
                durations.append(5.0)
        if len(durations) != count:
            durations = [5.0] * count
        continuity_validation = {}
        if manifest.get("job_type") == "drama_episode":
            try:
                continuity_validation = DramaContinuityValidator().validate(
                    [folder / relative for relative in saved_images],
                    prompts,
                    manifest.get("character_bible") or [],
                    result.get("visual_bible") or {},
                    manifest.get("previous_visual_bible") or {},
                )
            except Exception:
                for relative in saved_images:
                    (folder / relative).unlink(missing_ok=True)
                raise
            (folder / "prompts" / "continuity_validation.json").write_text(
                json.dumps(continuity_validation, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        (folder / "captions" / "video_title.txt").write_text(title, encoding="utf-8")
        (folder / "captions" / "video_description.txt").write_text(description, encoding="utf-8")
        if post_hashtags:
            (folder / "captions" / "hashtags.txt").write_text(post_hashtags, encoding="utf-8")
        (folder / "captions" / "narration_script.txt").write_text(narration, encoding="utf-8")
        (folder / "prompts" / "scene_prompts.json").write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
        if narrations:
            (folder / "captions" / "scene_narrations.json").write_text(json.dumps(narrations, ensure_ascii=False, indent=2), encoding="utf-8")
        selected_provider = self._image_ai_provider(
            result.get("image_generation_provider") or result.get("provider") or manifest.get("image_ai_provider") or "chatgpt"
        )
        manifest.update({
            "status": "ready_to_render",
            "ai_status": "ready",
            "ai_provider": str(result.get("provider") or f"{manifest.get('image_ai_provider', 'chatgpt')}_web_extension"),
            "image_generation_provider": str(result.get("image_generation_provider") or f"{manifest.get('image_ai_provider', 'chatgpt')}_web"),
            "image_generation_via_chatgpt_web": bool(result.get("image_generation_via_chatgpt_web", selected_provider == "chatgpt")),
            "image_generation_via_gemini_web": bool(result.get("image_generation_via_gemini_web", selected_provider == "gemini")),
            "video_title": title,
            "video_description": description,
            **({'hashtags': post_hashtags} if post_hashtags else {}),
            "cover": normalize_cover(result.get("cover") or manifest.get("cover")),
            "narration_script": narration,
            "pronunciation_notes": result.get("pronunciation_notes") if isinstance(result.get("pronunciation_notes"), dict) else manifest.get("pronunciation_notes", {}),
            "visual_bible": result.get("visual_bible") or {},
            "episode_title": str(result.get("episode_title") or title).strip(),
            "episode_summary": str(result.get("episode_summary") or description).strip(),
            "next_episode_hook": str(result.get("next_episode_hook") or "").strip(),
            "continuity_state": result.get("continuity_state") or {},
            "continuity_validation": continuity_validation,
            "dialogue_turns": dialogue_turns,
            "speaker_corrections": speaker_corrections,
            "scene_prompts": prompts,
            "scene_narrations": narrations,
            "scene_durations": durations,
            "engagement_cta_enabled": manifest['storytelling_options']['cta_enabled'] if manifest.get('storytelling_options') else not (manifest.get('flow_smoke_test', False) or story_performance.enabled(manifest) or authored_product_script(manifest)),
            "engagement_cta_added_by_program": cta_added,
            "generated_images": saved_images,
            "partial_generated_images": saved_images,
            "partial_image_count": len(saved_images),
            "video_status": "images_ready",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        if short_film_ad(manifest):
            manifest['product_film_plan'] = copy.deepcopy(result['product_film_plan'])
        if manifest.get('meta_prompt_version') == 5:
            motion = result.get('flow_shot_prompts')
            if (isinstance(motion, list) and len(motion) == count
                    and all(isinstance(value, str) and value.strip() for value in motion)):
                manifest['flow_shot_prompts'] = copy.deepcopy(motion)
        if creative_brief is not None:
            manifest['creative_brief'] = creative_brief
        manifest.update(content_identity)
        self._save(manifest)
        return manifest

    def update_narration(self, job_id, narration, scene_narrations=None):
        manifest = self.get(job_id)
        narration = str(narration or "").strip()
        narrations = self._strings(scene_narrations if scene_narrations is not None else manifest.get("scene_narrations"))
        if story_performance.enabled(manifest):
            raise ValueError('แก้บทตัวละครผ่านแผนรายฉาก ไม่แทนบทสนทนาด้วยบทพากย์')
        if short_film_ad(manifest):
            revised = copy.deepcopy(manifest)
            for scene, line in zip((revised.get('product_film_plan') or {}).get('scenes', []), narrations):
                scene['spoken_text'] = line
            revised.update(narration_script=narration, scene_narrations=narrations)
            validate_film_plan(manifest, revised)
            manifest['product_film_plan'] = revised['product_film_plan']
            manifest['scene_dialogue_turns'] = [[{'speaker': scene['speaker'], 'text': scene['spoken_text']}]
                                              for scene in revised['product_film_plan']['scenes']]
            manifest['dialogue_turns'] = [turn for group in manifest['scene_dialogue_turns'] for turn in group]
        if manifest.get('storytelling_options') or manifest.get('flow_smoke_test') or authored_product_script(manifest):
            cta_added = False
        else:
            narration, narrations, cta_added = self._ensure_engagement_cta(narration, narrations, manifest.get("topic"))
        folder = self._folder(job_id)
        if short_film_ad(manifest):
            # Explicit edits must survive the per-scene resume path, which reads
            # the checkpoint rather than the form/manifest. No receipt reset.
            checkpoint_store = AtomicJsonFile(folder / 'prompts' / 'ai_analysis_checkpoint.json')
            checkpoint = checkpoint_store.read({})
            if checkpoint:
                checkpoint.update({key: copy.deepcopy(manifest[key]) for key in
                                   ('product_film_plan', 'scene_dialogue_turns', 'dialogue_turns')})
                checkpoint.update(narration_script=narration, scene_narrations=narrations)
                validate_film_plan(manifest, checkpoint)
                checkpoint_store.write(checkpoint)
        (folder / "captions" / "narration_script.txt").write_text(narration, encoding="utf-8")
        if narrations:
            (folder / "captions" / "scene_narrations.json").write_text(json.dumps(narrations, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest.update({"narration_script": narration, "scene_narrations": narrations, "voice_status": "needs_regeneration", "status": "ready_to_render", "engagement_cta_enabled": manifest['storytelling_options']['cta_enabled'] if manifest.get('storytelling_options') else not (manifest.get('flow_smoke_test', False) or authored_product_script(manifest)), "engagement_cta_added_by_program": cta_added, "updated_at": datetime.now().isoformat(timespec="seconds")})
        self._save(manifest)
        return manifest

    def save_voice(self, job_id, source, external_job_id="", output_id="", reference_id=""):
        folder = self._folder(job_id)
        source = Path(source)
        if not source.is_file() or source.suffix.lower() not in {".mp3", ".wav", ".mp4"}:
            raise ValueError("ไฟล์เสียงเรื่องเล่าไม่ถูกต้อง")
        target = folder / "audio" / f"narration{source.suffix.lower()}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        manifest = self.get(job_id)
        if manifest.get("cancel_requested"):
            raise ValueError("Story Job นี้ถูกผู้ใช้ยกเลิกแล้ว")
        manifest.update({"voice_status": "ready", "voice_path": str(target.relative_to(folder)), "voice_job_id": external_job_id, "voice_output_id": output_id, "voice_reference_id": reference_id, "updated_at": datetime.now().isoformat(timespec="seconds")})
        self._save(manifest)
        return manifest

    def activate_flow_story_revision(self, job_id):
        from core.scene_context_revision import render_story
        manifest = self.get(job_id)
        effective = render_story(self._folder(job_id), manifest)
        revision = effective.get('flow_story_revision')
        if revision and manifest.get('flow_voice_revision') != revision:
            old_voice = (self._folder(job_id) / str(manifest.get('voice_path') or '')).resolve()
            if old_voice.is_file() and old_voice.is_relative_to(self._folder(job_id).resolve()):
                archive = self._folder(job_id) / 'audio' / ('before-revision-' + hashlib.sha256(revision.encode()).hexdigest()[:16] + old_voice.suffix)
                if not archive.exists():
                    shutil.copy2(old_voice, archive)
            fields = ('voice_status', 'voice_path', 'voice_job_id', 'voice_output_id',
                      'voice_reference_id', 'dialogue_voice_checkpoints')
            manifest.setdefault('flow_voice_history', []).append({key: manifest.get(key) for key in fields})
            manifest.update(voice_status='needs_regeneration', voice_job_id='', voice_output_id='',
                            voice_resubmit_count=int(manifest.get('voice_resubmit_count') or 0) + 1,
                            dialogue_voice_checkpoints={}, flow_voice_revision=revision)
            self._save(manifest)
            effective = render_story(self._folder(job_id), manifest)
        return effective

    def save_voice_checkpoint(self, job_id, external_job_id="", output_id="", reference_id="", status="queued"):
        """Persist a paid narration request before polling or downloading it."""
        with self._manifest_lock:
            manifest = self.get(job_id)
            if manifest.get("cancel_requested"):
                raise ValueError("Story Job นี้ถูกผู้ใช้ยกเลิกแล้ว")
            if external_job_id:
                manifest["voice_job_id"] = str(external_job_id)
            if output_id:
                manifest["voice_output_id"] = str(output_id)
            if reference_id:
                manifest["voice_reference_id"] = str(reference_id)
            manifest["voice_status"] = str(status or "queued")
            manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._save(manifest)
            return manifest

    def prepare_voice_resubmit(self, job_id, failed_job_id="", reason="", max_resubmits=1):
        """Retire one terminal server queue before a deterministic replacement.

        This is only for an explicit retryable terminal failure (for example
        the Voice server lost its temporary WAV).  Persisting the revision
        before submit means an app restart uses the same v2 idempotency key
        instead of creating an unbounded sequence of paid requests.
        """
        with self._manifest_lock:
            manifest = self.get(job_id)
            if manifest.get("cancel_requested"):
                raise ValueError("Story Job นี้ถูกผู้ใช้ยกเลิกแล้ว")
            count = int(manifest.get("voice_resubmit_count") or 0)
            if count >= max(0, int(max_resubmits or 0)):
                raise ValueError("AI Voice ลองสร้างคิวทดแทนครบจำนวนที่ปลอดภัยแล้ว")
            count += 1
            history = list(manifest.get("voice_resubmit_history") or [])
            history.append({
                "attempt": count,
                "failed_job_id": str(failed_job_id or manifest.get("voice_job_id") or ""),
                "reason": str(reason or "")[:1000],
                "created_at": datetime.now().isoformat(timespec="seconds"),
            })
            manifest.update({
                "voice_resubmit_count": count,
                "voice_resubmit_history": history[-5:],
                "voice_job_id": "",
                "voice_output_id": "",
                "voice_status": "resubmitting",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._save(manifest)
            return manifest

    def save_dialogue_voice_checkpoint(self, job_id, turn_index, **values):
        """Persist one paid dialogue TTS request before waiting for its result."""
        turn_index = max(1, int(turn_index or 1))
        with self._manifest_lock:
            manifest = self.get(job_id)
            checkpoints = dict(manifest.get("dialogue_voice_checkpoints") or {})
            checkpoint = dict(checkpoints.get(str(turn_index)) or {})
            for key in ("speaker", "reference_id", "external_job_id", "output_id", "status", "path", "resubmit_count", "last_error", "replaced_external_job_id"):
                if key in values:
                    checkpoint[key] = str(values.get(key) or "")
            checkpoint["updated_at"] = datetime.now().isoformat(timespec="seconds")
            checkpoints[str(turn_index)] = checkpoint
            manifest["dialogue_voice_checkpoints"] = checkpoints
            manifest["updated_at"] = checkpoint["updated_at"]
            self._save(manifest)
            return dict(checkpoint)

    @staticmethod
    def _sha256_file(path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sha256_text(value):
        return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _authenticated_flow_policy_history(manifest, shot_index):
        """Return only policy records tied to one real Extension run/card."""
        records = list(
            (manifest.get("flow_policy_failure_history") or {}).get(str(int(shot_index or 0))) or []
        )
        return [
            dict(item) for item in records
            if isinstance(item, dict)
            and item.get("failure_code", "FLOW_POLICY_BLOCKED") == "FLOW_POLICY_BLOCKED"
            and str(item.get("flow_run_id") or "").strip()
            and str(item.get("failure_card_fingerprint") or "").strip()
            and str(item.get("image_sha256") or "").strip()
            and str(item.get("prompt_sha256") or "").strip()
        ]

    @staticmethod
    def _authenticated_flow_attachment_history(manifest, shot_index):
        records = list(
            (manifest.get("flow_attachment_failure_history") or {}).get(str(int(shot_index or 0))) or []
        )
        authenticated = []
        for item in records:
            if not isinstance(item, dict) or item.get("failure_code") != FLOW_ATTACHMENT_UNCONFIRMED:
                continue
            if not item.get("image_sha256") or not item.get("prompt_sha256"):
                continue
            try:
                validated_attachment_failure_evidence(
                    item.get("attachment_failure_evidence"), item.get("flow_run_id"),
                    item.get("failure_card_fingerprint"),
                )
            except ValueError:
                continue
            authenticated.append(dict(item))
        return authenticated

    @classmethod
    def _authenticated_flow_local_fallback_history(cls, manifest, shot_index):
        return (
            cls._authenticated_flow_policy_history(manifest, shot_index)
            + cls._authenticated_flow_attachment_history(manifest, shot_index)
        )

    def register_flow_policy_failure(
        self, job_id, shot_index, reason="", flow_run_id="", failure_card_fingerprint="",
    ):
        """Persist the first authenticated policy denial and use local motion."""
        return self._register_flow_local_failure(
            job_id, shot_index, reason, flow_run_id, failure_card_fingerprint,
        )

    def register_flow_attachment_failure(
        self, job_id, shot_index, reason="", flow_run_id="", failure_card_fingerprint="", evidence=None,
    ):
        """Persist attachment failure after a pre-submit passive grace."""
        proof = validated_attachment_failure_evidence(evidence, flow_run_id, failure_card_fingerprint)
        return self._register_flow_local_failure(
            job_id, shot_index, reason, flow_run_id, failure_card_fingerprint,
            failure_code=FLOW_ATTACHMENT_UNCONFIRMED, evidence=proof,
        )

    def _register_flow_local_failure(
        self, job_id, shot_index, reason="", flow_run_id="", failure_card_fingerprint="",
        failure_code="FLOW_POLICY_BLOCKED", evidence=None,
    ):
        """Persist a distinct terminal Story input and choose one safe action.

        The first authenticated terminal decision uses the canonical still
        locally. It never creates or submits another Flow prompt. Duplicate
        evidence is idempotent and cannot trigger another physical action.
        """
        with self._manifest_lock:
            folder = self._folder(job_id)
            manifest = self.get(job_id)
            count = int(manifest.get("scene_count") or 0)
            shot_index = int(shot_index or 0)
            from core.scene_video_plan import provider_for
            if provider_for(manifest, shot_index) != "google_flow":
                raise ValueError("Story Job นี้ไม่ได้เลือกสร้างวิดีโอด้วย Google Flow")
            if not 1 <= shot_index <= count:
                raise ValueError("ลำดับฉาก Google Flow ไม่ถูกต้อง")
            canonical = folder / "generated" / f"scene_{shot_index:02d}.png"
            attachment = failure_code == FLOW_ATTACHMENT_UNCONFIRMED
            history_field = "flow_attachment_failure_history" if attachment else "flow_policy_failure_history"
            attempts_field = "flow_attachment_attempts" if attachment else "flow_policy_attempts"
            duplicate_action = "duplicate_attachment_event" if attachment else "duplicate_policy_event"
            history_map = dict(manifest.get(history_field) or {})
            history = list(history_map.get(str(shot_index)) or [])
            flow_run_id = str(flow_run_id or "").strip()[:160]
            failure_card_fingerprint = str(failure_card_fingerprint or "").strip()[:160]
            if not flow_run_id or not failure_card_fingerprint:
                raise ValueError(
                    "ไม่พบหลักฐาน Run/Fingerprint จากการ์ด Policy ปัจจุบันของ Google Flow"
                )
            completed = dict(manifest.get("flow_clips") or {}).get(str(shot_index))
            if completed and (folder / str(completed)).is_file():
                raise ValueError(f"ฉาก {shot_index} มีคลิป Google Flow จริงแล้ว")
            existing = self._authenticated_flow_local_fallback_history(manifest, shot_index)
            if existing and not history:
                return {
                    "job": manifest, "action": duplicate_action,
                    "attempt": int(existing[-1].get("attempt") or 1),
                    "record": dict(existing[-1]), "duplicate_reason": "scene_already_terminal",
                }
            duplicate_event = next((
                item for item in history
                if flow_run_id and failure_card_fingerprint
                and item.get("flow_run_id") == flow_run_id
                and item.get("failure_card_fingerprint") == failure_card_fingerprint
            ), None)
            if duplicate_event:
                return {
                    "job": manifest,
                    "action": duplicate_action,
                    "attempt": int(duplicate_event.get("attempt") or 1),
                    "record": dict(duplicate_event),
                    "duplicate_reason": "same_run_and_failure_card",
                }
            if not canonical.is_file():
                raise ValueError(f"ไม่พบรูปฉากที่ {shot_index} สำหรับบันทึก Local Motion Checkpoint")

            # A scene is terminal after its first authenticated fallback decision.
            # A later heartbeat/run is diagnostic only and must not request a
            # fresh Flow package (or create another physical fallback).
            if history:
                image_hash = self._sha256_file(canonical)
                duplicate = next((
                    item for item in history
                    if item.get("image_sha256") == image_hash
                ), history[-1])
                return {
                    "job": manifest, "action": duplicate_action,
                    "attempt": int(duplicate.get("attempt") or 1), "record": dict(duplicate),
                    "duplicate_reason": "same_image_and_prompt",
                }

            package = self.flow_package(job_id, shot_index)
            image_hash = self._sha256_file(canonical)
            prompt_hash = self._sha256_text(package.get("video_prompt"))
            duplicate = next((
                item for item in history
                if item.get("image_sha256") == image_hash and item.get("prompt_sha256") == prompt_hash
            ), None)
            if duplicate:
                return {
                    "job": manifest, "action": duplicate_action,
                    "attempt": int(duplicate.get("attempt") or 1), "record": dict(duplicate),
                    "duplicate_reason": "same_image_and_prompt",
                }

            attempt = len(history) + 1
            action = "local_motion_fallback"
            record = {
                "at": datetime.now().isoformat(timespec="seconds"),
                "scene_index": shot_index,
                "attempt": attempt,
                "image_path": str(canonical.relative_to(folder)),
                "image_sha256": image_hash,
                "prompt_sha256": prompt_hash,
                "flow_run_id": flow_run_id,
                "failure_card_fingerprint": failure_card_fingerprint,
                "failure_code": failure_code,
                "reason": str(reason or (
                    "Google Flow attachment could not be confirmed before submission"
                    if attachment else "Google Flow policy denial"
                ))[:1000],
                "action": action,
            }
            if attachment:
                record["attachment_failure_evidence"] = dict(evidence or {})
            history.append(record)
            history_map[str(shot_index)] = history[-4:]
            attempts = dict(manifest.get(attempts_field) or {})
            attempts[str(shot_index)] = attempt

            manifest.update({
                attempts_field: attempts,
                history_field: history_map,
                "last_flow_attachment_reason" if attachment else "last_flow_policy_reason": str(reason or "")[:1000],
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._save(manifest)
            return {"job": manifest, "action": action, "attempt": attempt, "record": record}

    def activate_flow_policy_local_fallback(self, job_id, shot_index):
        """Migrate a previously authenticated retry checkpoint to local fallback.

        This is intentionally separate from attachment: callers cannot attach a
        local clip until the checkpoint action itself is fail-closed.
        """
        with self._manifest_lock:
            manifest = self.get(job_id)
            shot_index = int(shot_index or 0)
            authenticated = self._authenticated_flow_policy_history(manifest, shot_index)
            if not authenticated:
                raise ValueError("ไม่พบ Checkpoint Policy ที่ยืนยันจาก Google Flow")
            latest = authenticated[-1]
            if str(latest.get("action") or "") == "local_motion_fallback":
                return manifest
            history_map = dict(manifest.get("flow_policy_failure_history") or {})
            history = list(history_map.get(str(shot_index)) or [])
            target_index = next(
                (
                    index for index in range(len(history) - 1, -1, -1)
                    if str(history[index].get("flow_run_id") or "") == str(latest.get("flow_run_id") or "")
                    and str(history[index].get("failure_card_fingerprint") or "")
                    == str(latest.get("failure_card_fingerprint") or "")
                ),
                -1,
            )
            if target_index < 0:
                raise ValueError("ไม่พบ Checkpoint Policy ที่ตรงกับหลักฐานเดิม")
            migrated = dict(history[target_index])
            migrated.update({
                "legacy_action": str(migrated.get("action") or ""),
                "action": "local_motion_fallback",
                "migrated_at": datetime.now().isoformat(timespec="seconds"),
            })
            history[target_index] = migrated
            history_map[str(shot_index)] = history
            prompt_profiles = dict(manifest.get("flow_prompt_profiles") or {})
            prompt_retries = dict(manifest.get("flow_prompt_retries") or {})
            prompt_profiles.pop(str(shot_index), None)
            prompt_retries.pop(str(shot_index), None)
            manifest.update({
                "flow_policy_failure_history": history_map,
                "flow_prompt_profiles": prompt_profiles,
                "flow_prompt_retries": prompt_retries,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._save(manifest)
            return manifest

    def prepare_scene_pipeline(self, job_id, index):
        with self._manifest_lock:
            job = self.get(job_id)
            from core.scene_video_plan import enabled as has_video_plan
            if job.get('scene_pipeline_version') != 1 or (job.get('video_generation_mode') != 'google_flow' and not has_video_plan(job)):
                raise ValueError('งานนี้ไม่ได้เปิดระบบรายฉาก')
            count = int(job.get('scene_count') or 0)
            if type(index) is not int or not 1 <= index <= count:
                raise ValueError('ฉากไม่ตรงงาน')
            folder = self._folder(job_id)
            analysis = AtomicJsonFile(folder/'prompts/ai_analysis_checkpoint.json').read({})
            analysis = story_performance.validate_plan(job, analysis)
            validate_film_plan(job, analysis)
            if len(analysis.get('scene_narrations') or []) != count:
                raise ValueError('ยังไม่มีบทที่บันทึกครบ')
            for key in ('scene_narrations','scene_prompts','scene_durations','narration_script',
                        'dialogue_turns','scene_dialogue_turns','video_title','video_description','visual_bible','pronunciation_notes', 'character_bible', 'product_film_plan'):
                if key in analysis:
                    job[key] = analysis[key]
            original_narration = str(job.get('narration_script') or '')
            added = False
            from core.product_editorial import assert_approved, enabled as editorial_enabled
            assert_approved(job)
            if not editorial_enabled(job) and not job.get('storytelling_options') and not job.get('flow_smoke_test') and not story_performance.enabled(job) and not authored_product_script(job):
                job['narration_script'], job['scene_narrations'], added = self._ensure_engagement_cta(
                    original_narration, job['scene_narrations'], job.get('topic',''))
            names = [str(row.get('name') or '') for row in job.get('character_bible') or []]
            turns = []
            for raw in list(job.get('dialogue_turns') or [])[:120]:
                text = clean_dialogue_turn_text(raw, names)
                if text:
                    speaker, _ = self._normalise_dialogue_speaker(str(raw.get('speaker') or 'ผู้บรรยาย'), names)
                    turns.append({'speaker':speaker,'text':text,'emotion':'normal','pause_after':.35})
            if added and turns:
                turns.append({'speaker':'ผู้บรรยาย','text':job['narration_script'][len(original_narration):].strip(),'emotion':'normal','pause_after':.4})
            job['dialogue_turns'] = turns
            groups = job.get('scene_dialogue_turns')
            if isinstance(groups,list) and len(groups)==count:
                normalized_groups=[]
                for group in groups:
                    if not isinstance(group,list):
                        raise ValueError('บทพูดรายฉากไม่ถูกต้อง')
                    cleaned=[]
                    for raw in group:
                        if not isinstance(raw,dict):
                            raise ValueError('ผู้พูดรายฉากไม่ถูกต้อง')
                        speaker,_=self._normalise_dialogue_speaker(str(raw.get('speaker') or 'ผู้บรรยาย'),names)
                        text=clean_dialogue_turn_text(raw,names)
                        if text:cleaned.append({'speaker':speaker,'text':text,'emotion':'normal','pause_after':.35})
                    normalized_groups.append(cleaned)
                if added:
                    normalized_groups[-1].append({'speaker':'ผู้บรรยาย','text':job['narration_script'][len(original_narration):].strip(),'emotion':'normal','pause_after':.4})
                job['scene_dialogue_turns']=normalized_groups
            if story_performance.enabled(job):
                job['scene_dialogue_turns'] = analysis['scene_dialogue_turns']
                job['dialogue_turns'] = analysis['dialogue_turns']
            slots = [f'generated/scene_{number:02d}.png' for number in range(1,count+1)]
            if not (folder/slots[index-1]).is_file():
                raise ValueError('ยังไม่มีภาพฉากที่บันทึกแล้ว')
            job['generated_images'] = slots
            self._save(job)
            return job

    def flow_package(self, job_id, shot_index=0):
        """Return one generated Story scene and its motion brief for Google Flow."""
        folder = self._folder(job_id)
        manifest = self.get(job_id)
        from core.product_editorial import assert_approved
        assert_approved(manifest)
        from core.scene_video_plan import effective_job, enabled as has_video_plan, package_binding, settings_for, legacy_active, validate_package
        validate_package(folder, manifest, int(shot_index or 0))
        manifest = effective_job(manifest, int(shot_index or 0))
        if manifest.get("story_image_fallbacks"):
            raise ValueError("งานมีฉากใช้ภาพสำรองจากการปฏิเสธ • ประกอบในโปรแกรมเท่านั้น ไม่ส่งต่อ Google Flow")
        if self._video_generation_mode(manifest.get("video_generation_mode")) != "google_flow":
            raise ValueError("Story Job นี้ไม่ได้เลือกสร้างวิดีโอด้วย Google Flow")
        image_files = list(manifest.get("generated_images") or [])
        prompts = list(manifest.get("scene_prompts") or [])
        narrations = list(manifest.get("scene_narrations") or [])
        count = int(manifest.get("scene_count") or len(image_files))
        if len(image_files) != count:
            raise ValueError("รูป Story ยังไม่ครบทุกฉากสำหรับส่งเข้า Google Flow")
        shot_index = int(shot_index or 0)
        if not 1 <= shot_index <= count:
            raise ValueError("ไม่พบรูปสำหรับฉากที่เลือก")
        if (
            self._authenticated_flow_local_fallback_history(manifest, shot_index)
            or dict(manifest.get("flow_fallback_clips") or {}).get(str(shot_index))
        ):
            raise ValueError(
                f"{'FLOW_ATTACHMENT_LOCAL_FALLBACK_CHECKPOINT' if self._authenticated_flow_attachment_history(manifest, shot_index) else 'FLOW_POLICY_LOCAL_FALLBACK_CHECKPOINT'} • ฉาก {shot_index} "
                "ถูกปิดการส่ง Google Flow แล้วและต้องใช้ Local Motion จากรูปเดิม"
            )
        relative = str(image_files[shot_index - 1])
        if not (folder / relative).is_file():
            raise ValueError(f"ไม่พบไฟล์รูปฉากที่ {shot_index}")
        raw_scene_prompt = str(prompts[shot_index - 1] if shot_index <= len(prompts) else "").strip()
        raw_scene_narration = str(narrations[shot_index - 1] if shot_index <= len(narrations) else "").strip()
        scene_prompt = self._flow_safe_motion_text(raw_scene_prompt)
        scene_narration = self._flow_safe_motion_text(raw_scene_narration)
        safety_reframed = scene_prompt != raw_scene_prompt or scene_narration != raw_scene_narration
        safety_note = ""
        if safety_reframed:
            safety_note = (
                "\nThis is a calm, gentle, family-friendly wellness-check. "
                "Everyone is safe and the mood is caring and reassuring."
            )
        orientation = 'horizontal 16:9' if manifest.get('long_video') else 'vertical 9:16'
        video_prompt = f"""Create exactly one playable {orientation} cinematic video from the uploaded reference image.
SCENE {shot_index} OF {count}: {scene_prompt}
Story beat: {scene_narration}{safety_note}

Preserve the exact character identity, face, body, clothing, props, location, colors, lighting and composition from the reference image. Add only natural character action, environmental motion, depth, parallax and a smooth cinematic camera move that fit this exact story beat. Keep continuity with adjacent scenes. Do not replace or redesign characters. No readable text, captions, logos, watermarks, split screen, collage, UI, HUD or unrelated CGI. Generate the actual video now, not a plan, explanation, storyboard or still image."""
        from core.flow_motion_plan import saved_motion_prompt, provider_for
        from core.flow_scene_edit import override
        manual = override(folder, manifest, shot_index, relative)
        motion_prompt = (manual['prompt'] + flow_audio_instruction(manifest, shot_index, manual['prompt'])) if manual else saved_motion_prompt(folder, manifest, shot_index, relative)
        if story_performance.enabled(manifest) and motion_prompt:
            actor_audio = flow_audio_instruction(manifest, shot_index)
            if actor_audio not in motion_prompt:
                motion_prompt += actor_audio
        if not manual:
            from core.story_visual_plan import repaired_image
            relative = repaired_image(folder, manifest, shot_index, relative)
        scene_settings = flow_settings(manifest.get('flow_settings'))
        if manual and not has_video_plan(manifest):
            scene_settings.pop('model', None)
            if manual['model']:
                scene_settings['model'] = manual['model']
        if has_video_plan(manifest):
            scene_settings = settings_for(manifest, shot_index)
        speech_retry = dict((manifest.get('flow_speech_retries') or {}).get(str(shot_index)) or {})
        speech_retry_id = str(speech_retry.get('retry_id') or '') if speech_retry.get('status') == 'pending' else ''
        selected_prompt = motion_prompt or video_prompt.strip() + flow_audio_instruction(manifest, shot_index)
        from core.product_pointing import apply_visual
        selected_prompt = apply_visual(manifest, selected_prompt)
        from core.generated_music import apply_to_prompt
        selected_prompt = apply_to_prompt(manifest, shot_index, selected_prompt)
        if speech_retry_id:
            from core.flow_speech_quality import retry_prompt
            selected_prompt = retry_prompt(selected_prompt)
        return {
            **({'scene_video_plan_required': True, 'scene_video_plan': package_binding(manifest, shot_index),
                'scene_video_plan_legacy_active': legacy_active(manifest, shot_index)}
               if has_video_plan(manifest) else {}),
            "image_ai_provider": provider_for(manifest),
            "motion_prompt_ready": bool(motion_prompt),
            "fictional_ai_characters_confirmed": manifest.get("fictional_ai_characters_confirmed") is True,
            "flow_settings": scene_settings,
            "job_id": job_id,
            "mode": "story",
            "story_title": manifest.get("video_title") or manifest.get("topic") or "Story Shorts",
            "aspect_ratio": '16:9' if manifest.get('long_video') else '9:16',
            "shot_index": shot_index,
            "shot_count": count,
            "video_prompt": selected_prompt,
            "speech_retry_id": speech_retry_id,
            "caption": manifest.get("video_description") or "",
            "hashtags": "",
            "warnings": ["flow_prompt_safety_reframed"] if safety_reframed else [],
            "image_files": [relative],
            "cgi_prompt_policy": "story_scene_motion_v1",
        }

    @staticmethod
    def _flow_safe_motion_text(value):
        """Reframe graphic/high-risk wording without changing story continuity.

        Google Flow can reject an otherwise family-safe rescue scene when a
        motion prompt contains clinical or graphic state words. The reference
        image remains authoritative; this only describes a gentle action that
        the video model can animate safely.
        """
        text = str(value or "").strip()
        replacements = (
            (r"\bcollapsed\s+unconscious\b", "resting weakly but safely"),
            (r"\bunconscious\b", "weak and resting safely"),
            (r"\bcollapsed\b", "resting on the floor"),
            (r"\b(?:dead|dying|lifeless)\b", "very tired and resting safely"),
            (r"\b(?:blood(?:y)?|bleeding|severe wound|open wound)\b", "non-graphic signs of fatigue"),
            (r"หมดสติ", "อ่อนแรงและกำลังนอนพักอย่างปลอดภัย"),
            (r"นอนแน่นิ่ง", "นอนพักอย่างอ่อนแรงแต่ยังปลอดภัย"),
            (r"ไร้สติ", "อ่อนแรงและกำลังพักฟื้น"),
            (r"เสียชีวิต|กำลังจะตาย|ตายแล้ว", "อ่อนเพลียและต้องการความช่วยเหลือ"),
            (r"เลือดไหล|เลือดอาบ|บาดแผลฉกรรจ์", "อาการอ่อนเพลียแบบไม่รุนแรง"),
        )
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return re.sub(r"\s{2,}", " ", text).strip()

    def attach_flow_clip(self, job_id, shot_index, source_path, *, scene_video_plan=None, expected_sha256=None):
        with self._manifest_lock:
            return self._attach_flow_clip_locked(job_id, shot_index, source_path,
                scene_video_plan=scene_video_plan, expected_sha256=expected_sha256)

    def _attach_flow_clip_locked(self, job_id, shot_index, source_path, *, scene_video_plan=None, expected_sha256=None):
        """Checkpoint one real Google Flow clip without losing completed scenes."""
        folder = self._folder(job_id)
        manifest = self.get(job_id)
        from core.scene_video_plan import provider_for, enabled as has_video_plan, assert_binding, verified_asset
        if manifest.get('cancel_requested') or manifest.get('status') in {'cancelled', 'canceled', 'deleted'}:
            raise ValueError('งานถูกยกเลิก • เก็บคลิปเดิมไว้')
        if has_video_plan(manifest):
            assert_binding(manifest, int(shot_index or 0), scene_video_plan, allow_legacy_active=True)
            if scene_video_plan and not expected_sha256:
                raise ValueError('ไม่มีหลักฐานไฟล์ดาวน์โหลดของรอบวิดีโอนี้')
        if provider_for(manifest, int(shot_index or 0)) != "google_flow":
            raise ValueError("Story Job นี้ไม่ได้เลือกสร้างวิดีโอด้วย Google Flow")
        shot_index = int(shot_index or 0)
        count = int(manifest.get("scene_count") or 0)
        if not 1 <= shot_index <= count:
            raise ValueError("ลำดับฉาก Google Flow ไม่ถูกต้อง")
        if (
            self._authenticated_flow_local_fallback_history(manifest, shot_index)
            or dict(manifest.get("flow_fallback_clips") or {}).get(str(shot_index))
        ):
            raise ValueError(
                f"ฉาก {shot_index} มี Local Motion Checkpoint แล้ว "
                "จึงห้ามใช้คลิป Google Flow ทับหรือส่งฉากเดิมซ้ำ"
            )
        source = Path(source_path)
        if not source.is_file() or source.suffix.lower() not in self.VIDEO_EXTENSIONS:
            raise ValueError("ไฟล์วิดีโอ Google Flow ไม่ถูกต้อง")
        if manifest.get('long_video'):
            from core.video_logo import VideoLogoRenderer
            info = VideoLogoRenderer().video_info(source)
            if info['width'] <= info['height']:
                raise ValueError('Google Flow ส่งคลิปแนวตั้งให้คลิปยาว • เก็บไฟล์ดาวน์โหลดไว้ ไม่สร้างซ้ำ กรุณาตรวจสัดส่วน 16:9')

        def fingerprint(path):
            digest = hashlib.sha256()
            with Path(path).open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()

        source_hash = fingerprint(source)
        if expected_sha256 is not None and source_hash != expected_sha256:
            raise ValueError('ไฟล์ดาวน์โหลดไม่ตรงหลักฐานของรอบวิดีโอนี้')
        if has_video_plan(manifest):
            kept = verified_asset(folder, manifest, shot_index, fresh=True)
            if kept:
                if kept['provider'] == 'google_flow' and kept['sha256'] == source_hash:
                    return manifest
                raise ValueError('ฉากนี้มีคลิปที่เก็บไว้แล้ว • ไม่รับผลอื่นทับ')
        clips = dict(manifest.get("flow_clips") or {})
        for existing_index, relative in clips.items():
            if str(existing_index) == str(shot_index):
                continue
            existing = folder / str(relative or "")
            if existing.is_file() and fingerprint(existing) == source_hash:
                raise ValueError(f"วิดีโอ Google Flow ฉาก {shot_index} ซ้ำกับฉาก {existing_index}")
        attempt_suffix = '-' + scene_video_plan['attempt_id'] if scene_video_plan else ''
        target = working_video_folder(folder) / f"flow_scene_{shot_index:02d}{attempt_suffix}{source.suffix.lower()}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        if fingerprint(target) != source_hash:
            raise ValueError('คลิปเปลี่ยนระหว่างเก็บไฟล์ • ยังไม่รับผลฉาก')
        clips[str(shot_index)] = str(target.relative_to(folder))
        fallback_clips = dict(manifest.get("flow_fallback_clips") or {})
        ready = all(
            (folder / str(clips.get(str(index)) or fallback_clips.get(str(index)) or "")).is_file()
            for index in range(1, count + 1)
        )
        manifest.update({
            "video_ai_provider": "flow",
            "flow_clips": clips,
            "flow_clip_count": len(clips),
            "flow_fallback_clips": fallback_clips,
            "flow_fallback_count": len(fallback_clips),
            "flow_scene_count": len(clips) + len(fallback_clips),
            "flow_video_status": "ready" if ready else "waiting_downloads",
            "video_status": "clips_ready" if ready else "collecting_clips",
            "video_source_type": "google_flow_story_hybrid_clips" if fallback_clips else "google_flow_story_clips",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save(manifest)
        return manifest

    def begin_native_speech_retry(self, job_id, finding, source_sha256, *, max_attempts=2):
        """Persist one new Flow attempt without discarding the old scene/clip."""
        from core.scene_pipeline import ScenePipeline
        index = int(finding.get('scene') or 0)
        with self._manifest_lock:
            manifest = self.get(job_id)
            count = int(manifest.get('scene_count') or 0)
            from core.scene_video_plan import provider_for
            if (manifest.get('scene_pipeline_version') != 1 or provider_for(manifest, index) != 'google_flow'
                    or not 1 <= index <= count or not source_sha256):
                raise ValueError('หลักฐานเสียงซ้ำไม่ตรงงาน Google Flow')
            folder = self._folder(job_id)
            pipeline = ScenePipeline(folder)
            row = pipeline.get(index)
            if row.get('phase') != 'complete':
                raise ValueError('ฉากเสียงซ้ำยังไม่ใช่ผลที่บันทึกครบ')
            audit = AtomicJsonFile(folder / 'audio' / 'flow_speech_quality.json').read({})
            if (audit.get('status') != 'repeat_confirmed' or audit.get('source_sha256') != source_sha256
                    or audit.get('scene_segments', {}).get(str(index)) != row.get('segment_sha256')
                    or not any(item.get('scene') == index and item.get('phrase') == finding.get('phrase')
                               for item in audit.get('findings') or [])):
                raise ValueError('หลักฐานเสียงซ้ำหรือไฟล์ฉากเปลี่ยน • ไม่สร้างซ้ำ')
            state = dict((manifest.get('flow_speech_retries') or {}).get(str(index)) or {})
            if state.get('status') == 'pending' and state.get('source_sha256') == source_sha256:
                return state
            history = list(state.get('history') or [])
            if len(history) >= max_attempts:
                raise ValueError(f'FLOW_SPEECH_REPEAT_REVIEW • ฉาก {index} ยังพูดซ้ำหลังสร้างใหม่ {max_attempts} รอบ • เก็บทุกคลิปไว้ตรวจ')
            retry_id = str(uuid.uuid4())
            relative = str((manifest.get('flow_clips') or {}).get(str(index)) or '')
            old_clip = (folder / relative).resolve() if relative else None
            backup = ''
            if old_clip and (not old_clip.is_relative_to(folder.resolve()) or not old_clip.is_file()):
                raise ValueError('คลิป Flow เดิมไม่ตรง Checkpoint • ไม่สร้างซ้ำ')
            if old_clip:
                target = folder / 'backups' / 'flow_speech' / f'scene-{index:02d}-{retry_id}{old_clip.suffix}'
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old_clip, target)
                backup = target.relative_to(folder).as_posix()
            history.append({'retry_id': retry_id, 'source_sha256': source_sha256,
                            'segment': row.get('segment'), 'segment_sha256': row.get('segment_sha256'),
                            'old_clip_backup': backup, 'phrase': str(finding.get('phrase') or '')[:120]})
            state = {'status': 'pending', 'retry_id': retry_id, 'attempt': len(history),
                     'scene': index, 'source_sha256': source_sha256,
                     'segment_sha256': row.get('segment_sha256'), 'history': history}
            retries = dict(manifest.get('flow_speech_retries') or {})
            retries[str(index)] = state
            clips = dict(manifest.get('flow_clips') or {})
            clips.pop(str(index), None)
            manifest.update(flow_speech_retries=retries, flow_clips=clips,
                            flow_clip_count=len(clips), updated_at=datetime.now().isoformat(timespec='seconds'))
            self._save(manifest)
            return state

    def complete_native_speech_retry(self, job_id, index, retry_id):
        with self._manifest_lock:
            manifest = self.get(job_id)
            retries = dict(manifest.get('flow_speech_retries') or {})
            state = dict(retries.get(str(index)) or {})
            if state.get('retry_id') != retry_id:
                raise ValueError('รอบแก้เสียงซ้ำเปลี่ยนแล้ว')
            if state.get('status') == 'complete':
                return manifest
            from core.scene_pipeline import ScenePipeline
            row = ScenePipeline(self._folder(job_id)).get(index)
            if row.get('phase') != 'complete' or row.get('speech_retry_id') != retry_id:
                raise ValueError('คลิปฉากใหม่ยังไม่พร้อม')
            state['status'] = 'complete'
            state['new_segment_sha256'] = row.get('segment_sha256')
            retries[str(index)] = state
            manifest['flow_speech_retries'] = retries
            self._save(manifest)
            return manifest

    def attach_flow_fallback_clip(self, job_id, shot_index, source_path, reason=""):
        with self._manifest_lock:
            return self._attach_flow_fallback_clip_locked(job_id, shot_index, source_path, reason)

    def _attach_flow_fallback_clip_locked(self, job_id, shot_index, source_path, reason=""):
        """Checkpoint one local-motion scene separately from real Flow clips."""
        folder = self._folder(job_id)
        manifest = self.get(job_id)
        if manifest.get("story_image_fallbacks"):
            raise ValueError("งานมีฉากใช้ภาพสำรองจากการปฏิเสธ • ประกอบในโปรแกรมเท่านั้น ไม่ส่งต่อ Google Flow")
        from core.scene_video_plan import provider_for, enabled as has_video_plan, verified_asset
        if provider_for(manifest, int(shot_index or 0)) != "google_flow":
            raise ValueError("Story Job นี้ไม่ได้เลือกสร้างวิดีโอด้วย Google Flow")
        shot_index = int(shot_index or 0)
        count = int(manifest.get("scene_count") or 0)
        if not 1 <= shot_index <= count:
            raise ValueError("ลำดับฉากสำรองไม่ถูกต้อง")
        if has_video_plan(manifest) and verified_asset(folder, manifest, shot_index, fresh=True):
            raise ValueError('ฉากนี้มีคลิปที่เก็บไว้แล้ว • ไม่ใช้คลิปสำรองทับ')
        policy_history = self._authenticated_flow_local_fallback_history(manifest, shot_index)
        latest_policy = dict(policy_history[-1]) if policy_history else {}
        if not latest_policy or str(latest_policy.get("action") or "") != "local_motion_fallback":
            raise ValueError(
                f"ฉาก {shot_index} ยังไม่มี Checkpoint ยืนยันที่กำหนด action=local_motion_fallback"
            )
        clips = dict(manifest.get("flow_clips") or {})
        real_relative = str(clips.get(str(shot_index)) or "")
        if real_relative and (folder / real_relative).is_file():
            raise ValueError(f"ฉาก {shot_index} มีคลิป Google Flow จริงแล้ว จึงไม่ใช้ภาพนิ่งทับ")
        source = Path(source_path)
        if not source.is_file() or source.suffix.lower() not in self.VIDEO_EXTENSIONS:
            raise ValueError("ไฟล์คลิปสำรองจากภาพนิ่งไม่ถูกต้อง")
        target = working_video_folder(folder) / f"local_motion_scene_{shot_index:02d}{source.suffix.lower()}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        fallback_clips = dict(manifest.get("flow_fallback_clips") or {})
        fallback_clips[str(shot_index)] = str(target.relative_to(folder))
        metadata = dict(manifest.get("flow_fallback_metadata") or {})
        attachment = latest_policy.get("failure_code") == FLOW_ATTACHMENT_UNCONFIRMED
        metadata[str(shot_index)] = {
            "source_type": "story_local_motion_fallback",
            "reason": str(reason or latest_policy.get("reason") or "Google Flow terminal policy denial")[:1000],
            "failure_code": latest_policy.get("failure_code", "FLOW_POLICY_BLOCKED"),
            "failure_category": "attachment_unconfirmed" if attachment else "policy",
            "flow_run_id": str(latest_policy.get("flow_run_id") or ""),
            "failure_card_fingerprint": str(latest_policy.get("failure_card_fingerprint") or ""),
            "image_path": str(latest_policy.get("image_path") or f"generated{os.sep}scene_{shot_index:02d}.png"),
            "image_sha256": str(latest_policy.get("image_sha256") or ""),
            "prompt_sha256": str(latest_policy.get("prompt_sha256") or ""),
            "attachment_attempt" if attachment else "policy_attempt": int(latest_policy.get("attempt") or 1),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        prompt_retries = dict(manifest.get("flow_prompt_retries") or {})
        retry_state = dict(prompt_retries.get(str(shot_index)) or {})
        if retry_state:
            retry_state.update({
                "status": "local_motion_fallback_ready",
                "fallback_clip_path": str(target.relative_to(folder)),
                "fallback_saved_at": metadata[str(shot_index)]["created_at"],
            })
            prompt_retries[str(shot_index)] = retry_state
        ready = all(
            (folder / str(clips.get(str(index)) or fallback_clips.get(str(index)) or "")).is_file()
            for index in range(1, count + 1)
        )
        manifest.update({
            "video_ai_provider": "flow",
            "flow_fallback_clips": fallback_clips,
            "flow_fallback_metadata": metadata,
            "flow_prompt_retries": prompt_retries,
            "flow_fallback_count": len(fallback_clips),
            "flow_clip_count": len(clips),
            "flow_scene_count": len(clips) + len(fallback_clips),
            "flow_video_status": "ready" if ready else "waiting_downloads",
            "video_status": "clips_ready" if ready else "collecting_clips",
            "video_source_type": "google_flow_story_hybrid_clips",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save(manifest)
        return manifest

    def save_video(self, job_id, source, plan):
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            pending = self._save_video_checkpoint_locked(job_id, source, plan)
        completion_id = pending["video_completion_token"]
        # Cover rendering must not hold the manifest lock and block cancellation.
        self._ensure_completion_cover(job_id, completion_id=completion_id)
        with self._manifest_lock, store.locked():
            covered = self.get(job_id)
            self._assert_video_completion_current(covered, completion_id)
            covered.update({
                "status": "ready", "video_status": "ready", "pipeline_stage": "complete",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._save(covered)
            return covered

    @staticmethod
    def _assert_video_completion_current(manifest, completion_id):
        if manifest.get("cancel_requested") or manifest.get("status") == "cancelled":
            raise ValueError("Story Job นี้ถูกผู้ใช้ยกเลิกแล้ว • เก็บวิดีโอเดิมไว้")
        if (manifest.get("video_completion_token") != completion_id
                or manifest.get("status") != "rendered_waiting_cover"
                or manifest.get("video_status") != "waiting_cover"
                or manifest.get("pipeline_stage") != "cover"):
            raise ValueError("สถานะงานเปลี่ยนระหว่างทำปก • ไม่ใช้ผลรอบเก่าทับการทำงานปัจจุบัน")

    def _save_video_checkpoint_locked(self, job_id, source, plan):
        folder = self._folder(job_id)
        source = Path(source)
        if not source.is_file():
            raise ValueError("ไม่พบวิดีโอเรื่องเล่า")
        manifest = self.get(job_id)
        if manifest.get("cancel_requested"):
            raise ValueError("Story Job นี้ถูกผู้ใช้ยกเลิกแล้ว")
        plan = dict(plan or {})
        if manifest.get("story_image_fallbacks"):
            plan.update(story_image_fallbacks=copy.deepcopy(manifest["story_image_fallbacks"]),
                        reused_image_count=len(manifest["story_image_fallbacks"]),
                        generated_image_count=int(manifest.get("scene_count") or 0) - len(manifest["story_image_fallbacks"]))
        planned_source_type = str(plan.get("source_type") or "").strip()
        video_generation_mode = self._video_generation_mode(manifest.get("video_generation_mode"))
        from core.scene_video_plan import enabled as has_video_plan, ordered_assets
        planned_assets = None
        if has_video_plan(manifest):
            planned_assets = ordered_assets(folder, manifest, fresh=True)
            expected = [{key: row[key] for key in ('index', 'provider', 'sha256')} for row in planned_assets]
            if plan.get('scene_video_sources') != expected or not expected:
                raise ValueError('แหล่งคลิปที่ประกอบไม่ตรงแผนรายฉาก • เก็บ Checkpoint ไว้')
            providers = {row['provider'] for row in planned_assets}
            expected_type = ('mixed_ai_story_composite' if len(providers) > 1 else
                'meta_ai_story_composite' if providers == {'meta_ai'} else
                'google_flow_story_composite' if providers == {'google_flow'} else
                'google_flow_story_hybrid_fallback')
            if planned_source_type != expected_type:
                raise ValueError('ประเภทผลลัพธ์ไม่ตรงแหล่งคลิปจริงรายฉาก')
            plan.update(flow_clip_count=sum(row['provider'] == 'google_flow' for row in planned_assets),
                        meta_clip_count=sum(row['provider'] == 'meta_ai' for row in planned_assets),
                        local_clip_count=sum(row['provider'] == 'local' for row in planned_assets))
        elif video_generation_mode == "google_flow":
            count = int(manifest.get("scene_count") or 0)
            clips = dict(manifest.get("flow_clips") or {})
            fallback_clips = dict(manifest.get("flow_fallback_clips") or {})
            complete_sources = count > 0 and all(
                (folder / str(clips.get(str(index)) or fallback_clips.get(str(index)) or "")).is_file()
                for index in range(1, count + 1)
            )
            pure_flow = (
                planned_source_type == "google_flow_story_composite"
                and not fallback_clips and len(clips) >= count and complete_sources
            )
            explicit_hybrid = (
                planned_source_type == "google_flow_story_hybrid_fallback"
                and bool(fallback_clips) and complete_sources
            )
            if not (pure_flow or explicit_hybrid):
                raise ValueError(
                    f"เลือก Google Flow ไว้ แต่มีคลิปจริงเพียง {len(clips)}/{count} ฉากจาก Google Flow และคลิปสำรองที่ระบุชัด "
                    f"{len(fallback_clips)}/{count} ฉาก • งานถูกเก็บไว้ที่ Checkpoint และจะไม่ปลอมภาพนิ่งเป็นคลิป Flow"
                )
        has_drama_footage = (
            manifest.get("job_type") == "drama_episode"
            and int(plan.get("footage_count") or 0) > 0
        )
        # Keep the acquisition source truthful at the top level.  Drama
        # footage is a later content-mix stage and must not hide that one or
        # more Flow scenes were supplied by an explicit local-motion fallback.
        if planned_assets is not None:
            source_type = planned_source_type
        elif video_generation_mode == 'meta_ai':
            from core.meta_video import MetaVideoManager
            MetaVideoManager(self).clips(job_id)
            if planned_source_type != 'meta_ai_story_composite':
                raise ValueError('ผลลัพธ์ไม่ตรงผู้สร้างวิดีโอ Meta AI')
            source_type = planned_source_type
        elif video_generation_mode == "google_flow":
            source_type = planned_source_type
        elif has_drama_footage:
            source_type = "drama_mixed_media"
        else:
            source_type = "story_image_sequence"
        manifest.update({
            "status": "rendered_waiting_cover",
            "video_status": "waiting_cover",
            "video_path": str(source.relative_to(folder)),
            "video_source_type": source_type,
            "video_content_mix_type": "drama_mixed_media" if has_drama_footage else "",
            "render_plan": plan,
            "video_completion_token": uuid.uuid4().hex,
            "pipeline_stage": "cover",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        manifest.pop("last_error", None)
        self._save(manifest)
        return manifest

    def save_cover(self, job_id, source):
        folder = self._folder(job_id)
        source = Path(source).resolve()
        if not source.is_file() or folder.resolve() not in source.parents:
            raise ValueError("ไม่พบไฟล์ปก Shorts ในโปรเจกต์")
        try:
            with Image.open(source) as opened:
                opened.verify()
            with Image.open(source) as opened:
                width, height = opened.size
        except (OSError, ValueError):
            raise ValueError("ไฟล์ปก Shorts เปิดอ่านไม่ได้") from None
        if self.get(job_id).get('long_video'):
            if width <= height:
                raise ValueError('ปกคลิปยาวต้องเป็นแนวนอน')
        elif height <= width:
            raise ValueError("ปก Shorts ต้องเป็นภาพแนวตั้ง")
        manifest = self.get(job_id)
        manifest.update({
            "cover_path": str(source.relative_to(folder)),
            "cover_status": "ready",
            "cover_size": [int(width), int(height)],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save(manifest)
        return manifest

    def ensure_story_cover(self, job_id):
        """Create or repair the dedicated 9:16 cover for a standalone Story Shorts job."""
        manifest = self.get(job_id)
        if manifest.get("job_type") != "story_short":
            return manifest
        return self._ensure_completion_cover(job_id)

    def _ensure_completion_cover(self, job_id, *, completion_id=None):
        """Create the required real-image cover before a Story/Drama is complete."""
        folder = self._folder(job_id).resolve()
        manifest = self.get(job_id)
        if completion_id is not None:
            self._assert_video_completion_current(manifest, completion_id)
        changes = ensure_cover(self.project_root, folder, manifest)
        store = self._manifest_store(folder / "job.json")
        with self._manifest_lock, store.locked():
            current = self.get(job_id)
            if completion_id is not None:
                self._assert_video_completion_current(current, completion_id)
            # Preserve a manual/AI cover selected while the local cover rendered,
            # and merge into the fresh job so unrelated user settings also win.
            if (changes and current.get("cover_revision") == manifest.get("cover_revision")
                    and current.get("cover_path") == manifest.get("cover_path")):
                current.update(changes)
                self._save(current)
            return current

    def repair_program_cta(self, job_id):
        """Remove only the exact old program-added suffix before any paid voice.

        AI-authored narration and any existing audio/checkpoints stay intact.
        """
        manifest = self.get(job_id)
        if manifest.get('storytelling_options') or story_performance.enabled(manifest) or authored_product_script(manifest):
            return manifest
        if not manifest.get("engagement_cta_added_by_program") or manifest.get("voice_job_id") or manifest.get("voice_status") == "ready":
            return manifest
        topic = str(manifest.get("topic") or "เรื่องนี้").strip()
        old = f"ถ้าเรื่องนี้ทำให้คุณรู้สึกอะไรบางอย่าง กดหัวใจไว้ แล้วคอมเมนต์บอกหน่อยว่า คุณคิดอย่างไรกับ {topic}"
        narration = str(manifest.get("narration_script") or "")
        if not narration.endswith(old):
            return manifest
        narration = narration[:-len(old)].rstrip()
        scenes = list(manifest.get("scene_narrations") or [])
        if scenes and scenes[-1].endswith(old):
            scenes[-1] = scenes[-1][:-len(old)].rstrip()
        narration, scenes, added = self._ensure_engagement_cta(narration, scenes, topic)
        manifest.update(narration_script=narration, scene_narrations=scenes,
                        engagement_cta_added_by_program=added, cta_repair_version=1)
        self._save(manifest)
        (self._folder(job_id) / "captions" / "narration_script.txt").write_text(narration, encoding="utf-8")
        return manifest

    def mark_running(self, job_id, stage="chatgpt"):
        manifest = self.get(job_id)
        stage = str(stage or "chatgpt")
        if stage == "chatgpt" and manifest.get("ai_status") != "ready":
            from core.ai_web_resume import ai_web_resume_target
            pending = ai_web_resume_target(self._folder(job_id), manifest)
            if pending and pending.get('stage') == 'analysis':
                manifest['ai_resume_checkpoint'] = pending
            manifest["video_status"] = "waiting_story_images"
        manifest.pop("last_error", None)
        manifest.update({
            "status": "running", "pipeline_stage": stage,
            "cancel_requested": False,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save(manifest)
        return manifest

    def mark_recovering(self, job_id, stage, reason=""):
        manifest = self.get(job_id)
        attempts = int(manifest.get("auto_recovery_attempts") or 0) + 1
        total_attempts = int(manifest.get("auto_recovery_total") or 0) + 1
        manifest.pop("last_error", None)
        manifest.update({
            "status": "running",
            "pipeline_stage": str(stage or manifest.get("pipeline_stage") or "chatgpt"),
            "auto_recovery_attempts": attempts,
            "auto_recovery_total": total_attempts,
            "last_recovery_reason": str(reason or "")[:1000],
            "cancel_requested": False,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save(manifest)
        return manifest

    def reset_recovery_attempts(self, job_id):
        manifest = self.get(job_id)
        manifest.pop("auto_recovery_attempts", None)
        manifest.pop("last_recovery_reason", None)
        self._save(manifest)
        return manifest

    def mark_cancelled(self, job_id, stage="", reason="ผู้ใช้ยกเลิกการทำงาน"):
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            return self._mark_cancelled_locked(job_id, stage, reason)

    def _mark_cancelled_locked(self, job_id, stage, reason):
        manifest = self.get(job_id)
        manifest.update({
            "status": "cancelled", "video_status": "cancelled",
            "pipeline_stage": str(stage or manifest.get("pipeline_stage") or ""),
            "cancel_requested": True, "cancel_reason": str(reason or "ผู้ใช้ยกเลิกการทำงาน")[:500],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save(manifest)
        return manifest

    def mark_failed(self, job_id, stage="", reason="งานทำไม่สำเร็จ"):
        store = self._manifest_store(self._folder(job_id) / "job.json")
        with self._manifest_lock, store.locked():
            return self._mark_failed_locked(job_id, stage, reason)

    def _mark_failed_locked(self, job_id, stage, reason):
        manifest = self.get(job_id)
        if manifest.get("status") == "cancelled" or manifest.get("cancel_requested"):
            return manifest
        manifest.update({
            "status": "error", "video_status": "error",
            "pipeline_stage": str(stage or manifest.get("pipeline_stage") or ""),
            "last_error": str(reason or "งานทำไม่สำเร็จ")[:1000],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save(manifest)
        return manifest

    def reopen_google_flow_checkpoint(self, job_id, reason="ทำต่อด้วยคลิป Google Flow จริง"):
        """Retire a legacy motion-fallback result without deleting its files."""
        manifest = self.get(job_id)
        if self._video_generation_mode(manifest.get("video_generation_mode")) != "google_flow":
            raise ValueError("Story Job นี้ไม่ได้เลือกสร้างวิดีโอด้วย Google Flow")
        previous_video = str(manifest.get("video_path") or "").strip()
        previous_plan = dict(manifest.get("render_plan") or {})
        if previous_video:
            manifest["rejected_fallback_video_path"] = previous_video
        if previous_plan:
            manifest["rejected_fallback_render_plan"] = previous_plan
        clips = dict(manifest.get("flow_clips") or {})
        manifest.update({
            "status": "error",
            "video_status": "collecting_clips" if clips else "waiting_flow",
            "video_source_type": "google_flow_story_clips" if clips else "google_flow_pending",
            "video_path": "",
            "pipeline_stage": "google_flow",
            "flow_fallback_used": False,
            "flow_fallback_reason": "",
            "cleanup_status": "checkpoint_reopened",
            "cancel_requested": False,
            "last_error": str(reason or "ทำต่อด้วยคลิป Google Flow จริง")[:1000],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        manifest.pop("render_plan", None)
        manifest.pop("final_validation", None)
        manifest["final_validation_status"] = "superseded_wrong_source"
        self._save(manifest)
        return manifest

    def _write_request(self, folder, job):
        from core.analysis_json_transport import analysis_json_prompt
        self._write_request_content(folder, job)
        target = folder / 'prompts' / 'chatgpt_request.txt'
        from core.speech_delivery import attach_request, enabled
        prompt = target.read_text(encoding='utf-8')
        if enabled(job):
            request_path = folder / 'ai_request.json'
            request = json.loads(request_path.read_text(encoding='utf-8'))
            prompt, request = attach_request(job, prompt, request)
            request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
        from core.product_editorial import enabled as editorial_enabled, instruction as editorial_instruction
        if editorial_enabled(job):
            request_path = folder / 'ai_request.json'
            request = json.loads(request_path.read_text(encoding='utf-8'))
            request['product_editorial_version'] = 1
            request['product_editorial_instruction'] = editorial_instruction(job)
            prompt += '\n\n' + request['product_editorial_instruction']
            request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
        target.write_text(analysis_json_prompt(prompt), encoding='utf-8')

    def _write_request_content(self, folder, job):
        from core.story_visual_plan import SCENE_ACTION_RULE
        if (job.get('long_video') or {}).get('version') == 2:
            self._write_long_video_request(folder, job)
            return
        if job.get('storytelling_options'):
            prompt, request = storytelling.build_request(job)
            request['visual_depiction_instruction'] = STORY_VISUAL_DEPICTION_INSTRUCTION
            prompt += '\n\n' + STORY_VISUAL_DEPICTION_INSTRUCTION
            (folder / 'prompts' / 'chatgpt_request.txt').write_text(prompt + '\n\n' + COVER_PROMPT, encoding='utf-8')
            (folder / 'ai_request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
            return
        if job.get("job_type") == "drama_episode":
            self._write_drama_request(folder, job)
            return
        if job.get('product_story') and not job.get('flow_smoke_test') and not job.get('long_video'):
            from core.product_story import compact_product_analysis_prompt
            visual_style = story_style_instruction(job.get('visual_style'), job.get('visual_style_custom'))
            prompt = compact_product_analysis_prompt(job, visual_style)
            if prompt:
                request = {"schema_version": 1, "mode": "story", "job_id": job["id"],
                           "prompt_file": "prompts/chatgpt_request.txt", "image_files": job["source_images"],
                           "image_count": job["scene_count"], "prompt_field": "scene_prompts",
                           "required_fields": ["video_title", "video_description", "narration_script",
                                               "visual_bible", "scene_narrations", "scene_prompts", "scene_durations"],
                           "visual_style_instruction": visual_style,
                           "visual_render_instruction": story_render_instruction(job.get('visual_style'), job.get('visual_style_custom')),
                           "visual_depiction_instruction": STORY_VISUAL_DEPICTION_INSTRUCTION}
                prompt = self._scene_dialogue_request(job, request, prompt)
                if job.get('product_script_options') is not None:
                    request['product_script_options'] = normalize_product_script(job['product_script_options'])
                if authored_product_script(job):
                    request['product_script_instruction'] = script_instruction(job)
                from core.creative_brief import attach_request
                prompt, request = attach_request(job, prompt, request)
                if short_film_ad(job):
                    request['required_fields'].append('product_film_plan')
                if job.get('story_content_contract') == {'version': 1}:
                    request['story_content_contract'] = {'version': 1}
                    request['required_named_entities'] = requested_story_names(job)
                    request['story_source_aliases'] = story_source_aliases(job)
                    request['required_fields'].extend(['story_entities', 'scene_entities'])
                    prompt += ('\nSTORY CONTENT CONTRACT v1: ตอบ story_entities=[{id,name,aliases,visual_identity}] '
                               'และ scene_entities เป็น array ของชื่อ id ที่เห็นจริงในแต่ละฉาก จำนวนตรงกับฉาก; '
                               'ถ้าไม่มีตัวละครชื่อเฉพาะใช้ story_entities=[] และ scene_entities เป็น [] ทุกฉาก '
                               'อย่านับชื่อสินค้าเป็นตัวละครหรือเปลี่ยนชื่อบุคคลที่ผู้ใช้ระบุ')
                prompt += '\nปกคลิปถ้าตอบได้: cover={headline,alternatives,scene_index,emphasis,theme,position}; ไม่ใส่ข้อความลงภาพฉาก'
                (folder / 'prompts' / 'chatgpt_request.txt').write_text(prompt, encoding='utf-8')
                (folder / 'ai_request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
                return
        topic = job.get("topic") or "ให้ตั้งหัวข้อจากเรื่องที่ผู้ใช้ให้มา"
        narrative_rule = ('เขียน narration_script ภาษาไทยบุคคลที่หนึ่ง เป็นคำพูดของผู้รีวิวที่มีบุคลิกคงที่ เปิดด้วยเหตุการณ์ชวนติดตามใน 2 วินาทีแรก แล้วเชื่อมเข้าสินค้าตาม PRODUCT STORY-FIRST REVIEW'
                          if story_first_review(job) else 'เขียน narration_script ภาษาไทยสำหรับ AI Voice อ่านลื่น เข้าใจง่าย มีฮุกใน 2 วินาทีแรก และเล่าเป็นเรื่องต่อเนื่องจนจบ')
        ending_rule = ('ฉากสุดท้ายปิดเหตุการณ์ให้จบอย่างเป็นธรรมชาติ ไม่บังคับขายหรือชวนกดหัวใจ/คอมเมนต์'
                       if story_first_review(job) else 'ฉากสุดท้ายต้องปิดเรื่องให้จบก่อน แล้วต่อด้วยคำชวนแบบเป็นธรรมชาติให้ผู้ชมกดหัวใจ และตั้งคำถามเฉพาะเรื่องเพื่อชวนคอมเมนต์ ห้ามใช้ประโยคกว้าง ๆ ซ้ำเดิม')
        last_scene_rule = ('scene_narrations รายการสุดท้ายจบเรื่องด้วยน้ำเสียงเดิม ไม่เติมคำขายหรือ CTA ส่วน scene_prompt สุดท้ายเป็นบทสรุปโดยไม่มีตัวอักษร'
                           if story_first_review(job) else 'scene_narrations รายการสุดท้ายต้องรวมประโยคปิดเรื่องและคำชวนกดหัวใจ/คอมเมนต์ ส่วน scene_prompt สุดท้ายต้องเป็นภาพบทสรุปของเรื่องโดยไม่มีตัวอักษร')
        if short_film_ad(job):
            narrative_rule = 'เขียนหนังสั้นสมมติเรื่องเดียว เริ่มจากเหตุการณ์ที่ยังไม่ขายสินค้า แล้วค่อยเชื่อมสินค้าอย่างมีเหตุผลตาม PRODUCT SHORT FILM AD'
            ending_rule = 'ปิดปมจากต้นเรื่องก่อน คำชวนดูตะกร้าใช้เฉพาะที่กำหนดใน product_script_options ไม่เพิ่มคำชวนไลก์หรือคอมเมนต์'
            last_scene_rule = 'scene_narrations ต้องเป็นบทพูดเท่านั้น แยกคำบรรยายการกระทำไว้ในแผนฉากและ scene_prompts ไม่บังคับให้ตัวละครหันมารีวิวทุกฉาก'
        if creative_product_script(job):
            narrative_rule = 'เขียนบทสินค้าเรื่องเดียวตาม PRODUCT CREATIVE SCRIPT v3 และข้อเท็จจริงที่ให้มา'
            ending_rule = 'ปิดเหตุการณ์อย่างเป็นธรรมชาติ ไม่เติมคำขายหรือคำชวนมีส่วนร่วมโดยอัตโนมัติ'
            last_scene_rule = 'บทฉากสุดท้ายปิดเรื่องโดยไม่ทวนฮุกหรือชื่อสินค้า คำพูดแยกจากคำกำกับฉาก'
        scene_input_rule = ("ไม่เขียนเพียงว่าเหมือนภาพก่อนหน้าและไม่กำหนดให้ต้องอัปโหลดภาพฉากก่อนหน้า"
                            if job.get("source_images") else "กำหนดภาพแต่ละฉากจากคำบรรยายข้อความที่ครบถ้วน")
        source_note = (
            "มีไฟล์รูปอ้างอิงที่ผู้ใช้ให้ไว้ ใช้เฉพาะรูปที่แนบสำเร็จจริงร่วมกับรายละเอียดข้อความเพื่อรักษาตัวละครและสิ่งสำคัญเดิม ไม่สมมติว่ามีภาพฉากก่อนหน้า"
            if job.get("source_images") else
            "สร้างภาพใหม่จากข้อความ ให้กำหนดตัวละครและภาพจำที่คงเดิมทุกฉากใน visual_bible ระบุหน้าตา เสื้อผ้า สถานที่ และสิ่งที่มองเห็นให้ครบ"
        )
        prompt = SCENE_ACTION_RULE + '\n\n' + f"""สร้างแพ็กเกจคลิปเรื่องเล่า Shorts ภาษาไทยแนวตั้ง 9:16

หัวข้อ: {topic}
เรื่องที่ผู้ใช้ให้มา: {job.get('story_input') or 'ให้คิดเรื่องจากหัวข้ออย่างสร้างสรรค์'}
จำนวนฉาก: {job['scene_count']}
รูปหลัก: {source_note}
แนวภาพที่ผู้ใช้เลือก: {story_style_instruction(job.get('visual_style'), job.get('visual_style_custom'))}

ข้อกำหนด:
1. เขียน video_title ที่ชวนคลิกแต่ไม่หลอก และ video_description พร้อมแฮชแท็กที่เกี่ยวข้อง
2. {narrative_rule}
3. สร้าง visual_bible ระบุหน้าตา/เสื้อผ้า/สถานที่/โทนสี/แสง/เลนส์ เพื่อให้ทุกภาพเป็นโลกเดียวกัน
4. สร้าง scene_narrations และ scene_prompts อย่างละ {job['scene_count']} รายการพอดี เรียงตามเนื้อเรื่อง
5. ทุก scene_prompt ต้องอ่านได้ด้วยตัวเอง (self-contained) ระบุชื่อตัวละคร รูปลักษณ์คงที่ สถานที่ และการกระทำที่มองเห็นจากเรื่องและ visual_bible เป็นข้อความครบในฉากนั้น {scene_input_rule} ฉากแรกสร้างภาพจำตาม text bible โดยคงชื่อ ตัวตน และอายุเฉพาะเมื่อผู้ใช้ระบุไว้ ไม่แต่งตัวเลขอายุเด็กหรือเพิ่มเด็กมนุษย์เองเพื่อแทนผลไม้ สัตว์ หรือสิ่งของที่ผู้ใช้ต้องการให้เป็นตัวละคร ภาพแนวตั้ง 9:16 ตามแนวภาพที่ผู้ใช้เลือก มี foreground/midground/background และไม่มีตัวอักษรหรือลายน้ำ
6. {ending_rule}
7. {last_scene_rule}
8. scene_durations จำนวน {job['scene_count']} ค่า ช่วง 3-7 วินาที
9. บทพากย์ต้องเขียนตัวเลขและคำอังกฤษเป็นคำอ่านภาษาไทยเพื่อให้ Voice AI อ่านถูก ห้ามเหลือตัวอักษร A-Z ใน narration_script หรือ scene_narrations เช่น Doctor Doom Supreme ต้องเขียนว่า ด็อกเตอร์ ดูม ซูพรีม
10. scene_prompts ต้องรักษาชื่อตัวละคร จักรวาล เหตุการณ์ ความสัมพันธ์ และภาพจำเดิมจากเรื่อง สไตล์ภาพเปลี่ยนเฉพาะวิธีวาด ไม่แทนตัวละครเดิมด้วยตัวละครทั่วไปหรือเรื่องใหม่ และไม่ใช้ใบหน้าของนักแสดงโดยอัตโนมัติ
11. ถ้าฉากต้องสื่อถึงตัวบุคคลจริงหรือบุคคลสาธารณะ ให้เก็บชื่อไว้ใน video_title, video_description และบทเล่าที่อิงข้อมูลผู้ใช้ ส่วนภาพที่แทนบุคคลจริงนั้นให้ใช้วัตถุ สถานที่ สถาปัตยกรรม หรือสภาพแวดล้อมจากเรื่อง โดยไม่สร้างใบหน้า รูปร่าง ภาพเหมือน หรือรูปลักษณ์เลียนแบบบุคคลนั้น และห้ามแต่งคำกล่าวอ้างใหม่ แยกชื่อนักแสดงจากตัวละครสมมติอย่างชัดเจน: การเอ่ยชื่อนักแสดงในบทวิเคราะห์ไม่ใช่คำสั่งให้ใช้ใบหน้านักแสดง และไม่ทำให้ต้องลบตัวละครสมมติออกจากภาพ ตัวละครในเรื่องยังคงชื่อ ตัวตน เครื่องแต่งกาย และภาพจำเดิมตามข้อ 10

เพิ่ม pronunciation_notes เป็น object คำต้นฉบับ:คำอ่านภาษาไทย สำหรับชื่อเฉพาะหรือคำต่างประเทศ โดยบทพากย์และทุก scene_narration ต้องใช้คำอ่านไทยอยู่แล้ว
เพิ่ม flow_shot_prompts เป็นร่างพรอมต์การเคลื่อนไหวสั้นสำหรับแต่ละฉาก เน้นเหตุการณ์ สิ่งแวดล้อม และกล้อง ไม่ทวนรูปลักษณ์ทั้งก้อน ยังไม่อ้างว่าได้ตรวจภาพจริงแล้ว
ตอบเป็น JSON เท่านั้น โดยมี job_id, video_title, video_description, narration_script, pronunciation_notes, visual_bible, scene_narrations, scene_prompts, scene_durations และ warnings"""
        if job.get('flow_smoke_test'):
            duration = str((job.get('flow_settings') or {}).get('duration') or '8s')
            prompt = '\n'.join(line for line in prompt.splitlines() if not line.startswith(('2. ', '6. ', '7. ', '8. ')))
            prompt += (f'\nโหมดทดสอบหนึ่งฉาก ความยาววิดีโอ {duration}: ไม่เพิ่มฮุก คำชวนกดไลก์หรือคอมเมนต์ '
                       'ใช้บทพูดที่ผู้ใช้กำหนดเท่านั้น ไม่ต่อคำบรรยายเพิ่ม ถ้าไม่ได้ระบุบทพูดให้เขียนสั้นพอดีเวลา '
                       'scene_durations มีหนึ่งค่าตรงความยาววิดีโอที่ระบุ ภาพนิ่งบรรยายเพียงจังหวะเดียว '
                       'ส่วนลำดับการเคลื่อนไหวให้เก็บใน flow_shot_prompts ไม่สั่งหลายจังหวะลงภาพเดียว')
        (folder / "prompts" / "chatgpt_request.txt").write_text(prompt + "\n\n" + COVER_PROMPT, encoding="utf-8")
        request = {"schema_version": 1, "mode": "story", "job_id": job["id"], "prompt_file": "prompts/chatgpt_request.txt", "image_files": job["source_images"], "image_count": job["scene_count"], "prompt_field": "scene_prompts", "required_fields": ["video_title", "video_description", "narration_script", "visual_bible", "scene_narrations", "scene_prompts", "scene_durations"]}
        request["visual_style_instruction"] = story_style_instruction(job.get("visual_style"), job.get("visual_style_custom"))
        request["visual_render_instruction"] = story_render_instruction(job.get("visual_style"), job.get("visual_style_custom"))
        request["visual_depiction_instruction"] = STORY_VISUAL_DEPICTION_INSTRUCTION
        prompt += "\n\n" + STORY_VISUAL_DEPICTION_INSTRUCTION
        if job.get("story_content_contract") == {"version": 1}:
            request["story_content_contract"] = {"version": 1}
            request["required_named_entities"] = requested_story_names(job)
            request["story_source_aliases"] = story_source_aliases(job)
            request["required_fields"].extend(["story_entities", "scene_entities"])
            prompt += "\n\n" + story_content_instruction(job)
        if job.get('long_video'):
            seconds = job['long_video']['duration_seconds']
            prompt = prompt.replace('แนวตั้ง 9:16', 'แนวนอน 16:9').replace('เรื่องเล่า Shorts', 'คลิปยาว')
            prompt = prompt.replace('ช่วง 3-7 วินาที', 'ช่วง 3-30 วินาที จัดเวลาให้เหมาะกับบทพากย์แต่ละฉาก')
            prompt += f'\nความยาวเป้าหมาย {seconds} วินาที เขียนบทเต็มสำหรับเวลานี้ แบ่งบทครบทุกฉากตามลำดับ ไม่ย่อด้วยจุดไข่ปลา ผลรวม scene_durations ต้องเท่ากับ {seconds} วินาที ทุกภาพแนวนอน16:9'
            request['aspect_ratio'] = '16:9'
        prompt = self._scene_dialogue_request(job,request,prompt)
        from core.product_story import story_brief
        prompt += story_brief(job)
        if job.get('product_script_options') is not None:
            request['product_script_options'] = normalize_product_script(job['product_script_options'])
        if authored_product_script(job):
            request['product_script_instruction'] = script_instruction(job)
            if not job.get('product_story'):
                prompt += '\n' + script_instruction(job)
        if short_film_ad(job):
            request['required_fields'].append('product_film_plan')
        if job.get('cast_creation'):
            prompt = story_brief(job)
        from core.creative_brief import attach_request
        prompt, request = attach_request(job, prompt, request)
        (folder / "prompts" / "chatgpt_request.txt").write_text(prompt + "\n\n" + COVER_PROMPT, encoding="utf-8")
        (folder / "ai_request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_long_video_request(self, folder, job):
        """Start with a small whole-story outline, never a 50-scene JSON reply."""
        from core.long_video import chapter_ranges
        count = int(job['scene_count'])
        chapters = len(chapter_ranges(count))
        request = {
            'schema_version': 2, 'mode': 'story', 'job_id': job['id'],
            'prompt_file': 'prompts/chatgpt_request.txt', 'image_files': job['source_images'],
            'image_count': count, 'prompt_field': 'scene_prompts', 'aspect_ratio': '16:9',
            'long_video_chapters': {'version': 2, 'batch_size': 10, 'chapter_count': chapters},
            'story_content_contract': {'version': 1},
            'required_named_entities': requested_story_names(job),
            'story_source_aliases': story_source_aliases(job),
            'required_fields': ['video_title', 'video_description', 'narration_script',
                                'visual_bible', 'story_entities', 'scene_entities',
                                'scene_narrations', 'scene_prompts', 'scene_durations'],
            'visual_style_instruction': story_style_instruction(job.get('visual_style'), job.get('visual_style_custom')),
            'visual_render_instruction': story_render_instruction(job.get('visual_style'), job.get('visual_style_custom')),
            'visual_depiction_instruction': STORY_VISUAL_DEPICTION_INSTRUCTION,
        }
        prompt = (
            f"วางโครงเรื่องเล่ายาวภาษาไทยสำหรับวิดีโอแนวนอน 16:9 จำนวน {count} ภาพ "
            f"ความยาวเป้าหมาย {job['long_video']['duration_seconds']} วินาที\n"
            f"หัวข้อ: {job.get('topic') or 'ตั้งชื่อจากเรื่อง'}\n"
            f"ข้อมูลจากผู้ใช้: {job.get('story_input') or 'คิดเรื่องใหม่จากหัวข้อ'}\n"
            f"ทำโครงเรื่อง {chapters} ชุด ชุดละไม่เกิน 10 ฉาก โดยให้เหตุการณ์ต่อเนื่องและจบจริงในชุดสุดท้าย\n"
            "รอบนี้ตอบโครงเรื่องสั้นเท่านั้น ห้ามเขียนบทเต็ม 50 ฉากและห้ามสร้างภาพ\n"
            "video_description ต้องเป็นคำอธิบายพร้อมโพสต์สำหรับผู้ชม 2–3 ประโยค ชวนดูตามหัวข้อจริง "
            "ห้ามใส่เวลาเป้าหมาย จำนวนภาพ จำนวนฉาก จำนวนชุด หรือวิธีผลิต; "
            "hashtags เป็น array แฮชแท็กเฉพาะเรื่อง 3–6 คำ แยกจากคำอธิบาย ไม่ยัดแฮชแท็กซ้ำในข้อความ; "
            "ตอบ JSON object เดียว: job_id, video_title, video_description, hashtags, visual_bible, "
            "story_entities (array ของ {id,name,aliases,visual_identity}; ถ้าไม่มีชื่อเฉพาะใช้ []), "
            f"chapter_beats (array ข้อความ {chapters} รายการ เริ่ม/กลาง/จบไม่ซ้ำ), "
            "pronunciation_notes (object)\n"
            "รักษาชื่อ ตัวละคร และข้อเท็จจริงที่ผู้ใช้ให้ไว้ ไม่ยืดบทด้วยคำซ้ำ "
            "ทุกภาพเป็นแนวนอน 16:9 ไม่มีตัวอักษรบนภาพ\n"
            "เลือกแนวทางที่เหมาะสมเองทันที ตอบเพียงคำตอบเดียว ห้ามเสนอหลายตัวเลือก ห้ามถามกลับหรือรอให้ผู้ใช้ตัดสินใจ"
        )
        (folder / 'prompts' / 'chatgpt_request.txt').write_text(prompt, encoding='utf-8')
        (folder / 'ai_request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')

    @staticmethod
    def _scene_dialogue_request(job, request, prompt):
        if story_performance.enabled(job):
            request['required_fields'].extend(['character_bible', 'scene_dialogue_turns'])
            # Replace narrator/CTA/duration requirements rather than appending
            # contradictory instructions to the original narrated template.
            prompt = '\n'.join(line for line in prompt.splitlines() if not line.startswith(('2. ', '6. ', '7. ', '8. ', '9. ')))
            return prompt + story_performance.request_instruction(job)
        if job.get('scene_pipeline_version') == 1:
            request['required_fields'].append('scene_dialogue_turns')
            prompt += ('\nFor per-scene video then speech: return scene_dialogue_turns, an array with exactly scene_count arrays. '
                       'Each inner array contains ordered spoken turns for ONLY that scene: speaker, text, emotion, pause_after. '
                       'Use the existing allowed speakers (or ผู้บรรยาย). scene_narrations[i] must equal its turns text concatenated in order. '
                       'No speaker labels inside text. dialogue_turns is the flattened array. Do not assign another scene speech here.')
            if short_film_ad(job):
                prompt = prompt.replace('Use the existing allowed speakers (or ผู้บรรยาย).',
                                        'Use the same speaker as product_film_plan.scenes[i].speaker, one speaking character per scene.')
        return prompt

    def _write_drama_request(self, folder, job):
        from core.story_visual_plan import SCENE_ACTION_RULE
        has_references = bool(job.get("source_images"))
        scene_input_rule = ("ไม่เขียนเพียงว่าเหมือนภาพก่อนหน้าและไม่กำหนดให้ต้องอัปโหลดภาพฉากก่อนหน้า"
                            if has_references else "กำหนดภาพแต่ละฉากจากคำบรรยายข้อความที่ครบถ้วน")
        source_note = (
            "มีไฟล์รูปอ้างอิงที่ผู้ใช้ให้ไว้ ใช้เฉพาะรูปที่แนบสำเร็จจริงเป็น Character Reference ร่วมกับ CHARACTER BIBLE ไม่สมมติว่ามีภาพฉากก่อนหน้า"
            if has_references else
            "สร้างภาพใหม่จากข้อความ ให้กำหนดตัวละครและภาพจำที่คงเดิมทุกฉากจาก CHARACTER BIBLE และ visual_bible ระบุหน้าตา เสื้อผ้า สถานที่ และสิ่งที่มองเห็นให้ครบ"
        )
        character_lines = []
        allowed_speakers = []
        for character in job.get("character_bible") or []:
            character_name = str(character.get("name") or "").strip()
            if character_name and character_name not in allowed_speakers:
                allowed_speakers.append(character_name)
            character_lines.append(
                f"- {character.get('name')}: {character.get('role')}; "
                f"รูปลักษณ์/บุคลิกที่ห้ามเปลี่ยน: {character.get('description') or ('ยึดตามรายละเอียดเดิมและรูปอ้างอิงที่แนบสำเร็จจริง' if has_references else 'อธิบายจากข้อมูลตัวละครเดิมเป็น text bible และคงเดิมทุกฉาก ไม่ต้องมีรูปอ้างอิง')}"
            )
        allowed_speakers.append("ผู้บรรยาย")
        allowed_speakers_json = json.dumps(allowed_speakers, ensure_ascii=False)
        character_bible = "\n".join(character_lines) or "กำหนดตัวละครหลักให้ชัดและคงเดิมทุกฉาก"
        is_final = int(job.get("episode_no") or 1) >= int(job.get("episode_count") or 1) and not bool(job.get("open_ended"))
        ending_rule = "ปิดเรื่องให้สมบูรณ์" if is_final else "จบด้วยเหตุการณ์ค้างที่ชวนติดตาม EP ถัดไป โดยไม่ตัดจบแบบไม่มีเหตุผล"
        prompt = SCENE_ACTION_RULE + '\n\n' + f"""สร้างแพ็กเกจละครสั้นภาษาไทยแนวตั้ง 9:16 แบบเป็นตอนต่อเนื่อง

ชื่อซีรีส์: {job.get('series_title') or job.get('topic')}
ตอนปัจจุบัน: EP {job.get('episode_no')} จาก {job.get('episode_count')}
แนวทางตอนนี้:
{job.get('story_input') or 'วางพล็อตตอนนี้ให้ต่อเนื่องจากข้อมูลก่อนหน้า'}

รูปอ้างอิง: {source_note}

CHARACTER BIBLE ที่ต้องยึดทุกภาพและทุก EP:
{character_bible}

ALLOWED SPEAKERS (ต้องใช้ชื่อตรงตามรายการนี้เท่านั้น):
{allowed_speakers_json}

VISUAL BIBLE จากตอนก่อนหน้า:
{json.dumps(job.get('previous_visual_bible') or {}, ensure_ascii=False)}

CONTINUITY STATE จากตอนก่อนหน้า:
{json.dumps(job.get('previous_continuity_state') or {}, ensure_ascii=False)}

สรุปตอนก่อนหน้า: {job.get('previous_episode_summary') or 'นี่คือตอนแรก'}
จุดค้างตอนก่อนหน้า: {job.get('previous_episode_hook') or 'ไม่มี'}

SERIES PLOT BOARD ที่อนุมัติไว้ก่อนเริ่มคิว:
{json.dumps(job.get('plot_board') or [], ensure_ascii=False)}

เป้าหมายของ EP นี้ (ต้องทำตามและห้ามข้ามไปพล็อตของ EP อื่น):
{json.dumps(job.get('planned_episode') or {}, ensure_ascii=False)}

ข้อกำหนดสำคัญ:
1. ให้คงใบหน้า รูปหน้า สีผิว อายุ ทรงผม รูปร่าง เสื้อผ้าหลัก และเครื่องประดับเดิมจาก CHARACTER BIBLE และรูปอ้างอิงที่มีจริงเท่านั้น ห้ามเปลี่ยนคนหรือออกแบบใหม่ หากไม่มีรูปอ้างอิง ให้ใช้รายละเอียดข้อความ ไม่บังคับขอรูปเพิ่ม
2. เขียนเรื่องเป็นละคร มีบทสนทนาที่ฟังเป็นธรรมชาติ มีฮุกใน 2 วินาทีแรก เหตุการณ์ต่อกันอย่างมีเหตุผล และยึด SERIES PLOT BOARD ของ EP นี้
3. สร้าง visual_bible ฉบับล่าสุดและ continuity_state ที่บอกตำแหน่งตัวละคร เสื้อผ้า อุปกรณ์ ความสัมพันธ์ ความลับ และเหตุการณ์ที่ต้องจำใน EP ถัดไป
4. สร้าง episode_title, episode_summary และ next_episode_hook สำหรับส่งต่อให้ EP ถัดไป
5. สร้าง scene_narrations และ scene_prompts อย่างละ {job['scene_count']} รายการพอดี
6. ทุก scene_prompt ต้องอ่านได้ด้วยตัวเอง (self-contained) ระบุชื่อตัวละครที่อยู่ในฉาก รูปลักษณ์คงที่ สถานที่ และการกระทำที่มองเห็นจากเรื่องและ CHARACTER BIBLE เป็นข้อความครบในฉากนั้น {scene_input_rule} ฉากแรกสร้างภาพจำตาม text bible โดยคงชื่อ ตัวตน อายุ และข้อมูลเดิม ภาพ 9:16 ตามแนวภาพที่ผู้ใช้เลือก ไม่มีข้อความและลายน้ำ
7. สร้าง dialogue_turns เป็นลำดับบทพูดจริง แต่ละรายการมี speaker, text, emotion และ pause_after; ก่อนตอบให้ตรวจทุก speaker ว่าตรงกับ ALLOWED SPEAKERS แบบตัวอักษรต่ออักษรเท่านั้น ห้ามเติมคำนำหน้า ฉายา หรือสร้างชื่อผู้พูดรองใหม่ หากเป็นคำพูดของพยาน/บุคคลนอก CHARACTER BIBLE ให้เปลี่ยนเป็นการเล่าผ่าน "ผู้บรรยาย"
8. narration_script รวมบทพูดทั้งหมดเป็นภาษาไทยที่ AI Voice อ่านง่าย ตัวเลขและคำอังกฤษเขียนเป็นคำอ่านภาษาไทย ห้ามเหลือตัวอักษร A-Z ใน narration_script, dialogue_turns[].text หรือ scene_narrations เช่น Doctor Doom Supreme ต้องเขียนว่า ด็อกเตอร์ ดูม ซูพรีม
9. {ending_rule} แล้วชวนผู้ชมกดหัวใจและคอมเมนต์แบบเข้ากับเนื้อเรื่อง
10. scene_durations จำนวน {job['scene_count']} ค่า ช่วง 3-7 วินาที

เพิ่ม flow_shot_prompts เป็นร่างพรอมต์การเคลื่อนไหวสั้นสำหรับแต่ละฉาก เน้นเหตุการณ์ สิ่งแวดล้อม และกล้อง ไม่ทวนรูปลักษณ์ทั้งก้อน ยังไม่อ้างว่าได้ตรวจภาพจริงแล้ว
ตอบเป็น JSON เท่านั้น โดยมี job_id, video_title, video_description, episode_title, episode_summary, next_episode_hook, narration_script, visual_bible, continuity_state, dialogue_turns, scene_narrations, scene_prompts, scene_durations และ warnings"""
        (folder / "prompts" / "chatgpt_request.txt").write_text(prompt + "\n\n" + COVER_PROMPT, encoding="utf-8")
        request = {
            "schema_version": 2,
            "mode": "story",
            "story_mode": "drama_episode",
            "job_id": job["id"],
            "prompt_file": "prompts/chatgpt_request.txt",
            "image_files": job["source_images"],
            "image_count": job["scene_count"],
            "prompt_field": "scene_prompts",
            "allowed_speakers": allowed_speakers,
            "required_fields": [
                "video_title", "video_description", "episode_title", "episode_summary",
                "next_episode_hook", "narration_script", "visual_bible", "continuity_state",
                "dialogue_turns", "scene_narrations", "scene_prompts", "scene_durations",
            ],
        }
        request["visual_style_instruction"] = story_style_instruction(job.get("visual_style"), job.get("visual_style_custom"))
        request["visual_render_instruction"] = story_render_instruction(job.get("visual_style"), job.get("visual_style_custom"))
        request["visual_depiction_instruction"] = STORY_VISUAL_DEPICTION_INSTRUCTION
        prompt += "\n" + request["visual_style_instruction"] + "\nส่ง pronunciation_notes เป็น object คำต้นฉบับ:คำอ่านไทย และใช้คำอ่านไทยในบทพูดทุกบรรทัด"
        prompt += "\n\n" + STORY_VISUAL_DEPICTION_INSTRUCTION
        if job.get("story_content_contract") == {"version": 1}:
            request["story_content_contract"] = {"version": 1}
            request["required_named_entities"] = requested_story_names(job)
            request["story_source_aliases"] = story_source_aliases(job)
            request["required_fields"].extend(["story_entities", "scene_entities"])
            prompt += "\n\n" + story_content_instruction(job)
        (folder / "prompts" / "chatgpt_request.txt").write_text(prompt + "\n\n" + COVER_PROMPT, encoding="utf-8")
        prompt = self._scene_dialogue_request(job,request,prompt)
        (folder / "prompts" / "chatgpt_request.txt").write_text(prompt + "\n\n" + COVER_PROMPT, encoding="utf-8")
        (folder / "ai_request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")

    def _folder(self, job_id):
        job_id = str(job_id or "")
        if not job_id.startswith("STORY-") or any(item in job_id for item in ("/", "\\", "..")):
            raise ValueError("Story Job ID ไม่ถูกต้อง")
        return self.root / job_id

    def _manifest_store(self, target):
        target = Path(target)
        return AtomicJsonFile(
            target,
            backup_path=runtime_backup_path(self.project_root, target),
        )

    def _save(self, manifest):
        from core.product_job_deletion import assert_job_available
        assert_job_available(self.project_root, manifest['id'])
        from core.speech_delivery import freeze_plan
        freeze_plan(manifest)
        folder = self._folder(manifest["id"])
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "job.json"
        store = self._manifest_store(target)
        with self._manifest_lock, store.locked():
            current_revision = 0
            if target.is_file():
                current = store.read_unlocked()
                if not isinstance(current, dict):
                    raise JsonPersistenceError(f"Story manifest ไม่ใช่ JSON object: {target}")
                # Only scene_video_plan's locked API may change this authority.
                # Progress writers often hold a pre-edit snapshot for minutes.
                if 'scene_video_plan' in current:
                    manifest['scene_video_plan'] = copy.deepcopy(current['scene_video_plan'])
                try:
                    current_revision = int(current.get("revision") or 0)
                except (TypeError, ValueError):
                    current_revision = 0
            manifest["revision"] = max(current_revision, int(manifest.get("revision") or 0)) + 1
            store.write_unlocked(manifest)
        return manifest

    @staticmethod
    def _strings(values):
        return [str(item if isinstance(item, str) else item.get("prompt") or item.get("text") or "").strip() for item in (values or []) if str(item if isinstance(item, str) else item.get("prompt") or item.get("text") or "").strip()]

    @staticmethod
    def _image_ai_provider(value):
        provider = str(value or "chatgpt").strip().lower()
        if "gemini" in provider:
            provider = "gemini"
        elif "chatgpt" in provider:
            provider = "chatgpt"
        if provider not in {"chatgpt", "gemini"}:
            raise ValueError("รองรับผู้สร้างภาพเฉพาะ ChatGPT Web หรือ Gemini Web")
        return provider

    @staticmethod
    def _video_generation_mode(value):
        mode = str(value or "image_motion").strip().lower()
        aliases = {"flow": "google_flow", "google_flow": "google_flow", "image_motion": "image_motion", "images": "image_motion"}
        mode = aliases.get(mode, mode)
        if mode not in {"image_motion", "google_flow", "meta_ai"}:
            raise ValueError("โหมดสร้างวิดีโอ Story ไม่ถูกต้อง")
        return mode

    @staticmethod
    def _ensure_engagement_cta(narration, scene_narrations, topic=""):
        narration = str(narration or "").strip()
        scene_narrations = list(scene_narrations or [])
        has_like = "กดหัวใจ" in narration or "กดไลก์" in narration
        # A direct question to the viewer is already an engagement CTA. Do not
        # append the raw title (which may contain unpronounceable English) again.
        has_comment = any(word in narration[-650:] for word in (
            "คอมเมนต์", "แสดงความคิดเห็น", "คุณคิด", "คุณจะ", "คุณเลือก", "คุณล่ะ", "แล้วคุณ",
        ))
        if has_like and has_comment:
            return narration, scene_narrations, False
        subject, issues = prepare_thai_tts_script(str(topic or "เรื่องนี้").strip())
        if issues or re.search(r"[A-Za-z]", subject) or len(subject) > 100:
            subject = "เรื่องนี้"
        parts = []
        if not has_like:
            parts.append("ถ้าชอบเรื่องนี้ กดหัวใจไว้")
        if not has_comment:
            parts.append(f"แล้วคอมเมนต์บอกหน่อยว่า คุณคิดอย่างไรกับ {subject}")
        cta = " ".join(parts)
        narration = f"{narration} {cta}".strip()
        if scene_narrations:
            scene_narrations[-1] = f"{scene_narrations[-1]} {cta}".strip()
        return narration, scene_narrations, True
