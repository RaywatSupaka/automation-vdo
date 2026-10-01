import subprocess
import tempfile
import unittest
import threading
from pathlib import Path
from unittest.mock import Mock
from ui.main_window import MainWindow


class SavedTabCleanupTests(unittest.TestCase):
    def test_bridge_requires_saved_checkpoint_and_freezes_only_exact_flow_run(self):
        from core.local_bridge import LocalBridge
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'STORY-X';folder.mkdir()
            row={'flow_clips':{'1':'scene.mp4'}}
            manager=Mock(root=root);manager.get.return_value=row
            bridge=LocalBridge.__new__(LocalBridge)
            bridge.membership=None  # Isolated legacy cleanup fixture, no license service.
            bridge.stories=manager;bridge.products=Mock()
            bridge._extension_lock=threading.RLock();bridge._extension_commands=[]
            bridge._extension_runs={('flow','STORY-X',1):{'run_id':'RUN-F1','updated_at':1},
                                    ('flow','STORY-X',2):{'run_id':'RUN-F2','updated_at':2},
                                    ('ai','STORY-X',0):{'run_id':'RUN-AI','updated_at':3}}
            with self.assertRaisesRegex(ValueError,'ยังไม่ได้บันทึก'):
                bridge.queue_extension_command('close_automation_browser','STORY-X',1)
            self.assertEqual(bridge._extension_commands,[])
            (folder/'scene.mp4').write_bytes(b'saved')
            cmd=bridge.queue_extension_command('close_automation_browser','STORY-X',1)
            self.assertEqual(cmd['cleanup_runs'],['RUN-F1'])
            self.assertEqual(cmd['cleanup_shot_index'],1)
            self.assertEqual(bridge._extension_runs[('ai','STORY-X',0)]['run_id'],'RUN-AI')
            row['flow_clips']['1']='../escape.mp4'
            (root/'escape.mp4').write_bytes(b'other')
            with self.assertRaises(ValueError):
                bridge.queue_extension_command('close_automation_browser','STORY-X',1)

    def test_cover_actual_source(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['node','tests/cover_cleanup_harness.js'],cwd=root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_only_saved_media_queues_cleanup_and_failure_is_not_render_failure(self):
        window=MainWindow.__new__(MainWindow);window.cfg={};window.bridge=Mock()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'scene.mp4'
            window._close_saved_flow_tab('STORY-X',1,path)
            window.bridge.queue_extension_command.assert_not_called()
            path.write_bytes(b'video')
            window._close_saved_flow_tab('STORY-X',1,path)
            window.bridge.queue_extension_command.assert_called_once_with('close_automation_browser','STORY-X',1)
            window.bridge.queue_extension_command.side_effect=RuntimeError('offline')
            self.assertIsNone(window._close_saved_flow_tab('STORY-X',1,path))
            self.assertEqual(path.read_bytes(),b'video')
