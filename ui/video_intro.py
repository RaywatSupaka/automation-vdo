from core.config import ROOT
from core.video_intro import IntroLibrary


def capture_intro(app, value):
    return IntroLibrary(ROOT, app.cfg.get('ffmpeg_path', '')).validate(value)


def intro_action(app, action, payload):
    library = IntroLibrary(ROOT, app.cfg.get('ffmpeg_path', ''))
    if action == 'intro_status':
        return {'ok':True, **library.state()}
    if action == 'intro_save':
        return {'ok':True, **library.save(payload.get('settings'))}
    if action == 'intro_choose_file':
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=app.root, title='เลือกวิดีโออินโทร',
                                         filetypes=[('วิดีโออินโทร', '*.mp4 *.mov *.mkv *.webm *.m4v *.avi')])
        if not path:
            return {'ok':True, 'cancelled':True}
        return {'ok':True, **library.import_file(path)}
    raise ValueError('ไม่พบคำสั่งอินโทร')
