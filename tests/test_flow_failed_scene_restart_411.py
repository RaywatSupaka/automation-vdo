"""Explicit failed-scene restart must reach a new helper, not legacy Home review."""
import copy
import subprocess
import threading
import unittest
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from core.atomic_json import AtomicJsonFile
from core.flow_review import completed_proposal_error, restartable_proposal_review
from core.cancellable_process import hidden_process_kwargs
from ui.story_flow_resume import start_saved_flow_scene
import test_flow_repair_resume_400 as repair_fixture


ERROR = 'ChatGPT Web ไม่ได้ตอบข้อมูล JSON ตามรูปแบบที่โปรแกรมต้องใช้'


class FailedSceneRestart411Tests(unittest.TestCase):
    setUp = repair_fixture.FlowRepairResume400.setUp
    act = repair_fixture.FlowRepairResume400.act
    image = repair_fixture.FlowRepairResume400.image
    proof = repair_fixture.FlowRepairResume400.proof
    manual = repair_fixture.FlowRepairResume400.manual

    def prepared(self):
        old = self.manual(error=ERROR)
        self.store = AtomicJsonFile(self.folder / 'prompts/flow_recovery.json')
        data = self.store.read({})
        data['scenes']['1'].pop()  # Fixture's successor has not been dispatched yet.
        for row in data['scenes']['1']:
            if row.get('request_id') == old:
                row.setdefault('phase', 'requested')  # Real audit always includes phase.
        data['scenes']['1'][-1].update(project_path='/project/old', original_prompt='original', at='2026-09-22')
        self.store.write(data)
        self.rows = data['scenes']['1']
        self.permit = AtomicJsonFile(self.folder / 'prompts/flow_manual_resume.json').read({})
        self.job.update(status='error', last_error='FLOW_REPAIR_REVIEW • '+ERROR,
                        scene_pipeline_version=1, video_generation_mode='google_flow', scene_count=2,
                        audio_choices={'mode': 'none'})
        return old

    def test_extension_new_scene_transaction_and_legacy_red(self):
        result = subprocess.run(['node', 'tests/flow_failed_scene_restart_411.cjs'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=45, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_completed_errors_only(self):
        for provider in ('ChatGPT Web', 'Gemini Web'):
            self.assertTrue(completed_proposal_error(ERROR.replace('ChatGPT Web', provider)))
        for error in ('unknown Send', 'Login required', ERROR+' uncertain', 'FLOW_ALTERNATIVE_FORMAT_OWNER_REVIEW'):
            self.assertFalse(completed_proposal_error(error))

    def test_backend_archives_old_failed_proposal_once(self):
        old = self.manual(error=ERROR)
        image = (self.folder / self.job['generated_images'][0]).read_bytes()
        row = self.act('begin')['replacement']
        self.assertNotEqual(row['request_id'], old)
        self.assertEqual(self.act('begin')['replacement'], row)
        saved = AtomicJsonFile(self.folder / 'prompts/flow_replacement.json').read({})
        self.assertEqual(len(saved['history']['1']), 1)
        self.assertEqual(saved['history']['1'][0]['request_id'], old)
        self.assertEqual((self.folder / self.job['generated_images'][0]).read_bytes(), image)

    def test_backend_does_not_rotate_uncertain_image(self):
        self.manual(error=ERROR, stage='image_sent')
        with self.assertRaises(ValueError):
            self.act('begin')

    def test_read_only_desktop_proof_preserves_all_files(self):
        self.prepared()
        before = {p: p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}
        self.assertEqual(restartable_proposal_review(self.folder, self.job, 1, self.permit)['error'], ERROR)
        self.assertEqual(before, {p: p.read_bytes() for p in self.folder.rglob('*') if p.is_file()})

    def test_proof_rejects_newer_or_uncertain_work(self):
        self.prepared()
        for mode in ('digest', 'request', 'job', 'index', 'image', 'submitted', 'fresh', 'newer', 'unknown-error', 'path'):
            with self.subTest(mode=mode):
                rows = copy.deepcopy(self.rows); permit = dict(self.permit)
                if mode in {'digest', 'request', 'job', 'index'}:
                    permit[{'digest': 'event_digest', 'request': 'request_id', 'job': 'job_id', 'index': 'index'}[mode]] = 'wrong'
                if mode == 'image': rows[-1]['alternative_stage'] = 'image_sent'
                if mode == 'submitted': rows.insert(-1, {**rows[-1], 'phase': 'submitted'})
                if mode == 'fresh': rows[-1]['fresh_project'] = {'phase': 'opening'}
                if mode == 'newer': rows.append({**rows[-1], 'request_id': 'newer'})
                if mode == 'unknown-error': rows[-1]['error'] = 'unknown Send'
                if mode == 'path': rows[-1]['project_path'] = '//foreign.invalid'
                self.store.write({'scenes': {'1': rows}})
                self.assertIsNone(restartable_proposal_review(self.folder, self.job, 1, permit))

    def test_proof_rejects_saved_image_completed_clip_and_cancel(self):
        self.prepared()
        for patch in ({'flow_clips': {'1': 'ready.mp4'}}, {'final_video_path': 'final.mp4'},
                      {'cancel_requested': True}, {'status': 'deleted'}):
            self.assertIsNone(restartable_proposal_review(self.folder, {**self.job, **patch}, 1, self.permit))
        store = AtomicJsonFile(self.folder / 'prompts/flow_replacement.json'); data = store.read({})
        for patch in ({'phase': 'image_saved'}, {'image_file': 'new.png'}, {'request_id': 'newer'}, {'revision': {'ready': True}}):
            changed = copy.deepcopy(data); changed['scenes']['1'].update(patch); store.write(changed)
            self.assertIsNone(restartable_proposal_review(self.folder, self.job, 1, self.permit))

    def app(self):
        self.prepared(); calls = []
        class Root:
            def __truediv__(inner, name): return self.folder
        app = SimpleNamespace(_story_cancel_event=threading.Event(), _story_pipeline_job_id='',
            _story_scene_threads={}, cfg={}, events=Queue(),
            story_job_id=SimpleNamespace(set=lambda _: None),
            stories=SimpleNamespace(root=Root(), get=lambda _: self.job,
                load_analysis_checkpoint=lambda _: {'saved': True}, reset_recovery_attempts=lambda _: None,
                prepare_scene_pipeline=lambda *a: self.job, mark_running=lambda *a: calls.append(('running', a))),
            bridge=SimpleNamespace(queue_extension_command=lambda *a: calls.append(('command', a))),
            root=SimpleNamespace(after=lambda *a: calls.append(('after', a))),
            _compatible_extension=lambda: ({}, True), _close_story_progress=lambda: None,
            _show_story_progress=lambda _: None, _update_story_progress=lambda p: calls.append(('progress', p)),
            _start_story_scene_worker=lambda p: calls.append(('worker', p)))
        return app, calls

    def test_actual_desktop_resume_routes_only_failed_scene(self):
        from ui.main_window import MainWindow
        app, calls = self.app()
        self.job['flow_clips'] = {'2': 'already-completed.mp4'}
        MainWindow._retry_story_job(app, self.job['id'])
        workers = [c[1] for c in calls if c[0] == 'worker']
        self.assertEqual(len(workers), 1); self.assertEqual(workers[0]['index'], 1)
        self.assertTrue(workers[0]['desktop_saved_resume'])
        self.assertTrue(workers[0]['desktop_scene_rebuild'])
        self.assertFalse(any(c[0] == 'command' for c in calls))
        self.assertIn('กำลังเริ่มฉากที่ล้มเหลวใหม่', next(c[1]['message'] for c in calls if c[0] == 'progress'))
        self.assertEqual(self.job['flow_clips'], {'2': 'already-completed.mp4'})

    def test_existing_worker_and_cancel_do_not_start_another(self):
        app, calls = self.app(); app._story_cancel_event.set()
        self.assertFalse(start_saved_flow_scene(app, self.job, self.permit))
        app._story_cancel_event.clear()
        app._story_scene_threads[(self.job['id'], 1)] = SimpleNamespace(is_alive=lambda: True)
        with self.assertRaises(ValueError): start_saved_flow_scene(app, self.job, self.permit)
        self.assertFalse(any(c[0] == 'worker' for c in calls))


if __name__ == '__main__':
    unittest.main()
