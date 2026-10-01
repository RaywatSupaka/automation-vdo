"""Build a product-fidelity fallback from the three approved ChatGPT images."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.audio_mixer import AudioMixer
from core.config import load_config
from core.product_manager import ProductManager
from core.subtitle_renderer import SubtitleVideoRenderer
from core.video_composer import MultiFlowComposer
from core.video_logo import VideoLogoRenderer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    config = load_config()
    ffmpeg = str(config.get("ffmpeg_path") or "")
    manager = ProductManager(root)
    folder = manager.root / args.job
    manifest_path = folder / "job.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    images = [folder / value for value in manifest.get("generated_images") or []]
    if len(images) != 3 or any(not image.is_file() for image in images):
        raise ValueError("ต้องมีรูป ChatGPT ที่ผ่านการตรวจ 3 รูป")

    current_final = folder / str(manifest.get("video_path") or "")
    flow_draft = folder / "videos" / "final_flow_draft_needs_review.mp4"
    if current_final.is_file() and current_final.resolve() != flow_draft.resolve():
        shutil.copy2(current_final, flow_draft)

    zooms = [
        "min(zoom+0.00018,1.065)",
        "min(zoom+0.00014,1.050)",
        "if(eq(on,1),1.060,max(zoom-0.00017,1.000))",
    ]
    clips = []
    for index, (image, zoom) in enumerate(zip(images, zooms), 1):
        clip = folder / "videos" / f"safe_image_shot_{index:02d}.mp4"
        temporary = clip.with_name(f".{clip.stem}.rendering.mp4")
        filters = (
            "scale=720:1280:force_original_aspect_ratio=increase,"
            "crop=720:1280,"
            f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=360:s=720x1280:fps=30,"
            "format=yuv420p"
        )
        command = [ffmpeg, "-y", "-loop", "1", "-i", str(image), "-vf", filters, "-frames:v", "360", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", str(temporary)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        if result.returncode or not temporary.is_file():
            raise RuntimeError("สร้างคลิปสำรองไม่สำเร็จ: " + result.stderr[-800:])
        temporary.replace(clip)
        clips.append(clip)

    voice = folder / str(manifest.get("voice_path") or "")
    base = folder / "videos" / "safe_images_with_voice.mp4"
    compose = MultiFlowComposer(ffmpeg).compose(clips, base, voice, width=720, height=1280, fps=30)

    logo = Path(str(config.get("logo_file") or ""))
    if not logo.is_absolute():
        logo = root / logo
    with_logo = folder / "videos" / "safe_images_with_voice_logo.mp4"
    logo_options = {
        "opacity": float(config.get("logo_opacity", 0.65)),
        "size_percent": float(config.get("logo_size_percent", 16)),
        "position": str(config.get("logo_position", "top_right")),
        "margin": int(config.get("logo_margin", 28)),
    }
    VideoLogoRenderer(ffmpeg).render(base, logo, with_logo, **logo_options)

    subtitle = folder / "captions" / "subtitle.srt"
    style = dict(manifest.get("subtitle_style") or {})
    font_path = Path(str(style.get("font_path") or ""))
    if not font_path.is_absolute():
        font_path = root / font_path
    style["font_path"] = str(font_path)
    subtitled = folder / "videos" / "safe_images_with_subtitles_logo.mp4"
    SubtitleVideoRenderer(ffmpeg).render(with_logo, subtitle, subtitled, **style)

    mixer = AudioMixer(ffmpeg)
    audio_settings = dict(manifest.get("audio_mix_settings") or {})
    backgrounds = mixer.scan_audio(root / "assets" / "audio" / "background") if config.get("audio_background_enabled", True) else []
    effects = mixer.scan_audio(root / "assets" / "audio" / "sfx") if config.get("audio_sfx_enabled", True) else []
    final = folder / "videos" / "final_safe_product_fidelity.mp4"
    plan = mixer.render(
        subtitled, final,
        background_files=backgrounds,
        background_mode=str(audio_settings.get("background_mode") or "auto"),
        background_volume=float(audio_settings.get("background_volume", 0.12)),
        sfx_files=effects,
        sfx_mode=str(audio_settings.get("sfx_mode") or "auto"),
        sfx_volume=float(audio_settings.get("sfx_volume", 0.22)),
        cue_times=mixer.cue_times(subtitle),
        min_sfx_interval=float(audio_settings.get("min_sfx_interval", 6)),
        max_sfx_count=int(audio_settings.get("max_sfx_count", 6)),
        seed=args.job + "-safe",
    )
    saved = manager.save_audio_mix_result(args.job, final, subtitled, audio_settings, plan)
    manager.save_video_qa(args.job, "needs_review", [
        "Google Flow draft changed the cabinet front into a black circular door and was preserved only as a draft.",
        "The active final uses the three approved ChatGPT images with controlled motion to reduce product-identity drift.",
        "AI marketing images must still be reviewed against the live Shopee product before posting.",
    ], [str(flow_draft.relative_to(folder)), str(final.relative_to(folder))])
    print(json.dumps({
        "job_id": args.job,
        "source": "three_chatgpt_images",
        "duration": compose["duration"],
        "flow_draft": str(flow_draft),
        "safe_final": str(final),
        "video_path": saved.get("video_path"),
        "video_qa_status": "needs_review",
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
