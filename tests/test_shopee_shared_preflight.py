"""No phone connection: real publisher/store/observer with synthetic phone I/O."""
import copy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from core.shopee_posting.device import ReviewRequired
from core.shopee_posting.options import DEFAULT_OPTIONS
from core.shopee_posting.progress import start_run
from core.shopee_posting.publish import publish_current
from core.shopee_posting.settings import P, CONTROLS, RESOURCES, verify_options, observe_options, apply_options
from core.shopee_posting.store import PostingStore, file_hash
from shopee_preflight_fixture import ready_device


class SharedObservationTests(unittest.TestCase):
    def test_four_controls_share_three_trees_and_two_images(self):
        d=ready_device();proof=verify_options(d,DEFAULT_OPTIONS)
        self.assertEqual(proof['options'],DEFAULT_OPTIONS);self.assertTrue(proof['sharing_off'])
        self.assertEqual(d.ui.dump_hierarchy.call_count,3)
        self.assertEqual(d.ui.screenshot.call_count,2)
        d.adb.shell.assert_not_called()

    def test_compare_previous_verifier_io_not_wall_time(self):
        old=ready_device()
        with patch('core.shopee_posting.device.time.sleep'):
            for control,label,text in CONTROLS.values():
                old.find(**{'resource-id':P+label,'text':text});old.visual_green(P+control)
            for control in ('iv_whatsapp','iv_facebook'):old.visual_green(P+control)
        self.assertEqual((old.ui.dump_hierarchy.call_count,old.ui.screenshot.call_count),(22,8))
        new=ready_device();verify_options(new,DEFAULT_OPTIONS)
        self.assertEqual((new.ui.dump_hierarchy.call_count,new.ui.screenshot.call_count),(3,2))

    def test_already_correct_settings_do_not_verify_again_or_tap(self):
        d=ready_device();apply_options(d,DEFAULT_OPTIONS)
        self.assertEqual(d.ui.dump_hierarchy.call_count,3);d.adb.shell.assert_not_called()

    def test_change_one_switch_one_gesture_then_shared_final_read(self):
        d=ready_device();d.fixture_values[P+'ai_generated_toggle']=False
        d.adb.shell.side_effect=lambda *a,**k:(d.fixture_values.update({P+'ai_generated_toggle':True}) or Mock(returncode=0))
        with patch('core.shopee_posting.device.time.sleep'):
            self.assertEqual(apply_options(d,DEFAULT_OPTIONS)['options'],DEFAULT_OPTIONS)
        self.assertEqual(d.adb.shell.call_count,1)

    def test_blank_or_obscured_pixels_cannot_mean_off(self):
        for color in ('white','black','red'):
            with self.subTest(color=color):
                d=ready_device();d.ui.screenshot.side_effect=None;d.ui.screenshot.return_value=Image.new('RGB',(400,800),color)
                with self.assertRaises(ReviewRequired):verify_options(d,DEFAULT_OPTIONS)
                d.adb.shell.assert_not_called()

    def test_missing_duplicate_disabled_hidden_foreign_controls(self):
        for kind in ('missing','duplicate','disabled','hidden','foreign','outside','negative','zero'):
            with self.subTest(kind=kind):
                d=ready_device();node=next(n for n in d.fixture_nodes if n['resource-id']==RESOURCES[0])
                if kind=='missing':d.fixture_nodes.remove(node)
                if kind=='duplicate':d.fixture_nodes.append(dict(node))
                if kind=='disabled':node['enabled']='false'
                if kind=='hidden':node['visible-to-user']='false'
                if kind=='foreign':node['package']='another.app'
                if kind=='outside':node['bounds']='[390,100][490,156]'
                if kind=='negative':node['bounds']='[-10,100][90,156]'
                if kind=='zero':node['bounds']='[10,100][10,156]'
                with self.assertRaises(ReviewRequired):verify_options(d,DEFAULT_OPTIONS)
                d.adb.shell.assert_not_called()

    def test_moving_control_between_image_and_tree_is_rejected(self):
        d=ready_device();shot=d.ui.screenshot.side_effect
        def moving():
            image=shot();next(n for n in d.fixture_nodes if n['resource-id']==RESOURCES[0])['bounds']='[10,101][110,157]'
            return image
        d.ui.screenshot.side_effect=moving
        with self.assertRaises(ReviewRequired):verify_options(d,DEFAULT_OPTIONS)

    def test_animation_changing_color_between_two_images_is_not_ready(self):
        d=ready_device();shot=d.ui.screenshot.side_effect
        def changing():
            image=shot();d.fixture_values[P+'ai_generated_toggle']=False;return image
        d.ui.screenshot.side_effect=changing
        with self.assertRaises(ReviewRequired):verify_options(d,DEFAULT_OPTIONS)

    def test_share_on_and_incorrect_option_block_post(self):
        for resource in (P+'iv_facebook',P+'iv_whatsapp',P+'allow_reuse_toggle',P+'ai_generated_toggle'):
            d=ready_device();d.fixture_values[resource]=not d.fixture_values[resource]
            with self.subTest(resource=resource),self.assertRaises(ReviewRequired):verify_options(d,DEFAULT_OPTIONS)

    def test_all_user_option_combinations_are_preserved(self):
        for reuse in (True,False):
            for ai in (True,False):
                d=ready_device();d.fixture_values[P+'allow_reuse_toggle']=reuse;d.fixture_values[P+'ai_generated_toggle']=ai
                options={'schema':1,'allow_reuse':reuse,'ai_label':ai}
                with self.subTest(reuse=reuse,ai=ai):self.assertEqual(apply_options(d,options)['options'],options)
                d.adb.shell.assert_not_called()

    def test_changed_label_is_not_assumed_to_mean_same_option(self):
        d=ready_device();next(n for n in d.fixture_nodes if n['resource-id']==P+'tv_allow_reuse')['text']='another setting'
        with self.assertRaises(ReviewRequired):verify_options(d,DEFAULT_OPTIONS)
        d.adb.shell.assert_not_called()

    def test_foreground_and_identity_errors_are_not_swallowed(self):
        for kind in ('locked','wrong_phone','cancelled'):
            d=ready_device()
            if kind=='locked':d.ui.info['screenOn']=False
            if kind=='wrong_phone':d.adb.prop.return_value='other'
            if kind=='cancelled':d.stop=threading.Event();d.stop.set()
            with self.subTest(kind=kind),self.assertRaises(ReviewRequired):verify_options(d,DEFAULT_OPTIONS)
            d.ui.screenshot.assert_not_called();d.adb.shell.assert_not_called()


class SharedPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=PostingStore(self.root)
        self.video=self.root/'final.mp4';self.video.write_bytes(b'unique test video')
        self.id=self.store.add([dict(item_id='fixture',title='Fixture',caption='caption',video_path=str(self.video),
                                     product_url='https://s.shopee.co.th/example')])[0]
        self.run=self.store.change(lambda s:start_run(s,[self.id],'owner','phone'))
        self.store.transition(self.id,{'draft'},'settings',video_sha256=file_hash(self.video),transfer={'album':'test'},
            run_contract=dict(account='owner',device_id='phone',post_options=dict(DEFAULT_OPTIONS),
                              video_sha256=file_hash(self.video)),latest_baseline={'account':'owner','latest_caption':'older'})
        self.d=ready_device(caption='caption')

    def row(self):return self.store.read()['items'][0]
    def publish(self):publish_current(self.d,self.store,self.id,'owner','Product',self.root/'proof')

    def test_success_claims_after_all_reads_then_one_gesture(self):
        at_press=[]
        def press(*a,**kw):
            row=self.row();self.assertEqual(row['phase'],'send_pending')
            self.assertEqual(row['publish_intent']['dispatch_state'],'press_committed')
            at_press.append((self.d.ui.dump_hierarchy.call_count,self.d.ui.screenshot.call_count))
            return Mock(returncode=0)
        self.d.adb.shell.side_effect=press;self.publish()
        self.assertEqual(self.row()['phase'],'processing');self.assertEqual(at_press,[(5,3)])
        self.assertEqual(self.d.adb.shell.call_count,1)
        self.assertEqual((self.d.ui.dump_hierarchy.call_count,self.d.ui.screenshot.call_count),(5,3))
        self.assertTrue((self.root/'proof'/'before_post.png').is_file())
        events=self.store.read()['posting_run']['events']
        self.assertTrue(any(e['step']=='preflight' and not e['send_started'] for e in events))
        with self.assertRaises(ReviewRequired):self.publish()
        self.assertEqual(self.d.adb.shell.call_count,1)

    def mutate_after_evidence(self, mutation):
        save=self.d.save_observation
        def captured(*a,**kw):save(*a,**kw);mutation()
        self.d.save_observation=captured

    def test_changed_caption_product_options_target_or_old_banner_no_claim(self):
        for kind in ('caption','product','extra_product','option','sharing','target','disabled','notice','keyboard'):
            with self.subTest(kind=kind):
                nodes=copy.deepcopy(self.d.fixture_nodes);values=dict(self.d.fixture_values)
                save=self.d.save_observation
                def mutate():
                    if kind in ('option','sharing'):
                        resource=P+('ai_generated_toggle' if kind=='option' else 'iv_whatsapp')
                        self.d.fixture_values[resource]=not self.d.fixture_values[resource]
                    elif kind=='extra_product':self.d.fixture_nodes.append(dict(next(n for n in self.d.fixture_nodes if n['resource-id']==P+'tv_product_title')))
                    elif kind=='notice':
                        # Exercise exact native-banner detection separately from flat fixture nodes.
                        original=self.d.ui.dump_hierarchy.side_effect
                        self.d.ui.dump_hierarchy.side_effect=lambda **kw:original(**kw).replace('</hierarchy>','<node package="com.shopee.th" enabled="true" class="android.view.ViewGroup" clickable="true"><node package="com.shopee.th" enabled="true" text="อัปโหลดสำเร็จ"/><node package="com.shopee.th" enabled="true" text="คลิกที่นี่เพื่อดูวิดีโอ"/></node></hierarchy>')
                    elif kind=='keyboard':self.d.fixture_nodes.append({'resource-id':'android:id/input_method_nav_back','package':'com.android.systemui'})
                    else:
                        resource={'caption':'et_caption','product':'tv_product_title','target':'btn_post','disabled':'btn_post'}[kind]
                        n=next(n for n in self.d.fixture_nodes if n['resource-id']==P+resource)
                        n['bounds' if kind=='target' else 'enabled' if kind=='disabled' else 'text']='[10,710][390,770]' if kind=='target' else 'false' if kind=='disabled' else 'changed'
                dump=self.d.ui.dump_hierarchy.side_effect
                self.mutate_after_evidence(mutate)
                with self.assertRaises(ReviewRequired):self.publish()
                self.assertNotIn('publish_intent',self.row());self.d.adb.shell.assert_not_called()
                self.d.fixture_nodes=nodes;self.d.fixture_values=values;self.d.save_observation=save;self.d.ui.dump_hierarchy.side_effect=dump

    def test_source_changed_before_preflight_no_phone_reads(self):
        self.video.write_bytes(b'changed')
        with self.assertRaises(ReviewRequired):self.publish()
        self.d.ui.dump_hierarchy.assert_not_called();self.d.adb.shell.assert_not_called()

    def test_evidence_write_failure_is_unsent(self):
        self.d.save_observation=Mock(side_effect=OSError('disk full'))
        with self.assertRaises(OSError):self.publish()
        self.store.settle_run([self.id],self.run,'disk full')
        self.assertEqual(self.row()['phase'],'review');self.assertNotIn('publish_intent',self.row())
        self.d.adb.shell.assert_not_called()

    def test_claim_write_failure_no_gesture(self):
        with patch.object(self.store,'claim_publish',side_effect=OSError('disk full')),self.assertRaises(OSError):self.publish()
        self.assertNotIn('publish_intent',self.row());self.d.adb.shell.assert_not_called()
        self.store.recover();self.assertEqual(self.row()['phase'],'review')

    def test_cancel_after_observation_before_claim_is_unsent(self):
        self.d.stop=threading.Event();commit=self.d.commit_observed_post
        def cancel(observation,claim):self.d.stop.set();return commit(observation,claim)
        self.d.commit_observed_post=cancel
        with self.assertRaises(ReviewRequired):self.publish()
        self.assertNotIn('publish_intent',self.row());self.d.adb.shell.assert_not_called()

    def test_stale_observation_before_claim_is_unsent(self):
        commit=self.d.commit_observed_post
        def stale(observation,claim):observation['monotonic_at']-=10;return commit(observation,claim)
        self.d.commit_observed_post=stale
        with self.assertRaises(ReviewRequired):self.publish()
        self.assertNotIn('publish_intent',self.row());self.d.adb.shell.assert_not_called()

    def test_lost_ack_keeps_intent_and_cannot_replay_after_restart(self):
        self.d.adb.shell.side_effect=OSError('lost ACK')
        with self.assertRaises(OSError):self.publish()
        self.assertEqual(self.row()['phase'],'unknown');intent=self.row()['publish_intent']
        self.store.recover();self.assertEqual(self.row()['publish_intent'],intent)
        with self.assertRaises(ReviewRequired):self.publish()
        self.assertEqual(self.d.adb.shell.call_count,1)

    def test_slow_claim_blocks_stale_gesture_without_clearing_intent(self):
        commit=self.d.commit_observed_post
        def slow(observation,claim):
            def claimed():claim();observation['monotonic_at']-=10
            return commit(observation,claimed)
        self.d.commit_observed_post=slow
        with self.assertRaises(ReviewRequired):self.publish()
        self.assertEqual(self.row()['phase'],'unknown');self.d.adb.shell.assert_not_called()

    def test_interrupt_after_claim_before_adb_keeps_unknown_on_restart(self):
        self.d.adb.shell.side_effect=KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.publish()
        self.assertEqual(self.row()['phase'],'send_pending')
        self.store.recover();self.assertEqual(self.row()['phase'],'unknown')
        with self.assertRaises(ReviewRequired):self.publish()

    def test_pause_during_claim_never_taps_or_clears_intent(self):
        self.d.stop=threading.Event();claim=self.store.claim_publish
        def pause(*a,**kw):
            result=claim(*a,**kw);self.d.stop.set();return result
        with patch.object(self.store,'claim_publish',side_effect=pause),self.assertRaises(ReviewRequired):self.publish()
        self.assertEqual(self.row()['phase'],'unknown');self.d.adb.shell.assert_not_called()

    def test_processing_write_failure_cannot_repeat_gesture(self):
        transition=self.store.transition
        def failed(row_id,expected,phase,**values):
            if phase=='processing':raise OSError('state disk unavailable')
            return transition(row_id,expected,phase,**values)
        with patch.object(self.store,'transition',side_effect=failed),self.assertRaises(OSError):self.publish()
        self.assertEqual(self.row()['phase'],'unknown');self.assertEqual(self.d.adb.shell.call_count,1)
        self.store.recover()
        with self.assertRaises(ReviewRequired):self.publish()
        self.assertEqual(self.d.adb.shell.call_count,1)

    def test_out_of_screen_post_target_cannot_claim(self):
        next(n for n in self.d.fixture_nodes if n['resource-id']==P+'btn_post')['bounds']='[10,700][410,760]'
        with self.assertRaises(ReviewRequired):self.publish()
        self.assertNotIn('publish_intent',self.row());self.d.adb.shell.assert_not_called()

    def test_wrong_foreground_in_final_guard_is_unsent(self):
        self.mutate_after_evidence(lambda:self.d.ui.info.update(currentPackageName='foreign.app'))
        with patch('core.shopee_posting.device.time.sleep'),patch('core.shopee_posting.device.time.monotonic',side_effect=range(100)),self.assertRaises(ReviewRequired):self.publish()
        self.assertNotIn('publish_intent',self.row());self.d.adb.shell.assert_not_called()
