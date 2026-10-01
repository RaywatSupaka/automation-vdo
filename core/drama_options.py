"""Immutable per-series output choices, separate from live form defaults."""
import copy
import math
from core.presenter import presenter_settings


def drama_render_options(value):
    if not isinstance(value, dict):
        raise ValueError("ตั้งค่าซีรีส์ไม่ถูกต้อง")
    mode = value.get("video_generation_mode", "image_motion")
    timing = value.get("timing_mode", "voice_fit")
    if mode not in {"image_motion", "google_flow", "meta_ai"} or timing not in {"voice_fit", "original"}:
        raise ValueError("วิธีสร้างวิดีโอหรือจัดเวลาไม่ถูกต้อง")
    tail = float(value.get("tail_seconds", 0.75))
    if not math.isfinite(tail) or not 0 <= tail <= 2:
        raise ValueError("ช่วงท้ายคลิปต้องอยู่ระหว่าง 0–2 วินาที")
    subtitle = value.get("subtitle_enabled", True)
    if not isinstance(subtitle, bool):
        raise ValueError("ตัวเลือก Subtitle ไม่ถูกต้อง")
    result = copy.deepcopy(dict(video_generation_mode=mode, timing_mode=timing,
        tail_seconds=tail, subtitle_enabled=subtitle,
        presenter=presenter_settings(value.get("presenter") or {"enabled": False})))
    if 'speech_delivery_version' in value:
        from core.speech_delivery import version
        result['speech_delivery_version'] = version(value['speech_delivery_version'])
    for field in ('primary_voice_reference_id', 'primary_voice_reference_file'):
        if field in value:
            selected = value[field]
            if not isinstance(selected, str) or len(selected) > 1024:
                raise ValueError('เสียงหลักของซีรีส์ไม่ถูกต้อง')
            result[field] = selected.strip()
    if "audio_choices" in value:
        from core.media_audio import audio_choices
        result["audio_choices"] = audio_choices(value["audio_choices"], mode)
        if not (value.get('generated_music_options') or {}).get('enabled'):
            result['audio_choices'].pop('generated_music_version', None)
        result["subtitle_enabled"] = result["audio_choices"]["subtitle"]
        from core.creation_queue import clean_settings
        captured = clean_settings({"audio": value.get("audio_mix_choices") or {}, "finish_config": value.get("media_finish_config") or {}})
        result["audio_mix_choices"] = captured["audio"]
        result["media_finish_config"] = captured["finish_config"]
    if "fictional_ai_characters_confirmed" in value:
        result["fictional_ai_characters_confirmed"] = value["fictional_ai_characters_confirmed"] is True
    if "flow_settings" in value:
        from core.flow_settings import flow_settings
        result["flow_settings"] = flow_settings(value["flow_settings"])
    if 'ai_cover_options' in value:
        from core.ai_cover import ai_cover_options
        result['ai_cover_options'] = ai_cover_options(value['ai_cover_options'])
    if 'intro_options' in value:
        from core.video_intro import intro_options
        result['intro_options'] = intro_options(value['intro_options'])
    if 'green_options' in value:
        from core.green_screen import green_options
        result['green_options'] = green_options(value['green_options'])
    if 'render_snapshot' in value:
        from core.creation_queue import clean_settings
        result['render_snapshot'] = clean_settings({'render': value['render_snapshot']})['render']
    if value.get('storytelling_options') is not None:
        from core.storytelling import validate_settings, native_acting
        result['storytelling_options'] = validate_settings(value['storytelling_options'], mode, result.get('audio_choices'),
            drama=True, generated_music_options=value.get('generated_music_options'))
        if native_acting(result['storytelling_options']) and not result.get('audio_choices'):
            from core.media_audio import audio_choices
            result['audio_choices'] = audio_choices({'mode': 'none' if result['storytelling_options']['mode'] == 'visual' else 'flow_original',
                                                     'subtitle': False}, mode)
            result['subtitle_enabled'] = False
    if value.get('generated_music_options') is not None:
        from core.generated_music import validate_options
        result['generated_music_options'] = validate_options(value['generated_music_options'], mode, result.get('audio_choices'))
    return result
