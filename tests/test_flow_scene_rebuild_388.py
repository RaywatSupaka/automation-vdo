import subprocess
import unittest
from pathlib import Path
from core.atomic_json import AtomicJsonFile
import test_flow_replacement as base


class FlowSceneRebuildTests(unittest.TestCase):
    """Real replacement ledger with synthetic media only; never touches user jobs."""

    setUp = base.FlowReplacementTests.setUp
    image = base.FlowReplacementTests.image
    act = base.FlowReplacementTests.act

    def proof(self, failure, request=None):
        store = AtomicJsonFile(self.folder/'prompts/flow_recovery.json')
        data = store.read({'scenes': {'1': []}})
        data['scenes']['1'].append(dict(run_id=self.body['run_id'], fingerprint='fp', reason='audio generation failed',
                                      request_id=request or self.body['request_id'], failure_id=failure))
        store.write(data)

    def ready(self, color):
        self.act('image', image=self.image(color))
        self.act('ready', candidate=dict(prompt=f'Vertical 9:16. The product sits beside a {color} background with a slow camera move. All spoken dialogue must be in Thai only.',
                 needs_review=False, reference_compatible=True, material_change=False))

    def test_product_four_confirmed_failures_rebuild_and_preserve(self):
        self.job['id'] = 'JOB-TEST'
        original = (self.folder/'generated/scene_01.png').read_bytes()
        previous = ''
        for index, color in enumerate(['blue', 'green', 'yellow', 'purple'], 1):
            self.body.update(rebuild_scene=True, previous_request_id=previous,
                             request_id=f'{index:08x}-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
            self.proof(f'{index}:fp')
            row = self.act('begin')['replacement']
            self.assertTrue(row['rebuild_scene'])
            self.assertFalse(row['revise_story'])
            self.assertEqual(self.act('begin')['replacement'], row)
            self.ready(color)
            previous = self.body['request_id']
        data = AtomicJsonFile(self.folder/'prompts/flow_replacement.json').read({})
        self.assertEqual(len(data['history']['1']), 3)
        self.assertEqual(len(list((self.folder/'generated').glob('recovery-*.png'))), 4)
        self.assertEqual((self.folder/'generated/scene_01.png').read_bytes(), original)
        self.assertEqual(self.job['scene_narrations'], ['Original narration'])
        self.assertEqual(len(self.act('begin')['context']['previous_visuals']), 3)

    def test_repeat_failure_pending_and_wrong_owner_cannot_rotate(self):
        self.body['rebuild_scene'] = True
        self.proof('1:fp'); self.act('begin')
        first = self.body['request_id']
        self.body.update(request_id='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', previous_request_id=first)
        self.proof('2:fp')
        with self.assertRaises(ValueError): self.act('begin')  # original image still pending
        self.body['request_id'] = first; self.ready('blue')
        self.body['request_id'] = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
        self.proof('1:fp')
        with self.assertRaises(ValueError): self.act('begin')
        self.proof('2:fp'); self.body['previous_request_id'] = 'wrong'
        with self.assertRaises(ValueError): self.act('begin')
        self.body['previous_request_id'] = first
        self.proof('2:fp', request='wrong')
        with self.assertRaises(ValueError): self.act('begin')

    def test_reused_failed_image_is_rejected(self):
        self.body['rebuild_scene'] = True
        self.proof('1:fp'); self.act('begin')
        with self.assertRaises(ValueError): self.act('image', image=self.image('red'))
        self.ready('blue')
        self.body.update(previous_request_id=self.body['request_id'], request_id='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb')
        self.proof('2:fp'); self.act('begin')
        with self.assertRaises(ValueError): self.act('image', image=self.image('blue'))
        self.ready('green')

    def test_actual_rebuild_controller_and_background(self):
        result = subprocess.run(['node', 'tests/flow_scene_rebuild_388.js'], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_native_failure_dom_selects_new_image_pipeline(self):
        result = subprocess.run(['node', 'tests/flow_service_terminal_385.js', 'browser_extension/flow.js', '--rebuild'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
