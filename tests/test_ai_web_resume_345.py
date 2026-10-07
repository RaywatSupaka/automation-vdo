import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.ai_web_resume import ai_web_resume_target, conversation_url, pre_send_bootstrap_failure, request_hash
from core.atomic_json import AtomicJsonFile
from core.flow_motion_plan import motion_plan_action, plan_context
from core.story_manager import StoryManager
from core.story_pipeline import story_recovery_action
from core.story_failure_timeline import story_failure_timeline

ROOT = Path(__file__).resolve().parents[1]


class AiWebResume345Tests(unittest.TestCase):
    def test_real_background_routes_and_content_reader(self):
        result = subprocess.run([shutil.which('node'), 'tests/ai_web_resume_345_harness.js'],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['cases'], 19)

    def test_pending_motion_navigation_for_product_story_and_drama(self):
        for kind in ('product', 'story', 'drama'):
            for provider in ('chatgpt', 'gemini'):
                with self.subTest(kind=kind, provider=provider), tempfile.TemporaryDirectory() as temp:
                    folder = Path(temp)
                    (folder / 'generated').mkdir()
                    filename = 'selling_image_01.png' if kind == 'product' else 'scene_01.png'
                    image = folder / 'generated' / filename
                    image.write_bytes(b'unchanged canonical image')
                    job = dict(id='JOB-345' if kind == 'product' else 'STORY-345', image_ai_provider=provider,
                               scene_narrations=['A person walks'], scene_prompts=['A person standing'],
                               image_prompts=['A product on a table'], flow_shot_prompts=['Slow camera move'],
                               video_generation_mode='google_flow')
                    if kind == 'drama':
                        job.update(series_id='SERIES-345', episode_number=1)
                    context = plan_context(folder, job, 1)
                    store = AtomicJsonFile(folder / 'prompts/flow_motion_plans.json')
                    store.write({'schema': 1, 'plans': {context['context_id']: dict(context=context, phase='requested', request='original')}})
                    url = ('https://gemini.google.com/app/aaaaaaaaaaaa0345' if provider == 'gemini'
                           else 'https://chatgpt.com/c/fixture-345')
                    (folder / 'logs').mkdir()
                    (folder / 'logs/extension_trace.jsonl').write_text(json.dumps(dict(job_id=job['id'], step='error', page_url=url)), encoding='utf-8')
                    original = store.path.read_bytes() if hasattr(store, 'path') else (folder / 'prompts/flow_motion_plans.json').read_bytes()
                    target = ai_web_resume_target(folder, job)
                    self.assertEqual(target['conversation_url'], url)
                    self.assertEqual(target['context_id'], context['context_id'])
                    self.assertEqual(target['stage'], 'motion')
                    self.assertEqual((folder / 'prompts/flow_motion_plans.json').read_bytes(), original)
                    self.assertEqual(image.read_bytes(), b'unchanged canonical image')
                    data = store.read()
                    data['plans'][context['context_id']]['phase'] = 'ready'
                    store.write(data)
                    self.assertIsNone(ai_web_resume_target(folder, job))

    def test_verified_sender_url_is_durable_but_status_does_not_rebind(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'generated').mkdir()
            (folder / 'generated/scene_01.png').write_bytes(b'canonical image')
            job = dict(id='STORY-345', image_ai_provider='gemini', scene_narrations=['A person walks'])
            context = plan_context(folder, job, 1)
            def call(action, **extra):
                return motion_plan_action(folder, job, dict(action=action, provider='gemini', index=1,
                                                           context_id=context['context_id'], **extra))
            url = 'https://gemini.google.com/app/aaaaaaaaaaaa0345'
            call('prepare', request='Original motion request')
            call('mark_sending', page_url=url)
            self.assertEqual(call('status', page_url='https://gemini.google.com/app/bbbbbbbbbbbb0345')['record']['conversation_url'], url)
            self.assertEqual(ai_web_resume_target(folder, job)['conversation_url'], url)
            with self.assertRaises(ValueError):
                call('mark_sending', page_url='https://gemini.google.com/app/bbbbbbbbbbbb0345')
            self.assertEqual(call('status')['record']['conversation_url'], url)

    def test_analysis_request_survives_running_and_repeated_package_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create('แมวน้อยกับไอติม', scene_count=6, image_ai_provider='gemini')
            folder = manager.root / job['id']
            manager.mark_failed(job['id'], 'chatgpt', 'GEMINI_TEXT_REQUEST_REVIEW')
            (folder / 'logs').mkdir(exist_ok=True)
            (folder / 'logs/extension_trace.jsonl').write_text(json.dumps(dict(job_id=job['id'], step='error',
                page_url='https://gemini.google.com/app/aaaaaaaaaaaa0345')), encoding='utf-8')
            before = ai_web_resume_target(folder, manager.get(job['id']))
            self.assertIn(job['id'], before['request'])
            self.assertIn('scene_prompts จำนวน 6', before['request'])
            request_file = folder / json.loads((folder / 'ai_request.json').read_text(encoding='utf-8'))['prompt_file']
            original = request_file.read_bytes()
            manager.mark_running(job['id'])
            for _ in range(2):
                package = manager.plugin_request(job['id'])
                self.assertEqual(package['ai_resume'], before)
                self.assertEqual(request_file.read_bytes(), original)

    def test_pre_send_bootstrap_review_does_not_create_an_empty_url_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create('นักไวโอลินกับทำนองที่ไม่มีใครจำได้', scene_count=6,
                                 image_ai_provider='chatgpt')
            folder = manager.root / job['id']
            trace_path = folder / 'logs/extension_trace.jsonl'
            trace_path.parent.mkdir(exist_ok=True)
            first_run = 'RUN-BOOTSTRAP-ONE'
            rows = [
                dict(job_id=job['id'], run_id=first_run, action='error', page_url='',
                     message='AI_WEB_WAIT_REVIEW • ไฟล์แนบที่ยืนยันเจ้าของไม่ได้ • ยังไม่ส่งคำขอ'),
                dict(job_id=job['id'], run_id=first_run, action='story_bootstrap_review', page_url='',
                     detail={'reason': 'attachment_present'}),
                dict(job_id=job['id'], run_id='RUN-BOOTSTRAP-TWO', action='error', page_url='',
                     message='AI_WEB_RESUME_REVIEW • ต้องกลับไปอ่านคำขอเดิม'),
            ]
            trace_path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows), encoding='utf-8')
            manager.mark_failed(job['id'], 'chatgpt', rows[-1]['message'])
            stale = dict(required=True, stage='analysis', provider='chatgpt', conversation_url='',
                         request='unsent original request', evidence='job_trace')
            manifest = manager.get(job['id'])
            manifest['ai_resume_checkpoint'] = stale
            manager._save(manifest)
            request = json.loads((folder / 'ai_request.json').read_text(encoding='utf-8'))
            prompt = folder / request['prompt_file']
            original = prompt.read_bytes()
            self.assertTrue(pre_send_bootstrap_failure(folder, manifest))
            self.assertIsNone(ai_web_resume_target(folder, manifest))
            self.assertIn('trace ที่บันทึกยังไม่ยืนยันว่าเว็บรับคำขอ',
                          story_failure_timeline(manager.root, job['id']))
            manager.mark_running(job['id'])
            self.assertNotIn('ai_resume_checkpoint', manager.get(job['id']))
            self.assertIsNone(manager.plugin_request(job['id'])['ai_resume'])
            self.assertEqual(prompt.read_bytes(), original)

            # Any evidence from the provider keeps the conservative old-turn
            # route; a bootstrap review alone cannot erase a possible Send.
            for extra in (dict(action='ai_send_accepted', page_url='https://chatgpt.com/c/owned'),
                          dict(action='analysis_request_claimed', page_url='')):
                with self.subTest(extra=extra['action']):
                    trace_path.write_text('\n'.join(json.dumps(row, ensure_ascii=False)
                        for row in [*rows, dict(job_id=job['id'], run_id='RUN-OTHER', **extra)]), encoding='utf-8')
                    guarded = {**manager.get(job['id']), 'ai_resume_checkpoint': stale}
                    self.assertFalse(pre_send_bootstrap_failure(folder, guarded))
                    self.assertEqual(ai_web_resume_target(folder, guarded), stale)

    def test_accepted_chatgpt_canonical_hydration_failure_reopens_only_owned_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create('สินค้าในครัว', scene_count=4, image_ai_provider='chatgpt')
            folder = manager.root / job['id']
            manager.mark_failed(job['id'], 'chatgpt', 'AI_WEB_RESUME_REVIEW • หน้าแชตเปลี่ยนระหว่างอ่านคำตอบ')
            saved_prompt = folder / json.loads((folder / 'ai_request.json').read_text(encoding='utf-8'))['prompt_file']
            original = saved_prompt.read_bytes()
            url = 'https://chatgpt.com/c/6ab3ef4c-70b0-83ec-a647-9d0a1008554d'
            accepted = dict(job_id=job['id'], run_id='RUN-OWNED', service='chatgpt',
                            shot_index=0, action='ai_send_accepted',
                            page_url='https://chatgpt.com/c/WEB:4ab4bfdd-2165-404f-99ae-afda0993ffde')
            failed = dict(job_id=job['id'], run_id='RUN-OWNED', service='chatgpt',
                          action='error', message='AI_WEB_RESUME_REVIEW • หน้าแชตเปลี่ยน', page_url=url)
            trace_path = folder / 'logs/extension_trace.jsonl'
            trace_path.parent.mkdir(exist_ok=True)
            def trace(*rows):
                trace_path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows), encoding='utf-8')
            trace(accepted, failed)
            target = ai_web_resume_target(folder, manager.get(job['id']))
            self.assertEqual((target['stage'], target['conversation_url'], target['provider']),
                             ('analysis', url, 'chatgpt'))
            self.assertTrue(target['required'])
            self.assertIn(job['id'], target['request'])
            self.assertIn('scene_prompts จำนวน 6', target['request'])
            manager.mark_running(job['id'])
            self.assertEqual(manager.plugin_request(job['id'])['ai_resume'], target)
            self.assertEqual(saved_prompt.read_bytes(), original)
            for rows in ((failed,), ({**accepted, 'run_id': 'RUN-OTHER'}, failed),
                         ({**accepted, 'shot_index': 1}, failed),
                         (accepted, {**failed, 'page_url': 'https://chatgpt.com/'})):
                trace(*rows)
                # A previous checkpoint is not the subject of these negative
                # cases; only the current failed run may create a new target.
                job_without_checkpoint = manager.get(job['id'])
                job_without_checkpoint.pop('ai_resume_checkpoint', None)
                self.assertIsNone(ai_web_resume_target(folder, job_without_checkpoint))
            self.assertEqual(saved_prompt.read_bytes(), original)

    def test_missing_owner_stop_cannot_auto_restart_and_url_allowlist(self):
        for code in ('GEMINI_TEXT_REQUEST_REVIEW', 'GEMINI_TEXT_SEND_REVIEW', 'AI_WEB_RESUME_REVIEW', 'AI_WEB_WAIT_REVIEW'):
            self.assertEqual(story_recovery_action({'scene_count': 6}, code), '')
        for url in ('https://chatgpt.com/', 'https://chatgpt.com.evil/c/1', 'https://gemini.google.com/app', 'file:///tmp/one'):
            self.assertEqual(conversation_url(url, 'chatgpt'), '')
            self.assertEqual(conversation_url(url, 'gemini'), '')
        self.assertEqual(request_hash(' \n Hello  world\t'), request_hash('Hello world'))
