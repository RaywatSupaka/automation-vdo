import copy
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from core.creation_queue import CreationQueue
from core.cancellable_process import OperationCancelled
from ui.main_window import MainWindow


class CreationQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.queue = CreationQueue(self.temp.name)

    def products(self, *names, **kwargs):
        return self.queue.enqueue('product', ['https://s.shopee.co.th/' + name for name in names], **kwargs)['items']

    def running(self):
        self.queue.resume()
        return self.queue.claim_next()

    def test_mixed_fifo_one_owner_until_final(self):
        first = self.products('one')[0]
        self.queue.enqueue('story', ['เรื่องหมา'], scene_count=6, visual_style='anime')
        self.products('two')
        self.assertIsNone(self.queue.claim_next())
        self.assertEqual(self.running()['queue_id'], first['queue_id'])
        self.queue.attach_job(first['queue_id'], 'JOB-1')
        # Receiving images / one clip is not queue completion.
        self.assertIsNone(self.queue.claim_next())
        self.queue.mark_completed_by_job('JOB-1', 'final.mp4')
        self.assertEqual(self.queue.claim_next()['mode'], 'story')
        self.assertIsNone(self.queue.claim_next())

    def test_append_does_not_pause_running_queue(self):
        self.products('one')
        self.running()
        self.products('two')
        self.assertFalse(self.queue.snapshot()['paused'])
        self.assertEqual(self.queue.snapshot()['counts']['running'], 1)

    def test_snapshots_immutable_and_secrets_not_persisted(self):
        settings = {'provider':'chatgpt', 'voice_reference_id':'voice-A', 'voice_api_key':'DO_NOT_SAVE',
                    'voice':{'speed':1.0, 'api_key':'DO_NOT_SAVE'}, 'render':{'width':1080},
                    'finish_config':{'subtitle_font_size':48, 'subtitle_credential':'DO_NOT_SAVE'}}
        self.products('one', settings=settings)
        settings['render']['width'] = 720
        row = self.queue.snapshot()['items'][0]
        row['settings']['render']['width'] = 360
        self.assertEqual(self.queue.snapshot()['items'][0]['settings']['render']['width'], 1080)
        self.assertNotIn('DO_NOT_SAVE', self.queue.path.read_text(encoding='utf-8'))
        self.assertEqual(self.queue.snapshot()['items'][0]['settings']['voice_reference_id'], 'voice-A')

    def test_duplicates_and_request_replay(self):
        first = self.products('one', 'one', request_id='request-1')
        self.assertEqual(len(first), 1)
        self.assertEqual(self.products('one'), [])
        self.assertEqual(self.products('two', request_id='request-1'), [])
        self.assertEqual(self.queue.snapshot()['total_count'], 1)

    def test_restart_pauses_preserves_bound_job_and_settings(self):
        self.products('one', settings={'voice_reference_id':'A'})
        row = self.running()
        self.queue.attach_job(row['queue_id'], 'JOB-KEEP')
        restored = CreationQueue(self.temp.name)
        restored.recover_on_startup()
        self.assertIsNone(restored.claim_next())
        self.assertEqual(restored.get_item(row['queue_id'])['job_id'], 'JOB-KEEP')
        restored.resume()
        self.assertEqual(restored.claim_next()['job_id'], 'JOB-KEEP')

    def test_retry_keeps_job_and_ignores_late_completion(self):
        self.products('one')
        row = self.running()
        self.queue.attach_job(row['queue_id'], 'JOB-KEEP')
        self.queue.mark_cancelled_by_job('JOB-KEEP')
        self.assertIsNone(self.queue.mark_completed_by_job('JOB-KEEP', 'late.mp4'))
        self.queue.retry(row['queue_id'])
        self.assertIsNone(self.queue.mark_completed_by_job('JOB-KEEP', 'late.mp4'))
        retried = self.queue.claim_next()
        self.assertEqual(retried['job_id'], 'JOB-KEEP')
        self.assertEqual(retried['attempt'], 2)

    def test_concurrent_claims_have_only_one_owner(self):
        self.products('one', 'two', 'three')
        self.queue.resume()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: CreationQueue(self.temp.name).claim_next(), range(6)))
        self.assertEqual(sum(row is not None for row in results), 1)

    def test_pause_current_can_finish_but_next_cannot_start(self):
        self.products('one', 'two')
        row = self.running()
        self.queue.attach_job(row['queue_id'], 'JOB-1')
        self.queue.pause()
        self.queue.mark_completed_by_job('JOB-1', 'final.mp4')
        self.assertIsNone(self.queue.claim_next())
        self.queue.resume()
        self.assertTrue(self.queue.claim_next()['link'].endswith('/two'))

    def test_edit_and_move_only_pending_rows(self):
        rows = self.products('one', 'two', 'three')
        self.queue.move(rows[2]['queue_id'], -1)
        self.assertEqual(self.queue.snapshot()['items'][1]['queue_id'], rows[2]['queue_id'])
        self.queue.edit(rows[2]['queue_id'], 'https://s.shopee.co.th/updated')
        row = self.running()
        with self.assertRaises(ValueError): self.queue.edit(row['queue_id'], 'invalid')
        with self.assertRaises(ValueError): self.queue.remove(row['queue_id'])
        self.queue.remove(rows[2]['queue_id'])
        self.assertEqual(self.queue.snapshot()['total_count'], 2)

    def test_edit_preserves_gemini_model_when_provider_unchanged(self):
        row = self.products('one', provider='gemini', ai_web_model='pro')[0]
        expected = row['ai_web_model']
        self.queue.edit(row['queue_id'], 'https://s.shopee.co.th/two', provider='gemini')
        self.assertEqual(self.queue.get_item(row['queue_id'])['ai_web_model'], expected)

    def test_drama_relative_order_is_preserved(self):
        self.queue.enqueue_drama_series('SERIES-20260905-ABCDEF', 'ละคร', 3)
        row = self.products('one')[0]
        self.queue.move(row['queue_id'], -1)
        self.queue.move(row['queue_id'], -1)
        episodes = [i['episode_no'] for i in self.queue.snapshot()['items'] if i.get('mode') == 'drama']
        self.assertEqual(episodes, [1, 2, 3])

    def test_limits_and_invalid_links_are_atomic(self):
        with self.assertRaises(ValueError): self.products(*[str(n) for n in range(11)])
        with self.assertRaises(ValueError): self.queue.enqueue('product', ['https://s.shopee.co.th/good', 'https://example.com/not-shopee'])
        self.assertEqual(self.queue.snapshot()['total_count'], 0)
        for batch in range(3): self.products(*[f'{batch}-{n}' for n in range(10)])
        with self.assertRaises(ValueError): self.products('31')


class CreationQueueAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = MainWindow.__new__(MainWindow)
        self.app.story_queue = CreationQueue(self.temp.name)
        self.app._creation_dispatch_item = None
        self.app._schedule_next_story_queue_item = Mock()
        self.app._write_console = Mock()
        self.app._desktop_set_notice = Mock()
        self.app.voice_api_key = Mock(get=Mock(return_value='runtime-secret'))
        self.app.voice_reference_id = Mock(get=Mock(return_value='voice-current'))
        self.app.voice_reference_file = Mock(get=Mock(return_value=''))
        self.app._subtitle_store = Mock(return_value=Mock(load=Mock(return_value='runtime-secret')))
        self.app._compatible_extension = Mock(return_value=({'connected':True}, True))
        self.app.products = Mock(root=Path(self.temp.name))
        self.app.stories = Mock(root=Path(self.temp.name))
        self.app._product_pipeline_job_id = ''
        self.app._story_pipeline_job_id = ''

    def start(self, job='JOB-1', settings=None):
        q = self.app.story_queue
        q.enqueue('product', ['https://s.shopee.co.th/one'], settings=settings)
        q.resume(); row = q.claim_next()
        if job: q.attach_job(row['queue_id'], job)
        self.app._creation_dispatch_item = row
        return q.get_item(row['queue_id'])

    def test_preflight_pauses_without_claim_or_browser_commands(self):
        row = self.start(job='')
        self.app.voice_api_key.get.return_value = ''
        self.assertFalse(self.app._creation_prepare_dispatch(row))
        self.assertTrue(self.app.story_queue.snapshot()['paused'])
        self.assertEqual(self.app.story_queue.get_item(row['queue_id'])['status'], 'queued')

    def test_options_restore_settings_but_keep_runtime_secrets(self):
        self.start(settings={'voice_reference_id':'voice-A', 'render':{'width':1080}, 'voice_api_key':'not-saved'})
        options = self.app._creation_pipeline_options({'voice_api_key':'current-secret', 'render':{'width':720}})
        self.assertEqual(options['voice_api_key'], 'current-secret')
        self.assertEqual(options['render']['width'], 1080)
        self.assertEqual(options['voice_reference_id'], 'voice-A')
        self.assertEqual(options['queue_attempt'], 1)

    def test_cancelled_or_stale_attempt_cannot_attach_job(self):
        row = self.start(job='')
        event = threading.Event()
        with self.assertRaises(OperationCancelled):
            self.app._creation_attach_product({'queue_id':row['queue_id'], 'queue_attempt':0}, 'JOB-STALE', event)
        event.set()
        with self.assertRaises(OperationCancelled):
            self.app._creation_attach_product({'queue_id':row['queue_id'], 'queue_attempt':1}, 'JOB-STALE', event)
        self.assertEqual(self.app.story_queue.get_item(row['queue_id'])['job_id'], 'JOB-STALE')

    def test_attach_job_before_work_and_terminal_file_gate(self):
        row = self.start(job='')
        self.app._creation_attach_product({'queue_id':row['queue_id'], 'queue_attempt':1}, 'JOB-1', threading.Event())
        self.app._creation_product_terminal('JOB-1', 'completed', output=Path(self.temp.name)/'missing.mp4')
        self.assertEqual(self.app.story_queue.get_item(row['queue_id'])['status'], 'failed')
        self.assertTrue(self.app.story_queue.snapshot()['paused'])

    def test_three_products_complete_in_order_only_after_final_files(self):
        q = self.app.story_queue
        q.enqueue('product', [f'https://s.shopee.co.th/{n}' for n in range(3)])
        q.resume()
        for n in range(3):
            row = q.claim_next()
            self.assertTrue(row['link'].endswith('/'+str(n)))
            self.app._creation_dispatch_item = row
            q.attach_job(row['queue_id'], f'JOB-{n}')
            self.assertIsNone(q.claim_next())
            target = Path(self.temp.name)/f'final-{n}.mp4'; target.write_bytes(b'fixture-final')
            self.app._creation_product_terminal(f'JOB-{n}', 'completed', output=target)
        self.assertEqual(q.snapshot()['counts']['completed'], 3)
        self.assertIsNone(q.claim_next())

    def test_remote_failure_pauses_and_preserves_job(self):
        row = self.start()
        self.app._creation_product_terminal('JOB-1', 'failed', 'Extension หลุด ผลยังไม่ทราบ')
        self.assertTrue(self.app.story_queue.snapshot()['paused'])
        self.assertEqual(self.app.story_queue.get_item(row['queue_id'])['job_id'], 'JOB-1')
        self.assertIsNone(self.app.story_queue.claim_next())

    def test_bad_input_before_import_can_skip(self):
        self.start(job='')
        self.app._creation_product_terminal('', 'failed', 'ไม่พบสินค้าจากลิงก์นี้')
        self.assertFalse(self.app.story_queue.snapshot()['paused'])

    def test_start_exception_pauses_instead_of_stranding_running(self):
        row = self.start()
        self.app._start_next_story_queue_item = Mock(side_effect=RuntimeError('dispatch failed'))
        self.app._creation_queue_tick()
        self.assertTrue(self.app.story_queue.snapshot()['paused'])
        self.assertEqual(self.app.story_queue.get_item(row['queue_id'])['status'], 'failed')

    def test_old_worker_blocks_next_even_after_ui_cancel_clears_busy(self):
        self.start()
        self.app._creation_product_worker = Mock(is_alive=Mock(return_value=True))
        self.app._start_next_story_queue_item()
        self.app._schedule_next_story_queue_item.assert_called_once_with(500)

    def test_manual_flow_also_blocks_queue(self):
        self.start()
        self.app._manual_multi_flow_job_id = 'JOB-MANUAL'
        self.app._start_next_story_queue_item()
        self.app._schedule_next_story_queue_item.assert_called_once_with(1000)

    def test_restart_recovers_saved_final_without_regeneration(self):
        row = self.start()
        folder = Path(self.temp.name)/'JOB-1'; folder.mkdir()
        (folder/'final.mp4').write_bytes(b'fixture-final')
        self.app.products.get_job.return_value = {'automation_status':'completed', 'video_status':'ready', 'video_path':'final.mp4'}
        self.app.story_queue.recover_on_startup()
        self.assertTrue(self.app._creation_restore_final(self.app.story_queue.get_item(row['queue_id'])))
        self.assertEqual(self.app.story_queue.snapshot()['counts']['completed'], 1)
        self.app._compatible_extension.assert_not_called()

    def test_story_terminal_failure_does_not_skip_into_next_browser_job(self):
        row = self.start()
        self.app._creation_story_failure(row, 'Google Flow still unknown')
        self.assertTrue(self.app.story_queue.snapshot()['paused'])

    def test_state_does_not_send_frozen_paths_or_credentials(self):
        self.start(settings={'voice_reference_file':'private-reference.wav', 'voice_api_key':'SECRET'})
        value = json.dumps(self.app._creation_queue_state())
        self.assertNotIn('private-reference', value)
        self.assertNotIn('SECRET', value)

    def test_preparing_queue_does_not_change_global_voice_selection(self):
        row = self.start(job='', settings={'voice_reference_id':'frozen-voice'})
        self.assertTrue(self.app._creation_prepare_dispatch(row))
        self.app.voice_reference_id.set.assert_not_called()

    def test_edit_rejects_duplicate_and_recapture_preserves_provider_model(self):
        queue = self.app.story_queue
        rows = queue.enqueue('product', ['https://s.shopee.co.th/a','https://s.shopee.co.th/b'], provider='gemini')['items']
        with self.assertRaises(ValueError): queue.edit(rows[1]['queue_id'], rows[0]['link'])
        updated = queue.edit(rows[0]['queue_id'], rows[0]['link'], settings={'provider':'chatgpt','ai_web_model':'auto','render':{'width':720}})
        self.assertEqual(updated['settings']['provider'], 'gemini')
        self.assertEqual(updated['settings']['ai_web_model'], updated['ai_web_model'])

    def test_drama_manual_recovery_retains_existing_completion_contract(self):
        queue = self.app.story_queue
        row = queue.enqueue_drama_series('SERIES-20260905-ABCDEF','ละคร',2)['items'][0]
        queue.resume(); queue.claim_next(); queue.attach_job(row['queue_id'],'STORY-EP1')
        queue.mark_failed_by_job('STORY-EP1','failed')
        recovered = queue.mark_completed_by_job('STORY-EP1','recovered.mp4')
        self.assertEqual(recovered['status'], 'completed')

    def test_cancel_queue_calls_existing_cancel_not_new_browser_driver(self):
        self.start()
        self.app._product_pipeline_job_id = 'JOB-1'
        self.app._cancel_product_pipeline = Mock()
        self.app._creation_queue_action('creation_cancel_current', {})
        self.assertTrue(self.app.story_queue.snapshot()['paused'])
        self.app._cancel_product_pipeline.assert_called_once()

    def test_import_placeholder_cancel_finishes_its_bound_queue_row(self):
        row = self.start(job='JOB-IMPORTED')
        self.assertTrue(self.app._creation_product_terminal('กำลังสร้าง Job', 'cancelled', 'user cancelled'))
        self.assertEqual(self.app.story_queue.get_item(row['queue_id'])['status'], 'cancelled')
        self.assertEqual(self.app.story_queue.get_item(row['queue_id'])['job_id'], 'JOB-IMPORTED')

    def test_cancelled_story_exception_cannot_become_retryable_error(self):
        import queue
        self.app.events = queue.Queue()
        event = threading.Event(); event.set()
        self.app._story_worker('STORY-OLD', Mock(side_effect=RuntimeError('stopped socket')), event)
        kind, payload = self.app.events.get_nowait()
        self.assertEqual(kind, 'story_cancelled')
        self.assertIs(payload['cancel_event'], event)


if __name__ == '__main__':
    unittest.main()
