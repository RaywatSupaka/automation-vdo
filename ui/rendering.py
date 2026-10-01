"""Owned render sessions: local progress only; never dispatch Extension work."""
from functools import wraps
from core.render_backend import render_session, has_render_session


def story_render(method):
    @wraps(method)
    def wrapped(self, job_id, job, voice, cancel_event):
        folder = self.stories.root / job_id
        def progress(message):
            phase = state.get('ui_phase', 'compose')
            self._queue_story_phase(job_id, cancel_event, phase, {
                'percent': 88, 'stage': 'finishing' if phase == 'finish' else 'video', 'message': message,
                'detail': 'ประมวลผลไฟล์ในเครื่อง • ไม่สร้างฉาก AI ซ้ำ'})
        with render_session(job.get('render_snapshot'), progress, folder/'logs'/'render-local.json') as state:
            return method(self, job_id, job, voice, cancel_event)
    return wrapped


def product_render(method):
    @wraps(method)
    def wrapped(self, job_id, *args, **kwargs):
        if has_render_session():
            return method(self, job_id, *args, **kwargs)
        job = self.products.get_job(job_id)
        folder = self.products.root / job_id
        def progress(message):
            self._product_progress_event(job_id, 88, 'finishing', message,
                                         'ประมวลผลไฟล์ในเครื่อง • ไม่สร้างฉาก AI ซ้ำ')
        with render_session(job.get('render_snapshot'), progress, folder/'logs'/'render-local.json'):
            return method(self, job_id, *args, **kwargs)
    return wrapped
