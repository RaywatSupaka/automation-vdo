# SmartFlow customer installer — beta rollout

Latest frozen customer test installer is **0.3.0-beta.16 / Extension 0.15.442**; see `docs/reports/customer-installer-beta16.md`. It is built and locally verified but not installed or tested on an independent Windows PC.

## Double-click builder for the next test installer

Run `BUILD_SMARTFLOW_INSTALLER.bat` from the canonical source folder after desktop/Extension changes are finished. It selects the next beta after `CURRENT_RELEASE.json.customer_distribution.version`; `--version 0.3.0-beta.N` can override that choice only with a newer beta. Use `BUILD_SMARTFLOW_INSTALLER.bat --check-only` to validate without building, or `--full-tests` to include the full source suite. The script requires the existing isolated `.build-env`, local FFmpeg/Android build inputs, Inno compiler and WebView2 bootstrapper. It checks paired Extension versions, refuses to reuse an Extension version when its bytes differ from a frozen deliverable, runs the existing customer preflight and focused installer-contract tests, builds through `tools/build_customer.py`, verifies payload hashes, source fingerprints and Extension ZIP, then compiles the normal Inno Setup. It never overwrites an existing customer-version folder.

The resulting Setup path and SHA-256 are printed at the end. This is a local **test installer**, not an automatic installation, signed update, live publish, or clean-machine/provider E2E certification. Do not deliver it if the builder reports a mismatch; pair a new Extension version first. Existing Chrome Extension installation still needs its same-folder update and user-approved Reload when idle.

## Previous packaged beta.12 scope

Customer desktop: **0.3.0-beta.12**, paired Extension **0.15.413**. Includes beta.11 first-login Shopee Flow-default fix,412 single-answer/Meta recovery and413 Story ChatGPT native-stream/idle refresh/original-prompt/fresh-failed-image recovery. Evidence: `docs/reports/browser-recovery-413.md`. Final2137 tests2136pass/1skip;2670 payload hashes and39 Extension files verified. Packaged EXE engine-only isolated startup, bundled tools and Thai video smoke passed; owned engine exited and port closed. Beta.12 native GUI/install-uninstall, remote-PC and provider E2E pending. Prior beta.10 isolated installed native/tool smoke and its unresolved hidden-test cleanup remain separately documented; not beta.12 verification. This is an unsigned local beta, not a published general-release update.

Beta.12 Setup: `deliverables/customer-0.3.0-beta.12/SmartFlow-AI-Setup-0.3.0-beta.12.exe` (143528417 bytes). SHA256 `19F0559DA4D8BC86438F1AF5E2FBF95F1AC871228B32B40CB655F7C67594D6CB`. Existing unpacked Chrome installations must update files in the SAME loaded folder and Reload when idle; the first-run seed intentionally does not overwrite an existing Extension directory. See `TEST-ON-ANOTHER-PC.md` beside Setup. Do not uninstall Extension or create a new ID to update it.

Fresh installs contain no developer audio library, personal logo/media, jobs, config, tokens or browser profiles. The previous beta.8 audio inventory below is historical. Unverified developer tracks are no longer redistributed; existing customer audio and preferences are preserved and users may import licensed media. Source music files were not deleted.

- Frozen one-directory application with Python/Tk/WebView integration, shipped OFL fonts, complete FFmpeg DLL set, ADB/scrcpy DLLs and scrcpy-server under `tools/android`.
- Inno per-user installer; first installation does not copy developer config, jobs, media, browser profiles or service credentials.
- Customer data: `%LOCALAPPDATA%/SmartFlowAI/data`; installation: `%LOCALAPPDATA%/Programs/SmartFlowAI`.
- `SMARTFLOW_TEST_DATA_ROOT` and `SMARTFLOW_TEST_PORT` isolate files, WebView storage and credential-vault targets. Test credentials use a path-hashed namespace, never the user's normal targets. Never set these variables for customer shortcuts.
- Installed WebView profile is isolated from source/developer WebView sessions.
- Microsoft-signed WebView2 bootstrapper is included. Setup checks process ownership, runs the prerequisite before replacing app files, checks exit/restart status and rechecks Runtime availability. Internet is required when Runtime is missing. A bootstrapper failure must stop Setup, not claim success.
- Optional desktop shortcut, Start Menu entry, uninstall keeps data outside installation intact.

## Build (isolated `.build-env`)

1. Install `requirements.txt` and PyInstaller in the build environment, never in the hosted Voice runtime.
2. Use the established public update key. Generate a publisher key only during an explicitly authorized first-time publisher setup; never replace an existing release key as a build step. Private keys must NEVER enter an installer, patch, website upload or log. Only `assets/update-public-key.txt` is distributed.
3. `tools/build_customer.py --version VERSION --ffmpeg-dir VERIFIED_FFMPEG_BIN --android-dir VERIFIED_SCRCPY_DIRECTORY` supports `--preflight-only`, validates paired versions/dependencies/public key, freezes source hashes and builds the app plus updater into a new directory. Existing output directories are rejected. Resource allowlists and packaged-state scans exclude private state; `BUILD.json` and `PAYLOAD.json` record provenance and all payload hashes.
4. Compile `launcher/customer.iss` with `BuildRoot` and `ReleaseVersion` definitions using Inno Setup. Compiler and WebView bootstrapper are build tools, not product assets.
5. `tools/sign_customer_release.py BUILD_DIRECTORY --from-version PREVIOUS_TESTED_CUSTOMER_VERSION` creates the cumulative patch and signed `release.json`. First installer has no supported older versions until migration/update testing is complete.
6. Check file hashes, signature, ZIP paths, no user state, matching packaged Extension version and actual EXE startup before uploading.

## Update contract

`core/app_updates.py`: Ed25519 release verification; HTTPS download restricted to catfufu update routes; size/hash verification; protected ZIP paths. `desktop/update_api.py` exposes native update controls; `web_ui/updates.js` checks actual extension heartbeat. Downloaded does not mean Extension installed. Unpacked Extension still requires user Reload.

`prepare_app_update` checks creation/remote work, Shopee/Facebook posting and phone setup; an update-only lock serializes the barrier against new direct actions. It pauses the queue and blocks new mutations. Double Install clicks are rejected, and size/hash/supported starting version are checked before closing. Failure to start the updater releases only the exact nonce-owned barrier; it does not resume queues. The updater waits for old GUI/engine exit, verifies signed metadata, stages/backups exact files and rolls back on copy/startup failure. Data is outside the patch target; power-loss and actual cross-version testing remain pending.

Frozen launches reject an existing engine with a different release version; isolated tests reject any unowned engine. They never kill a conflicting user engine. Logs are in the data directory, not the installed payload.

## Isolated installer testing

Compile with `/DSmokeTest` to use a separate AppId, install folder, group and output suffix. Never test using the normal AppId on the developer account: old beta.6 testing already occupies that uninstall entry. Same-host installation is not proof of a clean other Windows machine. Beta.9 test installed/reinstalled/uninstalled the isolated variant, retained synthetic config/workspace, and removed its own registration. Do not distribute the `-SmokeTest.exe` variant to customers.

Beta.9 customer Setup: `deliverables/customer-0.3.0-beta.9/SmartFlow-AI-Setup-0.3.0-beta.9.exe` (143,473,997 bytes). SHA256: `4A2E1EA9D17170E60B29D3E8DEA60585F0B13B2E0C33018F1C5959E3D74E0C6B`. Read `READ-ME.html` inside the installation for login, Chrome consent and stable Extension folder instructions. All38 Extension files match canonical399.

## Historical hosting preparation (not re-deployed by beta.9)

Host source: VoiceCloneOnline. New `/admin3s/smartflow-updates` page and `/api/smartflow-updates` router. Uses existing admin session plus same-origin checks. Upload slots: signed release metadata, app patch, Extension ZIP, full installer. Uploads use 8 MiB resumable chunks; public pointer changes only after all signed files validate.

Verifier runs in `smartflow_updates_runtime`, isolated from the Voice engine. Only public key is on the server. Files stored under `online_data/app_updates/smartflow`, outside frontend build. Stable and beta pointers are separate.

The following deployment record belongs to the earlier rollout: backend restart was withheld after its idle check failed, and its frontend was restored. It is not a current server-state diagnosis. Beta.9 did not restart, deploy or publish server files or an update manifest. Confirm current server ownership/state and the later two-file-admin plan before any future deployment; do not restart unrelated services.

## Gates still required before general customer release

- User's second-machine creation workflow, login/voice/subtitle activation and Extension installation.
- Real installed version-to-version update and forced startup-failure rollback, interrupted-power recovery, update cancellation and large-download resumption hardening. Current downloader restarts an interrupted download; admin uploads already resume.
- Verify WebView2 installation on a machine that lacks it (not uninstall the user's runtime to simulate this).
- Publisher code-signing certificate is not configured: installer/app EXEs are currently unsigned. Manifest signature is separate and does not remove Windows reputation warnings.
- Review commercial compiler terms and third-party redistribution/source obligations before broad distribution. FFmpeg's shipped LICENSE and source/build information accompany its binaries.
- Finish admin UI browser/regression checks after final chunk-upload change, restore service health and verify public download hashes before declaring hosting live.

Never call this beta a fully proven public auto-update release.

## Verification / 2026-09-09

- Beta.8: 1,030 tests passed (`build/customer-beta8-tests.log`). Isolated actual EXE startup and desktop audio UI state confirmed 4 tracks plus 13 SFX; copied audio and signed patch contents match source byte-for-byte. Own EXE/engine stopped and port 19065 verified closed. Setup SHA256 `51934a2d859281b72ca9dc94fbc9db5edffec71c36cd8928cadc719c52d66cbb`.

- Final source suite: 1,029 tests passed (`build/customer-final7-tests.log`).
- Beta.6 actual Setup installation succeeded into an isolated test directory; installed EXE reported matching health and native loaded-window PIDs. Subtitle preview and bundled FFmpeg H.264/AAC output succeeded.
- Beta.7 adds first-launch preparation of the packaged Extension directory, without overwriting an existing unpacked Extension. Final manifest signature, artifact sizes/hashes and all Extension ZIP contents verified against source.
- Beta.7 isolated EXE smoke passed: native ready marker PID 6660/engine 27196, matching 0.3.0-beta.7 health, first-run Extension 0.15.276 directory. These own test processes and the staged frontend test server were stopped; ports 19065 and 17100 are closed.
- Own beta.6 EXE/engine test processes stopped. Test installation remains on disk: uninstall execution was blocked and is NOT verified.
- Public update publishing and second-machine end-to-end generation remain pending. No customer account or job data is included.
