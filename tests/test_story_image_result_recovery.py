import json
import tempfile
import unittest
from pathlib import Path
from core.story_image_result_recovery import completed_image_result_proofs, story_image_result_review


class ResultRecoveryTests(unittest.TestCase):
    def test_receipt_review_distinguishes_empty_reply_from_failed_send(self):
        self.assertIsNone(story_image_result_review('STORY_IMAGE_REFUSED'))
        for reason in ('no_image','waiting_response','image_loading','multiple_images','request_missing',
                       'request_ambiguous','wrong_conversation','conversation_pending','generating','image_ready','send_unconfirmed','send_not_started'):
            value = story_image_result_review('STORY_IMAGE_RECEIPT_REVIEW • CHATGPT_IMAGE_RESULT_'+reason.upper())
            self.assertEqual(value['reason'], reason)
            self.assertIn('รีเฟรชตรวจผล', value['message'])
            self.assertIn('หากหน้าเว็บพร้อมและไม่มีผลจริง', value['message'])
        self.assertIn('ไม่ใช่หลักฐานว่าส่งไม่สำเร็จ', story_image_result_review(
            'STORY_IMAGE_RECEIPT_REVIEW CHATGPT_IMAGE_RESULT_NO_IMAGE')['message'])
        self.assertEqual(story_image_result_review('STORY_IMAGE_RECEIPT_REVIEW')['reason'], 'unconfirmed')
        self.assertEqual(story_image_result_review('STORY_IMAGE_RECEIPT_REVIEW CHATGPT_IMAGE_RESULT_BAD')['reason'], 'unconfirmed')

    def test_only_accepted_complete_owned_trace_authorizes_inspection(self):
        base={'job_id':'STORY-TEST','service':'chatgpt','run_id':'RUN-TEST','client_id':'a'*32,'tab_id':12,'version':'0.15.270'}
        rows=[{**base,'sequence':1,'action':'image_prompt_ready','page_url':'https://chatgpt.com/c/test',
            'detail':{'scene_index':3,'prompt':'full prompt','composer_matches':True}},
            {**base,'sequence':2,'action':'ai_send_accepted'},
            {**base,'sequence':3,'action':'recovering_stalled_image',
             'message':'พบภาพที่ 3 สมบูรณ์แล้ว แต่สถานะสร้างยังหมุนค้าง • กำลังเก็บภาพเดิมโดยไม่ส่ง Prompt ซ้ำ'}]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); (folder/'logs').mkdir(); path=folder/'logs/extension_trace.jsonl'
            def save(value):path.write_text('\n'.join(json.dumps(x) for x in value),encoding='utf-8')
            save(rows)
            self.assertEqual(list(completed_image_result_proofs(folder,'STORY-TEST','chatgpt')),['3'])
            self.assertEqual(completed_image_result_proofs(folder,'STORY-TEST','gemini'),{})
            for field,value in [('run_id','OTHER'),('job_id','OTHER'),('message','still generating')]:
                changed=[dict(x) for x in rows];changed[-1][field]=value;save(changed)
                self.assertEqual(completed_image_result_proofs(folder,'STORY-TEST','chatgpt'),{})
            save([rows[0],rows[2]])
            self.assertEqual(completed_image_result_proofs(folder,'STORY-TEST','chatgpt'),{})
