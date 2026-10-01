"""Reusable silent presenters. No voice synthesis or lip-sync in this module."""
import base64
from core.flow_settings import flow_settings
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image
from core.atomic_json import AtomicJsonFile, JsonPersistenceError
from core.cancellable_process import check_cancelled, hidden_process_kwargs
from core.render_backend import run_render as run_cancellable
from core.video_logo import locate_ffmpeg

STYLES = {"realistic": "photorealistic studio portrait", "anime": "2D anime illustration",
          "3d": "stylized 3D character", "mascot": "friendly cartoon mascot"}
MOTIONS = ["Gently moving lips as if explaining, natural blinking and small head movements.",
           "Gently moving lips as if speaking, small nods and subtle friendly expressions.",
           "Gently moving lips as if speaking, occasional restrained hand gestures within the frame."]


def presenter_settings(value):
    value = value or {}
    if not isinstance(value, dict):
        raise ValueError("ค่าผู้บรรยายไม่ถูกต้อง")
    if not value.get("enabled"):
        return {"enabled": False}
    ident = str(value.get("id") or "")
    if not re.fullmatch(r"PRESENTER-[A-F0-9]{12}", ident):
        raise ValueError("กรุณาเลือกตัวละครจากคลัง")
    result = {"enabled": True, "id": ident}
    for key, default, low, high in (("x", 95, 0, 100), ("y", 95, 0, 100),
                                   ("size", 32, 15, 60), ("similarity", .18, .01, .5),
                                   ("blend", .08, 0, .3)):
        number = float(value.get(key, default))
        if not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f"ค่าตัวละคร {key} ต้องอยู่ระหว่าง {low}–{high}")
        result[key] = number
    timing = str(value.get("timing") or "all")
    if timing not in {"all", "intro_outro"}:
        raise ValueError("ช่วงแสดงตัวละครไม่ถูกต้อง")
    result["timing"] = timing
    return result


def screen_quality(image, color):
    """Conservative edge check, not a claim of perfect matting or identity."""
    im = image.convert("RGB").resize((80, 120))
    values = [im.getpixel((x, y)) for y in range(120) for x in range(80)
              if x < 4 or x >= 76 or y < 4 or y >= 116]
    channel = 1 if color == "green" else 2
    good = sum(pixel[channel] > 80 and pixel[channel] > max(pixel[i] for i in range(3) if i != channel) * 1.35
               for pixel in values)
    ratio = good / len(values)
    return {"edge_screen_ratio": round(ratio, 3), "passed": ratio >= .8,
            "note": "ตรวจขอบพื้นสีเท่านั้น ต้องดูพรีวิวผม มือ และเสื้อด้วย"}


class PresenterManager:
    def __init__(self, root, ffmpeg_path=""):
        self.root = Path(root) / "workspace" / "presenters"
        self.ffmpeg_path = ffmpeg_path

    def folder(self, ident):
        if not re.fullmatch(r"PRESENTER-[A-F0-9]{12}", str(ident)):
            raise ValueError("รหัสตัวละครไม่ถูกต้อง")
        return self.root / ident

    def store(self, ident):
        return AtomicJsonFile(self.folder(ident) / "presenter.json")

    def get(self, ident):
        return self.store(ident).read()

    def update(self, ident, **changes):
        def edit(job):
            job.update(changes, updated_at=datetime.now().isoformat(timespec="seconds"))
            return job
        return self.store(ident).update(edit)

    def list_jobs(self):
        if not self.root.exists():
            return []
        return sorted((self.get(p.parent.name) for p in self.root.glob("PRESENTER-*/presenter.json")),
                      key=lambda j: j.get("created_at", ""), reverse=True)

    def defaults(self):
        """User preference only; existing Job/queue snapshots never read this."""
        return AtomicJsonFile(self.root / "defaults.json").read(default={"enabled": False})

    def set_library_state(self, ident, state):
        """Recoverable library removal only: never unlink media or change job snapshots."""
        if state not in {"visible", "hidden", "trash"}:
            raise ValueError("สถานะคลังไม่ถูกต้อง")
        # Validate the ID even when a caller does not come through the desktop adapter.
        self.folder(ident)
        if state == "trash":
            references = self.library_references(ident)
            if references:
                raise ValueError("ตัวละครถูกใช้อยู่ • ใช้ซ่อนจากคลังแทน: " + ", ".join(references[:5]))
        def edit(job):
            if not job or job.get("id") != ident:
                raise ValueError("ไม่พบตัวละคร")
            if job.get("status") == "running":
                raise ValueError("หยุดงานตัวละครก่อนจัดการคลัง")
            if state == "trash" and self.defaults().get("id") == ident:
                raise ValueError("ตัวนี้เป็นผู้บรรยายเริ่มต้น • เปลี่ยนตัวละครในหน้าตั้งค่าก่อน หรือใช้ซ่อนแทน")
            job.update(library_state=state, updated_at=datetime.now().isoformat(timespec="seconds"))
            return job
        try:
            return self.store(ident).update(edit)
        except FileNotFoundError as exc:
            raise ValueError("ไม่พบตัวละคร") from exc

    def library_references(self, ident):
        """Inspect only durable job/queue manifests; no logs, media, or provider calls."""
        self.folder(ident)
        workspace = self.root.parent
        paths = [workspace / "story_batch_queue.json"]
        for section in ("products", "stories"):
            paths.extend((workspace / section).glob("*/job.json"))
        paths.extend((workspace / "drama_series").glob("*/series.json"))
        def references(value):
            if isinstance(value, dict):
                return any(references(v) for v in value.values())
            if isinstance(value, list):
                return any(references(v) for v in value)
            return value == ident
        found = []
        for path in paths:
            if not path.exists():
                continue
            try:
                if references(AtomicJsonFile(path).read()):
                    found.append(str(path.relative_to(workspace)))
            except (OSError, ValueError, JsonPersistenceError) as exc:
                raise ValueError("ตรวจการใช้งานตัวละครไม่ครบ • ใช้ซ่อนแทน และตรวจไฟล์ " + str(path.relative_to(workspace))) from exc
        return found

    def save_defaults(self, value):
        selected = presenter_settings(value)
        if not selected["enabled"]:
            raise ValueError("เลือกตัวละครที่พร้อมใช้ก่อนบันทึก")
        self.assets(selected)
        if self.get(selected["id"]).get("library_state") == "trash":
            raise ValueError("กู้คืนตัวละครจากถังขยะก่อนเลือกใช้งานใหม่")
        if not (self.folder(selected["id"]) / "exports/presenter_green_screen.mp4").is_file():
            raise ValueError("ไฟล์ผู้บรรยายรวมไม่พร้อม • ตรวจคลังก่อนบันทึก")
        AtomicJsonFile(self.root / "defaults.json").write(selected)
        return selected

    def defaults_state(self):
        selected = self.defaults()
        try:
            assets = self.assets(selected)
            if assets and not (self.folder(selected["id"]) / "exports/presenter_green_screen.mp4").is_file():
                raise ValueError("ไฟล์ผู้บรรยายรวมสูญหาย • เลือกตัวละครใหม่ ไม่สร้างซ้ำเอง")
            return {"settings": selected, "available": bool(assets),
                    "name": assets[0]["name"] if assets else "", "error": ""}
        except (ValueError, OSError, KeyError, JsonPersistenceError) as exc:
            return {"settings": selected, "available": False, "name": "", "error": str(exc)}

    def create(self, name, description, provider="chatgpt", style="realistic", screen="green", reference=None, consent=False, review=False):
        name, description = str(name).strip(), str(description).strip()
        if not 1 <= len(name) <= 100 or not 1 <= len(description) <= 4000:
            raise ValueError("ใส่ชื่อตัวละครและคำบรรยาย (ไม่เกิน 4,000 ตัวอักษร)")
        if provider not in {"chatgpt", "gemini"} or style not in STYLES or screen not in {"green", "blue"}:
            raise ValueError("รูปแบบตัวละครหรือผู้สร้างภาพไม่ถูกต้อง")
        if reference and consent is not True:
            raise ValueError("กรุณายืนยันสิทธิ์ใช้รูปอ้างอิง")
        prepared = None
        if reference:
            with Image.open(reference) as img:
                if img.width < 128 or img.height < 128:
                    raise ValueError("รูปอ้างอิงเล็กเกินไป")
                prepared = img.convert("RGB")
                prepared.thumbnail((2048, 2048))
        ident = "PRESENTER-" + uuid.uuid4().hex[:12].upper()
        folder = self.folder(ident)
        for child in ("source", "generated", "clips", "logs", "exports"):
            (folder / child).mkdir(parents=True, exist_ok=True)
        if prepared:
            prepared.save(folder / "source/reference.png")
        job = {"id": ident, "name": name, "description": description, "image_ai_provider": provider,
               "ai_web_model": "auto", "style": style, "screen": screen, "review_image": bool(review),
               "source_images": ["source/reference.png"] if prepared else [], "image": "", "clips": {},
               "status": "draft", "stage": "draft", "intents": {}, "error": "", "run_id": "",
               "created_at": datetime.now().isoformat(timespec="seconds")}
        self.store(ident).write(job)
        return job

    def image_prompt(self, job):
        start = ("Create one new portrait using the attached reference; keep the same identity, face and clothing."
                 if job["source_images"] else "Create one new character portrait from this text; no reference image is required.")
        return (f"{start}\n{job['description']}\nStyle: {STYLES[job['style']]}. Vertical 9:16, waist-up, facing camera, "
                "mouth visible, arms and hands within frame with generous clear margins. Even studio lighting. "
                f"Solid flat saturated {job['screen']} chroma-key background, edge to edge, no gradient, no shadows on background. "
                f"Avoid {job['screen']} clothing or accessories. No text, collage or watermark. Return one generated image now.")

    def plugin_request(self, ident):
        job = self.get(ident)
        return {"mode": "presenter", "job": job, "prompt": self.image_prompt(job),
                "request": {"image_count": 1}, "checkpoint_images": []}

    def claim_image(self, ident, run_id):
        def claim(job):
            if job.get("run_id") != run_id or job.get("status") != "running":
                raise ValueError("ผลตัวละครไม่ใช่รอบที่กำลังทำ")
            if job.get("image") or job["intents"].get("image"):
                raise ValueError("ส่งสร้างภาพนี้แล้ว • หยุดเพื่อป้องกันส่งซ้ำ")
            job["intents"]["image"] = run_id
            return job
        self.store(ident).update(claim)

    def save_image(self, ident, run_id, data):
        if not isinstance(data, str) or not data.startswith("data:image/") or len(data) > 32 * 1024 * 1024:
            raise ValueError("ข้อมูลรูปตัวละครไม่ถูกต้อง")
        raw = base64.b64decode(data.split(",", 1)[1], validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            if image.width < 256 or image.height < 400 or not .45 <= image.width / image.height <= .72:
                raise ValueError("ภาพตัวละครต้องแนวตั้ง 9:16 และมีขนาดเพียงพอ")
            rgb = image.convert("RGB")
        store = self.store(ident)
        with store.locked():
            job = store.read_unlocked()
            if job.get("run_id") != run_id or job.get("status") != "running" or job["intents"].get("image") != run_id:
                raise ValueError("ผลภาพมาจากรอบเก่าหรืองานยกเลิก")
            if job.get("image"):
                return job
            path = self.folder(ident) / "generated/character.png"
            temporary = path.with_suffix(".saving.png")
            rgb.save(temporary); os.replace(temporary, path)
            quality = screen_quality(rgb, job["screen"])
            job.update(image="generated/character.png", image_quality=quality, stage="image_ready",
                       status="image_review" if job["review_image"] or not quality["passed"] else "running")
            store.write_unlocked(job)
            return job

    def flow_package(self, ident, shot_index=0):
        job = self.get(ident); index = int(shot_index)
        if job.get("status") in {"cancelled", "error"}:
            raise ValueError("งานตัวละครหยุดแล้ว • ไม่เริ่ม Flow เพิ่ม")
        if not 1 <= index <= 3 or not job.get("image"):
            raise ValueError("ภาพหลักหรือลำดับคลิปยังไม่พร้อม")
        if not (self.folder(ident) / job["image"]).is_file():
            raise ValueError("ไฟล์ภาพหลักหายไป ไม่สร้างทดแทนโดยอัตโนมัติ")
        return {"job_id": ident, "mode": "presenter", "shot_index": index, "shot_count": 3,
                "flow_settings": flow_settings(job.get("flow_settings")),
                "product_name": job["name"], "caption": "ผู้บรรยายเคลื่อนไหว • ไม่ซิงก์ปาก", "hashtags": "", "warnings": [],
                "image_files": [job["image"]], "video_prompt":
                f"Create exactly one playable vertical 9:16 video from the attached character portrait. {MOTIONS[index-1]} "
                "No specific dialogue is needed. Preserve the same face, clothes, proportions and framing. "
                "Static locked camera, no cuts, no zoom, no walking. Keep head and hands within frame. "
                f"Keep the entire background solid flat saturated {job['screen']} throughout, no gradients, scenery, text, shadows or objects. "
                "Gentle natural movement only. Begin and end in a relaxed front-facing pose. Generate the video now."}

    def save_clip(self, ident, index, source, run_id):
        renderer = PresenterRenderer(self.ffmpeg_path)
        info = renderer.info(source)
        if not 1 <= int(index) <= 3 or info["duration"] < 1 or not .45 <= info["width"] / info["height"] <= .72:
            raise ValueError("คลิปผู้บรรยายไม่ใช่วิดีโอแนวตั้งที่สมบูรณ์")
        quality = renderer.inspect_screen(source, self.get(ident)["screen"])
        digest = hashlib.sha256()
        with Path(source).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        fingerprint = digest.hexdigest()
        store = self.store(ident)
        with store.locked():
            job = store.read_unlocked()
            if job.get("run_id") != run_id or job.get("status") != "running":
                raise ValueError("คลิปมาจากรอบเก่าหรืองานยกเลิก")
            if any(str(other) != str(index) and clip.get("sha256") == fingerprint for other, clip in job["clips"].items()):
                raise ValueError("ไฟล์นี้ซ้ำกับคลิปผู้บรรยายที่บันทึกแล้ว • หยุดตรวจ ไม่สร้างซ้ำ")
            relative = f"clips/take_{int(index):02d}.mp4"
            target = self.folder(ident) / relative
            temporary = target.with_suffix(".saving.mp4")
            shutil.copyfile(source, temporary); os.replace(temporary, target)
            job["clips"][str(index)] = {"path": relative, **info, "quality": quality, "sha256": fingerprint}
            job.update(stage=f"clip_{index}_saved")
            if not quality["passed"]:
                job.update(status="clip_review", error="พื้นสีไม่สม่ำเสมอ • ตรวจพรีวิวก่อนนำไปใช้")
            store.write_unlocked(job)
            return job

    def assets(self, selection):
        settings = presenter_settings(selection)
        if not settings["enabled"]:
            return None
        job = self.get(settings["id"])
        if job["status"] != "ready" or len(job["clips"]) != 3:
            raise ValueError("ตัวละครนี้ยังไม่พร้อมครบ 3 คลิป")
        clips = [self.folder(job["id"]) / job["clips"][str(i)]["path"] for i in range(1, 4)]
        if any(not p.is_file() for p in clips):
            raise ValueError("ไฟล์คลิปตัวละครหาย • ไม่เรียก AI สร้างซ้ำ")
        if not (self.folder(job["id"]) / "exports/presenter_green_screen.mp4").is_file():
            raise ValueError("ไฟล์ผู้บรรยายรวมไม่พร้อม • ตรวจคลังก่อนเริ่มงาน")
        return job, clips, settings


class PresenterRenderer:
    def __init__(self, ffmpeg_path=""):
        self.ffmpeg = locate_ffmpeg(ffmpeg_path)
        self.ffprobe = self.ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")

    def info(self, path):
        result = subprocess.run([str(self.ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                capture_output=True, text=True, timeout=30, **hidden_process_kwargs())
        if result.returncode:
            raise ValueError("อ่านวิดีโอผู้บรรยายไม่ได้")
        data = json.loads(result.stdout); video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
        if not video:
            raise ValueError("ไม่พบภาพวิดีโอในไฟล์")
        duration = float(data["format"].get("duration", 0))
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("ความยาววิดีโอไม่ถูกต้อง")
        return {"duration": duration, "width": int(video["width"]), "height": int(video["height"])}

    def inspect_screen(self, path, color):
        info = self.info(path); checks = []
        for fraction in (.1, .5, .9):
            result = subprocess.run([str(self.ffmpeg), "-v", "error", "-ss", str(info["duration"] * fraction),
                                     "-i", str(path), "-frames:v", "1", "-vf", "scale=160:240", "-f", "image2pipe", "-vcodec", "png", "-"],
                                    capture_output=True, timeout=30, **hidden_process_kwargs())
            if result.returncode or not result.stdout:
                raise ValueError("ตรวจเฟรมพื้นเขียวไม่สำเร็จ")
            with Image.open(io.BytesIO(result.stdout)) as image:
                checks.append(screen_quality(image, color))
        return {"passed": all(c["passed"] for c in checks), "samples": checks}

    def _run(self, arguments, output, cancel_event=None):
        check_cancelled(cancel_event)
        output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(f".{output.stem}.{uuid.uuid4().hex[:8]}.mp4")
        try:
            result = run_cancellable([str(self.ffmpeg), "-y", *arguments, "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                                      "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", str(temp)],
                                     cancel_event=cancel_event, timeout=3600)
            if result.returncode:
                raise RuntimeError("ประกอบผู้บรรยายไม่สำเร็จ: " + result.stderr[-700:])
            self.info(temp); check_cancelled(cancel_event); os.replace(temp, output)
        finally:
            temp.unlink(missing_ok=True)
        return output

    def join(self, clips, output, cancel_event=None, color="green"):
        if len(clips) != 3:
            raise ValueError("ต้องมีคลิปผู้บรรยาย 3 คลิป")
        args, filters = [], []
        for i, path in enumerate(clips):
            self.info(path); args += ["-i", str(path)]
            key = "0x00ff00" if color == "green" else "0x0000ff"
            filters.append(f"[{i}:v]scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color={key},fps=30,setsar=1,setpts=PTS-STARTPTS[v{i}]")
        filters.append("[v0][v1][v2]concat=n=3:v=1:a=0[v]")
        return self._run([*args, "-filter_complex", ";".join(filters), "-map", "[v]", "-an"], output, cancel_event)

    def overlay(self, source, presenter, output, selection, color, cancel_event=None):
        settings = presenter_settings(selection); info = self.info(source)
        size = max(2, round(info["width"] * settings["size"] / 100 / 2) * 2)
        key = "0x00ff00" if color == "green" else "0x0000ff"
        x, y = settings["x"] / 100, settings["y"] / 100
        timing = "" if settings["timing"] == "all" else f":enable='lt(t,5)+gte(t,{max(5,info['duration']-5):.3f})'"
        filters = (f"[1:v]setpts=PTS-STARTPTS,chromakey={key}:{settings['similarity']}:{settings['blend']},"
                   f"despill=type={color},scale={size}:-2,format=rgba[person];"
                   f"[0:v]setpts=PTS-STARTPTS[base];[base][person]overlay=(W-w)*{x}:(H-h)*{y}:shortest=1{timing}[v]")
        return self._run(["-i", str(source), "-stream_loop", "-1", "-i", str(presenter),
                          "-filter_complex", filters, "-map", "[v]", "-map", "0:a?", "-c:a", "aac",
                          "-t", str(info["duration"])], output, cancel_event)


def apply_presenter(root, source, output, selection, ffmpeg_path="", cancel_event=None):
    manager = PresenterManager(root, ffmpeg_path)
    assets = manager.assets(selection)
    if not assets:
        return Path(source), {"enabled": False}
    job, clips, settings = assets
    loop = manager.folder(job["id"]) / "exports/presenter_green_screen.mp4"
    if not loop.is_file():
        raise ValueError("ไฟล์ผู้บรรยายรวมยังไม่พร้อม")
    target = PresenterRenderer(ffmpeg_path).overlay(source, loop, output, settings, job["screen"], cancel_event)
    return target, {**settings, "lip_sync": False, "audio_source": "main_video", "screen": job["screen"]}
