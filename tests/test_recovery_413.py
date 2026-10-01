import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Recovery413Tests(unittest.TestCase):
    def test_native_stream_and_fresh_scene_transaction(self):
        result = subprocess.run(['node', 'tests/recovery_413.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=35)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"ok":true', result.stdout)

    def test_desktop_declares_new_recovery_without_changing_user_jobs(self):
        import tempfile
        from core.story_manager import StoryManager
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create('แมวกับต้นไม้', scene_count=6)
            package = manager.plugin_request(job['id'])
            self.assertEqual(package['browser_recovery']['version'], 1)
            self.assertEqual(package['browser_recovery']['check_after_ms'], 60000)
            self.assertEqual(package['browser_recovery']['image_post_refresh_redo'],
                             {'version': 1, 'stable_check_ms': 30000, 'min_stable_samples': 3})
