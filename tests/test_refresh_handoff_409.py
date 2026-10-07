import subprocess
import unittest
from pathlib import Path
from ui.story_recovery import pending_short, stopped_short
from ui.creation_queue import CreationQueueMixin
from core.cancellable_process import hidden_process_kwargs


class RefreshHandoff409Tests(unittest.TestCase):
    def test_actual_extension_refresh_race_readiness_and_progress_channel(self):
        if not (Path(__file__).resolve().parents[1] / 'deliverables/SmartFlow_AI_Extension_0.15.408/background.js').is_file():
            self.skipTest('Historical 408 Extension is not available in this checkout')
        result=subprocess.run(['node','tests/refresh_handoff_409.cjs'],cwd=Path(__file__).resolve().parents[1],
                              capture_output=True,text=True,encoding='utf-8',timeout=30,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_stop_visible_but_explicit_dismiss_hidden(self):
        from ui.main_window import MainWindow
        job={'status':'cancelled','video_status':'cancelled','cancel_requested':True,
             'pipeline_stage':'user_cancel','cancel_reason':'ผู้ใช้ยกเลิกการทำงาน'}
        summary=MainWindow._desktop_story_row(job)
        self.assertEqual(summary['cancel_reason'],job['cancel_reason'])
        self.assertTrue(stopped_short(job));self.assertTrue(pending_short(job))
        self.assertTrue(CreationQueueMixin._creation_job_recoverable('story',job))
        for patch in ({'cancel_reason':'ผู้ใช้ยกเลิกงานเก่าจากหน้ารายการทำต่อ'},
                      {'cancel_reason':'ผู้ใช้ล้างรายการทำต่อทั้งหมดจากหน้าเล่าเรื่อง Shorts'},
                      {'status':'deleted'},{'series_id':'SERIES'},{'product_story':True}):
            self.assertFalse(pending_short({**job,**patch}))
            self.assertFalse(CreationQueueMixin._creation_job_recoverable('story',{**job,**patch}))

    def test_stop_discovery_preserves_files_and_does_not_resume(self):
        import test_creation_queue_recovery_controls as fixture
        from unittest.mock import Mock
        env=fixture.CreationQueueRecoveryControlsTests()
        env.setUp()
        try:
            folder=env.job('STORY-STOPPED',status='cancelled',automation_status='',cancel_requested=True,
                           pipeline_stage='user_cancel',cancel_reason='ผู้ใช้ยกเลิกการทำงาน')
            before={p:p.read_bytes() for p in folder.rglob('*') if p.is_file()}
            env.app.bridge.pending_job_commands=Mock(return_value=[])
            jobs=env.app._creation_queue_state()['recoverable_jobs']
            self.assertEqual([j['job_id'] for j in jobs],['STORY-STOPPED'])
            self.assertEqual(before,{p:p.read_bytes() for p in before})
            env.app.bridge.queue_extension_command.assert_not_called()
            env.app._schedule_next_story_queue_item.assert_not_called()
        finally:env.doCleanups()
