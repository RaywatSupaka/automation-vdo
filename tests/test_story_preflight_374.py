import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.ai_web_resume import ai_web_resume_target
from core.story_receipt_recovery import pending_story_image_target

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://chatgpt.com/c/preflight-374'


class StoryPreflight374Tests(unittest.TestCase):
    def fixture(self):
        common = dict(job_id='STORY-374', service='chatgpt', client_id='fixture',
                      run_id='RUN-374', tab_id=12, page_url=URL, version='0.15.373')
        def row(sequence, action, **extra):
            return dict(common, sequence=sequence, action=action, at='2026-09-17T12:18:01', **extra)
        rows = [row(1, 'generating_images'), row(2, 'waiting_for_composer'),
                row(3, 'image_prompt_ready', detail=dict(scene_index=5, prompt='Scene  five',
                    composer_text='Scene five', composer_matches=True)),
                row(4, 'image_attempt_result'), row(5, 'error', message=(
                    'ผิดพลาด: STORY_IMAGE_RECEIPT_REVIEW • ภาพฉาก 5 • '
                    'CHATGPT_IMAGE_RESULT_SEND_UNCONFIRMED • Prompt เปลี่ยนหรือไม่ครบก่อนกดส่ง '
                    '(11/10 ตัวอักษร) จึงยังไม่คลิก • เก็บฉากเดิมไว้ ไม่สร้างภาพซ้ำ'))]
        return dict(id='STORY-374', image_ai_provider='chatgpt', ai_status='ready'), rows

    def test_owned_pending_image_routes_before_analysis_ready_exit(self):
        job, rows = self.fixture()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'logs').mkdir()
            path = folder / 'logs/extension_trace.jsonl'
            path.write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
            before = path.read_bytes()
            result = ai_web_resume_target(folder, job)
            self.assertEqual((result['stage'], result['index'], result['conversation_url']), ('image', 5, URL))
            self.assertEqual(result['pre_send_proof']['prompt'], 'Scene five')
            self.assertEqual(path.read_bytes(), before)

    def test_passive_resume_at_root_keeps_exact_image_origin(self):
        job, rows = self.fixture()
        for action in ['ai_model_ready', 'waiting_for_analysis', 'analysis_saved', 'recovering_images',
                       'generating_images', 'waiting_for_image', 'story_image_result_review', 'error']:
            rows.append(dict(rows[-1], sequence=len(rows)+1, action=action, page_url='https://chatgpt.com/', tab_id=24))
        result = pending_story_image_target(Path('unused'), job, rows)
        self.assertEqual(result['conversation_url'], URL)
        self.assertIn('pre_send_proof', result)

    def test_unknown_or_dispatched_never_grants_pre_send_recovery(self):
        for mutation in ['version', 'sequence', 'client', 'message', 'accepted', 'prompt', 'missing_row', 'time']:
            with self.subTest(mutation=mutation):
                job, rows = self.fixture()
                if mutation == 'version': rows[4]['version'] = '0.15.372'
                elif mutation == 'sequence': rows[4]['sequence'] = 8
                elif mutation == 'client': rows[4]['client_id'] = 'other'
                elif mutation == 'message': rows[4]['message'] = 'send timed out'
                elif mutation == 'accepted': rows.append(dict(rows[4], action='ai_send_accepted'))
                elif mutation == 'prompt': rows[2]['detail']['composer_text'] = 'Different scene'
                elif mutation == 'missing_row': rows.pop(3)
                elif mutation == 'time': rows[4]['at'] = '2026-09-17T12:30:01'
                result = pending_story_image_target(Path('unused'), job, rows)
                self.assertNotIn('pre_send_proof', result)

    def test_completed_images_and_other_provider_unchanged(self):
        job, rows = self.fixture()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder/'generated').mkdir()
            (folder/'generated/scene_05.png').write_bytes(b'saved')
            self.assertIsNone(pending_story_image_target(folder, job, rows))
            job['image_ai_provider'] = 'gemini'
            self.assertIsNone(pending_story_image_target(folder, job, rows))

    def test_root_first_send_binds_only_owned_later_conversation(self):
        job, rows = self.fixture()
        rows[2]['page_url'] = 'https://chatgpt.com/'
        self.assertEqual(pending_story_image_target(Path('unused'), job, rows)['conversation_url'], URL)
        for row in rows: row['page_url'] = 'https://chatgpt.com/'
        self.assertIsNone(pending_story_image_target(Path('unused'), job, rows))

    def test_real_background_preflight_harness(self):
        result = subprocess.run([shutil.which('node'), 'tests/story_preflight_374_harness.js'],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
