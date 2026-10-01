"""Opt-in Shorts actor dialogue; legacy narrated jobs are unchanged."""
import copy
import json
import re
from core.storytelling import mode as storytelling_mode, visual_only


def enabled(job):
    return job.get('actor_dialogue') is True


def conversation_only(job):
    """New contract only; never migrate a saved actor job on resume."""
    return enabled(job) and (job.get('actor_dialogue_version') == 2 or storytelling_mode(job) == 'dialogue')


def conversation_audio(choices=None):
    return {**(choices or {}), 'mode': 'flow_original', 'subtitle': False,
            'keep_video_audio': False, 'allow_silent': False}


def validate_option(value, provider, choices=None, storytelling_options=None, *, drama=False, music_job=None):
    if type(value) is not bool:
        raise ValueError('ตัวเลือกตัวละครพูดเองต้องเป็นเปิดหรือปิด')
    if value:
        mode = (storytelling_options or {}).get('mode')
        if mode == 'visual':
            if provider not in {'image_motion', 'google_flow', 'meta_ai'}:
                raise ValueError('วิธีสร้างภาพล้วนไม่ถูกต้อง')
            if choices is not None and (choices.get('mode') not in {'none', 'flow_original'}
                                        or (provider == 'image_motion' and choices.get('mode') != 'none')):
                raise ValueError('ภาพล้วนต้องไม่มีเสียงพากย์')
            return value
        if provider not in {'google_flow', 'meta_ai'}:
            raise ValueError('ตัวละครพูดเองต้องสร้างวิดีโอด้วย Google Flow หรือ Meta AI')
        allowed = {'flow_original', 'api'} if drama and mode in {'solo', 'dialogue'} else {'flow_original'}
        from core.generated_music import api_music_dubbing
        music_dubbing = (drama and mode in {'solo', 'dialogue'} and isinstance(music_job, dict)
                         and api_music_dubbing(music_job.get('generated_music_options'), provider, choices, job=music_job))
        if choices is not None and (choices.get('mode') not in allowed or (choices.get('keep_video_audio') and not music_dubbing)):
            raise ValueError('ตัวละครพูดเองต้องใช้เสียงจากคลิป หรือพากย์รายตัวโดยไม่ผสมเสียงต้นฉบับ')
    return value


def validate_plan(job, result):
    from core.storytelling import validate_result
    validate_result(job, result)
    if not enabled(job):
        return result
    result = copy.deepcopy(result)
    cast = result.get('character_bible')
    groups = result.get('scene_dialogue_turns')
    if not isinstance(cast, list) or not 1 <= len(cast) <= 8:
        raise ValueError('ACTOR_PLAN_REVIEW • ต้องระบุนักแสดง 1–8 คน')
    names = []
    for character in cast:
        name = str(character.get('name') or '').strip() if isinstance(character, dict) else ''
        if not name or name.lower() in {'ผู้บรรยาย', 'narrator', 'voiceover'} or name in names:
            raise ValueError('ACTOR_PLAN_REVIEW • ชื่อนักแสดงว่าง ซ้ำ หรือเป็นผู้บรรยาย')
        names.append(name)
    locked = job.get('character_bible') or []
    if job.get('storytelling_options') and job.get('job_type') == 'drama_episode':
        if set(names) != {c['name'] for c in locked}:
            raise ValueError('ACTOR_PLAN_REVIEW • นักแสดงต้องตรงตัวละครของซีรีส์เดิม')
        # A generated description cannot replace the user's identity/voice refs.
        generated = {c['name']: c for c in cast}
        result['character_bible'] = [{**generated[c['name']], **copy.deepcopy(c)} for c in locked]
    entities = {row.get('name'): row.get('id') for row in result.get('story_entities', []) if isinstance(row, dict)}
    if job.get('story_content_contract') and any(name not in entities for name in names):
        raise ValueError('ACTOR_PLAN_REVIEW • รายชื่อนักแสดงต้องตรงกับ story_entities ก่อนบันทึก')
    if not isinstance(groups, list) or len(groups) != job['scene_count']:
        raise ValueError('ACTOR_PLAN_REVIEW • บทสนทนาต้องครบตามจำนวนฉาก')
    turns = []
    for index, group in enumerate(groups, 1):
        if not isinstance(group, list) or len(group) > 3:
            raise ValueError(f'ACTOR_PLAN_REVIEW • ฉาก {index} ให้พูดสั้นไม่เกิน 3 ช่วง หรือ [] สำหรับฉากเงียบ')
        for turn in group:
            if not isinstance(turn, dict) or turn.get('speaker') not in names:
                raise ValueError(f'ACTOR_PLAN_REVIEW • ผู้พูดฉาก {index} ไม่ตรงนักแสดง ห้ามแทนด้วยผู้บรรยาย')
            if turn.get('listener') and turn['listener'] not in names:
                raise ValueError('ACTOR_PLAN_REVIEW • ผู้ฟังไม่ตรงรายชื่อนักแสดง')
            if job.get('story_content_contract'):
                scenes = result.get('scene_entities') or []
                present = scenes[index-1] if index <= len(scenes) else []
                if any(entities.get(name) not in present for name in [turn['speaker'], turn.get('listener')] if name):
                    raise ValueError(f'ACTOR_PLAN_REVIEW • ฉาก {index} ต้องมีตัวละครที่พูดและฟังอยู่ในภาพ')
            text = turn.get('text')
            if not isinstance(text, str) or not text.strip() or len(text) > 180 or not re.search('[ก-๙]', text):
                raise ValueError(f'ACTOR_PLAN_REVIEW • บทพูดฉาก {index} ต้องเป็นภาษาไทยสั้น ๆ')
            if re.search('[A-Za-z]', text) or any(text.lstrip().startswith(n + ':') for n in names):
                raise ValueError('ACTOR_PLAN_REVIEW • บทพูดต้องไม่มีป้ายชื่อหรือคำอังกฤษที่ยังไม่ได้เขียนคำอ่าน')
        # This is a conservative drafting budget, not a guarantee of speech speed.
        duration = (result.get('scene_durations') or [])[index-1:index]
        try:
            seconds = float(duration[0])
        except (IndexError, TypeError, ValueError):
            raise ValueError('ACTOR_PLAN_REVIEW • ระบุเวลาของทุกฉาก')
        if not 1 <= seconds <= 30 or sum(len(t['text']) for t in group) > max(20, seconds * 12):
            raise ValueError(f'ACTOR_PLAN_REVIEW • บทพูดฉาก {index} ยาวเกินเวลาที่วางไว้ กรุณาย่อบท')
        if job.get('storytelling_options'):
            from core.storytelling import requested_scene_seconds
            requested = requested_scene_seconds(job)
            if requested and seconds > requested:
                raise ValueError(f'ACTOR_PLAN_REVIEW • เวลาฉาก {index} ยาวกว่าคลิปที่เลือกไว้')
        turns.extend(group)
    if visual_only(job) and turns:
        raise ValueError('ACTOR_PLAN_REVIEW • ภาพล้วนต้องไม่มีบทพูด')
    if not turns and not visual_only(job):
        raise ValueError('ACTOR_PLAN_REVIEW • เรื่องต้องมีบทสนทนาอย่างน้อยหนึ่งฉาก')
    if storytelling_mode(job) == 'solo' and len({t['speaker'] for t in turns}) != 1:
        raise ValueError('ACTOR_PLAN_REVIEW • โหมดพูดเองให้มีผู้พูดหลักเพียงคนเดียว')
    if job.get('storytelling_options'):
        beats = result.get('scene_narrations') or []
        for i, group in enumerate(groups):
            if any(t['text'].strip() == str(beats[i] if i < len(beats) else '').strip() for t in group):
                raise ValueError('ACTOR_PLAN_REVIEW • แยกการกระทำออกจากบทพูด')
    if conversation_only(job):
        if len({t['speaker'] for t in turns}) < 2:
            raise ValueError('ACTOR_PLAN_REVIEW • ตัวละครสนทนาต้องมีผู้พูดโต้ตอบอย่างน้อยสองคนในเรื่อง')
        for i, group in enumerate(groups):
            beats = result.get('scene_narrations') or []
            beat = str(beats[i] if i < len(beats) else '').strip()
            for turn in group:
                if not turn.get('listener') or turn['listener'] == turn['speaker']:
                    raise ValueError('ACTOR_PLAN_REVIEW • ระบุผู้ฟังที่เป็นตัวละครอีกคนให้แต่ละบทพูด')
                if beat and turn['text'].strip() == beat:
                    raise ValueError('ACTOR_PLAN_REVIEW • ห้ามคัดลอกคำอธิบายฉากเป็นบทพูด')
    result['dialogue_turns'] = turns
    result['narration_script'] = ' '.join(t['text'].strip() for t in turns)
    return result


def request_instruction(job):
    duration = (job.get('flow_settings') or {}).get('duration')
    visual = storytelling_mode(job) == 'visual'
    if visual:
        return ('\nVISUAL ACTING ONLY: Tell the story through visible decisions, gestures, reactions and scene changes. '
                'No speech, vocals, narrator, voiceover, lip-sync, subtitles, captions or engagement CTA. '
                'Return character_bible for visual continuity, and exactly scene_count empty arrays in '
                'scene_dialogue_turns. dialogue_turns is [] and narration_script is "". '
                'scene_narrations contain visual action/story beats, never spoken lines. '
                'Keep every scene_prompt and flow_shot_prompt consistent with those silent beats. '
                + (f'Requested video duration setting: {duration}; keep action within it.' if duration else
                   'Use conservative scene durations without promising a provider duration.'))
    conversation = (
        '\nCONVERSATION ONLY: At least two actors exchange natural Thai dialogue across this story. '
        'Every spoken turn addresses another named actor. Write what that person would actually say now, '
        'not third-person narration, a plot summary or a visual description read aloud. '
        'Keep visual directions separate from spoken text. Never copy scene_narrations into dialogue. '
        'Use short questions, answers, disagreements and emotional reactions, with time for listening. '
        'No subtitles, captions, explanatory voiceover or narrator. '
    ) if conversation_only(job) else ''
    return conversation + (
        '\nACTOR STORY MODE: Tell this Shorts story through the actors actions and Thai dialogue, not narration. '
        'No narrator, off-screen explanatory voiceover, direct-to-camera review, or automatic like/comment CTA. '
        'Keep the requested scene count, visual style, story identity and continuity. '
        'Return character_bible: an array of {name, appearance, voice_description}; keep actors visually consistent. '
        'Use the same exact actor names in story_entities, include their IDs in each relevant scene_entities, '
        'and include each actor name in that scene_prompt. '
        'Return scene_dialogue_turns: exactly one array per scene, each containing 0–3 ordered turns '
        '{speaker, listener, text, emotion, action}. speaker and listener refer to character_bible names. '
        'Use [] for intentionally silent acting scenes. Each spoken text is concise Thai only without speaker labels. '
        'scene_narrations contains the visual action/story beat, NOT text to read aloud. '
        'narration_script is only the concatenation of actual dialogue, kept for compatibility; never synthesize it. '
        'scene_prompts depict the starting pose and all necessary speakers/listeners, with visible speaking faces '
        'and clear spatial relationships. flow_shot_prompts describe natural acting and listener reactions. '
        'Characters speak to each other, one at a time, with pauses. Listeners do not speak or lip-sync others lines. '
        'Allow quiet reactions; end the story through the actors, not a moralizing narrator. '
        'Keep dialogue brief enough for scene_durations, reserving time for acting and pauses; never add scenes. '
        'Return exactly scene_count numeric scene_durations in seconds. '
        + (f'Requested video duration setting: {duration}; budget each scene accordingly.' if duration else
           'Actual provider duration is not yet fixed: use brief exchanges and do not promise an exact duration.')
    )


def audio_instruction(job, index):
    from core.generated_music import apply_to_prompt
    return apply_to_prompt(job, index, _audio_instruction(job, index))


def _audio_instruction(job, index):
    groups = job.get('scene_dialogue_turns') or []
    if not 1 <= index <= len(groups):
        raise ValueError('ACTOR_PLAN_REVIEW • ยังไม่มีบทสนทนาที่บันทึกไว้ของฉากนี้')
    if storytelling_mode(job) == 'visual':
        return ('\nVISUAL ONLY: No narrator, dialogue, vocals, lip-sync, subtitles or captions. '
                'Continue the saved silent action; natural ambient sound only if this clip includes it. '
                'Do not invent spoken lines or music.')
    group = groups[index-1]
    dubbed = (job.get('audio_choices') or {}).get('mode') == 'api'
    return ('\nACTOR DIALOGUE: This is dramatic acting, not a narrated review. No narrator or explanatory voiceover. '
            + ('Create visual acting WITHOUT generated speech or vocals; the desktop will add the saved character voices afterward. '
               'Show the visible actor and listener reacting naturally. Do not add music, captions or subtitles. ' if dubbed else
               'All spoken dialogue must be in Thai only. Match each speaker to the visible actor, in the supplied order; '
               'natural synchronized mouth movement, gestures and listener reactions. Do not read names or directions. '
               'No extra dialogue, background music or burned-in captions. ') + 'Preserve these dialogue assignments '
            'even when revising the visual scene. '
            + ('This scene is intentionally silent: no speech; acting and natural ambient sound only.' if not group else
               'Ordered dialogue: ' + json.dumps(group, ensure_ascii=False))
            + ('\nSOLO: Only this saved speaker talks, to self or camera. Supporting actors remain silent.' if storytelling_mode(job) == 'solo' else '')
            + '\nCast: ' + json.dumps(job.get('character_bible') or [], ensure_ascii=False))


def composition_choices(job, index=None):
    choices = dict(job.get('audio_choices') or {})
    if conversation_only(job) and not job.get('storytelling_options'):
        choices = conversation_audio(choices)
    if enabled(job):
        if not job.get('storytelling_options'):
            choices['mode'] = 'flow_original'
        choices['allow_silent'] = False
        groups = job.get('scene_dialogue_turns') or []
        if len(groups) != job['scene_count']:
            raise ValueError('ACTOR_PLAN_REVIEW • ยังไม่มีบทสนทนาครบทุกฉาก')
        choices['silent_scene_indices'] = ([1] if not groups[index-1] else []) if index else [i for i, g in enumerate(groups, 1) if not g]
    return choices
