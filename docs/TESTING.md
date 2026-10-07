# Focused development checks

`python tools/run_focused_tests.py --feature ui-terminology` checks the actual desktop markup in isolated Chromium: internal English wording is absent from the main text, Android diagnostics stay inside support details, loaded scripts use the shared confirmation dialog, and technical exception text is replaced at the common error boundary. It also runs existing product deletion, presenter library, Shopee posting/progress, Flow settings, scene plan, Android Wi-Fi and music library harnesses, plus syntax checks. It does not contact a provider or phone.

`python tools/run_focused_tests.py --feature setup-recovery-ui` checks seven setup steps, the four real readiness signals, manual web-login confirmation, the three recovery steps, protected uncertain-send guidance, Flow-credit wording, error dialog deduplication and stopped-work queue display. It does not send a provider request or mutate a customer job.

`python tools/run_focused_tests.py --feature create-wizard-ui` runs the six-step dialog in an isolated browser, checks Shopee URL, scene/episode limits, speaking/video guard, real readiness wording and Story payload equality against the actual legacy click handler. It also runs the existing Product/Drama snapshot stack, generation notice, and queue-choice harness. No provider request is made.

`python tools/run_focused_tests.py --feature jobs-page-ui` checks the real desktop markup, styles and queue controller in an isolated Chromium window. It covers one primary action per job, five status filters, preserved queue pause wording, saved scene count, no raw queue error on cards, 44px controls, old-entry confirmation and stopped-before-queued ordering. It makes no provider request and does not activate the open customer window.

`python tools/run_focused_tests.py --feature notification-layout` checks visible combinations of toast, minimized work and update controls across five viewport sizes, plus existing update notification behavior. Its screenshot is saved to `build/notification-stack/desktop.png`. This isolated browser check does not activate an already-open customer window.

For owner-authorized uncertain Story image replay, run `py -3 tools/run_focused_tests.py --feature story-image-result`. The selector includes the job authorization and receipt transition fixtures; it does not send to ChatGPT.

Use the Python interpreter from `.venv` if one exists. On Windows, for example:

```powershell
.venv\Scripts\python.exe tools\run_focused_tests.py --feature membership
.venv\Scripts\python.exe tools\run_focused_tests.py --feature ai-cover
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-dispatch
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-progress-stall
.venv\Scripts\python.exe tools\run_focused_tests.py --feature ai-send-viewport
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-recovery-ui
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-setup-ui
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-image-result
.venv\Scripts\python.exe tools\run_focused_tests.py --feature extension-update
.venv\Scripts\python.exe tools\run_focused_tests.py --feature release-contract
.venv\Scripts\python.exe tools\run_focused_tests.py --feature refactor
.venv\Scripts\python.exe tools\run_focused_tests.py --feature test-runner
.venv\Scripts\python.exe tools\run_focused_tests.py --feature installer
.venv\Scripts\python.exe tools\run_focused_tests.py --feature webview2-prototype
.venv\Scripts\python.exe tools\run_focused_tests.py --feature ui-foundation
.venv\Scripts\python.exe tools\run_focused_tests.py --feature config-defaults
.venv\Scripts\python.exe tools\run_focused_tests.py --changed
```

`ui-foundation` checks the shared UI layer without a provider request: stylesheet order and the single token set, no text below 10px, the six-state status vocabulary and the plain-Thai queue pause reasons (including a guard that fails when the backend adds a pause reason without text), the grouped sidebar at 1360x860 (fits without scrolling, opens the group of the active page, keyboard toggle, 44px rows), 4.5:1 contrast for every status pill and the primary button, and the existing queue and creative-control harnesses that execute `creation_queue.js`. Browser checks need Node Playwright (see below). Screenshots are saved to `build/ui-foundation/`; they come from an isolated browser, not the installed customer window.

`refactor` checks extracted UI and bridge helpers, browser module imports, and the paired source preflight without contacting a provider.

`config-defaults` checks a clean source checkout with no `config.json`, the first settings save, preservation of existing values, and refusal to replace a corrupt user config. It does not open the customer UI.

`webview2-prototype` checks profile separation, bounded read-only diagnostics, DEV-only page gating, child-control bounds, and bridge isolation. Run `.venv\Scripts\python.exe -m desktop.provider_prototype --smoke` for the separate offline CLI research window. Run `$env:SMARTFLOW_DEV_BYPASS_MEMBERSHIP='1'; .venv\Scripts\python.exe tools\smoke_provider_lab_ui.py` for an offline native fixture that verifies the provider WebView2 is a child of the same SmartFlow-style window, loads, and hides on page exit. In the source DEV MODE SmartFlow window, use the sidebar `AI Chat` menu for the embedded ChatGPT page. These checks do not send a prompt or exercise a real job.

`ai-cover` checks the post-video cover ledger and exact owned ChatGPT result collection. It covers an uncertain Send followed by a late answer, a completed cover image behind a stale Stop control, an accepted cover whose attachment filenames disappear after submission, and native stream-error ownership, durable Retry claim across paused collect-only resume, duplicate controls and ownership change before Retry. The browser fixtures make no provider request.

`story-dispatch` checks duplicate command protection, exact saved-conversation tab adoption on Resume, ambiguous-tab stop, desktop URL routing and heartbeat dispatch ownership, plus read-only ChatGPT bootstrap tab selection, image-tool icons versus actual attachments, late restored drafts, pre-Send bootstrap retry without an empty-URL resume, accepted/uncertain-send vetoes, retained-reference reuse, and the unchanged Gemini tab route.

`story-progress-stall` checks the exact-run three-minute watchdog, one guarded recovery command, timeout review, and Background receipt/tab/draft vetoes for accepted, dispatched, edited and racing Sends. The changed `chatgpt.js` syntax is checked; live provider output requires separate activation.

`ai-send-viewport` checks the actual ChatGPT MAIN-world Send resolver in an offline browser at narrow and resized viewports. It permits at most two owned prepress scroll attempts when geometry changes, verifies the same draft, composer and button after scrolling, and rejects a fixed offscreen button or a resized final arm without clicking a provider. It also tests a trusted CDP hover arriving at the exact Send point, missing and untrusted events, a resize after delivery, and one bounded refocus before a single press.
It also checks bounded removal of one exactly named unsent Story reference left in the composer after a failed Send preflight; ownership changes, unrelated drafts and multiple attachments remain blocked.
The actual Background Send harness also checks up to three five-second read-only readiness rechecks, including transient ambiguous Send controls, one final gesture, and no gesture after the draft changes or ambiguity persists. The Story image result group verifies bounded reason and recheck evidence reaches the local trace without prompt text.

`story-recovery-ui` checks durable saved-scene evidence, bounded trace fallback for a later reference error without a scene number, the Story recovery timeline, stopped-work display order, and direct Story Continue reclaiming only its failed queue row before the normal finisher runs. It does not send provider requests or alter saved jobs.

`story-setup-ui` checks the Story Shorts Quick Setup's bounded inner scroll, three visible setup steps and progress, navigation by click, retained form values, and narrow layouts without provider requests.

`story-image-result` checks owned ChatGPT image result collection when a stale progress marker remains after the completed image, while a real Stop button still blocks collection. It also checks that Continue never restarts an accepted prior-run image request after an empty post-refresh response. These fixtures make no provider request.

The same focused group runs `story_image_wait_342_harness.js` for an uncertain prior-run draft on checkpoint Resume: three read-only observations end in review without refresh or another Send.

`membership` checks the development token gate and membership backend plus JavaScript syntax. The optional real HTML login check needs Playwright and its Chromium browser: `node tests/membership_ui.cjs`.

`extension-update` checks the installer swap, update barrier, pairing diagnostic, Extension heartbeat reload contract, and JavaScript syntax. These are isolated tests; they do not install or reload the user's Chrome Extension.

`release-contract` checks version metadata and release file invariants. Use it when changing a version or packaging contract.

CI compares the pull request or `dev` push with its base commit and runs only mapped feature groups. A changed code file without a mapping fails with a clear message. Add it to `FILE_SUITES` in `tools/run_focused_tests.py` and add the relevant focused tests to the suite before merging. Documentation-only changes skip test execution.

For a rare full audit, explicitly use `.venv\Scripts\python.exe tools\run_audit_checks.py --full`. Calling that runner with no arguments stops before test discovery. The runner prints START and result plus elapsed time for every test and a RUNNING heartbeat every 30 seconds; its JSON includes `test_durations` and `slowest_tests`. A completed full report is saved at `build/audit-results.json`; another full run is refused unless `--repeat-full --reason "why a new full run is required"` is specified. The prior report is archived and the reason is saved. Use `.venv\Scripts\python.exe tools\run_audit_checks.py --failed` to rerun runnable failed IDs from the last full report, or pass exact unittest IDs. Entries without a runnable unittest ID are printed for manual review. Focused reruns write `build/audit-focused-results.json`, archive earlier focused results and retain the full report. On Windows, the runner normalizes the short/long spelling of the temporary directory within its own process.

Browser and real media fixtures require local test tools: Node Playwright and `marked`, Playwright Chromium, FFmpeg and FFprobe. Keep these in an isolated test-tool directory and put the FFmpeg and FFprobe executables together on PATH. Their absence is an environment failure, not evidence that the application behavior passed. Historical comparison tests also require their exact old release fixtures; do not substitute current source for missing historical files.

The installer builder's optional `--full-tests` flag uses the same audit guard. If a fresh full run is genuinely required, add `--repeat-full-tests-reason "reason"`; ordinary installer checks remain focused.

For a small change, completion means the behavior works, affected contract tests pass, syntax is valid, and the result says what was verified. Run the full suite for a release handoff, a broad change across independent systems, or when the owner asks. Keep that full-run report. If it fails, fix and rerun the failed test IDs and affected contracts; do not repeat the whole suite for small corrections. Run it again only when later broad runtime changes invalidate the result, a release gate requires a fresh run, or the owner asks. Keep the original non-green result visible. Installed Chrome and real provider results require their own separate verification and should be reported as such.
