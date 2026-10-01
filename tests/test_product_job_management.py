import copy
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.creation_queue import CreationQueue
from ui.product_jobs import manage_product_jobs, prepare_product_source


class ProductJobManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.queue = CreationQueue(self.tmp.name)
        self.jobs = {'JOB-OLD': {'id': 'JOB-OLD', 'status': 'cancelled'},
                     'STORY-NEW': {'id': 'STORY-NEW', 'product_story': {'version': 1}, 'status': 'failed'}}
        self.app = SimpleNamespace(story_queue=self.queue, _creation_idle_reason=lambda: '',
            bridge=SimpleNamespace(extension_status=lambda: {'connected': True, 'clients': []}, pending_job_commands=lambda ids: []),
            products=SimpleNamespace(get_job=lambda i: self.jobs[i], list_jobs=lambda: list(self.jobs.values())),
            stories=SimpleNamespace(get=lambda i: self.jobs[i], list_jobs=lambda: [
                row for ident, row in self.jobs.items() if ident.startswith('STORY-')]))
        self.queue.enqueue_existing_jobs([{'job_id': i, 'mode': 'story' if i.startswith('STORY') else 'product'} for i in self.jobs])

    def manage(self, op, ids=None, **extra):
        return manage_product_jobs(self.app, {'operation': op, 'job_ids': ids or list(self.jobs), **extra})

    def test_hide_show_persist_without_changing_jobs_or_queue(self):
        before = copy.deepcopy(self.jobs)
        items = self.queue.snapshot()['items']
        self.manage('hide')
        self.assertTrue(CreationQueue(self.tmp.name).product_job_controls()['JOB-OLD']['hidden'])
        self.assertEqual(items, self.queue.snapshot()['items'])
        self.manage('show')
        self.assertFalse(self.queue.product_job_controls()['JOB-OLD']['hidden'])
        self.assertEqual(before, self.jobs)

    def test_trash_restore_preserves_media_and_never_auto_requeues(self):
        media = Path(self.tmp.name) / 'saved-scene.mp4'
        media.write_bytes(b'unchanged saved video')
        before = copy.deepcopy(self.jobs)
        self.manage('trash', confirmed=True)
        self.assertEqual(self.queue.snapshot()['active_count'], 0)
        for i in self.jobs:
            with self.assertRaises(ValueError): self.queue.require_not_trashed(i)
            row = self.queue.item_for_job(i)
            with self.assertRaises(ValueError): self.queue.retry(row['queue_id'])
        self.queue.resume_unfinished()
        self.assertIsNone(self.queue.claim_next())
        # A late worker/Extension callback cannot resurrect a trashed job.
        self.queue.mark_failed_by_job('JOB-OLD', 'late failed response')
        self.queue.mark_completed_by_job('STORY-NEW', str(media))
        reopened = CreationQueue(self.tmp.name)
        reopened.recover_on_startup()
        reopened.resume_unfinished()
        self.assertIsNone(reopened.claim_next())
        self.assertTrue(reopened.product_job_controls()['STORY-NEW']['trashed'])
        self.manage('restore')
        self.queue.resume_unfinished()
        self.assertIsNone(self.queue.claim_next())
        self.queue.retry(self.queue.item_for_job('JOB-OLD')['queue_id'])
        self.assertEqual(self.queue.claim_next()['job_id'], 'JOB-OLD')
        self.assertEqual(media.read_bytes(), b'unchanged saved video')
        self.assertEqual(before, self.jobs)

    def test_running_and_unconfirmed_deletion_rejected(self):
        with self.assertRaises(ValueError): self.manage('trash')
        self.queue.resume()
        self.queue.claim_next()
        with self.assertRaises(ValueError): self.manage('trash', confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})

    def test_worker_cover_and_disconnected_extension_are_not_guessed_idle(self):
        self.app._creation_idle_reason=lambda: 'still working'
        with self.assertRaises(ValueError): self.manage('trash', confirmed=True)
        self.app._creation_idle_reason=lambda: ''
        self.app.bridge.extension_status=lambda: {'connected': False, 'clients': [
            {'ai_job_id': 'STORY-NEW', 'ai_step': 'generating'}]}
        with self.assertRaises(ValueError): self.manage('trash', confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})

    def test_validation_bulk_is_all_or_nothing(self):
        for ids in [[], ['../JOB-OLD'], ['STORY-OTHER']]:
            with self.assertRaises((ValueError, KeyError)):
                manage_product_jobs(self.app, {'operation': 'trash', 'job_ids': ids, 'confirmed': True})
        self.jobs['STORY-NEW']['series_id']='DRAMA-X'
        with self.assertRaises(ValueError): self.manage('trash', confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})
        self.assertEqual(self.queue.snapshot()['active_count'], 2)

    def test_queued_extension_command_blocks_deletion(self):
        self.app.bridge.pending_job_commands=lambda ids: ['JOB-OLD']
        with self.assertRaises(ValueError): self.manage('trash', confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})

    def test_real_bridge_command_barrier_includes_unacknowledged_delivery(self):
        import threading
        from core.local_bridge import LocalBridge
        bridge=LocalBridge.__new__(LocalBridge)
        bridge._extension_lock=threading.Lock()
        bridge._extension_commands=[{'job_id': 'JOB-OLD', 'status': s} for s in
                                    ('pending', 'delivered', 'completed', 'failed', 'cancelled')]
        bridge._extension_commands.append({'job_id': 'JOB-OTHER', 'status': 'pending'})
        self.assertEqual(bridge.pending_job_commands(['JOB-OLD']), ['JOB-OLD', 'JOB-OLD'])

    def test_finished_jobs_protected(self):
        self.jobs['JOB-OLD'].update(status='ready', video_status='ready')
        with self.assertRaises(ValueError): self.manage('trash', ['JOB-OLD'], confirmed=True)

    def test_disk_failure_does_not_report_success(self):
        with patch.object(self.queue, '_save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.manage('trash', confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})
        self.assertEqual(self.queue.snapshot()['active_count'], 2)

    def test_queue_import_cannot_bypass_tombstone(self):
        self.manage('trash', ['JOB-OLD'], confirmed=True)
        self.queue.clear_finished()
        with self.assertRaises(ValueError):
            self.queue.enqueue_existing_jobs([{'job_id': 'JOB-OLD', 'mode': 'product'}])

    def prepared_source(self):
        source = {'id': 'JOB-PREPARED', 'status': 'captured', 'story_source_only': True,
                  'story_prepare_request_id': 'PSP-original-request',
                  'story_prepare_options': {'provider': 'gemini', 'scene_count': 6},
                  'source_images': ['original/product.jpg']}
        self.jobs[source['id']] = source
        return source

    def test_prepared_hide_trash_restore_preserves_source_and_media(self):
        source = self.prepared_source()
        before = copy.deepcopy(source)
        media = Path(self.tmp.name) / 'original-product.jpg'
        media.write_bytes(b'original source bytes')
        self.manage('hide', [source['id']])
        self.assertTrue(CreationQueue(self.tmp.name).product_job_controls()[source['id']]['hidden'])
        self.manage('show', [source['id']])
        self.assertFalse(self.queue.product_job_controls()[source['id']]['hidden'])
        self.manage('trash', [source['id']], confirmed=True)
        reopened = CreationQueue(self.tmp.name)
        with self.assertRaises(ValueError):
            reopened.require_not_trashed(source['id'])
        self.assertIsNone(reopened.item_for_job(source['id']))
        self.manage('restore', [source['id']])
        self.queue.require_not_trashed(source['id'])
        self.assertIsNone(self.queue.item_for_job(source['id']))
        self.assertEqual(self.jobs[source['id']], before)
        self.assertEqual(media.read_bytes(), b'original source bytes')

    def test_prepared_manifest_story_and_queue_links_rejected_atomically(self):
        source = self.prepared_source()
        for key in ('story_job_id', 'story_queued_item_id'):
            with self.subTest(key=key):
                source[key] = 'linked-owner'
                with self.assertRaisesRegex(ValueError, 'ส่งเข้าคลิปหรือคิว'):
                    self.manage('trash', ['JOB-OLD', source['id']], confirmed=True)
                self.assertEqual(self.queue.product_job_controls(), {})
                del source[key]

    def test_prepared_existing_story_link_rejected_even_if_source_marker_missing(self):
        source = self.prepared_source()
        self.jobs['STORY-NEW']['product_story']['product_id'] = source['id']
        for operation in ('hide', 'trash', 'restore'):
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, 'ส่งเข้าคลิปหรือคิว'):
                self.manage(operation, [source['id']], confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})

    def test_prepared_existing_queue_context_rejected_even_without_source_marker(self):
        source = self.prepared_source()
        self.queue.enqueue('story', ['Prepared fixture'], request_id='PSP-queue-fixture',
            settings={'creative_context': {'kind': 'product_story', 'source_product_id': source['id']}})
        with self.assertRaisesRegex(ValueError, 'ส่งเข้าคลิปหรือคิว'):
            self.manage('trash', [source['id']], confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})

    def test_prepared_direct_queue_job_reference_rejected(self):
        source = self.prepared_source()
        self.queue.enqueue_existing_jobs([{'job_id': source['id'], 'mode': 'product'}])
        with self.assertRaisesRegex(ValueError, 'ส่งเข้าคลิปหรือคิว'):
            self.manage('trash', [source['id']], confirmed=True)

    def test_prepared_busy_pending_and_disconnected_remote_barriers(self):
        source = self.prepared_source()
        self.app._creation_idle_reason = lambda: 'capture worker is active'
        with self.assertRaisesRegex(ValueError, 'capture worker'):
            self.manage('trash', [source['id']], confirmed=True)
        self.app._creation_idle_reason = lambda: ''
        self.app.bridge.pending_job_commands = lambda ids: [source['id']]
        with self.assertRaisesRegex(ValueError, 'รอ Extension'):
            self.manage('trash', [source['id']], confirmed=True)
        self.app.bridge.pending_job_commands = lambda ids: []
        self.app.bridge.extension_status = lambda: {'connected': False, 'clients': [
            {'ai_job_id': source['id'], 'ai_step': 'capture'}]}
        with self.assertRaisesRegex(ValueError, 'Extension หยุด'):
            self.manage('hide', [source['id']])
        self.assertEqual(self.queue.product_job_controls(), {})

    def test_prepared_explicit_id_and_request_id_cannot_resume_trash(self):
        source = self.prepared_source()
        self.app.product_cast = object()
        self.manage('trash', [source['id']], confirmed=True)
        payloads = [{'product_id': source['id']},
                    {'request_id': source['story_prepare_request_id'], 'link': 'https://shopee.co.th/item/fixture'}]
        with patch('core.product_story.prepare_link', return_value={'ok': True}) as prepare:
            for payload in payloads:
                with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, 'ถังขยะ'):
                    prepare_product_source(self.app, payload)
            prepare.assert_not_called()
            self.manage('restore', [source['id']])
            for payload in payloads:
                self.assertTrue(prepare_product_source(self.app, payload)['ok'])
            self.assertEqual(prepare.call_count, 2)

    def test_prepared_direct_create_routes_cannot_bypass_trash(self):
        from ui.main_window import MainWindow
        source = self.prepared_source()
        self.manage('trash', [source['id']], confirmed=True)
        payload = {'creative_context': {'kind': 'product_story', 'source_product_id': source['id']}}
        with patch('core.membership.guard_action'):
            for action in ('create_product', 'create_story'):
                with self.subTest(action=action), self.assertRaisesRegex(ValueError, 'ถังขยะ'):
                    MainWindow._desktop_execute_action.__wrapped__(self.app, action, payload)

    def test_prepared_request_replay_desktop_route_cannot_bypass_trash(self):
        from ui.main_window import MainWindow
        source = self.prepared_source()
        self.app.product_cast = object()
        self.app._desktop_request = Mock(return_value={})
        self.manage('trash', [source['id']], confirmed=True)
        with patch('core.membership.guard_action'), patch('core.product_story.prepare_link') as prepare:
            for payload in ({'product_id': source['id']}, {'request_id': source['story_prepare_request_id']}):
                with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, 'ถังขยะ'):
                    MainWindow._desktop_action_request(self.app, 'product_story_prepare', payload)
            prepare.assert_not_called()

    def test_prepared_direct_queue_handoff_cannot_bypass_trash(self):
        from ui.creation_queue import CreationQueueMixin
        source = self.prepared_source()
        self.manage('trash', [source['id']], confirmed=True)
        before = self.queue.snapshot()['items']
        payload = {'creative_context': {'kind': 'product_story', 'source_product_id': source['id']}}
        for action in ('creation_enqueue', 'enqueue_story_batch'):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, 'ถังขยะ'):
                CreationQueueMixin._creation_queue_action.__wrapped__(self.app, action, payload)
        self.assertEqual(before, self.queue.snapshot()['items'])

    def test_prepared_capture_dispatch_cannot_race_trash_commit(self):
        source = self.prepared_source()
        self.app.product_cast = object()
        capture_entered, finish_capture, capture_finished, manage_entered, manage_finished = (
            threading.Event() for _ in range(5))
        errors = []

        def capture(*args):
            capture_entered.set()
            if not finish_capture.wait(2):
                raise AssertionError('fixture capture was not released')
            self.app.bridge.pending_job_commands = lambda ids: [source['id']]
            capture_finished.set()
            return {'ok': True, 'pending': True}

        def remove():
            manage_entered.set()
            try:
                self.manage('trash', [source['id']], confirmed=True)
            except ValueError as exc:
                errors.append(str(exc))
            finally:
                manage_finished.set()

        with patch('core.product_story.prepare_link', side_effect=capture):
            preparing = threading.Thread(target=prepare_product_source,
                args=(self.app, {'product_id': source['id']}))
            managing = threading.Thread(target=remove)
            preparing.start()
            try:
                self.assertTrue(capture_entered.wait(2))
                managing.start()
                self.assertTrue(manage_entered.wait(2))
                self.assertTrue(manage_finished.wait(0.5), 'UI management must not wait for source network work')
                self.assertFalse(capture_finished.is_set(), 'busy rejection must leave source capture running')
                self.assertEqual(self.queue.product_job_controls(), {})
            finally:
                finish_capture.set()
                preparing.join(2)
                if managing.ident is not None:
                    managing.join(2)
            self.assertFalse(preparing.is_alive())
            self.assertFalse(managing.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn('กำลังเตรียมข้อมูลสินค้า', errors[0])
        self.assertTrue(capture_finished.is_set())
        self.assertEqual(self.queue.product_job_controls(), {})
        # The failed nonblocking acquire never releases the preparation's lock;
        # after capture finishes, the original pending-command barrier still wins.
        with self.assertRaisesRegex(ValueError, 'รอ Extension'):
            self.manage('trash', [source['id']], confirmed=True)

    def pending_batch(self, count=251):
        ids = []
        for index in range(count):
            ident = f'STORY-BULK-{index}' if index % 3 == 0 else f'JOB-BULK-{index}'
            job = {'id': ident, 'status': 'failed'}
            if ident.startswith('STORY-'):
                job['product_story'] = {'version': 1}
            elif index % 3 == 1:
                job.update(story_source_only=True, story_prepare_request_id=f'PSP-bulk-{index}')
            self.jobs[ident] = job
            ids.append(ident)
        return ids

    def test_all_pending_over_200_mixed_jobs_commit_once(self):
        ids = self.pending_batch() + ['JOB-OLD', 'STORY-NEW']
        before = copy.deepcopy(self.jobs)
        with patch.object(self.queue, '_save', wraps=self.queue._save) as save:
            result = self.manage('trash', ids, scope='all_pending', confirmed=True)
        self.assertEqual(save.call_count, 1)
        self.assertEqual(set(result['product_job_controls']), set(ids))
        self.assertTrue(all(row['trashed'] for row in result['product_job_controls'].values()))
        self.assertEqual(self.queue.snapshot()['active_count'], 0)
        self.assertEqual(before, self.jobs)

    def test_all_pending_scope_does_not_expand_other_operation_limits(self):
        ids = self.pending_batch()
        for operation in ('hide', 'show', 'restore'):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                self.manage(operation, ids, scope='all_pending', confirmed=True)
        with self.assertRaises(ValueError):
            self.manage('trash', ids, confirmed=True)
        with self.assertRaises(ValueError):
            self.manage('trash', ids, scope='all_pending')
        with self.assertRaises(ValueError):
            self.manage('trash', ids + ['../JOB-invalid'], scope='all_pending', confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})

    def test_all_pending_hidden_since_confirmation_rejects_whole_batch(self):
        ids = self.pending_batch()
        self.manage('hide', [ids[-1]])
        before = self.queue.product_job_controls()
        with patch.object(self.queue, '_save', wraps=self.queue._save) as save:
            with self.assertRaisesRegex(ValueError, 'มีงานถูกซ่อน'):
                self.manage('trash', ids, scope='all_pending', confirmed=True)
        save.assert_not_called()
        self.assertEqual(self.queue.product_job_controls(), before)

    def test_all_pending_replay_preserves_tombstones_and_ignores_future_jobs(self):
        ids = self.pending_batch()
        self.manage('trash', ids, scope='all_pending', confirmed=True)
        before = self.queue.product_job_controls()
        self.jobs['JOB-FUTURE'] = {'id': 'JOB-FUTURE', 'status': 'failed'}
        # An already-trashed manifest need not survive to accept the same request.
        del self.jobs[ids[0]]
        with patch.object(self.queue, '_save', wraps=self.queue._save) as save:
            result = self.manage('trash', ids, scope='all_pending', confirmed=True)
        save.assert_not_called()
        self.assertEqual(result['product_job_controls'], before)
        self.assertNotIn('JOB-FUTURE', result['product_job_controls'])

    def test_all_pending_partial_replay_only_commits_remaining_exact_ids(self):
        ids = self.pending_batch()
        self.manage('trash', [ids[0]], confirmed=True)
        prior = self.queue.product_job_controls()[ids[0]]
        self.jobs['JOB-FUTURE'] = {'id': 'JOB-FUTURE', 'status': 'failed'}
        self.manage('trash', ids, scope='all_pending', confirmed=True)
        controls = self.queue.product_job_controls()
        self.assertEqual(controls[ids[0]], prior)
        self.assertEqual(set(controls), set(ids))

    def test_all_pending_protected_change_rejects_whole_batch(self):
        ids = self.pending_batch()
        target = self.jobs[ids[1]]
        for change in ({'status': 'ready', 'video_status': 'ready'},
                       {'story_job_id': 'STORY-LINKED'}, {'series_id': 'DRAMA-LINKED'}):
            original = copy.deepcopy(target)
            target.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manage('trash', ids, scope='all_pending', confirmed=True)
            self.assertEqual(self.queue.product_job_controls(), {})
            target.clear()
            target.update(original)
        self.app.bridge.pending_job_commands = lambda requested: [ids[-1]]
        with self.assertRaisesRegex(ValueError, 'รอ Extension'):
            self.manage('trash', ids, scope='all_pending', confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})

    def test_all_pending_disk_failure_preserves_entire_batch(self):
        ids = self.pending_batch()
        with patch.object(self.queue, '_save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.manage('trash', ids, scope='all_pending', confirmed=True)
        self.assertEqual(self.queue.product_job_controls(), {})
