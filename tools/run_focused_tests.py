"""Run small feature suites locally or select them from a Git diff in CI."""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SUITES = {
    "ui-terminology": {
        "python": [],
        "node": ["tests/ui_terminology.cjs", "tests/product_continue_ui.js",
                 "tests/presenter_library_ui_harness.js", "tests/shopee_posting_ui.cjs",
                 "tests/flow_settings_ui_harness.js", "tests/scene_video_plan_ui_457.cjs",
                 "tests/android_wifi_ui.cjs", "tests/music_library_dom.js",
                 "tests/shopee_post_progress_ui.cjs", "tests/membership_ui.cjs",
                 "tests/story_recovery_timeline.cjs", "tests/facebook_post_ui.js",
                 "tests/video_intro_ui_harness.js"],
        "syntax": ["web_ui/app.js", "web_ui/facebook_planner.js", "web_ui/membership.js",
                   "web_ui/presenter.js", "web_ui/product_continue.js", "web_ui/product_story.js",
                   "web_ui/shopee_posting.js", "web_ui/updates.js", "web_ui/clip_cover.js",
                   "web_ui/flow_settings.js", "web_ui/scene_video_plan.js", "web_ui/studio.js",
                   "web_ui/android_wifi.js", "web_ui/music_library.js", "web_ui/library_view.js",
                   "web_ui/shopee_post_progress.js", "web_ui/green_screen.js",
                   "web_ui/video_intro.js", "web_ui/provider_lab.js"],
    },
    "setup-recovery-ui": {
        "python": [],
        "node": ["tests/setup_recovery_ui.cjs", "tests/flow_failure_notice_ui_harness.js",
                 "tests/story_queue_declutter_ui.js"],
        "syntax": ["web_ui/setup_wizard.js", "web_ui/recovery_wizard.js", "web_ui/app.js",
                   "web_ui/creation_queue.js"],
    },
    "create-wizard-ui": {
        "python": [],
        "node": ["tests/create_wizard_ui.cjs", "tests/product_snapshot_stack.cjs",
                 "tests/generation_notice_426.cjs", "tests/queue_choice_ui_harness.js"],
        "syntax": ["web_ui/create_wizard.js", "web_ui/generation_notice.js", "web_ui/queue_choice.js"],
    },
    "jobs-page-ui": {
        "python": [],
        "node": ["tests/jobs_page_ui.cjs", "tests/creation_old_remove_ui.cjs",
                 "tests/story_queue_declutter_ui.js"],
        "syntax": ["web_ui/creation_queue.js"],
    },
    "notification-layout": {
        "python": [],
        "node": ["tests/notification_stack_ui.cjs", "tests/update_notifications_admin_20260922.cjs"],
        "syntax": ["web_ui/updates.js"],
    },
    "config-defaults": {
        "python": ["test_config_defaults.py", "test_customer_runtime.py"],
        "node": [],
        "syntax": [],
    },
    "webview2-prototype": {
        "python": ["test_provider_prototype.py", "test_provider_lab_ui.py", "test_webview2_request.py"],
        "node": ["tests/webview2_request_dom.cjs"],
        "syntax": ["web_ui/provider_lab.js"],
    },
    "ai-cover": {
        "python": ["test_ai_cover.py", "test_ai_cover_queue_gate.py"],
        "node": ["tests/cover_multiple_selection_450.cjs", "tests/cover_retry_reference_451.cjs",
                 "tests/cover_stream_error_512.cjs"],
        "syntax": ["browser_extension/chatgpt.js"],
    },
    "story-prompt": {
        "python": ["test_story_prompt_safety.py"],
        "node": [],
        "syntax": [],
    },
    "story-dispatch": {
        "python": ["test_story_duplicate_dispatch.py", "test_ai_web_resume_345.py"],
        "node": ["tests/story_bootstrap_tab_guard.cjs", "tests/story_retained_reference_resume.cjs",
                 "tests/ai_web_resume_345_harness.js", "tests/ai_send_acceptance_harness.js"],
        "syntax": ["browser_extension/background.js", "browser_extension/chatgpt.js"],
    },
    "story-progress-stall": {
        "python": ["test_story_image_progress_stall.py"],
        "node": ["tests/story_pre_send_stall_518.cjs"],
        "syntax": ["browser_extension/background.js", "browser_extension/chatgpt.js"],
    },
    "ai-send-viewport": {
        "python": ["test_ai_send_diagnostics_bridge.py"],
        "node": ["tests/send_fallback_466.cjs", "tests/ai_send_acceptance_harness.js"],
        "syntax": ["browser_extension/background.js"],
    },
    "story-recovery-ui": {
        "python": ["test_story_recovery_summary.py", "test_creation_queue.py"],
        "node": ["tests/story_recovery_timeline.cjs", "tests/story_recovery_clear_ui.js",
                 "tests/story_queue_declutter_ui.js"],
        "syntax": ["web_ui/app.js"],
    },
    "story-setup-ui": {
        "python": [],
        "node": ["tests/story_setup_scroll_ui.cjs"],
        "syntax": ["web_ui/app.js"],
    },
    "story-image-result": {
        "python": ["test_ai_send_diagnostics_bridge.py", "test_story_manual_image_replay.py"],
        "node": ["tests/chatgpt_semantic_turns_435.cjs", "tests/chatgpt_recovery_loop_456.cjs",
                 "tests/story_image_wait_342_harness.js", "tests/story_manual_replay_harness.cjs"],
        "syntax": ["browser_extension/chatgpt.js"],
    },
    "test-runner": {
        "python": ["test_audit_progress.py"],
        "node": [],
        "syntax": [],
    },
    "installer": {
        "python": ["test_build_installer_one_click.py"],
        "node": [],
        "syntax": [],
    },
    "refactor": {
        "python": [
            "test_audit_progress.py",
            "test_low_impact_refactor.py",
            "test_ai_send_diagnostics_bridge.py",
            "test_ai_cover_queue_gate.py",
            "test_story_flow_contract.py:test_drama_uses_the_video_mode_selected_by_the_user",
            "test_extension_modular_architecture.py",
        ],
        "node": ["tests/gemini_discovery_harness.js"],
        "syntax": ["browser_extension/src/core/timeout.js", "browser_extension/src/background/job-router.js"],
    },
    "membership": {
        "python": ["test_dev_membership.py", "test_membership.py"],
        "node": [],
        "syntax": ["web_ui/membership.js"],
    },
    "extension-update": {
        "python": [
            "test_extension_one_click_update.py",
            "test_customer_update_guard.py",
            "test_extension_upgrade_diagnostic_451.py",
            "test_project_integrity.py:extension_version_mismatch_pauses_without_an_explicit_reload_request",
        ],
        "node": ["tests/connection_diagnostic_451.cjs"],
        "syntax": ["web_ui/updates.js", "web_ui/app.js", "browser_extension/background.js"],
    },
    "ui-foundation": {
        "python": ["test_ui_foundation.py", "test_hybrid_information_architecture.py", "test_creative_controls.py",
                   "test_creative_picker_layout_20260927.py"],
        "node": ["tests/status_vocabulary.cjs", "tests/ui_foundation_ui.cjs", "tests/ux_2026_ui.cjs",
                 "tests/creation_old_remove_ui.cjs", "tests/creation_product_editor_ui_449.cjs",
                 "tests/product_snapshot_stack.cjs", "tests/queue_addons_456.cjs", "tests/progress_queue_ui_harness.js"],
        "syntax": ["web_ui/status_vocabulary.js", "web_ui/app.js", "web_ui/creation_queue.js",
                   "web_ui/product_continue.js", "web_ui/product_story.js", "web_ui/ux_2026.js"],
    },
    "release-contract": {
        "python": ["test_project_release_contract.py"],
        "node": [],
        "syntax": [],
    },
}

FILE_SUITES = {
    "core/config.py": ("config-defaults",),
    "core/customer_runtime.py": ("config-defaults",),
    "tests/test_config_defaults.py": ("config-defaults",),
    "tests/test_customer_runtime.py": ("config-defaults",),
    "desktop/provider_prototype.py": ("webview2-prototype",),
    "desktop/embedded_provider.py": ("webview2-prototype",),
    "desktop/webview2_request.py": ("webview2-prototype",),
    "desktop/hybrid.py": ("webview2-prototype",),
    "desktop/update_api.py": ("extension-update", "webview2-prototype"),
    "tests/test_provider_prototype.py": ("webview2-prototype",),
    "tests/test_provider_lab_ui.py": ("webview2-prototype",),
    "tests/test_webview2_request.py": ("webview2-prototype",),
    "tests/webview2_request_dom.cjs": ("webview2-prototype",),
    "web_ui/provider_lab.js": ("webview2-prototype", "ui-terminology"),
    "web_ui/provider_lab.css": ("webview2-prototype",),
    "tools/smoke_provider_lab_ui.py": ("webview2-prototype",),
    "tools/smoke_webview2_live_text.py": ("webview2-prototype",),
    "core/ai_cover.py": ("ai-cover",),
    "ui/ai_cover.py": ("ai-cover",),
    "tests/test_ai_cover.py": ("ai-cover",),
    "core/story_content.py": ("story-prompt",),
    "core/story_manager.py": ("story-prompt", "story-dispatch"),
    "core/ai_web_resume.py": ("story-dispatch",),
    "core/story_failure_timeline.py": ("story-prompt", "story-recovery-ui", "story-dispatch"),
    "core/story_progress_stall.py": ("story-progress-stall",),
    "tests/test_story_image_progress_stall.py": ("story-progress-stall",),
    "tests/story_pre_send_stall_518.cjs": ("story-progress-stall",),
    "tests/test_ai_web_resume_345.py": ("story-dispatch",),
    "core/story_pipeline.py": ("story-prompt",),
    "core/story_recovery_summary.py": ("story-recovery-ui",),
    "core/creation_queue.py": ("story-recovery-ui",),
    "tests/test_creation_queue.py": ("story-recovery-ui",),
    "tests/test_story_prompt_safety.py": ("story-prompt",),
    "tests/test_story_duplicate_dispatch.py": ("story-dispatch",),
    "tests/story_bootstrap_tab_guard.cjs": ("story-dispatch",),
    "tests/ai_web_resume_345_harness.js": ("story-dispatch",),
    "tests/story_retained_reference_resume.cjs": ("story-dispatch",),
    "tests/ai_send_acceptance_harness.js": ("story-dispatch", "ai-send-viewport"),
    "tests/send_fallback_466.cjs": ("ai-send-viewport",),
    "browser_extension/chatgpt.js": ("ai-cover", "story-dispatch", "story-image-result"),
    "tests/ai_cover_harness.js": ("ai-cover",),
    "tests/cover_multiple_selection_450.cjs": ("ai-cover",),
    "tests/cover_retry_reference_451.cjs": ("ai-cover",),
    "tests/cover_stream_error_512.cjs": ("ai-cover",),
    "tests/chatgpt_semantic_turns_435.cjs": ("story-image-result",),
    "tests/chatgpt_recovery_loop_456.cjs": ("story-image-result",),
    "tests/story_image_wait_342_harness.js": ("story-image-result",),
    "tests/story_manual_replay_harness.cjs": ("story-image-result",),
    "tests/test_story_manual_image_replay.py": ("story-image-result",),
    "RUN_DEV.bat": ("membership",),
    "core/membership.py": ("membership",),
    "web_ui/membership.js": ("membership", "ui-terminology"),
    "tests/test_dev_membership.py": ("membership",),
    "tests/test_membership.py": ("membership",),
    "tests/membership_ui.cjs": ("membership", "ui-terminology"),
    "core/extension_updater.py": ("extension-update",),
    "ui/update_guard.py": ("extension-update",),
    "ui/main_window.py": ("extension-update", "refactor", "story-recovery-ui", "story-progress-stall"),
    "ui/state_rules.py": ("refactor",),
    "web_ui/updates.js": ("extension-update", "notification-layout", "ui-terminology"),
    "web_ui/notification_stack.css": ("notification-layout",),
    "tests/notification_stack_ui.cjs": ("notification-layout",),
    "tests/update_notifications_admin_20260922.cjs": ("notification-layout",),
    "web_ui/app.js": ("extension-update", "story-recovery-ui", "story-setup-ui", "ui-foundation", "setup-recovery-ui", "ui-terminology"),
    "web_ui/index.html": ("extension-update", "webview2-prototype", "story-recovery-ui", "story-setup-ui", "notification-layout", "ui-foundation", "jobs-page-ui", "create-wizard-ui", "setup-recovery-ui", "ui-terminology"),
    "web_ui/creation_queue.js": ("story-recovery-ui", "ui-foundation", "jobs-page-ui", "setup-recovery-ui"),
    "web_ui/jobs_page.css": ("jobs-page-ui",),
    "tests/jobs_page_ui.cjs": ("jobs-page-ui",),
    "web_ui/create_wizard.js": ("create-wizard-ui",),
    "web_ui/create_wizard.css": ("create-wizard-ui",),
    "tests/create_wizard_ui.cjs": ("create-wizard-ui",),
    "web_ui/generation_notice.js": ("create-wizard-ui",),
    "web_ui/queue_choice.js": ("create-wizard-ui",),
    "tests/queue_choice_ui_harness.js": ("create-wizard-ui",),
    "web_ui/setup_wizard.js": ("setup-recovery-ui",),
    "web_ui/setup_wizard.css": ("setup-recovery-ui",),
    "web_ui/recovery_wizard.js": ("setup-recovery-ui",),
    "web_ui/recovery_wizard.css": ("setup-recovery-ui",),
    "tests/setup_recovery_ui.cjs": ("setup-recovery-ui",),
    "tests/flow_failure_notice_ui_harness.js": ("setup-recovery-ui",),
    "web_ui/styles.css": ("story-recovery-ui", "story-setup-ui", "ui-foundation"),
    "web_ui/status_vocabulary.js": ("ui-foundation", "story-recovery-ui"),
    "web_ui/foundation.css": ("ui-foundation",),
    "web_ui/workspace.css": ("ui-foundation",),
    "web_ui/ux_2026.js": ("ui-foundation",),
    "web_ui/product_continue.js": ("ui-foundation", "ui-terminology"),
    "web_ui/product_story.js": ("ui-foundation", "ui-terminology"),
    "web_ui/clip_cover.js": ("ui-terminology",),
    "web_ui/facebook_planner.js": ("ui-terminology",),
    "web_ui/presenter.js": ("ui-terminology",),
    "web_ui/shopee_posting.js": ("ui-terminology",),
    "web_ui/flow_settings.js": ("ui-terminology",),
    "web_ui/scene_video_plan.js": ("ui-terminology",),
    "web_ui/studio.js": ("ui-terminology",),
    "web_ui/android_wifi.js": ("ui-terminology",),
    "web_ui/music_library.js": ("ui-terminology",),
    "web_ui/library_view.js": ("ui-terminology",),
    "web_ui/shopee_post_progress.js": ("ui-terminology",),
    "web_ui/green_screen.js": ("ui-terminology",),
    "web_ui/video_intro.js": ("ui-terminology",),
    "tests/ui_terminology.cjs": ("ui-terminology",),
    "tests/product_continue_ui.js": ("ui-terminology",),
    "tests/presenter_library_ui_harness.js": ("ui-terminology",),
    "tests/shopee_posting_ui.cjs": ("ui-terminology",),
    "tests/story_recovery_clear_ui.js": ("story-recovery-ui", "ui-terminology"),
    "tests/flow_settings_ui_harness.js": ("ui-terminology",),
    "tests/scene_video_plan_ui_457.cjs": ("ui-terminology",),
    "tests/android_wifi_ui.cjs": ("ui-terminology",),
    "tests/music_library_dom.js": ("ui-terminology",),
    "tests/shopee_post_progress_ui.cjs": ("ui-terminology",),
    "tests/status_vocabulary.cjs": ("ui-foundation",),
    "tests/ui_foundation_ui.cjs": ("ui-foundation",),
    "tests/test_ui_foundation.py": ("ui-foundation",),
    "tests/ux_2026_ui.cjs": ("ui-foundation",),
    "tests/creation_old_remove_ui.cjs": ("ui-foundation",),
    "tests/creation_product_editor_ui_449.cjs": ("ui-foundation",),
    "tests/creative_controls_ui.cjs": ("ui-foundation",),
    "tests/creative_picker_layout_20260927.cjs": ("ui-foundation",),
    "tests/product_snapshot_stack.cjs": ("ui-foundation",),
    "tests/queue_addons_456.cjs": ("ui-foundation",),
    "tests/progress_queue_ui_harness.js": ("ui-foundation",),
    "tests/story_setup_scroll_ui.cjs": ("story-setup-ui",),
    "tests/test_story_recovery_summary.py": ("story-recovery-ui",),
    "tests/story_recovery_timeline.cjs": ("story-recovery-ui", "ui-terminology"),
    "tests/facebook_post_ui.js": ("ui-terminology",),
    "tests/video_intro_ui_harness.js": ("ui-terminology",),
    "tests/story_queue_declutter_ui.js": ("story-recovery-ui",),
    "browser_extension/background.js": ("extension-update", "story-dispatch", "ai-send-viewport"),
    "core/local_bridge.py": ("extension-update", "refactor", "story-dispatch"),
    "core/bridge_diagnostics.py": ("refactor", "story-image-result", "ai-send-viewport"),
    "tests/test_ai_send_diagnostics_bridge.py": ("story-image-result", "ai-send-viewport"),
    "core/bridge_types.py": ("refactor", "ai-send-viewport"),
    "browser_extension/src/core/timeout.js": ("refactor",),
    "browser_extension/src/core/constants.js": ("refactor", "release-contract"),
    "browser_extension/src/background/job-router.js": ("refactor",),
    "tools/verify_pair_contract.py": ("refactor", "release-contract"),
    "tools/package_current_extension.py": ("refactor", "release-contract"),
    "tests/test_low_impact_refactor.py": ("refactor",),
    "ui/creation_queue.py": ("ai-cover", "refactor"),
    "tests/test_ai_cover_queue_gate.py": ("ai-cover", "refactor"),
    "tests/test_extension_modular_architecture.py": ("refactor",),
    "tests/gemini_discovery_harness.js": ("refactor",),
    "tests/result_readiness_392.cjs": ("refactor",),
    "tests/test_audit_progress.py": ("test-runner",),
    "tools/run_audit_checks.py": ("test-runner",),
    "tools/build_installer_one_click.py": ("installer",),
    "tests/test_build_installer_one_click.py": ("installer",),
    "tests/test_extension_one_click_update.py": ("extension-update",),
    "tests/test_customer_update_guard.py": ("extension-update",),
    "tests/test_extension_upgrade_diagnostic_451.py": ("extension-update",),
    "tests/connection_diagnostic_451.cjs": ("extension-update",),
    "tests/test_project_integrity.py": ("extension-update",),
    "CURRENT_RELEASE.json": ("release-contract",),
    "browser_extension/manifest.json": ("release-contract",),
    "browser_extension/flow.js": ("release-contract",),
    "tests/test_project_release_contract.py": ("release-contract",),
    "tools/run_focused_tests.py": ("membership", "extension-update"),
}

CODE_SUFFIXES = {".py", ".js", ".cjs", ".html", ".bat", ".ps1", ".json"}
IGNORED_PREFIXES = ("docs/", ".github/")
IGNORED_FILES = {"AGENTS.md", "README.md", "PROGRAM_BLUEPRINT.md", "PROJECT_STATE.md", "CODEX_START_HERE.md", "EXTENSION_BLUEPRINT.md"}


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).splitlines()


def changed_files(base):
    if base and set(base) != {"0"}:
        return set(_git("diff", "--name-only", "--diff-filter=ACMR", base, "HEAD"))
    if base:
        return set(_git("diff", "--name-only", "--diff-filter=ACMR", "HEAD^", "HEAD"))
    files = set(_git("diff", "--name-only", "--diff-filter=ACMR", "HEAD"))
    files.update(_git("ls-files", "--others", "--exclude-standard"))
    return files


def select_suites(paths):
    selected = set()
    unmapped = []
    for name in sorted(paths):
        path = name.replace("\\", "/")
        if path in FILE_SUITES:
            selected.update(FILE_SUITES[path])
        elif path not in IGNORED_FILES and not path.startswith(IGNORED_PREFIXES) and Path(path).suffix in CODE_SUFFIXES:
            unmapped.append(path)
    return sorted(selected), unmapped


def run_suite(name):
    suite = SUITES[name]
    for filename in suite["syntax"]:
        command = ["node", "--check", filename]
        print("+", " ".join(command), flush=True)
        if subprocess.run(command, cwd=ROOT, check=False).returncode:
            return 1
    for filename in suite["python"]:
        pattern, separator, test_filter = filename.partition(":")
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern]
        if separator:
            command += ["-k", test_filter]
        print("+", " ".join(command), flush=True)
        if subprocess.run(command, cwd=ROOT, check=False).returncode:
            return 1
    for filename in suite["node"]:
        command = ["node", filename]
        print("+", " ".join(command), flush=True)
        if subprocess.run(command, cwd=ROOT, check=False).returncode:
            return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature", action="append", choices=sorted(SUITES), help="Run a named feature suite; repeatable")
    parser.add_argument("--changed", action="store_true", help="Select suites for changed files")
    parser.add_argument("--base", help="Git base commit for CI; local --changed uses working-tree changes")
    parser.add_argument("--plan", action="store_true", help="Print selected suites without running them")
    args = parser.parse_args()
    if not args.feature and not args.changed:
        parser.error("provide --feature or --changed")
    selected = set(args.feature or [])
    if args.changed:
        paths = changed_files(args.base)
        suites, unmapped = select_suites(paths)
        selected.update(suites)
        if unmapped:
            print("No focused test mapping for changed code:", *unmapped, sep="\n  ", file=sys.stderr)
            print("Add each file to FILE_SUITES and include its affected contract tests.", file=sys.stderr)
            return 2
    if not selected:
        print("No code requiring a focused suite changed.")
        return 0
    if args.plan:
        print("SUITES=" + ",".join(sorted(selected)))
        return 0
    print("Focused suites:", ", ".join(sorted(selected)), flush=True)
    for name in sorted(selected):
        if run_suite(name):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
