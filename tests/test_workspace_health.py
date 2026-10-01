import json
import tempfile
import unittest
from pathlib import Path

from core.atomic_json import AtomicJsonFile, runtime_backup_path
from core.product_manager import ProductManager
from core.drama_series import DramaSeriesManager
from core.story_manager import StoryManager
from core.video_library import VideoLibrary
from core.workspace_health import resolve_workspace_issue_folder, scan_workspace_issues


class WorkspaceHealthTests(unittest.TestCase):
    def test_corrupt_job_remains_visible_as_issue_without_changing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            product = root / 'workspace' / 'products' / 'JOB-BROKEN'
            story = root / 'workspace' / 'stories' / 'STORY-BROKEN'
            series = root / 'workspace' / 'drama_series' / 'SERIES-BROKEN'
            for folder, filename in ((product, 'job.json'), (story, 'job.json'), (series, 'series.json')):
                folder.mkdir(parents=True)
                (folder / filename).write_text('{broken', encoding='utf-8')
            result = scan_workspace_issues(root)
            self.assertEqual(result['count'], 3)
            self.assertEqual({item['id'] for item in result['items']}, {'JOB-BROKEN', 'STORY-BROKEN', 'SERIES-BROKEN'})
            self.assertEqual(resolve_workspace_issue_folder(root, 'product', 'JOB-BROKEN'), product)
            with self.assertRaises(ValueError):
                resolve_workspace_issue_folder(root, 'product', '..\\outside')
            self.assertEqual((product / 'job.json').read_text(encoding='utf-8'), '{broken')

    def test_log_only_probe_folder_is_not_reported_as_a_lost_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'workspace' / 'stories' / 'STORY-GEMINI-TEST'
            (folder / 'logs').mkdir(parents=True)
            self.assertEqual(scan_workspace_issues(Path(temporary), new_folder_grace_seconds=0)['count'], 0)

    def test_valid_backup_stays_read_only_during_list_and_library_poll(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'workspace' / 'stories' / 'STORY-BACKUP'
            folder.mkdir(parents=True)
            manifest = folder / 'job.json'
            store = AtomicJsonFile(manifest, backup_path=runtime_backup_path(root, manifest))
            store.write({'id': 'STORY-BACKUP', 'created_at': '2026-09-24T00:00:00'})
            manifest.write_text('{broken', encoding='utf-8')
            self.assertEqual(StoryManager(root).list_jobs()[0]['id'], 'STORY-BACKUP')
            VideoLibrary(root).list_items()
            self.assertEqual(scan_workspace_issues(root)['count'], 0)
            self.assertEqual(manifest.read_text(encoding='utf-8'), '{broken')
            manifest.unlink()
            self.assertEqual(StoryManager(root).list_jobs()[0]['id'], 'STORY-BACKUP')
            self.assertEqual(scan_workspace_issues(root)['count'], 0)
            self.assertFalse(manifest.exists())
            self.assertEqual(StoryManager(root).get('STORY-BACKUP')['id'], 'STORY-BACKUP')
            self.assertTrue(manifest.is_file())  # Explicit detail restores the valid backup.

    def test_product_list_and_detail_do_not_rewrite_legacy_job_or_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = ProductManager(root)
            folder = manager.root / 'JOB-READ-ONLY'
            folder.mkdir(parents=True)
            manifest = folder / 'job.json'
            request = folder / 'ai_request.json'
            saved = {'id': 'JOB-READ-ONLY', 'video_ai_provider': 'meta', 'product_name': 'เดิม',
                     'created_at': '2026-09-01T00:00:00', 'updated_at': '2026-09-01T00:00:00'}
            manifest.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
            request.write_text('{"schema_version":1,"prompt":"original"}', encoding='utf-8')
            original_manifest, original_request = manifest.read_bytes(), request.read_bytes()
            self.assertEqual(manager.list_jobs()[0]['video_ai_provider'], 'flow')
            self.assertEqual(manager.get_job('JOB-READ-ONLY')['video_ai_provider'], 'flow')
            self.assertEqual(manifest.read_bytes(), original_manifest)
            self.assertEqual(request.read_bytes(), original_request)

    def test_missing_primary_is_listed_from_existing_product_and_series_backups(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            product = ProductManager(root)
            drama = DramaSeriesManager(root)
            for folder, filename, value in (
                (product.root / 'JOB-BACKUP', 'job.json', {'id': 'JOB-BACKUP', 'created_at': '2026-09-24T00:00:00'}),
                (drama.root / 'SERIES-BACKUP', 'series.json', {'id': 'SERIES-BACKUP', 'created_at': '2026-09-24T00:00:00', 'episodes': []}),
            ):
                folder.mkdir(parents=True)
                manifest = folder / filename
                store = AtomicJsonFile(manifest, backup_path=runtime_backup_path(root, manifest))
                store.write(value)
                manifest.unlink()
            self.assertEqual(product.list_jobs()[0]['id'], 'JOB-BACKUP')
            self.assertEqual(drama.list_series()[0]['id'], 'SERIES-BACKUP')
            self.assertEqual(scan_workspace_issues(root)['count'], 0)
            self.assertFalse((product.root / 'JOB-BACKUP' / 'job.json').exists())
            self.assertEqual(product.get_job('JOB-BACKUP')['id'], 'JOB-BACKUP')
            self.assertEqual(drama.get('SERIES-BACKUP')['id'], 'SERIES-BACKUP')
            self.assertTrue((product.root / 'JOB-BACKUP' / 'job.json').is_file())


if __name__ == '__main__':
    unittest.main()
