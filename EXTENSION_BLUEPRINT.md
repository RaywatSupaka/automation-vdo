# พิมพ์เขียว Chrome Extension — SmartFlow AI

## Candidate `0.15.507`: guarded reference reattach

The 506 live trace showed `attachment_count_changed` before Send. A visibly empty and file-input-empty composer may continue to the existing saved-checkpoint attachment path. Multiple, busy, failed or hidden references still block Send; the upload path verifies the reattached scene before submission.

## Candidate `0.15.506`: replay preflight diagnostics

If the explicit replay preflight changes, log a non-content reason, request state and attachment count before stopping. The live 505 attempt failed before Send; 506 preserves that stop and makes the failing condition inspectable.

## Candidate `0.15.505`: owner-authorized Story image replay

## Candidate `0.15.504`: prior-run Story image draft watchdog

Result-only Resume now bounds an unchanged prior-run `dispatching` receipt when the request is absent but the exact prompt still occupies the composer. Three read-only observations over at least 15 seconds raise `STORY_IMAGE_RECEIPT_REVIEW` with `PRIOR_RUN_UNCONFIRMED_DRAFT_PRESENT`. The monitor does not clear the draft, refresh the tab or replay Send. The 503 acceptance-path guard remains.

## Candidate `0.15.503`: uncertain Story image Send watchdog

When a trusted ChatGPT Send gesture has no matching user turn after the acceptance minute and the exact owned prompt remains in the composer, perform three read-only checks five seconds apart. A persistent missing request becomes an explicit `STORY_IMAGE_RECEIPT_REVIEW` with `SEND_UNCONFIRMED_DRAFT_PRESENT`, preserving the pending receipt, image reference and draft. Never infer that an uncertain Send can be replayed. The background heartbeat remains a connection/status signal; it does not prove provider acceptance. Activation is pending while the installed 502 Story runs.

## Runtime installed `0.15.498`: accepted Story image from an earlier run

When Continue reads an accepted or uncertain image receipt whose run ID differs from the active Story run, an empty response after refreshing the saved conversation is not proof of provider failure. The content script retains the original receipt and conversation and raises `STORY_IMAGE_RECEIPT_REVIEW` before any reminder or new image request. Installed 497 reopened a new tab and sent scene 6 again after exactly this cross-run gap in Story E25264. Paired 498 is installed with the original Extension ID after the Story became idle. The guard has focused tests but no live provider output yet.

## Runtime installed `0.15.497`: completed Story image with a stale ChatGPT progress marker

The Story result monitor retains exact conversation, request and image ownership. When the current response contains one full-size completed image and its completion controls but a progress marker remains mounted, it observes the same image and marker for at least 60 seconds. If no Stop button is visible, it treats only that stale marker as finished and collects the existing image without a new Send. A visible Stop, changed image or changed marker continues to block collection. Progress reports include the separate Stop and progress-marker counts. Paired 497 main and the original Chrome Extension ID are installed and connected. Scene 6 saved under 497 after a duplicate cross-run Send; final Story output and the exact original scene-5 busy signal remain unverified.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.496` — one composer scope and exact reference count

The 495 live Story completed all ten images and its local video, but the resumed scene-5 request counted two composer attachments for one expected reference before Send. The retained-reference preflight and upload path used different composer-shell fallbacks when the editor lacked a closest form. Version 496 uses the same shell resolver for attachment detection, retained-reference proof and upload. A Story reference-image request now stops before Send if the composer attachment count is not exactly the expected source count or upload is busy/failed. The paired DEV desktop and original Chrome Extension ID connected at 496; this new guard has focused fixtures but no live provider request yet.

## เวอร์ชันก่อนหน้า: `0.15.495` — Story retained-reference whitespace proof

The 494 live resume stopped again at scene 5 before Send: the saved prompt and live composer were the same full text after whitespace normalization, but ChatGPT rendered some line breaks as spaces (2175 versus 2169 characters). Version 495 uses full normalized text equality for the retained-reference proof, retaining receipt ownership, exact reference filename, one attachment, same conversation and no sent request checks. The paired DEV desktop and original Chrome Extension ID connected at 495. A provider Send/result from this exact path remains unverified.

## เวอร์ชันก่อนหน้า: `0.15.494` — Story retained-reference resume

When resuming a prepared Story image request, the content script may reuse one retained previous-scene attachment only if its receipt is still prepared and unsent for the same job, run, scene and conversation, the attachment displays the exact generated reference filename, the composer contains the exact wrapped prompt, and no matching user request or active response exists. It does not upload a second copy. Changed drafts, extra attachments, busy uploads, sent requests, or uncertain receipts still stop before Send. Focused source fixtures pass; the original Chrome Extension ID and restarted DEV desktop are connected at 0.15.494. A real provider result for this path remains unverified.

## เวอร์ชันก่อนหน้า: `0.15.493` — Story resume single-tab guard

On Story resume, a stale stored tab ID now resolves to exactly one already-open saved conversation tab before creating a replacement. Multiple exact matches stop before Start. Desktop pairing and the original Chrome Extension ID connected at 0.15.493 in DEV MODE. A live Continue stopped at an old unconfirmed scene-3 attachment before Send; successful provider output remains unverified. Version 0.15.492 was the previously installed Story bootstrap release.

For a new ChatGPT Story only, a root tab adopted while empty but changed before Start is left intact; Background opens one owned root tab. If ChatGPT restores old plain text in this newly created tab, Background clears only that tab's composer, then verifies the same document is empty and stable before a single Start. It may repeat the clear once if the draft hydrates again. Conversation, attachment, active response, login, or uninspectable documents are never cleared. Existing Story resumes, accepted/uncertain sends, old tabs and Gemini routing remain unchanged. See `docs/reports/story-bootstrap-auto-clear-492-20261002.md`.

The DEV app and original Chrome Extension ID are connected at 0.15.492. A new live Story/provider output has not yet tested the clear path.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.491` — Story bootstrap review, installed bridge verified

The installed 490 guard stopped an actual Story before Send but did not identify the exact preflight cause or show a notice in Chrome. New Story starts now skip tab IDs previously owned by automation, require a stable empty document after a short hydration delay, and wait briefly when the composer has not mounted. If the final probe fails, Background shows a visible review notice on that ChatGPT tab and records only the tab ID and bounded reason (`draft_present`, `composer_not_ready`, etc.). It never copies draft text, clears the draft, or retries a provider Send. The old Story remains in error for explicit review. Gemini selection and owned resume remain unchanged.

The DEV app was restarted through its original entry point and the existing Chrome Extension ID reconnected as 0.15.491 through the update barrier. A real new Story/provider output has not yet been tested.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.490` — Story bootstrap tab guard, installed bridge verified

For a new ChatGPT Story request, Background inspects each complete root tab without changing it. It reuses only a document with one empty composer, no attachment, conversation or active response. If none qualifies, it opens one new root tab and checks that document again before loading the Story content script or issuing Start. A draft that appears between selection and Start causes `AI_WEB_WAIT_REVIEW`; the draft is preserved and no provider request is sent. Resume and owned result reading continue to use their recorded tab; Gemini routing is unchanged. The installed Extension reconnected as 0.15.490 with its original ID; actual provider output remains untested.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.487` — canonical pair, Chrome activation pending

Moved the existing JobRouter timeout helper to `src/core/timeout.js` and imported it from the router. Legacy `background.js` and `chatgpt.js` logic is unchanged apart from the required version/helper tags. MAIN487.0 and the 41-file Extension487 package were built together and integrated after a guarded cold handoff. Installed Chrome/version/path/provider acceptance have not been verified. Full suite remains non-green; see the 487 report.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.486` — canonical composer-owned Send/submit contract from466

Content/background resolve the same unique ready nativeform-ownedSend/submit target; disable/Stop/delete/feedback/unknownlabel/ambiguity veto.484prepress center/scroll/interior hit-tested fallback remains before the only trustedpress; no Enter/syntheticSend/postpressretry. Typed image-tool/subreason persists withoutprompts; image-toolgate/recoveryunchanged.485immutableheld for Flowhelpertagmismatch,486tag-only correction. PairedMAIN486.0 is canonical after15-targetcoldhandoff,10694protectedhashesunchanged. Native19/145checks and exact5reconciliation pass; original485fullNON-GREEN retained, installed486/providerSend unverified. No Setup/credits/oldresume. See docs/reports/chatgpt-submit-contract-486-20261001.md. Older entries below are chronology.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.484` — ฐาน466 เฉพาะการเตรียมกด Send

แผน A: จุดกลาง; B: เลื่อนหนึ่งครั้งเฉพาะปุ่มอยู่นอกจอ; C: ไม่เกิน8จุดภายในปุ่มที่ hit ปุ่ม/SVGลูกจริง ก่อน press เท่านั้น. ผูก final arm กับ draft/owner/node/geometry/viewport/scroll/point/focus; ไม่มี Enterหรือpressซ้ำหลังผลไม่แน่นอน. Gemini/Meta/Flow/receipt/queue/UI ใช้466เดิม; Flowเปลี่ยนเฉพาะbuild tag. MAIN484.0+Extension484แพ็ก40ไฟล์ตรงกัน แพ็ก466ไม่ถูกทับ. Native14/final-focused67pass; Chromeเปิดใช้จริง/วิดีโอจริงยังไม่ยืนยัน. ดู docs/reports/chatgpt-send-fallback-484-20261001.md; ข้อความรุ่นปัจจุบันที่เก่ากว่าด้านล่างเป็นประวัติ.

CURRENT466 ONLY BY USER REQUEST (2026-10-01): browser_extension restored exactly to original40-file0.15.466, including flow-0.15.466-20260929.1. Immutable folder/ZIP466 match every source byte; no new helper, phone viewport, disabled-Flow marker or later recovery is retained in runtime. Desktop-required466 is restored alongside original MAIN/source. Source pair verified; Chrome installed identity/path/version and connection466 remain unverified. Do not overwrite immutable artifacts, replay old Send/queues, bypass blocked browser-admin tools or upgrade without a new user request. See docs/reports/rollback-all-466-20261001.md. All newer contracts below are chronology only.

480 source/folder/ZIP pair is now integrated with canonical MAIN480.1; installed Chrome still reports479, so paired runtime is not activated. No new Extension bytes were changed by the desktop-only hotfix. Existing extensions-admin policy restriction is not retried or bypassed; awaiting one current Loaded-from response to preserve ID/storage. Selected approved plan29A8B8 retained, no provider Send or actual image/Final proof yet. See480.1 report's later handoff section.

480.1 is a DESKTOP-ONLY observability hotfix, not a new Extension version. All42 frozen Extension480 files and its immutable folder/ZIP are unchanged. The desktop now transports the existing bounded attachment diagnostics to status/trace; exact operation anchoring prevents unrelated detail fields from being accepted. No editor rebind, foreign-input allowance, ownership relaxation, duplicate generation or Send authority change. Original firstimage owner veto still needs actual named-predicate evidence. See `docs/reports/plan-image-handoff-480-desktop-diagnostics-20260930.md`; no activation/provider Final claim.

480 candidate preserves existing normal/foreign/unknownSend upload gates. Prepared boundary equality now compares the exact4keyset/types/count/hashes semantically, not JSON dictionary order. Bounded `source_attachment_preflight` diagnostics expose only namedfailure + booleans/count + before_upload/after_upload, never text/images/sourceURLs. Original selected firstimage uploadfailure remains undiagnosed; don't silently rebind editor or permit foreigninput. See `docs/reports/plan-image-handoff-480-20260930.md`; not yet installed/providerE2E.

## Canonical479 — fresh answer continuation (activation unverified)

Runtime follow-up: actual root main479 is active (UI26324/engine8320, bridge requires479); existing Chrome profile has only one connected478 client, incompatible. No generation/background, old queue paused/running0/oldqueued4. Installed479 identity/path/pairedactivation and real Final remain unverified, with no provider Send/credits. Preserve the existing identity/storage and immutable folders; no workaround for the previous extension-admin policy block.

Completed owned malformed responses use the pending-step recovery transaction with saved references and options. Creating a fresh tab is not successful startup: wait for a committed ready target, pin its Chrome document, start/acknowledge its worker and retain sanitized phase/error evidence. No swallowed launcher failure, receipt reset or automatic duplicate allocation. A typed Shopee Meta-prompt format successor preserves the already saved scene image and original accepted prompt receipt; it is separate from analysis and native-unavailable recovery. Canonical source and actual main-root EXE are now paired479 after the guarded backed-up cold handoff; immutable42-file Extension source/folder/ZIP parity and387 protected files unchanged are verified. Canonical integration61/61 passed20.484s with no drift. This does not verify the installed Chrome Extension's identity/path/version or real provider output; full3042 remains non-green with no newly failing IDs versus478. NEW Shopee jobs save atomic per-scene plan/image/Meta-prompt JSON before the corresponding ready ACK/provider barrier, without legacy migration. No provider credit use or Setup. See docs/reports/gpt-answer-recovery-479-20260930.md; never reapply the handoff or overwrite older versioned artifacts.

## New Shopee serial contract / paired 477

Current canonical source and immutable deliverable pair are477 (42 files exact); main EXE477 built/integrated, not Setup. Chrome loaded path/version/identity and actual provider Final are not yet observed. Preserve old immutable artifacts/storage and never reapply handoff or bypass the blocked Chrome-admin surface. Older476 isolated paragraphs below describe the cumulative base, not current integration status.

`chatgpt.js` marker1 attaches 1–3 frozen ORIGINAL product refs to EVERY scene image request, without a generated-image donor. After the saved image callback, it attaches only that exact saved scene image to the owned GPT text request and uses the desktop one-use intent before Send. Typed Meta-prompt state never masquerades as analysis recovery. Stable owned JSON `video_prompt` is saved with image/owner binding; Meta must store its matching playable clip before the next scene. Unknown Send stays waiting/read-only; malformed completed prompt JSON requires review, not another Send. Existing generic Story behavior remains. Fixtures are not installed-provider/Final evidence. See docs/plans/shopee-gpt-meta-v1.md; preserve the existing Chrome identity/path unless an explicit supported migration is agreed.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.476` — GPT + Meta focus, isolated

Capability `workflow_scope_v1:1` requires an exact paired main476 and explicit scope query before command leasing. Only Shopee capture, ChatGPT Product/Story, Meta video and owned read/cancel/cleanup paths remain enabled. Flow/Gemini provider entry, host injection, autonomous old-job recovery and Flow downloads are disabled without deleting old receipts/media. A trusted exact-build command/job/run/scene/request/context permit in Chrome session storage restores only its current collector after worker restart; browser/Extension restart clears authority, and unknown Send never authorizes another Send. Candidate475 is held for the reproduced memory-only collector stall. No scene2 attachment fix or installed Final is claimed from this narrowing change. User chose step-by-step program work; the clean GPT-only prototype is paused, not substituted for the clip program.

MAIN474 / Extension474 source now integrated and the main EXE rebuilt (2026-09-30), NOT Setup. Targeted canonical integration30/30 passed;945 tested hashes and41 source/folder/ZIP files exact,47 protected hashes unchanged. Chrome currently loads unchanged immutable473, not474. Activation/identity migration and actual new Final remain unverified. Do not overwrite loaded473, resume old receipts under a new ID, or reapply isolated patches. See docs/reports/main-project-474.md; older candidate status below is historical.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.474` — isolated, not activated

Prepared Story image recovery must retain the exact canonical conversation and current receipt/scene/input/review/run identity before fresh-tab handling. Missing legacy scene-1 source permits one durable inactive canonical reader with exact approved prior-request proof, never Home replay or receipt reset. Native document proof and cancellation/dispatch/late-result guards remain mandatory. Product checkpoint relay validates current tab ownership and forwards run_id. Canonical Chrome473 and its jobs remain unchanged; real provider recovery/Final unverified. Provisional Flow native capture is excluded. See docs/reports/extension-real-test-474-20260930.md.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.473` — isolated candidate, not canonical/activated

Read docs/reports/fresh-provider-recovery-473.md. User-requested fresh Home/GPT conversation applies only to completed stable exact-owned recoverable replies and the saved pending step. Preserve late results, original references and completed media. This is isolated source, not an installed version. Real login/quota/policy stays actionable; no provider Send, reload or installer by this task.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.472` — Flow model fallback integrated; activation pending

See docs/reports/flow-model-fallback-472.md for actual handoff/activation state. background.js distinguishes truly absent/disabled models from offscreen controls using flow_settings.js menu evidence. Optional auto_model_fallback (default true) permits a single pre-Generate substitution to Omni 1.1 Flash, not retries or other setting changes. Re-observe on verification; never mutate the original scene plan or click in verify-only. flow.js reports typed current-owner model decisions; desktop filters current run/version and UI deduplicates notices. Existing Send/stale-plan/media guards remain. Desktop and helper marker pair with 472. No installer, live-provider test or user Chrome reload.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.470` — Owned text intake and lossless pronunciation candidate

Canonical source now integrated with desktop470 and packaged40-file ZIP; installed Chrome activation remains user-owned/unverified. Do not reapply the staged handoff or restore469. No installer or live generation test. Canonical integration131pass/1skip; full transport-test interruption and recheck details in the470 report.

`CHECKPOINT_STORY_ANALYSIS_ANSWER` verifies existing job/run/tab/provider ownership plus current conversation before authenticated raw intake. One exact completed code block is preserved; multiple blocks remain ambiguous. The desktop owns revisions, field scope, approval and cooldown; the shared ChatGPT/Gemini loop persists Send intent before submitting each text repair and re-reads the original owned turn after uncertain Send/restart. Exact delivery may retry after lost ACK/storage failure without sending anything to AI. Account/policy replies do not enter format repair. Approved response needs the durable hash/result before media. Existing media ordering and per-scene provider selection are preserved; Product serial v2 prototype was withdrawn after a mixed-provider compatibility audit. Flow marker is pairing only, no Flow generation policy change. No installer, Chrome reload, user-job migration or paid provider test; see docs/reports/analysis-recovery-470.md.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.469` — Customer viewport prepress geometry and owned Gemini image remount (canonical integrated; not activated)

Main source now contains the exact approved469 candidate after an idle/no-Chrome check; integration report docs/reports/main-upgrade-469.md. User retains Chrome installation ownership. No profile/ID/storage changes, loaded-folder overwrite, provider Send or foreground test. Do not reapply the staged handoff or older releases.

Meta Send remeasures the SAME document/owned draft/attachment/button after debugger attach. A native hit-test may rebase CSS coordinates once BEFORE press, followed by a second proof at that point. No scaling by OS DPI. After press the original point is frozen; changed target/Stop/draft/document/owner cancels release outside the page. No resend, receipt reset, policy/retry/budget change. ChatGPT/Gemini/Flow send logic unchanged; Flow/background marker changes are pairing only. See docs/reports/customer-portability-beta21.md.

Gemini generated-image receipt revalidates the live owned-request reader and exact asset URL, then uses its current decoded IMG node. A DOM remount of the identical owned asset is not a new result and must not be rejected merely because node identity changed. Changed URLs, foreign scene/request and before-send assets remain rejected. No blanket last-image selection, receipt reset or generation retry. Fixture reproduces the old rejection and passes the narrow repair; no customer Error Log exists to establish that this was the remote failure.

### Previous 0.15.468 — Canonical editorial checkpoint and persisted approval

The shared ChatGPT/Gemini editorial writer cannot advance on a missing/null approval. Adopt only current-job canonical notes and durations from the desktop ACK. Preserve every existing Send/result ownership fence, provider selector and serial media barrier. Background/Flow marker changes are pairing only. Cumulative467 provider recovery remains intact; report docs/reports/editorial-persistence-468.md.

### Previous 0.15.467 — Meta Thai outage / Story prepress receipt / immediate error refresh

Canonical source now includes467 after the user closed SmartFlow; installed466 was not reloaded or replaced. See docs/reports/provider-recovery-467.md. Both classifiers recognize the exact Thai infrastructure outage without masking other policy text. ChatGPT reads the exact fresh owner before rejecting prepress and uses immediate native-error refresh with a durable one-reload guard. No provider Stop, real-job mutation or live activation.40-file package/source parity and30JS syntax passed; final2779/2771pass/8skip/0failures/errors.

Canonical cumulative464+465+466 integrated2026-09-29; one existing Chrome466 client is compatible with the reopened main desktop466, confirmed by actual popup466/466. Chrome profile Keerati / ID idlkladboobfhkdebkjmmngpghnkajkf remains loaded from immutable deliverables/SmartFlow_AI_Extension_0.15.466; no reload, install, uninstall or path migration. All40 Extension files match source/folder/ZIP,30JS syntax pass. Integration471:468pass/3missing-media skips/0failures/errors; no real-provider generation tested. Read docs/reports/main-upgrade-466.md. Earlier no-activation statements below describe preparation, not the current pairing.

ChatGPT generic text/image helpers require the unique fresh exact user turn, stable owner and cleared live composer before acceptance; Stop/count alone do not qualify. Gemini image uses owned request/cleared draft, preserving durable single retry and every transient wait veto. Meta exact prompt/reference echo additionally requires the composer draft and attachment to clear. Flow continuous unknown dispatch remains unknown and reaches the existing bounded FLOW_SEND_REVIEW, not fabricated generation. Real queued/active/results retain normal waiting and no-resend guards. No live activation; cumulative464+465 preserved. See docs/reports/provider-send-receipt-466.md.

Desktop owns editorial approval and two durable repair attempts for new product jobs. Shared writer checkpoints BEFORE sceneContents/images; failed drafts are not ready. PRODUCT_EDITORIAL_SENDING persists request identity before Send under existing owner guards; resumed sending reads the exact conversation/request without replay. Unknown Send, refusal and malformed responses never become permission to bypass the gate. See docs/reports/product-editorial-465.md. Includes464, no browser activation or immutable-artifact overwrite.

### Previous candidate 0.15.464

Versioned speech_delivery_instruction travels through shared ChatGPT/Gemini analysis and formatting repair. It is desktop-authored metadata, never an alternate script. New-contract speaker validation rejects unknown names before legacy normalization. Motion planning preserves SPEECH SCENE placement and requests visual-only prompts; desktop owns exact dialogue and appends the canonical audio block. Background/Flow build labels pair464; Meta Send/Stop/download implementations are unchanged. No installed activation, provider credits or silent legacy migration. Report docs/reports/professional-speech-464.md.

### Previous canonical 0.15.463

Canonical source and paired desktop were updated together at user request on2026-09-28. No Chrome reload/installation was performed: the user will install it. Verified40-file ZIP/source/folder parity, SHA25661921919B23C44F598D28957801804FBFAF889CCAE5D80A3A17922277D573ECF. Details: docs/reports/main-upgrade-pointing-463.md. Do not mistake unchanged installed Chrome for a source downgrade or reapply the staged patch.

Shared ChatGPT/Gemini image controller reads the exact saved Product v3 pointing_review choice and bounded desktop product_visual_instruction. Require that instruction before image work, append it to each owned scene context, and do not add the legacy visible-face/full-body garment instruction. Analysis repair preserves the product script and frozen creative brief. No provider selector, Send, receipt, video barrier or retry authority changes. Includes approved461+462; not installed. See docs/reports/shopee-pointing-review-463.md.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.462` — Meta safety service outage (staged)

Only the observed infrastructure-failure sentence is exempt from the safety-keyword gate; additional policy/quota still wins. Owned complete stable idle no-video proof and empty composer permit fresh-Home retry after cooldown. A repeated outage enters the original-provider two-stage helper through desktop arbitration. One durable successor/helper, capped backoff and history survive restart. Late media, busy, unknown Send, drafts and cancellation stay protected. Cumulative461 included; no activation. See docs/reports/meta-safety-service-462.md.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.461` — Conversation transport recovery (staged)

Recognize only a visible native error/retry panel outside messages on an owned chatgpt.com/c/ URL. Reload once with a document fence; persist a tagged replacement-tab intent only after a distinct refreshed document still has that error. Read the same conversation when it recovers. If the replacement also has a stable native error, explicit user authorization permits fresh conversation replay of ONLY the pending Story analysis/image step. Archive original request/receipt, keep backend_result=unknown, reuse the replacement tab as clean Home, bind the new document and claim once before Send. Lost create/Start/claim ACK never grants another tab or unconditional Send. Completed image checkpoints and Long outline/chapters remain unchanged; the full saved image request and references feed existing image generation. A late original result returns to its owned reader before the fresh claim. Drafts, active progress, changed checkpoints, login, refusal and cancelled/changed owners veto this exception. Motion stays same-URL read-only; cover and helper owners retain existing recovery. Source is isolated, not installed or merged into canonical460. Report docs/reports/chatgpt-unavailable-461.md.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.460` — ChatGPT → Meta ทีละฉาก (verified/packaged; activation pending)

บันทึกภาพ N → Meta สร้างและบันทึกวิดีโอ N → จึงสร้างภาพ N+1; ใช้บทครบเดิมและรวม Final/เสียงครั้งเดียวภายหลัง. โหมดใหม่แยกจาก Flow gate; desktop ตรวจไฟล์และ receipt จริง มีรหัสคำสั่งถาวรกันส่งซ้ำเมื่อ ACK หาย. งานเก่าเปลี่ยนได้ผ่านการยืนยันเฉพาะงานเมื่อไม่มีคำขอค้าง ไม่เปลี่ยนคิวอัตโนมัติ. แก้ name-binding ให้รับ exact single-answer wrapper โดยคง owner/Send guards. ดู docs/reports/meta-scene-sequence-460.md; ยังไม่ activate Chrome ไม่บิลด์ installer และทริกเกอร์ติดตามยังปิด. หัวข้อรุ่นก่อนด้านล่างเป็นประวัติ.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.459` — Story receipt owner / deferred refresh (verified; activation pending)

Focused52pass; full2685/2677pass/7skip/one documentation-header failure, then docs-only correction and final24pass.838source/test files stable;29JS syntax/39-file package parity. Actual installed459 workflow is pending, not implied by fixtures.

background.js::refreshStoryChatGPTResult fixes the proven pre-reload metadata race: save preclaim receipt in the durable refresh budget; after a final live veto restore that exact row only with full claim/receipt/document/cancellation proof. Keep deferred audit; no broad equality exemption, receipt reset or provider replay. Current-owner retry after Continue/new document remains guarded. Actual-source cross-layer fixture tests/story_image_refresh_owner_459.cjs covers original/restored/reminder image and ACK/race cases.

Desktop primary status prefers a fresh paired client but keeps every connected client visible and exact version leasing unchanged. Report docs/reports/story-image-owner-20260928.md; source459 verification/activation pending, installed458 original scene8 image retained.

## Runtime ก่อนหน้า: `0.15.458` — Meta Stop-title collision (source verified; historical activation record)

Final full2671:2664passed/7skipped/0failures/errors,835 source/test hashes unchanged;29JS syntax and39-file Extension source/folder/ZIP parity passed. Installed Chrome458 remains unverified; beta.17/457 stays unchanged.

Meta `inspectMetaDOM` now recognizes exact Stop control labels/test IDs and restricts text-only Stop to the visible composer. A conversation title containing Thai หยุด or English stop is not generation evidence. Original request/image ownership and all real Stop/Send/download fences stay unchanged. Route: `browser_extension/src/platforms/meta-ai/video.js`, `tests/meta_stop_title.cjs`, `tests/test_meta_stop_title.py`. Live457 recovery and458 validation are distinct; see `docs/reports/meta-stop-title-20260928.md`. No provider generation, Chrome reload or installer in this update.

## Prior Runtime `0.15.457` — remaining-scene provider plan

Opted-in Product Story commands carry an immutable scene_video_plan claim: scene index, selection revision/id, attempt id, provider and settings hash. Validate against the current desktop package before settings/Send and propagate the binding in progress/download/Meta results. Saved choices do not Stop current generation, clear receipts or reuse an old result as a new request. Legacy unplanned commands retain their existing ownership rules. Flow discovery must carry model-menu observation status through desktop to UI; exact model and dependent setting verification remains mandatory. Source validation/package status: docs/reports/scene-video-plan-457.md. No Chrome reload, live provider generation or installer.

## Prior Runtime `0.15.456` — paired main recovery integration

Canonical source now includes the reviewed456 C1 recovery and matching desktop version, while keeping the latest desktop-only UI changes. Protocol3 binds refresh cycles to exact accepted original/reminder owners and distinct Chrome documents; refresh while busy observes only, idle missing-result proof enables one durable fresh successor with the full original prompt/reference. Keep legacy protocol2, cancellation, cooldown, source-image exclusion, late-original ownership and lost-ACK reconciliation. Main verification/activation status: `docs/reports/main-pairing-456-20260927.md`. Do not replace newer main files with the old staged source ZIP. No new permissions, provider generation or customer installer are required for this integration.

## Prior Runtime `0.15.455` — one owned result, mandatory prompt instruction

Verified offline and packaged, not activated: new ChatGPT/Gemini/Flow/Meta writes require the shared response-format instruction. Missing content helper preparation is fenced to sender.documentId with post-await context/draft/busy checks; no raw Send is permitted from the current content path. Result selection keeps exact request/scene/source boundaries and one stable decoded asset or complete JSON value; Meta comparison offers require separated branch evidence, never merged acceptance or preference votes. Keep busy/Stop/cancellation and all 454 fresh-context guards. Backend Meta v5 owns motion/audio roles; the Extension transports rather than invents dialogue. Final full2531/2525passed/6skipped/0failures/errors,29JS syntax,39-file source/folder/ZIP parity. See docs/reports/prompt-roles-single-result-455.md. No provider generation, installer or automatic runtime activation.

## Prior Runtime `0.15.454` — fresh Meta context recovery candidate

The explicit user restart policy supersedes old URL-only recovery. Missing tab, lost session ownership, or stable ready empty Home requests an atomic desktop fresh_start successor; manual Continue also refreshes ownership for the unfinished Meta step. New owner opens only https://www.meta.ai/ with saved scene inputs, no cached upload/Send/choice flags. Serialize opens per scene, reject invalid successor ACK, retain archived attempts and honor cancellation/cooldown. Reconcile pending/complete request-owned downloads before inspecting the tab. Existing busy generation and known saved results are not reset by polling. See docs/reports/meta-fresh-context-454.md; no installed/provider test or installer claimed.

## Prior Runtime `0.15.453` — Meta Send geometry

Keep the original pointer over the same enabled Send node through Meta CSS active-scale animation; fractional center drift alone is not a changed target. All owner/document/Stop/draft/image guards remain. Bounded send_diagnostic distinguishes pre-press veto, cancelled release, unknown dispatch and completed gesture without permitting a retry. See docs/reports/meta-send-geometry-453.md; no live activation or provider Send.

## Prior Runtime `0.15.452` — creative controls verified, packaged not activated

ChatGPT/Gemini script validation and JSON repair preserve new Product v3/Shorts structure and the exact frozen creative brief. Flow/Meta prompts carry the desktop-owned selected-scene music directive through repairs; no browser-side reroll or extra Send. Logo dragging is local UI/render and adds no provider action. Preserve existing ownership, busy/Stop, unknown Send and consent gates. Validation: docs/reports/creative-controls-452-20260927.md; no installer or live activation.

## Prior Runtime `0.15.451` — pre-installer targeted corrections

Fence Meta Send against changed owner/document/draft/image/Stop/target after ACK and before gestures. Persist the cover original-reference/retry-user chain before collection; old cover prompt identity is unchanged, new versioned prompts honor the custom headline. Popup reports pairing/version separately from engine reachability; untrusted clients receive only public version diagnostics, never a capability. Final2446 tests:2440passed/6skipped/0failures/errors.39-file Extension packaged; installed E2E and installer are not claimed. See docs/reports/preinstaller-fixes-451-20260927.md.

## Prior Runtime `0.15.450` — choose one cover, replace confirmed failed downloads

Cover collection chooses one decoded result from the exact owned assistant response, even if two alternatives are offered. Keep the chosen asset stable and wait for generation to finish; do not vote or regenerate merely because alternatives exist. Only three actual failed image reads with unchanged owner/asset, idle provider, empty composer and prior stored download proof can create one atomic queued successor. Explicitly request one image/no choices for that child. Preserve historical receipts and Final; duplicate callbacks and unknown save ACK never authorize another generation. Desktop wait/status/cancel follow validated same-job parent/child links. See docs/reports/cover-selection-450.md. Source validation is not installed/provider E2E; no active app/Chrome reload or customer installer.

## Prior Runtime `0.15.449` — cover preflight scope and async readiness

Wait for a connected visible composer/form before attachment detection; pass that form explicitly and ignore hidden upload text outside visible attached nodes. Record exact owner/turn/draft/Stop/upload reason and nine bounded checks. Recheck snapshot and selected image-tool chip after ready-event ACK; changed forms reprepare passively while foreign owner/draft remains protected. Existing empty-document refresh and durable Send boundary are unchanged. Native real-parser tests replace reliance on only mocked attachment readers. See docs/reports/cover-preflight-449.md.

## Previous `0.15.448` — cover image-tool preparation recovery

Re-resolve hydrated/remounted composer controls within30s, prove selected chip, and record typed never-dispatched preparation. Cover-only retries wait before trying again; after two failed reads, retire the old worker and refresh only an exact empty owned Home document. Rotate preparation ID before refresh; stale documents cannot report or send. Persist unconfirmed Send before dispatch. No Stop, active-result reset, duplicate upload/Send or implicit job restart. See docs/reports/cover-preparation-448.md.

## Previous `0.15.447` — wait for actual image completion / Create image tool

Observed446 scene9 trace: image_result_verified → image_checkpoint_saved → recovering_stalled_image at15:04:59.447 never presses Stop automatically, including legacy quiet-image handling or after checkpoint. Decoded previews and owned image-ready snapshots still wait for actual idle; next-scene submission also waits. Only explicit user cancellation may Stop; retire_only exits local automation without Stop even on subsequent checks. Content Send and both trusted MAIN-world resolvers reject explicit Stop label/title/testid before pressing. Fresh ChatGPT image, cover, visual repair and once-owned same-chat reminder select Create image before uploads/drafting, verifying the removable composer chip (ลบ สร้างรูปภาพ / Remove Create image). Menu aria-current is only focus. Text/JSON preparation clears only the selected image-tool chip; Gemini is unchanged. Pending/read-only receipts do not select a tool or resend. No installer or provider generation in source tests. See docs/reports/chatgpt-image-wait-tool-447.md.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.446` — same-chat image reminder

Reverse-column ChatGPT newest-end detection uses abs(scrollTop)<=4; normal scroll math remains. After the exact accepted original request with decoded reference, stable post-refresh idle/no-answer evidence can prepare ONE short reminder in the same chat. It owns a separate nonce, proof, document and durable trusted-Send latch. Accepted child proof becomes the result owner; pending child is passive-only across restart/prior-run resume. Late original image or loading before press wins, proven no-press reads the original, and completed technical retry restores the full original scene prompt. Do not reset/re-upload/use a fresh tab for this branch, replay ambiguous Send, or bypass busy/refusal/quota/login/user draft. Source tests are not installed E2E; no reload/installer. See `docs/reports/story-same-chat-reminder-446.md`.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.445` — Story post-refresh collector liveness

After an accepted Story image Send and one guarded same-chat refresh, an observational progress RPC cannot suspend the result reader indefinitely. Background records exact job/run/scene/nonce/tab/document pulses; after 90 seconds of silence it requires an authenticated live desktop run owner, the same current Chrome document, the exact pending receipt and an idle collector ping before reattaching result-only reading. A late or active collector, changed document, paused desktop or unknown Send is not resend authority. This source fix does not restart the cancelled user job or prove installed E2E. See `docs/reports/story-refresh-collector-445.md`.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.444` — Meta image checkpoint before video prompt

The Meta redesign helper now creates one actual new image from the saved original reference, verifies the owned decoded result, and returns its bytes without first asking for a combined JSON proposal. Background waits for the desktop `save_image` ACK and its saved-image URL before starting a separate prompt request with that image attached. A valid prompt is stored through `save_prompt`; only then is the old Meta attempt archived and a new scene context opened at `https://www.meta.ai/`. The image checkpoint survives Chrome/worker restart and a prompt-only manual Continue. One owned format correction is allowed without mistaking its text for a different request. Stale helpers, unknown Sends and other users' drafts do not authorize duplicate submission. Source tests and packaged artifacts do not prove installed/provider E2E. See `docs/reports/meta-two-stage-444.md`.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.443` — explicit Meta Continue starts a clean scene

Desktop manual Story Continue replaces only an eligible unfinished Meta redesign receipt with a new request/redesign ID and no old conversation URL. The old helper cannot claim or Send for the new owner. The new helper obtains one changed image and matching video prompt via the job's saved image provider; after the verified image arrives, Meta opens exactly `https://www.meta.ai/` for this scene, not the previous `/prompt/...`. Repeated malformed helper JSON does not cause repeated GPT questions: at most one scoped format correction, then a reviewable result. Active/unknown Send, saved media, login/quota and policy guards are unchanged. The immutable 443 Extension folder+ZIP are in `deliverables/SmartFlow_AI_Extension_0.15.443[.zip]` (39 files; ZIP SHA256 E7C1255C104CF7F108D0C6B28810FB34958E0519470933D930AB641E57760ED7), not activated. Frozen beta.16 contains 442; installed/provider E2E is pending. See `docs/reports/meta-continue-fresh-443.md`.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.442` — Meta completed technical reply redesign

The exact completed Thai Meta apology is classified separately from general server errors and policy/quota. Assistant answer text excludes toolbar buttons and hidden content; only the exact owned, idle, stable no-video reply with no pending composer draft enters `redesign_prepare`. Desktop retains the original image/provider/prompt, requires a distinct generated image and new video prompt, and returns one fresh Meta context for this scene. The helper uses the saved 16:9 aspect for Long Video and 9:16 elsewhere. Existing generic server cooldown and all unknown-send/active-result guards remain. This source change is not yet verified by an installed provider run.

## เวอร์ชัน Runtime ปัจจุบัน: `0.15.441` — Meta saved-route redirect recovery

The 440 section below is historical; 441 adds the following paired recovery contract.

`src/platforms/meta-ai/video.js`: canonicalize a trailing slash on the same conversation ID; inspect login before route mismatch. On an owned submitted/generating scene redirected to Home, claim `route_recheck`, re-open the saved route read-only, fence `scripting.executeScript.documentId`, then sample empty ready Home after redirect. Only validated `route_retry` creates one clean successor; adopt via existing exact context/previous-request checks. Worker restart discards in-memory stability, not durable cooldown; lost ACK reconciles from desktop. Existing playable video wins, activity waits, another conversation/login/unknown Send/download remains protected. Version441 changes a wire contract and requires the paired desktop. No installed reload or generation in source validation.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.440` (source candidate): Meta AI รับ `aspect_ratio: 16:9` เฉพาะแพ็กเกจคลิปยาวเพื่อคงการส่งงานแนวตั้งเดิม; คำขอและคำตอบต่อเนื่องขอวิดีโอแนวนอนเพียงหนึ่งรายการ. การบันทึกฝั่งโปรแกรมต้องตรวจ MP4 จริง ขนาด/อัตราส่วน/แฮช/เจ้าของฉากก่อนรับผล; ห้ามนับคำบรรยายหรือภาพนิ่งเป็นคลิป. ทดสอบ Meta โดยเปิดหน้าใหม่และส่งภาพสังเคราะห์หนึ่งครั้ง ได้ MP4 แนวนอน 1280×720 ยาว 10 วินาที ไม่มีเสียง แต่ยังไม่ได้รันคำสั่ง SmartFlow Extension ที่ติดตั้งกับงานคลิปยาวจริง. ดู `docs/reports/long-meta-440.md`; ห้ามอ้างว่า E2E ผ่านหรือโหลดซ้ำ Extension ในระหว่างงานผู้ใช้.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.439` (source candidate): Meta confirmed server error/backoff/one successor, ChatGPT technical image error and malformed owned helper-answer repair, document-fenced refresh/worker reattach and exact Flow monitor beyond35minutes. Continue only with matching job/run/request evidence; never infer a failed Send from timeout alone. See `docs/reports/automation-recovery-loop-439.md`. Installed provider E2E remains unverified.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.438` (source candidate): document-fenced Story image refresh and handoff. Persist the pre-reload top document ID, wait for a distinct ready document, and pin helper injection plus START to that exact new document. URL/tab/run alone cannot distinguish an unloading document. Preserve legacy437 receipts and collect existing results without sending again. Report: `docs/reports/story-refresh-document-438.md`. Earlier version headings are history.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.437` (source candidate): stable pre-Send message IDs replace mutable mounted-DOM positions for new ChatGPT image requests. Pending dispatch → owned refresh → page/history-ready check → use result/wait while busy → only verified idle missing result may archive and create one scene successor, preserving prompt/reference files. Protocol2 typed post-refresh evidence is gated by desktop `image_post_refresh_redo.version=1`. Existing receipt/current successor takes precedence over an abandoned desktop URL. Do not claim a provider error from absence, clear receipts, or overwrite completed checkpoints. Source test/activation status: `docs/reports/story-refresh-check-redo-437.md`.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.436` (candidate): image-only assistant gallery after a ChatGPT reasoning block can omit the direct agent-start sibling. Require the direct assistant heading, owned message ID and generated gallery/preview, and retain exact prompt/turn ordering and source-image exclusion. Refresh outcome and bounded result observation must be visible to the desktop. Evidence: `docs/reports/story-image-gallery-436.md`.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.435`: saved previous-scene image is selected before a fresh/proven-unsent Story Send, including repaired/prepared requests. Upload proof must precede Send. Read both legacy DOM and observed current semantic user/assistant/message-ID image-gallery frames with strict prompt/reply ownership. A completed owned missing-reference response on Resume enters reference recovery. Full evidence and limits: `docs/reports/saved-reference-dom-435.md`.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.434`: exact visible ChatGPT `aria-label="ส่ง"` is supported in both trusted Send lookups. Reference repair retrieves current same-job checkpoints rather than only startup snapshots. A terminal-proven standalone branch does not inherit the old helper's exhausted rounds; unknown requests remain protected. Evidence and runtime limits: `docs/reports/chatgpt-send-reference-434.md`. Earlier version paragraphs are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.433` (candidate, not activated): เมื่อคำตอบสร้างภาพ Story เสร็จแล้วแจ้งว่าขาดภาพอ้างอิง ให้แนบภาพฉากก่อนหน้าที่บันทึกไว้เพื่อสร้างภาพฉากใหม่ หากไม่มีภาพที่ใช้ได้หรือยังขาดภาพ ให้เขียนฉากใหม่จากข้อความแล้วลองแบบไม่มีภาพแนบหนึ่งทางเท่านั้น เก็บ owner/receipt เพื่อไม่ส่งคำขอที่ยังไม่ทราบผลซ้ำ และไม่ใช้ภาพเดิมแทนภาพใหม่ รายงาน `docs/reports/story-previous-reference-433.md`; 432 เป็นตัวกลางที่ไม่ควรติดตั้ง

> ดัชนีปัจจุบัน: [พิมพ์เขียวระบบโปรแกรม + Extension 0.15.431](docs/SMARTFLOW_SYSTEM_BLUEPRINT_0.15.431.md) อธิบาย runtime ที่เปิดใช้จริง, HTTP Bridge, owner/receipt, AI Web/Flow/Meta และ release gate; หัวข้อรุ่นเก่าด้านล่างเป็นประวัติ ไม่ใช่คำยืนยันว่า 0.15.431 ติดตั้งแล้ว

เวอร์ชัน Runtime ปัจจุบัน: `0.15.431` (candidate): คลิปยาว v2 บันทึกคำถามโครงเรื่อง/บทชุดที่ส่งจริงก่อนกดส่ง รวมคำถามแก้รูปแบบ JSON แล้วทำต่อโดยอ่านคำตอบของคำถามเดิมที่เป็นเจ้าของงานเท่านั้น ไม่สร้างคำถามรวมแบบเก่าหรือกดส่งซ้ำเมื่อผลส่งไม่ชัดเจน. ข้อมูลภาพฉาก 16–50 ใช้เพดานของงานจริงทั้งตอนรับและบันทึก trace; Shorts ยังยึดเพดานเดิม. งานเดิมและเครดิตผู้ใช้ไม่ถูกแตะ; ยังไม่ทดสอบกับ Extension ที่โหลดใน Chrome และบริการ AI จริง.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.430` (candidate): ChatGPT รับคำขอบน URL ชั่วคราวแล้วเปลี่ยนเป็นแชตจริง อาจยังไม่มี user turn ชั่วคราว; รอไม่เกิน30วินาทีเฉพาะหน้าใหม่ที่ว่าง. คำสั่งวิเคราะห์428 ที่มี inline ` ```json ` ถูก ChatGPT แสดงเป็น `json`; เปรียบเทียบรูปแบบนี้เฉพาะประโยคที่โปรแกรมฉีดไว้ พร้อมตรวจคำขอเต็ม/ล่าสุด/ID และ job/run เดิม. งานที่หยุดหลัง Send accepted เปิดแชตเดิมเพื่ออ่านคำตอบเท่านั้น ไม่กดส่งซ้ำ.429 แบบแก้เพียง hydration ถูกยกเลิกก่อนใช้งาน. รายงาน `docs/reports/chatgpt-canonical-owner-430.md`; ยังไม่ยืนยันผลหลังติดตั้ง.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.428` (candidate): normal analysis JSON uses literal fenced-code text and owned completed format correction. Source desktop persists the format instruction in canonical new requests; no invisible Send suffix or old request rewrite. Flow/motion, media generation and successful receipts unchanged. Report `docs/reports/analysis-json-transport-428.md`; installed provider E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.427` — รวมชุดแก้ 426 และสิทธิ์ดาวน์โหลดรูป Flow ทั้งเริ่มงาน กู้ฉาก และปุ่มดาวน์โหลด ไม่ติดตั้งแทนผู้ใช้ รายงาน `docs/reports/audit-fixes-426.md`.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.426` (source candidate) — คู่กับ Desktop 426; Meta ออกแบบภาพใหม่ผ่าน AI เดิมและเปิดงานใหม่เฉพาะฉากเมื่อยืนยันผลล้มเหลวแล้ว การเข้าถึงไฟล์ต้องเป็น Extension ที่จับคู่ในเครื่อง รายงาน `docs/reports/audit-fixes-426.md` ยังไม่ทดสอบ provider จริงหรือติดตั้งแทน Chrome เดิม

เวอร์ชัน Runtime `0.15.425` — Product Story ที่บันทึกรูปชุดอย่างชัดเจนแนบ product/person/outfit ได้สูงสุด 4 รูป; งานเก่ายังคง 3 รูป. คำสั่งสร้างภาพแยกใบหน้าบุคคลออกจากชุดที่สวม และไม่ใช้รูปค้างใน composer เป็นหลักฐานว่าเป็นชุดของงานใหม่. รายงาน `docs/reports/product-outfit-425.md`.

เวอร์ชัน Runtime `0.15.424` (candidate): installed423 savedคลิป Meta ฉาก1–2 จริง; ฉาก3 Meta เสนอ `different take`/ชุดมิดชิดและชวน `try/create that version` แต่423 ไม่เข้า one-shot follow-up.424 เพิ่มตัวตรวจข้อเสนอชนิดนี้ภายใต้ completed-owned/no-video/stable/empty-composer เดิม; ไม่ส่งซ้ำเมื่อ busy, unknown, policy, quota. รายงาน `docs/reports/meta-different-take-424.md`; การสร้างภาพใหม่ผ่าน AI Web อีกตัวเป็นธุรกรรมแยกที่ยังไม่เปิดใช้งาน.

เวอร์ชัน Runtime `0.15.423` (candidate): installed422 ยืนยันคลิป Meta ฉาก1 จริงแล้ว แต่ฉาก2 ตอบข้อเสนอเวอร์ชันปลอดภัยภาษาอังกฤษและถูกปล่อยรอ.423 เพิ่มการจับ `wasn't/was not able to create` กับ `I can help with a safer version` โดยใช้ one-shot same-chat follow-up เดิม ไม่ส่งซ้ำ ไม่ถือข้อความเป็นวิดีโอ และไม่แตะ policy/quota. งานเดิมพักไว้พร้อมคลิปฉาก1 และแชตฉาก2. รายงาน `docs/reports/meta-safe-followup-423.md`; วิธีเปลี่ยนภาพ/พรอมต์ผ่าน AI Web อีกตัวเป็นงานแยกที่ยังไม่ได้ติดตั้ง.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.422` (source staged, not active) — Meta completed one-off offer to create a safer scene is distinct from a video result, policy refusal and two-option offer. Accept once only after exact owned user/reply, stable completion and a durable one-shot desktop claim; then inspect only the new answer for a playable video. Unknown Send, busy, quota, categorical policy refusal and changed conversation still block. New desktop prompt v4 affects only new jobs; old v1–v3 are not migrated. See `docs/reports/meta-safe-followup-422.md`.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.421` (source staged, not active) — Shopee detail capture uses visible/structured product metadata and up to three further passive reads after title/images. Blank image metadata never becomes the page URL. Desktop Product Story prompt is now concise and product-first; Meta v3 is shorter, while older job prompts and receipts stay unchanged. See `docs/reports/product-prompt-capture-421-20260923.md`.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.420` (source staged only) — Shopee Product Story capture now binds the saved Product Job, request ID and Extension command ID, verifies readable local image files before AI handoff, and resumes pending capture from the Product continuation panel. Prior `0.15.419` storage-order and capture-status safeguards remain. No installer or live activation; beta.13 remains418. See docs/reports/product-story-capture-resume-420-20260923.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.418` — unconfirmed Story motion Send uses one guarded same-chat reload/read after60s instead of immediately propagating the timeout. Exact late acceptance continues normal reading. Snapshot scalar reference descriptors only, never serialize DOM/React nodes. Keep requested checkpoint, saved images/plans and once-per-context nonce claim; no unknown-send reset/new-tab/resend. Read docs/reports/unconfirmed-motion-refresh-417.md (final418). Installed415 unchanged; no installer or live reload.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.415` — persist exact7s-stable completed native image failure in guarded refresh claim. If same-chat readiness fails60s without later activity/media, archive the accepted receipt and pass original prompt/references/checkpoints to existing fresh-image worker. Ready reload still reads original result. Busy/media latch, user draft, cancellation, changed owner/receipt and storage ACK remain vetoes; unknown Send/policy/login/quota are not failures eligible for replay. Visible composer chosen from all candidates, not hidden first match. Read docs/reports/refresh-failure-415.md. Main-only; no installer or live reload.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.414` — single-answer wire/canonical parity for all ChatGPT motion body layouts and plain repair-helper Resume. Initial/continued motion requests must recognize the exact original task despite our own terminal transport instruction; never accept arbitrary changed text or send again on missing ownership. Existing413 guarded stream recovery retained. Read docs/reports/motion-transport-414.md. Main-only; beta.12 remains413, no installer/reload/provider generation this turn.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.412` — shared single_answer.js adds one-answer wire instruction at every ChatGPT/Gemini/Meta/Flow writer, without mutating stored tasks. Exact suffix-aware canonical reads and complete wire Send verification preserve receipts. Meta current native preference-pair/file-unavailable handling plus fresh failed-scene Continue; no vote, no duplicate unknown Send, no saved-scene restart. docs/reports/single-answer-meta-412.md; installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.411` — exact completed generic ChatGPT/Gemini JSON error in a PRE-IMAGE proposal can enter existing fresh-scene transaction, matching backend begin authorization. Old review archive -> one new controller/helper ->410 automated JSON correction/new image/motion -> one new Flow project. No reopening old project/master plan, no unknown-send reset, no successful-scene regeneration. docs/reports/failed-scene-restart-411.md; installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.410` — new Flow alternative helpers opt into continuous completed-answer JSON formatting. runFlowAlternativeHelper.parseReply retains typed fields and real review flags; bad syntax/schema may ask text correction again only from an exact owned completed non-refusal reply. Durable per-stage intent/origin, cancellable2–30s backoff, before-Send guard and parent format progress. Unknown/busy/draft/attachment/refusal/auth/cancel stays protected; no live record migration or media replay. Report docs/reports/flow-format-recovery-410.md; installed410 E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.409` — reportWebActionProgress maps job-kind story to bridge AI channel chatgpt, so refresh failure cannot hide under Flow shot0. Generic tab waiter fixes read/listener race with registered-first listener plus passive polling/cleanup. Already-acknowledged ChatGPT result refresh uses exact-owned conversation/composer readiness with draft veto,1s passive polls and180s bound, not another reload or Send. Only guarded refresh startup uses that readiness; ordinary provider startup unchanged. Error/cancel remain truthful. Desktop shows ordinary stopped Shorts without resurrecting dismissed work. docs/reports/refresh-handoff-409.md; installed409 E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.408` — desktop ready_home_replacement proof recovers only completed Home/motion_sent false-review handoff: exact request/digest/source fingerprint/prompt, verified saved new-image hash, no project transaction or replacement Generate receipt. Browser missing cache/old run/loopback alias may be reconstructed; active/submitted/fresh or conflicting candidate cannot. Existing one-controller/permit recheck and fresh-project transaction retained. Desktop routes this explicit Resume straight to Flow, then hands off only after scene media complete. docs/reports/flow-direct-resume-408.md; installed408 E2E pending, no installer.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.407` — Home promotion/gallery media is not an owned failed-scene result. Only a matching explicit fresh-start terminal can disregard those media before the new-project handoff; genuine activity/approval/drafts and project outputs still veto. A precise paused Home motion_sent replacement may reuse its saved ready candidate/image with fresh desktop permit, matching verified package, retained source proof and no project/Generate receipt. Pending manifest handshake until permit recheck prevents another bootstrap race. No second helper, old-project reopen or receipt clearing. docs/reports/flow-home-recovery-407.md; installed407 E2E pending, no installer.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.406` — passive automation liveness audit. Monitor epoch/finally prevents storage-error dead air and stale callback reentry. Durable four-row fair outbox preserves failed reports, serializes ownership removal and retains legacy-key replay. Verified download completion gets its own durable report before command success. ChatGPT passive receipt-read/draft veto does not consume the one guarded refresh; dispatched/unknown reload remains one-shot. No provider Send, model, credit, scene/media or policy change. Source/fixtures separate from installed404. docs/reports/automation-liveness-406.md; no installer.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.405` — fixes automatic content-script reentry while creating a fresh Flow controller. Allocate blank, register owner and fresh proof, navigate Home, acknowledge fresh_start_pending without old-project inspection, then let one worker start the existing compliant scene helper. Only exact completed-review/pre-helper failures may abandon their controller under a new explicit command; no replay of sent/unknown work. Report docs/reports/flow-bootstrap-405.md.404 below is historical; no installer.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.404` — explicit completed pre-image Story review uses a new controller tab and new AI proposal/image/motion before a fresh Flow project. Supersedes403 old-project routing. openFlowReviewRebuild journals intent before tab creation, registers exact run/tab, revalidates permit, and invokes the existing start_alternative contract once. Duplicate command adopts its successor even after the desktop no longer exposes review_checkpoint. Home monitoring requires the matching manual review and fresh-start marker; arbitrary Home navigation remains non-recoverable. No old project navigation, media deletion, unknown Send reset or provider-policy bypass. User tests personally; no automatic reload. docs/reports/flow-fresh-start-404.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.403` — exact desktop-reviewed source project for explicit Story pre-image Resume; separate historical completed-review proof after native error tile disappears. Home navigation waits for the right document and worker lock. Preserve active/unknown image sends, drafts, receipts and all other projects. New helper/fresh-project validation checks its saved review identity, never fakes a no-charge failure. Source26 regression cases passed; installed403 generation not yet tested. No installer. docs/reports/flow-review-project-403.md. Older entries below are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.402` — source-only creative failed-scene recovery, no installer. New Story helpers carry creative_revision_version1 and creative_round from desktop. Completed proposal feedback can request a different event/script in the same owned chat with saved intent and cancellable max30s backoff, not replay unknown Send. New image motion review can archive/advance only an acknowledged image_saved round; old-result CAS and idempotent lost-ACK replay guard it. Ready candidate.prompt is the desktop effective_prompt, including revised actor speech, for every fresh-project/reopen path. Actual unresolved content concerns stay honest; no false approval or likeness relabeling. Legacy/Product modes unchanged. Full2090:2089passed/1skip,38-file package parity; installed402 E2E pending. docs/reports/flow-creative-recovery-402.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.401` — source-only candidate, no installer. Empty/malformed/partial completed Story bindings retain valid pairs and request only unresolved evidence, at most2 extra text requests per pair. A per-job/provider SHA256 plan context stores proof/attempts before Send; unknown outcome never resets or resends. Same conversation/latest user/completed answer, idle draft/no attachment, job/run and durable claim checked before Send. Anchored names, foreign/invented bindings and old media remain protected. Existing ChatGPT/Gemini Send and Flow400 logic unchanged. Report docs/reports/story-binding-recovery-401.md. Installed provider E2E pending; bridge unavailable, no reload. Older sections are history.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.399` — packaged with customer beta.9. Story image wait checks self/descendant aria-busy/data-is-streaming/progress in current response scopes (or missing-request history). Earlier frames do not block a matched current request. Flow refreshCompletedFlowResult requires fresh job/run/shot/project and no real activity/approval/new result, rechecked after claim and in450ms callback. Explicit read-only inspection never reloads; automatic owned result-only resume may. Queued-prose100% recovery and once-only budget survive late veto. No Send/upload/reset/model-cost change.72actual-source checks; final2066passed/1skip,215runtime fingerprints unchanged,38-file source/folder/ZIP parity. Installed native beta.9/399 host smoke passed, but installed Chrome/provider E2E and clean-machine still pending. User398 not reloaded; retain profile/ID/loaded path on deliberate upgrade. docs/reports/program-extension-audit-399/README.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.398` — accepted Story image request missing from DOM now gets one guarded same-chat reload before review, then strict original-image receipt recovery. Global Stop/conversation progress veto even when the request node is missing. Exact saved prompt/URL/turn, no newer/conflicting user request, stable30s/3samples, accepted nonce, persisted identity budget and final live guard required. Initial-send monitor supplies full prompt; resumed owner binding updates its monitor. No Send/reset/download-owner relaxation; Flow logic unchanged except build, existing100% reload retained. See docs/reports/story-missing-request-398.md. Final2021/434.497s and focused215 passed; candidate validated, installed E2E pending.397 storytelling remains unchanged.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.396` — accepted Story ChatGPT motion blank-answer recovery. Exact latest full request/message, idle empty composer, no response/media/progress,90s stable proof → one same-chat reload → existing requested checkpoint read. Durable per-scene-context budget survives restart/signature/run changes; no new Send/upload. Initial submit wait and same-motion Resume supported; helpers/cover/Gemini/Product analysis unchanged. Paired desktop required; installed E2E pending. docs/reports/pending-motion-refresh-396.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.394` — opt-in product story-first review. Initial prompts still come from the saved desktop package. Only product_short + request.product_script_options v1/story_first_review adds the saved product_script_instruction to existing JSON formatting/missing-scene repairs for both ChatGPT and Gemini. No new Send/retry/reveal/upload logic; existing393 URL binding retained; Flow build-only. docs/reports/product-story-first-394.md; installed E2E pending. Older current-version labels below are history.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.393` — fix confirmed392 false review on ChatGPT /c/WEB:<uuid> → /c/<uuid>. Bind the same job/run and unique exact latest full request, retain observed message identity, and check again after awaited reveal. Other chat/run/message changes still require review. Shared Send/image/Flow/Gemini/Meta algorithms unchanged; Flow build number only advances. See docs/reports/chatgpt-route-393.md. Installed393 verification pending; older current labels below are history.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.392` — current-request ChatGPT result reading/reveal and whitespace-equivalent Flow composer readiness. Bounded three reveals with user-input grace, scoped conversation scroller, cancellation and run/conversation checks; never Send/Stop/refresh from reveal. Collapsed decoded images require a non-user conversation frame and intrinsic256px minimum; Product results use exact owned request scope. Flow compares the complete normalized prompt, retains original saved text/hashes and submission receipts, coalesces duplicate package reloads and accepts only current pre-submit errors. Desktop selects Flow-origin diagnostics for relayed Flow failures. No membership gates restored. Details: docs/reports/result-readiness-392.md; installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.391` — no Extension membership/API Token checks; desktop Login remains independent. Installed verification pending.

391 supersedes390 licensing below: no background/content pre-Send authorization, no popup membership card/polling, no bridge command/cover/Meta license gates or Extension token endpoints (410). Desktop start/queue only checks desktop Login. Preserve localhost internal session capability, version/run/lease/tab/receipt safeguards and all provider algorithms. Random profile storage identity is retained for update continuity, not authorization; no vault migration. See docs/reports/extension-no-membership-391.md. Older licensing notes are historical.

Runtime390 supersedes dual-Token popup: Extension stores only its existing random profile and internal bridge capability in memory; membershipRequest supports status/authorize only and requires source=desktop/contract_version=1. Desktop production membership alone activates/renews its cloud lease. A fresh matching-version Chrome heartbeat binds profile to origin/client; wrong version/profile/origin, offline expired lease, desktop logout/kick/lock/expiry denies new command leases and physical Sends. Historical Extension vault is not read/written/deleted; no server change. Accepted results and passive commands retain original ownership guards. Popup offers connection status/recheck and instructions to open the normal desktop EXE, not a second Login. Product prepare_repair contract2 freezes structured new visual concept/changes/fact-preservation; exact repeated concepts or source/prior-candidate pixels cannot count as new media. Existing in-flight legacy proposals are adopted unchanged, not resent. See docs/reports/desktop-linked-extension-390.md.

Runtime389: Product `product_prompt_repair.enabled` enters original-provider text-only helper with the same original references (max3). One canonical complete prompt, typed review/compatibility/facts flags, no instruction bypass; real image generation returns to original owner tab. Backend durably claims helper BEFORE tab creation and each image Send; lost ACK/storage loss cannot allocate another helper. Service failures may repeat with5–60s cancellable backoff; one substantive policy redesign per slot, repeated refusals require review. Previously saved images/analysis and unknown reservations/downloads preserved. Legacy packages retain old donor budget. `docs/reports/product-prompt-repair-389.md`; installed E2E pending.

Runtime388 supersedes385 same-image service repair for NEW confirmed failures: getFlowPackage enables rebuild_scene_on_failure for Story/Product. Controller starts one original-provider alternate-image helper per exact attempt failure; background binds failure_id to monitor.startedAt + fingerprint. Existing alternative stages propose one safe scene, generate/save a NEW image, then inspect that new image for one full video prompt before fresh Flow project/Generate. Product keeps narration/facts; Story retains authorized revised scene and actor-dialogue gates. Backend rotates ready replacements only on a new failure + exact predecessor, archives all old rows/files and rejects reused failed images. Pending or approved legacy helpers finish unchanged. No repeated helper for duplicate failure, no replay of unknown Send, no policy flag override. See docs/reports/flow-scene-rebuild-388.md.

Runtime387: current continuous Flow waits do not stop on75second/30minute age alone. Project/repair identity binds every observation; cancelled repair/home-page events cannot revive the original scene receipt. Desktop resets attempt counters and extends only fresh acknowledged continuous observations, not stale heartbeats; uncertain sends no longer enter Stop/new-project retry. Confirmed385 service repair continues without a round cap. Same original image/provider, real terminal, single validated prompt, membership/cancel/settings/credits/content-review and no duplicate Generate guards preserved. See `docs/reports/flow-continuous-watch-387/README.md`.

Runtime386: keep the existing version-independent random membership profile. Popup observes broker remembered/restoring/profile_changed, polls status without activation, and does not ask for Token during same-profile renew/desktop disconnect. Revision guard rejects old status after explicit Login. Token input still clears immediately; no token/session/renewal credential in Chrome storage. Same-path/profile updates restore existing online rights; kick/logout/expiry/new profile retain manual gates. First-install stable source path `browser_extension`; versioned deliverables are immutable artifacts, not default Load unpacked targets on every update. User approved migration preparation only; do not silently overwrite385 artifact, copy storage/change manifest key or transfer rights. See `docs/reports/extension-login-persistence-386/MIGRATION.md`. Flow385 recovery functionally unchanged, helper build paired386.

Runtime0.15.385: native timeout/other non-policy Failed cards require exactly one new owned tile with reason/no-charge/Retry stable across two observations, unchanged narrative and no active render, new result, credit/rights dialog. Same-run automatic recovery only; explicit inspections are read-only. Confirmed service failures send the exact current image and original/last prompt to the original ChatGPT/Gemini helper for one JSON prompt, never automatically rewrite Story content. Existing durable same-image download/fresh-project/Generate receipts are retained; recheck late results after reference download. Unknown non-video replies, old/ambiguous tiles and real queue activity do not authorize retry. Details/tests: `docs/reports/flow-service-repair-385/README.md`. Manifest/helper/desktop paired385; no installed E2E or provider credits used.

Runtime0.15.384: scoped membership gate. Popup sends explicit Extension Token once to background, which exchanges it through the desktop broker; Chrome stores only a random profile ID, cloud credentials stay in Windows vault. Every new command lease/physical AI or Flow Send and Meta Send intent requires paired same-member scope. Checkpoints, provider progress and downloaded results retain their existing ownership/ACK logic after expiry/kick; no receipt reset or automatic activation/retry. Desktop and helper build paired384; source/fixture report `docs/reports/membership-384/README.md`, installed E2E pending. Prior provider contracts remain unchanged beyond pre-Send authorization.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.383` — ChatGPT Story helper reference/name contract. Read canonical /api/stories/{id}/chatgpt-package, check job/provider/saved scene labels/local file URLs, attach the same up-to-three initial references through the existing ready-check uploader. Reject foreign helper drafts/attachments. Completed missing-name candidates, including old ready records, consume the next existing repair round with expected-request CAS, archived predecessor and duplicate-successor adoption. Content-review, invalid schema, prohibited instructions, unknown sends or exhausted rounds do not qualify. Parent validates before updating its original image receipt and waits for image download/desktop ACK. No Gemini, Meta or Flow Send changes (Flow build tag paired only). docs/reports/scene-helper-383.md; installed smoke pending.

Desktop meta-single-green-v2 (2026-09-19): no Extension source/protocol change; stays382. New desktop Meta prompt2 requests one direct video; legacy prompt hashes and382 exact-request/result/choice-follow-up contracts retained. Actual-source controller tests accept the new desktop package. Local green compositing/cache/progress does not create provider commands. Details/installed limits: docs/reports/meta-single-green-v2.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.382` — confirmed two-option Meta offers are awaiting a selection, not failed-generation retries. Select option2 in the existing chat with a persisted follow-up, one-shot desktop Send authorization, fresh prepress DOM checks and exact second user receipt. Inspector binds ONLY the subsequent assistant/video; original proposal cannot become the video result. No image reupload/new tab. Other provider paths unchanged; docs/reports/meta-choice-382.md. Installed smoke pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.381` — Meta exact completed reply recognizes couldn't/could not/unable/failed; inspect final toolbar, all video nodes and busy indicators. Two unchanged observations >=5s debounce completion, not a generation timeout. Desktop retry_prepared archives the failed attempt and allocates one successor with unchanged source/prompt; Extension opens one fresh owned tab and uses normal attachment-ready → Send → download → desktop ACK flow. At most2 retries persisted across resume; uncertain sends, policy/quota and active results stay protected. docs/reports/meta-retry-381.md; installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.380` — actor motion and alternate-image planning explicitly forbid speaking visual directions or adding captions; exact speaker/listener turns remain authoritative. No Send, attachment, polling or receipt changes. Desktop new-job conversation contract and verification: docs/reports/conversation-only-380.md. Installed E2E pending; earlier runtime labels are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.379` — Meta composerFound/readable text is separate from composer click point. A filled long draft with an occluded center advances to uploading only if the unique current editor exactly matches the owned prompt, no previous user turn and no busy/Stop. Empty drafts still require a verified click target and durable insertion intent. Same-stage wait messages are deduplicated and never reset Send/receipt state. See docs/reports/meta-prepared-379.md. Earlier headings are historical; installed379 pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.378` — opt-in Shorts actor dialogue; ordered actor speech and listener reactions in initial and repaired motion prompts. Preserve native audio, silent-scene intent and existing receipt/Send controls. See “Shorts actor dialogue / 0.15.378” below and docs/reports/shorts-actor-dialogue-378.md. Installed E2E pending. Earlier version headings are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.377` — new isolated Meta AI video adapter, exact composer image and prompt → owned user/reply → request-specific Chrome download → desktop validated ACK → owned-tab close. Meta image inputs live outside the portal dialog; bind the visible composer, not the first hidden input. Provider key meta_ai; old meta stays retired. No ChatGPT/Gemini/Flow generation changes. docs/reports/meta-video-377.md. Installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.375` — owned motion service-error native Retry; persisted at-most-once claim, same-request wait, no prompt/upload duplication (installed E2E pending). See docs/reports/motion-service-retry-375.md. Gemini and Flow controls unchanged.

374: early Background draft/hit-test/attach failures before any mouse press must return notDispatched, only after validating any Story claim has not already dispatched. Actual/uncertain gesture evidence remains untouched. Shared whitespace normalization and two bounded read-only mismatch resamples, never fuzzy text acceptance or draft rewriting. Desktop routes resume to the pending image's saved chat; content still verifies ownership. Exact legacy373 no-click trace may recover only an intact matching draft with no dispatch/accepted request/busy state and receipt CAS. docs/reports/story-preflight-374.md.

373: waitForResponseIdle must receive completedCount from its caller, never read runJob-local lastCompletedImageCount. Actual image5 -> idle-wait regression runs without a fabricated global. Before a fresh next Story ChatGPT image, a stable full prior motion JSON with stale global Stop can refresh the same conversation once only after desktop confirms exact saved ready result and prior scene complete, with NO next-image receipt/draft/attachment/active scoped progress. Missing response action buttons alone do not block this desktop-backed recovery; unsaved answers still wait. Preserve all saved scenes, reuse analysis on resume, no old Send replay. Existing next-motion refresh/Gemini/Flow policies unchanged. docs/reports/response-idle-373.md.

372 supersedes371 picker readiness: require exactly one img.asset-thumbnail-image with currentSrc/src, complete, naturalWidth/naturalHeight>0, no busy/animation, two stable samples and prepress source identity. Filename-only cannot select. Animations/progress keep waiting;45s unchanged observation is a stall probe, not a generation timeout. One durable pickerRefresh on proven completed upload permits same-project reload only with fresh no-draft/no-submit/no-render/no-result/no-confirmation/no-cancel/current-owner proof and shared Generate mutex. Resume reselects existing image; pickerRefresh bypasses upload-age cutoff only, never clears receipts/terminals. Used-refresh remains passive/cancellable if still stuck. See docs/reports/flow-thumbnail-372.md.

Runtime0.15.371: Start-frame picker reads nested .asset-title in the sole visible dialog/listbox, exact unique filename and fresh hit-test. Wait while actual loading is visible; only45s unchanged idle picker may stop lookup. Per-sample and before-press job/shot/run/project/reference/pause/receipt checks. Reuse an already-open picker without another Start click. Desktop receives attachment_selecting observations. An owned completed upload terminal can advertise one same-project selection recovery; preserve terminal+attempt audit, require a newer desktop command, no submission/result/confirmation and no second upload. Reopening a closed tab uses only its saved project URL. See docs/reports/flow-picker-371.md; installed E2E pending.

Runtime 0.15.354: close_automation_browser accepts optional cleanup_shot_index only from desktop verified local Flow checkpoint, exact run and shot binding. Shared tab/new run is preserved. Cover ready persists cleanup_pending/cleanup_url; polls retry closure after rechecking ownership and URL, keeping receipt. No Send/generation/AI image logic changes. docs/reports/browser-lifecycle-354.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.370`

367: current owned Story policy card with exact failed title/reason/no-charge/Retry may enter existing repair on the second unchanged DOM read, without the legacy30s minimum. Require persisted exact project, same run/scene, enabled repair, no real progress/result/approval. Old/ambiguous evidence retains old observation path. docs/reports/flow-terminal-367.md.

367 alternate helper: proposal_check receives typed duplicate_story feedback from the desktop, persists a new correction intent and asks the same provider for a genuinely different safe event. Never generates from duplicate narration. Correction Resume reads only the exact saved request, does not resend; original image references, prior successful scenes and unresolved review decisions remain intact.

366: ChatGPT completed-response stale Stop recovery before the next persisted unsent motion request. Stable completed owned motion JSON or just-ACKed scene image, no draft/attachments/local progress; durable one-refresh budget, final live guard, same-tab same-run resume. Does not alter Gemini, cover helpers, unknown sends or Flow generation. See docs/reports/completed-response-refresh-366.md.

362: Product3–15 scene count comes from the saved Story package. Native-reviewer delivery retained when alternate scene narration changes. Provider Send/receipt behavior unchanged. docs/reports/product-planning-362.md.

360 Gemini motion: owned markdown aria-busy=false confirms completed output; unfinished JSON syntax is not generation proof. Actual Stop/progress waits; unknown state waits without an elapsed-time error. Completed stable malformed output reaches existing format review; exact restarted object can recover with original flags. ChatGPT unchanged. docs/reports/gemini-motion-360.md.

355: Gemini per-scene handoff carries provider; missing-provider diagnostic is explicit. No Send, image collector, Flow prompt or navigation changes. See docs/reports/gemini-scene-gate-355.md.

353: Flow alternate collector bypasses legacy image timeout/Stop. Empty completed image DOM may refresh the same exact owned conversation once, durably claimed and live-guarded; resume reads only, never resends. Desktop exposes checking_empty/empty_after_refresh, retains saved media and existing confirmed new-failure scene loop. See docs/reports/alternate-recovery-353.md; installed recovery pending.

Product Story jobs keep mode=story and per-scene gate. chatgpt.js adds explicit ordered product/person reference roles to each image request; existing verified multi-reference attachment and send receipts unchanged. Cast creation is one image only, desktop saves a draft asset and does not start speech/Flow. Legacy Product requests unchanged. docs/reports/product-story-351.md.

New scene_pipeline_version=1 jobs: chatgpt.js finishScene sends STORY_SCENE_GATE via background owner guard; desktop prepares saved partial analysis, renders only that scene and persists video+voice completion before next image. Polling observes state, not a fixed generation timeout. Error/cancellation retains ledger/media; old jobs and Product dispatch unchanged. See docs/reports/scene-pipeline-350.md. Installed E2E pending.

Story/Drama revise_story recovery supersedes same-image-only348: new actual situation, new narration/image, new-image motion, new Flow project. Proposal may material_change=true, but needs_review=false still required. Motion material_change compares to approved NEW story, not original. No flag coercion. Unknown Sends and cancellation retained. See docs/reports/flow-story-context-349.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.348`

Flow continuous repair removes347's two-round terminal only for Flow. Preserve confirmed owned failure, helper at-most-once and validated candidate gates. Same original image and provider; fresh-project transaction each new prompt. No implicit replacement image, no automatic retry of unknown Sends or content-review answers. Desktop round/audit limits paired. docs/reports/flow-continuous-repair-348.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.347`

Current 0.15.347: same_image_only gates every implicit start_alternative call in recoverFlowPolicy. Request original-provider text with original image, validated candidate → original reference → fresh project. Exhausted/review results pause for explicit resume, not image generation. Exact pre-dispatch replacement orphan transitions to review; rejected replacement begin restores a resumable terminal. See docs/reports/flow-same-image-only-347.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.346` — getFlowPackage enables fresh_project_on_repair without forcing rebuild_image_on_failure. recoverFlowPolicy first uses start (same-image text helper); prepare_reference durably downloads original image and records repair_reference.source=original. flowFreshProjectAction validates candidate, original image identity, terminal ownership and exact reference receipt before navigation. Preserve source project archive, other scene checkpoints and old Send receipts; bind one distinct new project and use request-specific repair receipt. Alternative replacement keeps its separate field/path. Do not overwrite in-flight helpers or suppress provider review flags. Installed346 pending; see docs/reports/flow-same-image-repair-346.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.345` — startAIWebJob honors desktop ai_resume targets. Closed/stale-root tabs reopen the exact provider conversation; missing/redirected target and forceFreshTab stop before Send or closing user tabs. Gemini binds first /app→/app/id navigation and a missing remounted container only for a unique identical full request at the same position with an empty live draft. Concrete cross-chat, changed request and ambiguous matches remain review. readPendingAnalysis is passive and validates exact job JSON; no Send, attachment or formatting request. FLOW_MOTION_PLAN persists authenticated sender URL; progress includes page_url and bounded owner-loss reasons. Existing physical Send budgets, Flow controls, images, cover and queue remain. docs/reports/resume-routing-345.md; installed345 E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.344` — shared motionResponseState/extractMotionJson for initial, Resume and candidate motion answers. A temporarily absent Stop plus a stable unclosed object is not completion. Completed JSON uses the current request owner; encoded JSON and optional review_reason remain supported. Read cached answered_text from the live owned answer, not the old string. Candidate formatting uses preparing_motion_format → durable motion_format_requested → validated ready, once only and without another image. Desktop preserves raw audit and blocks ambiguous/semantic/owner conflicts from schema repair. Flow/background physical actions unchanged except paired build. docs/reports/motion-response-344.md; installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.343` — resumeStoryVisualPlan plus desktop story_visual_* ledger: one same-image motion revision, then original-image attachment to the same provider for one corrected starting frame, candidate download and motion validation against its exact hash/context. Unknown image/motion sends resume read-only. Owned latest request, stable decoded image, cancellation and no six-minute generation deadline. Original media/ready plans retained. Flow controls unchanged; desktop paired. docs/reports/story-visual-repair-343.md; installed E2E pending. Earlier current headings are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.342` — accepted Story ChatGPT images use current owned DOM, not a six-minute generation deadline. Both initial wait and receipt Resume keep waiting while generating/loading. Repeated broken-image or completed-empty-response DOM evidence permits one durable same-receipt/same-tab refresh, with fresh owner/latest-request/draft/attachment/cancel checks immediately before reload; never resend or open a replacement tab. Completion still requires stable decoded owned pixels and checkpoint ACK. Real terminal text remains distinguishable from slow generation. Product/Gemini/Cover/Flow behavior is not widened by this fix. Read docs/reports/story-image-dom-wait-342.md; installed342 E2E pending. Older current-version headings below are historical.

Installed341 ChatGPT cover E2E verified2026-09-14: desktop/Extension341, request6ded19ea for00CDCD; filename proof2/2/2830ms, one accepted prompt with two references, one result, savedJPEG1080x1920, retry0 and own-tabclose. No Extension source change after package341. Oldfcf04cd0/2 remains historical; Run Queue does not regenerate it automatically. Detailed runtime/desktop recovery evidence: docs/reports/cover-queue-recovery-341.md. This narrowly supersedes installed-pending below for this cover path, not Flow/Gemini/global reliability.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.341` — cover-only chatGPTCoverAttachmentPreviews supports named role=group HTTPS/empty-alt file tiles plus named nearest-tile fallback; waitForCoverSourceAttachmentProof follows busy upload up to120s/idle30s and re-reads current owner/files/images after progress ACK. No second upload or generation on detection failure. Optional observed/elapsed_ms proof reaches paired desktop. Actual3390/2 regression with live two-image evidence; source fallback sees2 on same page read-only. Normal scene/Flow transport unchanged. docs/reports/cover-semantic-reference-341.md; installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.339` — prepareFlowMotionPlan consumes the paired desktop visual_request; legacy completed compatible-reference/material-draft conflicts use revise_visual once, then resolve the new persisted context on resume. No rejected prior draft in the new request, no flag override, no image regeneration or extra Send after unknown acceptance. Explicit Product scene_index must match image slots. ChatGPT/Gemini actual-source planner is tested against real Python validation in an isolated fixture, not installed browser E2E. docs/reports/product-visual-contract-339.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.338` — prepareFlowMotionPlan gives Product-only continuous same-reference visual scope and review_reason. A completed Product material conflict may enter the existing durable recheck_content once, attaching the same canonical image to the original provider; new concise English prompt keeps facts/narration and Thai-only speech instruction. Flags are never coerced and only a separately validated response reaches save. Cached337 answered records are revalidated, not cleared or resubmitted. Story/Drama, image generation, Send mechanics and Flow controls unchanged. Read docs/reports/product-reference-motion-338.md; installed338 E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.337` — coverResultImages enables intrinsic/declared image dimensions only inside its owned assistant scope, avoiding false zero images in collapsed/background layout. Shared normal image discovery remains unchanged by default. Declared dimensions mean loading, not completion; dedup/loaded≥256/no-Stop/stable3.5s remain. collector_state is bounded status/count metadata, not completion proof. Same-request collect_only recovery/ready ACK/owned tab close preserved. Read docs/reports/cover-intrinsic-result-337.md; installed337 pending, installed336 recovery actually passed.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.333` — cleanup only: closeAutomationBrowser(jobId,runId,commandId,cleanupRuns) derives targets from explicit Job/run bindings, freezes exact target IDs before browser mutation, rechecks rebound/shared tabs and retains receipts. Desktop snapshots cleanup_runs at enqueue to include existing AI/Flow runs, never later resumes. Close errors propagate; success ACK follows completed cleanup; plan is retired only after accepted ACK. Bridge cleans only matching run state and rejects ACK for cancelled/pending commands. Gemini/ChatGPT Send and Flow controls unchanged. docs/reports/lifecycle-readiness-333.md; installed333 E2E pending. Older labels below are history.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.332` — Gemini text-only stable exact Send acceptance (3samples/500ms, live cleared composer), original expected prompt prepress guard, bounded persisted request owner and exact-container answer selection. Missing owner receives30s passive remount recovery; unrelated latest Stop cannot prolong it. Transient candidate blocks retry; previous unchanged full-release60s single retry remains. Desktop retains draft/job and logs GEMINI_TEXT_REQUEST_REVIEW. Preserve331 image/ChatGPT330/Flow; no legacy receipt reset. docs/reports/gemini-text-request-332.md; installed332 E2E pending. Earlier versions below are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.331` — Gemini image first Send waits bounded12s for current draft/upload/idle readiness and rechecks before press. Shared passive60s acceptance watcher latches current request changes; reverting cannot grant retry, late acceptance still wins. Existing one-retry/full-release budget and ChatGPT330/Flow preserved. Diagnostic node/geometry counters split prepress/during gesture; bounded event on_target/time reaches desktop with owned_motion_user_turn. docs/reports/gemini-send-331.md; installed331 E2E pending. Older version labels below are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.330` — empty-new-chat Story Send may resolve root→/c/id only with exact unique first request and pre-Send boundary -1; bind URL/message immediately, persist before recovery download. Existing conversation changes stay invalid, unknown Send never retries. Dispatched329 root receipts recover existing images passively. Background/Flow only version pairing; desktop exposes conversation_pending. docs/reports/story-new-chat-330.md; installed330 E2E pending. Earlier version labels below are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.329` — Story-only fresh exact message acceptance, shared Send/result ownership, durable send_phase and one nonce per dispatch. New prepared receipts can resume preparation; dispatching/legacy awaiting_result cannot grant resend. Background validates claim/owner/readiness before press and persists a nonce marker. No Product/Gemini/Cover/Flow policy changes (Flow build pairing only). docs/reports/story-send-329.md; installed329 E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.328` — StoryChatGPT exact-prompt/answer image scope; no document fallback or pre-checkpoint Stop. Dedup layers byasset, reject old/multipleassets; recovery re-readsDOM bounded30s plus2s stability. Studio result reasons distinguish empty UI from failed Send. Keep cover327,Product/Gemini andFlow controls. Read docs/reports/story-image-scope-328.md; installed328 E2E pending. Olderlabelsbelowarehistory.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.327` — coverResultScope reads the exact assistant conversation SECTION, including sibling image media; no whole-thread fallback. coverResultImages deduplicates layers by canonical image identity and waits for loading/stability/idle; distinct assets remain ambiguous. Same-request collect_only recovery has zero Send/upload/native Retry/new tabs, checks exact latest prompt plus original request-indexed reference names, uses the stored owned tab and capability handshake; old reader needs explicit page refresh. Desktop result_proof is bounded and is not a substitute for saved bytes. Close only after existing ready ACK. Generic scene/Flow controls/retry policies and326 attachment proof unchanged. docs/reports/cover-result-327.md. Older labels below are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.326` — waitForCoverSourceAttachmentProof applies only to activeCoverRequest. Require empty entry composer references; one upload; all expected images loaded/stable and either actual indexed filenames or exact input File objects. Ignore hidden progress and editable prose; preserve cancellation/owner checks, reject changed files/drafts, partial/extra images and unproved identity. Minimal title prompt, normal scene attachments, Gemini historical reuse, Generate/Send retry budgets, ready ACK and owned-tab cleanup remain unchanged. Desktop stores bounded reference_proof; queue completion requires saved cover, not attachment success. docs/reports/cover-reference-326.md.

Desktop cover queue gate (2026-09-12), Extension325 unchanged: ready is accepted only after AICovers.event validates/saves the current image. Desktop additionally requires that exact saved cover file before queue completion/close/cleanup; needs_review/cancelled are terminal requests, NOT successful queue work. Active requests wait, failed cover pauses same Job. Existing AI_COVER_EVENT ownership/ready ACK/close-only-success path is preserved. See docs/reports/cover-queue-completion-gate.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.325` — live DOM audit verifies semantic controls rather than changing Angular-generated IDs. Gemini image retry sourceSignature/busy use current composer previews; page-wide generated-result/history guards and retry budget unchanged. ChatGPT attachment status removes editable prompt prose and ignores hidden progress. Flow control and model mapping matched live all5 menus; no Generate selector rewrite. docs/reports/provider-dom-audit-325.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.324` — Gemini text Send checks current .text-input-field attachments including img alt=attachment, latest message-content, and current job/run/draft. Old thumbnails and toolbar changes do not authorize or block Send. Worker reports specific preflight reasons and attested not_started without a mouse press; content retains this evidence through FLOW_PLAN_REVIEW. Existing Send/retry budgets and normal image paths preserved. docs/reports/gemini-text-preflight-324.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.323` — same-provider safe alternate illustration, new-image motion and a fresh Flow project for the exact confirmed failed scene. Durable navigation/click/bind and replacement receipt; preserve successful media. See docs/reports/flow-fresh-project-323.md. Installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.322` — both cover reference images decode from the request; no URL fetch for inline image2. Minimal title prompt unchanged. docs/reports/cover-second-reference-322.md. Installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.314` — exact assistant cover image ownership and idle/stability gate before save/close. See docs/reports/cover-owned-result-314.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.313`

Current313: scoped mobile completed video tile detection and standalone tile download target. Preserve old result baselines, no Generate/resend, existing once-only100% reload. See docs/reports/flow-mobile-result-313.md. Installed recovery pending.

Current runtime301: exact Gemini capability-only analysis phrase compatibility; bounded existing JSON repair. Keep current motion ownership and successful287 Product handoff architecture. See docs/reports/gemini-comparison-301.md. Older version headings below are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.312`

302: exact Gemini learning-image/guideline completed reply classified for existing scene helper; legacy no-image receipt can enter helper without resetting original receipt. Same provider, max2 durable rounds, actual image ACK then continue. Other provider paths unchanged. See docs/reports/gemini-scene-repair-302.md.

300: ChatGPT motion-only exact full typed object stable60s may be reviewed/saved before stale Stop clears. Preserve flags; no generic JSON extraction/partial answers/other owner, no Stop or Send. Initial and resumed requests use same gate. See docs/reports/motion-stale-stop-300.md.

299: Story accepted image requests wait passively instead of auto-Stop at3minutes or35second empty-response abort. Bounded6minute wait and exact-result receipt recovery preserved. A47CA3 scene10 evidence and tests: docs/reports/story-passive-wait-299.md. Installed smoke pending; never clear an unknown receipt or resend to recover.

298: only scoped Flow settings Enter/Space input gains keyDown text/unmodifiedText. Verify menu opened before reading options; terminal error retains field/requested/observed. Raw-CDP controller fixtures replace synthetic complete key presses. Live installed297 failure reproduced, installed298 pending. See docs/reports/flow-settings-key-input-298.md.

297: removed unreferenced physicalDrag/physicalFileDrop helpers only from ATTACH_LATEST_FLOW_MEDIA. CONFIGURE pins mandatory mobile directly, preserving existing scoped keyboard and error paths. No Send/Generate/receipt change. Paired desktop has per-form reset instead of custom checkbox. See docs/reports/flow-cleanup-297.md; installed E2E pending.

296: mobile no longer optional. Flow content enters mobile unconditionally before upload; settings handler ignores legacy display preference and uses compact. Exact legacy Agent-settings scope supported for keyboard controls. Core/UI always normalize compact. Retains295 Start-frame attachment and294 mobile lifetime. Installed296 generation pending.

295: Start-frame path in ATTACH_LATEST_FLOW_MEDIA precedes legacy gallery Animate only when empty Start is positively located. Exact filename+job+shot, visible dialog ownership, unique option and hit-test; one open/one selection, no Generate or upload. Existing composer proof gates success. Mobile stays pinned. See docs/reports/flow-start-frame-295.md.

294: persistent mobile viewport via installFlowMobileDebugger adapter. SET_FLOW_MOBILE_VIEW validates sender Flow tab and paused state before reference upload; CONFIGURE also pins for discovery. Owned Flow attach reuses debugger and detach is deferred until tab exit; other tabs unchanged. No clearDeviceMetricsOverride after settings. Display=compact schema remains compatible with job/queue snapshots. This supersedes292/291 temporary viewport behavior. See docs/reports/flow-persistent-mobile-294.md; installed E2E pending.

293: read_flow_settings delegates target choice to SmartFlowSettings.selectProjectTab. Accept the selected Flow project, or the sole open Flow project when another page is selected. Reject missing/multiple unselected projects and unrelated hostnames. No AI Send, generation, retry or job mutation changes. Live failure CMD-1E2A1F27E4 is documented in docs/reports/extension-targeted-test-293.md; installed293 verification pending.

292 supersedes291 compact keyboard gate: display=compact uses scoped Enter/Space whether it owns the viewport override or borrows an already-narrow user viewport. Attach/detach only owned debugger sessions; never clear borrowed metrics. After selecting a setting, wait up to six250ms read-only checks for Angular state before declaring failure; no re-click. Existing Generate/upload and other provider Send paths unchanged. See docs/reports/flow-settings-292.md.

## Runtime291: compact settings transaction

CONFIGURE_FLOW_VIDEO_SETTINGS borrows an already-narrow viewport or owns a temporary400x802 CSS metrics override (mobile:false). Restore/own-debugger detach completes before ACK, including unavailable settings and lost override acknowledgements. A failed attach must not detach another debugger. Compact-owned settings use scoped keyboard actions; Generate/attachment/download retain existing paths. Thai labels/durations are canonicalized; absent resolution toggle may be read as fixed only from the unique settings summary. Apply model/type/aspect before resolution/duration; re-read every requested value. Discovery uses one isolated relay, not injecting flow.js, opens settings/model menus and restores their prior open state without selecting a model or generating. See docs/reports/flow-compact-291.md for limits.

## Runtime290: independent post-video AI cover

Background polls authenticated ai-covers/pending, CAS claims before creating a dedicated same-provider tab, stores metadata only, and sends START_AI_COVER with real JPEG bytes. Synthetic COVER-request ownership is bound to provider/tab/run and live desktop state. Content attaches once, selects the job model once, uses existing trusted Send primitives, and accepts only fresh generated image evidence after its exact user request. Activity extends waiting; a completed confirmed image-service failure permits one durable retry, policy/unknown outcomes do not. Ready is published after desktop validation; only the created successful tab is closed, failed tabs remain for review. Worker/desktop restart must not reset receipts. See docs/reports/ai-cover-290.md; installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.289` candidate — all Gemini submitPrompt requests require an exact fresh latest user turn and strictly following assistant. Text coordinator persists initial claim and single retry, checks unchanged DOM and durable nonce before Background press, and returns GEMINI_TEXT_SEND_REVIEW on unsafe/exhausted send. Initial and next image requests still use the existing image coordinator. Canonical entity IDs may bind names locally with audited proof. See docs/reports/gemini-text-send-289.md; installed E2E pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.288` — read_flow_settings command uses authenticated lease/ACK, visible current Flow menu only. CONFIGURE_FLOW_VIDEO_SETTINGS applies model→type→resolution→duration then aspect/x1 and re-verifies all requested values. No silent alternatives or mobile switch.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.287` candidate — exact latest user request required for Gemini motion Send acceptance and response ownership. See docs/reports/gemini-motion-owner-287.md. Normal image/ChatGPT/Flow gates preserved; installed smoke pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.286` candidate — scope compact settings, verify Video/aspect/x1, expose observed options, never send on unverifiable settings. See docs/reports/flow-settings-286.md. Installed smoke pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.285` candidate — exact Gemini motion capability clarification with saved raw answer and one durable repair. See docs/reports/gemini-motion-capability-285.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.284` candidate — Gemini discovery Later only.

Current284 candidate: narrow Personal Intelligence discovery-card dismissal in Gemini only during active jobs; exact Thai Later text + dismiss aria-label; once per visible card. No consent/Send/Flow changes. See docs/reports/gemini-discovery-284.md. Installed smoke pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.283` candidate. Motion JSON types explicit; review returns per-field errors and durable answered result; parse/schema share one text-only repair. Existing attachment282/Send/Flow unchanged.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.282` candidate. Gemini strict composer scope corrected from actual82EF98 DOM; installed resume pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.281` candidate. Gemini filename-optional proof requires exact assigned File objects and a stable loaded composer preview after empty entry. No change to normal image Send. prepare/mark_sending motion actions; installed smoke pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.280` candidate. Motion plan content binding v2 and durable reformat action; no Send/Flow gesture redesign; same provider. Installed smoke pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.279` — candidate, installed smoke pending. FLOW_MOTION_PLAN → protected desktop ledger → image-bound short prompt; Flow repair uses canonical image provider and strict attachment. See docs/FLOW_MOTION_PROVIDER_PLAN_279.md.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.278`. Flow recovery needs_review replaces automatic image fallback; see PROGRAM_BLUEPRINT current278.


เวอร์ชัน Runtime ปัจจุบัน: `0.15.277` — Flow restart result recovery; retains submission receipts on browser cleanup and observes exact submitted checkpoint before any preparation. Paired desktop277; installed smoke pending. Supersedes276 hotfix. Every delivered Extension update must increment version; never publish changed code under the same version. Read PROGRAM_BLUEPRINT Flow restart result recovery.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.276` — Flow policy prompt recovery:2 compliant ChatGPT text-helper rounds, same project/source, separate durable repair send receipts; existing local-image fallback if unsafe/unavailable. No automatic legacy history replay, unknown-send retry or Presenter change. Paired desktop audit; installed smoke pending. Read PROGRAM_BLUEPRINT Flow prompt recovery.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.275` — bounded text-only scene-repair helper; same provider, original image tab, durable request and image receipts, paired desktop audit. Read PROGRAM_BLUEPRINT Scene prompt helper. Earlier current labels historical; installed smoke pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.274` — continuous confirmed Story ChatGPT service-error recovery per user instruction, same prompt,5–60s cancellable backoff, progress not error. See PROGRAM_BLUEPRINT Continuous Story service recovery. Product/Gemini/Flow unchanged; older labels historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.273` — Story ChatGPT stable completed no-image gate and exact Thai service-error one durable retry. See PROGRAM_BLUEPRINT Story Thai service failure. Older current labels are historical; no Product/Gemini/Flow behavior changes.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.272` — optional cover metadata sanitized before existing analysis checkpoint/result. See PROGRAM_BLUEPRINT Short-hook cover. No extra Send, no required cover field, no cover image generation. All271 owned image/receipt rules remain unchanged. Paired desktop; installed smoke pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.270` — long-video opt-in: 16:9, up to 50 scenes, bridge shot limit 50, immutable existing run/receipt safety. Default remains 9:16/15 scenes. Installed smoke pending.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.269` — Story ChatGPT confirmed service failure retries once with durable budget. No retry of unknown sends or policy; older current labels below are historical.

เวอร์ชัน Runtime ปัจจุบัน: `0.15.268` — Candidate: activity-based analysis wait; see PROGRAM_BLUEPRINT "Activity-based analysis wait / 0.15.268". Stop/answer activity renews waiting beyond six minutes; inactivity-only timeout, no resend. Match desktop268. Installed smoke pending.

0.15.266 current: Flow card reason goes to desktop popup/log as failure_reason→flow_failure_reason (plain600 characters, same `.error-message-text` only). Recognize supplied reputational/current-events refusal without broadening queue/active-generation gates. Existing policy fallback stays; Presenter does not promise local motion. Route PROGRAM_BLUEPRINT "Flow failure popup / 0.15.266" and docs/reports/flow-failure-popup-20260907/VALIDATION.md. Candidate installed popup smoke pending.

0.15.265 history: Story-only new owned policy card can supersede unchanged gallery/chat queue prose after30s/3 inspections without active render/result/approval. Store bounded card identity/baseline and observation hashes; reset grace on activity/text/owner/card change. Persist confirmed terminal before report and replay only same run/scene/project. Desktop already renders same-scene canonical local fallback; initial terminal inspection must not reopen it. Product logic and AI Send/image helpers unchanged. Route PROGRAM_BLUEPRINT "Story Flow policy handoff / 0.15.265"; docs/reports/story-flow-policy-20260907/VALIDATION.md.

0.15.264 current: selected analysis answer-body stability; exact unrelated audio Stop excluded only from ChatGPT analysis, genuine Stop preserved. Six-minute bound remains; coded bounded diagnostics survive existing logs. Desktop accepted-analysis timeout no longer reopens/resends. Shared Send/image/Gemini retry/Flow unchanged except synchronized build tags. Route PROGRAM_BLUEPRINT "Analysis completion / 0.15.264" and docs/reports/analysis-completion-20260907/VALIDATION.md. Candidate installed workflow pending; prior current labels are history.

0.15.263 current: confirmed Story refusal fallback is an acknowledged previous image used locally, never a new provider request. Only non-Drama image_motion, exact refused receipt, owned sender/run/provider, saved original donor; keep receipt and mandatory provenance through checkpoint/result. Pending copy resumes idempotently; no fallback for unknown Send, busy, reference request or Flow. PROGRAM_BLUEPRINT "Story confirmed refusal local reuse"; docs/reports/story-refusal-local-20260907/VALIDATION.md. Candidate installed smoke pending. Gemini263 retains the guarded262 image-send retry unchanged.

0.15.261 current: focus owned tab, attach debugger, measure semantic Generate, scroll and prove button/descendant hit after hover, one durable single press, retain old uncertain receipts. Existing high-demand/queue waiting is unchanged per user: no queue-triggered error/reload/resubmit. No-evidence silent send reports FLOW_SEND_REVIEW and desktop forbids retry; not a Flow policy/local fallback. Prompt/image and AI physical-send code unchanged. See PROGRAM_BLUEPRINT current contract and docs/reports/flow-generate-target-20260907/VALIDATION.md. Older release blocks below are cumulative history.

0.15.260 current: exact receipt comparison ignores only object key order, preserving all values/types/array order/ownership. Storage harness now sorts keys so259's real first-image false ACK stop is reproduced. Current owned AI review errors keep the conversation even after an answer empties the composer. Narrow259 first-image recovery requires desktop adjacent pre-send failure trace, no subsequent send/audit/result, exact saved plan and no images, plus receipt identity/run/provider/client/time; otherwise stop for review. No Master resend, receipt wipe or automatic browser close/reopen. See PROGRAM_BLUEPRINT Receipt storage and docs/reports/receipt-storage-20260906/VALIDATION.md; paired260 candidate pending installed E2E.

0.15.259 current: Presenter local pause preserves checkpoints/receipts; fresh inspection command IDs gate Resume; only proven pre-submit same-project work can continue. Story durable scene generation receipts distinguish missing image from pending download/unreadable checkpoint; unknown outcomes never resubmit. Exact provider/tab/run ownership is required on analysis/image/final writes. Shared desktop saved-plan loader and saved-voice reuse; AI owned tabs resume without reload or adopting unrelated chats. Read PROGRAM_BLUEPRINT current checkpoint-resume contract and docs/reports/checkpoint-resume-20260906/VALIDATION.md. Older recovery/refresh recipes below are historical where they conflict; source/tests are authoritative.

0.15.258: Story/Drama names resolve an explicitly paired Thai/Latin display spelling only for non-user-anchored entities. Reject ambiguous derived spellings, malformed/descriptor parentheses, and cross-entity relabels; never translate, rename a registry, or rewrite a scene. Matching Python validator is core/story_content.py. Send-unconfirmed during optional name review reports analysis already received while preserving the same error/code/diagnostics and no-retry behavior. No physical Send/Flow/attachment changes. Fixture STORY-20260906-6E3623 and report docs/reports/story-bilingual-names-20260906/VALIDATION.md. Install258 with matching desktop; installed smoke pending.

0.15.257: เพิ่ม mode=presenter แยกจาก Product/Story wrappers. PRESENTER_IMAGE claim/save ต้องตรง provider/tab/run และ ACK จากโปรแกรมก่อน Flow. ภาพจากข้อความหรือรูปอ้างอิงหนึ่งภาพ ใช้ Flow 3 takes ผ่านขั้นตอนแนบ/ส่ง/อนุมัติ/ดาวน์โหลดเดิม ไม่เพิ่ม physical clicks หรือ retry. การประกอบพื้นสีและเสียงทำในเครื่อง โปรแกรมและ Extension257 ต้องคู่รุ่น. Installed E2E pending; docs/reports/presenter-20260906/VALIDATION.md.

> เวอร์ชัน Runtime ปัจจุบัน: `0.15.267` (Candidate). Current delta: Gemini completed-analysis capability-only disclaimer reaches existing JSON repair; exact whole-reply allowlist excludes mixed policy. Read PROGRAM_BLUEPRINT "Gemini analysis capability / 0.15.267". Older current labels are historical.

0.15.256: แก้แผนใหม่ Story/Drama ที่มีวลีบรรยายตัวตนแต่ไม่อ้างชื่อ ตรวจข้อความครั้งเดียวสำหรับชื่อที่ AI สร้าง ไม่ใช่ชื่อผู้ใช้กำหนด รับเฉพาะวลีเดิมที่ปรากฏครั้งเดียวและตรงscene/entity จากนั้นเติมชื่อในวงเล็บในเครื่อง ตรวจทุกกติกาซ้ำและรอdesktopบันทึกanalysis/proofก่อนสร้างภาพ. ไม่เปลี่ยนบท ไม่ผ่อนตัวตรวจ ไม่ซ่อมแผนเก่า/รีวิวแล้ว/มีภาพแล้ว ไม่retryเมื่อยืนยันไม่ได้. Logแยกตรวจชื่อ/คำตอบ/ซ่อมสำเร็จ; coreตรวจbefore-afterและเก็บประวัติเมื่อผู้ใช้แก้ฉากภายหลัง. คงcompact255 image prompt/Send/แนบ/Flow/คิว. คู่โปรแกรม256 รอinstalled E2E; ผลจำลองไม่ใช่10ภาพจริง. รายงาน docs/reports/story-name-binding-20260906/VALIDATION.md.

0.15.255: โปรแกรมส่ง visual_render_instruction เฉพาะเทคนิคภาพแยกจากคำสั่งวิเคราะห์ Source-free Story/Drama ใช้ storyTextImageBrief: ฉากเดิม+เทคนิค+ข้อเท็จจริงภาพและตัวตนเฉพาะฉาก ไม่มี generic actor/violence/workflow paragraphs; analysis/non-graphic planning และ refusal terminal เดิมยังอยู่. คำตอบขอส่ง “คำสั่ง” ใหม่ไม่ใช่ขออัปโหลด “รูป”; completed no-image ยังหยุดไม่ส่งซ้ำ. 254ติดตั้งจริงยังล้มเหลว แต่ทดสอบ255 helper promptผ่านChromeด้วยCodexสร้างภาพ941x1672สำเร็จ ไม่มีsource. ไม่ถือเป็น Extension E2E. Source-backed Story/Productตรวจ45กรณีพรอมต์ตรง254; Flow/Send/แนบ/ACKเดิม. ติดตั้ง255คู่โปรแกรมแล้วเปิดEXEใหม่เมื่อidle. รายงาน docs/reports/story-first-image-live-20260906/VALIDATION.md

0.15.254: Story/Drama ไม่มีsourceใช้คำสั่งสร้างภาพใหม่จากข้อความทุกฉาก รายละเอียดชื่อ/ตัวละคร/สไตล์ยังอยู่ครบ ไม่แนะนำให้แก้ภาพเดิมหรืออัปโหลดภาพก่อนหน้าที่ไม่มีจริง. ก่อนส่งบันทึก image_prompt_ready ผ่าน CHATGPT_PROGRESS: exact prompt/composer, scene/attempt, source count/scope, visible mode labels และ SHA256 ใน logs/extension_trace.jsonl ของงาน ต้องได้รับ ACK หลังเขียนลงดิสก์; ไม่ทราบ mode ภายใน provider ให้รายงานว่าไม่เปิดเผย ไม่เดา. STORY_IMAGE_AUDIT_UNCONFIRMED / STORY_IMAGE_CONTEXT_CONFLICT หยุดก่อนส่งและไม่ auto-recovery. คง Product/Storyมีsource/physicalSend/Flow/ACK ภาพ. รายงาน docs/reports/story-text-image-audit-20260906/VALIDATION.md; ต้องติดตั้ง254คู่โปรแกรมแล้วเปิด EXE ใหม่เมื่อ idle ยังไม่อ้าง installed E2E สำเร็จ

0.15.253: ตรวจงานจริง9557A5ของ252พบฉาก1ยังไม่มีภาพ ส่ง3ครั้งก่อนหยุดขอภาพต้นฉบับ; logสองรอบแรกไม่มีคำตอบ จึงยังสรุปสาเหตุภายในเว็บไม่ได้. เพิ่มจำแนกคำตอบขอภาพแบบบอกเงื่อนไข และ STORY_IMAGE_RESPONSE_REVIEW สำหรับคำตอบมีข้อความแต่ยืนยันภาพใหม่ไม่ได้: หยุด ไม่ส่งซ้ำ ไม่เรียก desktop auto recovery. บันทึกฉาก/รอบ/error code/classification/ข้อความจริงใน trace message ก่อนตัดสินใจ. ฉาก1ไม่มีsourceใส่คำสั่งสร้างภาพใหม่จากข้อความก่อนสไตล์ ไม่แตะ Product/attach/trusted Send/Flow. ไม่มีการแนบ generated seed เพิ่มในรุ่นนี้; ACK บันทึกภาพก่อนฉากถัดไปคงเดิม. โปรแกรม253แสดงเหตุหยุดตรงกัน รายงาน docs/reports/story-image-response-20260906/VALIDATION.md ยังรอ installed smoke

0.15.252: แต่ละฉากสร้างใหม่จากแผนข้อความ/visual_bible ไม่บังคับมีรูปฉากก่อนหน้า ฉาก1ไม่มี source ต้องตั้งภาพจำจากข้อความ; sourceUrls ที่มีคือรูปหลักของผู้ใช้ ไม่ใช่รูปฉากก่อนหน้า ไม่เปลี่ยน attach/Send handlers และไม่ดึงภาพอื่นมาแนบเอง. คำตอบล่าสุดที่ไม่มีภาพและขอให้อัปโหลดรูปอย่างชัดเจนหยุดด้วย STORY_REFERENCE_REQUIRED พร้อมฉาก/จำนวน source/ข้อความจริง ห้าม retry คำสั่งเดิมหรือ desktop auto recovery. Policy refusal ยังคงมี priority และไม่เปลี่ยนชื่อเป็น reference error. โปรแกรม Story/Drama ไม่อ้างว่ามีรูปแนบเมื่อไม่มีจริง ผล docs/reports/story-reference-20260906/VALIDATION.md. ต้องติดตั้ง252คู่โปรแกรม; ยังไม่อ้าง installed E2E.

0.15.251: แยก scene visual prompt จาก raw narration; แนวทางภาพไม่แสดง strike/blood/injury ใช้ก่อนปะทะหรือ aftermath โดยไม่เปลี่ยน cast/style/plot. Structured bible ส่งเฉพาะ visual globals + ตัวตนในฉาก ไม่แนบทุกเรื่องเล่าเป็นคำสั่งภาพ. STORY_IMAGE_REFUSED คงเป็น terminal ไม่ส่งใหม่เอง. โปรแกรมให้ผู้ใช้แก้ Prompt ฉากที่ยังไม่มีภาพของงานหยุด/ยังไม่มีเสียง/Final บันทึกอย่างเดียวพร้อม revision/old-new history; effective analysis checkpoint ใช้ override ที่ตรวจแล้ว ไม่ทับด้วย Chrome cache. STORY_SCENE_PROMPT_STALE หยุดก่อนส่ง/ซ่อม/auto recovery. “ทำต่อ” ต้องใช้ valid saved analysis แม้มีภาพ0ฉาก. Flow actions/AI trusted Send/Voice เดิมไม่เปลี่ยน รายงาน docs/reports/story-depiction-20260906-66493F/VALIDATION.md; ยังไม่อ้าง provider acceptance หรือ installed E2E.

0.15.250: Story/Drama style = วิธีวาดเท่านั้น ไม่ใช่การเปลี่ยนจักรวาลหรือตัวละคร งานใหม่รับ request.story_content_contract version1 และ result.story_entities/scene_entities ตรวจชื่อและ mapping ก่อน checkpoint/generation แล้วแนบตัวตนที่เกี่ยวข้องกับฉากและบทฉากจริง หยุด STORY_CONTENT_MISMATCH หรือ STORY_IMAGE_REFUSED โดยไม่สั่งใหม่/เปลี่ยนเป็น original characters อัตโนมัติ แก้ภาพซ้ำเฉพาะมุมกล้องไม่เปลี่ยนเหตุการณ์ คง legacy checkpoints และ Product/Flow gestures ทั้งหมด การตรวจข้อความไม่ใช่การยืนยันภาพจริง ผลทดสอบ docs/reports/story-content-style-20260905/VALIDATION.md และ CURRENT_RELEASE.json

0.15.249: AI Send รับ job_id/run_id และตรวจ owner ทั้งก่อนเตรียมและก่อน press; per-tab single-flight กันคำสั่งซ้อน เตรียม focus ปุ่มก่อน press, hover แล้วตรวจ exact draft/node/geometry/hit target ต่อเนื่องสองครั้งก่อน arm เพียงหนึ่ง gesture. ใช้ releaseOnce ที่พิกัดเดิม ไม่มี Enter/press ซ้ำ/retarget. Capture V2 เก็บ up/click แม้หลุดปุ่ม โดยตรวจ original node/composedPath แยกจาก trusted click ที่โดน Send จริง. `dispatched` หมายถึงเริ่มส่ง press แล้ว; `dispatchCompleted` กับ `gesture_phase` แยกผลสำเร็จ/ไม่แน่นอน อ่าน passive acceptance ต่อ ไม่เพิ่ม timeout หรือส่งซ้ำ. Desktop whitelist รับหลักฐานเพิ่มแบบจำกัด. ตัวช่วยติดตั้งเลิกชี้ .244 ตายตัวและตรวจสามแหล่งเวอร์ชันก่อนเปิดโฟลเดอร์ source. Flow ไม่แก้ gesture เปลี่ยน helper version เท่านั้น; installed E2E ยังไม่ยืนยัน ดู `docs/reports/ai-send-20260905-16F867/VALIDATION.md`.

0.15.248: Product images → `PRODUCT_IMAGE_RECOVERY` (owner tab/provider/run guard) → `/api/jobs/image-recovery` → atomic per-slot ledger. `runProductImages` สร้างเฉพาะช่อง missing รอบแรก แล้วกู้ failed ด้วย initial-success donor ได้ครั้งเดียว; attachment identity guard เปิดเฉพาะ donor โดยไม่เปลี่ยนเส้นทางแนบปกติ. Policy/refusal/credit/unknown/pending ไม่ส่งซ้ำ. Final callback ต้องตรงภาพและ revision ใน ledger และมี durable receipt กัน replay หลัง restart. Desktop แยกภาพเก่าที่ผู้ใช้ยืนยันเป็น local motion ไม่ปลอมว่าภาพ AI/Flow ใหม่. Flow physical gestures ไม่แก้ นอกจากเลข helper build ให้คู่รุ่น. แผน/ผลดู `docs/reports/product-image-reliability-20260905/VALIDATION.md`.

0.15.247: `submitPrompt` ต้องตรวจข้อความเท่าเดิมต่อเนื่องก่อนถือว่าคำตอบนิ่ง ไม่ใช่จับเวลาโดยดูแค่ปุ่ม Stop; reset เมื่อข้อความเปลี่ยนแม้ความยาวเท่าเดิม และเมื่อ Stop กลับมา. คง timeout, cancellation, parser, selector, single Send และ Flow เดิม. Bridge เก็บ Send evidence แบบ allowlist ใน state/trace. งานจริง 7C0982 หยุดใน JSON repair หลัง initial accepted; การทดสอบจำลองยืนยัน timer bug แต่ไม่ได้ยืนยันว่านี่เป็นสาเหตุเดียวของ live failure. ผล/ข้อจำกัดอ่าน `docs/reports/live-watch-20260905-7C0982/OBSERVATIONS.md`.

0.15.246: ไม่เปลี่ยน physical Flow path. AI send หลัง Background press/release เสร็จแต่ไม่มี captured trusted click ใช้ `dispatched:true` + method เฉพาะ เพื่อให้ content helper ตรวจ passive submissionProof ต่อในรอบเดิม ไม่ click/Enter/upload ซ้ำ; unconfirmed 60s ต้องหยุดพร้อม diagnostics. เหตุการณ์จริง JOB-20260905-7447BE อยู่ใน JSON repair หลัง Master Prompt ส่งสำเร็จ ไม่ใช่รูปแรกแนบไม่เข้า. Desktop คู่รุ่นแก้ popup/cancel-resume ownership/queue recovery. Installed E2E ยัง pending.

กฎล่าสุด 0.15.245 (มีอำนาจเหนือข้อความ policy-only/หยุด Needs review ในประวัติด้านล่าง): single attach → passive grace 30s → ถ้ารูปเข้าทัน ให้ทำต่อด้วย guard เดิม; ถ้ายังไม่เข้าและพิสูจน์ว่าไม่มี submit/receipt/queue/render/result/confirmation ให้บันทึก terminal latch แบบ durable แล้วส่ง `attachment_failed` / `FLOW_ATTACHMENT_UNCONFIRMED` พร้อม `attachment_failure_evidence` ไป Bridge. Desktop สร้างช่วงจากรูปเดิมในเครื่องและเดินรูปถัดไป ห้าม terminal latch ของช็อตนี้กระทบช็อตอื่น และตรวจ latch ทุก generate/load/resume path เพื่อกันส่งหลังใช้รูปแทนแล้ว

รุ่น 0.15.244: แยก heartbeat จาก long-running command, เก็บผล action เพื่อ retry ACK อย่างเดียว, จับคู่ download receipt กับ Job/Shot/Run/ไฟล์จริง, ไม่ล้าง monitor ของงานอื่นเมื่อยกเลิก และกู้ไฟล์ที่ดาวน์โหลดเสร็จโดยไม่บังคับให้แท็บยังเปิดอยู่ โปรแกรมคู่รุ่นกรอง client/version, callback หลังยกเลิก และ canonical next-shot ดูแผน `docs/design/WORKFLOW_RELIABILITY_20260905.md` และผล `docs/reports/workflow-20260905/VALIDATION.md` ไม่แก้ขั้นตอนคลิก Flow และยังไม่อ้างผล installed E2E

รุ่น 0.15.243: `request.visual_style_instruction` มาจาก Job/Batch/Drama ในโปรแกรมและต้องแนบในคำสั่งสร้างภาพทุกฉาก รวม retry ที่เปลี่ยนข้อความ prompt; งานเก่าที่ไม่มี field ใช้พฤติกรรมเดิม Product ไม่ได้รับ style นี้ การส่งภาพครบใช้คำอธิบายว่า Desktop ยังต้องทำเสียง/Final ต่อ ไม่ใช่ Final complete ไม่มีการเปลี่ยน physical Flow transaction จาก 0.15.242 หลักฐาน 519 tests/36 files ด้านล่างเป็นของฐานเดิม ผลรุ่นนี้อ้างอิง CURRENT_RELEASE.json และยังต้องทดสอบ installed Chrome รุ่นใหม่
> ผลรุ่นปัจจุบันให้อ่าน CURRENT_RELEASE.json; 519/519 เป็น automated gate ของฐาน 0.15.242 ไม่ใช่ผลรุ่นใหม่ ส่วน `0.15.231` พิสูจน์ E2E all-Flow 3 ช็อตแล้ว, Golden ที่ย้อน Source ได้คือ `0.15.112` และ Modern E2E เดิมคือแพ็ก `0.15.216`  
> ลำดับอำนาจ: Source + Tests → `CURRENT_RELEASE.json`/`PROJECT_STATE.md` → กฎปัจจุบันในเอกสารนี้ → ประวัติรุ่นเก่า ประวัติด้านล่างใช้วิเคราะห์สาเหตุเท่านั้น ห้ามนำ handler/selector ทั้งไฟล์จากรุ่นเก่ามาทับ Runtime

กฎ Google Flow รุ่น `0.15.185`: หนึ่ง state transition ทำหนึ่ง physical action เท่านั้น; หลังส่ง Prompt แล้วห้ามใช้ Mouse + Enter + React `onClick` ซ้ำใน transaction เดียว, ข้อความ `waiting in the queue`/`high demand` คือสถานะรอทำงาน, และการไม่เห็นเปอร์เซ็นต์ 75 วินาทีต้องเฝ้าดูโปรเจกต์เดิมแทนการเปิดโปรเจกต์ใหม่

กฎ Google Flow รุ่น `0.15.186`: ถ้า Agent หา media id เดิมไม่เจอแต่ค้นพบรูปในโปรเจกต์และแสดงคำขออนุมัติใหม่ ปุ่มอนุมัติที่ยังกดได้ของ turn ล่าสุดต้องชนะ failure/no-charge text จาก turn เก่า และทำต่อในโปรเจกต์เดิม

กฎ Google Flow รุ่น `0.15.187`: รูปที่อยู่เพียงในคลังโปรเจกต์หรือผลตอบกลับว่า “คลิกเลือกรูปแล้ว” ยังไม่ถือว่าแนบสำเร็จ ต้องเห็น Thumbnail/การ์ดรูปอยู่ในช่องแชทเดียวกับ Prompt ก่อนจึงอนุญาตให้กดสร้าง ตรวจซ้ำทันทีก่อนกด และห้ามอัปโหลดหรือเลือกรูปซ้ำระหว่างรอ UI แสดงการ์ด

กฎ Google Flow รุ่น `0.15.188`: ช่อง Prompt ของ Flow เป็น Slate editor ห้ามแก้ DOM ด้วย `textContent`, `fill`, `execCommand` หรือ synthetic React handler เพราะทำให้ทั้งหน้าเกิด client-side exception; ใช้ trusted text input ทางเดียวและหยุดเป็น Checkpoint ถ้ายืนยันข้อความไม่ได้ นอกจากนี้ content script ที่ถูกถอด/Reload ต้องหยุด heartbeat ของตัวเองทันที ห้ามทิ้ง `Extension context invalidated` ทุก 5 วินาทีบนหน้าเว็บ

กฎ Google Flow รุ่น `0.15.190`: เมื่อเปิดตัวเลือกสื่อแล้ว Flow อาจเลือกภาพล่าสุดไว้ให้ทันที ถ้า option มีสถานะ selected ให้กด `เพิ่มไปยังพรอมต์` โดยไม่คลิกรูปซ้ำ เพราะการคลิกรูปที่เลือกอยู่แล้วอาจยกเลิกการเลือก จากนั้นต้องรอให้ Thumbnail ปรากฏใน Composer ก่อนใส่ Prompt และกดสร้าง

กฎป้องกัน Extension โหลดวนรุ่น `0.15.190`: ห้ามเรียก `chrome.runtime.reload()` จาก heartbeat และห้าม reload หน้า Flow เพียงเพราะ helper คนละรุ่น หากเวอร์ชันโปรแกรมกับ Extension ไม่ตรงให้หยุดรับคำสั่งและแสดงสถานะอัปเดต ผู้ใช้ reload Extension เพียงครั้งเดียว ส่วน helper ใช้คิวติดตั้งหนึ่งชุดต่อแท็บและ resume ตัวเดิมเมื่อเป็นเวอร์ชันเดียวกัน

กฎ Gemini รุ่น `0.15.191`: ปุ่มส่งของ Gemini/Angular ต้องใช้ trusted browser click จาก service worker เพียงหนึ่งครั้ง ห้ามยิง `Enter` ซ้ำสามรอบ การส่งสำเร็จต้องพิสูจน์ได้จากข้อความผู้ใช้ใหม่ ปุ่มหยุด หรือ Composer ที่ว่างลง และตัวอ่าน JSON ต้องกู้ object สมบูรณ์ตัวหลังได้แม้ Gemini ทิ้ง object แรกค้างไว้

กฎ AI Web รุ่น `0.15.219`: ลอจิกแนบรูปยึดเส้นทางที่ใช้งานจริงของ `0.15.216`—หาก Gemini เก็บรูปอ้างอิงไว้ใน user turn ก่อนหน้าให้ใช้ต่อ ห้ามบังคับเปิดเมนูแนบใหม่หรือรอ Preview ใหม่จนเกิดการแนบวน; หลังรูปและ Prompt พร้อม ให้ service worker focus หน้าต่าง/แท็บ ตรวจ hit target แล้วส่ง trusted click หนึ่งครั้ง พร้อม event proof โดยไม่มี Enter/click fallback ซ้ำ

กฎ Gemini JSON รุ่น `0.15.220`: เมื่อคำตอบวิเคราะห์เป็นข้อความปฏิเสธ เช่น “ฉันไม่สามารถช่วย/เป็นเพียงโมเดลภาษา” ให้คืน assistant turn นั้นเข้าสู่ `parseOrRepairAnalysis` ทันที แล้วส่ง Prompt JSON-only ใหม่แบบจำกัดสูงสุด 2 รอบผ่าน Provider เดิม ห้ามโยนเป็น no-response แล้วส่ง Master Prompt ซ้ำ และห้ามสลับ Provider เอง

กฎ Gemini วิเคราะห์สินค้ารุ่น `0.15.237`: Prompt แรกต้องประกาศว่าเป็นงานเขียนข้อความ JSON เท่านั้น ไม่ขอให้สร้างรูป วิดีโอ หรือเรียกเครื่องมือ เมื่อคำตอบเป็น refusal ห้ามกล่าวว่า “คำตอบก่อนหน้ามีข้อมูล” แต่ต้องขอวิเคราะห์ใหม่แบบข้อความล้วนจากข้อมูล/รูปในข้อความก่อนหน้า ส่วนกรณีมีข้อมูลแต่ JSON เสียจึงใช้การจัดรูปแบบเดิม การใส่ Prompt รอบซ่อมต้องผ่าน editor input path ที่ Gemini รับรู้ก่อน trusted click เพียงครั้งเดียว; ห้ามเพิ่ม Enter หรือคลิกซ้ำ

กฎ Gemini Composer รุ่น `0.15.238`: ก่อนเขียนให้แปลง whitespace จริงเป็นช่องว่างหนึ่งตัว เพราะ Gemini ทิ้งเนื้อหาหลัง newline เมื่อรับ multiline `insertText`; ตรวจข้อความแบบ exact จาก Composer ตัวล่าสุดสองรอบก่อนส่ง หากไม่ครบให้ใช้ CDP single-line input ได้อีกเพียงหนึ่งครั้งโดยไม่ย้อนกลับไปแนบรูป แล้วตรวจ exact ซ้ำ Background ต้องตรวจ Prompt เดิมอีกครั้งก่อน trusted click และหยุดโดยไม่คลิกทันทีหากข้อความเปลี่ยนหรือขาด

กฎ Gemini JSON recovery รุ่น `0.15.239`: หลังพบ refusal ต้องรอข้อความเดิมและสถานะ idle คงที่อย่างน้อย 1.8 วินาทีก่อนใส่พรอมต์กู้คืน จากนั้นต้องเห็น exact draft และปุ่มส่งตำแหน่งเดิม 3 snapshots; Background ต้อง resolve exact draft/ปุ่มใหม่หลัง attach CDP ก่อน dispatch คลิกหนึ่งครั้ง ตัวนับ turn ใช้ `user-query` ชั้นนอกเพียง node เดียวต่อข้อความ และแยก Log `ai_send_dispatched`, `ai_send_waiting_acceptance`, `ai_send_accepted`; หากยังไม่มีหลักฐานรับภายใน 60 วินาทีให้เก็บ draft แล้ว safe-stop ห้ามกดส่งหรือแนบรูปซ้ำ หลังยืนยัน acceptance แล้วให้รอคำตอบ turn เดิมสูงสุด 6 นาทีและห้ามส่ง Master Prompt ซ้ำ

กฎ Flow policy รุ่น `0.15.242`: การ์ด Policy ปัจจุบันต้องมีข้อความปฏิเสธ, ข้อความไม่หักเครดิต และปุ่ม Retry อยู่ในการ์ดเดียวกัน พร้อม fingerprint/จำนวนการ์ดที่ใหม่กว่า baseline ก่อนส่ง และต้องนิ่งครบ grace period; การ์ดเก่าหรือข้อความคิว/กำลังสร้าง/ระบบไม่ว่าง/ข้อผิดพลาดชั่วคราวให้รอหรือกู้ในโปรเจกต์เดิมโดยไม่ Reload/Submit/Upload ส่วน Extension ส่ง `failure_code=FLOW_POLICY_BLOCKED`, `policy_failure_category` และ `failure_card_fingerprint` เฉพาะ terminal branch จริง โปรแกรม Product, Story และ Drama ใช้รูป canonical เดิมสร้าง local motion ของ slot/ฉากนั้นทันทีตั้งแต่ terminal ครั้งแรก แล้วเดิน source/scene ถัดไป โดยห้าม safe-prompt retry, reupload และ Alternate Take และต้องเก็บ provenance/จำนวนแยกจากคลิป Flow จริง

กฎ AI Web overlay รุ่น `0.15.221`: แถบสถานะ SmartFlow ที่มุมจอต้องมองเห็นได้แต่ไม่รับ mouse/pointer (`pointer-events:none`) จึงห้ามบังปุ่มส่งของ Gemini/ChatGPT; ก่อน trusted click ให้ hit-test และเมื่อถูกบังต้องรายงาน tag/id/class ของตัวบังแล้วหยุดโดยไม่ใช้ Enter หรือคลิกซ้ำ

กฎ Gemini image expansion รุ่น `0.15.222`: ก่อนค้นหรือคลิกปุ่มแนบ ต้องตรวจรูปอ้างอิงที่อัปโหลดใน user turn เดิมก่อนและ reuse ทันที; candidate ปุ่มแนบที่มี `<img>` หรือป้าย preview/ขยายรูปต้องถูกตัดออก หาก `image-expansion-dialog-backdrop` ค้างตอนพร้อมส่ง ให้กด trusted Escape หนึ่งครั้ง รอ Overlay ปิด แล้วจึง hit-test และ trusted click ปุ่มส่งหนึ่งครั้ง ห้ามคลิกรูปหรืออัปโหลดซ้ำ

ประวัติ Flow policy รุ่น `0.15.224` (ถูกแทนที่ด้วย `0.15.242`): รุ่นนี้เริ่มให้ `generation_in_progress`/คิวของรอบปัจจุบันชนะการ์ด Error เก่าและเคยย้าย output slot ไปให้รูปถัดไปสร้าง Alternate Take หลัง terminal denial; เก็บไว้เป็นหลักฐานย้อนหลังเท่านั้น ห้ามนำ reassignment/Alternate Take กลับมาใช้กับ Runtime ปัจจุบัน

กฎ Upload รุ่น `0.15.224`: หลังใส่ไฟล์ต้องรอหลักฐาน asset ใหม่ของไฟล์รอบนี้หรือรูปที่ผูกใน Composer เท่านั้น รูปเก่าที่อยู่ใน Gallery ห้ามนับเป็น Upload สำเร็จ เพราะจะทำให้รีเฟรชเร็วเกินไปและเกิดภาพเหมือนอัปโหลดรูปเดิมวน

กฎ Attachment รุ่น `0.15.227`: ทุกช็อตใช้เส้นทางเดียวกับช็อตแรก—อัปโหลดหนึ่งครั้ง เลือกรูป แล้วต้องพบ chip/thumbnail ของรูปจริงภายใน `.base-prompt-box` ก่อนกรอก Prompt และกดสร้าง ปุ่มปิดทั่วไป พื้นหลังของ Composer หรือ `composerProof` จาก service worker เพียงอย่างเดียวห้ามนับเป็นรูปแนบ มิฉะนั้นจะเกิด false ready แล้วรอ 90 วินาทีก่อนเริ่มใหม่

กฎ Popup รุ่น `0.15.227`: ก่อนเตรียมงานและระหว่างรอเรนเดอร์ ให้ตรวจเฉพาะ dialog ที่มี `change-log-modal-actions` หรือมีปุ่มคู่ `ดูบันทึกการเปลี่ยนแปลงทั้งหมด` + `เริ่มต้นใช้งาน`; กด `เริ่มต้นใช้งาน` ด้วย trusted click เพียงครั้งเดียว แล้วทำงานเดิมต่อ ห้ามรีเฟรช ห้ามส่ง Prompt ซ้ำ และห้ามนำกฎนี้ไปกดหน้าต่างอนุมัติเครดิต/สิทธิ์รูป

กฎ Fast hand-off รุ่น `0.15.227`: ถ้า inspect แบบ passive พบรูปอ้างอิงและ Prompt ของ Job/SHOT เดิมอยู่ใน Composer พร้อมปุ่มสร้าง โดยไม่มี active monitor หรือ submission receipt ให้คืน AUTO FLOW token แล้วใช้ Generate transaction เดิม ห้ามเปิดโปรเจกต์หรืออัปโหลดรูปใหม่ ส่วนเมนูดาวน์โหลดที่คลิกแล้วไม่สร้าง Chrome download ต้อง fallback ภายใน 15 วินาทีแทนการค้าง 90 วินาที

กฎ Handoff/ความเป็นเจ้าของรุ่น `0.15.228`: เมื่อดาวน์โหลดไฟล์ของช็อตสำเร็จจริง ให้เร่งอ่านคำสั่งช็อตถัดไปแบบ bounded ที่ 250/1000/2500 ms โดยไม่ทำ physical action เองและ de-duplicate เหตุการณ์เดิม 10 วินาที; อนุมัติเครดิตใช้ trusted click ครั้งเดียว ไม่มี DOM `.click()` รอบสอง; Resume ห้ามเลือกแท็บโปรเจกต์อื่นเมื่อแท็บของ Job/SHOT เดิมไม่พร้อม; ปิดงานได้เฉพาะ tab id ที่ Extension ลงทะเบียนไว้ ห้ามค้นแล้วปิดแท็บผู้ใช้จาก URL อย่างเดียว

กฎ ChatGPT attachment รุ่น `0.15.229`: ใช้เมนู Composer ปัจจุบัน “เพิ่มไฟล์และอื่นๆ” และเลือก input อัปโหลดรูปที่ผูกกับ Composer; หลังส่งไฟล์ต้องเห็นการ์ด/ภาพอ้างอิงครบใน Composer ก่อนจึงใส่ Prompt และกดส่ง หากไม่มีหลักฐานจะหยุดโดยไม่ส่ง Prompt และไม่สร้างภาพเปล่า

กฎ Google Flow upload รุ่น `0.15.230`: เมื่อรูปอัปโหลดครบ 100% และมี asset พร้อมแล้ว ให้เลือก asset เข้า Composer ต่อในหน้าเดิมทันที ห้ามรีเฟรชหน้า ห้ามอัปโหลดรูปเดิมซ้ำ; การรีเฟรชหนึ่งครั้งสงวนไว้เฉพาะกรณีวิดีโอเรนเดอร์ถึง 100% แต่ยังไม่แสดงผลลัพธ์ที่เล่นได้

กฎ Flow composer รุ่น `0.15.231`: หลังเลือก asset และปิด Settings ต้องอ่าน Prompt จาก Composer ปัจจุบันอีกครั้ง ถ้าข้อความหายให้กรอก Prompt ใหม่อย่างเดียว ห้ามแนบรูปซ้ำ; สถานะพร้อมสร้างเกิดได้เมื่อปุ่มสร้างเปิดใช้งานจริงเท่านั้น และข้อความ “Agent ทำงานไม่สำเร็จ” ต้องถูกจำแนกเป็นความล้มเหลวโดยไม่รอ timeout

กฎ Flow media รุ่น `0.15.232`: หลังอัปโหลดครบ 100% ให้รอการ์ดรูปเดิมถูกวาดในโปรเจกต์หน้าเดิมแบบจำกัดเวลา แล้วจึงเปิดเมนู “ทำให้เคลื่อนไหว” เพียงครั้งเดียว การรอนี้ห้ามรีเฟรช ห้ามอัปโหลดซ้ำ และห้ามเลือก asset ซ้ำ

กฎ Flow upload overlay รุ่น `0.15.233`: หลังอัปโหลดครบ 100% หากเมนู `อัปโหลด/คอลเล็กชัน/ตัวละคร/ฉาก` ยังเปิดอยู่ ให้ปิดเฉพาะเมนูนี้ด้วย Escape หนึ่งครั้ง จากนั้นต้องตรวจ `elementFromPoint` ว่าจุดกึ่งกลางเป็นปุ่ม `ตัวเลือกเพิ่มเติม` จริงก่อนคลิก ห้ามคลิกทะลุ Overlay ลงบนการ์ดรูป เพราะจะเปิด Nano Banana `/edit/`; หากยังหลุดเข้าโหมดภาพนิ่งให้หยุดช็อตนั้นทันทีโดยไม่เปิดโปรเจกต์หรืออัปโหลดรูปซ้ำ

กฎ Flow attachment รุ่น `0.15.234`: ลำดับที่พิสูจน์กับหน้าเว็บจริงคือ `การ์ดรูปที่อัปโหลด → เมนูสามจุดของการ์ดนั้น → ทำให้เคลื่อนไหว → รอ thumbnail ใน Composer → ใส่ Prompt → สร้าง` เท่านั้น ตัวตรวจต้องอ่าน `aria-label` แยกจากข้อความไอคอน `cancel` และรองรับ URL `flow-content.google/image/`; ห้ามเปิด Composer `+`, ห้ามเลือกโปรเจกต์ และห้ามเลือก/อัปโหลดรูปเดิมซ้ำหลังคลิก `ทำให้เคลื่อนไหว`

กฎ Flow attachment รุ่น `0.15.236`: Material menu อาจขยับทั้งหลังเปิดและหลัง hover จึงต้องรอ semantic target นิ่งสามครั้ง, hover หนึ่งครั้ง, resolve/hit-test ซ้ำ แล้วจึง press/release เพียงครั้งเดียว หลังคลิกต้องพบว่ารูปเข้า Composer หรือเมนูหาย มิฉะนั้น safe-stop ทันที ห้ามคลิก/อัปโหลดซ้ำ; การ์ดต้องตรงชื่อ reference เท่านั้น และโปรแกรมต้องถือ `attachment_waiting_manual` เป็นการหยุดจริง ไม่ใช่กำลังเรนเดอร์

ทุกสถานะจาก `flow.js` และ `chatgpt.js` รวมทั้งขั้นย่อยของ physical attachment ต้องส่ง trace เข้า Local Bridge โดยไม่เปลี่ยนสถานะหลัก โปรแกรมแสดง trace ใน Log และเก็บสำเนาต่อ Job ที่ `logs/extension_trace.jsonl`

กฎ Gemini รุ่น `0.15.192`: ก่อนส่ง Prompt วิเคราะห์ ซ่อม JSON หรือสร้างภาพทุกรอบ Extension ต้องตรวจว่า Gemini อยู่ใน `Flash Extended` (`การคิดที่นานขึ้น`) หากยังไม่ใช่จึงเปิดเมนูและเลือกด้วย trusted click เพียงครั้งเดียว พร้อมตรวจสถานะหลังเลือก ห้ามกดสลับซ้ำเมื่อเลือกอยู่แล้ว

กฎเสถียรภาพรุ่น `0.15.193`: ยึด invariant จากรุ่น Golden/รุ่นที่สร้าง EP สำเร็จ—ปุ่มเลือกโหมดเป็นฟังก์ชันเสริม ห้ามเป็นเงื่อนไขที่ทำให้ Job หลักล้ม ต้องรอ Composer พร้อมก่อนตรวจ รองรับชื่อปุ่มหลายแบบ รอ DOM แบบมีขอบเขต และหาก Gemini ซ่อนตัวเลือกให้ใช้โหมดปัจจุบันทำงานต่อพร้อมบันทึกคำเตือน โดยห้ามทิ้ง Checkpoint

กฎ Google Flow รุ่น `0.15.194`: หลังอัปโหลดรูปเข้าโปรเจกต์ต้องรอ media card ให้พร้อมแล้วรีเฟรชได้หนึ่งครั้ง จากนั้นตั้งค่าการสร้างวิดีโอเป็น 9:16, 1x และ `ยืนยันก่อนสร้าง=ไม่เลย`; เลือกรูปจากคลังเข้า Composer ก่อนส่ง Prompt ถ้าการ์ดขึ้น 100% แต่ยังไม่เปิดวิดีโอให้รีเฟรชได้อีกหนึ่งครั้งโดยใช้ guard แยกและห้ามส่ง Prompt ซ้ำ

กฎดาวน์โหลดรุ่น `0.15.197`: เมื่อวิดีโอใหม่เสร็จ Extension ต้องหาเมนู `ตัวเลือกเพิ่มเติม` ภายในการ์ดวิดีโอล่าสุดเอง เปิด `ดาวน์โหลด` และเลือก `720p ขนาดดั้งเดิม` ห้ามใช้เมนู `ดาวน์โหลดโปรเจ็กต์`; ต้องรอ Chrome เขียนไฟล์เสร็จก่อนรายงาน `generation_complete` และเก็บ receipt ป้องกันคำสั่ง retry ดาวน์โหลดไฟล์เดิมซ้ำ

กฎอัปโหลด Google Flow รุ่น `0.15.197`: คืนลำดับ Golden จาก `0.15.112` ซึ่งมีหลักฐาน Final จริงครบ 3 ช็อต—ใช้ไฟล์อ้างอิงที่ดาวน์โหลดแล้วกับ hidden file input เพียงครั้งเดียว, รอ media card พร้อม, รีเฟรชโปรเจกต์เดิมหนึ่งครั้ง, เลือกรูปเดิมและกด `เพิ่มไปยังพรอมต์`; ห้ามเปิดคลังว่างก่อนอัปโหลด ห้าม physical file drop เป็น fallback และห้ามเปิดโปรเจกต์ใหม่เมื่อยังพิสูจน์การแนบไม่ได้

กฎเสถียรภาพและความปลอดภัย Runtime `0.15.198`: คำสั่งทุกตัวผูก `client_id + run_id + lease_token`, ACK ซ้ำต้อง idempotent และ ACK จาก Lease/Run เก่าต้องถูกปฏิเสธ; Progress ของ Flow รับจาก Owner tab/run และ Helper build ปัจจุบันเท่านั้น, Command polling กับ Monitor ต้องเป็น single-flight, และ Browser-origin routes ใช้ Session capability `X-SmartFlow-Token` ที่หมุนใหม่ทุก Engine session โดยห้ามใส่ Token ใน URL, Status หรือ Log

กฎความถูกต้อง Google Flow Runtime `0.15.199`: หลัง `DOM.setFileInputFiles` และ media card พร้อม ต้องตั้ง Reload guard และนัด Reload โปรเจกต์เดิมก่อนส่ง Diagnostics; Diagnostics ใช้ `uploadDebug` ของ Upload transaction ปัจจุบันเท่านั้น ห้ามอ้างตัวแปรจาก Attach path อื่นจน Successful upload ถูกกลืนเป็น `false`. คำสั่ง `open_flow` ต้องคง Lease จนพบ `/project/`, ลงทะเบียน Job/Shot/Tab และติดตั้ง Helper สำเร็จแล้วจึง ACK; หากหมดเวลาหรือ Redirect ไป Login ต้องส่ง Progress พร้อม `run_id` และ ACK failed. การ Handoff ยอมรับเฉพาะ Landing tab เดิมที่เปลี่ยน Route หรือ Tab ID ใหม่หลัง Snapshot ก่อนคลิก ห้ามรับ Project tab เก่าของ Job/Shot อื่น

กฎซ่อม Google Flow Runtime `0.15.200` build `20260903.2`: DOM ปัจจุบันใช้ปุ่มแม่ `button[type="submit"][aria-label="เริ่มสร้าง"]` และมี `<span class="mat-mdc-button-touch-target">` เป็นลูกสำหรับพื้นที่สัมผัส Extension ต้องหาและคลิกปุ่มแม่เท่านั้น หากการแนบอัตโนมัติหยุดอย่างปลอดภัยแล้วผู้ใช้แนบรูปใน Composer เดิมภายหลัง ให้เฝ้าดู DOM แบบ passive, พิสูจน์รูป+Prompt+ปุ่มพร้อมและ owner Job/Shot/Tab เดิม แล้วกลับเข้า submit gate ปกติโดยไม่อัปโหลด เลือกรูป หรือกดสร้างซ้ำ

Google Flow รุ่นใหม่ใช้ปุ่ม `ทริกเกอร์การตั้งค่า` และแสดงตัวเลือกแบบ compact popover โดยไม่มีหัวข้อ Agent settings หรือ confirm-policy เดิม Extension ต้องรองรับทั้งหน้าเก่าและหน้าใหม่นี้ เลือก `วิดีโอ 9:16` และ `x1` จาก radiogroup ที่มองเห็นจริง แล้วตรวจ `aria-checked` ก่อนแนบรูป ห้ามหยุดเพียงเพราะช่อง `ไม่เลย` ไม่มีใน UI รุ่นใหม่

หาก Flow เปลี่ยนหน้าตั้งค่าจนยืนยัน `9:16`/`x1` ไม่ได้ ระบบต้องใส่ข้อกำหนด “วิดีโอแนวตั้ง 9:16 เพียง 1 ผลลัพธ์” ใน Prompt และเดินงานต่อ แทนการหยุดก่อนแนบรูป โดยยังบันทึกสถานะ fallback ไว้ตรวจสอบย้อนหลัง

ถ้า Flow ตอบว่า Prompt อาจละเมิดนโยบาย ต้องแยกจากคิวเต็ม และจะส่ง `FLOW_POLICY_BLOCKED` ได้ต่อเมื่อการ์ดปัจจุบันมีหลักฐาน Policy + ไม่หักเครดิต + Retry ครบและ fingerprint ใหม่เท่านั้น เมื่อยืนยันแล้วโปรแกรมใช้รูป canonical เดิมทำ local motion ของ slot/ฉากนั้นทันที ห้ามสร้าง Prompt safety reframe หรือส่งฉากนั้นเข้า Flow อีก

กฎผลลัพธ์ Google Flow รุ่น `0.15.202` build `20260903.1`: หลังเคยเห็นเปอร์เซ็นต์ของช็อตปัจจุบันแล้ว การ์ดวิดีโอใหม่ที่นิ่งและไม่มี active progress ต้องชนะข้อความ “กำลังสร้าง/อยู่ในคิว” จากประวัติเก่า ห้ามเปิดโปรเจกต์หรือส่ง Prompt ซ้ำ; ตอนดาวน์โหลดให้คลิกขวาการ์ดวิดีโอล่าสุด → `ดาวน์โหลด` → `720p ขนาดดั้งเดิม` เป็นเส้นทางหลัก เพราะปุ่ม `ดาวน์โหลดฉาก` ใน editor อาจไม่เริ่ม Chrome download และใช้ editor เป็น fallback เท่านั้น

กฎ Resume รุ่น `0.15.202`: ถ้าไฟล์ `Downloads/SmartPost/<job>/flow-shot-NN.mp4` มีอยู่ก่อนเริ่ม Resume ให้รับไฟล์นั้นได้เฉพาะเมื่อ receipt ของ Extension ระบุ Job/Shot เดียวกัน สถานะ `generation_complete` และ path ตรงกันทุกตัวอักษร เพื่อกู้ผลที่ดาวน์โหลดเสร็จแล้วโดยไม่สร้างซ้ำหรือเสียเครดิตเพิ่ม

กฎผลลัพธ์ Google Flow รุ่น `0.15.203` build `20260903.1`: หากเคยเห็นเปอร์เซ็นต์จริงของช็อตปัจจุบันแม้ Flow จะหยุดรายงานก่อนถึง 80% เมื่อเปอร์เซ็นต์หาย การ์ดวิดีโอใหม่ต้องนิ่งอย่างน้อย 15 วินาที ไม่มีสถานะกำลังสร้าง และ fingerprint มากกว่า baseline ก่อนยืนยันว่าเสร็จ เพื่อดาวน์โหลดผลเดิมแทนการค้างหรือส่ง Prompt ซ้ำ

กฎแนบรูป Google Flow รุ่น `0.15.210` build `20260903.1`: หลังอัปโหลดและรีเฟรชหนึ่งครั้ง ต้องเปิดเมนูของรูปใน Project Gallery แล้วกด `ทำให้เคลื่อนไหว` เพื่อเข้าโหมดวิดีโอก่อนเสมอ จากนั้นจึงอนุญาตให้เลือกรูปใน Media picker หากหน้าเว็บยังร้องขอ และต้องเห็นรูปอยู่ใน Composer ก่อนกดสร้าง; ถ้าหาเมนูหรือคำสั่งวิดีโอไม่พบให้หยุดอย่างปลอดภัย ห้ามอัปโหลดหรือส่งซ้ำ

กฎบัญชีใหม่และผลล้มเหลวรุ่น `0.15.211` build `20260903.1`: หากขั้นอัปโหลดตรวจพบหน้าต่างยืนยันสิทธิ์ แม้ Flow จะ re-render จนหน้าต่างหายก่อนจบรอบ ต้องคงสถานะ `awaiting_rights_confirmation` และ Resume โปรเจกต์เดิมโดยไม่อัปโหลดซ้ำ; ระหว่างติดตามผล หากพบคำตอบล้มเหลวแบบไม่หักเครดิตพร้อมปุ่ม `ลองอีกครั้ง` ที่เกิดหลัง baseline ติดต่อกัน 3 รอบ ให้ถือเป็นผลล้มเหลวปัจจุบัน แม้ Composer จะยังค้างปุ่ม `หยุด` และ Retry เฉพาะช็อตนี้

กฎคิวภาษาไทยรุ่น `0.15.212` build `20260903.1`: ข้อความ `จัดคิวเรียบร้อยแล้ว`, `กำลังรอคิว`, `รอคิว` และ `ความต้องการสูง` เป็นหลักฐานงานที่กำลังทำ ต้องคงโปรเจกต์เดิมและรอผล ห้ามเปลี่ยนเป็น unknown หรือ Retry

กฎส่งต่อเร็วรุ่น `0.15.214` build `20260903.1`: Monitor เริ่มตรวจใน 2.5 วินาทีและปรับเป็นทุก 5 วินาทีเมื่อเห็นหลักฐานเรนเดอร์จริง/2.5 วินาทีเมื่อใกล้เสร็จ โดยยังเป็น recursive single-flight; เมื่อ Extension มี receipt `generation_complete` ที่ path ตรง Job/SHOT โปรแกรมตรวจชนิดไฟล์และ SHA ทันทีโดยไม่เพิ่ม stability poll และ worker เดิมเปิดช็อตถัดไปตรง ๆ หลัง commit ช็อตก่อนหน้า ส่วนการ Resume หลังโปรแกรมเปิดใหม่ยังต้องตรวจ Remote Checkpoint ตามเดิม

กฎจับดาวน์โหลดรุ่น `0.15.215` build `20260903.1`: Chrome native download ที่มาจาก `flow-content.google` เป็นไฟล์ผลลัพธ์จริงของ Google Flow เช่นเดียวกับ `flow.google.com`; ตัวเฝ้าดาวน์โหลดต้องรับเหตุการณ์นี้ทันที เพื่อไม่รอ timeout 90 วินาทีทั้งที่ไฟล์ลงดิสก์สำเร็จแล้ว และยังต้องตรวจ Job/SHOT/ชนิดไฟล์ก่อนส่ง receipt กลับโปรแกรม

บทเรียนจากรุ่นทดลอง `0.15.218`: การบังคับให้ Gemini ต้องเห็น Preview ใหม่ใน Composer ปัจจุบันทุกรอบเป็นการตีความผิด เพราะรูปอ้างอิงที่หน้าเว็บรับไว้แล้วอาจอยู่ใน user turn เดิม ลอจิกนี้ถูกถอนใน `0.15.219`; ห้ามใช้เป็นฐานสำหรับการแนบรูปอีก

กฎกู้ผลวิดีโอ: ถ้า helper/service worker หลุดหลังสร้างเสร็จ แต่ Checkpoint `active` ยังชี้มาที่โปรเจกต์ Job/SHOT เดิมและพบ `<video src="https://flow-content.google/video/...">` ให้ถือเป็นผลใหม่ของ Checkpoint นั้น ดาวน์โหลดทันที และห้ามให้ข้อความ “รอคิว” เก่าในแชทชนะผลวิดีโอจริง
> อัปเดต: 5 กันยายน 2569  
> หน้าที่ของเอกสาร: อธิบายการทำงานของ Extension ตั้งแต่รับคำสั่งจนส่งผลงานกลับโปรแกรม และเป็นกฎหลักก่อนแก้หรืออัปเดต Extension

## 1. Extension ทำอะไร

SmartFlow AI Extension เป็นสะพานระหว่างโปรแกรมบนคอมกับหน้าเว็บที่ผู้ใช้ล็อกอินไว้ใน Google Chrome โดยทำงาน 3 กลุ่ม:

1. อ่านข้อมูลสินค้าจาก Shopee
2. ส่งงานสร้างข้อมูลและรูปไป ChatGPT Web หรือ Gemini Web ตามตัวเลือกของผู้ใช้
3. แนบรูปและ Prompt เข้า Google Flow สร้างวิดีโอจริง ดาวน์โหลดผล และส่งกลับเข้า Job เดิม

Extension ไม่ประกอบวิดีโอ ไม่สร้างเสียง ไม่สร้าง Subtitle และไม่ตัดต่อ Final เอง งานเหล่านี้เป็นหน้าที่ของโปรแกรม SmartFlow AI หลังบ้าน

## 2. ภาพรวมการไหลของงาน

```text
ผู้ใช้กดเริ่มงานใน SmartFlow AI
        ↓
Local Bridge ที่ 127.0.0.1:8765 สร้างคำสั่งผูก Job/Run/Shot
        ↓
background.js รับคำสั่งและเลือกแท็บที่เป็นเจ้าของงานนั้น
        ├─ Shopee → content.js อ่านข้อมูลสินค้า
        ├─ ChatGPT/Gemini → chatgpt.js สร้าง Analysis + รูป
        └─ Google Flow → flow.js แนบรูป + Prompt + สร้าง + เฝ้าผล
        ↓
Extension รายงาน Progress/Checkpoint กลับ Local Bridge
        ↓
ดาวน์โหลดคลิปจริงและส่งไฟล์เข้า Job เดิม
        ↓
โปรแกรมรวมคลิป + เสียง + Subtitle + Logo + Audio Mix เป็น Final
```

หลักสำคัญคือ โปรแกรมเป็นผู้สั่งงานและถือสถานะ Job ส่วน Extension เป็นผู้ควบคุมหน้าเว็บตามคำสั่งที่ผูกกับ Job นั้นเท่านั้น

## 3. ส่วนประกอบของ Extension

| ไฟล์ | หน้าที่ |
|---|---|
| `manifest.json` | ชื่อ รุ่น สิทธิ์ เว็บไซต์ที่รองรับ Content Script และไอคอน |
| `src/background/service-worker.js` | จุดเข้า Runtime แบบ ES Module; โหลดสถาปัตยกรรมใหม่ก่อน Legacy adapter ที่พิสูจน์แล้ว |
| `src/background/job-router.js` | Registry กลาง ตรวจ schema/action, timeout, duplicate receipt และ structured error |
| `src/core/` | Message schema, error code, logger, retry, storage, WebSocket transport และ chunked media transfer |
| `src/platforms/` | Adapter แยก Shopee, AI Web และ Google Flow พร้อม selectors เฉพาะแพลตฟอร์ม |
| `src/platforms/google-flow/*observer*` | เฝ้าหลักฐานวิดีโอแบบอ่านอย่างเดียวตั้งแต่ `document_start`; ห้ามคลิก/Reload/Submit |
| `background.js` | ศูนย์ควบคุมคำสั่ง แท็บ Checkpoint ดาวน์โหลด Heartbeat และการเชื่อม Local Bridge |
| `content.js` | อ่านข้อมูลสินค้าจาก Shopee/Affiliate |
| `chatgpt.js` | ควบคุม ChatGPT Web และ Gemini Web สร้าง JSON และรูป พร้อม Resume จาก Checkpoint |
| `flow.js` | ควบคุม Google Flow ตั้งแต่เปิดโปรเจกต์ แนบรูป ใส่ Prompt กดสร้าง เฝ้าผล และรายงานสถานะ |
| `popup.html/css/js` | หน้าต่างเล็กเมื่อกดไอคอน Extension ใช้ตรวจการเชื่อมต่อและเปิดหน้าที่เกี่ยวข้อง |
| `icons/` | ไอคอน SmartFlow AI ใน Chrome |

ห้ามแยกเป็น Extension สองตัวที่ควบคุม Google Flow พร้อมกัน เพราะ Service Worker และ Content Script จะแข่งกันกดหน้าเดียวกัน การแบ่งงานต้องแบ่งภายใน Extension ตัวเดียว

Runtime `0.15.200` ใช้แนวทาง incremental migration: Job Router ใหม่ตรวจ contract และ action registry ก่อนส่งต่อไปยัง Legacy runtime adapter ที่มีหลักฐาน Golden ห้ามย้าย physical action ของ Flow หลายขั้นพร้อมกัน ส่วน passive observer ใช้เป็น download evidence fallback หลังเส้นทางเมนูการ์ดเดิมเท่านั้น

## 4. เว็บไซต์และขอบเขตที่รองรับ

- Shopee Affiliate และ Shopee Thailand
- ChatGPT Web และหน้า Login ของ OpenAI
- Gemini Web และหน้า Login ของ Google
- Google Flow ที่ `labs.google` และ `flow.google.com`
- Local Bridge เฉพาะ `http://127.0.0.1:8765`

Meta AI Vibes ถูกยกเลิกถาวร ไม่มีสิทธิ์ Host ไม่มี Content Script และห้ามเพิ่มกลับโดยไม่มีคำสั่งใหม่จากผู้ใช้

## 5. สัญญาระหว่างโปรแกรมกับ Extension

### 5.1 โปรแกรมส่งอะไร

ทุกคำสั่งที่เปลี่ยนสถานะงานต้องระบุอย่างน้อย:

- `job_id` — งานใด
- `shot_index` — ช็อต/ฉากใดเมื่อเป็น Google Flow
- `run_id` — รอบการทำงานใด
- Provider ที่ผู้ใช้เลือก — ChatGPT Web หรือ Gemini Web
- Action ที่ต้องทำ

คำสั่งหลัก:

- `capture_shopee_product`
- `open_chatgpt`, `resume_chatgpt`, `inspect_chatgpt`
- `open_story_chatgpt`, `cancel_story_chatgpt`
- `focus_ai_web`, `focus_flow_web`
- `open_flow`, `resume_flow_workspace`, `inspect_flow`
- `approve_flow_credit`, `stop_flow_generation`
- `open_flow_result`, `download_flow_result`
- `close_automation_browser`

### 5.2 Extension ส่งอะไรกลับ

- Heartbeat: รุ่น Extension, Browser, หน้าเว็บปัจจุบัน และเวลาที่เห็นล่าสุด
- Progress: ขั้นตอน ข้อความ Job/Shot สถานะรูป Prompt Login เครดิต และ URL โปรเจกต์
- Checkpoint: Analysis รูปที่สร้างแล้ว Flow project URL และช็อตที่ดาวน์โหลดแล้ว
- Result: JSON/รูป/วิดีโอที่พิสูจน์แล้วว่าเป็นผลของ Job และ Shot ปัจจุบัน
- Error: สาเหตุที่จัดประเภทแล้ว ไม่ใช่ข้อความเดาสุ่ม

Local Bridge ต้องรับเฉพาะ Extension รุ่นที่ตรงกับ `REQUIRED_EXTENSION_VERSION` เพื่อป้องกันโปรแกรมใหม่คุยกับลอจิกเก่า

## 6. เจ้าของแท็บและกฎไม่ให้เปิดแท็บวน

หนึ่งงานต้องมีเจ้าของชัดเจน:

```text
AI Web: job_id + provider → tab id เดียว
Google Flow: job_id + shot_index + project id/url → tab id เดียว
```

กฎบังคับ:

- ถ้ามีแท็บที่ลงทะเบียนตรง Job/Shot ให้ใช้แท็บเดิม
- ห้ามเลือกแท็บล่าสุดหรือแท็บที่มีผลลัพธ์เยอะที่สุดจากช็อตอื่น
- ถ้าไม่มี Checkpoint ของ Shot นั้นจึงเปิดโปรเจกต์ใหม่
- Resume ต้องทำในโปรเจกต์เดิม ห้าม Reload เพียงเพราะตัวตรวจยังไม่เห็นสถานะชั่วครู่
- ห้ามเปิด Flow URL ดิบก่อนส่งคำสั่งที่มี Job/Shot เพราะจะทำให้ Helper จำ Shot เป็น 0
- ปิดได้เฉพาะแท็บงานที่ Extension บันทึกว่าเป็นของ SmartFlow AI ห้ามปิดแท็บส่วนตัวผู้ใช้

## 7. ลอจิก ChatGPT Web / Gemini Web

### 7.1 ลำดับปกติ

```text
รับ Job package
→ เปิด/โฟกัสแท็บ Provider ที่ผู้ใช้เลือก
→ ตรวจ Login และ Composer
→ ส่ง Prompt วิเคราะห์สินค้า/เรื่อง
→ รับ JSON และจัดรูปแบบตาม Schema
→ สร้างรูปตามจำนวนที่ Job ต้องการ
→ บันทึกรูปทีละใบเป็น Partial Checkpoint
→ เมื่อครบ ส่ง Result กลับโปรแกรม
→ หยุด ไม่เปลี่ยน Provider และไม่ย้อนสร้างซ้ำ
```

### 7.2 Checkpoint และ Resume

- Product สร้าง 3 รูป
- Story ใช้จำนวนรูปตาม Scene ที่โปรแกรมกำหนด
- ถ้ามี Analysis แล้วให้ใช้ของเดิม
- ถ้ามีรูป 1–2 แล้วให้สร้างเฉพาะรูปที่ขาด
- ห้ามเรียกเสียงซ้ำ เพราะเสียงอยู่นอกหน้าที่ Extension
- ห้ามสลับ ChatGPT เป็น Gemini หรือ Gemini เป็น ChatGPT เอง
- ถ้า JSON ไม่ตรง Schema ให้ซ่อมรูปแบบตามจำนวนรอบที่กำหนด แล้วรายงานสาเหตุจริงถ้ายังไม่ผ่าน
- ถ้าบริการปฏิเสธเนื้อหา ให้หยุดและแจ้ง Policy error ห้ามบันทึก Job ว่าสำเร็จทั้งที่รูปไม่ครบ

### 7.3 Login Gate

เมื่อพบ Login, CAPTCHA หรือ Verification:

```text
Extension → user_action_required
โปรแกรม → หยุดเวลา Retry และแสดง Popup
ผู้ใช้ → Login/ยืนยันเอง
Extension → ตรวจ Composer พร้อมจริง
Extension → user_action_resolved
โปรแกรม → ทำ Job เดิมต่อจาก Checkpoint
```

Extension ห้ามอ่าน กรอก หรือบันทึกรหัสผ่าน OTP Cookies หรือ Token ของผู้ใช้

## 8. ลอจิก Google Flow ที่ถูกต้อง

### 8.1 หนึ่งช็อตต่อหนึ่งโปรเจกต์

เส้นทางปกติของ Product ใช้วิดีโอ Google Flow จริงหนึ่งช็อตต่อ source slot แต่ละช็อตต้องใช้:

- รูปที่ตรงกับ `shot_index`
- Prompt ที่ตรงกับรูปนั้น
- Project ID/URL ของช็อตนั้น
- Monitor และผลดาวน์โหลดของช็อตนั้น

กฎข้างต้นเป็นเส้นทางปกติของ Product: ห้ามเอาผลจากช็อตก่อนหน้ามาเป็นช็อตใหม่ และห้ามระบุ local motion ว่าเป็นคลิป Flow หาก source slot ใดได้รับ structured current-card `FLOW_POLICY_BLOCKED` ครั้งแรก ให้ใช้รูป canonical ของ slot เดิมสร้าง local motion ทันที บันทึกใน `flow_local_motion_clips` แล้วเดิน source ถัดไป ห้าม Retry Flow, reupload, reassign หรือ Alternate Take; Final ที่มี local อย่างน้อยหนึ่ง slot ต้องเป็น `google_flow_hybrid_composite` พร้อมจำนวน Flow จริง/local/ทั้งหมดตามจริง

Story และ Drama ที่เลือก Google Flow ใช้กฎเดียวกันแบบรายฉาก: การปฏิเสธต้องมาจาก structured terminal evidence ของการ์ดปัจจุบันเท่านั้น และ terminal ครั้งแรกใช้รูป canonical เดิมสร้าง local motion ของฉากนั้นทันที บันทึกใน `flow_fallback_clips` แล้วเดินฉากถัดไป ห้าม safe-prompt retry, Upload/Submit ซ้ำ หรือ Alternate Take Final ผสมต้องระบุ `google_flow_story_hybrid_fallback`, เก็บ content-mix ของ Drama แยก และรายงาน `flow_clip_count`, `flow_fallback_count` กับรายการฉากสำรองตามจริง

### 8.2 ลำดับที่ยืนยันจากการใช้งานจริง

```text
1. เปิดโปรเจกต์ใหม่ของ Shot ปัจจุบัน
2. อัปโหลดรูปอ้างอิงเพียงครั้งเดียวและรอ media card พร้อม
3. รอรูปอัปโหลดและ media card พร้อมโดยไม่รีเฟรชเพราะ upload100%; ตั้งวิดีโอผ่านเส้นทางปัจจุบันและใช้ข้อกำหนด9:16/หนึ่งคลิปในพรอมต์ตาม source
4. เปิดเมนูเพิ่มองค์ประกอบ เลือกรูปที่อัปโหลด และตรวจว่ารูปแสดงอยู่ใน Composer จริง
5. ใส่ Prompt เพียงครั้งเดียว
6. รอจนรูป + Prompt พร้อม และปุ่มสร้างล่างสุดเปิดใช้งาน
7. กด “สร้าง” เพียงครั้งเดียว; ถ้ายังมีถามเครดิตให้กด `อนุมัติ` ของ Turn ล่าสุดเพียงครั้งเดียว
8. รอคิว/กำลังคิด/เปอร์เซ็นต์/เรนเดอร์โดยไม่แนบรูปหรือส่ง Prompt ซ้ำ
9. ถ้าการ์ดขึ้น 100% แต่ยังไม่มีวิดีโอ รีเฟรชได้เพียงหนึ่งครั้งด้วย Result guard
10. เมื่อวิดีโอใหม่เสร็จ เปิดเมนูของการ์ดล่าสุด → ดาวน์โหลด → 720p ขนาดดั้งเดิม
11. Extension รอไฟล์ `SmartPost/JOB-.../flow-shot-NN.mp4` เขียนเสร็จและบันทึก receipt
12. โปรแกรมตรวจไฟล์และ SHA-256 ก่อนบันทึก Checkpoint
13. ไป Shot ถัดไปเมื่อ Shot ปัจจุบันมีไฟล์จริงแล้วเท่านั้น
```

### 8.3 ประตูตรวจ “พร้อมก่อนกดสร้าง”

ก่อนคลิกต้องผ่านทุกข้อ:

- URL เป็น Project ของ `job_id + shot_index` ปัจจุบัน
- รูปอ้างอิงแสดงอยู่ใน Composer แล้ว ไม่ใช่เพียงอัปโหลดอยู่ใน Media Library
- Prompt อยู่ครบในช่องสร้างวิดีโอ
- ไม่มี File Picker ค้าง
- ไม่มีหน้าต่างยืนยันสิทธิ์ที่ต้องให้ผู้ใช้กดเอง
- ไม่มีหน้า Login/Verification
- เลือกปุ่ม `arrow_forward สร้าง` ที่มองเห็น อยู่ล่างสุดใกล้ Composer
- ปุ่มไม่มี `disabled` และ `aria-disabled` ไม่เป็น `true`

ถ้ามีคำว่า “สร้าง” หลายจุด ห้ามกดปุ่มบนเมนู `add_2 โปรเจ็กต์ใหม่`; ต้องกดปุ่มสร้างล่างสุดของ Composer เท่านั้น

### 8.4 สิ่งที่ห้ามทำเด็ดขาดหลังพร้อมหรือหลังกดสร้าง

- ห้ามแนบรูปซ้ำ
- ห้ามเปิด File Picker ซ้ำ
- ห้ามใส่ Prompt ซ้ำ
- ห้ามกดสร้างซ้ำ
- ห้ามกด Enter และคลิกปุ่มพร้อมกันหลาย fallback
- ห้าม Refresh หน้า
- ห้ามเปลี่ยน URL
- ห้ามเปิดโปรเจกต์ใหม่ขณะมี `กำลังคิด`, `Stop/หยุด`, คิว หรือเปอร์เซ็นต์
- ห้ามสลับ Provider หรือย้อนกลับไปสร้างรูป

หลังคลิกสร้างแล้ว Extension ต้องเปลี่ยนจากโหมด “ลงมือ” เป็นโหมด “เฝ้าดู” ทันที

### 8.5 การแนบรูปแบบ Single-flight

การแนบรูปเป็น at-most-once ต่อ:

```text
job_id + shot_index + flow_project_id
```

- เขียน `startedAt` ก่อน Gesture แนบรูป
- เลือกสื่อเดิมหรือ Trusted drop ได้อย่างมากหนึ่งครั้ง
- ถ้าระบบพิสูจน์รูปใน Composer ได้ ให้ถือว่าพร้อมและห้ามแนบอีก
- ถ้าพิสูจน์ไม่ได้ ให้เป็น `attachment_needs_review` ไม่ลองอัปโหลดซ้ำในโปรเจกต์เดิม
- การเริ่มแนบใหม่ต้องเป็นโปรเจกต์ใหม่ที่มี Attachment key ใหม่อย่างชัดเจน

### 8.6 การรอปุ่มสร้าง

Google Flow อาจใช้เวลาตรวจรูปนานกว่า 20 วินาที หลังรูปและ Prompt พร้อมต้องรอปุ่มเปิดใช้งานได้ถึง 90 วินาทีในโปรเจกต์เดิม โดยไม่ Reload หรือแนบใหม่

ถ้าครบเวลาแล้วยังไม่พร้อม ให้รายงานสถานะพร้อมหลักฐาน DOM แล้วให้โปรแกรมตัดสิน Retry เฉพาะ Shot ห้าม Extension เปิดโปรเจกต์ใหม่เองแบบวนลูป

### 8.7 เครดิตและสิทธิ์รูป

- เครดิต: เลือก “อนุมัติ ไม่ต้องถามอีก” ได้หนึ่งครั้ง ถ้าไม่มีจึงเลือกอนุมัติธรรมดา
- สิทธิ์/ลิขสิทธิ์รูป: ต้องให้ผู้ใช้กดเอง
- เครดิตหมด: ต้องพบข้อความเตือนสดว่าไม่พอจริง ห้ามตัดสินจากยอด 0 เพียงอย่างเดียว
- เมื่อเครดิตหมดให้หยุด Shot เดิม รักษารูป เสียง และคลิปที่เสร็จแล้วทั้งหมด

### 8.8 การพิสูจน์ว่ากำลังสร้าง

หลักฐานอย่างใดอย่างหนึ่งต่อไปนี้หมายถึงต้องรอ:

- `กำลังคิด…` หรือ `Considering Video Generation`
- ปุ่ม `Stop/หยุด`
- สถานะคิวจริง
- เปอร์เซ็นต์ 1–99
- Placeholder ที่เกิดหลังการกดสร้างและยัง Busy

ระหว่างมีหลักฐานเหล่านี้ห้าม Recovery, Reload หรือเปิดโปรเจกต์ใหม่

### 8.9 การพิสูจน์ว่าเสร็จจริง

รับผลสำเร็จได้เมื่อ:

- เห็น Video/Result card ใหม่กว่าค่า Baseline ของ Shot ปัจจุบัน
- หรือเห็นปุ่ม Download ของผลใหม่
- และไม่มี Busy/Progress ปัจจุบัน
- Project/Job/Shot ตรงกับเจ้าของ Monitor

การหายไปของเปอร์เซ็นต์ต่ำ เช่น 11% ไม่ใช่ผลสำเร็จ และการ์ดเก่าที่มีอยู่ก่อนกดสร้างไม่ใช่ผลของ Shot ใหม่

## 9. สถานะสำคัญที่โปรแกรมต้องเข้าใจ

| กลุ่ม | ตัวอย่างสถานะ | ความหมาย/การตอบสนอง |
|---|---|---|
| เตรียม | `package_loaded`, `opening_project`, `preparing` | กำลังเตรียม ห้ามสั่งซ้ำ |
| พร้อม | `ready_to_generate` | รูปและ Prompt พร้อม รอ/กดสร้างครั้งเดียว |
| ส่งแล้ว | `submission_sent` | กดแล้ว กำลังยืนยันว่าคิวเริ่ม |
| ต้องรอ | `generation_started`, `generation_in_progress` | ห้ามแตะหน้า |
| ผู้ใช้ต้องทำ | `user_action_required` | Login, Verification หรือ Rights confirmation |
| เครดิต | `awaiting_credit_approval`, `credit_exhausted` | อนุมัติครั้งเดียวหรือพัก Job |
| สำเร็จ | `generation_complete` | เปิดผลใหม่และดาวน์โหลด |
| ตรวจทาน | `attachment_needs_review`, `generation_status_unknown` | หยุด Gesture เพิ่มและตรวจหลักฐาน |
| ล้มเหลว | `generation_failed`, `wrong_output_type` | Retry เฉพาะ Shot ภายในเพดาน |

สถานะเก่าจากหน้าประวัติห้ามชนะสถานะสดของรอบปัจจุบัน ทุกการตัดสินต้องเทียบกับ Baseline ที่เก็บก่อนคลิกสร้าง

## 10. Checkpoint ใน Chrome Storage

คีย์หลักที่ใช้รักษางาน:

- `smartpostActiveJobId`
- `smartpostActiveShotIndex`
- `smartpostAIWebTab:{provider}:{jobId}`
- `smartpostFlowTab:{jobId}:{shotIndex}`
- `smartpostFlowCheckpoints`
- `smartpostFlowActiveProject`
- `smartpostFlowMonitor`
- `smartpostFlowAttachmentAttempts`
- `smartpostPendingWebAction`
- `smartpostPendingFlowDownload`

Checkpoint ต้องมีอายุจำกัด ล้างเมื่อ Job จบ/ยกเลิกอย่างปลอดภัย และห้ามล้างช็อตที่ยังต้อง Resume ก่อนโปรแกรมบันทึกไฟล์จริง

## 11. Recovery Matrix

| เหตุการณ์ | สิ่งที่ทำ | สิ่งที่ห้ามทำ |
|---|---|---|
| Chrome/Extension หลุด | รอ Heartbeat แล้ว Resume Job/Shot เดิม | เริ่ม Job ใหม่ |
| Login | Popup ให้ผู้ใช้ Login แล้ว Resume Checkpoint | กรอกรหัสผ่านแทนผู้ใช้ |
| รูปพร้อม Prompt พร้อม แต่ปุ่มยังปิด | รอในโปรเจกต์เดิมสูงสุด 90 วินาที | แนบซ้ำ/Reload |
| รูปแนบแล้วแต่ Helper มองไม่เห็น Chip | หยุดเป็น Needs review | Upload fallback ซ้ำ |
| กดสร้างแล้วมีคิว/เปอร์เซ็นต์ | เฝ้าดูอย่างเดียว | กดซ้ำ/เปิดแท็บใหม่ |
| เครดิตหมดจริง | พัก Shot และแจ้งเปลี่ยนบัญชี | ลบ Checkpoint |
| Flow ล้มเหลว | ตรวจ structured terminal: policy/attachment ที่ผ่าน guard ใช้ local motion เฉพาะโหมดที่อนุญาต; อื่นๆตรวจโปรเจกต์เดิมหรือหยุดรีวิว | เปิดโปรเจกต์ใหม่/ส่งซ้ำเพียงเพราะข้อความล้มเหลว |
| ดาวน์โหลดได้ไฟล์ซ้ำ Shot เดิม | ปฏิเสธด้วย SHA-256 | ประกอบ Final |
| ดาวน์โหลดไม่สำเร็จ | เปิด Result card เดิมและลองดาวน์โหลดแบบจำกัด | สร้างวิดีโอใหม่ทันที |
| ผู้ใช้ยกเลิก | หยุดคำสั่งและรักษา Checkpoint | ปล่อย Worker ทำต่อ |

## 12. หลักฐานเหตุการณ์จริงที่ต้องจำ

ดัชนีร่วมโปรแกรม/Extension ล่าสุดอยู่ที่ PROGRAM_BLUEPRINT.md หัวข้อ12.4: known-good ที่มีขอบเขตหลักฐาน, บั๊ก322–325, วิธีแก้, regression tests และสิ่งที่ยังไม่ยืนยัน. อ่านก่อนแก้ซ้ำ; ตารางรุ่นย้อนหลังด้านล่างเป็นประวัติ ไม่ใช่คำสั่งคืนค่าโค้ดทั้งรุ่น.

- Golden `0.15.112` / Git `afcb918`: งาน `JOB-20260830-8BF0DB` ทำ Flow 3 ช็อต ดาวน์โหลดและประกอบ Final สำเร็จ
- `JOB-20260902-88C0E2`: แก้ Shot ownership/Shot 0 และทำ Final สำเร็จ
- `JOB-20260902-CA57FF`: พบการแนบรูปซ้ำและการรับ Result card เก่า จึงเพิ่ม Single-flight และ Exact-shot ownership; Final สำเร็จหลังแก้
- `JOB-20260902-828831`: รูปและ Prompt พร้อม แต่ปุ่มสร้างเปิดช้ากว่า 20 วินาที จึงเพิ่มเวลารอเป็น 90 วินาทีและเลือกปุ่มสร้างล่างสุด
- ลำดับที่ผู้ใช้สาธิตและยืนยัน: แนบรูปครั้งเดียว → ใส่ Prompt → ตรวจหน้าก่อนกด → กดสร้างครั้งเดียว → กดอนุมัติครั้งเดียว → รอจนเรนเดอร์เสร็จ → ดาวน์โหลดก่อนเปลี่ยนหน้า

### 12.1 ผลตรวจย้อนหลังรายรุ่น

| รุ่น/กลุ่มรุ่น | หลักฐาน | สิ่งที่รับเข้ารุ่นปัจจุบัน |
|---|---|---|
| `0.15.70` | Drama one-click Final จริงครบภาพ/เสียง/ซับ/โลโก้/ปก/Audio Mix | เก็บกฎ AI checkpoint และล้างป้ายชื่อผู้พูด; ไม่ใช้ยืนยัน Flow upload |
| `0.15.72` | Product Flow หลาย Job จบ 3/3 และ Final จริง รวมงานกางเกง B9 | เก็บการอ่าน Agent activity/คิวและการเดิน Flow ทีละช็อต |
| `0.15.112` / `afcb918` | หลักฐานสูงสุด: `JOB-20260830-8BF0DB` จบ Flow 3/3 ดาวน์โหลดและ Final | ใช้เป็นฐาน upload/attach/generate/monitor/download |
| `0.15.118` | `JOB-20260831-621A48` จบ Flow จริงหนึ่งช็อต 8 วินาที | เก็บการตรวจ thumbnail/media URL; ไม่อ้างว่าเป็นหลักฐานครบ pipeline |
| `0.15.121–0.15.122` | Drama Gemini Final และ Story 15 ฉาก Final | เก็บเฉพาะ Gemini/Story checkpoint และเพดาน 15 ฉาก |
| `0.15.162` | `JOB-20260902-88C0E2` ทำต่อจากช็อตเดิมและได้ Final 46.10 วินาที | เก็บ exact shot ownership, package reload และ crop แนวตั้ง |
| `0.15.179` | พบ closure แข่งกันและ upload ซ้ำ | ไม่รับลอจิก reinject/แนบซ้ำ |
| `0.15.182–0.15.189` | แก้จากเหตุจริงเป็นรายจุด แต่บางรุ่นมีเพียง targeted tests | รับเฉพาะ exact-result, 90s wait, single physical submit, Slate trusted input, composer proof และ selected-media guard |
| `0.15.194–0.15.196` | ลำดับตั้งค่า/รีเฟรชและดาวน์โหลดพัฒนาต่อ แต่ `0.15.196` ล้มจริงที่ empty picker + file drop + new-project retry | เก็บ settings fallback, 100% refresh และ downloader; ถอด empty-picker-first/file-drop/retry loop |
| `0.15.197` | รุ่นรวมตามลำดับหลักฐานข้างต้น | ต้อง Reload หนึ่งครั้งและผ่าน real 3-shot smoke ก่อนเลื่อนเป็น Golden ใหม่ |
| `0.15.198` | เพิ่ม Run/Lease/Owner-tab และ Session capability จาก Security audit | เก็บ Command lease, stale-run rejection, single-flight monitor และ Token boundary โดยไม่เปลี่ยน Golden physical actions |
| `0.15.199` | ตรวจ Source/Log พบ Successful upload ถูกหยุดด้วยตัวแปร `trustedDrop` นอก Scope และ `open_flow` ACK ก่อน Project handoff | นัด Reload ก่อน Diagnostics, ใช้ `uploadDebug`, ACK หลัง Exact project/helper เท่านั้น และ Snapshot Project tabs ก่อนคลิกเพื่อกันข้าม Job |

เหตุการณ์ที่ทำงานได้ต้องเก็บเป็น Regression/Golden rule ส่วนเหตุการณ์ที่ผิดต้องเก็บเป็นข้อห้าม ห้ามแก้จากการเดาโดยไม่มีหลักฐานหน้าเว็บหรือ Log

## 13. จุดแก้ตามประเภทบัค

| อาการ | อ่าน/แก้ไฟล์แรก |
|---|---|
| เปิดแท็บผิด/เปิดแท็บวน/Shot ผิด | `background.js` ส่วน tab ownership และ command polling |
| แนบรูปซ้ำ/กดสร้างซ้ำ | `flow.js` ส่วน attachment guard และ submit gate |
| อ่านสถานะ Flow ผิด | `flow.js` ส่วน monitor/baseline + `background.js` ส่วน result DOM |
| ดาวน์โหลดผิดการ์ด/ผิด Shot | `background.js` ส่วน exact-shot result/download |
| ChatGPT/Gemini JSON หรือรูปค้าง | `chatgpt.js` + Partial checkpoint routes |
| Login/Verification | `background.js`, `chatgpt.js`, `flow.js`, `core/local_bridge.py` |
| โปรแกรมไม่ทำต่อหลัง Extension รายงาน | `core/local_bridge.py` และ worker ใน `ui/main_window.py` |
| Popup Extension | `popup.html`, `popup.css`, `popup.js` |
| สิทธิ์เว็บ/รุ่น/ไอคอน | `manifest.json` |

ให้ค้นหัวข้อที่ตรงอาการก่อน ห้ามอ่านหรือแก้ทั้ง Extension พร้อมกันถ้าไม่จำเป็น

## 14. การทดสอบก่อนอัปเดต Runtime

ขั้นต่ำทุกครั้งที่แก้ Extension:

```text
1. ตรวจ JavaScript syntax: background.js, chatgpt.js, flow.js, popup.js
2. ตรวจ manifest และ version ให้ตรง Local Bridge
3. รัน targeted tests ของอาการที่แก้
4. รัน Extension bridge harness
5. รัน Product/Flow/Login regression
6. Real smoke test หนึ่ง Shot โดยผู้ใช้เห็นหน้าจอ
7. ยืนยันว่าแนบรูปหนึ่งครั้ง กดสร้างหนึ่งครั้ง และดาวน์โหลดผลใหม่จริง
8. จึงค่อยประกาศเป็น Runtime/Golden ใหม่
```

ห้ามเพิ่ม Selector, Click fallback, Reload หรือ Recovery ใหม่จากการเดา และห้ามเปลี่ยน Submit + Monitor + Download พร้อมกันหลายชั้นในรุ่นเดียว

## 15. Definition of Done ของ Extension

- Extension และโปรแกรมใช้ version ตรงกัน
- Heartbeat ต่อเนื่องและไม่มี Client ซ้ำควบคุมหน้าเดียวกัน
- Provider ตรงกับที่ผู้ใช้เลือก
- Job/Shot/Project/Tab ตรงกันตลอดรอบ และ `open_flow` ACK สำเร็จเฉพาะหลัง Exact Project handoff
- รูปและ Prompt ถูกส่งครั้งเดียว
- ปุ่มสร้างถูกกดครั้งเดียว
- หลังเริ่มสร้างไม่มี Refresh หรือเปลี่ยนหน้าเอง
- Result เป็นการ์ดใหม่ของ Shot ปัจจุบัน
- ดาวน์โหลดคลิปจริงได้และ SHA ไม่ซ้ำช็อตอื่น
- Login/เครดิต/สิทธิ์รูปแจ้งผู้ใช้ถูกประเภท
- Resume ทำเฉพาะสิ่งที่ขาดและไม่ย้อนใช้เครดิตขั้นที่สำเร็จแล้ว
- ปิดเฉพาะแท็บงานเมื่อ Job จบ
- มี Test และบันทึกเหตุการณ์ในพิมพ์เขียวก่อนอัปเดต Runtime

## 16. Persistent approval, compact overlay และ Download scene (อัปเดต 2026-09-03)

- DOM หน้าจริงของคำถามเครดิตรุ่นล่าสุดใช้ `role="radio" aria-label="อนุมัติเสมอ"`; Extension เลือกแถวนี้ก่อน `อนุมัติ ไม่ต้องถามอีก` และ `อนุมัติ` แล้วกดหนึ่ง trusted click ต่อคำถาม ห้ามกดซ้ำเมื่อ radio ถูก checked/disabled หรือมีคิว/ผลลัพธ์แล้ว
- หลังอนุมัติให้ monitor โปรเจกต์เดิมจนพบวิดีโอใหม่ ห้าม reload, เปิดแท็บใหม่, แนบรูปซ้ำ หรือส่ง Prompt ซ้ำระหว่างรอ
- หน้าแก้ไขผลลัพธ์ใหม่มีปุ่ม `aria-label="ดาวน์โหลดฉาก"`; downloader รองรับทั้งปุ่มนี้ เมนูดาวน์โหลดแบบเดิม HTTPS evidence และ player/blob โดยผูก Job/Shot และบันทึก `flow_download_path` ให้ Desktop รับไฟล์ได้อย่างเจาะจง
- Overlay ของ Google Flow ย่อเป็นแถบสถานะโดยปริยาย รายละเอียดซ่อนจนกดขยายและเปิดเองเมื่อพบ Error/User action มีปุ่ม `คัดลอก Log สำหรับ Codex` ซึ่งรวม Version, Build, URL, Job, Shot, Run และหลักฐาน attach ล่าสุด
- Regression guard: `tests/test_flow_approval_overlay_error_log.py`
- URL `/project/<project-id>/edit/<media-id>` ไม่ใช่หลักฐานว่าเป็นรูปนิ่งอีกต่อไป เพราะ Flow รุ่นปัจจุบันใช้ route เดียวกันกับตัวแก้วิดีโอที่สร้างเสร็จแล้ว ให้พิสูจน์วิดีโอจาก `ดาวน์โหลดฉาก`, `แก้ไขฉากเสร็จแล้ว` หรือตัวเล่น `<video>`; ถ้าพบให้ดาวน์โหลดผลเดิมทันที ห้ามย้อนกลับไป Generate
- หลัง Desktop/Engine รีสตาร์ต หาก binding ของ Job/Shot หาย แต่มี Flow project เปิดอยู่ ให้รับแท็บกลับได้เฉพาะกรณีพบ finished-video editor ที่เข้าเงื่อนไขเพียงแท็บเดียว ถ้ามีหลายแท็บต้องหยุดและแจ้ง ห้ามเดาว่าแท็บล่าสุดคือของ Job นี้
# เวอร์ชัน Runtime ปัจจุบัน: `0.15.336` — Story cross-chat recovery

User explicitly permits a different chat. On changed conversation URL, a unique FULL matching prompt must be its latest user turn; rebind to its live IDs and collect only its answer. Preserve same-chat exact-message ownership, stable image and saved-media ACK. No resend or arbitrary latest image. docs/reports/story-cross-chat-336.md; installed336 pending.

335 supersedes334's incorrect whole-button text matching: actual responsive spans concatenate mobile and desktop labels. Match exact semantic child span labels after current reply ownership. Read docs/reports/story-responsive-comparison-335.md; installed335 pending.

chatGPTStoryImageSnapshot recognizes the explicit two-image preference controls only inside the exact owned reply, chooses one loaded image locally, and keeps stable receipt/download/ACK gates. Resume can recover the saved request; no vote, Send or regeneration. Other ambiguous images stay review. docs/reports/story-image-comparison-334.md; installed E2E pending.
# Runtime 0.15.352 — alternate image-only reply

Flow alternative image_sent uses the exact unique current request and subsequent conversation frames, including roleless ChatGPT image responses. Old/source images and busy/incomplete outputs are excluded. Proof persists before existing image ACK; no global assistant selector/Send/retry changes. Desktop repair status is explicit. docs/reports/alternate-image-352.md. Installed recovery pending.
# Shorts actor dialogue / 0.15.378

Opt-in ACTOR DIALOGUE context from desktop is an ordered actor/speech contract, not product review narration. ChatGPT/Gemini motion preparation includes speakers/listeners and silent acting instructions. Alternate-scene proposals replace only visual action; retain original actor dialogue and do not replace it with scene_narration or hands-only off-screen review. Existing Send, result ownership, receipt and retry policies remain unchanged. Meta adapter receives the desktop-authored prompt unchanged. Installed new-version E2E pending; see docs/reports/shorts-actor-dialogue-378.md.
# Runtime 0.15.426 — audited recovery and desktop pairing

Meta's completed image-not-viable or post-follow-up no-video result enters desktop `redesign_prepare` with exact owned terminal proof. `ensureMetaRedesign` owns one fresh ChatGPT/Gemini helper and uses `runMetaRedesignHelper` for complete JSON + new image. A completed override returns a new context/request; adapter adopts it before comparing old context, then opens a new Meta conversation. Lost completion ACK returns the same successor. `smartflowRepairHelper` Send ownership checks the current desktop redesign and session tab binding. Browser bootstrap is limited to locally verified installed SmartFlow identities, scoped to origin/profile, without Extension login input. See `docs/reports/audit-fixes-426.md`; fixture validation is not installed E2E.
## Saved-image handoff 471 (canonical integrated; user activation pending)

After the desktop image ACK, finishScene explicitly reports the saved image while waiting for video/voice handoff. A rejected gate preserves its original error prefix and states that the image must not be regenerated. No Send/retry budget or next-scene barrier changes. Paired desktop correction preserves approved expressive turns. See docs/reports/editorial-handoff-471.md and logic-version-map-471.md; user owns activation. Historical versions/headings below are not today's authority. Old Meta Vibes removal does not describe the current Meta AI video adapter. Keep proven single-flight/receipt behavior; do not transplant obsolete selectors from a historical success.

An explicit per-job authorization allows one scene 2 retry after a prior-run uncertain Send. The content script checks the original receipt and unchanged ChatGPT draft/reference over three samples, archives the old receipt with an ACK, then creates a new prepared receipt carrying the one-time token. Later resumes read the new receipt and cannot prepare another replay from the same authorization.
