"""Provider-authored motion prompts bound to canonical image bytes and settings."""
import hashlib
import json
import re
from pathlib import Path
from core.atomic_json import AtomicJsonFile
from core.media_audio import flow_audio_instruction
from core.motion_json_contract import motion_json_contract
from core.product_visual_contract import visual_context, visual_request, can_revise_visual
from core.story_visual_plan import motion_request as story_motion_request, repair_available, visual_action

DECLARATION = "ในรูปเป็นบุคคลที่ไม่มีอยู่จริงสร้างโดยai"
CLARIFICATION = "บุคคลในภาพเป็นตัวละครสมมติที่สร้างด้วย AI ไม่ใช่บุคคลจริง"


def _closed_motion_object(text):
    """A streaming prefix cannot spend the durable formatting allowance."""
    start = None
    stack, quoted, escaped = [], False, False
    for offset, char in enumerate(text):
        if start is None:
            if char != '{':
                continue
            start = offset
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in '{[':
            stack.append(char)
        elif char in '}]':
            if not stack or stack.pop() != ('{' if char == '}' else '['):
                return False
            if not stack:
                closed = text[start:offset + 1]
                if all(field in closed for field in ('"prompt"', '"context_id"')):
                    return True
                # An unrelated earlier object is not completion evidence for
                # the actual motion answer that follows it.
                start = None
    return False


def _ambiguous_motion_objects(text):
    """Do not turn choosing between complete answers into JSON formatting."""
    fields = {'job_id', 'index', 'context_id', 'prompt', 'needs_review',
              'reference_compatible', 'material_change', 'review_reason'}
    roots = list(re.finditer(r'\{\s*"(?:' + '|'.join(sorted(fields)) + r')"\s*:', text))[-20:]
    decoder, unique = json.JSONDecoder(), set()
    for root in roots:
        try:
            value, _ = decoder.raw_decode(text, root.start())
        except (ValueError, RecursionError):
            continue
        if not isinstance(value, dict) or not fields.intersection(value):
            continue
        unique.add(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
        if len(unique) > 1:
            return True
    return False


def motion_format_request(context, answer, original_request=''):
    """Formatting clarification bound to the actual image/scene, never a rewrite."""
    identifiers = {field: context[field] for field in ('job_id', 'index', 'context_id')}
    request = (
        'Text-only JSON formatting correction of the previous motion-plan response; do not generate media. '
        'Return exactly one JSON object, without a code fence or explanation. '
        'Required fields: job_id (string), index (integer), context_id (string), '
        'prompt (string, 40–2500 characters), needs_review (boolean), reference_compatible (boolean), '
        'material_change (boolean). Optional review_reason is a string. Copy the supplied identifiers exactly. '
        'Preserve the existing prompt substance, action, direction, reference and every explicit content decision. '
        'Do not convert a review or incompatibility into approval; do not invent missing semantic values. '
        'If a value cannot be determined from the original request and answer, explain the actual uncertainty '
        'in review_reason and keep needs_review true.\n'
        + motion_json_contract(context) + '\nACTUAL REPAIR DATA:\n'
        + json.dumps({'identifiers': identifiers, 'current_context': context,
                      'original_request': original_request, 'previous_answer': answer}, ensure_ascii=False))
    if len(request) > 20000:
        raise ValueError('FLOW_PLAN_REVIEW • คำขอแก้รูปแบบยาวเกินกำหนด ไม่ตัดข้อมูลฉากทิ้ง')
    return request


def _format_request_for_record(record, context):
    if not record:
        return ''
    if record.get('format_request'):
        return record['format_request']
    if record.get('phase') not in {'answered_text', 'answered'} or not (record.get('validation') or {}).get('repairable'):
        return ''
    answer = record.get('answer_text') if record.get('phase') == 'answered_text' else json.dumps(record.get('result'), ensure_ascii=False)
    return motion_format_request(context, answer, record.get('request', ''))


def motion_text_review(answer, provider):
    """Only exact capability-only replies qualify, never appended policy reasons."""
    if _ambiguous_motion_objects(str(answer or '')):
        return {'errors': ['คำตอบพรอมต์มีหลายชุดขัดกัน ต้องตรวจคำตอบเดิม'],
                'repairable': False, 'repair_kind': 'ambiguous_json'}
    text = re.sub(r"\s+", " ", str(answer or "")).strip()
    text = re.sub(r"^Gemini\s*บอกว่า\s*", "", text).strip().rstrip(".!。")
    capability = provider == "gemini" and text in {
        "ฉันเป็นแค่โมเดลภาษา และไม่สามารถให้ความช่วยเหลือในเรื่องนี้ได้",
        "ฉันเป็นแค่โมเดลภาษา",
        "ฉันเป็นเพียงโมเดลภาษา",
        "ฉันไม่สามารถช่วยในเรื่องนี้ได้ เพราะเป็นแค่โมเดลภาษาและไม่เข้าใจคำถามนี้",
        "ฉันเป็นแค่โมเดลภาษา และคำถามนี้อยู่นอกเหนือความสามารถที่ออกแบบมาให้ฉันทำ",
        "ฉันเป็นเพียงโมเดลภาษา และคำถามนี้อยู่นอกเหนือความสามารถที่ออกแบบมาให้ฉันทำ",
    }
    json_format = all(x in str(answer or '') for x in ('"prompt"', '"context_id"')) and _closed_motion_object(str(answer or ''))
    return {"errors": ["Gemini ตอบข้อจำกัดความสามารถแทนข้อมูลพรอมต์" if capability else "JSON อ่านไม่ได้"],
            "repairable": capability or json_format,
            "repair_kind": "capability" if capability else "json_format" if json_format else "review"}


def provider_for(job):
    value = str(job.get("image_ai_provider") or "chatgpt").lower()
    if value not in {"chatgpt", "gemini"}:
        raise ValueError("FLOW_PLAN_REVIEW • ไม่รู้ผู้ให้บริการภาพเดิม")
    return value


def validate_motion_result(result, context):
    """Separate repairable schema errors from ownership/content conflicts."""
    errors, fatal = [], []
    if not isinstance(result, dict):
        return {"errors": ["result ต้องเป็น JSON object"], "repairable": False}
    for field in ("job_id", "index", "context_id"):
        if type(result.get(field)) is not type(context[field]) or result.get(field) != context[field]:
            fatal.append(field + " ไม่ตรงคำขอเดิม")
    for field, safe in (("needs_review", False), ("reference_compatible", True), ("material_change", False)):
        value = result.get(field)
        if type(value) is not bool:
            errors.append(field + " ต้องเป็น boolean ไม่ใช่ค่าว่างหรือข้อความ")
        elif value is not safe:
            fatal.append(field + " ระบุว่าต้องตรวจเนื้อหา")
    prompt = result.get("prompt")
    if not isinstance(prompt, str) or not 40 <= len(prompt.strip()) <= 2500:
        errors.append("prompt ต้องเป็นข้อความ 40–2500 ตัวอักษร")
    else:
        ratios = set(re.findall(r"(?<!\d)(\d{1,2}\s*:\s*\d{1,2})(?!\d)", prompt))
        if any(re.sub(r"\s", "", ratio) != context["aspect_ratio"] for ratio in ratios):
            fatal.append("aspect_ratio ขัดกับค่าของงาน")
        if re.search(r"bypass|ignore (?:all |previous )?instructions|หลบ(?:เลี่ยง)?ตัวกรอง", prompt, re.I):
            fatal.append("prompt มีคำสั่งหลบข้อจำกัด")
        if (DECLARATION in prompt or CLARIFICATION in prompt) and not context["fictional_confirmed"]:
            fatal.append("ยังไม่มีคำยืนยันตัวละครสมมติ")
    recheck_flags = {"needs_review ระบุว่าต้องตรวจเนื้อหา", "reference_compatible ระบุว่าต้องตรวจเนื้อหา"}
    # Product drafts can propose a cut to a setting absent from the reference.
    # Allow one provider-authored, same-image correction, NOT acceptance of
    # the conflicting prompt. Story/Drama material conflicts stay unchanged.
    product_reference = str(context.get("job_id", "")).startswith("JOB-")
    if product_reference:
        recheck_flags.add("material_change ระบุว่าต้องตรวจเนื้อหา")
    recheckable = bool(fatal) and not errors and (product_reference or result.get("material_change") is False) and all(
        item in recheck_flags for item in fatal)
    return {"errors": fatal + errors, "repairable": bool(errors) and not fatal, "content_recheckable": recheckable}


def plan_context(folder, job, index, relative=None):
    from core.product_editorial import assert_approved, enabled as editorial_enabled
    assert_approved(job)
    if type(index) is not int or not 1 <= index <= 50:
        raise ValueError("FLOW_PLAN_REVIEW • หมายเลขฉากไม่ถูกต้อง")
    story = str(job.get("id", "")).startswith("STORY-")
    relative = relative or f"generated/{'scene' if story else 'selling_image'}_{index:02d}.png"
    folder = Path(folder).resolve()
    image = (folder / relative).resolve()
    if not image.is_relative_to(folder / "generated") or not image.is_file():
        raise ValueError("FLOW_PLAN_REVIEW • ไม่พบภาพที่บันทึกแล้วของฉากนี้")
    provider = provider_for(job)
    ratio = "16:9" if job.get("long_video") else "9:16"
    prompts = job.get("scene_prompts" if story else "image_prompts") or []
    beats = job.get("scene_narrations" if story else "flow_shot_prompts") or []
    # Product analysis is checkpointed before final media commit. Use those
    # same fields, not empty strings, while preparing motion prompts.
    if not story:
        checkpoint = AtomicJsonFile(folder / "prompts" / "image_recovery.json").read({})
        analysis = checkpoint.get("analysis") or {}
        prompts = prompts or analysis.get("image_prompts") or []
        beats = beats or analysis.get("flow_shot_prompts") or []
        slot = (checkpoint.get("slots") or {}).get(str(index), {})
        if (slot.get("status") == "succeeded" and slot.get("effective_prompt")
                and slot.get("sha256") == hashlib.sha256(image.read_bytes()).hexdigest()):
            prompts = list(prompts)
            while len(prompts) < index:
                prompts.append("")
            prompts[index-1] = slot["effective_prompt"]
    from core.product_script import authored_product_script, film_scene
    if story and not editorial_enabled(job) and job.get("narration_script") and beats and not job.get('storytelling_options') and not job.get('actor_dialogue') and not authored_product_script(job):
        from core.story_manager import StoryManager
        _, beats, _ = StoryManager._ensure_engagement_cta(job["narration_script"], beats, job.get("topic", ""))
    context = {
        "job_id": job["id"], "index": index, "provider": provider,
        "image_file": image.relative_to(folder).as_posix(),
        "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "aspect_ratio": ratio, "title": job.get("video_title") or job.get("topic") or job.get("product_name") or "",
        "scene_description": str(prompts[index-1] if index <= len(prompts) else ""),
        "story_beat": str(beats[index-1] if index <= len(beats) else ""),
        "audio_instruction": ("No narrator, speech, vocals or lip-sync. Tell this scene through visual actions only."
            if (job.get('storytelling_options') or {}).get('mode') == 'visual' else
            flow_audio_instruction(job,index)
            if (job.get('actor_dialogue') or job.get('product_presentation_version') == 1)
               and (job.get('audio_choices') or {}).get('mode') in {'flow_original', 'api'} else
            "ใช้เสียงต้นฉบับ Flow แต่ไม่แต่งบทพูด โปรแกรมจะเติมบทพูดที่บันทึกไว้ตอนส่ง"
            if (job.get("audio_choices") or {}).get("mode") == "flow_original" else "ไม่เพิ่มบทพูดใหม่"),
        # AI generation alone does not prove the depicted person is fictional.
        "fictional_confirmed": job.get("fictional_ai_characters_confirmed") is True,
    }
    from core.generated_music import apply_to_prompt
    from core.product_pointing import enabled as pointing_review, visual_instruction
    from core.speech_delivery import enabled as speech_enabled, scene_delivery
    if speech_enabled(job):
        context['audio_instruction'] = flow_audio_instruction(job, index)
        context['speech_delivery'] = scene_delivery(job, index)
    if pointing_review(job):
        context['audio_instruction'] = (flow_audio_instruction(job, index)
            if (job.get('audio_choices') or {}).get('mode') == 'flow_original'
            else 'Do not generate speech or lip-sync. Preserve the saved silent or external voice-track mode.')
        context['product_visual_instruction'] = visual_instruction(job)
    context['audio_instruction'] = apply_to_prompt(job, index, context['audio_instruction'])
    identity = {key: context[key] for key in (
        "job_id", "index", "provider", "image_file", "image_sha256",
        "aspect_ratio", "audio_instruction", "fictional_confirmed",
        "scene_description", "story_beat")}
    if context.get('product_visual_instruction'):
        identity['product_visual_instruction'] = context['product_visual_instruction']
    if context.get('speech_delivery'):
        identity['speech_delivery'] = context['speech_delivery']
    if job.get('creative_brief'):
        from core.creative_brief import instruction
        context['creative_brief'] = json.loads(json.dumps(job['creative_brief'], ensure_ascii=False))
        context['creative_instruction'] = instruction(job)
        identity['creative_brief'] = context['creative_brief']
        identity['creative_instruction'] = context['creative_instruction']
    scene = film_scene(job, index)
    if scene is not None:
        context['product_film_scene'] = json.loads(json.dumps(scene))
        identity['product_film_scene'] = context['product_film_scene']
    context["content_binding_version"] = 2
    context["context_id"] = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return context


def motion_plan_action(folder, job, body):
    context = plan_context(folder, job, body.get("index"))
    if body.get("provider") != context["provider"]:
        raise ValueError("FLOW_PLAN_REVIEW • ผู้เขียนพรอมต์ไม่ตรงผู้สร้างภาพ")
    key = context["context_id"]
    store = AtomicJsonFile(Path(folder) / "prompts" / "flow_motion_plans.json")
    with store.locked():
        data = store.read_unlocked({"schema": 1, "plans": {}})
        record = data["plans"].get(key)
        proposed = visual_context(folder, job, context) if key and str(job['id']).startswith('JOB-') else None
        if proposed and proposed['context_id'] in data['plans']:
            context = proposed
            key = context['context_id']
            record = data['plans'][key]
        elif proposed:
            # Facts/narration changing after a visual revision must not silently
            # create another revision or reset its Send budget.
            if any((row.get('context') or {}).get('base_context_id') == key for row in data['plans'].values()):
                raise ValueError('FLOW_PLAN_REVIEW • ข้อมูลสินค้าเปลี่ยนหลังปรับแผน ต้องตรวจฉากเดิมก่อน')
        if record is None:
            # Adopt proven unchanged 279 ready records only. Preserve their
            # original keys/history; never turn an unknown Send into a retry.
            for previous in list(data["plans"].values()):
                old = previous.get("context") or {}
                if old.get('index') == context['index'] and previous.get('story_visual_repair'):
                    raise ValueError('FLOW_PLAN_REVIEW • ฉากเปลี่ยนหลังเริ่มแก้ภาพ ต้องตรวจคำขอภาพแก้เดิม ไม่เริ่มซ้ำ')
                if old.get("index") == context["index"] and previous.get("phase") in {"requested", "preparing", "answered_text"}:
                    raise ValueError("FLOW_PLAN_REVIEW • ฉากนี้มีคำขอเดิมที่ยังไม่รู้ผล แม้เนื้อหาเปลี่ยนก็ไม่ส่งซ้ำ")
                if old.get("index") != context["index"] or old.get("content_binding_version"):
                    continue
                if previous.get("phase") != "ready" or any(old.get(k) != context.get(k) for k in (
                    "job_id", "provider", "image_sha256", "image_file", "aspect_ratio",
                    "audio_instruction", "fictional_confirmed", "scene_description", "story_beat")):
                    raise ValueError("FLOW_PLAN_REVIEW • พรอมต์รุ่นเดิมต้องตรวจเนื้อหาหรือผลการส่งก่อน")
                record = {**previous, "context": context, "adopted_from": old.get("context_id")}
                data["plans"][key] = record
                store.write_unlocked(data)
                break
        if record is None and proposed:
            context = proposed
            key = context['context_id']
        action = body.get("action", "status")
        if action != "status" and body.get("context_id") != key:
            raise ValueError("FLOW_PLAN_REVIEW • ภาพหรือค่าฉากเปลี่ยนแล้ว")
        if action != 'status' and (job.get('cancel_requested') or job.get('status') in {'cancelled', 'deleted'}):
            raise ValueError('FLOW_PLAN_REVIEW • งานถูกยกเลิกแล้ว ไม่แก้คำขอหรือคำตอบเดิม')
        # Background supplies the authenticated sender tab URL. Keep this with
        # pending results so a closed tab cannot send Resume to a provider root.
        if action != 'status' and record:
            from core.ai_web_resume import conversation_url
            page = conversation_url(body.get('page_url'), context['provider'])
            if page:
                record = {**record, 'conversation_url': page}
        if str(action).startswith('story_visual_'):
            record, extra = visual_action(folder, job, body, context, record)
            data['plans'][key] = record
            store.write_unlocked(data)
            return {'ok': True, 'context': context, 'record': record, **extra}
        if action == 'revise_visual':
            if job.get('cancel_requested') or job.get('status') in {'cancelled', 'deleted'}:
                raise ValueError('FLOW_PLAN_REVIEW • งานถูกยกเลิกแล้ว ไม่เริ่มปรับแผน')
            validation = validate_motion_result((record or {}).get('result'), context)
            if not can_revise_visual(record, context, validation):
                raise ValueError('FLOW_PLAN_REVIEW • ฉากนี้ไม่ใช่คำตอบที่จบแล้วและขัดกับร่างภาพเดิม')
            if any((row.get('context') or {}).get('index') == context['index']
                   and row.get('phase') in {'preparing', 'requested', 'answered_text'} for row in data['plans'].values()):
                raise ValueError('FLOW_PLAN_REVIEW • ยังมีคำขอฉากนี้ที่ไม่ทราบผล')
            old_key = key
            context = proposed
            key = context['context_id']
            request = visual_request(context)
            if len(request) > 20000:
                raise ValueError('FLOW_PLAN_REVIEW • ข้อมูลฉากยาวเกินกำหนด ต้องตรวจโดยไม่ตัดข้อมูลทิ้ง')
            record = {'phase': 'preparing', 'context': context,
                      'request': request, 'visual_revision_attempt': 1,
                      'supersedes': old_key, 'revision_reason': 'reference_compatible_material_draft_conflict'}
            data['plans'][key] = record
            store.write_unlocked(data)
            return {'ok': True, 'claimed': True, 'context': context, 'record': record}
        elif action == "prepare":
            if record is None:
                request = visual_request(context) if context.get('product_visual_contract') else str(body.get("request") or "")
                if not request or len(request) > 20000:
                    raise ValueError("FLOW_PLAN_REVIEW • คำขอไม่ครบ")
                record = {"phase": "preparing", "context": context, "request": request}
                data["plans"][key] = record
                store.write_unlocked(data)
            return {"ok": True, "claimed": record.get("phase") == "preparing", "context": context, "record": record}
        elif action == "mark_sending":
            if not record or record.get("phase") != "preparing":
                raise ValueError("FLOW_PLAN_REVIEW • ไม่อนุญาตส่งคำขอเดิมซ้ำ")
            record = {**record, "phase": "requested"}
            data["plans"][key] = record
            store.write_unlocked(data)
        elif action == "claim":
            if record is None:
                record = {"phase": "requested", "context": context, "request": visual_request(context) if context.get('product_visual_contract') else str(body.get("request") or "")}
                if not record["request"] or len(record["request"]) > 20000:
                    raise ValueError("FLOW_PLAN_REVIEW • คำขอไม่ครบ")
                data["plans"][key] = record
                store.write_unlocked(data)
                return {"ok": True, "claimed": True, "context": context, "record": record}
        elif action == "review":
            if not record or record.get("phase") not in {"requested", "answered", "answered_text"}:
                raise ValueError("FLOW_PLAN_REVIEW • ไม่มีคำขอที่รอตรวจคำตอบ")
            if (record.get('validation') or {}).get('repair_kind') == 'ambiguous_json':
                raise ValueError('FLOW_PLAN_REVIEW • คำตอบเดิมมีหลายชุด ไม่เลือกคำตอบใดคำตอบหนึ่งแทนผู้ใช้')
            result = body.get("result")
            if len(json.dumps(result, ensure_ascii=False)) > 16000:
                raise ValueError("FLOW_PLAN_REVIEW • คำตอบยาวเกินกำหนด")
            validation = validate_motion_result(result, context)
            if record.get('phase') == 'answered_text' and not validation['errors']:
                record = {**record, 'prior_invalid_answer_text': record.get('answer_text'),
                          'prior_invalid_text_validation': record.get('validation')}
            # Retain the invalid cached answer when passive same-request
            # inspection recovers a later, correctly bound response.
            if record.get("phase") == "answered" and (record.get("validation") or {}).get("errors") and not validation["errors"]:
                record = {**record, "prior_invalid_answer": record.get("result"),
                          "prior_invalid_validation": record.get("validation")}
            record = {**record, "phase": "answered", "result": result, "validation": validation}
            data["plans"][key] = record
            store.write_unlocked(data)
            return {"ok": True, "context": context, "record": record, "validation": validation,
                    "format_request": _format_request_for_record(record, context),
                    "story_visual_repair_available": repair_available(record, context),
                    "revision_available": can_revise_visual(record, context, validation)}
        elif action == "review_text":
            if not record or record.get("phase") not in {"requested", "answered_text"}:
                raise ValueError("FLOW_PLAN_REVIEW • ไม่มีคำขอที่รอตรวจข้อความ")
            answer = body.get("answer_text")
            if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 16000:
                raise ValueError("FLOW_PLAN_REVIEW • ข้อความคำตอบว่างหรือยาวเกินกำหนด")
            if (record.get('validation') or {}).get('repair_kind') == 'ambiguous_json' and answer != record.get('answer_text'):
                raise ValueError('FLOW_PLAN_REVIEW • เก็บคำตอบหลายชุดเดิมไว้ ไม่เขียนทับหลักฐาน')
            validation = motion_text_review(answer, context["provider"])
            record = {**record, "phase": "answered_text", "answer_text": answer, "validation": validation}
            data["plans"][key] = record
            store.write_unlocked(data)
            return {"ok": True, "context": context, "record": record, "validation": validation,
                    "format_request": _format_request_for_record(record, context)}
        elif action == "recheck_content":
            if context.get('product_visual_contract'):
                raise ValueError('FLOW_PLAN_REVIEW • ปรับแผนภาพแล้ว ยังต้องแก้ข้อกำหนดหรือภาพเฉพาะฉาก ไม่ส่งซ้ำ')
            if not record or record.get("phase") != "answered":
                raise ValueError("FLOW_PLAN_REVIEW • ไม่มีคำตอบที่ยืนยันแล้วให้ตรวจภาพซ้ำ")
            if record.get("content_recheck_attempt"):
                return {"ok": True, "claimed": False, "context": context, "record": record}
            validation = validate_motion_result(record.get("result"), context)
            if not validation.get("content_recheckable"):
                raise ValueError("FLOW_PLAN_REVIEW • ไม่ใช่กรณีที่ตรวจภาพซ้ำได้")
            request = str(body.get("request") or "").strip()
            if not 20 <= len(request) <= 20000:
                raise ValueError("FLOW_PLAN_REVIEW • คำขอตรวจภาพไม่ครบ")
            record = {**record, "phase": "preparing", "content_recheck_attempt": 1,
                      "prior_content_answer": record["result"], "prior_content_validation": validation,
                      "original_content_request": record["request"], "request": request}
            data["plans"][key] = record
            store.write_unlocked(data)
            return {"ok": True, "claimed": True, "context": context, "record": record}
        elif action == "reformat":
            if not record or record.get("phase") not in {"requested", "answered", "answered_text"}:
                raise ValueError("FLOW_PLAN_REVIEW • ไม่พบคำขอที่รอตรวจรูปแบบ")
            if record.get("format_attempt"):
                return {"ok": True, "claimed": False, "context": context, "record": record}
            if record.get("phase") == "answered" and not (record.get("validation") or {}).get("repairable"):
                raise ValueError("FLOW_PLAN_REVIEW • ไม่ใช่ข้อผิดพลาดรูปแบบที่ซ่อมได้")
            answer = str(body.get("answer_text") or "").strip()
            if record.get("phase") == "answered_text" and answer != record.get("answer_text", "").strip():
                raise ValueError("FLOW_PLAN_REVIEW • ข้อความซ่อมไม่ตรงคำตอบที่บันทึก")
            text_review = motion_text_review(answer, context["provider"])
            if not 10 <= len(answer) <= 16000 or not text_review["repairable"]:
                raise ValueError("FLOW_PLAN_REVIEW • ไม่ใช่คำตอบ JSON ที่ยืนยันว่าซ่อมรูปแบบได้")
            request = motion_format_request(context, answer, record['request'])
            record = {**record, "phase": "requested", "format_attempt": 1, "repair_kind": text_review["repair_kind"], "original_request": record["request"], "answer_text": answer, "request": request, 'format_request': request}
            data["plans"][key] = record
            store.write_unlocked(data)  # durable before the one text-only Send
            return {"ok": True, "claimed": True, "context": context, "record": record, 'format_request': request}
        elif action == "save":
            if not record or record["phase"] not in {"requested", "answered", "ready"}:
                raise ValueError("FLOW_PLAN_REVIEW • ไม่มีคำขอเดิม")
            result = body.get("result") or {}
            if not isinstance(result, dict):
                raise ValueError("FLOW_PLAN_REVIEW • คำตอบต้องเป็น JSON object")
            validation = validate_motion_result(result, context)
            if validation["errors"]:
                raise ValueError("FLOW_PLAN_REVIEW • " + " • ".join(validation["errors"]))
            prompt = result["prompt"].strip()
            if context["aspect_ratio"] not in prompt:
                prompt = f"สร้างวิดีโอหนึ่งคลิปแนว {context['aspect_ratio']}\n" + prompt
            if context["fictional_confirmed"]:
                prompt = DECLARATION + "\n" + CLARIFICATION + "\n" + prompt.removeprefix(DECLARATION).lstrip().removeprefix(CLARIFICATION).lstrip()
            elif DECLARATION in prompt:
                raise ValueError("FLOW_PLAN_REVIEW • ยังไม่มีคำยืนยันว่าบุคคลเป็นตัวละครสมมติ")
            if record["phase"] == "ready" and record["prompt"] != prompt:
                raise ValueError("FLOW_PLAN_REVIEW • ไม่เขียนทับพรอมต์ที่ยืนยันแล้ว")
            record = {**record, "phase": "ready", "prompt": prompt}
            data["plans"][key] = record
            store.write_unlocked(data)
        elif action not in {"status", "claim"}:
            raise ValueError("FLOW_PLAN_REVIEW • คำสั่งไม่ถูกต้อง")
        return {"ok": True, "claimed": False, "context": context, "record": record,
                "format_request": _format_request_for_record(record, context),
                "visual_request": visual_request(context) if context.get('product_visual_contract') else story_motion_request(context) if str(job['id']).startswith('STORY-') else '',
                "story_visual_repair_available": repair_available(record, context),
                "revision_available": can_revise_visual(record, context,
                    validate_motion_result((record or {}).get('result'), context))}


def saved_motion_prompt(folder, job, index, relative):
    store_path = Path(folder) / "prompts" / "flow_motion_plans.json"
    if not store_path.exists():
        return ""  # Historical jobs keep their original package, not silent new requests.
    context = plan_context(folder, job, index, relative)
    record = motion_plan_action(folder, job, {"provider": context["provider"], "index": index})["record"]
    saved_context = (record or {}).get('context') or {}
    if not record or record.get("phase") != "ready" or (saved_context.get('base_context_id') or saved_context.get("context_id")) != context["context_id"]:
        raise ValueError("FLOW_PLAN_REVIEW • ภาพหรือค่าฉากไม่ตรงพรอมต์ที่บันทึก ต้องตรวจจาก AI เดิม")
    from core.generated_music import apply_to_prompt
    return apply_to_prompt(job, index, record["prompt"] + flow_audio_instruction(job, index, record["prompt"]))
