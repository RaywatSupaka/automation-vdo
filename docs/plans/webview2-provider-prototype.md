# WebView2 provider prototype

Branch: `feature/webview2-prototype`. This is a separate future prototype. The current desktop shell already uses WebView2 for SmartFlow's own UI; provider sites still run in Chrome with the Extension.

## Work remaining

1. Create an isolated WebView2 provider window and profile without changing the customer's Chrome profile, installed Extension, or current Story route.
2. Verify login/session persistence, file upload, ChatGPT Story prompt entry, stable Send acceptance, image result reading, and download using a disposable test job. Record each outcome and page/operation ID in bounded logs without credentials or full prompt content.
3. Add a host-to-page message contract with job/run/scene ownership and the existing pre-send, receipt, checkpoint, and no-replay rules. Compare its behavior with the current Extension callback path.
4. Add a developer-only switch for a single test job after the prototype passes focused tests. Keep production on Chrome until a real end-to-end Story completes and error recovery is verified.
5. Decide whether the WebView2 extension API is viable on the supported runtime. If it is not, keep automation in a host-controlled adapter; do not assume Chrome Extension APIs are automatically present in WebView2.

The current Story recovery UI work remains on `dev`. Do not move or discard unfinished work to start this prototype. No provider WebView2 behavior has been implemented or verified yet.
