import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from core.creation_queue import CreationQueue


class DramaSeriesStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.q = CreationQueue(self.temp.name)
        self.q.enqueue('product', ['https://s.shopee.co.th/fixture'])
        self.q.enqueue_drama_series('SERIES-other', 'Other', 2)
        self.q.enqueue_drama_series('SERIES-target', 'Target', 3)
        self.target = [i for i in self.q.snapshot()['items'] if i.get('series_id') == 'SERIES-target']
        self.q._update(self.target[0]['queue_id'], status='completed', job_id='STORY-done', output_path='keep.mp4')

    def test_only_selected_series_runs_then_stops(self):
        others = [i for i in self.q.snapshot()['items'] if i.get('series_id') != 'SERIES-target']
        self.q.resume(series_id='SERIES-target')
        self.q.resume(series_id='SERIES-target')  # duplicate before worker claim
        for ep in (2, 3):
            self.assertEqual(self.q.next_queued_item()['episode_no'], ep)
            item = self.q.claim_next()
            self.assertEqual(item['series_id'], 'SERIES-target')
            self.assertEqual(item['episode_no'], ep)
            self.assertIsNone(self.q.claim_next())
            self.q._update(item['queue_id'], status='completed')
        self.assertIsNone(self.q.next_queued_item())
        self.assertIsNone(self.q.claim_next())
        self.assertTrue(self.q.snapshot()['paused'])
        self.assertEqual([i for i in self.q.snapshot()['items'] if i.get('series_id') != 'SERIES-target'], others)
        self.assertEqual(self.q.get_item(self.target[0]['queue_id'])['output_path'], 'keep.mp4')

    def test_restart_preserves_scope_and_job_but_waits_for_user(self):
        self.q._update(self.target[1]['queue_id'], job_id='STORY-saved')
        self.q.resume(series_id='SERIES-target')
        self.q.claim_next()
        reopened = CreationQueue(self.temp.name)
        reopened.recover_on_startup()
        self.assertTrue(reopened.snapshot()['paused'])
        self.assertEqual(reopened.snapshot()['run_series_id'], 'SERIES-target')
        self.assertIsNone(reopened.claim_next())
        reopened.resume(series_id='SERIES-target')
        self.assertEqual(reopened.claim_next()['job_id'], 'STORY-saved')

    def test_explicit_global_start_restores_fifo(self):
        self.q.resume(series_id='SERIES-target')
        self.q.pause()
        self.q.resume()
        self.assertEqual(self.q.snapshot()['run_series_id'], '')
        self.assertEqual(self.q.claim_next()['mode'], 'product')

    def test_completed_episode_wins_over_old_cancelled_attempt(self):
        with self.q._lock, self.q._store.locked():
            data = self.q._load()
            old = dict(self.target[0], queue_id='SQ-old', status='cancelled')
            data['items'].insert(0, old)
            self.q._save(data)
        self.q.resume(series_id='SERIES-target')
        self.assertEqual(self.q.claim_next()['episode_no'], 2)

    def test_failure_or_cancel_does_not_skip_episode(self):
        for status in ('failed', 'cancelled'):
            self.q._update(self.target[1]['queue_id'], status=status)
            self.q.resume(series_id='SERIES-target')
            self.assertIsNone(self.q.claim_next())
            self.assertTrue(self.q.snapshot()['paused'])

    def test_cannot_switch_scope_during_running_or_missing_series(self):
        with self.assertRaises(ValueError):
            self.q.resume(series_id='SERIES-missing')
        self.q.resume()
        self.q.claim_next()
        with self.assertRaises(ValueError):
            self.q.resume(series_id='SERIES-target')

    def test_desktop_action_scopes_queue_and_schedules_once_without_new_job(self):
        owner = SimpleNamespace(story_queue=self.q,
            drama_series=SimpleNamespace(get=lambda key: {'id':key,'status':'queued','episodes':[
                {'episode_no':1,'status':'completed'}, {'episode_no':2,'status':'queued'}]}),
            _creation_idle_reason=lambda: '', _creation_clear_idle_references=Mock(),
            _schedule_next_story_queue_item=Mock())
        # Execute only the actual new branch; the surrounding action method
        # contains unrelated form/Tk adapters, not required by this command.
        import ast
        from pathlib import Path
        source = Path('ui/creation_queue.py').read_text(encoding='utf-8')
        module = ast.parse(source)
        branch = next(node for node in ast.walk(module) if isinstance(node, ast.If)
                      and ast.unparse(node.test) == "action == 'creation_start_series'")
        fn = ast.FunctionDef(name='action', args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='self'),ast.arg(arg='payload')],
            kwonlyargs=[],kw_defaults=[],defaults=[]), body=branch.body, decorator_list=[])
        scope={}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])), '<actual-series-action>', 'exec'),scope)
        scope['action'](owner, {'series_id':'SERIES-target'})
        self.assertEqual(self.q.snapshot()['run_series_id'],'SERIES-target')
        owner._schedule_next_story_queue_item.assert_called_once_with(200)
        self.q.claim_next()
        scope['action'](owner, {'series_id':'SERIES-target'})
        owner._schedule_next_story_queue_item.assert_called_once()
