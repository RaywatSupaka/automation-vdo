"""Exact pre-send Story prompt evidence on an isolated local bridge."""
import copy
import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.story_manager import StoryManager

ROOT = Path(__file__).resolve().parents[1]


class StoryImageRequestAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        products = ProductManager(Path(temp.name))
        self.stories = StoryManager(products.project_root)
        self.job = self.stories.create('ทดสอบภาพจากข้อความ', scene_count=6)
        self.bridge = LocalBridge('127.0.0.1', 0, products, logging.getLogger('story-audit-test')).start()
        self.bridge.stories = self.stories
        self.addCleanup(self.bridge.stop)
        self.base = f'http://127.0.0.1:{self.bridge.server.server_address[1]}'
        self.run = self.bridge._resolve_extension_run_id('open_story_chatgpt', self.job['id'], 0)
        self.post('/api/extension/heartbeat', {'client_id':'audit-test','version':LocalBridge.REQUIRED_EXTENSION_VERSION})
        self.snapshot = dict(schema_version=1, scene_index=1, attempt=1, input_kind='text_to_image',
            source_count=0, prompt='สร้างภาพใหม่จากข้อความ 🐈\n\nฉากในสวน', composer_text='สร้างภาพใหม่จากข้อความ 🐈\n\nฉากในสวน',
            source_attachment_count=0, attachment_scope='composer', source_attachment_busy=False,
            source_attachment_failed=False, image_expansion_open=False, send_button_enabled=True,
            visible_mode_labels=[], entry_mode='not_exposed')
        self.folder = self.stories.root / self.job['id']

    def post(self, route, payload):
        req = urllib.request.Request(self.base+route, data=json.dumps(payload).encode(),
                                     headers={'Content-Type':'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    def progress(self, **extra):
        return self.post('/api/extension/progress', dict(scope='chatgpt',client_id='audit-test',
            job_id=self.job['id'],run_id=self.run,provider='chatgpt',step='image_prompt_ready',
            message='audit snapshot',image_request=self.snapshot, **extra))

    def trace(self):
        return [json.loads(line) for line in (self.folder/'logs/extension_trace.jsonl').read_text(encoding='utf-8').splitlines()]

    def test_persisted_before_ack_with_exact_text_hashes_and_no_job_mutation(self):
        before = (self.folder/'job.json').read_bytes()
        self.snapshot['unrelated_token'] = 'DO_NOT_COPY_ARBITRARY_FIELDS'
        reply = self.progress()
        self.assertTrue(reply['ok'])
        item = self.trace()[-1]
        detail = item['detail']
        self.assertEqual(item['run_id'],self.run)
        self.assertEqual(detail['prompt'],self.snapshot['prompt'])
        self.assertEqual(detail['composer_text'],self.snapshot['composer_text'])
        self.assertEqual(detail['prompt_sha256'],hashlib.sha256(self.snapshot['prompt'].encode()).hexdigest())
        self.assertTrue(detail['composer_matches'])
        self.assertNotIn('unrelated_token',detail)
        self.assertEqual((self.folder/'job.json').read_bytes(),before)

    def test_changed_composer_is_recorded_truthfully(self):
        self.snapshot['composer_text']='different draft'
        self.progress()
        self.assertFalse(self.trace()[-1]['detail']['composer_matches'])

    def test_same_length_requests_and_repeated_snapshot_are_not_silently_dropped(self):
        for text in ('first prompt','other prompt','other prompt'):
            self.snapshot.update(prompt=text,composer_text=text)
            self.progress()
        self.assertEqual([x['detail']['prompt'] for x in self.trace()],['first prompt','other prompt','other prompt'])

    def test_disk_failure_never_acknowledges_even_duplicate_then_can_recover(self):
        with patch('core.local_bridge.os.fsync', side_effect=OSError('test disk failed')):
            for _ in range(2):
                with self.assertRaises(urllib.error.HTTPError):
                    self.progress()
        self.assertTrue(self.progress()['ok'])
        self.assertEqual(self.trace()[-1]['detail']['prompt'],self.snapshot['prompt'])

    def test_stamped_outbox_retry_requires_durable_ack(self):
        for scope in ('chatgpt', 'flow'):
            payload = dict(scope=scope, client_id='audit-test', job_id=self.job['id'],
                           run_id=self.run, tab_id=12, step='waiting_for_image',
                           observed_at_ms=100, message='pending durable status')
            with patch.object(self.bridge, '_record_extension_trace', side_effect=OSError('disk unavailable')):
                for _ in range(2):
                    with self.assertRaises(urllib.error.HTTPError):
                        self.post('/api/extension/progress', payload)
            reply = self.post('/api/extension/progress', payload)
            self.assertTrue(reply['ok'])
            self.assertFalse(reply.get('ignored', False))
            self.assertEqual(self.trace()[-1]['message'], 'pending durable status')
            self.assertTrue(self.post('/api/extension/progress', payload)['ignored'])

    def test_invalid_fields_rejected_and_do_not_create_prompt_log(self):
        for field,value in [('schema_version',True),('scene_index',0),('attempt',0),('source_count',True),
                            ('input_kind','reference_image'),('prompt',''),('composer_text','x'*100001),
                            ('source_attachment_busy',1),('visible_mode_labels',['x']*9),('attachment_scope','secret')]:
            with self.subTest(field=field):
                broken = copy.deepcopy(self.snapshot); broken[field]=value
                with self.assertRaises(ValueError):
                    self.bridge._safe_story_image_request({'image_request':broken})
        self.snapshot['schema_version']=True
        with self.assertRaises(urllib.error.HTTPError): self.progress()
        self.assertFalse((self.folder/'logs/extension_trace.jsonl').exists())

    def test_reference_source_and_visible_labels_are_preserved(self):
        self.snapshot.update(source_count=1,input_kind='reference_image',source_attachment_count=1,
                             visible_mode_labels=['Images'],entry_mode='visible_labels')
        self.progress()
        self.assertEqual(self.trace()[-1]['detail']['visible_mode_labels'],['Images'])
        self.assertEqual(self.trace()[-1]['detail']['input_kind'],'reference_image')

    def test_long_job_scene_50_and_retry_4_cross_http_and_durable_trace(self):
        self.job = self.stories.create('คลิปยาวฉาก 50', long_video={'version': 2, 'scene_count': 50})
        self.folder = self.stories.root / self.job['id']
        self.run = self.bridge._resolve_extension_run_id('open_story_chatgpt', self.job['id'], 0)
        self.snapshot.update(scene_index=50, attempt=4)
        self.assertTrue(self.progress()['ok'])
        self.assertEqual(self.trace()[-1]['detail']['scene_index'], 50)
        self.assertEqual(self.trace()[-1]['detail']['attempt'], 4)
        self.snapshot['scene_index'] = 51
        with self.assertRaises(urllib.error.HTTPError):
            self.progress()
        self.assertEqual(len(self.trace()), 1)

    def test_missing_job_does_not_acknowledge_audit(self):
        with self.assertRaises(ValueError):
            self.bridge._record_extension_trace(dict(job_id='STORY-MISSING',action='image_prompt_ready',detail=self.snapshot))

    def test_trace_entry_cannot_bypass_snapshot_validation(self):
        with self.assertRaises(ValueError):
            self.bridge._record_extension_trace(dict(job_id=self.job['id'],action='image_prompt_ready',detail={'token':'not allowed'}))

    def test_actual_extension_audit_harness(self):
        node=shutil.which('node')
        if not node: self.skipTest('Node required')
        result=subprocess.run([node,str(ROOT/'tests/story_image_request_audit_harness.js')],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['cases'],14)


if __name__=='__main__': unittest.main()
