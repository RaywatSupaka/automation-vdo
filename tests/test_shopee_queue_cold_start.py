"""Explicit queue lifecycle; synthetic device only, no real force-stop or Post."""
import copy
import unittest
from unittest.mock import Mock, patch

from core.shopee_posting.device import ReviewRequired
from core.shopee_posting.workflow import restart_before_first_post, P
from shopee_preflight_fixture import ready_device


class ColdStartTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(id='first',phase='prepared',posting_run_id='run',
                      run_contract=dict(close_before_first_post=True,account='owner',device_id='phone'))
        self.state=dict(items=[self.row],posting_run=dict(id='run',status='running',ids=['first','next'],current_id='first',account='owner'))
        self.store=Mock();self.store.read.side_effect=lambda:self.state
        self.d=Mock(identity='phone',package='com.shopee.th')
        self.d.ui.info=dict(screenOn=True,currentPackageName='com.shopee.th')
        self.d.snapshot.return_value=('<hierarchy/>',[]);self.d.adb.shell.return_value=Mock(returncode=0)

    def restart(self):return restart_before_first_post(self.d,self.store,'first','owner','run')

    def test_first_clip_closes_then_launches_even_if_foreground_still_reports_shopee(self):
        order=[]
        self.d.adb.shell.side_effect=lambda *a,**k:(order.append('close') or Mock(returncode=0))
        self.d.ui.app_start.side_effect=lambda p:order.append('open')
        self.d.foreground.side_effect=lambda **kw:order.append('ready')
        before=copy.deepcopy(self.state)
        self.assertTrue(self.restart());self.assertEqual(order,['close','open','ready'])
        self.d.adb.shell.assert_called_once_with('am','force-stop','com.shopee.th',timeout=10)
        self.assertEqual(self.state,before);self.assertIs(self.d._shopee_closed,False)
        self.d.tap.assert_not_called()

    def test_old_queues_keep_captured_policy(self):
        del self.row['run_contract']['close_before_first_post']
        self.assertFalse(self.restart());self.d.verify.assert_not_called();self.d.adb.shell.assert_not_called()

    def test_only_first_current_unsent_row_of_running_owned_queue(self):
        original=copy.deepcopy(self.state)
        changes=[lambda s:s['posting_run'].update(id='old'),lambda s:s['posting_run'].update(status='pausing'),
                 lambda s:s['posting_run'].update(current_id='next'),lambda s:s['posting_run'].update(ids=['next','first']),
                 lambda s:s['posting_run'].update(account='other'),lambda s:s['items'][0].update(posting_run_id='old'),
                 lambda s:s['items'][0].update(phase='processing'),lambda s:s['items'][0].update(publish_intent={'id':'old'}),
                 lambda s:s['items'][0]['run_contract'].update(device_id='other'),lambda s:s['items'][0]['run_contract'].update(account='other')]
        for change in changes:
            self.state=copy.deepcopy(original);change(self.state)
            with self.assertRaises(ReviewRequired):self.restart()
        self.d.adb.shell.assert_not_called();self.d.ui.app_start.assert_not_called()

    def test_unconfirmed_previous_send_on_same_or_unknown_phone_is_never_closed(self):
        for phase in ('send_pending','processing','unknown','review'):
            for phone in ('phone',None):
                self.state['items']=[self.row,dict(id='old',phase=phase,publish_intent={'id':'old-send','device_id':phone})]
                with self.subTest(phase=phase,phone=phone),self.assertRaises(ReviewRequired):self.restart()
        self.d.adb.shell.assert_not_called()

    def test_other_phone_or_completed_history_is_not_reset(self):
        for old in (dict(id='old',phase='unknown',publish_intent={'id':'old-send','device_id':'another-phone'}),
                    dict(id='old',phase='published',publish_intent={'id':'old-send','device_id':'phone'})):
            self.state['items']=[self.row,old];before=copy.deepcopy(self.state)
            self.assertTrue(self.restart());self.assertEqual(self.state,before)

    def test_native_uploading_blocks_close_but_caption_text_is_not_a_banner(self):
        self.d.snapshot.return_value=('',[dict(package='com.shopee.th',text='กำลังอัปโหลด')])
        with self.assertRaises(ReviewRequired):self.restart()
        self.d.adb.shell.assert_not_called()
        self.d.snapshot.return_value=('',[{'package':'com.shopee.th','text':'กำลังอัปโหลด','resource-id':P+'et_caption'}])
        self.assertTrue(self.restart())

    def test_user_authorized_reset_can_leave_unsent_old_composer_without_clearing_data(self):
        self.d.snapshot.return_value=('',[{'package':'com.shopee.th','resource-id':P+'et_caption','text':'unsent old draft'}])
        self.assertTrue(self.restart())
        self.d.adb.shell.assert_called_once_with('am','force-stop','com.shopee.th',timeout=10)
        self.d.ui.app_clear.assert_not_called();self.d.ui.press.assert_not_called()

    def test_locked_phone_or_wrong_identity_never_restarts(self):
        self.d.ui.info['screenOn']=False
        with self.assertRaises(ReviewRequired):self.restart()
        self.d.ui.info['screenOn']=True;self.d.verify.side_effect=ReviewRequired('wrong phone or cancelled')
        with self.assertRaises(ReviewRequired):self.restart()
        self.d.adb.shell.assert_not_called()

    def test_state_change_during_phone_read_is_rechecked_before_close(self):
        self.d.snapshot.side_effect=lambda:(self.state['posting_run'].update(status='pausing') or ('',[]))
        with self.assertRaises(ReviewRequired):self.restart()
        self.d.adb.shell.assert_not_called()

    def test_failed_close_or_lost_ack_never_retries_or_launches(self):
        self.d.adb.shell.return_value=Mock(returncode=1)
        with self.assertRaises(ReviewRequired):self.restart()
        self.d.adb.shell.assert_called_once();self.d.ui.app_start.assert_not_called()
        self.d.adb.shell.reset_mock();self.d.adb.shell.side_effect=OSError('lost ACK')
        with self.assertRaises(OSError):self.restart()
        self.d.adb.shell.assert_called_once();self.d.ui.app_start.assert_not_called()

    def test_launch_failure_or_cancel_after_close_never_posts(self):
        self.d.ui.app_start.side_effect=OSError('launch failed')
        with self.assertRaises(OSError):self.restart()
        self.d.adb.shell.assert_called_once();self.d.tap.assert_not_called()
        self.assertIs(self.d._shopee_closed,True)

    def test_next_clip_open_obeys_confirmed_close_even_with_stale_accessibility_package(self):
        d=ready_device();d._shopee_closed=True
        with patch('core.shopee_posting.device.time.sleep'):
            d.open();d.open()
        d.ui.app_start.assert_called_once_with('com.shopee.th')
        self.assertIs(d._shopee_closed,False);d.adb.shell.assert_not_called()
