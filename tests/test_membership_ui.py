import json
import subprocess
import unittest
from pathlib import Path


class MembershipUiTests(unittest.TestCase):
    def test_actual_source_login_ui(self): self.run_fixture('membership_ui.cjs')
    def test_actual_source_extension_has_no_membership_gate(self): self.run_fixture('extension_no_membership_391.cjs')
    def test_extension_connection_only_popup(self): self.run_fixture('extension_popup_391.cjs')
    def run_fixture(self, file):
        result=subprocess.run(['node','tests/'+file],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8',timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
