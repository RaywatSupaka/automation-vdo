# WebView2 provider prototype

Branch: `feature/webview2-prototype`. This is a separate future prototype. The current desktop shell already uses WebView2 for SmartFlow's own UI; provider sites still run in Chrome with the Extension.

## Stage 1: isolated read-only lab (implemented on this branch)

`desktop/provider_prototype.py` opens a separate Edge WebView2 window and a separate profile under ignored `build/webview2-provider-prototype/profile-chatgpt`. It does not load the Chrome profile, install an Extension, route a Story job, send prompts, upload files, or read message text. Its page probe records only origin class, readiness, control visibility, and bounded element counts in `events.jsonl`; it records no credentials, full URLs, prompts, or responses. Navigation-time probe errors are retried without logging exception text.

Run `.venv\Scripts\python.exe -m desktop.provider_prototype --smoke` to open and close an offline fixture. Run `--check-provider` to open ChatGPT read-only and close it after page readiness or 30 seconds. Run `--provider chatgpt` for manual inspection in the separate profile; close that window when finished. None of these modes uses a real job.

The source DEV MODE SmartFlow window has an `AI Chat` sidebar page. `desktop/embedded_provider.py` hosts a raw WebView2 control inside the same WinForms window, aligned to the page content. It uses `profile-embedded-chatgpt` under the ignored build folder and does not inject the SmartFlow JavaScript bridge into the provider. Leaving the page hides the control. The old Setup button that launched a second window was removed. The DEV gate hides this menu in the packaged customer app and ordinary browser; the provider control still does not route Story jobs. The native child-control smoke passed (`same_window=true`, `fixture_loaded=true`, `hidden_on_leave=true`), and the reopened source DEV window visibly rendered logged-out ChatGPT inside the SmartFlow page on 2026-10-02. Login and provider workflow were not tested.

On 2026-10-02, four CLI lab safety tests and four embedded page/native bridge tests passed. The separate CLI read-only ChatGPT check reached `ready=complete`; it did not verify login/session persistence. The embedded page is source DEV only and has not been packaged into the customer SmartFlow executable.

## Work remaining

1. Verify login/session persistence and page controls in the embedded profile.
2. Add a host-to-page message contract with job/run/scene ownership and the existing pre-send, receipt, checkpoint, and no-replay rules. Compare its behavior with the current Extension callback path.
3. Verify file upload, Story prompt entry, stable Send acceptance, image result reading, and download using a disposable test job. Record each outcome and page/operation ID in bounded logs without credentials or full prompt content.
4. Add a developer-only switch for a single test job after the prototype passes focused tests. Keep production on Chrome until a real end-to-end Story completes and error recovery is verified.
5. Decide whether the WebView2 extension API is viable on the supported runtime. If it is not, keep automation in a host-controlled adapter; do not assume Chrome Extension APIs are automatically present in WebView2.

The current Story recovery UI work remains on `dev`. Do not move or discard unfinished work to continue this prototype.
