"""Meta AI video receipts, independent of Google Flow and image-provider state."""
import hashlib
import json
import math
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageOps

from core.atomic_json import AtomicJsonFile
from core.workspace_cleaner import working_video_folder
from core.meta_redesign import MetaRedesign
from core.meta_route_recovery import empty_home, route_event
from core.meta_error_report import safe_meta_url


_SEND_DIAGNOSTIC_PHASES = ('before_press', 'pressed', 'released')
_SEND_DIAGNOSTIC_OUTCOMES = frozenset({
    'blocked_before_press', 'release_cancelled', 'dispatch_unknown', 'gesture_released',
})
_SEND_DIAGNOSTIC_REASONS = frozenset({
    'owner_changed', 'tab_changed', 'document_changed', 'draft_changed',
    'target_changed', 'target_moved', 'source_changed', 'busy',
    'dispatch_error', 'validation_failed',
})
_SEND_DIAGNOSTIC_FLAGS = ('press_dispatched', 'release_dispatched')


def _safe_send_diagnostic(value):
    """Keep only bounded gesture facts; malformed telemetry cannot block a result."""
    if not isinstance(value, dict):
        return None
    phase, outcome = value.get('phase'), value.get('outcome')
    if (not isinstance(phase, str) or phase not in _SEND_DIAGNOSTIC_PHASES
            or not isinstance(outcome, str) or outcome not in _SEND_DIAGNOSTIC_OUTCOMES):
        return None
    result = {'phase': phase, 'outcome': outcome}
    if 'reason' in value:
        reason = value['reason']
        if not isinstance(reason, str) or reason not in _SEND_DIAGNOSTIC_REASONS:
            return None
        result['reason'] = reason
    for name in _SEND_DIAGNOSTIC_FLAGS:
        if name in value:
            if type(value[name]) is not bool:
                return None
            result[name] = value[name]
    return result


def _merge_send_diagnostic(previous, current):
    """Observability only: dispatch attempts are not acceptance or retry authority."""
    current = _safe_send_diagnostic(current)
    if current is None:
        return None
    previous = _safe_send_diagnostic(previous)
    if previous is not None:
        if (_SEND_DIAGNOSTIC_PHASES.index(previous['phase'])
                > _SEND_DIAGNOSTIC_PHASES.index(current['phase'])):
            return previous
        for name in _SEND_DIAGNOSTIC_FLAGS:
            if name in previous and (previous[name] is True or name not in current):
                current[name] = previous[name]
    return current


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


_SAFETY_SERVICE_OUTAGE = re.compile(
    r"^the video (?:couldn't|could not) be generated right now\s*[—–:-]\s*"
    r'the safety check service is temporarily unavailable[.!](?=\s|$)')


def meta_safety_service_outage(text):
    value = ' '.join(str(text or '').replace('’', "'").lower().split())
    return bool(_SAFETY_SERVICE_OUTAGE.match(value))


def meta_reply_failure(text):
    """Completed reply classification only; never infer failure from elapsed time."""
    value = ' '.join(str(text or '').replace('’', "'").lower().split())
    outage = meta_safety_service_outage(value)
    policy_text = _SAFETY_SERVICE_OUTAGE.sub('', value) if outage else value
    if re.search(r'polic|safety|guideline|not allowed|prohibited|copyright|นโยบาย|ความปลอดภัย|ละเมิด|ไม่อนุญาต', policy_text):
        return 'policy'
    if re.search(r'rate.?limit|quota|limit reached|reached.{0,30}limit|too many|ขีดจำกัด|โควตา', value):
        return 'quota'
    if re.search(r'\b(?:log|sign)[ -]?in\b|\bauthenticate\b|เข้าสู่ระบบ', value):
        return 'authentication_required'
    if outage:
        return 'transient_service_error'
    # Meta's completed, standalone apology has no video and does not identify
    # the starting image as unsafe. Redesign this scene through the original
    # image provider instead of retrying the identical Meta input indefinitely.
    if re.fullmatch(r'ขออภัย ดูเหมือนว่าทางฝั่งของฉันจะเกิดปัญหาบางอย่าง โปรดลองอีกครั้ง[.!?。]?', value):
        return 'technical_redesign'
    # A service outage is not an image/scene defect. Require both a concrete
    # technical failure and an explicit unsuccessful generation, not “error” alone.
    if (re.search(r'\b(?:server|network) error\b|\bservice (?:is )?(?:temporarily )?unavailable\b|ข้อผิดพลาด(?:ของ|จาก)?(?:เซิร์ฟเวอร์|เครือข่าย)', value)
            and re.search(r"(?:could not|couldn't|cannot|can't|unable to|failed to|wasn't able to|was not able to)\s+(?:be\s+)?(?:create|generate|make)(?:d)?\b|without producing (?:a video|video|media)|ไม่ได้สร้าง(?:วิดีโอ|คลิป)|สร้าง(?:วิดีโอ|คลิป)ไม่สำเร็จ", value)):
        return 'transient_service_error'
    if re.search(r'วิดีโอ.{0,50}(?:สร้าง|ทำ).{0,12}ไม่ได้|ภาพต้นฉบับ.{0,100}ไม่สามารถ.{0,45}(?:วิดีโอ|เคลื่อนไหว)|(?:image|starting frame).{0,80}(?:cannot|can.t|unable).{0,40}(?:video|animate)', value):
        return 'image_not_viable'
    if re.search(r"\bfile unavailable\b|\bvideo (?:file )?(?:is )?unavailable\b|ไฟล์(?:วิดีโอ)?ไม่พร้อมใช้งาน|(?:couldn't|could not|can't|cannot|unable to|failed to|wasn't able to|was not able to)\s+(?:create|generate|make)\b|ไม่สามารถ(?:สร้าง|ทำตาม)|สร้าง(?:วิดีโอ|คลิป)ไม่สำเร็จ", value):
        return 'completed_no_video'
    return ''


def meta_choice_offer(answer, aspect_ratio='9:16'):
    """Recognize a completed two-option video offer, not arbitrary instructions."""
    value = ' '.join(str(answer or '').split())
    if len(value) > 12000 or meta_reply_failure(value) in ('policy', 'quota', 'authentication_required'):
        return None
    markers = list(re.finditer(r'(?:\boption|(?:ตัวเลือก|ทางเลือก)(?:ที่)?|ข้อ)\s*([1-9])\s*[-:–—.)]', value, re.I))
    if [m[1] for m in markers] != ['1', '2'] or not re.search(r'video|วิดีโอ|คลิป', value, re.I):
        return None
    tail = value[markers[1].end():]
    ask = re.search(r'(?:want me to|would you like me to|shall i)\s+(?:generate|create|make)|which (?:option|version)|(?:ต้องการ|อยาก)(?:ให้)?(?:ฉัน|ผม)?.{0,35}(?:สร้าง|เลือก)|เลือก(?:ข้อ|ตัวเลือก|ทางเลือก).{0,20}(?:ไหน|ใด)', tail, re.I)
    if not ask:
        return None
    first = value[markers[0].end():markers[1].start()].strip()
    selected = tail[:ask.start()].strip()
    if not first or not 5 <= len(selected) <= 4000:
        return None
    orientation = 'landscape 16:9' if aspect_ratio == '16:9' else 'vertical 9:16'
    prompt = (f'I choose option 2: {selected}\n'
              f'Create that actual playable {orientation} video now, using the image already attached in this conversation. '
              'Keep the characters and audio/dialogue instructions from my original request. No text, captions or watermark.')
    return dict(number=2, text=selected, proposal_text=value, prompt=prompt)


def meta_safe_offer(answer, aspect_ratio='9:16'):
    """Accept only Meta's completed, explicit offer to make a compliant variant.

    A bare refusal or a categorical policy/quota reply is not retry authority.
    The original image/request stay in their receipt; this is one owned follow-up.
    """
    value = ' '.join(str(answer or '').split())
    if not 0 < len(value) <= 12000 or meta_reply_failure(value) not in ('image_not_viable', 'completed_no_video'):
        return None
    # Historical M6 is NOT a one-off yes/no offer. Accept only the explicitly
    # bounded clothing-only first option, not its alternative animation style.
    # Other unnumbered choices continue through the existing no-video recovery.
    if re.search(r'อยากให้ลองทำเป็นเวอร์ชันไหน', value):
        clothing_choice = re.search(
            r'เช่น\s+ปรับชุดให้มิดชิดขึ้นเป็นเสื้อยืดกับกางเกงขายาว\s+หรือทำเป็นสไตล์แอนิเมชัน/ภาพวาด\s+'
            r'แบบไม่มีการเน้นสรีระ\s+อยากให้ลองทำเป็นเวอร์ชันไหนดี(?:คะ|ครับ)?\??$', value)
        if (not clothing_choice or not re.search(r'ฉันช่วยทำเวอร์ชันที่ปลอดภัยขึ้นให้ได้\s+โดยยังคงไอเดียเดิมไว้ทั้งหมด', value)
                or re.search(r'เปลี่ยน(?:ตัวละคร|บุคคล|สินค้า|บท|เสียง|สไตล์)|แทนที่(?:สินค้า|ตัวละคร)|เพิ่ม(?:บทพูด|เพลง)|(?:ตัวเลือก|ทางเลือก|\boption)\s*[1-9]', value, re.I)):
            return None
        orientation = 'landscape 16:9' if aspect_ratio == '16:9' else 'vertical 9:16'
        prompt = (
            'Yes. Use only the first adjustment you offered: a modest T-shirt and long trousers. '
            'Keep the original characters, product identity and visibility, setting, action, visual style, '
            'exact dialogue and audio settings unchanged. Do not choose the alternative animation/drawing style. '
            'If changing the clothing would replace or hide the product, or require changing those other details, '
            'report that conflict truthfully instead of inventing a different scene. '
            f'Generate exactly one actual playable {orientation} video, not a still image or text description. '
            'Do not offer alternatives or ask me to choose or confirm again. No added text or watermark.'
        )
        return dict(kind='safe_revision', selection='first_clothing_only', number=1,
                    text='Meta-proposed modest clothing only', proposal_text=value, prompt=prompt)
    if (not re.search(r'ปลอดภัยขึ้น|แต่งกายให้มิดชิด|safer (?:version|scene)|compliant (?:version|scene)|different take|more covered outfit|wider framing', value, re.I)
            or not re.search(r'ฉันช่วยทำ|ช่วยทำเวอร์ชัน|ฉันสามารถสร้างวิดีโอใหม่ให้ได้ด้วยภาพเริ่มต้นที่ฉันสร้างขึ้นเอง|i can (?:help with|make|create|generate)', value, re.I)
            or not re.search(r'อยากให้.{0,100}(?:ทำ|สร้าง).{0,30}ไหม\??|อยากให้ฉันลองทำเวอร์ชันที่ปรับเฟรมให้ปลอดภัยขึ้นแต่ยังคงฮุคนี้ไว้เลยไหม(?:คะ|ครับ)?\??|(?:would you like|want me to|let me know if you.d like me to).{0,100}(?:make|create|generate|try)', value, re.I)):
        return None
    orientation = 'landscape 16:9' if aspect_ratio == '16:9' else 'vertical 9:16'
    prompt = (
        'Yes, please make the safer version you just offered. Choose compliant clothing, framing, '
        f'and a revised starting visual if needed. Generate exactly one actual playable {orientation} video, '
        'not a still image or a text description. Preserve the harmless hook, scene action, product identity '
        'where possible, and the original Thai spoken line and audio settings. Do not ask me to choose or confirm '
        'again. If video generation is unavailable, report that truthfully.'
    )
    return dict(kind='safe_revision', number=0, text='Meta-proposed safer version',
                proposal_text=value, prompt=prompt)


def meta_followup_offer(answer, aspect_ratio='9:16'):
    return meta_choice_offer(answer, aspect_ratio) or meta_safe_offer(answer, aspect_ratio)


def meta_comparison_offer(branches, aspect_ratio='9:16'):
    """Select one independently completed reply; never parse combined alternatives."""
    if (not isinstance(branches, list) or len(branches) != 2 or any(
            not isinstance(branch, dict) or not isinstance(branch.get('text'), str)
            or not 0 < len(branch['text']) <= 12000 or branch.get('complete') is not True
            or branch.get('truncated') is not False or branch.get('busy') is not False
            or type(branch.get('video_count')) is not int or branch['video_count'] != 0
            for branch in branches)):
        return None
    for index, branch in enumerate(branches):
        offer = meta_followup_offer(branch['text'], aspect_ratio)
        if offer:
            return {**offer, 'proposal_branch': index,
                    'proposal_branches': [' '.join(item['text'].split()) for item in branches],
                    'prompt': f'Use response {index + 1} only, with this selected proposal; disregard the other response.\n'
                              + offer['prompt']}
    return None


class MetaVideoManager(MetaRedesign):
    MAX_RETRIES = 2
    SERVICE_RETRY_DELAYS = (15, 30, 60, 120, 300)
    STAGES = ('prepared', 'uploading', 'ready_to_send', 'send_intent', 'submitted',
              'generating', 'download_intent', 'downloading', 'stored')

    def __init__(self, stories, validator=None, products=None):
        self.stories = stories
        self.products = products
        self.validator = validator

    def _manager(self, job_id):
        if str(job_id or '').startswith('STORY-'):
            if not self.stories:
                raise ValueError('ยังไม่ได้เปิดโหมดเรื่องเล่า')
            return self.stories
        if str(job_id or '').startswith('JOB-') and self.products:
            return self.products
        raise ValueError('ไม่พบงานคลิปที่รองรับ Meta AI')

    def _job(self, job_id):
        manager = self._manager(job_id)
        return manager.get(job_id) if manager is self.stories else manager.get_job(job_id)

    def _folder(self, job_id):
        manager = self._manager(job_id)
        return manager._folder(job_id) if manager is self.stories else manager.root / job_id

    def _save_job(self, job_id, job):
        manager = self._manager(job_id)
        if manager is self.stories:
            manager._save(job)
        else:
            manager._save_manifest_file(self._folder(job_id) / 'job.json', job)

    def _lock(self, job_id):
        return self._manager(job_id)._manifest_lock

    def _store(self, job_id):
        return AtomicJsonFile(self._folder(job_id) / 'prompts' / 'meta_video_receipts.json')

    def package(self, job_id, index):
        manager = self._manager(job_id)
        job = self._job(job_id)
        from core.product_editorial import assert_approved
        assert_approved(job)
        serial_image = None
        from core.meta_scene_sequence import enabled as serial_meta, scene_input
        if manager is self.stories and serial_meta(job):
            job, serial_image, _ = scene_input(self.stories, job, int(index))
        from core.scene_video_plan import effective_job, enabled as has_video_plan, package_binding, legacy_active, validate_package
        if manager is self.stories:
            validate_package(self._folder(job_id), job, int(index))
            job = effective_job(job, int(index))
        if manager is self.stories and job.get('video_generation_mode') != 'meta_ai':
            raise ValueError('งานนี้ไม่ได้เลือก Meta AI')
        if manager is self.products and str(job.get('video_ai_provider') or 'flow') != 'meta_ai':
            raise ValueError('งานสินค้านี้ยังไม่ได้เลือก Meta AI')
        # Story cancellation is a durable content state. Product cancellation is
        # tracked by automation_status and an explicit Continue sets it back to
        # running before the Extension command is queued; the old Product
        # manifest status may still say "cancelled" even though resuming is valid.
        product_resume_active = manager is self.products and job.get('automation_status') == 'running'
        if (job.get('cancel_requested')
                or (manager is self.stories and job.get('status') in {'cancelled', 'canceled'})
                or (manager is self.products and job.get('status') in {'cancelled', 'canceled'}
                    and not product_resume_active)):
            raise ValueError('งานถูกยกเลิก • เก็บผล Meta เดิมไว้')
        is_long_video = bool(job.get('long_video'))
        aspect_ratio = '16:9' if is_long_video else '9:16'
        orientation = 'landscape 16:9' if is_long_video else 'vertical 9:16'
        from core.media_audio import audio_choices, flow_audio_instruction
        sound = audio_choices(job.get('audio_choices') or {'mode': 'api'}, 'meta_ai')
        from core.meta_prompt import meta_prompt_version, SINGLE_VIDEO_INSTRUCTION, compliant_video_instruction
        version = meta_prompt_version(job.get('meta_prompt_version', 1))
        index = int(index)
        images = job.get('generated_images') or []
        if manager is self.products:
            # Google Flow's policy/local-fallback guard is intentionally scoped
            # to Flow. A user who explicitly switches a legacy Product Job to
            # Meta may use its already-reviewed source image and saved brief.
            product_package = manager.flow_package(job_id, shot_index=index, provider='meta_ai')
            images = product_package.get('image_files') or []
            count = int(job.get('flow_target_clip_count') or len(job.get('composition_images') or job.get('generated_images') or job.get('source_images') or []) or 3)
            image_value = images[0] if images else ''
            prompt_value = str(product_package.get('video_prompt') or '')
            scene_value = str((job.get('spoken_script_segments') or job.get('scene_narrations') or [''])[index - 1] or '') if index <= int(job.get('flow_target_clip_count') or len(images) or 0) else ''
        else:
            count = int(job.get('scene_count') or 0)
            image_value = serial_image or (images[index - 1] if index <= len(images) else '')
            prompt_value = str((job.get('scene_prompts') or [])[index - 1] if index <= len(job.get('scene_prompts') or []) else '')
            scene_value = str((job.get('scene_narrations') or [])[index - 1] if index <= len(job.get('scene_narrations') or []) else '')
        if not 1 <= index <= count or not image_value:
            raise ValueError('ภาพฉาก Meta ยังไม่พร้อม')
        folder = self._folder(job_id).resolve()
        image = (folder / image_value).resolve() if not Path(str(image_value)).is_absolute() else Path(image_value).resolve()
        if not image.is_relative_to(folder) or not image.is_file():
            raise ValueError('ไม่พบภาพฉาก Meta ในงานนี้')
        if is_long_video:
            with Image.open(image) as opened:
                oriented = ImageOps.exif_transpose(opened)
                if (min(oriented.size) < 128
                        or abs(oriented.width / oriented.height - 16 / 9) > .08):
                    raise ValueError('ภาพฉาก Meta คลิปยาวต้องเป็นแนวนอน 16:9 • เก็บภาพเดิมไว้ให้ตรวจ')
        if version == 5:
            from core.meta_prompt import saved_scene_motion
            scene_value = saved_scene_motion(job, index, folder)
        # Preserve legacy silent prompt bytes and receipt hashes unless the job
        # explicitly requests source audio. Never reset an in-flight receipt.
        audio_prompt = 'No music, speech or ambient audio; narration is added separately.'
        if sound['mode'] == 'flow_original':
            audio_prompt = ('Generate this video with its original audible soundtrack. '
                            'All spoken dialogue must be in Thai only. No background music. '
                            + flow_audio_instruction(job, index))
            if version == 5 and 'NARRATOR AUDIO:' in audio_prompt:
                audio_prompt = ('Generate this video with its original audible soundtrack. '
                                'Use only the saved audio delivery below. No background music. '
                                + flow_audio_instruction(job, index))
        elif sound['keep_video_audio']:
            audio_prompt = 'Include natural ambient sounds only. No speech or music; narration is added separately.'
        from core.generated_music import apply_to_prompt
        audio_prompt = apply_to_prompt(job, index, audio_prompt)
        if version in (3, 4, 5):
            opening = (f'Create exactly one playable {orientation} video from the attached image as the first frame. '
                       if version == 3 else
                       f'Create exactly one playable {orientation} video using the attached image as visual reference and, when suitable, the first frame. ')
            prompt = (opening
                      + 'Keep its characters, product and setting. Animate the described action with subtle background motion '
                      'and one smooth camera move; no text or watermark. ' + audio_prompt
                      + '\nScene: ' + prompt_value + '\nAction: ' + scene_value
                      + '\nReturn the actual video, not options or an explanation. If unavailable, report that truthfully.')
        else:
            prompt = (f'Create one actual playable {orientation} video from the attached image, not a still image or explanation. '
                      'Use the image as the starting frame. Preserve the characters, product and scene continuity. '
                      'Add natural visible action, subtle environmental motion and one smooth camera move. '
                      'No text, captions or watermark. ' + audio_prompt + '\n'
                       + 'Scene: ' + prompt_value
                       + '\nStory action: ' + scene_value)
        from core.product_script import film_scene
        scene = film_scene(job, index) if manager is self.stories else None
        from core.speech_delivery import enabled as speech_enabled, scene_delivery
        # The final audio block owns speech exactly once; continuity metadata
        # still carries role/action/reveal timing without a second spoken copy.
        if scene is not None and speech_enabled(job):
            scene = {key: value for key, value in scene.items() if key != 'spoken_text'}
        if scene is not None:
            prompt += ('\nSAVED SHORT FILM SCENE (data): ' + json.dumps(scene, ensure_ascii=False)
                       + '\nUse action for visible motion; spoken_text is dialogue only, never read directions aloud. '
                       'Preserve the scene role, listener and reveal timing. Do not show products when product_visible is false. '
                       'No new story, reviewer monologue, product claims or CTA. Respect the audio settings above.')
        wardrobe = (job.get('product_story') or {}).get('outfit_mode')
        from core.product_pointing import enabled as pointing_review, apply_visual, visual_instruction
        if wardrobe in {'auto', 'saved', 'product'} and not pointing_review(job):
            prompt += ('\nClothing continuity: animate the adult character in the clothing shown in the starting image. '
                       'Keep an ordinary, appropriately covered appearance and suitable camera framing. '
                       'If this visual cannot be animated under provider rules, choose a genuinely compliant '
                       'clothing/framing revision without changing the product identity or making a false video claim.')
        if version == 2:
            prompt += '\nGeneration instruction: ' + SINGLE_VIDEO_INSTRUCTION
        elif version in (4, 5):
            prompt += '\nGeneration instruction: ' + compliant_video_instruction(aspect_ratio)
        prompt = apply_visual(job, apply_to_prompt(job, index, prompt))
        image_hash = digest(image)
        context = hashlib.sha256((job_id + ':' + str(index) + ':' + image_hash + ':' + prompt).encode()).hexdigest()
        package=dict(job_id=job_id, index=index, context_id=context, image_path=str(image),
                    image_name=image.name, image_sha256=image_hash, prompt=prompt, provider='meta_ai',
                    audio_instruction=audio_prompt,scene_value=scene_value,
                    continuity_instruction=('\nSAVED SHORT FILM SCENE (data): '+json.dumps(scene,ensure_ascii=False)
                                            +'\nKeep role, dialogue and product reveal timing.' if scene is not None else ''))
        if pointing_review(job):
            package['continuity_instruction'] += '\n' + visual_instruction(job)
        if speech_enabled(job):
            package['speech_delivery'] = scene_delivery(job, index)
        if manager is self.stories and has_video_plan(job):
            package.update(scene_video_plan_required=True, scene_video_plan=package_binding(job, index),
                           scene_video_plan_legacy_active=legacy_active(job, index))
        if version == 5:
            from core.meta_prompt import narrator_text
            package.update(meta_prompt_version=5, narrator_text=narrator_text(job, index))
        if is_long_video:
            package['aspect_ratio'] = aspect_ratio
        override=(self._store(job_id).read({}).get('overrides') or {}).get(str(index))
        if override:
            if override['base_context_id']!=context: raise ValueError('ต้นฉบับ Meta เปลี่ยนหลังสร้างภาพใหม่')
            replacement=Path(override['image_path']).resolve()
            if not replacement.is_relative_to(folder) or not replacement.is_file() or digest(replacement)!=override['image_sha256']:
                raise ValueError('รูปทดแทน Meta ไม่พร้อมใช้งาน')
            package.update(override)
        package['image_relative']=Path(package['image_path']).relative_to(folder).as_posix()
        return package

    def begin(self, job_id, index, resume=False):
        if self._manager(job_id) is self.stories:
            from core.meta_scene_sequence import assert_scene_dispatch
            assert_scene_dispatch(self.stories, self._job(job_id), int(index))
        package = self.package(job_id, index)
        store = self._store(job_id)
        with store.locked():
            data = store.read_unlocked(default={'scenes': {}})
            old = data['scenes'].get(str(index))
            if old and package.get('scene_video_plan') and old.get('scene_video_plan') != package['scene_video_plan']:
                job = self._job(job_id)
                row = ((job.get('scene_video_plan') or {}).get('scenes') or {}).get(str(index)) or {}
                retired = any(item.get('meta_request_id') == old.get('request_id')
                              and item.get('proof', {}).get('terminal') is True
                              for item in row.get('attempt_history') or [])
                if not retired:
                    raise ValueError('รอบ Meta เดิมยังถือสิทธิ์อยู่ • ไม่เริ่มรอบใหม่')
                data.setdefault('attempt_history', {}).setdefault(str(index), []).append(dict(old))
                old = None
            if old and old['context_id'] != package['context_id']:
                raise ValueError('ภาพหรือบท Meta เปลี่ยนหลังเริ่มงาน • ตรวจงานเดิมก่อนส่งใหม่')
            if not old:
                if package.get('scene_video_plan_required') and not package.get('scene_video_plan'):
                    raise ValueError('ยังไม่มีสิทธิ์สร้าง Meta ของฉากนี้ • ไม่เริ่มคำขอใหม่')
                old = dict(context_id=package['context_id'], request_id=uuid.uuid4().hex,
                           job_id=job_id, index=int(index), stage='prepared', updated_at=time.time())
                if package.get('scene_video_plan'):
                    old['scene_video_plan'] = dict(package['scene_video_plan'])
                data['scenes'][str(index)] = old
                store.write_unlocked(data)
            elif resume and old['stage'] == 'needs_attention':
                fresh_allowed = (old.get('resume_stage') in ('prepared', 'uploading', 'ready_to_send') or
                                 (old.get('retry_exhausted') is True and old.get('resume_stage') == 'generating'))
                if fresh_allowed:
                    # Explicit user Continue after proven completed failure starts
                    # a fresh attempt. Never inherit URL/Send/upload/download flags.
                    data.setdefault('attempt_history', {}).setdefault(str(index), []).append(dict(old))
                    old = dict(context_id=package['context_id'], request_id=uuid.uuid4().hex,
                               job_id=job_id, index=int(index), stage='prepared', updated_at=time.time(),
                               retry_count=0, retry_previous_request_id=old['request_id'],
                               manual_restart_count=int(old.get('manual_restart_count') or 0) + 1,
                               message='เริ่มฉากที่ล้มเหลวใหม่ใน Meta • เก็บฉากที่สำเร็จแล้ว')
                    if package.get('scene_video_plan'):
                        old['scene_video_plan'] = dict(package['scene_video_plan'])
                    data['scenes'][str(index)] = old
                else:
                    old.update(stage=old.get('resume_stage') or 'prepared', message='', updated_at=time.time())
                store.write_unlocked(data)
            return {**package, **old}

    def _fresh_scene(self, data, store, old, *, reason, evidence=None, route_evidence=None):
        """Archive one owner and atomically publish its clean direct successor."""
        now = time.time()
        data.setdefault('attempt_history', {}).setdefault(str(old['index']), []).append(dict(old))
        fresh = dict(job_id=old['job_id'], index=old['index'], context_id=old['context_id'],
                     request_id=uuid.uuid4().hex, stage='prepared', updated_at=now,
                     retry_previous_request_id=old['request_id'], fresh_start_reason=reason,
                     message='เริ่มเฉพาะฉากที่ค้างบน Meta หน้าแรกใหม่ • ใช้ภาพและพรอมต์ที่บันทึกไว้')
        if old.get('scene_video_plan'):
            fresh['scene_video_plan'] = dict(old['scene_video_plan'])
        if evidence is None:
            fresh['manual_restart_count'] = int(old.get('manual_restart_count') or 0) + 1
        else:
            count = int(old.get('fresh_start_count') or 0) + 1
            fresh.update(fresh_start_count=count, fresh_start_evidence=dict(evidence),
                         fresh_start_not_before=now + min(60, 5 * 2 ** min(count - 1, 4)))
            if route_evidence is not None:
                fresh['fresh_start_route_evidence'] = {key: route_evidence[key] for key in (
                    'observed_url', 'document_id', 'ready', 'composer_empty', 'answer_empty',
                    'login', 'busy', 'stop', 'dialog', 'composer_count', 'user_count', 'image_count',
                    'video_count', 'message_count', 'samples', 'stable_ms')}
        data['scenes'][str(old['index'])] = fresh
        store.write_unlocked(data)
        return dict(fresh)

    def restart_unfinished_on_continue(self, job_id):
        """The explicit UI action restarts only the first unfinished Meta step.

        Automatic queue/startup resume continues to use begin(resume=True).
        The caller must own the manual Continue action, not a progress heartbeat.
        """
        job = self._job(job_id)
        if str(job.get('video_generation_mode') or '') != 'meta_ai':
            return None
        for index in range(1, int(job.get('scene_count') or 0) + 1):
            current = self.get(job_id, index)
            if current.get('stage') == 'stored' or str(index) in (job.get('meta_clips') or {}):
                continue
            if not current:
                return None
            if (current.get('stage') == 'redesigning' or
                    current.get('stage') == 'needs_attention' and current.get('resume_stage') == 'redesigning'):
                return self.restart_unfinished_redesign_on_continue(job_id)
            package = self.package(job_id, index)
            store = self._store(job_id)
            with store.locked():
                data = store.read_unlocked({'scenes': {}})
                old = data.get('scenes', {}).get(str(index)) or {}
                latest_job = self._job(job_id)
                if latest_job.get('cancel_requested') or latest_job.get('status') in {'cancelled', 'canceled'}:
                    raise ValueError('งานถูกยกเลิก • เก็บผล Meta เดิมไว้')
                if (old.get('context_id') != package['context_id'] or
                        old.get('stage') == 'stored' or
                        str(index) in (latest_job.get('meta_clips') or {})):
                    return None
                if old.get('request_id') != current.get('request_id'):
                    # A racing Continue already published the direct successor.
                    if old.get('retry_previous_request_id') == current.get('request_id'):
                        return dict(old)
                    return None
                if old.get('stage') == 'prepared' and old.get('fresh_start_reason') == 'manual_continue':
                    return dict(old)
                if old.get('stage') not in self.STAGES and old.get('stage') != 'needs_attention':
                    return None
                return self._fresh_scene(data, store, old, reason='manual_continue')
        return None

    def restart_unfinished_redesign_on_continue(self, job_id):
        """Explicit Continue abandons only an unfinished, proven failed Meta redesign.

        The ordinary worker and automatic queue resume must never call this:
        an unknown Send or active Meta render still belongs to its old receipt.
        """
        job = self._job(job_id)
        if str(job.get('video_generation_mode') or '') != 'meta_ai':
            return None
        for index in range(1, int(job.get('scene_count') or 0) + 1):
            current = self.get(job_id, index)
            if current.get('stage') == 'stored' or str(index) in (job.get('meta_clips') or {}):
                continue
            repair = current.get('redesign') if isinstance(current.get('redesign'), dict) else {}
            eligible = (current.get('stage') == 'redesigning' or
                        current.get('stage') == 'needs_attention' and current.get('resume_stage') == 'redesigning')
            if not eligible or repair.get('phase') not in {'prepared', 'requested', 'image_saved'}:
                return None
            package = self.package(job_id, index)
            store = self._store(job_id)
            with store.locked():
                data = store.read_unlocked(default={'scenes': {}})
                old = data.get('scenes', {}).get(str(index)) or {}
                original = old.get('redesign') if isinstance(old.get('redesign'), dict) else {}
                if (old.get('request_id') != current.get('request_id') or
                        old.get('context_id') != package['context_id'] or
                        old.get('stage') not in {'redesigning', 'needs_attention'} or
                        old.get('stage') == 'needs_attention' and old.get('resume_stage') != 'redesigning' or
                        original.get('phase') not in {'prepared', 'requested', 'image_saved'} or
                        original.get('failure_reason') not in {'technical_redesign', 'transient_service_error', 'image_not_viable', 'completed_no_video'} or
                        original.get('provider') not in {'chatgpt', 'gemini'} or
                        not isinstance(original.get('request'), str) or not original['request'].strip() or
                        not isinstance(original.get('id'), str) or not original['id']):
                    return None
                if (old.get('fresh_start_reason') == 'manual_redesign_continue' and old.get('stage') == 'redesigning'
                        and original['phase'] == 'prepared'):
                    return dict(old)
                if original['phase'] == 'image_saved':
                    # Preserve the prompt-only checkpoint only while its
                    # durable image still matches the saved receipt.
                    saved = original.get('saved_image') or {}
                    target = Path(saved.get('image_path') or '').resolve()
                    folder = self._folder(job_id).resolve()
                    try:
                        image_ready = (bool(saved.get('image_sha256')) and
                                       target.is_relative_to(folder) and target.is_file() and
                                       digest(target) == saved['image_sha256'])
                    except OSError:
                        image_ready = False
                    if image_ready:
                        if old['stage'] == 'needs_attention':
                            original['prompt_attempt'] = int(original.get('prompt_attempt') or 0) + 1
                            old.update(stage='redesigning', updated_at=time.time(),
                                       message='ภาพใหม่บันทึกแล้ว • ทำต่อเฉพาะพรอมต์วิดีโอ')
                            old.pop('resume_stage', None)
                            store.write_unlocked(data)
                        return dict(old)
                # The old helper/Meta conversation remains archived for audit,
                # but neither URL nor Send intent is inherited by the successor.
                data.setdefault('attempt_history', {}).setdefault(str(index), []).append(dict(old))
                next_round = max(int(old.get('redesign_round') or 0), int(original.get('round') or 0)) + 1
                base_request = self._redesign_image_request(package, original['failure_reason'])
                # A new image owner must not inherit a corrupt image or an
                # already-attempted prompt checkpoint from the archived run.
                clean_redesign = {key: value for key, value in original.items()
                                  if key not in {'saved_image', 'prompt_request', 'prompt_attempt',
                                                 'proposal', 'image_prompt', 'video_prompt'}}
                fresh = dict(job_id=job_id, index=index, context_id=package['context_id'],
                             request_id=uuid.uuid4().hex, stage='redesigning', updated_at=time.time(),
                             redesign_round=next_round,
                             redesign_previous_request_id=old['request_id'],
                             superseded_redesign_id=original['id'],
                             fresh_start_reason='manual_redesign_continue',
                             manual_restart_count=int(old.get('manual_restart_count') or 0) + 1,
                             message='เริ่มออกแบบภาพและพรอมต์ใหม่เฉพาะฉากที่ค้าง ก่อนเปิด Meta หน้าแรก',
                             redesign={**clean_redesign, 'id':uuid.uuid4().hex, 'phase':'prepared',
                                       'round':next_round,
                                       'base_request':base_request,
                                       'image_request':base_request,
                                       'request':base_request})
                data['scenes'][str(index)] = fresh
                store.write_unlocked(data)
                return dict(fresh)
        return None

    def get(self, job_id, index):
        return self._store(job_id).read({'scenes': {}})['scenes'].get(str(index), {})

    def event(self, body):
        job_id, index = str(body.get('job_id') or ''), int(body.get('index') or 0)
        package = self.package(job_id, index)
        store = self._store(job_id)
        with store.locked():
            data = store.read_unlocked(default={'scenes': {}})
            receipt = data['scenes'].get(str(index)) or {}
            if package.get('scene_video_plan_required'):
                from core.scene_video_plan import assert_binding
                job = self._job(job_id)
                assert_binding(job, index, body.get('scene_video_plan'), allow_legacy_active=True)
                if receipt.get('scene_video_plan') != body.get('scene_video_plan'):
                    raise ValueError('ใบรับ Meta ไม่ตรงรอบของแผนวิดีโอ')
                if (not body.get('scene_video_plan') and body.get('stage') in
                        {'prepared', 'uploading', 'ready_to_send', 'send_intent', 'choice_send_intent',
                         'retry_prepared', 'fresh_start', 'route_retry', 'redesign_prepare'}):
                    raise ValueError('รอบ Meta เดิมตรวจผลได้เท่านั้น • ไม่ส่งใหม่หลังเปลี่ยนแผน')
            if body.get('stage') == 'fresh_start':
                return self._fresh_start(data, store, receipt, body, package)
            # A lost retry ACK returns the existing successor, not another send.
            if (body.get('stage') in ('retry_prepared', 'route_retry') and receipt
                    and body.get('request_id') == receipt.get('retry_previous_request_id')
                    and (body.get('stage') != 'route_retry' or
                         body.get('route_check_id') == receipt.get('route_previous_check_id'))
                    and body.get('context_id') == receipt.get('context_id') == package['context_id']):
                return dict(receipt)
            if (not receipt or body.get('request_id') != receipt['request_id']
                    or body.get('context_id') != package['context_id']
                    or receipt['context_id'] != package['context_id']):
                raise ValueError('ผล Meta ไม่ตรงงาน ฉาก หรือภาพที่ส่ง')
            stage = str(body.get('stage') or '')
            if stage in ('route_recheck', 'route_retry', 'route_restored'):
                return route_event(data, store, receipt, body)
            if stage == 'redesign_prepare':
                return self._redesign_prepare(data,store,receipt,body,package)
            if stage == 'retry_prepared':
                return self._retry(data, store, receipt, body, package)
            if stage in ('choice_prepare', 'choice_send_intent', 'choice_submitted'):
                return self._choice(data, store, receipt, body, package)
            if stage == 'video_select':
                proof = body.get('video_evidence') or {}
                digest = proof.get('asset_sha256')
                if (receipt['stage'] != 'generating' or not receipt.get('conversation_url')
                        or body.get('conversation_url') != receipt['conversation_url']
                        or proof.get('matched_request') is not True or proof.get('ready') is not True
                        or proof.get('stop') is not False or proof.get('busy') is not False
                        or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                        or receipt.get('choice') and receipt['choice']['stage'] != 'accepted'):
                    raise ValueError('ยังยืนยันวิดีโอที่เลือกจากคำขอ Meta เดิมไม่ได้')
                selection = receipt.get('video_selection')
                if selection and selection.get('asset_sha256') != digest:
                    raise ValueError('วิดีโอ Meta ที่เลือกเปลี่ยน • เก็บผลเดิม ไม่เปลี่ยนตัวเลือก')
                if not selection:
                    receipt['video_selection'] = {'asset_sha256': digest, 'selected_at': time.time()}
                    store.write_unlocked(data)
                return dict(receipt)
            if stage not in self.STAGES and stage != 'needs_attention':
                raise ValueError('สถานะ Meta ไม่ถูกต้อง')
            if receipt['stage'] == 'stored':
                return dict(receipt)
            if stage == 'download_intent' and receipt.get('choice') and receipt['choice']['stage'] != 'accepted':
                raise ValueError('ยังยืนยันคำตอบเลือก Meta ไม่ได้ • ไม่รับวิดีโอจากคำตอบเก่า')
            if (stage == 'download_intent' and receipt.get('video_selection')
                    and body.get('asset_sha256') != receipt['video_selection']['asset_sha256']):
                raise ValueError('คำขอดาวน์โหลดไม่ตรงวิดีโอ Meta ที่เลือกไว้')
            if stage == 'needs_attention' and receipt['stage'] != 'needs_attention':
                receipt['resume_stage'] = receipt['stage']
            diagnostic = body.get('page_diagnostic')
            if isinstance(diagnostic, dict) and safe_meta_url(diagnostic.get('observed_url')):
                receipt['page_diagnostic'] = {'observed_url':safe_meta_url(diagnostic['observed_url'])}
            url = str(body.get('conversation_url') or receipt.get('conversation_url') or '')
            if url:
                parsed = urlparse(url)
                if parsed.scheme != 'https' or parsed.netloc != 'www.meta.ai' or not parsed.path.startswith('/prompt/') or parsed.query or parsed.fragment:
                    raise ValueError('ลิงก์บทสนทนา Meta ไม่ถูกต้อง')
                if receipt.get('conversation_url') and receipt['conversation_url'] != url:
                    raise ValueError('ผล Meta มาจากคนละบทสนทนา')
            if stage == 'stored':
                if receipt['stage'] != 'downloading' or not url or int(body.get('download_id', -1)) != receipt.get('download_id'):
                    raise ValueError('ยังไม่มีใบรับดาวน์โหลด Meta ของฉากนี้')
                saved = self._save_clip(package, body, receipt)
                receipt.update(saved)
            elif stage != 'needs_attention' and receipt['stage'] != 'needs_attention':
                before, after = self.STAGES.index(receipt['stage']), self.STAGES.index(stage)
                if after < before or after > before + 1:
                    raise ValueError('ลำดับงาน Meta ไม่ตรงใบรับเดิม')
            elif receipt['stage'] == 'needs_attention' and stage != 'needs_attention':
                raise ValueError('Meta ต้องตรวจงานเดิมก่อน • ไม่ส่งซ้ำอัตโนมัติ')
            if stage == 'downloading':
                download_id = body.get('download_id')
                if not isinstance(download_id, int) or download_id < 0:
                    raise ValueError('ไม่พบหมายเลขดาวน์โหลด Meta')
                receipt['download_id'] = download_id
            receipt.update(stage=stage, conversation_url=url, updated_at=time.time(),
                           message=str(body.get('message') or '')[:300])
            if stage != 'generating':
                receipt.pop('recovery', None)
            send_diagnostic = _merge_send_diagnostic(
                receipt.get('send_diagnostic'), body.get('send_diagnostic'))
            if send_diagnostic is not None:
                receipt['send_diagnostic'] = send_diagnostic
            store.write_unlocked(data)
            return dict(receipt)

    def _fresh_start(self, data, store, receipt, body, package):
        """Only a current missing/unowned page observation can replace a Meta owner."""
        proof = body.get('fresh_start_evidence')
        if (not isinstance(proof, dict)
                or set(proof) != {'reason', 'tab_id', 'tab_missing', 'session_owned'}
                or not isinstance(proof.get('reason'), str)
                or type(proof.get('tab_id')) is not int or not -1 <= proof['tab_id'] < 2 ** 31
                or type(proof.get('tab_missing')) is not bool
                or type(proof.get('session_owned')) is not bool):
            raise ValueError('ยังไม่มีหลักฐานแท็บ Meta ที่หายหรือเปลี่ยนเจ้าของ')
        reason = proof['reason']
        if reason == 'tab_missing':
            valid = proof['tab_missing'] is True
        elif reason == 'tab_not_owned':
            valid = proof['tab_id'] >= 0 and not proof['tab_missing'] and not proof['session_owned']
        elif reason in {'tab_left_meta', 'route_home'}:
            valid = proof['tab_id'] >= 0 and not proof['tab_missing'] and proof['session_owned']
        else:
            valid = False
        if reason == 'route_home':
            route = body.get('route_evidence')
            stable = route.get('stable_ms') if isinstance(route, dict) else None
            valid = (valid and empty_home(route)
                     and type(route.get('samples')) is int and route['samples'] >= 2
                     and type(stable) in (int, float) and math.isfinite(stable) and stable >= 5000)
        job = self._job(package['job_id'])
        active = (job.get('status') == 'running' if self._manager(package['job_id']) is self.stories
                  else job.get('automation_status') == 'running')
        if not valid or not active or job.get('cancel_requested'):
            raise ValueError('งานหรือแท็บ Meta ยังไม่ตรงเงื่อนไขเริ่มฉากที่ค้างใหม่')
        if (not receipt or receipt.get('context_id') != package['context_id']
                or body.get('context_id') != package['context_id']):
            raise ValueError('ผล Meta ไม่ตรงงาน ฉาก หรือภาพที่ส่ง')
        # A lost response can be replayed only against this exact direct child.
        if (body.get('request_id') == receipt.get('retry_previous_request_id')
                and receipt.get('fresh_start_evidence') == proof):
            return dict(receipt)
        if body.get('request_id') != receipt.get('request_id'):
            raise ValueError('เจ้าของคำขอ Meta เปลี่ยนแล้ว • เก็บรอบใหม่ไว้')
        if (receipt.get('stage') == 'stored' or str(package['index']) in (job.get('meta_clips') or {})
                or receipt.get('stage') not in self.STAGES + ('needs_attention',)
                or receipt.get('resume_stage') == 'redesigning'):
            raise ValueError('ฉาก Meta บันทึกแล้วหรือยังมีขั้นภาพที่ต้องทำต่อ')
        if (receipt.get('stage') == 'prepared'
                and time.time() < float(receipt.get('fresh_start_not_before') or 0)):
            return dict(receipt)
        return self._fresh_scene(data, store, receipt, reason=reason, evidence=proof,
                                 route_evidence=body.get('route_evidence') if reason == 'route_home' else None)

    def _retry(self, data, store, receipt, body, package):
        proof = body.get('retry_evidence') or {}
        answer = str(proof.get('answer_text') or '')
        reason = meta_reply_failure(answer)
        # A lost/concurrent due-event ACK must not allocate a second helper.
        repair = receipt.get('redesign') or {}
        if (receipt.get('stage') == 'redesigning'
                and repair.get('failure_reason') == reason == 'transient_service_error'
                and repair.get('failure_sha256') == hashlib.sha256(answer.encode()).hexdigest()):
            return dict(receipt)
        # Unknown sends, policy/quota, active processing and videos still loading
        # must never enter the new-attempt transition.
        if (receipt['stage'] != 'generating'
                or not receipt.get('conversation_url')
                or body.get('conversation_url') != receipt['conversation_url']
                or proof.get('matched_request') is not True
                or proof.get('answer_complete') is not True
                or proof.get('answer_truncated') is not False
                or proof.get('stop') is not False or proof.get('busy') is not False
                or type(proof.get('video_count')) is not int or proof['video_count'] != 0
                or not isinstance(proof.get('stable_ms'), (int, float))
                or not math.isfinite(proof['stable_ms']) or proof['stable_ms'] < 5000
                or not isinstance(proof.get('samples'), int) or proof['samples'] < 2
                or not 0 < len(answer) <= 12000
                or (receipt.get('choice') and (receipt['choice']['stage'] != 'accepted'
                    or proof.get('choice_prompt') != receipt['choice']['prompt']))
                or reason not in ('completed_no_video', 'transient_service_error')
                or meta_followup_offer(answer, package.get('aspect_ratio', '9:16'))):
            raise ValueError('ยังไม่มีหลักฐานว่า Meta ตอบจบโดยไม่มีวิดีโอ • ไม่ส่งซ้ำ')
        if reason == 'transient_service_error':
            outage = meta_safety_service_outage(answer) or receipt.get('safety_service_recovery') == 1
            if outage and proof.get('composer_empty') is not True:
                raise ValueError('ช่องพิมพ์ Meta ยังไม่ว่าง • เก็บงานเดิม ไม่ส่งซ้ำ')
            redesign = outage and int(receipt.get('service_retry_count') or 0) >= 1
            return self._service_retry(data, store, receipt, answer,
                                       redesign_body=body if redesign else None, package=package)
        count = int(receipt.get('retry_count') or 0)
        if count >= self.MAX_RETRIES:
            receipt.update(stage='needs_attention', resume_stage='generating', retry_exhausted=True,
                           failure_reason='completed_no_video', failure_answer_sha256=hashlib.sha256(answer.encode()).hexdigest(),
                           updated_at=time.time(), message='Meta ยังไม่คืนไฟล์วิดีโอหลังลองใหม่ 2 รอบ • กดทำงานต่อเพื่อเริ่มฉากนี้ในแชตใหม่')
            store.write_unlocked(data)
            return dict(receipt)
        archived = dict(receipt, failure_reason='completed_no_video',
                        failure_answer_sha256=hashlib.sha256(answer.encode()).hexdigest(),
                        failure_excerpt=answer[:700])
        data.setdefault('attempt_history', {}).setdefault(str(receipt['index']), []).append(archived)
        successor = dict(job_id=receipt['job_id'], index=receipt['index'], context_id=receipt['context_id'],
                         request_id=uuid.uuid4().hex, stage='prepared', updated_at=time.time(),
                         retry_count=count + 1, retry_previous_request_id=receipt['request_id'],
                         message=f'Meta ไม่ได้คืนวิดีโอ • เตรียมรูปและพรอมต์เดิมใหม่ รอบ {count + 1}/{self.MAX_RETRIES}')
        if receipt.get('service_retry_count'):
            successor['service_retry_count'] = receipt['service_retry_count']
        data['scenes'][str(receipt['index'])] = successor
        store.write_unlocked(data)
        return dict(successor)

    def _service_retry(self, data, store, receipt, answer, *, redesign_body=None, package=None):
        """Schedule, then claim one successor only on fresh completed-error proof.

        This is a recovery substate, not a backwards jump in the linear media
        stages. Elapsed time alone never authorizes a retry. _retry revalidates
        owner, cancellation, completed reply and absence of activity/media first.
        """
        now = time.time()
        answer_hash = hashlib.sha256(answer.encode()).hexdigest()
        attempt = int(receipt.get('service_retry_count') or 0) + 1
        recovery = receipt.get('recovery') if isinstance(receipt.get('recovery'), dict) else {}
        if (recovery.get('protocol') != 1 or recovery.get('category') != 'transient_service_error'
                or recovery.get('state') != 'cooldown' or recovery.get('attempt') != attempt
                or recovery.get('answer_sha256') != answer_hash
                or type(recovery.get('next_retry_at')) not in (int, float)
                or not math.isfinite(recovery['next_retry_at'])):
            scoped_loop = meta_safety_service_outage(answer) or receipt.get('safety_service_recovery') == 1
            rounds = int(receipt.get('redesign_round') or 0) if scoped_loop else 0
            delay = self.SERVICE_RETRY_DELAYS[min(attempt - 1 + 2 * rounds, len(self.SERVICE_RETRY_DELAYS) - 1)]
            receipt.update(recovery=dict(protocol=1, category='transient_service_error', state='cooldown',
                                         attempt=attempt, started_at=now, next_retry_at=now + delay,
                                         answer_sha256=answer_hash, excerpt=answer[:700]),
                           updated_at=now,
                           message=f'Meta แจ้งข้อผิดพลาดของบริการ • รอ {delay} วินาทีแล้วตรวจผลก่อนเริ่มใหม่ รอบ {attempt}')
            store.write_unlocked(data)
            return dict(receipt)
        if now < recovery['next_retry_at']:
            return dict(receipt)
        if redesign_body is not None:
            return self._redesign_prepare(data, store, receipt, redesign_body, package)
        archived = dict(receipt, failure_reason='transient_service_error',
                        failure_answer_sha256=answer_hash, failure_excerpt=answer[:700])
        data.setdefault('attempt_history', {}).setdefault(str(receipt['index']), []).append(archived)
        successor = dict(job_id=receipt['job_id'], index=receipt['index'], context_id=receipt['context_id'],
                         request_id=uuid.uuid4().hex, stage='prepared', updated_at=now,
                         retry_count=int(receipt.get('retry_count') or 0), service_retry_count=attempt,
                         retry_previous_request_id=receipt['request_id'],
                         message=f'กู้ข้อผิดพลาดบริการ Meta รอบ {attempt} • เตรียมรูปและพรอมต์เดิมในแชตใหม่')
        data['scenes'][str(receipt['index'])] = successor
        if meta_safety_service_outage(answer) or receipt.get('safety_service_recovery') == 1:
            successor['safety_service_recovery'] = 1
        if receipt.get('redesign_round'):
            successor['redesign_round'] = receipt['redesign_round']
        if receipt.get('scene_video_plan'):
            successor['scene_video_plan'] = dict(receipt['scene_video_plan'])
        store.write_unlocked(data)
        return dict(successor)

    def _choice(self, data, store, receipt, body, package):
        if (receipt['stage'] != 'generating' or not receipt.get('conversation_url')
                or body.get('conversation_url') != receipt['conversation_url']):
            raise ValueError('คำตอบเลือก Meta ไม่ตรงขั้นตอนหรือบทสนทนาเดิม')
        action = body['stage']
        choice = receipt.get('choice')
        if action == 'choice_prepare':
            proof = body.get('choice_evidence') or {}
            answer = str(proof.get('answer_text') or '')
            comparison = proof.get('comparison') is True
            offer = (meta_comparison_offer(proof.get('comparison_branches'), package.get('aspect_ratio', '9:16'))
                     if comparison else meta_followup_offer(answer, package.get('aspect_ratio', '9:16')))
            if (not offer or proof.get('matched_request') is not True
                    or comparison and (type(proof.get('selected_branch')) is not int
                                       or proof['selected_branch'] != offer['proposal_branch']
                                       or answer != offer['proposal_text'])
                    or proof.get('answer_complete') is not True or proof.get('answer_truncated') is not False
                    or proof.get('stop') is not False or proof.get('busy') is not False
                    or type(proof.get('video_count')) is not int or proof['video_count'] != 0
                    or not isinstance(proof.get('stable_ms'), (int, float))
                    or not math.isfinite(proof['stable_ms']) or proof['stable_ms'] < 5000
                    or not isinstance(proof.get('samples'), int) or proof['samples'] < 2):
                raise ValueError('Meta ยังไม่ได้เสนอทางเลือกที่ตอบจบและตรวจสอบได้')
            if choice:
                if (choice['proposal_text'] != offer['proposal_text']
                        or choice.get('proposal_branch') != offer.get('proposal_branch')
                        or choice.get('proposal_branches') != offer.get('proposal_branches')):
                    raise ValueError('Meta มีข้อเสนอใหม่หลังตอบเลือกแล้ว • เก็บคำตอบเดิมให้ตรวจ')
                return dict(receipt)
            receipt['choice'] = {**offer, 'stage': 'prepared', 'prepared_at': time.time(),
                                 'proposal_sha256': hashlib.sha256(offer['proposal_text'].encode()).hexdigest()}
            message = ('Meta เสนอฉากที่ปรับให้เหมาะสม • กำลังตอบรับในแชตเดิม'
                       if offer.get('kind') == 'safe_revision' else
                       'Meta เสนอ 2 ทางเลือก • กำลังตอบเลือกข้อ 2 ในแชตเดิม')
        else:
            if not choice or body.get('choice_prompt') != choice['prompt']:
                raise ValueError('คำตอบเลือก Meta ไม่ตรงข้อความที่บันทึก')
            if action == 'choice_send_intent':
                if choice['stage'] != 'prepared':
                    return {**receipt, 'choice_send_authorized': False}
                choice.update(stage='send_intent', send_at=time.time())
                message = 'กำลังตรวจว่า Meta รับคำตอบติดตามแล้ว • ไม่ส่งซ้ำ'
            else:
                if (choice['stage'] not in ('send_intent', 'accepted')
                        or body.get('matched_choice') is not True or body.get('user_count') != 2):
                    raise ValueError('ยังยืนยันข้อความตอบเลือกใน Meta ไม่ได้')
                choice.update(stage='accepted', accepted_at=choice.get('accepted_at') or time.time())
                message = 'Meta รับคำตอบติดตามแล้ว • รอวิดีโอจริงจากคำตอบใหม่'
        receipt.update(updated_at=time.time(), message=message)
        store.write_unlocked(data)
        # This one-shot authorization is NOT stored and cannot survive/replay an
        # uncertain press. A restarted worker observes acceptance, never resends.
        return {**receipt, **({'choice_send_authorized': True} if action == 'choice_send_intent' else {})}

    def _save_clip(self, package, body, receipt):
        source = Path(str(body.get('filename') or '')).resolve()
        if source.suffix.lower() != '.mp4' or not source.is_file() or source.stat().st_size < 1024:
            raise ValueError('ไฟล์ Meta ยังดาวน์โหลดไม่เสร็จหรือไม่ใช่ MP4')
        if self.validator:
            info = self.validator(source)
        else:
            from core.video_logo import VideoLogoRenderer
            info = VideoLogoRenderer().video_info(source)
        aspect_ratio = package.get('aspect_ratio', '9:16')
        expected_ratio = 16 / 9 if aspect_ratio == '16:9' else 9 / 16
        if (not 1 <= info['duration'] <= 120 or info['height'] <= 0
                or abs(info['width'] / info['height'] - expected_ratio) > .08):
            if aspect_ratio == '16:9':
                raise ValueError('วิดีโอ Meta ไม่ตรงแนวนอน 16:9 หรือความยาวผิดปกติ')
            raise ValueError('วิดีโอ Meta ไม่ตรงแนวตั้งหรือความยาวผิดปกติ')
        sha = digest(source)
        folder = self._folder(package['job_id'])
        target = working_video_folder(folder) / ('meta_scene_%02d_%s.mp4' % (package['index'], sha[:12]))
        with self._lock(package['job_id']):
            job = self._job(package['job_id'])
            from core.scene_video_plan import enabled as has_video_plan, assert_binding, verified_asset
            if has_video_plan(job):
                assert_binding(job, package['index'], body.get('scene_video_plan'), allow_legacy_active=True)
                kept = verified_asset(folder, job, package['index'], fresh=True)
                if kept:
                    if kept['provider'] == 'meta_ai' and kept['sha256'] == sha:
                        return dict(path=kept['path'], sha256=sha, duration=kept['duration'])
                    raise ValueError('ฉากนี้มีคลิปที่เก็บไว้แล้ว • ไม่รับผล Meta ทับ')
            for key, proof in (job.get('meta_clip_receipts') or {}).items():
                if key != str(package['index']) and proof.get('sha256') == sha:
                    raise ValueError('วิดีโอ Meta ซ้ำกับฉากอื่น • ไม่ใช้คลิปเก่าแทน')
            if not target.is_file():
                temporary = target.with_suffix('.partial')
                shutil.copyfile(source, temporary)
                if digest(temporary) != sha:
                    raise ValueError('ไฟล์ Meta เปลี่ยนระหว่างบันทึก')
                os.replace(temporary, target)
            relative = str(target.relative_to(folder))
            job.setdefault('meta_clips', {})[str(package['index'])] = relative
            job.setdefault('meta_clip_receipts', {})[str(package['index'])] = dict(
                sha256=sha, context_id=package['context_id'], request_id=receipt['request_id'],
                download_id=receipt['download_id'], duration=info['duration'])
            if aspect_ratio == '16:9':
                job['meta_clip_receipts'][str(package['index'])].update(
                    aspect_ratio=aspect_ratio, width=info['width'], height=info['height'])
            if receipt.get('choice', {}).get('stage') == 'accepted':
                job['meta_clip_receipts'][str(package['index'])]['choice'] = {
                    key: receipt['choice'][key] for key in ('number', 'text', 'proposal_sha256', 'prompt')}
            job['meta_clip_count'] = len(job['meta_clips'])
            if str(package['job_id']).startswith('JOB-'):
                from core.product_manager import ProductManager
                ProductManager._refresh_product_segment_state(job)
            self._save_job(package['job_id'], job)
        return dict(path=relative, sha256=sha, duration=info['duration'])

    def clips(self, job_id):
        job = self._job(job_id)
        result = []
        if str(job_id).startswith('JOB-'):
            count = int(job.get('flow_target_clip_count') or len(
                job.get('composition_images') or job.get('generated_images') or job.get('source_images') or []
            ) or 3)
        else:
            count = int(job.get('scene_count') or 0)
        for index in range(1, count + 1):
            package, receipt = self.package(job_id, index), self.get(job_id, index)
            if receipt.get('stage') != 'stored' or receipt.get('context_id') != package['context_id']:
                raise ValueError('วิดีโอ Meta ยังไม่ครบทุกฉาก')
            path = self._folder(job_id) / receipt['path']
            if not path.is_file() or digest(path) != receipt['sha256']:
                raise ValueError('ไฟล์ Meta ที่บันทึกไว้เปลี่ยนหรือหายไป')
            result.append(path)
        return result
