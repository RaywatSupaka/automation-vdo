# Long video — paired source candidate 0.15.440

## 2026-09-25: Meta AI 16:9 source path (not installed end-to-end)

Long Video v2 now exposes Meta AI as a video provider for 18–50 landscape scenes. The same saved provider choice flows through immediate jobs, queued jobs and Studio review. Only long-video Meta packages request 16:9; existing vertical Meta jobs retain their prior prompt/receipt format. The program accepts a scene only after a real downloaded MP4 passes ownership, duration and landscape checks. It assembles ten-scene chapters in `long_meta_chapters`, separate from Google Flow cache, and adds full narration only once after joining chapters. Existing saved scenes and Flow/local outputs are not silently relabelled as Meta clips.

One authorized manual Meta submission used a benign synthetic 16:9 image in a new chat and returned a playable 1280×720, ten-second silent MP4. This confirms one landscape output, not that the installed SmartFlow Extension can complete the long-video workflow. No 18–50-scene live job, native speech mode, installed Extension E2E or customer-machine test has been completed; account credit usage was not measured. The full source regression status and activation gates are tracked in `docs/reports/long-meta-440.md`. No EXE installer was built.

## 2026-09-24 post-copy source correction (not activated)

New v2 outlines request one audience-ready description and 3–6 separate hashtags. If the AI puts production metrics in the description, the desktop substitutes a topic-based public caption and retains usable tags; this changes posting text only, not images or rendering. Completed Story videos have a library editor that saves a separate atomic post-copy override and updates copy-all without rewriting the original manifest or video. Focused local tests passed; no provider generation, customer installer build, or live app restart was performed for this correction.

## 2026-09-24 paired source 0.15.431 correction (not activated)

Confirmed contract gaps in the source candidate: an image audit passed the first long-job check but the durable trace revalidated with the Shorts 15-scene default; retries after attempt 3 were rejected; queued long-video edits used the Shorts limit; the list read subtitles from a removed flat field; and Continue could regenerate the legacy full-analysis request instead of reopening the exact v2 outline/chapter. The paired desktop and Extension now persist the current v2 request before Send (also before format repair), clear it only with a matching accepted checkpoint, and route Continue to read the owned reply without resending. The trace and refusal-image fallback use the actual job-scene limit through 50; old Shorts limits remain. Queue edits preserve 18–50 and the UI reads saved audio choices. Isolated tests cover those boundaries and a 23/50-scene Extension plan. No real AI/Flow generation, installed Chrome reload, or EXE installer was performed; provider end-to-end remains pending.

Final paired-431 offline verification: full Python suite 2,231 tests = 2,226 passed, five skipped, zero failures/errors; 29 Extension JavaScript syntax checks; actual-source plan and format-repair harnesses; Chromium queue UI smoke; 39-file source/folder/ZIP parity. Packaged ZIP is `deliverables/SmartFlow_AI_Extension_0.15.431.zip` (SHA-256 `47D40F615D36D10E8956112A7814A5EE7479B4D7A92F6080D226DD3AB8328859`). Detailed report: `docs/reports/long-video-cross-contract-431.md`.

## 2026-09-24 source candidate: long-video v2 (not activated)

New jobs can target 3–10 minutes and 18–50 images in 16:9. The program asks the selected AI for one self-chosen answer, first an outline and then 10-scene chapters; each accepted chapter and each image is durably checkpointed. After saving a scene, the Extension retains a checkpoint marker and duplicate-detection digest rather than its base64 image; the final reply references those saved images instead of retransmitting them. The desktop verifies SHA-256 and landscape for every scene before rendering. Local motion or real Google Flow clips are assembled in ten-scene video chapters; the full narration is attached only after concatenation. Old version-1 jobs retain their existing logic. Offline regression covers 10/10/3 chapter resume, five 10-scene plan chapters, 18-image checkpoint finalization and tamper rejection, synthetic real FFmpeg joins, existing Story/Flow voice paths, and one-answer instruction. This is source-only: no installed Extension/EXE swap, installer, provider credit use, or 50-scene real-service test has been done yet.

Validation on 2026-09-24: 61 focused Python tests, JS syntax checks, the 23/50-scene Extension harness and the existing one-answer browser harness passed. A full-repository test attempt was not green in either available Python environment: the system Python lacked `cryptography` and required a bundled Node module path; the bundled Python lacked `requests` and showed unrelated Thai subtitle test differences. The missing-dependency cases rerun with their available dependencies passed, but the entire suite has not been claimed green.

Date: 2026-09-08. Paired desktop revision: long-video-1. Candidate until installed-provider smoke passes.

## Customer workflow

Sidebar → สร้างคลิปยาว → enter topic/details → target 3/4/5 minutes → auto or 18–50 images → ChatGPT Web or Gemini Web → local image motion or Google Flow → create now or add to queue. Existing voice settings apply. Start/pause uses the shared sequential queue. Enqueuing does not generate anything.

Target length is a writing target, not a guarantee from an AI provider. Final length follows the complete narration; no silent padding to claim 3–5 minutes. Long Flow clips loop within their allocated scene when shorter than narration. This can visibly repeat movement but avoids a long frozen frame. No lip-sync promise.

## Implemented contracts

- core/long_video.py: explicit180–300second target,18–50scenes,1920×1080.
- core/story_manager.py: existing Story lifecycle with opt-in long_video; image request and Flow package carry16:9; landscape image/download checks preserve old work on mismatch; landscape cover.
- core/story_queue.py, ui/main_window.py: frozen long settings survive queued creation/resume. Existing Shorts/Drama remain6–15scenes and9:16. Long mode renders1920×1080. Narration speed unchanged.
- Extension chatgpt.js:50images only for long job +16:9request. Both providers receive horizontal scene prompts. Preserve receipts, no-resend, retry budgets, cancellation and policy behavior.
- local_bridge.py, message-schema: bounded0–50shot transport; managers enforce actual scene count. Progress reports up to50images.
- flow.js/background.js: explicit16:9 setting with9:16default; one output; no new refresh/upload/retry. Status shows requested orientation.
- video_composer.py: optional loop extension only for long jobs; existing hold mode unchanged elsewhere. Real H.264/yuv420p test preserves full narration.
- web_ui/index.html, app.js, usability.*: dedicated sidebar/page, create/queue, responsive layout, landscape modal. video_library.py labels long results.

## Subtitle API boundary

Long videos use existing local script-and-voice subtitles, not a new whole-audio API upload. Isolated core/subtitle_chunks.py is tested for sequential ≤60-second PCM uploads, offset merging and checkpoint replay, but is NOT activated in the manual Subtitle API workflow. Billing and silence-aware word boundaries remain unverified; do not claim that workflow switched to chunks.

## Validation and installation

Actual-source JS:141cases, including both providers completing40horizontal scenes. Focused Python:6long/foundation tests and2real FFmpeg voice-fit tests passed. UI checks1440/1024/768 with transport mocked: no overflow, correct create/queue payload, zero paid requests. Own temporary browser closed.

Final regression suite:978 tests passed, zero failures/errors. Receipt harness49 cases passed. Packaged36files match source/folder/ZIP byte-for-byte;26Extension JS syntax checks passed. UI screenshot: docs/reports/long-video-270/long-video-ui.png.

Package: deliverables/SmartFlow_AI_Extension_0.15.270.zip, paired canonical desktop. Reload existing Extension from the new folder; do not uninstall stored receipts. Close/open SmartFlow AI.exe when idle. Running desktop was observed to require269; automatic EXE restart was blocked by the execution environment. New EXE startup and installed AI/Flow end-to-end are pending. Do not call this release proven from offline tests alone. Final full-suite result is recorded in CURRENT_RELEASE.json.
