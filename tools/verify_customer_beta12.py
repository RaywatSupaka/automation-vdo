"""Read-only package audit plus isolated frozen ENGINE smoke, never provider work."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'deliverables/customer-0.3.0-beta.12'
APP = BUILD / 'SmartFlow AI'
DATA = ROOT / 'build/data-engine-beta12-utf8'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    global BUILD, APP, DATA
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=BUILD)
    parser.add_argument('--data', type=Path, default=DATA)
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args()
    BUILD, DATA = args.build.resolve(), args.data.resolve()
    APP = BUILD / 'SmartFlow AI'
    metadata = json.loads((BUILD / 'BUILD.json').read_text(encoding='utf-8'))
    version, extension = metadata['version'], metadata['extension_version']
    from tools.build_customer import validate_payload
    validate_payload(APP, extension)
    manifest = json.loads((BUILD / 'PAYLOAD.json').read_text(encoding='utf-8'))
    assert set(manifest) == {p.relative_to(APP).as_posix() for p in APP.rglob('*') if p.is_file()}
    for name, spec in manifest.items():
        assert digest(APP / name) == spec['sha256'], name
    # The builder fingerprints external tools by install path; those were also
    # validated by payload hashes. Project input fingerprints are rechecked.
    source_count = 0
    for name, expected in metadata['source_sha256'].items():
        source = ROOT / name
        if source.is_file():
            assert digest(source) == expected, name
            source_count += 1
    with zipfile.ZipFile(BUILD / f'SmartFlow-Extension-{extension}.zip') as zipped:
        files = {p.relative_to(ROOT / 'browser_extension').as_posix(): p
                 for p in (ROOT / 'browser_extension').rglob('*') if p.is_file()}
        assert set(zipped.namelist()) == set(files)
        for name, source in files.items():
            assert zipped.read(name) == source.read_bytes() == (APP / 'browser_extension' / name).read_bytes()
    if args.audit_only:
        print(json.dumps(dict(payload_files=len(manifest), source_files=source_count,
                              extension_files=len(files), version=version, extension=extension)))
        return
    assert not DATA.exists(), 'Use a new isolated test data directory; never reset an existing one'
    DATA.mkdir(parents=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    env.update(PATH=os.environ['SystemRoot'] + '/System32;' + os.environ['SystemRoot'],
               SMARTFLOW_TEST_DATA_ROOT=str(DATA), SMARTFLOW_TEST_PORT=str(port))
    exe = APP / 'SmartFlow AI.exe'
    process = subprocess.Popen([str(exe), '--engine'], cwd=APP, env=env,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    base = 'http://127.0.0.1:' + str(port)
    health = None
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Isolated engine exited: ' + str(process.returncode))
            try:
                with urlopen(base + '/health', timeout=2) as response:
                    health = json.load(response)
                assert health['engine_pid'] == process.pid, 'Never adopt another engine'
                break
            except OSError:
                time.sleep(.4)
        assert health and health['release_version'] == version
        assert health['extension_version_required'] == extension
        assert json.loads((DATA / 'browser_extension/manifest.json').read_text(encoding='utf-8'))['version'] == extension
        for tool, args in [('ffmpeg/ffmpeg.exe', ['-version']), ('tools/android/adb.exe', ['version']),
                           ('tools/android/scrcpy.exe', ['--version'])]:
            result = subprocess.run([str(APP / tool), *args], env=env, capture_output=True,
                                    timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode == 0, tool
        output = DATA / 'synthetic-thai.mp4'
        command = [str(APP / 'ffmpeg/ffmpeg.exe'), '-hide_banner', '-loglevel', 'error',
                   '-f', 'lavfi', '-i', 'color=c=0x101020:s=360x640:d=1',
                   '-vf', "drawtext=fontfile=assets/fonts/smartsubai/Sarabun-Bold.ttf:text='ทดสอบระบบ':fontcolor=white:fontsize=26:x=30:y=300",
                   '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(output)]
        result = subprocess.run(command, cwd=APP, env=env, capture_output=True, timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr.decode(errors='replace')[-800:]
        probe = subprocess.run([str(APP / 'ffmpeg/ffprobe.exe'), '-v', 'error', '-show_streams',
                                '-of', 'json', str(output)], env=env, capture_output=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        stream = json.loads(probe.stdout)['streams'][0]
        assert stream['codec_name'] == 'h264' and stream['pix_fmt'] == 'yuv420p'
    finally:
        # Graceful shutdown ONLY after verifying the exact newly owned PID.
        if process.poll() is None:
            with urlopen(base + '/health', timeout=2) as response:
                current = json.load(response)
            assert current['engine_pid'] == process.pid
            request = Request(base + '/api/desktop/action', method='POST',
                              data=b'{"action":"shutdown","payload":{}}',
                              headers={'Content-Type': 'application/json'})
            with urlopen(request, timeout=5) as response:
                assert json.load(response).get('ok')
            process.wait(timeout=15)
    with socket.socket() as check:
        assert check.connect_ex(('127.0.0.1', port)) != 0, 'Isolated port must close'
    result = dict(payload_files=len(manifest), source_files=source_count, extension_files=len(files),
                  engine_pid=process.pid, engine_exit=process.returncode, port_closed=True,
                  engine_release=health['release_version'], extension=extension,
                  media='H264/yuv420p/Thai font', native_gui_verified=False,
                  clean_machine_verified=False, provider_generation=False)
    (BUILD / 'LOCAL-VERIFICATION.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
