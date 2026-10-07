# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**[AGENTS.md](AGENTS.md) holds the binding working rules (recovery-first fixes, user-data safety, versioned builds, test policy, UI activation). Read it first and follow it.** This file only adds orientation.

SmartFlow AI is a Windows desktop app that builds Shopee affiliate product clips, Story Shorts, long videos and multi-EP AI dramas. It drives ChatGPT Web / Gemini Web (images, scripts) and Google Flow (video) inside the user's own Chrome through the SmartFlow Chrome Extension. No provider API keys replace the browser sessions. Docs and UI copy are Thai.

UI redesign in progress: read `docs/plans/ui-redesign-handoff-20261007.md` before touching `web_ui/`.

## Where to start reading

1. `CURRENT_RELEASE.json` and the top of `PROJECT_STATE.md`: the current version and release state. Older "Current" headings are historical.
2. `CODEX_START_HERE.md`: an index into `PROGRAM_BLUEPRINT.md` (~800 KB) and `EXTENSION_BLUEPRINT.md`.
   - These files are huge. `rg` for the section you need; never read them whole.
3. If evidence conflicts, trust in this order: source and tests, then release/state metadata, then blueprint sections, then reports, backups and deliverables.

The owner may have a live queue running in the DEV window. Check `CODEX_START_HERE.md` and `PROJECT_STATE.md` before you close or restart the app, or reload the Extension.

## Commands

Use `.venv\Scripts\python.exe` (Python 3.11). Dependencies are in `requirements.txt`; browser fixtures also need Node, Playwright Chromium, `marked`, FFmpeg and FFprobe. This repo has no Playwright of its own: set `NODE_PATH=C:/Users/RaywatSupaka/Desktop/project/frontend/node_modules` before running Node UI tests.

```powershell
RUN.bat                                     # dev launch, membership token enforced
RUN_DEV.bat                                 # sets SMARTFLOW_DEV_BYPASS_MEMBERSHIP=1, then calls RUN.bat
.venv\Scripts\python.exe app.py --page story   # open on a page (dashboard|guide|products|story|drama|library|voice|subtitle|audio|logo|queue|logs)

.venv\Scripts\python.exe tools\run_focused_tests.py --changed            # suites for working-tree changes
.venv\Scripts\python.exe tools\run_focused_tests.py --changed --plan     # print the selection only
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-setup-ui
.venv\Scripts\python.exe tools\run_focused_tests.py --feature ui-foundation   # palette, status vocabulary, sidebar
.venv\Scripts\python.exe -m unittest tests.test_creation_queue           # one module (tests are unittest)
node tests\story_queue_declutter_ui.js                                   # one JS/CJS harness
.venv\Scripts\python.exe tools\run_audit_checks.py --failed              # rerun failed IDs from the last full audit
.venv\Scripts\python.exe tools\run_audit_checks.py --full                # rare; refuses a repeat without --repeat-full --reason
.venv\Scripts\python.exe tools\package_current_extension.py              # package the Extension
```

- `docs/TESTING.md` explains each feature group.
- The file-to-suite map is `FILE_SUITES` in `tools/run_focused_tests.py`. CI (`.github/workflows/focused-checks.yml`) fails when a changed code file has no mapping, so add one when you add a feature.
- `SmartFlow AI.exe` is a C# launcher (`launcher/SmartFlowLauncher.cs`) built under `build/`. Customer installers follow `docs/plans/clean-machine-installer.md`.

## Architecture

```
SmartFlow AI.exe / RUN.bat → app.py → desktop/hybrid.py run_hybrid()
  ├─ spawns hidden engine: app.py --engine → ui/main_window.py MainWindow (Tk, never shown)
  │     └─ core/local_bridge.py HTTP server on 127.0.0.1:8765 (config bridge_port)
  │           ├─ /desktop/*            static Hybrid UI from web_ui/
  │           ├─ /api/desktop/state    polled UI state (compact|logs|subtitle_preview)
  │           ├─ /api/desktop/action   {action,payload} → guard_action → MainWindow._desktop_action_request → Tk queue
  │           └─ /api/extension/*      Chrome Extension heartbeat, commands, results
  ├─ pywebview/WebView2 window loads http://127.0.0.1:8765/desktop/#<page>
  │     js_api = desktop/update_api.py UpdateApi (updates + DEV-only provider lab only)
  └─ watchdog restarts the engine (bounded)
browser_extension/ (MV3) ↔ local bridge; it automates ChatGPT/Gemini/Google Flow tabs in the user's Chrome
```

### Backend

- `ui/main_window.py` (~12.7k lines) is the engine controller. It owns about 110 desktop actions and job orchestration. Despite the folder name, it is not the visible UI.
- `core/` (~120 modules) holds the domain logic:
  - pipelines: `product_manager.py`, `story_manager.py`, `story_pipeline.py`, `drama_series.py`
  - `creation_queue.py`
  - `video_library.py`
  - membership and updates
  - `atomic_json.py`: every config, queue and manifest write goes through it, with last-known-good recovery.
- Jobs are checkpointed. Resume must redo only the missing parts. Accepted or uncertain provider sends are never replayed automatically.

### Hybrid UI (`web_ui/`)

- Plain HTML/CSS/JS with no build step. `index.html` defines most pages as `data-view` sections. `app.js` handles navigation (`showPage`, `#hash`), state polling and `postAction`.
- Many feature scripts inject or move markup at runtime: `media_audio.js`, `green_screen.js`, `ai_cover.js`, `presenter.js`, `creator_ux.js`, `usability.js`, `studio.js`, `product_story.js`, and others. Some even create whole pages (`product-cast`, `intro`, `green`, `facebook`). Read the injecting script, not just `index.html`.
- Script load order matters.
- Styles are spread over ~28 CSS files. `foundation.css` loads last and holds the one colour token set (the `styles.css` `--bg/--cyan/...` and `ux_2026.css` `--sf-*` families share its values), status pill styles and the grouped sidebar. Older stylesheets still hard-code many colours; replace them with tokens page by page.
- `status_vocabulary.js` (`window.SmartFlowStatus`) is the only mapping from backend status codes and queue pause reasons to customer wording (six states). Use it instead of writing labels by hand. It must load before `app.js` and `creation_queue.js`, and every test harness that executes `creation_queue.js` must load it first.
- The desktop window serves these files live from the bridge.
- After a UI change, follow AGENTS.md "Local UI checks". Close and reopen the window with the same entry point when idle. F5 is not proof.

### DEV vs prod

- The UI is the same; there is no separate DEV UI.
- DEV mode (`core/membership.py`) requires all of these: `SMARTFLOW_DEV_BYPASS_MEMBERSHIP=1`, a non-frozen source checkout, `.git` and `.venv`.
- DEV mode only skips the token gate, shows "DEV MODE", and enables the provider-lab "AI Chat" page.

### Runtime data

- `workspace/`, `data/`, `videos/`, `config.json`, `backups/`, `logs/` and `screenshots/` are user and runtime data. Never clear them.
- A clean checkout without `config.json` uses the defaults in `core/customer_runtime.py`.

### Extension

- Source lives only in `browser_extension/`. Packages in `deliverables/`, `backups/` and `build/` are outputs and must never be edited.
- An Extension change bumps `manifest.version` and must stay paired with the desktop's required version and release metadata.
