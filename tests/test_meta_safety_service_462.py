"""Observed outage: same input retry, then durable original-provider helper. Offline only."""
import json
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from core.meta_video import MetaVideoManager, meta_reply_failure
from tests import test_meta_retry_381 as fixture
from tests.test_audit_fixes_426 import picture

CASES = json.loads((fixture.ROOT / 'tests/meta_safety_service_462.json').read_text(encoding='utf-8'))
ANSWER = CASES[0][0]


class MetaSafetyService462(unittest.TestCase):
    setUp = fixture.MetaRetry381Tests.setUp
    retry = fixture.MetaRetry381Tests.retry

    def advance(self, end='generating'):
        receipt=self.manager.begin(self.job_id,1)
        body={key:receipt[key] for key in ('job_id','index','request_id','context_id')}
        if receipt.get('scene_video_plan'): body['scene_video_plan']=receipt['scene_video_plan']
        for stage in self.manager.STAGES[1:]:
            if stage=='submitted': body['conversation_url']='https://www.meta.ai/prompt/'+receipt['request_id']
            self.manager.event({**body,'stage':stage})
            if stage==end: break
        return body

    def failure(self, body, **changes):
        return self.retry(body, **dict(answer_text=ANSWER, composer_empty=True, **changes))

    def due(self, body, now=1000):
        with patch('core.meta_video.time.time', return_value=now):
            waiting = self.manager.event(self.failure(body))
        self.assertEqual(waiting['stage'], 'generating')
        deadline = waiting['recovery']['next_retry_at']
        self.manager = MetaVideoManager(self.stories)
        with patch('core.meta_video.time.time', return_value=deadline):
            return self.manager.event(self.failure(body)), deadline

    def finish_helper(self, body, receipt, color='orange'):
        claim = {**body, 'redesign_id': receipt['redesign']['id'], 'action': 'claim'}
        self.assertTrue(self.manager.redesign_event(claim)['send_authorized'])
        self.assertFalse(self.manager.redesign_event(claim)['send_authorized'])
        saved = self.manager.redesign_event({**claim, 'action':'save_image', 'image':picture(color)})
        self.assertEqual(saved['redesign']['phase'], 'image_saved')
        prompt = {**claim, 'action':'save_prompt', 'proposal': {
            'needs_review':False, 'video_prompt':'Slow side camera track across the quiet market.'}}
        fresh = self.manager.redesign_event(prompt)
        self.assertEqual(self.manager.redesign_event(prompt), fresh)
        self.assertNotIn('conversation_url', fresh)
        return fresh

    def test_classifier_python_js_share_exact_observed_and_opposite_cases(self):
        for text, expected in CASES:
            with self.subTest(text=text):
                self.assertEqual(meta_reply_failure(text), expected)

    def test_fresh_same_input_then_two_stage_helper_and_repeated_cycles(self):
        store = self.manager._store(self.job_id)
        body = self.advance()
        data = store.read(); data['scenes']['2'] = dict(stage='stored', path='keep.mp4', sha256='keep')
        store.write(data)
        original = self.manager.package(self.job_id, 1)
        now = 1000
        for round_no, color in enumerate(('orange','blue','green'), 1):
            fresh, now = self.due(body, now)
            self.assertEqual(fresh['stage'], 'prepared')
            self.assertEqual(fresh['service_retry_count'], 1)
            self.assertEqual(fresh.get('redesign_round',0), round_no - 1)
            self.assertNotIn('conversation_url', fresh)
            before = self.manager.package(self.job_id, 1)
            if round_no == 1: self.assertEqual(before, original)
            body = self.advance()
            helper, now = self.due(body, now + 10)
            self.assertEqual(helper['stage'], 'redesigning')
            self.assertEqual(helper['redesign']['round'], round_no)
            self.assertEqual(helper['redesign']['failure_reason'], 'transient_service_error')
            self.assertIn('technical error', helper['redesign']['request'])
            self.assertEqual(self.manager.package(self.job_id, 1), before)
            self.finish_helper(body, helper, color)
            self.assertEqual(store.read()['scenes']['2'], data['scenes']['2'])
            self.assertEqual((self.stories._folder(self.job_id)/'generated/scene.png').read_bytes(), b'original-image')
            self.assertNotIn('rejected composition', self.manager.package(self.job_id, 1)['prompt'])
            body = self.advance()
            now += 10
        self.assertEqual(len(store.read()['attempt_history']['1']), 6)

    def test_no_helper_before_retry_cooldown_or_without_fresh_proof(self):
        body = self.advance()
        with self.assertRaises(ValueError):
            self.manager.event({**self.failure(body), 'stage':'redesign_prepare'})
        self.due(body)
        body = self.advance()
        with patch('core.meta_video.time.time', return_value=2000):
            waiting = self.manager.event(self.failure(body))
            with self.assertRaises(ValueError):
                self.manager.event({**self.failure(body), 'stage':'redesign_prepare'})
        for changes in ({'busy':True},{'stop':True},{'video_count':1},{'matched_request':False},
                        {'answer_complete':False},{'answer_truncated':True},{'composer_empty':False},
                        {'stable_ms':float('nan')},{'stable_ms':float('inf')},{'samples':1}):
            proof = self.failure(body); proof['retry_evidence'].update(changes)
            with self.subTest(changes=changes), patch('core.meta_video.time.time',return_value=3000), self.assertRaises(ValueError):
                self.manager.event(proof)
        for text, expected in CASES:
            if expected in ('policy','quota','authentication_required'):
                proof=self.failure(body); proof['retry_evidence']['answer_text']=text
                with self.subTest(expected=expected), self.assertRaises(ValueError): self.manager.event(proof)
        self.assertEqual(self.manager.get(self.job_id,1),waiting)

    def test_duplicate_due_and_restart_keep_one_helper(self):
        self.due(self.advance())
        body = self.advance()
        with patch('core.meta_video.time.time', return_value=2000): self.manager.event(self.failure(body))
        with patch('core.meta_video.time.time', return_value=2300), ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _: self.manager.event(self.failure(body)), range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(results[0]['stage'],'redesigning')
        self.assertEqual(MetaVideoManager(self.stories).event(self.failure(body)),results[0])
        self.assertEqual(len(self.manager._store(self.job_id).read()['attempt_history']['1']),1)

    def test_late_video_cancel_and_stale_owner_prevent_helper(self):
        self.due(self.advance()); body=self.advance()
        with patch('core.meta_video.time.time',return_value=2000): self.manager.event(self.failure(body))
        for change in ({'request_id':'foreign'},{'context_id':'foreign'},
                       {'conversation_url':'https://www.meta.ai/prompt/foreign'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manager.event({**self.failure(body),**change})
        self.manager.event({**body,'stage':'download_intent'})
        with self.assertRaises(ValueError): self.manager.event(self.failure(body))
        job=self.stories.get(self.job_id); job['cancel_requested']=True; self.stories._save(job)
        with self.assertRaises(ValueError): self.manager.event(self.failure(body))

    def test_controller_and_native_provider_html(self):
        result=subprocess.run(['node','tests/meta_safety_service_462.cjs'],cwd=fixture.ROOT,
            capture_output=True,text=True,encoding='utf-8',timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_remaining_scene_plan_binding_survives_retry_and_helper(self):
        from core import scene_video_plan as plans
        job=self.stories.get(self.job_id); job.update(product_story={'product_id':'FIXTURE'},status='error')
        self.stories._save(job)
        plans.save(self.stories,self.job_id,0,'meta_ai',[1],None)
        applied=plans.apply_at_safe_boundary(self.stories,self.job_id,1)
        binding=plans.package_binding(applied['job'],1)
        first,_=self.due(self.advance())
        self.assertEqual(first['scene_video_plan'],binding)
        body=self.advance(); helper,_=self.due(body,2000)
        next_scene=self.finish_helper(body,helper)
        self.assertEqual(next_scene['scene_video_plan'],binding)
        self.assertEqual(self.manager.begin(self.job_id,1)['request_id'],next_scene['request_id'])

    def test_changed_technical_wording_after_outage_still_reaches_helper(self):
        fresh,_=self.due(self.advance())
        self.assertEqual(fresh['safety_service_recovery'],1)
        body=self.advance(); request=self.failure(body)
        request['retry_evidence']['answer_text']='Server error: could not generate a video.'
        with patch('core.meta_video.time.time',return_value=2000):
            wait=self.manager.event(request)
        with patch('core.meta_video.time.time',return_value=wait['recovery']['next_retry_at']):
            result=self.manager.event(request)
        self.assertEqual(result['stage'],'redesigning')
        next_scene=self.finish_helper(body,result)
        self.assertEqual(next_scene['safety_service_recovery'],1)


if __name__=='__main__': unittest.main()
