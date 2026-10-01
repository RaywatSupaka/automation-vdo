"""Create a signed release envelope and cumulative code patch, offline."""
import argparse
import base64
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.app_updates import canonical, safe_patch_name, version
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def make_upload_bundle(envelope, patch, destination):
    """Two-input admin upload: signed metadata + unchanged patch payload.

    Wrapper is not itself the signed/downloaded asset (avoids circular hashes).
    Its two stored entries can be sliced by the browser in bounded chunks.
    """
    release = envelope["release"]
    if release.get("app_id") != "smartflow" or release.get("installer") or not release.get("supported_from"):
        raise ValueError("Update bundle requires a patch-only release and supported source versions")
    if any(version(old) >= version(release["version"]) for old in release["supported_from"]):
        raise ValueError("Supported source must be older than target")
    patch = Path(patch)
    with patch.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != release["patch"]["sha256"] or patch.stat().st_size != release["patch"]["size"]:
        raise ValueError("Patch does not match signed metadata")
    metadata = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    if len(metadata) > 131072 or patch.stat().st_size + len(metadata) + 4096 > 2 * 1024**3:
        raise ValueError("Upload bundle exceeds supported bounds")
    with zipfile.ZipFile(destination, "x", zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.writestr("release.json", metadata)
        archive.write(patch, "patch.zip")
    return Path(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build", type=Path)
    parser.add_argument("--from-version", action="append", default=[])
    args = parser.parse_args()
    app = args.build / "SmartFlow AI"
    metadata = json.loads((app / "customer-release.json").read_text())
    release = {**metadata, "platform": "windows-x64", "supported_from": args.from_version,
               "notes": "รุ่นทดสอบติดตั้งเครื่องใหม่ • แยกข้อมูลผู้ใช้ • แจ้งอัปเดตโปรแกรมและ Extension แยกกัน • ไม่เปลี่ยน logic สร้างคลิป"}
    patch = args.build / f"SmartFlow-Patch-{metadata['version']}.zip"
    with zipfile.ZipFile(patch, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                name = path.relative_to(app).as_posix()
                safe_patch_name(name)
                archive.write(path, name)
    files = {"patch": patch, "extension": next(args.build.glob("SmartFlow-Extension-*.zip")),
             "installer": args.build / f"SmartFlow-AI-Setup-{metadata['version']}.exe"}
    for kind, path in files.items():
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        release[kind] = {"name": path.name, "sha256": digest, "size": path.stat().st_size,
                         "url": "https://www.catfufu.com/api/smartflow-updates/files/" + digest}
    key = Ed25519PrivateKey.from_private_bytes((Path(os.environ["LOCALAPPDATA"]) / "SmartFlowReleaseKeys/publisher.ed25519").read_bytes())
    envelope = {"release": release, "signature": base64.b64encode(key.sign(canonical(release))).decode()}
    (args.build / "release.json").write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.from_version:
        update_release = {k: v for k, v in release.items() if k != "installer"}
        update_envelope = {"release": update_release,
            "signature": base64.b64encode(key.sign(canonical(update_release))).decode()}
        make_upload_bundle(update_envelope, patch, args.build / f"SmartFlow-Admin-Patch-{metadata['version']}.zip")
        print("Admin upload: SmartFlow-Admin-Patch ZIP + matching Extension ZIP (no EXE/JSON selection)")
    else:
        print("No update upload bundle: specify tested --from-version values before publishing a customer patch")
    print("Signed beta release prepared")


if __name__ == "__main__":
    main()
