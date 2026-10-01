"""Signed SmartFlow release checks; no automation/browser gestures."""
import base64
import hashlib
import json
import re
import shutil
import threading
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import urlopen

MANIFEST_URL = "https://www.catfufu.com/api/smartflow-updates/latest/beta"
RESOURCE_ROOT = Path(__file__).resolve().parents[1]


def customer_version():
    try:
        return json.loads((RESOURCE_ROOT / "customer-release.json").read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "development"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def safe_url(url):
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or parsed.hostname != "www.catfufu.com" or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("แหล่งดาวน์โหลดอัปเดตไม่ถูกต้อง")
    if not parsed.path.startswith("/api/smartflow-updates/"):
        raise ValueError("เส้นทางดาวน์โหลดไม่ถูกต้อง")
    return str(url)


def version(value):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?", str(value))
    if not match:
        raise ValueError("เวอร์ชันไม่ถูกต้อง")
    a, b, c, beta = match.groups()
    return int(a), int(b), int(c), 1 if beta is None else 0, int(beta or 0)


def verify_release(envelope, public_key=None):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if public_key is None:
        public_key = (RESOURCE_ROOT / "assets/update-public-key.txt").read_text().strip()
    payload = envelope["release"]
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
        base64.b64decode(envelope["signature"], validate=True), canonical(payload))
    if payload.get("app_id") != "smartflow" or payload.get("channel") not in ("beta", "stable"):
        raise ValueError("แพตช์ไม่ใช่ SmartFlow AI")
    version(payload["version"])
    version(payload["extension_version"])
    if payload.get("platform") != "windows-x64":
        raise ValueError("แพตช์ไม่รองรับเครื่องนี้")
    for kind in ("patch", "extension", "installer"):
        asset = payload.get(kind)
        if not asset:
            continue
        safe_url(asset["url"])
        if not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
            raise ValueError("Checksum ไม่ถูกต้อง")
        if not isinstance(asset["size"], int) or not 0 < asset["size"] <= 2 * 1024**3:
            raise ValueError("ขนาดไฟล์ไม่ถูกต้อง")
    return payload


def download(asset, target, progress=lambda received, total: None):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    digest, count = hashlib.sha256(), 0
    try:
        with urlopen(safe_url(asset["url"]), timeout=30) as response, partial.open("wb") as stream:
            safe_url(response.url)
            while block := response.read(256 * 1024):
                count += len(block)
                if count > asset["size"]:
                    raise ValueError("ไฟล์ใหญ่กว่าที่ประกาศ")
                stream.write(block)
                digest.update(block)
                progress(count, asset["size"])
        if count != asset["size"] or digest.hexdigest() != asset["sha256"]:
            raise ValueError("ไฟล์ดาวน์โหลดไม่ครบหรือไม่ตรงลายเซ็นรุ่น")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def safe_patch_name(name):
    path = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or path.is_absolute() or any(p in ("..", ".") for p in name.split("/")):
        raise ValueError("Unsafe patch path")
    if path.parts[0].lower() in {"data", "workspace", "logs", "config.json", "videos", "extension-download"}:
        raise ValueError("Patch targets protected data")
    if any(part.rstrip(" .") != part or part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]} for part in path.parts):
        raise ValueError("Unsafe Windows path")
    return path
