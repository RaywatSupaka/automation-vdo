# AI browser recovery: refresh, check, redo the missing scene

Status: implemented in paired source0.15.437, source/fixture validated and Extension packaged. Installed/runtime baseline0.15.436 is untouched. See `../reports/story-refresh-check-redo-437.md` for final verification and activation limits.

## User's decision

When an AI browser response cannot be found or is unusable, refresh first and inspect it again. If there really is no usable result after that check, submit the saved scene again; use a clean tab if the original page remains broken. Continue automatically until that scene produces a usable result, while honoring user cancellation. Successful earlier scenes stay saved. A `SEND_UNCONFIRMED` label alone must not block this sequence indefinitely.

## Why the current implementation misses this

The 2E5103 scene-4 audit proves that the original prompt and completed image are present. The source also reproduces a mutable DOM ordinal causing `request_missing` after an older exchange unmounts. `sendAndVerify` exits at 60 seconds before it enters the image wait/refresh monitor. The monitor's missing-request proof requires old numeric turn IDs, while the background refresh path requires `send_phase=accepted`; both exclude this semantic-DOM `dispatching` receipt. Fresh restart currently requires an explicit completed service-error/no-image receipt. These gates together prevent the user-requested refresh/check/redo path.

Reference: `docs/reports/story-scene4-send-436-audit.md`.

## Runtime sequence

1. Preserve the exact scene prompt, saved reference files, scene index, job/run and current attempt before acting. Detect an already saved scene first. Use stable message identities to match browser results rather than recalculating position from the currently mounted history.
2. After 60 seconds without a confirmed request/result, enter a visible recovering state. If generation is visibly active, keep waiting. Otherwise claim one same-conversation reload for this attempt. Retire the old collector and resume the same attempt after page readiness; do not let multiple callbacks reload it independently.
3. Wait for real page/history readiness and inspect the latest owned request/result repeatedly for up to 30 seconds after readiness, with at least three stable observations at the conversation end. An empty loading shell, login screen, transport failure or unhydrated history is not a successful no-result check. If a usable image/video/JSON is found, save it and continue. If the provider is still generating or the image is loading, wait and check again. Preserve an unsent user draft instead of reloading or overwriting it.
4. A ready, stable and idle page without an unsent draft that still lacks a usable result can enter `missing_after_refresh`; a completed ordinary service error/unusable answer can enter `unusable_after_refresh`. These describe observations, not an invented provider failure. Recheck result/activity immediately before claiming the successor. Archive the original attempt and allocate one durable successor for this scene. Copy its saved prompt and actual references; never reset the whole job or reuse a previous image as the new result.
5. Retry once in a healthy current context when appropriate; if it remains broken, create one clean provider tab and submit there. Verify the reference attachment and issue one Send for that successor. Repeat the recovery cycle for recoverable failures without a fixed lifetime scene-attempt cap, using cancellable backoff. The next cycle cannot allocate another successor while the current one is active.
6. Manual Continue resumes the saved recovery phase and the current successor. It must not reopen an abandoned old URL after the clean successor has been registered. Late results from an older attempt cannot overwrite a checkpoint saved by the current attempt.

## Implementation scope

- `browser_extension/chatgpt.js`: stable pre-Send identities; route acceptance timeout into the refresh/check state; support legacy ordinal-only pending receipts; preserve exact prompt/reference input; continuous acceptance diagnostics.
- `browser_extension/background.js`: allow an authenticated same-job/tab pending dispatch to request read-only refresh even before a user message ID was captured; revalidate page readiness and current ownership; reuse the durable archive/successor mechanism with explicit post-refresh absence evidence. Extend the restart validator, startup routing, restart handler and content receipt `freshRetry`/`restore` consumption together, so the new evidence cannot pass one gate and get stuck at the next.
- `core/story_receipt_recovery.py`, `core/story_image_result_recovery.py` and Story package routing: carry current attempt/recovery state, avoid reopening superseded URLs, recover compatible old jobs without deleting images or receipts.
- `core/local_bridge.py` and progress UI: recovering steps remain nonterminal; show “กำลังรีเฟรชตรวจผลเดิม”, “พบภาพแล้ว กำลังบันทึก” and “ยังไม่มีผล กำลังเริ่มฉากนี้ใหม่”. Save bounded reason/attempt/message-identity evidence so the next failure is diagnosable.

Reuse the same state meanings across AI providers, but validate each provider's actual ready/busy/result signals. Explicit policy refusals are not transient transport failures; login/usage limits require their existing actionable handling. No silent provider/model changes.

## Verification before delivery

- Actual-source DOM test: older analysis exchange disappears after Send; full prompt/new message is still recognized.
- Existing 436 receipt: scene 4 already has an image; reload/recheck saves that image with zero new Sends, leaving scenes 1–3 unchanged.
- After refresh the page is ready, idle and genuinely missing the result: exactly one successor is allocated and the original prompt/reference is submitted once.
- A result or active generation appears during readiness checking: use/wait for it; no successor submission.
- Page still loading, disconnected or requiring login: do not misclassify it as an empty completed response.
- Restart Extension/app during reload, after successor creation, during attachment or after Send: resume the same recorded attempt without duplicate allocation/submission.
- User cancellation, wrong job/run, stale replies, duplicate prompts and late old images cannot corrupt the current checkpoint.
- Test repeated recoverable failures followed by success, accurate UI state and useful durable diagnostics.

Implementation changes canonical source and the paired Extension only. No installer, Chrome state or current user-job changes. User previously chose to perform live job execution personally. A persisted unknown reload claim may receive one freshly guarded read-only reload on an explicit new resumed run; it cannot allocate a successor without new ready/stable observations. This handles the non-atomic browser reload/storage acknowledgment boundary without blindly submitting again.
