"""Render every SmartSubAI-derived theme/animation and validate all audio modes."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.audio_mixer import AudioMixer
from core.config import ROOT, load_config
from core.font_manager import FontManager
from core.subtitle_renderer import SubtitleVideoRenderer
from core.subtitle_styles import SUBTITLE_ANIMATIONS, SUBTITLE_THEMES


def main():
    cfg = load_config()
    ffmpeg = str(cfg.get("ffmpeg_path") or "")
    source_job = ROOT / "workspace" / "products" / "JOB-20260826-AAC2D9"
    target = ROOT / "workspace" / "qa_media_features"
    target.mkdir(parents=True, exist_ok=True)
    short_source = target / "source_2s.mp4"
    subprocess.run([ffmpeg, "-y", "-i", str(source_job / "videos" / "final.mp4"), "-t", "2", "-c", "copy", str(short_source)], check=True, capture_output=True)
    srt = target / "thai_vowel_test.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,900\nเก็บบรรยากาศให้น่าประทับใจ\n", encoding="utf-8")
    fonts = FontManager(ROOT).scan()
    font_by_name = {record.path.name.lower(): record for record in fonts}
    animations = list(SUBTITLE_ANIMATIONS)
    renderer = SubtitleVideoRenderer(ffmpeg)
    theme_results = []
    for index, (key, theme) in enumerate(SUBTITLE_THEMES.items()):
        record = font_by_name[theme["font_file"].lower()]
        animation = animations[index % len(animations)]
        output = target / f"theme_{index + 1:02d}_{key}_{animation}.mp4"
        renderer.render(
            short_source, srt, output, font_name=record.family, font_path=record.path,
            font_size=theme["font_size"], text_color=theme["text_color"], highlight_color="#FACC15",
            outline_color=theme["outline_color"], outline_width=theme["outline_width"],
            background_enabled=theme["background_enabled"], background_color=theme["background_color"],
            background_opacity=theme["background_opacity"], position="bottom", margin_v=52,
            animation=animation,
        )
        theme_results.append({"theme": key, "animation": animation, "bytes": output.stat().st_size})

    mixer = AudioMixer(ffmpeg)
    backgrounds = mixer.scan_audio(ROOT / "assets" / "audio" / "background")
    effects = mixer.scan_audio(ROOT / "assets" / "audio" / "sfx")
    audio_results = []
    for mode in ("auto", "random", "selected"):
        output = target / f"audio_{mode}.mp4"
        plan = mixer.render(
            short_source, output, background_files=backgrounds, background_mode=mode,
            background_volume=0.12, sfx_files=effects, sfx_mode=mode,
            sfx_volume=0.22, cue_times=[1.0], min_sfx_interval=6, max_sfx_count=1,
            seed=f"qa-{mode}",
        )
        audio_results.append({"mode": mode, "music": len(plan["music_plan"]), "sfx": len(plan["sfx_events"]), "bytes": output.stat().st_size})
    summary = {
        "themes_passed": len(theme_results), "animations_covered": sorted({item["animation"] for item in theme_results}),
        "theme_results": theme_results, "audio_modes_passed": len(audio_results), "audio_results": audio_results,
    }
    (target / "validation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
