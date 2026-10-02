"""Guarded, local one-click entry point for a *test* customer Setup.

This orchestrates the existing allowlisted payload builder and Inno compiler.
It never installs, publishes, signs a release, changes source versions, or
touches running desktop/Chrome jobs.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BETA_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)-beta\.(\d+)\Z")
EXTENSION_VERSION_PATTERN = r"[0-9]+\.[0-9]+\.[0-9]+"


class BuildGateError(RuntimeError):
    """A safe, user-actionable reason not to create a customer installer."""


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def next_beta_version(root):
    release = json.loads((root / "CURRENT_RELEASE.json").read_text(encoding="utf-8"))
    previous = str(release["customer_distribution"]["version"])
    match = re.fullmatch(r"(\d+\.\d+\.\d+-beta\.)(\d+)", previous)
    if not match:
        raise BuildGateError("Cannot choose the next beta automatically; pass --version explicitly.")
    return f"{match.group(1)}{int(match.group(2)) + 1}"


def assert_new_customer_version(root, version):
    requested = BETA_VERSION_PATTERN.fullmatch(version)
    if not requested:
        raise BuildGateError("This button creates beta test installers only. Example: 0.3.0-beta.14")
    release = json.loads((root / "CURRENT_RELEASE.json").read_text(encoding="utf-8"))
    previous = str(release["customer_distribution"]["version"])
    last = BETA_VERSION_PATTERN.fullmatch(previous)
    if not last:
        raise BuildGateError("The previous customer version is not a beta; review the release channel manually.")
    if tuple(map(int, requested.groups())) <= tuple(map(int, last.groups())):
        raise BuildGateError(f"Customer version {version} must be newer than {previous}.")


def paired_extension_version(root):
    release = json.loads((root / "CURRENT_RELEASE.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "browser_extension/manifest.json").read_text(encoding="utf-8"))
    version = str(manifest["version"])
    bridge = (root / "core/local_bridge.py").read_text(encoding="utf-8")
    if (version != str(release["runtime"]["extension_version"])
            or f'REQUIRED_EXTENSION_VERSION = "{version}"' not in bridge):
        raise BuildGateError("Extension manifest, CURRENT_RELEASE and desktop bridge have different versions.")
    assert_extension_not_older_than_packaged(root, version)
    return version


def assert_extension_not_older_than_packaged(root, version):
    """Read immutable release manifests; never silently build an older pair."""
    if not re.fullmatch(EXTENSION_VERSION_PATTERN, version):
        raise BuildGateError(f"Invalid canonical Extension version: {version!r}.")
    current = tuple(map(int, version.split(".")))
    deliverables = root / "deliverables"
    if not deliverables.exists():
        return
    artifacts = []
    try:
        for path in sorted(deliverables.iterdir()):
            match = re.fullmatch(rf"SmartFlow_AI_Extension_({EXTENSION_VERSION_PATTERN})(\.zip)?", path.name)
            if match:
                artifacts.append((path, match[1], bool(match[2])))
            elif path.name.startswith("customer-") and path.is_dir():
                for archive in sorted(path.iterdir()):
                    match = re.fullmatch(rf"SmartFlow-Extension-({EXTENSION_VERSION_PATTERN})\.zip", archive.name)
                    if match:
                        artifacts.append((archive, match[1], True))
    except OSError as exc:
        raise BuildGateError(f"Cannot inspect packaged Extension versions in {deliverables}.") from exc
    for path, packaged_version, is_zip in artifacts:
        # Older immutable artifacts cannot prove a downgrade. Do not inspect
        # their historical manifest/layout or require repackaging old releases.
        if tuple(map(int, packaged_version.split("."))) < current:
            continue
        try:
            if path.is_symlink():
                raise ValueError("linked artifact")
            if is_zip:
                with zipfile.ZipFile(path) as archive:
                    if archive.namelist().count("manifest.json") != 1:
                        raise ValueError("missing or duplicate root manifest.json")
                    if archive.getinfo("manifest.json").file_size > 1024 * 1024:
                        raise ValueError("oversized manifest.json")
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            else:
                manifest_path = path / "manifest.json"
                if manifest_path.is_symlink() or manifest_path.stat().st_size > 1024 * 1024:
                    raise ValueError("linked or oversized manifest.json")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or manifest.get("version") != packaged_version:
                raise ValueError("manifest version does not match the numeric artifact filename")
        except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
            raise BuildGateError(
                f"Cannot verify Extension artifact {path}: invalid, unreadable or mismatched manifest. "
                "Review the preserved artifact before building; no downgrade is allowed."
            ) from exc
        if tuple(map(int, packaged_version.split("."))) > current:
            raise BuildGateError(
                f"Canonical Extension {version} is older than packaged {packaged_version} at {path}. "
                "Reconcile the approved newer desktop/Extension source before building; do not downgrade."
            )


def extension_sources(root):
    source = root / "browser_extension"
    files = {}
    for path in source.rglob("*"):
        if path.is_symlink():
            raise BuildGateError(f"Linked Extension source is not allowed: {path.name}")
        if path.is_file():
            files[path.relative_to(source).as_posix()] = path
    if not files:
        raise BuildGateError("Extension source is empty.")
    return files


def assert_same_extension_folder(folder, files):
    frozen = {path.relative_to(folder).as_posix(): path for path in folder.rglob("*") if path.is_file()}
    if set(frozen) != set(files):
        raise BuildGateError(f"Extension files differ from frozen version at {folder}. Bump the paired Extension version first.")
    for name, source in files.items():
        if source.read_bytes() != frozen[name].read_bytes():
            raise BuildGateError(f"Extension {name} differs from frozen version at {folder}. Bump the paired Extension version first.")


def assert_same_extension_zip(archive_path, files):
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(files):
            raise BuildGateError(f"Extension files differ from frozen version at {archive_path}. Bump the paired Extension version first.")
        for name, source in files.items():
            if archive.read(name) != source.read_bytes():
                raise BuildGateError(f"Extension {name} differs from frozen version at {archive_path}. Bump the paired Extension version first.")


def assert_extension_version_not_reused(root, version):
    """A fixed Chrome Extension version must always identify the same bytes."""
    files = extension_sources(root)
    frozen_folder = root / "deliverables" / f"SmartFlow_AI_Extension_{version}"
    if frozen_folder.exists():
        assert_same_extension_folder(frozen_folder, files)
    archives = [root / "deliverables" / f"SmartFlow_AI_Extension_{version}.zip"]
    archives.extend((root / "deliverables").glob(f"customer-*/SmartFlow-Extension-{version}.zip"))
    for archive in archives:
        if archive.is_file():
            assert_same_extension_zip(archive, files)


def require_file(path, label):
    if not path.is_file():
        raise BuildGateError(f"Missing {label}: {path}")
    return path


def verify_payload(output, version, extension):
    build = json.loads((output / "BUILD.json").read_text(encoding="utf-8"))
    if build.get("version") != version or build.get("extension_version") != extension:
        raise BuildGateError("Built desktop/Extension version does not match the requested Setup.")
    app = output / "SmartFlow AI"
    manifest = json.loads((output / "PAYLOAD.json").read_text(encoding="utf-8"))
    actual = {path.relative_to(app).as_posix(): path for path in app.rglob("*") if path.is_file()}
    if set(actual) != set(manifest):
        raise BuildGateError("Payload file list differs from PAYLOAD.json; do not distribute this Setup.")
    for name, record in manifest.items():
        path = actual[name]
        if path.stat().st_size != record["size"] or sha256(path).lower() != record["sha256"].lower():
            raise BuildGateError(f"Payload hash mismatch: {name}")
    extension_zip = output / f"SmartFlow-Extension-{extension}.zip"
    require_file(extension_zip, "paired Extension ZIP")
    if sha256(extension_zip).lower() != build["extension_sha256"].lower():
        raise BuildGateError("Extension ZIP hash mismatch.")
    assert_same_extension_zip(extension_zip, extension_sources(ROOT))
    return len(manifest)


def verify_build_sources(output, root, ffmpeg_dir, android_dir):
    """Catch source edits that occur after freezing but before Setup finishes."""
    build = json.loads((output / "BUILD.json").read_text(encoding="utf-8"))
    for name, expected in build["source_sha256"].items():
        if name.startswith("ffmpeg/"):
            filename = name.removeprefix("ffmpeg/")
            source = (ffmpeg_dir.parent if filename in {"LICENSE", "README.txt"} else ffmpeg_dir) / filename
        elif name.startswith("tools/android/"):
            source = android_dir / name.removeprefix("tools/android/")
        elif name == "READ-ME.html":
            source = root / "launcher/CUSTOMER_README.html"
        else:
            source = root / name
        if not source.is_file() or sha256(source).lower() != expected.lower():
            raise BuildGateError(f"Build input changed while packaging: {name}. Do not distribute this Setup.")


def run(command, label):
    print(f"\n[{label}]", flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        raise BuildGateError(f"{label} failed (exit {result.returncode}). Partial build files, if any, were kept for inspection.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a guarded SmartFlow AI customer test installer")
    parser.add_argument("--version", help="Customer version; default is the next beta after CURRENT_RELEASE.json")
    parser.add_argument("--check-only", action="store_true", help="Run gates without creating customer release artifacts")
    parser.add_argument("--full-tests", action="store_true", help="Also run the full source test suite before building")
    parser.add_argument("--repeat-full-tests-reason", help="Document why this build needs another full test run")
    parser.add_argument("--ffmpeg-dir", type=Path, default=ROOT / "build/ffmpeg-beta12/bin")
    parser.add_argument("--android-dir", type=Path, default=ROOT / "tools/scrcpy-win64-v4.1")
    parser.add_argument("--inno", type=Path, default=ROOT / "build/installer-tools/inno/ISCC.exe")
    args = parser.parse_args(argv)
    if args.repeat_full_tests_reason is not None:
        if not args.full_tests:
            parser.error("--repeat-full-tests-reason requires --full-tests")
        if not args.repeat_full_tests_reason.strip():
            parser.error("--repeat-full-tests-reason must not be empty")
    try:
        if sys.platform != "win32":
            raise BuildGateError("The customer Setup can only be built on Windows.")
        version = args.version or next_beta_version(ROOT)
        assert_new_customer_version(ROOT, version)
        output = ROOT / "deliverables" / f"customer-{version}"
        if output.exists():
            raise BuildGateError(f"This version already has an output folder: {output}. Choose a NEW version; do not overwrite it.")
        extension = paired_extension_version(ROOT)
        print(f"SmartFlow AI customer version: {version}", flush=True)
        print(f"Paired Extension version: {extension}", flush=True)
        assert_extension_version_not_reused(ROOT, extension)
        python = require_file(ROOT / ".build-env/Scripts/python.exe", "isolated build Python")
        require_file(args.ffmpeg_dir / "ffmpeg.exe", "FFmpeg")
        require_file(args.ffmpeg_dir / "ffprobe.exe", "FFprobe")
        require_file(args.android_dir / "adb.exe", "Android tools")
        require_file(args.inno, "Inno Setup compiler")
        require_file(ROOT / "build/installer-tools/MicrosoftEdgeWebview2Setup.exe", "WebView2 bootstrapper")
        command = [str(python), str(ROOT / "tools/build_customer.py"), "--version", version,
                   "--ffmpeg-dir", str(args.ffmpeg_dir), "--android-dir", str(args.android_dir)]
        run(command + ["--preflight-only"], "Dependency and source preflight")
        for filename in ("test_build_installer_one_click.py", "test_customer_builder.py", "test_customer_installer_guard.py",
                         "test_project_release_contract.py"):
            require_file(ROOT / "tests" / filename, "installer regression test")
            run([str(python), "-m", "unittest", "discover", "-s", "tests", "-p", filename],
                f"Installer gate: {filename}")
        if args.full_tests:
            audit = [str(python), str(ROOT / "tools/run_audit_checks.py"), "--full"]
            if args.repeat_full_tests_reason:
                audit += ["--repeat-full", "--reason", args.repeat_full_tests_reason]
            run(audit, "Full source regression suite")
        if args.check_only:
            print("CHECK ONLY: all gates passed; no installer was built.")
            return 0
        run(command, "Build standalone app, updater and Extension ZIP")
        count = verify_payload(output, version, extension)
        run([str(args.inno), "/Q", f"/DBuildRoot={output}", f"/DReleaseVersion={version}",
             str(ROOT / "launcher/customer.iss")], "Compile customer Setup")
        verify_build_sources(output, ROOT, args.ffmpeg_dir, args.android_dir)
        installer = require_file(output / f"SmartFlow-AI-Setup-{version}.exe", "finished installer")
        print(f"\nSETUP READY FOR TESTING: {installer}")
        print(f"Size: {installer.stat().st_size:,} bytes | SHA-256: {sha256(installer)}")
        print(f"Verified payload files: {count} | Extension: {extension}")
        print("Not installed, published, signed, or verified on a clean second PC.")
        return 0
    except (BuildGateError, KeyError, ValueError, OSError, zipfile.BadZipFile) as exc:
        print(f"\nBUILD BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
