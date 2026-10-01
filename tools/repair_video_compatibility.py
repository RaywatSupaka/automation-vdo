import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.config import ROOT, load_config
from core.video_library import VideoLibrary


def probe(ffprobe, path):
    result = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,profile,pix_fmt", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-600:])
    payload = json.loads(result.stdout)
    video = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "audio"), {})
    return {
        "duration": float((payload.get("format") or {}).get("duration") or 0),
        "codec": video.get("codec_name"),
        "profile": video.get("profile"),
        "pix_fmt": video.get("pix_fmt"),
        "audio_codec": audio.get("codec_name"),
    }


def compatible(info):
    return info.get("codec") == "h264" and info.get("pix_fmt") == "yuv420p" and info.get("audio_codec") in {None, "aac"}


def repair(ffmpeg, ffprobe, item):
    source = Path(item["path"])
    before = probe(ffprobe, source)
    if compatible(before):
        return {"job": item["job_id"], "status": "already_compatible", "before": before, "after": before}
    temporary = source.with_name(f".{source.stem}.windows-compatible.rendering.mp4")
    command = [
        str(ffmpeg), "-y", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.1",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(temporary),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7200)
        if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError("แปลงวิดีโอไม่สำเร็จ: " + result.stderr.strip()[-800:])
        after = probe(ffprobe, temporary)
        if not compatible(after):
            raise RuntimeError(f"ไฟล์ใหม่ยังไม่รองรับ Windows: {after}")
        if before["duration"] and abs(after["duration"] - before["duration"]) > 0.25:
            raise RuntimeError("ความยาวไฟล์ใหม่ไม่ตรงกับต้นฉบับ")
        manifest_path = Path(item["manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        final_path = source
        try:
            os.replace(temporary, source)
        except PermissionError:
            # Windows Media Player/Codex preview may keep the old file open.
            # Publish the verified file under a new main name and repoint the
            # manifest instead of forcing or deleting the locked source.
            final_path = source.with_name(f"{source.stem}_windows.mp4")
            os.replace(temporary, final_path)
            manifest["video_path"] = str(final_path.relative_to(manifest_path.parent))
        manifest["media_compatibility"] = {
            "windows_media_player": True,
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "audio_codec": after.get("audio_codec"),
            "output": str(final_path.relative_to(manifest_path.parent)),
            "verified_at": datetime.now().isoformat(timespec="seconds"),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"job": item["job_id"], "status": "repaired", "output": str(final_path), "before": before, "after": after}
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", action="append", default=[])
    args = parser.parse_args()
    cfg = load_config()
    ffmpeg = Path(str(cfg.get("ffmpeg_path") or ""))
    ffprobe = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise SystemExit("ไม่พบ FFmpeg/FFprobe")
    items = VideoLibrary(ROOT).list_items()
    if args.job:
        selected = set(args.job)
        items = [item for item in items if item["job_id"] in selected]
    failures = []
    for index, item in enumerate(items, 1):
        print(f"[{index}/{len(items)}] {item['job_id']} • ตรวจสอบ {Path(item['path']).name}", flush=True)
        try:
            result = repair(ffmpeg, ffprobe, item)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            failures.append({"job": item["job_id"], "error": str(exc)})
            print(json.dumps(failures[-1], ensure_ascii=False), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
