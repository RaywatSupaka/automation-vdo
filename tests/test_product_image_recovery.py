import base64
import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from core.product_image_recovery import ProductImageRecovery


def encoded(color):
    data = io.BytesIO()
    Image.new('RGB', (320, 500), color).save(data, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(data.getvalue()).decode()


class Manager:
    def __init__(self, root):
        self.root = Path(root)
        self.job = {'id': 'JOB-TEST', 'source_images': ['original/a.png']}
        folder = self.root / 'JOB-TEST'
        (folder / 'original').mkdir(parents=True)
        (folder / 'generated').mkdir()
        Image.new('RGB', (200, 200), 'white').save(folder / 'original/a.png')

    def get_job(self, job_id): return self.job

    def save_partial_image(self, job_id, index, image):
        (self.root / job_id / 'generated' / f'selling_image_{index:02d}.png').write_bytes(base64.b64decode(image.split(',')[-1]))


class RecoveryTests(unittest.TestCase):
    def test_product_scene_indexes_must_match_image_slots(self):
        for index in (1, '2', True):
            analysis = {**self.analysis, 'flow_shot_prompts': [{'scene_index':1},{'scene_index':index},{'scene_index':3}]}
            with self.assertRaisesRegex(ValueError, 'scene_index'):
                self.r.start(analysis)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = Manager(self.temp.name)
        self.r = ProductImageRecovery(self.manager, 'JOB-TEST')
        self.analysis = {'job_id': 'JOB-TEST', 'image_prompts': ['one', 'two', 'three']}
        self.rev = self.r.start(self.analysis)['revision']

    def reserve(self, index=1, donor=0, run='RUN-1'):
        return self.r.reserve(self.rev, index, run, f'request-{index}-{donor}', donor)

    def finish(self, reservation, index=1, outcome='failed', image=None, run='RUN-1'):
        return self.r.finish(self.rev, index, run, reservation['token'], outcome, image)

    def test_pending_reservation_survives_restart_no_resubmit(self):
        self.reserve()
        other = ProductImageRecovery(self.manager, 'JOB-TEST')
        other.start(self.analysis)
        with self.assertRaises(ValueError): other.reserve(self.rev, 1, 'RUN-2', 'other')
        with self.assertRaises(ValueError): other.reserve(self.rev, 2, 'RUN-2', 'other-slot')

    def test_failed_slot_uses_initial_donor_once(self):
        first = self.reserve(1)
        self.finish(first)
        donor = self.reserve(2)
        self.finish(donor, 2, 'succeeded', encoded('red'))
        recovery = self.reserve(1, 2)
        state = self.finish(recovery, 1, 'succeeded', encoded('blue'))
        self.assertEqual(state['slots']['1']['origin'], 'recovered_from_reference')
        with self.assertRaises(ValueError): self.reserve(1, 2)

    def test_policy_uncertain_download_and_blocked_never_retry(self):
        for status in ['policy_blocked', 'uncertain', 'download_pending', 'blocked']:
            with self.subTest(status=status):
                self.r.store.write({})
                self.r.start(self.analysis)
                reservation = self.reserve()
                self.finish(reservation, outcome=status)
                with self.assertRaises(ValueError): self.reserve()

    def test_revision_change_keeps_old_budget(self):
        self.reserve()
        with self.assertRaises(ValueError): self.r.start(dict(self.analysis, image_prompts=['other', 'two', 'three']))
        self.assertEqual(self.r.state()['slots']['1']['attempts'], 1)

    def test_wrong_run_token_and_cancelled_rejected(self):
        reservation = self.reserve()
        with self.assertRaises(ValueError): self.finish(reservation, run='RUN-OTHER')
        self.manager.job['automation_status'] = 'cancelled'
        with self.assertRaises(ValueError): self.finish(reservation)

    def test_recovered_donor_cannot_chain(self):
        a = self.reserve(1); self.finish(a)
        b = self.reserve(2); self.finish(b, 2, 'succeeded', encoded('red'))
        a = self.reserve(1, 2); self.finish(a, 1, 'succeeded', encoded('blue'))
        c = self.reserve(3); self.finish(c, 3)
        with self.assertRaises(ValueError): self.reserve(3, 1)

    def test_duplicate_result_does_not_count_success(self):
        a = self.reserve(1); self.finish(a, 1, 'succeeded', encoded('red'))
        b = self.reserve(2)
        state = self.finish(b, 2, 'succeeded', encoded('red'))
        self.assertEqual(state['slots']['2']['status'], 'failed')
        self.assertFalse((self.r.folder / 'generated/selling_image_02.png').exists())

    def test_corrupt_donor_rejected(self):
        a = self.reserve(1); self.finish(a, 1, 'succeeded', encoded('red'))
        b = self.reserve(2); self.finish(b, 2)
        (self.r.folder / 'generated/selling_image_01.png').write_bytes(b'broken')
        with self.assertRaises(Exception): self.reserve(2, 1)

    def test_image_metadata_change_does_not_make_duplicate_new(self):
        from PIL.PngImagePlugin import PngInfo
        a = self.reserve(1); self.finish(a, 1, 'succeeded', encoded('red'))
        meta = PngInfo(); meta.add_text('attempt', 'new attempt')
        output = io.BytesIO()
        Image.new('RGB', (320, 500), 'red').save(output, format='PNG', pnginfo=meta)
        b = self.reserve(2)
        result = self.finish(b, 2, 'succeeded', base64.b64encode(output.getvalue()).decode())
        self.assertEqual(result['slots']['2']['reason'], 'duplicate_image')

    def test_square_result_is_failed_not_counted_as_completed(self):
        output = io.BytesIO(); Image.new('RGB', (500, 500), 'red').save(output, format='PNG')
        result = self.finish(self.reserve(), 1, 'succeeded', base64.b64encode(output.getvalue()).decode())
        self.assertEqual(result['slots']['1']['reason'], 'invalid_image_dimensions')
