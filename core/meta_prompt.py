"""Versioned Meta video instructions. Missing saved versions remain legacy."""
CURRENT_META_PROMPT_VERSION = 5


def meta_prompt_version(value):
    if type(value) is not int or value not in (1, 2, 3, 4, 5):
        raise ValueError('รุ่นพรอมต์ Meta ไม่ถูกต้อง • เก็บคำขอเดิมไว้')
    return value


def separated_roles(job):
    """Opt in only via the saved new Meta contract; never alter Flow hashes."""
    return (job.get('meta_prompt_version') == 5
            and (job.get('video_generation_mode') == 'meta_ai'
                 or job.get('video_ai_provider') == 'meta_ai'))


def narrator_text(job, index):
    """Speech stays data, including quoted character words in narration."""
    from core.product_script import film_scene
    from core.product_pointing import enabled as pointing_review
    if pointing_review(job):
        lines = job.get('scene_narrations') or job.get('spoken_script_segments') or []
        line = lines[index - 1] if 0 < index <= len(lines) else ''
        return str(line.get('text') or line.get('script') or '') if isinstance(line, dict) else str(line)
    if (job.get('actor_dialogue') or job.get('product_presentation_version') == 1
            or (job.get('storytelling_options') or {}).get('mode') in {'solo', 'dialogue', 'visual'}
            or film_scene(job, index) is not None):
        return ''
    lines = job.get('scene_narrations') or job.get('spoken_script_segments') or []
    line = lines[index - 1] if 0 < index <= len(lines) else ''
    if isinstance(line, dict):
        line = line.get('text') or line.get('script') or ''
    return str(line)


def saved_scene_motion(job, index, folder):
    """Read motion for the exact saved scene, with no provider request or write."""
    from pathlib import Path
    from core.atomic_json import AtomicJsonFile
    from core.product_script import film_scene
    scene = film_scene(job, index)
    if scene is not None:
        return scene['action']
    count = int(job.get('scene_count') or 0)
    actor = (job.get('actor_dialogue')
             or (job.get('storytelling_options') or {}).get('mode') in {'solo', 'dialogue', 'visual'})
    lines = job.get('scene_narrations') or job.get('spoken_script_segments') or []
    narration = str(lines[index - 1]) if not actor and 0 < index <= len(lines) else ''

    def selected(values):
        if (isinstance(values, list) and len(values) == count and 0 < index <= count
                and all(isinstance(value, str) and value.strip() for value in values)):
            value = values[index - 1].strip()
            # A misplaced narrator line is not a visual plan, even if saved in
            # the motion field. Leave quoted speech inside the narration.
            if not narration or narration.strip() not in value:
                return value
        return ''

    motion = selected(job.get('flow_shot_prompts'))
    if not motion:
        checkpoint = AtomicJsonFile(Path(folder) / 'prompts' / 'ai_analysis_checkpoint.json').peek({})
        if (isinstance(checkpoint, dict) and checkpoint.get('job_id') == job.get('id')
                and checkpoint.get('scene_prompts') == job.get('scene_prompts')):
            motion = selected(checkpoint.get('flow_shot_prompts'))
    if not motion and actor:
        # Actor plans explicitly define scene_narrations as visual beats.
        motion = selected(job.get('scene_narrations'))
    return motion or ('Preserve the visible composition, characters and objects in the starting image. '
                      'Use subtle natural movement and one smooth camera move; do not invent a new event. '
                      'Speech, if requested, belongs only to the audio instructions, never the action.')


COMPLIANT_VIDEO_INSTRUCTION = (
    'If the starting image cannot be animated as supplied, make one compliant revised visual yourself '
    '(for example, adjust clothing or framing) while preserving the harmless hook and scene meaning. '
    'Proceed to generate exactly one actual playable vertical 9:16 video without asking a confirmation question. '
    'Preserve the original Thai spoken line and requested audio settings. Follow the provider safety rules; '
    'if a video still cannot be made, report that truthfully instead of claiming a result.'
)


def compliant_video_instruction(aspect_ratio='9:16'):
    """Keep the exact v4 instruction for saved vertical jobs."""
    if aspect_ratio == '9:16':
        return COMPLIANT_VIDEO_INSTRUCTION
    if aspect_ratio == '16:9':
        return COMPLIANT_VIDEO_INSTRUCTION.replace('vertical 9:16', 'landscape 16:9')
    raise ValueError('สัดส่วนวิดีโอ Meta ไม่ถูกต้อง')


SINGLE_VIDEO_INSTRUCTION = (
    'Generate exactly one actual playable video now using the attached starting image. '
    'Do not provide alternative options, numbered choices, a plan, or a confirmation question. '
    'Choose one feasible visual interpretation yourself and proceed directly to video generation. '
    'If a physical movement is too complex to animate reliably, simplify only the movement or camera work '
    'while preserving the essential event, its direction and outcome, characters, product identity and continuity. '
    'Do not invent a different story or contradict the supplied dialogue. '
    'Keep all requested audio settings and supplied spoken lines unchanged. '
    'Do not treat a text description or still image as the completed video. '
    'If generation genuinely fails or is unavailable, report that truthfully; do not claim a video was created.'
)
