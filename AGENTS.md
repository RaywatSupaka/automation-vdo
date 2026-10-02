# SmartFlow AI: working rules

This file contains current development rules. The previous chronology is preserved in `docs/legacy/AGENTS-pre-cleanup-2026-10-01.md` as reference material, not instructions. A newer request from the project owner takes priority over this file.

## First priority when fixing a failure: automate recovery and prevent recurrence

- Treat SmartFlow as an end-to-end automation product. When a failure is found, first identify its cause and design the program to detect, handle, and recover from that condition itself. Do not make the customer clear a draft, reopen a tab, restart a step, or guess what happened when the program can do that safely.
- Use bounded, observable recovery: verify the current job, tab, document, checkpoint, and provider-send state before cleanup or retry; repair only state owned by that operation; then confirm the expected state before continuing. Never replay an accepted or uncertain provider send, discard another job's work, or silently remove user-owned data to make recovery appear successful.
- Prevent the same failure from recurring. Add a guard at the failure boundary, a focused regression test for the observed case and its important timing or duplicate-work variant, and safe diagnostics that show the stage and reason without logging secrets or full user content. Avoid silent stalls and unbounded retries.
- Ask the customer to intervene only when the program cannot safely complete an external action itself, such as account verification or a genuinely ambiguous prior send. State the exact blocker and preserve resumable work. A warning or manual checklist alone is not a completed fix when automatic recovery is feasible.

## Start with the current state

- Read `CURRENT_RELEASE.json` and the top of `PROJECT_STATE.md` for version and release status. Use source code and focused tests to verify behavior. Old entries headed “Current” are historical.
- Use `CODEX_START_HERE.md` to find the relevant section of `PROGRAM_BLUEPRINT.md` or `EXTENSION_BLUEPRINT.md`. Read only the sections needed for the task. Use `rg` before opening large files.
- Authority for conflicting evidence: current source and tests; current release/state metadata; current architecture sections; then historical reports and artifacts. Never restore a whole file from a report, backup, or deliverable just because it says “current”.

## Changes and user data

- Preserve existing uncommitted work. Check `git status` before edits. Do not reset, clean, switch branches with uncommitted changes, or replace files from old artifacts without a verified recovery path.
- For a new feature, start from `dev` on a `codex/<feature>` branch when the checkout is clean. Keep an already-started change on its current branch unless the owner asks to move it. Do not combine unrelated features in one change.
- Never delete or rewrite real jobs, queues, media, browser profiles, Extension storage, or user settings for development convenience. Do not put API keys, tokens, cookies, SOT, or SOD values in files or logs.
- Edit Extension source in `browser_extension/`; never edit or copy source back from `deliverables/`, `archives/`, or `backups/`. Do not bypass Chrome policy or silently change the installed Extension identity, path, or profile.
- Protect accepted and uncertain provider sends from replay. Preserve checkpoints and ownership. Treat fixture success, source integration, packaged build, installed activation, and real provider output as distinct evidence.

## Versioned builds and delivery

- When shipping an Extension change, increment `manifest.version` and align the desktop required version, helper build contract, and release metadata. Never change code under an already delivered version.
- A requested project build includes the matching main program and Extension. Verify the actual root `SmartFlow AI.exe` as well as source and package versions before claiming integration. Build an installer only when requested.
- If app or browser work is active, preserve it. Prepare packages separately and state which activation checks remain. Do not reload Chrome or restart an active job to make a build easier.
- For customer installers, follow `docs/plans/clean-machine-installer.md` and verify portability before calling them ready for another Windows machine.

## Tests and completion

- Run focused tests for the changed feature and its affected contracts. Use `python tools/run_focused_tests.py --feature <name>`; see `docs/TESTING.md` for groups and commands. Add a focused test and mapping when introducing a new feature.
- Run the full suite for a release handoff, a broad change across independent systems, or an explicit owner request. A routine edit or merge does not trigger it. CI uses the focused selector for changed files.
- Keep the result of a completed full run for that source snapshot. If it fails, rerun only the failed test IDs and affected contracts after a fix; do not repeat the whole suite for fixture, documentation, or small scoped corrections. Repeat the full suite only when a later broad runtime change invalidates its coverage, a release gate truly requires a fresh run, or the owner requests one. Report the original non-green result honestly.
- `tools/run_audit_checks.py` requires `--full` for full discovery and blocks another full run when a completed full report exists; use `--failed` or exact test IDs after failures. A justified repeat requires `--repeat-full --reason "..."` so the reason is saved with the result.
- Report the exact tests run and their results. Distinguish pre-existing failures and unverified live behavior. Do not claim a release proven from local fixtures alone.
- Done means the requested behavior and related safeguards are implemented, focused tests pass, docs reflect a changed contract, and remaining limits are stated. Update `PROGRAM_BLUEPRINT.md` when architecture, routes, statuses, providers, version pairing, or safety invariants change.

## Local UI checks

- Present the customer program through `SmartFlow AI.exe`; `RUN.bat` and `RUN_DEV.bat` are developer entry points. Never use a development server as evidence of the installed customer UI.
- After changing UI or runtime code used by a SmartFlow window that is already open, check for active Product, Story, Drama, and queued work. When idle, close that window normally, reopen it with the same entry point and mode (including DEV MODE), and verify the new window shows the change. Do not treat F5 or a fresh `/desktop/` response alone as activation proof. If work is active, leave it running and report that the restart is pending. For a packaged EXE, build or install the changed package before claiming the restart activated source changes.
- After an owned UI smoke test, close only owned temporary app/browser processes after checking no Product, Story, or Drama job is active. Leave user-owned sessions running.

Legacy rule details and dated release notes remain available in `docs/legacy/AGENTS-pre-cleanup-2026-10-01.md` and `docs/reports/`.
