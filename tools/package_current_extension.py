"""Package only canonical extension source; refuse to overwrite a different release."""
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'browser_extension'
    release = json.loads((root / 'CURRENT_RELEASE.json').read_text(encoding='utf-8'))
    version = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid release version')
    assert release['runtime']['extension_version'] == version
    assert f'REQUIRED_EXTENSION_VERSION = "{version}"' in (root / 'core/local_bridge.py').read_text(encoding='utf-8')
    folder = root / 'deliverables' / f'SmartFlow_AI_Extension_{version}'
    archive = folder.parent / (folder.name + '.zip')
    assert release['runtime']['install_directory'] == folder.relative_to(root).as_posix()
    assert release['runtime']['install_zip'] == archive.relative_to(root).as_posix()
    files = {p.relative_to(source).as_posix(): p for p in source.rglob('*') if p.is_file()}
    if not folder.exists():
        shutil.copytree(source, folder)
    installed = {p.relative_to(folder).as_posix(): p for p in folder.rglob('*') if p.is_file()}
    assert files.keys() == installed.keys(), 'Existing folder differs; do not overwrite'
    for name, path in files.items():
        assert path.read_bytes() == installed[name].read_bytes(), f'Existing release differs: {name}'
    if not archive.exists():
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as zipped:
            for name, path in sorted(files.items()):
                zipped.write(path, name)
    with zipfile.ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == files.keys()
        for name, path in files.items(): assert zipped.read(name) == path.read_bytes(), name
    print(json.dumps({'version':version, 'files':len(files), 'sha256':hashlib.sha256(archive.read_bytes()).hexdigest().upper(),
                      'zip':str(archive), 'directory':str(folder),
                      'directory_role':'immutable_release_artifact',
                      'stable_install_directory':str(source),
                      'update_guidance':'Keep the same Chrome profile, extension ID and loaded path. Existing versioned-path installations require an explicit migration; never uninstall to update.'}, indent=2))


if __name__ == '__main__': main()
