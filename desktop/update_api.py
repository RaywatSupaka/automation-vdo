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
from core.extension_updater import installed_extension_id, install_archive, verify_bundled_package


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
            return {"ok": True, "path": str(target), "message": "ดาวน์โหลด Extension แล้ว" if kind == "extension" else "ดาวน์โหลดแพตช์แล้ว"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            self._progress["busy"] = False
            self._lock.release()

    def update_install_extension(self):
        """Apply a signed ZIP to the same unpacked path and request one reload."""
        if not self._install_lock.acquire(blocking=False):
            return {"ok": False, "error": "กำลังติดตั้งอัปเดตอื่นอยู่"}
        nonce = ""
        outcome = {"ok": False, "error": "ยังไม่ได้อัปเดต Extension"}
        try:
            if not getattr(sys, "frozen", False) or not self._envelope or "extension" not in self._downloaded:
                raise ValueError("ฟีเจอร์นี้ใช้กับชุดติดตั้งที่ดาวน์โหลด Extension แล้ว")
            release = verify_release(self._envelope)
            asset = release.get("extension") or {}
            archive = self._downloaded["extension"]
            with archive.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if archive.stat().st_size != asset.get("size") or digest != asset.get("sha256"):
                raise ValueError("ไฟล์ Extension ที่ดาวน์โหลดไม่ตรงกับรุ่นเผยแพร่")
            health = self._read_local("/health")
            target_version = str(release["extension_version"])
            if target_version != health.get("extension_version_required"):
                raise ValueError("ต้องอัปเดตโปรแกรมให้รองรับ Extension รุ่นนี้ก่อน")
            verify_bundled_package(archive, RESOURCE_ROOT / "browser_extension")
            folder = Path(os.environ["LOCALAPPDATA"]) / "SmartFlowAI/data/browser_extension"
            config_file = folder.parent / "config.json"
            config = json.loads(config_file.read_text(encoding="utf-8")) if config_file.is_file() else {}
            chrome_root = Path(config.get("chrome_user_data_dir") or Path.home() / "AppData/Local/Google/Chrome/User Data")
            client_id = installed_extension_id(folder, chrome_root, str(config.get("chrome_profile_directory") or ""))
            status = self._read_local("/api/extension/status")
            clients = [client for client in status.get("clients", []) if client.get("client_id") == client_id]
            if not clients:
                raise ValueError("Extension ตัวเดิมยังไม่เชื่อมต่อ • เปิด Chrome โปรไฟล์เดิมแล้วลองอีกครั้ง")
            if any(client.get("version") == target_version for client in clients):
                outcome = {"ok": True, "message": "Extension ที่เชื่อมต่ออยู่เป็นรุ่นนี้แล้ว", "reload_requested": False,
                           "version": target_version}
                return outcome
            barrier = self._update_barrier({"extension_update": True})
            if not barrier.get("ok") or not barrier.get("nonce"):
                raise ValueError(barrier.get("error") or "ยังมีงานอยู่ กรุณารอให้จบก่อนอัปเดต")
            nonce = str(barrier["nonce"])
            backup = install_archive(archive, folder, target_version)
            try:
                requested = self._desktop_update_action("reload_extension_after_update", {
                    "nonce": nonce, "client_id": client_id, "target_version": target_version})
                if not requested.get("ok"):
                    raise ValueError(requested.get("error") or "Extension ยังไม่รับคำสั่ง Reload")
                message = "อัปเดตไฟล์แล้ว • กำลังให้ Extension โหลดใหม่ โปรดรอตรวจการเชื่อมต่อ คิวงานยังพักไว้"
                reload_requested = True
            except Exception:
                message = "อัปเดตไฟล์แล้ว • Extension รุ่นเดิมยังไม่รองรับปุ่มนี้ กรุณากด Reload ที่ตัวเดิมใน Chrome อีกหนึ่งครั้ง คิวงานยังพักไว้"
                reload_requested = False
            outcome = {"ok": True, "message": message, "reload_requested": reload_requested,
                       "version": target_version, "backup": str(backup)}
        except Exception as exc:
            outcome = {"ok": False, "error": str(exc)}
        finally:
            if nonce:
                try:
                    released = self._update_barrier({"cancel": True, "nonce": nonce})
                    if not released.get("ok"):
                        raise ValueError("ไม่ได้รับการยืนยันว่าปลดสถานะอัปเดตแล้ว")
                except Exception:
                    outcome = {"ok": False, "error": "ปลดสถานะอัปเดตไม่สำเร็จ • กรุณาเปิดโปรแกรมใหม่ก่อนเริ่มงาน"}
            self._install_lock.release()
        return outcome

    def _read_local(self, path):
        with urlopen(self._host.base_url + path, timeout=8) as response:
            return json.load(response)

    def _desktop_update_action(self, action, payload):
        request = Request(self._host.base_url + "/api/desktop/action",
                          data=json.dumps({"action": action, "payload": payload}).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=12) as response:
            return json.load(response)

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
        return self._desktop_update_action("prepare_app_update", payload)

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
