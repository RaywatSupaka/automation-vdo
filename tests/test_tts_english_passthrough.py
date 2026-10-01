"""English narration must reach speech unchanged, not stop automation."""
import json
import tempfile
import unittest
from pathlib import Path

from core.product_manager import ProductManager
from core.story_finisher import _subtitle_script
from core.studio_review import voice_review
from core.thai_tts import prepare_thai_tts_script


class TtsEnglishPassthroughTests(unittest.TestCase):
    def test_reported_title_and_unknown_names_are_not_blockers(self):
        for text in ('เรื่อง Re:Zero เริ่มต้นแล้ว', 'UnknownHero ปรากฏตัว',
                     'Re:Zero', 'Hello from AnotherWorld', 'ชื่อ X และ Y'):
            with self.subTest(text=text):
                self.assertEqual(prepare_thai_tts_script(text), (text, []))

    def test_existing_readings_numbers_and_pause_tags_stay_unchanged(self):
        text, issues = prepare_thai_tts_script('Re:Zero EP 2 [pause:0.5] ใช้ USB',
                                              {'Re:Zero': 'รี ซีโร่'})
        self.assertEqual(text, 'รี ซีโร่ อีพี สอง [pause:0.5] ใช้ ยูเอสบี')
        self.assertEqual(issues, [])

    def test_empty_script_and_unsupported_tags_still_need_attention(self):
        self.assertEqual(prepare_thai_tts_script('  '), ('', ['ยังไม่มีบทพูด']))
        text, issues = prepare_thai_tts_script('Re:Zero [unsupported] มาแล้ว')
        self.assertIn('Re:Zero', text)
        self.assertEqual(issues, ['พบแท็กที่ Voice AI อาจไม่รองรับ: [unsupported]'])

    def test_story_voice_review_and_subtitles_preserve_english_without_job_edit(self):
        job = {'narration_script': 'เรื่อง Re:Zero เริ่มต้นแล้ว'}
        before = json.dumps(job, sort_keys=True)
        review = voice_review(job)
        self.assertTrue(review['ready'])
        self.assertEqual(review['issues'], [])
        self.assertEqual(_subtitle_script(job)[0], review['script'])
        self.assertEqual(review['script'], job['narration_script'])
        self.assertEqual(json.dumps(job, sort_keys=True), before)

    def test_drama_subtitle_dialogue_allows_english(self):
        job = {'job_type': 'drama_episode', 'dialogue_turns': [
            {'speaker': 'ผู้เล่า', 'text': 'ไปที่ AnotherWorld กัน'}]}
        self.assertEqual(_subtitle_script(job)[0], 'ไปที่ AnotherWorld กัน')

    def test_product_saved_english_warning_recomputed_without_invalidating_paid_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({'product_name': 'กล้อง',
                                             'product_url': 'https://shopee.co.th/product/1/2'})
            folder = manager.root / job['id']
            script = 'กล้อง AnotherBrand ภาพสวย'
            (folder / 'captions' / 'spoken_script_raw.txt').write_text(script, encoding='utf-8')
            (folder / 'captions' / 'spoken_script.txt').write_text(script, encoding='utf-8')
            job.update(spoken_script_raw=script, spoken_script=script,
                       tts_script_issues=['พบคำอังกฤษที่ควรตรวจคำอ่าน: AnotherBrand'],
                       voice_status='ready', voice_path='voice/paid.mp3', voice_job_id='paid-id')
            manager._save_manifest_file(folder / 'job.json', job)
            saved, actual = manager.spoken_script(job['id'])
            self.assertEqual(actual, script)
            self.assertEqual(saved['tts_script_issues'], [])
            self.assertEqual(saved['voice_status'], 'ready')
            self.assertEqual(saved['voice_path'], 'voice/paid.mp3')
            self.assertEqual(saved['voice_job_id'], 'paid-id')


if __name__ == '__main__':
    unittest.main()
