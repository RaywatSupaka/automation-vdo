"""Durable, provider-reviewed alternate illustrations per confirmed failed attempt.

Original media and analysis are never overwritten. Revised scene dialogue is
derived separately. This is a new content proposal, not a retry of a denied
request or a reset of a Send receipt.
"""
import base64
import copy
import hashlib
import io
import json
import re
from PIL import Image
from core.atomic_json import AtomicJsonFile
from core.flow_motion_plan import plan_context
from core.scene_context_revision import DuplicateSceneRevision, validate_revision, revised_story
from core.product_script import authored_product_script
from core.flow_review import completed_proposal_error


def creative_context(context, job, index, row):
    if row and row.get('creative_revision_version') == 1:
        context = {**context, 'creative_revision_version': 1,
                   'actor_dialogue': job.get('actor_dialogue') is True,
                   'scene_dialogue_turns': (job.get('scene_dialogue_turns') or [])[index-1] if index <= len(job.get('scene_dialogue_turns') or []) else [],
                   'storytelling_mode': (job.get('storytelling_options') or {}).get('mode', ''),
                   'cast_names': [actor.get('name') for actor in job.get('character_bible', [])]}
    return context


def replacement_action(folder, job, body):
    index, request_id = body.get('index'), body.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9-]{36}', request_id):
        raise ValueError('Invalid alternate-image request')
    if type(index) is not int or not 1 <= index <= len(job.get('generated_images') or []):
        raise ValueError('Invalid alternate-image scene')
    context = plan_context(folder, job, index, job['generated_images'][index-1])
    if job.get('cancel_requested') or job.get('status') in {'cancelled', 'deleted'}:
        raise ValueError('งานถูกยกเลิกแล้ว')
    if body.get('replacement_action') == 'begin' and (
            (job.get('flow_clips') or {}).get(str(index))
            or any(job.get(field) for field in ('video_path', 'final_video_path', 'final_path'))):
        raise ValueError('ฉากหรืองานนี้มีวิดีโอแล้ว')
    store = AtomicJsonFile(folder / 'prompts' / 'flow_replacement.json')
    with store.locked():
        data = store.read_unlocked({'scenes': {}})
        row = data['scenes'].get(str(index))
        action = body.get('replacement_action')
        context = creative_context(context, job, index, row)
        creative_round = row.get('creative_round', 0) if row else 0
        supplied_round = body.get('creative_round', 0)
        replay_redesign = bool(row and action == 'redesign' and row.get('redesign_from_round') == supplied_round)
        if row and row.get('creative_revision_version') == 1 and action != 'begin' and (
                type(supplied_round) is not int or (supplied_round != creative_round and not replay_redesign)):
            raise ValueError('ผลภาพ/บทเป็นของรอบซ่อมเก่า ไม่เขียนทับฉากปัจจุบัน')
        if action == 'begin':
            rebuild = body.get('rebuild_scene') is True and str(job['id']).startswith(('STORY-', 'JOB-'))
            ledger = AtomicJsonFile(folder / 'prompts' / 'flow_recovery.json').read({})
            events = ledger.get('scenes', {}).get(str(index), [])
            last = events[-1] if events else {}
            if rebuild and (last.get('request_id') != request_id or last.get('run_id') != body.get('run_id')
                            or not last.get('failure_id') or not last.get('fingerprint') or not last.get('reason')):
                raise ValueError('ไม่มีหลักฐานการสร้างวิดีโอล้มเหลวที่ตรงคำขอใหม่')
            if row and row['context_id'] != context['context_id']:
                raise ValueError('Alternate-image ownership changed')
            if row and row['request_id'] != request_id:
                old_failure = row.get('failure_id') or next((event.get('failure_id') for event in reversed(events)
                    if event.get('request_id') == row['request_id'] and event.get('failure_id')), '')
                next_attempt = rebuild and body.get('previous_request_id') == row['request_id'] and old_failure and old_failure != last.get('failure_id')
                legacy_revision = not rebuild and body.get('revise_story') and str(job['id']).startswith('STORY-') and not authored_product_script(job)
                # Explicit desktop Resume can replace a completed text proposal,
                # never an unknown image Send. Keep its old row/history intact.
                permit = AtomicJsonFile(folder / 'prompts' / 'flow_manual_resume.json').read({})
                review = next((event for event in reversed(events) if event.get('request_id') == row['request_id']
                               and event.get('digest') == permit.get('event_digest')), {})
                manual_proposal = (rebuild and bool(body.get('manual_resume_token'))
                    and body['manual_resume_token'] == permit.get('token')
                    and permit.get('job_id') == job['id'] and permit.get('index') == index
                    and permit.get('request_id') == row['request_id'] == body.get('previous_request_id')
                    and row.get('phase') == 'requested' and not row.get('image_file')
                    and review.get('phase') == 'needs_review'
                    and review.get('alternative_stage', 'proposal') in {'proposal', 'proposal_correction'}
                    and completed_proposal_error(review.get('error')))
                if not manual_proposal and (row.get('phase') != 'ready' or not (next_attempt or legacy_revision)):
                    raise ValueError('ฉากนี้มีงานภาพทดแทนที่ยังต้องตรวจสอบ')
                data.setdefault('history', {}).setdefault(str(index), []).append(row)
                row = None
            if not row:
                if last.get('run_id') != body.get('run_id') or not last.get('fingerprint') or not last.get('reason'):
                    raise ValueError('ไม่มีหลักฐานฉากล้มเหลวในรอบนี้')
                row = dict(request_id=request_id, phase='requested', context_id=context['context_id'],
                           provider=context['provider'], original_image=context['image_file'],
                           rebuild_scene=rebuild, failure_id=last.get('failure_id', ''),
                           revise_story=body.get('revise_story') is True and str(job['id']).startswith('STORY-') and not authored_product_script(job))
                if rebuild and row['revise_story'] and body.get('creative_revision_version') == 1:
                    row.update(creative_revision_version=1, creative_round=0)
        elif not row or row['request_id'] != request_id or row['context_id'] != context['context_id']:
            raise ValueError('Alternate-image ownership changed')
        elif action == 'redesign':
            candidate = body.get('candidate')
            if (row.get('creative_revision_version') != 1 or not isinstance(candidate, dict)
                    or any(type(candidate.get(flag)) is not bool for flag in ('needs_review', 'reference_compatible', 'material_change'))
                    or not isinstance(candidate.get('prompt'), str)
                    or (candidate['needs_review'] is False and candidate['reference_compatible'] is True and candidate['material_change'] is False)):
                raise ValueError('ไม่มีคำตอบตรวจภาพใหม่ที่ยืนยันว่าต้องออกแบบฉากใหม่')
            digest = hashlib.sha256(json.dumps(candidate, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if replay_redesign:
                if row.get('redesign_digest') != digest or row.get('phase') != 'requested' or row.get('revision'):
                    raise ValueError('หลักฐานรอบออกแบบใหม่เปลี่ยนแล้ว')
            else:
                if (row.get('phase') != 'image_saved' or not row.get('image_file')
                        or (job.get('flow_clips') or {}).get(str(index))
                        or any(job.get(field) for field in ('video_path', 'final_video_path', 'final_path'))):
                    raise ValueError('ยังไม่มีผลตรวจภาพที่เสร็จแล้ว หรือฉากสำเร็จไปแล้ว ไม่เริ่มภาพใหม่')
                data.setdefault('history', {}).setdefault(str(index), []).append(copy.deepcopy(row))
                row = {key: value for key, value in row.items() if key in {
                    'request_id', 'context_id', 'provider', 'original_image', 'rebuild_scene',
                    'failure_id', 'revise_story', 'creative_revision_version'}}
                row.update(phase='requested', creative_round=creative_round + 1,
                           redesign_from_round=creative_round, redesign_digest=digest)
        elif action == 'image_wait':
            state = body.get('wait_state')
            if state not in {'checking_empty', 'empty_after_refresh'}:
                raise ValueError('Invalid replacement wait state')
            # A late observation must never downgrade an acknowledged image.
            if row.get('phase') == 'requested':
                row['image_wait_state'] = state
        elif action in {'proposal', 'proposal_check'}:
            if not row.get('revise_story'):
                raise ValueError('ไม่ได้เปิดการเปลี่ยนเนื้อเรื่อง')
            history = [item.get('revision', {}) for item in data.get('history', {}).get(str(index), [])]
            try:
                revision = validate_revision(body.get('candidate'), context, history)
                # Validate exact speaker/listener assignments before any image
                # spend, including the newly authorized per-scene dialogue.
                effective = revised_story(job, {str(index): {'phase': 'ready', 'revision': revision}})
            except ValueError as error:
                if (action != 'proposal_check' or row.get('revision') or row.get('phase') != 'requested'
                        or (not isinstance(error, DuplicateSceneRevision) and row.get('creative_revision_version') != 1)):
                    raise
                candidate = body['candidate']
                digest = hashlib.sha256(json.dumps(candidate, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                rejected = row.setdefault('rejected_proposals', [])
                if not any(item['digest'] == digest for item in rejected):
                    rejected.append({'digest': digest, 'candidate': candidate, 'reason': str(error)})
                row['proposal_feedback'] = {'code': 'duplicate_story' if isinstance(error, DuplicateSceneRevision) else 'revision_invalid',
                                            'reason': str(error), 'digest': digest}
            else:
                if row.get('revision') and row['revision'] != revision:
                    raise ValueError('เนื้อเรื่องฉบับนี้บันทึกแล้ว ไม่เขียนทับ')
                # Verify dialogue ownership before spending image/video credits.
                row['revision'] = revision
                row.pop('proposal_feedback', None)
                if row.get('creative_revision_version') == 1:
                    from core.media_audio import flow_audio_instruction
                    row['motion_context'] = {**context, 'story_beat': revision['scene_narration'],
                        'scene_description': revision['prompt'],
                        'audio_instruction': flow_audio_instruction(effective, index),
                        'scene_dialogue_turns': copy.deepcopy(revision.get('scene_dialogue_turns', []))}
        elif action == 'image':
            if row.get('revise_story') and not row.get('revision'):
                raise ValueError('ต้องบันทึกเนื้อเรื่องใหม่ก่อนสร้างภาพ')
            encoded = body.get('image', '')
            if not isinstance(encoded, str) or len(encoded) > 18_000_000 or not re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+=*', encoded):
                raise ValueError('Invalid alternate image')
            raw = base64.b64decode(encoded.split(',', 1)[1], validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.width < 96 or image.height < 96 or image.width * image.height > 25_000_000:
                    raise ValueError('Invalid alternate image dimensions')
                expected = 16/9 if job.get('long_video') else 9/16
                if abs(image.width / image.height - expected) > .12:
                    raise ValueError('ภาพทดแทนมีสัดส่วนไม่ตรงงาน')
                buffer = io.BytesIO()
                image.convert('RGB').save(buffer, format='PNG')
            raw = buffer.getvalue()
            digest = hashlib.sha256(raw).hexdigest()
            if row.get('rebuild_scene'):
                with Image.open(folder / row['original_image']) as original:
                    original_bytes = io.BytesIO()
                    original.convert('RGB').save(original_bytes, format='PNG')
                if digest == hashlib.sha256(original_bytes.getvalue()).hexdigest():
                    raise ValueError('ต้องได้ภาพฉากใหม่ ไม่ใช้ภาพต้นฉบับเดิมซ้ำ')
            if (row.get('revise_story') or row.get('rebuild_scene')) and digest in {item.get('image_sha256') for item in data.get('history', {}).get(str(index), [])}:
                raise ValueError('ภาพนี้เคยใช้ในบริบทที่ไม่ผ่านแล้ว')
            if row.get('image_sha256') and row['image_sha256'] != digest:
                raise ValueError('ภาพทดแทนถูกบันทึกแล้ว ไม่เขียนทับ')
            suffix = f'-r{creative_round}' if creative_round else ''
            relative = f'generated/recovery-{index:02d}-{request_id}{suffix}.png'
            target = folder / relative
            # Unique path + atomic publication; never replace source images.
            temporary = target.with_suffix('.part')
            temporary.write_bytes(raw)
            temporary.replace(target)
            row.update(phase='ready' if row.get('phase') == 'ready' else 'image_saved', image_file=relative, image_sha256=digest)
        elif action == 'ready':
            candidate = body.get('candidate') or {}
            if not isinstance(candidate, dict):
                raise ValueError('Invalid alternate video response')
            if (not row.get('image_file') or candidate.get('needs_review') is not False
                    or candidate.get('reference_compatible') is not True or candidate.get('material_change') is not False):
                raise ValueError('ภาพหรือสาระของฉากทดแทนยังต้องตรวจสอบ')
            prompt = candidate.get('prompt')
            if (not isinstance(prompt, str) or not 40 <= len(prompt) <= 2500
                    or context['aspect_ratio'] not in prompt
                    or re.search(r'bypass|ignore (?:all |previous )?instructions|หลบ(?:เลี่ยง)?ตัวกรอง', prompt, re.I)):
                raise ValueError('Invalid alternate video prompt')
            if row.get('phase') == 'ready' and row.get('prompt') != prompt:
                raise ValueError('พรอมต์ทดแทนถูกบันทึกแล้ว')
            effective_prompt = prompt
            if row.get('creative_revision_version') == 1:
                instruction = str((row.get('motion_context') or {}).get('audio_instruction') or '')
                if row.get('revision', {}).get('dialogue_revision_version') == 1 and 'ACTOR DIALOGUE:' not in instruction:
                    raise ValueError('ยังไม่มีบทนักแสดงฉบับใหม่ที่ตรวจแล้ว')
                if instruction and instruction not in effective_prompt:
                    effective_prompt += instruction
            from core.generated_music import apply_to_prompt
            effective_prompt = apply_to_prompt(job, index, effective_prompt)
            row.update(phase='ready', prompt=prompt, effective_prompt=effective_prompt,
                       change_summary=str(candidate.get('change_summary') or '')[:1500])
        else:
            raise ValueError('Invalid alternate-image action')
        data['scenes'][str(index)] = row
        store.write_unlocked(data)
        context = creative_context(context, job, index, row)
        if row.get('revise_story'):
            context = {**context, 'previous_scene': (job.get('scene_narrations') or [''])[index-2] if index > 1 else '',
                       'next_scene': (job.get('scene_narrations') or [])[index] if index < len(job.get('scene_narrations') or []) else '',
                       'previous_contexts': [item.get('revision', {}) for item in data.get('history', {}).get(str(index), [])]}
        if row.get('rebuild_scene'):
            context = {**context, 'previous_visuals': [dict(prompt=item.get('prompt', ''),
                change_summary=item.get('change_summary', '')) for item in data.get('history', {}).get(str(index), [])][-8:]}
    return {'ok': True, 'replacement': row, 'context': context}


def apply_replacement(folder, job, index, package):
    row = AtomicJsonFile(folder / 'prompts' / 'flow_replacement.json').read({}).get('scenes', {}).get(str(index))
    if not row or row.get('phase') != 'ready':
        return
    context = plan_context(folder, job, index, job['generated_images'][index-1])
    if row['context_id'] != context['context_id']:
        raise ValueError('ภาพต้นฉบับเปลี่ยน ต้องตรวจภาพทดแทนก่อน')
    image = folder / row['image_file']
    if not image.is_file() or hashlib.sha256(image.read_bytes()).hexdigest() != row['image_sha256']:
        raise ValueError('ไฟล์ภาพทดแทนไม่ตรงหลักฐาน')
    prompt = row.get('effective_prompt') or row['prompt']
    if row.get('creative_revision_version') == 1 and row.get('revision', {}).get('dialogue_revision_version') == 1:
        instruction = str((row.get('motion_context') or {}).get('audio_instruction') or '')
        if not instruction or 'ACTOR DIALOGUE:' not in instruction:
            raise ValueError('ยังไม่มีบทนักแสดงฉบับใหม่ที่ตรวจแล้ว')
        if instruction not in prompt:
            prompt += instruction
    from core.generated_music import apply_to_prompt
    prompt = apply_to_prompt(job, index, prompt)
    package.update(image_files=[row['image_file']], video_prompt=prompt,
                   motion_prompt_ready=True, replacement_id=row['request_id'])
