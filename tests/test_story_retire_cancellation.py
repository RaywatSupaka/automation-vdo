import json
import pathlib
import subprocess
import unittest


class StoryRetireCancellationTests(unittest.TestCase):
    def test_retired_collector_never_stops_provider_generation(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/story_retire_cancellation.cjs'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data['ok'])
        self.assertGreaterEqual(data['cases'], 30)
        self.assertEqual(data['providerSubmissions'], 0)
