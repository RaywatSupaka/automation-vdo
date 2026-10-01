"""Compose Flow clips, burn Thai subtitles, apply logo, and mix professional audio."""

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.audio_mixer import AudioMixer
from core.config import load_config
from core.product_manager import ProductManager
from core.secure_store import WindowsCredentialStore
from core.smartsub_online import SmartSubOnlineClient
from core.subtitle_renderer import SubtitleVideoRenderer
from core.subtitle_styles import SUBTITLE_THEMES
from core.video_composer import MultiFlowComposer
from core.video_logo import VideoLogoRenderer


def relative_or_absolute(root, value):
    path = Path(str(value or ""))
    return path if path.is_absolute() else root / path


def mode(value, kind):
    text = str(value or "").lower()
    if "สุ่ม" in text or "random" in text:
        return "random"
    if "เลือก" in text or "selected" in text:
        return "selected"
    if kind == "sfx" and ("ปิด" in text or text == "off"):
        return "off"
    return "auto"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--reuse-subtitle", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    config = load_config()
    ffmpeg = str(config.get("ffmpeg_path") or "")
    manager = ProductManager(root)
    folder = manager.root / args.job
    manifest = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    clips = [folder / "videos" / f"flow_shot_{index:02d}.mp4" for index in (1, 2, 3)]
    for index, clip in enumerate(clips, 1):
        manager.attach_flow_clip(args.job, index, clip)

    voice = folder / str(manifest.get("voice_path") or "")
    composed = folder / "videos" / "multi_flow_with_voice.mp4"
    compose_plan = MultiFlowComposer(ffmpeg).compose(clips, composed, voice, width=720, height=1280, fps=30)
    manager.promote_video(args.job, str(composed.relative_to(folder)), "videos/flow_shot_01.mp4")
    print("STEP 1/5 COMPOSED", flush=True)

    logo_source = relative_or_absolute(root, config.get("logo_file"))
    with_logo = folder / "videos" / "multi_flow_with_voice_logo.mp4"
    logo_options = {
        "opacity": float(config.get("logo_opacity", 0.65)),
        "size_percent": float(config.get("logo_size_percent", 16)),
        "position": str(config.get("logo_position", "top_right")),
        "margin": int(config.get("logo_margin", 28)),
    }
    VideoLogoRenderer(ffmpeg).render(composed, logo_source, with_logo, **logo_options)
    manager.save_logo_video(args.job, with_logo, composed, logo_source, logo_options)
    print("STEP 2/5 LOGO", flush=True)

    syllables = int(config.get("subtitle_syllables_per_cue", 3))
    if args.reuse_subtitle:
        current = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        subtitle_job_id = str(current.get("subtitle_job_id") or "REUSED")
    else:
        credential = WindowsCredentialStore("SmartPostAI/CatfufuSmartSubOnlineSOD").load()
        if not credential:
            raise RuntimeError("ยังไม่ได้บันทึกรหัสอุปกรณ์ Subtitle")
        subtitle_client = SmartSubOnlineClient(credential, config.get("subtitle_api_base_url"))
        wav = folder / "audio" / "subtitle_source.wav"
        subtitle_client.prepare_wav(voice, wav, ffmpeg)
        created = subtitle_client.create_job(wav, str(config.get("subtitle_language") or "th"), str(uuid.uuid4()))
        subtitle_job_id = str(created.get("jobId") or created.get("job_id"))
        manager.mark_subtitle_queued(args.job, subtitle_job_id, str(config.get("subtitle_language") or "th"))
        result = subtitle_client.wait_until_done(
            subtitle_job_id,
            on_status=lambda status, _result: print(f"SUBTITLE {status}", flush=True),
        )
        manager.save_subtitle_result(args.job, subtitle_job_id, result, syllables)
    _, subtitle = manager.correct_subtitle_from_script(args.job)
    print("STEP 3/5 SUBTITLE API", flush=True)

    theme_key = str(config.get("subtitle_theme") or "standard")
    theme = dict(SUBTITLE_THEMES.get(theme_key) or SUBTITLE_THEMES["standard"])
    font_path = relative_or_absolute(root, config.get("subtitle_font_file") or f"assets/fonts/smartsubai/{theme['font_file']}")
    style = {
        "font_name": font_path.stem,
        "font_path": str(font_path),
        "font_size": int(config.get("subtitle_font_size") or theme["font_size"]),
        "text_color": str(config.get("subtitle_text_color") or theme["text_color"]),
        "highlight_color": str(config.get("subtitle_highlight_color") or "#FACC15"),
        "outline_color": str(config.get("subtitle_outline_color") or theme["outline_color"]),
        "outline_width": int(config.get("subtitle_outline_width", theme["outline_width"])),
        "background_enabled": bool(config.get("subtitle_background_enabled", theme["background_enabled"])),
        "background_color": str(config.get("subtitle_background_color") or theme["background_color"]),
        "background_opacity": float(config.get("subtitle_background_opacity", theme["background_opacity"])),
        "position": str(config.get("subtitle_position") or "bottom"),
        "margin_v": int(config.get("subtitle_margin_v", 72)),
        "animation": str(config.get("subtitle_animation") or "fade"),
    }
    subtitled = folder / "videos" / "final_with_subtitles_logo.mp4"
    SubtitleVideoRenderer(ffmpeg).render(with_logo, subtitle, subtitled, **style)
    stored_style = dict(style)
    stored_style["font_path"] = str(font_path.relative_to(root)) if root in font_path.parents else str(font_path)
    manager.save_subtitled_video(args.job, subtitled, with_logo, subtitle, stored_style)
    print("STEP 4/5 SUBTITLE RENDER", flush=True)

    mixer = AudioMixer(ffmpeg)
    backgrounds = mixer.scan_audio(root / "assets" / "audio" / "background") if config.get("audio_background_enabled", True) else []
    effects = mixer.scan_audio(root / "assets" / "audio" / "sfx") if config.get("audio_sfx_enabled", True) else []
    final = folder / "videos" / "final_with_audio.mp4"
    audio_settings = {
        "background_mode": mode(config.get("audio_background_mode"), "background"),
        "background_volume": float(config.get("audio_background_volume", 0.12)),
        "sfx_mode": mode(config.get("audio_sfx_mode"), "sfx"),
        "sfx_volume": float(config.get("audio_sfx_volume", 0.22)),
        "min_sfx_interval": float(config.get("audio_sfx_min_interval", 6)),
        "max_sfx_count": int(config.get("audio_sfx_max_count", 6)),
    }
    audio_plan = mixer.render(
        subtitled, final,
        background_files=backgrounds,
        background_mode=audio_settings["background_mode"],
        background_volume=audio_settings["background_volume"],
        sfx_files=effects,
        sfx_mode=audio_settings["sfx_mode"],
        sfx_volume=audio_settings["sfx_volume"],
        cue_times=mixer.cue_times(subtitle),
        min_sfx_interval=audio_settings["min_sfx_interval"],
        max_sfx_count=audio_settings["max_sfx_count"],
        seed=args.job,
    )
    saved = manager.save_audio_mix_result(args.job, final, subtitled, audio_settings, audio_plan)
    print("STEP 5/5 AUDIO MIX", flush=True)
    print(json.dumps({
        "job_id": args.job,
        "flow_clips": len(clips),
        "compose": {key: value for key, value in compose_plan.items() if key != "output"},
        "subtitle_job_id": subtitle_job_id,
        "syllables_per_cue": syllables,
        "subtitle_theme": theme_key,
        "subtitle_animation": style["animation"],
        "music_segments": len(audio_plan["music_plan"]),
        "sfx_events": len(audio_plan["sfx_events"]),
        "final": str(final),
        "video_status": saved.get("video_status"),
        "readiness": saved.get("readiness"),
    }, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
