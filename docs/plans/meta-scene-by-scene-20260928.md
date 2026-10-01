# Meta scene-by-scene production — 2026-09-28

## User direction and scope

Target: **image 1 saved -> video 1 saved -> image 2 saved -> video 2 saved -> ... -> Final**. Finish one scene, save and verify its result, then start the next. Assemble completed clips at the end.

This is an implementation plan only. No runtime change, version bump, build, provider request, job resume, Chrome reload or app restart is part of this planning turn. The user stopped the Codex monitoring trigger; it remains paused.

- Change media sequencing for the ChatGPT Web -> Meta AI Story Shorts/Long route. Keep outline, validated full script and chapter preparation unchanged.
- Preserve existing successful scenes, saved prompts/references, selected model, audio, subtitle, music, aspect and cover settings.
- Coordinate the desktop and Extension together: the browser cannot declare a scene saved until the desktop verifies its file and receipt.
- Leave Google Flow, Gemini, local image-motion, Drama and mixed-provider/per-scene video plans on their existing paths. Do not silently enroll those jobs or flip their providers.

## Verified current behavior

- Long v2 writes an outline and all chapter analyses (ten scenes per chapter), then creates and saves images serially. Meta video creation starts only after all images are ready. This is not 38 simultaneous generation requests.
- core/story_manager.py sets scene_pipeline_version=0 for Long v2. The existing ChatGPT per-scene gate is Flow-specific. Do not enable it for ordinary Meta by changing that number alone.
- ui/main_window.py::_collect_story_meta_clips already supports only_scene and validates stored receipt, local file and SHA. Reuse that exact single-scene operation.
- ScenePipeline complete means a rendered segment with audio, whereas LongMetaBatchComposer currently applies whole-story audio once. Reusing its completion flag indiscriminately risks duplicate audio.
- story_manager.py::save_partial_image stores partial_generated_images; MetaVideoManager.package currently reads generated_images and scene_prompts/scene_narrations from the manifest. Calling only_scene directly before the full image pass can fail with an image-not-ready or missing-script condition.
- _render_story_worker requires the complete script/image set. That check belongs at final composition, not at entry to the new single-scene video operation; otherwise ChatGPT waits for Meta while Meta waits for all ChatGPT images.
- Meta package overrides can use a verified replacement image and prompt. A successful repair must be accepted through its same-scene successor lineage, not rejected merely because its image hash differs from the original scene PNG.

## Per-scene contract

Introduce a separately versioned Meta media-sequencing contract; the exact field/API names should be chosen during implementation. Do not repurpose the Flow-only scene_pipeline_version=1 flag.

The durable scene record binds the job, execution run, scene index, saved script revision/options digest, original image path/hash, provider request/context, command identity and any authorized repair lineage. Reading progress must never allocate another command or provider request.

Conceptual states:

`image_pending -> image_saved -> video_pending -> video_stored -> scene_ready`

`scene_ready(N)` is the only permission to start new image work for N+1. It means the exact owned Meta result has a stored receipt and a valid local clip with matching SHA and expected media properties. A thumbnail, browser completion message or download-start event is insufficient. This is raw scene-video readiness, not the existing audio-rendered ScenePipeline.complete.

1. **Image:** recover or create only the current scene, then require the desktop image checkpoint ACK. Resolve its exact scene filename/index, not its position in a sorted partial-image list; compute/verify the file hash even for older Shorts without a saved partial hash.
2. **Handoff:** make a scoped single-scene package from the verified image and saved analysis checkpoint. Carry the frozen narration/motion/audio settings and preserve legacy prompt bytes. Do not fabricate all-image slots or set the whole job ai_status=ready early.
3. **Meta:** dispatch the existing single-scene collector once. Persist the command/request identity before dispatch; a lost ACK reattaches to that identity. A repeated gate/status call must not dispatch again.
4. **Result:** verify the local file and receipt. If Meta used a repair, verify the exact successor, context and replacement media against its recorded lineage; retain the original image. Do not make that repair the next scene's reference implicitly.
5. **Advance:** atomically checkpoint scene readiness and the next index. Stale callbacks from earlier runs cannot advance the job. While waiting, expose a real waiting-for-scene-video state so watchdogs do not restart the image collector or mark the whole job complete.

Only one unfinished scene may own new media-generation work for this sequence. Allow the current scene's existing repair helper, but not a second master image worker. Check the ChatGPT helper/tab and busy-lock handoff explicitly: waiting for Meta must not prevent the same scene's approved ChatGPT repair from running, or let that helper overwrite the master conversation's request owner.

## Recovery and finalization

- Reload/reconnect/timeout: reconcile the exact saved attempt and files first. Active generation continues waiting; a transient failure follows its existing proven recovery contract with cooldown. Elapsed time alone is not failure evidence or Send authority.
- Missing ACK after image save, Meta Send, download or scene advance: read durable state before repeating an operation. Never erase an uncertain receipt, resend blindly or overwrite completed files.
- Failure in video N: remain at video N; do not recreate its saved image unless the existing confirmed repair contract specifically requires a new image. Failure in local composition: reuse saved clips/audio, with no provider generation.
- Login, quota, explicit cancellation and ownership conflicts retain truthful blocked/review states. This sequencing change does not promise automatic resolution of external restrictions or silently skip a failed scene.
- After every expected scene is ready, run the existing Shorts/Long composition path with saved audio/subtitle/music choices. Reuse stored Meta clips; do not trigger another full video-generation pass. Apply each final audio mix once.
- Validate Final, then complete any requested cover before the existing queue-completion transition. A scene-ready event is never whole-job completion. Final/cover/queue ACK recovery must not duplicate composition or advance twice.

## Implementation order

1. Fix the independently proven name-binding transport mismatch first. Staged candidate and 46-check offline reproduction: build/story-binding-transport-20260928/. It is not applied to canonical459. It must not reset the existing pending request.
2. Implement the desktop versioned ledger and exact partial-image/script adapter in the Story/Meta managers. Add a Meta-specific single-scene worker route; the current default scene worker dispatches Flow and cannot simply be reused unchanged.
3. Add the owner-fenced bridge/Extension gate and durable command deduplication. In chatgpt.js, invoke it after each image checkpoint and also when reusing an already-saved image. Wait for verified video readiness before continuing the image loop. Preserve existing Flow routing.
4. Integrate current-scene Meta recovery and helper ownership; add truthful UI progress such as "Scene 2/15: image saved, creating video". Check watchdog, cancel and reconnect handling across both providers. Do not report Extension/job complete after one scene.
5. Join the existing finalization path, reuse stored clips, and test audio/cover/queue completion once. Retain all-image validation at Final without making it a single-scene precondition.
6. Add explicit continuation handling for eligible existing jobs, then perform focused and full regression verification. Pair a new unoccupied Extension/desktop/helper release only after source is stable. Do not overwrite459 or any older immutable package.

## Existing-job continuation

- New eligible jobs may freeze the new sequencing contract at creation. Existing jobs need an explicit, durable adoption transition after checking saved media, pending requests and owners; no migration on read or ordinary status polling.
- Reconcile any already-sent image/video operation before beginning missing earlier work. Preserve original receipt bytes and resolve installed identity/storage ownership before resuming.
- For STORY-20260928-29347A, keep all seven local images and recover the already-generated scene8 from its original request; do not generate scene8 again. Then process the first scene without a saved video, reusing its saved image. Do not jump straight to creating image9 while earlier scenes still lack video.
- Keep saved clips wherever already present and valid; validate rather than regenerate. Gaps in the image list must not renumber scenes.
- Only eligible ChatGPT -> Meta rows among the existing five queues enter this contract. The three local-video rows retain their original route; cancelled/deleted jobs never return. Do not create additional queues for verification.

## Separate planning change

Writing the script itself one scene at a time is not the same as serial media production. It requires a new scene-plan contract bound to outline, scene index and previous continuity summary. Do not merely change long v2 batch_size from10 to1: the current validators and pending_request are chapter-bound. Preserve already-approved script. Implement only the scope confirmed for that stage, separately from the current transport hotfix.

## Verification before activation

- Actual single-answer transport through name-binding pre-Send guard; normal success and manual draft/busy/attachment/cancel/foreign-owner rejection.
- Actual desktop partial-image/analysis -> Meta package -> Extension -> stored-video -> next-image integration, not isolated mocks that bypass package prerequisites.
- Two-scene event order must prove image1-save, video1-save, image2-Send, video2-save, Final. For a new job there is never image2-Send before video1 is verified stored.
- Crash/resume after image save, after Meta Send with lost ACK, after video stored with lost gate ACK and before scene advance; no duplicate provider Send or next scene before stored.
- Duplicate gate polls, competing workers, stale callbacks, missing image slots, old completed scenes, changed options and invalid file hashes must not bypass exact scene ownership.
- Current-scene Meta redesign with a verified replacement image must finish without a false original-image mismatch; the saved next-scene reference remains unchanged.
- A waiting ChatGPT master and its eligible Meta repair helper must not deadlock on global busy/ownership guards. No automatic Stop or restart of healthy work.
- Existing images and clips reused without overwrite; cancelled/deleted jobs remain excluded.
- Shorts/Long aspect ratios, saved voice/subtitles/music and Final single-audio behavior unchanged. Test interruption during Final/cover and before queue-completion ACK.
- Flow, Gemini, local video and existing mixed-provider scene plans retain their original behavior.
- Pair the next unoccupied version across desktop/Extension, focused tests then one final full suite after source freezes; immutable old packages retained.
- Installed workflow is a separate verification at a safe authorized boundary: confirm the paired versions and preserved identity/storage, observe a scoped two-scene order and playable Final, then expand verification. Matching versions or offline tests do not prove the live request has recovered. No paid/new job or activation is authorized by this plan alone.

## Planning result

Ready for implementation in the order above. This document is the only change made by this planning turn; the source remains on its prior runtime and the monitoring trigger remains paused. No full-suite rerun is needed for a plan-only edit.

## Implementation follow-up — 2026-09-28

The user subsequently approved implementation. Paired source0.15.460 implements the serial media barrier, exact partial-image adapter, durable dispatch identity, explicit legacy conversion and final readiness checks. The bridge reuses the existing Meta adapter directly rather than starting a second desktop video worker; this avoids waiting for all images or a competing worker lock. Full script preparation and the original final/audio pipeline remain unchanged. Evidence and activation limitations are tracked in docs/reports/meta-scene-sequence-460.md. No live job conversion, queue resume, provider generation or Chrome reload occurred; monitoring remains paused.
