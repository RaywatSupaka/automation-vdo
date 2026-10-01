"""Small, thread-safe preview service: one render running, only latest pending."""
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path

from core.subtitle_renderer import SubtitleVideoRenderer


class SubtitlePreviewService:
    def __init__(self, folder, ffmpeg_path="", renderer=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.renderer = renderer or SubtitleVideoRenderer(ffmpeg_path)
        self.lock = threading.RLock()
        self.token = 0
        self.ready_token = 0
        self.pending = None
        self.running = False
        self.signature = ""
        self.error = ""
        self.files = {}
        self.cache = {}
        self.render_ms = 0

    def request(self, text, settings):
        settings = dict(settings)
        font = Path(str(settings.get("font_path") or ""))
        stamp = font.stat().st_mtime_ns if font.is_file() else 0
        signature = hashlib.sha256(json.dumps([text, settings, stamp], sort_keys=True).encode()).hexdigest()
        with self.lock:
            if signature == self.signature and not self.error:
                return self.token
            self.token += 1
            token = self.token
            self.signature, self.error = signature, ""
            cached = self.cache.get(signature)
            if cached and all(path.is_file() for path in cached):
                self.files[token] = cached
                self.ready_token = token
                self.pending = None
                self.render_ms = 0
                self._prune()
                return token
            self.pending = (token, signature, str(text), settings, time.monotonic())
            if not self.running:
                self.running = True
                threading.Thread(target=self._run, name="subtitle-preview", daemon=True).start()
            return token

    def _run(self):
        while True:
            with self.lock:
                request, self.pending = self.pending, None
                if request is None:
                    self.running = False
                    return
            token, signature, text, settings, requested = request
            target = self.folder / f"subtitle_preview_hybrid_{os.getpid()}_{token}.png"
            video = target.with_suffix(".mp4")
            started = time.monotonic()
            try:
                self.renderer.render_preview_image(target, text=text, **settings)
                self.renderer.render_preview_video(video, text=text, **settings)
                with self.lock:
                    self.files[token] = (target, video)
                    self.cache[signature] = (target, video)
                    if token == self.token:
                        self.ready_token = token
                        self.render_ms = round((time.monotonic() - started) * 1000)
                    self._prune()
                logging.getLogger(__name__).info(
                    "SUBTITLE_PREVIEW token=%s queue_ms=%s render_ms=%s result=ready",
                    token, round((started - requested) * 1000), round((time.monotonic() - started) * 1000),
                )
            except Exception as exc:
                with self.lock:
                    if token == self.token:
                        self.error = str(exc)
                target.unlink(missing_ok=True)
                video.unlink(missing_ok=True)
                logging.getLogger(__name__).warning("SUBTITLE_PREVIEW token=%s result=error error=%s", token, exc)

    def _prune(self):
        keep = set(sorted(self.files)[-3:]) | {self.ready_token}
        retained = {path for token, paths in self.files.items() if token in keep for path in paths}
        for token in list(self.files):
            if token not in keep:
                for path in self.files.pop(token):
                    if path not in retained:
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            pass  # A media response may still be reading it on Windows.
        self.cache = {key: paths for key, paths in self.cache.items() if all(path in retained for path in paths)}

    def snapshot(self):
        with self.lock:
            ready = self.ready_token in self.files
            item = f"__subtitle_preview__:{os.getpid()}:{self.ready_token}"
            busy = self.ready_token != self.token and not self.error
            return {
                "preview_token": self.token, "preview_ready_token": self.ready_token,
                "preview_busy": busy, "preview_error": self.error,
                "preview_url": f"/api/desktop/media?item_id={item}&kind=preview" if ready else "",
                "preview_video_url": f"/api/desktop/media?item_id={item}&kind=video" if ready else "",
                "preview_render_ms": self.render_ms,
                "preview_status": "กำลังอัปเดตพรีวิว…" if busy else "พรีวิวจริงพร้อมแล้ว • ฟอนต์และแอนิเมชันเดียวกับวิดีโอ",
            }

    def media(self, item_id, kind):
        with self.lock:
            prefix = f"__subtitle_preview__:{os.getpid()}:"
            if not str(item_id).startswith(prefix):
                raise FileNotFoundError("พรีวิวไม่ใช่ของโปรแกรมรอบนี้")
            token = int(str(item_id)[len(prefix):])
            paths = self.files.get(token)
            if not paths:
                raise FileNotFoundError("พรีวิวรอบนี้หมดอายุแล้ว")
            return paths[1 if kind == "video" else 0]
