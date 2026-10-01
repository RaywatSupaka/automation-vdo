import copy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from core.drama_series import DramaSeriesManager


class DramaQueueResumeTests(unittest.TestCase):
    def test_actual_frontend(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node required')
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, 'tests/drama_queue_resume_harness.js'], cwd=root,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_old_recovered_series_read_does_not_write_or_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            series = manager.create('Recovered series', episode_count=3, characters=[{'name':'A', 'description':'A character'}])
            series['status'] = 'needs_attention'
            series['episodes'][0].update(status='completed', story_job_id='STORY-OLD', video_path='existing.mp4')
            manager._save(series)
            path = manager.root / series['id'] / 'series.json'
            before = path.read_bytes()
            self.assertEqual(manager.get(series['id'])['status'], 'queued')
            snapshot = manager.snapshot()
            self.assertEqual(snapshot['needs_attention_count'], 0)
            self.assertEqual(snapshot['items'][0]['episodes'], series['episodes'])
            self.assertEqual(path.read_bytes(), before)

    def test_real_failures_cancellation_unknown_and_running_preserved(self):
        for state in ('failed', 'running', 'cancelled', 'unknown'):
            series = {'status':'needs_attention', 'episode_count':2,
                      'episodes':[{'status':'completed'}, {'status':state}]}
            expected = copy.deepcopy(series)
            self.assertEqual(DramaSeriesManager._recovered_series_status(series), expected)
        cancelled = {'status':'cancelled', 'episode_count':1, 'episodes':[{'status':'completed'}]}
        self.assertEqual(DramaSeriesManager._recovered_series_status(cancelled)['status'], 'cancelled')

    def test_completion_after_failure_leaves_remaining_episodes_queued(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = DramaSeriesManager(temporary)
            series = manager.create('Recovery', episode_count=3, characters=[{'name':'A', 'description':'A character'}])
            manager.mark_episode_failed(series['id'], 1, 'old failure')
            result = manager.mark_episode_ready({'series_id':series['id'], 'episode_no':1}, 'existing.mp4')
            self.assertEqual(result['status'], 'queued')
            self.assertEqual([ep['status'] for ep in result['episodes']], ['completed','queued','queued'])
