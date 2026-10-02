# SmartFlow AI — Codex Quick Blueprint

Paired 0.15.507 permits the existing guarded upload path to reattach the saved prior scene when the one-time replay preflight finds no visible or hidden file. See `PROGRAM_BLUEPRINT.md` “Owner-authorized uncertain Story image replay / 0.15.505–507” and `EXTENSION_BLUEPRINT.md` top. Activation and live provider output are separate checks.

Paired 0.15.504 extends the uncertain Story image watchdog to result-only checkpoint Resume. A prior-run dispatching receipt with the exact draft still present now stops after three read-only observations over 15 seconds with `PRIOR_RUN_UNCONFIRMED_DRAFT_PRESENT`; it does not refresh or resend. Live checkpoint retry reproduced that exact bounded review with zero new Send events under the original Extension ID and root launcher 504. See `PROGRAM_BLUEPRINT.md` “Prior-run Story image draft watchdog / 0.15.504” and `PROJECT_STATE.md` top.

Paired 0.15.503 candidate bounds a Story image Send that was dispatched but never accepted while its exact draft stays in the composer. After three five-second read-only checks it records a specific review error instead of an indefinite image wait; it never clicks Send again. Installed 502 Story 55A401 remains active, so activation waits until idle. See `PROGRAM_BLUEPRINT.md` “Uncertain Story image Send watchdog / 0.15.503” and `PROJECT_STATE.md` top.

Paired 0.15.502 extends the three five-second read-only Send checks to a transient ambiguous ChatGPT target and keeps the exact reason/recheck count in new Story content traces. Bridge and original Extension ID connected at 502; Story 9DF011 saved scene 4 after one Send and advanced to scene 5. The active Story tab may retain its prior content script, and the SmartFlow window predates launcher 502; leave them running and reopen only when idle. See `PROGRAM_BLUEPRINT.md` “ChatGPT ambiguous Send recheck / 0.15.502” and `PROJECT_STATE.md` top.

Paired 0.15.501 adds three read-only ChatGPT Send preflight rechecks at five-second intervals for a transient missing or blocked Send control or active response. The exact Story draft, owner, single gesture, and prepared receipt guards remain. Bridge and original Extension ID are connected at 501; Story 9DF011 saved scene 3 and advanced to scene 4 after one Send. The current SmartFlow window began under launcher 500 and must be reopened under the root launcher 501 once the active Story finishes. See `PROGRAM_BLUEPRINT.md` “ChatGPT Send readiness retry / 0.15.501” and `PROJECT_STATE.md` top.

Paired 0.15.500 on `feature/webview2-prototype` adds passive post-video cover liveness and result collection plus owned unsent Story reference cleanup. Root SmartFlow and the original Chrome Extension ID connected at 500 in DEV MODE; queued Story A9425B resumed from saved scene 1 and saved scene 2. Cover heartbeat awaits live provider output. An older, different immutable 499 package remains in the main root. See `PROGRAM_BLUEPRINT.md` “AI cover send diagnostics” and `PROJECT_STATE.md` top.

รุ่น `0.15.497` เป็น candidate แยกสำหรับรับภาพ Story ที่เสร็จแล้วแม้ตัวบ่งชี้ progress ค้าง โดยยังตรวจ Stop/เจ้าของผลและไม่ส่งซ้ำ; โปรแกรมและ Chrome ที่เปิดอยู่ยังใช้ 496 ระหว่างงาน `STORY-20261002-E25264` ทำงาน.

รุ่น `0.15.496` ติดตั้งและเชื่อมต่อใน DEV MODE ใช้กรอบช่องพิมพ์เดียวกันเพื่อตรวจ/แนบรูปอ้างอิง Story และหยุดก่อนส่งถ้าจำนวนรูปไม่ตรง; ดู `PROGRAM_BLUEPRINT.md` หัวข้อ Story image composer scope and attachment count และรายงาน 496. งานจริง CB0614 เสร็จภายใต้ 495 แต่ฉาก 5 นับรูปแนบ 2 ต่อคำขอ 1; ผลจริงของกติกา 496 ยังไม่ยืนยัน.

รุ่น `0.15.492` เปิดใช้และเชื่อมต่อแล้วใน DEV MODE: Story ใหม่จัดการร่างเก่าที่ถูกคืนมาในแท็บ ChatGPT ซึ่งโปรแกรมเพิ่งเปิดเอง โดยล้างเฉพาะข้อความในแท็บงานใหม่ ตรวจว่าหน้าว่างคงที่ แล้วเริ่มคำขอหนึ่งครั้ง หากแท็บที่เลือกไว้เปลี่ยนระหว่างตรวจจะย้ายไปแท็บงานใหม่โดยไม่แตะแท็บเดิม ไม่ล้างงานที่มีไฟล์แนบ บทสนทนา หรือกำลังสร้างผล และไม่ส่งซ้ำงาน Resume. ยังไม่ลอง Story ใหม่กับผู้ให้บริการ; ดู `PROGRAM_BLUEPRINT.md` หัวข้อ Automatic Story bootstrap draft recovery และรายงาน 492.

รุ่น `0.15.491` เปิดใช้และเชื่อมต่อแล้วใน DEV MODE: หลังรัน490จริง Story 895662 หยุดก่อน Send เพราะหน้า ChatGPT ไม่ว่าง แต่ Chrome ไม่แสดงเหตุให้เห็นชัด. รุ่น491 ตรวจความว่างสองครั้งหลังหน้าโหลด, ข้ามแท็บงานเก่า, รอ composer ชั่วครู่ และแสดงข้อความบนแท็บพร้อมบันทึกเพียงรหัสเหตุ/แท็บโดยไม่เก็บร่าง. งานเดิมยัง error, คิวหยุดอยู่, ยังไม่ทดสอบ Story ใหม่กับผู้ให้บริการ; อ่าน `PROGRAM_BLUEPRINT.md` หัวข้อ Story bootstrap review และ `docs/reports/story-bootstrap-review-491-20261002.md`.

รุ่น `0.15.490` เป็นคู่ MAIN/Extension ที่เปิดใช้และเชื่อมต่อแล้วใน DEV MODE: Story ใหม่จะเลือกแท็บ ChatGPT หน้าแรกเฉพาะเอกสารที่ว่างจริง หากมีร่างค้างจะเก็บแท็บเดิมและเปิดแท็บใหม่เพียงครั้งเดียว ตรวจซ้ำก่อน Start. งาน Story ที่ล้มเหลวเดิมและร่างปกยังเก็บไว้; ห้ามส่งซ้ำอัตโนมัติ. ยังไม่ทดสอบส่งคำขอจริงกับผู้ให้บริการ. อ่าน `PROGRAM_BLUEPRINT.md` หัวข้อ Story bootstrap tab guard และ `docs/reports/story-bootstrap-tab-490-20261002.md`. รุ่น 489 เป็นแพ็กที่พักไว้ ไม่เคยเปิดใช้.

รุ่น Runtime `0.15.487`: canonical MAIN487.0 + Extension487 source/41-file package integrated after cold guard and 16-file backup; 23 targets copied exactly and 13 protected user-state files unchanged. Pure UI state and bridge diagnostic filters were extracted behind their existing entry points; modular JobRouter timeout and paired-build preflight added. Focused canonical checks passed. Full suite 2,788 tests remains NON-GREEN; see `docs/reports/refactor-low-impact-487-20261001.md`. Chrome activation, installed identity and provider output remain unverified; no Setup or provider Send. Older headings are chronology.

รุ่น Runtime `0.15.486`: canonical MAIN486.0 + Extension486 from original466/Send-only484–485,15-targetbacked-upcoldhandoff complete,10694protectedhashesunchanged. Composer-owned unique nativeSend/submit resolver; center→oneoffscreen scroll→interior nativehit points BEFORE the onlypress; passiveacceptance, no unknown-Send replay.485heldimmutable for mismatchedhelperversiontags,486tag-only correction/no newfunctionalruntime. Full485once2785NON-GREEN retained and exact5rechecks pass; no fullrerun. InstalledChrome486/provideroutput unverified, no launch/credits/Setup. See docs/reports/chatgpt-submit-contract-486-20261001.md. Older headers are chronology.

รุ่น Runtime `0.15.484`: original466-derived ChatGPT Send-only MAIN pair integrated. Acenter → Bone offscreen scroll → Ceight interior hit-tested points BEFORE press; final arm binds exact draft/owner/node/frame/point/focus. No second press/Enter. MAIN484.0 and immutable40-file Extension484 verified; no477–483 UI/runtime merged. Native14/final-focused67 pass; original full2780 NON-GREEN with17 exact fixture/environment cases resolved, no runtime change. Installed Chrome activation and real output unverified. See docs/reports/chatgpt-send-fallback-484-20261001.md; older runtime headings below are history.

LIVE ROLLBACK CHECKPOINT: main466 is normally open UI41088/engine7188,5targetedchecks passed,982original files still exact. Chrome reports483/incompatible466; do not mistake source rollback for installedextensionrollback. Await user-supported466enable/load and disableotherSmartFlowcopies without deletion/storagetransfer/policybypass. Oldqueuepaused, no newproviderjob. Report docs/reports/rollback-all-466-20261001.md; evidence build/rollback-all-466-20261001/runtime-activation.json.

CURRENT USER CHOICE:466 ONLY. Read `docs/reports/rollback-all-466-20261001.md`. Original cumulative464+465+466 stage restored mechanically to canonical;982 managed files exact, no later patches/helpers remain in runtime. Original source-launcher0.2.0.0 loads required466; do not bump its label or mix in483 EXE. Original40-file Extension466 source/folder/ZIP exact. Config/workspace/media preserved. Chrome activation remains a separate unverified step under existing no-policy-bypass constraints. No old queue resume, new provider generation, Setup or re-upgrade without a new user request. Newer chronology below is not current. Rollback evidence and recoverable483 backup are under `build/rollback-all-466-20261001/`.

CURRENT ROOT MAIN483.1 OPENED: start `docs/reports/main-project-483-1-20261001.md` and `build/main-project-483-1-20261001/canonical-handoff-verification.json`. The screenshot was caused by handing off a stage EXE without user config; fixed through cold-safe scoped integration of tested main/runtime/paired Extension483 into root, preserving existing config. Root visible UI32316/engine15860 and one compatible connected483 verified. Never launch stage/create dummy config/copy EXE alone. Installed identity/path and real Final still unverified; full483 NON-GREEN. Creation queue paused/running0; no provider Send, credits or Setup. Existing startup recovery changed only posting queue after all874 protected hashes matched prelaunch; no manual state edit/restore or claim of exact old-body parity. Historical staged-only paragraphs below do not describe current state.

Latest requested MAIN483.1 build: `docs/reports/main-project-483-1-20261001.md`. ActualEXE compiled with restoredexistingicon and immutableExtension483 pair; sourcefunctionalruntimeunchanged, noSetup. Builtonly, NOT rootintegrated/activated. Canonical480.1 unchanged; Main/Pythonabsent/8765closed butChrome/providerunknown. No coldhandoff permission from unreachablebridge; preserve pendinginstalledidentity evidence, oldjobs and versionedartifacts.

Latest483 isolated paired candidate: `docs/reports/chatgpt-analysis-reconcile-483-20261001.md` and `build/chatgpt-analysis-reconcile-483-20261001/handoff-checkpoint.json`. Main483.0/Extension483 built, no Setup or canonical handoff. Strict exact full-request completed-analysis reader plus durable completed-invalid repair capped2. Real73CD14 has matching submitted request and JSON2scenes, but no appcheckpoint/media; editorial UNSUPPORTED_CLAIM must be repaired, not suppressed. Full483 once NON-GREEN/no drift/all19newmethods passed; post-full4fixture-only methods passed/runtime+artifacts unchanged, no full rerun. Last live480 Story/background stillbusy. Preserve original tab/client/receipts, no oldqueueStart or extensions-admin policy bypass. One Loaded-from480 request pending.

Current480.1 main is now canonical and normally started; Extension480 source/artifact pair verified but actual Chrome remains479 incompatible. See the480.1 report's later handoff section. Preserve selected approved two-scene plan and all receipts; one Loaded-from response is needed before an identity-preserving activation. No policy bypass, oldqueueStart, provider Send or realFinal claim. Parent full remains NON-GREEN.

Current480.1 desktop-only candidate: `docs/reports/plan-image-handoff-480-desktop-diagnostics-20260930.md`. Main480.1 plus byte-identical frozen Extension480 (not a new Extension release) repair only bounded source-attachment diagnostics transport. Existing ownership/unknown-Send vetoes remain; the original upload predicate and provider output are still unverified. Parent480 full suite is NON-GREEN, not rerun; the candidate_ status contract is corrected only in this branch. Use exact scoped/pair proof before any handoff. No Setup or live activation in this stage.

Current480 isolated main/Extension pair: `docs/reports/plan-image-handoff-480-20260930.md`. Strict semantic prepared-boundary equality + bounded attachment predicate diagnostics only. Source tests preserve saved plan→imageACK→image-groundedMeta prompt→videoACK→nextscene; these synthetic results do not establish live output. Main479+connectedExtension479 were compatible; candidate480notactivated. Do not repeat oldqueue, change activefiles or bypass browserpolicy. Buildmain withExtension; no Setup.

CURRENT479 CANONICAL MAIN PAIR: start `docs/reports/gpt-answer-recovery-479-20260930.md`. Actual main-root EXE479.0 and matching runtime/Extension479 source are integrated through the guarded28-target backup/handoff;42-file immutable Extension parity and387 protected files unchanged verified. Canonical integration61/61 passed20.484s with no drift. Completed-invalid GPT recovery and NEW-job Shopee per-scene JSON retain original owner/Send/image receipts; unknown Send, login/quota/policy or unchanged invalid answers cannot retry. Focused189 passed; one frozen full3042 completed NON-GREEN, all new19 passed, no source drift/new failing IDs versus478. Installed activation and real provider Final remain unverified, with no provider credit use or Setup. User wants NEW jobs, not old-job recovery. Never reapply the cold handoff or resume the old queue. Earlier478 integration/candidate entries below are chronological.

Current runtime: actual root EXE launched, UI26324/engine8320, bridge requires479. All3progress/combined background inactive; paused queue/running0 retains4oldrows. Chrome existing profile has only connected478, incompatible479; main activation verified but paired Extension479 activation/identity/path and actual Final blocked/unverified. Do not bypass the previously blocked extension-admin page or start the old queue; no provider Send/credits occurred.

CURRENT478 MAIN PAIR: start docs/reports/shopee-attachment-fix-478-20260930.md. Actual main-root SmartFlow AI.exe478.0 plus matching changed Python/UI/Extension478 source are integrated after a backed-up10-target cold handoff;42-file immutable artifact parity verified. No Setup. Installed Chrome activation and a playable Final remain unverified. Do not reapply handoff, recreate retired job ownership, reset receipts or claim all tests passed. Every Extension update must build and verify the actual main project too; staging build, canonical integration, installed activation and real output are separate outcomes.

CURRENT477 HANDOFF: start docs/reports/shopee-gpt-meta-477-20260930.md. Actual main source/EXE and paired42-file Extension477 are integrated in canonical with exact73-target backup, protected state untouched and no Setup. Chrome activation and actual two-scene Final remain pending. Supported188 focused checks pass but full3010 has unresolved105fail/79error/10skip. Do not reapply handoff, silently migrate identity/storage, bypass chrome://extensions browser policy or resume abandoned jobs. User supplied the two-scene Shopee link and authorized credits; start only after the actual matching Extension is observed.

CURRENT477: read docs/plans/shopee-gpt-meta-v1.md. NEW Product-only marker1 implements exact N1–10 and serial original refs → saved scene image → GPT Meta prompt → stored Meta clip before next scene. API auto text means reading saved dialogue with existing voice, not selecting a new voice/style. User authorized first real two-scene Shopee link test. Main source/EXE + paired Extension477, NO Setup. Built/source/fixture/installed/real Final must be reported separately; canonical/activation/Final remain unverified at this checkpoint. Legacy Story/jobs stay unchanged and abandoned work stays parked.

รุ่น Runtime `0.15.476` — isolated GPT + Meta focus. Only Shopee Product and Story Shorts new workflows; ChatGPT text/images and Meta video. Google Flow/Gemini/Drama/long-video creation disabled at UI, desktop actions, command pre-lease and Extension dispatch. Old files/options/receipts remain readable, never remapped or automatically resumed. Candidate475 is held for a reproduced Meta service-worker restart collector defect;476 uses only exact current-command trusted session permits, never startup adoption. Build actual changed main project plus paired Extension, no Setup. Source/fixture/build proof is not installed provider/Final proof. See docs/reports/gpt-meta-focus-476-20260930.md. Earlier474/466/rollback/MVP paragraphs are history, not current authorization.

MAIN474 canonical source and rebuilt EXE integrated (2026-09-30), NOT a Setup installer. Start docs/reports/main-project-474.md. Desktop-required/manifest/release/helper-build474 are paired in source; canonical integration30/30 passed,945 tested files and41 Extension files exact,47 protected hashes unchanged. Chrome still loads immutable473, unchanged; do not launch the main app until the paired extension activation is resolved. No queue/receipt changes, provider Send or new Final proof. Preserve extension identity/storage and do not resume AD0434 under a new identity. Earlier candidate/473 build status paragraphs are historical.

กฎบิลด์ถาวรจากผู้ใช้ (2026-09-30): ทุกครั้งที่บิลด์/แพ็กเอ็กเทนชั่น ต้องบิลด์โปรเจกต์หลักพร้อม source/logic และคู่รุ่นที่ตรงกันในงานเดียวกัน ไม่ส่งมอบเอ็กเทนชั่นเดี่ยว ไม่ถือว่าแก้เลขรุ่นหรือบิลด์ launcher เก่าอย่างเดียวเพียงพอ ไม่บิลด์ Setup เว้นแต่สั่งชัดเจน อ่าน Mandatory paired-build rule ใน AGENTS.md; เตรียมแยกเมื่อยัง active/unknown และไม่อ้าง built เป็น activated หรือ Final สำเร็จ การแก้เอกสารอย่างเดียวไม่ต้องบิลด์ใหม่

รุ่น Runtime `0.15.473` canonical integrated; main SmartFlow AI.exe rebuilt. Source Desktop/Extension paired473, canonical22/22 integration tests pass. Chrome473 activation/real Final pending. Start docs/reports/main-project-473.md; user requested main project NOT an installer. Never reapply the deferred handoff or resume the cancelled partial beta23 build.

LATEST473 CANDIDATE ONLY: docs/reports/fresh-provider-recovery-473.md remembers the user's fresh Meta/GPT completed-response rule. Canonical/loaded472 remains untouched; never reapply old patches or reload/restart while loaded/unknown. Preserve completed scenes and uncertain Sends. Offline candidate proof is not provider/Final proof. No new installer or user-job/queue mutation.

LATEST CUSTOMER BUILD: beta.22 / paired472, docs/reports/customer-installer-beta22.md. Guarded local build and isolated frozen engine/media verification passed; source unchanged. Immutable output deliverables/customer-0.3.0-beta.22/. User runtime472 remained active; do not install/reload/stop it as cleanup. Clean-PC/provider/upgrade E2E and signing remain unverified. Older no-installer notes refer to prior source-only tasks.

LATEST472 INTEGRATED: read docs/reports/flow-model-fallback-472.md. Main-source handoff23-file parity, focused91pass and canonical integration6pass confirmed;40-file Extension472 packaged. Chrome activation/user-provider test remains user-owned and unverified. Route Flow model choice through core/flow_settings.py, ui/flow_settings.py, web_ui/flow_settings.js, browser_extension/flow_settings.js and CONFIGURE_FLOW_VIDEO_SETTINGS in background.js. Omni default applies to new requests; saved snapshots stay immutable. Only proven missing/disabled model may fall back before Generate. Do not reapply the candidate, reinterpret FLOW_SCENE_PLAN_STALE as model absence or rerun completed suites without a relevant change. No installer requested.

CANONICAL470 NOW INTEGRATED: read docs/reports/analysis-recovery-470.md before acting. Main-source handoff and131pass/1skip integration verified; user-provider E2E and Chrome activation pending. No installer requested. Do not reapply old staged patches or interpret the earlier candidate/pending chronology below as current main status.

User-requested clip workflow history (470 candidate): route to PROGRAM_BLUEPRINT “Local clip workflow history (schema 1)” and `core/clip_run_history.py`. Look at one selected failing run plus a relevant preserved success before future updates; do not scan all customer jobs. Library file details exposes a read-only summary/open-folder button. Main activation is still pending.

รุ่น Runtime `0.15.470` candidate: read docs/reports/analysis-recovery-470.md first. User requests main-project test before any installer. Never claim canonical integration or Chrome activation until recorded there. Durable raw analysis, pronunciation reading alias and new-product repair protocol are scoped changes. Product Meta serial v2 is deferred after a mixed-provider compatibility audit; keep existing media ordering and selection. Preserve old work/receipts, cumulative469 and immutable beta21/469. No installer or monitor restart.

รุ่น Runtime `0.15.469` is integrated into canonical source; installed Chrome activation remains user-owned and unverified.

MAIN469 INTEGRATION (2026-09-29): begin docs/reports/main-upgrade-469.md, then docs/reports/customer-portability-beta21.md for prior fixture/build evidence. Applied the exact28-file handoff after confirming SmartFlow/Chrome absent; all909 tested files matched. Includes customer path portability, Meta prepress resize recovery, owned Gemini image remount and local diagnostics. Existing main EXE loads this source on the user's next launch. Beta.21/469 artifacts already exist and remain immutable. Do not reapply staged patches, downgrade, launch/focus UI while the user is gaming, install Chrome or restart the paused monitor. Older active468/pending-build notes below are historical.

Latest customer Setup: beta.20 / paired468, canonical cumulative468 plus Shopee deletion-v2. Built and locally frozen-verified; docs/reports/customer-installer-beta20.md has hashes and limitations.2679payload/301inputs/40Extensionfiles pass; own38312closed after Thai media smoke. All869tested files remain exact. Do not rebuild/overwrite beta20, reapply patches, restart the paused monitor or infer Chrome activation. Older pending/beta19 statements below are history.

Latest desktop follow-up: Shopee permanent-delete batch-v2, canonical integrated on paired468; route docs/reports/product-delete-batch-v2-20260929.md → web_ui/product_continue.js → ui/product_jobs.py → core/product_job_deletion.py. Full2807:2799pass/8skip/0failures/errors,869 tested hashes exact. Independent per-item blocked reasons, no cascade or provider Stop, no real-job deletion by tests. User explicitly requested beta.20 installer; verification pending. Older “no installer” statements describe earlier scopes.

รุ่น Runtime `0.15.468` integrated; Chrome activation pending: lossless pronunciation approval/persistence, exact old-checkpoint repair and wrapped editorial error routing. Full2794:2786pass/8skip/0failures/errors; integration115/115pass,868 tested files exact.215C11 approval repaired once with backup, original checkpoint/receipts/scenes/queue preserved; no generation or resume. Includes467; Extension468 packaged for user installation. Start docs/reports/editorial-persistence-468.md; never reapply the staged patch or one-job repair. No installer or monitor restart.

รุ่น Runtime `0.15.467` (canonical integrated, activation pending): Thai Meta safety-service outage, passive exact-owned Story image reconciliation after prepress rejection, and immediate native unavailable-panel refresh. See docs/reports/provider-recovery-467.md. User closed SmartFlow;22source/doc/test files integrated,866tested fingerprints exact. No Chrome reload/install or app restart. User must activate467 before new work; do not reapply staged patches. Beta19 is still the older466 installer.

Latest requested customer Setup is beta.19 / paired466, built from canonical main: docs/reports/customer-installer-beta19.md. Guarded payload and isolated frozen-engine/media checks passed; not installed, published or clean-PC verified. Main app became active during packaging and was preserved. Use this installer checkpoint, not beta18/464, for the next customer version. Runtime remains466.

MAIN UPDATE COMPLETE (2026-09-29): canonical and running desktop are paired with the user's existing Extension0.15.466. Start at docs/reports/main-upgrade-466.md. Includes approved464 speech,465 editorial and466 Send receipts; no older patch should be reapplied. Integration471:468pass/3skip/0failure/error; config and all154 saved queue rows/options unchanged. Normal main EXE is open; connected466 is compatible and UI shows both versions466. No Chrome reload/install, provider generation, installer, queue resume or monitor restart. All isolated/staged-only notes below describe earlier checkpoints.

รุ่น Runtime `0.15.466` (isolated candidate): verify actual provider acceptance, not only Send/Generate dispatch; includes464+465. Route docs/reports/provider-send-receipt-466.md → chatgpt.js::sendAndVerify / geminiImageSendAccepted, Meta video.js::step/stepChoice, flow.js::readGenerationState, LocalBridge bounded proof enums. Canonical463 remains untouched; no installer or activation implied.

รุ่น Runtime `0.15.465` (isolated, cumulative464): Shopee evidence → product_editorial → Story checkpoint typed repair → shared writer approval → existing serial media. Route docs/reports/product-editorial-465.md. New jobs only; no migration, no canonical merge/Chrome activation yet. Older464 patch is superseded by the cumulative465 handoff, not another patch to stack.

Customer beta.18 / paired Extension464 built at user request (2026-09-28) from the verified isolated professional-speech464 source, NOT the older canonical463. Guarded builder passed39tests/1symlinkskip;2679payload/299inputs/40Extension files verified. Frozen engine beta.18/464 and bundled Thai H264/yuv420p smoke passed; owned38100exited and privateportclosed. Setup in deliverables/customer-0.3.0-beta.18, report docs/reports/customer-installer-beta18.md. No installation, Chrome reload, provider generation or monitor restart. Main runtime source still463; do not claim main integration or use463 for the next build. Prior install-when-safe patch must be regenerated against these release-document updates before integration; never weaken runtime baseline checks.

รุ่น Runtime `0.15.464` (isolated professional-speech candidate): start at docs/reports/professional-speech-464.md. New jobs only capture speech_delivery_version1, shared professional writing guidance, derived exact speech/role/placement snapshots, matching pronunciation preparation, and canonical Meta/Flow audio. Preserve legacy jobs/paid keys, pointing-review POV and serial receipt barriers. Unknown speakers must not silently become narrator. User owns Extension installation; source tests do not prove live voices or activation. Canonical merge is pending loaded-source safety.

Canonical463 is now integrated in the MAIN program (2026-09-28), including461+462 and Shopee "นิ้วชี้". User handles Extension installation; no live activation/provider generation claimed.330/330 post-merge checks passed; source/desktop markers463 and40-file ZIP verified. Route docs/reports/main-upgrade-pointing-463.md first. Existing EXE loads the new main source on next launch. The staged-only notes below describe prior preparation; do not apply those patches again.

รุ่น Runtime `0.15.463` (cumulative staged only): Shopee แนวบท “นิ้วชี้” → core/product_pointing.py + creative_brief/product_script/product_story → shared chatgpt.js image context → Flow motion + Meta package/recovery. Saved product_script_options v3 pointing_review keeps camera-holder POV and off-camera voice. Existing queue/scene gates and presets unchanged. Includes461+462; no installed activation. See docs/reports/shopee-pointing-review-463.md.

รุ่น Runtime `0.15.462` (cumulative staged only): Meta safety-check service unavailable is technical, not content refusal. Route docs/reports/meta-safety-service-462.md → metaReplyFailure/meta_reply_failure → _service_retry → _redesign_prepare. First same-input fresh Home retry, repeated exact outage after cooldown enters existing two-stage helper. Includes approved461; canonical/live460 not modified. Preserve saved scenes, original audio and true policy/quota/unknown-send guards.

รุ่น Runtime `0.15.461` (staged only): native ChatGPT unavailable-conversation panel -> same-URL reload -> one tagged same-URL replacement tab -> read original if recovered. User explicitly authorized a final exception: if both checks still confirm that native error, start a fresh conversation ONLY for the pending Story analysis/image step. Keep original attempt in an immutable recovery archive; never replay saved scenes or treat an unknown backend result as proven failure. The already-allocated replacement tab is reused, not a third tab. background validates current desktop run/tab/document/checkpoints and a once-only claim; chatgpt.js consumes the capsule through the original receipt/analysis reader. Motion/helper/cover-specific owners retain existing recovery. Canonical/live460 remains untouched; docs/reports/chatgpt-unavailable-461.md tracks scope and tests.

รุ่น Runtime `0.15.460`: new ChatGPT -> Meta serial-media contract. Route docs/reports/meta-scene-sequence-460.md -> core/meta_scene_sequence.py -> Story scene-gate in local_bridge.py -> chatgpt.js::finishScene -> MetaVideoManager package/begin. Image N and video N must be durably saved before new image N+1. Script preparation, Flow gate and final/audio path retained; explicit old-job adoption does not resume. Name-binding exact wrapper fix included. Verified/packaged: full2701 followed by six fixture-only corrections and final82pass; unchanged runtime hashes and39-file parity. Not installed, no installer/provider generation. Monitor remains PAUSED. Prior entries are historical.

459 verification complete/package ready: focused52pass; full2685/2677pass/7skip/one doc-version-header failure corrected with final24pass. No runtime/test changes after full suite;838files stable,29JS syntax/39-file parity. Installed activation and five-queue completion remain pending; current report docs/reports/story-image-owner-20260928.md. Do not reapply the already-integrated staged patches.

รุ่น Runtime `0.15.459`: Story image generated/owner_changed after a pre-reload live veto → background.js::refreshStoryChatGPTResult; isolated cross-layer regression tests/story_image_refresh_owner_459.cjs. Restore exact preclaim receipt only before reload, retaining deferred budget audit; do not weaken owner equality or resend. core/local_bridge.py::extension_status prefers fresh required-version primary but retains all clients. Report docs/reports/story-image-owner-20260928.md records five authorized queue IDs and pending activation. No installer.

458 verification: final2671/2664pass/7skip/0failures/errors,835files unchanged;29JS syntax and39-file Extension source/folder/ZIP parity passed. Source paired458 is packaged, but loaded engine23600 remains457 until reopened and Chrome458 activation is not verified. Exact report below; do not mistake old beta.17/457 installer for this source update.

รุ่น Runtime `0.15.458`: แก้ Meta อ่านชื่อแชตที่มีคำว่า “หยุด” เป็น Stop ผิด → `browser_extension/src/platforms/meta-ai/video.js::inspectMetaDOM`; fixture `tests/meta_stop_title.cjs` / `test_meta_stop_title.py`. รับเฉพาะชื่อปุ่ม Stop จริงหรือข้อความตรงตัวใน composer; ไม่เปลี่ยน ownership/Send/download. รายงาน `docs/reports/meta-stop-title-20260928.md` แยกหลักฐานกู้งาน457จนFinal15ฉากจากผลทดสอบ458. นำซอร์สเข้าเมื่อ Chrome ปิด/คิวพักแล้วเท่านั้น ยังไม่รีโหลดหรือบิลด์ installer.

ตัวติดตั้งล่าสุด beta.17 / Extension457 (2026-09-28): `deliverables/customer-0.3.0-beta.17/` รวมตัวแก้ล่าสุดแล้ว ตรวจ payload2678ไฟล์/input295/Extension39 และเปิด engine+ทดสอบสื่อในสำเนาแยกผ่าน ยังไม่ติดตั้งหรือทดสอบ clean-PC/provider จริง; งานผู้ใช้ที่กำลังรันไม่ถูกปิด รายงาน `docs/reports/customer-installer-beta17.md`.

Shopee ลบงานถาวร (2026-09-28): `web_ui/product_continue.js/css` → `ui/product_jobs.py` → `core/product_job_deletion.py`. สองแท็บงานค้าง/ซ่อนไว้ ไม่มีถังขยะหรือกู้คืน; รายการถังขยะเก่าต้องกดยืนยันลบแยก ไม่ลบอัตโนมัติ. บันทึกคำขอ/ID ป้องกันงานฟื้นจาก backup/callback, ลบไฟล์เบื้องหลังและตรวจผลผ่าน `product_jobs_delete_status`; คำตอบหายไม่ส่งลบซ้ำเอง. ป้องกันงานกำลังทำ/Final/ไฟล์ใช้ร่วม. Extension457 เดิมใช้ได้ ไม่เปลี่ยน bytes หรือแพ็กเกจ; เปิดโปรแกรมใหม่เมื่อปลอดภัยเพื่อโหลด backend ที่ประกาศ `product_job_delete_version:1`. รายงาน `docs/reports/product-permanent-delete-20260928.md`.

รุ่น Runtime `0.15.457`: โปรแกรมและ Extension จับคู่รุ่นเดียวกันสำหรับแผนเปลี่ยนผู้สร้างรายฉาก งานนี้ไม่บิลด์ตัวติดตั้งและไม่เปิดใช้กับเบราว์เซอร์ของผู้ใช้เอง

Runtime457 source verified and Extension packaged: Shopee “ดูงาน” → remaining-scene Flow/Meta choice → `core/scene_video_plan.py` → `core/scene_video_worker.py` / Story worker → Extension bound settings/Generate/results. Review UI `web_ui/scene_video_plan.js` shares strict saved-job Flow editor. Preserve all completed clips/voices and legacy pure-provider contracts. Full2641 plus documented fixture/doc corrections and final251/251pass;39-file package parity. Use docs/plans/shopee-remaining-scene-provider-switch-20260927.md and docs/reports/scene-video-plan-457.md; no installed/provider E2E or installer claimed.

ปุ่มลบงานค้างทั้งหมด (follow-up 2026-09-27): ต้องเห็นโดยไม่เปิดรายการและใช้pendingทั้งชุด ไม่ใช่5แถวที่แสดง; exactIDs+confirmed+scope all_pending → ui/product_jobs.py ตรวจครบ/บันทึกครั้งเดียว รวมกรณีมากกว่า200งาน ส่งซ้ำไม่เพิ่มงานใหม่ ไม่ลบhidden/ready. รายงาน docs/reports/product-clear-all-20260927.md; ชุดทดสอบใหม่อยู่ใน Product continue UIและjob managementเดิม ไม่เปลี่ยนExtension456.

Shopee รายการเตรียมสินค้ารก/ลบไม่ได้ (2026-09-27): route `web_ui/product_continue.js/css` → `ui/product_jobs.py` → guards เฉพาะจุดใน `ui/main_window.py`, `ui/creation_queue.py`. รวม prepared sources เข้างานค้าง/ซ่อน/ถังขยะ นับถูกต้อง พับเริ่มต้น แสดง5รายการและเพิ่มได้ ลบแบบกู้คืนโดยไม่ลบสื่อ; sourceต้องยังไม่ผูก Story/คิว และ managementไม่รอ prepare lock บน UI thread. รายงาน `docs/reports/product-preparations-sidebar-20260927.md`; ไม่เปลี่ยน Extension456 หรือ provider generation.

Codex skills (2026-09-27): ใช้สกิลส่วนตัว `smartflow-operator` สำหรับสถานะ, `smartflow-extension-tester` สำหรับกรณี ChatGPT/Meta/ปก/คิว, `smartflow-extension-installer` สำหรับติดตั้งจริง และ `smartflow-release-builder` สำหรับตรวจความพร้อม/บิลด์เมื่อผู้ใช้สั่ง อ่าน SKILL.md ใต้ C:/Users/keera/.codex/skills/ ตามงาน รายงาน docs/reports/smartflow-codex-skills-20260927.md. Helperสถานะไม่เรียก GETที่leaseคำสั่ง และไม่ถือข้อมูลขาดเป็นidle; static preflightไม่ใช่การบิลด์หรือยืนยันพร้อมแจก ไม่มีการเปลี่ยนรุ่นโปรแกรม/Extensionจากการเพิ่มสกิลนี้.

Product แนวบท UI (2026-09-27): แก้ dialog ล้น/ชิดซ้ายและช่องค้นหาไม่เข้า theme ใน web_ui/creative_controls.js/css; เก็บ14ตัวเลือกและสัญญาเดิมถึง Extension456 ไม่เปลี่ยน provider/prompt/snapshot. รายงาน docs/reports/product-creative-picker-ui-20260927.md และ tests/test_creative_picker_layout_20260927.py ตรวจ CSS จริงครบ25ไฟล์/หลายขนาด/คิวและStory ใช้ค่าเดิม. ห้ามจำกัดความกว้าง outer .modal อีก; จำกัดที่ .modal-card และให้รายการเลื่อนเพียงชั้นเดียว.

รุ่น Runtime `0.15.456` รวมเข้าโปรเจกต์หลัก: นำตัวแก้ ChatGPT image C1 ที่เตรียมไว้พร้อม desktop required456 มาใช้ โดยรักษา UI ช่องพิมพ์/ผู้พูดแบบย่อและ function-overlap ล่าสุด ไม่แตก Source_Update เก่าทับทั้งโครงการ. Route `docs/reports/main-pairing-456-20260927.md`, `browser_extension/chatgpt.js`, `background.js`, `core/local_bridge.py`, `tests/test_chatgpt_recovery_loop_456.py`, `tests/test_story_refresh_loop_background_456.py`. ผลทดสอบและสถานะเชื่อมต่อจริงอ้างรายงานนี้ ไม่ใช้ข้อความ not_activated ของรอบเตรียมชุดเก่าแทนสถานะใหม่.

กติกาผู้ใช้ล่าสุด 2026-09-27: อัปเกรดโปรแกรมต้องตรวจและอัปเดต Extension ไปกับชุดล่าสุด ห้ามกลับไปใช้ฐานเก่าเพราะตัวแก้ใหม่อยู่แยกโฟลเดอร์ ก่อนทำ/ส่งมอบต้องเทียบซอร์สหลัก รุ่นที่โปรแกรมต้องใช้ ชุดที่เตรียมไว้ และ heartbeat ของ Extension จริง รวมตัวแก้ที่อนุมัติไว้โดยรักษา UI ใหม่ ไม่แก้แค่เลขรุ่น ไม่ลดรุ่น และไม่รีโหลด/รีสตาร์ตงานเอง ล่าสุดตรวจพบ Chrome456 แต่โปรแกรมหลักยัง required455; ต้องแก้ความไม่ตรงกันนี้ก่อนอ้างว่าอัปเกรดชุดหลักพร้อมใช้งาน.

Main UI follow-up 2026-09-27: ใช้ช่องพิมพ์แนวทางเดิมของ Shorts/หลายเรื่อง/Drama เป็นหลัก และย่อการ์ดผู้พูดเป็น select 4 ค่าเดิม; ตัวช่วยโทน/โครงเรื่อง/เปิดเรื่อง/ตอนจบ/CTA พับรวมกัน ตัวอย่างเพิ่มท้ายข้อความเมื่อกดเอง ไม่ทับร่างหรือส่ง AI. Route `web_ui/storytelling.js/css`, `web_ui/index.html`, `tests/test_storytelling_compact_ui.py`, `tests/test_storytelling_free_text_contract_20260927.py`; ผลตรวจ `docs/reports/storytelling-compact-20260927.md`. สัญญารับส่ง/Extension 455 ไม่เปลี่ยน ไม่รวม/เปิดใช้ staged456 ไม่เปลี่ยนคิวหรืองานเก่า ไม่สร้างตัวติดตั้งหรือรีโหลดผู้ใช้เอง.

Main-project follow-up after 455: แก้ 9 จุดฟังก์ชันทับซ้อน ดู `docs/reports/function-overlap-fixes-20260927.md` สำหรับผลทดสอบล่าสุด ไม่ใช้ full-suite 455 ด้านล่างแทนรอบนี้ Route: `web_ui/media_audio.js`, `storytelling.js`, `queue_choice.js`, `ai_cover.js`, `green_screen.js`, `app.js`, `ui/creation_queue.py`, `main_window.py`; เสียง `core/generated_music.py`, `story_performance.py`, `long_video_render.py`. คิวส่ง editor allowlist ไม่ส่ง execution config; งาน Long ใหม่มี desktop-only source-audio version 1 งานเก่าคง 0. Extension 455 ไม่เปลี่ยนและไม่ต้องแพ็กใหม่ ไม่รีโหลด/รีสตาร์ต/สร้างงานหรือบิลด์ตัวติดตั้งเอง.

รุ่น Runtime `0.15.455` ผ่านออฟไลน์และแพ็กแล้ว ยังไม่เปิดใช้จริง: full2531/2525passed/6skipped/0failures/errors;39ไฟล์ตรงกันทั้ง source/folder/ZIP. แยกบทเสียง/การกระทำด้วย Meta prompt v5 เฉพาะงานใหม่; คง legacy hashes. ตรวจข้อกำกับคำตอบเดียวก่อนส่งใหม่ และเลือกผลที่ใช้ได้หนึ่งชิ้นของคำขอเดิมโดยไม่โหวตหรือหยุด generation. Route `core/meta_prompt.py`, `meta_video.py`, `meta_redesign.py`, `media_audio.py`, `browser_extension/chatgpt.js`, `src/platforms/meta-ai/video.js`; รายงาน `docs/reports/prompt-roles-single-result-455.md`. ไม่แก้งานหรือ Final เดิม ไม่บิลด์ตัวติดตั้ง/รีโหลด Chrome/สร้างด้วย AI จริง.

รุ่น Runtime `0.15.454`: Meta ทำต่อ/แท็บหาย → `core/meta_video.py`, `ui/main_window.py`, `browser_extension/src/platforms/meta-ai/video.js`. เปิด clean Home ด้วยคำขอใหม่เฉพาะขั้นตอนที่ค้าง ไม่ใช้ URL เก่า; เก็บสื่อสำเร็จและประวัติเดิม ป้องกันคำขอซ้ำและรับไฟล์ดาวน์โหลดก่อนพิจารณาสร้างใหม่ รายงาน docs/reports/meta-fresh-context-454.md; ยังไม่รีโหลดหรือสร้างงานจริง/ตัวติดตั้ง.

รุ่น Runtime `0.15.453`: Meta Send active-scale geometry → `browser_extension/src/platforms/meta-ai/video.js::inspectMetaDOM/sendGuarded`; bounded diagnostic persistence → `core/meta_video.py::event`. Original pointer hit + exact node identity replace floating-point center equality; all Stop/owner/source/draft fences remain. Report docs/reports/meta-send-geometry-453.md. Source validation is separate from installed/provider generation; no live reload or installer.

รุ่น Runtime `0.15.452` source verified, Extension packaged, not activated: creative catalogs → `core/creative_brief.py`, compact `web_ui/creative_controls.js`; generated scene music → `core/generated_music.py` and opt-in Long source-audio preservation; draggable logo → `core/logo_layout.py`, `web_ui/logo_editor.js`, shared render geometry. Queue/Product/series use saved options, not current controls. Final2484/2478passed/6skipped/0failures/errors;37JSsyntax and39-file package parity passed. See docs/reports/creative-controls-452-20260927.md; no installer, paid generation or live reload.

รุ่น Runtime `0.15.451` (paired source, source verified; Extension packaged, not activated): pre-installer targeted fixes for shared deletion/start claims, frozen Product UI/runtime options, Meta Send fencing, durable cover retry ownership and versioned headlines, narrator-only Drama, UTF-8 updater diagnostics and origin-restricted TTS redirects. Preserve installed active work; no reload, provider Send or installer. See docs/reports/preinstaller-fixes-451-20260927.md.

รุ่น Runtime `0.15.450` (paired desktop/Extension): `chatgpt.js::collectCoverImage` chooses one ready owned cover even if two alternatives exist; `runAICover` reports typed failure only after three actual failed reads. `core/ai_cover.py::_download_replacement` creates one atomic child with one-image/no-choice instruction; `ui/ai_cover.py::_linked_cover_request` follows only validated same-job parent/child chains for wait/status/cancel. Raw Extension receipt remains request-exact. Preserve Final, saved media, user drafts, busy/unknown Send and unknown save ACK. No installed activation or installer. Route docs/reports/cover-selection-450.md.

Browser startup20260926 (desktop-only,449 Extension unchanged): `ui/main_window.py::_start_browser_connection` + `desktop/hybrid.py::ensure_browser_connection` connect installed-profile Chrome on new/adopted/refocused canonical EXE entry without generation/resume commands. Preserve test-root/update/close guards, missing/ambiguous-profile refusal, single-flight and60s observation bound. `system.browser_connection` must not show stale ready text offline. Full2377/2371passed/6skipped; live activation pending user restart after current work finishes. Route docs/reports/browser-startup-20260926.md; no installer.

Product queue button fix20260926 (UI-only, Extension449 unchanged): `web_ui/creation_queue.js` generated extra-options details must retain id creation-product-extra-settings or openEditor throws before showModal. Native regression tests/creation_product_editor_ui_449.cjs is wired into unittest discovery. See docs/reports/queue-product-editor-20260926.md; no installer or protocol changes.

รุ่น Runtime `0.15.449`: แก้ด่านเตรียมปกก่อนส่งที่อ่านไฟล์แนบจากทั้งหน้าเมื่อช่องแชตยังไม่พร้อม พร้อมตรวจเครื่องมือซ้ำหลัง ACK และเก็บเหตุย่อยแบบไม่บันทึกพรอมต์. Route docs/reports/cover-preflight-449.md → chatgpt.js::coverPreparationSnapshot/prepareCoverImageTool → core/ai_cover.py. Source tests and activation are separate; do not claim actual cover success before saved media. No installer.

รุ่น Runtime `0.15.448` source candidate: กู้ขั้นเตรียมเครื่องมือสร้างปกก่อนส่ง พร้อมสถานะ/ปุ่มตรงกับหลักฐาน ไม่แตะ Final หรือส่งซ้ำเมื่อกำลังสร้าง; no live activation or installer. ดู docs/reports/cover-preparation-448.md.

Current447 contract: no automatic Stop while collecting/preparing images, including after checkpoint. A decoded image with active generation remains waiting. Retire-only does not cancel provider work. Real Stop cannot become Send. Fresh ChatGPT image/cover/repair/reminder requests select Create image and verify the exact removable composer chip; text requests clear the image-only mode. Read docs/reports/chatgpt-image-wait-tool-447.md. User job4A9904 completed on446 with15saved images and a final video;447 provider E2E is pending.

Current paired source 0.15.446: observed reverse-column ChatGPT newest end is scrollTop0, not the normal scroll bottom. A stable refreshed accepted original with a loaded reference and no assistant response can issue ONE short same-chat reminder, with independent nonce/dispatch latch and accepted message ownership. Do not send the whole prompt/upload again, reset the original receipt, or open a fresh tab in this branch. Unknown child Send is passive-only across restart; actual generation/late original image wins before press. Read docs/reports/story-same-chat-reminder-446.md and Blueprint12.4. Active installed445 remains untouched; fixture tests are not provider E2E; no installer.

รุ่น Runtime `0.15.445` source candidate: แก้ตัวเก็บผลภาพ ChatGPT ที่เงียบหลังรีเฟรชเฉพาะคำขอเดิม โดยกำหนดเวลารอรายงานสถานะ และปลุกตัวอ่านผลกลับมาเฉพาะเมื่อโปรแกรมยังเป็นเจ้าของงาน/รอบนั้นและ Chrome ยังอยู่เอกสารเดิม ไม่ส่งพรอมต์ภาพซ้ำจากความเงียบ ดู `docs/reports/story-refresh-collector-445.md` → `browser_extension/chatgpt.js`, `background.js`, `core/local_bridge.py`. Chrome 444 ยังโหลดจาก deliverable รุ่นเก่า; อย่าทับไฟล์นั้นหรือรีโหลดระหว่างงาน.

รุ่น Runtime `0.15.444` candidate: แก้การกู้วิดีโอ Meta เป็นสองขั้นที่แยกบันทึกจริง—สร้างภาพใหม่จาก AI ภาพเดิม, ตรวจและเซฟภาพ, จากนั้นแนบภาพใหม่ขอพรอมต์วิดีโอและเซฟพรอมต์ ก่อนเปิด `https://www.meta.ai/` เพื่อเริ่มเฉพาะฉากที่ค้าง. หากขั้นพรอมต์เสีย กดทำงานต่อจะใช้ภาพใหม่ที่บันทึกแล้ว ไม่สร้างภาพซ้ำ; ถ้าไฟล์ภาพเสียจริงจึงเริ่มขั้นภาพใหม่. เริ่มที่ `docs/reports/meta-two-stage-444.md`, `core/meta_redesign.py`, `core/meta_video.py`, `browser_extension/background.js`, `browser_extension/chatgpt.js`, `tests/test_meta_continue_fresh.py`. ไม่บิลด์ตัวติดตั้งและยังไม่ทดสอบส่งงานกับ AI จริง; เก็บงานและคลิปเดิม.

รุ่น Runtime `0.15.443` paired Extension artifact packaged, not activated: ผู้ใช้กด “ทำต่อ” ใน Story Meta ที่ค้างระหว่างแก้ภาพแล้ว โปรแกรมเปลี่ยนเฉพาะฉากนั้นเป็นเจ้าของคำขอใหม่ ขอภาพและพรอมต์ใหม่จาก AI ภาพเดิมก่อน แล้วเปิด Meta หน้าเริ่มต้น `https://www.meta.ai/` เพื่อสร้างวิดีโอใหม่ ไม่กลับ `/prompt/...` เก่า. Helper JSON ที่ผิดรูปแบบแก้ข้อความได้ครั้งเดียว ไม่ถาม GPT วน. เริ่มที่ `docs/reports/meta-continue-fresh-443.md`, `core/meta_video.py`, `ui/main_window.py`, `browser_extension/chatgpt.js`, `src/platforms/meta-ai/video.js`, `tests/test_meta_continue_fresh.py`. Extension 443 โฟลเดอร์และ ZIP อยู่ใน `deliverables/SmartFlow_AI_Extension_0.15.443[.zip]`; Chrome path เดิมที่ต้องรักษา ID/ข้อมูลคือ `browser_extension`. Beta.16/442 ยังเป็นไฟล์ติดตั้งเดิม; 443 ยังไม่โหลดใน Chrome/โปรแกรมหรือทดสอบ provider จริง และยังไม่ได้บิลด์ตัวติดตั้งโปรแกรม.

รุ่น Runtime `0.15.442` paired candidate: exact completed Thai Meta technical apology + stable no-video proof enters the original-image-provider redesign transaction, then a new Meta context. Assistant toolbar text is excluded; Long helper image is 16:9. Start with `docs/reports/meta-technical-redesign-442.md`, `core/meta_video.py`, `core/meta_redesign.py`, `browser_extension/src/platforms/meta-ai/video.js`, `background.js`, `chatgpt.js`, and `tests/test_meta_technical_redesign_442.py`. No running job/Chrome reload or provider generation in source validation.

รุ่น Runtime `0.15.441` paired candidate: route failure before Meta answer-reading now has a durable saved-route recheck and single clean-scene successor; ready empty Home must be proven in a new Chrome document. Long Video recovery list and Meta-specific failure logs are in this same contract. Start with `docs/reports/meta-route-long-recovery-441.md`, `core/meta_route_recovery.py`, `core/meta_error_report.py`, `tests/test_meta_route_recovery.py`. Source fixtures are not installed E2E; no EXE installer/reload/job dispatch. The 440 section below describes the previous release.

รุ่น Runtime `0.15.440` source candidate: โหมดคลิปยาว 16:9 เพิ่ม Meta AI ในเส้นทางเลือกผู้สร้าง → เก็บคลิปจริงแยกตามฉาก → ตรวจภาพ/MP4 แนวนอน → รวมทีละ 10 ฉากใน `long_meta_chapters` โดยไม่ปะปนคลิป Google Flow. เส้นทาง Meta แนวตั้งของงานเดิมคงเดิม. ทดสอบ Meta ด้วยภาพสังเคราะห์เพียงหนึ่งคำขอได้ MP4 จริง 1280×720 ยาว 10 วินาที แต่ยังไม่ได้ยืนยัน Extension ที่ติดตั้งและงานคลิปยาว 18–50 ฉาก end-to-end. Route `core/long_video.py`, `core/meta_video.py`, `core/long_video_render.py`, `ui/main_window.py`, `web_ui/app.js`, `browser_extension/src/platforms/meta-ai/video.js`; ดู `docs/reports/long-meta-440.md`. ยังไม่สร้างตัวติดตั้ง.

รุ่น Runtime `0.15.439` source candidate: วงรอบกู้คำตอบผิดพลาดที่ยืนยันแล้วด้วย owner/receipt เดิม, cooldown, ตรวจผลหลังรีเฟรชและ successor เดียว; โปรแกรมรักษา progress และไม่รับ error จาก run เก่า ข้อความ Unknown Send/สิทธิ์/เครดิต/การปฏิเสธจริงไม่ถูกกดซ้ำแบบเดาสุ่ม ดู `docs/reports/automation-recovery-loop-439.md` ยังไม่ได้ทดสอบ provider จริงหรือสร้างตัวติดตั้ง

รุ่น Runtime `0.15.438` source candidate: fix the reproduced old-document reload race. Route `docs/reports/story-refresh-document-438.md` and `background.js::refreshStoryChatGPTResult/waitForAIRefreshReady/startAIWebJob`. A ready old document and its already_running reply cannot prove the refreshed document has a collector. Keep exact job/scene receipts and saved results; installed437 remains untouched until safe activation. No installer.

รุ่น Runtime `0.15.437` source candidate: user-authorized refresh/check/redo for missing ChatGPT Story image results; preserve busy/results/drafts and saved scenes. Route `docs/reports/story-refresh-check-redo-437.md` → `chatgpt.js` stable request/receipt monitor → `background.js` owned reload/single successor → desktop package, bounded diagnostics and checkpoint integrity. Installed436/job/Chrome are not restarted by this change; no installer.

รุ่น Runtime `0.15.436` อยู่ระหว่างตรวจ: รับภาพที่ ChatGPT ตอบหลังบล็อกคิด โดยยืนยัน gallery/เจ้าของคำขอแทนการบังคับตำแหน่งเครื่องหมายเริ่มคำตอบ; ติดตามผลรีเฟรชและ Log แบบย่อ ดู `docs/reports/story-image-gallery-436.md`. ภาพฉาก 2 ที่มีแล้วต้องถูกอ่านก่อนเริ่มงานใหม่

รุ่น Runtime `0.15.435`: actual saved-reference attachment before new/unsent Story generation (including legacy prepared/repaired requests), current ChatGPT semantic user/assistant/gallery DOM plus legacy readers, and completed missing-reference Resume classification. Read `docs/reports/saved-reference-dom-435.md`; do not mistake passing fixtures for installed generation or reset an unknown Send.

รุ่น Runtime `0.15.434`: fixes the verified short Thai Send label mismatch between content preflight and trusted click, reads latest same-job previous-scene checkpoints, and isolates the standalone-reference repair branch. See `docs/reports/chatgpt-send-reference-434.md` for tested scope and activation; older versions below are history, not instructions to revert.

รุ่น Runtime `0.15.433` (candidate, not activated): completed Story image missing-reference answer may start one new image request with the exact saved preceding-scene PNG attached. If no prior image exists or that attempt still reports a missing reference, request one standalone text-only scene brief. Unknown Sends and explicit refusal remain review. Pair desktop and Extension before testing; intermediate 432 is superseded. See `docs/reports/story-previous-reference-433.md`.

> พิมพ์เขียวรวมของซอร์สคู่กัน 0.15.431: [โปรแกรม Windows + Chrome Extension](docs/SMARTFLOW_SYSTEM_BLUEPRINT_0.15.431.md) แยกสถานะ candidate ออกจากรุ่นที่ติดตั้งจริง และรวม Job/Queue, ทุกโหมด, Browser Bridge, recovery, release gate ในเอกสารเดียว

รุ่น Runtime `0.15.431` (not activated): long-video v2 exact pending outline/chapter request survives before-Send interruption and Continue reads only the owned reply; Story image audit accepts scene 16–50 in both validation layers, and queued long edits keep the proper scene settings. Route `core/story_manager.py`, `core/ai_web_resume.py`, `core/local_bridge.py`, `core/creation_queue.py`, `browser_extension/chatgpt.js`, `web_ui/creation_queue.js`; see `docs/LONG_VIDEO_IMPLEMENTATION_STATUS.md`. Do not treat this as installed or provider-proven. No EXE installer was built.

Drama controls source follow-up (2026-09-24, not activated): route `web_ui/storytelling.js`, `web_ui/media_audio.js`, `core/story_performance.py`, `core/drama_series.py`, `core/scene_voice.py`, `core/story_finisher.py` and Blueprint §5B. Speaking Drama can choose native clip audio or post-generation per-character SmartSub dubbing; visual-only is silent and can use local motion. First-EP narrated cast may be generated and frozen; primary voice is frozen with the series. See `docs/reports/drama-controls-20260924.md`. Old jobs, current user app/Chrome and provider credits untouched; no installer/live E2E.

Source follow-up on paired 0.15.430 (not activated): repeated native Flow speech is checked using the existing subtitle transcript and actual scene durations before Final is published. Exact-scene retry uses an archived old segment/clip, bounded fresh Flow attempt ID, new project ownership and a single-take delivery note; other scenes remain checkpoints. Desktop requires the changed Extension heartbeat capability before sending this new retry, so an old loaded 430 must be reloaded safely. Route `core/flow_speech_quality.py`, `core/story_finisher.py`, `core/scene_pipeline.py`, `core/story_manager.py`, `ui/main_window.py`, `browser_extension/background.js`; read `docs/reports/flow-speech-repeat-430.md`. Subtitles-off jobs are not audited by this source change. No installer or live provider E2E.

รุ่น Runtime `0.15.430` candidate: accepted ChatGPT analysis on temporary `WEB:` URL survives canonical hydration AND the exact injected inline ` ```json ` rendering as `json`; only the saved same-run conversation may be read on Continue without Send. Route `browser_extension/chatgpt.js::revealChatGPTAnswer/chatGPTKnownRenderedRequestMatches`, `core/ai_web_resume.py`, `tests/chatgpt_route_393.cjs`, `tests/test_ai_web_resume_345.py`; report `docs/reports/chatgpt-canonical-owner-430.md`. Supersedes partial429 ZIP; pair desktop/Extension before activation.

รุ่น Runtime `0.15.428` candidate: quoted product-name JSON transport. Route `core/analysis_json_transport.py`, `StoryManager._write_request`, `ProductManager._write_ai_request`, and `browser_extension/chatgpt.js` analysis extraction/format repair. Report `docs/reports/analysis-json-transport-428.md`. Preserve submitted request bytes and completed media. No installer/live activation.

รุ่น Runtime `0.15.427`: final audit delivery adds authenticated native Flow reference downloads and Origin-less Chrome GET support. Use 427, not intermediate 426. Report `docs/reports/audit-fixes-426.md`.

รุ่น Runtime `0.15.426`: audit fixes route to `core/product_prepare_options.py`, `product_story.py`, `extension_identity.py`, `meta_redesign.py`, `meta_video.py`, `local_bridge.py`, `browser_extension/src/platforms/meta-ai/video.js`, `background.js::ensureMetaRedesign`, `chatgpt.js::runMetaRedesignHelper`, and `web_ui/generation_notice.js`. Report `docs/reports/audit-fixes-426.md`; no installer/live activation.

รุ่น Runtime `0.15.425` (source candidate): Product Story wardrobe `auto/product/saved` freezes person/product/outfit reference roles; opted-in saved outfits send four images through `browser_extension/chatgpt.js`, with wardrobe-aware scene/Meta prompts. Route `core/product_story.py::ProductCast/outfit_instruction`, `web_ui/product_story.js`, `web_ui/creation_queue.js`, `core/meta_video.py`, and the Extension attachment guard. Old jobs and Meta receipts remain unchanged; cross-provider image redesign and installed provider E2E are not claimed. See `docs/reports/product-outfit-425.md`.

รุ่น Runtime `0.15.424` (candidate): Meta scene1–2 saved actual videos under installed423; scene3 completed no-video `different take` offer was missed and retried.424 accepts provider-authored revised-take proposals with `Want me to try` or `Let me know...` under the same one-shot ownership gate. Job paused with two clips and latest scene3 conversation. Route `core/meta_video.py::meta_safe_offer`, `browser_extension/src/platforms/meta-ai/video.js::metaSafeOffer`; report `docs/reports/meta-different-take-424.md`.

รุ่น Runtime `0.15.423` (candidate): installed422 saved actual Meta scene1 after the Thai safer-offer follow-up. Scene2's English `I wasn't able to create... I can help with a safer version... Want me to make that version?` was completed/no-video but unrecognized.423 classifies this exact offer on the existing one-shot same-chat path. Job paused, scene1 stored, scene2 receipt retained. Route `core/meta_video.py::meta_reply_failure/meta_safe_offer`, `browser_extension/src/platforms/meta-ai/video.js`, `tests/test_meta_safe_offer_422.py`; report `docs/reports/meta-safe-followup-423.md`.

รุ่น Runtime `0.15.422` (candidate, not activated): Meta's completed single safer-version offer → durable one-time same-chat follow-up → require real playable video. New Meta prompt v4 permits compliant visual revision without a confirmation question; old v1–v3 contexts remain exact. Route `core/meta_video.py::meta_safe_offer/_choice`, `browser_extension/src/platforms/meta-ai/video.js::metaSafeOffer/stepChoice`, `core/meta_prompt.py`; report `docs/reports/meta-safe-followup-422.md`. Beta.14 installer still contains421.

Latest customer installer: `0.3.0-beta.14` paired Extension `0.15.421` at `deliverables/customer-0.3.0-beta.14`. Read `docs/reports/customer-installer-beta14.md`. Isolated frozen engine/media and payload audit passed; broad source suite still has known failures and clean-PC/native-GUI/provider E2E are pending. Unsigned/unpublished; user runtime untouched.

รุ่น Runtime `0.15.421` (candidate, not installed): Product-first compact AI request, richer Shopee detail capture, Meta v3 compact video prompt. See `docs/reports/product-prompt-capture-421-20260923.md`; source desktop and Extension must match before activation.

Current 0.15.421 Product prompt/capture candidate: route to `core/product_story.py::compact_product_analysis_prompt`, `core/story_manager.py::_write_request`, `browser_extension/content.js::pageProduct`, `browser_extension/background.js::capture_shopee_product` and `core/meta_video.py::package`. Product-only concise prompt, passive metadata wait, new Meta v3; old jobs/receipts preserved. Report `docs/reports/product-prompt-capture-421-20260923.md`; not installed.

รุ่น Runtime `0.15.420` (candidate, not released): Shopee capture uses durable Product-source request IDs, exact Extension capture-command ownership and server proof of a real readable image file. Failed/unfinished source preparation can resume from the single Product continuation panel using its frozen settings; handoff to Story is idempotent. Read `docs/reports/product-story-capture-resume-420-20260923.md`. Paired Extension 0.15.420 candidate folder/ZIP is in `deliverables`, but the stable Chrome path remains `browser_extension`; no Chrome reload or provider test was done for this package. Source desktop requires 0.15.420, no installer built, and beta.13 remains 0.15.418.

Product image path source fix (not activated): `docs/reports/product-source-path-20260923.md` → `core/product_manager.py::_download_product_images/_load_manifest_file`, `core/product_source_images.py::canonical_source_image_paths`, `core/product_story.py::ProductCast.snapshot`. Saved old paths with the exact Job prefix are accepted only when the image exists inside that Job; new imports use Job-relative paths. User media/Job, running app and Extension are untouched.

Post-419 source staging (not activated/released): `docs/reports/story-flow-product-ux-post419-20260923.md`. Routes: `browser_extension/background.js::refreshStoryChatGPTResult/startAIWebJob`, `chatgpt.js::START_CHATGPT_JOB`, `flow_settings.js::read`, `web_ui/product_continue.js`, `web_ui/flow_settings.js`, `web_ui/app.js`. Exact active Story run attaches; different active run waits, never replays; confirmed failed image uses existing fresh transaction. The saved Lower Priority Flow model is not equivalent to ordinary Lite: if Google removes it, keep the job/settings intact and do not Generate with another model. One Product continuation list and compact preselection Flow controls. Do not treat installed 419 as this staged source or reload a live job.

รุ่น Runtime `0.15.419`: review storage key-order fix + Product Shopee pre-AI handoff visibility and delayed-ACK race fix. Read `docs/reports/review-storage-product-capture-419.md`; routes background FLOW_ALTERNATIVE_EVENT, chatgpt.runFlowAlternativeHelper, core.product_story.prepare_link, web_ui/product_story.js. Native storage reorder is reproducible; remote beta.13 capture root cause not yet observed. Source/full-suite validated; no live reload/job restart/installer. beta.13 remains418.

Latest customer installer: `0.3.0-beta.13` paired Extension`0.15.418`, in `deliverables/customer-0.3.0-beta.13`. Read `docs/reports/customer-installer-beta13.md` for hashes and exact verification.2670payload hashes/245source inputs/39Extension files verified; isolated packaged engine/tools/Thai media passed and owned6940 exited. Unsigned testing beta, no native GUI/other-PC/provider E2E this turn. User55328/418 activeStory untouched; no runtime changes or server publish. Prior no-installer statements below describe earlier turns.

รุ่น Runtime `0.15.418` — unconfirmed motion Send refresh-first; installed verification pending.

Runtime418: docs/reports/unconfirmed-motion-refresh-417.md → chatgpt.submitPrompt / refreshUnconfirmedChatGPTMotion and background.refreshCompletedChatGPTResponse. Full trusted60s unconfirmed motion Send may reload/read the same saved requested checkpoint once; late exact acceptance continues. Scalar attachment hashing avoids React DOM cycles. No unknown resend/new-tab/reset. Full/packaging results in CURRENT_RELEASE; installed415 not restarted. No installer.

Desktop/admin update workflow 2026-09-22: docs/reports/admin-update-workflow-20260922.md → tools/sign_customer_release.py creates a signed two-asset admin wrapper (release.json + unchanged patch.zip) for explicit compatible --from-version; web_ui/updates.js polls metadata every15min, notifies only newer versions while idle. Host duration/search/compact/two-file admin staged, not deployed; user will restart visible BAT. Full2143=2142pass1skip; Extension415 unchanged; no installer/publication. Do not confuse admin wrapper with customer inner patch or silently reload Chrome.

รุ่น Runtime `0.15.415`: docs/reports/refresh-failure-415.md -> chatgpt.js image monitor + background.js refreshStoryChatGPTResult/waitForAIRefreshReady. Preserve exact completed technical failure before refresh; failed60s readiness may hand only that failed attempt to existing fresh-image transaction. Never let active/media/unknown ownership become replay authority. Tests refresh_failure_415.cjs and refresh_failure_dom_415.cjs. Main source only, NO installer; beta.12 remains413. Installed414 is not activated415.

รุ่น Runtime `0.15.414`: docs/reports/motion-transport-414.md -> chatgpt.js::chatGPTMotionRequestText and runSceneRepairHelper. Actual writer adds the single-answer suffix; canonical readers must remove only that suffix before exact request comparison. Covers initial motion Send, requested Resume, stable/pending reply and plain helper recovery; no blanket retry/new-tab on ownership errors. Native Chromium round-trip tests in motion_transport_414.cjs. Main source only, NO installer this turn; beta.12 remains413.

รุ่น Runtime `0.15.413` / customer `0.3.0-beta.12`: refresh / retry original request / fresh failed image page. Main source final2137tests=2136pass/1skip; paired Setup built in deliverables/customer-0.3.0-beta.12. Packaged engine/tools/Thai media smoke passed and own process exited; native GUI/independent-PC/provider E2E pending. Read docs/reports/browser-recovery-413.md first. Earlier "latest" version labels below are historical.

Current source412 (not in beta.11 installer): docs/reports/single-answer-meta-412.md → browser_extension/single_answer.js, ChatGPT/Flow writer and exact wire Send checks, src/platforms/meta-ai/video.js, core/meta_video.py. All providers request one final result; native Meta A/B/unavailable proof enters fresh retry, explicit failed-scene Continue never inherits the old URL. Keep canonical prompt identity, unknown-Send/active/policy guards and completed scenes. Installed validation pending; do not reload a running job.

Latest installer beta.11/Extension411: docs/reports/flow-defaults-first-login-beta11.md → web_ui/membership.js::render and flow_settings.js::ensureSettings. Fixes first-login Shopee “กำลังโหลดค่าตั้ง Flow” before creation; only read-default retry, no generation retry/auth bypass. Full2130/405.819s=2129pass1skip0fail; installer in deliverables/customer-0.3.0-beta.11. Existing411 Extension unchanged. Remote-PC retest pending. Beta.10 cleanup note below remains historical/open.

Latest customer installer:0.3.0-beta.10/Extension411 in deliverables/customer-0.3.0-beta.10. Normal Setup ready for another-PC testing; unsigned/no online publish. Host install/native/media passed, independent machine/provider E2E pending. IMPORTANT remaining cleanup: hidden isolated smoke GUI24584/engine36336,port19065,build/install-smoke-beta10; graceful close unavailable/termination denied. Do not touch active user43336/8765. Report docs/reports/customer-installer-beta10.md.

รุ่น Runtime `0.15.411`: docs/reports/failed-scene-restart-411.md -> background.completedFlowProposalReview, core.flow_review completed_proposal_error/restartable_proposal_review, flow_replacement.begin, ui.story_flow_resume. Explicit failed pre-image JSON review starts one new scene/helper/project;410 repeated malformed-answer correction remains. No master-plan reanalysis or completed-media deletion, no unknown Send reset. Paired411 required; installed E2E pending.

รุ่น Runtime `0.15.410`: route docs/reports/flow-format-recovery-410.md -> chatgpt.runFlowAlternativeHelper.parseReply, background.storyRepairMessage start_alternative, flow.recoverFlowPolicy progress. Completed owned malformed proposal/motion JSON requests another text-only correction until valid, with durable intent and capped cancellable backoff; no unknown-send replay or refusal coercion. New helpers opt in; old paused records/receipts/media are not rewritten. Paired desktop410 required; installed E2E pending, no installer or live resume.

Desktop english-voice-pass-through-1: route docs/reports/english-voice-pass-through-20260922.md -> core/thai_tts.py. Unmapped English narration is passed to the selected voice engine, not a pronunciation error. Shared scene/whole-story/Product/Drama/subtitle paths use the same normalizer; known readings and malformed-tag checks remain. Extension409 unchanged, no new installer/package or live Resume.

รุ่น Runtime `0.15.409`: ChatGPT refresh handoff/AI progress routing and ordinary stopped-job visibility. Route docs/reports/refresh-handoff-409.md -> background.waitForTabComplete/waitForAIRefreshReady/reportWebActionProgress; ui/story_recovery.py, ui/creation_queue.py, MainWindow._desktop_story_row, web_ui.renderStories. No cancellation reset or provider Send changes. Installed408 scenes9/10 observed complete;409 E2E pending, no installer.

รุ่น Runtime `0.15.408`: exact saved-ready Home recovery goes directly from desktop to NEW Flow, bypassing the AI driver until this scene completes. Route docs/reports/flow-direct-resume-408.md -> ui/story_flow_resume.py, core/flow_review.ready_home_replacement, bridge flow-package, background.openFlowReviewRebuild. Desktop append-only pre-project proof plus media hash may restore lost browser cache; no fresh/submitted/unknown work reset. Installed407 failure confirmed,408 installed E2E pending. No installer.

รุ่น Runtime `0.15.407`: Flow Home promotional-video false-positive fix and reuse of already-saved NEW image/motion after that precise review. Route docs/reports/flow-home-recovery-407.md -> flow.recoverFlowPolicy and background.openFlowReviewRebuild/manualFlowReviewCheckpoint. Exact fresh-start Home owner only; project results, active generation, drafts, approvals, unknown sends and receipts remain protected. Installed desktop/Extension406 now confirmed (supersedes older404 observations);407 provider E2E pending, no installer or live generation.

รุ่น Runtime `0.15.406`: passive automation liveness. Route docs/reports/automation-liveness-406.md -> flow.monitorGeneration, background progress outbox/download command, chatgpt.createStoryImageWaitMonitor. Preserve405 new-controller bootstrap and unknown-Send/owner guards. Source fault tests pass; final validation recorded in report. Last observed Chrome/desktop404 are untouched; installed406 E2E pending. No installer or live provider generation.

รุ่น Runtime `0.15.404`: manual failed Story proposal starts a separate AI→new image/motion→new Flow project, NOT403's old-project reopen. Route docs/reports/flow-fresh-start-404.md → background.openFlowReviewRebuild and Flow's exact-owned Home controller monitor. Old media/receipts remain; no active/unknown-send reset. Desktop and Extension paired404; verification in report. User runs live tests themselves; do not dispatch/reload. No installer.

รุ่น Runtime `0.15.403`: Story explicit Flow-review resume from desktop's exact checkpoint project, not Home/cache-only. Route docs/reports/flow-review-project-403.md → background.js manualFlowReviewCheckpoint/manualFlowReviewProofMatches/storyRepairMessage/open_flow/resume_flow_workspace and flow.js autoPrepare/ownedStoryPolicyTerminal. Completed proposal proof is distinct from no-charge generation failure; old media, active/unknown sends and other tabs preserved.26 actual-source cases; final/installed verification pending. No installer. Older labels below are historical.

รุ่น Runtime `0.15.402`: new Story Flow creative recovery contract; paired source only, no installer. Route docs/reports/flow-creative-recovery-402.md → flow_replacement.py / scene_context_revision.py / runFlowAlternativeHelper. New failed-scene event/dialogue allowed; completed rejected proposals ask for different benign ideas, not approval coercion. Durable creative rounds archive completed images, reject late results, preserve unknown sends and existing clips. Validated new speech reaches candidate.prompt for fresh Flow project/reopen as well as desktop package/render. Legacy/Product contracts unchanged. Full2090/356.182s:2089passed/1skip,208runtime hashes unchanged,38-file package parity; installed402 provider E2E pending. Final bridge unavailable, no launch/reload. Older entries below are history.

รุ่น Runtime `0.15.401`: completed incomplete name-binding text recovery; source-only, no installer. Route docs/reports/story-binding-recovery-401.md → chatgpt.js repairStoryNameBindings/collectStoryNameBindings and tests/story_name_binding_recovery_harness.js. Keep validated pairs, ask only unresolved pairs max2 extra text requests each; durable job/context budget, exact completed reply/draft/attachment guards, no unknown-send replay. Existing local ID, user anchors, desktop audit and media preserved. Source/desktop versions paired; installed provider E2E pending, bridge unavailable, no reload.400 Flow proposal fixes remain. Older current labels below describe historical releases.

รุ่น Runtime `0.15.399` / customer `0.3.0-beta.9`: audit and installer built. Route docs/reports/program-extension-audit-399/README.md → chatgpt.js storyImageWaitObservation, flow.js refreshCompletedFlowResult, ui/creation_queue.py, ui/update_guard.py and docs/CUSTOMER_INSTALLER.md. Current-frame busy/streaming and fresh-owner/delayed-cancel reload guards; existing Send/retry/model/cost contracts preserved. Final2066passed/1skip426.610s;215runtime fingerprints unchanged,60JSsyntax,38Extension/2669payload parity. Same-host isolated install/native-ready/reinstall/uninstall preserves data. Unsigned beta; independent clean-machine, visual installed UI, real login/provider and signed A-to-B update still pending. User27016/398 untouched, own tests closed. Never deploy/reload user work merely to test.

รุ่น Runtime `0.15.398`: accepted Story ChatGPT missing-request DOM refresh before review. Route docs/reports/story-missing-request-398.md → chatgpt.js storyImageMissingRequestEvidence/storyImageWaitObservation/createStoryImageWaitMonitor and background.js refreshStoryChatGPTResult. Same saved chat/request/scene only, stable idle30s +3samples, one durable reload then strict owned-image read; global Stop/progress veto even without request DOM. No Send/reset, saved media unchanged. Flow100% reload preserved and replay-tested. Final2021 passed434.497s; focused215 passed;38-file package parity and50frozen runtime files unchanged. Candidate validated; installed E2E pending.

รุ่น Runtime `0.15.397`: shared Shorts/Drama storytelling modes and compact controls. Route docs/reports/storytelling-397/README.md → core/storytelling.py, story_performance.py, drama_options.py, creation_queue.py, web_ui/storytelling.js/css; Extension chatgpt.js validates new opt-in structure and retains it in existing JSON repair. Old jobs remain legacy, Send/receipts/Flow controls unchanged. Full2020/379.972s and focused238 passed; candidate validated, installed E2E pending. Keep Chrome profile/ID/loaded path; reload only when safely idle, not uninstall.

Desktop sidebar-flow-test-remove-1: only left “สร้าง” → “ทดสอบ AI → Flow” entry removed from web_ui/index.html. Header entry, controller and old jobs remain. Extension395 unchanged; route docs/reports/sidebar-flow-test-remove-20260921.md.

รุ่น Runtime `0.15.396`: pending Story ChatGPT motion answer reload/read recovery. Route docs/reports/pending-motion-refresh-396.md → chatgpt.js pendingChatGPTMotionSnapshot/refreshPendingChatGPTMotion + initial/resume waits; background.js refreshCompletedChatGPTResponse pending_motion_answer purpose. One durable same-context reload after90s blank idle owned DOM, then read only; never replay requested Send or images. Prior395 short-film mode retained. Installed396 E2E pending.

Desktop function-controls1 (2026-09-21): `web_ui/function_controls.js/css` → display-only allowlisted switch rows, segmented native audio radios; native values/controller identity preserved. Selection/consent excluded; no provider/queue logic changes, Extension394 unchanged. Route `docs/reports/function-controls-20260921/README.md`; installed EXE/WebView2 pending, no live reload.

รุ่น Runtime `0.15.394`: optional Shopee story-first review checkbox, immutable per-job/queue style, no forced CTA in prompt/result/edit/resume/motion, original audio choice preserved. Route docs/reports/product-story-first-394.md → core/product_script.py + core/product_story.py + story_manager.py + product_story.js; Extension chatgpt.js only retains saved style during existing JSON repair. No Send/Flow/reveal algorithm changes, installed E2E pending. Preserve old jobs and no live reload.

รุ่น Runtime `0.15.393`: ChatGPT temporary WEB: URL → saved conversation binding. Route docs/reports/chatgpt-route-393.md → chatgpt.js revealChatGPTAnswer and tests/chatgpt_route_393.cjs. Same job/run, unique exact latest request and any observed message ID required; never a general URL-change bypass. Existing392 reveal/Flow fixes and391 no-membership behavior retained. Installed verification pending; do not auto-resume or reload the user's pending job.

Desktop creation-old-remove-1: confirmed individual/bulk cleanup of old stopped queue/orphan suggestions with persistent dismissal and no media deletion. Route core/creation_queue.py → ui/creation_queue.py → web_ui/creation_queue.js/CSS/index and docs/reports/creation-old-remove-20260920/README.md. Preserve scheduler, saved settings, receipts and live ownership. Extension392 unchanged; app restart needed for new action.

รุ่น Runtime `0.15.392` — result readiness and Flow prepared-project continuation. Route docs/reports/result-readiness-392.md → chatgpt.js revealChatGPTAnswer/generatedImageElements/submitImagePrompt, flow.js flowPromptMatches/autoPrepare/queuePackageReload, background.js freshFlowProgressMatches and Generate duplicate evidence, ui/main_window.py error origin. Preserve current request/run/conversation ownership, no-resend receipts, Gemini/Meta/settings and391 no-membership contract. Source and immutable package ready; full1978 exposed one fixture-only dependency fixed and final202 focused passed with40 runtime hashes unchanged. Installed verification pending; never reload active/uncertain work.

รุ่น Runtime `0.15.391` — user-requested removal of ALL Extension membership/API Token checks. Route docs/reports/extension-no-membership-391.md → background/chatgpt/popup, LocalBridge enqueue/lease/cover/Meta, desktop-only start/queue guards and connection UI. No Extension status/authorize requests; former routes410. Keep desktop Login, internal loopback capability, paired version and job/run/tab/receipt ownership. No license-wait UI.390 Product redesign unchanged; historical Extension vault untouched. Installed391 E2E pending; never reload active/uncertain work.

Desktop UX2026 refresh: `web_ui/ux_2026.js/css`, nativebackdrop/full-logo/localSVG/compactExtension panel. Display-only state adapter; app/Presenter/Shopee controllers retain final/minimize/action ownership. Full/compact state adds only bound-profile authorization boolean. Report `docs/reports/ux-2026-implementation/README.md`; no user reload/provider generation/server work; installed WebView2 verification pending. Extension384 unchanged, do not repackage/reload it for this UI change.

รุ่น Runtime `0.15.389` — Product compliant-image prompt recovery; installed verification pending.

Current389: `docs/reports/product-prompt-repair-389.md` → core/product_image_recovery.py + flow_motion_plan.py, background productPromptRepairMessage, chatgpt runProductImages/runSceneRepairHelper. Product-only saved-source helper returns one compliant new composition to the original image tab. Confirmed service failures may continue with cancellable backoff; one policy redesign per slot, never an endless refusal-bypass loop. Exact failure/claim/candidate/reservation journal survives restart and preserves saved images/original analysis. Unknown sends/downloads/auth/review remain stopped. Motion uses effective saved prompt. Story/Flow388 and membership unchanged; runtime paired389, no active reload.

Current388: `docs/reports/flow-scene-rebuild-388.md` → flow.js recoverFlowPolicy, background storyRepairMessage/getFlowPackage, core/flow_replacement.py. New Story/Product packages rebuild BOTH image and video prompt through the saved original AI provider after an owned confirmed failure, including audio/timeout service errors. New images are reviewed before the existing fresh-project transaction. Product rotation requires a new exact failure and previous request, preserving facts/dialogue and old media. In-flight helpers/approved results stay intact; real review, unknown Send, busy, login/credits/settings/cancel stay protected. Continuous watch387 unchanged. No active runtime reload.

Current387: `docs/reports/flow-continuous-watch-387/README.md` → flow.js monitor/report/load, background freshFlowProgressMatches, local_bridge continuous flag, MainWindow._wait_flow_step.7A343B round7:0credits verified in saved settings log, then desktop Stop and home-page stale947seconds. Reset attempt counters; live owned observation extends wait; cancellation/home must not rehydrate old receipt. No automatic unknown-Send replay or provider-policy bypass. Stable install folder/member386 and confirmed-service385 repair preserved.

Current386: `docs/reports/extension-login-persistence-386/README.md` + `MIGRATION.md` → core/membership status, popup membership UI, desktop Login/guide. Auth remains version-independent; saved same-profile renew is not Login Required. Stable path is browser_extension; release deliverables remain immutable. Installed Default385 uses a versioned path; user authorized preparing one-time migration, not performed. Never reset/copy profile/receipts or auto-adopt a new ID. Flow385, membership384 server/client guards and provider sends preserved.

Current385: `docs/reports/flow-service-repair-385/README.md` → flow.js generationSnapshot/readGenerationState/recoverFlowPolicy. New stable native Failed + reason + no-charge + Retry card for the exact job/run/scene/project may override stale queue prose, never active controls/results. Service errors use the same image/provider text-only helper, then an owned fresh project through existing receipts. Preserve Story policy alternatives, settings/membership/cancellation/unknown-send protections. No app/Chrome reload or paid test performed; do not infer installed success from fixtures.

Membership403/1010 route: `docs/reports/membership-384/transport-fix.md` → `core/membership.py::request_server`. Explicit product User-Agent for shared desktop/Extension broker, no server/Extension change. Restart desktop only when safe, never restart the user's visible server for this fix.

Current384 membership client: `docs/reports/membership-384/README.md` → core/membership + LocalBridge/MainWindow action gates + web_ui/membership + Extension popup/background/content gates. Token Login, Windows secure renewal/proof, 30s heartbeat/300s memory lease, manual same-Token/same-machine after kick, separate same-member Extension/profile. Accepted result/receipt paths preserved; no automatic activation, no real Tokens/online writes/reload. P1 is deployed per owner-server live20260920 report (older staged-only notes below superseded). P2 installed/frozen verification and P3–P6 remain pending; never claim release-ready from fixtures.

Desktop Shorts queue cleanup: `docs/reports/story-queue-declutter-20260920/README.md` → web_ui index/app/creation_queue + read-only finished_at field. One shared queue, default unfinished/history filters, collapsed standalone recovery. Philips75FE71 stopped at5saved/7planned; scene6 already accepted, original conversation preserved on explicit Resume. Extension383 unchanged; do not interrupt active jobs or treat fixtures as installed recovery.

Desktop Shopee attachment/skip: docs/reports/shopee-product-attachment-retry-20260919.md → product_attachment.py + workflow/service/store/progress. Bounded3 same-link imports, observed-IME dismissal, guarded same-card Add; typed unavailable products skip their clip and continue after owned Shopee close/reopen. Never count skipped as published/substitute another product; unknown Send/loading/ambiguous remain protected. Full1865passed395.709s, focused245passed82.037s. User restarted engine41656; Samsung skipped via confirmed action. Real run2af36775 complete5/5 in508.475s with native receipts; automatic skip continuation fixture-tested. Original19 preserved,24totalpublished/0uncertain, idle/test19065closed/heartbeatpaused. PostingJS9/progressJS10, Extension383 unchanged; never take foreground while user games.

Desktop Shopee adaptive settings: docs/reports/shopee-adaptive-settings-20260919.md → settings_layout/settings/device/options/store/workflow/service + postingJS8. Recognize combined reuse or split Duet/Stitch, set present switches from saved choices, sharing OFF; missing AI is null/unavailable, not enabled. User-authorized new-Start allow_missing_controls defaults true, explicit false stays strict. Preserve ambiguous-control and unknown-send guards. Full1834passed359.639s; captured-page replay passed, new-code live Post unverified. Normal EXE reopened/idle; no further foreground takeover while user games, no new Start; heartbeat paused. Extension383 unchanged.

Desktop Shopee reset remaining: docs/reports/shopee-reset-remaining-20260919.md → restart/service + postingJS7/progressJS9. Normal Start automatically clears old preparation for selected never-sent rows; explicit reset-unsent creates ready0/N without a worker. Preserve published/uncertain receipts, media and choices, archive old evidence; guard busy/revision/run. UI clears old error/step/count and restores ready selection. Actual reset13published+17unsent→0/17 verified; after user unlocked, new Start published1/17 with native receipt and automatically continued2/17. Not all17 complete. Full1818passed360.967s; Extension383 unchanged, user worker left active.

Desktop Shopee direct Start: docs/reports/shopee-direct-start-20260919.md → service/contract/store/workflow + progressJS8/postingJS6. New Starts use explicit confirmed_selection, not an automatic profile/account tour; close/reopen then direct Video/create/gallery. Distinguish user-confirmed intended account from live_ui proof, preserve old modes/unknown sends, veto only already-visible contradictory own account without extra navigation. Normal idle restart needed; Extension383 unchanged; live E2E unverified. Supersedes account-once behavior for new Starts below.

Desktop Shopee close-before-first-post: docs/reports/shopee-queue-cold-start-20260919.md → service/workflow/device + progressJS7. New queue closes Shopee once before first account/create, then uses existing native-success close between clips. After cancellation at any unsent stage, explicit Start creates a fresh run, not a resume of the old last_step. Explicit first launch and confirmed-close flag avoid trusting stale accessibility package. Unknown sends/other workers are not reset, no clear-data or blind Post. Normal idle restart required; Extension383 unchanged; new live E2E unverified.

Desktop Shopee shared-preflight: docs/reports/shopee-shared-preflight-20260919.md → device.observe_controls/commit_observed_post + settings/publish/store + progressJS6. Replaces repeated per-control passes with shared stable screenshots/hierarchies; validates final page before Send claim, no slow phone checks after claim. Prepared versus press_committed is explicit, but committed/unknown never auto-replays. No new phone publication or measured live savings; normal idle restart required. Extension383 unchanged.

Desktop Shopee confirmed-post close/reopen: docs/reports/shopee-reopen-navigation-20260919.md → service/workflow + progress UI. New Starts freeze close_after_publish; exact durable live native success permits closing only Shopee, then prepare_post_page opens it before the next clip. Unknown/draft/wrong identity/pause cannot close. Actual phone home→Live & Video→+→gallery tested twice with idle targeted close/reopen; no new publication. Legacy baseline now clearly labelled as old stopped history. ProgressJS5/CSS3; Extension383 unchanged; normal idle restart required.

Desktop Shopee continuous queue v2: docs/reports/shopee-continuous-queue-20260919.md → core/shopee_posting/contract.py + service/store/workflow and progress UI. New confirmed queues verify live account once per batch; no per-clip old-post/caption baseline and no old-profile fallback after missing native acknowledgement. Same-caption distinct clips permitted, local duplicate/unknown-send guards retained, selected-order continuation after native success. Existing queued histories not rewritten, old versionless readers retained for old sends only. User28-row queue and running app untouched; normal idle restart required. Extension383 unchanged; no new real Post in this fix.

Desktop Shopee posting-stability + native-upload completion: docs/reports/shopee-post-stability-20260919/README.md → core/shopee_posting/device.py/workflow.py/result.py/store.py/service.py and progress UI. Fullscreen own-profile entry, one account check, stable100ms single gestures, exact product-picker readiness/one guarded navigation retry; native upload acknowledgement completes without a profile tour. Legacy same-send native acknowledgement may reconcile an unknown through the explicit local evidence action, no Post/replay. Real La Fleur single publication completed and reconciled1/1; not multi-clip E2E. Extension383 unchanged; final tests/cleanup in report.

Desktop Shopee queue-progress-v1: docs/reports/shopee-queue-progress-20260919/README.md → core/shopee_posting/progress.py + store/service/workflow and web_ui/shopee_post_progress.js/css + shopee_posting.js. Select all eligible existing rows, durable owned posting_run, actual-step popup/pill and verified-only completion; no automatic Post/replay. Existing-queue selection has no30cap; import still30. Extension383 unchanged. EXE UI used current backend with fixture progress only, not a real posting batch.

Desktop Shopee post-options-v1: docs/reports/shopee-post-options-20260919/README.md → core/shopee_posting/options.py/settings.py plus store/service/device/workflow/publish, core/android_wifi.py, web_ui/shopee_posting.js. Typed defaults/per-row snapshots, actual switch verification, latest-caption baseline, no duplicate Post and unique saved-phone port recovery. No Chrome Extension changes; real mobile settings test only, not another publication.

Desktop render-backend-v1: docs/reports/render-backend-20260919.md → core/render_backend.py/render_copy.py, ui/rendering.py, versioned render_snapshot and video_encoder/source-fps settings. Legacy CPU/voice identity retained; new GPU/CPU fallback, measured progress, strict video-copy with normalized audio, fused subtitle/logo, bounded4green threads. Extension383 unchanged. Installed restart/E2E not performed.

รุ่น Runtime `0.15.383`: ChatGPT Story helper references/name recovery: docs/reports/scene-helper-383.md → chatgpt.js sceneRepairRequest/validateSceneRepair/runSceneRepairHelper/generateStoryImageWithRepair and background.js storyRepairMessage. Canonical source images + exact entity labels, legacy invalid-ready correction within the existing two rounds; no endless policy retries or changes to normal Gemini/Flow/Meta sends. Installed E2E pending.

SmartFlow membership P1 staged (2026-09-20): `docs/reports/smartflow-membership-p1-20260920.md` → owner-host server `backend/services/smartflow_membership.py`, router, admin members/online pages. Separate lazy SQLite, hashed secrets, atomic one-Token/one-installation proof, scoped Extension pairing, expiry/block/kick/reset, admin audit. User confirmed same Token works manually on SAME machine after kick; never auto-reactivate. 36 server tests + 10 headless UI checks and staged Next build passed. NOT deployed, no production membership DB, desktop/Extension gate P2 still pending. Update TWO-input patch/Extension and installer plans remain unchanged and pending; no runtime/version/receipt changes.

Customer release execution plan (in progress, synced2026-09-20): `docs/plans/smartflow-customer-release-roadmap.md` defines P0 packaging/data/two-file contracts and early internal smoke → P1 server Token/online pages (staged) → P2 desktop/Extension Login → P3 two-input updater → P4 separate integrated Setup A → P5 real A-to-B patch/rollback → P6 staged delivery. P0 frozen smoke and P2–P6 remain pending. Tests include patch-only/existing Extension and patch/new Extension without JSON/EXE uploads, plus Shopee/other-worker safe idle. Deferred Shorts motion/cast plan remains linked, not implemented. Do not distribute before working login/updater.

Facebook Planner v2 (desktop): docs/reports/facebook-planner-v2/README.md → core/facebook_planner.py / facebook_post.py / facebook_upload.py and web_ui/facebook_planner.js / facebook_post.css. Saved Final category selection, durable editable drafts, Bangkok spacing/shift previews, explicitly confirmed sequential Page schedule batch. No automatic/local-clock posts, no unknown POST retry, no Extension/creation queue changes. Tests test_facebook_planner / test_facebook_post; live Page scheduling unverified.

Desktop Meta single-video + green render v2: docs/reports/meta-single-green-v2.md → core/meta_prompt.py / MetaVideoManager.package / queue+StoryManager+UI version capture; green_screen.py / green_cache.py / green_progress.py. NEW Meta prompt2 only, old queues/jobs retain legacy bytes; Extension382 unchanged with choice fallback intact. Green direct pass or bounded alpha cache plus measured frame progress, not preview changes. Tests test_meta_single_video/test_green_render_v2 and benchmark_green_render.py. Installed provider smoke pending; no automatic reload.

รุ่น Runtime `0.15.382`: Meta two-option video offers → choose option2 once in the same chat, before considering381 reattachment. core/meta_video.py meta_choice_offer/_choice and Extension metaChoiceOffer/stepChoice/inspectMetaDOM; exact original request plus exact follow-up owns the new answer. Preserve source/audio instructions, no duplicate choice Send or stale first-answer download. Read docs/reports/meta-choice-382.md; installed E2E pending.

รุ่น Runtime `0.15.381`: Meta completed-no-video recovery only. Route core/meta_video.py retry_prepared and browser_extension/src/platforms/meta-ai/video.js. Full completed owned reply + no video/progress, stable samples → two durable SAME-image/prompt retries; archive old receipt/conversation and adopt successor after lost ACK. Unknown/policy/quota/busy/loading-video paths cannot retry. Preserve all Flow/Gemini/ChatGPT contracts. Read docs/reports/meta-retry-381.md; installed381 pending.

รุ่น Runtime `0.15.380`: ตัวละครสนทนา ไม่มีผู้บรรยาย/ซับ สำหรับงาน Shorts ใหม่ actor_dialogue_version=2. Route core/story_performance.py, web_ui/media_audio.js, story batch copy, queue capture and final subtitle gate. Preserve versionless old actor jobs and all provider Send/receipt logic. See docs/reports/conversation-only-380.md; installed E2E pending.

รุ่น Runtime `0.15.379`: Meta prepared must validate exact text in the unique readable editor independently of its center click target. Long drafts can obscure that center after insertion. Existing draft advances to upload without retyping; absent/busy/blocked empty editors expose a deduplicated wait reason. All Send/image/receipt guards retained. See docs/reports/meta-prepared-379.md; active378 untouched, installed379 pending.

รุ่น Runtime `0.15.378`: opt-in Shorts actor dialogue via core/story_performance.py; UI media_audio.js → queue/settings → StoryManager → motion/Meta prompts → original soundtrack. Actor dialogue survives repair without narrator substitution. Read docs/reports/shorts-actor-dialogue-378.md. Installed378 pending; preserve ordinary narrated jobs.

Desktop native-meta-audio supersedes the initial audio-ui-v2 Meta gate: original clip audio selectable for Meta/Flow, conditional Thai soundtrack prompt, original MP4 retained and probed at composition; actual-audio subtitle route, no automatic TTS fallback. Keep version1 snapshots and Extension377 Send/receipts unchanged. Read docs/reports/native-meta-audio.md; installed new native generation remains unverified.

รุ่น Runtime `0.15.377`: user-authorized Meta AI experimental video provider for new product stories and Story Shorts. Separate meta_ai receipts/owned tabs/downloads; preserve ChatGPT/Gemini image provider and Flow behavior. UI/queue/compose contract and limitations: docs/reports/meta-video-377.md. Installed377 E2E pending, not equivalent to previous manual Meta tests. Preserve376 completed-answer fix.

Story Shorts clear-all recovery list: `ui/story_recovery.py`, `CreationQueue.dismiss_story_jobs`, `web_ui/app.js` clearStoryRecovery/renderStories. Confirmed idle-only cancellation of all pending ordinary Shorts; preserve files and exclude other modes. Desktop app37/styles8; Extension375 unchanged. See docs/reports/story-recovery-clear.md.

รุ่น Runtime `0.15.375`: exact owned ChatGPT motion service-error Retry, including native error controls inside a user message. Read docs/reports/motion-service-retry-375.md before changing motion wait/recovery. One durable native Retry per exact pending request; no new prompt/upload, busy/partial/result/policy/stale-owner retry. Initial and Resume share the guard. Installed375 pending; active374 retained.

รุ่น Runtime `0.15.374`: pending Story ChatGPT image routes and pre-click failure phases. Read docs/reports/story-preflight-374.md for the exact E79325 evidence, bounded draft stabilization and narrow373 no-click reconciliation. Preserve uncertain-send receipts. Older runtime headings below are historical; installed374 E2E pending.

รุ่น Runtime `0.15.373`: fix waitForResponseIdle's out-of-scope progress variable and extend existing same-chat stale-Stop refresh to the boundary after a saved complete scene, before starting the next image. Exact ready desktop motion result + completed scene + absent next request + idle owned DOM required. See docs/reports/response-idle-373.md; installed E2E pending. No Flow attachment or generation policy changes.

รุ่น Runtime `0.15.372`: Flow Start picker requires a loaded thumbnail and no loading animation. A stalled exact thumbnail may refresh the same project once after completed-upload/no-submit proof; durable claim prevents repeated refresh/reupload. Read docs/reports/flow-thumbnail-372.md. Running animation/progress keeps waiting; prepress source guard returns to lookup on remount. Installed E2E pending.

Installer requirement2026-09-17: clean-machine complete dependency installation, paired desktop/Extension and real installed checks. Read docs/plans/clean-machine-installer.md before future installer work; do not ship only an EXE or rely on developer-machine packages/profiles. Requirement recorded, not yet a certified clean-machine installer.

รุ่น Runtime `0.15.371`: CC3703 shot2 uploaded successfully but Start picker lookup expired after8s. Activity-based exact-asset picker wait and same-project pre-submit recovery; read docs/reports/flow-picker-371.md before attachment changes. Preserve submission receipts and all successful provider paths. Installed371 E2E pending.

Desktop product-jobs-2: Shopee compact pending/hidden/trash sidebar; recoverable job removal stored atomically in the creation queue, no media deletion or automatic restore/requeue. Route `ui/product_jobs.py`, `core/creation_queue.py`, `web_ui/product_continue.js/css`, PROGRAM_BLUEPRINT section3 and `docs/reports/product-jobs-sidebar.md`. Extension370 unchanged; no provider automation edits.

รุ่น Runtime `0.15.370`: cover-only guarded ignored-click retry, bounded original-image download recovery, durable send diagnostics and truthful desktop cover pause. See docs/reports/cover-unsent-93047F.md and PROGRAM_BLUEPRINT. No installed reload or legacy receipt reset. Unreleased369 package preserved;370 fixes snapshot form scope with actual-function tests.

รุ่น Runtime `0.15.368`: music-selection-1 and observation contract. Read docs/reports/music-observation-368.md; core/music_library.py, core/automation_observation.py, browser_extension progress outbox and passive waitForResponseIdle. Existing safe refresh owners/receipts preserved. UI app36 with music_library/automation_status. Installed E2E pending; do not reload active user work.

Completed popup auto-close: desktop-only app.js renderProgress and presenter_progress.js, app cache35/presenter cache3. Close inactive successful owned job immediately, including minimized pill; never infer Final from active100% or Extension complete. Extension367 unchanged. docs/reports/completed-popup-autoclose.md.

รุ่น Runtime `0.15.367`: explicit owned failed/no-charge/Retry card routes to existing repair after two unchanged DOM reads, not a30s timer. Duplicate alternate proposals now receive typed desktop feedback and a persisted same-provider text correction loop before image generation. No blind Retry, receipt reset or review bypass. Read docs/reports/flow-terminal-367.md. Latest6FDFEE entered repair then stopped on duplicate narration; duplicate rejection remains enforced but is now recoverable.

รุ่น Runtime `0.15.366`: ChatGPT completed answer with stale Stop may refresh the exact tab once before a persisted unsent motion follow-up, then resume the saved job. Requires completion/ownership/stability and fresh no-draft/no-local-progress proof. See docs/reports/completed-response-refresh-366.md. Installed recovery pending; no active-user reload.

Desktop scene-gate atomic resume (2026-09-16), Extension365 unchanged: explicit ready persists requested before UI dispatch/ACK; status never retries terminal state. Historical error moves to error_history before active/complete transitions. Resume may retain the same run ID. docs/reports/scene-resume-gate-20260916.md.

รุ่น Runtime `0.15.365`: fresh-project repair handoff identity, pre-submit monitor barrier, delayed-event rejection and paired desktop handoff wait. docs/reports/flow-handoff-365.md. No resetting receipts or blind Generate retries; installed E2E pending.

รุ่น Runtime `0.15.364`: separate old-reference proposal compatibility from new-image motion compatibility for authorized revise_story. No coercion or unresolved-review bypass. See docs/reports/alternate-reference-364.md.

รุ่น Runtime `0.15.363`: alternate-image motion JSON exact saved-dialogue quote recovery. See docs/reports/alternate-json-363.md. No extra Send, media generation or review-flag coercion. Installed E2E pending.

Motion JSON quoting: core/motion_json_contract.py shared by story_visual_plan.motion_request and flow_motion_plan.motion_format_request. D5DE10 invalid embedded Thai-dialogue quotes; report docs/reports/motion-json-quotes-20260916.md. Desktop-only; Extension362 unchanged; no legacy receipt reset.

รุ่น Runtime `0.15.362`: Product3–15 scenes and versioned native on-camera Thai reviewer prompts; frozen count, local remembered default, repair delivery preservation. See docs/reports/product-planning-362.md. Installed/lip-sync verification pending.

รุ่น Runtime `0.15.361`: automatic same-run Flow checkpoint recovery can hand a confirmed owned terminal to existing alternate scene/image/prompt recovery. Never lift observation for another run, unknown send or Presenter. See docs/reports/flow-recovered-terminal-361.md. Installed recovery unverified.

รุ่น Runtime `0.15.360`: Gemini motion response waits use owned answer DOM state, not a six-minute idle limit. Completed malformed JSON is inspected as completed; actual busy remains waiting. Supersedes undelivered359 candidate. docs/reports/gemini-motion-360.md.

รุ่น Runtime `0.15.359`: Gemini-only restarted motion JSON recovery and activity-based wait in initial/Resume/candidate readers. Exact job/index/context and all content flags retained. docs/reports/gemini-motion-359.md. Installed validation pending.

รุ่น Runtime `0.15.358`: Gemini text attachment identity uses decoded full-image signatures for readable local blobs, not transient blob URL alone. Retain strict unreadable-URL/order/content guards. See docs/reports/gemini-attachment-358.md. Installed validation pending.

รุ่น Runtime `0.15.355`: Gemini saved-image scene gate includes PROVIDER_KEY for prepare/ready/status. Background rejects missing provider explicitly instead of defaulting to ChatGPT. docs/reports/gemini-scene-gate-355.md. Unsent/empty-conversation recovery remains separate, no automatic replay.

รุ่น Runtime `0.15.354`: Chrome launch/tab cleanup: core/chrome_profile.py, MainWindow._open_url/_activate_or_launch_chrome/_close_saved_flow_tab, LocalBridge cleanup command guard/ACK, background.closeAutomationBrowser/closeSavedCoverTabs. docs/reports/browser-lifecycle-354.md. Do not close a saved image chat while the next scene still uses it.

Final88% / เวลาคำบรรยายไม่อยู่ในช่วงเสียงหรือซ้อนกัน: inspect core/subtitle_chunks.py and docs/reports/subtitle-eof-recovery.md. Clip/drop only out-of-audio intervals against PCM chunk bounds, retain raw cached results and reject other corruption. Do not resend Flow/transcription to fix a local merge. Extension353 unchanged.

Product page/resume UX: core/product_continue.py → existing retry_story/create_product; web_ui/product_continue.js/CSS → exact-job latest cancelled card. No new form values on Resume, no automatic queue-wide resume. Extension353 unchanged. docs/reports/product-continue-ui.md.

รุ่น Runtime `0.15.353`: alternate-image state wait and one exact-owned empty-result refresh; no legacy Stop/timeout, no resend or receipt reset. See docs/reports/alternate-recovery-353.md. Installed E2E pending.

รุ่น Runtime `0.15.352`: Flow alternate-image reader accepts current roleless ChatGPT image replies only after the exact unique request; excludes earlier/source images, persists proof before desktop ACK. Desktop shows replacement stage. docs/reports/alternate-image-352.md; installed recovery pending.

รุ่น Runtime `0.15.351`: เรื่องเล่าสินค้า Shorts replaces NEW Product form submissions; legacy Product job resume unchanged. Product/person reference snapshots and cast image-only library. Read docs/reports/product-story-351.md. Installed E2E pending.

รุ่น Runtime `0.15.350`: new Story/Drama Flow jobs use an image → video → scene voice → next-image barrier. Read docs/reports/scene-pipeline-350.md. Legacy jobs retain their ordering; installed E2E pending, not a proven golden build.

รุ่น Runtime `0.15.349`: changed Story/Drama event recovery. Read docs/reports/flow-story-context-349.md; core/scene_context_revision.py, core/flow_replacement.py, StoryManager.activate_flow_story_revision, render worker, and runFlowAlternativeHelper. Installed E2E pending.

รุ่น Runtime `0.15.348`: continuous same-image Flow repair. Read docs/reports/flow-continuous-repair-348.md; background storyRepairMessage/getFlowPackage, flow recoverFlowPolicy, core/story_prompt_recovery.py. Supersedes347's automatic two-round limit for Flow only. Installed E2E pending.

รุ่น Runtime `0.15.347`: recovery routing: read docs/reports/flow-same-image-only-347.md. Source package same_image_only; preserve two automatic rounds, explicit manual text restart, and unknown-send receipts.

รุ่น Runtime `0.15.346`: Flow same-image text-first recovery → fresh project. Route docs/reports/flow-same-image-repair-346.md, background getFlowPackage/storyRepairMessage/flowFreshProjectAction and flow recoverFlowPolicy. Do not fabricate replacement provenance for the original image; original-reference and replacement checkpoints stay distinct. Old in-flight helper work is not restarted. Story progress displays the matching job/run/scene helper message. Installed346 pending.

รุ่น Runtime `0.15.345`: fix pending-request conversation routing and Gemini accepted-request remounts, not a blanket rollback. Start at docs/reports/resume-routing-345.md, core/ai_web_resume.py, Background startAIWebJob and content geminiTextRequestSnapshot/readPendingAnalysis. Preserve exact old requests, saved media, ready motion plans, cover queue gate and at-most-once boundaries. Read docs/reports/three-content-workflow-audit-20260914.md for actual successful Product/Story/Drama baselines and the installed344 failures that prior fixtures missed. Source/fixture and installed results are separate.

รุ่น Runtime `0.15.344`: motion-answer completion and passive partial-JSON recovery. Read docs/reports/motion-response-344.md before changing submitPrompt/prepareFlowMotionPlan/resumeStoryVisualPlan. Incomplete JSON is still waiting; an owned full live answer replaces cached answered_text with original evidence retained. One durable schema-only format request comes from the desktop contract; do not rewrite flags or regenerate images for a partial answer. Preserve generic analysis, Gemini ownership and existing Flow controls. Installed344 E2E pending.

รุ่น Runtime `0.15.343`: Story/Drama pre-Flow visual conflict repair. Read docs/reports/story-visual-repair-343.md and core/story_visual_plan.py. Same-image motion recheck → same-provider corrected candidate → validated new motion → Flow package selects that image/prompt together. Preserve original media/narration, ready scenes and unknown Sends. No flag coercion or fake Flow failure. Installed343 E2E pending.

รุ่น Runtime `0.15.342`: Story ChatGPT ภาพช้าเกิน6นาทีไม่ใช่ failure. อ่าน docs/reports/story-image-dom-wait-342.md ก่อนแก้ซ้ำ: initial/Resume รอ DOM ฉากเดิมต่อ; refresh ได้ครั้งเดียวเมื่อพบ broken-load/completed-empty จริง พร้อมตรวจเจ้าของ/ข้อความล่าสุด/ไม่มี draft/ไม่มีงานกำลังสร้าง. ไม่ส่งซ้ำ ไม่รีเฟรชเพียงเพราะภาพโหลดช้า. Desktop monitor ไม่มี total timeout อยู่แล้ว; pair342 และตรวจ heartbeat field names. Installed342 ยังไม่ทดสอบจริง.

กรณีติดตั้ง341แล้วยังเห็นปก0/2: อ่าน docs/reports/cover-queue-recovery-341.md ก่อนแก้ซ้ำ. Run Queue อาจกำลังอ่านคำขอ terminalเดิม. งาน00CDCDกู้ผ่าน existing cover-only action จริงแล้ว: แนบ2/2→ส่งหนึ่งครั้ง→บันทึกปก→ปิดแท็บ โดยFinalเดิมไม่เปลี่ยน. ห้ามถือว่าติดตั้งใหม่เท่ากับกู้คำขอเก่าแล้ว

รุ่น Runtime `0.15.341`: ปกหยุด0/2ทั้งที่ ChatGPT แนบครบเพราะรูป HTTPS altว่างอยู่ในกรอบ role=group ที่มีชื่อไฟล์. อ่าน docs/reports/cover-semantic-reference-341.md ก่อนแก้ซ้ำ. Cover-only semantic/structural fallback และ bounded upload activity wait; อ่านภาพใหม่หลังรอprogressACKเพื่อกันรูปเปลี่ยน. ไม่แนบหรือส่งซ้ำ. โปรแกรมเก็บ observed/elapsed_ms โดยไม่ถือว่าปกเสร็จ. Full/installed results แยกในรายงาน; งานผู้ใช้เดิมไม่ถูก reset.

รุ่น Runtime `0.15.339`: Product visual contract and one durable legacy visual revision. Read docs/reports/product-visual-contract-339.md and core/product_visual_contract.py before motion/resume changes. Original product facts/narration and saved image bind the new request; old AI camera cuts are audit only. Ready/unknown legacy requests are preserved; paired desktop and Extension required. Installed E2E pending.

รุ่น Runtime `0.15.338`: Product motion drafts must stay inside the actual reference shot. JOB2D9579 scene2 requested a dashboard cut absent from its studio product image; material_change=true previously skipped all recheck. Permit one same-provider/same-image product motion correction for otherwise valid owned content flags, never save the flagged answer. Preserve product facts/narration; Story/Drama material-change rules unchanged. Original answer/request and retry budget survive resume. Read docs/reports/product-reference-motion-338.md; installed338 pending.

รุ่น Runtime `0.15.337`: cover-only intrinsic/declared image size discovery in the exact owned answer; preserve loaded/stable/no-Stop and saved-file-before-close gates. Bounded collector_state distinguishes request/answer/loading/download from generic timeout. Live installed336 recovered4F9F85 via existing collect_only in7.2s without generation;337 installed test pending. Read docs/reports/cover-intrinsic-result-337.md. Historical failure-time DOM geometry is unknown; do not call it proven.

รุ่น Runtime `0.15.336`: user authorizes cross-chat Story image recovery. Changed /c URL may rebind only to a unique full matching prompt in the latest user turn; old chat message IDs/turn counters do not block that match. Persist new owner before download on resume. No Send/retry/tab creation;335 preference-pair fix retained. Read docs/reports/story-cross-chat-336.md. Installed336 pending.

รุ่น Runtime `0.15.335`: fixes334 responsive preference labels (hidden mobile+desktop spans concatenated in textContent). Read actual child labels within exact owned response; stable one-image receipt/download/ACK recovery remains. Read docs/reports/story-responsive-comparison-335.md. Installed335 pending; live334 confirmed.

รุ่น Runtime `0.15.333`: readiness hardening, not provider Send changes. Job/run-scoped close with enqueue cleanup_runs and durable tab plan; cleanup must finish before success ACK, cancelled/pending commands reject late ACK. Desktop freezes terminal Drama queue rows and binds EP callbacks to current Story; token/fresh-manifest cover finalization preserves cancel/manual edits. Final publish checks cancellation; native composition honors FPS/CRF; green uses versioned candidates; missing-primary/corrupt-backup JSON fails closed. See docs/reports/lifecycle-readiness-333.md. Installed333 E2E pending; retain all332 provider guards and user jobs.

รุ่น Runtime `0.15.332`: Gemini text requires stable exact request identity plus a live cleared composer; preserve original caller text through physical Send. Pin the answer to the accepted request's conversation container, persist bounded owner, and recover DOM remounts passively for30s instead of waiting for an unrelated answer/Stop. Transient acceptance disables retry; unchanged full-release60s retry budget is retained. Desktop preserves the draft and reports GEMINI_TEXT_REQUEST_REVIEW. Read docs/reports/gemini-text-request-332.md; installed332 E2E pending, do not reset legacy331 receipts or reload user work.

รุ่น Runtime `0.15.331`: Gemini first-image preflight and just-before-press current-reference guard; sampled changes during the60s acceptance wait remain latched even when reverted. Late exact acceptance wins, one retry only with unchanged current request/full release. Historical thumbnails excluded. Desktop preserves owned_motion_user_turn and phase-separated target/event diagnostics. Read docs/reports/gemini-send-331.md; installed331 E2E pending, no active-job reload.

รุ่น Runtime `0.15.330`: fixes verified329 new-chat root→/c/id rejection for Story ChatGPT. Require empty pre-Send boundary and exact unique first user message; pin resolved URL/message and recover dispatched329 root receipts without Send. Keep existing-chat/no-duplicate guards. docs/reports/story-new-chat-330.md; installed330 E2E pending.

รุ่น Runtime `0.15.329`: Story ChatGPT requires a fresh exact user message before waiting for its image; Stop/cleared/count alone no longer confirm Story Send. Durable prepared/dispatching/accepted phase and background nonce prevent replay; shared message ownership survives remounts and excludes old replies. Legacy unknown sends stay read-only recovery. Read docs/reports/story-send-329.md. Installed329 E2E pending; do not reload unresolved user jobs.

รุ่น Runtime `0.15.328`: StoryChatGPT exact prompt→owned answer images, no whole-thread fallback, stable asset identity, fresh-DOM recovery and no Stop before checkpoint/atStorytimeout. DesktopStudio explains empty/loading/wrong-owner without restarting the story. Live9E0644 scene11stillblank afteridle reload;10savedimagespreserved. Read docs/reports/story-image-scope-328.md. Installed328 E2E pending.

รุ่น Runtime `0.15.327`: live6D587F cover exists outside assistant text in SECTION[data-turn=assistant], with3 visual layers for1image. Fix cover-only scope/dedup/loading and addดึงปกเดิมจากเว็บ collect_only recovery to same owned tab/request. No generation/upload/newtab; preserve cover/FIFO saved-file gate. Read docs/reports/cover-result-327.md. Installed327 E2E pending; observed326 only.

Desktop intro-splice-2: ผู้ใช้แก้ความเข้าใจว่าให้เล่าไปก่อน แล้วสุ่มจุดแทรก ไม่ใช่ล็อกวินาที3. เลือกจังหวะพักในช่วงต้น4–12sก่อน (คลิปสั้นปรับ25–65%); ไม่มีจังหวะพักก็สุ่มช่วงต้นต่อ ไม่หยุดคิว. seedจากJob+introทำให้งานเดิม/inputเดิมได้จุดเดิม. นำเข้าและsnapshotก่อนสร้าง/เข้าคิวเหมือนเดิม. อ่าน docs/reports/video-intro/README.md และ core/video_intro.py; Extension326ไม่เปลี่ยนเพราะเป็นการประกอบในเครื่อง. Installed EXE E2E pending.

รุ่น Runtime `0.15.326`: ปก1–2รูปยืนยันจากชื่อไฟล์จริงที่มีเลขท้าย หรือ exact input File พร้อมรูปใหม่ทุกใบโหลดเสร็จและนิ่ง. ไม่เทียบชื่อ stem ที่ไม่มีเลขกับชื่อ indexed อีก. โปรแกรมบันทึกเฉพาะ reference_proof ที่กรองแล้ว; แนบครบไม่ใช่ปกเสร็จ. คิว/close/cleanupยังรอไฟล์ปกจริงตาม cover-completion-gate-1. อ่าน docs/reports/cover-reference-326.md; installed E2E pending.

Desktop cover queue gate (2026-09-12): video ready is not queue complete when AI cover is enabled. Read docs/reports/cover-queue-completion-gate.md and PROGRAM_BLUEPRINT12.4 before changing completion/resume/cleanup. This supersedes historical290 "cover failed but queue continues"; Extension325 protocol unchanged. Never rerender/regenerate scenes merely to repair a cover.

ก่อนแก้บั๊กซ้ำ: เปิด PROGRAM_BLUEPRINT.md หัวข้อ12.4 (ดัชนี2026-09-12) เพื่อดูส่วนที่เคยผ่านจริง วิธีที่เคยพัง วิธีแก้ และ regression guards. แยกงานจริงจบ/ตรวจเว็บเฉพาะจุด/ชุดทดสอบ; บันทึกเก่าที่เขียนว่า “ปัจจุบัน” ไม่ใช่รุ่นวันนี้. รายการ322–325ยังมี installed E2E ที่ไม่ยืนยัน ห้ามสรุปว่าจบเพราะ test ผ่าน.

รุ่น Runtime `0.15.325`: live provider DOM audit; Gemini image retry now binds composer references/upload state, preserving historical image-result guards and legacy reference reuse. ChatGPT attachment status excludes editable prompt prose/hidden progress. Desktop Flow discovery returns a structured busy block and UI never polls a missing command ID. Read docs/reports/provider-dom-audit-325.md. Installed325 E2E pending.

รุ่น Runtime `0.15.324`: Gemini text preflight scopes references to the current composer and reads the latest answer body, excluding historical image loading/toolbars. Trusted zero-click preflight reasons reach Desktop logs without claiming cancellation. Read docs/reports/gemini-text-preflight-324.md. Installed324 E2E pending; preserve legacy requested receipts.

รุ่น Runtime `0.15.323`: confirmed owned failed scene → same-provider safe alternate image → new-image motion → durable Flow home/new-project transaction. Single-scene smoke collector and dialogue fixes. Read docs/reports/flow-fresh-project-323.md. Installed E2E pending.

รุ่น Runtime `0.15.322`: sourceFile decodes both indexed cover source_images instead of passing the second inline image to URL fetch. Actual desktop packet/bytes test added. docs/reports/cover-second-reference-322.md.

รุ่น Runtime `0.15.321`: one safe alternate image via the job's original AI provider after confirmed Flow failure and unsuitable/exhausted same-image repair. Durable new image + new-image motion review + paired Flow attachment. Read docs/reports/flow-alternate-image-321.md. Installed E2E pending.

รุ่น Runtime `0.15.320`: English Thai-only dialogue instruction for new initial/repair motion requests. docs/reports/thai-dialogue-320.md. Manual-resume conflict remains separate/unresolved.

รุ่น Runtime `0.15.314`: cover collector scopes images to exact latest assistant reply, waits for Stop to disappear then stable image before save/close. No image/Flow Send changes.

รุ่น Runtime `0.15.313`: mobile completed tile detection and standalone tile download. No resend;312 prompt and checkpoint editor preserved. docs/reports/flow-mobile-result-313.md.

รุ่น Runtime `0.15.312`: Extension requests concise English role/action/camera prompts for new motion and repair. No forced fictional declaration; removes two legacy declaration prefixes on Flow handoff. No Send/queue changes.

รุ่น Runtime `0.15.311`: silent Send review preserves owned monitor and elapsed diagnostics; strong render activity excludes timeout. Actual422A9B acceptance remains unknown. docs/reports/flow-send-311.md.

รุ่น Runtime `0.15.310`: Extension-owned cover instruction, paired explicit title, exact prompt receipt; actual-source tests for both providers/ratios. Legacy queued requests retained.

รุ่น Runtime `0.15.309`: reconcile missing/cancelled helper with latest digest-bound desktop review on explicit resume; stop preserves needs_review. docs/reports/flow-review-reconcile-309.md.

รุ่น Runtime `0.15.308`: explicit failed-scene resume token, archived previous helper, new same-image/provider prompt before Flow; one persisted JSON formatting follow-up. docs/reports/flow-manual-resume-308.md.

รุ่น Runtime `0.15.307`: current policy-card grace cannot fall into generic retries. Confirmed current no-charge failures route to same-image/provider repair. Read docs/reports/flow-failure-routing-307.md.

รุ่น Runtime `0.15.306`: explicit fictional-AI clarification in initial and repaired motion prompts, only for saved confirmed jobs. No automatic confirmation, extra retry or policy override. docs/reports/flow-fictional-306.md.

รุ่น Runtime `0.15.305`: Gemini image download recovery via exact rendered URL in owned tab, then page fetch; no Generate/refresh. Same-turn proof may refresh saved URL on resume. Read docs/reports/gemini-download-305.md.

รุ่น Runtime `0.15.304`: Gemini Story missing-Send pre-dispatch checkpoint supports one same-tab reload; exact current user owns acceptance and image selection. Unknown legacy receipts remain review. Read docs/reports/gemini-reload-304.md.

รุ่น Runtime `0.15.303`: one durable same-image motion content recheck for exact owned needs_review/reference_compatible flags. Never override flags; require validated answer before Flow. See docs/reports/flow-content-recheck-303.md.

รุ่น Runtime `0.15.302`: Gemini completed learning-image/guideline reply → existing scene helper (same provider, bounded2 rounds), including saved no-image resume. Read docs/reports/gemini-scene-repair-302.md. No changes to successful Product/Flow dispatch.

Desktop smooth-flow-motion-1: voice-fit Flow composition uses continuous retiming instead of cloned-frame holds. Read docs/reports/smooth-flow-composition.md; Extension301 unchanged, installed EXE render pending.

รุ่น Runtime `0.15.301`: Gemini historical comparison264/287 vs300; exact completed D379C1 capability-only phrase now reaches existing bounded JSON repair. No Send/motion/Flow/name-validation bypass. Read docs/reports/gemini-comparison-301.md. Installed301 pending.

รุ่น Runtime `0.15.300`: ChatGPT motion-only complete typed JSON may pass to existing desktop review/save after60s unchanged despite stale Stop. Exact current request/job/index/context; no Stop/Send/reset. Initial and resume paths covered; generic analysis and Gemini still wait. See docs/reports/motion-stale-stop-300.md. Installed smoke pending.

รุ่น Runtime `0.15.299`: Story image waits must not press Stop merely because the DOM is quiet. A47CA3 scene10 proved the old3min Stop stranded awaiting_result. Preserve receipts, never resend unknown requests. See docs/reports/story-passive-wait-299.md; installed smoke pending.

รุ่น Runtime `0.15.298`: Flow settings keyDown now includes text/unmodifiedText; raw-CDP fixture reproduces297 failure and verifies298. Explicit menu-open proof precedes setting availability. Read docs/reports/flow-settings-key-input-298.md. Do not alter normal Send/Generate.

รุ่น Runtime `0.15.297`: compact Flow form cleanup, explicit per-form reset to saved defaults, preserved queue snapshots. Removed unused ATTACH drag/drop helpers; no Send/Generate changes. See docs/reports/flow-cleanup-297.md. Installed297 E2E pending.

รุ่น Runtime `0.15.296`: mandatory mobile Flow; removed display selector across all panels. UI and Python normalize display=compact; Extension enforces mobile even for legacy packets. Model/type/resolution/duration preserved. See docs/reports/flow-mobile-default-296.md. Earlier display-choice contracts below are superseded.

รุ่น Runtime `0.15.295`: mobile Start-frame attachment, exact existing filename and current job/shot. Read docs/reports/flow-start-frame-295.md. Live manual Start→asset verified, selected720p/10s and retained400x802; installed295 E2E pending. Older runtime labels below are historical.

รุ่น Runtime `0.15.294` — persistent mobile Flow candidate; installed E2E pending. See docs/reports/flow-persistent-mobile-294.md. Compact now means mobile throughout the Flow tab lifetime, not settings-only. Start before reference upload; retain debugger across subsequent operations, release on leaving Flow/closing tab. Other providers unchanged.

293: live read command failed while chrome://extensions was selected although a single Flow project was open. Prefer selected Flow project; otherwise select the sole open Flow project, never guess among multiple projects. See docs/reports/extension-targeted-test-293.md. Existing settings/Generate/AI Send logic unchanged.

Desktop UI3: all five user-account models available before discovery, with live-verified model-specific resolution/duration and both reference types. Read docs/reports/flow-five-models.md. Real desktop→installed Extension→Flow→desktop discovery CMD-ED79B0169C completed with all five names; this is not a paid-generation E2E. Extension code remains292; exact model-selection regressions cover all five at400/1365 widths.

292: use scoped keyboard controls when display=compact even if the user's viewport is already narrow;291 incorrectly limited this to overrides owned by SmartFlow. Read back selected values with bounded settling, no repeated click. Live browser controls verified without Generate; not an installed292 end-to-end test. See docs/reports/flow-settings-292.md.

Desktop UI revision `flow-precreate-controls-2` fixes empty dropdowns: direct per-job editing and evidence-backed initial model/resolution/duration choices, verified again by the existing Extension291. Read docs/reports/flow-precreate-controls-2.md before UI changes; earlier mandatory-discovery UI is superseded.

อ่าน docs/reports/flow-compact-291.md ก่อนแก้ Flow settings: Thai/English controls, fixed resolution, temporary compact settings lease with restore before ACK, automatic menu discovery, context-dependent options. Aspect remains tied to job type; arbitrary aspect and full-run mobile are NOT delivered. Earlier290 cover rules remain.

Runtime290: ปก AI ทำหลังบันทึกวิดีโอ ใช้ผู้ให้บริการเดิมและรูปจริงหนึ่งรูป งานปกแยกสถานะจากวิดีโอ ค่าหายจากงานเก่าแปลว่าปิด อ่าน docs/reports/ai-cover-290.md, core/ai_cover.py, ui/ai_cover.py และ tests/test_ai_cover.py ก่อนแก้ ไม่เปลี่ยน Send เดิมของงานอื่น รุ่นติดตั้งจริงยังรอตรวจ

รุ่น Runtime `0.15.289`: Gemini text Send → fresh exact user-turn proof → owned answer. One guarded retry only after60s unchanged full-release failure; durable budget survives new runs. Local canonical-ID name binding and desktop no-restart-on-uncertain-wait. Route docs/reports/gemini-text-send-289.md, tests/test_gemini_text_send_retry.py, tests/test_story_canonical_id_binding.py. Preserve image/ChatGPT/Flow; installed smoke pending.

รุ่น Runtime `0.15.288`: Flow settings UI → immutable jobs/queue/series → verified web controls. See docs/reports/flow-settings-288.md. Preserve Gemini287 ownership and all Send/receipt paths. Mobile remains gated, not proven.

รุ่น Runtime `0.15.287`: Gemini motion request/answer ownership. Route docs/reports/gemini-motion-owner-287.md, tests/test_gemini_motion_ownership.py. No unknown-send retry; do not clear A03A20 receipt or send its draft automatically.

รุ่น Runtime `0.15.286`: verified Flow settings; route docs/reports/flow-settings-286.md and tests/test_flow_video_settings.py. No forced mobile mode, no automatic model/duration/resolution change.

รุ่น Runtime `0.15.285`: Gemini motion capability recovery; docs/reports/gemini-motion-capability-285.md. Preserve existing image/Flow paths.

รุ่น Runtime `0.15.284`: Gemini optional discovery popup; docs/reports/gemini-discovery-284.md.

Current284: dismiss only visible Gemini discovery-card-dialog Personal Intelligence via exact Thai Later text and dismiss aria-label, once per DOM card during active non-cancelled jobs. Hook composer wait and existing polling sleep; no consent, Send, attachment, Flow or receipt logic changes. See docs/reports/gemini-discovery-284.md. Installed smoke pending; never reload an active job.

รุ่น Runtime `0.15.283`: motion schema validation and saved-answer recovery. See PROGRAM_BLUEPRINT current283. No live resume yet.

รุ่น Runtime `0.15.282`: live-DOM Gemini composer attachment scope fix; see PROGRAM_BLUEPRINT current282.

รุ่น Runtime `0.15.281`: Gemini strict attachment proof and motion preparation lifecycle. See PROGRAM_BLUEPRINT current281. Preserve old requested records; installed smoke pending.

รุ่น Runtime `0.15.280`: stability phase1; content-bound prompts, motion wait, cancellable composition, bounded JSON formatting. Route docs/reports/stability-280/SUMMARY.md. Earlier versions below are history.

รุ่น Runtime `0.15.279`: พรอมต์วิดีโอสั้นจากผู้สร้างภาพเดิม พร้อมภาพอ้างอิงจริงและคำยืนยันตัวละครสมมติ อ่าน docs/FLOW_MOTION_PROVIDER_PLAN_279.md ก่อนแก้ส่วนนี้ รุ่นก่อนด้านล่างเป็นประวัติ

รุ่น Runtime `0.15.278`: Flow video-only recovery; route PROGRAM_BLUEPRINT current278. Old fallback rules below are historical.


Desktop drama-series-start-1: missing queued EP start control, scoped per-series execution. Route PROGRAM_BLUEPRINT Drama per-series start; core/story_queue.py selector/resume, core/creation_queue.py global resume, ui/creation_queue.py action, main_window scheduler candidate, app.js card/modal. Extension277 unchanged.

รุ่น Runtime `0.15.277`: Flow restart result recovery, paired desktop277. Supersedes same-version276 hotfix below; use deliverables/SmartFlow_AI_Extension_0.15.277.zip. Every future delivered Extension change must bump manifest/desktop contract; no same-version hotfix delivery.

Flow cancel/reopen result recovery: PROGRAM_BLUEPRINT "Flow restart result recovery", background.js closeAutomationBrowser, flow.js resumeSubmittedCheckpoint; tests/flow_restart_checkpoint_harness.js.276 helper build20260909.2 source hotfix; existing release ZIP unchanged, installed smoke pending. Do not clear paid-send history or regenerate a submitted shot to recover a download.

รุ่น Runtime `0.15.276`: route Flow refusal/helper to PROGRAM_BLUEPRINT Flow prompt recovery, flow.js recoverFlowPolicy, background.js storyRepairMessage flow scope + CLICK_FLOW_GENERATE repair receipts, bridge flow-recovery audit. Tests flow_prompt_repair_harness/test_flow_prompt_repair, existing Flow snapshot/target/collector. Old queue/Send paths unchanged. Installed E2E pending.

รุ่น Runtime `0.15.275`: scene prompt helper. Route PROGRAM_BLUEPRINT Scene prompt helper; chatgpt.js generateStoryImageWithRepair/runSceneRepairHelper; background.js storyRepairMessage/isStoryRepairSendOwner; core/story_prompt_recovery.py and paired bridge. Tests story_image_receipt_harness, story_repair_background_harness, test_story_prompt_recovery. Installed E2E pending.

รุ่น Runtime `0.15.274`: user-authorized continuous confirmed Story ChatGPT service-error recovery with same prompt, cancellable backoff, old owned-reply reinspection. Route PROGRAM_BLUEPRINT Continuous Story service recovery. Supersedes273 one-retry cap, not unknown-send protection.

รุ่น Runtime `0.15.273`: Story Thai service-error recovery, paired desktop and helper build identifiers.

Current273: Story Thai service failure; route PROGRAM_BLUEPRINT matching section, chatgpt.js submitImagePrompt/confirmedStoryImageServiceError/storyImageNoResultReady, tests/story_image_receipt_harness.js. Do not reset old truncated receipts. Product/Gemini/Flow unchanged.

Current desktop audio-choices-1: audio selection BEFORE create/queue across Product/Story/Drama/Long/batch; core/media_audio.py, web_ui/media_audio.js, MainWindow workers/composers, CreationQueueMixin snapshots, StoryFinisher. Read PROGRAM_BLUEPRINT Pre-create audio choices and docs/reports/audio-choices-1/VALIDATION.md. Extension272 unchanged; optional speech uses existing video_prompt transport. Earlier phase1 scope below is historical.

Native audio phase1: Storyboard local saved-clip export only; core/flow_native_audio.py, ui/flow_native_audio.py, web_ui/studio.js. Read PROGRAM_BLUEPRINT Native Flow audio and docs/reports/native-audio-1/VALIDATION.md. New-job/queue audio settings and Extension speech prompts remain pending; do not claim complete.

รุ่น Runtime `0.15.272`: optional short-hook cover metadata + local non-destructive cover editor. Start at PROGRAM_BLUEPRINT “Short-hook cover / 0.15.272”; docs/reports/clip-cover-272/VALIDATION.md. Existing271 image-receipt behavior preserved. Earlier runtime labels are historical.

Desktop library-compact-1: route video-library UX to PROGRAM_BLUEPRINT “Compact video library”; core/video_library.py, desktop summary/detail/media routes, web_ui/library_view.js/library.css + app.js. No Extension changes. Report docs/reports/library-compact-1/VALIDATION.md.

รุ่น Runtime `0.15.270`: long-video sidebar and paired Extension. Route: docs/LONG_VIDEO_IMPLEMENTATION_STATUS.md; core/long_video.py, story_manager.py, local_bridge.py, ui/main_window.py, browser_extension/chatgpt.js + flow.js + background.js. Older versions below are history.

รุ่น Runtime `0.15.269`: bounded Story ChatGPT service-error retry. Read current PROGRAM_BLUEPRINT section; durable one-retry budget, exact complete service error only. Legacy receipts without response evidence remain review.

รุ่น Runtime `0.15.268` — Candidate: activity-based analysis wait. Read PROGRAM_BLUEPRINT "Activity-based analysis wait / 0.15.268" and docs/reports/analysis-active-wait-20260907/VALIDATION.md. Six-minute inactivity only; never time out active Stop or evolving answer. Preserve no-resend, completion, Flow and Send paths.

Desktop drama-voice-fit-1: read docs/DRAMA_VOICE_FIT_2026-09-07.md for saved Drama render settings, queue-only creation and narration-fit composition. Extension remains267; EXE smoke pending. Existing user finals untouched.

Current267: Gemini analysis capability disclaimer repair. Route PROGRAM_BLUEPRINT "Gemini analysis capability / 0.15.267", chatgpt.js geminiAnalysisCapabilityOnly/parseOrRepairAnalysis, tests/story_style_extension_harness.js and docs/reports/gemini-analysis-capability-20260907/VALIDATION.md. Keep existing JSON repair prompt, Send/image and Flow behaviors.

Current266: Flow failure popup. Route PROGRAM_BLUEPRINT "Flow failure popup / 0.15.266"; flow.js card reason/classification, core/local_bridge.py reason transport, ui/main_window.py notice and web_ui dialog. Reuse docs/reports/flow-failure-popup-20260907/VALIDATION.md before broad scans. Keep265 current-card/queue and all successful Send/image/fallback paths.

Current265: Story Flow policy handoff; route PROGRAM_BLUEPRINT "Story Flow policy handoff / 0.15.265", flow.js readGenerationState/currentStoryFailureCard/observeStoryPolicyCard/ownedStoryPolicyTerminal and _collect_story_flow_clips initial inspection. Tests flow_snapshot_harness.js (actual complete reader) and test_story_flow_contract.py (scene2 policy→fresh scene3). Report docs/reports/story-flow-policy-20260907/VALIDATION.md. Do not change successful264 Product, AI Send/images, image-motion or normal queue behavior. Older current labels below are history.

Current runtime264: route analysis/6-minute timeout bugs to PROGRAM_BLUEPRINT "Analysis completion / 0.15.264" and docs/reports/analysis-completion-20260907/VALIDATION.md. Read those and the focused tests before comparing archives again. The proven desktop resend loop is stopped; answer-body stability fix is fixture-tested, not yet verified on the exact failing browser DOM. Preserve shared Send/image/Gemini retry/Flow/queue contracts. Older current labels below are history.

Current runtime263 Candidate: confirmed Story image refusal can use an acknowledged previous illustration locally, only non-Drama image_motion. Inspect PROGRAM_BLUEPRINT "Story confirmed refusal local reuse", core/story_manager.py, chatgpt.js receipt/fallback path, background.js owned checkpoint handler and bridge. Do not retry a refusal or weaken unknown-send/Flow gates. Extension and desktop263 must match; reload existing install, do not uninstall receipt storage. Report docs/reports/story-refusal-local-20260907/VALIDATION.md. Older262 version sections are history.

Presenter library UI revision `presenter-library-1`: compact cards, one detail player, filters and recoverable metadata trash. Inspect PROGRAM_BLUEPRINT "Presenter library" and tests/test_presenter_library.py first. No generation/Extension changes and no physical deletion of user assets.

Desktop status update 2026-09-07: Product image→voice→Flow remains serial. User requested explicit voice waiting/queue/download/reused/ready status, not preloading Flow. Route to PROGRAM_BLUEPRINT `product-handoff-status-1`, `ui/main_window.py:_prepare_product_narration`, `tests/test_product_handoff_status.py`. Extension unchanged262; no reinstall.

รุ่น Runtime `0.15.267` — Candidate คู่โปรแกรม267; ยังต้องยืนยัน installed Gemini analysis repair E2E ไม่ใช่ Golden.

Current262: PROGRAM_BLUEPRINT “Gemini image Send / 0.15.262”. User authorizes a single additional Gemini image click only after completed release, full60s observation and unchanged exact draft/history/image/owner state. Durable one-retry claim and final pre-press guard; no third click or re-upload. Shared Send/analysis and ChatGPT unchanged. No automatic old receipt reset/resume. Tests gemini_image_send_retry_harness.js/test_gemini_image_send_retry.py; report docs/reports/gemini-image-send-20260907/VALIDATION.md. Prior current blocks below are history.

Current261: route to PROGRAM_BLUEPRINT “Flow Generate target / 0.15.261”. Only pre-press target/focus/hit-test and uncertain-send no-retry boundaries changed. High demand/queued work still waits in the same project as before; do not change that into errors or refreshes. Actual-source33 simulation cases; report docs/reports/flow-generate-target-20260907/VALIDATION.md. No customer receipt wipe, old Job mutation or Codex-controlled provider send. Prior current blocks below are history.

Current260: begin at PROGRAM_BLUEPRINT “Receipt storage / 0.15.260”. Reproduce259 false receipt ACK using key-sorted storage, compare exact values without object order, keep answered AI tabs on owned review errors. Legacy recovery is only a desktop trace-proven259 pre-send first-image claim; never clear uncertain submissions. Files chatgpt.js, core/story_receipt_recovery.py, StoryManager package, Story error preservation; tests/report docs/reports/receipt-storage-20260906/VALIDATION.md. Earlier version blocks below are history.

Current runtime **0.15.259 Candidate**: checkpoint-first resume fixes. Read PROGRAM_BLUEPRINT “Checkpoint resume / 0.15.259” and docs/reports/checkpoint-resume-20260906/VALIDATION.md. Presenter pause is NOT legacy Flow reset; keep submit evidence, require stop ACK + fresh inspection command ID, only proven pre-submit same-project continuation. Story package/manual/auto resume share validated saved analysis; unreadable/generated-but-not-downloaded images never become missing slots. Image receipt guards and receiver run ownership are required. Install259 with matching desktop and idle EXE restart. All version labels below are history; no whole-file restoration.

Current runtime **0.15.258 Candidate**: แก้ Story bilingual display-name false mismatch ทั้ง core/story_content.py และ browser_extension/chatgpt.js. อ่าน PROGRAM_BLUEPRINT หัวข้อ Story bilingual names และ regression12.4; ชื่อไทย (Latin Proper Name) ใช้ได้เฉพาะ spelling ที่ประกาศอยู่แล้วและไม่ชนตัวตนอื่น ไม่อนุมานเพิ่มสำหรับ user anchors. คง Send/Flow/timeout/retry. คู่โปรแกรม258 ติดตั้งแล้วเปิด SmartFlow AI.exe ใหม่เมื่อ idle. รายงาน docs/reports/story-bilingual-names-20260906/VALIDATION.md; รอ installed smoke. ข้อความรุ่น257และรุ่นก่อนหน้าด้านล่างเป็นประวัติ ไม่ใช่รุ่นติดตั้งล่าสุด.

Desktop 2026-09-06 / presenter-queue-3: ตัวเลือกผู้บรรยายใน modal Story batch และคิวสินค้า; `enqueue_story_batch` ต้องผ่าน presenterPayload ด้วย ไม่ใช่เฉพาะ create_story/creation_enqueue. เริ่มอ่าน PROGRAM_BLUEPRINT หัวข้อ Presenter queue choices และ tests/presenter_queue_ui_harness.js; Extension257คงเดิม ไม่แก้คิวเก่าย้อนหลัง

Desktop 2026-09-06: ตั้งค่าผู้บรรยายที่เดียวแล้วติ๊กใช้ Product/Story + dialogสถานะเดิม รองรับ `presenter_progress`; Extension257ไม่เปลี่ยน เริ่มอ่าน PROGRAM_BLUEPRINT ส่วน `Presenter settings/progress` และ tests/test_presenter_settings_progress.py ก่อนแก้ จุดเก็บ defaults เป็น user data ไม่ใช่ cache ต้องรักษา Job/queue snapshot เดิมเสมอ

Previous runtime **0.15.257 Candidate**: reusable silent presenter. Read PROGRAM_BLUEPRINT.md section “Presenter Studio / 0.15.257”. Modules core/presenter.py, core/presenter_pipeline.py, ui/presenter.py, web_ui/presenter.js/css; bridge routes /api/presenters/* and mode=presenter in the existing Extension. Product/Story queue snapshots store optional presenter settings. No lip-sync or new voice API; existing browser gestures unchanged. Install257 and restart SmartFlow AI.exe only when idle. Validation: docs/reports/presenter-20260906/VALIDATION.md. Installed E2E pending.

Previous runtime **0.15.256 Candidate**: แก้ Story/Drama แผนใหม่ที่คำบรรยายมีตัวตนอยู่แล้วแต่ขาดชื่อ ใช้คำถามตรวจข้อความหนึ่งครั้งแล้วเติมชื่อกำกับวลีเดิมในเครื่อง ตรวจโครงสร้างเดิมและบันทึกหลักฐานก่อนเริ่มภาพ ไม่เปลี่ยนบทหรือแผนทั้งชุด ไม่ซ่อมอัตโนมัติเมื่อเป็นชื่อที่ผู้ใช้กำหนด/แผนที่รีวิวแล้ว/มีภาพแล้ว/ส่งไม่แน่นอน. คงพรอมต์ภาพกระชับ255และ Product/Send/Flow. ติดตั้ง256คู่โปรแกรมแล้วเปิด SmartFlow AI.exe ใหม่เมื่อ idle. ยังรอ installed E2E; รายงาน docs/reports/story-name-binding-20260906/VALIDATION.md

Previous runtime **0.15.254 Candidate**: Story/Drama ไม่มีรูปตั้งต้นใช้คำสั่งสร้างภาพใหม่จากข้อความแบบครบทุกฉาก คงเนื้อเรื่อง/สไตล์เดิม ไม่ขอภาพก่อนหน้าที่ไม่มีอยู่ เพิ่ม image_prompt_ready บันทึกพรอมต์จริงและช่องพิมพ์/สถานะก่อนส่งลง Job log พร้อม ACK หากบันทึกไม่ได้หรือพบรูปค้างในช่อง ChatGPT จะหยุดก่อนส่ง ไม่ retry. Product/Story มีรูป/physical Send/Flow คงเดิม คู่โปรแกรม254 เปิด EXE ใหม่เมื่อ idle; ยังรอ installed smoke รายงาน docs/reports/story-text-image-audit-20260906/VALIDATION.md

Previous runtime **0.15.252 Candidate**: Story/Drama source รูปหลัก optional ไม่ใช่รูปฉากก่อนหน้า ฉาก1เริ่มสร้างจากข้อความ; ทุกฉากต้อง self-contained ใช้ text identity/visual bible โดยไม่บังคับไฟล์ภาพที่ไม่มี. AI ขอโหลดย้ำเป็น STORY_REFERENCE_REQUIRED หยุด ไม่ retry หรือ desktop auto recovery; policy มี priority เดิม. Source: core/story_manager.py, core/story_pipeline.py, browser_extension/chatgpt.js; attach/Send/Flow ไม่เปลี่ยน. ผลเทส/แพ็ก CURRENT_RELEASE.json และ docs/reports/story-reference-20260906/VALIDATION.md ติดตั้ง252คู่โปรแกรมแล้วเปิด EXE ใหม่เมื่อ idle; ยังไม่ยืนยัน installed E2E

Previous runtime **0.15.251 Candidate**: Story image refusal แยกจาก Send failure; ไม่ส่งซ้ำอัตโนมัติ ภาพใช้ visual plan/non-graphic depiction แยก raw narration. Storyboard บันทึก Prompt ที่ผู้ใช้แก้เฉพาะ missing scene ของงาน stopped/unpaid, revision+audit+override กัน stale callback; ไม่เริ่มสร้างจนผู้ใช้กดทำต่อ. Manual resume ใช้ saved analysis แม้ภาพ0ฉาก. Flow/trusted Send/Voice ไม่เปลี่ยน เริ่มที่ core/story_manager.py, core/story_content.py, core/studio_review.py, web_ui/studio.js, browser_extension/chatgpt.js และรายงาน docs/reports/story-depiction-20260906-66493F/VALIDATION.md. CURRENT_RELEASE.json ระบุผลเทส/แพ็ก ติดตั้ง251คู่โปรแกรมและเปิด EXE ใหม่เมื่อ idle; ยังไม่ยืนยัน installed smoke

Previous runtime **0.15.250 Candidate**: Story/Drama visual medium แยกจากเนื้อเรื่องและตัวละคร งานใหม่มี story_content_contract + registry และ mapping รายฉาก; Core/Extension ตรวจความครบ/ชื่อก่อนภาพ ไม่สร้างตัวละครใหม่แทนเมื่อเว็บปฏิเสธ ไม่เปลี่ยนเหตุการณ์ตอนแก้ภาพซ้ำ Storyboard แสดงผลตรวจแบบอ่านอย่างเดียว งานเก่าคง checkpoint/ภาพ/เสียงเดิม ผล gate อ้าง CURRENT_RELEASE.json และ docs/reports/story-content-style-20260905/VALIDATION.md ต้องติดตั้ง Extension250 และเปิด EXE ใหม่เมื่อ idle; ยังไม่อ้าง installed visual E2E

Previous runtime **0.15.249 Candidate**: แก้ AI Send lifecycle แบบจำกัด—focus ก่อน press, ตรวจ node/ตำแหน่ง/draft หลัง hover, owner+single-flight, gesture capture ที่ไม่ทิ้งหลักฐาน release หลุดปุ่ม และ Bridge รองรับ diagnostics คู่รุ่น. Installer ตรวจ version ของ canonical browser_extension เทียบ release/desktop ก่อนบอกโฟลเดอร์ ไม่ชี้ .244 เก่า. คงงานภาพ248 และ Voice แบ่ง2,000ตัวอักษรทั้งหมด; ไม่แก้ Flow gestures. Installed E2E ยังไม่ผ่านการยืนยัน อ่าน `docs/reports/ai-send-20260905-16F867/VALIDATION.md`; ต้องติดตั้ง249และเปิด EXE ใหม่เมื่อไม่มีงานรัน ประวัติด้านล่างห้ามนำมาทับ source.

Current runtime delta **0.15.245 Candidate**: คำสั่งผู้ใช้ล่าสุดให้ใช้รูปเดิมประกอบคลิปเมื่อแนบเข้า Flow ไม่ผ่านด้วย (ไม่ใช่เฉพาะ policy) เพิ่ม terminal `FLOW_ATTACHMENT_UNCONFIRMED` หลังตรวจแบบอ่านอย่างเดียว 30 วินาทีและ latch ห้ามส่งต่อ เมื่อยังไม่มี submission/queue/render/result/approval เท่านั้น Desktop ใช้ checkpoint แยกเหตุผลแล้วเดินรูปถัดไป Product/Story/Drama ดู `docs/reports/attachment-fallback-20260905/VALIDATION.md`; ต้องติดตั้ง Extension ใหม่และเปิดโปรแกรม EXE ใหม่ ข้อความ “Extension ไม่เปลี่ยน” ด้านล่างเป็นประวัติของงานคิวก่อนรุ่นนี้

Current desktop delta (2026-09-05): คิวสร้างคลิปร่วมสินค้า/Story ใช้ `core/creation_queue.py`, `ui/creation_queue.py`, `web_ui/creation_queue.js/.css` และ store `story_batch_queue.json` เดิม รวม 14 หน้าแล้ว แผน/ขอบเขต: `docs/design/CREATION_QUEUE_20260905.md` ผลตรวจ: `docs/reports/creation-queue-20260905/VALIDATION.md` ไม่ได้แก้/แพ็ก Extension ใหม่ ใช้ 0.15.244 เดิม

Current delta 2026-09-05 / Runtime **0.15.244 Candidate**: แก้ workflow จริงทั้ง Extension/Bridge/Desktop เรื่อง heartbeat, ACK receipt, download identity, cancel ownership, late AI callback, next-shot และ compatible-client selection; physical Flow actions คงเดิม เริ่มที่ `docs/design/WORKFLOW_RELIABILITY_20260905.md` และ `docs/reports/workflow-20260905/VALIDATION.md` ตรวจผล/แพ็กใน CURRENT_RELEASE.json ก่อนบอกผู้ใช้ว่าติดตั้งตัวไหน

Desktop phase 2 (2026-09-05): `core/studio_review.py`, `web_ui/studio.js`, `studio.css` เพิ่ม Storyboard/คำอ่านรายงาน + Dashboard งานปัจจุบัน + Log filters/compact logs; ไม่แก้ Flow/Extension และไม่ออกแพ็กใหม่ ใช้ 0.15.243 เดิม อ่าน PROGRAM_BLUEPRINT หัวข้อ Studio review delta ก่อนแก้

Previous delta 2026-09-05: รุ่น `0.15.243` เพิ่ม `core/story_styles.py` (Job/Batch/Series style → Extension image prompt), `core/subtitle_preview.py` (single worker + latest pending + small state + token media), CTA repair/คำอ่านร่วมเสียงและซับ ดูแผน UX/UI ทั้ง 13 หน้าและสิ่งที่ลงมือจริงใน `docs/design/UX_UI_STABILITY_PLAN_20260905.md` ไม่ใช้เอกสาร Tk รุ่นเก่าเป็นแบบหน้าจอปัจจุบัน

อ่าน `CURRENT_RELEASE.json` และ `PROJECT_STATE.md` ก่อนเสมอ เอกสารสองไฟล์นี้เป็นตัวแยก “Runtime ปัจจุบัน”, “Golden ที่พิสูจน์แล้ว” และ “รุ่นทดลอง/รุ่นที่ห้ามย้อนกลับ” หากข้อมูลประวัติขัดกับสัญญาปัจจุบัน ให้ยึด Source + Tests + CURRENT_RELEASE ตามลำดับ ห้ามคัดลอกไฟล์ทั้งก้อนจากรุ่นเก่ามาทับรุ่นปัจจุบัน

อ่านไฟล์นี้ก่อนทุกงาน แล้วเปิดเฉพาะหัวข้อที่ตรงงานใน `PROGRAM_BLUEPRINT.md` ผ่าน `rg` ห้ามอ่าน source/พิมพ์เขียวฉบับเต็มโดยไม่มีเหตุจำเป็น

งานเกี่ยวกับ Chrome Extension ให้เริ่มจาก `EXTENSION_BLUEPRINT.md` ซึ่งสรุปส่วนประกอบ State machine กฎก่อนกดสร้าง Tab ownership Recovery และ Test matrix ของ Extension โดยเฉพาะ แล้วจึงเปิด Source เฉพาะไฟล์ที่หัวข้อ 13 ระบุ

## ตัวตนระบบ

- โปรแกรม: SmartFlow AI — AI Clip Creator
- Root: `C:\Users\keera\Desktop\Shopee_Android_AutoPost`
- UI: Hybrid HTML/CSS/JS (`web_ui/`) บน pywebview/WebView2
- Engine: Python/Tk ที่ซ่อน (`ui/main_window.py`)
- Bridge: `127.0.0.1:8765` (`core/local_bridge.py`)
- Extension: `browser_extension/` รุ่น Runtime `0.15.267` (สถานะ Candidate รอการทดสอบจริงหลังติดตั้ง); รุ่น Golden `0.15.112` จาก Git `afcb918`

AI Web attach/send รุ่น `0.15.229`: ChatGPT ต้องเปิดเมนู Composer “เพิ่มไฟล์และอื่นๆ” และเลือกช่องอัปโหลดภาพปัจจุบัน จากนั้นต้องตรวจพบ thumbnail/attachment ของรูปอ้างอิงครบใน Composer ก่อนใส่ Prompt และกดส่ง หากพิสูจน์ไม่ได้ให้หยุดโดยไม่ส่ง Prompt; กฎ Gemini `0.15.216` เรื่องใช้รูปเดิมและห้ามแนบซ้ำยังคงเดิม

Google Flow รุ่น `0.15.230`: รูปอัปโหลดครบ 100% ต้องถูกเลือกเข้า Composer ในหน้าเดิมทันที ห้ามรีเฟรชหลังอัปโหลดและห้ามอัปโหลดซ้ำ การรีเฟรชผลลัพธ์ใช้ได้เฉพาะวิดีโอเรนเดอร์ 100% แต่ยังไม่ปรากฏวิดีโอที่เล่นได้

Google Flow รุ่น `0.15.231`: หลัง Flow รีเรนเดอร์จากการเลือก asset/ตั้งค่า ต้องตรวจ Prompt สดจาก Composer และกรอกใหม่เฉพาะ Prompt หากหาย รอปุ่มสร้าง Enabled จริงก่อนรายงานพร้อม และจับ error “Agent ทำงานไม่สำเร็จ” ทันทีโดยไม่รอ timeout 75–90 วินาที
Google Flow รุ่น `0.15.232`: เมื่ออัปโหลดครบ 100% แต่ Angular ยังไม่วาดการ์ดรูป ให้รอการ์ดเดิมในหน้าเดิมแบบอ่านอย่างเดียวก่อนเปิด “ทำให้เคลื่อนไหว” ห้ามรีเฟรชหรืออัปโหลดซ้ำ
Google Flow รุ่น `0.15.233`: ปิดเฉพาะเมนูอัปโหลดที่ยังลอยค้างด้วย Escape หนึ่งครั้ง และตรวจจุดคลิกว่าชนปุ่มสามจุดจริงก่อนกด; ห้ามเปิดการ์ดรูป/Nano Banana editor และหากเกิดขึ้นให้หยุดโดยไม่เปิดโปรเจกต์หรืออัปโหลดซ้ำ
Google Flow รุ่น `0.15.234`: หลังอัปโหลดให้เปิดเมนูของการ์ดรูปและกด `ทำให้เคลื่อนไหว` เพียงครั้งเดียว จากนั้น Flow จะใส่รูปเข้า Composer เอง; ตรวจ thumbnail จาก `aria-label=องค์ประกอบ`, alt `รูปภาพองค์ประกอบ` และ `flow-content.google/image/` โดยไม่เปิดเมนู `+` ไม่เลือกโปรเจกต์ และไม่เลือกรูปซ้ำ ทุก transition และ physical action สำคัญถูกบันทึกใน Log โปรแกรมและ `extension_trace.jsonl`
Google Flow รุ่น `0.15.236`: ก่อนคลิก `ทำให้เคลื่อนไหว` ต้องรอ semantic target นิ่ง, hover, resolve/hit-test ซ้ำ แล้ว press/release เพียงครั้งเดียว ต้องตรวจ postcondition ก่อนรายงานว่าคลิกสำเร็จ; ถ้า Flow ไม่รับให้ safe-stop ทันที โปรแกรมต้องไม่รายงานว่าเรนเดอร์และห้ามเปิดโปรเจกต์/อัปโหลดซ้ำ
Gemini วิเคราะห์สินค้ารุ่น `0.15.237`: Master Prompt ต้องระบุชัดว่าเป็นงานเขียน JSON เท่านั้น ไม่ได้ขอให้ Gemini สร้างรูปหรือวิดีโอ หาก Gemini ตอบปฏิเสธ/อ้างว่าเป็นโมเดลภาษา ให้ส่ง Prompt วิเคราะห์ใหม่แบบข้อความล้วน ไม่ใช้คำสั่ง “จัดรูปแบบคำตอบเดิม” เพราะคำตอบเดิมไม่มีข้อมูล และต้องใส่ข้อความผ่าน editor input path ก่อน trusted click หนึ่งครั้งเพื่อไม่ให้ Prompt ค้างใน Composer

Gemini Composer รุ่น `0.15.238`: งานจริง `JOB-20260904-84A00F` พิสูจน์ว่า multiline input เหลือเพียงบรรทัดแรก 113 ตัวอักษร แต่ single-line normalized input ผ่านครบ 2,069/2,069 และ Gemini ตอบ JSON ได้ จึงต้อง flatten เฉพาะ whitespace จริง, ตรวจ exact จาก live Composer สองรอบ, fallback CDP ได้หนึ่งครั้ง, ห้ามแนบรูปซ้ำ และ Background ต้องตรวจ exact อีกครั้งก่อนคลิกส่ง
Gemini JSON recovery รุ่น `0.15.239`: งานจริง `JOB-20260904-CD2A8C` พิสูจน์ว่าพรอมต์กู้คืนตอบ JSON ได้ แต่การส่งทันทีหลัง refusal เกิด race กับ DOM; ต้องรอ refusal และปุ่มส่งนิ่ง, นับเฉพาะ `user-query` ชั้นนอก, ตรวจตำแหน่งอีกครั้งหลังผูก Trusted click และบันทึกหลักฐานคลิก/รับข้อความแยกกัน โดยห้ามกดหรือแนบรูปซ้ำ

Flow policy/fallback รุ่น `0.15.242`: Extension ต้องยืนยันการปฏิเสธจากการ์ด Error ที่มองเห็นจริง โดยหลักฐาน Policy + ไม่หักเครดิต + ปุ่ม Retry ต้องอยู่ในการ์ดเดียวกันและ fingerprint ต้องใหม่กว่าก่อนส่ง; terminal `FLOW_POLICY_BLOCKED` ครั้งแรกทำให้ Product, Story และ Drama ใช้รูป canonical เดิมสร้าง local motion ของ slot/ฉากนั้นทันที แล้วเดิน source/scene ถัดไป ห้าม safe-prompt retry, reupload หรือ Alternate Take ข้อความเข้าคิว/กำลังสร้าง/ระบบไม่ว่าง/ข้อผิดพลาดชั่วคราวยังให้รอหรือกู้ใน Run เดิม และ Final ที่ผสมต้องระบุ source type พร้อมจำนวน Flow จริง/local แยกกัน
- รูป: ChatGPT Web หรือ Gemini Web ผ่าน Chrome Extension ไม่ใช้ API key และไม่ใช้ Codex ImageGen
- วิดีโอสินค้า: เส้นทางปกติคือ Google Flow ทีละรูป; slot ที่มี structured current-card policy terminal เท่านั้นใช้ local motion จากรูปเดิม Story เลือก `image_motion` (ค่าเริ่มต้น) หรือ `google_flow` ทีละฉาก และ Drama ที่เดินผ่าน Story `google_flow` ใช้กฎเดียวกัน
- Output: H.264 High + yuv420p + AAC
- Launcher ต้อง focus เฉพาะหน้าต่าง Hybrid ที่มองเห็น; Hidden Engine ใช้ชื่อแยกและห้ามถูกดึงขึ้นมาเป็นหน้า Legacy
- เมื่อ Launcher พบหน้าต่าง Hybrid เดิมต้อง focus แล้ว Refresh หน้า WebView ด้วย เพื่อไม่ให้ UI เก่าค้างหลัง Engine/HTML อัปเดต
- ไม่มีทางเข้า UI รุ่นเก่า: `SmartFlow AI.exe`, Shortcut และ `RUN.bat` เปิด Hybrid เท่านั้น; หาก WebView2 เปิดไม่ได้ให้แจ้ง error ห้าม fallback
- `SmartFlow AI.exe` และ `RUN.bat` ต้อง resolve Python ผ่าน `launcher/resolve_python.ps1` แหล่งเดียว; ห้ามใส่พาธ Python แบบตายตัวกลับเข้า Launcher
- JSON runtime หลักใช้ `core/atomic_json.py`: ห้ามเขียน `config.json`, queue หรือ manifest หลักด้วย `write_text()` ตรง และห้ามอ่าน JSON เสียแล้วคืนรายการว่าง เพราะจะทำให้งานหายจาก UI

## โฟลว์หลัก

```text
Affiliate: Shopee link → Product Job → AI Web 3 รูป/บท/แคปชั่น
→ Voice → Google Flow/local-motion ตามลำดับ 3 source slots → Edit → Subtitle → Logo/Audio → Library → Android

Story: หัวข้อ/รูปอ้างอิง → AI Web บท+ภาพหลายฉาก → Voice
→ ผู้ใช้เลือก Story renderer ในเครื่อง หรือ Google Flow ทีละฉาก
→ Subtitle/Logo/Audio → Library

Drama: Series + Character Bible → EP Queue ทีละตอน → Story engine เดิม
→ Plot Board ที่ล็อกไว้ + continuity validator + ธีมปกเดียวกัน → EP ถัดไป
→ ถ้า EP ล้มให้พักทั้งซีรีส์ กู้ EP เดิมก่อน แล้วจึงเดินคิวต่อ
```

ทุกโฟลว์ใช้ Checkpoint: สร้างต่อเฉพาะไฟล์/รูป/ช็อตที่ขาด ห้ามเริ่มใหม่ทั้ง Job และห้ามเรียก Voice ซ้ำถ้ามีไฟล์เสียงพร้อมแล้ว คำสั่ง Extension ทุกคำสั่งต้องผูก `run_id`; Product AI callback ต้องผูกทั้ง `run_id + attempt_id`; Flow clip ต้องผูก `ai_generation_id` ของรูปชุดเดียวกัน ผลจากรอบเก่าต้องถูกปฏิเสธ

Runtime `0.15.200` บังคับ Browser contract จริง: command ทุกตัวมี `run_id + lease_token + client_id`, Progress รับเฉพาะ owner tab/run และ Extension versionปัจจุบัน, Monitor Flow ทำงานแบบ single-flight ไม่ซ้อนกัน และ Browser-origin routes ใช้ Session capability `X-SmartFlow-Token` ที่หมุนใหม่ทุก Engine session โดยห้ามใส่ Token ใน URL, Status หรือ Log

Runtime `0.15.200` เพิ่มโครงสร้าง Extension แบบ modular ภายใต้ `browser_extension/src/` และ passive Google Flow result observer แบบอ่านอย่างเดียว ตัว observer ห้ามคลิก Reload Submit หรือ monkey-patch API ของหน้าเว็บ ใช้เป็นหลักฐานสำรองสำหรับค้นหาไฟล์วิดีโอหลังเส้นทางดาวน์โหลด Golden เท่านั้น

Provider lock: ChatGPT/Gemini ที่ผู้ใช้เลือกและบันทึกใน Job ต้องคงเดิมตลอด Resume/Recovery ห้ามสลับ provider อัตโนมัติแม้ JSON/ภาพล้มเหลว เว้นแต่ผู้ใช้สั่งเปลี่ยนเองอย่างชัดเจน

Product AI ต้องรับรูปแนวตั้งที่เปิดอ่านได้จริง แตกต่างกัน 3 รูปพอดี (ขั้นต่ำ 256×400, อัตราส่วนกว้าง/สูง 0.45–0.72) และบังคับ Product Identity Lock ตลอด 3 ช็อต: สินค้า สี รูปทรง โลโก้ บรรจุภัณฑ์ ฉากและแสงต้องต่อเนื่อง ส่วน CGI ใช้ได้เฉพาะคุณสมบัติที่เห็นหรือยืนยันจากข้อมูลสินค้าจริง ห้ามแต่งสเปกหรือสรรพคุณ

AI Voice: เมื่อ API ตอบ terminal error ต้องแสดง `detail`/`stage` จริง ไม่ย่อเหลือเพียง `error`; ทุก request ใช้ deterministic idempotency key และบันทึก remote `voice_job_id` ก่อน poll เพื่อ Resume คิวเดิมโดยไม่หักเครดิตซ้ำ ถ้าเป็นข้อผิดพลาดชั่วคราวชนิดเปิดไฟล์ WAV ไม่ได้ (`Error opening`/`System error`) ให้ submit เสียงใหม่อัตโนมัติได้อีกหนึ่งครั้งด้วย attempt key ใหม่ โดยคงรูป บท reference และ Checkpoint เดิมทั้งหมด ส่วน error ถาวรหรือยกเลิกห้าม Retry

หน้า Hybrid แสดงเครดิต AI Voice และ AI Subtitle จาก API จริงที่แถบบน หน้า Dashboard และหน้าบริการ: Voice ใช้ `/api/tts/external/status`, Subtitle ใช้ `/api/smartsub-online/v2/status`; หากไม่มี credential ต้องขึ้น `ยังไม่เชื่อม` และห้ามส่ง API Key/SOD กลับหน้าเว็บหรือ log

พรีวิวหน้า Subtitle ใช้ MP4 720×1280 จาก ASS/FFmpeg renderer เดียวกับ Final ผ่าน action `subtitle_preview_style` พร้อม PNG fallback; ห้ามใช้ข้อความ CSS จำลอง และฟอนต์ TTF/OTF ที่อัปโหลดต้องเก็บใน `assets/fonts/user/`

Product Subtitle ต้องใช้ `api_speech_intervals_v2`: คำจาก `spoken_script`, เวลา/ช่วงพูดจาก SmartSub raw SRT, รักษา `[pause:x]` และ lead 120 ms; ปุ่มทำต่อที่ค้าง Flow ต้องเปิด Chrome และ focus ช็อตแรกที่ขาดทันที

Google Flow: `flow_page_excerpt` ใช้เพื่อวินิจฉัยเท่านั้น ห้ามนำข้อความทั้งหน้ามาตัดสิน Failure โปรแกรมจะเปลี่ยนเป็น local motion ได้เฉพาะ structured `failure_code=FLOW_POLICY_BLOCKED` ที่ Extension สร้างจากการ์ดปัจจุบันซึ่งมีข้อความ Policy + ไม่หักเครดิต + Retry อยู่ในการ์ดเดียวกันและใหม่กว่า baseline; เมื่อรับครั้งแรกให้ใช้รูป canonical เดิมทำ local motion ทันทีและไป source/scene ถัดไป โดยห้ามส่ง Prompt/รูปนั้นกลับ Flow อีก หากมีหลักฐานคิว/กำลังสร้าง/ระบบไม่ว่าง/ข้อผิดพลาดชั่วคราวของรอบใหม่ให้รอต่อหรือกู้ Run เดิม ห้าม Reload, Upload หรือ Submit ซ้ำ

Google Flow Agent รุ่นปัจจุบันอาจแสดง `Considering Video Generation` พร้อมปุ่ม `Stop/หยุด` โดยไม่มีเปอร์เซ็นต์: ให้ถือว่าเรนเดอร์ทำงานจริง ไม่ใช่ `generation_status_unknown`; ถ้าไม่มีหลักฐานทำงานใดเลยให้ผูก Workspace เดิมใหม่ที่ประมาณ 30/60 วินาทีและเปิดโปรเจกต์ใหม่เฉพาะช็อตเมื่อครบ 90 วินาที ห้ามรอค้าง 52% ถึง timeout ใหญ่

Google Flow Golden rule: ใช้เส้นทาง `ready_to_generate → generation_started → awaiting_credit_approval → generation_complete → download` ของ Extension `0.15.112`; ห้ามเพิ่มการคลิก/Enter/React fallback ซ้อนหรือเปิดโปรเจกต์ใหม่เป็นวงรอบ เพราะเคยทำให้รูปและ Prompt ถูกส่งซ้ำโดยไม่จบงาน

Google Flow UI ปัจจุบันอยู่ที่ `https://flow.google.com/`: อัปโหลดเข้า `สื่อทั้งหมด` ไม่เท่ากับแนบใน Composer ต้องเปิด media selector ข้าง Prompt เลือก `selling_image_XX`/`flow-reference` และพิสูจน์ thumbnail ใน Composer ก่อนกดสร้าง Resume ของ Job+shot เดิมต้องใช้แท็บ `/project/` เดิมโดยไม่ Reload และห้ามเปิดแท็บใหม่เพียงเพราะ `prepare_incomplete`

Runtime `0.15.199` แก้ Flow upload/handoff โดยตรง: เมื่อ hidden file input อัปโหลดสำเร็จต้องตั้ง Reload guard และนัด Reload โปรเจกต์เดิมก่อนเขียน Diagnostics ห้ามอ้างตัวแปรนอก Scope; คำสั่ง `open_flow` ACK สำเร็จได้ต่อเมื่อพบและผูก `/project/` จริง และรับเฉพาะ Landing tab เดิมที่เปลี่ยน Route หรือแท็บใหม่จากการคลิกครั้งนั้น ห้ามรับโปรเจกต์เก่าของ Job อื่น

Runtime `0.15.200` build `20260903.2` รองรับ Manual attachment handoff: ถ้า Extension หยุดหลัง attachment proof ไม่ผ่าน แต่ผู้ใช้แนบรูปใน Composer เดิม ระบบต้องตรวจพบแล้วทำต่อเองจาก Job/Shot/Tab เดิม ปุ่มส่งใช้ปุ่มแม่ `button[type="submit"][aria-label="เริ่มสร้าง"]` ไม่คลิก span `mat-mdc-button-touch-target`; watcher ห้ามอัปโหลดหรือเลือกภาพซ้ำ

Google Flow เครดิตหมด: Extension ต้องส่ง `credit_exhausted` เฉพาะเมื่อพบข้อความเตือนสดว่าเครดิตหมด/ไม่พอ ไม่ใช้ยอด `0 credits` เพียงอย่างเดียวตัดสิน เพราะงานที่ใช้เครดิตก้อนสุดท้ายอาจยังสร้างสำเร็จได้; โปรแกรมหยุดที่ช็อตปัจจุบัน แสดง Popup `เครดิต Google Flow หมดหรือไม่เพียงพอ` และปุ่ม `ทำต่อด้วยบัญชี Google Flow ใหม่` โดยรักษาภาพ เสียง Subtitle และช็อตที่เสร็จแล้วทั้งหมด

Meta AI Vibes ถูกถอดออกถาวรและไม่มี host permission/content script ใน Extension `0.15.112` เพราะบริการมีโควตาสร้างวิดีโอและไม่ใช่ตัวเลือกฟรีที่เชื่อถือได้ ห้ามเพิ่มกลับโดยไม่มีคำสั่งใหม่จากผู้ใช้

หน้า Affiliate แยก `สร้างรูปด้วย` ออกจากสถานะผู้สร้างวิดีโอ Google Flow; One-click และปุ่มทำต่อแบบ 3 ช็อตใช้ `video_provider=flow` เท่านั้น

Product Gemini Web: `warnings` เป็นฟิลด์เสริมและอาจเป็น `[]` ได้ ห้ามทิ้ง Analysis/Checkpoint เพราะ `warnings` ว่าง; ทุกคำสั่งเริ่ม/ทำต่อ AI ต้องตามด้วย `focus_ai_web` และ Windows Chrome restore เพื่อให้ผู้ใช้เห็นแท็บจริง

AI Web attach/send รุ่น `0.15.219`: คืนเส้นทางแนบรูปที่พิสูจน์แล้วจาก `0.15.216`; ถ้า Gemini มีรูปอ้างอิงใน user turn เดิมให้ใช้ต่อโดยไม่เปิดเมนูหรือแนบซ้ำ จากนั้น focus หน้าต่าง/แท็บและกดปุ่มส่งด้วย trusted click เพียงครั้งเดียว พร้อมตรวจว่า click ถึงปุ่มจริง ห้ามใช้ Enter/click/re-upload ซ้ำเมื่อหลักฐานหน้าเว็บตอบช้า

Gemini JSON repair รุ่น `0.15.220`: คำตอบประเภท “ฉันไม่สามารถช่วย/เป็นโมเดลภาษา” ถือเป็น assistant turn ที่จบแล้วและส่งเข้าลูปจัด JSON ใหม่ทันที ไม่ทิ้ง Job หรือส่ง Master Prompt ซ้ำ; ซ่อมสูงสุด 2 รอบผ่าน Provider เดิมก่อนแจ้ง Error

AI Web overlay รุ่น `0.15.221`: แถบสถานะ SmartFlow แสดงผลได้แต่ต้อง `pointer-events:none` เสมอ ห้ามบัง Composer/ปุ่มส่งของ ChatGPT หรือ Gemini; hit-test ที่ไม่ผ่านต้องบันทึก tag/id/class ของ element ที่บังและหยุดโดยไม่ส่งซ้ำ

Gemini image expansion รุ่น `0.15.222`: ตรวจและใช้รูปอ้างอิงเดิมก่อนค้นปุ่ม Upload เสมอ; ห้ามนับปุ่มที่มีรูปย่อเป็นปุ่มแนบ หากหน้าขยายรูปค้างก่อนส่งให้ปิดด้วย trusted Escape หนึ่งครั้ง แล้วตรวจปุ่มส่งใหม่โดยไม่แนบรูปหรือส่ง Prompt ซ้ำ

ประวัติ Flow policy รุ่น `0.15.224` (ถูกแทนที่ด้วยสัญญา `0.15.242`): รุ่นนั้นให้ `generation_in_progress`/คิวของรอบปัจจุบันชนะการ์ด Error เก่า และเคยย้าย output slot ไปให้รูปถัดไปสร้าง Alternate Take หลัง denial; ห้ามนำกฎ reassignment/Alternate Take นี้กลับมาใช้กับ Runtime ปัจจุบัน

Flow attachment รุ่น `0.15.227`: ทุกช็อตต้องพิสูจน์ chip/thumbnail ของรูปจริงใน `.base-prompt-box` แบบเดียวกับช็อตแรกก่อนกดสร้าง ห้ามนับปุ่มปิด/พื้นหลังใกล้ Composer หรือผล `composerProof` จาก service worker เพียงอย่างเดียวเป็นรูปแนบ และต้องปิด Popup บันทึกการเปลี่ยนแปลงด้วยปุ่ม `เริ่มต้นใช้งาน` ที่อยู่ใน dialog นั้นเท่านั้นก่อนทำขั้นตอนเดิมต่อ หากการตรวจแบบ passive พบรูป+Prompt+ปุ่มสร้างพร้อมโดยไม่มีใบเสร็จการส่ง ให้คืน token แล้วเข้าธุรกรรมกดสร้างเดิมหนึ่งครั้งโดยไม่อัปโหลดซ้ำ

Flow hand-off รุ่น `0.15.228`: หลังดาวน์โหลดไฟล์จริงแล้ว Extension อ่านคิวใหม่แบบเร่งชั่วคราวที่ 0.25/1/2.5 วินาทีโดยไม่คลิกหน้าเว็บเอง; การอนุมัติเครดิตมี trusted click เพียงครั้งเดียวและไม่มี DOM click รอบสอง; Resume รับเฉพาะแท็บที่ผูก Job/SHOT เดิม และการปิดงานแตะเฉพาะแท็บที่ Extension ลงทะเบียนไว้

Story/Drama Recovery: ก่อนส่งคำสั่งกู้รอบใหม่ต้องล้างเฉพาะ terminal AI progress ของ Job เดิมด้วย `clear_ai_progress(job_id)` แล้วค่อย queue คำสั่งและเริ่ม monitor มิฉะนั้น Error heartbeat เก่าจะกินสิทธิ์กู้ครบทุกครั้งก่อน Extension เริ่มงานจริง; ห้ามลบ Analysis หรือ partial-image Checkpoint

Story/Drama Google Flow: เก็บ `video_generation_mode=google_flow`, ส่ง `scene_NN.png` ผ่าน Flow package เดิมทีละฉาก และบันทึกคลิปจริงเป็น `videos/flow_scene_NN.mp4`/`flow_clips`; เมื่อฉากได้รับ structured current-card `FLOW_POLICY_BLOCKED` ครั้งแรก ให้สร้าง local motion จาก `scene_NN.png` เดิม บันทึกแยกใน `flow_fallback_clips` แล้วเดินฉากถัดไปทันที ห้ามส่ง safe Prompt, reupload หรือ Retry Flow ของฉากนั้น Retry/app restart ต้องข้ามทั้งคลิปจริงและ fallback ที่ Checkpoint แล้ว ห้ามสร้างซ้ำ คลิปคนละฉากห้ามมี SHA-256 ซ้ำกัน Final ผสมใช้ `google_flow_story_hybrid_fallback` พร้อม `flow_clip_count`, `flow_fallback_count` และรายการฉากสำรองจริง ส่วนค่าเริ่มต้นหน้า Story ยังเป็น `image_motion` เพื่อไม่ใช้เครดิต Flow โดยไม่ตั้งใจ

Voice stability: ทุก Product/Story/Drama ต้องใช้ `emotion_id=normal` และ `speed=1.0` เท่านั้น โดยบังคับซ้ำใน `ExternalTtsClient`; หน้า AI Voice มีปุ่มบันทึกค่าและบทพูดผ่าน `voice_save_settings` และถ้าบทเปลี่ยนต้อง invalidate Voice/Subtitle เดิม ห้ามเอาค่าอารมณ์จากบทละครหรือ config เก่ากลับมาใช้

## Web Login Gate

- รองรับ ChatGPT Web, Gemini Web และ Google Flow
- Extension ส่ง `user_action_required + login_required + service`
- UI popup บอกชื่อเว็บและมีปุ่มเปิด Chrome
- ระหว่างรอ Login หยุด timeout และไม่เข้า recovery
- ผู้ใช้ Login เอง; ห้ามอ่าน/กรอก/เก็บ password, cookie, OTP
- Extension ต้องตรวจ composer/workspace พร้อมจริงก่อนส่ง `user_action_resolved`
- จากนั้นใช้ `resume_chatgpt` หรือ `open_flow` กับ Job/ช็อตเดิม
- รายละเอียดเต็ม: `PROGRAM_BLUEPRINT.md` หัวข้อ 6.5

## แผนที่ไฟล์แบบสั้น

| งาน | เปิดก่อน |
|---|---|
| Login/CAPTCHA/Extension/Chrome | Blueprint 6.5, `browser_extension/background.js`, `chatgpt.js`, `flow.js`, `core/local_bridge.py`, `tests/test_web_login_gate.py` |
| Product one-click/วิดีโอ AI | Blueprint 4, 6.4 และ 6.6, `core/product_pipeline.py`, methods `_run_product_pipeline`, `_multi_flow_worker`, `_wait_flow_step` ใน `ui/main_window.py` |
| Story/Batch/Checkpoint | Blueprint 5, `core/story_manager.py`, `core/story_pipeline.py`, `core/story_queue.py` |
| Drama/EP/ตัวละคร | Blueprint 5.6, `core/drama_series.py`, `core/drama_media.py`, `tests/test_drama_*` |
| Hybrid UI/ปุ่ม/หน้า | Blueprint 3, `web_ui/index.html`, `styles.css`, `app.js`, `tests/test_hybrid_ui.py` |
| Subtitle ไทย | Blueprint 5.2, `core/subtitle_renderer.py`, subtitle helpers/tests |
| Voice | Blueprint 7, `core/external_tts.py`, เฉพาะ voice methods ใน `ui/main_window.py` |
| Library/Popup ปก Shorts/ลบไฟล์ | Blueprint 5.5 และ 5A, `core/video_library.py`, `web_ui/app.js`, tests ที่เกี่ยวข้อง |
| Android/Post | Blueprint 8 Shopee product-video posting / Android Wi-Fi pairing, `core/shopee_posting/`, `core/android_wifi.py`, `core/adb_manager.py`, `web_ui/shopee_posting.js`, `web_ui/android_wifi.js`, `tests/test_shopee_posting.py`, `tests/test_android_wifi.py`; CSV legacy `core/job_manager.py` remains separate |
| เปิดโปรแกรม/CMD/EXE | Blueprint 2 และ 9, `desktop/hybrid.py`, `app.py`, launcher |
| Config/Queue/Manifest หายหรือชนกัน | Blueprint 4 และ 11, `core/atomic_json.py`, manager ที่เกี่ยวข้อง, `tests/test_atomic_json.py` |

## กฎทำงานประหยัดเครดิต

1. ใช้ `rg` หา symbol ก่อน เปิดครั้งละประมาณ 80–160 บรรทัดรอบ symbol
2. ห้าม dump `ui/main_window.py` ทั้งไฟล์
3. ห้ามสแกน `workspace/`, `backups/`, `logs/`, `screenshots/`, `deliverables/` ถ้าไม่ได้ระบุ Job/ไฟล์
4. แก้ renderer ให้ใช้รูป/เสียงเดิมและ `--reuse-voice`
5. รัน targeted tests ก่อน แล้ว full suiteเมื่อ code เปลี่ยน
6. อัปเดต `PROGRAM_BLUEPRINT.md` และไฟล์นี้เมื่อ route/status/version/invariant เปลี่ยน
7. ห้ามบันทึก API key, SOT, SOD, token, cookie หรือ password ลง source/log
8. ก่อนแก้ Product/Flow/Extension ต้องอ่าน Blueprint 12.4 และเทียบ known-good ก่อน ห้ามเพิ่ม selector, auto-click หรือ state transition จากการเดา
9. ทุกบั๊กที่ยืนยันแล้วต้องเพิ่มทั้งวิธีที่พัง วิธีที่ใช้ได้ และ regression guard ลง Blueprint 12.4 ในรอบเดียวกับการแก้

## คำสั่งตรวจมาตรฐาน

```powershell
python -m unittest discover -s tests -p "test_*.py"
node --check browser_extension/background.js
node --check browser_extension/chatgpt.js
node --check browser_extension/flow.js
node tests/extension_bridge_harness.js
Invoke-RestMethod http://127.0.0.1:8765/health
```

ก่อน browser automation ต้องตรวจว่า `/health` ตอบ `ok=true`, `desktop_ui=hybrid` และ Extension version ตรง `LocalBridge.REQUIRED_EXTENSION_VERSION`
# รุ่น Runtime `0.15.334`

Story ChatGPT preference-pair response selects one loaded image locally instead of timing out on multiple_images. Exact request/old-asset/stability guards retained, restore supported. No preference vote or new Send. Read docs/reports/story-image-comparison-334.md. Installed E2E pending;333 lifecycle remains in force.
471 CANONICAL INTEGRATED: start docs/reports/logic-version-map-471.md for per-logic observed versions and limits, then editorial-handoff-471.md for2994AFroot cause and handoff. Main now paired471; installed activation and actual Final unverified. Do not reapply staged patches, rerun unchanged tests, infer old current-version headings as authority or reactivate monitoring. User owns Extension update; no installer.
