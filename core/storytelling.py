"""Opt-in storytelling contract. Missing options always mean legacy behavior."""
import copy
import json
import re

MODES = {'narrator', 'solo', 'dialogue', 'visual'}
TONES = {'auto', 'comedy', 'warm', 'drama', 'mystery'}
HOOKS = {'auto', 'event', 'question', 'anomaly'}
ENDINGS = {'auto', 'resolved', 'twist', 'cliffhanger'}


def storytelling_options(value):
    if value is None:
        return None
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('รูปแบบการเล่าไม่ถูกต้อง')
    result = {'version': 1}
    for key, allowed, default in [('mode', MODES, 'narrator'), ('tone', TONES, 'auto'),
                                  ('hook', HOOKS, 'auto'), ('ending', ENDINGS, 'auto')]:
        item = value.get(key, default)
        if not isinstance(item, str) or item not in allowed:
            raise ValueError('ตัวเลือกรูปแบบการเล่าไม่ถูกต้อง: ' + key)
        result[key] = item
    cta = value.get('cta_enabled', False)
    if type(cta) is not bool or (result['mode'] == 'visual' and cta):
        raise ValueError('ละครภาพล้วนไม่มีคำชวนติดตามแบบพูด')
    result['cta_enabled'] = cta
    return result


def mode(job):
    return (job.get('storytelling_options') or {}).get('mode')


def visual_only(job):
    return mode(job) == 'visual'


def validate_result(job, result):
    options = storytelling_options(job.get('storytelling_options'))
    if not options:
        return
    if not isinstance(result, dict):
        raise ValueError('STORYTELLING_REVIEW • คำตอบต้องเป็นข้อมูลบทแบบ JSON')
    if not options['cta_enabled']:
        turns = result.get('scene_dialogue_turns') or []
        texts = [t.get('text', '') for group in turns if isinstance(group, list) for t in group if isinstance(t, dict)]
        if options['mode'] == 'narrator':
            texts += [result.get('narration_script', '')] + list(result.get('scene_narrations') or [])
        if any(re.search(r'(?:กด|ฝาก|ช่วย)\s*(?:หัวใจ|ไล[กค]์|ติดตาม|คอมเมนต์|แชร์)|จิ้ม\s*(?:ลิงก์|ตะกร้า)|subscribe', str(t), re.I) for t in texts):
            raise ValueError('STORYTELLING_REVIEW • ปิดคำชวนติดตามไว้ แต่บทมี CTA')
    if options['mode'] == 'visual' and (result.get('narration_script') or result.get('dialogue_turns')):
        raise ValueError('STORYTELLING_REVIEW • ภาพล้วนต้องไม่มีบทพูดหรือผู้บรรยาย')


def native_acting(options):
    return bool(options and options['mode'] != 'narrator')


def requested_scene_seconds(job):
    value = str((job.get('flow_settings') or {}).get('duration') or '')
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(?:s|seconds?|วินาที)?\s*', value, re.I)
    return float(match[1]) if match and 1 <= float(match[1]) <= 30 else None


def validate_settings(options, video_mode, choices=None, *, drama=False, generated_music_options=None):
    options = storytelling_options(options)
    if not options:
        return None
    selected = (choices or {}).get('mode')
    if options['mode'] == 'visual':
        if video_mode not in {'image_motion', 'google_flow', 'meta_ai'}:
            raise ValueError('วิธีสร้างวิดีโอสำหรับเรื่องเล่าด้วยภาพไม่ถูกต้อง')
        if choices is not None and (selected not in {'none', 'flow_original'}
                                    or (video_mode == 'image_motion' and selected != 'none')
                                    or choices.get('keep_video_audio') or choices.get('subtitle')):
            raise ValueError('ภาพล้วนต้องไม่มีเสียงพากย์หรือซับ • ภาพเคลื่อนไหวในเครื่องใช้โหมดไม่มีเสียงหลัก')
    elif options['mode'] in {'solo', 'dialogue'}:
        if video_mode not in {'google_flow', 'meta_ai'}:
            raise ValueError('ตัวละครพูดเองต้องใช้ Google Flow หรือ Meta AI')
        from core.generated_music import api_music_dubbing
        music_dubbing = drama and api_music_dubbing(generated_music_options, video_mode, choices)
        if choices is not None and (selected not in ({'flow_original', 'api'} if drama else {'flow_original'})
                                    or (choices.get('keep_video_audio') and not music_dubbing)):
            raise ValueError('เลือกเสียงในคลิป หรือพากย์ SmartSub รายตัวโดยไม่ผสมเสียงพูดต้นฉบับ')
    return options


def ending_instruction(job):
    options = job.get('storytelling_options') or {}
    ending = options.get('ending', 'auto')
    if ending == 'auto':
        ongoing = (job.get('job_type') == 'drama_episode' and
                   (job.get('open_ended') or int(job.get('episode_no', 1)) < int(job.get('episode_count', 1))))
        ending = 'cliffhanger' if ongoing else 'resolved'
    return {'resolved': 'Resolve the central conflict; finish this story without teasing a nonexistent next episode.',
            'twist': 'Resolve the episode with an earned twist consistent with established facts.',
            'cliffhanger': 'End at a meaningful turning point that invites the next episode, not an arbitrary cutoff.'}[ending]


def build_request(job):
    """Compose sections, never remove numbered rules from another template."""
    from core.story_visual_plan import SCENE_ACTION_RULE
    from core.story_styles import story_style_instruction, story_render_instruction
    from core.story_content import story_content_instruction, requested_story_names, story_source_aliases
    options = storytelling_options(job['storytelling_options'])
    acting = native_acting(options)
    visual = options['mode'] == 'visual'
    drama = job.get('job_type') == 'drama_episode'
    cast = copy.deepcopy(job.get('character_bible') or [])
    names = [c['name'] for c in cast]
    required = ['video_title', 'video_description', 'visual_bible', 'scene_narrations', 'scene_prompts', 'scene_durations']
    if not visual:
        required.append('narration_script')
    if acting:
        required += ['character_bible', 'scene_dialogue_turns']
    elif job.get('scene_pipeline_version') == 1 or drama:
        required += ['scene_dialogue_turns', 'dialogue_turns']
    if drama:
        required += ['episode_title', 'episode_summary', 'next_episode_hook', 'continuity_state']
        if job.get('auto_cast_pending'):
            required.append('character_bible')
    request = {
        'schema_version': 2 if drama else 1, 'mode': 'story', 'job_id': job['id'],
        'prompt_file': 'prompts/chatgpt_request.txt', 'image_files': job['source_images'],
        'image_count': job['scene_count'], 'prompt_field': 'scene_prompts', 'required_fields': required,
        'storytelling_options': options, 'storytelling_cast': names,
        'storytelling_scene_seconds': requested_scene_seconds(job),
        'allowed_speakers': names + ([] if acting else ['ผู้บรรยาย']),
        'visual_style_instruction': story_style_instruction(job.get('visual_style'), job.get('visual_style_custom')),
        'visual_render_instruction': story_render_instruction(job.get('visual_style'), job.get('visual_style_custom')),
    }
    if drama:
        request['story_mode'] = 'drama_episode'
    brief = {key: job.get(key) for key in ('topic', 'story_input', 'scene_count', 'series_title', 'episode_no',
        'episode_count', 'planned_episode', 'plot_board', 'previous_episode_summary', 'previous_episode_hook',
        'previous_visual_bible', 'previous_continuity_state', 'open_ended') if key in job}
    sections = [SCENE_ACTION_RULE, 'Create ONE Thai story package, not alternatives. Return only a JSON object.',
        'USER STORY / SERIES CONTEXT:\n' + json.dumps(brief, ensure_ascii=False),
        'SAVED STORYTELLING OPTIONS:\n' + json.dumps(options, ensure_ascii=False),
        request['visual_style_instruction'],
        'Keep exactly scene_count scenes. Each scene_prompt is a self-contained starting image: named cast, '
        'consistent appearance, location, spatial relationships and ONE visible moment, no text/watermarks. '
        'Use only successfully attached references; if none exist, create images from the complete text bible. '
        'Return visual_bible and scene_durations in seconds, and flow_shot_prompts for motion AFTER that image. '
        'Tone controls the story and performance, not TTS speed. Hook must arise from the story, never false claims.',
        ending_instruction(job)]
    if drama:
        if cast:
            sections.append('LOCKED CAST (do not replace names, identity, roles, clothing or relationships):\n' + json.dumps(cast, ensure_ascii=False))
        sections += ['Follow only the current planned episode. Continue from actual previous events; no repeating completed '
            'reveals or giving a character knowledge they have not acquired. Return episode_title, episode_summary, '
            'next_episode_hook (use a closure note for a finished story), continuity_state including each character\'s '
            'location, goals, knowledge, relationships and unresolved conflicts. Do not invent a different series.']
        if job.get('auto_cast_pending'):
            sections.append('FIRST EP CAST SETUP: The user left cast details blank. Invent 1–4 original fictional '
                'characters for this series and return character_bible entries with unique Thai names and clear '
                'stable appearance/description. Use exactly those names in story_entities and scene_prompts. '
                'This result will be locked for later episodes; do not use a generic name such as ตัวละครหลัก.')
    if acting:
        sections += [
            'ACTING CONTRACT: No narrator, explanatory voiceover or plot summary read aloud. '
            'Show character goals through decisions, actions and reactions. Keep action directions separate from dialogue. '
            'Return character_bible [{name,appearance,voice_description}] using exactly the locked names when supplied. '
            'Use the SAME names in story_entities and prompts; include speaker/listener entity IDs in scene_entities. '
            'Return scene_dialogue_turns: exactly scene_count arrays, each 0–3 turns '
            '{speaker,listener,text,emotion,action}. Thai spoken text only, no names/directions/English letters inside text. '
            'scene_narrations are VISUAL beats, never spoken lines. Dialogue must not copy those beats. '
            'Return dialogue_turns as flattened turns and narration_script as concatenated spoken text, for compatibility only. '
            'One speaker at a time, visible speaking face; listeners react silently. Leave time for gestures and pauses. '
            'No burned-in subtitles; no added music (desktop handles optional music).',
            {'solo': 'SOLO: Exactly one named character speaks across the story; supporting characters may act silently. '
                     'That character speaks in first person from this situation, to self or camera; listener may be empty. '
                     'No detached third-person explanation.',
             'dialogue': 'DIALOGUE: At least two named actors speak across the episode. Each turn addresses a different '
                         'named listener visible in that scene. Write real questions, answers and reactions, not exposition.',
             'visual': 'VISUAL ONLY: Every scene_dialogue_turns entry is []. dialogue_turns is [], narration_script is "". '
                       'No speech, vocals, narrator or lip-sync. Tell the story through actions and natural ambient sound.'}[options['mode']]]
    else:
        sections += ['NARRATED MODE: scene_narrations contains the actual Thai spoken words for each scene; '
            'narration_script is their concatenation. Write all numbers/foreign terms as Thai pronunciations. '
            'When dialogue turns are requested, scene_dialogue_turns has one array per scene, whose ordered text '
            'equals that scene_narration; dialogue_turns is the flattened array. Use exact allowed speakers, '
            'or ผู้บรรยาย for a narrated Shorts story. No speaker labels inside spoken text.']
    sections += [('Only at the END, after resolving the scene, add one brief in-character invitation to follow/comment. '
                  'Never invent a narrator to say it.') if options['cta_enabled'] else
                 'CTA OFF: No like, comment, follow, subscribe, shopping-basket or other engagement request anywhere in spoken text.']
    duration = (job.get('flow_settings') or {}).get('duration')
    sections += [f'VIDEO DURATION SETTING: {duration}. Keep each scene and concise speech within it, including pauses.'
                 if duration else 'Provider duration not fixed: use short dialogue and conservative scene durations of 3–7 seconds.']
    if job.get('story_content_contract') == {'version': 1}:
        request.update(story_content_contract={'version': 1}, required_named_entities=requested_story_names(job),
                       story_source_aliases=story_source_aliases(job))
        required += ['story_entities', 'scene_entities']
        sections.append(story_content_instruction(job))
    request['storytelling_instruction'] = '\n\n'.join(sections[5:])
    sections.append('Required fields: ' + ', '.join(required) + '. Also return job_id, warnings and pronunciation_notes.')
    from core.creative_brief import attach_request
    return attach_request(job, '\n\n'.join(sections), request)
