"""Create a fresh Product Job and validate the complete subtitle/font render path."""

import argparse
import base64
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import ROOT, load_config
from core.product_manager import ProductManager
from core.secure_store import WindowsCredentialStore
from core.smartsub_online import SmartSubOnlineClient
from core.subtitle_renderer import SubtitleVideoRenderer


def as_data_url(path):
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-job", default="JOB-20260825-587C75")
    args = parser.parse_args()
    cfg = load_config()
    products = ProductManager(ROOT)
    source_folder = products.root / args.source_job
    source = json.loads((source_folder / "job.json").read_text(encoding="utf-8"))
    credential = WindowsCredentialStore("SmartPostAI/CatfufuSmartSubOnlineSOD").load()
    if not credential:
        raise RuntimeError("เครื่องนี้ยังไม่มี SOD สำหรับทดสอบ Subtitle API")

    product = {key: source.get(key, "") for key in (
        "product_id", "shop_id", "product_name", "product_url", "posting_product_url",
        "affiliate_url", "resolved_product_url", "product_source", "link_status", "price",
        "commission", "description",
    )}
    job, _ = products.import_product(product, force_new=True)
    job_id = job["id"]
    print(f"STEP 1/7 PRODUCT {job_id}", flush=True)
    products.attach_images(job_id, sorted((source_folder / "original").glob("*")))

    hashtags_path = source_folder / "captions" / "hashtags.txt"
    ai_result = {
        "job_id": job_id,
        "caption_short": source.get("caption", ""),
        "hashtags": hashtags_path.read_text(encoding="utf-8").split() if hashtags_path.exists() else [],
        "video_prompt": (source_folder / "prompts" / "google_flow_prompt.txt").read_text(encoding="utf-8") if (source_folder / "prompts" / "google_flow_prompt.txt").exists() else "",
        "spoken_script": source.get("spoken_script_raw") or source.get("spoken_script", ""),
        "spoken_script_short": source.get("spoken_script_short", ""),
        "pronunciation_notes": source.get("pronunciation_notes", {}),
        "warnings": source.get("warnings", []),
        "image_prompts": source.get("image_prompts", []),
        "flow_shot_prompts": source.get("flow_shot_prompts", []),
        "flow_gui_design": source.get("flow_gui_design", []),
        "editing_overlay_plan": source.get("editing_overlay_plan", []),
        "spoken_script_segments": source.get("spoken_script_segments", []),
        "generated_images": [as_data_url(path) for path in sorted((source_folder / "generated").glob("*")) if path.is_file()],
    }
    products.apply_ai_result(ai_result)
    products.approve_ai_result(job_id)
    print("STEP 2/7 AI RESULT + 3 IMAGES", flush=True)

    voice_source = source_folder / str(source.get("voice_path"))
    products.save_voice_result(job_id, voice_source, "E2E-REUSED-VOICE", source.get("voice_reference_id", ""), "E2E-VOICE")
    video_relative = source.get("video_without_subtitle_path") or source.get("video_path")
    video_source = source_folder / str(video_relative)
    products.attach_video(job_id, video_source)
    products.set_subtitle_requested(job_id, True)
    print("STEP 3/7 VOICE + VIDEO READY", flush=True)

    folder = products.root / job_id
    audio = folder / "audio" / f"voiceover{voice_source.suffix.lower()}"
    wav = folder / "audio" / "subtitle_source.wav"
    client = SmartSubOnlineClient(credential, cfg.get("subtitle_api_base_url"))
    client.prepare_wav(audio, wav, cfg.get("ffmpeg_path", ""))
    print("STEP 4/7 WAV READY", flush=True)
    created = client.create_job(wav, "th", str(uuid.uuid4()))
    external_job_id = str(created.get("jobId") or created.get("job_id"))
    products.mark_subtitle_queued(job_id, external_job_id, "th")
    print(f"STEP 5/7 API JOB {external_job_id}", flush=True)
    api_result = client.wait_until_done(external_job_id, on_status=lambda status, _: print(f"  API {status}", flush=True))
    job, paths = products.save_subtitle_result(job_id, external_job_id, api_result, 3)
    print("STEP 6/7 SRT READY", flush=True)

    style = {
        "font_name": "Prompt",
        "font_path": str(ROOT / "assets" / "fonts" / "smartsubai" / "Prompt-ExtraBold.ttf"),
        "font_size": 22,
        "text_color": "#FFFFFF",
        "outline_color": "#16213E",
        "outline_width": 3,
        "background_enabled": True,
        "background_color": "#000000",
        "background_opacity": 0.42,
        "position": "bottom",
        "margin_v": 72,
    }
    subtitle = folder / paths["subtitle.srt"]
    source_video = folder / "videos" / f"final{video_source.suffix.lower()}"
    output = folder / "videos" / "final_with_subtitles.mp4"
    rendered = SubtitleVideoRenderer(cfg.get("ffmpeg_path", "")).render(source_video, subtitle, output, **style)
    stored_style = dict(style)
    stored_style["font_path"] = "assets/fonts/smartsubai/Prompt-ExtraBold.ttf"
    job = products.save_subtitled_video(job_id, output, source_video, subtitle, stored_style)
    cues = sum(1 for line in subtitle.read_text(encoding="utf-8-sig").splitlines() if line.isdigit())
    summary = {
        "tested_at": datetime.now().isoformat(timespec="seconds"),
        "source_job": args.source_job,
        "job_id": job_id,
        "external_subtitle_job_id": external_job_id,
        "font": "Prompt ExtraBold (SmartSubAI)",
        "bundled_font_count": len(list((ROOT / "assets" / "fonts" / "smartsubai").glob("*.ttf"))),
        "syllables_per_cue": 3,
        "cue_count": cues,
        "subtitle": str(subtitle),
        "video": str(output),
        "video_bytes": output.stat().st_size,
        "status": "passed" if job.get("subtitle_video_status") == "ready" else "failed",
    }
    (folder / "e2e_font_test_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STEP 7/7 VIDEO READY", flush=True)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
