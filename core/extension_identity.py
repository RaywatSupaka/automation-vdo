"""Trust the installed local SmartFlow package, not a caller-supplied name/ID."""
import hashlib
import json
import re
import time
from pathlib import Path


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


class ExtensionIdentity:
    def __init__(self, project_root, source_root=None, chrome_root=None):
        self.project_root=Path(project_root)
        self.source=Path(source_root or Path(__file__).resolve().parents[1]/'browser_extension').resolve()
        self.chrome_root=chrome_root
        self.cached_at=0
        self.ids=set()

    def allowed(self, origin):
        if not re.fullmatch(r'chrome-extension://[a-p]{32}',origin): return False
        if time.monotonic()-self.cached_at>10:
            self.ids=self.discover();self.cached_at=time.monotonic()
        return origin.removeprefix('chrome-extension://') in self.ids

    def discover(self):
        config=read_json(self.project_root/'config.json')
        root=Path(self.chrome_root or config.get('chrome_user_data_dir') or
                  Path.home()/'AppData/Local/Google/Chrome/User Data')
        if not root.is_dir(): return set()
        trusted={}
        # Compare the complete executable package when the user installed a copy.
        # Same-path unpacked installs keep their ID when source is updated.
        for file in self.source.rglob('*'):
            if file.is_file() and file.suffix.lower() in {'.js','.json','.html','.css'}:
                trusted[file.relative_to(self.source)]=hashlib.sha256(file.read_bytes()).digest()
        result=set()
        for profile in root.iterdir():
            if not profile.is_dir() or not re.fullmatch(r'Default|Profile \d+',profile.name): continue
            if config.get('chrome_profile_directory') and profile.name!=config['chrome_profile_directory']: continue
            settings={}
            for name in ('Preferences','Secure Preferences'):
                settings.update(read_json(profile/name).get('extensions',{}).get('settings',{}))
            for ident,entry in settings.items():
                if not re.fullmatch('[a-p]{32}',ident) or entry.get('state') not in (None,1) or entry.get('disable_reasons'): continue
                value=entry.get('path')
                if not value: continue
                folder=Path(value)
                if not folder.is_absolute(): folder=profile/'Extensions'/folder
                folder=folder.resolve()
                try:
                    # Previous immutable packages in this application's own
                    # deliverables remain identifiable so an older loaded worker
                    # can report its version and show the normal upgrade notice.
                    known_artifact=(folder.parent==(self.source.parent/'deliverables').resolve()
                        and re.fullmatch(r'SmartFlow_AI_Extension_\d+\.\d+\.\d+',folder.name)
                        and read_json(folder/'manifest.json').get('name')=='SmartFlow AI'
                        and folder.name=='SmartFlow_AI_Extension_'+str(read_json(folder/'manifest.json').get('version','')))
                    if folder==self.source or known_artifact or (trusted and all(
                        hashlib.sha256((folder/relative).read_bytes()).digest()==digest
                        for relative,digest in trusted.items())):
                        result.add(ident)
                except OSError:
                    continue
        return result
