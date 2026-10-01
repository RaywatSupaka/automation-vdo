import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from core.video_library import VideoLibrary


class LibraryCompactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = VideoLibrary(self.root)

    def job(self, number=1):
        folder = self.root / 'workspace/stories' / f'STORY-{number}'
        (folder / 'videos').mkdir(parents=True)
        (folder / 'generated').mkdir()
        (folder / 'videos/final.mp4').write_bytes(b'video')
        manifest = dict(id=f'STORY-{number}', video_status='ready', video_path='videos/final.mp4',
                        video_title=f'Clip {number}', generated_images=['generated/scene.png'])
        (folder / 'job.json').write_text(json.dumps(manifest), encoding='utf-8')
        return folder

    def test_all_old_jobs_remain_searchable(self):
        for i in range(125): self.job(i)
        items = self.library.list_items()
        self.assertEqual(len(items),125)
        self.assertIn('story:STORY-124',{item['item_id'] for item in items})
        source = (Path(__file__).resolve().parents[1]/'ui/main_window.py').read_text(encoding='utf-8')
        body = source.split('def _desktop_library_rows(self):',1)[1].split('def _desktop_log_lines',1)[0]
        self.assertNotIn('[:100]',body)
        self.assertNotIn('item_detail(',body)

    def test_single_item_detail_does_not_scan_library(self):
        self.job()
        with patch.object(self.library,'list_items',side_effect=AssertionError('must not scan')):
            self.assertEqual(self.library.item_detail('story:STORY-1')['job_id'],'STORY-1')

    def test_untrusted_identifier_cannot_escape_workspace(self):
        for item in ['story:../STORY-1','other:STORY-1','story:C:/file','story:STORY-1/../../file']:
            with self.assertRaises(ValueError): self.library.item_detail(item)

    def test_thumbnail_cache_is_small_reused_and_tracks_source(self):
        folder = self.job()
        source = folder / 'generated/scene.png'
        Image.new('RGB',(1080,1920),'red').save(source)
        original = source.read_bytes()
        target = Path(self.library.thumbnail('story:STORY-1'))
        self.assertEqual(target,Path(self.library.thumbnail('story:STORY-1')))
        with Image.open(target) as image:
            self.assertLessEqual(image.width,400); self.assertLessEqual(image.height,240)
        self.assertEqual(source.read_bytes(),original)
        Image.new('RGB',(1080,1920),'blue').save(source)
        self.assertNotEqual(target,Path(self.library.thumbnail('story:STORY-1')))
        self.assertTrue(target.is_file())


if __name__ == '__main__': unittest.main()
