import json
import unittest
from core.motion_json_contract import motion_json_contract
from core.story_visual_plan import motion_request
from core.flow_motion_plan import motion_format_request


class MotionJsonContractTests(unittest.TestCase):
    def test_quoted_thai_dialogue_example_is_valid_json(self):
        context = dict(job_id='STORY-FIXTURE', index=1, context_id='fixture-context',
                       audio_instruction='AUDIO PERFORMANCE: พูดคำว่า "สวัสดี"')
        contract = motion_json_contract(context)
        example = json.loads(contract.split('\n', 1)[1])
        self.assertIn('"ตัวอย่างบทพูด"', example['prompt'])
        self.assertIs(example['needs_review'], True)
        self.assertEqual(example['context_id'], context['context_id'])
        request = motion_request(context)
        self.assertIn(contract, request)
        self.assertIn('on-camera', request)
        self.assertEqual(json.loads(request.split('ACTUAL SCENE DATA:\n')[1])['context'], context)

    def test_repair_preserves_malformed_answer_and_instructs_quote_escape(self):
        context = dict(job_id='STORY-FIXTURE', index=1, context_id='fixture-context')
        bad = '{"prompt":"Spoken line: "สวัสดี"", "needs_review":false}'
        with self.assertRaises(json.JSONDecodeError):
            json.loads(bad)
        request = motion_format_request(context, bad, 'original scene instructions')
        self.assertIn(motion_json_contract(context), request)
        data = json.loads(request.split('ACTUAL REPAIR DATA:\n')[1])
        self.assertEqual(data['previous_answer'], bad)
        self.assertEqual(data['original_request'], 'original scene instructions')
        self.assertIn('Do not convert a review', request)
