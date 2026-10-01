import copy
import json
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.atomic_json import AtomicJsonFile, runtime_backup_path
from core.creation_queue import CreationQueue
from core.job_file_guard import app_guard
from core.product_job_deletion import assert_job_available, journal, snapshot
from core.product_manager import ProductManager
from core.story_manager import StoryManager
from ui.main_window import MainWindow
from ui.product_jobs import manage_product_jobs, product_jobs_delete_status, _DELETE_WORKERS


class HeldThread:
    pending = []
    def __init__(self, target, args=(), **kwargs):
        self.target, self.args = target, args
    def start(self): self.pending.append(self)
    def run(self): return self.target(*self.args)


class ProductPermanentDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = MainWindow.__new__(MainWindow)
        self.app.products = ProductManager(self.root)
        self.app.stories = StoryManager(self.root)
        self.app.story_queue = CreationQueue(self.root)
        self.app.bridge = SimpleNamespace(extension_status=lambda: {'clients': []}, pending_job_commands=lambda ids: [])
        self.app.events = queue.Queue()
        self.app._product_pipeline_job_id = self.app._story_pipeline_job_id = ''
        self.app.cfg = {}
        HeldThread.pending = []
        self.patch = patch('ui.product_jobs.threading.Thread', HeldThread)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(lambda: [claim.release() for claim in tuple(app_guard(self.app).claims)])
        self.addCleanup(lambda: [_DELETE_WORKERS.pop(key, None) for key in list(_DELETE_WORKERS) if key[0] == str(self.root)])
        self.make('JOB-ONE')
        self.make('STORY-TWO')

    def make(self, ident, **changes):
        folder = (self.app.products.root if ident.startswith('JOB-') else self.app.stories.root) / ident
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'videos').mkdir(exist_ok=True)
        (folder / 'videos/partial.mp4').write_bytes(b'owned unfinished video')
        job = {'id': ident, 'status': 'error', **({'product_story': {'product_id': 'JOB-SOURCE'}} if ident.startswith('STORY-') else {}), **changes}
        if ident.startswith('JOB-'): self.app.products._save_manifest_file(folder / 'job.json', job)
        else: self.app.stories._save(job)
        return folder

    def delete(self, ids=None, request_id='delete-fixture-0001', scope='selected', **changes):
        return manage_product_jobs(self.app, {'operation': 'delete', 'job_ids': ids or ['JOB-ONE', 'STORY-TWO'],
            'confirmed': True, 'request_id': request_id, 'scope': scope, **changes})

    def status(self, request_id='delete-fixture-0001'):
        return product_jobs_delete_status(self.app, {'request_id': request_id})

    def run_worker(self): HeldThread.pending.pop(0).run()

    def test_explicit_delete_removes_only_owned_folders_and_exact_backups(self):
        outside = self.root / 'keep.mp4'; outside.write_bytes(b'unrelated')
        source = self.make('JOB-SOURCE', story_source_only=True)
        saved = self.delete()
        self.assertEqual(saved['deletion']['status'], 'deleting')
        self.assertTrue((self.app.products.root / 'JOB-ONE').exists())
        self.run_worker()
        result = self.status()
        self.assertEqual(result['deletion']['status'], 'complete')
        self.assertEqual(set(result['deletion']['deleted_ids']), {'JOB-ONE', 'STORY-TWO'})
        self.assertFalse((self.app.products.root / 'JOB-ONE').exists())
        self.assertFalse(runtime_backup_path(self.root, self.app.products.root / 'JOB-ONE/job.json').exists())
        self.assertTrue(source.is_dir())
        self.assertEqual(outside.read_bytes(), b'unrelated')
        self.assertTrue(result['product_job_controls']['JOB-ONE']['permanently_deleted'])

    def test_delete_requires_distinct_consent_request_and_scope(self):
        for changes in ({'confirmed': False}, {'request_id': ''}, {'scope': 'all'}, {'job_ids': ['../JOB-ONE']}):
            result = self.delete(**changes)
            self.assertEqual(result['deletion']['status'], 'rejected')
            self.assertFalse(journal(self.root).path.exists())
        self.assertEqual(HeldThread.pending, [])

    def test_queued_selected_rows_removed_but_other_queue_untouched(self):
        self.make('JOB-OTHER')
        self.app.story_queue.enqueue_existing_jobs([{'job_id': i, 'mode': 'product'} for i in ['JOB-ONE', 'JOB-OTHER']])
        before = self.app.story_queue.item_for_job('JOB-OTHER')
        result = self.delete(['JOB-ONE'])
        self.assertEqual(result['deletion']['status'], 'deleting')
        self.assertIsNone(self.app.story_queue.item_for_job('JOB-ONE'))
        self.assertEqual(self.app.story_queue.item_for_job('JOB-OTHER'), before)
        self.run_worker()
        with self.assertRaises(ValueError): self.app.story_queue.enqueue_existing_jobs([{'job_id': 'JOB-ONE', 'mode': 'product'}])

    def test_running_remote_pending_and_reference_claim_reject_without_intent(self):
        for prepare, reset in (
            (lambda: setattr(self.app, '_product_pipeline_job_id', 'JOB-ONE'), lambda: setattr(self.app, '_product_pipeline_job_id', '')),
            (lambda: setattr(self.app.bridge, 'pending_job_commands', lambda ids: ['JOB-ONE']), lambda: setattr(self.app.bridge, 'pending_job_commands', lambda ids: [])),
            (lambda: setattr(self.app.bridge, 'extension_status', lambda: {'connected': False, 'clients': [{'flow_job_id': 'JOB-ONE', 'flow_step': 'generating'}]}), lambda: setattr(self.app.bridge, 'extension_status', lambda: {'clients': []})),
        ):
            prepare()
            self.assertEqual(self.delete()['deletion']['status'], 'rejected')
            self.assertFalse(journal(self.root).path.exists())
            reset()
        with app_guard(self.app).start('STORY-USER', references='JOB-ONE'):
            self.assertEqual(self.delete()['deletion']['status'], 'rejected')

    def test_ready_final_other_story_and_linked_source_block_entire_batch(self):
        cases = [dict(video_path='videos/final.mp4'), dict(video_status='ready'), dict(status='posted')]
        for change in cases:
            self.make('JOB-ONE', **change)
            self.assertEqual(self.delete()['deletion']['status'], 'rejected')
            self.assertFalse(journal(self.root).path.exists())
        self.make('JOB-ONE')
        self.make('STORY-TWO', product_story=None)
        self.assertEqual(self.delete()['deletion']['status'], 'rejected')
        self.make('STORY-TWO')
        self.make('JOB-SOURCE', story_source_only=True)
        self.assertEqual(self.delete(['JOB-SOURCE'])['deletion']['status'], 'rejected')

    def test_inactive_other_job_reference_blocks_no_cascade(self):
        self.make('STORY-OTHER', source_footage=[str(self.app.products.root / 'JOB-ONE/videos/partial.mp4')])
        self.assertEqual(self.delete(['JOB-ONE'])['deletion']['status'], 'rejected')
        self.assertFalse(journal(self.root).path.exists())

    def test_legacy_trash_explicit_cleanup_and_scope_mismatch(self):
        self.app.story_queue.manage_product_jobs(['JOB-ONE'], 'trash')
        self.assertEqual(self.delete(['JOB-ONE', 'STORY-TWO'], scope='legacy_trash')['deletion']['status'], 'rejected')
        self.assertTrue((self.app.products.root / 'JOB-ONE').exists())
        self.delete(['JOB-ONE'], scope='legacy_trash')
        self.run_worker()
        with self.assertRaises(ValueError): self.app.story_queue.manage_product_jobs(['JOB-ONE'], 'restore')
        self.assertFalse((self.app.products.root / 'JOB-ONE').exists())

    def test_all_pending_over200_exact_set_and_hidden_revalidation(self):
        ids = [f'JOB-BULK-{i}' for i in range(201)]
        for ident in ids: self.make(ident)
        self.assertEqual(self.delete(ids)['deletion']['status'], 'rejected')
        self.app.story_queue.manage_product_jobs([ids[0]], 'hide')
        self.assertEqual(self.delete(ids, scope='all_pending')['deletion']['status'], 'rejected')
        self.app.story_queue.manage_product_jobs([ids[0]], 'show')
        self.delete(ids, scope='all_pending')
        future = self.make('JOB-ARRIVED-LATER')
        self.run_worker()
        self.assertEqual(len(self.status()['deletion']['deleted_ids']), 201)
        self.assertTrue(future.exists())

    def test_same_request_doubleclick_and_replay_never_expand(self):
        self.delete(['JOB-ONE'])
        self.delete(['JOB-ONE'])
        self.assertEqual(len(HeldThread.pending), 1)
        self.assertEqual(self.delete(['JOB-ONE', 'STORY-TWO'])['deletion']['status'], 'rejected')
        self.run_worker()
        self.assertEqual(self.delete(['JOB-ONE'])['deletion']['status'], 'complete')
        self.assertEqual(self.delete(['JOB-ONE'], request_id='delete-new-0002')['deletion']['status'], 'complete')
        self.assertFalse(HeldThread.pending)

    def test_partial_delete_reports_and_explicit_same_request_retries_only_remaining(self):
        self.delete()
        from core.product_job_deletion import purge_tree
        def deny_story(path, root, identity):
            if Path(path).name == 'STORY-TWO': raise PermissionError('fixture locked')
            return purge_tree(path, root, identity)
        with patch('core.product_job_deletion.purge_tree', side_effect=deny_story): self.run_worker()
        status = self.status()['deletion']
        self.assertEqual(status['status'], 'partial')
        self.assertEqual(status['deleted_ids'], ['JOB-ONE'])
        self.assertEqual(status['failed'][0]['job_id'], 'STORY-TWO')
        self.delete()
        self.run_worker()
        self.assertEqual(self.status()['deletion']['status'], 'complete')

    def test_interrupted_owner_status_is_read_only_and_retry_is_explicit(self):
        self.delete(['JOB-ONE'])
        claim = HeldThread.pending.pop().args[-1]
        claim.release()
        _DELETE_WORKERS.clear()
        before = journal(self.root).path.read_bytes()
        self.assertEqual(self.status()['deletion']['status'], 'partial')
        self.assertEqual(before, journal(self.root).path.read_bytes())
        self.assertTrue((self.app.products.root / 'JOB-ONE').exists())
        self.delete(['JOB-ONE'])
        self.run_worker()
        self.assertEqual(self.status()['deletion']['status'], 'complete')

    def test_state_write_failure_does_not_loop_deleting_or_repeat_completed_files(self):
        self.delete(['JOB-ONE'])
        original = AtomicJsonFile.write_unlocked
        def fail_state(store, value):
            if store.path.name == 'product_job_deletions.json': raise OSError('fixture disk error')
            return original(store, value)
        with patch.object(AtomicJsonFile, 'write_unlocked', fail_state), self.assertRaises(OSError): self.run_worker()
        self.assertFalse((self.app.products.root / 'JOB-ONE').exists())
        self.assertEqual(self.status()['deletion']['status'], 'partial')
        self.delete(['JOB-ONE'])
        self.run_worker()
        self.assertEqual(self.status()['deletion']['status'], 'complete')

    def test_missing_request_status_is_definitive_without_mutation(self):
        result = self.status()
        self.assertEqual(result['deletion']['status'], 'not_found')
        self.assertFalse(result['deletion']['accepted'])
        self.assertFalse(journal(self.root).path.exists())

    def test_symlink_and_replacement_folder_fail_closed(self):
        outside = self.root / 'outside'; outside.mkdir()
        kept = outside / 'keep'; kept.write_text('keep', encoding='utf-8')
        link = self.app.products.root / 'JOB-ONE/linked'
        try: link.symlink_to(outside, target_is_directory=True)
        except OSError: self.skipTest('symlink creation unavailable')
        self.assertEqual(self.delete(['JOB-ONE'])['deletion']['status'], 'rejected')
        self.assertEqual(kept.read_text(encoding='utf-8'), 'keep')
        self.assertFalse(journal(self.root).path.exists())

    def test_replacement_directory_identity_and_reparse_guard(self):
        from core.product_job_deletion import purge_tree, validate_tree
        folder = self.app.products.root / 'JOB-ONE'
        identity = validate_tree(folder, self.root)
        with self.assertRaises(ValueError): purge_tree(folder, self.root, [identity[0], identity[1] + 1])
        self.assertTrue((folder / 'videos/partial.mp4').is_file())
        from core.product_job_deletion import _not_link
        def reject_junction(path):
            if Path(path).name == 'videos': raise ValueError('fixture reparse point')
            return _not_link(path)
        with patch('core.product_job_deletion._not_link', side_effect=reject_junction):
            self.assertEqual(self.delete(['JOB-ONE'])['deletion']['status'], 'rejected')
        self.assertFalse(journal(self.root).path.exists())

    def test_late_checkpoint_save_and_backup_read_cannot_resurrect(self):
        old = self.app.stories.get('STORY-TWO')
        target = self.app.stories.root / 'STORY-TWO'
        self.delete(['STORY-TWO'])
        self.run_worker()
        for operation in (lambda: self.app.stories._save(old), lambda: self.app.stories.get('STORY-TWO'),
                          lambda: AtomicJsonFile(target / 'prompts/late.json').write({'late': True}),
                          lambda: assert_job_available(self.root, 'STORY-TWO')):
            with self.assertRaises(ValueError): operation()
        self.assertFalse(target.exists())

    def test_durable_meta_and_flow_unfinished_receipts_block_offline_delete(self):
        folder = self.app.products.root / 'JOB-ONE'
        (folder / 'prompts').mkdir(exist_ok=True)
        ledger = folder / 'prompts/meta_video_receipts.json'
        for stage in ('prepared', 'send_intent', 'generating', 'downloading', 'redesigning', 'needs_attention'):
            ledger.write_text(json.dumps({'scenes': {'1': {'stage': stage}}}), encoding='utf-8')
            self.assertEqual(self.delete(['JOB-ONE'])['deletion']['status'], 'rejected')
            self.assertFalse(journal(self.root).path.exists())

