import io
import json
import logging
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.video_intro import IntroLibrary, MAX_INTRO_BYTES
from core.audio_mixer import AudioMixer
from core.cancellable_process import run_cancellable


class IntroBrowserUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='intro-upload-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = IntroLibrary(self.root)

    def test_stream_validation_and_incomplete_upload_preserve_settings(self):
        for name, size, data in [('x.png', 1, b'x'), ('../x.mp4', 1, b'x'),
                                 ('C:\\x.mp4', 1, b'x'), ('x.mp4', 0, b''),
                                 ('x.mp4', MAX_INTRO_BYTES+1, b''), ('x.mp4', 5, b'x')]:
            with self.subTest(name=name, size=size), self.assertRaises(ValueError):
                self.library.import_stream(io.BytesIO(data), size, name)
        self.assertEqual(self.library.state()['assets'], [])

    def test_separate_defaults_persist_and_do_not_change_job_options(self):
        # Existing global enabled keeps legacy Long behavior; new targets are
        # defaults only, never copied into an already-created job/queue item.
        with patch.object(self.library, 'validate') as validate:
            for story, drama in [(True,False),(False,True),(True,True),(False,False)]:
                settings={'enabled':False,'file':'','targets':{'story':story,'drama':drama}}
                self.library.save(settings)
                self.assertEqual(IntroLibrary(self.root).state()['settings'],settings)
                self.assertEqual(validate.call_args.args[0]['enabled'],story or drama)
        with self.assertRaises(ValueError):
            self.library.save({'enabled':False,'file':'','targets':{'story':True,'drama':False}})
        for targets in [None, {'story':True}, {'story':'yes','drama':False}]:
            with self.assertRaises(ValueError):
                self.library.save({'enabled':False,'file':'','targets':targets})
        self.library.store.write({'settings':{'enabled':True,'file':'assets/intro/'+('a'*64)+'.mp4'}})
        legacy=self.library.state()['settings']
        self.assertTrue(legacy['enabled'])
        self.assertNotIn('targets',legacy)  # UI maps old enabled to both boxes.

    def test_http_upload_same_origin_no_desktop_queue_and_atomic_import(self):
        desktop = Mock(side_effect=AssertionError('must not enter Tk queue'))
        bridge = LocalBridge('127.0.0.1', 0, ProductManager(self.root), logging.getLogger('intro-upload'),
                             desktop_action=desktop, desktop_intro_library=self.library).start()
        self.addCleanup(bridge.stop)
        base = f'http://127.0.0.1:{bridge.server.server_address[1]}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(origin, name='intro.mp4'):
            return urllib.request.Request(base+'/api/desktop/intro-upload', data=b'fixture-video',
                headers={'Origin':origin, 'Content-Type':'application/octet-stream', 'X-File-Name':name})
        with self.assertRaises(urllib.error.HTTPError) as blocked:
            opener.open(request('https://outside.example'), timeout=5)
        self.assertEqual(blocked.exception.code, 403)
        blocked.exception.close()
        info = {'duration':2., 'width':192, 'height':108, 'fps':30., 'has_audio':True}
        with patch('core.video_intro.inspect_video', return_value=info):
            for _ in range(2):
                with opener.open(request(base, '%E0%B8%9B%E0%B8%81.mp4'), timeout=5) as response:
                    result = json.load(response)
                self.assertTrue(result['ok'])
                self.assertEqual(result['asset']['name'], 'ปก.mp4')
            self.assertEqual(len(self.library.state()['assets']), 1)
            self.assertEqual((self.root/result['asset']['file']).read_bytes(), b'fixture-video')
        with patch('core.video_intro.inspect_video', side_effect=ValueError('invalid video')):
            with self.assertRaises(urllib.error.HTTPError) as invalid:
                opener.open(request(base), timeout=5)
            invalid.exception.close()
        self.assertEqual(len(self.library.state()['assets']), 1)
        desktop.assert_not_called()

    def test_intro_settings_skip_ui_queue_and_legacy_picker_rejected(self):
        from ui.main_window import MainWindow
        app = SimpleNamespace(cfg={}, _desktop_request=Mock(side_effect=AssertionError('UI queue blocked')))
        with patch('ui.video_intro.ROOT', self.root):
            result = MainWindow._desktop_action_request(app, 'intro_status', {})
            self.assertTrue(result['ok'])
            saved = MainWindow._desktop_action_request(app, 'intro_save', {'settings':{'enabled':False,'file':''}})
            self.assertFalse(saved['settings']['enabled'])
            with self.assertRaises(ValueError):
                MainWindow._desktop_action_request(app, 'intro_choose_file', {})
        app._desktop_request.assert_not_called()

    def test_real_video_upload_is_playable_and_keeps_default_off(self):
        source = self.root/'real.mp4'
        command = [str(AudioMixer().ffmpeg), '-v', 'error', '-y', '-f', 'lavfi',
                   '-i', 'color=c=blue:s=192x108:r=24:d=1', '-c:v', 'libx264',
                   '-pix_fmt', 'yuv420p', str(source)]
        self.assertEqual(run_cancellable(command, timeout=20).returncode, 0)
        original = source.read_bytes()
        bridge = LocalBridge('127.0.0.1', 0, ProductManager(self.root), logging.getLogger('intro-real'),
                             desktop_intro_library=self.library).start()
        self.addCleanup(bridge.stop)
        request = urllib.request.Request(
            f'http://127.0.0.1:{bridge.server.server_address[1]}/api/desktop/intro-upload',
            data=original, headers={'Content-Type':'application/octet-stream', 'X-File-Name':'real.mp4'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=15) as response:
            result = json.load(response)
        self.assertTrue(result['ok'])
        self.assertEqual(result['asset']['width'], 192)
        self.assertAlmostEqual(result['asset']['duration'], 1., places=1)
        self.assertEqual((self.root/result['asset']['file']).read_bytes(), original)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(result['settings']['enabled'])


if __name__ == '__main__':
    unittest.main()
