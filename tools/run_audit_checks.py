"""Offline audit runner. A full run always requires an explicit --full flag."""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.chdir(ROOT)


def _test_id(test):
    if isinstance(test, unittest.TestCase):
        return unittest.TestCase.id(test)
    value = getattr(test, 'id', None)
    return value() if callable(value) else str(value if value is not None else test)


def _source_fingerprint():
    """Identify the current non-ignored checkout, including untracked source files."""
    names = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT
    ).split(b"\0")
    digest = hashlib.sha256()
    for raw_name in sorted(set(names)):
        if not raw_name:
            continue
        relative = os.fsdecode(raw_name)
        normalized = relative.replace("\\", "/")
        if normalized.startswith("docs/") or normalized.lower().endswith(".md"):
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        digest.update(raw_name)
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _read_report(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None


def _previous_full_report(full_report, legacy_report):
    current = _read_report(full_report)
    if current and current.get("mode") == "full":
        return full_report, current
    legacy = _read_report(legacy_report)
    if legacy:
        return legacy_report, legacy
    return None, None


def _archive_report(path):
    """Keep the previous full result before an explicitly repeated run."""
    if not path.is_file():
        return None
    history = path.parent / "audit-history"
    history.mkdir(parents=True, exist_ok=True)
    archived = history / f"audit-{time.time_ns()}.json"
    shutil.copy2(path, archived)
    return archived


def _failed_test_names(report):
    names = {item["test"].split(" (", 1)[0] for item in report.get("details", [])
             if isinstance(item, dict) and item.get("test")}
    runnable = sorted(name for name in names if len(name.split(".")) >= 3
                      and all(part.isidentifier() for part in name.split(".")))
    unsupported = sorted(names - set(runnable))
    return runnable, unsupported


def _normalize_test_temp_path():
    """Use the same spelling for tempfile paths and resolved paths on Windows."""
    if os.name != "nt":
        return
    canonical = str(Path(tempfile.gettempdir()).resolve())
    for name in ("TEMP", "TMP"):
        os.environ[name] = canonical
    tempfile.tempdir = None


class ProgressResult(unittest.TextTestResult):
    """Show the active test and retain elapsed time for the final report."""

    def __init__(self, *args, total_tests=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_tests = total_tests
        self.test_durations = []
        self._outcomes = {}
        self._active = None
        self._run_started = time.monotonic()
        self._stop_progress = threading.Event()
        self._ticker = threading.Thread(target=self._heartbeat, daemon=True)
        self._ticker.start()

    def _heartbeat(self):
        while not self._stop_progress.wait(30):
            active = self._active
            if active is not None:
                number, name, started = active
                print(f"[{number}/{self.total_tests}] RUNNING {time.monotonic()-started:.1f}s {name}", flush=True)
            else:
                print(f"[{self.testsRun}/{self.total_tests}] RUNNING fixture setup/teardown "
                      f"{time.monotonic()-self._run_started:.1f}s elapsed", flush=True)

    def startTest(self, test):
        super().startTest(test)
        self._active = (self.testsRun, _test_id(test), time.monotonic())
        print(f"[{self.testsRun}/{self.total_tests}] START {self._active[1]}", flush=True)

    def addFailure(self, test, err):
        self._outcomes[id(test)] = "FAIL"
        super().addFailure(test, err)

    def addError(self, test, err):
        self._outcomes[id(test)] = "ERROR"
        super().addError(test, err)

    def addSkip(self, test, reason):
        self._outcomes[id(test)] = "SKIP"
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._outcomes[id(test)] = "FAIL" if issubclass(err[0], AssertionError) else "ERROR"
        super().addSubTest(test, subtest, err)

    def addExpectedFailure(self, test, err):
        self._outcomes[id(test)] = "XFAIL"
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._outcomes[id(test)] = "UNEXPECTED_SUCCESS"
        super().addUnexpectedSuccess(test)

    def stopTest(self, test):
        active = self._active
        elapsed = time.monotonic() - active[2] if active is not None else 0.0
        outcome = self._outcomes.pop(id(test), "PASS")
        name = _test_id(test)
        self.test_durations.append({"test": name, "seconds": round(elapsed, 3), "status": outcome})
        print(f"[{self.testsRun}/{self.total_tests}] {outcome} {elapsed:.3f}s {name}", flush=True)
        self._active = None
        super().stopTest(test)

    def stopTestRun(self):
        self._stop_progress.set()
        super().stopTestRun()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--full", action="store_true", help="Run all tests explicitly")
    mode.add_argument("--failed", action="store_true", help="Run failed IDs from the last full report")
    parser.add_argument("--repeat-full", action="store_true", help="Allow another full run after a previous report")
    parser.add_argument("--reason", help="Required reason for --repeat-full; saved in the full report")
    parser.add_argument("tests", nargs="*", help="Exact unittest test IDs for a focused run")
    args = parser.parse_args(argv)
    if not args.full and not args.failed and not args.tests:
        parser.error("choose --full, --failed, or exact test IDs; no-argument full runs are disabled")
    if args.tests and (args.full or args.failed):
        parser.error("exact test IDs cannot be combined with --full or --failed")
    if args.repeat_full and not args.full:
        parser.error("--repeat-full requires --full")
    if args.repeat_full and not (args.reason or "").strip():
        parser.error("--repeat-full requires a nonempty --reason")
    if args.reason and not args.repeat_full:
        parser.error("--reason is only used with --repeat-full")

    full_report = ROOT / "build" / "audit-results.json"
    legacy_report = ROOT / "build" / "audit-426-results.json"
    focused_report = ROOT / "build" / "audit-focused-results.json"
    previous_path, previous = _previous_full_report(full_report, legacy_report)
    source_before = _source_fingerprint() if args.full else None
    if args.full and not args.repeat_full and previous:
        print("A completed full audit report already exists. Use --failed or exact test IDs; "
              "--repeat-full requires a documented reason for another full run.", file=sys.stderr)
        return 2
    if args.repeat_full:
        archived = _archive_report(previous_path) if previous_path else None
        if archived:
            print("Previous full report preserved:", archived, flush=True)

    unsupported = []
    if args.failed:
        if not previous:
            print("No completed full audit report is available for --failed.", file=sys.stderr)
            return 2
        names, unsupported = _failed_test_names(previous)
        if unsupported:
            print("Failed entries without runnable unittest IDs need manual review: "
                  + ", ".join(unsupported), file=sys.stderr)
        if not names:
            if unsupported:
                return 2
            print("The last full audit report has no failed test IDs.")
            return 0
        print(f"Rerunning {len(names)} failed test IDs from the last full audit report.", flush=True)
        suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    elif args.full:
        print("Discovering full test suite...", flush=True)
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    else:
        suite = unittest.defaultTestLoader.loadTestsFromNames(args.tests)

    _normalize_test_temp_path()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='backslashreplace')
    stream=io.StringIO()
    started=time.monotonic()
    total_tests=suite.countTestCases()
    runner=unittest.TextTestRunner(stream=stream,verbosity=0,
                                   resultclass=lambda *args, **kwargs: ProgressResult(*args,total_tests=total_tests,**kwargs))
    result=runner.run(suite)
    report={'mode': 'full' if args.full else 'focused',
            'ran':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'unexpected_successes':len(result.unexpectedSuccesses),
            'duration_seconds':round(time.monotonic()-started,3),
            'test_durations':result.test_durations,
            'slowest_tests':sorted(result.test_durations,key=lambda item:item['seconds'],reverse=True)[:20],
            'skip_details':[{'test':_test_id(test),'reason':reason} for test,reason in result.skipped],
            'details':[{'test':_test_id(test),'traceback':detail[:5000]+'\n…\n'+detail[-1500:] if len(detail)>6500 else detail} for test,detail in result.failures+result.errors]}
    if unsupported:
        report["unrunnable_failed_entries"] = unsupported
    if args.full:
        source_after = _source_fingerprint()
        report["source_fingerprint"] = source_before
        report["source_changed_during_run"] = source_after != source_before
        report["repeat_reason"] = args.reason.strip() if args.repeat_full else None
    target = full_report if args.full else focused_report
    target.parent.mkdir(parents=True,exist_ok=True)
    if not args.full:
        _archive_report(target)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('details','test_durations')},ensure_ascii=True))
    for entry in report['details']: print(entry['test'])
    print('Report:',target)
    if not result.wasSuccessful():
        return 1
    return 2 if unsupported else 0


if __name__ == "__main__":
    sys.exit(main())
