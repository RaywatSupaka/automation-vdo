import copy
import subprocess
import unittest
from pathlib import Path

from core.meta_video import MetaVideoManager
from tests import test_meta_choice_382 as choice_fixture

ROOT = Path(__file__).resolve().parents[1]
CASES = choice_fixture.CASES


class MetaMultipleResults455Tests(unittest.TestCase):
    setUp = choice_fixture.MetaChoice382Tests.setUp
    prepare_body = choice_fixture.MetaChoice382Tests.prepare_body

    def comparison(self):
        branches = [dict(text=' '.join(CASES[0]['answer'].split()), complete=True, truncated=False, busy=False, video_count=0),
                    dict(text=' '.join(CASES[2]['answer'].split()), complete=True, truncated=False, busy=False, video_count=0)]
        return self.prepare_body(comparison=True, answer_text=branches[0]['text'], comparison_branches=branches,
                                 selected_branch=0)

    def test_comparison_persists_one_exact_supported_branch_and_one_send(self):
        receipt = self.manager.event(self.comparison())
        choice = receipt['choice']
        self.assertEqual(choice['proposal_branch'], 0)
        self.assertEqual(len(choice['proposal_branches']), 2)
        self.assertNotIn(CASES[2]['answer'], choice['prompt'])
        restarted = MetaVideoManager(self.stories)
        self.assertEqual(restarted.event(self.comparison()), receipt)
        send = dict(self.body, stage='choice_send_intent', choice_prompt=choice['prompt'])
        self.assertTrue(restarted.event(send)['choice_send_authorized'])
        self.assertFalse(restarted.event(send)['choice_send_authorized'])
        changed = self.comparison()
        changed['choice_evidence']['comparison_branches'][1]['text'] += ' changed'
        with self.assertRaises(ValueError): restarted.event(changed)

    def test_invalid_or_mixed_branch_evidence_does_not_authorize_choice(self):
        original = self.comparison()
        for change in ('missing', 'busy', 'unfinished', 'wrong_selection', 'combined', 'video'):
            body = copy.deepcopy(original)
            proof = body['choice_evidence']
            if change == 'missing': proof.pop('comparison_branches')
            if change == 'busy': proof['comparison_branches'][1]['busy'] = True
            if change == 'unfinished': proof['comparison_branches'][1]['complete'] = False
            if change == 'wrong_selection': proof['selected_branch'] = 1
            if change == 'combined': proof['answer_text'] += proof['comparison_branches'][1]['text']
            if change == 'video': proof['comparison_branches'][1]['video_count'] = 1
            with self.subTest(change=change), self.assertRaises(ValueError): self.manager.event(body)
        self.assertNotIn('choice', self.manager.get(self.job_id, 1))

    def test_actual_source_dom(self):
        result = subprocess.run(['node', 'tests/meta_multiple_results_455.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_selected_video_is_durable_and_download_cannot_switch_assets(self):
        proof = dict(matched_request=True, ready=True, stop=False, busy=False, asset_sha256='a' * 64)
        body = dict(self.body, stage='video_select', video_evidence=proof)
        receipt = self.manager.event(body)
        self.assertEqual(receipt['stage'], 'generating')
        self.assertEqual(MetaVideoManager(self.stories).event(body), receipt)
        for invalid in ({'asset_sha256': 'b' * 64}, {'ready': False}, {'stop': True}, {'busy': True},
                        {'matched_request': False}, {'asset_sha256': 'signed-url'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.manager.event(dict(body, video_evidence=proof | invalid))
        with self.assertRaises(ValueError):
            self.manager.event(dict(self.body, stage='download_intent', asset_sha256='b' * 64))
        self.assertEqual(self.manager.event(dict(self.body, stage='download_intent', asset_sha256='a' * 64))['stage'], 'download_intent')

    def test_unconfirmed_choice_cannot_select_an_old_video(self):
        self.manager.event(self.comparison())
        with self.assertRaises(ValueError):
            self.manager.event(dict(self.body, stage='video_select', video_evidence=dict(
                matched_request=True, ready=True, stop=False, busy=False, asset_sha256='a' * 64)))


if __name__ == '__main__': unittest.main()
