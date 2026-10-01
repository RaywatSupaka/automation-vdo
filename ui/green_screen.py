from core.config import ROOT
from core.green_screen import GreenLibrary


def capture_green(app, value):
    return GreenLibrary(ROOT, app.cfg.get('ffmpeg_path', '')).validate(value)
