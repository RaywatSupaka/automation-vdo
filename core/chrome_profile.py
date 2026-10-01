"""Resolve the installed SmartFlow profile without reading or logging credentials."""
import json
import re
from pathlib import Path


def _json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def smartflow_profiles(root):
    root = Path(root)
    if not root.is_dir():
        return []
    found = []
    for profile in root.iterdir():
        if not profile.is_dir() or not re.fullmatch(r'Default|Profile \d+', profile.name):
            continue
        settings = {}
        for name in ('Preferences', 'Secure Preferences'):
            settings.update(_json(profile / name).get('extensions', {}).get('settings', {}))
        for entry in settings.values():
            # Current Chrome omits state for enabled unpacked extensions.
            if entry.get('state') not in (None, 1) or entry.get('disable_reasons'):
                continue
            manifest = entry.get('manifest') or {}
            extension_path = entry.get('path')
            if not manifest and extension_path:
                path = Path(extension_path)
                manifest = _json((path if path.is_absolute() else profile / 'Extensions' / path) / 'manifest.json')
            if manifest.get('name') in {'SmartFlow AI', 'SmartPost AI'}:
                found.append(profile.name)
                break
    return sorted(found)


def resolve_profile(config, default_root=None):
    root = Path(config.get('chrome_user_data_dir') or default_root or
                Path.home() / 'AppData/Local/Google/Chrome/User Data')
    candidates = smartflow_profiles(root)
    chosen = str(config.get('chrome_profile_directory') or '')
    if chosen:
        if chosen not in candidates:
            raise RuntimeError('โปรไฟล์ Chrome ที่บันทึกไว้ไม่พบ SmartFlow Extension ที่เปิดใช้งาน')
    elif len(candidates) == 1:
        chosen = candidates[0]
    elif len(candidates) > 1:
        raise RuntimeError('พบ SmartFlow หลายโปรไฟล์ • ระบุ chrome_profile_directory ก่อนเริ่มงาน: ' + ', '.join(candidates))
    else:
        raise RuntimeError('ไม่พบ Chrome โปรไฟล์ที่เปิดใช้ SmartFlow Extension • เปิดใช้งาน Extension แล้วลองใหม่')
    return {'chrome_user_data_dir': str(root.resolve()), 'chrome_profile_directory': chosen}


def launch_arguments(profile):
    return ['--user-data-dir=' + profile['chrome_user_data_dir'],
            '--profile-directory=' + profile['chrome_profile_directory']]
