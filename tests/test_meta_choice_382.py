import json
import logging
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path

from core.meta_video import MetaVideoManager, meta_choice_offer
from core.story_manager import StoryManager

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'tests/meta_choice_cases_382.json').read_text(encoding='utf-8'))


class MetaChoice382Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stories = StoryManager(self.temp.name)
        job = self.stories.create(topic='meta choice', scene_count=6, video_generation_mode='meta_ai')
        self.job_id = job['id']
        folder = self.stories._folder(self.job_id)
        (folder / 'generated/scene.png').write_bytes(b'original-image')
        job.update(scene_count=1, generated_images=['generated/scene.png'], scene_prompts=['market'],
                   scene_narrations=['path opens'], audio_choices={'mode':'flow_original'})
        self.stories._save(job)
        self.manager = MetaVideoManager(self.stories, lambda _: dict(width=720, height=1280, duration=10))
        self.original = self.manager.begin(self.job_id, 1)
        self.body = {key:self.original[key] for key in ('job_id','index','request_id','context_id')}
        for stage in ('uploading','ready_to_send','send_intent','submitted','generating'):
            if stage == 'submitted': self.body['conversation_url'] = 'https://www.meta.ai/prompt/owned'
            self.manager.event({**self.body,'stage':stage})

    def prepare_body(self, **proof):
        return {**self.body, 'stage':'choice_prepare', 'choice_evidence':dict(
            matched_request=True, answer_complete=True, answer_truncated=False, stop=False, busy=False,
            video_count=0, stable_ms=5000, samples=2, answer_text=CASES[0]['answer']) | proof}

    def prepare(self):
        return self.manager.event(self.prepare_body())

    def confirm(self):
        receipt = self.prepare()
        prompt = receipt['choice']['prompt']
        self.manager.event({**self.body,'stage':'choice_send_intent','choice_prompt':prompt})
        return self.manager.event({**self.body,'stage':'choice_submitted','choice_prompt':prompt,
                                   'matched_choice':True,'user_count':2})

    def test_offer_parser_and_original_request_preserved(self):
        for case in CASES:
            with self.subTest(case=case['name']):
                result = meta_choice_offer(case['answer'])
                self.assertEqual(bool(result),case['expected'])
                if result:
                    self.assertEqual(result['number'],2)
                    self.assertIn('I choose option 2:',result['prompt'])
        receipt = self.prepare()
        self.assertEqual(receipt['request_id'],self.original['request_id'])
        self.assertEqual(receipt['stage'],'generating')
        self.assertEqual(receipt['conversation_url'],self.body['conversation_url'])
        self.assertEqual(self.manager.package(self.job_id,1)['context_id'],self.original['context_id'])
        self.assertNotIn('retry_count',receipt)

    def test_choice_send_claim_is_one_shot_after_restart_and_ack_loss(self):
        prepared = self.prepare()
        self.assertEqual(self.prepare(),prepared)
        send = {**self.body,'stage':'choice_send_intent','choice_prompt':prepared['choice']['prompt']}
        first = self.manager.event(send)
        self.assertTrue(first['choice_send_authorized'])
        self.assertNotIn('choice_send_authorized',self.manager.get(self.job_id,1))
        restarted = MetaVideoManager(self.stories)
        self.assertFalse(restarted.event(send)['choice_send_authorized'])
        self.assertEqual(restarted.begin(self.job_id,1)['choice']['stage'],'send_intent')
        self.assertEqual(restarted.event(self.prepare_body())['choice']['stage'],'send_intent')

    def test_unknown_choice_send_resume_never_reopens_claim(self):
        self.prepare()
        prompt = self.manager.get(self.job_id,1)['choice']['prompt']
        send = {**self.body,'stage':'choice_send_intent','choice_prompt':prompt}
        self.manager.event(send)
        self.manager.event({**self.body,'stage':'needs_attention'})
        resumed = self.manager.begin(self.job_id,1,resume=True)
        self.assertEqual(resumed['choice']['stage'],'send_intent')
        self.assertFalse(self.manager.event(send)['choice_send_authorized'])

    def test_no_retry_of_an_offer_and_no_old_video_while_choice_unconfirmed(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.manager.event({**self.body,'stage':'download_intent'})
        with self.assertRaises(ValueError):
            self.manager.event({**self.body,'stage':'retry_prepared','retry_evidence':self.prepare_body()['choice_evidence']})

    def test_wrong_confirmation_and_modified_offer_rejected(self):
        prepared = self.prepare()
        with self.assertRaises(ValueError):
            self.manager.event({**self.body,'stage':'choice_submitted','choice_prompt':prepared['choice']['prompt'],
                               'matched_choice':True,'user_count':2})
        self.manager.event({**self.body,'stage':'choice_send_intent','choice_prompt':prepared['choice']['prompt']})
        for invalid in ({'choice_prompt':'wrong'}, {'matched_choice':False}, {'user_count':1}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.manager.event({**self.body,'stage':'choice_submitted','choice_prompt':prepared['choice']['prompt'],
                                   'matched_choice':True,'user_count':2,**invalid})
        with self.assertRaises(ValueError): self.manager.event(self.prepare_body(answer_text=CASES[2]['answer']))

    def test_invalid_completion_cannot_select(self):
        for change in ({'stop':True},{'busy':True},{'video_count':1},{'answer_complete':False},
                       {'answer_truncated':True},{'matched_request':False},{'stable_ms':4999},{'samples':1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manager.event(self.prepare_body(**change))
        self.assertNotIn('choice',self.manager.get(self.job_id,1))

    def test_cancel_wrong_url_and_context_block_selection(self):
        for change in ({'conversation_url':'https://www.meta.ai/prompt/other'},{'context_id':'wrong'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manager.event({**self.prepare_body(),**change})
        job = self.stories.get(self.job_id);job['cancel_requested']=True;self.stories._save(job)
        with self.assertRaises(ValueError): self.prepare()

    def test_actual_file_stored_with_choice_provenance(self):
        receipt = self.confirm()
        self.assertEqual(receipt['choice']['stage'],'accepted')
        for stage in ('download_intent','downloading'):
            self.manager.event({**self.body,'stage':stage,'download_id':9})
        source = Path(self.temp.name)/'result.mp4';source.write_bytes(b'actual-fixture-video'*100)
        self.manager.event({**self.body,'stage':'stored','download_id':9,'filename':str(source)})
        proof = self.stories.get(self.job_id)['meta_clip_receipts']['1']['choice']
        self.assertEqual(proof['number'],2)
        self.assertEqual(proof['proposal_sha256'],receipt['choice']['proposal_sha256'])
        self.assertEqual(self.manager.clips(self.job_id)[0].read_bytes(),source.read_bytes())

    def test_real_source_dom_and_controller(self):
        expected = [meta_choice_offer(case['answer']) for case in CASES]
        result = subprocess.run(['node',str(ROOT/'tests/meta_choice_382.cjs')],input=json.dumps(expected,ensure_ascii=False),
                                capture_output=True,text=True,encoding='utf-8',timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_concurrent_claims_authorize_only_one_press(self):
        from concurrent.futures import ThreadPoolExecutor
        prepared = self.prepare()
        send = {**self.body,'stage':'choice_send_intent','choice_prompt':prepared['choice']['prompt']}
        with ThreadPoolExecutor(max_workers=2) as executor:
            replies = list(executor.map(lambda _: MetaVideoManager(self.stories).event(send),range(2)))
        self.assertEqual(sum(r['choice_send_authorized'] for r in replies),1)

    def test_choice_lifecycle_via_authenticated_bridge(self):
        from core.local_bridge import LocalBridge
        from core.product_manager import ProductManager
        bridge = LocalBridge('127.0.0.1',0,ProductManager(self.temp.name),logging.getLogger('choice-http'),
                             stories=self.stories).start()
        try:
            base = f'http://127.0.0.1:{bridge.server.server_address[1]}'
            from tests.extension_identity_fixture import pair_fixture
            headers = {'Origin':pair_fixture(bridge),'X-SmartFlow-Token':bridge._extension_token,
                       'Content-Type':'application/json'}
            def post(body):
                request = urllib.request.Request(base+'/api/meta-video/event',
                    data=json.dumps({**body,'version':LocalBridge.REQUIRED_EXTENSION_VERSION}).encode(),headers=headers)
                with urllib.request.urlopen(request,timeout=5) as response: return json.load(response)['receipt']
            prepared = post(self.prepare_body())
            send = {**self.body,'stage':'choice_send_intent','choice_prompt':prepared['choice']['prompt']}
            self.assertTrue(post(send)['choice_send_authorized'])
            self.assertFalse(post(send)['choice_send_authorized'])
            accepted = post({**send,'stage':'choice_submitted','matched_choice':True,'user_count':2})
            self.assertEqual(accepted['choice']['stage'],'accepted')
            self.assertEqual(accepted['request_id'],self.original['request_id'])
        finally:
            bridge.stop()


if __name__ == '__main__': unittest.main()
