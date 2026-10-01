import json
from pathlib import Path
import subprocess
import unittest


class ChatGPTRecoveryLoop456Tests(unittest.TestCase):
    def test_actual_receipt_reminder_monitor_continuity(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', 'tests/chatgpt_recovery_loop_456.cjs'], cwd=root,
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['ok'])
        self.assertEqual(report['providerSubmissions'], 0)
        self.assertEqual(report['liveStateWrites'], 0)


if __name__ == '__main__':
    unittest.main()
