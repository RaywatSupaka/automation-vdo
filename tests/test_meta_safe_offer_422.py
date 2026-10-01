"""Meta completed one-off safer-version offer is not a playable video."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.meta_video import MetaVideoManager, meta_reply_failure, meta_safe_offer
from core.story_manager import StoryManager


SAFE_OFFER = (
    'วิดีโอจากภาพนี้ยังสร้างไม่ได้ในตอนนี้ค่ะ\n'
    'ภาพต้นฉบับมีการจัดองค์ประกอบที่ทำให้ระบบไม่สามารถทำเป็นวิดีโอเคลื่อนไหวพร้อมเสียงพูดได้\n'
    'ฉันช่วยทำเวอร์ชันที่ปลอดภัยขึ้นให้ได้ทันที โดยปรับการแต่งกายให้มิดชิดขึ้นและจัดเฟรมให้เห็นห้องมากขึ้น\n'
    'อยากให้ลองทำเวอร์ชันนั้นให้เลยไหม?'
)

ENGLISH_SAFE_OFFER = (
    "I wasn't able to create that exact video from this image. "
    "If you want to keep the same story, I can help with a safer version that will go through: "
    "a more covered outfit and wider framing, with the same harmless action. "
    "Want me to make that version instead?"
)

ENGLISH_DIFFERENT_TAKE = (
    "I wasn't able to generate that video from this image. "
    "If you'd like, I can help with a different take on the same moment — for example, "
    "a version with a more covered outfit, focused on the action and still vertical 9:16. "
    "Want me to try that version?"
)

ENGLISH_DIFFERENT_TAKE_INVITE = (
    "I wasn't able to generate that video from this image. "
    "If you'd like, I can help with a different take on the same moment: "
    "a vertical clip with a more covered outfit and focus on the room and the bag. "
    "Let me know if you'd like me to create that version instead."
)


class MetaSafeOffer422Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.stories = StoryManager(temp.name)
        job = self.stories.create(topic='missing keys', scene_count=1, video_generation_mode='meta_ai')
        self.job_id = job['id']
        folder = self.stories._folder(self.job_id)
        (folder / 'generated').mkdir(exist_ok=True)
        (folder / 'generated/scene.png').write_bytes(b'source-image')
        job.update(generated_images=['generated/scene.png'], scene_prompts=['living room'],
                   scene_narrations=['กุญแจหายไปไหน'], audio_choices={'mode': 'flow_original'})
        self.stories._save(job)
        self.manager = MetaVideoManager(self.stories)
        self.original = self.manager.begin(self.job_id, 1)
        self.body = {key: self.original[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        self.body['conversation_url'] = 'https://www.meta.ai/prompt/owned'
        for stage in ('uploading', 'ready_to_send', 'send_intent', 'submitted', 'generating'):
            self.manager.event({**self.body, 'stage': stage})

    def evidence(self, **overrides):
        return dict(matched_request=True, answer_complete=True, answer_truncated=False,
                    stop=False, busy=False, video_count=0, stable_ms=5000, samples=2,
                    answer_text=SAFE_OFFER) | overrides

    def test_exact_safer_offer_is_recognized_without_pretending_video(self):
        self.assertEqual(meta_reply_failure(SAFE_OFFER), 'image_not_viable')
        offer = meta_safe_offer(SAFE_OFFER)
        self.assertEqual(offer['kind'], 'safe_revision')
        self.assertIn('exactly one actual playable', offer['prompt'])
        self.assertNotIn('image already attached', offer['prompt'])
        source = Path(__file__).resolve().parents[1] / 'browser_extension/src/platforms/meta-ai/video.js'
        script = ("const fs=require('fs'),vm=require('vm');"
                  "const s={};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8').replaceAll('export ', '')"
                  "+'\\nthis.offer=metaSafeOffer;',s);"
                  "console.log(JSON.stringify(s.offer(fs.readFileSync(0,'utf8'))));")
        result = subprocess.run(['node', '-e', script, str(source)], input=SAFE_OFFER,
                                capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), offer)

    def test_live_english_safer_offer_is_recognized_by_both_sides(self):
        self.assertEqual(meta_reply_failure(ENGLISH_SAFE_OFFER), 'completed_no_video')
        offer = meta_safe_offer(ENGLISH_SAFE_OFFER)
        self.assertEqual(offer['kind'], 'safe_revision')
        source = Path(__file__).resolve().parents[1] / 'browser_extension/src/platforms/meta-ai/video.js'
        script = ("const fs=require('fs'),vm=require('vm');"
                  "const s={};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8').replaceAll('export ', '')"
                  "+'\\nthis.result=[metaReplyFailure,metaSafeOffer];',s);"
                  "const answer=fs.readFileSync(0,'utf8');"
                  "console.log(JSON.stringify(s.result.map(f=>f(answer))));" )
        result = subprocess.run(['node', '-e', script, str(source)], input=ENGLISH_SAFE_OFFER,
                                capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['completed_no_video', offer])

    def test_live_different_take_offer_is_a_single_followup_not_same_image_retry(self):
        source = Path(__file__).resolve().parents[1] / 'browser_extension/src/platforms/meta-ai/video.js'
        script = ("const fs=require('fs'),vm=require('vm');const s={};"
                  "vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8').replaceAll('export ', '')"
                  "+'\\nthis.offer=metaSafeOffer;',s);"
                  "console.log(JSON.stringify(s.offer(fs.readFileSync(0,'utf8'))));")
        for answer in (ENGLISH_DIFFERENT_TAKE, ENGLISH_DIFFERENT_TAKE_INVITE):
            with self.subTest(answer=answer):
                self.assertEqual(meta_reply_failure(answer), 'completed_no_video')
                offer = meta_safe_offer(answer)
                self.assertIsNotNone(offer)
                self.assertEqual(offer['kind'], 'safe_revision')
                result = subprocess.run(['node', '-e', script, str(source)], input=answer,
                                        capture_output=True, text=True, encoding='utf-8', timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), offer)

    def test_same_owned_chat_one_durable_followup_not_original_retry(self):
        receipt = self.manager.event({**self.body, 'stage': 'choice_prepare', 'choice_evidence': self.evidence()})
        self.assertEqual(receipt['stage'], 'generating')
        self.assertEqual(receipt['request_id'], self.original['request_id'])
        self.assertEqual(receipt['choice']['kind'], 'safe_revision')
        self.assertEqual(receipt['choice']['stage'], 'prepared')
        with self.assertRaises(ValueError):
            self.manager.event({**self.body, 'stage': 'retry_prepared', 'retry_evidence': self.evidence()})
        send = {**self.body, 'stage': 'choice_send_intent', 'choice_prompt': receipt['choice']['prompt']}
        self.assertTrue(self.manager.event(send)['choice_send_authorized'])
        self.assertFalse(MetaVideoManager(self.stories).event(send)['choice_send_authorized'])
        accepted = self.manager.event({**self.body, 'stage': 'choice_submitted',
                                       'choice_prompt': receipt['choice']['prompt'],
                                       'matched_choice': True, 'user_count': 2})
        self.assertEqual(accepted['choice']['stage'], 'accepted')

    def test_unfinished_foreign_and_explicit_policy_not_followed(self):
        for change in ({'answer_complete': False}, {'busy': True}, {'matched_request': False},
                       {'stable_ms': 4999}, {'samples': 1}, {'video_count': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manager.event({**self.body, 'stage': 'choice_prepare',
                                    'choice_evidence': self.evidence(**change)})
        self.assertIsNone(meta_safe_offer('วิดีโอไม่ได้ เพราะละเมิดนโยบายความปลอดภัย'))
        self.assertIsNone(meta_safe_offer('ฉันช่วยทำเวอร์ชันที่ปลอดภัยขึ้นได้ แต่ยังไม่ได้ตอบว่าสร้างวิดีโอไม่ได้'))
        self.assertNotIn('choice', self.manager.get(self.job_id, 1))


if __name__ == '__main__':
    unittest.main()
