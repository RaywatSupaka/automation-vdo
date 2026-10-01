"""Opt-in, frozen scene music requests; never dispatch or regenerate media."""
import copy
import hashlib
import random
import re


MOODS = {
    'auto': 'matching the mood of this scene',
    'warm': 'with a warm, gentle mood',
    'bright': 'with a light, cheerful mood',
    'gentle_suspense': 'with gentle, restrained suspense',
    'tender': 'with a tender, emotional mood',
}
FREQUENCIES = {'sparse': .15, 'moderate': .30}
MARKER = 'AI GENERATED MUSIC v1:'
END_MARKER = '[END AI GENERATED MUSIC]'


def normalize_options(value):
    if value is None:
        return None
    if not isinstance(value, dict) or type(value.get('version', 1)) is not int or value.get('version', 1) != 1:
        raise ValueError('ตัวเลือกดนตรี AI ไม่ถูกต้อง')
    enabled = value.get('enabled', False)
    mood, frequency = value.get('mood', 'auto'), value.get('frequency', 'moderate')
    if (type(enabled) is not bool or not isinstance(mood, str) or mood not in MOODS
            or not isinstance(frequency, str) or frequency not in FREQUENCIES):
        raise ValueError('ตัวเลือกดนตรี AI ไม่ถูกต้อง')
    return {'version': 1, 'enabled': enabled, 'mood': mood, 'frequency': frequency}


def validate_options(value, video_mode, choices):
    options = normalize_options(value)
    if not options or not options['enabled']:
        return options
    choices = choices or {}
    if video_mode not in {'flow', 'google_flow', 'meta_ai'}:
        raise ValueError('ดนตรี AI ใช้ได้เมื่อสร้างวิดีโอด้วย Google Flow หรือ Meta AI')
    if choices.get('mode', 'api') == 'none':
        raise ValueError('กรุณาเลือกเสียงหลักก่อนเปิดดนตรี AI ไม่สามารถใช้กับวิดีโอเงียบสนิท')
    if choices.get('music'):
        raise ValueError('กรุณาเลือกดนตรี AI หรือเพลงจากคลังอย่างใดอย่างหนึ่ง')
    if choices.get('mode', 'api') == 'api' and not choices.get('keep_video_audio'):
        raise ValueError('ดนตรี AI พร้อมเสียงพากย์ต้องเปิดเก็บเสียงต้นฉบับจากวิดีโอ')
    if choices.get('video_audio_volume', 100 if choices.get('mode') == 'flow_original' else 35) == 0:
        raise ValueError('กรุณาเพิ่มระดับเสียงต้นฉบับให้มากกว่า 0% ก่อนเปิดดนตรี AI')
    return options


def api_music_dubbing(value, video_mode, choices, *, job=None):
    """Narrow API/source exception, proved by saved options and (at render) plan.

    Creation has no scene plan yet. Rendering must supply the frozen job; a
    client-supplied audio marker alone never authorizes original actor speech.
    This validator does not freeze/reroll a plan or change prompt bytes.
    """
    if not choices or choices.get('mode') != 'api' or not choices.get('keep_video_audio'):
        return False
    options = validate_options(value, video_mode, choices)
    if not options or not options['enabled']:
        return False
    if job is not None:
        if choices.get('generated_music_version') != 1:
            raise ValueError('ยังไม่มีสัญญาดนตรี AI ที่บันทึกก่อนสร้างคลิป')
        _read_plan(job, options)
    return True


def _scene_count(job):
    count = job.get('scene_count') or job.get('flow_target_clip_count')
    if not count and str(job.get('id') or '').startswith('JOB-'):
        count = len(job.get('composition_images') or job.get('generated_images') or [])
    if type(count) is not int or not 1 <= count <= 50:
        raise ValueError('ต้องมีจำนวนฉากจริงก่อนบันทึกแผนดนตรี AI')
    return count


def _seed(job):
    if not isinstance(job.get('id'), str) or not job['id']:
        raise ValueError('ต้องมีรหัสงานก่อนบันทึกแผนดนตรี AI')
    return hashlib.sha256(('generated-music-v1:' + job['id']).encode()).hexdigest()


def _read_plan(job, options):
    plan = job.get('generated_music_plan')
    count = _scene_count(job)
    if (not isinstance(plan, dict) or plan.get('version') != 1
            or plan.get('seed') != _seed(job) or plan.get('scene_count') != count
            or plan.get('options') != options):
        raise ValueError('แผนดนตรี AI ยังไม่ได้บันทึกหรือไม่ตรงงาน • ไม่เปลี่ยนคำขอเดิม')
    indices = plan.get('scene_indices')
    if (not isinstance(indices, list) or not indices or any(type(i) is not int or not 1 <= i <= count for i in indices)
            or indices != sorted(set(indices)) or (count > 1 and len(indices) >= count)):
        raise ValueError('แผนฉากดนตรี AI ไม่ถูกต้อง')
    return plan


def freeze_plan(job):
    """Mutate a NEW job before its save/first Send; callers persist the job.

    Reading packages never calls this function. Existing plans are validated,
    never rerolled on resume or when the live UI defaults change.
    """
    options = validate_options(job.get('generated_music_options'),
        job.get('video_generation_mode') or job.get('video_provider') or job.get('video_ai_provider'), job.get('audio_choices'))
    if not options or not options['enabled']:
        return None
    if 'generated_music_plan' in job:
        plan = _read_plan(job, options)
    else:
        count, seed = _scene_count(job), _seed(job)
        wanted = max(1, round(count * FREQUENCIES[options['frequency']]))
        wanted = min(wanted, count - 1) if count > 1 else 1
        candidates = list(range(1, count + 1))
        random.Random(seed).shuffle(candidates)
        selected = []
        for index in candidates:
            if all(abs(index - other) > 1 for other in selected):
                selected.append(index)
            if len(selected) == wanted:
                break
        plan = {'version': 1, 'seed': seed, 'scene_count': count,
                'scene_indices': sorted(selected), 'options': copy.deepcopy(options)}
        job['generated_music_plan'] = plan
    job['generated_music_options'] = options
    job['audio_choices'] = {**(job.get('audio_choices') or {}), 'generated_music_version': 1}
    return copy.deepcopy(plan)


def selected(job, index):
    options = validate_options(job.get('generated_music_options'),
        job.get('video_generation_mode') or job.get('video_provider') or job.get('video_ai_provider'), job.get('audio_choices'))
    if not options or not options['enabled']:
        return False
    plan = _read_plan(job, options)
    if type(index) is not int or not 1 <= index <= plan['scene_count']:
        raise ValueError('หมายเลขฉากดนตรี AI ไม่ถูกต้อง')
    return index in plan['scene_indices']


def apply_to_prompt(job, index, prompt):
    """Modify only opted-in selected scenes, keeping every legacy byte intact."""
    if not selected(job, index):
        return prompt
    # Replace exact program-owned compound prohibitions without losing speech,
    # caption or actor constraints. The final directive is idempotent.
    replacements = {
        'Include natural ambient sounds only.': 'Include natural ambient sounds.',
        'No music, speech or ambient audio; narration is added separately.': 'No generated speech; narration is added separately.',
        'No speech or music; narration is added separately.': 'No generated speech; narration is added separately.',
        'Do not add music, captions or subtitles.': 'Do not add captions or subtitles.',
        'No extra dialogue, background music or burned-in captions.': 'No extra dialogue or burned-in captions.',
        'Do not invent spoken lines or music.': 'Do not invent spoken lines.',
    }
    prompt = re.sub(r'\n?' + re.escape(MARKER) + r'.*?' + re.escape(END_MARKER), '', prompt, flags=re.S)
    # Audio directions are outside quoted dialogue/data. Never rewrite an
    # English product name or spoken line such as "No music, please".
    parts = re.split(r'("(?:\\.|[^"\\])*"|(?<!\w)\'(?:\\.|[^\'\\])*\'(?!\w)|(?i:Spoken line:) [^\n]*|(?im:^[ \t]*(?:Scene:|Story action:|Action:|Dialogue:) [^\n]*))', prompt)
    for index_part in range(0, len(parts), 2):
        value = parts[index_part]
        for old, new in replacements.items():
            value = re.sub(re.escape(old), new, value, flags=re.I)
        value = re.sub(r'(?<!\w)(?:No background music|No music|Do not add background music|Do not add music|Without background music|Without music)\b[ \t]*(?:[.;]|(?=$|\n))', '', value, flags=re.I)
        parts[index_part] = value
    prompt = ''.join(parts)
    mood = MOODS[job['generated_music_plan']['options']['mood']]
    instruction = (f'\n{MARKER} Add subtle original instrumental background music {mood}. '
                   'Keep dialogue clearly dominant. No singing or lyrics. Use gentle entry and exit.')
    if (job.get('audio_choices') or {}).get('mode', 'api') == 'api':
        instruction += ' No generated speech; narration is added separately.'
    return prompt + instruction + ' ' + END_MARKER
