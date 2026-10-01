import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import Mock
from core.presenter import PresenterManager
from core.atomic_json import AtomicJsonFile
from ui.presenter import PresenterMixin


class PresenterLibraryTests(unittest.TestCase):
    def test_actual_library_ui(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('presenter_library_ui_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = PresenterManager(self.temp.name)
        self.job = self.manager.create('Guide', 'A friendly guide')
        self.ident = self.job['id']

    def test_trash_restore_preserves_media_and_checkpoints(self):
        media = self.manager.folder(self.ident) / 'clips/take_01.mp4'
        media.write_bytes(b'original')
        self.manager.update(self.ident, clips={'1': 'clips/take_01.mp4'}, intents={'flow_1': 'owned'})
        self.manager.set_library_state(self.ident, 'trash')
        self.assertEqual(media.read_bytes(), b'original')
        self.assertEqual(self.manager.get(self.ident)['intents'], {'flow_1': 'owned'})
        self.manager.set_library_state(self.ident, 'visible')
        self.assertEqual(self.manager.get(self.ident)['clips'], {'1': 'clips/take_01.mp4'})

    def test_default_trash_blocked_but_hide_allowed(self):
        AtomicJsonFile(self.manager.root / 'defaults.json').write({'enabled': True, 'id': self.ident})
        with self.assertRaises(ValueError):
            self.manager.set_library_state(self.ident, 'trash')
        self.assertEqual(self.manager.set_library_state(self.ident, 'hidden')['library_state'], 'hidden')

    def test_running_blocked(self):
        self.manager.update(self.ident, status='running')
        with self.assertRaises(ValueError):
            self.manager.set_library_state(self.ident, 'trash')

    def test_referenced_job_and_queue_cannot_be_trashed(self):
        for relative in ('stories/STORY-EXAMPLE/job.json', 'story_batch_queue.json'):
            target = Path(self.temp.name) / 'workspace' / relative
            AtomicJsonFile(target).write({'options': {'presenter': {'enabled': True, 'id': self.ident}}})
            with self.assertRaises(ValueError):
                self.manager.set_library_state(self.ident, 'trash')
            self.manager.set_library_state(self.ident, 'hidden')
            self.assertEqual(AtomicJsonFile(target).read()['options']['presenter']['id'], self.ident)

    def test_corrupt_reference_manifest_fails_closed(self):
        target = Path(self.temp.name) / 'workspace/story_batch_queue.json'
        target.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.manager.set_library_state(self.ident, 'trash')

    def test_bad_state_and_id_rejected(self):
        for ident, state in [(self.ident, 'purge'), ('../elsewhere', 'trash'), ('PRESENTER-000000000000', 'trash')]:
            with self.assertRaises(ValueError):
                self.manager.set_library_state(ident, state)

    def test_adapter_requires_confirmation_and_idle_worker(self):
        app = PresenterMixin()
        app.presenters = self.manager
        with self.assertRaises(ValueError):
            app._presenter_action('presenter_library_state', {'id': self.ident, 'state': 'trash'})
        app._presenter_worker = Mock()
        app._presenter_worker.is_alive.return_value = True
        with self.assertRaises(ValueError):
            app._presenter_action('presenter_library_state', {'id': self.ident, 'state': 'trash', 'confirmed': True})
        app._presenter_worker.is_alive.return_value = False
        result = app._presenter_action('presenter_library_state', {'id': self.ident, 'state': 'trash', 'confirmed': True})
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
