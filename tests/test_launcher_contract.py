import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LauncherContractTests(unittest.TestCase):
    def test_run_and_exe_launcher_use_one_python_resolver(self):
        batch = (ROOT / "RUN.bat").read_text(encoding="utf-8")
        launcher = (ROOT / "launcher" / "SmartFlowLauncher.cs").read_text(encoding="utf-8")
        resolver = ROOT / "launcher" / "resolve_python.ps1"

        self.assertTrue(resolver.is_file())
        self.assertIn("launcher\\resolve_python.ps1", batch)
        self.assertIn("resolve_python.ps1", launcher)
        self.assertNotIn('"Programs", "Python", "Python311"', launcher)
        self.assertNotIn("start \"\" pythonw app.py", batch)

    def test_python_resolver_returns_an_existing_pythonw(self):
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "launcher" / "resolve_python.ps1"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(Path(result.stdout.strip()).is_file())


if __name__ == "__main__":
    unittest.main()
