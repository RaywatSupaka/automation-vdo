"""Native-only update UI bridge. Remote web pages cannot invoke these methods."""
import json
import hashlib
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.request import Request, urlopen
from core.app_updates import MANIFEST_URL, RESOURCE_ROOT, download, safe_url, verify_release, version


class UpdateApi:
    def __init__(self, host):
        self._host = host
        self._window = None
        self._envelope = None
        self._lock = threading.Lock()
        self._install_lock = threading.Lock()
        self._install_started = False
        self._downloaded = {}
        self._progress = {"busy": False, "message": ""}

    def update_check(self):
        local = {}
        try:
            local = json.loads((RESOURCE_ROOT / "customer-release.json").read_text())
            with urlopen(MANIFEST_URL, timeout=12) as response:
                safe_url(response.url)
                raw = response.read(128 * 1024 + 1)
                if len(raw) > 128 * 1024:
                    raise ValueError("ข้อมูลอัปเดตมีขนาดผิดปกติ")
                envelope = json.loads(raw)
            release = verify_release(envelope)
            self._envelope = envelope
            return {"ok": True, "local": local, "release": release,
                    "app_update": version(release["version"]) > version(local["version"])}
        except Exception as exc:
            return {"ok": False, "local": local, "error": "ยังตรวจสอบอัปเดตไม่ได้ • " + str(exc)[:160]}

    def update_bundled_extension(self):
        folder = RESOURCE_ROOT / "extension-download"
        if not folder.is_dir():
            return {"ok": False, "error": "ใช้ไฟล์ Extension ZIP ที่อยู่ข้างตัวติดตั้ง"}
        os.startfile(str(folder))
        return {"ok": True, "message": "เปิดโฟลเดอร์ Extension ที่มากับตัวติดตั้งแล้ว • แตก ZIP และติดตั้งใน Chrome"}

    def update_progress(self):
        return dict(self._progress)

    def update_download(self, kind):
        if kind not in ("patch", "extension") or not self._envelope:
            return {"ok": False, "error": "กรุณาตรวจสอบอัปเดตก่อน"}
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "error": "กำลังดาวน์โหลดอยู่"}
        try:
            release = verify_release(self._envelope)
            asset = release.get(kind)
            if not asset:
                raise ValueError("รุ่นนี้ไม่มีไฟล์ประเภทนี้")
            target = Path(os.environ["LOCALAPPDATA"]) / "SmartFlowAI/updates/downloads" / (asset["sha256"] + ".zip")
            self._progress = {"busy": True, "message": "กำลังดาวน์โหลด", "percent": 0}
            download(asset, target, lambda count, total: self._progress.update(percent=round(count * 100 / total)))
            self._downloaded[kind] = target
            if kind == "extension":
                subprocess.Popen(["explorer.exe", "/select,", str(target)])
            return {"ok": True, "path": str(target), "message": "ดาวน์โหลดแล้ว • ยังต้องเปลี่ยนไฟล์และ Reload Extension" if kind == "extension" else "ดาวน์โหลดแพตช์แล้ว"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            self._progress["busy"] = False
            self._lock.release()

    def update_install(self):
        if not self._install_lock.acquire(blocking=False):
            return {"ok": False, "error": "กำลังเตรียมอัปเดตอยู่ กรุณารอ"}
        try:
            if self._install_started:
                return {"ok": False, "error": "เริ่มตัวอัปเดตแล้ว กรุณารอเปิดโปรแกรมใหม่"}
            return self._install_once()
        finally:
            self._install_lock.release()

    def _update_barrier(self, payload):
        request = Request(self._host.base_url + "/api/desktop/action", data=json.dumps({"action": "prepare_app_update", "payload": payload}).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=12) as response:
            return json.load(response)

    def _install_once(self):
        if not getattr(sys, "frozen", False) or "patch" not in self._downloaded or not self._envelope:
            return {"ok": False, "error": "ต้องดาวน์โหลดแพตช์จากชุดติดตั้งก่อน"}
        barrier_nonce = ""
        try:
            envelope = json.loads(json.dumps(self._envelope))
            release = verify_release(envelope)
            local = json.loads((RESOURCE_ROOT / "customer-release.json").read_text())
            if version(release["version"]) <= version(local["version"]):
                raise ValueError("ไม่มีโปรแกรมรุ่นใหม่ให้ติดตั้ง")
            if local["version"] not in release.get("supported_from", []):
                raise ValueError("แพตช์ไม่รองรับรุ่นที่ติดตั้ง กรุณาใช้ตัวติดตั้งเต็ม")
            source = RESOURCE_ROOT / "SmartFlow Updater.exe"
            if not source.is_file():
                raise ValueError("ไม่พบตัวอัปเดต กรุณาใช้ตัวติดตั้งเต็ม")
            patch = self._downloaded["patch"]
            asset = release.get("patch") or {}
            with patch.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if patch.stat().st_size != asset.get("size") or digest != asset.get("sha256"):
                raise ValueError("แพตช์ที่ดาวน์โหลดไม่ตรงกับรุ่นที่เลือก กรุณาดาวน์โหลดใหม่")
            pending = Path(os.environ["LOCALAPPDATA"]) / "SmartFlowAI/updates/pending"
            pending.mkdir(parents=True, exist_ok=True)
            envelope_path = pending / "release.json"
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
            updater = pending / "SmartFlow Updater.exe"
            shutil.copy2(source, updater)
            result = self._update_barrier({})
            if not result.get("ok"):
                raise ValueError(result.get("error") or "ยังมีงานอยู่ กรุณารอให้จบก่อน")
            barrier_nonce = str(result.get("nonce") or "")
            subprocess.Popen([str(updater), "--root", str(RESOURCE_ROOT), "--release", str(envelope_path),
                              "--patch", str(patch), "--wait-pid", str(os.getpid()),
                              "--engine-pid", str(self._host.engine_pid or 0)], creationflags=subprocess.CREATE_NO_WINDOW)
            self._install_started = True
            threading.Timer(0.4, self._window.destroy).start()
            return {"ok": True, "message": "กำลังปิดโปรแกรมเพื่อติดตั้ง • คิวเดิมถูกพักไว้"}
        except Exception as exc:
            if barrier_nonce and not self._install_started:
                try:
                    released = self._update_barrier({"cancel": True, "nonce": barrier_nonce})
                    if not released.get("ok"):
                        raise ValueError("Update barrier release not confirmed")
                except Exception:
                    return {"ok": False, "error": "เปิดตัวอัปเดตไม่สำเร็จและยังยืนยันการปลดสถานะไม่ได้ • กรุณาเปิดโปรแกรมใหม่ คิวเดิมยังพักไว้"}
            return {"ok": False, "error": str(exc)}
