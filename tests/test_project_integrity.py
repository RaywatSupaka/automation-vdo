import json
import re
import unittest
from pathlib import Path

from PIL import Image

from core.config import ROOT, load_config
from core.local_bridge import LocalBridge


class ProjectIntegrityTests(unittest.TestCase):
    def test_flow_inspect_recovers_a_ready_composer_without_reuploading(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        recovery = flow.split("const currentComposerReady = Boolean(", 1)[1].split(
            "const hasBoundDirectVideo", 1
        )[0]
        self.assertIn("promptHasAttachedMedia()", recovery)
        self.assertIn("currentPromptText.includes", recovery)
        self.assertIn("findGenerateButton()", recovery)
        self.assertIn("!monitorMatches && !readyReceiptActive", recovery)
        self.assertIn("recoveredReadyComposer: true", recovery)
        self.assertIn('report("ready_to_generate_recovery"', recovery)
        self.assertIn("return await runAutoPrepareOnce()", recovery)
        self.assertNotIn("dropReferenceImage", recovery)

    def test_flow_changelog_popup_is_scoped_and_dismissed_during_prepare_and_monitor(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("function hasFlowChangelogAnnouncement()", flow)
        self.assertIn('chrome.runtime.sendMessage({ type: "DISMISS_FLOW_CHANGELOG" })', flow)
        self.assertGreaterEqual(flow.count('report("dismissed_changelog"'), 2)
        handler = background.split('message?.type === "DISMISS_FLOW_CHANGELOG"', 1)[1].split(
            'message?.type === "CLOSE_FLOW_OVERLAY"', 1
        )[0]
        self.assertIn("mat-dialog-actions.change-log-modal-actions,.change-log-modal-actions", handler)
        self.assertIn("ดูบันทึกการเปลี่ยนแปลงทั้งหมด", handler)
        self.assertIn("เริ่มต้นใช้งาน", handler)
        self.assertNotIn("อนุมัติเสมอ", handler)

    def test_drama_ui_exposes_checkpoint_recovery_for_orphaned_episode(self):
        source = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("runningNeedsRecovery", source)
        self.assertIn("กู้คืนไฟล์ EP", source)
        self.assertIn("กู้คืนไฟล์และทำต่อ", source)
        self.assertIn(
            "renderDramaSeries(state.drama_series || {}, state.story_progress || {})",
            source,
        )

    def test_tools_extension_and_logo_exist(self):
        config = load_config()
        self.assertEqual(config["ai_provider"], "chatgpt_plugin")
        self.assertFalse(config["use_openai_api"])
        self.assertNotIn("openai_api_key", config)
        self.assertTrue(Path(config["adb_path"]).is_file())
        self.assertTrue(Path(config["scrcpy_path"]).is_file())
        extension = ROOT / "browser_extension"
        manifest = json.loads((extension / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(manifest["version"], LocalBridge.REQUIRED_EXTENSION_VERSION)
        self.assertIn("https://gemini.google.com/*", manifest["host_permissions"])
        self.assertIn(config["image_ai_provider"], {"chatgpt", "gemini"})
        self.assertIn(config["video_resolution"], {"540x960", "720x1280", "1080x1920"})
        self.assertIn(config["video_fps"], {24, 30, 50, 60})
        for filename in ("content.js", "popup.js", "background.js", "popup.html", "popup.css", "logo.jpg"):
            self.assertTrue((extension / filename).is_file(), filename)
        with Image.open(ROOT / "assets" / "smartflow_logo.png") as image:
            self.assertEqual(image.size, (1254, 1254))
        with Image.open(ROOT / "assets" / "smartflow_icon.png") as image:
            self.assertEqual(image.size, (1024, 1024))
        self.assertGreater((ROOT / "assets" / "smartflow_icon.ico").stat().st_size, 10_000)
        self.assertEqual(Path(config["logo_file"]).resolve(), (ROOT / "assets" / "smartflow_logo.png").resolve())

    def test_chatgpt_accepts_virtualized_completed_turns(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        self.assertIn('return visible(turn) || Boolean(text) || Boolean(turn.querySelector("img"));', source)
        self.assertIn("ChatGPT virtualizes long turns", source)

    def test_drama_speaker_guard_runs_before_image_generation(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        self.assertIn("function normaliseDialogueSpeakers(result, allowedSpeakers = [])", source)
        self.assertIn('speaker = "ผู้บรรยาย";', source)
        self.assertIn("pkg.request?.allowed_speakers || []", source)
        self.assertLess(source.index("normaliseDialogueSpeakers(result, allowedSpeakers)"), source.index("const generatedImages = mode ==="))

    def test_story_supports_fifteen_scenes_and_repairs_short_saved_analysis(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
        self.assertIn("Math.min(pkg.job?.long_video && pkg.request?.aspect_ratio === '16:9' ? 50 : 15", source)
        self.assertNotIn("Math.min(12, Number(pkg.request?.image_count", source)
        self.assertIn('"ai_image_count": max(0, min(50, int(body.get("image_count") or 0)))', bridge)
        self.assertIn("async function validateOrRepairStoredAnalysis", source)
        self.assertIn("คง ${promptField} ${existingCount} รายการแรกตามเดิม", source)
        self.assertIn("pkg.checkpoint_images.length", source)
        self.assertIn("result = await validateOrRepairStoredAnalysis(result, pkg, promptField, imageCount);", source)

    def test_story_analysis_requires_aligned_narrations_and_durations(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        self.assertIn('"scene_narrations", "scene_durations",', source)
        self.assertIn("values.length !== imageCount", source)

    def test_analysis_waits_on_the_accepted_turn_without_resubmitting_master_prompt(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        run_analysis = source.split("const masterPrompt =", 1)[1].split('await report("analysis_ready"', 1)[0]
        self.assertIn("latestAssistantStrictlyAfterLatestUser", source)
        self.assertIn("Date.now() - started > 35000", source)
        self.assertIn('"analysis_response_delayed"', source)
        self.assertIn("รอคำตอบเดิมโดยไม่ส่ง Prompt หรือแนบรูปซ้ำ", source)
        self.assertIn('timeoutError.code = "AI_ANALYSIS_TIMEOUT"', source)
        self.assertEqual(run_analysis.count("submitPrompt(masterPrompt"), 1)
        self.assertNotIn('report("retrying_analysis"', run_analysis)
        self.assertIn('["CHATGPT_NO_IMAGE", "CHATGPT_NO_RESPONSE", "CHATGPT_IMAGE_STALLED"]', source)

    def test_chatgpt_detects_an_explicit_image_generation_failure(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        self.assertIn("function explicitImageFailure(text)", source)
        self.assertIn("การสร้าง(?:รูป)?ภาพ(?:เกิดข้อ)?ผิดพลาด", source)
        self.assertIn("failed to generate", source)

    def test_story_image_refusal_stops_without_changing_characters_or_events(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        self.assertIn("ผู้ให้บริการเนื้อหาบุคคลที่สาม", source)
        self.assertIn("storyImageRefusal", source)
        self.assertIn("STORY_IMAGE_REFUSED", source)
        self.assertIn("STORY_CONTENT_MISMATCH", source)
        self.assertNotIn("originalStoryImagePrompt", source)
        self.assertNotIn("Do not depict, name, imitate or reproduce any copyrighted franchise character", source)
        self.assertNotIn("ผู้ใหญ่อายุอย่างน้อยยี่สิบห้าปี", source)
        self.assertIn("ห้ามเปลี่ยนเป็นเหตุการณ์ใหม่", source)

    def test_chatgpt_analysis_and_reference_uploads_have_bounded_recovery(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        self.assertIn('"retrying_analysis_after_refusal"', source)
        self.assertIn('"analysis_response_delayed"', source)
        self.assertIn('report("retrying_source_image"', source)
        self.assertIn("หมดเวลารอรูปอ้างอิงจากโปรแกรม", source)
        self.assertIn("latestAssistantStrictlyAfterLatestUser();", source)

    def test_gemini_json_repair_uses_local_safe_variants_before_resubmitting(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        self.assertIn("function escapeJsonControlCharacters(value)", source)
        self.assertIn("function localJsonVariants(candidate)", source)
        self.assertIn("if (typeof parsed === \"string\") parsed = JSON.parse(parsed);", source)
        self.assertIn("for (const variant of localJsonVariants(candidate))", source)
        self.assertIn("ห้ามใช้ ... ย่อข้อมูล", source)
        self.assertIn("สาเหตุที่ระบบตรวจพบ", source)
        self.assertIn("const rootStarts = [...text.matchAll", source)
        self.assertIn("parsedCandidates.sort", source)

    def test_ai_web_submit_waits_for_stable_draft_then_uses_one_trusted_click(self):
        ai_web = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        # Scope only the ordinary Send function. Motion service recovery below
        # it may click the provider's separate, durably claimed native Retry.
        sender = ai_web.split("async function sendAndVerify", 1)[1].split("async function ensureAiWebModel", 1)[0]
        handler = background.split('message?.type === "CLICK_AI_SEND_BUTTON"', 1)[1].split('message?.type === "CONFIGURE_FLOW_VIDEO_SETTINGS"', 1)[0]
        resolver = handler.split("const resolveAiSendPrepressPoint = (", 1)[1].split("const readInitialSendPoint =", 1)[0]
        self.assertIn("async function waitForStableSendDraft", ai_web)
        self.assertIn("stableMatches >= 3", ai_web)
        self.assertIn("await waitForStableSendDraft(expectedPrompt,12000,Boolean(storySend))", sender)
        self.assertIn("owned_story_user_turn", sender)
        self.assertIn('type: "CLICK_AI_SEND_BUTTON"', sender)
        self.assertIn("promptBeforeSend && liveEditor && !currentPrompt", sender)
        self.assertIn("const liveEditor = composer();", sender)
        self.assertIn("assistantTurns().length > beforeAssistantTurns", sender)
        self.assertIn("attempt < 240", sender)
        self.assertIn('error.code = "AI_SEND_DISPATCHED_UNCONFIRMED"', sender)
        self.assertIn('"ai_send_dispatched"', sender)
        self.assertIn('"ai_send_accepted"', sender)
        self.assertIn("โดยไม่กดและไม่แนบรูปซ้ำ", sender)
        self.assertNotIn("requestSubmit", sender)
        self.assertNotIn("new KeyboardEvent", sender)
        self.assertNotIn("button.click()", sender)
        self.assertIn("single_trusted_ai_send", handler)
        self.assertIn("Input.dispatchMouseEvent", handler)
        # The shared resolver rejects empty/changed drafts before selecting a
        # point; both initial and final MAIN-world checks use that resolver.
        self.assertIn("if (!editor || !expected || draft(editor) !== expected)", resolver)
        self.assertIn("reason:'draft_mismatch'", resolver)
        self.assertLess(resolver.index("draft(editor) !== expected"), resolver.index("let selected = hitPoint"))
        self.assertEqual(len(re.findall(r"func\s*:\s*resolveAiSendPrepressPoint\b", handler)), 2)
        self.assertIn("finalPoint = await inspectSendPoint(false, finalPoint.key);", handler)
        self.assertEqual(handler.count('type: "mousePressed"'), 1)
        self.assertEqual(handler.count('type: "mouseReleased"'), 1)
        self.assertNotIn("sendGeminiWithEnter", ai_web)

    def test_gemini_preserves_proven_015216_attachment_reuse_without_reupload_loop(self):
        ai_web = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = ai_web.split("async function attachSourceImages", 1)[1].split("function aiWebFailureDiagnostic", 1)[0]
        self.assertIn("source_images_reused", attach)
        self.assertIn("ใช้รูปอ้างอิง", attach)
        self.assertIn("existingReferences.length", attach)
        self.assertLess(attach.index("existingReferences.length"), attach.index("attach?.click()"))
        self.assertIn('button.querySelector("img")', attach)
        self.assertIn("image-expansion-dialog", attach)
        self.assertIn("input.dispatchEvent(new Event(\"change\"", attach)
        self.assertIn("waitForChatGPTSourceAttachmentProof", ai_web)
        self.assertIn("if (!IS_GEMINI)", attach)
        self.assertNotIn('type: "OPEN_AI_ATTACHMENT_MENU"', attach)
        self.assertNotIn('message?.type === "OPEN_AI_ATTACHMENT_MENU"', background)

    def test_chatgpt_requires_real_reference_preview_before_sending_prompt(self):
        ai_web = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        attach = ai_web.split("async function attachSourceImages", 1)[1].split("function aiWebFailureDiagnostic", 1)[0]
        submit = ai_web.split("async function submitPrompt", 1)[1].split("async function ensureAiWebModel", 1)[0]
        self.assertIn('element.id === "upload-files"', ai_web)
        self.assertIn('data-photo-upload-enabled', ai_web)
        self.assertIn('เพิ่มไฟล์(?:และอื่นๆ)?', attach)
        self.assertIn('Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "files")', attach)
        self.assertIn("waitForChatGPTSourceAttachmentProof(expectedCount)", attach)
        self.assertIn("ระบบยังไม่ส่ง Prompt เพื่อป้องกันการสร้างภาพโดยไม่มีรูปอ้างอิง", ai_web)
        self.assertLess(submit.index("await attachSourceImages(imageUrls)"), submit.index("await setComposerText(editor, text)"))

    def test_ai_web_send_focuses_tab_and_proves_one_trusted_click(self):
        ai_web = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        handler = background.split('message?.type === "CLICK_AI_SEND_BUTTON"', 1)[1].split('message?.type === "CONFIGURE_FLOW_VIDEO_SETTINGS"', 1)[0]
        resolver = handler.split("const resolveAiSendPrepressPoint = (", 1)[1].split("const readInitialSendPoint =", 1)[0]
        banner = ai_web.split("function statusBanner()", 1)[1].split("async function report", 1)[0]
        self.assertIn('pointerEvents: "none"', banner)
        self.assertIn("chrome.windows.update", handler)
        self.assertIn("chrome.tabs.update", handler)
        self.assertIn("document.elementFromPoint(x,y)", resolver)
        self.assertRegex(resolver, r"return\s+hit\s*&&\s*\(hit\s*===\s*button\s*\|\|\s*button\.contains\(hit\)\)\s*\?")
        self.assertIn("if (!selected) return {ok:false,reason:'target_blocked'", resolver)
        self.assertIn("image-expansion-dialog-backdrop", handler)
        self.assertIn('"Input.dispatchKeyEvent"', handler)
        self.assertIn('key: "Escape"', handler)
        self.assertIn("event.isTrusted", handler)
        self.assertIn("trustedClickSeen", handler)
        self.assertEqual(len(re.findall(r"func\s*:\s*resolveAiSendPrepressPoint\b", handler)), 2)
        self.assertIn("if (!editor || !expected || draft(editor) !== expected)", resolver)
        self.assertIn("expectedArmKey && gesture.lastFrame !== frame()", resolver)
        self.assertIn("key!==expectedArmKey || document.activeElement!==button", resolver)
        self.assertLess(handler.index("releaseAttempted = true;"), handler.index('type: "mouseReleased"'))
        self.assertEqual(handler.count('type: "mousePressed"'), 1)
        self.assertEqual(handler.count('type: "mouseReleased"'), 1)

    def test_gemini_counts_one_outer_user_query_per_real_turn(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        user_turns = source.split("function userTurns()", 1)[1].split("function lastUserTurnSignature", 1)[0]
        self.assertIn('document.querySelectorAll("user-query")', user_turns)
        self.assertIn("if (primary.length) return primary", user_turns)
        self.assertIn("parentElement?.closest", user_turns)
        self.assertNotIn("user-query, [data-test-id", user_turns)

    def test_ai_web_error_reports_page_and_attachment_diagnostic(self):
        ai_web = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("function aiWebFailureDiagnostic()", ai_web)
        self.assertIn("source_attachment_count", ai_web)
        self.assertIn("image_expansion_open", ai_web)
        self.assertIn("ai_page_url", bridge)
        self.assertIn("ai_page_excerpt", bridge)
        self.assertIn("def _product_error_service", engine)
        self.assertIn("Gemini Web / วิเคราะห์และสร้างรูปสินค้า", engine)
        self.assertIn("client.get(\"ai_page_excerpt\")", engine)

    def test_ai_web_selects_the_job_model_once_per_fresh_meta_step(self):
        ai_web = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        submit_analysis = ai_web.split("async function submitPrompt", 1)[1].split("function escapeJsonControlCharacters", 1)[0]
        submit_image = ai_web.split("async function submitImagePrompt", 1)[1].split("async function imageData", 1)[0]
        handler = background.split('message?.type === "SELECT_AI_MODEL"', 1)[1].split('message?.type === "CLICK_AI_SEND_BUTTON"', 1)[0]
        self.assertNotIn("ensureAiWebModel", submit_analysis)
        self.assertNotIn("ensureAiWebModel", submit_image)
        cover = ai_web.split('async function runAICover(',1)[1].split('async function runMetaRedesignHelper(',1)[0]
        redesign = ai_web.split('async function runMetaRedesignHelper(',1)[1].split('async function runSceneRepairHelper(',1)[0]
        self.assertEqual(cover.count("await ensureAiWebModel("), 1)
        # Meta redesign now has separate image and prompt steps. The prompt
        # step selects a model only if it opens a fresh helper tab.
        self.assertEqual(redesign.count("await ensureAiWebModel("), 2)
        self.assertEqual(ai_web.replace(cover,'').replace(redesign,'').count("await ensureAiWebModel("), 1)
        self.assertIn('type: "SELECT_AI_MODEL"', ai_web)
        self.assertIn('pkg.job?.ai_web_model', ai_web)
        self.assertIn("flash_lite", handler)
        self.assertIn("long_thinking", handler)
        self.assertIn("instant", handler)
        self.assertIn("การคิดที่นานขึ้น", handler)
        self.assertIn("trusted_ai_model", handler)
        self.assertIn("Input.dispatchMouseEvent", handler)
        self.assertIn("ระบบยังไม่ส่ง Prompt เพื่อป้องกันงานผิดโมเดล", ai_web)
        self.assertNotIn("nonFatal: true", handler)

    def test_chatgpt_stalled_image_recovery_preserves_the_current_scene(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        self.assertIn("CHATGPT_IMAGE_STALL_WARNING_MS = 90000", source)
        self.assertIn("CHATGPT_IMAGE_STALL_ABORT_MS = 180000", source)
        self.assertNotIn("CHATGPT_COMPLETE_IMAGE_GRACE_MS", source)
        passive_wait = source.split("async function stopStalledChatGPTGeneration(", 1)[1].split("async function waitForResponseIdle(", 1)[0]
        self.assertIn("await waitForResponseIdle(", passive_wait)
        self.assertNotIn(".click(", passive_wait)
        self.assertIn("while (storyWait || stopButtonVisible() || Date.now() - started < 360000)", source)
        self.assertIn('error.code = "CHATGPT_IMAGE_STALLED";', source)
        self.assertIn('"CHATGPT_IMAGE_STALLED"].includes(error?.code)', source)
        self.assertIn("ไม่กดหยุดหรือส่งซ้ำ", source)

    def test_fresh_chatgpt_recovery_retires_the_stuck_job_tab_first(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        recovery = source.split("if (reuseAnalysis && forceFreshTab) {", 1)[1].split("if (reuseAnalysis && !forceFreshTab)", 1)[0]
        self.assertIn('type: "CANCEL_CHATGPT_JOB", job_id: jobId', recovery)
        self.assertIn("await chrome.tabs.remove(staleIds)", recovery)
        self.assertLess(recovery.index("CANCEL_CHATGPT_JOB"), recovery.index("chrome.tabs.remove(staleIds)"))

    def test_flow_uses_animate_menu_without_reopening_media_selector(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = source.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
            'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
        )[0]
        self.assertIn('findPoint("gallery_media_card"', attach)
        self.assertIn('findPoint("gallery_media_menu"', attach)
        self.assertIn('findPoint("animate_media_action")', attach)
        self.assertIn("waitForPromptMediaProof(60)", attach)
        self.assertNotIn('findPoint("composer_media_selector")', attach)
        self.assertNotIn('findPoint("latest_media"', attach)
        self.assertNotIn('findPoint("add_to_prompt")', attach)
        self.assertIn("flow-content\\.google\\/image\\/", attach)
        self.assertIn("chipAriaLabel", attach)

    def test_flow_does_not_mistake_project_gallery_media_for_prompt_attachment(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        proof = background.split("const promptHasAttachedMedia = async () =>", 1)[1].split("if (sender.tab?.windowId)", 1)[0]
        self.assertIn("same small", proof)
        self.assertIn("composer.contains(element)", proof)
        self.assertIn("maxComposerHeight", proof)
        self.assertIn("Math.min(760, Math.max(560, innerHeight - 80))", proof)
        self.assertIn("removableContainer", proof)
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertIn("function promptHasAttachedMedia()", flow)
        self.assertIn("const imageReady = Boolean(imageAttachAttempted && promptHasAttachedMedia())", flow)
        self.assertNotIn("promptHasAttachedMedia() || attachDebug?.composerProof === true", flow)
        self.assertIn("removableContainer(element)", flow)
        self.assertIn('editor.closest?.(".base-prompt-box")', flow)
        self.assertIn("DEBUG_PROMPT_MEDIA", flow)

    def test_flow_runtime_update_does_not_reload_mid_project_handoff(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        manifest = json.loads((ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], LocalBridge.REQUIRED_EXTENSION_VERSION)
        self.assertNotIn("smartpostFlowRuntimeBuild", flow)
        self.assertNotIn("chrome.runtime.reload();", flow)
        self.assertIn("Never reload the whole Extension from inside a Flow project", flow)

    def test_flow_landing_page_always_opens_a_real_project_before_upload(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        auto = flow.split("async function autoPrepare()", 1)[1]
        self.assertIn('const onProjectPage = /\\/project\\//i.test(location.pathname);', auto)
        self.assertIn("if (!onProjectPage) {", auto)
        self.assertNotIn("!onProjectPage && !hasEditor", auto)
        self.assertLess(auto.index('await report("opening_project"'), auto.index("dropReferenceImage()"))

    def test_optional_flow_overlay_cleanup_cannot_stall_preparing(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        cleanup = flow.split("async function dismissNonLegalOverlay()", 1)[1].split("async function ensureAgentMode()", 1)[0]
        self.assertIn("Promise.race([", cleanup)
        self.assertIn('chrome.runtime.sendMessage({ type: "CLOSE_FLOW_OVERLAY" })', cleanup)
        self.assertIn("setTimeout(() => resolve(null), 5000)", cleanup)
        self.assertIn('if (!/\\/project\\//i.test(location.pathname)) return 0;', cleanup)

    def test_flow_overlay_cleanup_never_removes_the_prompt_reference_chip(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        cleanup = flow.split("async function dismissNonLegalOverlay()", 1)[1].split("async function ensureAgentMode()", 1)[0]
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        physical = background.split('message?.type === "CLOSE_FLOW_OVERLAY"', 1)[1].split('message?.type === "CLICK_NEW_FLOW_PROJECT"', 1)[0]
        # Flow labels the remove button on an attached prompt image as
        # `close`. Both the content and trusted-click paths must require a
        # modal owner before they click such a control.
        self.assertIn("if (!dialog) return false;", cleanup)
        self.assertIn("if (!dialog) return false;", physical)

    def test_flow_project_open_wait_has_an_explicit_failure_state(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        open_flow = background.split('command.action === "open_flow"', 1)[1].split('command.action === "resume_flow_workspace"', 1)[0]
        self.assertIn('step: "project_open_failed"', open_flow)
        self.assertIn("ไม่สร้างโปรเจกต์ใหม่ภายใน 60 วินาที", open_flow)

    def test_flow_resume_reloads_only_a_proven_blank_project_tab(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        resume = background.split('command.action === "resume_flow_workspace"', 1)[1].split('command.action === "inspect_flow"', 1)[0]
        self.assertIn("pickHealthyFlowProjectTab", resume)
        self.assertIn("preferredTabs", resume)
        self.assertIn("workspaceBlank", resume)
        self.assertIn("interactiveCount", resume)
        self.assertIn("if (workspaceBlank && !presenterResume)", resume)
        self.assertIn("chrome.tabs.reload(projectTab.id)", resume)
        #371 permits reopening only a saved pre-submit project whose completed
        # upload is recoverable. Actual execution/negative cases also live in
        # flow_attachment_terminal_harness; ordinary resume cannot open home.
        #404 routes a completed manual proposal into its separate fresh-start
        # controller before this ordinary attachment/project resume branch.
        self.assertEqual(resume.count("chrome.tabs.create"), 1)
        self.assertIn("if(await openFlowReviewRebuild(command,source.package))", resume)
        self.assertIn("if(!projectTab?.id)", resume)
        self.assertIn("terminal?.attachment_failure_evidence?.selection_recovery_available", resume)
        self.assertIn("isFlowUrl(terminal.page_url)", resume)
        self.assertIn("flowProjectId(terminal.page_url)===terminal.attachment_failure_evidence.project_id", resume)
        self.assertIn("chrome.tabs.create({url:terminal.page_url,active:true})", resume)
        self.assertNotIn("openFlowTab(", resume)

    def test_flow_tab_selection_rejects_a_newer_blank_project(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("async function inspectFlowTabHealth(tab)", background)
        self.assertIn("async function pickHealthyFlowProjectTab(tabs, preferred = [])", background)
        self.assertIn("if (health.healthy) return tab;", background)
        self.assertIn("await pickHealthyFlowProjectTab(flowTabs)", background)
        open_flow = background.split('command.action === "open_flow"', 1)[1].split('command.action === "resume_flow_workspace"', 1)[0]
        self.assertIn("inspectFlowTabHealth(candidate)", open_flow)

    def test_only_the_registered_flow_tab_can_consume_auto_flow(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        auto = flow.split("async function autoPrepare()", 1)[1]
        self.assertIn('type: "IS_ACTIVE_FLOW_TAB"', auto)
        self.assertIn('message?.type === "IS_ACTIVE_FLOW_TAB"', background)
        self.assertIn("registeredIds.includes(tabId)", background)

    def test_flow_dead_workspace_recovers_in_the_same_tab(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        auto = flow.split("async function autoPrepare()", 1)[1]
        recovery = background.split('message?.type === "RECOVER_FLOW_WORKSPACE"', 1)[1].split('message?.type === "CLICK_NEW_FLOW_PROJECT"', 1)[0]
        self.assertIn('report("project_workspace_unavailable"', auto)
        self.assertIn('type: "RECOVER_FLOW_WORKSPACE"', auto)
        self.assertIn("chrome.tabs.update(tabId, { url: FLOW_URL, active: true })", recovery)
        self.assertNotIn("chrome.tabs.create", recovery)

    def test_flow_supports_the_current_flow_google_domain_and_legacy_redirect(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        popup = (ROOT / "browser_extension" / "popup.js").read_text(encoding="utf-8")
        manifest = json.loads((ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn('const FLOW_URL = "https://flow.google.com/";', background)
        self.assertIn("flow\\.google\\.com", background)
        self.assertIn("pending.service === \"flow\" ? isFlowUrl(url)", background)
        self.assertIn("function isFlowUrl(value)", popup)
        self.assertIn("const isFlow = isFlowUrl(tab?.url)", popup)
        self.assertIn("https://flow.google.com/*", manifest["host_permissions"])
        flow_matches = next(item["matches"] for item in manifest["content_scripts"] if "flow.js" in item["js"])
        self.assertIn("https://flow.google.com/*", flow_matches)
        self.assertIn("https://labs.google/fx/*", flow_matches)

    def test_gemini_analysis_refusal_waits_until_stable_then_enters_bounded_json_repair(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        submit = source.split("async function submitPrompt", 1)[1].split("async function waitForTurnImage", 1)[0]
        repair = source.split("async function parseOrRepairAnalysis", 1)[1].split("function largeAssistantImages", 1)[0]
        self.assertIn("function explicitAnalysisRefusal", source)
        self.assertIn("นอกเหนือขอบเขตโปรแกรม", source)
        self.assertIn("เป็น(?:เพียง|แค่)โมเดลภาษา", source)
        self.assertIn("ไม่เข้าใจคำถามนี้", source)
        self.assertIn("if (last && hasResponse && explicitAnalysisRefusal(content))", submit)
        self.assertIn("refusalStableSince", submit)
        self.assertIn("Date.now() - refusalStableSince >= 1800", submit)
        self.assertIn("return last;", submit)
        self.assertNotIn("ปฏิเสธการวิเคราะห์และไม่ส่ง JSON", submit)
        self.assertIn('const refused = explicitAnalysisRefusal(responseText)', repair)
        self.assertIn('"retrying_analysis_after_refusal"', repair)
        self.assertIn("งานนี้เป็นงานเขียนข้อความ JSON เท่านั้น ไม่ต้องสร้างรูป ไม่ต้องสร้างวิดีโอ", repair)
        self.assertIn("อ่านข้อมูลสินค้าและรูปอ้างอิงจากข้อความผู้ใช้ก่อนหน้า", repair)
        self.assertIn('"flow_gui_design", "flow_shot_prompts", "spoken_script_segments"', source)
        self.assertIn("ต้องเป็น JSON array จริงและมีอย่างละ ${imageCount} รายการพอดี", repair)
        self.assertIn("คำตอบก่อนหน้ามีข้อมูลที่ต้องการ แต่ JSON ยังอ่านไม่ได้", repair)
        self.assertIn("attempt < 3", repair)
        self.assertIn("หลังลองจัดรูปแบบอัตโนมัติ 2 รอบ", repair)

    def test_gemini_composer_uses_editor_input_path_before_single_send(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        composer = source.split("async function setComposerText", 1)[1].split("async function attachSourceImages", 1)[0]
        submit = source.split("async function sendAndVerify", 1)[1].split("async function ensureAiWebModel", 1)[0]
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        handler = background.split('message?.type === "CLICK_AI_SEND_BUTTON"', 1)[1].split('message?.type === "CONFIGURE_FLOW_VIDEO_SETTINGS"', 1)[0]
        resolver = handler.split("const resolveAiSendPrepressPoint = (", 1)[1].split("const readInitialSendPoint =", 1)[0]
        self.assertIn('const preparedText = String(text).trim().replace(/[\\r\\n\\t ]+/g, " ")', composer)
        self.assertIn('document.execCommand("insertText", false, preparedText)', composer)
        self.assertIn("stableMatches >= 2", composer)
        self.assertIn("const live = composer() || lastLive", composer)
        self.assertIn("actual !== preparedText", composer)
        self.assertIn('type: "TYPE_AI_PROMPT"', composer)
        self.assertIn('error.code = "AI_COMPOSER_TEXT_INCOMPLETE"', composer)
        self.assertIn('"composer_prompt_ready"', composer)
        self.assertIn("return finalEditor", composer)
        self.assertNotIn("editor.replaceChildren()", composer)
        self.assertEqual(source.count("editor = await setComposerText(editor, text)"), 2)
        self.assertIn("expectedPrompt", submit)
        self.assertIn('message?.type === "TYPE_AI_PROMPT"', background)
        self.assertIn('Input.insertText", { text: prompt }', background)
        self.assertIn("if (!editor || !expected || draft(editor) !== expected)", resolver)
        self.assertLess(resolver.index("draft(editor) !== expected"), resolver.index("button.scrollIntoView"))
        # Only ChatGPT receives fallback authority. Gemini retains its visible,
        # enabled, non-Stop button gate in both initial and prepress captures.
        self.assertRegex(handler, r"args:\s*\[wirePrompt,true,true,'',message\.provider\s*===\s*'chatgpt'\]")
        self.assertRegex(handler, r"args:\s*\[wirePrompt,false,prepareFocus,armKey,message\.provider\s*===\s*'chatgpt'\]")
        self.assertIn("(allowFallback ? rendered(element) : visible(element)) && !element.disabled", resolver)
        self.assertIn("element.getAttribute('aria-disabled') !== 'true' && !isStopControl(element)", resolver)
        self.assertIn("if (!selected && allowFallback && !expectedArmKey)", resolver)

    def test_gemini_resume_reuses_current_composer_references_without_reupload(self):
        source = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        attach = source.split("async function attachSourceImages", 1)[1].split("function latestAssistantAfterLatestUser", 1)[0]
        current_proof = attach.index("const currentComposerReferences = sourceAttachmentPreviews()")
        file_input = attach.index("let input = preferredSourceFileInput()")
        self.assertLess(current_proof, file_input)
        self.assertIn("stableComposerReferences.length >= expectedCount", attach)
        self.assertIn("พบรูปอ้างอิงในช่อง Gemini แล้ว", attach)

    def test_flow_accepts_product_and_story_reference_image_routes(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("function isAllowedFlowImageUrl(value)", source)
        self.assertIn('url.startsWith(`${BRIDGE}/api/jobs/`)', source)
        self.assertIn('url.startsWith(`${BRIDGE}/api/stories/`)', source)
        self.assertEqual(source.count("if (!isAllowedFlowImageUrl(message.url))"), 3)

    def test_flow_uses_golden_hidden_input_before_large_base64_fallback(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        start = source.index("async function dropReferenceImage()")
        end = source.index("async function autoPrepare()", start)
        fresh = source.index('status: "started"', start, end)
        upload = source.index('type: "OPEN_FLOW_MEDIA_UPLOAD"', fresh, end)
        base64_fallback = source.index('type: "GET_FLOW_IMAGE_DATA"', start, end)
        self.assertLess(upload, base64_fallback)
        self.assertIn("golden_hidden_file_input", source[fresh:base64_fallback])
        self.assertIn("if (!transfer) return false;", source[start:end])

    def test_flow_attachment_is_at_most_once_per_job_shot_and_project(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        drop_start = source.index("async function dropReferenceImage()")
        auto_start = source.index("async function autoPrepare()", drop_start)
        drop = source[drop_start:auto_start]
        self.assertIn("FLOW_ATTACHMENT_ATTEMPTS_KEY", source)
        self.assertIn("attachmentGuardBlocked", drop)
        self.assertIn('status: uploadDebug?.fileSet ? "uploaded_waiting_media" : "upload_failed"', drop)
        self.assertIn("The file-input transaction is at-most-once", drop)
        self.assertNotIn("const trustedDrop", drop)
        fresh = drop.index('status: "started"')
        self.assertLess(drop.index('type: "OPEN_FLOW_MEDIA_UPLOAD"', fresh), drop.index("return false;\n\n    /* Legacy fallback"))
        self.assertIn('step = confirmation === "credit"', source)
        self.assertIn('"attachment_needs_review"', source)

    def test_flow_requires_visible_composer_proof_after_media_selection(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
            'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
        )[0]
        self.assertIn("attachmentLikely", attach)
        self.assertIn("waitForPromptMediaProof", attach)
        self.assertIn("return imageAttached || backgroundAttached", attach)
        self.assertNotIn("removableCardAttached", attach)
        self.assertIn("retryable: false", attach)

    def test_flow_configures_verified_vertical_video_defaults_after_attachment(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        handler = background.split('message?.type === "CONFIGURE_FLOW_VIDEO_SETTINGS"', 1)[1].split(
            'message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1
        )[0]
        auto = flow.split("async function autoPrepare()", 1)[1]
        self.assertIn('type: "CONFIGURE_FLOW_VIDEO_SETTINGS"', flow)
        self.assertIn('input[type="radio"][value="2"]', handler)
        self.assertIn("สัดส่วนภาพเริ่มต้นสำหรับการสร้างวิดีโอ", handler)
        self.assertIn("จำนวนเอาต์พุตเริ่มต้นของการสร้างวิดีโอ", handler)
        self.assertIn("const targetAspect = message.aspect_ratio === '16:9' ? '16:9' : '9:16'", handler)
        self.assertIn('videoAspect: targetAspect', handler)
        self.assertIn("neverChecked", handler)
        self.assertIn("portraitChecked", handler)
        self.assertIn("singleChecked", handler)
        self.assertIn("modernVideoAspect", handler)
        self.assertIn("modernVideoCount", handler)
        self.assertIn("การตั้งค่า", handler)
        self.assertIn("FLOW_VIDEO_PROMPT_GUARD", flow)
        self.assertNotIn("flow_settings_prompt_fallback", flow)
        self.assertIn("FLOW_VIDEO_SETTINGS_REVIEW", flow)
        self.assertIn("videoChecked", handler)
        self.assertNotIn("หยุดก่อนแนบรูป", flow)
        self.assertLess(auto.index("dropReferenceImage()"), auto.index("ensureFlowVideoSettings()"))

    def test_flow_continues_after_project_upload_without_reloading(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        drop = flow.split("async function dropReferenceImage()", 1)[1].split("async function autoPrepare()", 1)[0]
        self.assertIn("golden_hidden_file_input", drop)
        self.assertIn("uploaded_ready", drop)
        # Legacy checkpoints are consumed without repeating the upload.
        self.assertIn("uploaded_waiting_reload", drop)
        self.assertIn("uploaded_reloaded", drop)
        self.assertNotIn("location.reload", drop)
        self.assertNotIn('return "reload_pending"', drop)
        self.assertIn("กำลังเลือกรูปในหน้าเดิมโดยไม่รีเฟรช", drop)
        self.assertIn("const attached = await attachExistingMediaToPrompt()", drop)

    def test_flow_attach_handler_never_uploads_or_drops_a_second_file(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
            'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
        )[0]
        self.assertIn("upload transaction is", attach)
        self.assertIn("at-most-once", attach)
        self.assertNotIn("physicalFileDrop(", attach)
        self.assertNotIn("single_trusted_file_drop_to_project", attach)

    def test_desktop_never_opens_a_new_project_after_attachment_safe_stop(self):
        desktop = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        marker = "หยุดเพื่อป้องกันการอัปโหลดรูปซ้ำ"
        self.assertGreaterEqual(desktop.count(marker), 3)
        self.assertIn("ไม่เปิดโปรเจกต์ใหม่และไม่อัปโหลดรูปซ้ำ", desktop)
        product = desktop.split("def _multi_flow_worker", 1)[1]
        safe_stop = product.split("if any(marker in failure_text", 1)[1].split("if generation_attempt >=", 1)[0]
        self.assertIn("raise RuntimeError", safe_stop)
        self.assertNotIn("stop_flow_generation", safe_stop)
        self.assertNotIn("open_flow", safe_stop)

    def test_flow_refreshes_a_hundred_percent_result_once_without_resubmitting(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = flow.split("async function readGenerationState()", 1)[1]
        refresh = flow.split("async function refreshCompletedFlowResult(monitor)", 1)[1].split(
            "async function readGenerationState()", 1
        )[0]
        candidate = inspect.split("const reachedHundredWithoutPlayableResult", 1)[1].split(
            "const completedAfterObservedProgress", 1
        )[0]
        self.assertIn("generationHighestProgress >= 100", candidate)
        self.assertIn("!Number(monitor?.resultRefreshedAt || 0)", candidate)
        self.assertIn("if(await refreshCompletedFlowResult(monitor))return;", candidate)
        self.assertIn("!hasStrongActiveGeneration", candidate)
        self.assertIn("Google Flow ขึ้น 100% แล้ว • รีเฟรชหนึ่งครั้ง", refresh)
        self.assertIn("Number(row.resultRefreshedAt||0)===claimedAt", refresh)
        self.assertIn("owns(stored.smartpostFlowMonitor)", refresh)
        self.assertIn("automationPaused", refresh)
        self.assertIn("!current.activeProgress && !current.activeRenderControl", refresh)
        self.assertIn("resultRefreshedAt:claimedAt", refresh)
        delayed = refresh.split("setTimeout(async()=>{", 1)[1].split("},450)", 1)[0]
        self.assertIn("if(await verify())location.reload()", delayed)
        self.assertEqual(refresh.count("location.reload()"), 1)
        self.assertLess(refresh.index("resultRefreshedAt:claimedAt"), refresh.index("setTimeout(async()=>{"))
        for code in (candidate, refresh):
            self.assertNotIn("CLICK_FLOW_GENERATE", code)
            self.assertNotIn("fillPrompt(", code)
            self.assertNotIn("physicalFileDrop(", code)
        # Native DOM + asynchronous late-cancel/owner/activity and repeat-budget
        # behavior is exercised by test_refresh_safety_399, not inferred here
        # from the historical unguarded timeout's exact formatting.

    def test_flow_downloads_from_the_finished_video_tile_context_menu(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        locator = background.split("async function locateFlowDownloadPoint", 1)[1].split(
            "async function downloadFlowResult", 1
        )[0]
        downloader = background.split("async function downloadFlowResult", 1)[1].split(
            "async function inspectFlowResultDom", 1
        )[0]
        self.assertIn("flow-grid-tile-container,flow-video-tile", locator)
        self.assertIn("openVideoContextMenu: true", locator)
        self.assertIn("openVideoMenu: true", locator)
        self.assertIn("menuDownload: true", locator)
        self.assertIn("ดาวน์โหลดโปรเจ็กต์", locator)
        self.assertIn("if (point.openVideoContextMenu)", downloader)
        self.assertIn('await clickPoint(point, false, "right")', downloader)
        self.assertIn("if (point.openVideoMenu)", downloader)
        self.assertIn("if (!point?.menuDownload)", downloader)
        self.assertIn("await clickPoint(point)", downloader)
        self.assertIn("720p.*(?:ขนาดดั้งเดิม|ต้นฉบับ|original)", downloader)
        self.assertIn("watchNativeFlowDownload", downloader)
        self.assertIn("pendingDownload.downloadId", downloader)
        self.assertIn("alreadyStarted: true", downloader)
        self.assertIn("smartpostFlowDownloadReceipt", downloader)

    def test_flow_auto_downloads_the_finished_video_before_reporting_complete(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        inspect = flow.split("async function inspectGenerationState()", 1)[1].split(
            '(".copy-prompt").addEventListener', 1
        )[0]
        self.assertIn('type: "AUTO_DOWNLOAD_FLOW_RESULT"', inspect)
        self.assertIn("ค้นหาเมนูดาวน์โหลดอัตโนมัติอีกครั้ง", inspect)
        self.assertLess(inspect.index('type: "AUTO_DOWNLOAD_FLOW_RESULT"'), inspect.rindex("await report(step, message"))
        self.assertIn('message?.type === "AUTO_DOWNLOAD_FLOW_RESULT"', background)
        self.assertIn("alreadyCompleted: true", background)

    def test_flow_never_generates_without_image_and_prompt_in_the_same_composer(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        auto = flow.split("async function autoPrepare()", 1)[1]
        verify = auto.split("if (generateButton) {", 1)[1].split("generationBaseline = generationSnapshot();", 1)[0]
        self.assertIn("const mediaStillAttached = Boolean(promptHasAttachedMedia())", verify)
        self.assertNotIn("attachDebug?.composerProof === true", verify)
        self.assertIn("const promptStillReady", verify)
        self.assertIn("if (!mediaStillAttached || !promptStillReady)", verify)
        self.assertIn("ต้องเห็นรูปแนบและ Prompt อยู่ในช่องแชทเดียวกัน", verify)

    def test_flow_slate_prompt_uses_only_trusted_text_input(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        fill = flow.split("async function fillPrompt()", 1)[1].split("function findNewProjectButton()", 1)[0]
        self.assertIn('type: "TYPE_FLOW_PROMPT"', fill)
        self.assertIn("if (!inserted) return false;", fill)
        self.assertNotIn('type: "FILL_FLOW_SLATE"', fill)
        slate = fill.split('const isSlateEditor = editor.getAttribute("data-slate-editor") === "true";', 1)[1]
        self.assertIn("if (!inserted && !isSlateEditor)", slate)

    def test_removed_extension_stops_orphan_heartbeats(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        content = (ROOT / "browser_extension" / "content.js").read_text(encoding="utf-8")
        self.assertIn("const extensionHeartbeatTimer = setInterval", flow)
        self.assertIn("clearInterval(extensionHeartbeatTimer)", flow)
        self.assertIn("const extensionTickTimer = setInterval", content)
        self.assertIn("clearInterval(extensionTickTimer)", content)

    def test_flow_recognizes_cancel_as_a_reference_remove_control_and_prunes_duplicates(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("async function removeDuplicatePromptReferences()", flow)
        self.assertIn("removalButtons.slice(0, -1)", flow)
        self.assertIn("const scope = composer || document", flow)
        self.assertIn("close|cancel|remove|delete", flow)
        self.assertIn("close|cancel|remove|delete", background)
        self.assertIn('reason: attachmentControlAttached ? "attachment_control_without_media" : "composer_missing"', flow)
        self.assertNotIn("if (attachmentControlAttached) return true", background)
        self.assertIn("ready: visuals.length > 0", flow)

    def test_flow_generate_uses_scored_composer_bound_single_click(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        generate = background.split('message?.type === "CLICK_FLOW_GENERATE"', 1)[1].split('sendResponse({ ok: false, error: "unknown_message"', 1)[0]
        self.assertIn('.ProseMirror[contenteditable="true"]', generate)
        finder = background.split("function resolveFlowGenerateClickTarget(", 1)[1].split("const AI_WEB =", 1)[0]
        self.assertIn("score += 40", finder)
        self.assertIn("score += 25", finder)
        self.assertIn("button.contains(top)", finder)
        self.assertIn("func: resolveFlowGenerateClickTarget", generate)
        self.assertIn('method: "single_cdp_mouse_click"', generate)
        self.assertNotIn("keyboardFallback", generate)
        self.assertNotIn("__reactProps$", generate)

    def test_failed_flow_retry_resets_only_the_current_workspace_in_the_same_tab(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        start = background.index("async function stopFlowGeneration")
        end = background.index("async function openFlowResultCard", start)
        stop = background[start:end]
        self.assertIn("delete checkpoints[checkpointKey]", stop)
        self.assertIn("await chrome.storage.local.remove(flowTabKey)", stop)
        self.assertIn("url: FLOW_URL, active: true", stop)
        self.assertIn("resetWorkspace: true, reusedTab: true", stop)
        self.assertNotIn("chrome.tabs.create", stop)

    def test_flow_upload_uses_hidden_input_without_opening_windows_file_picker(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        start = source.index('if (message?.type === "OPEN_FLOW_MEDIA_UPLOAD")')
        end = source.index('if (message?.type === "CLICK_FLOW_AGENT")', start)
        upload = source[start:end]
        self.assertIn("Input.dispatchMouseEvent", upload)
        self.assertIn("type, x: point.x, y: point.y", upload)
        self.assertIn('"Page.setInterceptFileChooserDialog", { enabled: true }', upload)
        self.assertIn("type, x: uploadPoint.x, y: uploadPoint.y", upload)
        self.assertIn('method !== "Page.fileChooserOpened"', upload)
        self.assertIn("DOM.setFileInputFiles", upload)
        self.assertIn("rightsRequired", upload)
        self.assertIn("uploadActionClicked: false", upload)
        self.assertIn("เมนู\\s*เพิ่มสื่อ", upload)
        self.assertIn("for (let attempt = 0; attempt < 12; attempt += 1)", upload)

    def test_flow_legal_consent_is_live_only_and_resumes_same_helper_once(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertIn('window.dispatchEvent(new Event("smartpost-flow-resume"));', source)
        self.assertIn("function activeRightsDialog()", source)
        self.assertIn("function runAutoPrepareOnce()", source)
        self.assertIn('window.addEventListener("smartpost-flow-resume"', source)
        self.assertIn("waitingForRights: true", source)
        self.assertIn('if (hasRightsDialog) {', source)
        confirmation = source.split("function confirmationKind", 1)[1].split("async function dismissNonLegalOverlay", 1)[0]
        self.assertIn('if (activeRightsDialog()) return "legal_rights";', confirmation)
        self.assertNotIn('if (/ฉันยอมรับ', confirmation)

    def test_flow_preserves_rights_gate_detected_during_trusted_upload(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        prepare = source.split("async function autoPrepare()", 1)[1].split(
            "function stopGenerationMonitor()", 1
        )[0]
        self.assertIn("const uploadRightsRequired", prepare)
        self.assertIn("uploadDebug?.rightsRequired", prepare)
        self.assertIn("uploadDebug?.mediaState?.rightsRequired", prepare)
        self.assertIn('confirmation === "legal_rights" || uploadRightsRequired', prepare)
        self.assertIn("!hasRightsDialog", prepare)
        self.assertLess(prepare.index("uploadRightsRequired"), prepare.index('const step = confirmation === "credit"'))

    def test_flow_trusted_attachment_stops_while_live_rights_dialog_is_open(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = source.split('if (message?.type === "ATTACH_LATEST_FLOW_MEDIA")', 1)[1].split('if (message?.type === "OPEN_FLOW_MEDIA_UPLOAD")', 1)[0]
        self.assertIn("const activeRightsDialog = async () =>", attach)
        self.assertIn("if (await activeRightsDialog())", attach)
        self.assertIn("FLOW_RIGHTS_CONFIRMATION_REQUIRED", attach)
        first_physical_click = attach.index("const physicalClick = async")
        guard = attach.index("if (await activeRightsDialog())", first_physical_click)
        debugger_attach = attach.index("chrome.debugger.attach", first_physical_click)
        self.assertLess(guard, debugger_attach)

    def test_flow_rights_confirmation_waits_for_owner_without_stopping_attempt(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        wait = source.split("def _wait_flow_step", 1)[1].split("def _wait_download", 1)[0]
        rights = wait.split('if step == "awaiting_rights_confirmation":', 1)[1].split('if rights_confirmation_waiting:', 1)[0]
        self.assertIn('self.events.put(("flow_rights_required"', rights)
        self.assertIn("continue", rights)
        self.assertNotIn('queue_extension_command("stop_flow_generation"', rights)
        resolution = wait.split('if rights_confirmation_waiting:', 1)[1].split('if web_action_waiting:', 1)[0]
        self.assertIn('queue_extension_command("resume_flow_workspace"', resolution)
        self.assertNotIn('queue_extension_command("stop_flow_generation"', resolution)

    def test_flow_keeps_the_agent_submission_path_single_action(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertNotIn("await ensureAgentMode();", flow)
        self.assertNotIn('key: "Enter", code: "Enter"', background)
        self.assertIn("single_cdp_mouse_click", background)

    def test_flow_does_not_double_submit_mouse_and_enter(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        click = source.split('if (message?.type === "CLICK_FLOW_GENERATE")', 1)[1].split('sendResponse({ ok: false, error: "unknown_message"', 1)[0]
        self.assertEqual(click.count('type: "mousePressed"'), 1)
        self.assertEqual(click.count('type: "mouseReleased"'), 1)
        self.assertNotIn("Input.dispatchKeyEvent", click)
        self.assertNotIn("keyboardFallback", click)
        self.assertNotIn("__reactProps$", click)

    def test_flow_credit_approval_uses_one_trusted_click(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        approval = source.split("async function approveFlowCreditOnce", 1)[1].split("async function stopFlowGeneration", 1)[0]
        self.assertNotIn("button.click?.()", approval)
        self.assertEqual(approval.count('type: "mousePressed"'), 1)
        self.assertEqual(approval.count('type: "mouseReleased"'), 1)
        self.assertNotIn("approvalStillVisible", approval)
        self.assertIn("document.elementFromPoint", approval)
        self.assertIn("const fallback = false", approval)

    def test_flow_credit_approval_prefers_current_question_and_clickable_wrapper(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        approval = source.split("async function approveFlowCreditOnce", 1)[1].split("async function stopFlowGeneration", 1)[0]
        always = 'latest(controls.filter(({ label }) => /^(?:อนุมัติเสมอ|always approve|approve always)$/i.test(label)))'
        persistent = 'latest(controls.filter(({ label }) => /อนุมัติ/.test(label) && /ไม่ต้องถามอีก/.test(label)'
        plain = 'latest(controls.filter(({ label }) => /^(?:อนุมัติ|approve)$/i.test(label)))'
        self.assertIn(always, approval)
        self.assertIn(plain, approval)
        self.assertIn(persistent, approval)
        self.assertLess(approval.index(always), approval.index(persistent))
        self.assertLess(approval.index(persistent), approval.index(plain))
        self.assertIn("for (let depth = 0; cursor && depth < 8", approval)
        self.assertIn("[jsaction],[data-mdc-dialog-action]", approval)
        self.assertIn("cursor.parentElement && getComputedStyle(cursor.parentElement).cursor", approval)
        self.assertIn('const tabIndexAttribute = cursor.getAttribute?.("tabindex")', approval)
        self.assertIn("tabIndexAttribute === null || tabIndexAttribute === undefined", approval)
        self.assertNotIn('const tabIndex = Number(cursor.getAttribute?.("tabindex"))', approval)

    def test_flow_status_distinguishes_upload_from_real_generation(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertIn("ยังไม่ใช่วิดีโอ • กำลังกดสร้าง", source)
        self.assertIn('clickResult?.ok ? "submission_sent" : "submission_unconfirmed"', source)
        self.assertIn("รอสัญญาณคิวหรือเปอร์เซ็นต์ก่อนนับว่าเริ่มสร้าง", source)
        self.assertNotIn('report("generation_started"', source)

    def test_flow_waits_for_slow_reference_validation_before_missing_generate(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("attempt < 180 && !generateButton", flow)
        self.assertIn("do not reattach, reload, or open another project", flow)
        finder = flow.split("function findGenerateButton()", 1)[1].split("function generationSnapshot()", 1)[0]
        self.assertIn("right.getBoundingClientRect().top - left.getBoundingClientRect().top", finder)
        clicker = background.split("function resolveFlowGenerateClickTarget(", 1)[1].split("const AI_WEB =", 1)[0]
        self.assertIn("element.disabled", clicker)
        self.assertIn("b.score - a.score", clicker)

    def test_flow_rechecks_live_prompt_after_asset_and_settings_rerender(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        prepare = flow.split("async function autoPrepare()", 1)[1].split("async function monitorGeneration()", 1)[0]
        self.assertIn("const liveEditorBeforeFill = findPromptEditor()", prepare)
        self.assertIn("promptReady = flowPromptMatches(livePromptTextBeforeFill, pkg.video_prompt)", prepare)
        self.assertNotIn("promptReady = livePromptTextBeforeFill.includes", prepare)
        self.assertLess(prepare.index("ensureFlowVideoSettings()"), prepare.index("const liveEditorBeforeFill"))
        self.assertLess(prepare.index("const liveEditorBeforeFill"), prepare.index("if (!promptReady)"))
        self.assertIn('"waiting_generate_enabled"', prepare)
        self.assertIn("กำลังรอปุ่มสร้างเปิดใช้งานในหน้าเดิม", prepare)

    def test_flow_recognizes_current_agent_failed_retry_card(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        snapshot = flow.split("function generationSnapshot()", 1)[1].split("async function saveFlowProjectCheckpoint", 1)[0]
        inspect = flow.split("async function inspectGenerationState()", 1)[1].split('(\".copy-prompt\").addEventListener', 1)[0]
        self.assertIn("Agent\\s*(?:ทำงาน)?ไม่สำเร็จ", snapshot)
        self.assertIn("Agent\\s*(?:ทำงาน)?ไม่สำเร็จ", inspect)
        self.assertIn("generationFailureChecks >= 3", inspect)

    def test_flow_project_handoff_does_not_force_duplicate_helper(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        handoff = background.split("const handoffProjectTab", 1)[1].split("const [injection]", 1)[0]
        self.assertNotIn("ensureFlowHelper(projectTab.id, true)", handoff)
        self.assertNotIn("ensureFlowHelper(flowTabId, true)", handoff)
        self.assertIn("which could race a second injected helper", handoff)

    def test_flow_can_download_a_blob_player_without_visible_download_button(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("if (!button && !videoUrl) return null;", background)
        self.assertIn('/^(?:blob:|data:)/i.test(point.videoUrl', background)
        self.assertNotIn("if (!button && !/^https?:/i.test(videoUrl)) return null;", background)

    def test_flow_download_prefers_the_exact_completed_checkpoint_tab(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        flow_tab_lookup = background.split("async function flowTabForJob", 1)[1].split("async function approveFlowCreditOnce", 1)[0]
        self.assertIn('"smartpostFlowCheckpoints"', flow_tab_lookup)
        self.assertIn("checkpointTab", flow_tab_lookup)
        self.assertLess(flow_tab_lookup.index("if (checkpointTab?.id)"), flow_tab_lookup.index("const storedId"))
        self.assertIn("pickHealthyFlowProjectTab(preferred, preferred)", flow_tab_lookup)
        self.assertNotIn("pickHealthyFlowProjectTab(tabs, preferred)", flow_tab_lookup)

    def test_flow_credit_history_cannot_mask_live_progress(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertIn("!hasActiveGeneration && !observedActiveGeneration", source)
        self.assertNotIn("queued|กำลังสร้าง|กำลังประมวลผล", source)

    def test_flow_current_credit_question_wins_over_old_no_charge_failure(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        self.assertIn("explicitUnchargedFailure", inspect)
        self.assertIn("latestVisibleFailureCard?.hasNoCharge", inspect)
        self.assertLess(inspect.index('else if (confirmation === "credit")'), inspect.index("else if (currentExplicitUnchargedFailure"))
        self.assertIn("พบรูปเดิมแล้วและรออนุมัติสร้างต่อในโปรเจกต์เดิม", inspect)
        self.assertIn("currentVisibleFailure && explicitUnchargedFailure && newFailure && isFailed", inspect)

    def test_current_stop_control_wins_over_old_flow_failure_history(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        confirmation = source.split("function confirmationKind(pageText)", 1)[1].split("async function dismissNonLegalOverlay", 1)[0]
        self.assertIn("current on-screen Stop control", confirmation)
        self.assertLess(confirmation.index("current on-screen Stop control"), confirmation.index("latestCreditQuestionAt"))
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        self.assertIn("const isBusy = hasStrongActiveGeneration", inspect)
        current = inspect.split("const currentExplicitUnchargedFailure", 1)[1].split("const stableUnchargedFailure", 1)[0]
        self.assertIn("&& !isBusy", current)

    def test_current_explicit_uncharged_failure_waits_while_busy_or_queued(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        self.assertIn("const currentExplicitUnchargedFailure", inspect)
        current = inspect.split("const currentExplicitUnchargedFailure", 1)[1].split("const stableUnchargedFailure", 1)[0]
        self.assertIn("currentVisibleUnchargedFailure", current)
        self.assertIn("&& !isBusy", current)
        self.assertIn("&& !isQueued", current)
        self.assertIn("currentExplicitUnchargedFailure\n      || (newFailure", inspect)
        self.assertIn("currentExplicitUnchargedFailure && generationFailureChecks >= 3", inspect)
        self.assertLess(
            inspect.index("currentExplicitUnchargedFailure && generationFailureChecks >= 3"),
            inspect.index("else if (isQueued)")
        )
        self.assertLess(inspect.index('else if (confirmation === "credit")'), inspect.index("currentExplicitUnchargedFailure && generationFailureChecks >= 3"))

    def test_flow_result_card_alone_is_not_completion(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertIn("hasDownload && monitorAge >= 30000", source)
        self.assertIn("snapshot.resultCardCount > Number(generationBaseline.resultCardCount || 0)", source)

    def test_flow_accepts_new_result_card_after_observed_progress_becomes_stably_complete(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertIn("completedCardAfterObservedProgress", source)
        self.assertIn("generationHighestProgress > 0", source)
        self.assertIn("resultCardsStableAfterProgress", source)
        self.assertIn("15 * 1000", source)
        self.assertIn("snapshot.resultCardCount > Number(generationBaseline.resultCardCount || 0)", source)
        self.assertIn("|| completedCardAfterObservedProgress", source)

    def test_inspect_flow_preserves_live_monitor_baseline_and_progress(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("if (matchingInspection)", 1)[1].split("const monitorStore", 1)[0]
        self.assertIn('chrome.storage.local.get("smartpostFlowMonitor")', inspect)
        self.assertIn("generationBaseline = monitorMatches", inspect)
        self.assertIn("observedActiveGeneration = monitorMatches", inspect)
        self.assertIn("if (monitorMatches || recoverActiveCheckpoint) monitorGeneration()", inspect)
        self.assertNotIn("generationBaseline = null;\n      observedActiveGeneration = false", inspect)

    def test_flow_has_only_one_non_overlapping_generation_monitor(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertIn("let generationMonitorTimer = null", source)
        self.assertIn("let generationMonitorActive = false", source)
        monitor = source.split("function monitorGeneration()", 1)[1].split("async function inspectGenerationState()", 1)[0]
        self.assertIn("if (generationMonitorActive) return", monitor)
        self.assertIn("generationMonitorTimer = setTimeout(inspectNext, nextGenerationMonitorDelay())", monitor)
        self.assertIn("generationMonitorTimer = setTimeout(inspectNext, 2500)", monitor)
        self.assertIn("Date.now() - monitorStartedAt >= 30 * 60 * 1000", monitor)
        self.assertIn("stopGenerationMonitor()", monitor)
        self.assertNotIn("setInterval(async", monitor)

    def test_flow_high_demand_queue_is_active_and_never_a_retry_signal(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        self.assertIn("const isQueued", inspect)
        self.assertIn("waiting\\s+in\\s+the\\s+queue", inspect)
        self.assertIn("high\\s+demand", inspect)
        self.assertIn("snapshot.activeProgress || isBusy || isQueued", inspect)
        self.assertIn("else if (isQueued)", inspect)
        self.assertIn("จะรอในโปรเจกต์เดิมโดยไม่สร้างซ้ำ", inspect)
        self.assertIn("&& !isQueued", inspect)

    def test_flow_thai_queued_response_stays_in_the_same_project(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        queued = inspect.split("const queuedStateIndex =", 1)[1].split("const failureStateIndex", 1)[0]
        self.assertIn("(?:ได้รับการ)?จัดคิว", queued)
        self.assertIn("กำลังรอคิว", queued)
        self.assertIn("รอคิว", queued)

    def test_flow_semantic_retry_label_is_not_hidden_by_material_icon_text(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        labels = inspect.split("const allButtonLabels", 1)[1].split("const buttonLabels", 1)[0]
        self.assertIn('button.getAttribute("aria-label")', labels)
        self.assertIn('button.getAttribute("title")', labels)
        self.assertIn("button.innerText", labels)
        self.assertIn("button.textContent", labels)
        self.assertLess(labels.index('button.getAttribute("aria-label")'), labels.index("button.innerText"))
        snapshot = source.split("function generationSnapshot()", 1)[1].split("async function saveFlowProjectCheckpoint", 1)[0]
        retry = snapshot.split("const hasRetry", 1)[1].split("const hasNoCharge", 1)[0]
        self.assertIn("ลองอีกครั้ง", retry)
        self.assertIn("retry", retry)

    def test_flow_exact_current_queue_phrase_is_weak_and_waits_without_resubmit(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        queue_detection = inspect.split("const queuedStateIndex", 1)[1].split("const failureStateIndex", 1)[0]
        self.assertIn("(?:currently|still)\\s+(?:waiting\\s+)?in\\s+the\\s+queue", queue_detection)
        self.assertIn("const hasStrongActiveGeneration", inspect)
        self.assertIn("const hasWeakQueuedNarrative", inspect)
        queue_branch = inspect.split("} else if (isQueued) {", 1)[1].split("} else if", 1)[0]
        self.assertIn('step = "generation_in_progress"', queue_branch)
        self.assertIn("จะรอในโปรเจกต์เดิมโดยไม่สร้างซ้ำ", queue_branch)
        self.assertNotIn("CLICK_FLOW_GENERATE", queue_branch)
        self.assertNotIn("location.reload", queue_branch)
        self.assertNotIn("dropReferenceImage", queue_branch)

    def test_flow_policy_terminal_decision_rejects_busy_or_queued_state(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        decision = source.split("function evaluateFlowPolicyFailure", 1)[1].split("function generationSnapshot", 1)[0]
        self.assertIn("state.hasStrongActiveGeneration || state.isQueued || state.isBusy", decision)
        self.assertIn("state.currentVisiblePolicyFailure", decision)
        self.assertIn("active ? \"generation_in_progress\"", decision)
        grace = inspect.split("const policyFailureGraceElapsed", 1)[1].split("const currentExplicitUnchargedFailure", 1)[0]
        self.assertIn("30 * 1000", grace)
        self.assertIn("const terminalPolicyDecision = evaluateFlowPolicyFailure", inspect)
        policy_branch = "terminalPolicyDecision.terminal"
        self.assertIn(policy_branch, inspect)
        self.assertIn("FLOW_POLICY_BLOCKED", inspect)
        self.assertLess(inspect.index(policy_branch), inspect.index("else if (isQueued)"))
        current_failure = inspect.split("currentExplicitUnchargedFailure && generationFailureChecks >= 3", 1)[1].split(") {", 1)[0]
        self.assertIn("!isPolicyFailure", current_failure)

    def test_flow_newer_busy_text_cannot_be_suppressed_by_old_no_charge_card(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        busy = inspect.split("const isBusy", 1)[1].split("const noCredits", 1)[0]
        self.assertIn("hasStrongActiveGeneration", busy)
        self.assertIn("hasWeakBusyNarrative && !hasWeakQueuedNarrative", busy)
        self.assertNotIn("explicitUnchargedFailure", busy)
        stable = inspect.split("const stableUnchargedFailure", 1)[1].split("const stalledProgress", 1)[0]
        self.assertIn("currentVisibleUnchargedFailure", stable)
        self.assertIn("isFailed", stable)
        self.assertIn("!isBusy", stable)
        self.assertIn("!isQueued", stable)

    def test_flow_new_policy_failure_with_newer_queue_prose_stays_active(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        new_failure = inspect.split("const newFailure", 1)[1].split("const policyFailureCandidate", 1)[0]
        self.assertIn("snapshot.failureCount > generationBaseline.failureCount", new_failure)
        self.assertIn("!baselineFailureFingerprints.has(policyFailureFingerprint)", new_failure)
        self.assertIn("snapshot.visibleFailureCardCount", new_failure)
        self.assertIn("generationBaseline?.visibleFailureCardCount", new_failure)
        self.assertIn("newPolicyFailureFingerprint || newVisibleFailureCount", new_failure)
        same_card = new_failure.split("const hasSameCardPolicyProof", 1)[1].split("const policyFailureFingerprint", 1)[0]
        self.assertIn("latestVisibleFailureCard.hasNoCharge === true", same_card)
        self.assertIn("latestVisibleFailureCard.hasRetry === true", same_card)
        initial = inspect.split("const initialPolicyDecision", 1)[1].split("const policyFailureCandidate", 1)[0]
        self.assertIn("isQueued", initial)
        self.assertIn("isBusy", initial)
        terminal = inspect.split("const terminalPolicyDecision", 1)[1].split("const hasVideoResult", 1)[0]
        self.assertIn("isQueued", terminal)
        self.assertIn("isBusy", terminal)

    def test_flow_old_policy_baseline_plus_new_queue_remains_waiting(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        currentness = inspect.split("const newPolicyFailureFingerprint", 1)[1].split("const policyFailureCategory", 1)[0]
        self.assertIn("!baselineFailureFingerprints.has(policyFailureFingerprint)", currentness)
        self.assertIn("newPolicyFailureFingerprint || newVisibleFailureCount", currentness)
        # Scenario truth table: an unchanged baseline card is historical;
        # either a new fingerprint or a higher failure count is current.
        def is_current(card_fp, baseline_fps, current_count, baseline_count):
            return bool(card_fp) and (card_fp not in baseline_fps or current_count > baseline_count)
        self.assertFalse(is_current("old-policy", {"old-policy"}, 1, 1))
        self.assertTrue(is_current("new-policy", {"old-policy"}, 2, 1))
        self.assertTrue(is_current("same-policy", {"same-policy"}, 2, 1))
        queue_branch = inspect.split("} else if (isQueued) {", 1)[1].split("} else if", 1)[0]
        self.assertIn('step = "generation_in_progress"', queue_branch)
        self.assertIn("โปรเจกต์เดิมโดยไม่สร้างซ้ำ", queue_branch)
        self.assertNotIn("generation_failed", queue_branch)

    def test_flow_reports_visible_policy_card_fingerprint_and_category(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        snapshot = source.split("function generationSnapshot()", 1)[1].split("async function saveFlowProjectCheckpoint", 1)[0]
        self.assertIn("visibleFailureCards", snapshot)
        self.assertIn("semanticControls", snapshot)
        self.assertIn("hasRetry", snapshot)
        self.assertIn("hasNoCharge", snapshot)
        self.assertIn("latestVisibleFailureText", snapshot)
        self.assertIn("latestFailureCardFingerprint", snapshot)
        self.assertIn("faces?|facial", snapshot)
        bounded_face = re.compile(r"\b(?:faces?|facial)\b", re.IGNORECASE)
        self.assertIsNotNone(bounded_face.search("face"))
        self.assertIsNotNone(bounded_face.search("facial policy"))
        self.assertIsNone(bounded_face.search("interface failure"))
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        self.assertIn('failure_code: silentSubmission ? "FLOW_SEND_REVIEW" : (terminalPolicyFailure?.code || "")', inspect)
        self.assertIn('policy_failure_category: terminalPolicyFailure?.category || ""', inspect)
        self.assertIn('failure_card_fingerprint: terminalPolicyFailure?.fingerprint || ""', inspect)
        self.assertIn('"face_or_public_figure"', inspect)

    def test_flow_policy_grace_is_keyed_to_the_exact_visible_card_fingerprint(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        first_seen = inspect.split("const samePolicyFailureAsMonitor", 1)[1].split("const policyFailureGraceElapsed", 1)[0]
        self.assertIn("monitor?.policyFailureFingerprint", first_seen)
        self.assertIn("=== policyFailureFingerprint", first_seen)
        self.assertIn("samePolicyFailureAsMonitor ? Number(monitor?.policyFailureFirstSeenAt", first_seen)
        monitor_write = inspect.split("smartpostFlowMonitor: {", 1)[1].split("let downloadedPath", 1)[0]
        self.assertIn('policyFailureFingerprint: policyFailureCandidate ? policyFailureFingerprint : ""', monitor_write)

    def test_unrelated_generation_failure_never_reports_policy_code_from_old_card(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        terminal_branch = inspect.split("} else if (terminalPolicyDecision.terminal", 1)[1].split("} else if", 1)[0]
        self.assertIn('code: "FLOW_POLICY_BLOCKED"', terminal_branch)
        silent_timeout = inspect.split("if (silentSubmission) {", 1)[1].split("if (monitor &&", 1)[0]
        self.assertNotIn("terminalPolicyFailure =", silent_timeout)
        report = inspect.split("await report(step, message, {", 1)[1].split("});", 1)[0]
        self.assertIn('failure_code: silentSubmission ? "FLOW_SEND_REVIEW" : (terminalPolicyFailure?.code || "")', report)
        self.assertNotIn('step === "generation_failed" && isPolicyFailure', report)

    def test_flow_generate_transaction_uses_one_physical_action_only(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        submit = flow.split('if (step === "ready_to_generate" || step === "waiting_generate_enabled")', 1)[1].split('await report("generate_button_missing"', 1)[0]
        handler = background.split('if (message?.type === "CLICK_FLOW_GENERATE")', 1)[1].split('sendResponse({ ok: false, error: "unknown_message"', 1)[0]
        self.assertIn('type: "CLICK_FLOW_GENERATE"', submit)
        self.assertNotIn("generateButton.click()", submit)
        self.assertIn('method: "single_cdp_mouse_click"', handler)
        self.assertNotIn("Input.dispatchKeyEvent", handler)
        self.assertNotIn("__reactProps$", handler)

    def test_flow_silent_submission_waits_in_same_project(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("const silentSubmission", 1)[1].split("if (monitor &&", 1)[0]
        self.assertIn('step = "error"', inspect)
        self.assertIn("FLOW_SEND_REVIEW", inspect)
        self.assertIn("&& !isQueued", inspect)
        self.assertIn("&& !isBusy", inspect)
        self.assertNotIn('step = "generation_failed"', inspect)
        self.assertNotIn("ใหม่อัตโนมัติ", inspect)

    def test_flow_recovers_newest_result_from_exact_active_checkpoint_after_helper_reload(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn('inspectOnly.checkpointStatus === "active"', flow)
        self.assertIn("currentSnapshot.resultCardCount > 0", flow)
        self.assertIn("Math.max(0, currentSnapshot.resultCardCount - 1)", flow)
        self.assertIn("checkpointStatus: String(checkpoint?.status || \"\")", background)
        self.assertIn("checkpointBaseline: checkpoint?.baseline || null", background)
        self.assertIn("...(generationBaseline ? { baseline: generationBaseline } : {})", flow)

    def test_flow_helper_hot_update_replaces_stale_helper_without_reloading_project(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("host.dataset.extensionVersion = helperVersion", flow)
        self.assertIn('existingHost?.dataset?.helperBuild === helperBuild', flow)
        self.assertIn("existingHost?.remove()", flow)
        ensure = background.split("async function ensureFlowHelper", 1)[1].split("async function assertStoryCheckpointOwner", 1)[0]
        self.assertIn("flowHelperInstallPromises.get(tabId)", ensure)
        self.assertIn("installedHelper.build === FLOW_HELPER_BUILD", ensure)
        self.assertIn('window.dispatchEvent(new Event("smartpost-flow-resume"))', ensure)
        self.assertIn('document.getElementById("smartpost-flow-helper-host")?.remove()', ensure)
        self.assertNotIn("chrome.tabs.reload", ensure)
        self.assertNotIn("chrome.tabs.create", ensure)

    def test_browser_progress_is_filtered_by_owner_tab_and_run_before_bridge(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        flow_handler = background.split('if (message?.type === "FLOW_PROGRESS")', 1)[1].split('if (message?.type === "CHATGPT_PROGRESS")', 1)[0]
        ai_handler = background.split('if (message?.type === "CHATGPT_PROGRESS")', 1)[1].split('if (message?.type === "GET_CHATGPT_SOURCE_IMAGE")', 1)[0]
        self.assertIn("flowProgressOwnership(progress, sender.tab?.id)", flow_handler)
        self.assertIn("tab_id: Number(sender.tab?.id || 0)", flow_handler)
        self.assertIn("aiProgressOwnership(progress, sender.tab?.id)", ai_handler)
        self.assertIn("stale_flow_tab", background)
        self.assertIn("stale_flow_run", background)
        self.assertIn("stale_ai_tab", background)
        self.assertIn("stale_ai_run", background)

    def test_extension_bridge_uses_session_capability_without_url_secrets(self):
        bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        popup = (ROOT / "browser_extension" / "popup.js").read_text(encoding="utf-8")
        self.assertIn("secrets.token_urlsafe(32)", bridge)
        self.assertIn("X-SmartFlow-Token", bridge)
        self.assertIn('"extension_token": capability', bridge)
        self.assertIn('"X-SmartFlow-Token": BRIDGE_TOKEN', background)
        self.assertIn("async function bridgeFetch", background)
        self.assertEqual(background.count('fetch(`${BRIDGE}/api/extension/heartbeat`'), 1)
        self.assertNotIn("extension_token=", background)
        self.assertNotIn("X-SmartFlow-Token", popup)
        self.assertNotIn("/api/products/import", popup)
        self.assertIn('type: "IMPORT_PRODUCTS"', popup)

    def test_extension_commands_are_run_and_lease_scoped(self):
        bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        chatgpt = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        self.assertIn("COMMAND_LEASE_SECONDS", bridge)
        self.assertIn('"lease_token": lease_token', bridge)
        self.assertIn('"run_id": resolved_run_id', bridge)
        self.assertIn("lease_token: String(command.lease_token || \"\")", background)
        self.assertIn("await rememberCommandRun(command)", background)
        self.assertIn('run_id: String(pkg?.run_id || "")', flow)
        self.assertIn("run_id: activeRunId", chatgpt)

    def test_extension_version_mismatch_pauses_once_and_never_self_reloads(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        heartbeat = background.split("async function heartbeat()", 1)[1].split("async function acknowledge", 1)[0]
        tick = background.split("async function extensionTick()", 1)[1].split("chrome.runtime.onMessage", 1)[0]
        self.assertIn("smartpostExtensionUpdateRequired", heartbeat)
        self.assertIn("return { updateRequired: true", heartbeat)
        self.assertNotIn("chrome.runtime.reload", heartbeat)
        self.assertIn("if (extensionTickPromise) return extensionTickPromise", tick)
        self.assertIn("if (heartbeatState?.updateRequired) return", tick)

    def test_stale_flow_tab_cannot_consume_exact_checkpoint_inspection(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = flow.split("if (matchingInspection)", 1)[1].split("const activeMonitorStore", 1)[0]
        mismatch = inspect.index("expectedProject && currentProject !== expectedProject")
        remove = inspect.index('chrome.storage.local.remove("smartpostFlowInspectOnly")')
        self.assertLess(mismatch, remove)
        self.assertIn("Leave it in storage for the", inspect)

    def test_flow_result_diagnostic_includes_checkpoint_monitor_and_registered_tab(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        inspect = background.split("async function inspectFlowResultDom", 1)[1].split("async function getFlowPackage", 1)[0]
        self.assertIn("extensionState", inspect)
        self.assertIn("registeredTabId", inspect)
        self.assertIn("monitor: stored.smartpostFlowMonitor", inspect)
        self.assertIn("checkpoint: (stored.smartpostFlowCheckpoints || {})[checkpointKey]", inspect)

    def test_flow_download_prefers_newest_completed_video_card(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        download = background.split("async function openFlowResultCard", 1)[1].split("async function inspectFlowResultDom", 1)[0]
        self.assertGreaterEqual(download.count("right.index - left.index"), 2)
        self.assertIn('document.querySelectorAll("video")].reverse().find', download)
        diagnostic = background.split("async function inspectFlowResultDom", 1)[1].split("async function getFlowPackage", 1)[0]
        self.assertLess(diagnostic.index("extensionState:"), diagnostic.index("...(injection?.result || {})"))

    def test_flow_never_treats_a_still_image_download_as_a_video(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("hasExplicitVideoDownload", flow)
        self.assertIn(": false;", flow)
        self.assertNotIn(": Boolean(videoCount || hasDownload)", flow)
        locator = background.split("async function locateFlowDownloadPoint", 1)[1].split("async function downloadFlowResult", 1)[0]
        self.assertIn("A still-image detail page also has a generic Download button", locator)
        self.assertIn("ดาวน์โหลด(?:วิดีโอ|ฉาก)|download (?:video|scene)", locator)

    def test_flow_attachment_does_not_reopen_generic_media_picker(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split('message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1)[0]
        self.assertNotIn('findPoint("composer_media_selector")', attach)
        self.assertNotIn('findPoint("latest_media"', attach)
        self.assertNotIn('findPoint("add_to_prompt")', attach)
        self.assertIn("Never open the generic `+`", attach)

    def test_flow_attachment_never_switches_project_to_find_uploaded_asset(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split('message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1)[0]
        self.assertNotIn('findPoint("empty_project_selector")', attach)
        self.assertNotIn('findPoint("latest_project_option")', attach)
        self.assertNotIn("_select_current_project", attach)
        self.assertIn("ไม่เปิดเมนู + และไม่เลือกรูปซ้ำ", attach)

    def test_flow_attachment_uses_uploaded_card_animate_action_only(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
            'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
        )[0]
        self.assertIn('method = "uploaded_media_create_video"', attach)
        self.assertIn('guard: "animate_media_action"', attach)
        self.assertIn("FLOW_ANIMATE_TARGET_CHANGED_BEFORE_CLICK", attach)
        self.assertIn('const refreshedPoint = await findPoint("animate_media_action")', attach)
        self.assertIn("stablePointCount >= 3", attach)
        self.assertIn('const hoveredPoint = await findPoint("animate_media_action")', attach)
        self.assertIn("FLOW_ANIMATE_CLICK_NOT_ACCEPTED", attach)
        self.assertIn('animateMediaPoint = await findPoint("animate_media_action")', attach)
        self.assertIn('"animate_menu_reused"', attach)
        self.assertIn('"animate_action_click_blocked"', attach)
        self.assertNotIn("}) || tiles.at(-1) || null", attach)
        self.assertNotIn('"active_unselected_click_select_image"', attach)
        self.assertNotIn('if (!mediaPoint.selected)', attach)
        self.assertNotIn('findPoint("add_to_prompt")', attach)

    def test_flow_safe_stop_rearms_only_passive_attachment_proof(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        prepare = flow.split("async function autoPrepare()", 1)[1].split(
            "function stopGenerationMonitor", 1
        )[0]
        waiting = prepare.split("request?.waitingForManualAttachment", 1)[1].split(
            "const dismissedChangelog", 1
        )[0]
        self.assertIn('report("attachment_waiting_manual"', waiting)
        self.assertIn("await watchForManualAttachment(request)", waiting)
        self.assertIn("return true", waiting)
        self.assertNotIn("dropReferenceImage", waiting)
        self.assertNotIn("ATTACH_LATEST_FLOW_MEDIA", waiting)

    def test_open_flow_reuses_same_shot_reference_download(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        open_flow = background.split('command.action === "open_flow"', 1)[1].split(
            'command.action === "resume_flow_workspace"', 1
        )[0]
        self.assertIn('"smartpostFlowReferenceFile"', open_flow)
        self.assertIn("const referenceMatches = Boolean", open_flow)
        self.assertIn("pkg.image_urls?.[0] && !referenceMatches", open_flow)
        self.assertLess(open_flow.index("referenceMatches"), open_flow.index("chrome.downloads.download"))

    def test_flow_enters_video_mode_and_waits_for_automatic_attachment(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
            'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
        )[0]
        self.assertIn('targetKind === "gallery_media_card"', attach)
        self.assertIn('targetKind === "gallery_media_menu"', attach)
        self.assertIn('targetKind === "animate_media_action"', attach)
        self.assertIn("ทำให้เคลื่อนไหว", attach)
        self.assertIn('method = "uploaded_media_create_video"', attach)
        self.assertIn("videoModeActivated = true", attach)
        self.assertIn("const attached = await waitForPromptMediaProof(60)", attach)
        self.assertNotIn('selectorPoint = await findPoint("composer_media_selector")', attach)
        self.assertIn("หยุดโดยไม่เปิดเมนู + และไม่เลือกรูปซ้ำ", attach)

    def test_flow_transitions_are_persisted_as_job_diagnostics(self):
        bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
        self.assertIn("def _append_flow_diagnostic(self, progress):", bridge)
        self.assertIn('log_folder / "flow_extension.jsonl"', bridge)
        self.assertIn("bridge._append_flow_diagnostic(flow_transition)", bridge)

    def test_flow_unlabelled_fullscreen_media_picker_requires_strong_sentinels(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
            'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
        )[0]
        self.assertIn("fullScreenPickerProven", attach)
        self.assertIn("directFileRows.length > 0", attach)
        self.assertIn('"proven_fullscreen_picker"', attach)
        self.assertIn("fullScreenPickerProven ? document.body : null", attach)
        self.assertLess(attach.index("fullScreenPickerProven"), attach.index("fullScreenPickerProven ? document.body : null"))

    def test_flow_responsive_picker_ignores_unrelated_semantic_overlays(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
            'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
        )[0]
        self.assertIn("containsDirectFileRow", attach)
        self.assertIn("mediaAssetLists = assetLists.filter(containsDirectFileRow)", attach)
        self.assertIn("mediaOverlays = overlays.filter(containsDirectFileRow)", attach)
        self.assertIn("controlledMediaScope || mediaAssetLists.at(-1) || mediaOverlays.at(-1)", attach)
        self.assertNotIn("const scope = controlled || assetLists.at(-1) || overlays.at(-1)", attach)

    def test_flow_waits_for_late_attachment_proof_without_clicking_again(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        attach = flow.split("async function attachExistingMediaToPrompt()", 1)[1].split("async function dropReferenceImage()", 1)[0]
        self.assertIn("for (let proofAttempt = 0; proofAttempt < 6", attach)
        self.assertEqual(attach.count('type: "ATTACH_LATEST_FLOW_MEDIA"'), 1)
        self.assertLess(attach.index("for (let proofAttempt"), attach.index("physicalResult?.retryable === false"))

    def test_flow_upload_waits_for_new_asset_instead_of_any_old_gallery_image(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        upload = background.split('message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1)[1].split(
            'message?.type === "CLICK_FLOW_AGENT"', 1
        )[0]
        self.assertIn("galleryAssetIds", upload)
        self.assertIn("uploadBaselineAssetIds", upload)
        self.assertIn("newGalleryAsset", upload)
        self.assertIn("matchingReferenceAsset", upload)
        self.assertIn("promptAttached || newGalleryAsset || matchingReferenceAsset", upload)
        self.assertNotIn("promptAttached || addEnabled || imageCards.length > 0", upload)

    def test_flow_rejects_nano_banana_still_editor_as_wrong_output_type(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        desktop = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("function isFlowProjectWorkspaceUrl", background)
        self.assertIn("Whether an editor contains a video is proved", background)
        project_lookup = background.split("async function findUnambiguousFinishedFlowVideoTab", 1)[1].split(
            "async function waitForTabComplete", 1
        )[0]
        self.assertIn("videoCount", project_lookup)
        self.assertIn("hasVideoDownload", project_lookup)
        self.assertIn('report("wrong_output_type"', flow)
        self.assertIn('"wrong_output_type"', desktop)
        fresh = background.split("async function openFlowTab", 1)[1].split("function normalizeAIProvider", 1)[0]
        self.assertIn('tabs.find((tab) => /\\/edit(?:\\/|$)/i.test', fresh)

    def test_flow_has_one_authoritative_tab_for_auto_and_inspect_work(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        ownership = background.split('message?.type === "IS_ACTIVE_FLOW_TAB"', 1)[1].split('message?.type === "CLICK_NEW_FLOW_PROJECT"', 1)[0]
        self.assertIn("const primaryId", ownership)
        self.assertIn("const fallbackId = !primaryId", ownership)
        self.assertIn("const registeredIds = [primaryId || fallbackId]", ownership)
        inspect = flow.split("if (matchingInspection)", 1)[1].split("const expectedProject", 1)[0]
        self.assertIn('type: "IS_ACTIVE_FLOW_TAB"', inspect)
        self.assertIn("if (!inspectOwnership?.active)", inspect)
        chooser = background.split("async function flowTabForJob", 1)[1].split("async function approveFlowCreditOnce", 1)[0]
        self.assertIn("flowProjectId(tab.url) === checkpointProjectId", chooser)
        self.assertIn("smartpostFlowActiveProject", chooser)

    def test_inspect_flow_registers_existing_project_before_publishing_request(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        inspect = background.split('command.action === "inspect_flow"', 1)[1].split('command.action === "approve_flow_credit"', 1)[0]
        self.assertIn("flowProjectId(tab.url) === checkpointProjectId", inspect)
        self.assertLess(inspect.index("let flowTabId = 0"), inspect.index("smartpostFlowInspectOnly:"))
        self.assertLess(inspect.index("smartpostFlowActiveProject:"), inspect.index("smartpostFlowInspectOnly:"))
        publish = inspect.split("Publish the inspect request only after", 1)[1]
        self.assertIn("smartpostFlowInspectOnly", publish)
        self.assertIn("await ensureFlowHelper(flowTabId)", publish)

    def test_flow_resume_refreshes_package_and_focus_publishes_shot_first(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("function queuePackageReload()", flow)
        self.assertIn('window.addEventListener("smartpost-flow-resume", () => {\n    queuePackageReload()', flow)
        focus = background.split("async function focusFlowWebTab", 1)[1].split("async function waitForTabComplete", 1)[0]
        self.assertLess(focus.index("smartpostActiveShotIndex"), focus.index("chrome.tabs.create"))
        self.assertIn("ensureFlowHelper(tab.id)", focus)

    def test_same_project_duplicate_tabs_choose_the_one_with_real_video_results(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        health = background.split("async function inspectFlowTabHealth", 1)[1].split("async function pickRichestFlowProjectTab", 1)[0]
        self.assertIn("videoCount", health)
        self.assertIn("resultControlCount", health)
        richest = background.split("async function pickRichestFlowProjectTab", 1)[1].split("async function pickHealthyFlowProjectTab", 1)[0]
        self.assertIn("right.health.videoCount", richest)
        self.assertIn("right.health.resultControlCount", richest)
        chooser = background.split("async function flowTabForJob", 1)[1].split("async function approveFlowCreditOnce", 1)[0]
        self.assertIn("await pickRichestFlowProjectTab(checkpointTabs)", chooser)
        inspect = background.split('command.action === "inspect_flow"', 1)[1].split('command.action === "approve_flow_credit"', 1)[0]
        self.assertIn("await pickRichestFlowProjectTab(checkpointTabs)", inspect)

    def test_new_flow_shot_cannot_adopt_previous_shot_project(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        chooser = background.split("async function flowTabForJob", 1)[1].split("async function approveFlowCreditOnce", 1)[0]
        self.assertIn("without its own registered tab or checkpoint is new work", chooser)
        self.assertIn("pickHealthyFlowProjectTab(preferred, preferred)", chooser)
        self.assertNotIn("pickHealthyFlowProjectTab(tabs, preferred)", chooser)
        self.assertIn("return null;", chooser)
        inspect = background.split('command.action === "inspect_flow"', 1)[1].split("let flowTabId = 0", 1)[0]
        missing = inspect.split("if (!monitorMatches && !checkpoint?.url)", 1)[1]
        self.assertIn("Never adopt an unrelated live project", missing)
        self.assertNotIn("liveProjectTab", missing)
        fresh = background.split("async function openFlowTab", 1)[1].split("function normalizeAIProvider", 1)[0]
        self.assertIn("let freshTab = tabs.find", fresh)
        self.assertNotIn("|| tabs.at(-1)", fresh)

    def test_flow_low_progress_disappearing_cannot_be_false_completion(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        inspect = source.split("async function inspectGenerationState()", 1)[1]
        completed = inspect.split("const completedAfterObservedProgress", 1)[1].split("const resultCardsStableAfterProgress", 1)[0]
        self.assertIn("generationHighestProgress >= 80", completed)
        self.assertIn("snapshot.resultCardCount > Number(generationBaseline.resultCardCount || 0)", completed)
        new_video = inspect.split("const newVideo", 1)[1].split("if (newVideo", 1)[0]
        self.assertIn(": false);", new_video)
        self.assertIn("completedMobileResult || (generationBaseline", new_video)
        self.assertIn("baseline.videoCount !== 0 || baseline.resultCardCount !== 0", source)

    def test_flow_monitor_excludes_smartpost_helper_controls(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        # The helper has an image-download button of its own. It must not make
        # an in-progress Google Flow render look like a completed video.
        self.assertIn('button.closest?.("#smartpost-flow-helper-host")', source)
        self.assertIn('element.closest?.("#smartpost-flow-helper-host")', source)
        self.assertIn('bodyText.replace(helperText, "")', source)

    def test_flow_persists_active_project_checkpoint_before_completion(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertIn('saveFlowProjectCheckpoint("active")', source)
        self.assertIn('saveFlowProjectCheckpoint("complete")', source)
        self.assertIn("url: location.href", source)
        self.assertIn('previous.status === "complete"', source)

    def test_flow_prompt_history_is_not_live_generation_proof_and_delayed_credit_can_win(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertNotIn("pageText.includes(pkg.video_prompt.slice(0, 80))", source)
        self.assertIn("latestCreditQuestionAt > latestActivityAt", source)
        self.assertIn("newest actionable question", source)

    def test_flow_numeric_progress_wins_over_stale_credit_question(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        confirmation = source.split("function confirmationKind(pageText)", 1)[1].split("async function dismissNonLegalOverlay", 1)[0]
        numeric_guard = 'if (hasNumericProgress) return "";'
        delayed_question = "if (livePlainCreditApproval && latestCreditQuestionAt >= 0 && latestCreditQuestionAt > latestActivityAt"
        self.assertIn(numeric_guard, confirmation)
        self.assertIn(delayed_question, confirmation)
        self.assertLess(confirmation.index(numeric_guard), confirmation.index(delayed_question))
        self.assertIn("livePlainCreditApproval", confirmation)
        self.assertIn('getComputedStyle(row).cursor !== "pointer"', confirmation)
        self.assertIn('row.getAttribute("aria-disabled") === "true"', confirmation)

    def test_flow_credit_approval_prefers_the_visible_latest_question(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        approval = source.split("async function approveFlowCreditOnce", 1)[1].split("async function stopFlowGeneration", 1)[0]
        self.assertIn("left.rect.bottom > 0 && left.rect.top < innerHeight", approval)
        self.assertIn("left.rect.bottom - right.rect.bottom", approval)
        self.assertIn('element.getAttribute("aria-disabled") !== "true"', approval)
        always = 'latest(controls.filter(({ label }) => /^(?:อนุมัติเสมอ|always approve|approve always)$/i.test(label)))'
        persistent = 'latest(controls.filter(({ label }) => /อนุมัติ/.test(label) && /ไม่ต้องถามอีก/.test(label)'
        plain = 'latest(controls.filter(({ label }) => /^(?:อนุมัติ|approve)$/i.test(label)))'
        self.assertLess(approval.index(always), approval.index(persistent))
        self.assertLess(approval.index(persistent), approval.index(plain))

    def test_flow_resume_reuses_one_helper_without_new_project(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        resume = source.split('command.action === "resume_flow_workspace"', 1)[1].split('command.action === "inspect_flow"', 1)[0]
        self.assertIn("ensureFlowHelper(projectTab.id)", resume)
        self.assertNotIn("ensureFlowHelper(projectTab.id, true)", resume)
        self.assertNotIn("openFlowTab(", resume)

    def test_flow_resume_clears_only_a_proven_stale_monitor_and_empty_project_attempt(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        resume = background.split('command.action === "resume_flow_workspace"', 1)[1].split(
            'command.action === "inspect_flow"', 1
        )[0]
        self.assertIn("resumeEvidence?.readyComposer && !resumeEvidence?.hasGenerationEvidence", resume)
        self.assertIn('chrome.storage.local.remove("smartpostFlowMonitor")', resume)
        self.assertIn("An empty picker is not proof", resume)
        self.assertNotIn("delete attempts[attemptKey]", resume)
        self.assertNotIn("location.reload", resume)

    def test_flow_requires_current_composer_proof_before_generate(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        attach = flow.split("async function attachExistingMediaToPrompt()", 1)[1].split(
            "async function dropReferenceImage()", 1
        )[0]
        prepare = flow.split("async function autoPrepare()", 1)[1].split(
            "function stopGenerationMonitor()", 1
        )[0]
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        worker_attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
            'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
        )[0]
        self.assertIn("physicalResult?.composerProof === true && promptHasAttachedMedia()", attach)
        self.assertNotIn("if (physicalResult?.ok) return true", attach)
        self.assertNotIn("promptHasAttachedMedia() || attachDebug?.composerProof === true", prepare)
        self.assertNotIn("attachDebug?.ok", prepare)
        self.assertIn("uploadDebug = null", prepare)
        self.assertGreaterEqual(worker_attach.count("composerProof: true"), 2)

    def test_stale_flow_monitor_stops_before_it_can_publish_an_old_status(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        monitor = flow.split("function monitorGeneration()", 1)[1].split(
            "async function inspectGenerationState()", 1
        )[0]
        self.assertIn('chrome.storage.local.get("smartpostFlowMonitor")', monitor)
        self.assertIn("if (!ownsMonitor)", monitor)
        self.assertLess(monitor.index("if (!ownsMonitor)"), monitor.index("await inspectGenerationState()"))

    def test_smartflow_chrome_launch_hides_only_the_crash_restore_bubble(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn('"--hide-crash-restore-bubble",', source)
        self.assertIn('"--start-maximized",', source)
        self.assertNotIn('subprocess.Popen([str(chrome), "--restore-last-session", url])', source)

    def test_product_runtime_recovery_status_cannot_block_its_own_worker(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        recovery = source.split("def _run_product_runtime_recovery", 1)[1].split(
            "def _schedule_next_story_queue_item", 1
        )[0]
        progress = source.split("def _update_product_progress", 1)[1].split(
            "def _cancel_product_pipeline", 1
        )[0]
        self.assertIn("active_product_worker", recovery)
        self.assertIn("self._product_cancel_event is not None", recovery)
        self.assertIn("self._product_cancel_event is None", recovery)
        self.assertIn("ปลดสถานะ worker เก่าที่จบแล้ว", recovery)
        self.assertIn("if self._product_cancel_event is not None:", progress)

    def test_story_offline_monitor_opens_only_one_provider_tab_per_job(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        launch = source.split("def _launch_story_browser", 1)[1].split("def _monitor_story_browser_progress", 1)[0]
        self.assertIn('if state.get("opened_once"):', launch)
        self.assertIn('"opened_once": True', launch)
        self.assertIn("ระบบจะไม่เปิดแท็บซ้ำ", launch)
        self.assertLess(launch.index('if state.get("opened_once"):'), launch.index("self._activate_or_launch_chrome"))

    def test_smartflow_restores_and_focuses_chrome_after_opening_a_web_job(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("threading.Thread(target=self._focus_chrome_after_launch", source)
        self.assertIn('class_name.value != "Chrome_WidgetWin_1"', source)
        self.assertIn("user32.ShowWindow(handle, 3)", source)
        self.assertIn("user32.SetForegroundWindow(handle)", source)
        self.assertIn("user32.AttachThreadInput(current_thread, thread_id, True)", source)
        self.assertIn("user32.AttachThreadInput(current_thread, thread_id, False)", source)
        self.assertIn("async function focusOpenedBrowserTab(tab)", background)
        self.assertIn("await focusOpenedBrowserTab(freshTab);", background)
        self.assertIn("await focusOpenedBrowserTab(tab);", background)

    def test_product_ai_always_focuses_the_exact_provider_tab(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn('queue_extension_command("focus_ai_web", job_id, provider_hint=active_provider)', source)
        self.assertIn("threading.Thread(target=self._focus_chrome_after_launch, daemon=True).start()", source)

    def test_ai_jobs_never_silently_switch_between_chatgpt_and_gemini(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertNotIn('"chatgpt" if original_provider == "gemini" else "gemini"', source)
        self.assertIn("requested_provider != job_provider", bridge)
        self.assertIn("requestedProvider !== jobProvider", background)
        self.assertIn("const provider = jobProvider;", background)

    def test_flow_recovery_log_distinguishes_a_stall_from_a_duplicate(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn('if duplicate_existing:', source)
        self.assertIn('action = "กำลังสร้างใหม่เพราะตรวจพบคลิปซ้ำ"', source)
        self.assertIn('elif generation_attempt > 1:', source)
        self.assertIn('action = "กำลังเปิดโปรเจกต์ใหม่หลังรอบก่อนค้างหรือผิดพลาด"', source)

    def test_story_recovery_clears_the_previous_terminal_ai_state(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        recovery = source.split("def _resume_story_automatically", 1)[1].split("def _create_story_and_run", 1)[0]
        self.assertLess(recovery.index("self.bridge.clear_ai_progress(job_id)"), recovery.index("self.bridge.queue_extension_command(action"))

    def test_drama_voice_recovery_reuses_the_paid_tts_job_checkpoint(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        render = source.split("def _render_drama_dialogue_voice", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('checkpoint.get("external_job_id")', render)
        self.assertIn("save_dialogue_voice_checkpoint", render)
        self.assertLess(render.index('checkpoint.get("external_job_id")'), render.index("client.synthesize"))

    def test_flow_upload_completion_selects_existing_asset_without_navigation(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        drop = source.split("async function dropReferenceImage()", 1)[1].split("async function autoPrepare()", 1)[0]
        upload = drop.split('if (uploadDebug?.fileSet && uploadDebug?.mediaReady)', 1)[1]
        upload = upload.split('status: uploadDebug?.fileSet ? "uploaded_waiting_media"', 1)[0]
        self.assertNotIn("trustedDrop", upload)
        self.assertIn("JSON.stringify(uploadDebug || {})", upload)
        self.assertNotIn("location.reload", upload)
        self.assertIn('status: "uploaded_ready"', upload)
        self.assertLess(upload.index('await report("flow_media_uploaded"'), upload.index("attachExistingMediaToPrompt()"))

    def test_open_flow_ack_reflects_the_real_project_handoff(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        flow = source.split('} else if (command.action === "open_flow") {', 1)[1].split(
            '} else if (command.action === "resume_flow_workspace") {', 1
        )[0]
        fresh = flow.split("const flowTabId = await openFlowTab(true);", 1)[1]
        before_scan = fresh.split("let projectTab = null;", 1)[0]
        self.assertNotIn("await acknowledge(command, true)", before_scan)
        success = fresh.split("if (projectTab?.id) {", 1)[1].split("} else {", 1)[0]
        self.assertLess(success.index("await ensureFlowHelper(projectTab.id)"), success.index("await acknowledge(command, true)"))
        self.assertIn("await acknowledge(command, false, failureMessage)", fresh)
        self.assertIn('run_id: String(command.run_id || "")', fresh)
        self.assertIn("const projectTabIdsBeforeOpen = new Set", fresh)
        self.assertIn("tab.id === flowTabId || !projectTabIdsBeforeOpen.has(tab.id)", fresh)

    def test_flow_resume_accepts_only_the_exact_completed_download_receipt(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        wait_download = source.split("def _wait_download", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("completed_download_receipt", wait_download)
        self.assertIn('flow_client.get("flow_step") or "") == "generation_complete"', wait_download)
        self.assertIn("reported_path == expected_target", wait_download)
        self.assertIn("target.stat().st_mtime >= started_at or completed_download_receipt", wait_download)

    def test_completed_flow_card_wins_over_stale_queue_text_after_progress(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        completed = source.split("const completedCardAfterObservedProgress", 1)[1].split(";", 1)[0]
        self.assertIn("observedActiveGeneration", completed)
        self.assertIn("resultCardsStableAfterProgress", completed)
        self.assertIn("!snapshot.activeProgress", completed)
        self.assertIn("snapshot.resultCardCount >", completed)
        self.assertNotIn("!isBusy", completed)

    def test_production_source_contains_no_destroyed_utf8_placeholders(self):
        roots = ["app.py", "core", "desktop", "ui", "web_ui", "browser_extension", "launcher", "tools"]
        suffixes = {".py", ".js", ".json", ".html", ".css", ".bat", ".ps1", ".cs"}
        corrupted = []
        markers = ("?" * 4, "Ã", "Â", "à¸", "à¹", "\ufffd")
        for item in roots:
            path = ROOT / item
            candidates = [path] if path.is_file() else path.rglob("*")
            for candidate in candidates:
                if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
                    continue
                text = candidate.read_text(encoding="utf-8")
                if any(marker in text for marker in markers):
                    corrupted.append(str(candidate.relative_to(ROOT)))
        self.assertEqual(corrupted, [])

    def test_runtime_version_contract_is_consistent_across_source_and_blueprints(self):
        extension = ROOT / "browser_extension"
        manifest = json.loads((extension / "manifest.json").read_text(encoding="utf-8"))
        version = manifest["version"]
        self.assertEqual(version, LocalBridge.REQUIRED_EXTENSION_VERSION)
        self.assertIn(f'const FLOW_HELPER_BUILD = "flow-{version}-', (extension / "background.js").read_text(encoding="utf-8"))
        self.assertIn(f'const helperBuild = "flow-{version}-', (extension / "flow.js").read_text(encoding="utf-8"))
        self.assertIn(f"รุ่น Runtime `{version}`", (ROOT / "CODEX_START_HERE.md").read_text(encoding="utf-8"))
        self.assertIn(f"เวอร์ชัน Runtime ปัจจุบัน: `{version}`", (ROOT / "EXTENSION_BLUEPRINT.md").read_text(encoding="utf-8"))
        self.assertIn(f"Runtime Extension {version}", (ROOT / "PROGRAM_BLUEPRINT.md").read_text(encoding="utf-8"))

    def test_flow_generate_is_at_most_once_per_job_shot_and_run(self):
        extension = ROOT / "browser_extension"
        background = (extension / "background.js").read_text(encoding="utf-8")
        flow = (extension / "flow.js").read_text(encoding="utf-8")
        generate = background.split('if (message?.type === "CLICK_FLOW_GENERATE")', 1)[1].split(
            'sendResponse({ ok: false, error: "unknown_message"', 1
        )[0]
        self.assertIn("FLOW_SUBMISSION_RECEIPTS_KEY", background)
        self.assertIn("flowGenerateInFlight", generate)
        self.assertIn("persistent_submission_guard", generate)
        self.assertIn("existing_sent_prompt_guard", generate)
        self.assertLess(
            generate.index("chrome.storage.local.set({ [FLOW_SUBMISSION_RECEIPTS_KEY]: receipts })"),
            generate.index('type: "mousePressed"'),
        )
        self.assertIn("submission_guarded", flow)
        self.assertIn("existing_composer_checkpoint", flow)
        self.assertIn("duplicateBlocked", flow)

    def test_flow_unknown_recovery_is_bounded_without_counter_reset_loops(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        wait = source.split("def _wait_flow_step", 1)[1].split("def _wait_download", 1)[0]
        self.assertIn("unknown_state_total_checks", wait)
        self.assertIn("unknown_state_requeues < 2", wait)
        self.assertIn("unknown_state_total_checks in {10, 20}", wait)
        self.assertIn("unknown_state_total_checks >= 30", wait)

    def test_flow_overlay_stays_clear_of_bottom_right_generate_control(self):
        source = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        self.assertIn('right:14px;top:72px;bottom:auto', source)
        status = source.split("const setStatus = (text) => {", 1)[1].split("};", 1)[0]
        self.assertNotIn("setExpanded(true)", status)

    def test_flow_policy_denial_pauses_without_local_motion_or_resend(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        desktop = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        manager = (ROOT / "core" / "product_manager.py").read_text(encoding="utf-8")
        self.assertIn("const isPolicyFailure", flow)
        self.assertIn("FLOW_POLICY_BLOCKED", flow)
        worker = desktop.split("def _multi_flow_worker", 1)[1].split("\n    def ", 1)[0]
        self.assertNotIn("mark_flow_policy_fallback", worker)
        self.assertNotIn("_render_product_policy_fallback_segment", worker)
        self.assertIn("FlowVideoReviewError", worker)
        self.assertNotIn("reassign_flow_shot_source", worker)
        self.assertNotIn("advance_flow_policy_prompt", worker)
        self.assertIn("def mark_flow_policy_fallback", manager)
        self.assertIn("def attach_flow_local_motion_clip", manager)
        self.assertIn("flow_source_image_map", manager)
        self.assertIn("flow_segment_provenance", manager)
        self.assertIn("flow_local_motion_clips", manager)
        self.assertIn("flow_target_clip_count", manager)
        self.assertIn("const lastPatternIndex", flow)
        self.assertIn("queuedStateIndex > failureStateIndex", flow)
        self.assertIn("failureStateIndex > Math.max(queuedStateIndex, busyStateIndex)", flow)


if __name__ == "__main__": unittest.main()
