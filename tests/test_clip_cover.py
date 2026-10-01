import copy
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.clip_cover import (normalize_cover, cover_settings, compose_cover,
                             ensure_cover, image_choices, fallback_headline, ClipCoverRenderer)
from core.video_library import VideoLibrary


ROOT = Path(__file__).resolve().parents[1]


class ClipCoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'workspace' / 'stories' / 'STORY-COVER'
        (self.folder / 'generated').mkdir(parents=True)
        (self.folder / 'videos').mkdir()
        (self.folder / 'videos' / 'final.mp4').write_bytes(b'unchanged final')
        for i, color in enumerate(('red', 'blue'), 1):
            Image.new('RGB', (480, 720), color).save(self.folder / 'generated' / f'{i}.png')
        self.manifest = dict(id='STORY-COVER', job_type='story_short', video_title='ใครอยู่หลังประตู',
                             generated_images=['generated/1.png', 'generated/2.png'],
                             video_status='ready', status='ready', video_path='videos/final.mp4',
                             narration_script='บทเดิมไม่เปลี่ยน', updated_at='2026-09-08T10:00:00')
        self.path = self.folder / 'job.json'
        self.path.write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_optional_malformed_cover_never_fails(self):
        for value in (None, [], 'invalid', {}, {'headline': []}, {'headline': 'x' * 61},
                      {'scene_index': 'oops', 'theme': []}):
            self.assertIsInstance(normalize_cover(value), dict)

    def test_bounds_and_dedup(self):
        result = normalize_cover(dict(headline=' ใครอยู่ข้างใน ', alternatives=['ใครอยู่ข้างใน', 'ประตูบานนั้น', 'ความลับ'], scene_index=500,
                                      emphasis='สิ่งที่ไม่มี', position='outside', theme='invalid'))
        self.assertEqual(result['headline'], 'ใครอยู่ข้างใน')
        self.assertEqual(len(result['alternatives']), 2)
        self.assertEqual(result['scene_index'], 50)
        self.assertEqual(result['emphasis'], '')

    def test_invalid_optional_scene_defaults_to_real_image(self):
        self.manifest['cover'] = dict(headline='ใครอยู่ข้างใน', scene_index=40)
        settings = cover_settings(self.manifest, image_choices(self.folder, self.manifest))
        self.assertEqual(settings['scene_index'], 1)

    def test_no_path_escape(self):
        self.manifest['generated_images'] = ['../../outside.png', str(ROOT / 'AGENTS.md')]
        self.assertEqual(image_choices(self.folder, self.manifest), [])
        with self.assertRaises(ValueError): compose_cover(ROOT, self.folder, self.manifest)

    def test_render_uses_selected_scene_and_preserves_source(self):
        before = (self.folder / 'generated/2.png').read_bytes()
        self.manifest['cover'] = dict(headline='ใครอยู่ข้างใน', scene_index=2)
        change = compose_cover(ROOT, self.folder, self.manifest)
        with Image.open(self.folder / change['cover_path']) as image:
            self.assertEqual(image.size, (1080, 1920))
            self.assertGreater(image.getpixel((500, 500))[2], 240)
        self.assertEqual((self.folder / 'generated/2.png').read_bytes(), before)

    def test_landscape_has_real_text_and_correct_size(self):
        self.manifest['long_video'] = {'duration_minutes': 3}
        change = compose_cover(ROOT, self.folder, self.manifest)
        with Image.open(self.folder / change['cover_path']) as image:
            self.assertEqual(image.size, (1920, 1080))
            self.assertGreater(len(image.getcolors(3000000)), 20)

    def test_existing_cover_not_replaced(self):
        self.manifest.update(compose_cover(ROOT, self.folder, self.manifest))
        before = (self.folder / self.manifest['cover_path']).read_bytes()
        self.assertEqual(ensure_cover(ROOT, self.folder, self.manifest), {})
        self.assertEqual((self.folder / self.manifest['cover_path']).read_bytes(), before)

    def test_fallback_is_short_without_cutting_words(self):
        self.assertEqual(fallback_headline({'job_type': 'story_short', 'video_title': 'ก' * 120}), 'เรื่องนี้น่าติดตาม')
        self.assertEqual(fallback_headline({'video_title': 'ประตูบานนั้น: ' + 'ก' * 100}), 'ประตูบานนั้น')

    def test_preview_no_file_or_manifest_write(self):
        before = self.path.read_bytes()
        library = VideoLibrary(self.root)
        editor = library.cover_editor('story:STORY-COVER')
        result = library.compose_library_cover(editor['item_id'], editor['settings'], editor['revision'])
        self.assertTrue(result['preview'].startswith('data:image/jpeg;base64,'))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.folder / 'covers').exists())

    def test_save_cover_only_and_stale_editor_rejected(self):
        library = VideoLibrary(self.root)
        editor = library.cover_editor('story:STORY-COVER')
        result = library.compose_library_cover(editor['item_id'], editor['settings'], editor['revision'], save=True)
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        for key, value in self.manifest.items(): self.assertEqual(saved[key], value)
        first = (self.folder / result['cover_path']).read_bytes()
        with self.assertRaisesRegex(ValueError, 'หน้าต่างอื่น'):
            library.compose_library_cover(editor['item_id'], editor['settings'], '', save=True)
        settings = copy.deepcopy(editor['settings']); settings['headline'] = 'ความลับหลังประตู'
        second = library.compose_library_cover(editor['item_id'], settings, result['revision'], save=True)
        self.assertNotEqual(result['cover_path'], second['cover_path'])
        self.assertEqual((self.folder / result['cover_path']).read_bytes(), first)
        self.assertEqual((self.folder / 'videos/final.mp4').read_bytes(), b'unchanged final')

    def test_user_overlong_headline_rejected_without_write(self):
        library = VideoLibrary(self.root)
        editor = library.cover_editor('story:STORY-COVER')
        editor['settings']['headline'] = 'ยาว' * 100
        with self.assertRaises(ValueError):
            library.compose_library_cover(editor['item_id'], editor['settings'], '', save=True)
        self.assertFalse((self.folder / 'covers').exists())

    def test_two_lines_keep_whole_words(self):
        from PIL import ImageDraw
        renderer = ClipCoverRenderer(ROOT)
        font = renderer.font(90)
        draw = ImageDraw.Draw(Image.new('RGB', (1080, 1920)))
        text = 'ความลับหลังประตูบานนั้น'
        lines = renderer.wrap(text, font, 880, draw)
        self.assertIsNotNone(lines)
        self.assertLessEqual(len(lines), 2)
        self.assertEqual(''.join(lines), text)

    def test_story_checkpoint_preserves_optional_cover_without_changing_plan(self):
        from core.story_manager import StoryManager
        manager = StoryManager(self.root)
        job = manager.create('ประตูแห่งความลับ', scene_count=6)
        job.pop('story_content_contract', None)
        manager._save(job)
        analysis = dict(job_id=job['id'], video_title='ประตูแห่งความลับ', narration_script='เรื่องเดิม',
                        scene_prompts=['ฉากเดิม'] * 6, scene_narrations=['บทเดิม'] * 6,
                        scene_durations=[4] * 6, cover=dict(headline='ใครอยู่หลังประตู?', scene_index=3))
        manager.save_analysis_checkpoint(job['id'], analysis)
        restored = manager.load_analysis_checkpoint(job['id'])
        self.assertEqual(restored['cover']['scene_index'], 3)
        self.assertEqual(restored['cover']['headline'], 'ใครอยู่หลังประตู?')
        self.assertEqual(restored['scene_prompts'], analysis['scene_prompts'])
        self.assertEqual(restored['narration_script'], analysis['narration_script'])
        package = manager.plugin_request(job['id'])
        self.assertIn('ข้อมูลเสริมปกคลิป', package['prompt'])
        self.assertNotIn('cover', package['request']['required_fields'])

    def test_corrupt_selected_image_uses_existing_valid_scene_for_automatic_cover(self):
        (self.folder / 'generated/2.png').write_bytes(b'broken')
        self.manifest['cover'] = dict(headline='ประตูบานนั้น', scene_index=2)
        result = compose_cover(ROOT, self.folder, self.manifest)
        self.assertEqual(result['cover_settings']['scene_index'], 1)


if __name__ == '__main__': unittest.main()
