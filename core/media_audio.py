"""Versioned, per-job sound choices. Absent choices preserve legacy behavior."""
import copy

def video_audio_volume(value):
    if type(value) not in (int, float) or not 0 <= value <= 100:
        raise ValueError("ระดับเสียงวิดีโอต้องอยู่ระหว่าง 0–100%")
    return float(value)

def audio_choices(value, video_mode=None):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("ตั้งค่าเสียงไม่ถูกต้อง")
    mode = value.get("mode", "api")
    if mode not in {"api", "flow_original", "none"}:
        raise ValueError("โหมดเสียงไม่ถูกต้อง")
    # Keep the persisted v1 mode name: old jobs/queues must not be migrated.
    if mode == "flow_original" and video_mode is not None and video_mode not in {"flow", "google_flow", "meta_ai"}:
        raise ValueError("เสียงต้นฉบับใช้ได้เมื่อเลือก Google Flow หรือ Meta AI")
    result = {"version": 1, "mode": mode}
    result["video_audio_volume"] = video_audio_volume(value.get("video_audio_volume", 100 if mode == "flow_original" else 35))
    for key, default in (("subtitle", mode == "api"), ("music", False), ("sfx", False), ("allow_silent", False), ("keep_video_audio", False)):
        val = value.get(key, default)
        if not isinstance(val, bool):
            raise ValueError("ตัวเลือกเสียงต้องเป็นเปิดหรือปิด")
        result[key] = val
    if result["keep_video_audio"] and (mode == "none" or video_mode not in {None, "flow", "google_flow", "meta_ai"}):
        raise ValueError("เก็บเสียงวิดีโอได้เมื่อใช้ Google Flow หรือ Meta AI และเปิดเสียงหลักเท่านั้น")
    if 'generated_music_version' in value:
        if type(value['generated_music_version']) is not int or value['generated_music_version'] != 1 or mode == 'none':
            raise ValueError('สัญญาดนตรี AI ไม่ถูกต้อง')
        result['generated_music_version'] = 1
    return result

def audio_mode(job):
    return (job.get("audio_choices") or {}).get("mode", "api")

def product_audio_options(options, choices):
    if not choices:
        return options
    result = copy.deepcopy(options)
    result["audio_choices"] = audio_choices(choices, "flow")
    result["subtitle_enabled"] = choices["subtitle"]
    result["audio_enabled"] = choices["music"] or choices["sfx"]
    audio = result.setdefault("audio", {})
    audio["source_silent"] = choices["mode"] == "none"
    if not choices["music"]:
        audio["background_files"] = []
    if not choices["sfx"]:
        audio["sfx_files"] = []
        audio["sfx_mode"] = "off"
    return result

def product_native_delivery(job):
    return job.get('product_presentation_version') == 1 and audio_mode(job) == 'flow_original'


def flow_audio_instruction(job, index, prompt=""):
    from core.generated_music import apply_to_prompt
    return apply_to_prompt(job, index, _flow_audio_instruction(job, index, prompt))


def _flow_audio_instruction(job, index, prompt=""):
    from core.speech_delivery import native_instruction
    speech = native_instruction(job, index, prompt)
    if speech is not None:
        return speech
    if audio_mode(job) != "flow_original":
        if job.get('actor_dialogue') and audio_mode(job) == 'api':
            from core.story_performance import audio_instruction
            return audio_instruction(job, index)
        return ""
    from core.product_pointing import enabled as pointing_review, native_audio
    if pointing_review(job):
        return native_audio(job, index, prompt)
    from core.product_script import film_scene
    scene = film_scene(job, index)
    if scene is not None:
        # Saved dialogue owns the audio; never read action/marketing directions.
        import json
        if 'SHORT FILM AUDIO:' in prompt and scene['spoken_text'] in prompt:
            return ''
        return ('\nSHORT FILM AUDIO: Speak the exact saved Thai line naturally with synchronized mouth movement. '
                'The character addresses the scene listener, not a reviewer talking to camera. '
                'Only the final CTA may address the viewer. No separate narrator or invented dialogue. '
                'No burned-in subtitles. Speaker: ' + scene['speaker'] + '; listener: ' + scene['listener']
                + '. Spoken line: ' + json.dumps(scene['spoken_text'], ensure_ascii=False))
    from core.story_performance import enabled, audio_instruction
    from core.meta_prompt import separated_roles, narrator_text
    if enabled(job) or (separated_roles(job)
                        and (job.get('storytelling_options') or {}).get('mode') in {'solo', 'dialogue', 'visual'}):
        return audio_instruction(job, index)
    if separated_roles(job) and not product_native_delivery(job):
        import json
        line = narrator_text(job, index)
        if not line.strip():
            return ('\nNARRATOR AUDIO: No narration is saved for this scene. Characters remain silent; '
                    'no speech, vocals, invented lines, subtitles or captions.')
        return ('\nNARRATOR AUDIO: One off-screen narrator reads the exact saved Thai narration once. '
                'Characters remain silent; no lip-sync, character dialogue, extra words or invented speech. '
                'Quoted words inside the narration are read by the same narrator, not assigned to a character. '
                'Do not read visual directions. No subtitles or captions burned into the picture. '
                'Voiceover text: ' + json.dumps(line, ensure_ascii=False))
    # A provider/scene editor can already specify one exact dialogue line.
    # Never append the entire narrator script as a contradictory second line.
    import re
    delivery = ('\nAUDIO PERFORMANCE: The visible reviewer speaks Thai directly to camera with natural synchronized lip movements, '
                'expressive gestures and natural product handling. This is on-camera dialogue, not off-screen narration. '
                'Do not make a silent video or add a separate narrator. Preserve the exact supplied Thai line; do not invent claims. '
                'No subtitles or captions burned into the picture.\n') if product_native_delivery(job) else ''
    if re.search(r'(?:the only spoken line is|spoken line)\s*:\s*\S', prompt, re.I):
        return '' if not delivery or 'AUDIO PERFORMANCE:' in prompt else delivery
    lines = job.get("scene_narrations") or job.get("spoken_script_segments") or []
    line = lines[index - 1] if 0 < index <= len(lines) else ""
    if isinstance(line, dict):
        line = line.get("text") or line.get("script") or ""
    return delivery + "\nAUDIO: Include clear natural Thai speech for this scene. No subtitles or captions burned into the picture. Spoken line: " + str(line)[:1500]

def native_transcript(source, folder, credential, config, cancel_event=None):
    from core.smartsub_online import SmartSubOnlineClient
    from core.subtitle_chunks import transcribe_chunks
    from pathlib import Path
    if not credential:
        raise ValueError("เปิดซับจากเสียงต้นฉบับไว้ กรุณาเชื่อมต่อ Subtitle API")
    client = SmartSubOnlineClient(credential, config.get("subtitle_api_base_url", "https://www.catfufu.com/api/smartsub-online/v2"))
    wav = Path(folder) / "audio" / "flow_subtitle_source.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    client.prepare_wav(source, wav, config.get("ffmpeg_path", ""), cancel_event=cancel_event)
    return transcribe_chunks(client, wav, Path(folder) / "audio" / "flow_subtitle_chunks", cancel_event=cancel_event)
