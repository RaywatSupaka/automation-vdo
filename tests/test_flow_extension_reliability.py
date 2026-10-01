from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / "browser_extension" / name).read_text(encoding="utf-8")


def test_extension_and_bridge_versions_match():
    from core.local_bridge import LocalBridge
    manifest = json.loads((ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8"))
    release = json.loads((ROOT / "CURRENT_RELEASE.json").read_text(encoding="utf-8"))
    assert manifest["version"] == LocalBridge.REQUIRED_EXTENSION_VERSION == release["runtime"]["extension_version"]


def test_ready_composer_recovery_reuses_the_exact_project_without_reuploading():
    flow = source("flow.js")
    recovery = flow.split("const currentComposerReady = Boolean(", 1)[1].split("const hasBoundDirectVideo", 1)[0]
    assert "promptHasAttachedMedia()" in recovery
    assert "currentPromptText.includes" in recovery
    assert "findGenerateButton()" in recovery
    assert "!monitorMatches && !readyReceiptActive" in recovery
    assert "recoveredReadyComposer: true" in recovery
    assert 'report("ready_to_generate_recovery"' in recovery
    assert "return await runAutoPrepareOnce()" in recovery
    assert "dropReferenceImage" not in recovery


def test_native_download_start_fallback_is_bounded_to_fifteen_seconds():
    background = source("background.js")
    assert "const FLOW_NATIVE_DOWNLOAD_START_TIMEOUT_MS = 15000;" in background
    watcher = background.split("const watchNativeFlowDownload", 1)[1].split("const normaliseNativeDownload", 1)[0]
    assert "FLOW_NATIVE_DOWNLOAD_START_TIMEOUT_MS" in watcher
    assert "ภายใน 15 วินาที" in watcher


def test_flow_changelog_modal_is_dismissed_once_without_touching_credit_dialogs():
    background, flow = source("background.js"), source("flow.js")
    assert 'message?.type === "DISMISS_FLOW_CHANGELOG"' in background
    assert 'mat-dialog-actions.change-log-modal-actions,.change-log-modal-actions' in background
    assert "ดูบันทึกการเปลี่ยนแปลงทั้งหมด" in background
    assert "เริ่มต้นใช้งาน" in background
    assert "function hasFlowChangelogAnnouncement()" in flow
    assert 'chrome.runtime.sendMessage({ type: "DISMISS_FLOW_CHANGELOG" })' in flow
    assert 'report("dismissed_changelog"' in flow


def test_bound_direct_flow_video_survives_lost_monitor_and_downloads():
    flow = source("flow.js")
    assert "const hasBoundDirectVideo" in flow
    assert "/^https:\\/\\/flow-content\\.google\\/video\\//i" in flow
    assert "currentSnapshot.resultCardCount > 0 || hasBoundDirectVideo" in flow
    assert "currentSnapshot.videoCount - (hasBoundDirectVideo ? 1 : 0)" in flow
    assert "generationHighestProgress = hasBoundDirectVideo" in flow


def test_flow_progress_is_owner_gated():
    background, flow = source("background.js"), source("flow.js")
    assert "const ownership = await flowProgressOwnership(progress, sender.tab?.id)" in background
    assert 'reason: "stale_flow_tab"' in background
    assert 'reason: "stale_flow_run"' in background
    assert 'type: "IS_ACTIVE_FLOW_TAB"' in flow
    assert "if (!ownership?.active) return false" in flow
    assert "run_id: String(pkg.run_id || \"\")" in flow


def test_extension_ticks_and_commands_are_single_flight():
    background = source("background.js")
    assert "if (extensionTickPromise) return extensionTickPromise" in background
    assert "extensionTickPromise = (async () =>" in background
    assert "function runExtensionTickOnce()" in background
    assert "setInterval(runExtensionTickOnce, 5000)" in background
    assert "setInterval(extensionTick, 5000)" not in background


def test_completed_download_schedules_bounded_fast_command_handoff():
    background = source("background.js")
    assert "const FLOW_FAST_HANDOFF_DELAYS_MS = [250, 1000, 2500]" in background
    assert 'progress.step === "generation_complete"' in background
    assert "String(progress.download_path || \"\")" in background
    assert "scheduleFastCommandHandoff(progress.job_id, progress.shot_index, progress.run_id)" in background
    assert "now - flowFastHandoffScheduledAt < 10000" in background


def test_flow_monitor_is_serialized():
    flow = source("flow.js")
    assert "function stopGenerationMonitor()" in flow
    assert "function nextGenerationMonitorDelay()" in flow
    assert "generationHighestProgress >= 80" in flow
    assert "generationMonitorTimer = setTimeout(inspectNext, nextGenerationMonitorDelay())" in flow
    assert "generationMonitorTimer = setTimeout(inspectNext, 2500)" in flow
    assert "setInterval(async () =>" not in flow


def test_completed_download_receipt_and_sequential_handoff_are_fast_but_safe():
    desktop = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
    wait_download = desktop.split("def _wait_download", 1)[1].split("\n    def ", 1)[0]
    worker = desktop.split("def _multi_flow_worker", 1)[1].split("\n    def ", 1)[0]
    assert "stable = 2 if completed_download_receipt else" in wait_download
    assert "probable_mp4" in wait_download and "probable_webm" in wait_download
    assert "previous_shot_completed_in_worker = False" in worker
    assert "skip_remote_checkpoint_probe = bool(" in worker
    assert "if not force_new and skip_remote_checkpoint_probe:" in worker
    assert "previous_shot_completed_in_worker = True" in worker


def test_terminal_policy_never_retries_flow_and_announces_immediate_local_fallback():
    flow = source("flow.js")
    desktop = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
    terminal = flow.split("} else if (terminalPolicyDecision.terminal) {", 1)[1].split(
        "} else if (currentExplicitUnchargedFailure", 1
    )[0]
    worker = desktop.split("def _multi_flow_worker", 1)[1].split("\n    def ", 1)[0]
    assert "Extension จะไม่กดลองใหม่หรือส่งรูปนี้ซ้ำ" in terminal
    assert "ไม่ใช้ภาพนิ่งแทน" in terminal
    assert "mark_flow_policy_fallback" not in worker
    assert "_render_product_policy_fallback_segment" not in worker
    assert "reassign_flow_shot_source" not in worker
    assert "advance_flow_policy_prompt" not in worker


def test_attachment_likelihood_is_not_proof():
    flow = source("flow.js")
    assert "trustedDrop?.ok || trustedDrop?.attachmentLikely" not in flow
    assert "physicalResult?.composerProof === true && promptHasAttachedMedia()" in flow
    assert "promptHasAttachedMedia() || attachDebug?.composerProof === true" not in flow


def test_flow_waits_for_uploaded_gallery_tile_without_repeating_the_upload():
    background = source("background.js")
    attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
        'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
    )[0]
    assert "for (let galleryAttempt = 0; galleryAttempt < 48" in attach
    assert "for (let menuAttempt = 0; menuAttempt < 16" in attach
    assert "for (let animateAttempt = 0; animateAttempt < 16" in attach
    assert attach.count('findPoint("gallery_media_card"') == 1
    assert 'type: "OPEN_FLOW_MEDIA_UPLOAD"' not in attach


def test_animate_click_waits_for_stable_target_and_requires_postcondition_without_retry():
    background = source("background.js")
    click = background.split("const physicalClick = async (point) =>", 1)[1].split(
        "const physicalHover = async (point) =>", 1
    )[0]
    assert "stablePointCount >= 3" in click
    assert 'throw new Error("FLOW_ANIMATE_TARGET_UNSTABLE")' in click
    assert 'throw new Error("FLOW_ANIMATE_CLICK_NOT_ACCEPTED")' in click
    assert "if (await promptHasAttachedMedia()) return" in click
    assert 'if (!(await findPoint("animate_media_action"))) return' in click
    assert "const hoveredPoint = await findPoint" in click
    # One trusted pointer sequence only: no second action click is allowed when
    # Flow ignores the first one.
    assert click.count('type: "mousePressed"') == 1
    postcondition = click.rsplit('if (point?.guard === "animate_media_action") {', 1)[1]
    assert 'type: "mousePressed"' not in postcondition


def test_flow_closes_only_the_upload_menu_and_never_clicks_through_to_still_editor():
    background = source("background.js")
    attach = background.split('message?.type === "ATTACH_LATEST_FLOW_MEDIA"', 1)[1].split(
        'message?.type === "OPEN_FLOW_MEDIA_UPLOAD"', 1
    )[0]
    desktop = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "const dismissOpenUploadMenu = async () =>" in attach
    assert '"Input.dispatchKeyEvent"' in attach
    assert 'key: "Escape"' in attach
    assert "if (!hit || !(hit === target || target.contains(hit))) return null;" in attach
    assert attach.index("dismissOpenUploadMenu()") < attach.index('physicalClick(galleryMenuPoint)')
    assert "เปิดโหมดแก้ภาพนิ่งแทนโหมดสร้างวิดีโอ" in desktop


def test_flow_attachment_proof_requires_real_composer_media():
    background, flow = source("background.js"), source("flow.js")
    for script in (background, flow):
        assert 'editor.closest?.(".base-prompt-box")' in script
        assert "((runMediaVisual && removableContainer(element)) || elementChip)" in script
    assert "return imageAttached || backgroundAttached;" in background
    assert "removableCardAttached" not in background
    assert "const imageReady = Boolean(imageAttachAttempted && promptHasAttachedMedia())" in flow
    assert "const mediaStillAttached = Boolean(promptHasAttachedMedia())" in flow


def test_result_detection_uses_fingerprints():
    flow = source("flow.js")
    assert "resultFingerprints" in flow
    assert "snapshot.resultCardCount > Number(generationBaseline.resultCardCount || 0)" in flow
    assert "completedCardAfterObservedProgress" in flow


def test_bridge_uses_command_lease_and_structured_evidence():
    bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
    assert '"lease_token": lease_token' in bridge
    assert '"lease_expires_at": now + bridge.COMMAND_LEASE_SECONDS' in bridge
    assert '"flow_download_path"' in bridge
    assert '"flow_page_excerpt"' in bridge

def test_cleanup_and_flow_reuse_only_touch_registered_automation_tabs():
    background = source("background.js")
    assert "async function rememberedAutomationTabIds()" in background
    cleanup = background.split("async function closeAutomationBrowser", 1)[1].split("return { closedTabs: tabIds.length };", 1)[0]
    assert "const candidates = await rememberedAutomationTabIds()" in cleanup
    assert "chrome.tabs.query({})" not in cleanup
    assert "Never discover cleanup targets from URL alone" in background
    assert "projectTabIdsBeforeOpen" in background

def test_flow_status_labels_use_real_shot_count():
    flow = source("flow.js")
    assert "${pkg.shot_index}/3" not in flow
    assert "${Number(pkg.shot_count || 3)}" in flow

def test_credit_fallback_checks_the_same_action_row_not_page_history():
    background = source("background.js")
    assert "const currentQuestion = [...document.querySelectorAll(\"p\")]" in background
    assert "const questionScope = currentQuestion?.parentElement || document" in background
    assert "Re-read the current action row immediately before the trusted event" in background
    assert "approvalStillVisible" not in background
    assert "const fallback = false" in background
    assert "document.elementFromPoint(x, y)" in background

def test_stop_and_resume_never_fallback_to_another_flow_job():
    background = source("background.js")
    assert "no_registered_flow_tab" in background
    assert "pickHealthyFlowProjectTab(preferredTabs, preferredTabs)" in background
    assert "Resume is Job/SHOT-scoped" in background

def test_result_fingerprint_does_not_depend_on_dom_position():
    flow = source("flow.js")
    fingerprint = flow.split("const resultFingerprints", 1)[1].split("return {", 1)[0]
    assert "resultCards.map((card) =>" in fingerprint
    assert "parts.join(\"|\")" in fingerprint
    assert "|${index}`" not in flow

def test_latest_result_card_can_be_selected_when_initially_offscreen():
    background = source("background.js")
    start = background.index("async function openFlowResultCard")
    end = background.index("async function locateFlowDownloadPoint", start)
    block = background[start:end]
    assert "const rendered = (element)" in block
    assert "target.scrollIntoView" in block
    assert "document.elementFromPoint" in block


def test_flow_marks_any_observed_progress_as_disappeared_before_accepting_new_card():
    flow = source("flow.js")
    assert "previousProgressSignature && !progressSignature && generationHighestProgress > 0" in flow
    assert "resultCardsStableAfterProgress" in flow
    assert "snapshot.resultCardCount > Number(generationBaseline.resultCardCount || 0)" in flow


def load_tests(loader, tests, pattern):
    """Expose the module-level regression checks to unittest discovery."""
    suite = unittest.TestSuite()
    for name, candidate in sorted(globals().items()):
        if name.startswith("test_") and callable(candidate):
            suite.addTest(unittest.FunctionTestCase(candidate, description=name))
    return suite
