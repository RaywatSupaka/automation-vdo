"""Build a standalone, allowlisted customer payload; never copy user state."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ('pywebview', 'cryptography', 'uiautomator2', 'adbutils', 'Pillow',
            'PyThaiNLP', 'fonttools', 'requests', 'pythonnet', 'clr_loader')
RESOURCE_FOLDERS = ('web_ui', 'assets/fonts/smartsubai', 'browser_extension')
BRAND_FILES = ('smartflow_icon.ico', 'smartflow_icon.png', 'smartflow_logo.png', 'smartpost_logo.jpg')
ANDROID_REQUIRED = ('adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll', 'scrcpy.exe',
                    'scrcpy-server', 'SDL3.dll', 'LICENSE.txt')
FORBIDDEN_PARTS = {'workspace', 'logs', 'screenshots', 'webview-profile', 'chrome-profile',
                   'backups', 'archives', '.git', '.codex', '__pycache__'}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def payload_sources(root, ffmpeg, android):
    files = {}
    def add(target, source):
        if source.is_symlink() or not source.is_file():
            raise ValueError('Missing or linked build resource: ' + target)
        if {part.casefold() for part in Path(target).parts} & FORBIDDEN_PARTS:
            raise ValueError('User state in resource tree: ' + target)
        files[target] = source
    for folder in RESOURCE_FOLDERS:
        source = root / folder
        if not source.is_dir() or source.is_symlink():
            raise ValueError('Missing or linked resource folder: ' + folder)
        for path in sorted(source.rglob('*')):
            if path.is_symlink():
                raise ValueError('Linked resource is not allowed: ' + str(path.relative_to(root)))
            if path.is_file():
                add(path.relative_to(root).as_posix(), path)
    for name in BRAND_FILES + ('update-public-key.txt',):
        add('assets/' + name, root / 'assets' / name)
    add('READ-ME.html', root / 'launcher/CUSTOMER_README.html')
    for name in ('ffmpeg.exe', 'ffprobe.exe'):
        add('ffmpeg/' + name, ffmpeg / name)
    for path in sorted(ffmpeg.glob('*.dll')):
        add('ffmpeg/' + path.name, path)
    for name in ('LICENSE', 'README.txt'):
        add('ffmpeg/' + name, ffmpeg.parent / name)
    for name in ANDROID_REQUIRED:
        add('tools/android/' + name, android / name)
    for path in sorted(android.glob('*.dll')):
        add('tools/android/' + path.name, path)
    # No assets/audio, personal logos, jobs, config, cookies or profiles.
    return files


def preflight(root, ffmpeg, android, version):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-beta\.\d+)?', version):
        raise ValueError('Invalid customer version')
    extension = json.loads((root / 'browser_extension/manifest.json').read_text(encoding='utf-8'))['version']
    release = json.loads((root / 'CURRENT_RELEASE.json').read_text(encoding='utf-8'))
    if release['runtime']['extension_version'] != extension or f'REQUIRED_EXTENSION_VERSION = "{extension}"' not in (root / 'core/local_bridge.py').read_text(encoding='utf-8'):
        raise ValueError('Desktop and Extension versions are not paired')
    key = base64.b64decode((root / 'assets/update-public-key.txt').read_text().strip(), validate=True)
    if len(key) != 32:
        raise ValueError('Invalid public update verification key')
    versions = {name: importlib.metadata.version(name) for name in PACKAGES + ('PyInstaller',)}
    return payload_sources(root, ffmpeg, android), extension, versions


def write_notices(app, root):
    licenses = app / 'licenses'
    licenses.mkdir(exist_ok=True)
    for name in PACKAGES:
        dist = importlib.metadata.distribution(name)
        for item in dist.files or ():
            path = Path(item)
            if path.name.lower().startswith(('license', 'copying', 'notice')) and path.suffix.lower() in ('', '.txt', '.md', '.rst'):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    target = licenses / name / path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() and target.read_bytes() != source.read_bytes():
                        target = target.with_name(digest(source)[:10] + '-' + target.name)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise ValueError('Python redistribution license missing')
    shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
    from fontTools.ttLib import TTFont
    notices, full_ofl = [], ''
    for path in sorted((root / 'assets/fonts/smartsubai').glob('*.ttf')):
        with TTFont(path) as font:
            names = font['name']
            license_text = names.getDebugName(13) or ''
            if 'SIL OPEN FONT LICENSE' not in license_text.upper():
                raise ValueError('Unverified font license: ' + path.name)
            if len(license_text) > len(full_ofl):
                full_ofl = license_text
            notices.append(path.name + '\n' + '\n'.join(filter(None, (names.getDebugName(i) for i in (0, 7, 8, 14)))))
    if len(full_ofl) < 3000:
        raise ValueError('Full font license text missing')
    (licenses / 'Fonts-OFL.txt').write_text('\n\n'.join(notices) + '\n\n' + full_ofl, encoding='utf-8')


def validate_payload(app, extension):
    for path in app.rglob('*'):
        rel = path.relative_to(app)
        if path.is_symlink() or {part.casefold() for part in rel.parts} & FORBIDDEN_PARTS:
            raise ValueError('Unsafe packaged path: ' + rel.as_posix())
        if rel.as_posix().casefold() == 'config.json' or path.name.lower() in {'adbkey', 'adbkey.pub', 'membership.json', 'private.pem', 'private.key'}:
            raise ValueError('Private state packaged: ' + rel.as_posix())
    required = ('SmartFlow AI.exe', 'SmartFlow Updater.exe', 'python311.dll', 'web_ui/index.html',
                'assets/update-public-key.txt', 'ffmpeg/ffmpeg.exe', 'ffmpeg/ffprobe.exe',
                'tools/android/adb.exe', 'tools/android/scrcpy.exe', 'tools/android/scrcpy-server',
                'licenses/Fonts-OFL.txt', 'READ-ME.html')
    for name in required:
        if not (app / name).is_file():
            raise ValueError('Missing packaged dependency: ' + name)
    if (app / 'assets/audio').exists():
        raise ValueError('Unapproved media included in installer')
    if json.loads((app / 'browser_extension/manifest.json').read_text(encoding='utf-8'))['version'] != extension:
        raise ValueError('Packaged Extension mismatch')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffmpeg-dir', type=Path, required=True)
    parser.add_argument('--android-dir', type=Path, default=ROOT / 'tools/scrcpy-win64-v4.1')
    parser.add_argument('--version', required=True)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    sources, extension, versions = preflight(ROOT, args.ffmpeg_dir, args.android_dir, args.version)
    source_code = {p.relative_to(ROOT).as_posix(): p for folder in ('core', 'desktop', 'ui')
                   for p in (ROOT / folder).rglob('*.py')}
    source_code.update({'app.py': ROOT / 'app.py', 'tools/customer_updater.py': ROOT / 'tools/customer_updater.py'})
    fingerprints = {name: digest(path) for name, path in sorted({**sources, **source_code}.items())}
    if args.preflight_only:
        print(json.dumps({'version': args.version, 'extension_version': extension, 'resources': len(sources), 'packages': versions}, indent=2))
        return
    output = ROOT / 'deliverables' / ('customer-' + args.version)
    if output.exists():
        raise SystemExit('Output already exists; use a new build version/directory')
    work = ROOT / 'build' / ('customer-' + args.version)
    work.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--onedir',
               '--contents-directory', '.', '--name', 'SmartFlow AI',
               '--icon', str(ROOT / 'assets/smartflow_icon.ico'), '--distpath', str(output),
               '--workpath', str(work / 'app'), '--specpath', str(work)]
    for module in ('webview', 'pythainlp', 'uiautomator2', 'adbutils', 'fontTools'):
        command += ['--collect-all', module]
    for folder in RESOURCE_FOLDERS:
        command += ['--add-data', f'{ROOT / folder};{folder}']
    for name in BRAND_FILES + ('update-public-key.txt',):
        command += ['--add-data', f'{ROOT / "assets" / name};assets']
    subprocess.run(command + [str(ROOT / 'app.py')], cwd=ROOT, check=True)
    app = output / 'SmartFlow AI'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
                    '--name', 'SmartFlow Updater', '--icon', str(ROOT / 'assets/smartflow_icon.ico'),
                    '--distpath', str(app), '--workpath', str(work / 'updater'), '--specpath', str(work),
                    '--add-data', f'{ROOT / "assets/update-public-key.txt"};assets',
                    str(ROOT / 'tools/customer_updater.py')], cwd=ROOT, check=True)
    for name, source in {**sources, **source_code}.items():
        if digest(source) != fingerprints[name]:
            raise ValueError('Source changed during build; do not distribute: ' + name)
    for name, source in sources.items():
        target = app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    write_notices(app, ROOT)
    validate_payload(app, extension)
    extension_zip = output / f'SmartFlow-Extension-{extension}.zip'
    with zipfile.ZipFile(extension_zip, 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((app / 'browser_extension').rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(app / 'browser_extension').as_posix())
    metadata = {'app_id': 'smartflow', 'version': args.version, 'extension_version': extension,
                'channel': 'beta', 'extension_sha256': digest(extension_zip)}
    (app / 'customer-release.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (output / 'BUILD.json').write_text(json.dumps(dict(metadata, packages=versions, source_sha256=fingerprints,
        built_at=datetime.now(timezone.utc).isoformat(), personal_audio_bundled=False,
        clean_machine_verified=False, signed_executable=False), indent=2), encoding='utf-8')
    manifest = {p.relative_to(app).as_posix(): {'sha256': digest(p), 'size': p.stat().st_size}
                for p in sorted(app.rglob('*')) if p.is_file()}
    (output / 'PAYLOAD.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(str(output))


if __name__ == '__main__':
    main()
