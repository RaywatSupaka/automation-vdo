from pathlib import Path
import os
import shutil
import time

from core.audio_mixer import AudioMixer
from core.cancellable_process import check_cancelled
from core.product_manager import ProductManager
from core.story_script import spoken_script_for_job
from core.subtitle_renderer import SubtitleVideoRenderer
from core.subtitle_styles import SUBTITLE_THEMES
from core.thai_tts import prepare_thai_tts_script
from core.studio_review import pronunciation_notes
from core.video_logo import VideoLogoRenderer
from core.logo_layout import logo_render_options
from core.workspace_cleaner import working_video_folder
from core.presenter import apply_presenter


def _path(root, value):
    path = Path(str(value or ""))
    return path if path.is_absolute() else Path(root) / path


def _audio_mode(value, kind):
    text = str(value or "").lower()
    if "สุ่ม" in text or "random" in text:
        return "random"
    if "เลือก" in text or "selected" in text:
        return "selected"
    if kind == "sfx" and ("ปิด" in text or text == "off"):
        return "off"
    return "auto"


def _subtitle_script(job):
    """Return only text that is actually spoken in the rendered voice track."""
    if str(job.get("job_type") or "") == "drama_episode" and job.get("dialogue_turns"):
        # Speaker labels belong to the production script, not the audio.
        # Keeping them in the SRT consumed timing for words nobody spoke
        # and made the visible subtitle trail the dialogue.
        raw_script = spoken_script_for_job(job)
        source = "exact_drama_dialogue_turns"
    else:
        raw_script = str(job.get("narration_script") or "").strip()
        source = "exact_chatgpt_narration_script"
    # Voice rendering always passes through the same deterministic Thai TTS
    # normalizer.  Subtitle text must do the same or an English proper name can
    # be spoken in Thai while the on-screen caption still shows the raw word.
    from core.speech_delivery import enabled as speech_enabled, effective_script
    script, issues = (effective_script(job) if speech_enabled(job)
                      else prepare_thai_tts_script(raw_script, pronunciation_notes(job)))
    if issues:
        raise ValueError("ซับไตเติ้ลไม่ตรงบทเสียง: " + " • ".join(issues))
    return script, source


def finish_story_media(root, story_manager, job_id, source_video, config, progress=None, cancel_event=None):
    """Reuse the program's subtitle, logo and audio preferences for Story Shorts."""
    root = Path(root)
    progress = progress or (lambda percent, stage, message: None)
    check_cancelled(cancel_event)
    job = story_manager.get(job_id)
    from core.product_editorial import assert_approved
    assert_approved(job)
    saved_job = job
    from core.scene_video_plan import enabled as planned_video, ordered_assets
    video_plan_enabled = planned_video(job)
    if job.get('scene_pipeline_version') == 1:
        from core.scene_context_revision import render_story
        job = render_story(story_manager.root / job_id, job)
        assert_approved(job)
    from core.media_audio import audio_mode, native_transcript
    choices = job.get("audio_choices") or {}
    subtitle_enabled = choices.get("subtitle", (job.get("render_options") or {}).get("subtitle_enabled", True))
    from core.story_performance import conversation_only
    if conversation_only(job) and not job.get('storytelling_options'):
        subtitle_enabled = False
    config = dict(config)
    if choices:
        config.update(audio_background_enabled=choices["music"], audio_sfx_enabled=choices["sfx"])
    folder = story_manager.root / job_id
    working = working_video_folder(folder)
    source = Path(source_video)
    _presenter_plan = {"enabled": False}
    if (job.get("presenter") or {}).get("enabled"):
        progress(85, "presenter", "วางตัวละครผู้บรรยาย • ใช้เสียงหลัก ไม่ซิงก์ปาก")
        source, _presenter_plan = apply_presenter(root, source, working / "story_with_presenter.mp4",
            job["presenter"], config.get("ffmpeg_path", ""), cancel_event)
    mixer = AudioMixer(config.get("ffmpeg_path", ""))
    duration = mixer.duration(source)
    script, subtitle_source = _subtitle_script(job) if subtitle_enabled and audio_mode(job) == "api" else (str(job.get("narration_script") or "") if subtitle_enabled and audio_mode(job) == "none" else "", "scene_text" if subtitle_enabled else "disabled")
    syllables = max(1, min(5, int(config.get("subtitle_syllables_per_cue") or 3)))
    quality_crf = {"standard": 21, "high": 18, "maximum": 16}.get(str(config.get("video_quality") or "high"), 18)
    voice_path = _path(folder, job.get("voice_path") or "audio/narration.mp3")
    progress(86, "finishing", "กำลังเทียบจังหวะซับกับเสียงพูดจริง" if subtitle_enabled else "เตรียมประกอบคลิป • ไม่ใส่ซับ")
    speech_intervals = mixer.speech_intervals(voice_path, cancel_event=cancel_event) if subtitle_enabled and audio_mode(job) == "api" and voice_path.is_file() else [(0.0, duration)]
    subtitle_lead_ms = max(0, min(500, int(config.get("subtitle_sync_lead_ms") or 120)))
    character_names = [
        str(character.get("name") or "").strip()
        for character in (job.get("character_bible") or [])
        if isinstance(character, dict) and str(character.get("name") or "").strip()
    ]
    timed_words = ProductManager._script_to_timed_words(
        script, duration, speech_intervals=speech_intervals,
        lead_seconds=subtitle_lead_ms / 1000.0,
        protected_terms=character_names,
    )
    if subtitle_enabled and audio_mode(job) == 'api' and job.get('scene_pipeline_version') == 1:
        from core.scene_pipeline import ScenePipeline
        pipeline = ScenePipeline(folder)
        timed_words, offset = [], 0.0
        actor_groups = job.get('scene_dialogue_turns') if job.get('actor_dialogue') and job.get('storytelling_options') else None
        for index, text in enumerate(job.get('scene_narrations') or [], 1):
            row = pipeline.get(index)
            length = float(row.get('duration') or 0)
            if actor_groups is not None:
                text = ' '.join(str(turn.get('text') or '') for turn in actor_groups[index - 1])
            scene_voice = folder / str(row.get('voice') or '')
            intervals = mixer.speech_intervals(scene_voice,cancel_event=cancel_event) if scene_voice.is_file() else [(0,length)]
            words = ProductManager._script_to_timed_words(str(text),length,speech_intervals=intervals,
                lead_seconds=subtitle_lead_ms/1000.0,protected_terms=character_names)
            timed_words.extend([{**word,'start':word['start']+offset,'end':word['end']+offset} for word in words])
            offset += length
    srt = ProductManager._segments_to_srt([{"words": timed_words}], syllables) if subtitle_enabled else ""
    if subtitle_enabled and audio_mode(job) == "flow_original":
        transcript = native_transcript(source, folder, config.get("native_subtitle_credential", ""), config, cancel_event)
        if (job.get('actor_dialogue') or job.get('product_presentation_version') == 1) and not any(str(row.get('text') or '').strip() or row.get('words') for row in transcript.get('segments', [])):
            raise ValueError('FLOW_SPEECH_REVIEW • ไม่พบคำพูดจากเสียงคลิป เก็บคลิปเดิมไว้ตรวจ ไม่ใช้บทที่วางไว้แทนเสียงจริง')
        if video_plan_enabled or (job.get('scene_pipeline_version') == 1 and job.get('video_generation_mode') == 'google_flow'):
            from core.atomic_json import AtomicJsonFile
            from core.flow_speech_quality import audit_native_scene_speech, RepeatedNativeSpeechError
            from core.scene_pipeline import ScenePipeline
            pipeline = ScenePipeline(folder)
            scene_rows = [pipeline.get(index) for index in range(1, int(job['scene_count']) + 1)]
            assets = ordered_assets(folder, saved_job) if video_plan_enabled else []
            durations = ([asset.get('duration') for asset in assets]
                         if video_plan_enabled and job.get('scene_pipeline_version') != 1
                         else [row.get('duration') for row in scene_rows])
            expected_speech = job.get('scene_narrations') or []
            if job.get('actor_dialogue') and job.get('storytelling_options'):
                groups = job.get('scene_dialogue_turns') or []
                expected_speech = [' '.join(str(turn.get('text') or '') for turn in group)
                                   for group in groups]
            audit = audit_native_scene_speech(transcript, expected_speech, durations,
                                              composed_duration=duration)
            audit['scene_segments'] = {str(index): str(row.get('segment_sha256') or '')
                                       for index, row in enumerate(scene_rows, 1)}
            if video_plan_enabled:
                audit['scene_providers'] = {str(asset['index']): asset['provider'] for asset in assets}
            AtomicJsonFile(folder / 'audio' / 'flow_speech_quality.json').write(audit)
            if audit['status'] == 'unverified':
                raise ValueError('FLOW_SPEECH_REVIEW • เวลาฉากกับเสียงต้นฉบับไม่ตรงกัน • เก็บคลิปเดิมไว้ตรวจ')
            if audit['findings']:
                if video_plan_enabled:
                    finding = audit['findings'][0]
                    provider = audit['scene_providers'].get(str(finding['scene']))
                    if provider != 'google_flow' or job.get('scene_pipeline_version') != 1:
                        label = 'Meta AI' if provider == 'meta_ai' else 'Google Flow' if provider == 'google_flow' else 'คลิปในเครื่อง'
                        raise ValueError(f"SCENE_SPEECH_REVIEW • ฉาก {finding['scene']} จาก {label} มีเสียงพูดซ้ำ • เก็บคลิปเดิมไว้ตรวจ ไม่สั่งผู้สร้างอื่นแทน")
                raise RepeatedNativeSpeechError(audit)
        srt = ProductManager._segments_to_srt(transcript["segments"], syllables)
        if video_plan_enabled:
            providers = {asset['provider'] for asset in ordered_assets(folder, saved_job)}
            subtitle_source = ('mixed_actual_audio' if len(providers) > 1 else
                               'meta_actual_audio' if providers == {'meta_ai'} else 'flow_actual_audio')
        else:
            subtitle_source = "meta_actual_audio" if job.get('video_generation_mode') == 'meta_ai' else "flow_actual_audio"
    subtitle = folder / "captions" / "story_subtitle.srt"
    if subtitle_enabled:
        subtitle.write_text(srt.rstrip() + "\n", encoding="utf-8")

    progress(88, "finishing", "กำลังใส่คำบรรยายลงวิดีโอ" if subtitle_enabled else "ไม่ใส่ Subtitle ตามค่าที่บันทึกไว้")
    theme = dict(SUBTITLE_THEMES.get(str(config.get("subtitle_theme") or "standard")) or SUBTITLE_THEMES["standard"])
    font_path = _path(root, config.get("subtitle_font_file") or f"assets/fonts/smartsubai/{theme['font_file']}")
    subtitled = working / "story_with_subtitles.mp4"
    from core.render_backend import optimized_render
    logo = _path(root, config.get('logo_file') or 'assets/smartflow_logo.png')
    combined_logo = ({'file': str(logo), **logo_render_options(config)}
        if optimized_render() and subtitle_enabled and logo.is_file() else None)
    subtitle_plan = SubtitleVideoRenderer(config.get("ffmpeg_path", "")).render(
        source, subtitle, subtitled,
        font_name=font_path.stem, font_path=str(font_path),
        font_size=int(config.get("subtitle_font_size") or theme["font_size"]),
        letter_spacing=float(config.get("subtitle_letter_spacing", theme.get("letter_spacing", 0))),
        thai_mark_gap=float(config.get("subtitle_thai_mark_gap", theme.get("thai_mark_gap", 14))),
        text_color=str(config.get("subtitle_text_color") or theme["text_color"]),
        highlight_color=str(config.get("subtitle_highlight_color") or "#FACC15"),
        outline_color=str(config.get("subtitle_outline_color") or theme["outline_color"]),
        outline_width=int(config.get("subtitle_outline_width", theme["outline_width"])),
        background_enabled=bool(config.get("subtitle_background_enabled", theme["background_enabled"])),
        background_color=str(config.get("subtitle_background_color") or theme["background_color"]),
        background_opacity=float(config.get("subtitle_background_opacity", theme["background_opacity"])),
        position=str(config.get("subtitle_position") or "bottom"),
        position_y_percent=float(config.get("subtitle_position_y_percent", 90)),
        margin_v=int(config.get("subtitle_margin_v", 72)),
        animation=str(config.get("subtitle_animation") or "fade"),
        cancel_event=cancel_event,
        crf=quality_crf,
        **({'logo_overlay': combined_logo} if combined_logo else {}),
    ) if subtitle_enabled else {"output": source}
    progress(92, "finishing", "ใส่คำบรรยายเสร็จแล้ว" if subtitle_enabled else "ข้ามการใส่ Subtitle แล้ว")
    active = subtitled if subtitle_enabled else source
    logo_plan = {'combined_with_subtitle': True} if subtitle_plan.get('logo_included') else None
    logo = _path(root, config.get("logo_file") or "assets/smartflow_logo.png")
    if logo.is_file() and not logo_plan:
        check_cancelled(cancel_event)
        progress(92, "finishing", "กำลังใส่โลโก้")
        with_logo = working / "story_with_subtitles_logo.mp4"
        logo_plan = VideoLogoRenderer(config.get("ffmpeg_path", "")).render(
            active, logo, with_logo,
            **logo_render_options(config),
            cancel_event=cancel_event,
            crf=quality_crf,
        )
        active = with_logo
    progress(95, "finishing", "เตรียมเพลงและเสียงประกอบ")

    check_cancelled(cancel_event)
    backgrounds = mixer.scan_audio(root / "assets" / "audio" / "background") if config.get("audio_background_enabled", True) else []
    effects = mixer.scan_audio(root / "assets" / "audio" / "sfx") if config.get("audio_sfx_enabled", True) else []
    captured_audio = job.get("audio_mix_choices") or {}
    if choices and captured_audio:
        backgrounds = captured_audio.get("background_files", []) if choices["music"] else []
        effects = captured_audio.get("sfx_files", []) if choices["sfx"] else []
        for source_key, config_key in (("background_volume", "audio_background_volume"), ("background_mode", "audio_background_mode"), ("sfx_volume", "audio_sfx_volume"), ("sfx_mode", "audio_sfx_mode"), ("music_segment_max_sec", "audio_background_segment_max_sec")):
            if source_key in captured_audio:
                config[config_key] = captured_audio[source_key]
    destination = folder / "videos" / "story_short_complete.mp4"
    final = working / "story_short_complete_candidate.mp4"
    audio_plan = mixer.render(
        active, final,
        background_files=backgrounds,
        music_track_count=captured_audio.get("music_track_count"),
        background_mode=_audio_mode(config.get("audio_background_mode"), "background"),
        background_volume=float(config.get("audio_background_volume", 0.12)),
        music_segment_max_sec=float(config.get("audio_background_segment_max_sec", 12.0)),
        music_duck_ratio=float(config.get("audio_background_duck_percent", 38)) / 100,
        sfx_files=effects,
        sfx_mode=_audio_mode(config.get("audio_sfx_mode"), "sfx"),
        sfx_volume=float(config.get("audio_sfx_volume", 0.22)),
        cue_times=mixer.cue_times(subtitle) if subtitle_enabled else [],
        min_sfx_interval=float(config.get("audio_sfx_min_interval", 6)),
        max_sfx_count=int(config.get("audio_sfx_max_count", 6)),
        seed=job_id,
        cancel_event=cancel_event,
        source_silent=audio_mode(job) == "none",
    )
    final = Path(audio_plan["output"])
    progress(99, "finishing", "ตรวจไฟล์ผลงานขั้นสุดท้าย")
    final_duration = mixer.duration(final)
    if abs(final_duration - duration) > 0.25:
        raise ValueError("ภาพ/เสียงหลังใส่เอฟเฟกต์มีระยะเวลาไม่ตรงต้นฉบับ • ยังไม่แทนที่ผลงานเดิม")
    intro_plan = {'enabled':False}
    if (job.get('intro_options') or {}).get('enabled'):
        from core.video_intro import insert_intro
        progress(99, 'intro', 'สุ่มจังหวะหลังเริ่มเล่า แล้วแทรกอินโทรก่อนเล่นคลิปต่อ')
        final, intro_plan = insert_intro(root, final, working/'story_with_intro_candidate.mp4', job['intro_options'],
                                       config.get('ffmpeg_path', ''), cancel_event, quality_crf,
                                       timing_source=voice_path if audio_mode(job) == 'api' and voice_path.is_file() else source,
                                       seed=f'{job_id}|{job["intro_options"]["file"]}')
        final_duration = intro_plan['duration']
    green_plan = {'enabled':False}
    if (job.get('green_options') or {}).get('enabled'):
        from core.green_screen import render_green
        progress(99,'finishing','กำลังซ้อนกรีนสกรีนชั้นบนสุด • ไม่ใช้เสียงเอฟเฟกต์')
        final, green_plan = render_green(root,final,working/'story_green_candidate.mp4',job['green_options'],config.get('ffmpeg_path',''),cancel_event,
                                        progress=lambda message: progress(99,'finishing',message))
    check_cancelled(cancel_event)
    if destination.is_file():
        backups = folder / "backups" / "finals"
        backups.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination, backups / f"previous-{time.time_ns()}.mp4")
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(final, destination)
    final = destination
    plan = {
        "intro": intro_plan,
        "green_screen": green_plan,
        "presenter": _presenter_plan,
        "source_type": "story_image_sequence",
        "scene_count": len(job.get("generated_images") or []),
        "duration": final_duration,
        "duration_validation": "passed",
        "voice_included": audio_mode(job) != "none",
        "audio_mode": audio_mode(job),
        "subtitle_included": subtitle_enabled,
        "subtitle_source": subtitle_source,
        "subtitle_timing": "disabled" if not subtitle_enabled else ("actual_mixed_audio" if subtitle_source == 'mixed_actual_audio' else "actual_meta_audio" if subtitle_source == 'meta_actual_audio' else "actual_flow_audio") if audio_mode(job) == "flow_original" else "scene_text" if audio_mode(job) == "none" else "voice_activity_aligned",
        "subtitle_speech_intervals": len(speech_intervals),
        "subtitle_sync_lead_ms": subtitle_lead_ms,
        "subtitle_word_integrity": "whole_words_no_midword_split",
        "subtitle_protected_character_names": character_names,
        "subtitle_syllables_per_cue": syllables,
        "logo_included": bool(logo_plan),
        "background_segments": len(audio_plan.get("music_plan") or []),
        "audio_mix_version": int(audio_plan.get("audio_mix_version") or 1),
        "background_unique_tracks": int(audio_plan.get("music_unique_tracks") or 0),
        "background_requested_tracks": audio_plan.get("music_requested_tracks"),
        "background_selected_files": list(audio_plan.get("music_selected_files") or []),
        "background_music_plan": list(audio_plan.get("music_plan") or []),
        "background_max_segment_sec": float(audio_plan.get("music_segment_max_sec") or 0),
        "background_crossfade_sec": float(audio_plan.get("music_crossfade_sec") or 0),
        "background_duck_percent": round(float(audio_plan.get("music_duck_ratio") or 0) * 100),
        "background_warnings": list(audio_plan.get("music_warnings") or []),
        "sfx_events": len(audio_plan.get("sfx_events") or []),
        "subtitle_output": str(subtitle_plan["output"]),
    }
    return final, plan
