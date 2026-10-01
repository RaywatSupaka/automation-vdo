"""Exact retained Meta M5/M6 replies, not hypothetical provider instructions."""
import json
import subprocess
import unittest
from pathlib import Path

from core.meta_video import MetaVideoManager, meta_followup_offer, meta_reply_failure, meta_safe_offer
from tests import test_meta_safe_offer_422 as fixture


ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'tests/meta_historical_offer_cases.json').read_text(encoding='utf-8'))


class MetaHistoricalOffersTests(unittest.TestCase):
    setUp = fixture.MetaSafeOffer422Tests.setUp
    evidence = fixture.MetaSafeOffer422Tests.evidence

    def assert_js_parity(self, answer, expected):
        script = ("const fs=require('fs'),vm=require('vm');const scope={};"
                  "vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8').replaceAll('export ', '')"
                  "+'\\nthis.read=metaFollowupOffer;',scope);"
                  "console.log(JSON.stringify(scope.read(fs.readFileSync(0,'utf8'))));")
        result = subprocess.run(['node', '-e', script, str(ROOT / 'browser_extension/src/platforms/meta-ai/video.js')],
                                input=answer, capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)

    def test_exact_one_off_new_starting_image_offer_matches_both_sides(self):
        answer = CASES[0]['answer']
        self.assertEqual(meta_reply_failure(answer), 'completed_no_video')
        offer = meta_followup_offer(answer)
        self.assertEqual(offer['kind'], 'safe_revision')
        self.assertEqual(offer['number'], 0)
        self.assertIn('revised starting visual', offer['prompt'])
        self.assertIn('exactly one actual playable', offer['prompt'])
        self.assert_js_parity(answer, offer)

    def test_exact_two_alternatives_choose_only_proven_modest_clothing_not_style(self):
        answer = CASES[1]['answer']
        self.assertEqual(meta_reply_failure(answer), 'completed_no_video')
        offer = meta_followup_offer(answer)
        self.assertEqual(offer['selection'], 'first_clothing_only')
        self.assertEqual(offer['number'], 1)
        self.assertIn('Use only the first adjustment', offer['prompt'])
        self.assertIn('product identity and visibility', offer['prompt'])
        self.assertIn('visual style, exact dialogue and audio settings unchanged', offer['prompt'])
        self.assertIn('Do not choose the alternative animation/drawing style', offer['prompt'])
        self.assertIn('report that conflict truthfully', offer['prompt'])
        self.assertIn('exactly one actual playable', offer['prompt'])
        self.assertNotIn('รอแป๊บ', offer['prompt'])  # No guessed replacement script.
        self.assert_js_parity(answer, offer)

    def test_ambiguous_first_change_or_additional_choices_are_not_accepted(self):
        answer = CASES[1]['answer']
        mutations = (
            answer.replace('เสื้อยืดกับกางเกงขายาว', 'เสื้อยืดกับกางเกงขายาวและเปลี่ยนสินค้า'),
            answer.replace('เสื้อยืดกับกางเกงขายาว', 'คนใหม่ในเสื้อยืดกับกางเกงขายาว'),
            answer.replace('เสื้อยืดกับกางเกงขายาว', 'เสื้อยืดกับกางเกงขายาวและพูดบทใหม่'),
            answer.replace('หรือทำเป็นสไตล์แอนิเมชัน/ภาพวาด', 'หรือทำเป็นสไตล์แอนิเมชัน/ภาพวาด หรือเพิ่มเสียงเพลง'),
            answer.replace('โดยยังคงไอเดียเดิมไว้ทั้งหมด', 'โดยเปลี่ยนเรื่องใหม่'),
            answer.replace('โดยยังคงไอเดียเดิมไว้ทั้งหมด', 'โดยยังคงไอเดียเดิมไว้ทั้งหมดและเปลี่ยนเสียง'),
            answer.replace('เช่น ปรับชุด', 'ตัวเลือก 1 เช่น ปรับชุด'),
        )
        for changed in mutations:
            with self.subTest(answer=changed):
                self.assertIsNone(meta_followup_offer(changed))
                self.assert_js_parity(changed, None)

    def test_one_off_requires_completed_inability_explicit_offer_and_invitation(self):
        answer = CASES[0]['answer']
        mutations = (
            answer.replace('ไม่สามารถสร้างวิดีโอจากภาพอ้างอิงนี้ได้ในตอนนี้ค่ะ', 'กำลังสร้างวิดีโอจากภาพนี้ค่ะ'),
            answer.replace('ฉันสามารถสร้างวิดีโอใหม่ให้ได้ด้วยภาพเริ่มต้นที่ฉันสร้างขึ้นเอง', 'มีภาพเริ่มต้นอีกภาพหนึ่ง'),
            answer[:answer.index('อยากให้ฉันลอง')],
        )
        for changed in mutations:
            with self.subTest(answer=changed):
                self.assertIsNone(meta_safe_offer(changed))
                self.assert_js_parity(changed, None)

    def test_policy_and_quota_are_not_converted_to_offers(self):
        for row in CASES:
            for suffix in (' This violates safety policy.', ' Quota exceeded.'):
                answer = row['answer'] + suffix
                self.assertIsNone(meta_followup_offer(answer))
                self.assert_js_parity(answer, None)

    def test_each_offer_uses_one_durable_followup_and_never_reuploads_original(self):
        for row in CASES:
            with self.subTest(family=row['family']):
                # Separate fixture per family, including its own saved image.
                self.setUp()
                package = self.manager.package(self.job_id, 1)
                proof = self.evidence(answer_text=row['answer'])
                prepared = self.manager.event(dict(self.body, stage='choice_prepare', choice_evidence=proof))
                self.assertEqual(prepared['request_id'], self.original['request_id'])
                self.assertEqual(prepared['stage'], 'generating')
                self.assertEqual(prepared['choice']['stage'], 'prepared')
                self.assertEqual(prepared, MetaVideoManager(self.stories).event(dict(self.body, stage='choice_prepare', choice_evidence=proof)))
                with self.assertRaises(ValueError):
                    self.manager.event(dict(self.body, stage='retry_prepared', retry_evidence=proof))
                send = dict(self.body, stage='choice_send_intent', choice_prompt=prepared['choice']['prompt'])
                self.assertTrue(self.manager.event(send)['choice_send_authorized'])
                self.assertFalse(MetaVideoManager(self.stories).event(send)['choice_send_authorized'])
                accepted = self.manager.event(dict(self.body, stage='choice_submitted', matched_choice=True,
                    user_count=2, choice_prompt=prepared['choice']['prompt']))
                self.assertEqual(accepted['choice']['stage'], 'accepted')
                self.assertEqual(accepted['stage'], 'generating')
                self.assertFalse(self.manager.event(send)['choice_send_authorized'])
                self.assertEqual(self.manager.package(self.job_id, 1), package)

    def test_native_comparison_busy_unfinished_or_unowned_offer_cannot_authorize_send(self):
        for row in CASES:
            for change in ({'comparison': True}, {'busy': True}, {'stop': True}, {'video_count': 1},
                           {'matched_request': False}, {'answer_complete': False}, {'answer_truncated': True},
                           {'samples': 1}, {'stable_ms': 4999}, {'stable_ms': float('nan')}, {'stable_ms': float('inf')}):
                with self.subTest(family=row['family'], change=change), self.assertRaises(ValueError):
                    self.manager.event(dict(self.body, stage='choice_prepare',
                                            choice_evidence=self.evidence(answer_text=row['answer'], **change)))
        self.assertNotIn('choice', self.manager.get(self.job_id, 1))


if __name__ == '__main__':
    unittest.main()
