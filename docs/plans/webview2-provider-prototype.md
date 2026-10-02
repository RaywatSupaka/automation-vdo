# WebView2 provider prototype

Branch: `feature/webview2-prototype`. This is a separate future prototype. The current desktop shell already uses WebView2 for SmartFlow's own UI; provider sites still run in Chrome with the Extension.

## Stage 1: isolated read-only lab (implemented on this branch)

`desktop/provider_prototype.py` opens a separate Edge WebView2 window and a separate profile under ignored `build/webview2-provider-prototype/profile-chatgpt`. It does not load the Chrome profile, install an Extension, route a Story job, send prompts, upload files, or read message text. Its page probe records only origin class, readiness, control visibility, and bounded element counts in `events.jsonl`; it records no credentials, full URLs, prompts, or responses. Navigation-time probe errors are retried without logging exception text.

Run `.venv\Scripts\python.exe -m desktop.provider_prototype --smoke` to open and close an offline fixture. Run `--check-provider` to open ChatGPT read-only and close it after page readiness or 30 seconds. Run `--provider chatgpt` for manual inspection in the separate profile; close that window when finished. None of these modes uses a real job.

On 2026-10-02, four focused safety tests passed, the offline native window exposed a composer, Send control, and file input, and the read-only ChatGPT load reached `ready=complete` in the separate profile. That check saw no visible composer, so login/session persistence and provider operations remain unverified. The WebView2 window is a developer lab and is not yet embedded in the customer SmartFlow window.

## Work remaining

1. Verify login/session persistence and page controls in the separate profile.
2. Add a host-to-page message contract with job/run/scene ownership and the existing pre-send, receipt, checkpoint, and no-replay rules. Compare its behavior with the current Extension callback path.
3. Verify file upload, Story prompt entry, stable Send acceptance, image result reading, and download using a disposable test job. Record each outcome and page/operation ID in bounded logs without credentials or full prompt content.
4. Add a developer-only switch for a single test job after the prototype passes focused tests. Keep production on Chrome until a real end-to-end Story completes and error recovery is verified.
5. Decide whether the WebView2 extension API is viable on the supported runtime. If it is not, keep automation in a host-controlled adapter; do not assume Chrome Extension APIs are automatically present in WebView2.

The current Story recovery UI work remains on `dev`. Do not move or discard unfinished work to continue this prototype.
