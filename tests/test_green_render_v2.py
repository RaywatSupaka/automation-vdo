import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core.green_cache import cycle_key, restore_cycle, remember_cycle
from core.green_progress import read_progress, progress_notice
from core.cancellable_process import OperationCancelled
from tests import test_green_screen as fixtures


class GreenCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'cycle.mkv'
        self.source.write_bytes(b'fake alpha stream')
        self.key = 'a' * 64

    def test_keys_bind_order_parameters_resolution_fps_duration_and_renderer(self):
        base = cycle_key({'clips': ['a', 'b'], 'opacity': .5}, 720, 1280, 60, [1, 2])
        for values in [({'clips': ['b', 'a'], 'opacity': .5}, 720, 1280, 60, [1, 2]),
                       ({'clips': ['a', 'b'], 'opacity': .7}, 720, 1280, 60, [1, 2]),
                       ({'clips': ['a', 'b'], 'opacity': .5}, 360, 640, 60, [1, 2]),
                       ({'clips': ['a', 'b'], 'opacity': .5}, 720, 1280, 30, [1, 2]),
                       ({'clips': ['a', 'b'], 'opacity': .5}, 720, 1280, 60, [1, 1])]:
            self.assertNotEqual(base, cycle_key(*values))

    def test_cache_hit_corruption_and_cancellation(self):
        self.assertTrue(remember_cycle(self.root, self.key, self.source))
        target = self.root / 'copy.mkv'
        self.assertTrue(restore_cycle(self.root, self.key, target))
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        target.unlink()
        cached = self.root / 'workspace/cache/screenfx-v2' / (self.key + '.mkv')
        cached.write_bytes(b'corrupt')
        self.assertFalse(restore_cycle(self.root, self.key, target))
        event = threading.Event(); event.set()
        with self.assertRaises(OperationCancelled): restore_cycle(self.root, self.key, target, event)
        with self.assertRaises(OperationCancelled): remember_cycle(self.root, self.key, self.source, event)

    def test_bounded_eviction_only_disposable_cache_and_missing_cache_optional(self):
        self.assertTrue(remember_cycle(self.root, self.key, self.source))
        folder = self.root / 'workspace/cache/screenfx-v2'
        protected = folder / 'original-user-file.mkv'; protected.write_bytes(b'keep')
        orphan = folder / ('f'*64 + '-' + 'e'*32 + '.tmp'); orphan.write_bytes(b'abandoned cycle')
        with patch('core.green_cache.MAX_CACHE_BYTES', self.source.stat().st_size):
            self.assertTrue(remember_cycle(self.root, 'b' * 64, self.source))
        self.assertFalse(orphan.exists())
        self.assertFalse((folder / (self.key + '.mkv')).exists())
        self.assertEqual(protected.read_bytes(), b'keep')
        with patch('core.green_cache.MAX_ENTRY_BYTES', 1):
            self.assertFalse(remember_cycle(self.root, 'c' * 64, self.source))
        with patch('core.green_cache._paths', side_effect=PermissionError):
            self.assertFalse(restore_cycle(self.root, self.key, self.root / 'absent.mkv'))
            self.assertFalse(remember_cycle(self.root, self.key, self.source))

    def test_progress_uses_completed_real_records_and_never_claims_saved(self):
        path = self.root / 'progress.txt'
        self.assertIsNone(read_progress(path, 10))

        path.write_text('frame=120\nout_time_us=4000000\nspeed=0.8x\nprogress=continue\nframe=150\n')
        self.assertEqual(read_progress(path, 10), {'frame': 120, 'seconds': 4., 'percent': 40, 'speed': .8})
        messages = []
        progress_notice(path, 10, 'test', messages.append)(12)
        self.assertIn('40%', messages[-1]); self.assertIn('เฟรม 120', messages[-1])
        path.write_text('frame=300\nout_time_us=10000000\nspeed=1.0x\nprogress=end\n')
        self.assertEqual(read_progress(path, 10)['percent'], 99)
        path.write_text('frame=1\nout_time_us=nan\nspeed=nanx\nprogress=end\n')
        self.assertIsNone(read_progress(path, 10))

    def test_malformed_cache_index_is_disposable_not_a_render_error(self):
        from core.atomic_json import AtomicJsonFile
        self.assertTrue(remember_cycle(self.root, self.key, self.source))
        index = AtomicJsonFile(self.root / 'workspace/cache/screenfx-v2/index.json')
        for invalid in ([], {self.key: 'bad'}, {self.key: {'size': 'bad'}}):
            index.write(invalid)
            self.assertFalse(restore_cycle(self.root, self.key, self.root/'missing.mkv'))
            self.assertTrue(remember_cycle(self.root, self.key, self.source))


class GreenRenderV2Tests(fixtures.GreenTests):
    # Inherit helpers only; existing test methods are suppressed below.
    def test_single_pass_uses_no_alpha_intermediate_and_preserves_fps(self):
        from core.green_screen import render_green
        from core.video_intro import inspect_video
        options = self.options()
        base = self.video('base.mp4', duration=2)
        messages = []
        with patch('core.green_screen.remember_cycle', side_effect=AssertionError('single file must not cache')):
            output, plan = render_green(self.root, base, self.root/'final.mp4', options, progress=messages.append)
        self.assertEqual(plan['strategy'], 'single_pass')
        self.assertEqual(plan['prepare_seconds'], 0)
        self.assertEqual(inspect_video(output)['fps'], inspect_video(base)['fps'])
        self.assertIn('100%', messages[-1])
        self.assertTrue(any('เฟรม' in m for m in messages))
        self.assertFalse(list(self.root.glob('green-render-*')))

    def test_multifile_reuses_validated_cycle_and_invalidates_changed_settings(self):
        from core.green_screen import render_green
        options = self.options(3)
        base = self.video('base.mp4', duration=4)
        a, first = render_green(self.root, base, self.root/'a.mp4', options)
        b, second = render_green(self.root, base, self.root/'b.mp4', options)
        self.assertFalse(first['cache_hit']); self.assertTrue(second['cache_hit'])
        self.assertEqual(a.read_bytes(), b.read_bytes())
        _, changed = render_green(self.root, base, self.root/'c.mp4', {**options, 'opacity': .3})
        self.assertFalse(changed['cache_hit'])
        self.assertFalse(list(self.root.glob('green-render-*')))

    def test_short_single_effect_repeated_many_times_uses_one_cached_cycle(self):
        from core.green_screen import render_green
        options = self.options()
        base = self.video('long-base.mp4', duration=4)
        _, first = render_green(self.root, base, self.root/'one.mp4', options)
        output, second = render_green(self.root, base, self.root/'two.mp4', options)
        self.assertEqual(first['strategy'], 'cached_cycle')
        self.assertTrue(second['cache_hit'])
        for second in (.5, 1.5, 2.5, 3.5):
            self.assertGreater(self.pixel(output, second)[0], 180)

    def test_real_product_progress_is_forwarded_without_changing_publication(self):
        from core.atomic_json import AtomicJsonFile
        from core.green_screen import finish_product_green
        from core.product_manager import ProductManager
        products = ProductManager(self.root)
        folder = products.root/'JOB-PROGRESS'; (folder/'videos').mkdir(parents=True)
        source = self.video('source.mp4', duration=1)
        (folder/'videos/base.mp4').write_bytes(source.read_bytes())
        AtomicJsonFile(folder/'job.json').write({'id': 'JOB-PROGRESS', 'video_path': 'videos/base.mp4',
                                                'green_options': self.options()})
        notices = []
        output = finish_product_green(products, 'JOB-PROGRESS', self.root, progress=notices.append)
        self.assertTrue(output.is_file())
        self.assertIn('100%', notices[-1])
        self.assertEqual(products.get_job('JOB-PROGRESS')['green_result']['renderer_version'], 2)

    def test_cancel_mid_render_retains_previous_final_and_reaps_process(self):
        from core.green_screen import render_green
        options = self.options()
        base = self.video('base.mp4', duration=2)
        output = self.root/'old.mp4'; output.write_bytes(b'previous final')
        event = threading.Event()
        with self.assertRaises(OperationCancelled):
            render_green(self.root, base, output, options, cancel_event=event, progress=lambda _: event.set())
        self.assertEqual(output.read_bytes(), b'previous final')
        self.assertFalse(list(self.root.glob('green-render-*')))


for name in fixtures.GreenTests.__dict__:
    if name.startswith('test_'):
        setattr(GreenRenderV2Tests, name, None)

if __name__ == '__main__': unittest.main()
