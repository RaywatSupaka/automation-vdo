"""Render one approved Flow scene with revision-bound, resumable speech."""
import hashlib
import json
from pathlib import Path
from core.chunked_tts import render_chunked_voice
from core.cancellable_process import check_cancelled
from core.media_audio import audio_mode
from core.scene_context_revision import normalized
from core.render_backend import scene_render


def scene_turns(job, index):
    from core.story_performance import enabled
    if enabled(job) and job.get('storytelling_options'):
        grouped = job.get('scene_dialogue_turns')
        if not isinstance(grouped, list) or len(grouped) != int(job.get('scene_count') or 0):
            raise ValueError('บทพูดรายฉากไม่ครบตามงาน')
        selected = grouped[index-1]
        if not isinstance(selected, list) or any(not isinstance(turn, dict) or not str(turn.get('text') or '').strip()
                                                 for turn in selected):
            raise ValueError('บทพูดรายฉากไม่ถูกต้อง')
        return selected
    narration = job['scene_narrations'][index-1]
    grouped = job.get('scene_dialogue_turns')
    if isinstance(grouped, list) and len(grouped) == len(job['scene_narrations']):
        selected = grouped[index-1]
        if isinstance(selected,list) and selected and all(isinstance(t,dict) and isinstance(t.get('text'),str) for t in selected):
            if normalized(''.join(t['text'] for t in selected)) == normalized(narration):
                return selected
    turns = job.get('dialogue_turns') or []
    if not turns:
        return [{'speaker': 'ผู้บรรยาย', 'text': narration}]
    matches = []
    for start in range(len(turns)):
        text = ''
        for end in range(start, len(turns)):
            text += normalized(turns[end].get('text'))
            if text == normalized(narration):
                matches.append(turns[start:end+1])
            if len(text) >= len(normalized(narration)):
                break
    if len(matches) != 1:
        raise ValueError('ยังจับคู่ผู้พูดกับฉากไม่ได้ ไม่ใช้บทพูดผิดฉาก')
    return matches[0]


@scene_render
def render_scene_asset(folder, job, index, video, client, reference_id, render, ffmpeg, cancel_event, progress):
    from core.product_editorial import assert_approved
    assert_approved(job)
    from core.video_composer import MultiFlowComposer
    from core.thai_tts import prepare_thai_tts_script
    from core.cancellable_process import run_cancellable
    from core.external_tts import CLIP_VOICE_EMOTION, CLIP_VOICE_SPEED
    from core.video_logo import locate_ffmpeg
    ffmpeg = str(locate_ffmpeg(ffmpeg))
    folder, video = Path(folder), Path(video)
    mode = audio_mode(job)
    if job.get('actor_dialogue'):
        from core.story_performance import validate_option
        validate_option(True, job.get('video_generation_mode'), job.get('audio_choices'),
                        job.get('storytelling_options'), drama=job.get('job_type') == 'drama_episode', music_job=job)
    turns = scene_turns(job, index) if mode == 'api' else []
    from core.speech_delivery import enabled as speech_enabled, effective_text
    if speech_enabled(job) and mode == 'api':
        # New contracts bind the audible payload (including pronunciation notes)
        # to the paid request key. Legacy keys/bytes are deliberately untouched.
        turns = [dict(turn) for turn in turns]
        for turn in turns:
            text, issues = effective_text(job, turn.get('text'))
            if issues:
                raise ValueError('บทพากย์ฉากนี้ยังไม่พร้อม: ' + ' • '.join(issues))
            turn['text'] = text
    refs = {str(row.get('name') or ''): str(row.get('voice_reference_id') or reference_id)
            for row in job.get('character_bible') or []}
    identity_render = render
    if (job.get('render_snapshot') or {}).get('backend_version') != 1:
        # Old unsaved-default jobs must not get new paid-voice request keys just
        # because this build added local encoder settings to current defaults.
        identity_render = {k: v for k, v in render.items() if k not in {'backend_version', 'encoder', 'green_filter_threads'}}
    payload = [turns,refs,reference_id,job.get('audio_choices'),identity_render,
               hashlib.sha256(video.read_bytes()).hexdigest()]
    if speech_enabled(job):
        payload.append('speech-v1')
    identity = hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    target_dir = folder/'audio'/'scenes'/f'{index:02d}-{identity[:20]}'
    target_dir.mkdir(parents=True,exist_ok=True)
    voice = None
    if mode == 'api' and turns:
        if not client or not reference_id:
            raise ValueError('ยังไม่มีการตั้งค่าเสียงสำหรับฉากนี้')
        paths = []
        for number, turn in enumerate(turns,1):
            check_cancelled(cancel_event)
            # Already normalized with the saved map above for the new contract;
            # do not normalize twice (custom readings can contain numerals).
            text, issues = ((str(turn.get('text') or ''), []) if speech_enabled(job)
                            else prepare_thai_tts_script(str(turn.get('text') or '')))
            if issues or not text:
                raise ValueError('บทพากย์ฉากนี้ยังไม่พร้อม: ' + ' • '.join(issues))
            path = target_dir/f'turn-{number:03d}.wav'
            # The chunk ledger persists every paid request and result, including
            # a one-chunk turn; restart never creates another request key.
            render_chunked_voice(client,text,refs.get(turn.get('speaker')) or reference_id,path,
                scope=f'story:{job["id"]}:scene:{index}:{identity}:turn:{number}',
                options={'language':'th','engine':'auto','silence_sec':.2,'speed':CLIP_VOICE_SPEED,'emotion_id':CLIP_VOICE_EMOTION},ffmpeg_path=ffmpeg,
                cancel_event=cancel_event,on_progress=progress)
            paths.append(path)
        voice = target_dir/'narration.wav'
        listing = target_dir/'concat.txt'
        listing.write_text('\n'.join("file '"+p.resolve().as_posix().replace("'","'\\''")+"'" for p in paths),encoding='utf-8')
        result = run_cancellable([str(ffmpeg or 'ffmpeg'),'-y','-f','concat','-safe','0','-i',str(listing),
            '-c:a','pcm_s16le',str(voice)],cancel_event=cancel_event,timeout=1800)
        if result.returncode or not voice.is_file():
            raise ValueError('รวมเสียงรายฉากไม่สำเร็จ')
    output = target_dir/'scene.mp4'
    from core.story_performance import composition_choices
    scene_choices = composition_choices(job, index) if job.get('actor_dialogue') else job.get('audio_choices')
    if mode == 'api' and not turns:
        # An intentionally silent acting scene must not create an empty concat
        # file or accidentally retain the provider's unrelated spoken audio.
        from core.generated_music import selected
        if not selected(job, index):
            scene_choices = {**(scene_choices or {}), 'mode': 'none', 'keep_video_audio': False}
    plan = MultiFlowComposer(ffmpeg).compose([video],output,voice_path=voice or '',
        width=render['width'],height=render['height'],fps=render['fps'],crf=render['crf'],
        transition_sec=0,timing_mode='voice_fit',tail_seconds=0,extend_mode='smooth',
        audio_choices=scene_choices,cancel_event=cancel_event)
    return {'segment':output.relative_to(folder).as_posix(),'voice':voice.relative_to(folder).as_posix() if voice else '',
            'content_revision':identity,'duration':plan.get('duration')}
