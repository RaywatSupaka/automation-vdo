import base64
import io
import tempfile
import threading
import unittest
import subprocess
import json
import logging
import os
import urllib.request
from urllib.error import HTTPError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from core.ai_cover import AICovers, ai_cover_options
from core.atomic_json import AtomicJsonFile
from core.creation_queue import clean_settings
from core.drama_options import drama_render_options
from ui.ai_cover import finish_ai_cover, ai_cover_action


class AICoverTests(unittest.TestCase):
    def test_cover_send_recovery_actual_source(self):
        result = subprocess.run(['node', 'tests/cover_send_recovery.js'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_cover_send_diagnostics_are_bounded(self):
        rid = self.claim()
        self.service.event(rid, dict(phase='running', send_state='accepted', send_diagnostics={
            'gesture_phase':'released','release_on_send_target':True,'prompt':'must not store'}))
        row = self.service.get(rid)
        self.assertEqual(row['send_state'], 'accepted')
        self.assertEqual(row['send_diagnostics'], {'gesture_phase':'released','release_on_send_target':True})
        self.assertFalse(self.service.completion(self.job)['ready'])

    def test_cover_send_records_target_motion_without_prompt_or_coordinates(self):
        rid = self.claim()
        self.service.event(rid, dict(phase='running', send_state='unconfirmed', send_diagnostics={
            'gesture_phase':'released', 'dispatch_completed':True, 'trusted_click_seen':False,
            'send_target_strategy':'center', 'target_changed':True,
            'target_geometry_changes_during_gesture':1,
            'target_node_changes_prepress':0,
            'click_events':[{'type':'pointerdown','trusted':True,'on_target':True,
                             'elapsed_ms':18,'phase':'pressed','x':401,'prompt':'private'},
                            {'type':'mouseup','trusted':True,'on_target':False,
                             'elapsed_ms':88,'phase':'released','y':812},
                            {'type':'unknown','prompt':'private'}],
            'prompt':'private','x':401}))
        detail = self.service.get(rid)['send_diagnostics']
        self.assertEqual(detail['send_target_strategy'],'center')
        self.assertTrue(detail['target_changed'])
        self.assertEqual(detail['target_geometry_changes_during_gesture'],1)
        self.assertEqual(detail['click_events'],[
            {'type':'pointerdown','trusted':True,'on_target':True,'elapsed_ms':18,'phase':'pressed'},
            {'type':'mouseup','trusted':True,'on_target':False,'elapsed_ms':88,'phase':'released'}])
        self.assertNotIn('prompt',repr(detail))
        self.assertNotIn("'x'",repr(detail))
        self.assertNotIn("'y'",repr(detail))
        self.assertEqual(self.service.get(rid)['phase'],'running')

    def test_collector_diagnostics_are_bounded_not_completion(self):
        rid=self.claim()
        state=dict(stage='stabilizing',owned=True,candidates=1,loaded=1,
                   stop_visible=True,stalled_ms=60000,url='omit',prompt='omit')
        self.service.event(rid,dict(phase='running',collector_state=state))
        saved=self.service.get(rid)['collector_state']
        self.assertEqual(saved,dict(stage='stabilizing',owned=True,candidates=1,loaded=1,
                                    stop_visible=True,stalled_ms=60000))
        self.assertEqual(self.manifest.read()['ai_cover_state']['collector_state'],saved)
        self.assertFalse(self.service.completion(self.job)['ready'])
        for bad in ({**state,'stage':'unknown'}, {**state,'candidates':True}, {**state,'loaded':11},
                    {**state,'loaded':2}, {**state,'owned':'yes'},
                    {**state,'stop_visible':'yes'}, {**state,'stalled_ms':-1}):
            with self.assertRaises(ValueError):self.service.event(rid,dict(phase='running',collector_state=bad))

    def test_native_stream_retry_claim_survives_collect_only_resume(self):
        self.manifest.update(lambda m:{**m,'image_ai_provider':'chatgpt'})
        rid=self.claim()
        proof=dict(status='verified',expected=1,loaded=1,method='filename',reason='ready')
        self.service.event(rid,dict(phase='running',send_state='accepted',reference_proof=proof))
        self.service.event(rid,dict(phase='needs_review',message='native stream error'))
        self.assertEqual(self.service.event(rid,dict(phase='running',retry_count=1))['retry_count'],0)
        self.service.recover_result(rid,self.job)
        self.service.event(rid,dict(phase='claimed'))
        self.service.event(rid,dict(phase='running',send_state='accepted'))
        claim=dict(version=1,request_id=rid,conversation_url='https://chatgpt.com/c/fixture',
                   user_id='owned-user-id',reason='native_stream_error')
        state=dict(stage='stream_error_retry',owned=True,candidates=0,loaded=0)
        row=self.service.event(rid,dict(phase='running',retry_count=1,
                                         native_retry_claim=claim,collector_state=state))
        self.assertEqual(row['retry_count'],1)
        self.assertEqual(row['native_retry_claim'],claim)
        self.assertEqual(self.manifest.read()['ai_cover_state']['native_retry_claim'],claim)
        self.service.event(rid,dict(phase='needs_review',message='Retry did not finish'))
        self.service.recover_result(rid,self.job)
        packet=self.service.package(rid)
        self.assertEqual(packet['native_retry_claim'],claim)
        self.assertEqual(packet['retry_count'],1)
        self.assertTrue(packet['collect_only'])

    def test_native_stream_retry_claim_rejects_wrong_owner_or_missing_proof(self):
        self.manifest.update(lambda m:{**m,'image_ai_provider':'chatgpt'})
        rid=self.claim()
        self.service.event(rid,dict(phase='running',send_state='accepted'))
        claim=dict(version=1,request_id=rid,conversation_url='https://chatgpt.com/c/fixture',
                   user_id='owned-user-id',reason='native_stream_error')
        state=dict(stage='stream_error_retry',owned=True,candidates=0,loaded=0)
        event=dict(phase='running',retry_count=1,native_retry_claim=claim,collector_state=state)
        with self.assertRaises(ValueError):self.service.event(rid,event)
        proof=dict(status='verified',expected=1,loaded=1,method='filename',reason='ready')
        self.service.event(rid,dict(phase='running',reference_proof=proof))
        for change in ({'request_id':'foreign'},{'user_id':''},{'conversation_url':'https://example.com/c/fixture'},
                       {'reason':'quota'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.service.event(rid,{**event,'native_retry_claim':{**claim,**change}})
        with self.assertRaises(ValueError):
            self.service.event(rid,{**event,'collector_state':{**state,'stage':'answer_missing'}})
        self.assertEqual(self.service.get(rid)['retry_count'],0)

    def test_worker_timeout_reports_last_collector_stage_keeps_video(self):
        rid=self.claim()
        self.service.event(rid,dict(phase='running',active=False,
            collector_state=dict(stage='downloading',owned=True,candidates=1,loaded=1)))
        cancel=SimpleNamespace(is_set=lambda:False,wait=lambda _:None)
        ticks=iter([0,361])
        with patch('ui.ai_cover.time',SimpleNamespace(monotonic=lambda:next(ticks))):
            finish_ai_cover(SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service)),self.job,cancel,lambda _:None)
        row=self.service.get(rid)
        self.assertEqual(row['phase'],'needs_review')
        self.assertIn('พบภาพแล้วแต่ยังบันทึกไฟล์ไม่สำเร็จ',row['message'])
        self.assertEqual(self.manifest.read()['video_status'],'ready')

    def test_worker_timeout_identifies_unconfirmed_send_before_image_reader(self):
        rid=self.claim()
        self.service.event(rid,dict(phase='running',send_state='unconfirmed',active=False,
            send_diagnostics={'dispatch_completed':True,'trusted_click_seen':False,
                              'gesture_phase':'released'}))
        cancel=SimpleNamespace(is_set=lambda:False,wait=lambda _:None)
        ticks=iter([0,361])
        with patch('ui.ai_cover.time',SimpleNamespace(monotonic=lambda:next(ticks))):
            finish_ai_cover(SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service)),
                            self.job,cancel,lambda _:None)
        row=self.service.get(rid)
        self.assertEqual(row['phase'],'needs_review')
        self.assertIn('ยังยืนยันไม่ได้ว่า ChatGPT รับคำสั่งสร้างปก',row['message'])
        self.assertNotIn('ตัวอ่านภาพ',row['message'])
        self.assertEqual(self.manifest.read()['video_status'],'ready')
        self.assertEqual(len(self.service.store.read()),1)

    def test_one_selected_cover_from_two_candidates_saves_once_and_preserves_final(self):
        rid=self.claim()
        state=dict(stage='stabilizing',owned=True,candidates=2,loaded=2)
        proof=dict(request_id=rid,scope='latest_assistant_turn',images=1,width=576,height=1024)
        self.service.event(rid,dict(phase='running',collector_state=state,result_proof=proof))
        self.assertEqual(self.service.get(rid)['collector_state'],state)
        self.assertFalse(self.service.completion(self.job)['ready'])

        row=self.service.event(rid,dict(phase='ready',image=self.image(),result_proof=proof))
        manifest=self.manifest.read()
        self.assertEqual(row['collector_state'],state)
        self.assertEqual(row['result_proof'],proof)
        self.assertEqual(manifest['ai_cover_state']['collector_state'],state)
        self.assertEqual(len(manifest['ai_cover_history']),1)
        self.assertEqual(manifest['ai_cover_history'][0]['request_id'],rid)
        self.assertEqual(manifest['cover_revision'],rid)
        self.assertEqual(list((self.folder/'covers').iterdir()),[self.folder/manifest['cover_path']])
        with Image.open(self.folder/manifest['cover_path']) as image:
            self.assertEqual(image.size,(1080,1920))
        self.assertTrue(self.service.completion(self.job)['ready'])
        self.assertEqual((self.folder/'video.mp4').read_bytes(),b'preserve this final video')
        self.assertEqual(manifest['video_status'],'ready')

    def downloading_cover(self, rid=None):
        rid=rid or self.claim()
        proof=dict(request_id=rid,scope='latest_assistant_turn',images=1,width=576,height=1024)
        self.service.event(rid,dict(phase='running',result_proof=proof,
            collector_state=dict(stage='downloading',owned=True,candidates=2,loaded=2)))
        return rid

    def failed_cover_download(self, rid):
        return self.service.event(rid,dict(phase='needs_review',message='download failed',
            download_failure=dict(attempts=3,owned=True,idle=True)))

    def test_confirmed_cover_download_failure_creates_clean_frozen_successor(self):
        rid=self.downloading_cover()
        original=self.service.get(rid)
        self.service.store.update(lambda rows:{**rows,rid:{**rows[rid],
            'collect_only':True,'retry_count':1,'send_state':'accepted',
            'send_diagnostics':{'gesture_phase':'released'},
            'preparation_state':{'stage':'image_tool','not_dispatched':False},
            'reference_proof':{'status':'verified'},'prompt':'original saved prompt'}})
        self.manifest.update(lambda m:{**m,'video_title':'later edited title','image_ai_provider':'chatgpt'})
        parent=self.failed_cover_download(rid)
        child=self.service.get(parent['successor_request_id'])
        self.assertEqual(parent['phase'],'needs_review')
        self.assertEqual(parent['result_proof'],original['result_proof'])
        self.assertEqual(parent['retry_count'],1)
        self.assertEqual(child['parent_request_id'],rid)
        self.assertEqual(child['phase'],'queued')
        self.assertEqual(child['download_replacement_count'],1)
        self.assertEqual(child['retry_count'],0)
        self.assertTrue(child['single_image_only'])
        for key in ('source','sources','title','provider','ai_web_model','scene_index',
                    'headline','aspect_ratio','previous_cover_revision'):
            self.assertEqual(child[key],original[key])
        self.assertEqual(child['prompt'],'original saved prompt')
        for key in ('collect_only','send_state','send_diagnostics','collector_state','result_proof',
                    'preparation_state','reference_proof','download_failure','successor_request_id'):
            self.assertNotIn(key,child)
        self.assertEqual(self.service.pending(),[child])
        self.assertEqual(self.manifest.read()['ai_cover_state']['request_id'],child['request_id'])
        self.assertEqual(self.manifest.read()['ai_cover_state']['phase'],'queued')
        self.assertTrue(self.service.completion(self.job)['waiting'])
        self.assertFalse(self.service.completion(self.job)['ready'])
        self.assertTrue(self.service.package(child['request_id'])['single_image_only'])
        self.assertIn('source_images',self.service.package(child['request_id']))
        self.assertEqual((self.folder/'video.mp4').read_bytes(),b'preserve this final video')
        self.assertEqual(self.manifest.read()['video_status'],'ready')
        self.assertEqual(self.manifest.read()['cover_revision'],'old')

    def test_download_successor_duplicate_failure_and_late_parent_result_are_idempotent(self):
        rid=self.downloading_cover()
        parent=self.failed_cover_download(rid)
        child_id=parent['successor_request_id']
        before=self.service.store.read()
        self.assertEqual(self.failed_cover_download(rid)['successor_request_id'],child_id)
        self.assertEqual(self.service.event(rid,dict(phase='ready',image=self.image()))['phase'],'needs_review')
        self.assertEqual(self.service.store.read(),before)
        self.assertEqual(len(before),2)
        self.assertFalse((self.folder/'covers').exists())
        self.assertEqual(self.manifest.read()['ai_cover_state']['request_id'],child_id)

    def test_download_failure_racing_callbacks_commit_only_one_successor(self):
        from concurrent.futures import ThreadPoolExecutor
        rid=self.downloading_cover()
        with ThreadPoolExecutor(max_workers=2) as workers:
            parents=list(workers.map(lambda _:self.failed_cover_download(rid),range(2)))
        self.assertEqual(parents[0]['successor_request_id'],parents[1]['successor_request_id'])
        self.assertEqual(len(self.service.store.read()),2)

    def test_download_successor_requires_typed_failure_and_previous_saved_download_proof(self):
        rid=self.claim()
        self.service.event(rid,dict(phase='running',send_state='unconfirmed'))
        proof=dict(request_id=rid,scope='latest_assistant_turn',images=1,width=576,height=1024)
        state=dict(stage='downloading',owned=True,candidates=2,loaded=2)
        failure=dict(attempts=3,owned=True,idle=True)
        before=self.service.store.read()
        with self.assertRaises(ValueError):
            self.service.event(rid,dict(phase='needs_review',download_failure=failure,
                result_proof=proof,collector_state=state))
        self.assertEqual(self.service.store.read(),before)
        self.downloading_cover(rid)
        before=self.service.store.read()
        for change in ({'attempts':True},{'attempts':2},{'owned':False},{'idle':False},
                       {'owned':1},{'idle':1},{'url':'must not store'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.service.event(rid,dict(phase='needs_review',download_failure={**failure,**change}))
            self.assertEqual(self.service.store.read(),before)
        with self.assertRaises(ValueError):
            self.service.event(rid,dict(phase='running',download_failure=failure))
        self.assertEqual(self.service.store.read(),before)

    def test_download_successor_rejects_non_download_collector_and_manual_cover_change(self):
        rid=self.downloading_cover()
        for state in (dict(stage='stabilizing',owned=True,candidates=2,loaded=2),
                      dict(stage='downloading',owned=False,candidates=2,loaded=2),
                      dict(stage='downloading',owned=True,candidates=2,loaded=0)):
            self.service.event(rid,dict(phase='running',collector_state=state))
            before=self.service.store.read()
            with self.assertRaises(ValueError):self.failed_cover_download(rid)
            self.assertEqual(self.service.store.read(),before)
        self.downloading_cover(rid)
        self.manifest.update(lambda m:{**m,'cover_revision':'manual','cover_path':'manual.jpg'})
        before=self.service.store.read()
        with self.assertRaises(ValueError):self.failed_cover_download(rid)
        self.assertEqual(self.service.store.read(),before)
        self.assertEqual(self.manifest.read()['cover_path'],'manual.jpg')

    def test_download_successor_rejects_queued_or_superseded_request(self):
        row=self.service.request(self.job)
        before=self.service.store.read()
        with self.assertRaises(ValueError):self.failed_cover_download(row['request_id'])
        self.assertEqual(self.service.store.read(),before)
        self.service.event(row['request_id'],dict(phase='claimed'))
        self.downloading_cover(row['request_id'])
        newer={**row,'request_id':'newer','created_at':row['created_at']+1}
        self.service.store.update(lambda rows:{**rows,'newer':newer})
        before=self.service.store.read()
        with self.assertRaises(ValueError):self.failed_cover_download(row['request_id'])
        self.assertEqual(self.service.store.read(),before)

    def test_download_failure_cannot_reopen_cancelled_or_saved_cover(self):
        rid=self.downloading_cover()
        self.service.event(rid,dict(phase='cancelled'))
        self.assertEqual(self.failed_cover_download(rid)['phase'],'cancelled')
        self.assertEqual(len(self.service.store.read()),1)
        child=self.service.request(self.job,force=True)
        self.service.event(child['request_id'],dict(phase='claimed'))
        self.downloading_cover(child['request_id'])
        self.service.event(child['request_id'],dict(phase='ready',image=self.image()))
        self.assertEqual(self.failed_cover_download(child['request_id'])['phase'],'ready')
        self.assertEqual(len(self.service.store.read()),2)
        self.assertEqual(len(self.manifest.read()['ai_cover_history']),1)

    def test_each_download_replacement_needs_its_own_confirmed_failure(self):
        rid=self.downloading_cover()
        parent=self.failed_cover_download(rid)
        child_id=parent['successor_request_id']
        self.service.event(child_id,dict(phase='claimed'))
        with self.assertRaises(ValueError):self.failed_cover_download(child_id)
        self.downloading_cover(child_id)
        child=self.failed_cover_download(child_id)
        next_child=self.service.get(child['successor_request_id'])
        self.assertEqual(next_child['download_replacement_count'],2)
        self.assertEqual(next_child['parent_request_id'],child_id)
        self.assertEqual(len(self.service.store.read()),3)

    def test_cover_worker_follows_download_successor_and_resets_wait_deadline(self):
        rid=self.downloading_cover()
        parent=self.failed_cover_download(rid)
        child_id=parent['successor_request_id']
        def complete_child(_):
            self.service.event(child_id,dict(phase='claimed'))
            self.service.event(child_id,dict(phase='ready',image=self.image()))
        cancel=SimpleNamespace(is_set=lambda:False,wait=complete_child)
        ticks=iter([0,1000,1001])
        progress=[]
        with patch.object(self.service,'request',return_value=parent), \
                patch('ui.ai_cover.time',SimpleNamespace(monotonic=lambda:next(ticks))):
            finish_ai_cover(SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service)),
                self.job,cancel,progress.append)
        self.assertEqual(self.service.get(child_id)['phase'],'ready')
        self.assertEqual(progress[-1],'ปก AI เสร็จแล้ว')
        self.assertFalse(any('ยังไม่สำเร็จ' in message for message in progress))
        self.assertEqual(self.manifest.read()['ai_cover_history'][0]['request_id'],child_id)
        self.assertEqual((self.folder/'video.mp4').read_bytes(),b'preserve this final video')

    def test_cover_worker_cancellation_targets_download_successor(self):
        rid=self.downloading_cover()
        parent=self.failed_cover_download(rid)
        child_id=parent['successor_request_id']
        cancel=threading.Event();cancel.set()
        with patch.object(self.service,'request',return_value=parent):
            finish_ai_cover(SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service)),
                self.job,cancel,lambda _:None)
        self.assertEqual(self.service.get(rid)['phase'],'needs_review')
        self.assertEqual(self.service.get(child_id)['phase'],'cancelled')
        self.assertEqual(self.service.active(),[])
        self.assertEqual((self.folder/'video.mp4').read_bytes(),b'preserve this final video')

    def test_cover_worker_cancel_racing_download_ack_cancels_new_child(self):
        rid=self.downloading_cover()
        def cancellation_arrives():
            self.failed_cover_download(rid)
            return True
        cancel=SimpleNamespace(is_set=cancellation_arrives)
        finish_ai_cover(SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service)),
            self.job,cancel,lambda _:None)
        parent=self.service.get(rid)
        self.assertEqual(parent['phase'],'needs_review')
        self.assertEqual(self.service.get(parent['successor_request_id'])['phase'],'cancelled')
        self.assertEqual(self.service.active(),[])

    def test_cover_status_and_cancel_follow_exact_download_successor(self):
        rid=self.downloading_cover()
        parent=self.failed_cover_download(rid)
        child_id=parent['successor_request_id']
        app=SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service))
        for _ in range(2):
            state=ai_cover_action(app,'ai_cover_status',{'request_id':rid})['request']
            self.assertEqual(state['request_id'],child_id)
            self.assertEqual(state['phase'],'queued')
        self.assertEqual(self.service.get(rid)['phase'],'needs_review')
        result=ai_cover_action(app,'ai_cover_cancel',{'request_id':rid})['request']
        self.assertEqual(result['request_id'],child_id)
        self.assertEqual(result['phase'],'cancelled')
        self.assertEqual(self.service.get(rid),parent)

    def test_cover_status_and_cancel_reject_wrong_job_parent_and_cycles(self):
        rid=self.downloading_cover()
        parent=self.failed_cover_download(rid)
        child_id=parent['successor_request_id']
        saved=self.service.store.read()
        app=SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service))
        bad_rows=[{**saved,child_id:{**saved[child_id],'job_id':'STORY-OTHER'}},
                  {**saved,child_id:{**saved[child_id],'parent_request_id':'unrelated'}},
                  {**saved,rid:{**saved[rid],'parent_request_id':child_id},
                   child_id:{**saved[child_id],'successor_request_id':rid}}]
        for rows in bad_rows:
            self.service.store.write(rows)
            for action in ('ai_cover_status','ai_cover_cancel'):
                with self.subTest(action=action),self.assertRaises(ValueError):
                    ai_cover_action(app,action,{'request_id':rid})
                self.assertEqual(self.service.store.read(),rows)

    def test_legacy_cover_request_prompt_is_not_removed(self):
        row=self.service.request(self.job)
        self.service.store.update(lambda records:{**records,row['request_id']:{**row,'prompt':'saved legacy prompt'}})
        self.assertEqual(self.service.request(self.job)['prompt'],'saved legacy prompt')
        self.assertEqual(self.service.package(row['request_id'])['prompt'],'saved legacy prompt')

    def test_background_cover_claim_does_not_redeliver(self):
        from core.cancellable_process import hidden_process_kwargs
        result=subprocess.run(['node',str(Path(__file__).with_name('ai_cover_background_harness.js'))],capture_output=True,text=True,timeout=20,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout),{'ok':True,'cases':5})

    def test_restart_preserves_unknown_and_deleted_job_does_not_block(self):
        request = self.service.request(self.job)
        self.assertEqual(self.manifest.read()['ai_cover_state']['phase'], 'queued')
        self.service.recover_startup()
        self.assertEqual(self.service.get(request['request_id'])['phase'], 'queued')
        self.assertEqual([r['request_id'] for r in self.service.pending()],
                         [request['request_id']])
        self.service.event(request['request_id'], {'phase':'claimed'})
        self.service.recover_startup()
        self.assertEqual(self.service.get(request['request_id'])['phase'], 'needs_review')
        next_request = self.service.request(self.job, force=True)
        (self.folder / 'job.json').unlink()
        self.service.recover_startup()
        self.assertEqual(self.service.get(next_request['request_id'])['phase'], 'needs_review')
        self.assertEqual(self.service.active(), [])

    def test_extension_collector_and_retry(self):
        from core.cancellable_process import hidden_process_kwargs
        result=subprocess.run(['node',str(Path(__file__).with_name('ai_cover_harness.js'))],capture_output=True,text=True,timeout=20,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout),{'ok':True,'cases':11})

    def test_cover_result_observed_dom(self):
        from core.cancellable_process import hidden_process_kwargs
        env=dict(os.environ)
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result=subprocess.run(['node',str(Path(__file__).with_name('ai_cover_result_dom_harness.js'))],
            capture_output=True,text=True,encoding='utf-8',env=env,timeout=30,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_existing_cover_recovery_ui(self):
        from core.cancellable_process import hidden_process_kwargs
        env=dict(os.environ)
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result=subprocess.run(['node',str(Path(__file__).with_name('ai_cover_recovery_ui_harness.js'))],
            capture_output=True,text=True,encoding='utf-8',env=env,timeout=30,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_collect_only_recovery_same_request_no_sources_reupload_and_final_preserved(self):
        rid=self.claim();self.service.event(rid,dict(phase='needs_review',message='old false no-image',retry_count=1))
        self.service.recover_result(rid,self.job)
        self.assertEqual(self.service.pending()[0]['request_id'],rid)
        packet=self.service.package(rid)
        self.assertTrue(packet['collect_only']);self.assertNotIn('source_data',packet);self.assertNotIn('source_images',packet)
        self.assertEqual(packet['retry_count'],1)
        self.assertEqual(packet['collection_history'][-1]['previous_message'],'old false no-image')
        self.service.event(rid,dict(phase='claimed'))
        with self.assertRaises(ValueError):self.service.event(rid,dict(phase='ready',image=self.image()))
        proof=dict(request_id=rid,scope='latest_assistant_turn',images=1,width=576,height=1024,secret='omit')
        self.service.event(rid,dict(phase='running',result_proof=proof))
        self.assertFalse(self.service.completion(self.job)['ready'])
        self.service.event(rid,dict(phase='ready',image=self.image(),result_proof=proof))
        self.assertTrue(self.service.completion(self.job)['ready'])
        self.assertNotIn('secret',self.service.get(rid)['result_proof'])
        self.assertEqual((self.folder/'video.mp4').read_bytes(),b'preserve this final video')
        self.assertEqual(len(self.manifest.read()['ai_cover_history']),1)

    def test_owner_supplied_existing_cover_finishes_exact_request_without_provider_replay(self):
        rid = self.claim()
        self.service.event(rid, dict(phase='running', send_state='accepted',
            send_diagnostics={'gesture_phase': 'released', 'trusted_click_seen': True}))
        self.service.event(rid, dict(phase='needs_review', message='image visible but collector lost identity'))
        supplied = self.root / 'downloaded-cover.png'
        Image.new('RGB', (576, 1024), 'red').save(supplied)
        row = self.service.adopt_user_supplied_result(rid, self.job, supplied)
        manifest = self.manifest.read()
        self.assertEqual((row['phase'], row['completion_source']), ('ready', 'user_supplied'))
        self.assertNotIn('result_proof', row)
        self.assertTrue(self.service.completion(self.job)['ready'])
        self.assertEqual(manifest['cover_revision'], rid)
        self.assertEqual(manifest['cover_renderer'], 'user-supplied-ai-cover-v1')
        self.assertEqual(manifest['ai_cover_history'][-1]['source'], 'user_supplied')
        self.assertTrue((self.folder / manifest['cover_path']).is_file())
        self.assertEqual((self.folder / 'video.mp4').read_bytes(), b'preserve this final video')
        self.assertTrue(supplied.is_file())
        with self.assertRaises(ValueError):
            self.service.adopt_user_supplied_result(rid, self.job, supplied)

    def test_owner_supplied_cover_repairs_manifest_saved_before_ledger_ack(self):
        rid = self.claim()
        self.service.event(rid, dict(phase='running', send_state='accepted'))
        self.service.event(rid, dict(phase='needs_review'))
        supplied = self.root / 'downloaded-cover.png'
        Image.new('RGB', (576, 1024), 'red').save(supplied)
        self.service.adopt_user_supplied_result(rid, self.job, supplied)
        saved = self.folder / self.manifest.read()['cover_path']
        before = saved.read_bytes()
        self.service.store.update(lambda records: {**records,
            rid: {**records[rid], 'phase': 'needs_review', 'completion_source': ''}})
        self.assertFalse(self.service.completion(self.job)['ready'])
        self.service.adopt_user_supplied_result(rid, self.job, supplied)
        self.assertEqual(saved.read_bytes(), before)
        self.assertTrue(self.service.completion(self.job)['ready'])
        self.assertEqual(len(self.manifest.read()['ai_cover_history']), 1)

    def test_owner_supplied_cover_rejects_unaccepted_wrong_or_changed_request(self):
        supplied = self.root / 'downloaded-cover.png'
        Image.new('RGB', (576, 1024), 'red').save(supplied)
        rid = self.claim()
        self.service.event(rid, dict(phase='needs_review'))
        with self.assertRaises(ValueError):
            self.service.adopt_user_supplied_result(rid, self.job, supplied)
        self.assertFalse(self.service.completion(self.job)['ready'])
        newer = self.service.request(self.job, force=True)
        self.service.event(newer['request_id'], dict(phase='claimed'))
        self.service.event(newer['request_id'], dict(phase='running', send_state='accepted'))
        self.service.event(newer['request_id'], dict(phase='needs_review'))
        with self.assertRaises(ValueError):
            self.service.adopt_user_supplied_result(rid, self.job, supplied)
        with self.assertRaises(ValueError):
            self.service.adopt_user_supplied_result(newer['request_id'], 'STORY-OTHER', supplied)
        wide = self.root / 'wide-cover.png'
        Image.new('RGB', (1024, 576), 'red').save(wide)
        with self.assertRaises(ValueError):
            self.service.adopt_user_supplied_result(newer['request_id'], self.job, wide)
        Image.new('RGB', (576, 1024), 'green').save(self.folder / 'old.jpg')
        with self.assertRaises(ValueError):
            self.service.adopt_user_supplied_result(newer['request_id'], self.job, supplied)
        self.assertFalse(self.service.completion(self.job)['ready'])

    def test_collect_only_rejects_wrong_cancelled_newer_and_active_request(self):
        rid=self.claim()
        with self.assertRaises(ValueError):self.service.recover_result(rid,self.job)
        self.service.event(rid,dict(phase='needs_review'))
        with self.assertRaises(ValueError):self.service.recover_result(rid,'JOB-OTHER')
        new=self.service.request(self.job,force=True)
        with self.assertRaises(ValueError):self.service.recover_result(rid,self.job)
        self.service.event(new['request_id'],dict(phase='cancelled'))
        with self.assertRaises(ValueError):self.service.recover_result(new['request_id'],self.job)

    def test_result_proof_rejects_wrong_request_and_bad_dimensions(self):
        rid=self.claim();proof=dict(request_id=rid,scope='latest_assistant_turn',images=1,width=941,height=1672)
        for change in ({'request_id':'wrong'},{'images':True},{'images':2},{'scope':'whole_page'},{'width':1},{'height':'1672'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.service.event(rid,dict(phase='running',result_proof={**proof,**change}))
        self.assertNotIn('result_proof',self.service.get(rid))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.products=SimpleNamespace(root=self.root/'products')
        self.stories=SimpleNamespace(root=self.root/'stories')
        self.service=AICovers(self.products,self.stories)
        self.job='STORY-TEST-123'
        self.folder=self.stories.root/self.job
        self.folder.mkdir(parents=True)
        Image.new('RGB',(576,1024),'blue').save(self.folder/'scene.jpg')
        (self.folder/'video.mp4').write_bytes(b'preserve this final video')
        self.manifest=AtomicJsonFile(self.folder/'job.json')
        self.manifest.write(dict(id=self.job,job_type='story_short',video_path='video.mp4',video_status='ready',
            video_title='กระต่ายกับไก่',generated_images=['scene.jpg'],image_ai_provider='gemini',
            cover={'headline':'เพื่อนที่ไม่ทิ้งกัน','scene_index':1},cover_revision='old',cover_path='old.jpg',
            ai_cover_options={'enabled':True}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_saved_sources_packaged_without_duplicate(self):
        Image.new('RGB',(576,1024),'green').save(self.folder/'second.jpg')
        self.manifest.update(lambda m:{**m,'generated_images':['scene.jpg','second.jpg']})
        row=self.service.request(self.job)
        self.assertEqual(len(row['sources']),2)
        packet=self.service.package(row['request_id'])
        self.assertEqual(len(packet['source_images']),2)
        self.assertNotEqual(*packet['source_images'])
        self.assertEqual(packet['source_data'],packet['source_images'][0])
        from core.cancellable_process import hidden_process_kwargs
        packet_path=self.root/'packet.json'
        packet_path.write_text(json.dumps(packet),encoding='utf-8')
        result=subprocess.run(['node',str(Path(__file__).with_name('ai_cover_dispatch_harness.js')),str(packet_path)],capture_output=True,text=True,timeout=20,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        result=subprocess.run(['node',str(Path(__file__).with_name('ai_cover_source_files_harness.js')),str(packet_path)],capture_output=True,text=True,timeout=20,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_cover_attachment_from_desktop_packet(self):
        Image.new('RGB',(576,1024),'green').save(self.folder/'second.jpg')
        self.manifest.update(lambda m:{**m,'generated_images':['scene.jpg','second.jpg']})
        packet=self.service.package(self.service.request(self.job)['request_id'])
        packet_path=self.root/'packet.json'
        packet_path.write_text(json.dumps(packet),encoding='utf-8')
        env=dict(os.environ)
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        from core.cancellable_process import hidden_process_kwargs
        result=subprocess.run(['node',str(Path(__file__).with_name('ai_cover_attachment_harness.js')),str(packet_path)],
                              capture_output=True,text=True,encoding='utf-8',env=env,timeout=60,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout),{'ok':True,'cases':37})

    def test_attachment_wait_diagnostics_are_bounded_and_not_completion(self):
        rid=self.claim()
        proof=dict(status='review',expected=1,loaded=0,method='filename',reason='upload_busy',
                   observed=1,elapsed_ms=35000,url='must not retain')
        row=self.service.event(rid,dict(phase='running',reference_proof=proof))
        self.assertEqual(row['reference_proof'],{k:v for k,v in proof.items() if k!='url'})
        self.assertEqual(self.manifest.read()['ai_cover_state']['reference_proof'],row['reference_proof'])
        self.assertFalse(self.service.completion(self.job)['ready'])
        for change in ({'observed':True},{'observed':11},{'elapsed_ms':-1},{'elapsed_ms':120001}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.service.event(rid,dict(phase='running',reference_proof={**proof,**change}))
        self.assertEqual(self.service.get(rid)['reference_proof'],row['reference_proof'])

    def test_attachment_evidence_is_saved_but_not_cover_completion(self):
        rid=self.claim()
        proof=dict(status='verified',expected=1,loaded=1,method='input_files',reason='ready',secret='not retained')
        row=self.service.event(rid,dict(phase='running',reference_proof=proof))
        self.assertEqual(row['reference_proof'],{k:v for k,v in proof.items() if k!='secret'})
        self.assertEqual(self.manifest.read()['ai_cover_state']['reference_proof'],row['reference_proof'])
        self.assertFalse(self.service.completion(self.job)['ready'])
        self.service.event(rid,dict(phase='ready',image=self.image()))
        self.assertTrue(self.service.completion(self.job)['ready'])
        self.assertEqual(self.service.get(rid)['reference_proof'],row['reference_proof'])

    def test_invalid_attachment_evidence_preserves_request(self):
        rid=self.claim()
        proof=dict(status='verified',expected=1,loaded=1,method='filename',reason='ready')
        for change in ({'expected':2},{'expected':True},{'loaded':True},{'loaded':0},
                       {'loaded':11},{'method':'none'},{'reason':'arbitrary browser data'},{'status':'unknown'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.service.event(rid,dict(phase='running',reference_proof={**proof,**change}))
        self.assertNotIn('reference_proof',self.service.get(rid))
        self.assertEqual(self.service.get(rid)['phase'],'claimed')

    def image(self,size=(576,1024)):
        out=io.BytesIO();Image.new('RGB',size,'red').save(out,'PNG')
        return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()

    def claim(self):
        row=self.service.request(self.job)
        self.service.event(row['request_id'],{'phase':'claimed'})
        return row['request_id']

    def test_provider_reference_prompt_and_legacy_disabled(self):
        row=self.service.request(self.job)
        self.assertEqual(row['provider'],'gemini')
        self.assertNotIn('prompt',row)  # Extension310 is the sole new-prompt builder.
        self.assertEqual(row['title'],'กระต่ายกับไก่')
        self.assertEqual(row['headline'],'')  # Empty AI text uses title, not local cover fallback.
        self.assertEqual(row['cover_prompt_version'],2)
        self.assertEqual(row['aspect_ratio'],'9:16')
        self.assertEqual(row['source'],'scene.jpg')
        self.assertTrue(self.service.package(row['request_id'])['source_images'][0].startswith('data:image/jpeg;base64,'))
        self.assertEqual(len(self.service.package(row['request_id'])['source_images']),1)
        self.manifest.update(lambda m:{k:v for k,v in m.items() if k!='ai_cover_options'})
        self.assertIsNone(self.service.request(self.job))

    def test_one_request_duplicate_claim_and_restart(self):
        first=self.service.request(self.job)
        self.assertEqual(self.service.request(self.job)['request_id'],first['request_id'])
        self.service.event(first['request_id'],{'phase':'claimed'})
        with self.assertRaises(ValueError):self.service.event(first['request_id'],{'phase':'claimed'})
        restarted=AICovers(self.products,self.stories)
        self.assertEqual(restarted.pending(),[])
        self.assertEqual(restarted.request(self.job,force=True)['request_id'],first['request_id'])

    def test_ready_image_and_duplicate_result_preserve_video(self):
        rid=self.claim()
        self.service.event(rid,{'phase':'ready','image':self.image()})
        self.service.event(rid,{'phase':'ready','image':self.image()})
        result=self.manifest.read()
        self.assertEqual((self.folder/'video.mp4').read_bytes(),b'preserve this final video')
        self.assertEqual(result['video_status'],'ready')
        self.assertEqual(len(result['ai_cover_history']),1)
        self.assertEqual(result['cover_revision'],rid)
        with Image.open(self.folder/result['cover_path']) as image:self.assertEqual(image.size,(1080,1920))

    def test_manual_cover_change_wins(self):
        rid=self.claim();self.manifest.update(lambda m:{**m,'cover_revision':'manual','cover_path':'manual.jpg'})
        self.service.event(rid,{'phase':'ready','image':self.image()})
        result=self.manifest.read();self.assertEqual(result['cover_path'],'manual.jpg')
        self.assertEqual(len(result['ai_cover_history']),1)

    def test_cancelled_cannot_accept_late_image(self):
        rid=self.claim();self.service.event(rid,{'phase':'cancelled'})
        self.assertEqual(self.service.event(rid,{'phase':'ready','image':self.image()})['phase'],'cancelled')
        self.assertEqual(self.manifest.read()['cover_revision'],'old')

    def test_wrong_ratio_or_invalid_data_preserve_old_cover(self):
        rid=self.claim()
        for data in [self.image((1024,576)),'bad','data:image/png;base64,invalid!']:
            with self.subTest(data=data[:30]),self.assertRaises((ValueError,OSError)):
                self.service.event(rid,{'phase':'ready','image':data})
        self.assertEqual(self.manifest.read()['cover_revision'],'old')

    def test_missing_video_and_outside_source_rejected(self):
        self.manifest.update(lambda m:{**m,'video_path':'../outside.mp4'})
        with self.assertRaises(ValueError):self.service.request(self.job)
        with self.assertRaises(ValueError):self.service.folder('../STORY-TEST')

    def test_settings_queue_and_series_snapshots(self):
        option=dict(enabled=True,headline='อย่าทิ้งเพื่อน',scene_index=1)
        self.assertEqual(clean_settings({'ai_cover_options':option})['ai_cover_options'],option)
        self.assertEqual(drama_render_options({'ai_cover_options':option})['ai_cover_options'],option)
        self.assertFalse(ai_cover_options()['enabled'])
        for value in [{'headline':'x'*41},{'scene_index':True},{'scene_index':-1}]:
            with self.assertRaises(ValueError):ai_cover_options(value)

    def test_cover_failure_is_not_video_failure_and_retry_bounded(self):
        rid=self.claim()
        with self.assertRaises(ValueError):self.service.event(rid,{'phase':'running','retry_count':2})
        self.service.event(rid,{'phase':'needs_review','message':'test error'})
        events=[]
        finish_ai_cover(SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service)),self.job,threading.Event(),events.append)
        self.assertIn('ยังไม่สำเร็จ',events[-1]);self.assertEqual(self.manifest.read()['video_status'],'ready')

    def test_explicit_regenerate_keeps_history_and_generates_new_id(self):
        rid=self.claim();self.service.event(rid,{'phase':'ready','image':self.image()})
        new=self.service.request(self.job,force=True)
        self.assertNotEqual(rid,new['request_id'])
        self.assertTrue((self.folder/f'covers/ai_cover_{rid}.jpg').exists())

    def test_worker_cancel_keeps_final(self):
        event=threading.Event();event.set()
        finish_ai_cover(SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service)),self.job,event,lambda _:None)
        self.assertEqual(self.service.active(),[])
        self.assertEqual(self.manifest.read()['video_status'],'ready')

    def test_worker_request_error_does_not_escape(self):
        with patch.object(self.service,'request',side_effect=ValueError('no source')):
            events=[]
            finish_ai_cover(SimpleNamespace(bridge=SimpleNamespace(ai_covers=self.service)),self.job,threading.Event(),events.append)
            self.assertIn('วิดีโอเสร็จแล้ว',events[0])

    def test_provider_portrait_is_padded_to_shorts_not_cropped(self):
        rid=self.claim();self.service.event(rid,{'phase':'ready','image':self.image((512,768))})
        with Image.open(self.folder/self.manifest.read()['cover_path']) as image:
            self.assertEqual(image.size,(1080,1920))

    def test_bridge_auth_version_and_claim_result_roundtrip(self):
        from core.local_bridge import LocalBridge
        bridge=LocalBridge('127.0.0.1',0,self.products,logging.getLogger('test'),stories=self.stories)
        bridge.start();rid=self.service.request(self.job)['request_id']
        base=f'http://127.0.0.1:{bridge.server.server_port}'
        from tests.extension_identity_fixture import pair_fixture
        origin={'Origin':pair_fixture(bridge)}
        def request(path,body=None,headers=None):
            req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers or {})
            with urllib.request.urlopen(req) as response:return json.load(response)
        try:
            with self.assertRaises(HTTPError) as caught:request('/api/ai-covers/pending',headers=origin)
            self.assertEqual(caught.exception.code,403)
            headers={**origin,'X-SmartFlow-Token':bridge._extension_token,'Content-Type':'application/json'}
            self.assertEqual(request('/api/ai-covers/pending',headers=headers)['requests'][0]['request_id'],rid)
            event={'request_id':rid,'phase':'claimed','version':'wrong'}
            with self.assertRaises(HTTPError):request('/api/ai-covers/event',event,headers)
            event['version']=bridge.REQUIRED_EXTENSION_VERSION
            self.assertEqual(request('/api/ai-covers/event',event,headers)['request']['phase'],'claimed')
            self.assertEqual(request('/api/ai-covers/status/'+rid,headers=headers)['request']['phase'],'claimed')
            request('/api/ai-covers/event',{**event,'phase':'ready','image':self.image()},headers)
            self.assertEqual(self.service.get(rid)['phase'],'ready')
        finally:bridge.stop()


if __name__=='__main__':unittest.main()
