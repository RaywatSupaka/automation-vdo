import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HybridUiContractTests(unittest.TestCase):
    def test_hybrid_assets_cover_primary_workflows(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        action_contract = html + script + engine
        for page in (
            "dashboard", "products", "story", "drama", "library", "voice",
            "subtitle", "audio", "logo", "queue", "guide", "logs",
        ):
            self.assertIn(f'data-view="{page}"', html)
        for action in (
            "create_product", "create_story", "create_drama_series", "cancel_product", "cancel_story",
            "open_library_video", "open_library_cover", "import_product_link", "update_product",
            "approve_product_ai", "check_product_readiness", "product_add_images",
            "product_add_video", "product_tool", "voice_create", "voice_save_settings", "voice_ai_script",
            "subtitle_create", "subtitle_save_style", "audio_render", "logo_render",
            "queue_add_video", "queue_add_folder", "queue_safety",
            "delete_all_product_projects", "delete_all_library_renders",
            "delete_completed_projects",
            "scan_workspace_junk", "clean_workspace_junk",
            "enqueue_story_batch", "story_queue_pause", "story_queue_resume",
            "story_queue_clear_finished", "retry_story",
            "check_system_readiness",
        ):
            self.assertIn(action, action_contract)
        self.assertIn("@media(max-width:1000px)", styles)
        self.assertIn("progress-modal", html)
        self.assertIn('id="voice-save-settings"', html)
        self.assertIn("ทุกคลิปล็อกอารมณ์ Normal และความเร็ว 1.0x", html)
        self.assertIn("emotion:'normal'", script)
        self.assertIn("speed:1", script)
        self.assertNotIn("emotion_id=emotion", engine)
        self.assertNotIn("speed=float(self.voice_speed.get())", engine)
        self.assertIn("detail-modal", html)
        self.assertIn("item.aspect_ratio === '16:9'", script)
        self.assertIn("สร้างปก Shorts แนวตั้ง 9:16", html)
        self.assertIn('id="story-video-mode"', html)
        self.assertIn('id="story-batch-video-mode"', html)
        self.assertIn('value="google_flow"', html)
        self.assertIn("video_generation_mode:$('#story-video-mode').value", script)
        self.assertIn("video_generation_mode:$('#story-batch-video-mode').value", script)
        self.assertIn("item.cover_url || item.preview_url", script)
        self.assertIn("detail-cover-panel", styles)
        self.assertIn('id="cleanup-scan"', html)
        self.assertIn('id="cleanup-run"', html)
        self.assertIn("Final ปลอดภัย", html)
        self.assertIn("renderWorkspaceCleanup", script)
        self.assertIn("workspace_cleanup", engine)
        self.assertIn(".cleanup-panel", styles)
        self.assertIn("product-detail-modal", html)
        self.assertIn("progressCloseTimer", script)
        completion = script.split('    if (completed) {', 1)[1].split('    } else if', 1)[0]
        self.assertIn('dismissProgressResult();', completion)
        self.assertNotIn('showModal', completion)
        self.assertNotIn('setTimeout', completion)
        self.assertIn("current.action_button", script)
        self.assertIn("service:progress.action_service", script)
        self.assertIn('"action_kind": str(self._product_web_action', engine)
        self.assertIn('"action_kind": str((self._story_web_actions', engine)
        self.assertIn("__subtitle_preview__", engine)
        self.assertIn("except tk.TclError", engine)
        self.assertIn("if not self.hybrid_engine", engine)
        self.assertIn("subtitle_preview_hybrid_{os.getpid()}_{token}", engine)
        self.assertIn('self.console.get("1.0", "end-1c")', engine)
        self.assertIn('(selected_job or {}).get("image_ai_provider")', engine)
        self.assertNotIn("เปิดเครื่องมือแบบละเอียด", html)
        self.assertNotIn("data-open-legacy", html)
        self.assertNotIn("open_legacy", script)
        self.assertNotIn("จัดการโปรเจกต์ทั้งหมด", html)
        self.assertNotIn("เครื่องมือวิเคราะห์เพิ่มเติม", html)

    def test_saved_credentials_have_safe_connected_and_disconnect_states(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        for element_id in ("voice-key-state", "subtitle-token-state", "voice-delete-key", "subtitle-delete-credential"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertEqual(html.count("ยกเลิกการเชื่อมต่อ</button>"), 2)
        self.assertIn("function applyCredentialState", script)
        self.assertIn("✓ เชื่อมต่อแล้ว", script)
        self.assertIn("voice_disconnect", script)
        self.assertIn("subtitle_disconnect", script)
        self.assertIn("Token SOT ใหม่", script)
        self.assertIn(".credential-badge.connected", styles)
        self.assertIn('"key_saved": bool(self.voice_api_key.get().strip())', engine)
        self.assertIn('"credential_saved": bool(subtitle_connected)', engine)
        self.assertNotIn('"api_key": self.voice_api_key', engine)
        self.assertNotIn('"token": self.subtitle_token', engine)

    def test_voice_and_subtitle_credits_are_prominent_and_secret_safe(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        for element_id in (
            "credit-voice-mini", "credit-subtitle-mini", "dashboard-credit-voice",
            "dashboard-credit-subtitle", "voice-page-credit", "subtitle-page-credit",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("function renderCredits", script)
        self.assertIn("refresh_service_credits", script)
        self.assertIn(".credit-dock", styles)
        self.assertIn(".credit-overview", styles)
        self.assertIn('"credits": {', engine)
        self.assertIn("_service_credit_worker", engine)
        self.assertNotIn('"api_key": voice_key', engine)
        self.assertNotIn('"credential": subtitle_credential', engine)

    def test_subtitle_preview_uses_real_renderer_and_font_upload(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        renderer = (ROOT / "core" / "subtitle_renderer.py").read_text(encoding="utf-8")
        for element_id in (
            "subtitle-preview-video", "subtitle-preview-image", "subtitle-preview-state",
            "subtitle-preview-meta", "subtitle-upload-font", "subtitle-preview-replay",
            "subtitle-preview-focus-badge",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("รองรับไฟล์ TTF และ OTF", html)
        self.assertIn("function scheduleSubtitlePreview", script)
        self.assertIn("function applySubtitlePreviewMode", script)
        self.assertIn("data-subtitle-preview-mode", html)
        self.assertIn('data-mode="detail"', html)
        self.assertIn("subtitle_preview_style", script)
        self.assertIn("apply_theme:applyTheme", script)
        self.assertNotIn("webkitTextStroke", script)
        self.assertIn(".subtitle-preview-state", styles)
        self.assertIn('.subtitle-live-preview[data-mode="frame"]', styles)
        self.assertIn('"preview_video_url"', engine)
        self.assertIn('action in {"subtitle_preview_style", "subtitle_save_style", "subtitle_apply_style"}', engine)
        self.assertIn("self.fonts.upload(path)", engine)
        self.assertIn("def render_preview_video", renderer)
        self.assertIn('"-pix_fmt", "yuv420p"', renderer)

    def test_audio_mix_v2_controls_short_cuts_and_voice_ducking(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        mixer = (ROOT / "core" / "audio_mixer.py").read_text(encoding="utf-8")
        finisher = (ROOT / "core" / "story_finisher.py").read_text(encoding="utf-8")
        for element_id in (
            "audio-segment-max", "audio-segment-max-label",
            "audio-duck-percent", "audio-duck-percent-label",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('data-tool="audio_open_background_folder"', html)
        self.assertIn('data-tool="audio_open_sfx_folder"', html)
        self.assertIn("เปิดโฟลเดอร์เพลงพื้นหลังทั้งหมด", html)
        self.assertIn("เปิดโฟลเดอร์เสียงเน้นข้อความทั้งหมด", html)
        self.assertIn("def _open_audio_asset_folder", engine)
        self.assertNotIn("id=\"audio-add-background\"", html)
        self.assertNotIn("id=\"audio-add-sfx\"", html)
        self.assertIn("เพลงพื้นหลัง • สุ่มท่อนอัตโนมัติ", html)
        self.assertIn("ท่อนละ 8–12 วินาที", html)
        self.assertIn('id="audio-segment-max" type="range" min="8" max="12" step="1"', html)
        self.assertIn("segment_max_sec:Number($('#audio-segment-max').value)", script)
        self.assertIn("duck_percent:Number($('#audio-duck-percent').value)", script)
        self.assertIn(".audio-v2-note", styles)
        self.assertIn("music_segment_max_sec", engine)
        self.assertIn("music_duck_ratio", engine)
        self.assertIn("def build_music_plan", mixer)
        self.assertIn("sidechaincompress", mixer)
        self.assertIn('"audio_mix_version": 2', mixer)
        self.assertIn('"background_duck_percent"', finisher)

    def test_logo_page_has_persistent_library_selection_and_explicit_save(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        for element_id in (
            "logo-library", "logo-upload-file", "logo-selected-summary",
            "logo-preview-name", "logo-save", "logo-preview-button", "logo-render",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertNotIn('id="logo-choose-file"', html)
        self.assertIn("data-logo-asset", script)
        self.assertIn("prepareLogoImage", script)
        for action in ("logo_upload", "logo_select_asset", "logo_save"):
            self.assertIn(action, script)
            self.assertIn(action, engine)
        self.assertIn(".logo-library-grid", styles)
        self.assertIn('ROOT / "assets" / "logos" / "user"', engine)
        self.assertIn('ROOT / "assets" / "smartflow_logo.png"', engine)
        self.assertIn('item_id == "__brand_full__"', engine)
        self.assertIn("self._logo_preview_asset_id == str(selected_logo.get", engine)
        self.assertIn("__brand_full__", html)
        self.assertIn("def _save_logo_preferences", engine)
        self.assertIn("self.cfg.update(settings)", engine)

    def test_affiliate_workspace_is_aligned_and_hides_duplicate_shortcuts(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8") + (ROOT / "web_ui" / "workspace.css").read_text(encoding="utf-8")
        product_page = html.split('<section class="page" data-view="products">', 1)[1].split('<section class="page" data-view="voice">', 1)[0]
        for tool in (
            "multi_flow", "effects", "ai_web", "add_images",
            "add_video", "edit", "open_job", "delete_project", "delete_all_products",
        ):
            self.assertIn(f'data-product-tool="{tool}"', product_page)
        for duplicate in (
            'data-page="voice"', 'data-page="subtitle"', 'data-page="logo"',
            'data-product-tool="approve"', 'data-product-tool="readiness"',
            'data-product-tool="copy_link"', 'data-product-tool="refresh"',
        ):
            self.assertNotIn(duplicate, product_page)
        self.assertIn('class="product-source-row"', product_page)
        self.assertIn('class="product-form-footer"', product_page)
        self.assertIn('class="advanced-job-tools"', product_page)
        self.assertIn(".product-source-row", styles)
        self.assertIn(".product-form-footer", styles)
        self.assertIn(".advanced-job-grid", styles)
        self.assertNotIn(".create-submit{grid-column:1/-1}", styles)
        self.assertNotIn('data-product-tool="auto_flow"', product_page)

    def test_story_page_is_creation_focused_and_primary_modes_are_premium(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn('class="nav-item nav-creator nav-affiliate"', html)
        self.assertIn('class="nav-item nav-creator nav-story"', html)
        self.assertIn('class="story-compose-grid"', html)
        self.assertIn('class="story-submit-bar"', html)
        self.assertNotIn('class="panel story-history"', html)
        self.assertIn('id="story-recovery-panel"', html)
        self.assertIn('id="story-list"', html)
        self.assertIn('งานที่ต้องดำเนินการต่อ', html)
        self.assertIn('ทำต่อจาก Checkpoint เดิม', html)
        self.assertNotIn('<h2>งานล่าสุด</h2>', html)
        self.assertIn(".nav-creator", styles)
        self.assertIn(".story-create-button", styles)
        self.assertIn("function renderStories(stories, storyProgress = {})", script)
        self.assertIn('data-retry-story=', script)
        self.assertIn("panel.hidden = pending.length === 0", script)

    def test_story_batch_adds_up_to_ten_but_queue_controls_live_only_on_creation_page(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        for element_id in (
            "open-story-batch", "story-batch-modal", "story-batch-topics",
            "story-batch-submit", "creation-list", "creation-start", "creation-status-filter",
            "story-batch-provider", "story-batch-scenes", "story-batch-scene-label",
            "choose-story-batch-image", "story-batch-image-path",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("สูงสุด 10 คลิป", html)
        self.assertIn('id="story-batch-submit"', html)
        self.assertIn("เพิ่มรายการเข้าคิว", html)
        self.assertIn('id="creation-list"', html)
        self.assertNotIn('id="story-queue-panel"', html)
        self.assertNotIn('id="nav-story-queue-count"', html)
        self.assertNotIn("function renderStoryQueue", script)
        self.assertNotIn("$('#story-queue-toggle')", script)
        self.assertIn('class="story-queue-link"', html)
        self.assertIn("provider:$('#story-batch-provider').value", script)
        self.assertIn("scene_count:Number($('#story-batch-scenes').value)", script)
        self.assertIn("main_image:ui.storyBatchImage || $('#story-batch-image-path').value", script)
        self.assertIn("topics.length <= 10", script)
        self.assertIn("enqueue_story_batch", script)
        self.assertIn("story_queue_pause", script)
        self.assertIn("story_queue_resume", script)
        self.assertIn(".story-queue-link", styles)
        self.assertIn(".story-batch-compose-grid", styles)
        self.assertIn('"story_queue": self.story_queue.snapshot()', engine)

    def test_drama_series_ui_keeps_characters_and_runs_ep_queue(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        for element_id in (
            "drama-title", "drama-premise", "drama-provider", "drama-episodes",
            "drama-scenes", "drama-character-1-name", "drama-character-1-description",
            "drama-character-1-image", "drama-character-1-voice", "drama-character-2-voice",
            "choose-drama-footage", "drama-footage-name", "create-drama-series", "drama-series-list",
            "drama-plot-board", "drama-cover-theme",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('class="workflow-disclosure drama-character-disclosure"', html)
        self.assertIn("ใช้ข้อมูลนี้ซ้ำทุกฉากและทุก EP", html)
        self.assertIn("create_drama_series", script)
        self.assertIn("upload_reference_image", script)
        self.assertIn('id="drama-character-1-file"', html)
        self.assertIn('id="drama-continue-modal"', html)
        self.assertIn('id="drama-project-modal"', html)
        self.assertIn('id="drama-project-content"', html)
        self.assertIn("continue_drama_series", script)
        self.assertIn("retry_drama_episode", script)
        self.assertIn("cancel_drama_series", script)
        self.assertIn("data-cancel-drama-series", script)
        self.assertIn("open_drama_series_folder", script)
        self.assertIn("story_job_id", script)
        self.assertIn("data-continue-series", script)
        self.assertIn("data-retry-story", script)
        self.assertIn("choose_drama_footage", script)
        self.assertIn("voice_reference_id", script)
        self.assertIn("renderDramaSeries", script)
        self.assertIn("currentDramaPlotBoard", script)
        self.assertIn("continuity_validation", script)
        self.assertIn("duration_seconds", script)
        self.assertIn("automation_retry_count", script)
        self.assertIn(".drama-create-button", styles)
        self.assertIn(".drama-plot-planner", styles)
        self.assertIn("DramaSeriesManager", engine)
        self.assertIn('"drama_series": self.drama_series.snapshot()', engine)

    def test_entrypoint_exposes_hybrid_only_and_keeps_engine_hidden(self):
        entrypoint = (ROOT / "app.py").read_text(encoding="utf-8")
        hybrid = (ROOT / "desktop" / "hybrid.py").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("run_hybrid", entrypoint)
        self.assertNotIn("--legacy", entrypoint)
        self.assertNotIn("run_legacy", entrypoint)
        self.assertIn("run_engine", entrypoint)
        self.assertIn("show_startup_error", entrypoint)
        self.assertIn("--engine", entrypoint)
        self.assertIn("pywebview", requirements.lower())
        self.assertFalse((ROOT / "RUN_LEGACY.bat").exists())
        self.assertIn('WINDOW_TITLE = "SmartFlow AI — AI Clip Creator"', hybrid)
        self.assertIn("_apply_windows_window_icon", hybrid)
        self.assertIn("smartflow_icon.ico", hybrid)
        self.assertIn("smartflow-window-icon", hybrid)
        self.assertIn("_focus_existing_window", hybrid)
        self.assertIn("keybd_event(0x74", hybrid)
        self.assertIn("IsWindowVisible", hybrid)
        self.assertIn("smartflow-engine-watchdog", hybrid)
        self.assertIn("WATCHDOG engine exited", hybrid)
        self.assertIn("self.engine_pid", hybrid)
        self.assertIn('"action": "shutdown"', hybrid)
        self.assertIn("current_pid == engine_pid", hybrid)
        self.assertIn("if self._stopped:", hybrid)
        health_source = hybrid.split("def _health(self)", 1)[1].split("def _ready(self)", 1)[0]
        ready_source = hybrid.split("def _ready(self)", 1)[1].split("def start_engine", 1)[0]
        self.assertIn('f"{self.base_url}/health"', health_source)
        self.assertNotIn("/api/desktop/state", ready_source)
        self.assertIn('"SmartFlow AI — Hidden Engine" if self.hybrid_engine', engine)
        self.assertTrue((ROOT / "CREATE_SMARTFLOW_SHORTCUT.ps1").is_file())
        self.assertTrue((ROOT / "launcher" / "SmartFlowLauncher.cs").is_file())
        self.assertGreater((ROOT / "SmartFlow AI.exe").stat().st_size, 10_000)

    def test_hybrid_inner_html_escapes_invalid_date_fallbacks(self):
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("${escapeHtml(formatDate(latest.updated_at))}", script)
        self.assertIn("${escapeHtml(formatDate(item.updated_at))}", script)
        self.assertNotIn("${formatDate(latest.updated_at)}", script)
        self.assertNotIn("${formatDate(item.updated_at)}", script)

    def test_ui_uses_readable_state_led_motion_without_model_or_library_regressions(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('id="progress-minimized"', html)
        self.assertIn('role="progressbar"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('required aria-describedby="product-link-error product-readiness"', html)
        self.assertIn('required aria-describedby="story-topic-error story-submit-hint"', html)
        self.assertIn('required aria-describedby="drama-title-error drama-submit-hint"', html)
        self.assertIn('id="setting-chatgpt-model" disabled', html)
        self.assertIn("function updateCreationAvailability()", script)
        self.assertIn("ui.libraryVisibleCount += 24", script)
        self.assertIn('loading="lazy" decoding="async"', script)
        self.assertIn("select.disabled = locked", script)
        self.assertIn("prefers-reduced-motion:reduce", styles)
        self.assertIn("button.is-busy", styles)

    def test_cinematic_workspace_keeps_creation_clear_and_accessible(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web_ui" / "workspace.css").read_text(encoding="utf-8")
        for element_id in ("new-job-menu", "library-search", "library-sort", "progress-result", "automation-error-return"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('class="sf-fx-stage"', html)
        self.assertNotIn('data-view="video"', html)
        self.assertNotIn("function videoPayload()", script)
        self.assertIn("document.body.dataset.page = page", script)
        self.assertIn("document.body.dataset.fxMode", script)
        self.assertIn("pointer-events:none", styles)
        self.assertIn("prefers-reduced-motion:reduce", styles)
        self.assertIn("Capture delegated controls before a WebView/browser overlay can stop bubbling", script)
        self.assertIn("function bindLibraryOpenControls", script)
        self.assertIn("function bindModalCloseControls", script)
        self.assertIn("function bindNavigationFallbacks", script)
        self.assertIn("event.smartflowDelegated = true", script)
        self.assertGreaterEqual(script.count("bindLibraryOpenControls("), 4)
        self.assertIn(".latest-output{position:relative}", styles)
        self.assertIn(".video-card-button{z-index:4;cursor:pointer}", styles)
        self.assertIn("sf-phone-float", styles)
        self.assertIn("sf-dashboard-rise", styles)

    def test_library_detail_clicks_are_not_swallowed_by_active_page_marker(self):
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn(
            "event.target.closest('button[data-page], a[data-page], [role=\"button\"][data-page]')",
            script,
        )
        self.assertNotIn("const pageButton = event.target.closest('[data-page]');", script)
        for action in (
            "open_library_folder",
            "open_library_video",
            "open_library_cover",
            "data-detail-delete-video",
            "data-detail-delete-project",
        ):
            self.assertIn(action, script)

    def test_hybrid_cards_and_details_label_mixed_video_sources_truthfully(self):
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function videoSourcePresentation(item = {})", script)
        for field in (
            "source_remote_count", "source_local_count", "source_total_count",
            "source_target_count", "video_source_type", "video_source_label",
        ):
            self.assertIn(field, script)
        self.assertIn("Hybrid • Google Flow ${remote} + Local Motion ${local}", script)
        self.assertIn("/ ${target || total} ${unit}", script)
        self.assertNotIn("/ ${total || target} ${unit}", script)
        self.assertIn("? videoSourcePresentation(job).label", script)
        self.assertIn("const source = videoSourcePresentation(item);", script)
        self.assertIn("['แหล่งวิดีโอ', source.label, 'video_source_label']", script)
        self.assertIn("${escapeHtml(videoSourcePresentation(latest).label)}", script)
        self.assertNotIn("? `Google Flow ${Number(job.flow_clip_count || 0)}/${Number(job.scene_count || 0)}`", script)


if __name__ == "__main__":
    unittest.main()
