import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from core.story_prompt_recovery import record_recovery


class ContinuousFlow348Tests(unittest.TestCase):
    def test_actual_source_rounds_and_legacy_budget(self):
        result = subprocess.run(['node', 'tests/flow_continuous_repair_348_harness.js'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_flow_audit_beyond_two_rounds_and_forty_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            job = {'id': 'STORY-TEST', 'scene_count': 1}
            for number in range(1, 46):
                body = {'index': 1, 'run_id': 'RUN-TEST', 'event': {
                    'phase': 'requested', 'round': number, 'request_id': f'R{number}'}}
                record_recovery(folder, job, body, flow=True)
                record_recovery(folder, job, body, flow=True)
            rows = json.loads((folder / 'prompts/flow_recovery.json').read_text())['scenes']['1']
            self.assertEqual(len(rows), 45)
            self.assertEqual(rows[-1]['round'], 45)
            with self.assertRaises(ValueError):
                record_recovery(folder, job, body, flow=False)
            body['event']['round'] = True
            with self.assertRaises(ValueError):
                record_recovery(folder, job, body, flow=True)
