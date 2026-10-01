"""Actual callback dispatch and permanent-delete fences; temporary files only."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.atomic_json import AtomicJsonFile, runtime_backup_path
from core.job_file_guard import guard_for
from core.local_bridge import LocalBridge
from core.product_job_deletion import journal
from core.product_manager import ProductManager
from core.story_manager import StoryManager


class ProductDeleteCallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.products, self.stories = ProductManager(self.root), StoryManager(self.root)
        self.bridge = LocalBridge('127.0.0.1', 0, self.products, Mock(), stories=self.stories)
        self.guard = guard_for(self.root)
        self.guard.probe = None
        self.addCleanup(lambda: [claim.release() for claim in tuple(self.guard.claims)])
        # Capture the real Handler without binding a port or launching a thread.
        def server(_address, handler):
            self.handler = handler
            return SimpleNamespace(serve_forever=lambda: None)
        with patch('core.local_bridge.ThreadingHTTPServer', side_effect=server), patch('core.local_bridge.threading.Thread'):
            self.bridge.start()

    def deny(self, ident, state='deleted', request_id=''):
        data = {'version': 1, 'jobs': {ident: {'state': state}}, 'requests': {}}
        if request_id:
            data['jobs'][ident]['source_request_sha256'] = hashlib.sha256(request_id.encode()).hexdigest()
        journal(self.root).write(data)

    def post(self, path, body, *, authenticated=True):
        raw = json.dumps(body).encode()
        handler = object.__new__(self.handler)
        handler.path, handler.rfile = path, io.BytesIO(raw)
        handler.headers = {'Content-Length': str(len(raw)), 'Content-Type': 'application/json'}
        replies = []
        handler._send = lambda value, status=200: replies.append((status, value))
        def auth():
            if not authenticated:
                handler._send({'ok': False, 'error': 'unauthorized'}, 403)
            return authenticated
        handler._require_extension_request = auth
        handler.do_POST()
        self.assertEqual(len(replies), 1)
        self.assertFalse(self.guard.claims, 'all HTTP exit paths must release callback claims')
        return replies[0]

    def test_deleted_passive_report_is_terminal_ack_without_progress_mutation(self):
        self.deny('STORY-DELETED')
        original = dict(self.bridge._extension_clients)
        status, response = self.post('/api/extension/progress', {'client_id': 'fixture', 'job_id': 'STORY-DELETED', 'step': 'generation_complete'})
        self.assertEqual((status, response), (200, {'ok': True, 'ignored': True, 'reason': 'job_permanently_deleted'}))
        self.assertEqual(self.bridge._extension_clients, original)
        self.assertFalse((self.stories.root / 'STORY-DELETED').exists())

    def test_denied_media_and_capture_callbacks_are_not_success_acks(self):
        for path, ident, extra in [
            ('/api/ai/result', 'JOB-DELETED', {}),
            ('/api/jobs/partial-image', 'JOB-DELETED', {}),
            ('/api/stories/partial-image', 'STORY-DELETED', {}),
            ('/api/stories/result', 'STORY-DELETED', {}),
            ('/api/meta-video/event', 'STORY-DELETED', {'version': '0.15.457'}),
            ('/api/products/import', 'JOB-DELETED', {'target_job_id': 'JOB-DELETED', 'target_capture_command_id': 'old-capture'}),
        ]:
            with self.subTest(path=path):
                self.deny(ident)
                body = extra if path == '/api/products/import' else {'job_id': ident, **extra}
                status, response = self.post(path, body)
                self.assertEqual(status, 400)
                self.assertFalse(response['ok'])
                self.assertNotIn('ignored', response)

    def test_durable_delete_intent_and_failed_purge_also_deny_delayed_reports(self):
        for state in ('deleting', 'failed', 'deleted'):
            with self.subTest(state=state):
                self.deny('JOB-DELETED', state=state)
                status, response = self.post('/api/extension/progress', {'job_id': 'JOB-DELETED'})
                self.assertEqual(status, 200)
                self.assertEqual(response.get('reason'), 'job_permanently_deleted')
                self.assertFalse((self.products.root / 'JOB-DELETED').exists())

    def test_auth_precedes_tombstone_lookup_and_terminal_ack(self):
        self.deny('JOB-DELETED')
        with patch.object(self.bridge, '_claim_callback_files') as claim:
            status, response = self.post('/api/extension/progress', {'job_id': 'JOB-DELETED'}, authenticated=False)
        self.assertEqual(status, 403)
        self.assertFalse(response['ok'])
        claim.assert_not_called()

    def test_malformed_journal_is_not_a_permanent_deletion_ack(self):
        journal(self.root).write({'version': 1, 'jobs': [], 'requests': {}})
        status, response = self.post('/api/extension/progress', {'job_id': 'JOB-UNKNOWN'})
        self.assertEqual(status, 400)
        self.assertFalse(response['ok'])
        self.assertNotIn('ignored', response)

    def test_inflight_actual_callback_blocks_delete_before_result_lock(self):
        def accept(body):
            self.assertTrue(any('JOB-ACTIVE' in claim.targets for claim in self.guard.claims))
            self.assertFalse(self.bridge._ai_result_lock.locked())
            with self.assertRaises(ValueError):
                self.guard.reserve_delete(['JOB-ACTIVE'])
            return {'ok': True, 'job_id': body['job_id']}
        with patch.object(self.bridge, '_accept_product_ai_result', side_effect=accept):
            status, response = self.post('/api/ai/result', {'job_id': 'JOB-ACTIVE'})
        self.assertEqual(status, 200)
        self.assertTrue(response['ok'])

    def test_story_callback_claim_precedes_extension_lock_and_releases_on_failure(self):
        def reject(_body):
            self.assertTrue(any('STORY-ACTIVE' in claim.targets for claim in self.guard.claims))
            # Python 3.11 RLock exposes current-thread ownership, not locked().
            self.assertFalse(self.bridge._extension_lock._is_owned())
            raise ValueError('fixture incomplete image')
        with patch.object(self.bridge, '_accept_story_checkpoint', side_effect=reject):
            status, _response = self.post('/api/stories/partial-image', {'job_id': 'STORY-ACTIVE'})
        self.assertEqual(status, 400)

    def test_active_delete_conflict_is_not_terminal_ignored(self):
        claim = self.guard.reserve_delete(['JOB-DELETE-IN-FLIGHT'])
        try:
            with self.assertRaises(ValueError):
                self.bridge._claim_callback_files('/api/extension/progress', {'job_id': 'JOB-DELETE-IN-FLIGHT'})
        finally:
            claim.release()

    def test_tombstone_committed_between_lookup_and_claim_still_denies(self):
        original = self.guard.start
        def race(*args, **kwargs):
            self.deny('JOB-RACE')
            return original(*args, **kwargs)
        with patch.object(self.guard, 'start', side_effect=race):
            with self.assertRaises(ValueError):
                self.bridge._claim_callback_files('/api/ai/result', {'job_id': 'JOB-RACE'})
        self.assertFalse(self.guard.claims)

    def test_backup_and_stale_inmemory_manifests_cannot_resurrect(self):
        for ident, manager in [('JOB-DELETED', self.products), ('STORY-DELETED', self.stories)]:
            with self.subTest(ident=ident):
                target = manager.root / ident / 'job.json'
                backup = runtime_backup_path(self.root, target)
                AtomicJsonFile(backup).write({'id': ident, 'status': 'error'})
                self.deny(ident)
                getter = manager.get_job if ident.startswith('JOB-') else manager.get
                with self.assertRaises(ValueError):
                    getter(ident)
                with self.assertRaises(ValueError):
                    if ident.startswith('JOB-'):
                        manager._save_manifest_file(target, {'id': ident, 'status': 'error'})
                    else:
                        manager._save({'id': ident, 'status': 'error'})
                self.assertFalse(target.parent.exists())
                with self.assertRaises(ValueError):
                    AtomicJsonFile(target, backup_path=backup).read()
                self.assertFalse(target.parent.exists())

    def test_fresh_ids_and_requests_remain_allowed_without_legacy_replay(self):
        from core.product_job_deletion import assert_source_request_available
        self.deny('JOB-DELETED', request_id='deleted-request')
        with self.assertRaises(ValueError):
            assert_source_request_available(self.root, 'deleted-request')
        assert_source_request_available(self.root, 'fresh-request')
        claim = self.bridge._claim_callback_files('/api/jobs/partial-image', {'job_id': 'JOB-NEW'})
        self.assertIsNotNone(claim)
        claim.release()
        target = self.products.root / 'JOB-NEW' / 'job.json'
        self.products._save_manifest_file(target, {'id': 'JOB-NEW', 'status': 'error'})
        self.assertEqual(self.products.get_job('JOB-NEW')['id'], 'JOB-NEW')

    def test_existing_extension_outbox_consumes_only_successful_terminal_ack(self):
        script = Path(__file__).with_name('product_delete_outbox_457.cjs')
        result = subprocess.run(['node', str(script)], cwd=script.parent.parent,
                                capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
