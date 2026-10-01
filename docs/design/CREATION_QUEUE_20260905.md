# Shared creation queue — Product + Story Shorts

Implemented desktop feature. Entry: `SmartFlow AI.exe`. Extension unchanged: 0.15.244 Candidate. This is not the Android publishing queue.

## Source ownership

- `core/creation_queue.py`: FIFO, deduplication, snapshots, restart/retry/edit/move. Extends `StoryBatchQueue` using the existing `workspace/story_batch_queue.json`, atomic lock and backup. No second store.
- `ui/creation_queue.py`: credential-free capture, preflight, dispatch guard, Product Job binding/completion, actions and compact view.
- `ui/main_window.py`: existing Product/Story/Drama executors remain responsible for full generation. One creation/manual Flow owner; cancelled workers must exit before handoff.
- `web_ui/creation_queue.js` + `.css`: queue page, Product multi-link dialog, Story single-item shortcut, row actions/live phase. Existing Story batch dialog forwards into this queue.
- `tests/test_creation_queue.py`: store, concurrency, cancellation, Final gate, recovery, snapshots and adapter regressions.
- `tools/hybrid_ui_click_smoke.js --queue-audit`: real paused UI CRUD + fixture progress + layout checks. Blocks generation actions and removes only its own rows.

## Lifecycle

`Add → queued → explicit Start → preflight → running + Job binding → existing full pipeline → verified Final → completed → next item`

Images arriving, one Flow shot finishing or a download click are NOT queue completion. Product readiness and non-empty Final are required. Story must finish the existing subtitle/logo/audio stages and publish a non-empty Final. Structured Flow policy fallback remains the current local-motion rule; no new prompts, retries or attachment gestures.

## UI contract

- 1–10 links/topics per batch; maximum 30 queued/running entries. Product and Story batches may be mixed.
- Append during running without pausing; an empty/finished queue waits for Start.
- Active rows above history, current queue positions, type filters and actual phase/progress.
- Start, pause after current, cancel current + pause, reorder pending, edit unstarted link/topic, remove non-running row, retry failed/cancelled Product/Story with its original Job.
- Row removal never deletes Job files. Completed rows open the existing library detail, not another preview implementation.
- Drama shares serialization but retains its series-specific continuity and recovery controls. Do not reorder dependent episodes from this page.

## Snapshots

Provider/model, Story scenes/style/direction/reference, voice reference, subtitle style, audio and render preferences are frozen per item. ChatGPT uses `auto`/current model. Runtime credentials come from existing stores and are excluded recursively from queue data. Queued voice references do not rewrite the global voice selection.

Edit preserves the snapshot. Its optional checkbox recaptures current voice/subtitle/render settings while retaining provider/model. Story preserves its existing always-captioned finisher.

## Safety

- Single timer and running claim, shared lock, per-claim attempt, atomic imported-Job binding. Cancel during import retains the Job; stale attempts cannot bind a different Job.
- Pause lets current finish. Cancel uses existing run-specific cancellation and retains checkpoints. Worker exit and owned-browser close confirmation gate the next job.
- Startup converts interrupted running rows to queued, keeps Job/checkpoints, pauses; Product/Story startup recovery must not auto-start queued work.
- A verified saved Final can be reconciled after restart without rerendering or spending more credits.
- Invalid Product input before import may skip. Unknown browser/login/credit/extension terminal failures pause; never start another remote job while results are uncertain.
- Progress polling does not replace row buttons under the pointer.
- `CREATION QUEUE` logs record queue ID, Job ID, attempt and pause/completion reason; existing pipeline/Extension logs retain step detail.

## Validation boundary

Offline tests and real paused GUI CRUD prove queue persistence/routing, not multi-job paid generation. Installed SmartFlow mixed Product/Story E2E remains separate. Do not claim a new Extension release or use Codex clicks as proof that the SmartFlow extension generated the work.
