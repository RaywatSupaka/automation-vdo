"""Cover preparation evidence, FIFO preservation and UI; isolated files only."""
import base64
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image
from core.ai_cover import AICovers
from core.atomic_json import AtomicJsonFile
from core.creation_queue import CreationQueue
from ui.creation_queue import CreationQueueMixin


class AICoverPreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.job = 'STORY-COVER-PREPARATION'
        self.stories = SimpleNamespace(root=self.root/'stories')
        self.folder = self.stories.root/self.job
        self.folder.mkdir(parents=True)
        self.video = self.folder/'final.mp4'
        self.video.write_bytes(b'keep final and all existing scenes')
        Image.new('RGB', (576, 1024), 'blue').save(self.folder/'scene.jpg')
        self.manifest = AtomicJsonFile(self.folder/'job.json')
        self.manifest.write(dict(id=self.job, job_type='story_short', status='ready',
            video_status='ready', video_path='final.mp4', video_title='เรื่องเดิม',
            generated_images=['scene.jpg'], image_ai_provider='chatgpt',
            ai_cover_options={'enabled':True}))
        self.service = AICovers(SimpleNamespace(root=self.root/'products'), self.stories)
        self.rid = self.service.request(self.job)['request_id']
        self.service.event(self.rid, {'phase':'claimed'})

    def proof(self, **changes):
        return dict(stage='image_tool', reason='opener_disabled', attempt=1,
                    not_dispatched=True, request_id=self.rid, **changes)

    def prepare(self, phase='preparing', **changes):
        return self.service.event(self.rid, dict(phase=phase,
            preparation_state={**self.proof(), **changes}, error_code='AI_SEND_NOT_READY',
            notDispatched=True, active=True, message='กำลังเตรียมสร้างปก'))

    def image(self):
        buffer = io.BytesIO()
        Image.new('RGB', (576, 1024), 'red').save(buffer, 'PNG')
        return 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()

    def test_preparation_waits_preserves_final_and_round_trips_bounded_proof(self):
        row = self.prepare(reason='opener_missing', prompt='must not persist')
        expected = {**self.proof(), 'reason':'opener_missing'}
        self.assertEqual(row['preparation_state'], expected)
        self.assertEqual(self.manifest.read()['ai_cover_state']['preparation_state'], expected)
        self.assertEqual(self.manifest.read()['ai_cover_state']['error_code'], 'AI_SEND_NOT_READY')
        self.assertTrue(self.manifest.read()['ai_cover_state']['notDispatched'])
        completion = self.service.completion(self.job)
        self.assertTrue(completion['waiting'])
        self.assertFalse(completion['ready'])
        self.assertIn('กำลังเตรียมสร้างปก', completion['message'])
        self.prepare('recovering', attempt=1000)
        self.assertEqual(self.service.active()[0]['request_id'], self.rid)
        self.assertEqual(self.service.pending(), [])
        self.assertEqual(self.video.read_bytes(), b'keep final and all existing scenes')

    def test_tool_ready_is_not_a_send_or_saved_cover(self):
        self.prepare('recovering')
        row = self.service.event(self.rid, {'phase':'running',
            'preparation_state':{**self.proof(), 'reason':'ready'}})
        self.assertTrue(row['notDispatched'])
        self.assertNotIn('error_code', row)
        self.assertNotIn('send_state', row)
        self.assertFalse(self.service.completion(self.job)['ready'])
        self.assertNotIn('cover_path', self.manifest.read())

    def test_invalid_preparation_is_atomic_and_does_not_become_resend_proof(self):
        self.prepare()
        saved = self.service.get(self.rid)
        for change in ({'request_id':'other'}, {'stage':'send'}, {'reason':'unknown'},
                       {'reason':[]}, {'attempt':True}, {'attempt':-1}, {'attempt':0},
                       {'attempt':1000001}, {'not_dispatched':False}, {'not_dispatched':'true'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.service.event(self.rid, {'phase':'recovering',
                    'preparation_state':{**self.proof(), **change}})
            self.assertEqual(self.service.get(self.rid), saved)
        for event in ({'phase':'recovering','error_code':'arbitrary'},
                      {'phase':'running','notDispatched':'true'}):
            with self.assertRaises(ValueError):self.service.event(self.rid,event)
        self.assertEqual(self.service.get(self.rid), saved)

    def test_unstructured_pre_send_claim_is_rejected(self):
        for event in ({'phase':'recovering'}, {'phase':'preparing'},
                      {'phase':'needs_review','notDispatched':True}):
            with self.assertRaises(ValueError):self.service.event(self.rid,event)
        self.assertEqual(self.service.get(self.rid)['phase'], 'claimed')

    def test_send_state_clears_unsent_claim_and_prevents_later_preparation(self):
        self.prepare()
        row = self.service.event(self.rid, {'phase':'running','send_state':'unconfirmed'})
        self.assertFalse(row['notDispatched'])
        self.assertFalse(row['preparation_state']['not_dispatched'])
        self.assertNotIn('error_code',row)
        self.assertFalse(self.manifest.read()['ai_cover_state']['notDispatched'])
        for send_state in ('unconfirmed', 'accepted'):
            self.service.event(self.rid, {'phase':'running','send_state':send_state})
            with self.assertRaises(ValueError):self.prepare('recovering',attempt=2)
        self.service.event(self.rid, {'phase':'needs_review'})
        self.service.recover_result(self.rid,self.job)
        self.assertTrue(self.service.package(self.rid)['collect_only'])
        self.assertNotIn('source_images',self.service.package(self.rid))

    def test_dispatch_evidence_cannot_be_erased_to_authorize_preparation(self):
        for evidence in ({'dispatch_completed':True}, {'trusted_click_seen':True},
                         {'release_on_send_target':True}, {'gesture_phase':'pressed'},
                         {'gesture_phase':'released'}, {'gesture_phase':'release_uncertain'}):
            with self.subTest(evidence=evidence):
                row=self.service.request(self.job,force=True)
                rid=row['request_id']
                if row['phase']=='queued':self.service.event(rid,{'phase':'claimed'})
                self.service.event(rid,{'phase':'running','send_diagnostics':evidence})
                self.service.event(rid,{'phase':'running','send_diagnostics':{
                    'dispatch_completed':False,'trusted_click_seen':False,
                    'release_on_send_target':False,'gesture_phase':'not_started'}})
                with self.assertRaises(ValueError):
                    self.service.event(rid,{'phase':'recovering',
                        'preparation_state':{**self.proof(),'request_id':rid}})
                self.service.event(rid,{'phase':'needs_review'})

    def test_incoming_send_or_result_cannot_coexist_with_unsent_proof(self):
        for evidence in ({'send_state':'accepted'}, {'send_state':'unconfirmed'},
                         {'send_diagnostics':{'gesture_phase':'pressed'}},
                         {'collector_state':{'stage':'downloading','owned':True,'candidates':1,'loaded':1}},
                         {'result_proof':{'request_id':self.rid,'scope':'latest_assistant_turn',
                                          'images':1,'width':576,'height':1024}},
                         {'retry_count':1}):
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                self.service.event(self.rid,{'phase':'recovering',
                    'preparation_state':self.proof(),**evidence})
        self.assertEqual(self.service.get(self.rid)['phase'],'claimed')

    def test_saved_image_can_finish_recovery_and_only_then_release_gate(self):
        for phase in ('preparing','recovering'):
            row=self.service.request(self.job,force=True)
            self.rid=row['request_id']
            if row['phase']=='queued':self.service.event(self.rid,{'phase':'claimed'})
            self.prepare(phase)
            with self.assertRaises(ValueError):self.service.event(self.rid,{'phase':'ready'})
            self.assertFalse(self.service.completion(self.job)['ready'])
            self.service.event(self.rid,{'phase':'ready','image':self.image()})
            self.assertTrue(self.service.completion(self.job)['ready'])
            self.assertFalse(self.service.get(self.rid)['notDispatched'])
        self.assertEqual(self.video.read_bytes(), b'keep final and all existing scenes')

    def test_explicit_unsent_retry_keeps_old_record_and_never_collects_nonexistent_reply(self):
        self.prepare()
        self.service.event(self.rid,{'phase':'needs_review'})
        old=self.service.get(self.rid)
        with self.assertRaises(ValueError):self.service.recover_result(self.rid,self.job)
        successor=self.service.request(self.job,force=True)
        self.assertNotEqual(successor['request_id'],self.rid)
        self.assertEqual(self.service.get(self.rid),old)
        self.assertEqual(successor['sources'],old['sources'])
        self.assertEqual(successor['title'],old['title'])
        self.assertEqual(successor['provider'],old['provider'])
        self.assertNotIn('preparation_state',successor)
        self.assertEqual(self.video.read_bytes(), b'keep final and all existing scenes')

    def test_recovering_keeps_fifo_owner_and_manual_pause(self):
        queue=CreationQueue(self.root)
        queue.enqueue('story',['เรื่องเดิม','เรื่องต่อไป'])
        queue.resume()
        item=queue.claim_next()
        queue._update(item['queue_id'],job_id=self.job)
        app=CreationQueueMixin()
        app.story_queue=queue
        app.bridge=SimpleNamespace(ai_covers=self.service)
        app.status=Mock()
        app._desktop_set_notice=Mock()
        app._schedule_next_story_queue_item=Mock()
        self.prepare('recovering')
        self.assertFalse(app._creation_cover_gate(self.job))
        self.assertFalse(queue.snapshot()['paused'])
        self.assertIsNone(queue.claim_next())
        queue.pause('user_pause')
        self.assertFalse(app._creation_cover_gate(self.job))
        self.assertEqual(queue.snapshot()['pause_reason'],'user_pause')
        self.service.event(self.rid,{'phase':'ready','image':self.image()})
        self.assertTrue(app._creation_cover_gate(self.job))
        self.assertEqual(queue.snapshot()['pause_reason'],'user_pause')
        self.assertEqual(queue.item_for_job(self.job)['job_id'],self.job)

    def test_cover_recovery_ui_uses_typed_pre_send_state(self):
        env=dict(os.environ)
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result=subprocess.run(['node','tests/cover_preparation_ui.cjs'],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,
            encoding='utf-8',env=env,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
