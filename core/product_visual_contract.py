"""Product visual brief separate from AI-authored draft camera/cut choices."""
import hashlib
import json
from pathlib import Path
from core.atomic_json import AtomicJsonFile


def visual_context(folder, job, base):
    analysis = AtomicJsonFile(Path(folder) / 'prompts' / 'image_recovery.json').read({}).get('analysis') or {}
    # The analysis checkpoint is canonical before AND after apply_ai_result;
    # importer TTS normalization must not invalidate a completed motion plan.
    segments = analysis.get('spoken_script_segments') or job.get('spoken_script_segments') or []
    index = base['index']
    segment = segments[index - 1] if index <= len(segments) else ''
    narration = segment.get('text', '') if isinstance(segment, dict) else str(segment)
    contract = {
        'version': 1, 'visual_brief': base['scene_description'],
        'product_name': job.get('product_name') or base['title'],
        'product_information': str(job.get('description') or ''),
        'saved_narration': narration,
    }
    context = {**base, 'base_context_id': base['context_id'],
               'content_binding_version': 3, 'product_visual_contract': contract,
               'story_beat': base['scene_description'], 'title': contract['product_name']}
    context.pop('context_id')
    context['context_id'] = hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return context


def visual_request(context):
    # Deliberately do not include prior motion drafts, prior requests or rejected
    # answers. They remain in the ledger; they are not the new visual contract.
    data = {key: context[key] for key in ('job_id', 'index', 'context_id', 'aspect_ratio',
            'audio_instruction', 'product_visual_contract')}
    return '\n\n'.join([
        'Text-only image-to-video motion planning. Inspect the attached image; do not generate an image or video.',
        'Use this current product visual brief, not camera cuts proposed earlier in the conversation. '
        'The saved image defines the visible product and setting. Write one continuous shot with natural motion and a simple camera move. '
        'Do not add a display, setting, accessory, demonstration or object absent from the reference.',
        'Keep product identity, factual claims, saved narration and explicit requirements in product_information unchanged. '
        'Narration can describe a verified feature while the image shows the product; do not invent a visual demonstration. '
        'An earlier AI-suggested camera cut is not an immutable product fact. Changing camera treatment alone is not material_change. '
        'If the current brief or an explicit requirement cannot be fulfilled from the image, retain needs_review=true '
        'and explain it; do not discard that requirement or force approval.',
        'Write prompt in concise English, 2–4 sentences, with the requested aspect ratio and exactly one video. '
        'Include: All spoken dialogue must be in Thai only. Do not invent speech, add text, identity declarations or policy explanations.',
        'Return only JSON: job_id and context_id (exact strings), index (exact integer), prompt (string, 40–2500 characters), '
        'needs_review, reference_compatible, material_change (true/false booleans), review_reason (string). '
        'reference_compatible means the final motion fits the attached image and current visual brief. '
        'material_change means changing product identity, facts, narration or explicit requirements, not a superseded AI camera draft. '
        'Report all flags honestly; no policy bypass or guarantees of generation.',
        json.dumps(data, ensure_ascii=False),
    ])


def can_revise_visual(record, context, validation):
    result = (record or {}).get('result') or {}
    return (str(context.get('job_id', '')).startswith('JOB-')
            and not context.get('product_visual_contract')
            and (record or {}).get('phase') == 'answered'
            and validation.get('content_recheckable') is True
            and result.get('needs_review') is True
            and result.get('reference_compatible') is True
            and result.get('material_change') is True)


def product_motion_progress(folder, job):
    """Read-only UI summary; never creates a plan or grants Send permission."""
    from core.flow_motion_plan import plan_context
    folder = Path(folder)
    plans = AtomicJsonFile(folder / 'prompts/flow_motion_plans.json').read({}).get('plans') or {}
    images = ready = 0
    for index in range(1, 4):
        path = folder / 'generated' / f'selling_image_{index:02d}.png'
        if not path.is_file():
            continue
        images += 1
        base = plan_context(folder, job, index)
        revised = visual_context(folder, job, base)
        row = plans.get(revised['context_id']) or plans.get(base['context_id']) or {}
        if row.get('phase') == 'ready':
            ready += 1
    return f'ภาพบันทึกแล้ว {images}/3 • แผนวิดีโอพร้อม {ready}/3 • ยังไม่ใช่วิดีโอที่สร้างเสร็จ'
