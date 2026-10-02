import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.run_audit_checks import ProgressResult, _archive_report, _failed_test_names, _test_id, main


class AuditProgressTests(unittest.TestCase):
    def test_no_argument_command_cannot_start_the_full_suite(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
            main([])
        self.assertEqual(stopped.exception.code, 2)

    def test_repeat_full_requires_a_reason_before_discovery(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
            main(["--full", "--repeat-full"])
        self.assertEqual(stopped.exception.code, 2)

    def test_existing_full_report_requires_explicit_repeat(self):
        prior = {"source_fingerprint": "same-source", "source_changed_during_run": False}
        for signature in ("same-source", "changed-source"):
            with self.subTest(signature=signature), \
                    patch("tools.run_audit_checks._source_fingerprint", return_value=signature), \
                    patch("tools.run_audit_checks._read_report", return_value=prior), \
                    patch.object(unittest.defaultTestLoader, "discover", side_effect=AssertionError("full suite started")), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--full"]), 2)

    def test_failed_selector_exposes_non_runnable_report_entries(self):
        report = {"details": [
            {"test": "test_example.ExampleTests.test_one"},
            {"test": "setUpClass"},
        ]}
        self.assertEqual(_failed_test_names(report),
                         (["test_example.ExampleTests.test_one"], ["setUpClass"]))

    def test_repeat_preserves_the_previous_full_report(self):
        with tempfile.TemporaryDirectory() as temp:
            current = Path(temp) / "audit-results.json"
            current.write_text('{"failures": 1}', encoding="utf-8")
            archived = _archive_report(current)
            current.write_text('{"failures": 0}', encoding="utf-8")
            self.assertEqual(archived.read_text(encoding="utf-8"), '{"failures": 1}')

    def test_failed_rerun_keeps_full_report_and_writes_focused_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "build" / "audit-results.json"
            report.parent.mkdir()
            body = json.dumps({"mode": "full", "details": [{"test":
                "test_audit_progress.AuditProgressTests.test_no_argument_command_cannot_start_the_full_suite"}]})
            report.write_text(body, encoding="utf-8")
            with patch("tools.run_audit_checks.ROOT", root), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--failed"]), 0)
            self.assertEqual(report.read_text(encoding="utf-8"), body)
            focused = root / "build" / "audit-focused-results.json"
            self.assertEqual(json.loads(focused.read_text(encoding="utf-8"))["ran"], 1)

    def test_progress_records_time_and_subtest_outcome(self):
        class Passing(unittest.TestCase):
            def runTest(self):
                time.sleep(0.01)

        class SubtestFailure(unittest.TestCase):
            def runTest(self):
                with self.subTest(case="failure"):
                    self.assertEqual(1, 2)

        suite = unittest.TestSuite([Passing(), SubtestFailure()])
        output = io.StringIO()
        runner = unittest.TextTestRunner(
            stream=io.StringIO(), verbosity=0,
            resultclass=lambda *args, **kwargs: ProgressResult(*args, total_tests=2, **kwargs),
        )
        with contextlib.redirect_stdout(output):
            result = runner.run(suite)
        self.assertEqual([item["status"] for item in result.test_durations], ["PASS", "FAIL"])
        self.assertIsInstance(result.test_durations[0]["seconds"], float)
        self.assertGreaterEqual(result.test_durations[0]["seconds"], 0)
        self.assertIn("[1/2] START", output.getvalue())
        self.assertIn("[2/2] FAIL", output.getvalue())
        self.assertEqual(_test_id(type("Holder", (), {"id": "fixture-id"})()), "fixture-id")
        custom = Passing()
        custom.id = "STORY-TEMP-ID"
        self.assertEqual(_test_id(custom), unittest.TestCase.id(custom))


if __name__ == "__main__":
    unittest.main()
