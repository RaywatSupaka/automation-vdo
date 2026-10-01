"""Run-scoped cleanup against a temporary real HTTP bridge, never the user port."""
import copy
import json
import logging
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


class ReadinessBridgeTests(unittest.TestCase):
    def test_profile_focus_preserves_job_state(self):
        runs = copy.deepcopy(self.bridge._extension_runs)
        clients = copy.deepcopy(self.bridge._extension_clients)
        queued = self.bridge.queue_extension_command('focus_browser')
        self.assertEqual(self.bridge._extension_commands[-1]['action'], 'focus_browser')
        self.assertEqual(self.bridge._extension_runs, runs)
        self.assertEqual(self.bridge._extension_clients, clients)
        self.bridge._extension_commands[-1].update(status='delivered', client_id='fixture', lease_token='focus-lease', lease_expires_at=time.time()+60)
        payload = dict(command_id=queued['id'], client_id='fixture', run_id=queued['run_id'], lease_token='focus-lease', ok=True)
        request = urllib.request.Request(self.base+'/api/extension/command-ack', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertTrue(json.load(response)['ok'])
        self.assertEqual(self.bridge._extension_runs, runs)
        self.assertEqual(self.bridge._extension_clients, clients)
        with self.assertRaises(ValueError):
            self.bridge.queue_extension_command('focus_browser', 'JOB-A')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bridge = LocalBridge('127.0.0.1', 0, ProductManager(Path(self.tmp.name)),
                                  logging.getLogger('readiness-bridge')).start()
        self.addCleanup(self.bridge.stop)
        self.base = f'http://127.0.0.1:{self.bridge.server.server_address[1]}'
        self.command = dict(id='CMD-CLOSE', action='close_automation_browser', job_id='JOB-A',
            run_id='RUN-OLD', status='delivered', client_id='fixture', lease_token='LEASE-TEST',
            lease_expires_at=time.time() + 60)
        self.bridge._extension_commands.append(self.command)
        self.bridge._extension_runs = {
            ('job', 'JOB-A', 0): {'run_id': 'RUN-OLD'},
            ('flow', 'JOB-A', 1): {'run_id': 'RUN-NEW'},
            ('ai', 'JOB-A', 0): {'run_id': 'RUN-NEW'},
            ('flow', 'JOB-B', 1): {'run_id': 'RUN-OTHER'},
        }
        self.bridge._extension_clients['fixture'] = {
            'version': self.bridge.REQUIRED_EXTENSION_VERSION, 'last_seen_epoch': time.time(),
            'ai_job_id': 'JOB-A', 'ai_run_id': 'RUN-NEW', 'ai_step': 'generating',
            'flow_job_id': 'JOB-A', 'flow_run_id': 'RUN-NEW', 'flow_step': 'generating',
        }

    def ack(self, **changes):
        payload = dict(command_id='CMD-CLOSE', client_id='fixture', run_id='RUN-OLD',
                       lease_token='LEASE-TEST', ok=True, **changes)
        req = urllib.request.Request(self.base + '/api/extension/command-ack',
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    def test_late_close_ack_preserves_new_run_and_other_job(self):
        client = copy.deepcopy(self.bridge._extension_clients['fixture'])
        self.assertTrue(self.ack()['ok'])
        self.assertEqual(self.bridge._extension_clients['fixture'], client)
        self.assertNotIn(('job', 'JOB-A', 0), self.bridge._extension_runs)
        self.assertEqual(self.bridge._extension_runs[('flow', 'JOB-A', 1)]['run_id'], 'RUN-NEW')
        self.assertEqual(self.bridge._extension_runs[('ai', 'JOB-A', 0)]['run_id'], 'RUN-NEW')
        self.assertIn(('flow', 'JOB-B', 1), self.bridge._extension_runs)
        self.assertTrue(self.ack()['duplicate'])
        self.assertEqual(self.bridge._extension_clients['fixture'], client)

    def test_current_close_ack_retires_only_matching_scope(self):
        client = self.bridge._extension_clients['fixture']
        client['ai_run_id'] = 'RUN-OLD'
        self.bridge._extension_runs[('ai', 'JOB-A', 0)]['run_id'] = 'RUN-OLD'
        self.ack()
        self.assertNotIn('ai_job_id', client)
        self.assertEqual(client['flow_run_id'], 'RUN-NEW')
        self.assertNotIn(('ai', 'JOB-A', 0), self.bridge._extension_runs)

    def test_saved_shot_ack_preserves_ai_and_next_shot_even_with_shared_run(self):
        self.command.update(cleanup_shot_index=1,cleanup_runs=['RUN-OLD'])
        self.bridge._extension_runs[('flow','JOB-A',1)]={'run_id':'RUN-OLD'}
        self.bridge._extension_runs[('flow','JOB-A',2)]={'run_id':'RUN-OLD'}
        self.bridge._extension_runs[('ai','JOB-A',0)]={'run_id':'RUN-OLD'}
        client=self.bridge._extension_clients['fixture']
        client.update(ai_run_id='RUN-OLD',flow_run_id='RUN-OLD',flow_shot_index=2)
        before=copy.deepcopy(client)
        self.ack()
        self.assertNotIn(('flow','JOB-A',1),self.bridge._extension_runs)
        self.assertIn(('flow','JOB-A',2),self.bridge._extension_runs)
        self.assertIn(('ai','JOB-A',0),self.bridge._extension_runs)
        self.assertEqual(client,before)

    def test_cancelled_command_cannot_be_completed_by_late_ack(self):
        self.command['status'] = 'cancelled'
        runs = copy.deepcopy(self.bridge._extension_runs)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.ack()
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.command['status'], 'cancelled')
        self.assertEqual(self.bridge._extension_runs, runs)

    def test_pending_command_with_old_lease_cannot_be_completed(self):
        self.command['status'] = 'pending'
        with self.assertRaises(urllib.error.HTTPError):
            self.ack()
        self.assertEqual(self.command['status'], 'pending')

    def test_close_snapshot_covers_existing_ai_flow_runs_not_later_resume(self):
        self.bridge.products.list_jobs = lambda: [{'id': 'JOB-A'}]
        self.bridge._extension_runs[('ai', 'JOB-A', 0)]['run_id'] = 'RUN-AI'
        queued = self.bridge.queue_extension_command('close_automation_browser', 'JOB-A', run_id='RUN-OLD')
        self.assertEqual(set(queued['cleanup_runs']), {'RUN-OLD', 'RUN-NEW', 'RUN-AI'})
        self.command['cleanup_runs'] = queued['cleanup_runs']
        self.bridge._extension_runs[('flow', 'JOB-A', 1)]['run_id'] = 'RUN-RESUMED'
        client = self.bridge._extension_clients['fixture']
        client.update(ai_run_id='RUN-AI', flow_run_id='RUN-RESUMED')
        self.ack()
        self.assertNotIn('ai_job_id', client)
        self.assertEqual(client['flow_run_id'], 'RUN-RESUMED')
        self.assertNotIn(('ai', 'JOB-A', 0), self.bridge._extension_runs)
        self.assertEqual(self.bridge._extension_runs[('flow', 'JOB-A', 1)]['run_id'], 'RUN-RESUMED')
