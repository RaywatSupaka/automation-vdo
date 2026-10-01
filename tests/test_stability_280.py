import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from core.cancellable_process import OperationCancelled
from core.video_composer import MultiFlowComposer
from ui.main_window import MainWindow


class Stability280Tests(unittest.TestCase):
    def test_motion_progress_extends_wait_only_for_fresh_real_activity(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for active, fresh, expected in ((True,True,True),(True,False,False),(False,True,False)):
            with self.subTest(active=active,fresh=fresh):
                clock=[0.0]
                event=Mock();event.is_set.return_value=False
                def wait(_):clock[0]+=2;return False
                event.wait.side_effect=wait
                window=MainWindow.__new__(MainWindow)
                window.products=SimpleNamespace(root=Path(temp.name),get_job=lambda _: {'image_ai_provider':'gemini'})
                window.bridge=SimpleNamespace(REQUIRED_EXTENSION_VERSION='test',extension_status=lambda:{'clients':[{
                    'version':'test','ai_job_id':'JOB-X','ai_provider':'gemini','ai_step':'preparing_flow_prompt',
                    'ai_updated_at':str(clock[0]) if fresh else 'same','ai_response_active':active,'ai_response_signature':'same'}]})
                window._chrome_window_available=lambda:True
                window._product_progress_event=Mock()
                with patch('ui.main_window.time.monotonic',side_effect=lambda:clock[0]):
                    if expected:
                        window._wait_product_job('JOB-X',lambda _:clock[0]>=40,event,10,'ai','timeout')
                        self.assertGreaterEqual(clock[0],40)
                    else:
                        with self.assertRaises(TimeoutError):window._wait_product_job('JOB-X',lambda _:False,event,10,'ai','timeout')

    def test_cancelled_render_never_promotes_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);clips=[root/'one.mp4',root/'two.mp4']
            for clip in clips:clip.write_bytes(b'fixture')
            output=root/'final.mp4';output.write_bytes(b'keep original')
            composer=MultiFlowComposer.__new__(MultiFlowComposer);composer.ffmpeg=Path('ffmpeg');composer.ffprobe=Path('ffprobe')
            composer.media_info=lambda _: {'duration':1.0}
            event=threading.Event()
            def render(command,**kwargs):
                self.assertIs(kwargs['cancel_event'],event)
                Path(command[-1]).write_bytes(b'candidate')
                event.set()
                return SimpleNamespace(returncode=0,stderr='')
            with patch('core.video_composer.run_cancellable',side_effect=render):
                with self.assertRaises(OperationCancelled):composer.compose(clips,output,cancel_event=event)
            self.assertEqual(output.read_bytes(),b'keep original')
            self.assertFalse(list(root.glob('*.partial.mp4')))

    def test_cancel_before_render_does_not_start_process(self):
        event=threading.Event();event.set()
        composer=MultiFlowComposer.__new__(MultiFlowComposer)
        with patch('core.video_composer.run_cancellable') as run:
            with self.assertRaises(OperationCancelled):composer.compose([], 'unused.mp4',cancel_event=event)
            run.assert_not_called()
