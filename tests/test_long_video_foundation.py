import tempfile
import unittest
import wave
from pathlib import Path
from core.long_video import long_video_settings
from core.subtitle_chunks import prepare_subtitle_chunks, merge_subtitle_segments
from core.subtitle_chunks import transcribe_chunks


class LongVideoFoundationTests(unittest.TestCase):
    def test_image_audit_accepts_late_scenes_and_retries_for_owned_long_job(self):
        from core.local_bridge import LocalBridge
        from core.story_manager import StoryManager
        import logging
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            long_job = manager.create('คลิปยาว', long_video={'version': 2, 'scene_count': 50})
            short_job = manager.create('คลิปสั้น', scene_count=10)
            bridge = LocalBridge('127.0.0.1', 0, object(), logging.getLogger('long-video-audit-test'), stories=manager)
            detail = dict(schema_version=1, scene_index=50, attempt=4,
                          prompt='สร้างภาพฉาก 50', composer_text='สร้างภาพฉาก 50',
                          source_count=0, source_attachment_count=0, input_kind='text_to_image',
                          attachment_scope='composer', entry_mode='not_exposed',
                          source_attachment_busy=False, source_attachment_failed=False,
                          image_expansion_open=False, send_button_enabled=True,
                          visible_mode_labels=[])
            bridge._record_extension_trace(dict(job_id=long_job['id'], action='image_prompt_ready', detail=detail))
            self.assertEqual(bridge._safe_story_image_request({'image_request': detail}, scene_count=50)['attempt'], 4)
            detail['scene_index'] = 51
            with self.assertRaises(ValueError):
                bridge._record_extension_trace(dict(job_id=long_job['id'], action='image_prompt_ready', detail=detail))
            detail['scene_index'] = 11
            with self.assertRaises(ValueError):
                bridge._record_extension_trace(dict(job_id=short_job['id'], action='image_prompt_ready', detail=detail))

    def test_pending_long_plan_preserves_exact_request_and_chapter_owner(self):
        from core.ai_web_resume import ai_web_resume_target
        from core.story_manager import StoryManager
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create('เรื่องยาว', long_video={'version': 2, 'scene_count': 18})
            job_id = job['id']
            request = f'ขอโครงเรื่องเดียว job_id={job_id}\nตอบเพียงคำตอบเดียว'
            pending = dict(stage='outline', chapter_index=0, provider='chatgpt', request=request)
            saved = manager.save_long_video_plan_step(job_id, pending_request=pending)
            self.assertEqual(saved['pending_request']['request'], request)
            repair_request = f'จัดรูปแบบคำตอบใหม่ กำหนด job_id เป็น {job_id} ตอบ JSON เดียว'
            saved = manager.save_long_video_plan_step(job_id, pending_request=dict(pending, request=repair_request))
            self.assertEqual(saved['pending_request']['request'], repair_request)
            manager.save_long_video_plan_step(job_id, pending_request=pending)
            resume = ai_web_resume_target(manager.root / job_id, manager.get(job_id))
            self.assertEqual((resume['request'], resume['evidence'], resume['long_video_stage']),
                             (request, 'long_video_plan', 'outline'))
            package = manager.plugin_request(job_id)
            self.assertEqual(package['ai_resume']['request'], request)
            outline = dict(job_id=job_id, video_title='เรื่องยาว', visual_bible='เมืองเก่า',
                           story_entities=[], chapter_beats=['เริ่มต้น', 'บทสรุป'])
            manager.save_long_video_plan_step(job_id, outline=outline, clear_pending=True)
            self.assertNotIn('pending_request', manager.long_video_plan(job_id))
            chapter_request = f'บทฉาก 1–10 job_id={job_id} chapter_index=1'
            chapter_pending = dict(stage='chapter', chapter_index=1, provider='chatgpt', request=chapter_request)
            manager.save_long_video_plan_step(job_id, pending_request=chapter_pending)
            resume = ai_web_resume_target(manager.root / job_id, manager.get(job_id))
            self.assertEqual((resume['request'], resume['chapter_index']), (chapter_request, 1))
            with self.assertRaises(ValueError):
                manager.save_long_video_plan_step(job_id, pending_request=dict(chapter_pending, chapter_index=2))
            with self.assertRaises(ValueError):
                manager.save_long_video_plan_step(job_id, pending_request=dict(chapter_pending,
                    request='จัดรูปแบบคำตอบของ STORY-OTHER เท่านั้น'))

    def test_edit_long_queue_keeps_18_to_50_scene_contract(self):
        from core.creation_queue import CreationQueue
        with tempfile.TemporaryDirectory() as temp:
            queue = CreationQueue(temp)
            row = queue.enqueue('story', ['หัวข้อคลิปยาว'], long_video={'version': 2, 'scene_count': 18})['items'][0]
            queue.edit(row['queue_id'], 'หัวข้อคลิปยาวใหม่', scene_count=50)
            saved = queue.get_item(row['queue_id'])
            self.assertEqual(saved['scene_count'], 50)
            self.assertEqual(saved['long_video']['scene_count'], 50)
            with self.assertRaises(ValueError):
                queue.edit(row['queue_id'], 'หัวข้อคลิปยาวใหม่', scene_count=51)

    def test_long_landscape_checkpoint_and_bridge_shot40(self):
        import base64
        import io
        from PIL import Image
        from core.story_manager import StoryManager
        from core.local_bridge import LocalBridge
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            manager=StoryManager(temp)
            job=manager.create('สวน',long_video={'scene_count':40})
            for size, accepted in [((320,180),True),((180,320),False)]:
                image=io.BytesIO(); Image.new('RGB',size,'green').save(image,format='PNG')
                encoded=base64.b64encode(image.getvalue()).decode()
                if accepted: manager.save_partial_image(job['id'],40,encoded)
                else:
                    with self.assertRaisesRegex(ValueError,'แนวนอน'):
                        manager.save_partial_image(job['id'],40,encoded)
            job=manager.get(job['id'])
            job.update(video_generation_mode='google_flow',generated_images=['generated/scene_40.png']*40,scene_prompts=['สวน']*40)
            manager._save(job)
            self.assertEqual(manager.flow_package(job['id'],40)['aspect_ratio'],'16:9')
            bridge=LocalBridge('127.0.0.1',0,Mock(),Mock(),stories=manager)
            command=bridge.queue_extension_command('open_flow',job['id'],shot_index=40)
            self.assertEqual(command['shot_index'],40)
            with self.assertRaises(ValueError): bridge.queue_extension_command('open_flow',job['id'],shot_index=51)
    def test_long_job_package_and_queue_keep_landscape_and_scene_count(self):
        from core.story_manager import StoryManager
        from core.story_queue import StoryBatchQueue
        with tempfile.TemporaryDirectory() as temp:
            manager=StoryManager(temp)
            job=manager.create('การปลูกต้นไม้',long_video={'duration_seconds':300,'scene_count':40})
            package=manager.plugin_request(job['id'])
            self.assertEqual(package['request']['image_count'],40)
            self.assertEqual(package['request']['aspect_ratio'],'16:9')
            self.assertNotIn('แนวตั้ง 9:16',package['prompt'])
            queue=StoryBatchQueue(temp)
            queue.enqueue_batch(['การปลูกต้นไม้'],long_video={'duration_seconds':300,'scene_count':40})
            self.assertEqual(queue.snapshot()['items'][0]['scene_count'],40)
            self.assertEqual(queue.snapshot()['items'][0]['long_video']['aspect_ratio'],'16:9')
            old=manager.create('Shorts เดิม',scene_count=10)
            self.assertNotIn('long_video',old)
            self.assertEqual(old['scene_count'],10)
            new_flow=manager.create('คลิปยาวใหม่',long_video={'version':2,'scene_count':20},
                                    video_generation_mode='google_flow')
            self.assertEqual(new_flow['scene_pipeline_version'],0)
            legacy_flow=manager.create('คลิปยาวเดิม',long_video={'version':1,'scene_count':20},
                                       video_generation_mode='google_flow')
            self.assertEqual(legacy_flow['scene_pipeline_version'],1)
    def test_api_is_sequential_and_resume_does_not_resubmit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'voice.wav'
            with wave.open(str(source),'wb') as output:
                output.setparams((1,2,8000,0,'NONE','not compressed'))
                output.writeframes(b'\x00\x00'*8000*61)
            class Client:
                def __init__(self):self.events=[]
                def create_job(self,path,language,key):
                    self.events.append('submit');return {'jobId':str(len(self.events))}
                def wait_until_done(self,job_id,**kwargs):
                    self.events.append('done');return {'segments':[{'start':0,'end':.5,'text':'คำ'}]}
                def extract_artifacts(self,result):return result
            client=Client()
            first=transcribe_chunks(client,source,root/'parts')
            self.assertEqual(client.events,['submit','done','submit','done'])
            self.assertEqual(first['segments'][1]['start'],60)
            self.assertEqual(transcribe_chunks(client,source,root/'parts'),first)
            self.assertEqual(len(client.events),4)
    def test_duration_and_scene_defaults(self):
        self.assertEqual(long_video_settings({'duration_seconds':300})['scene_count'],38)
        self.assertEqual(long_video_settings({})['aspect_ratio'],'16:9')
        self.assertEqual(long_video_settings({'duration_seconds':600})['scene_count'],50)
        self.assertEqual(long_video_settings({'duration_seconds':600})['version'],2)
        for seconds in (0,179,601,float('nan')):
            with self.assertRaises(ValueError):
                long_video_settings({'duration_seconds':seconds})
        with self.assertRaises(ValueError):
            long_video_settings({'version':1,'duration_seconds':301})

    def test_chapters_and_plan_steps_are_durable_and_append_only(self):
        from core.long_video import chapter_ranges, combine_chapters
        from core.story_manager import StoryManager
        self.assertEqual(chapter_ranges(23),[(1,10),(11,20),(21,23)])
        with tempfile.TemporaryDirectory() as temp:
            manager=StoryManager(temp)
            job=manager.create('ตำนานห้องสมุด',long_video={'version':2,'scene_count':23})
            job_id=job['id']
            outline={'job_id':job_id,'video_title':'ตำนานห้องสมุด','visual_bible':'ห้องสมุดไม้',
                     'story_entities':[],'chapter_beats':['พบแผนที่','เดินทาง','ไขปริศนา']}
            manager.save_long_video_plan_step(job_id,outline=outline)
            chapters=[]
            for index,count in enumerate((10,10,3),1):
                chapter={'job_id':job_id,'chapter_index':index,
                         'scene_prompts':[f'ภาพ {index}-{n}' for n in range(count)],
                         'scene_narrations':[f'บท {index}-{n}' for n in range(count)],
                         'scene_durations':[6]*count,'scene_entities':[[] for _ in range(count)],
                         'continuity_summary':f'เหตุการณ์ชุด {index}'}
                manager.save_long_video_plan_step(job_id,chapter=chapter,chapter_index=index)
                manager.save_long_video_plan_step(job_id,chapter=chapter,chapter_index=index)
                chapters.append(chapter)
            package=manager.plugin_request(job_id)
            self.assertEqual(len(package['long_video_plan']['chapters']),3)
            self.assertIn('ตอบเพียงคำตอบเดียว',package['prompt'])
            self.assertEqual(package['request']['long_video_chapters']['batch_size'],10)
            self.assertEqual(len(combine_chapters(outline,chapters,job_id,23)['scene_prompts']),23)
            changed=dict(chapters[1],continuity_summary='เรื่องใหม่')
            with self.assertRaisesRegex(ValueError,'ไม่เขียนทับ'):
                manager.save_long_video_plan_step(job_id,chapter=changed,chapter_index=2)

    def test_long_video_final_result_reuses_verified_image_checkpoints(self):
        import base64
        import io
        from PIL import Image
        from core.story_manager import StoryManager
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create('การเดินทาง', long_video={'version': 2, 'scene_count': 18})
            job_id = job['id']
            manager.save_long_video_plan_step(job_id, outline={
                'job_id': job_id, 'video_title': 'การเดินทาง',
                'video_description': 'ความยาวเป้าหมาย 180 วินาที จำนวน 18 ภาพ แบ่งเป็น 2 ชุด',
                'hashtags': ['#การเดินทาง', '#เรื่องเล่า', '#คลิปยาว'],
                'visual_bible': 'ถนน', 'story_entities': [],
                'chapter_beats': ['ออกเดินทาง', 'ถึงจุดหมาย'],
            })
            for index in range(1, 19):
                buffer = io.BytesIO()
                Image.new('RGB', (64, 36), (index, 50, 80)).save(buffer, format='PNG')
                manager.save_partial_image(job_id, index, base64.b64encode(buffer.getvalue()).decode())
            original = (manager.root / job_id / 'generated' / 'scene_01.png').read_bytes()
            result = {'job_id': job_id, 'video_title': 'การเดินทาง', 'video_description': 'เรื่องเล่า',
                      'narration_script': ' '.join(['การเดินทางดำเนินต่อ'] * 18),
                      'story_entities': [], 'scene_entities': [[] for _ in range(18)],
                      'scene_prompts': [f'ภาพการเดินทาง {i}' for i in range(18)],
                      'scene_narrations': [f'เรื่องเล่าภาพ {i}' for i in range(18)],
                      'scene_durations': [8] * 18, 'generated_images': [],
                      'image_checkpoint_mode': 'saved_scene_files_v1'}
            accepted = manager.apply_ai_result(result)
            self.assertEqual(len(accepted['generated_images']), 18)
            self.assertNotIn('ความยาวเป้าหมาย', accepted['video_description'])
            self.assertEqual(accepted['hashtags'], '#การเดินทาง #เรื่องเล่า #คลิปยาว')
            self.assertEqual((manager.root / job_id / 'captions' / 'hashtags.txt').read_text(encoding='utf-8'),
                             accepted['hashtags'])
            self.assertEqual((manager.root / job_id / 'generated' / 'scene_01.png').read_bytes(), original)
            corrupted = manager.root / job_id / 'generated' / 'scene_09.png'
            corrupted.write_bytes(b'not the saved image')
            with self.assertRaisesRegex(ValueError, 'Checkpoint ภาพฉาก 9 เปลี่ยนไป'):
                manager.apply_ai_result(result)

    def test_audio_chunks_reconstruct_every_sample_including_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'source.wav'
            samples=bytes(range(256))*1000
            with wave.open(str(source),'wb') as output:
                output.setparams((1,2,8000,0,'NONE','not compressed'))
                output.writeframes(samples)
            plan=prepare_subtitle_chunks(source,root/'chunks',15)
            rebuilt=b''
            for part in plan['parts']:
                with wave.open(part['path'],'rb') as audio:
                    rebuilt+=audio.readframes(audio.getnframes())
            self.assertEqual(rebuilt,samples)
            self.assertEqual(len(plan['parts']),2)
            self.assertEqual(plan['parts'][1]['offset_seconds'],15)

    def test_merge_and_reject_missing_chunk(self):
        parts=[{'offset_seconds':0,'duration_seconds':60,'segments':[{'start':59,'end':60,'text':'a'}]},
               {'offset_seconds':60,'duration_seconds':4,'segments':[{'start':0,'end':2,'text':'b'}]}]
        self.assertEqual(merge_subtitle_segments(parts)[1]['start'],60)
        parts[1]['offset_seconds']=61
        with self.assertRaises(ValueError):merge_subtitle_segments(parts)
