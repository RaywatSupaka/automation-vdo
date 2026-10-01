import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.facebook_post import FacebookPost
from core.facebook_planner import timestamp, local_time, MIN_LEAD
from core.facebook_upload import VideoMultipart

ROOT = Path(__file__).resolve().parents[1]


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'final.mp4'; self.file.write_bytes(b'video-fixture' * 1024)
        self.library = Mock()
        self.library.item_detail.side_effect = lambda item: {'path': str(self.file), 'title': item, 'post_text': 'ข้อความ ' + item}
        self.credentials = Mock(); self.credentials.load.return_value = 'FAKE-TEST-ONLY'
        self.session = Mock(); self.session.request.side_effect = self.request
        self.sent = []; self.remote = {}; self.failure = False; self.mismatch = False
        self.entered = threading.Event(); self.release = threading.Event(); self.release.set()
        self.fb = FacebookPost(self.root, self.library, self.credentials, self.session)
        self.fb.connect('FAKE-TEST-ONLY'); self.p = self.fb.planner
        self.addCleanup(self.release.set)

    def request(self, method, url, **kw):
        if method == 'POST':
            self.entered.set(); self.release.wait(3)
            stream = kw['data']; chunks = []
            while part := stream.read(1024): chunks.append(part)
            raw = b''.join(chunks)
            self.assertEqual(len(raw), len(stream))
            message = BytesParser().parsebytes(('Content-Type: ' + stream.content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + raw)
            fields = {p.get_param('name', header='content-disposition'): p.get_payload(decode=True) for p in message.get_payload()}
            self.sent.append(fields)
            if self.failure: raise TimeoutError('FAKE-TEST-ONLY')
            key = str(1000 + len(self.sent)); scheduled = int(fields.get('scheduled_publish_time', b'0'))
            self.remote[key] = {'status': {'video_status': 'ready'}, 'published': fields['published'] == b'true',
                                'scheduled_publish_time': scheduled + (60 if self.mismatch else 0), 'permalink_url': '/videos/' + key}
            value = {'id': key}
        elif url.endswith('/me'):
            value = {'id': '123', 'name': 'Page Fixture', 'category': 'Test'}
        else:
            value = self.remote[url.rsplit('/', 1)[-1]]
        return SimpleNamespace(ok=True, status_code=200, json=lambda: value)

    def state(self): return self.fb.state()['planner']
    def add(self, count=3):
        self.p.add([f'story:{i}' for i in range(count)], self.state()['revision'])
        return [r['id'] for r in self.state()['rows']]
    def edit(self, op, ids, **extra):
        return self.p.edit(dict(operation=op, ids=ids, revision=self.state()['revision'], **extra))
    def spread(self, ids):
        return self.edit('spread', ids, minutes=60, start=local_time(time.time() + 7200))
    def send(self, ids, mode='schedule'):
        self.p.start(ids, self.state()['revision'], '123', mode)
        self.fb.workers['planner'].join(5)
        self.assertFalse(self.fb.workers['planner'].is_alive())

    def test_timezone_is_bangkok_not_host_timezone(self):
        self.assertEqual(timestamp('2030-01-02T07:00'), int(datetime(2030, 1, 2, tzinfo=timezone.utc).timestamp()))
        self.assertEqual(local_time(timestamp('2030-01-02T07:00')), '2030-01-02T07:00')
        for invalid in ['', '2030-02-30T07:00', '2030-01-02T07:00Z']:
            with self.assertRaises(ValueError): timestamp(invalid)

    def test_add_deduplicates_and_never_posts_and_restart_keeps_drafts(self):
        ids = self.add(); self.add()
        self.assertEqual(len(self.state()['rows']), 3); self.assertFalse(self.sent)
        fb = FacebookPost(self.root, self.library, self.credentials, self.session)
        self.assertEqual([r['id'] for r in fb.state()['planner']['rows']], ids)
        self.assertNotIn('FAKE-TEST-ONLY', self.fb.store.path.read_text())

    def test_stale_revision_and_invalid_ids_do_not_mutate(self):
        ids = self.add(); before = self.fb.store.path.read_bytes()
        with self.assertRaises(ValueError): self.p.edit(dict(operation='remove', ids=ids, revision=-1))
        for invalid in [[], [ids[0], ids[0]], [{}], None]:
            with self.assertRaises(ValueError): self.p.add(invalid, self.state()['revision'])
        self.assertEqual(before, self.fb.store.path.read_bytes())

    def test_preview_spread_shift_only_selected_and_no_hidden_mutation(self):
        ids = self.add(); before = self.fb.store.path.read_bytes()
        params = dict(minutes=1440, start=local_time(time.time() + 7200))
        preview = self.edit('spread', ids[:2], preview=True, **params)
        self.assertEqual(before, self.fb.store.path.read_bytes())
        self.assertEqual(len(preview['preview']), 2)
        self.edit('spread', ids[:2], **params)
        rows = self.state()['rows']; self.assertEqual(rows[1]['scheduled_at'] - rows[0]['scheduled_at'], 86400)
        self.assertIsNone(rows[2]['scheduled_at'])
        old = rows[1]['scheduled_at']; self.edit('shift', [ids[1]], minutes=30)
        self.assertEqual(self.state()['rows'][1]['scheduled_at'], old + 1800)
        self.assertEqual(self.state()['rows'][0], rows[0])

    def test_collision_past_and_too_far_are_atomic_errors(self):
        ids = self.add(); self.spread(ids); before = self.fb.store.path.read_bytes()
        for start in [local_time(time.time()), local_time(time.time() + 181 * 86400)]:
            with self.assertRaises(ValueError): self.edit('spread', ids, minutes=60, start=start)
        with self.assertRaises(ValueError): self.edit('shift', [ids[0]], minutes=60)
        self.assertEqual(before, self.fb.store.path.read_bytes())

    def test_caption_order_remove_preserves_files(self):
        ids = self.add(); self.edit('save', [ids[0]], updates={ids[0]: {'caption': 'แก้ข้อความ', 'time': ''}})
        self.edit('move', [ids[0]], direction=1)
        self.assertEqual(self.state()['rows'][1]['caption'], 'แก้ข้อความ')
        self.edit('remove', [ids[0]])
        self.assertEqual(len(self.state()['rows']), 2); self.assertTrue(self.file.is_file()); self.assertFalse(self.sent)

    def test_schedule_uploads_once_in_order_and_verifies_remote_time(self):
        ids = self.add(); self.spread(ids); self.send(ids)
        rows = self.state()['rows']; self.assertEqual([r['status'] for r in rows], ['scheduled'] * 3)
        self.assertEqual([s['description'].decode() for s in self.sent], ['ข้อความ story:0', 'ข้อความ story:1', 'ข้อความ story:2'])
        self.assertTrue(all(s['published'] == b'false' and s['unpublished_content_type'] == b'SCHEDULED' for s in self.sent))
        self.assertTrue(all(r['scheduled_at'] == r['remote_scheduled_at'] for r in rows))
        with self.assertRaises(ValueError): self.send(ids)
        self.assertEqual(len(self.sent), 3)
        self.assertNotIn('FAKE-TEST-ONLY', json.dumps(self.fb.state()))

    def test_immediate_batch_requires_empty_times(self):
        ids = self.add(1); self.spread(ids)
        with self.assertRaises(ValueError): self.send(ids, 'now')
        self.edit('save', ids, updates={ids[0]: {'caption': 'now', 'time': ''}})
        self.send(ids, 'now'); self.assertEqual(self.state()['rows'][0]['status'], 'published')
        self.assertNotIn('scheduled_publish_time', self.sent[0])

    def test_unknown_post_pauses_remaining_no_resend_on_restart(self):
        ids = self.add(); self.spread(ids); self.failure = True; self.send(ids)
        self.assertEqual([r['status'] for r in self.state()['rows']], ['review', 'draft', 'draft'])
        self.assertEqual(len(self.sent), 1)
        fb = FacebookPost(self.root, self.library, self.credentials, self.session)
        self.assertEqual(fb.state()['planner']['rows'][0]['status'], 'review')
        with self.assertRaises(ValueError): fb.planner.start([ids[0]], fb.state()['planner']['revision'], '123', 'schedule')
        self.assertEqual(len(self.sent), 1)

    def test_schedule_mismatch_is_review_not_false_success(self):
        ids = self.add(2); self.spread(ids); self.mismatch = True; self.send(ids)
        self.assertEqual([r['status'] for r in self.state()['rows']], ['review', 'draft'])
        self.assertEqual(len(self.sent), 1)

    def test_pause_during_upload_and_second_instance_do_not_steal_or_duplicate(self):
        ids = self.add(); self.spread(ids); self.release.clear()
        try:
            self.p.start(ids, self.state()['revision'], '123', 'schedule')
            self.assertTrue(self.entered.wait(2))
            fb = FacebookPost(self.root, self.library, self.credentials, self.session)
            self.assertEqual(fb.state()['planner']['rows'][0]['status'], 'uploading')
            with self.assertRaises(ValueError): fb.planner.start(ids, fb.state()['planner']['revision'], '123', 'schedule')
            with self.assertRaises(ValueError): fb.disconnect()
            self.p.pause()
        finally:
            self.release.set(); self.fb.workers['planner'].join(5)
        self.assertEqual([r['status'] for r in self.state()['rows']], ['scheduled', 'draft', 'draft'])
        self.assertEqual(len(self.sent), 1)
        self.send(ids[1:]); self.assertEqual(len(self.sent), 3)

    def test_page_mismatch_and_missing_time_never_posts(self):
        ids = self.add(1)
        with self.assertRaises(ValueError): self.p.start(ids, self.state()['revision'], '456', 'now')
        with self.assertRaises(ValueError): self.send(ids)
        self.assertFalse(self.sent)

    def test_missing_file_is_editable_draft_and_pauses_batch(self):
        ids = self.add(2); self.spread(ids); self.file.unlink(); self.send(ids)
        self.assertTrue(all(r['status'] == 'draft' for r in self.state()['rows']))
        self.assertFalse(self.sent)

    def test_same_previous_manual_post_is_adopted_not_sent_again(self):
        ids = self.add(1); self.spread(ids)
        key = self.fb.post_key('123', 'story:0', self.fb._hash(self.file))
        self.fb.store.update(lambda d: d['posts'].update({key: {'id': key, 'status': 'review', 'page_id': '123'}}))
        self.send(ids); self.assertFalse(self.sent); self.assertEqual(self.state()['rows'][0]['status'], 'review')

    def test_restart_queue_recovery_and_sent_row_immutable(self):
        ids = self.add(2)
        def change(data):
            data['planner'][0].update(status='queued')
            data['planner'][1].update(status='submitted', post_id='old')
            data['posts']['old'] = {'status': 'uploading'}
        self.fb.store.update(change)
        fb = FacebookPost(self.root, self.library, self.credentials, self.session)
        self.assertEqual([r['status'] for r in fb.state()['planner']['rows']], ['draft', 'review'])
        with self.assertRaises(ValueError): fb.planner.edit(dict(operation='remove', ids=[ids[1]], revision=fb.state()['planner']['revision']))

    def test_http_200_without_id_or_schedule_proof_never_completes(self):
        ids = self.add(1); self.spread(ids)
        self.session.request.side_effect = lambda *a, **k: SimpleNamespace(ok=True, status_code=200, json=lambda: {'success': True})
        self.send(ids); self.assertEqual(self.state()['rows'][0]['status'], 'review')

    def test_scheduled_later_becomes_published_by_read_only_check(self):
        ids = self.add(1); self.spread(ids); self.send(ids)
        row = self.state()['rows'][0]; remote = self.remote[row['video_id']]
        remote['published'] = True
        with patch('core.facebook_post.time.time', return_value=row['scheduled_at'] + 1):
            self.fb.check(row['post_id'])
        self.assertEqual(self.state()['rows'][0]['status'], 'published'); self.assertEqual(len(self.sent), 1)

    def test_time_expired_while_queued_never_shifted_or_uploaded(self):
        ids = self.add(1); self.spread(ids); original = self.state()['rows'][0]['scheduled_at']
        with patch('core.facebook_planner.validate_time', side_effect=[None, ValueError('too late')]):
            self.send(ids)
        row = self.state()['rows'][0]; self.assertEqual(row['scheduled_at'], original)
        self.assertEqual(row['status'], 'draft'); self.assertFalse(self.sent)

    def test_multipart_is_streamed_and_content_length_known(self):
        with self.file.open('rb') as f:
            body = VideoMultipart(f, {'description': 'ไทย\r\nข้อความ', 'published': 'false'})
            import requests
            req = requests.Request('POST', 'http://localhost/not-sent', data=body, headers={'Content-Type': body.content_type}).prepare()
            self.assertIs(req.body, body); self.assertEqual(int(req.headers['Content-Length']), len(body))
            self.assertEqual(f.tell(), 0)

    def test_check_timeout_keeps_remote_id_and_recovers_without_post(self):
        ids = self.add(1); self.spread(ids)
        original = self.request
        def failing_check(method, url, **kwargs):
            if method == 'GET': raise TimeoutError('FAKE-TEST-ONLY')
            return original(method, url, **kwargs)
        self.session.request.side_effect = failing_check
        self.send(ids); row = self.state()['rows'][0]
        self.assertEqual(row['status'], 'review'); self.assertTrue(row['video_id'])
        self.session.request.side_effect = original
        self.fb.check(row['post_id'])
        self.assertEqual(self.state()['rows'][0]['status'], 'scheduled'); self.assertEqual(len(self.sent), 1)

    def test_worker_start_failure_returns_draft_and_releases_dispatch_lock(self):
        ids = self.add(1); self.spread(ids)
        with patch('core.facebook_planner.threading.Thread.start', side_effect=RuntimeError('fixture')):
            with self.assertRaises(ValueError): self.p.start(ids, self.state()['revision'], '123', 'schedule')
        self.assertEqual(self.state()['rows'][0]['status'], 'draft')
        self.assertFalse(self.state()['batch']['active']); self.send(ids)
        self.assertEqual(len(self.sent), 1)

    def test_remote_datetime_and_absent_or_wrong_time(self):
        self.assertEqual(self.fb._remote_time('2030-01-01T09:00:00+0700'), timestamp('2030-01-01T09:00'))
        for value in [True, '', None, '2030-01-01T09:00:00']:
            self.assertIsNone(self.fb._remote_time(value))
        ids = self.add(1); self.spread(ids); self.send(ids); row = self.state()['rows'][0]
        self.remote[row['video_id']].pop('scheduled_publish_time')
        self.fb.check(row['post_id']); self.assertEqual(self.state()['rows'][0]['status'], 'review')
        self.assertEqual(len(self.sent), 1)

    def test_loopback_real_http_transport_streams_multipart_no_real_facebook(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import requests
        captured = {}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, value):
                raw = json.dumps(value).encode(); self.send_response(200)
                self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                if '/me?' in self.path: self.reply({'id': '123', 'name': 'Local fake Page', 'category': 'Test'})
                else: self.reply({'status': {'video_status': 'ready'}, 'published': False, 'scheduled_publish_time': captured['scheduled']})
            def do_POST(self):
                size = int(self.headers['Content-Length']); raw = self.rfile.read(size)
                parsed = BytesParser().parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\n\r\n').encode()+raw)
                parts = {p.get_param('name', header='content-disposition'): p.get_payload(decode=True) for p in parsed.get_payload()}
                captured.update(parts=parts, scheduled=int(parts['scheduled_publish_time']), bytes=len(raw), content_length=size)
                self.reply({'id': '9001'})
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        session = requests.Session(); self.addCleanup(session.close)
        def local_request(method, url, **kwargs):
            self.assertTrue(url.startswith('https://graph.facebook.com/'))
            return session.request(method, f'http://127.0.0.1:{server.server_port}/'+url.split('/', 3)[3], **kwargs)
        try:
            self.session.request.side_effect = local_request
            ids = self.add(1); self.spread(ids); self.send(ids)
            self.assertEqual(self.state()['rows'][0]['status'], 'scheduled')
            self.assertEqual(captured['parts']['source'], self.file.read_bytes())
            self.assertEqual(captured['content_length'], captured['bytes'])
        finally:
            server.shutdown(); server.server_close(); thread.join(2)

    def test_desktop_router_accepts_planner_actions_without_extension_dispatch(self):
        from ui.main_window import MainWindow
        host = SimpleNamespace(facebook_post=Mock(), _app_update_lock=threading.RLock())
        host.facebook_post.action.return_value = {'ok': True}
        import inspect
        method = next(name for name, value in MainWindow.__dict__.items() if callable(value) and 'facebook_planner_start' in inspect.getsource(value))
        for action in ('facebook_planner_add', 'facebook_planner_edit', 'facebook_planner_start', 'facebook_planner_pause'):
            self.assertEqual(getattr(MainWindow, method)(host, action, {'fixture': True}), {'ok': True})
            host.facebook_post.action.assert_called_with(action, {'fixture': True})


class PlannerBrowserTests(unittest.TestCase):
    def test_actual_source_ui(self):
        env = os.environ.copy()
        result = subprocess.run(['node', 'tests/facebook_post_ui.js'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
