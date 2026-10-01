"""Pre-Flow Story visual repair. Never invent a Flow failure or replace originals."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from PIL import Image
from core.motion_json_contract import motion_json_contract


SCENE_ACTION_RULE = """ข้อกำหนดภาพและการเคลื่อนไหวร่วมกัน: ในแต่ละ scene_prompt ระบุเหตุการณ์หลักที่ต้องคงไว้ จุดเริ่มต้นและปลายทางของการกระทำ และภาพจังหวะเริ่มต้นเพียงจังหวะเดียว แล้วให้ flow_shot_prompts ใช้เหตุการณ์เดียวกัน ห้ามสลับเข้า/ออก ผู้ให้/ผู้รับ หรือก่อน/หลังเหตุการณ์
ระบุความสัมพันธ์ระหว่างตัวละครกับสถานที่ให้ชัด เช่นเดินออกจากเมืองต้องเคลื่อนห่างเมือง ไม่ใช้เพียงคำว่า foreground/background หรือหันหลังกล้องแทนทิศทางของเหตุการณ์ กล้องและท่าทางต้องไม่ขัดกัน ตรวจ scene_narrations, scene_prompts และ flow_shot_prompts แต่ละฉากก่อนส่ง ไม่วาดข้อคิดหรือคำชวนคอมเมนต์เป็นเหตุการณ์เพิ่ม"""

MOTION_RULE = """The attached image is the STARTING FRAME, not a frozen depiction of the whole narrated event. Preserve the essential story action, its direction, actors, objects, outcome and saved speech. First identify that action from the supplied scene and narration; moral commentary and audience calls to action are voiceover, not additional visible actions.
Write a concise English prompt, 2–4 short sentences, for exactly one continuous video at the requested aspect ratio. Describe natural visible action, subtle environmental motion and one simple camera move. Refer to visible roles, never personal names; do not repeat facial features, hair or clothing. A natural turn, pause or camera adjustment is allowed when it preserves the event. Leaving a city must remain leaving, not entering; giving must not become receiving. Do not follow a contradictory draft camera move.
reference_compatible means the proposed motion can start naturally from the actual reference. material_change means changing the essential STORY, identity or outcome, not a natural change of pose or camera. If keeping the story requires a different starting image, report the actual conflict in review_reason. Never force approval or hide content restrictions. Include exactly: All spoken dialogue must be in Thai only. Do not invent speech for silent scenes. No readable text or watermark.
Return JSON only: job_id, index, context_id, prompt (string 40–2500 characters), needs_review, reference_compatible, material_change (real booleans), review_reason. Copy identifiers exactly."""


def motion_request(context, previous=None):
    data = {"context": context}
    if previous is not None:
        data["previous_answer"] = previous
        data["task"] = "Correct the actual reported visual conflict using natural motion from this same image first."
    rule = MOTION_RULE
    if (context.get('speech_delivery') or {}).get('version') == 1:
        rule = rule.replace('moral commentary and audience calls to action are voiceover, not additional visible actions.',
                            'the saved speech placement determines who speaks; spoken commentary is not an extra visible action.')
        rule += ('\nWrite VISUAL MOTION ONLY in prompt. Do not copy dialogue or AUDIO blocks. '
                 'The desktop appends the exact saved SPEECH SCENE v1 block once. '
                 'Preserve its speaker/listener identities and on-camera/off-screen/behind-camera placement; '
                 'do not add a narrator, visible speaking face or lip-sync where the saved placement forbids it.')
    if context.get('product_visual_instruction'):
        rule += ('\nKeep the saved POINTING REVIEW camera-holder POV in the visible motion. '
                 'Describe only visual movement in prompt; do not include spoken text or lip-sync. '
                 'The desktop will append the exact saved audio instructions separately. '
                 + context['product_visual_instruction'])
    if 'ACTOR DIALOGUE:' in str(context.get('audio_instruction') or ''):
        rule = rule.replace('moral commentary and audience calls to action are voiceover, not additional visible actions.',
                            'this scene is performed by actors; no narrator or explanatory voiceover is allowed.')
        rule += '\nInclude the ordered Thai actor dialogue and speaker-to-visible-role assignments from audio_instruction. Keep listener reactions, natural lip synchronization and silent scenes intact. Do not replace dialogue with narration or direct-to-camera reviewing.'
    if 'AUDIO PERFORMANCE:' in str(context.get('audio_instruction') or ''):
        rule = rule.replace('moral commentary and audience calls to action are voiceover, not additional visible actions.',
                            'the supplied Thai line is spoken on camera by the visible reviewer, not a separate voiceover.')
        rule += '\nInclude the supplied Thai spoken line and on-camera audio performance in the video prompt. Natural synchronized mouth movement and expressive product interaction are required. Do not request silence or deferred narration.'
    return "Text-only video prompt planning; do not generate media.\n" + rule + "\n" + motion_json_contract(context) + "\nACTUAL SCENE DATA:\n" + json.dumps(data, ensure_ascii=False)


def repair_available(record, context):
    from core.flow_motion_plan import validate_motion_result
    if not str(context.get('job_id', '')).startswith('STORY-') or not record or record.get('phase') != 'answered':
        return False
    result = record.get('result') or {}
    errors = validate_motion_result(result, context)['errors']
    flags = {f'{name} ระบุว่าต้องตรวจเนื้อหา' for name in ('needs_review', 'reference_compatible', 'material_change')}
    return bool(errors) and all(error in flags for error in errors)


def _fail(message):
    raise ValueError('FLOW_PLAN_REVIEW • ' + message)


def _candidate_context(folder, job, repair):
    from core.flow_motion_plan import plan_context
    context = plan_context(folder, job, repair['index'], repair['image_file'])
    if context['image_sha256'] != repair['image_sha256']:
        _fail('ภาพแก้ไขเปลี่ยนจากหลักฐานเดิม')
    return context


def visual_action(folder, job, body, context, record):
    """Called inside the motion ledger lock; caller publishes returned record."""
    from core.flow_motion_plan import validate_motion_result, motion_text_review, motion_format_request, DECLARATION, CLARIFICATION
    if not str(job.get('id', '')).startswith('STORY-') or job.get('cancel_requested') or job.get('status') in {'cancelled', 'deleted'}:
        _fail('ไม่อนุญาตแก้ภาพของงานนี้')
    if any(job.get(k) for k in ('video_path', 'final_video_path', 'final_path')) or (job.get('flow_clips') or {}).get(str(context['index'])):
        _fail('ฉากหรืองานนี้มีวิดีโอแล้ว')
    action = body['action']
    record = dict(record or {})
    if action == 'story_visual_recheck':
        if not repair_available(record, context) or record.get('story_visual_revision'):
            _fail('ฉากนี้ไม่ได้รอแก้การเคลื่อนไหวหรือใช้รอบแก้แล้ว')
        return {**record, 'phase': 'preparing', 'story_visual_revision': 1,
                'prior_story_visual_answer': record.get('result'), 'prior_story_visual_request': record.get('request'),
                'request': motion_request(context, record.get('result'))}, {}
    repair = dict(record.get('story_visual_repair') or {})
    if action == 'story_visual_begin':
        if repair:
            return record, {}
        if not record.get('story_visual_revision') or not repair_available(record, context):
            _fail('ต้องตรวจการเคลื่อนไหวของภาพเดิมก่อนสร้างภาพแก้')
        rid = str(uuid.uuid4())
        request = (f"Create exactly one {context['aspect_ratio']} illustration using the attached original as reference. "
                   "Correct only the starting pose, spatial composition and action direction needed for the SAME story event. "
                   "Preserve characters, identities, ages, objects, setting and style. Do not change the story, add dialogue or reproduce unsafe content. "
                   "The picture is one starting moment for subsequent natural motion. No text or watermark. "
                   "If this cannot preserve the story safely, explain instead of generating.\n"
                   + json.dumps({'scene': context, 'actual_conflict': record.get('result'), 'request_id': rid}, ensure_ascii=False))
        repair = {'request_id': rid, 'index': context['index'], 'phase': 'preparing_image',
                  'base_context_id': context['context_id'], 'image_request': request}
    else:
        if not repair or body.get('request_id') != repair.get('request_id') or repair.get('base_context_id') != context['context_id']:
            _fail('คำขอแก้ภาพไม่ตรงฉากเดิม')
        if action == 'story_visual_mark_image':
            if repair['phase'] != 'preparing_image':
                _fail('มีคำขอภาพแก้เดิมแล้ว ไม่ส่งซ้ำ')
            url = str(body.get('conversation_url') or '')
            host = 'chatgpt.com' if context['provider'] == 'chatgpt' else 'gemini.google.com'
            if not re.fullmatch(r'https://' + re.escape(host) + r'/(?:c/[^/?#]+|app(?:/[^/?#]+)?)?', url):
                _fail('หน้าเว็บภาพแก้ไม่ตรงผู้ให้บริการ')
            repair.update(phase='image_requested', conversation_url=url)
        elif action == 'story_visual_image':
            if repair['phase'] not in {'image_requested', 'image_saved'}:
                _fail('ฉากนี้ไม่ได้รอไฟล์ภาพแก้')
            value = body.get('image')
            if not isinstance(value, str) or len(value) > 18_000_000 or not re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+=*', value):
                _fail('ข้อมูลภาพแก้ไม่ถูกต้อง')
            raw = base64.b64decode(value.split(',', 1)[1], validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                ratio = 16/9 if context['aspect_ratio'] == '16:9' else 9/16
                if min(image.size) < 256 or image.width * image.height > 25_000_000 or abs(image.width/image.height-ratio) > .12:
                    _fail('ขนาดหรือสัดส่วนภาพแก้ไม่ตรงงาน')
                buffer = io.BytesIO()
                image.convert('RGB').save(buffer, format='PNG')
            raw = buffer.getvalue()
            digest = hashlib.sha256(raw).hexdigest()
            if repair.get('image_sha256') and repair['image_sha256'] != digest:
                _fail('ภาพแก้บันทึกแล้ว ไม่เขียนทับด้วยภาพอื่น')
            relative = f"generated/visual-{context['index']:02d}-{repair['request_id']}.png"
            target = Path(folder) / relative
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                _fail('ไฟล์ภาพแก้เดิมไม่ตรงผลใหม่')
            if not target.exists():
                temp = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.part', delete=False) as handle:
                        temp = Path(handle.name)
                        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
                    os.replace(temp, target)
                finally:
                    if temp and temp.exists(): temp.unlink()
            repair.update(phase='image_saved', image_file=relative, image_sha256=digest)
        elif action == 'story_visual_prepare_motion':
            if repair['phase'] != 'image_saved':
                _fail('ยังไม่มีภาพแก้ที่บันทึกสำเร็จ')
            candidate_context = _candidate_context(folder, job, repair)
            repair.update(phase='preparing_motion', candidate_context=candidate_context,
                          motion_request=motion_request(candidate_context))
        elif action == 'story_visual_mark_motion':
            if repair['phase'] != 'preparing_motion':
                _fail('ส่งคำขอตรวจภาพใหม่แล้ว ไม่ส่งซ้ำ')
            _candidate_context(folder, job, repair)
            repair['phase'] = 'motion_requested'
        elif action == 'story_visual_review_text':
            if repair['phase'] not in {'motion_requested', 'motion_answered_text', 'motion_format_requested'}:
                _fail('ไม่มีคำขอพรอมต์ภาพแก้ที่รอตรวจข้อความ')
            candidate_context = _candidate_context(folder, job, repair)
            answer = body.get('answer_text')
            if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 16000:
                _fail('ข้อความคำตอบภาพแก้ว่างหรือยาวเกินกำหนด')
            if (repair.get('validation') or {}).get('repair_kind') == 'ambiguous_json' and answer != repair.get('answer_text'):
                _fail('เก็บคำตอบหลายชุดของภาพแก้เดิมไว้ ไม่เขียนทับหลักฐาน')
            validation = motion_text_review(answer, candidate_context['provider'])
            repair.update(phase='motion_answered_text', answer_text=answer, validation=validation)
            if validation['repairable'] and not repair.get('format_attempt'):
                repair['format_request'] = motion_format_request(candidate_context, answer, repair['motion_request'])
        elif action == 'story_visual_reformat':
            if repair.get('format_attempt'):
                return record, {'claimed': False}
            if repair['phase'] not in {'motion_answered_text', 'motion_answered'} or not (repair.get('validation') or {}).get('repairable'):
                _fail('คำตอบภาพแก้ไม่ใช่ข้อผิดพลาดรูปแบบที่ซ่อมได้')
            candidate_context = _candidate_context(folder, job, repair)
            if repair['phase'] == 'motion_answered_text':
                answer = repair['answer_text']
                if not motion_text_review(answer, candidate_context['provider'])['repairable']:
                    _fail('ข้อความภาพแก้ยังไม่ครบหรือไม่ใช่รูปแบบที่ซ่อมได้')
            else:
                if not validate_motion_result(repair.get('result'), candidate_context)['repairable']:
                    _fail('ผลตรวจภาพแก้ขัดกับฉาก ไม่แก้ธงตรวจเนื้อหา')
                answer = json.dumps(repair['result'], ensure_ascii=False)
            request = motion_format_request(candidate_context, answer, repair['motion_request'])
            repair.update(phase='preparing_motion_format', format_attempt=1,
                          original_motion_request=repair['motion_request'], original_answer_text=answer,
                          prior_format_result=repair.get('result'), prior_format_validation=repair.get('validation'),
                          motion_request=request, format_request=request)
            record['story_visual_repair'] = repair
            return record, {'claimed': True}
        elif action == 'story_visual_mark_format':
            if repair['phase'] != 'preparing_motion_format' or repair.get('format_attempt') != 1:
                _fail('ส่งคำขอแก้รูปแบบภาพแก้แล้ว ไม่ส่งซ้ำ')
            _candidate_context(folder, job, repair)
            repair['phase'] = 'motion_format_requested'
        elif action == 'story_visual_save':
            if repair['phase'] not in {'motion_requested', 'motion_answered_text', 'motion_answered', 'motion_format_requested', 'ready', 'needs_review'}:
                _fail('ยังไม่ได้ตรวจพรอมต์จากภาพใหม่')
            if (repair.get('validation') or {}).get('repair_kind') == 'ambiguous_json':
                _fail('คำตอบภาพแก้เดิมมีหลายชุด ไม่เลือกคำตอบใดคำตอบหนึ่งแทนผู้ใช้')
            candidate_context = _candidate_context(folder, job, repair)
            result = body.get('result')
            if len(json.dumps(result, ensure_ascii=False)) > 16000:
                _fail('คำตอบภาพแก้ยาวเกินกำหนด')
            validation = validate_motion_result(result, candidate_context)
            if repair['phase'] in {'ready', 'needs_review'} and repair.get('result') != result:
                _fail('ผลตรวจภาพแก้ถูกบันทึกแล้ว')
            if repair.get('answer_text') and not validation['errors']:
                repair.update(prior_invalid_answer_text=repair['answer_text'],
                              prior_invalid_text_validation=repair.get('validation'))
            repair.update(result=result, validation=validation)
            if validation['errors']:
                repair['phase'] = 'motion_answered' if validation['repairable'] else 'needs_review'
                if validation['repairable'] and not repair.get('format_attempt'):
                    repair['format_request'] = motion_format_request(candidate_context, json.dumps(result, ensure_ascii=False), repair['motion_request'])
            else:
                prompt = result['prompt'].strip()
                if candidate_context['aspect_ratio'] not in prompt:
                    prompt = f"One {candidate_context['aspect_ratio']} video. " + prompt
                if 'All spoken dialogue must be in Thai only.' not in prompt:
                    prompt += ' All spoken dialogue must be in Thai only.'
                if candidate_context['fictional_confirmed']:
                    prompt = DECLARATION + '\n' + CLARIFICATION + '\n' + prompt.removeprefix(DECLARATION).lstrip().removeprefix(CLARIFICATION).lstrip()
                repair.update(phase='ready', prompt=prompt)
                record.update(phase='ready', prompt=prompt)
        else:
            _fail('คำสั่งแก้ภาพไม่ถูกต้อง')
    record['story_visual_repair'] = repair
    return record, {}


def repaired_image(folder, job, index, relative):
    from core.flow_motion_plan import motion_plan_action
    if not (Path(folder) / 'prompts/flow_motion_plans.json').exists():
        return relative
    status = motion_plan_action(folder, job, {'index': index, 'provider': job.get('image_ai_provider') or 'chatgpt'})
    record = status.get('record') or {}
    repair = record.get('story_visual_repair') or {}
    if record.get('phase') != 'ready' or repair.get('phase') != 'ready':
        return relative
    _candidate_context(folder, job, repair)
    return repair['image_file']
