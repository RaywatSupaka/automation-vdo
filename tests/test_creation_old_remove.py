import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock

import test_creation_queue_recovery_controls as fixtures
from core.creation_queue import CreationQueue
from core.cancellable_process import hidden_process_kwargs


class OldQueueRemovalTests(unittest.TestCase):
    read_product = fixtures.CreationQueueRecoveryControlsTests.read_product
    read_story = fixtures.CreationQueueRecoveryControlsTests.read_story
    job = fixtures.CreationQueueRecoveryControlsTests.job
    row = fixtures.CreationQueueRecoveryControlsTests.row
    action = fixtures.CreationQueueRecoveryControlsTests.action

    def setUp(self):
        fixtures.CreationQueueRecoveryControlsTests.setUp(self)
        self.app.bridge.pending_job_commands.return_value = []

    def remove(self, jobs=(), rows=(), **extra):
        return self.action('creation_remove_old', confirmed=True,
                           job_ids=list(jobs), queue_ids=list(rows), **extra)

    def assert_no_provider_work(self):
        self.app._schedule_next_story_queue_item.assert_not_called()
        self.app.bridge.queue_extension_command.assert_not_called()
        self.app.bridge.clear_flow_progress.assert_not_called()
        self.app._cancel_product_pipeline.assert_not_called()
        self.app._cancel_story_pipeline.assert_not_called()

    def test_orphan_removed_durably_without_changing_any_job_file(self):
        folder = self.job()
        before = {p:p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        self.assertEqual(len(self.app._creation_queue_state()['recoverable_jobs']),1)
        result = self.remove(['JOB-OLD'])
        self.assertEqual(result['removed'],1)
        self.assertEqual(result['creation_queue']['recoverable_jobs'],[])
        self.app.story_queue = CreationQueue(self.root)
        self.app._creation_recovery_inventory = None
        self.assertEqual(self.app._creation_queue_state()['removable_old_job_ids'],[])
        self.assertEqual({p:p.read_bytes() for p in before},before)
        self.assert_no_provider_work()

    def test_bulk_includes_more_than_thirty_but_preserves_other_rows(self):
        for n in range(35): self.job(f'JOB-OLD-{n}')
        failed = self.row(job_id='JOB-BOUND')
        stopped = self.row('story','STORY-STOPPED','cancelled')
        done = self.row('story','STORY-DONE','completed')
        drama = self.row('story','STORY-DRAMA','failed')
        self.queue._update(drama['queue_id'],mode='drama',series_id='SERIES-KEEP')
        waiting = self.row('story','STORY-WAITING','queued')
        before = self.queue.snapshot()
        state = self.app._creation_queue_state()
        self.assertEqual(len(state['recoverable_jobs']),30)
        self.assertEqual(len(state['removable_old_job_ids']),35)
        self.assertEqual(set(state['removable_old_queue_ids']),{failed['queue_id'],stopped['queue_id']})
        result = self.remove(state['removable_old_job_ids'],state['removable_old_queue_ids'])
        self.assertEqual(result['removed'],37)
        after = self.queue.snapshot()
        self.assertEqual(after['paused'],before['paused'])
        self.assertEqual(after['items'],[row for row in before['items'] if row['queue_id'] in
                                      {waiting['queue_id'],done['queue_id'],drama['queue_id']}])
        self.assertEqual(self.queue.dismissed_creation_jobs().keys(),
                         {f'JOB-OLD-{n}' for n in range(35)} | {'JOB-BOUND','STORY-STOPPED'})
        self.assert_no_provider_work()

    def test_stale_confirmation_rejected_atomically_when_row_resumes(self):
        self.job()
        row = self.row('story','STORY-RESUMED','failed')
        self.queue._update(row['queue_id'],status='queued')
        before = self.queue.path.read_bytes()
        with self.assertRaises(ValueError): self.remove(['JOB-OLD'],[row['queue_id']])
        self.assertEqual(self.queue.path.read_bytes(),before)
        self.assertEqual(self.queue.dismissed_creation_jobs(),{})

    def test_orphan_cannot_be_removed_after_entering_queue(self):
        self.job()
        self.row(job_id='JOB-OLD',status='queued')
        before = self.queue.path.read_bytes()
        with self.assertRaises(ValueError): self.remove(['JOB-OLD'])
        self.assertEqual(self.queue.path.read_bytes(),before)

    def test_pending_command_or_live_worker_does_not_mutate(self):
        self.job()
        before = self.queue.path.read_bytes()
        self.app.bridge.pending_job_commands.return_value = ['unacknowledged']
        with self.assertRaisesRegex(ValueError,'รอยืนยัน'): self.remove(['JOB-OLD'])
        self.app.bridge.pending_job_commands.return_value = []
        self.app._creation_story_worker = Mock(is_alive=Mock(return_value=True))
        with self.assertRaises(ValueError): self.remove(['JOB-OLD'])
        self.assertEqual(self.queue.path.read_bytes(),before)
        self.assert_no_provider_work()

    def test_foreign_or_invalid_selection_confirmation_and_terminals_rejected(self):
        self.job()
        self.job('JOB-DONE',automation_status='completed')
        self.job('STORY-DRAMA',series_id='SERIES-1')
        before = self.queue.path.read_bytes()
        invalid = [dict(job_ids=['JOB-OLD']),dict(confirmed=True,job_ids=['../JOB-OLD']),
                   dict(confirmed=True,job_ids='JOB-OLD'),dict(confirmed=True),
                   dict(confirmed=True,job_ids=['JOB-DONE']),dict(confirmed=True,job_ids=['STORY-DRAMA']),
                   dict(confirmed=True,queue_ids=['CQ-MISSING'])]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.action('creation_remove_old',**payload)
            self.assertEqual(self.queue.path.read_bytes(),before)

    def test_disconnected_provider_is_not_assumed_stopped(self):
        self.job()
        before=self.queue.path.read_bytes()
        self.app.bridge.extension_status.return_value={'connected':False,'clients':[
            {'flow_job_id':'JOB-OLD','flow_step':'generation_in_progress'}]}
        with self.assertRaisesRegex(ValueError,'เว็บหยุด'): self.remove(['JOB-OLD'])
        self.assertEqual(self.queue.path.read_bytes(),before)
        self.assert_no_provider_work()

    def test_existing_remove_does_not_resurface_or_adopt_late_callback(self):
        folder = self.job()
        row = self.row()
        before = (folder/'job.json').read_bytes()
        self.action('creation_remove',queue_id=row['queue_id'])
        self.assertEqual(self.app._creation_queue_state()['recoverable_jobs'],[])
        self.queue.mark_completed_by_job('JOB-OLD','late.mp4')
        self.assertEqual(self.queue.snapshot()['items'],[])
        self.assertEqual((folder/'job.json').read_bytes(),before)
        self.assert_no_provider_work()

    def test_actual_queue_ui_confirmation_and_empty_state(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node','tests/creation_old_remove_ui.cjs'],cwd=root,
                                capture_output=True,text=True,encoding='utf-8',timeout=45,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
