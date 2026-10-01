"""Stopped Story recovery still uses the original durable provider receipt."""
import json
import subprocess
import unittest
from pathlib import Path

from core.creation_queue import CreationQueue
from tests import test_story_saved_plan_resume as saved_resume
from ui.main_window import MainWindow


class StoppedStoryQueueTests(unittest.TestCase):
    setUp = saved_resume.SavedStoryPlanResumeTests.setUp
    job_and_analysis = saved_resume.SavedStoryPlanResumeTests.job_and_analysis
    window = saved_resume.SavedStoryPlanResumeTests.window

    def test_cancelled_partial_job_resumes_original_scene_without_new_master(self):
        job, analysis = self.job_and_analysis('chatgpt')
        ident = job['id']
        self.manager.save_analysis_checkpoint(ident, analysis)
        folder = self.manager.root / ident
        from PIL import Image
        images, clips = [], {}
        for index in range(1, 6):
            image = folder / f'generated/scene_{index:02d}.png'
            Image.new('RGB',(256,456),(index*20,30,40)).save(image)
            video = folder / f'videos/flow_scene_{index:02d}.mp4'
            video.write_bytes(b'preserved fixture video '+bytes([index]))
            images.append(str(image.relative_to(folder)))
            clips[str(index)] = str(video.relative_to(folder))
        job = self.manager.get(ident)
        job.update(generated_images=images+['generated/scene_06.png'], partial_generated_images=images,
                   partial_image_count=5, flow_clips=clips, flow_clip_count=5,
                   video_generation_mode='google_flow')
        self.manager._save(job)
        chat = 'https://chatgpt.com/c/saved-scene-six'
        trace = folder/'logs/extension_trace.jsonl'
        trace.parent.mkdir(exist_ok=True)
        common = dict(job_id=ident,service='chatgpt',run_id='RUN-SAVED',client_id='fixture',tab_id=6,page_url=chat)
        rows = [common | dict(action=action,detail={'scene_index':6}) for action in
                ('image_prompt_ready','ai_send_dispatched','ai_send_accepted','waiting_for_image')]
        trace.write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
        self.manager.mark_cancelled(ident, 'user_cancel')
        queue = CreationQueue(folder.parent.parent)
        row = queue.enqueue('story',['saved'],settings={'voice_reference_id':'frozen'})['items'][0]
        queue._update(row['queue_id'],job_id=ident,status='cancelled',cancel_requested=True)
        preserved = [trace, folder/'prompts/ai_analysis_checkpoint.json',
                     *[folder/p for p in images], *[folder/p for p in clips.values()]]
        before = {p:p.read_bytes() for p in preserved}
        queue.retry(row['queue_id'])
        queue.resume()
        self.assertEqual(queue.claim_next()['job_id'],ident)
        app = self.window()
        app.story_queue = queue
        MainWindow._retry_story_job(app,ident)
        package = self.manager.plugin_request(ident)
        app.bridge.queue_extension_command.assert_called_once_with('resume_chatgpt',ident)
        self.assertEqual(package['checkpoint_images'],images)
        self.assertEqual(package['ai_resume']['index'],6)
        self.assertEqual(package['ai_resume']['conversation_url'],chat)
        self.assertEqual(package['job']['flow_clips'],clips)
        self.assertFalse(package['job']['cancel_requested'])
        self.assertEqual(queue.item_for_job(ident)['settings']['voice_reference_id'],'frozen')
        self.assertEqual({p:p.read_bytes() for p in preserved},before)


class StoryQueueUiTests(unittest.TestCase):
    def test_actual_html_controllers_keep_one_queue_and_stopped_job_resume(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node','tests/story_queue_declutter_ui.js'],cwd=root,
                                capture_output=True,text=True,encoding='utf-8',timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('"cases":14',result.stdout)
