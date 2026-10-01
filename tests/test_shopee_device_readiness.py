import threading
import unittest
from unittest.mock import Mock, PropertyMock, patch

from core.shopee_posting.device import ShopeeDevice, DeviceUnavailable, ReviewRequired
from core.shopee_posting.workflow import account_on_home, video_feed_visible, video_feed_account


class ReadinessTests(unittest.TestCase):
    def device(self, infos):
        d=ShopeeDevice.__new__(ShopeeDevice);d.adb=Mock();d.adb.prop.return_value='phone'
        d.identity='phone';d.stop=None;d.ui=Mock();d.on_device_state=Mock()
        type(d.ui).info=PropertyMock(side_effect=infos)
        return d

    def ready(self):
        return {'currentPackageName':'com.shopee.th','screenOn':True}

    def test_transient_foreground_waits_and_resumes_without_gesture(self):
        d=self.device([{'currentPackageName':'android','screenOn':True},self.ready(),self.ready()])
        with patch('core.shopee_posting.device.time.sleep'):self.assertEqual(d.foreground(),self.ready())
        self.assertEqual([c.args[0] for c in d.on_device_state.call_args_list],[True,False])
        d.ui.app_start.assert_not_called();d.adb.shell.assert_not_called()

    def test_locked_phone_never_wakes_unlocks_or_clicks(self):
        d=self.device([{'screenOn':False,'currentPackageName':'com.android.systemui'}])
        with self.assertRaises(DeviceUnavailable) as e:d.foreground()
        self.assertFalse(e.exception.evidence['screen_on']);d.adb.shell.assert_not_called()

    def test_wrong_phone_not_retried(self):
        d=self.device([self.ready()]);d.adb.prop.return_value='other'
        with self.assertRaises(ReviewRequired):d.foreground()
        d.on_device_state.assert_not_called()

    def test_persistent_wrong_app_returns_evidence_not_false_ready(self):
        d=self.device([{'screenOn':True,'currentPackageName':'com.other'}])
        with self.assertRaises(DeviceUnavailable) as e:d.foreground(timeout=0)
        self.assertEqual(e.exception.evidence['foreground_package'],'com.other');d.adb.shell.assert_not_called()

    def test_missing_screen_state_not_assumed_ready(self):
        d=self.device([{'currentPackageName':'com.shopee.th'}])
        with self.assertRaises(DeviceUnavailable):d.foreground(timeout=0)

    def test_cancellation_immediate(self):
        d=self.device([self.ready()]);d.stop=threading.Event();d.stop.set()
        with self.assertRaises(ReviewRequired):d.foreground()

    def test_open_visible_shopee_does_not_relaunch(self):
        d=self.device([self.ready()]*4)
        with patch('core.shopee_posting.device.time.sleep'):d.open()
        d.ui.app_start.assert_not_called()

    def test_open_other_app_launches_once_then_waits_stable(self):
        d=self.device([{'screenOn':True,'currentPackageName':'other'},self.ready(),self.ready(),self.ready()])
        with patch('core.shopee_posting.device.time.sleep'):d.open()
        d.ui.app_start.assert_called_once_with('com.shopee.th')

    def test_scrolled_me_profile_scrolls_only_exact_list(self):
        d=self.device([self.ready()]);d.snapshot=Mock(side_effect=[('',[
            {'package':d.package,'resource-id':d.package+':id/main_view','scrollable':'true'},
            {'package':d.package,'resource-id':'meCircleView'}]),('',[
            {'package':d.package,'resource-id':'labelUserName','text':'test-account'}])])
        with patch('core.shopee_posting.device.time.sleep'):self.assertEqual(d.profile_account(),'test-account')
        d.ui.assert_called_once_with(resourceId='com.shopee.th:id/main_view')
        d.ui.return_value.scroll.backward.assert_called_once_with()

    def test_no_profile_proof_never_scrolls_feed_or_guesses_account(self):
        d=self.device([]);d.snapshot=Mock(return_value=('',[{'package':d.package,'text':'name'}]))
        with patch('core.shopee_posting.device.time.monotonic',side_effect=[0,1,16]),patch('core.shopee_posting.device.time.sleep'),self.assertRaises(ReviewRequired):d.profile_account()
        d.ui.assert_not_called()

    def test_multiple_usernames_stop(self):
        d=self.device([]);n={'package':d.package,'resource-id':'labelUserName','text':'test'};d.snapshot=Mock(return_value=('',[n,n]))
        with self.assertRaises(ReviewRequired):d.profile_account()

    def test_account_route_uses_profile_reader(self):
        d=Mock();d.profile_account.return_value='test';d.snapshot.return_value=('',[])
        self.assertEqual(account_on_home(d),'test');d.tap.assert_called_once_with(**{'content-desc':'tab_bar_button_me'})

    def test_fullscreen_feed_account_uses_only_own_profile(self):
        d=Mock(package='com.shopee.th');feed=[dict(package=d.package,enabled='true',**{'content-desc':desc}) for desc in ['click me page icon','click top right create icon']]
        d.snapshot.side_effect=[('',feed),('',[{'package':d.package,'text':'ชื่อผู้ใช้: expected-account'}])]
        self.assertEqual(account_on_home(d),'expected-account')
        self.assertEqual([c.kwargs for c in d.tap.call_args_list],[{'content-desc':'click me page icon'},{'content-desc':'click to get back'}])
        d.profile_account.assert_not_called();d.ui.press.assert_not_called()

    def test_foreign_creator_avatar_and_partial_feed_not_account_proof(self):
        d=Mock(package='com.shopee.th');d.snapshot.return_value=('',[{'package':d.package,'enabled':'true','content-desc':'click other profile avatar icon'}])
        self.assertFalse(video_feed_visible(d));d.tap.assert_not_called()

    def test_ambiguous_video_profile_names_stop_before_navigation_or_post(self):
        d=Mock(package='com.shopee.th');d.snapshot.return_value=('',[{'package':d.package,'text':'ชื่อผู้ใช้: one'},{'package':d.package,'text':'ชื่อผู้ใช้: two'}])
        with self.assertRaises(ReviewRequired):video_feed_account(d)
        d.tap.assert_called_once_with(**{'content-desc':'click me page icon'})

    def test_hide_keyboard_waits_for_closed_state_and_only_one_back(self):
        d=self.device([]);keyboard=[{'resource-id':'android:id/input_method_nav_back'}]
        d.snapshot=Mock(side_effect=[('',keyboard),('',keyboard),('',[]),('',[])])
        with patch('core.shopee_posting.device.time.sleep'):d.hide_keyboard()
        d.ui.press.assert_called_once_with('back');self.assertEqual(d.snapshot.call_count,4)

    def test_keyboard_timeout_does_not_back_out_of_composer(self):
        d=self.device([]);d.snapshot=Mock(return_value=('',[{'resource-id':'android:id/input_method_nav_back'}]))
        with patch('core.shopee_posting.device.time.monotonic',side_effect=[0,1,9]),patch('core.shopee_posting.device.time.sleep'),self.assertRaises(ReviewRequired):d.hide_keyboard()
        d.ui.press.assert_called_once_with('back')

    def test_slow_wifi_reads_still_require_three_equal_in_screen_samples(self):
        d=self.device([dict(self.ready(),displayWidth=1080,displayHeight=2340)]*3)
        d.find=Mock(return_value={'bounds':'[955,2176][1025,2246]'})
        with patch('core.shopee_posting.device.time.monotonic',side_effect=[0,3,7,11]),patch('core.shopee_posting.device.time.sleep'):
            self.assertEqual(d.stable_target()['bounds'],'[955,2176][1025,2246]')
        self.assertEqual(d.find.call_count,3);d.adb.shell.assert_not_called()


if __name__=='__main__':unittest.main()
