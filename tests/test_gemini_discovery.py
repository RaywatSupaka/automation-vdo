import subprocess
import unittest
from pathlib import Path


class GeminiDiscoveryTests(unittest.TestCase):
    def test_actual_extension_discovery_guard(self):
        root = Path(__file__).resolve().parents[1]
        subprocess.run(['node', 'tests/gemini_discovery_harness.js'], cwd=root, check=True, timeout=20)
