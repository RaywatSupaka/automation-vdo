# Focused development checks

Use the Python interpreter from `.venv` if one exists. On Windows, for example:

```powershell
.venv\Scripts\python.exe tools\run_focused_tests.py --feature membership
.venv\Scripts\python.exe tools\run_focused_tests.py --feature ai-cover
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-dispatch
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-recovery-ui
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-image-result
.venv\Scripts\python.exe tools\run_focused_tests.py --feature extension-update
.venv\Scripts\python.exe tools\run_focused_tests.py --feature release-contract
.venv\Scripts\python.exe tools\run_focused_tests.py --feature refactor
.venv\Scripts\python.exe tools\run_focused_tests.py --feature test-runner
.venv\Scripts\python.exe tools\run_focused_tests.py --feature installer
.venv\Scripts\python.exe tools\run_focused_tests.py --changed
```

`refactor` checks extracted UI and bridge helpers, browser module imports, and the paired source preflight without contacting a provider.

`story-dispatch` checks duplicate command protection, exact saved-conversation tab adoption on Resume, ambiguous-tab stop, desktop URL routing and heartbeat dispatch ownership, plus read-only ChatGPT bootstrap tab selection, stale drafts, document replacement, retained-reference reuse for a prepared unsent Story draft across unified composer forms, exact attachment count before Send, and the unchanged Gemini tab route.

`story-recovery-ui` checks durable saved-scene evidence, bounded trace fallback for a later reference error without a scene number, and the Story recovery timeline shown in the desktop UI. It does not send provider requests or alter saved jobs.

`story-image-result` checks owned ChatGPT image result collection when a stale progress marker remains after the completed image, while a real Stop button still blocks collection. It makes no provider request.

`membership` checks the development token gate and membership backend plus JavaScript syntax. The optional real HTML login check needs Playwright and its Chromium browser: `node tests/membership_ui.cjs`.

`extension-update` checks the installer swap, update barrier, pairing diagnostic, Extension heartbeat reload contract, and JavaScript syntax. These are isolated tests; they do not install or reload the user's Chrome Extension.

`release-contract` checks version metadata and release file invariants. Use it when changing a version or packaging contract.

CI compares the pull request or `dev` push with its base commit and runs only mapped feature groups. A changed code file without a mapping fails with a clear message. Add it to `FILE_SUITES` in `tools/run_focused_tests.py` and add the relevant focused tests to the suite before merging. Documentation-only changes skip test execution.

For a rare full audit, explicitly use `.venv\Scripts\python.exe tools\run_audit_checks.py --full`. Calling that runner with no arguments stops before test discovery. The runner prints START and result plus elapsed time for every test and a RUNNING heartbeat every 30 seconds; its JSON includes `test_durations` and `slowest_tests`. A completed full report is saved at `build/audit-results.json`; another full run is refused unless `--repeat-full --reason "why a new full run is required"` is specified. The prior report is archived and the reason is saved. Use `.venv\Scripts\python.exe tools\run_audit_checks.py --failed` to rerun runnable failed IDs from the last full report, or pass exact unittest IDs. Entries without a runnable unittest ID are printed for manual review. Focused reruns write `build/audit-focused-results.json`, archive earlier focused results and retain the full report. On Windows, the runner normalizes the short/long spelling of the temporary directory within its own process.

Browser and real media fixtures require local test tools: Node Playwright and `marked`, Playwright Chromium, FFmpeg and FFprobe. Keep these in an isolated test-tool directory and put the FFmpeg and FFprobe executables together on PATH. Their absence is an environment failure, not evidence that the application behavior passed. Historical comparison tests also require their exact old release fixtures; do not substitute current source for missing historical files.

The installer builder's optional `--full-tests` flag uses the same audit guard. If a fresh full run is genuinely required, add `--repeat-full-tests-reason "reason"`; ordinary installer checks remain focused.

For a small change, completion means the behavior works, affected contract tests pass, syntax is valid, and the result says what was verified. Run the full suite for a release handoff, a broad change across independent systems, or when the owner asks. Keep that full-run report. If it fails, fix and rerun the failed test IDs and affected contracts; do not repeat the whole suite for small corrections. Run it again only when later broad runtime changes invalidate the result, a release gate requires a fresh run, or the owner asks. Keep the original non-green result visible. Installed Chrome and real provider results require their own separate verification and should be reported as such.
