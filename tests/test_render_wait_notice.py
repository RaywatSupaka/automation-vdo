import subprocess
import unittest
from unittest.mock import Mock, patch

from core.cancellable_process import run_cancellable, OperationCancelled


class RenderWaitNoticeTests(unittest.TestCase):
    def test_notice_without_cancel_event_preserves_result(self):
        process = Mock(returncode=0)
        process.communicate.side_effect = [subprocess.TimeoutExpired('render', .25), ('ok', '')]
        process.poll.return_value = 0
        notice = Mock()
        with patch('core.cancellable_process.subprocess.Popen', return_value=process), patch('core.cancellable_process.time.monotonic', side_effect=[0, 1, 6]):
            result = run_cancellable(['render'], on_wait=notice)
        notice.assert_called_once_with(6)
        self.assertEqual(result.stdout, 'ok')
        process.kill.assert_not_called()

    def test_cancel_takes_priority_over_notice(self):
        process = Mock()
        process.communicate.side_effect = [subprocess.TimeoutExpired('render', .25), ('', '')]
        process.poll.return_value = 0
        event = Mock()
        event.is_set.side_effect = [False, True]
        notice = Mock()
        with patch('core.cancellable_process.subprocess.Popen', return_value=process):
            with self.assertRaises(OperationCancelled):
                run_cancellable(['render'], cancel_event=event, on_wait=notice)
        notice.assert_not_called()
        process.terminate.assert_called_once()
