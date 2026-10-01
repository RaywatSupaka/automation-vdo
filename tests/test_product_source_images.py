import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from core.product_source_images import inspect_source_image, select_source_images


class SourceImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def save(self, name, mode, color, box=None):
        image = Image.new(mode, (600, 600), color)
        if box: ImageDraw.Draw(image).rectangle(box, fill=(50, 220, 140, 255))
        path = self.root / name
        image.save(path)
        return path

    def test_user_confirmed_overlay(self):
        path = Path(r'C:\Users\keera\AppData\Local\Temp\codex-clipboard-3cb7aeaf-a2e7-4496-8a28-a54145fafc35.png')
        if not path.is_file(): self.skipTest('User fixture not present')
        self.assertEqual(inspect_source_image(path)['decision'], 'exclude')

    def test_transparent_real_product_kept(self):
        path = self.save('cutout.png', 'RGBA', (0, 0, 0, 0), (200, 60, 400, 530))
        self.assertEqual(inspect_source_image(path)['decision'], 'accept')

    def test_black_product_kept(self):
        self.assertEqual(inspect_source_image(self.save('black.png', 'RGB', (0, 0, 0)))['decision'], 'accept')

    def test_opaque_promotion_baked_into_photo_kept(self):
        path = self.save('baked.png', 'RGBA', (200, 200, 200, 255), (0, 525, 400, 600))
        self.assertEqual(inspect_source_image(path)['decision'], 'accept')

    def test_sparse_edge_requires_independent_proof(self):
        path = self.save('edge.png', 'RGBA', (0, 0, 0, 0), (0, 525, 350, 599))
        self.assertEqual(inspect_source_image(path)['decision'], 'review')
        self.assertEqual(inspect_source_image(path, {'decorative_layer': True, 'overlaps_product': True})['decision'], 'exclude')

    def test_selection_non_destructive_duplicates_and_outside(self):
        self.save('one.png', 'RGB', (30, 50, 70))
        self.save('two.png', 'RGB', (30, 50, 70))
        accepted, decisions = select_source_images(self.root, ['one.png', 'two.png', '../outside.png'])
        self.assertEqual(accepted, ['one.png'])
        self.assertEqual(decisions[1]['reason'], 'duplicate_product_image')
        self.assertEqual(decisions[2]['decision'], 'review')
        self.assertTrue((self.root / 'two.png').exists())
