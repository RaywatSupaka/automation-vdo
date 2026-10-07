import base64
import copy
from core.flow_settings import snapshot_flow
import ctypes
import queue
import random
import re
import hashlib
import shutil
import subprocess
import threading
import time
import tkinter as tk
import uuid
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from ctypes import wintypes
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk
from ui.state_rules import credit_state, story_video_mode_key, video_render_settings

from core.adb_manager import AdbManager
from core.ai_web_models import AI_WEB_MODEL_OPTIONS, ai_web_model_label, normalize_ai_web_model
from core.atomic_json import AtomicJsonFile, JsonPersistenceError
from core.audio_mixer import AudioMixer
from core.cancellable_process import OperationCancelled, check_cancelled, run_cancellable
from core.config import ROOT, save_audio_settings, save_logo_settings, save_subtitle_settings, save_video_settings, save_voice_settings
from core.automation_observation import public_observations
from core.drama_series import DramaSeriesManager
from core.drama_media import DramaFootageMixer
from core.external_tts import CLIP_VOICE_EMOTION, CLIP_VOICE_SPEED, ExternalTtsClient, ExternalTtsError
from core.external_tts import MAX_TTS_REQUEST_CHARS
from core.chunked_tts import render_chunked_voice
from core.font_manager import FontManager
from core.flow_fallback import validated_attachment_failure_evidence
from core.flow_review import FlowVideoReviewError
from core.job_manager import JobManager
from core.local_bridge import LocalBridge
from core.long_video import meta_landscape_available
from core.logger import build_logger
from core.product_manager import ProductManager
from core.product_pipeline import PRODUCT_AI_AUTO_RECOVERY_LIMIT, PRODUCT_RUNTIME_RECOVERY_LIMIT, PRODUCT_STAGES, ai_package_complete, completed_flow_clips, completed_product_segments, interrupted_product_candidate, product_ai_recovery_action, product_ai_recovery_command, product_progress, product_provider_failover_action, product_runtime_recovery_action, real_product_data, recoverable_product_candidate
from core.product_image_video import ProductImageVideoComposer
from core.product_image_recovery import ProductImageRecovery
from core.product_source_images import select_source_images
from core.product_image_review import product_image_review, product_image_asset
from core.secure_store import WindowsCredentialStore
from core.smartsub_online import SmartSubOnlineClient
from core.story_manager import StoryManager
from core.creation_queue import CreationQueue
from ui.creation_queue import CreationQueueMixin
from ui.rendering import story_render, product_render
from ui.presenter import PresenterMixin
from core.presenter import PresenterManager, apply_presenter
from core.story_finisher import finish_story_media
from core.story_script import spoken_script_for_job
from core.story_video import StoryVideoComposer
from core.story_pipeline import (
    STORY_AUTO_RECOVERY_LIMIT,
    STORY_STAGES,
    browser_progress,
    story_existing_draft_notice,
    story_image_refusal_notice,
    story_provider_failover_action,
    story_recovery_action,
)
from core.subtitle_styles import SUBTITLE_ANIMATIONS, SUBTITLE_THEMES, animation_by_label, random_animation, random_theme, theme_by_label
from core.subtitle_renderer import SubtitleVideoRenderer
from core.thai_tts import prepare_thai_tts_script
from core.subtitle_preview import SubtitlePreviewService
from core.story_styles import STORY_VISUAL_STYLES, normalize_story_style
from core.studio_review import story_review, scene_asset, pronunciation_notes, voice_review, validate_user_notes
from core.video_logo import POSITIONS, VideoLogoRenderer
from core.logo_layout import PROFILE_SIZES, frozen_logo_config, logo_profile, logo_render_options, normalize_logo_layout
from core.video_composer import MultiFlowComposer
from core.drama_options import drama_render_options
from core.media_audio import audio_choices, audio_mode, product_audio_options
from core.video_effects import ProductEffectsRenderer
from core.video_library import VideoLibrary
from core.job_file_guard import app_guard, guarded_thread, uses_job_files
from core.workspace_health import scan_workspace_issues, resolve_workspace_issue_folder
from core.workspace_cleaner import FinalVideoValidator, WorkspaceCleaner, working_video_folder


_PRODUCT_STORY_DISPATCH_LOCK = threading.RLock()


def interrupted_story_restart_candidate(job, now=None, *, owned_meta_receipt=False):
    """Only an owned, recent unfinished stage may resume after an app restart."""
    if job.get('status') != 'running' or job.get('cancel_requested'):
        return False
    try:
        age = ((now or datetime.now()) - datetime.fromisoformat(str(job.get('updated_at') or ''))).total_seconds()
    except (TypeError, ValueError):
        return False
    long_meta = bool(job.get('long_video')) and job.get('video_generation_mode') == 'meta_ai'
    if age > (6 * 3600 if long_meta else 30 * 60) and not (long_meta and owned_meta_receipt):
        return False
    if job.get('pipeline_stage') == 'chatgpt' and job.get('ai_status') != 'ready':
        return True
    if job.get('ai_status') != 'ready':
        return False
    if long_meta:
        return (len(job.get('generated_images') or []) == int(job.get('scene_count') or 0)
                and job.get('pipeline_stage') in {'meta_ai', 'voice', 'video', 'finishing'})
    return (job.get('voice_status') == 'ready'
            and job.get('pipeline_stage') in {'voice', 'google_flow', 'video', 'finishing'})


COLORS = {
    "bg": "#070A14",
    "sidebar": "#0B1020",
    "panel": "#10172A",
    "panel_2": "#151E35",
    "panel_3": "#0B1122",
    "line": "#24304A",
    "line_soft": "#19233A",
    "text": "#F5F7FF",
    "muted": "#94A0BA",
    "subtle": "#64718E",
    "cyan": "#27D4F0",
    "blue": "#4B7BFF",
    "blue_hover": "#638DFF",
    "purple": "#A855F7",
    "green": "#34D399",
    "orange": "#F59E5B",
    "yellow": "#FACC15",
    "danger": "#FB7185",
}

IMAGE_AI_PROVIDERS = {
    "ChatGPT Web": "chatgpt",
    "Gemini Web": "gemini",
}

VIDEO_AI_PROVIDERS = {
    "Google Flow": "flow",
    "Meta AI (ทดลอง)": "meta_ai",
}

STORY_VIDEO_MODES = {
    "ภาพเคลื่อนไหวอัตโนมัติ": "image_motion",
    "Google Flow ทุกฉาก": "google_flow",
    "Meta AI ทุกฉาก (ทดลอง)": "meta_ai",
}

VIDEO_RESOLUTIONS = {
    "540p • 540 × 960": "540x960",
    "720p HD • 720 × 1280": "720x1280",
    "1080p Full HD • 1080 × 1920": "1080x1920",
}

VIDEO_QUALITIES = {
    "มาตรฐาน • ไฟล์เล็ก": "standard",
    "คมชัดสูง • แนะนำ": "high",
    "คมชัดสูงสุด • ไฟล์ใหญ่": "maximum",
}


class MainWindow(CreationQueueMixin, PresenterMixin):
    def __init__(self, cfg):
        self.cfg = cfg
        self._app_update_lock = threading.RLock()
        from core.membership import production_membership
        from core.app_updates import customer_version
        self.membership = production_membership(customer_version())
        self.events = queue.Queue()
        self._desktop_requests = queue.Queue()
        self._ui_thread_id = threading.get_ident()
        self.hybrid_engine = os.getenv("SMARTPOST_HYBRID_ENGINE", "0") == "1"
        self._desktop_notice = {"kind": "", "message": "", "at": ""}
        self._automation_error_log = {"job_id": "", "service": "", "message": "", "text": "", "at": ""}
        self._flow_failure_notice_ids = []
        self.log = build_logger(ROOT)
        self.jobs = JobManager(ROOT / "data" / "jobs.csv")
        self.products = ProductManager(ROOT)
        self.stories = StoryManager(ROOT)
        self.presenters = PresenterManager(ROOT, cfg.get("ffmpeg_path", ""))
        self.drama_series = DramaSeriesManager(ROOT)
        self.story_queue = CreationQueue(ROOT)
        self.creation_queue = self.story_queue
        self.story_queue.recover_on_startup()
        self._creation_dispatch_item = None
        self._creation_tick_after = None
        self.video_library = VideoLibrary(ROOT, logger=self.log)
        app_guard(self)
        from core.product_story import ProductCast
        self.product_cast = ProductCast(ROOT)
        from core.facebook_post import FacebookPost
        from core.secure_store import WindowsCredentialStore
        self.facebook_post = FacebookPost(ROOT, self.video_library, WindowsCredentialStore('SmartFlowAI/FacebookPage'))
        self.facebook_post.membership = self.membership
        self.workspace_cleaner = WorkspaceCleaner(
            ROOT,
            recycler=self.video_library._recycler,
            logger=self.log,
            validator=FinalVideoValidator(cfg.get("ffmpeg_path", "")),
            existing_job_min_age_sec=10 * 60,
        )
        self._workspace_cleanup_lock = threading.Lock()
        self._workspace_cleanup_state = WorkspaceCleaner.empty_summary()
        self._backfill_story_short_covers()
        self.fonts = FontManager(ROOT)
        self.adb = AdbManager(cfg["adb_path"], cfg.get("device_serial", ""), ROOT)
        from core.android_wifi import AndroidWifi
        from core.config import save_android_selection
        self.android_wifi = AndroidWifi(
            self.adb, cfg.get('android_device_identity', ''), save_selection=save_android_selection,
            notify=lambda text, connected: self.events.put(('device', (text, 'CONNECTED' if connected else 'DISCONNECTED'))),
        )
        from core.shopee_posting.service import ShopeePosting
        self.shopee_posting = ShopeePosting(ROOT, self.video_library, self.android_wifi, cfg.get('ffmpeg_path', ''))
        self.shopee_posting.membership = self.membership
        from core.video_intro import IntroLibrary
        from core.green_screen import GreenLibrary
        self.bridge = LocalBridge(
            cfg.get("bridge_host", "127.0.0.1"),
            cfg.get("bridge_port", 8765),
            self.products,
            self.log,
            self._product_imported,
            self.stories,
            self._story_ai_ready,
            desktop_state=self._desktop_state_request,
            desktop_action=self._desktop_action_request,
            desktop_media=self._desktop_media_request,
            desktop_intro_library=IntroLibrary(ROOT, cfg.get('ffmpeg_path', '')),
            desktop_green_library=GreenLibrary(ROOT, cfg.get('ffmpeg_path', '')),
            desktop_web_root=ROOT / "web_ui",
            presenters=self.presenters,
            membership=self.membership,
            story_run_active=self._story_run_active,
        )

        self.bridge.on_story_scene_ready = lambda payload: self.events.put(('story_scene_ready', payload))
        self._story_scene_threads = {}
        self.root = tk.Tk()
        self.root.title("SmartFlow AI — Hidden Engine" if self.hybrid_engine else "SmartFlow AI — AI Clip Creator")
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        window_width, window_height = min(1280, screen_width - 50), min(820, screen_height - 100)
        self.root.geometry(f"{window_width}x{window_height}+{max(0, (screen_width-window_width)//2)}+{max(0, (screen_height-window_height)//2-15)}")
        self.root.minsize(1080, 700)
        self.root.configure(bg=COLORS["bg"])
        if self.hybrid_engine:
            self.root.withdraw()
            self._install_hybrid_messagebox_bridge()

        self.device = tk.StringVar(value="กำลังตรวจสอบอุปกรณ์ Android...")
        self.device_badge = tk.StringVar(value="CHECKING")
        self.bridge_status = tk.StringVar(value="LOCAL BRIDGE • กำลังเริ่ม")
        self.extension_status = tk.StringVar(value="CHROME EXTENSION • รอเชื่อม")
        self.status = tk.StringVar(value="ระบบพร้อม • Dry Run เปิดอยู่")
        self.log_activity = tk.StringVar(value="รอรับงาน • ทุกขั้นตอนสำคัญจะแสดงที่นี่")
        self._console_last_line = ""
        self._console_last_at = 0.0
        self._extension_trace_seen = set()
        self.guide_bridge = tk.StringVar(value="กำลังตรวจ Local Bridge")
        self.guide_extension = tk.StringVar(value="กำลังตรวจ Chrome Extension")
        self.guide_voice = tk.StringVar(value="กำลังตรวจ AI Voice")
        self.guide_subtitle = tk.StringVar(value="กำลังตรวจ AI Subtitle")
        self.guide_summary = tk.StringVar(value="กำลังตรวจความพร้อมก่อนเริ่ม")
        self.stat_products = tk.StringVar(value="0")
        self.stat_ai = tk.StringVar(value="0")
        self.stat_videos = tk.StringVar(value="0")
        self.stat_posts = tk.StringVar(value="0")
        self.product_link = tk.StringVar()
        self._product_pipeline_job_id = ""
        self._startup_recovery_claimed = False
        self._product_cancel_event = None
        # Manual MULTI FLOW uses the same browser/Extension lane as the
        # one-click Product and Story workers. Track it explicitly so a second
        # workflow cannot start on top of an active Google Flow render.
        self._manual_multi_flow_job_id = ""
        self._manual_multi_flow_cancel_event = None
        self._product_progress_dialog = None
        self._product_progress_value = tk.DoubleVar(value=0)
        self._product_progress_percent = tk.StringVar(value="0%")
        self._product_progress_message = tk.StringVar(value="กำลังเตรียมงาน")
        self._product_progress_detail = tk.StringVar(value="เปอร์เซ็นต์เพิ่มตามผลงานที่เสร็จจริง")
        self._product_progress_job = tk.StringVar(value="")
        self._product_progress_stage_widgets = {}
        self._product_verification_job = ""
        self._product_web_action = {}
        self.story_topic = tk.StringVar()
        self.story_main_image = tk.StringVar()
        self.story_scene_count = tk.IntVar(value=10)
        self.story_video_mode = tk.StringVar(value="ภาพเคลื่อนไหวอัตโนมัติ")
        self.story_job_id = tk.StringVar()
        self.story_status = tk.StringVar(value="ใส่หัวข้อหรือเรื่องเล่า แล้วกดเริ่มครั้งเดียว")
        saved_ai_provider = str(cfg.get("image_ai_provider", "chatgpt"))
        self.image_ai_provider = tk.StringVar(value=next((label for label, key in IMAGE_AI_PROVIDERS.items() if key == saved_ai_provider), "ChatGPT Web"))
        self.chatgpt_web_model = tk.StringVar(value=normalize_ai_web_model("chatgpt", cfg.get("chatgpt_web_model")))
        self.gemini_web_model = tk.StringVar(value=normalize_ai_web_model("gemini", cfg.get("gemini_web_model")))
        saved_video_provider = str(cfg.get("video_ai_provider", "flow"))
        if saved_video_provider not in {"flow", "meta_ai"}:
            saved_video_provider = "flow"
            cfg["video_ai_provider"] = "flow"
            save_video_settings({"video_ai_provider": "flow"})
        self.video_ai_provider = tk.StringVar(value=next((label for label, key in VIDEO_AI_PROVIDERS.items() if key == saved_video_provider), "Google Flow"))
        self.story_provider_note = tk.StringVar(value=f"แหล่งภาพ: {self.image_ai_provider.get()} ผ่าน Chrome\nเลือกได้ว่าจะประกอบภาพเดิมหรือส่งทุกฉากเข้า Google Flow")
        saved_resolution = str(cfg.get("video_resolution", "720x1280"))
        self.video_resolution = tk.StringVar(value=next((label for label, value in VIDEO_RESOLUTIONS.items() if value == saved_resolution), "720p HD • 720 × 1280"))
        self.video_fps = tk.StringVar(value=str(int(cfg.get("video_fps", 30))))
        self.video_encoder = tk.StringVar(value=str(cfg.get('video_encoder', 'auto')))
        saved_quality = str(cfg.get("video_quality", "high"))
        self.video_quality = tk.StringVar(value=next((label for label, value in VIDEO_QUALITIES.items() if value == saved_quality), "คมชัดสูง • แนะนำ"))
        self.video_motion_strength = tk.IntVar(value=round(float(cfg.get("video_motion_strength", 1.0)) * 100))
        self.video_transition_ms = tk.IntVar(value=round(float(cfg.get("video_transition_sec", 0.22)) * 1000))
        self.video_settings_status = tk.StringVar(value="ค่าที่บันทึกจะใช้กับ Story และวิดีโอ AI รอบถัดไป")
        self._story_render_active = None
        self._story_pipeline_job_id = ""
        self._story_cancel_event = None
        self._story_progress_dialog = None
        self._story_progress_value = tk.DoubleVar(value=0)
        self._story_progress_percent = tk.StringVar(value="0%")
        self._story_progress_message = tk.StringVar(value="กำลังเตรียมงาน")
        self._story_progress_detail = tk.StringVar(value="ยังไม่ได้เริ่ม")
        self._story_progress_job = tk.StringVar(value="")
        self._story_progress_stage_widgets = {}
        self._story_popup_terminal = False
        self._story_monitor_after = None
        self._story_verification_jobs = {}
        self._story_web_actions = {}
        self.library_status = tk.StringVar(value="กำลังตรวจสอบผลงานที่เสร็จแล้ว")
        self._library_items = {}
        self._library_delete_active = False
        self._library_detail_dialog = None
        self._project_manager_dialog = None
        self._project_manager_table = None
        self._project_manager_items = {}
        self._project_delete_active = False
        self.voice_api_key = tk.StringVar()
        self.voice_job_id = tk.StringVar()
        saved_reference_file = str(cfg.get("voice_reference_file", ""))
        self.voice_reference_file = tk.StringVar(value=saved_reference_file if Path(saved_reference_file).is_file() else "")
        self.voice_reference_id = tk.StringVar(value=str(cfg.get("voice_reference_id", "")))
        self.voice_language = tk.StringVar(value=str(cfg.get("voice_language", "th")))
        self.voice_emotion = tk.StringVar(value=CLIP_VOICE_EMOTION)
        self.voice_speed = tk.StringVar(value=str(CLIP_VOICE_SPEED))
        self.voice_silence = tk.StringVar(value=str(cfg.get("voice_silence_sec", 0.3)))
        self.voice_format = tk.StringVar(value=str(cfg.get("voice_output_format", "mp3")))
        self.voice_status = tk.StringVar(value="พร้อมตั้งค่าเสียง AI • API Key จะไม่ถูกบันทึก")
        self.voice_show_key = tk.BooleanVar(value=False)
        self.voice_key_saved = tk.StringVar(value="○ ยังไม่ได้เชื่อมต่อ")
        self.voice_catalog_choice = tk.StringVar(value="กดโหลดรายการเสียง")
        self.voice_catalog_info = tk.StringVar(value="เสียงพื้นฐานของระบบ + เสียงที่บันทึกในบัญชีนี้")
        self._voice_catalog_by_label = {}
        self._service_credit_state = {
            "voice": self._credit_state(False, "ยังไม่ได้เชื่อม AI Voice"),
            "subtitle": self._credit_state(False, "ยังไม่ได้เชื่อม AI Subtitle"),
        }
        self._service_credit_refreshing = False
        self._service_credit_last_requested = 0.0
        self.subtitle_token = tk.StringVar()
        self.subtitle_show_token = tk.BooleanVar(value=False)
        self.subtitle_job_id = tk.StringVar()
        self.subtitle_language = tk.StringVar(value=str(cfg.get("subtitle_language", "th")))
        self.subtitle_syllables = tk.StringVar(value=str(cfg.get("subtitle_syllables_per_cue", 3)))
        self.subtitle_auto = tk.BooleanVar(value=bool(cfg.get("subtitle_auto_after_voice", True)))
        self.subtitle_preference_status = tk.StringVar(value="เปิดใช้งานถาวร" if self.subtitle_auto.get() else "ปิดใช้งาน")
        self.subtitle_client_id = str(cfg.get("subtitle_client_id") or f"smartpost-{uuid.uuid4().hex[:16]}")
        self.subtitle_status = tk.StringVar(value="ยังไม่ได้เชื่อมต่อ Subtitle Token")
        self.subtitle_credential_saved = tk.StringVar(value="○ ยังไม่ได้เชื่อมต่อ")
        self.subtitle_audio_label = tk.StringVar(value="เลือก Product Job แล้วระบบจะหาไฟล์เสียงให้อัตโนมัติ")
        self.subtitle_font_label = tk.StringVar()
        self.subtitle_font_size = tk.IntVar(value=int(cfg.get("subtitle_font_size", 28)))
        self.subtitle_letter_spacing = tk.IntVar(value=int(cfg.get("subtitle_letter_spacing", 0)))
        self.subtitle_thai_mark_gap = tk.IntVar(value=int(cfg.get("subtitle_thai_mark_gap", 14)))
        self.subtitle_text_color = tk.StringVar(value=str(cfg.get("subtitle_text_color", "#FFFFFF")))
        self.subtitle_outline_color = tk.StringVar(value=str(cfg.get("subtitle_outline_color", "#101010")))
        self.subtitle_outline_width = tk.IntVar(value=int(cfg.get("subtitle_outline_width", 2)))
        self.subtitle_background_enabled = tk.BooleanVar(value=bool(cfg.get("subtitle_background_enabled", False)))
        self.subtitle_background_color = tk.StringVar(value=str(cfg.get("subtitle_background_color", "#000000")))
        self.subtitle_background_opacity = tk.IntVar(value=round(float(cfg.get("subtitle_background_opacity", 0.45)) * 100))
        self.subtitle_highlight_color = tk.StringVar(value=str(cfg.get("subtitle_highlight_color", "#FACC15")))
        saved_theme_key = str(cfg.get("subtitle_theme", "standard"))
        self.subtitle_theme = tk.StringVar(value=SUBTITLE_THEMES.get(saved_theme_key, SUBTITLE_THEMES["standard"])["label"])
        self.subtitle_theme_random = tk.BooleanVar(value=bool(cfg.get("subtitle_theme_random", False)))
        saved_animation_key = str(cfg.get("subtitle_animation", "fade"))
        self.subtitle_animation = tk.StringVar(value=SUBTITLE_ANIMATIONS.get(saved_animation_key, SUBTITLE_ANIMATIONS["fade"]))
        self.subtitle_animation_random = tk.BooleanVar(value=bool(cfg.get("subtitle_animation_random", False)))
        self.subtitle_position = tk.StringVar(value={"top": "ด้านบน", "center": "กึ่งกลาง", "bottom": "ด้านล่าง"}.get(str(cfg.get("subtitle_position", "bottom")), "ด้านล่าง"))
        default_y = {"ด้านบน": 10, "กึ่งกลาง": 50, "ด้านล่าง": 90}[self.subtitle_position.get()]
        self.subtitle_position_y = tk.IntVar(value=int(cfg.get("subtitle_position_y_percent", default_y)))
        self.subtitle_margin_v = tk.IntVar(value=int(cfg.get("subtitle_margin_v", 72)))
        self._subtitle_font_records = []
        self._subtitle_preview_photo = None
        self._subtitle_preview_source_image = None
        self._subtitle_preview_dimensions = None
        self._subtitle_style_after = None
        self._subtitle_preview_token = 0
        self._subtitle_preview_busy = False
        self._subtitle_preview_error_message = ""
        self.subtitle_preview_meta = tk.StringVar(value="กำลังสร้างพรีวิวจริง...")
        self._subtitle_active_job = None
        self._subtitle_render_active = None
        self.audio_job_id = tk.StringVar()
        self.audio_background_enabled = tk.BooleanVar(value=bool(cfg.get("audio_background_enabled", True)))
        saved_background_mode = str(cfg.get("audio_background_mode", "อัตโนมัติ • ยำท่อนสั้น V2"))
        if saved_background_mode == "อัตโนมัติ • ยำ 3 ช่วง":
            saved_background_mode = "อัตโนมัติ • ยำท่อนสั้น V2"
        self.audio_background_mode = tk.StringVar(value=saved_background_mode)
        self.audio_background_file = tk.StringVar(value=str(cfg.get("audio_background_file", "สุ่มจากคลัง")))
        self.audio_background_volume = tk.IntVar(value=round(float(cfg.get("audio_background_volume", 0.12)) * 100))
        saved_segment_max = float(cfg.get("audio_background_segment_max_sec", 12.0))
        # Migrate the older 4–8 second preset that sounded too busy.  The new
        # simple mixer keeps every random cut within the user-approved 8–12s.
        if saved_segment_max < 8:
            saved_segment_max = 12.0
        self.audio_background_segment_max = tk.DoubleVar(value=max(8.0, min(12.0, saved_segment_max)))
        self.audio_background_duck_percent = tk.IntVar(value=int(cfg.get("audio_background_duck_percent", 38)))
        self.audio_sfx_enabled = tk.BooleanVar(value=bool(cfg.get("audio_sfx_enabled", True)))
        self.audio_sfx_mode = tk.StringVar(value=str(cfg.get("audio_sfx_mode", "อัตโนมัติ • เว้นจังหวะ")))
        self.audio_sfx_file = tk.StringVar(value=str(cfg.get("audio_sfx_file", "สุ่มจากคลัง")))
        self.audio_sfx_volume = tk.IntVar(value=round(float(cfg.get("audio_sfx_volume", 0.22)) * 100))
        self.audio_sfx_min_interval = tk.IntVar(value=int(cfg.get("audio_sfx_min_interval", 6)))
        self.audio_sfx_max_count = tk.IntVar(value=int(cfg.get("audio_sfx_max_count", 6)))
        self.audio_status = tk.StringVar(value="พร้อมใส่เพลงคลอและเสียงข้อความแบบมืออาชีพ")
        self._audio_render_active = None
        saved_logo = str(cfg.get("logo_file") or ROOT / "assets" / "smartflow_logo.png")
        # The previous SmartPost artwork is a different logo. Migrate only
        # that bundled legacy default; never replace a logo uploaded by user.
        if Path(saved_logo).name.casefold() == "smartpost_logo.jpg":
            saved_logo = str(ROOT / "assets" / "smartflow_logo.png")
        self.logo_job_id = tk.StringVar()
        self.logo_file = tk.StringVar(value=saved_logo if Path(saved_logo).is_file() else "")
        self.logo_opacity = tk.DoubleVar(value=float(cfg.get("logo_opacity", 0.8)) * 100)
        self.logo_size = tk.DoubleVar(value=float(cfg.get("logo_size_percent", 18)))
        self.logo_position = tk.StringVar(value=POSITIONS.get(str(cfg.get("logo_position", "bottom_right")), POSITIONS["bottom_right"]))
        self.logo_margin = tk.IntVar(value=int(cfg.get("logo_margin", 28)))
        self.logo_status = tk.StringVar(value="เลือก Job ที่มีวิดีโอ แล้วกดดูตัวอย่าง")
        self.logo_opacity_text = tk.StringVar()
        self.logo_size_text = tk.StringVar()
        self.logo_margin_text = tk.StringVar()
        self._logo_frame_cache = None
        self._logo_preview_photo = None
        self._logo_preview_token = 0
        self._logo_preview_asset_id = ""
        self.logo_layout = normalize_logo_layout(cfg.get('logo_layout'))
        self._logo_editor_request = ''
        self._logo_editor_preview = {}
        self._logo_editor_files = ()
        self.dry = tk.BooleanVar(value=bool(cfg.get("dry_run", True)))
        self.confirm = tk.BooleanVar(value=bool(cfg.get("confirm_before_post", True)))
        self.pages = {}
        self.nav_buttons = {}
        self.nav_markers = {}
        self._images = []

        self._load_subtitle_fonts(str(cfg.get("subtitle_font_file", "")))
        self._configure_styles()
        self._load_saved_voice_key()
        self._load_saved_subtitle_credential()
        self._build_shell()
        self._refresh()
        if self.voice_api_key.get().strip():
            self.root.after(500, lambda: self._refresh_voice_catalog(silent=True))
        self.root.after(900, lambda: self._refresh_service_credits(force=True, silent=True))
        self.root.after(100, self._poll)
        self.root.after(2500, self._resume_pending_subtitles)
        self.root.after(15000, self._periodic_refresh)
        self._bg(self._check)

        try:
            self.membership.start()
            self.bridge.start()
            self.bridge_status.set(f"LOCAL BRIDGE • ONLINE :{cfg.get('bridge_port', 8765)}")
            self.root.after(600, self._start_browser_connection)
            self.root.after(900, self._refresh_guide_status)
            self.root.after(1200, self._resume_interrupted_product_on_startup)
            self.root.after(2800, self._resume_interrupted_story_on_startup)
            self.root.after(4200, self._resume_story_queue_on_startup)
        except OSError as exc:
            self.bridge_status.set("LOCAL BRIDGE • PORT ถูกใช้งาน")
            self._write_console(f"Local Bridge เปิดไม่ได้: {exc}", "error")
        self.root.protocol("WM_DELETE_WINDOW", self._hide_legacy if self.hybrid_engine else self._close)

    def _backfill_story_short_covers(self):
        """Upgrade finished standalone stories that predate dedicated Shorts covers."""
        migrated = 0
        for job in self.stories.list_jobs():
            if job.get("job_type") != "story_short" or not job.get("generated_images"):
                continue
            if not job.get("video_path") or job.get("video_status") != "ready":
                continue
            try:
                before = str(job.get("cover_path") or "")
                covered = self.stories.ensure_story_cover(job["id"])
                if not before and covered.get("cover_path"):
                    migrated += 1
            except (OSError, ValueError) as exc:
                self.log.warning(
                    "job_id=%s state=STORY_COVER_BACKFILL result=skip error=%s",
                    job.get("id"), exc,
                )
        if migrated:
            self.log.info("state=STORY_COVER_BACKFILL result=success count=%s", migrated)

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Dark.Treeview", background=COLORS["panel"], fieldbackground=COLORS["panel"], foreground=COLORS["text"], borderwidth=0, rowheight=38, font=("Segoe UI", 10))
        style.configure("Dark.Treeview.Heading", background=COLORS["panel_2"], foreground=COLORS["muted"], relief="flat", borderwidth=0, padding=(10, 9), font=("Segoe UI Semibold", 9))
        style.map("Dark.Treeview", background=[("selected", "#203665")], foreground=[("selected", "#FFFFFF")])
        style.map("Dark.Treeview.Heading", background=[("active", COLORS["panel_2"])])
        style.configure("Primary.TButton", background=COLORS["blue"], foreground="white", borderwidth=0, focusthickness=0, padding=(16, 10), font=("Segoe UI Semibold", 10))
        style.map("Primary.TButton", background=[("active", COLORS["blue_hover"]), ("pressed", "#3D68E6"), ("disabled", "#263450")], foreground=[("disabled", "#7A88A7")])
        style.configure("PrimaryLarge.TButton", background=COLORS["blue"], foreground="white", borderwidth=0, focusthickness=0, padding=(20, 13), font=("Segoe UI Semibold", 11))
        style.map("PrimaryLarge.TButton", background=[("active", COLORS["blue_hover"]), ("pressed", "#3D68E6"), ("disabled", "#263450")], foreground=[("disabled", "#7A88A7")])
        style.configure("Accent.TButton", background=COLORS["purple"], foreground="white", borderwidth=0, focusthickness=0, padding=(15, 10), font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", "#B86CF8"), ("pressed", "#9143D5")])
        style.configure("Ghost.TButton", background=COLORS["panel_2"], foreground=COLORS["text"], borderwidth=0, focusthickness=0, padding=(13, 9), font=("Segoe UI", 10))
        style.map("Ghost.TButton", background=[("active", "#202C48"), ("pressed", "#18233C")], foreground=[("disabled", COLORS["subtle"])])
        style.configure("Quiet.TButton", background=COLORS["panel"], foreground=COLORS["muted"], borderwidth=1, focusthickness=0, padding=(12, 8), font=("Segoe UI", 9))
        style.map("Quiet.TButton", background=[("active", COLORS["panel_2"])], foreground=[("active", COLORS["text"])])
        style.configure("Dark.TCheckbutton", background=COLORS["panel"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.map("Dark.TCheckbutton", background=[("active", COLORS["panel"])], indicatorcolor=[("selected", COLORS["purple"]), ("!selected", COLORS["panel_2"])])
        for combo_style in ("TCombobox", "Dark.TCombobox"):
            style.configure(combo_style, fieldbackground=COLORS["panel_3"], background=COLORS["panel_2"], foreground=COLORS["text"], arrowcolor=COLORS["muted"], bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"], padding=(9, 7), font=("Segoe UI", 10))
            style.map(combo_style, fieldbackground=[("readonly", COLORS["panel_3"])], foreground=[("readonly", COLORS["text"])], selectbackground=[("readonly", COLORS["panel_3"])], selectforeground=[("readonly", COLORS["text"])])
        style.configure("Story.Horizontal.TScale", background=COLORS["panel"], troughcolor=COLORS["panel_3"], borderwidth=0, lightcolor=COLORS["blue"], darkcolor=COLORS["blue"])
        style.configure("Story.Horizontal.TProgressbar", background=COLORS["blue"], troughcolor=COLORS["panel_3"], borderwidth=0, lightcolor=COLORS["blue"], darkcolor=COLORS["blue"], thickness=12)
        style.configure("Vertical.TScrollbar", background=COLORS["panel_2"], troughcolor=COLORS["panel_3"], bordercolor=COLORS["line"], arrowcolor=COLORS["muted"], lightcolor=COLORS["panel_2"], darkcolor=COLORS["panel_2"])
        style.map("Vertical.TScrollbar", background=[("active", "#25345C"), ("pressed", COLORS["blue"])])

    def _build_shell(self):
        sidebar = tk.Frame(self.root, bg=COLORS["sidebar"], width=248)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        body = tk.Frame(self.root, bg=COLORS["bg"])
        body.pack(side="left", fill="both", expand=True)
        self.page_host = tk.Frame(body, bg=COLORS["bg"])
        self.page_host.pack(fill="both", expand=True, padx=28, pady=(24, 14))
        self.footer = tk.Frame(body, bg=COLORS["sidebar"], height=38, highlightbackground=COLORS["line_soft"], highlightthickness=1)
        self.footer.pack(fill="x", side="bottom")
        tk.Label(self.footer, text="●", bg=COLORS["sidebar"], fg=COLORS["green"], font=("Segoe UI", 8)).pack(side="left", padx=(18, 7), pady=9)
        tk.Label(self.footer, textvariable=self.status, bg=COLORS["sidebar"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(side="left", pady=9)
        tk.Label(self.footer, text="SAFE MODE  •  ป้องกันการโพสต์โดยไม่ยืนยัน", bg=COLORS["sidebar"], fg=COLORS["green"], font=("Segoe UI Semibold", 8)).pack(side="right", padx=18)

        self._build_dashboard()
        self._build_guide()
        self._build_products()
        self._build_story()
        self._build_video_library()
        self._build_video_settings()
        self._build_voice()
        self._build_subtitle()
        self._build_audio()
        self._build_logo()
        self._build_queue()
        self._build_logs()
        self._show_page("dashboard")

    def _build_sidebar(self, parent):
        brand = tk.Frame(parent, bg=COLORS["sidebar"])
        brand.pack(fill="x", padx=20, pady=(22, 22))
        logo_path = ROOT / "assets" / "smartflow_icon.png"
        if logo_path.exists():
            image = Image.open(logo_path).convert("RGB")
            image.thumbnail((52, 52), Image.Resampling.LANCZOS)
            logo = ImageTk.PhotoImage(image)
            self._images.append(logo)
            tk.Label(brand, image=logo, bg=COLORS["sidebar"], bd=0).pack(side="left")
            try:
                icon = ImageTk.PhotoImage(Image.open(logo_path).resize((64, 64), Image.Resampling.LANCZOS))
                self._images.append(icon); self.root.iconphoto(True, icon)
            except Exception:
                pass
        title = tk.Frame(brand, bg=COLORS["sidebar"]); title.pack(side="left", padx=(11, 0))
        tk.Label(title, text="SMARTFLOW AI", bg=COLORS["sidebar"], fg=COLORS["text"], font=("Segoe UI Semibold", 13)).pack(anchor="w")
        tk.Label(title, text="AI CLIP CREATOR", bg=COLORS["sidebar"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(2, 0))

        tk.Label(parent, text="พื้นที่ทำงาน", bg=COLORS["sidebar"], fg=COLORS["subtle"], font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=24, pady=(0, 8))
        for key, icon, label in (
            ("dashboard", "◈", "ภาพรวม"),
            ("guide", "?", "คู่มือ / ติดตั้ง Extension"),
            ("products", "▦", "สินค้าจาก Affiliate"),
            ("story", "✦", "เล่าเรื่อง Shorts"),
            ("library", "▣", "คลังวิดีโอ"),
            ("video", "◫", "ตั้งค่าวิดีโอ"),
            ("voice", "◉", "AI Voice / บทพูด"),
            ("subtitle", "▤", "AI Subtitle"),
            ("audio", "♫", "เสียงประกอบ"),
            ("logo", "◆", "โลโก้วิดีโอ"),
            ("queue", "▶", "คิววิดีโอ"),
            ("logs", "≡", "ระบบและ Log"),
        ):
            item = tk.Frame(parent, bg=COLORS["sidebar"])
            item.pack(fill="x", padx=10, pady=2)
            marker = tk.Frame(item, bg=COLORS["sidebar"], width=3)
            marker.pack(side="left", fill="y")
            button = tk.Button(item, text=f"  {icon}   {label}", command=lambda k=key: self._show_page(k), anchor="w", relief="flat", bd=0, bg=COLORS["sidebar"], fg=COLORS["cyan"] if key == "guide" else COLORS["muted"], activebackground="#17213A", activeforeground="white", font=("Segoe UI Semibold", 9), padx=14, pady=7, cursor="hand2")
            button.pack(side="left", fill="x", expand=True)
            self.nav_buttons[key] = button
            self.nav_markers[key] = marker

        bottom = tk.Frame(parent, bg=COLORS["sidebar"])
        bottom.pack(side="bottom", fill="x", padx=16, pady=18)
        connection = tk.Frame(bottom, bg=COLORS["panel_3"], highlightbackground=COLORS["line_soft"], highlightthickness=1)
        connection.pack(fill="x")
        tk.Label(connection, text="การเชื่อมต่อ", bg=COLORS["panel_3"], fg=COLORS["subtle"], font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=11, pady=(10, 4))
        tk.Label(connection, text="●  ChatGPT / Gemini Web • ไม่ใช้ API Key", bg=COLORS["panel_3"], fg="#D8B4FE", font=("Segoe UI Semibold", 8), wraplength=190, justify="left").pack(anchor="w", padx=11, pady=3)
        tk.Label(connection, textvariable=self.bridge_status, bg=COLORS["panel_3"], fg=COLORS["green"], font=("Segoe UI Semibold", 8), padx=10, pady=3, anchor="w").pack(fill="x")
        tk.Label(connection, textvariable=self.extension_status, bg=COLORS["panel_3"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 8), padx=10, pady=3, wraplength=190, justify="left", anchor="w").pack(fill="x", pady=(0, 8))
        tk.Label(bottom, text="v0.7 • One-Click Creator Workspace", bg=COLORS["sidebar"], fg=COLORS["subtle"], font=("Segoe UI", 8)).pack(pady=(9, 0))

    def _page(self, name):
        frame = tk.Frame(self.page_host, bg=COLORS["bg"])
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.pages[name] = frame
        return frame

    def _heading(self, parent, title, subtitle, action=None):
        row = tk.Frame(parent, bg=COLORS["bg"]); row.pack(fill="x", pady=(0, 16))
        left = tk.Frame(row, bg=COLORS["bg"]); left.pack(side="left")
        tk.Label(left, text=title, bg=COLORS["bg"], fg=COLORS["text"], font=("Segoe UI Semibold", 22)).pack(anchor="w")
        tk.Label(left, text=subtitle, bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        if action: action(row)

    def _panel(self, parent, **pack):
        frame = tk.Frame(parent, bg=COLORS["panel"], highlightbackground=COLORS["line_soft"], highlightthickness=1)
        frame.pack(**pack)
        return frame

    def _scroll_panel(self, parent, width=None, **pack):
        """Panel with a vertical viewport for dense settings on short screens."""
        outer = tk.Frame(parent, bg=COLORS["panel"], highlightbackground=COLORS["line_soft"], highlightthickness=1)
        outer.pack(**pack)
        if width:
            outer.configure(width=width)
            outer.pack_propagate(False)
        canvas = tk.Canvas(outer, bg=COLORS["panel"], highlightthickness=0, bd=0, yscrollincrement=28)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=COLORS["panel"])
        body._smartpost_scroll_body = True
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def sync_viewport(event=None):
            canvas.update_idletasks()
            viewport_width = max(1, canvas.winfo_width())
            viewport_height = max(1, canvas.winfo_height())
            content_height = max(viewport_height, body.winfo_reqheight())
            canvas.itemconfigure(window_id, width=viewport_width, height=content_height)
            canvas.configure(scrollregion=(0, 0, viewport_width, content_height))

        body.bind("<Configure>", lambda event: body.after_idle(sync_viewport))
        canvas.bind("<Configure>", sync_viewport)

        def wheel(event):
            if not outer.winfo_ismapped():
                return None
            pointer_x, pointer_y = outer.winfo_pointerxy()
            left, top = outer.winfo_rootx(), outer.winfo_rooty()
            if left <= pointer_x <= left + outer.winfo_width() and top <= pointer_y <= top + outer.winfo_height():
                canvas.yview_scroll(-int(event.delta / 120) if event.delta else 0, "units")
                return "break"
            return None

        self.root.bind_all("<MouseWheel>", wheel, add="+")
        return outer, body

    def _build_dashboard(self):
        page = self._page("dashboard")
        self._heading(page, "ศูนย์ควบคุม", "Shopee Affiliate → AI Content → Android AutoPost")

        device_card = self._panel(page, fill="x", pady=(0, 15))
        accent = tk.Frame(device_card, bg=COLORS["cyan"], width=4); accent.pack(side="left", fill="y")
        device_info = tk.Frame(device_card, bg=COLORS["panel"]); device_info.pack(side="left", fill="both", expand=True, padx=18, pady=15)
        badge = tk.Frame(device_info, bg=COLORS["panel"]); badge.pack(fill="x")
        tk.Label(badge, text="ANDROID DEVICE", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Label(badge, textvariable=self.device_badge, bg="#153D3B", fg=COLORS["green"], font=("Segoe UI Semibold", 8), padx=9, pady=3).pack(side="right")
        tk.Label(device_info, textvariable=self.device, bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI", 11), wraplength=650, justify="left").pack(anchor="w", pady=(9, 0))
        actions = tk.Frame(device_card, bg=COLORS["panel"]); actions.pack(side="right", padx=16)
        ttk.Button(actions, text="ตรวจ Connection", style="Ghost.TButton", command=lambda: self._bg(self._check)).pack(side="left", padx=4)
        ttk.Button(actions, text="เปิดมือถือ", style="Primary.TButton", command=self._scrcpy).pack(side="left", padx=4)

        stats = tk.Frame(page, bg=COLORS["bg"]); stats.pack(fill="x", pady=(0, 15))
        for index, (label, var, color) in enumerate((("สินค้า", self.stat_products, COLORS["cyan"]), ("AI พร้อม", self.stat_ai, COLORS["purple"]), ("มีวิดีโอ", self.stat_videos, COLORS["blue"]), ("โพสต์สำเร็จ", self.stat_posts, COLORS["green"]))):
            card = tk.Frame(stats, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0 if index == 3 else 6))
            stats.columnconfigure(index, weight=1)
            tk.Label(card, text=label, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=15, pady=(13, 2))
            tk.Label(card, textvariable=var, bg=COLORS["panel"], fg=color, font=("Segoe UI Semibold", 24)).pack(anchor="w", padx=15, pady=(0, 12))

        pipeline = self._panel(page, fill="both", expand=True)
        tk.Label(pipeline, text="CONTENT PIPELINE", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=18, pady=(16, 12))
        flow = tk.Frame(pipeline, bg=COLORS["panel"]); flow.pack(fill="x", padx=18)
        stages = (("01", "วางลิงก์สินค้า", "Product Source"), ("02", "สร้างคอนเทนต์", "AI Web"), ("03", "สร้างวิดีโอ", "AI Video Provider"), ("04", "ส่งเข้ามือถือ", "ADB Transfer"), ("05", "ตรวจและโพสต์", "Safe Dry Run"))
        for index, (number, title, subtitle) in enumerate(stages):
            stage = tk.Frame(flow, bg=COLORS["panel_2"], highlightbackground=COLORS["line"], highlightthickness=1)
            stage.grid(row=0, column=index * 2, sticky="nsew", padx=3)
            flow.columnconfigure(index * 2, weight=1)
            tk.Label(stage, text=number, bg=COLORS["panel_2"], fg=COLORS["purple"] if index < 2 else COLORS["blue"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=12, pady=(12, 5))
            tk.Label(stage, text=title, bg=COLORS["panel_2"], fg=COLORS["text"], font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=12)
            tk.Label(stage, text=subtitle, bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(3, 12))
            if index < len(stages) - 1:
                tk.Label(flow, text="›", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI", 18)).grid(row=0, column=index * 2 + 1)

        automation_options = tk.Frame(pipeline, bg="#111A34", highlightbackground=COLORS["line"], highlightthickness=1)
        automation_options.pack(fill="x", padx=18, pady=(16, 0))
        ttk.Checkbutton(automation_options, text="สร้าง Subtitle ให้ทุกงานอัตโนมัติ", variable=self.subtitle_auto, style="Dark.TCheckbutton", command=self._subtitle_option_changed).pack(side="left", padx=(14, 8), pady=11)
        tk.Label(automation_options, textvariable=self.subtitle_preference_status, bg="#111A34", fg=COLORS["green"], font=("Segoe UI Semibold", 8)).pack(side="left")
        tk.Label(automation_options, text="ติ๊กครั้งเดียว โปรแกรมจะจำค่าและทำต่อทันทีเมื่อเสียง AI พร้อม", bg="#111A34", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="right", padx=14)

        quick = tk.Frame(pipeline, bg=COLORS["panel"]); quick.pack(fill="x", padx=18, pady=18)
        quick_primary = tk.Frame(quick, bg=COLORS["panel"]); quick_primary.pack(fill="x")
        ttk.Button(quick_primary, text="AUTO GOOGLE FLOW", style="Primary.TButton", command=self._send_to_google_flow).pack(side="left", padx=(0, 8))
        ttk.Button(quick_primary, text="+ เพิ่มลิงก์สินค้า", style="Primary.TButton", command=lambda: self._show_page("products")).pack(side="left")
        ttk.Button(quick_primary, text="เปิด Shopee Affiliate", style="Ghost.TButton", command=self._open_affiliate).pack(side="left", padx=8)

    def _build_guide(self):
        page = self._page("guide")
        self._heading(
            page,
            "คู่มือเริ่มต้น",
            "ติดตั้ง Chrome Extension และตรวจความพร้อมก่อนสร้างคลิปแบบปุ่มเดียว",
            lambda row: tk.Label(row, text="SETUP CENTER", bg="#102A28", fg=COLORS["green"], font=("Segoe UI Semibold", 8), padx=12, pady=7).pack(side="right", pady=4),
        )

        hero = tk.Frame(page, bg="#111D37", highlightbackground="#294A79", highlightthickness=1)
        hero.pack(fill="x", pady=(0, 8))
        hero_copy = tk.Frame(hero, bg="#111D37"); hero_copy.pack(side="left", fill="both", expand=True, padx=18, pady=9)
        tk.Label(hero_copy, text="เริ่มสร้างคลิปใน 4 ขั้นตอน", bg="#111D37", fg=COLORS["text"], font=("Segoe UI Semibold", 15)).pack(anchor="w")
        tk.Label(hero_copy, text="ติดตั้ง Extension → ล็อกอินเว็บ → ตั้งค่าเสียง → วางลิงก์แล้วกดสร้าง", bg="#111D37", fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        ttk.Button(hero, text="✦  ไปหน้าสร้างคลิปสินค้า", style="PrimaryLarge.TButton", command=lambda: self._show_page("products")).pack(side="right", padx=18)

        status_row = tk.Frame(page, bg=COLORS["bg"]); status_row.pack(fill="x", pady=(0, 8))
        self._guide_status_labels = {}
        cards = (
            ("bridge", "01", "โปรแกรมเชื่อมเว็บ", self.guide_bridge),
            ("extension", "02", "Chrome Extension", self.guide_extension),
            ("voice", "03", "AI Voice", self.guide_voice),
            ("subtitle", "04", "AI Subtitle", self.guide_subtitle),
        )
        for index, (key, number, title, variable) in enumerate(cards):
            card = tk.Frame(status_row, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 5, 0 if index == len(cards) - 1 else 5))
            status_row.columnconfigure(index, weight=1)
            head = tk.Frame(card, bg=COLORS["panel"]); head.pack(fill="x", padx=12, pady=(7, 3))
            tk.Label(head, text=number, bg="#17284A", fg=COLORS["cyan"], font=("Segoe UI Semibold", 8), padx=7, pady=2).pack(side="left")
            indicator = tk.Label(head, text="●", bg=COLORS["panel"], fg=COLORS["orange"], font=("Segoe UI", 9)); indicator.pack(side="right")
            tk.Label(card, text=title, bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=12)
            value_label = tk.Label(card, textvariable=variable, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=220, justify="left")
            value_label.pack(anchor="w", padx=12, pady=(2, 7))
            self._guide_status_labels[key] = (indicator, value_label)

        content = tk.Frame(page, bg=COLORS["bg"]); content.pack(fill="both", expand=True)
        extension_panel = self._panel(content, side="left", fill="both", expand=True, padx=(0, 6))
        workflow_panel = self._panel(content, side="left", fill="both", expand=True, padx=(6, 0))

        tk.Label(extension_panel, text="ติดตั้ง Extension บน Google Chrome", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=17, pady=(11, 2))
        tk.Label(extension_panel, text="ติดตั้งครั้งเดียว แล้วโปรแกรมจะสั่ง ChatGPT/Gemini และ Google Flow ผ่าน Chrome", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=560, justify="left").pack(anchor="w", padx=17, pady=(0, 6))

        def guide_step(parent, number, title, detail):
            row = tk.Frame(parent, bg=COLORS["panel_3"], highlightbackground=COLORS["line_soft"], highlightthickness=1)
            row.pack(fill="x", padx=17, pady=1)
            tk.Label(row, text=str(number), bg="#244B91", fg="white", font=("Segoe UI Semibold", 9), width=3, pady=2).pack(side="left", padx=(8, 10), pady=3)
            copy = tk.Frame(row, bg=COLORS["panel_3"]); copy.pack(side="left", fill="both", expand=True, pady=2)
            tk.Label(copy, text=title, bg=COLORS["panel_3"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w")
            tk.Label(copy, text=detail, bg=COLORS["panel_3"], fg=COLORS["muted"], font=("Segoe UI", 7), wraplength=480, justify="left").pack(anchor="w")

        guide_step(extension_panel, 1, "เปิดหน้าจัดการ Extension", "Chrome จะเปิดหน้า chrome://extensions ให้โดยตรง")
        guide_step(extension_panel, 2, "เปิด Developer mode", "เปิดสวิตช์มุมขวาบนของหน้า Extensions")
        guide_step(extension_panel, 3, "ติดตั้งครั้งแรกในโฟลเดอร์ถาวร", "กด Load unpacked เลือก browser_extension ของ SmartFlow AI • ไม่เลือกโฟลเดอร์หมายเลขรุ่นใหม่ทุกครั้ง")
        guide_step(extension_panel, 4, "อัปเดตตัวเดิมด้วย Reload", "ใช้โปรไฟล์และโฟลเดอร์เดิม อัปเดตไฟล์แล้ว Reload เมื่อไม่มีงานรัน • ไม่ลบ Extension เพื่อรักษาสิทธิ์และประวัติ")
        extension_actions = tk.Frame(extension_panel, bg=COLORS["panel"]); extension_actions.pack(fill="x", padx=17, pady=(5, 7))
        ttk.Button(extension_actions, text="เปิด Extensions", style="Primary.TButton", command=lambda: self._open_url("chrome://extensions")).pack(side="left")
        ttk.Button(extension_actions, text="เปิดโฟลเดอร์", style="Accent.TButton", command=lambda: self._open_folder(ROOT / "browser_extension")).pack(side="left", padx=7)
        ttk.Button(extension_actions, text="คัดลอก Path", style="Ghost.TButton", command=self._copy_extension_path).pack(side="left")

        tk.Label(workflow_panel, text="วิธีสร้างคลิปสินค้า", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=17, pady=(11, 2))
        tk.Label(workflow_panel, textvariable=self.guide_summary, bg="#102A28", fg=COLORS["green"], font=("Segoe UI Semibold", 9), padx=11, pady=5, wraplength=560, justify="left").pack(fill="x", padx=17, pady=(3, 6))
        guide_step(workflow_panel, 1, "ล็อกอินเว็บด้วยตัวเอง", "ล็อกอิน Shopee, AI Web และ Google Flow ใน Chrome")
        guide_step(workflow_panel, 2, "ตั้งค่า AI Voice และ Subtitle", "ตั้งค่า API Key, เสียง และ Subtitle Token ครั้งเดียว")
        guide_step(workflow_panel, 3, "เลือก AI สร้างภาพ", "เลือก ChatGPT Web หรือ Gemini Web")
        guide_step(workflow_panel, 4, "วางลิงก์แล้วกดปุ่มเดียว", "วางลิงก์ แล้วระบบสร้างคลิป Final อัตโนมัติ")
        web_actions = tk.Frame(workflow_panel, bg=COLORS["panel"]); web_actions.pack(fill="x", padx=17, pady=(5, 3))
        ttk.Button(web_actions, text="Shopee", style="Primary.TButton", command=self._open_affiliate).pack(side="left")
        ttk.Button(web_actions, text="Gemini", style="Ghost.TButton", command=lambda: self._open_url("https://gemini.google.com/app")).pack(side="left", padx=6)
        ttk.Button(web_actions, text="ChatGPT", style="Ghost.TButton", command=lambda: self._open_url("https://chatgpt.com/")).pack(side="left")
        lower_actions = tk.Frame(workflow_panel, bg=COLORS["panel"]); lower_actions.pack(fill="x", padx=17, pady=(0, 7))
        ttk.Button(lower_actions, text="ตรวจระบบ", style="Accent.TButton", command=self._refresh_guide_status).pack(side="left")
        ttk.Button(lower_actions, text="AI Voice", style="Ghost.TButton", command=lambda: self._show_page("voice")).pack(side="left", padx=6)
        ttk.Button(lower_actions, text="Subtitle", style="Ghost.TButton", command=lambda: self._show_page("subtitle")).pack(side="left")

    def _copy_extension_path(self):
        path = str((ROOT / "browser_extension").resolve())
        self.root.clipboard_clear(); self.root.clipboard_append(path)
        self.status.set("คัดลอกตำแหน่งโฟลเดอร์ Extension แล้ว")
        self._write_console(f"EXTENSION • คัดลอกตำแหน่งแล้ว • {path}", "success")

    def _refresh_guide_status(self):
        extension = self.bridge.extension_status()
        compatible = extension.get("connected") and str((extension.get("client") or {}).get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION
        voice_ready = bool(self.voice_api_key.get().strip() and (self.voice_reference_id.get().strip() or Path(self.voice_reference_file.get().strip()).is_file()))
        try:
            subtitle_ready = bool(self._subtitle_store().load())
        except Exception:
            subtitle_ready = False
        values = {
            "bridge": (self.bridge.server is not None, "Local Bridge ออนไลน์" if self.bridge.server is not None else "Local Bridge ยังไม่ทำงาน"),
            "extension": (compatible, f"Extension {self.bridge.REQUIRED_EXTENSION_VERSION} ออนไลน์" if compatible else f"ต้องติดตั้ง/Reload รุ่น {self.bridge.REQUIRED_EXTENSION_VERSION}"),
            "voice": (voice_ready, "API Key และเสียงพร้อม" if voice_ready else "ยังต้องตั้งค่า Key หรือเสียง"),
            "subtitle": (subtitle_ready, "เชื่อมรหัสอุปกรณ์แล้ว" if subtitle_ready else "ยังไม่ได้เชื่อม Subtitle Token"),
        }
        self.guide_bridge.set(values["bridge"][1]); self.guide_extension.set(values["extension"][1])
        self.guide_voice.set(values["voice"][1]); self.guide_subtitle.set(values["subtitle"][1])
        for key, (ready, _message) in values.items():
            widgets = self._guide_status_labels.get(key) if hasattr(self, "_guide_status_labels") else None
            if widgets:
                color = COLORS["green"] if ready else COLORS["danger"]
                widgets[0].configure(fg=color); widgets[1].configure(fg=color if ready else COLORS["orange"])
        ready_count = sum(ready for ready, _message in values.values())
        self.guide_summary.set("พร้อมสร้างคลิปแบบปุ่มเดียวแล้ว" if ready_count == 4 else f"พร้อม {ready_count}/4 รายการ • แก้รายการสีส้ม/แดงก่อนเริ่ม")
        self.status.set(f"ตรวจความพร้อมระบบแล้ว • {ready_count}/4")
        self._write_console(f"SETUP CHECK • พร้อม {ready_count}/4 • Bridge {'OK' if values['bridge'][0] else 'WAIT'} • Extension {'OK' if compatible else 'WAIT'} • Voice {'OK' if voice_ready else 'WAIT'} • Subtitle {'OK' if subtitle_ready else 'WAIT'}", "success" if ready_count == 4 else "error")

    def _build_products(self):
        page = self._page("products")
        self._heading(page, "สินค้าจาก Affiliate", "รายการที่นำเข้าจากหน้า product_offer", lambda row: ttk.Button(row, text="เปิด Shopee Affiliate", style="Primary.TButton", command=self._open_affiliate).pack(side="right", pady=5))
        link_panel = self._panel(page, fill="x", pady=(0, 12))
        link_text = tk.Frame(link_panel, bg=COLORS["panel"]); link_text.pack(fill="x", padx=14, pady=(12, 5))
        tk.Label(link_text, text="ลิงก์สินค้านายหน้า", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 10)).pack(side="left")
        tk.Label(link_text, text="ลิงก์นี้จะติดกับวิดีโอและใช้ตรวจสินค้าก่อนโพสต์", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(side="left", padx=12)
        provider_row = tk.Frame(link_panel, bg=COLORS["panel"])
        provider_row.pack(fill="x", padx=14, pady=(0, 6))
        ttk.Checkbutton(provider_row, text="เอา Subtitle ทุกงาน", variable=self.subtitle_auto, style="Dark.TCheckbutton", command=self._subtitle_option_changed).pack(side="right")
        self.product_ai_provider_combo = ttk.Combobox(provider_row, textvariable=self.image_ai_provider, values=tuple(IMAGE_AI_PROVIDERS), state="readonly", width=14, style="Dark.TCombobox")
        self.product_ai_provider_combo.pack(side="right", padx=(5, 10)); self.product_ai_provider_combo.bind("<<ComboboxSelected>>", lambda event: self._image_provider_changed())
        tk.Label(provider_row, text="สร้างรูปด้วย", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="right")
        self.product_video_provider_combo = ttk.Combobox(provider_row, textvariable=self.video_ai_provider, values=tuple(VIDEO_AI_PROVIDERS), state="readonly", width=24, style="Dark.TCombobox")
        self.product_video_provider_combo.pack(side="right", padx=(5, 10))
        tk.Label(provider_row, text="สร้างวิดีโอด้วย", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="right")
        link_row = tk.Frame(link_panel, bg=COLORS["panel"]); link_row.pack(fill="x", padx=14, pady=(0, 12))
        self.product_link_entry = tk.Entry(link_row, textvariable=self.product_link, bg="#080D1E", fg=COLORS["text"], insertbackground="white", relief="flat", highlightthickness=1, highlightbackground=COLORS["line"], highlightcolor=COLORS["blue"], font=("Segoe UI", 10))
        self.product_link_entry.pack(side="left", fill="x", expand=True, ipady=9)
        self.product_link_entry.bind("<Return>", lambda event: self._create_product_and_run())
        ttk.Button(link_row, text="วาง", style="Ghost.TButton", command=self._paste_link).pack(side="left", padx=7)
        ttk.Button(link_row, text="บันทึกลิงก์อย่างเดียว", style="Ghost.TButton", command=self._import_link).pack(side="left")
        self.product_run_button = ttk.Button(link_row, text="✦  สร้างคลิปขายอัตโนมัติจนเสร็จ", style="PrimaryLarge.TButton", command=self._create_product_and_run)
        self.product_run_button.pack(side="left", padx=(7, 0))
        toolbar = self._panel(page, fill="x", pady=(0, 12))
        toolbar_head = tk.Frame(toolbar, bg=COLORS["panel_2"])
        toolbar_head.pack(fill="x")
        tk.Label(toolbar_head, text="เครื่องมือทำต่อ / แก้เฉพาะขั้นตอน", bg=COLORS["panel_2"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left", padx=14, pady=7)
        tk.Label(toolbar_head, text="แยกเป็นหมวดเพื่อให้ทุกปุ่มมองเห็นในหน้าจอขนาดเล็ก", bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="left")

        create_actions = tk.Frame(toolbar, bg=COLORS["panel"])
        create_actions.pack(fill="x", padx=10, pady=(7, 3))
        tk.Label(create_actions, text="สร้างต่อ", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 8), width=10, anchor="w").pack(side="left", padx=(4, 2))
        ttk.Button(create_actions, text="AUTO FLOW", style="Primary.TButton", command=self._send_to_google_flow).pack(side="left", padx=3)
        ttk.Button(create_actions, text="MULTI FLOW ×3", style="Primary.TButton", command=self._start_multi_flow).pack(side="left", padx=3)
        ttk.Button(create_actions, text="AI VOICE", style="Accent.TButton", command=self._open_voice_for_selected).pack(side="left", padx=3)
        ttk.Button(create_actions, text="AI SUBTITLE", style="Accent.TButton", command=self._open_subtitle_for_selected).pack(side="left", padx=3)
        ttk.Button(create_actions, text="ใส่โลโก้", style="Accent.TButton", command=self._open_logo_for_selected).pack(side="left", padx=3)
        ttk.Button(create_actions, text="เอฟเฟกต์", style="Accent.TButton", command=self._render_product_effects).pack(side="left", padx=3)

        data_actions = tk.Frame(toolbar, bg=COLORS["panel"])
        data_actions.pack(fill="x", padx=10, pady=3)
        tk.Label(data_actions, text="ข้อมูล Job", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 8), width=10, anchor="w").pack(side="left", padx=(4, 2))
        ttk.Button(data_actions, text="AI Web", style="Primary.TButton", command=self._prepare_chatgpt_plugin).pack(side="left", padx=3)
        ttk.Button(data_actions, text="เพิ่มรูป", style="Accent.TButton", command=self._attach_product_images).pack(side="left", padx=3)
        ttk.Button(data_actions, text="เพิ่มวิดีโอ", style="Accent.TButton", command=self._attach_video).pack(side="left", padx=3)
        ttk.Button(data_actions, text="แก้ข้อมูล", style="Ghost.TButton", command=self._edit_selected_product).pack(side="left", padx=3)
        ttk.Button(data_actions, text="อนุมัติ AI", style="Ghost.TButton", command=self._approve_ai).pack(side="left", padx=3)
        ttk.Button(data_actions, text="ตรวจพร้อม", style="Ghost.TButton", command=self._check_selected_readiness).pack(side="left", padx=3)

        utility_actions = tk.Frame(toolbar, bg=COLORS["panel"])
        utility_actions.pack(fill="x", padx=10, pady=(3, 7))
        tk.Label(utility_actions, text="จัดการ", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI Semibold", 8), width=10, anchor="w").pack(side="left", padx=(4, 2))
        ttk.Button(utility_actions, text="คัดลอกลิงก์", style="Ghost.TButton", command=self._copy_selected_link).pack(side="left", padx=3)
        ttk.Button(utility_actions, text="เปิด Job", style="Ghost.TButton", command=self._open_selected_product).pack(side="left", padx=3)
        ttk.Button(utility_actions, text="รีเฟรช", style="Ghost.TButton", command=self._refresh).pack(side="left", padx=3)

        holder = self._panel(page, fill="both", expand=True)
        table_hint = tk.Frame(holder, bg=COLORS["panel_2"])
        table_hint.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(
            table_hint,
            text="เลือกผลงาน",
            bg=COLORS["panel_2"],
            fg=COLORS["cyan"],
            font=("Segoe UI Semibold", 9),
        ).pack(side="left", padx=(10, 8), pady=7)
        tk.Label(
            table_hint,
            text="คลิกที่แถวสินค้าเพื่อดูวิดีโอ ชื่อคลิป แคปชั่น และลิงก์นายหน้า",
            bg=COLORS["panel_2"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(side="left", pady=7)
        self.product_delete_all_button = tk.Button(
            table_hint,
            text="ลบทั้งหมด",
            command=self._delete_all_product_projects,
            relief="flat",
            bd=0,
            bg="#681B2E",
            fg="#FFFFFF",
            activebackground="#84243C",
            activeforeground="#FFFFFF",
            font=("Segoe UI Semibold", 9),
            padx=14,
            pady=7,
            cursor="hand2",
        )
        self.product_delete_all_button.pack(side="right", padx=7, pady=5)
        columns = ("id", "name", "product_id", "link", "ai", "voice", "subtitle", "video", "ready", "post")
        self.product_table = ttk.Treeview(holder, columns=columns, show="headings", style="Dark.Treeview")
        for key, title, width in zip(columns, ("JOB", "สินค้า", "Product ID", "ลิงก์", "AI", "เสียง", "ซับ", "วิดีโอ", "พร้อม", "โพสต์"), (135, 190, 95, 58, 68, 68, 68, 68, 70, 68)):
            self.product_table.heading(key, text=title); self.product_table.column(key, width=width, anchor="w")
        self.product_table.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.product_table.yview); scroll.pack(side="right", fill="y", padx=(0, 8), pady=10)
        self.product_table.configure(yscrollcommand=scroll.set)
        self.product_table.bind("<ButtonRelease-1>", self._product_table_clicked)
        self.product_table.bind("<Return>", lambda event: self._show_selected_product_detail())

    def _build_story(self):
        page = self._page("story")
        self._heading(
            page,
            "Story Shorts Studio",
            "ใส่เรื่องครั้งเดียว แล้วระบบสร้างบท ภาพ เสียง ซับ และวิดีโอแนวตั้งจนเสร็จ",
            lambda row: tk.Label(row, text="●  AUTOMATION READY", bg="#102A28", fg=COLORS["green"], font=("Segoe UI Semibold", 8), padx=12, pady=7).pack(side="right", pady=4),
        )

        top = self._panel(page, fill="x", pady=(0, 8))
        intro = tk.Frame(top, bg=COLORS["panel_2"])
        intro.pack(fill="x")
        intro_left = tk.Frame(intro, bg=COLORS["panel_2"]); intro_left.pack(side="left", padx=16, pady=7)
        tk.Label(intro_left, text="สร้างคลิปแบบจบในครั้งเดียว", bg=COLORS["panel_2"], fg=COLORS["text"], font=("Segoe UI Semibold", 11)).pack(anchor="w")
        tk.Label(intro_left, text="ระบบจะรักษาธีมภาพเดียวกันและแสดงความคืบหน้าตามงานจริง", bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))
        steps = tk.Frame(intro, bg=COLORS["panel_2"]); steps.pack(side="right", padx=14, pady=7)
        for index, label in enumerate(("เขียนบท", "สร้างภาพ", "สร้างเสียง", "ประกอบคลิป"), 1):
            chip = tk.Frame(steps, bg=COLORS["panel_3"], highlightbackground=COLORS["line_soft"], highlightthickness=1)
            chip.pack(side="left", padx=3)
            tk.Label(chip, text=f"{index}", bg=COLORS["panel_3"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 8), padx=7, pady=5).pack(side="left")
            tk.Label(chip, text=label, bg=COLORS["panel_3"], fg=COLORS["muted"], font=("Segoe UI", 8), padx=6, pady=5).pack(side="left")

        fields = tk.Frame(top, bg=COLORS["panel"]); fields.pack(fill="x", padx=16, pady=(9, 6))
        topic_box = tk.Frame(fields, bg=COLORS["panel"]); topic_box.pack(side="left", fill="x", expand=True, padx=(0, 12))
        topic_label = tk.Frame(topic_box, bg=COLORS["panel"]); topic_label.pack(fill="x", pady=(0, 5))
        tk.Label(topic_label, text="หัวข้อคลิป", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Label(topic_label, text="  ใส่หัวข้อหรือเรื่องอย่างน้อยหนึ่งช่อง", bg=COLORS["panel"], fg=COLORS["subtle"], font=("Segoe UI", 8)).pack(side="left")
        tk.Entry(topic_box, textvariable=self.story_topic, bg=COLORS["panel_3"], fg=COLORS["text"], insertbackground="white", selectbackground="#31539B", relief="flat", highlightbackground=COLORS["line"], highlightcolor=COLORS["blue"], highlightthickness=1, font=("Segoe UI", 10)).pack(fill="x", ipady=8)

        scene_box = tk.Frame(fields, bg=COLORS["panel"], width=230); scene_box.pack(side="right", fill="y")
        scene_box.pack_propagate(False)
        scene_header = tk.Frame(scene_box, bg=COLORS["panel"]); scene_header.pack(fill="x", pady=(0, 6))
        tk.Label(scene_header, text="จำนวนฉาก", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        self.story_scene_value_label = tk.Label(scene_header, text=f"{self.story_scene_count.get()} ฉาก", bg="#15284A", fg=COLORS["cyan"], font=("Segoe UI Semibold", 8), padx=9, pady=2)
        self.story_scene_value_label.pack(side="right")
        ttk.Scale(scene_box, from_=6, to=15, variable=self.story_scene_count, orient="horizontal", length=220, style="Story.Horizontal.TScale", command=self._update_story_scene_badge).pack(fill="x")

        detail_header = tk.Frame(top, bg=COLORS["panel"]); detail_header.pack(fill="x", padx=16, pady=(0, 5))
        tk.Label(detail_header, text="รายละเอียดเรื่อง / แนวทางการเล่า", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Label(detail_header, text="ไม่บังคับ ถ้าใส่หัวข้อไว้แล้ว", bg=COLORS["panel"], fg=COLORS["subtle"], font=("Segoe UI", 8)).pack(side="right")
        self.story_input = tk.Text(top, height=3, bg=COLORS["panel_3"], fg=COLORS["text"], insertbackground="white", selectbackground="#31539B", relief="flat", highlightbackground=COLORS["line"], highlightcolor=COLORS["blue"], highlightthickness=1, wrap="word", font=("Segoe UI", 10), padx=11, pady=7)
        self.story_input.pack(fill="x", padx=16)

        options = tk.Frame(top, bg=COLORS["panel"]); options.pack(fill="x", padx=16, pady=(7, 8))
        image_option = tk.Frame(options, bg=COLORS["panel_3"], highlightbackground=COLORS["line_soft"], highlightthickness=1)
        story_option_controls = tk.Frame(options, bg=COLORS["panel"])
        story_option_controls.pack(fill="x")
        image_option = tk.Frame(story_option_controls, bg=COLORS["panel_3"], highlightbackground=COLORS["line_soft"], highlightthickness=1)
        image_option.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Button(image_option, text="＋  เลือกรูปหลัก", style="Quiet.TButton", command=self._select_story_image).pack(side="left", padx=4, pady=4)
        tk.Label(image_option, textvariable=self.story_main_image, bg=COLORS["panel_3"], fg=COLORS["muted"], font=("Segoe UI", 8), anchor="w").pack(side="left", fill="x", expand=True, padx=(4, 9))
        story_provider = ttk.Combobox(story_option_controls, textvariable=self.image_ai_provider, values=tuple(IMAGE_AI_PROVIDERS), state="readonly", width=13, style="Dark.TCombobox")
        story_provider.pack(side="left", padx=(0, 8)); story_provider.bind("<<ComboboxSelected>>", lambda event: self._image_provider_changed())
        ttk.Combobox(
            story_option_controls, textvariable=self.story_video_mode, values=tuple(STORY_VIDEO_MODES),
            state="readonly", width=22, style="Dark.TCombobox",
        ).pack(side="left", padx=(0, 8))
        story_option_actions = tk.Frame(options, bg=COLORS["panel"])
        story_option_actions.pack(fill="x", pady=(6, 0))
        self.story_run_button = ttk.Button(story_option_actions, text="✦  สร้าง Story Shorts อัตโนมัติจนเสร็จ", style="PrimaryLarge.TButton", command=self._create_story_and_run)
        self.story_run_button.pack(side="left", fill="x", expand=True)
        ttk.Button(story_option_actions, text="เปิดโฟลเดอร์งาน", style="Ghost.TButton", command=lambda: self._open_folder(self.stories.root)).pack(side="right", padx=(8, 0))
        content = tk.Frame(page, bg=COLORS["bg"]); content.pack(fill="both", expand=True)
        _story_history_viewport, left = self._scroll_panel(content, width=320, side="left", fill="y")

        story_action_stack = tk.Frame(left, bg=COLORS["panel"])
        story_action_stack.pack(side="bottom", fill="x", padx=15, pady=(4, 7))
        self.story_resume_button = ttk.Button(story_action_stack, text="↻  ทำงานนี้ต่อจาก Checkpoint", style="Accent.TButton", command=lambda: self._retry_story_job(self.story_job_id.get().strip(), fresh_meta_scene=True))
        self.story_resume_button.pack(fill="x", pady=(0, 5))
        story_file_actions = tk.Frame(story_action_stack, bg=COLORS["panel"])
        story_file_actions.pack(fill="x")
        ttk.Button(story_file_actions, text="เปิด Job", style="Ghost.TButton", command=self._open_story_folder).pack(side="left", fill="x", expand=True, padx=(0, 3))
        tk.Button(story_file_actions, text="ลบวิดีโอ", command=self._delete_selected_story_renders, relief="flat", bd=0, bg=COLORS["panel"], fg="#FF9AAF", activebackground="#482035", activeforeground="#FFFFFF", font=("Segoe UI Semibold", 8), pady=8, cursor="hand2").pack(side="left", fill="x", expand=True, padx=3)
        tk.Button(story_file_actions, text="ลบโปรเจกต์", command=self._delete_selected_story_project, relief="flat", bd=0, bg="#551827", fg="#FFD4DC", activebackground="#722238", activeforeground="#FFFFFF", font=("Segoe UI Semibold", 8), pady=8, cursor="hand2").pack(side="left", fill="x", expand=True, padx=(3, 0))

        history_head = tk.Frame(left, bg=COLORS["panel"]); history_head.pack(fill="x", padx=15, pady=(7, 3))
        tk.Label(history_head, text="งานล่าสุด", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 10)).pack(side="left")
        tk.Label(history_head, text="HISTORY", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 8)).pack(side="right")
        combo = ttk.Combobox(left, textvariable=self.story_job_id, state="readonly", style="Dark.TCombobox")
        combo.pack(fill="x", padx=15); combo.bind("<<ComboboxSelected>>", lambda event: self._load_story_job())
        self.story_job_combo = combo
        status_card = tk.Frame(left, bg=COLORS["panel_3"], highlightbackground=COLORS["line_soft"], highlightthickness=1)
        status_card.pack(fill="x", padx=15, pady=4)
        tk.Label(status_card, text="●  สถานะงาน", bg=COLORS["panel_3"], fg=COLORS["green"], font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=11, pady=(4, 1))
        tk.Label(status_card, textvariable=self.story_status, bg=COLORS["panel_3"], fg=COLORS["cyan"], font=("Segoe UI", 8), wraplength=270, justify="left").pack(anchor="w", padx=11, pady=(0, 4))

        right = self._panel(content, side="left", fill="both", expand=True, padx=(12, 0))
        result_head = tk.Frame(right, bg=COLORS["panel"]); result_head.pack(fill="x", padx=15, pady=(13, 7))
        tk.Label(result_head, text="บทและข้อมูลจาก AI Web", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 10)).pack(side="left")
        tk.Label(result_head, text="LIVE RESULT", bg="#102A28", fg=COLORS["green"], font=("Segoe UI Semibold", 8), padx=8, pady=3).pack(side="right")
        tk.Label(result_head, textvariable=self.image_ai_provider, bg="#1B1731", fg="#D8B4FE", font=("Segoe UI Semibold", 7), padx=8, pady=3).pack(side="right", padx=(0, 6))
        self.story_result = tk.Text(right, bg=COLORS["panel_3"], fg=COLORS["text"], relief="flat", wrap="word", font=("Segoe UI", 10), padx=13, pady=11, selectbackground="#31539B")
        self.story_result.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def _update_story_scene_badge(self, value=None):
        count = max(6, min(15, int(round(float(value if value is not None else self.story_scene_count.get())))))
        self.story_scene_count.set(count)
        if hasattr(self, "story_scene_value_label"):
            self.story_scene_value_label.configure(text=f"{count} ฉาก")

    def _select_story_image(self):
        path = filedialog.askopenfilename(filetypes=[("รูปหลัก", "*.png *.jpg *.jpeg *.webp")])
        if path:
            self.story_main_image.set(path)

    def _show_story_progress(self, job_id):
        if self._story_progress_dialog and self._story_progress_dialog.winfo_exists():
            self._story_progress_dialog.destroy()
        self._story_popup_terminal = False
        self._story_progress_value.set(0)
        self._story_progress_percent.set("0%")
        self._story_progress_message.set("กำลังเตรียม Story Job")
        self._story_progress_detail.set("เปอร์เซ็นต์เพิ่มตามผลงานที่เสร็จจริง ไม่ได้เดาจากเวลา")
        self._story_progress_job.set(job_id)
        self._story_progress_stage_widgets = {}

        # The Hybrid shell renders this progress as HTML. Keep the Tk state
        # variables alive for the existing pipeline without opening a second
        # native window behind WebView2.
        if self.hybrid_engine:
            self._story_progress_dialog = None
            return

        dialog = tk.Toplevel(self.root)
        self._story_progress_dialog = dialog
        dialog.title("SmartFlow Automation")
        dialog.geometry("560x500")
        dialog.resizable(False, False)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", self._cancel_story_pipeline)

        shell = tk.Frame(dialog, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        shell.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(shell, text="SMARTFLOW • AUTOMATION", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 9)).pack(pady=(20, 3))
        tk.Label(shell, text="กำลังสร้าง Story Shorts", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 20)).pack()
        tk.Label(shell, textvariable=self._story_progress_job, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(pady=(3, 8))
        tk.Label(shell, textvariable=self._story_progress_percent, bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 28)).pack()

        style = ttk.Style(dialog)
        style.configure("Story.Horizontal.TProgressbar", troughcolor=COLORS["panel_3"], background=COLORS["blue"], bordercolor=COLORS["panel_3"], lightcolor=COLORS["blue"], darkcolor=COLORS["blue"], thickness=14)
        ttk.Progressbar(shell, variable=self._story_progress_value, maximum=100, style="Story.Horizontal.TProgressbar").pack(fill="x", padx=32, pady=(3, 12))
        tk.Label(shell, textvariable=self._story_progress_message, bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 11), wraplength=470, justify="center").pack()
        tk.Label(shell, textvariable=self._story_progress_detail, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=470, justify="center").pack(pady=(3, 13))

        stages = tk.Frame(shell, bg=COLORS["panel_2"], highlightbackground=COLORS["line"], highlightthickness=1)
        stages.pack(fill="x", padx=32)
        for index, (key, label, _start, _end) in enumerate(STORY_STAGES, 1):
            row = tk.Frame(stages, bg=COLORS["panel_2"]); row.pack(fill="x", padx=14, pady=(9 if index == 1 else 5, 9 if index == len(STORY_STAGES) else 5))
            bullet = tk.Label(row, text="○", width=2, bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI Semibold", 11))
            bullet.pack(side="left")
            text = tk.Label(row, text=label, bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 9))
            text.pack(side="left", padx=5)
            self._story_progress_stage_widgets[key] = (bullet, text)

        self._story_progress_note_label = tk.Label(shell, text="สามารถยกเลิกได้ ระบบจะเก็บไฟล์ที่เสร็จแล้วและไม่ทำขั้นถัดไป", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8))
        self._story_progress_note_label.pack(pady=(13, 7))
        footer = tk.Frame(shell, bg=COLORS["panel"]); footer.pack(fill="x", padx=32, pady=(0, 18))
        self._story_progress_open_button = ttk.Button(footer, text="เปิดโฟลเดอร์ผลงาน", style="Ghost.TButton")
        self._story_cancel_button = tk.Button(footer, text="ยกเลิกการทำงาน", command=self._cancel_story_pipeline, bg="#3A1730", fg="#FFB2C2", activebackground="#5A1D3A", activeforeground="white", relief="flat", bd=0, padx=18, pady=9, font=("Segoe UI Semibold", 9), cursor="hand2")
        self._story_cancel_button.pack(side="right")

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()

    def _update_story_flow_progress(self, payload):
        """Apply owned Flow detail without counting helper work as a saved clip."""
        if not isinstance(payload, dict):
            return
        job_id, shot_index = payload.get('job_id'), payload.get('shot_index')
        if (not job_id or job_id != getattr(self, '_story_pipeline_job_id', '')
                or not str(job_id).startswith('STORY-')
                or type(shot_index) is not int or not 1 <= shot_index <= 50
                or getattr(self, '_story_flow_progress_owner', None) != (job_id, shot_index)
                or not payload.get('flow_run_id')):
            return
        with self.bridge._extension_lock:
            expected = self.bridge._extension_runs.get(('flow', job_id, shot_index)) or {}
            if expected.get('run_id') != payload['flow_run_id']:
                return
        if payload.get('generation_accepted'):
            from core.scene_pipeline import ScenePipeline
            pipeline = ScenePipeline(self.stories.root / job_id)
            row = pipeline.get(shot_index)
            if row.get('phase') == 'video' and str(row.get('message') or '').startswith('กำลังเตรียม Google Flow'):
                pipeline.update(shot_index, row['revision'], message='ส่งสร้างวิดีโอแล้ว • กำลังรอผลจาก Google Flow')
        self._update_story_progress(payload)

    def _queue_story_phase(self, job_id, cancel_event, phase, payload):
        """Local worker progress carries an exact run owner, not just a percent."""
        self.events.put(('story_progress', {**payload, 'progress_job_id': job_id,
            'progress_cancel_event': cancel_event, 'pipeline_phase': phase}))

    def _update_story_progress(self, payload):
        if not isinstance(payload, dict):
            payload = {"message": str(payload), "percent": self._story_progress_value.get(), "stage": "voice", "detail": "กำลังดำเนินการ"}
        percent = max(0, min(100, int(round(float(payload.get("percent", 0))))))
        current_percent = max(0, min(100, int(round(float(self._story_progress_value.get())))))
        # Progress can arrive from the browser extension after the local voice/video
        # pipeline has already advanced. Ignore those stale callbacks so both the
        # percentage and its message remain truthful in the hybrid web UI too.
        phase = payload.get('pipeline_phase')
        phases = {'source_video': 1, 'voice': 2, 'compose': 3, 'finish': 4, 'cover': 5}
        if phase is not None:
            owner = (payload.get('progress_job_id'), payload.get('progress_cancel_event'))
            active_owner = (getattr(self, '_story_pipeline_job_id', ''), getattr(self, '_story_cancel_event', None))
            if (phase not in phases or not owner[0] or owner != active_owner
                    or owner[1] is None or owner[1].is_set()):
                return
            previous_owner, previous_phase = getattr(self, '_story_phase_owner', (None, 0))
            if previous_owner == owner and phases[phase] < previous_phase:
                return
            self._story_phase_owner = (owner, phases[phase])
            percent = max(percent, current_percent)
        else:
            previous_owner, previous_phase = getattr(self, '_story_phase_owner', (None, 0))
            active_owner = (getattr(self, '_story_pipeline_job_id', ''), getattr(self, '_story_cancel_event', None))
            if previous_owner == active_owner and previous_phase and payload.get('stage') == 'chatgpt':
                return
            if percent < current_percent:
                recovery_steps = {'recovering_response', 'recovering_result',
                    'image_refresh_check', 'image_restart_pending', 'image_restart_started',
                    'recovering_images', 'retrying_image', 'repairing_analysis',
                    'repairing_story_names'}
                if (payload.get('stage') != 'chatgpt' or payload.get('step') not in recovery_steps
                        or not active_owner[0] or current_percent > 60):
                    return
                # The same AI job can recover an earlier browser phase without
                # undoing its saved work. Keep the percent, show the new message.
                percent = current_percent
        stage = str(payload.get("stage") or "chatgpt")
        message = str(payload.get("message") or "กำลังทำงาน")
        detail = str(payload.get("detail") or "เปอร์เซ็นต์มาจากขั้นตอนที่เสร็จจริง")
        self._story_progress_value.set(percent)
        self._story_progress_percent.set(f"{percent}%")
        self._story_progress_message.set(message)
        self._story_progress_detail.set(detail)
        self.story_status.set(f"{self._story_pipeline_job_id or self.story_job_id.get()} • {percent}% • {message}")
        self.status.set(f"Story Shorts • {percent}% • {message}")
        story_job_id = self._story_pipeline_job_id or self.story_job_id.get() or "STORY"
        self._write_console(f"{story_job_id} • {percent}% • {message} • {detail}")
        for key, _label, start, end in STORY_STAGES:
            bullet, text = self._story_progress_stage_widgets.get(key, (None, None))
            if not bullet:
                continue
            if percent >= end:
                bullet.configure(text="●", fg=COLORS["green"]); text.configure(fg=COLORS["green"])
            elif key == stage or start <= percent < end:
                bullet.configure(text="◉", fg=COLORS["cyan"]); text.configure(fg=COLORS["text"])
            else:
                bullet.configure(text="○", fg=COLORS["muted"]); text.configure(fg=COLORS["muted"])

    def _focus_ai_verification(self, job_id, provider):
        """Bring the exact Chrome login/verification tab forward for the user."""
        try:
            target = str(provider or "").strip().lower()
            self._activate_or_launch_chrome(
                "https://labs.google/fx/th/tools/flow" if target == "flow" else self._ai_web_url(provider)
            )
            if str(provider or "").strip().lower() == "flow":
                self.bridge.queue_extension_command("focus_flow_web", job_id)
            else:
                self.bridge.queue_extension_command("focus_ai_web", job_id, provider_hint=provider)
            self.status.set("รอผู้ใช้ดำเนินการใน Google Chrome")
            self._write_console(f"{job_id} • เปิด Chrome ให้ผู้ใช้เข้าสู่ระบบ/ยืนยัน", "log")
        except Exception:
            target = str(provider or "").strip().lower()
            self._open_url("https://labs.google/fx/th/tools/flow" if target == "flow" else self._ai_web_url(provider))

    def _focus_product_web_action(self, job_id):
        """Handle the product popup button without losing its exact video shot."""
        action = dict(self._product_web_action or {})
        provider = str(action.get("service") or "flow").strip().lower()
        if action.get("action_kind") == "credit_exhausted" and provider == "flow":
            shot_index = max(1, int(action.get("shot_index") or 1))
            self._activate_or_launch_chrome("https://labs.google/fx/th/tools/flow")
            self.bridge.clear_flow_progress(job_id, shot_index)
            self.bridge.queue_extension_command("open_flow", job_id, shot_index)
            self._product_progress_message.set("กำลังเปิด Google Flow ด้วยบัญชีปัจจุบัน")
            self._product_progress_detail.set(f"กำลังลองใหม่เฉพาะช็อต {shot_index}/3 • หากยังเป็นบัญชีเดิมที่เครดิตหมด Popup จะยังคงแจ้งเตือน")
            self._write_console(f"{job_id} • FLOW CREDIT RECOVERY • เปิดโปรเจกต์ใหม่เฉพาะช็อต {shot_index}/3", "log")
            return
        self._focus_ai_verification(job_id, provider)

    def _show_story_verification_required(self, job_id, provider, action_kind="verification_required", message=""):
        provider_name = "Google Flow" if provider == "flow" else ("Gemini Web" if provider == "gemini" else "ChatGPT Web")
        login_required = action_kind == "login_required"
        rights_required = action_kind == "legal_rights"
        title = (f"กรุณาเข้าสู่ระบบ {provider_name} ก่อน" if login_required else
                 ("กรุณากด “ฉันยอมรับ” ใน Google Flow" if rights_required else "ต้องการให้คุณยืนยันว่าไม่ใช่โปรแกรมอัตโนมัติ"))
        detail = (f"กดปุ่มด้านล่างแล้ว Login ใน Google Chrome • จากนั้นระบบจะทำต่อเองใน {provider_name} จาก Checkpoint เดิม"
                  if login_required else
                  ("โปรแกรมหยุดรอโดยไม่กดยกเลิก • เมื่อคุณกด “ฉันยอมรับ” ระบบจะแนบรูปเดิมและทำต่ออัตโนมัติ"
                   if rights_required else f"กรุณากดปุ่มด้านล่าง ไปที่ Chrome แล้วติ๊กช่องยืนยันของ Google • จากนั้นระบบจะทำต่อเองใน {provider_name}"))
        self._update_story_progress({
            "percent": self._story_progress_value.get(), "stage": "chatgpt",
            "message": message or title,
            "detail": detail,
        })
        self._story_web_actions[job_id] = {"action_kind": action_kind, "service": provider, "button_label": f"เปิด {provider_name} เพื่อเข้าสู่ระบบ" if login_required else "เปิด Chrome เพื่อกดยืนยัน"}
        if self._story_progress_dialog and self._story_progress_dialog.winfo_exists():
            self._story_progress_open_button.configure(
                text=self._story_web_actions[job_id]["button_label"],
                command=lambda: self._focus_ai_verification(job_id, provider),
            )
            if not self._story_progress_open_button.winfo_manager():
                self._story_progress_open_button.pack(side="left")
            self._story_progress_note_label.configure(
                text="กำลังหยุดรอคุณ • งานและรูปที่สร้างเสร็จแล้วไม่หาย",
                fg=COLORS["yellow"],
            )
            self._story_progress_dialog.lift()
        if self._story_verification_jobs.get(job_id) != "waiting":
            self.root.bell()
        self._story_verification_jobs[job_id] = "waiting"

    def _clear_story_verification(self, job_id):
        self._story_verification_jobs.pop(job_id, None)
        self._story_web_actions.pop(job_id, None)
        if self._story_progress_dialog and self._story_progress_dialog.winfo_exists():
            if str(self._story_progress_open_button.cget("text")).startswith("เปิด "):
                self._story_progress_open_button.pack_forget()
            self._story_progress_note_label.configure(
                text="ยืนยันเรียบร้อยแล้ว • ระบบกำลังทำต่อจาก Checkpoint เดิม",
                fg=COLORS["green"],
            )

    @staticmethod
    def _ai_web_url(provider):
        return "https://gemini.google.com/app" if str(provider or "").strip().lower() == "gemini" else "https://chatgpt.com/"

    def _compatible_extension(self):
        extension = self.bridge.extension_status()
        clients = extension.get("clients") or []
        compatible = next((item for item in clients if str(item.get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION), None)
        return extension, compatible

    def _story_browser_target_url(self, job_id, provider, action):
        """Open the exact saved conversation when recovery requires its old turn."""
        if action == "resume_chatgpt":
            from core.ai_web_resume import ai_web_resume_target, conversation_url
            job = self.stories.get(job_id)
            target = ai_web_resume_target(self.stories.root / job_id, job) or {}
            if target.get("required"):
                saved_url = conversation_url(target.get("conversation_url"), provider)
                if target.get("provider") != provider or not saved_url:
                    raise ValueError("AI_WEB_RESUME_REVIEW • ไม่พบ URL แชตเดิมที่ยืนยันได้ • ไม่เปิดแท็บใหม่หรือส่งซ้ำ")
                return saved_url
        return self._ai_web_url(provider)

    def _launch_story_browser(self, job_id, provider="", reason="Chrome หรือ Extension ยังไม่ออนไลน์", command_queued=False, action=""):
        """Open the provider once, then wait for Extension instead of spawning tabs."""
        if self._story_pipeline_job_id != job_id:
            return False
        try:
            job = self.stories.get(job_id)
        except Exception:
            return False
        provider = str(provider or job.get("image_ai_provider") or "chatgpt").strip().lower()
        launches = getattr(self, "_story_browser_launches", {})
        state = dict(launches.get(job_id) or {})
        resume_action = action or state.get("action") or ("resume_chatgpt" if job.get("ai_status") == "ready" or job.get("generated_images") or job.get("partial_generated_images") else "open_story_chatgpt")
        try:
            browser_url = self._story_browser_target_url(job_id, provider, resume_action)
        except ValueError as exc:
            self.events.put(("story_error", {"job_id": job_id, "cancel_event": self._story_cancel_event, "value": str(exc)}))
            return False
        now = time.monotonic()
        if state.get("opened_once"):
            if (
                not self._chrome_window_available()
                and now - float(state.get("opened_at") or 0) >= 5
                and int(state.get("relaunch_count") or 0) < 4
            ):
                state["opened_at"] = now
                state["waiting_notice_at"] = now
                state["relaunch_count"] = int(state.get("relaunch_count") or 0) + 1
                launches[job_id] = state
                self._story_browser_launches = launches
                self._activate_or_launch_chrome(browser_url)
                self._update_story_progress({
                    "percent": 3,
                    "stage": "chatgpt",
                    "message": "Chrome ถูกปิดระหว่างงาน • กำลังเปิดกลับอัตโนมัติ",
                    "detail": f"รักษา Checkpoint เดิมไว้ • ลองเปิดกลับ {state['relaunch_count']}/4",
                })
                return True
            # The monitor runs every 600 ms. Opening the URL on a time-based
            # cooldown created a new Gemini/ChatGPT tab forever whenever the
            # Extension was offline. Keep the first tab and wait for its
            # heartbeat; current-Job progress clears this state at line 1125.
            if now - float(state.get("waiting_notice_at") or 0) >= 30:
                state["waiting_notice_at"] = now
                launches[job_id] = state
                self._story_browser_launches = launches
                provider_name = "Gemini Web" if provider == "gemini" else "ChatGPT Web"
                self._update_story_progress({
                    "percent": 3,
                    "stage": "chatgpt",
                    "message": f"เปิด {provider_name} แล้ว • กำลังรอ Extension เชื่อม",
                    "detail": "ระบบจะไม่เปิดแท็บซ้ำ และจะส่ง Job ต่อทันทีเมื่อ Extension พร้อม",
                })
            return False
        self._activate_or_launch_chrome(browser_url)
        state.update({
            "provider": provider,
            "action": resume_action,
            "opened_at": now,
            "opened_once": True,
            "waiting_notice_at": now,
            "relaunch_count": 0,
            "online_since": 0.0,
            "resume_sent": bool(command_queued),
        })
        launches[job_id] = state
        self._story_browser_launches = launches
        provider_name = "Gemini Web" if provider == "gemini" else "ChatGPT Web"
        self._update_story_progress({"percent": 3, "stage": "chatgpt", "message": f"กำลังเปิด Google Chrome และ {provider_name} อัตโนมัติ", "detail": f"{reason} • เมื่อ Extension เชื่อมแล้วระบบจะส่ง Job ต่อเอง"})
        self._write_console(f"{job_id} • เปิด Google Chrome → {provider_name} อัตโนมัติ", "log")
        return True

    def _story_run_active(self, job_id):
        """Read-only gate for an Extension collector belonging to this live Story worker."""
        event = getattr(self, "_story_cancel_event", None)
        if getattr(self, "_story_pipeline_job_id", "") != job_id or event is None or event.is_set():
            return False
        try:
            job = self.stories.get(job_id)
        except (OSError, ValueError):
            return False
        return not job.get("cancel_requested") and job.get("status") not in {
            "cancelled", "canceled", "error", "ready", "completed", "deleted",
        }

    def _monitor_story_browser_progress(self, job_id):
        if self._story_pipeline_job_id != job_id or not self._story_cancel_event or self._story_cancel_event.is_set():
            return
        story_job = self.stories.get(job_id)
        locked_provider = str(story_job.get("image_ai_provider") or "chatgpt").strip().lower()
        extension = self.bridge.extension_status()
        clients = extension.get("clients") or ([extension.get("client")] if extension.get("client") else [])
        # extension_status supplies fresh heartbeats; select job evidence only
        # from that snapshot's exact desktop-compatible Extension version.
        clients = [item for item in clients if str((item or {}).get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION]
        compatible = next((item for item in clients if str((item or {}).get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION), None)
        expected_run = str((getattr(self.bridge, '_extension_runs', {}).get(("ai", job_id, 0)) or {}).get("run_id") or "")
        client = next((item for item in clients
            if str((item or {}).get("ai_job_id") or "") == job_id
            and (not expected_run or str((item or {}).get("ai_run_id") or "") == expected_run)), None)
        client_provider = str((client or {}).get("ai_provider") or locked_provider).strip().lower()
        if client and client_provider != locked_provider:
            self.events.put(("story_error", {"job_id": job_id, "cancel_event": self._story_cancel_event, "value": f"Extension เปิด {client_provider} ไม่ตรงกับ Provider ของ Job ({locked_provider})"}))
            return
        from core.story_progress_stall import image_prompt_ready_stalled
        if image_prompt_ready_stalled(client, job_id, expected_run):
            marker = (job_id, expected_run, str(client.get("ai_updated_at") or ""))
            if locked_provider != "chatgpt":
                self.events.put(("story_error", {"job_id": job_id,
                    "cancel_event": self._story_cancel_event,
                    "value": "STORY_IMAGE_PROGRESS_STALLED • ผู้ให้บริการไม่รองรับการกู้ร่างก่อนส่ง • เก็บงานเดิมไว้"}))
                return
            if getattr(self, "_story_image_stall_marker", None) != marker:
                self._story_image_stall_marker = marker
                self._story_image_stall_since = time.monotonic()
                self._story_image_stall_reported = False
                try:
                    self.bridge.queue_extension_command("recover_stalled_story_image", job_id,
                        provider_hint="chatgpt", run_id=expected_run)
                    self._update_story_progress({"percent": self._story_progress_value.get(),
                        "stage": "chatgpt", "message": "พบขั้นสร้างภาพค้าง • กำลังตรวจหลักฐานการส่ง",
                        "detail": "ตรวจ Job, แชต และใบรับคำขอก่อนเริ่มต่อจากภาพที่บันทึกไว้"})
                except Exception as exc:
                    self.events.put(("story_error", {"job_id": job_id,
                        "cancel_event": self._story_cancel_event,
                        "value": f"STORY_IMAGE_PROGRESS_STALLED • ส่งคำสั่งกู้คืนไม่ได้ ({type(exc).__name__})"}))
                    return
            elif time.monotonic() - getattr(self, "_story_image_stall_since", 0) >= 90:
                if not getattr(self, "_story_image_stall_reported", False):
                    self._story_image_stall_reported = True
                    self.events.put(("story_error", {"job_id": job_id,
                        "cancel_event": self._story_cancel_event,
                        "value": "STORY_IMAGE_PROGRESS_STALLED • Extension ไม่ยืนยันผลกู้คืนใน 90 วินาที • เก็บแชตเดิมและภาพที่บันทึกไว้"}))
                return
            self._story_monitor_after = self.root.after(600, lambda: self._monitor_story_browser_progress(job_id))
            return
        payload = browser_progress(client, job_id, story_job.get("scene_count", 1)) if client else None
        if payload:
            # Keep dispatch ownership through heartbeat gaps. Dropping this
            # marker made the monitor queue a second Resume after a reconnect.
            state = getattr(self, "_story_browser_launches", {}).get(job_id)
            if state:
                state["resume_sent"] = True
            if payload.get("step") == "user_action_required":
                provider = locked_provider
                action_kind = str((client or {}).get("ai_action_kind") or "verification_required")
                service = str((client or {}).get("ai_service") or provider).strip().lower()
                self._show_story_verification_required(job_id, service, action_kind, payload.get("message") or "")
                self._story_monitor_after = self.root.after(600, lambda: self._monitor_story_browser_progress(job_id))
                return
            elif payload.get("step") == "user_action_resolved":
                provider = locked_provider
                if self._story_verification_jobs.get(job_id) != "resuming":
                    self._story_verification_jobs[job_id] = "resuming"
                    self.bridge.clear_ai_progress(job_id)
                    self.bridge.queue_extension_command("resume_chatgpt", job_id, provider_hint=provider)
                    self._clear_story_verification(job_id)
                    self._update_story_progress({
                        "percent": self._story_progress_value.get(), "stage": "chatgpt",
                        "message": "เข้าสู่ระบบ/ยืนยันสำเร็จแล้ว • กำลังทำงานต่ออัตโนมัติ",
                        "detail": "ใช้ Analysis และรูปจาก Checkpoint เดิม ไม่เริ่ม Job ใหม่",
                    })
                self._story_monitor_after = self.root.after(600, lambda: self._monitor_story_browser_progress(job_id))
                return
            elif job_id in self._story_verification_jobs:
                self._clear_story_verification(job_id)
            if payload.get("step") == "error":
                self.events.put(("story_error", {"job_id": job_id, "cancel_event": self._story_cancel_event, "value": payload.get("message") or "AI Web ทำงานไม่สำเร็จ"}))
                return
            if payload.get("step") == "cancelled":
                self.events.put(("story_cancelled", {"job_id": job_id, "cancel_event": self._story_cancel_event}))
                return
            self._update_story_progress(payload)
        elif not compatible:
            self._launch_story_browser(job_id, reason="ตรวจไม่พบ Extension รุ่นที่พร้อมทำงาน")
        else:
            launches = getattr(self, "_story_browser_launches", {})
            state = launches.get(job_id)
            if state and not state.get("resume_sent"):
                now = time.monotonic()
                if not state.get("online_since"):
                    state["online_since"] = now
                    provider_name = "Gemini Web" if state.get("provider") == "gemini" else "ChatGPT Web"
                    self._update_story_progress({"percent": 3, "stage": "chatgpt", "message": "Chrome Extension เชื่อมแล้ว", "detail": f"กำลังรอหน้า {provider_name} พร้อมรับ Job"})
                elif now - float(state.get("online_since") or now) >= 2.5:
                    try:
                        self.bridge.clear_ai_progress(job_id)
                        self.bridge.queue_extension_command(state.get("action") or "resume_chatgpt", job_id, provider_hint=state.get("provider") or "")
                        state["resume_sent"] = True
                        self._update_story_progress({"percent": 4, "stage": "chatgpt", "message": "Chrome พร้อมแล้ว • ส่ง Job ต่ออัตโนมัติ", "detail": "กำลังรอหน้าเว็บเริ่มวิเคราะห์บทและสร้างภาพ"})
                    except Exception as exc:
                        self._write_console(f"{job_id} • ส่ง Job หลังเปิด Chrome ไม่สำเร็จ • {exc}", "error")
        self._story_monitor_after = self.root.after(600, lambda: self._monitor_story_browser_progress(job_id))

    def _cancel_story_pipeline(self):
        job_id = self._story_pipeline_job_id
        if not job_id:
            self._close_story_progress()
            return
        running_queue_item = self.story_queue.running_item()
        if running_queue_item and running_queue_item.get("job_id") == job_id:
            self.story_queue.pause()
        cancel_event = self._story_cancel_event
        if cancel_event is None:
            cancel_event = threading.Event()
            self._story_cancel_event = cancel_event
        cancel_event.set()
        self._story_progress_message.set("กำลังหยุดงานอย่างปลอดภัย...")
        self._story_progress_detail.set("จะไม่เริ่มขั้นตอนถัดไป ไฟล์ชั่วคราวที่กำลังเขียนจะถูกล้าง")
        if hasattr(self, "_story_cancel_button"):
            self._story_cancel_button.configure(state="disabled", text="กำลังยกเลิก...")
        try:
            self.bridge.queue_extension_command("cancel_story_chatgpt", job_id)
        except Exception:
            pass
        try:
            self.stories.mark_cancelled(job_id, "user_cancel")
        except Exception:
            pass
        self.root.after(400, lambda active_job=job_id, active_event=cancel_event: self._finish_story_cancel(active_job, active_event))

    def _finish_story_cancel(self, job_id, cancel_event):
        # A cancelled worker can report late, after the same Story is resumed
        # or another EP starts. Only its original Job+Event may clear the UI.
        if cancel_event is None or cancel_event is not self._story_cancel_event or not cancel_event.is_set():
            return False
        if self._story_pipeline_job_id != job_id:
            return False
        if job_id:
            try:
                if self.stories.get(job_id).get("status") != "cancelled":
                    self.stories.mark_cancelled(job_id, "user_cancel")
            except Exception as exc:
                self.log.warning("job_id=%s state=STORY_MARK_CANCELLED result=error error=%s", job_id, exc)
            self._park_drama_checkpoint_for_recovery(
                job_id,
                "ผู้ใช้หยุด EP กลางงาน • ไฟล์และ Checkpoint เดิมยังอยู่ กดกู้คืนไฟล์เพื่อทำต่อ",
            )
        if self._story_pipeline_job_id == job_id:
            self._story_pipeline_job_id = ""
        self._story_cancel_event = None
        self._story_render_active = None
        if hasattr(self, "story_run_button"):
            self.story_run_button.configure(state="normal")
        self._story_popup_terminal = True
        self.story_status.set(f"{job_id} • ยกเลิกแล้ว")
        self.status.set("Story Shorts • ยกเลิกการทำงานแล้ว")
        self._story_progress_message.set("ยกเลิกการทำงานแล้ว")
        self._story_progress_detail.set("ระบบหยุดก่อนเริ่มขั้นตอนถัดไป")
        if hasattr(self, "_story_progress_note_label"):
            self._story_progress_note_label.configure(text="ยกเลิกแล้ว • ไฟล์ที่สร้างเสร็จก่อนหน้านี้ยังอยู่ในโฟลเดอร์ Job")
        if self._story_progress_dialog and self._story_progress_dialog.winfo_exists():
            try: self._story_progress_dialog.grab_release()
            except Exception: pass
            self._story_cancel_button.configure(state="normal", text="ปิด", command=self._close_story_progress, bg="#17233F", fg=COLORS["text"])
        self._refresh()
        self._close_automation_browser(job_id, "ยกเลิก Story Shorts แล้ว")
        if self.story_queue.mark_cancelled_by_job(job_id):
            self.story_queue.pause("user_cancel")
        self._creation_dispatch_item = None
        return True

    def _handle_story_cancelled(self, payload):
        if not isinstance(payload, dict):
            return False
        job_id = str(payload.get("job_id") or "")
        cancel_event = payload.get("cancel_event")
        if (not job_id or job_id != self._story_pipeline_job_id
                or cancel_event is None or cancel_event is not self._story_cancel_event):
            return False
        cancel_event.set()
        return self._finish_story_cancel(job_id, cancel_event)

    def _park_drama_checkpoint_for_recovery(self, job_id, reason):
        """Turn a stopped Drama worker into a recoverable EP without deleting its files."""
        job_id = str(job_id or "").strip()
        if not job_id:
            return None
        try:
            job = self.stories.get(job_id)
        except Exception:
            return None
        series_id = str(job.get("series_id") or "").strip()
        episode_no = int(job.get("episode_no") or 0)
        if not series_id or episode_no < 1:
            return None
        try:
            series = self.drama_series.get(series_id)
            episode = next(
                (row for row in series.get("episodes") or [] if int(row.get("episode_no") or 0) == episode_no),
                None,
            )
            # Cancelling the whole series is terminal by explicit user intent.
            # Do not resurrect it from this delayed single-Job callback.
            if (series.get("status") == "cancelled" or not episode
                    or episode.get("status") in {"cancelled", "completed"}
                    or (episode.get("story_job_id") and episode["story_job_id"] != job_id)
                    or (not episode.get("story_job_id") and episode.get("retry_count"))):
                return None
        except Exception:
            return None
        queue_item = self.story_queue.mark_failed_by_job(job_id, str(reason or "งานหยุดกลางทาง"))
        if queue_item:
            self._pause_failed_drama_episode(queue_item, reason)
        else:
            try:
                self.drama_series.mark_episode_failed(series_id, episode_no, reason, job_id=job_id)
            except Exception as exc:
                self.log.warning("job_id=%s state=DRAMA_RECOVERY_PARK result=error error=%s", job_id, exc)
        return queue_item

    def _repair_orphaned_drama_checkpoint(self):
        """Repair legacy running/cancelled mismatches before startup recovery."""
        if self._story_pipeline_job_id:
            return None
        running = self.story_queue.running_item()
        if not running or running.get("mode") != "drama" or not running.get("job_id"):
            return None
        job_id = str(running.get("job_id") or "")
        try:
            job = self.stories.get(job_id)
        except Exception:
            return None
        if str(job.get("status") or "").lower() not in {"cancelled", "canceled", "error", "failed"}:
            return None
        return self._park_drama_checkpoint_for_recovery(
            job_id,
            "ตรวจพบโปรแกรมหยุด แต่คิวยังค้างว่า running • ไฟล์เดิมยังอยู่ กดกู้คืนไฟล์เพื่อทำต่อ",
        )

    def _close_story_progress(self):
        if self._story_progress_dialog and self._story_progress_dialog.winfo_exists():
            try: self._story_progress_dialog.grab_release()
            except Exception: pass
            self._story_progress_dialog.destroy()
        self._story_progress_dialog = None

    def _finish_story_popup(self, state, message, detail="", target=None):
        self._story_popup_terminal = True
        if state == "success":
            self._update_story_progress({"percent": 100, "stage": "finishing", "message": message, "detail": detail})
        else:
            self._story_progress_message.set(message)
            self._story_progress_detail.set(detail)
        if self._story_progress_dialog and self._story_progress_dialog.winfo_exists():
            try: self._story_progress_dialog.grab_release()
            except Exception: pass
            if target:
                self._story_progress_open_button.configure(text="เปิดโฟลเดอร์ผลงาน")
                self._story_progress_open_button.configure(command=lambda: self._open_folder(Path(target).parent))
                self._story_progress_open_button.pack(side="left")
            elif state != "success" and (self._story_pipeline_job_id or self.story_job_id.get().strip()):
                retry_job_id = self._story_pipeline_job_id or self.story_job_id.get().strip()
                self._story_progress_open_button.configure(text="ลองทำต่อจากจุดเดิม", command=lambda: self._retry_story_job(retry_job_id, fresh_meta_scene=True))
                self._story_progress_open_button.pack(side="left")
            color = COLORS["green"] if state == "success" else COLORS["danger"]
            if hasattr(self, "_story_progress_note_label"):
                note = "งานเสร็จสมบูรณ์ • เปิดดูวิดีโอได้จากคลังวิดีโอหรือโฟลเดอร์ผลงาน" if state == "success" else "งานหยุดแล้ว • กดทำต่อจากจุดเดิมได้โดยไม่ต้องสร้าง Job ใหม่"
                self._story_progress_note_label.configure(text=note, fg=color)
            self._story_progress_percent.set("100%" if state == "success" else "หยุด")
            self._story_cancel_button.configure(state="normal", text="ปิด", command=self._close_story_progress, bg="#17233F", fg=COLORS["text"])
            for widget in (getattr(self, "_story_cancel_button", None),):
                if widget: widget.configure(activebackground=color)

    @uses_job_files(lambda app, job_id, **kwargs: job_id)
    def _retry_story_job(self, job_id, *, fresh_meta_scene=False):
        queue = getattr(self, "story_queue", None)
        if queue is not None and hasattr(queue, "require_not_trashed"):
            queue.require_not_trashed(job_id)
        if self._story_pipeline_job_id:
            return
        job = self.stories.get(job_id)
        if (
            str(job.get("video_generation_mode") or "") == "google_flow"
            and str(job.get("video_source_type") or "") == "story_image_sequence_fallback"
        ):
            job = self.stories.reopen_google_flow_checkpoint(
                job_id,
                "ผลรอบก่อนเป็นภาพนิ่งต่อกัน • เปิดงานเดิมเพื่อสร้างคลิป Google Flow จริงเฉพาะฉากที่ขาด",
            )
        failover_action = story_provider_failover_action(job, job.get("last_error") or job.get("last_recovery_reason"))
        if failover_action:
            job = self.stories.set_image_ai_provider(
                job_id, "chatgpt", job.get("last_error") or job.get("last_recovery_reason") or "Gemini Web ไม่ส่งผลที่ใช้ต่อได้"
            )
        generated_paths = [self.stories.root / job_id / item for item in (job.get("generated_images") or [])]
        ai_ready = job.get("ai_status") == "ready" and len(generated_paths) == int(job.get("scene_count") or 0) and all(path.is_file() for path in generated_paths)
        from core.meta_scene_sequence import needs_scene_work
        serial_pending = needs_scene_work(self.stories, job)
        if serial_pending:
            ai_ready = False  # Reuse saved images through the per-scene video gate.
        # Use the exact same saved-plan resolver as the Extension package.
        # Invalid persisted analysis needs review, not another master request.
        analysis_ready = bool(self.stories.load_analysis_checkpoint(job_id)) if not ai_ready else False
        voice_path = self.stories.root / job_id / str(job.get("voice_path") or "")
        voice_ready = job.get("voice_status") == "ready" and voice_path.is_file()
        if ai_ready and audio_mode(job) == "api" and not voice_ready:
            api_key = self.voice_api_key.get().strip()
            reference_id = self.voice_reference_id.get().strip()
            reference_file = self.voice_reference_file.get().strip()
            frozen = self._creation_settings(job_id)
            reference_id = str(frozen.get("voice_reference_id", reference_id) or "")
            reference_file = str(frozen.get("voice_reference_file", reference_file) or "")
            if not api_key or (not reference_id and not Path(reference_file).is_file()):
                messagebox.showinfo("ตั้งค่า AI Voice ก่อนทำต่อ", "ภาพครบแล้ว กรุณาตรวจ API Key และเสียงต้นแบบเพื่อเริ่มสร้างเสียง")
                return
        _extension, compatible = self._compatible_extension()
        if (ai_ready or serial_pending) and fresh_meta_scene and job.get('video_generation_mode') == 'meta_ai' and not compatible:
            raise ValueError(f'โปรดเชื่อมต่อ SmartFlow Extension {self.bridge.REQUIRED_EXTENSION_VERSION} ก่อนเริ่มฉาก Meta ที่ค้างใหม่')
        self._close_story_progress()
        from core.flow_review import request_scene_repair_resume
        from core.scene_video_plan import enabled as planned_video
        manual_flow_resume = request_scene_repair_resume(self.stories.root / job_id, job) if job.get('video_generation_mode') == 'google_flow' and not planned_video(job) else None
        # A direct retry bypasses claim_next(); restore its failed queue owner
        # so the normal ready/error finisher can record the terminal state.
        if queue is not None:
            queue.claim_failed_story_for_direct_resume(job_id)
        self.stories.reset_recovery_attempts(job_id)
        self._story_pipeline_job_id = job_id
        self._story_browser_launches = getattr(self, "_story_browser_launches", {})
        self._story_browser_launches.pop(job_id, None)
        self._story_cancel_event = threading.Event()
        self.story_job_id.set(job_id)
        self.stories.mark_running(job_id, "voice" if ai_ready else "chatgpt")
        if hasattr(self, "story_run_button"):
            self.story_run_button.configure(state="disabled")
        self._show_story_progress(job_id)
        from ui.story_flow_resume import start_saved_flow_scene
        restarted = None
        try:
            if not planned_video(job) and start_saved_flow_scene(self, job, manual_flow_resume):
                return
            if (ai_ready or serial_pending) and fresh_meta_scene and job.get('video_generation_mode') == 'meta_ai' and not planned_video(job):
                from core.meta_video import MetaVideoManager
                restarted = MetaVideoManager(self.stories).restart_unfinished_on_continue(job_id)
                if restarted:
                    helper = restarted.get('stage') == 'redesigning'
                    image_saved = (restarted.get('redesign') or {}).get('phase') == 'image_saved'
                    self._update_story_progress({"percent": 60, "stage": "video",
                        "message": (f"เริ่มฉาก {restarted['index']} ที่ค้างบน Meta หน้าแรกใหม่" if not helper else
                                    f"ฉาก {restarted['index']} มีภาพใหม่แล้ว • ขอพรอมต์วิดีโอ"
                                    if image_saved else f"เริ่มฉาก {restarted['index']} ใหม่ด้วยภาพก่อน"),
                        "detail": ("ใช้ภาพและพรอมต์ที่บันทึกไว้ • เก็บคลิปที่สำเร็จแล้ว" if not helper else
                                   "เก็บภาพใหม่และคลิปที่สำเร็จแล้ว • ไม่สร้างภาพฉากนี้ซ้ำ"
                                   if image_saved else "เก็บคลิปที่สำเร็จแล้ว • รอภาพใหม่ก่อนแก้พรอมต์")})
        except Exception as exc:
            self.events.put(("story_error", {"job_id": job_id, "cancel_event": self._story_cancel_event, "value": str(exc)}))
            return
        if ai_ready:
            if restarted:
                helper = restarted.get('stage') == 'redesigning'
                image_saved = (restarted.get('redesign') or {}).get('phase') == 'image_saved'
                self._update_story_progress({"percent": 61, "stage": "video",
                    "message": (f"กำลังเริ่ม Meta ฉาก {restarted['index']} ใหม่" if not helper else
                                f"กำลังแก้พรอมต์ฉาก {restarted['index']}"
                                if image_saved else f"กำลังสร้างภาพใหม่ฉาก {restarted['index']}"),
                    "detail": ("เปิดหน้าแรกใหม่ด้วยภาพและพรอมต์เดิม • เก็บคลิปฉากก่อนหน้า" if not helper else
                               "ใช้ภาพใหม่ที่บันทึกแล้ว แล้วเปิด Meta หน้าแรก • เก็บคลิปฉากก่อนหน้า"
                               if image_saved else "บันทึกภาพใหม่ก่อนขอพรอมต์วิดีโอ • เก็บคลิปฉากก่อนหน้า")})
            else:
                self._update_story_progress({"percent": 61, "stage": "voice", "message": "บทและภาพครบแล้ว กำลังทำต่อจาก AI Voice", "detail": "ไม่ย้อนกลับไปสร้างบทหรือภาพซ้ำ"})
            self.root.after(300, self._render_story)
            return
        provider_name = "Gemini Web" if job.get("image_ai_provider") == "gemini" else "ChatGPT Web"
        self._update_story_progress({"percent": 4, "stage": "chatgpt", "message": f"กำลังทำต่อจากผลเดิมใน {provider_name}", "detail": "ระบบจะใช้บทและภาพที่สร้างเสร็จแล้ว ไม่เริ่มใหม่ทั้งหมด"})
        try:
            resume_action = failover_action or ("resume_chatgpt" if analysis_ready or job.get("ai_status") == "ready" or job.get("generated_images") or job.get("partial_generated_images") else "open_story_chatgpt")
            self.bridge.clear_ai_progress(job_id)
            self.bridge.queue_extension_command(resume_action, job_id)
            self._story_browser_launches[job_id] = {"resume_sent": True}
            if not compatible or not self._chrome_window_available():
                self._launch_story_browser(job_id, job.get("image_ai_provider"), "กำลังเปิด Chrome เพื่อทำต่อจาก Checkpoint", command_queued=True, action=resume_action)
            else:
                self._activate_or_launch_chrome(self._ai_web_url(job.get("image_ai_provider")))
        except Exception as exc:
            self.events.put(("story_error", {"job_id": job_id, "cancel_event": self._story_cancel_event, "value": str(exc)}))
            return
        self._story_monitor_after = self.root.after(700, lambda: self._monitor_story_browser_progress(job_id))

    def _resume_interrupted_story_on_startup(self):
        """Restore the newest interrupted browser stage after the desktop app restarts."""
        if getattr(self, 'membership', None) and not self.membership.allowed():
            return
        if self.story_queue.snapshot().get("active_count"):
            return  # Persisted creation work resumes only after the user starts the queue.
        if self._story_pipeline_job_id or self._product_pipeline_job_id or self._startup_recovery_claimed:
            return
        self._repair_orphaned_drama_checkpoint()
        candidates = []
        for job in self.stories.list_jobs():
            receipt_active = False
            if (job.get('status') == 'running' and job.get('long_video')
                    and job.get('video_generation_mode') == 'meta_ai'):
                try:
                    receipt_file = self.stories.root / job['id'] / 'prompts' / 'meta_video_receipts.json'
                    data = AtomicJsonFile(receipt_file).peek({'scenes': {}})
                    receipt_active = any(isinstance(row, dict) and row.get('job_id') == job['id'] and row.get('stage') in {
                        'send_intent', 'submitted', 'generating', 'download_intent', 'downloading'}
                        for row in (data.get('scenes') or {}).values())
                except (OSError, ValueError, JsonPersistenceError, AttributeError):
                    receipt_active = False
            if interrupted_story_restart_candidate(job, owned_meta_receipt=receipt_active):
                candidates.append(job)
        if not candidates:
            return
        job = candidates[0]
        self.story_job_id.set(job["id"])
        self._show_page("story")
        self._write_console(f"{job['id']} • พบงานค้างจากรอบก่อน • กำลังเปิด Chrome และทำต่ออัตโนมัติ", "log")
        self._retry_story_job(job["id"])

    def _schedule_story_recovery(self, job_id, error_message):
        """Keep the same Job and resume only the last incomplete safe stage."""
        if str(error_message or '').startswith('PRODUCT_EDITORIAL_'):
            return False
        if any(code in str(error_message or "") for code in (
            "STORY_FLOW_DUPLICATE_POLICY_EVENT", "FLOW_REPAIR_REVIEW", "FLOW_SEND_REVIEW",
            "FLOW_POLICY_BLOCKED", "FLOW_FACE_POLICY_BLOCKED", "FLOW_ATTACHMENT_UNCONFIRMED",
            "AI_IMAGE_REFERENCE_UNCONFIRMED", "AI_WEB_RESUME_REVIEW",
                    "STORY_IMAGE_PROGRESS_STALLED", "STORY_IMAGE_STALL_REVIEW",
        )):
            # The exact terminal event was already handled. Automatic recovery
            # would reopen Flow and physically submit the same scene again.
            # Leave the persisted prompt/checkpoint ready for an explicit user
            # resume after the stale heartbeat has disappeared.
            return False
        try:
            job = self.stories.get(job_id)
            failover_action = story_provider_failover_action(job, error_message)
            action = failover_action or story_recovery_action(job, error_message)
            attempts = int(job.get("auto_recovery_attempts") or 0)
        except Exception:
            return False
        if not action or attempts >= STORY_AUTO_RECOVERY_LIMIT:
            return False
        try:
            saved_analysis = self.stories.load_analysis_checkpoint(job_id) if action == "resume_chatgpt" else None
        except (OSError, ValueError, TypeError):
            # Do not spend the recovery budget or open a fresh chat around a
            # damaged saved plan. Manual resume exposes the precise review.
            return False
        if failover_action:
            job = self.stories.set_image_ai_provider(job_id, "chatgpt", error_message)
        recovery_stage = "chatgpt" if action in {"resume_chatgpt", "open_story_chatgpt"} else ("voice" if action == "voice" else "video")
        recovered = self.stories.mark_recovering(job_id, recovery_stage, error_message)
        attempt = int(recovered.get("auto_recovery_attempts") or 1)
        checkpoint_count = len(recovered.get("partial_generated_images") or [])
        scene_count = int(recovered.get("scene_count") or 0)
        has_ai_checkpoint = (
            bool(saved_analysis)
            or recovered.get("ai_status") == "ready"
            or bool(recovered.get("generated_images"))
            or bool(recovered.get("partial_generated_images"))
        )
        wait_ms = 2500 if attempt == 1 else 6000
        self._story_render_active = None
        self._story_progress_message.set(f"พบข้อขัดข้อง • กำลังกู้ต่ออัตโนมัติ {attempt}/{STORY_AUTO_RECOVERY_LIMIT}")
        if action == "resume_chatgpt":
            detail = f"เก็บภาพสำเร็จแล้ว {checkpoint_count}/{scene_count} • จะสร้างเฉพาะฉากที่ยังขาด"
        elif action == "voice":
            detail = "ภาพครบแล้ว • จะรอคิว AI Voice เดิมต่อโดยไม่ส่งบทหรือหักเครดิตซ้ำ"
        else:
            detail = "ภาพและเสียงเดิมยังอยู่ • จะประกอบวิดีโอใหม่โดยไม่เรียก AI ซ้ำ"
        self._story_progress_detail.set(detail)
        self.story_status.set(f"{job_id} • กำลังกู้ต่อจาก checkpoint อัตโนมัติ")
        self.status.set("Story Shorts • กำลังกู้ข้อมูลงานเดิม")
        self._write_console(f"{job_id} • AUTO RECOVERY {attempt}/{STORY_AUTO_RECOVERY_LIMIT} • {detail}", "log")
        resume_action = action
        if action == "resume_chatgpt":
            from core.ai_web_resume import ai_web_resume_target
            resume_target = ai_web_resume_target(self.stories.root / job_id, recovered) or {}
            must_read_old_chat = bool(resume_target.get("required"))
            if not has_ai_checkpoint:
                resume_action = "open_story_chatgpt"
            elif attempt >= 2 and not must_read_old_chat and "STORY_IMAGE_AUDIT_TIMEOUT_PRE_SEND" not in error_message:
                resume_action = "restart_chatgpt_images"
        provider_hint = str(recovered.get("image_ai_provider") or "chatgpt").strip().lower()
        provider_name = "Gemini Web" if provider_hint == "gemini" else "ChatGPT Web"
        if action == "resume_chatgpt" and attempt >= 2:
            if not has_ai_checkpoint:
                resume_action = "open_story_chatgpt"
            retry_detail = "ใช้ Analysis และ Checkpoint เดิม" if has_ai_checkpoint else "วิเคราะห์บทใหม่ใน Job เดิม เพราะยังไม่มี Checkpoint"
            self._story_progress_detail.set(f"{detail} • Retry บน {provider_name} เดิมและ{retry_detail}")
        recovery_event = self._story_cancel_event
        self.root.after(wait_ms, lambda active_event=recovery_event: self._resume_story_automatically(
            job_id, resume_action, provider_hint, cancel_event=active_event,
        ))
        return True

    def _resume_story_automatically(self, job_id, action, provider_hint="", cancel_event=None):
        queue = getattr(self, "story_queue", None)
        if queue is not None and hasattr(queue, "require_not_trashed"):
            try:
                queue.require_not_trashed(job_id)
            except ValueError:
                return
        # A timer from before Cancel/clear-state must not act on a fresh event
        # merely because the user resumed the same Job id.
        if (
            cancel_event is None or cancel_event is not self._story_cancel_event
            or self._story_pipeline_job_id != job_id or cancel_event.is_set()
        ):
            return
        try:
            if action in {"voice", "render"}:
                if action == "voice":
                    self._update_story_progress({"percent": 68, "stage": "voice", "message": "กำลังเชื่อมต่อคิว AI Voice เดิม", "detail": "ไม่ส่งงานเสียงซ้ำและไม่เสียเครดิตซ้ำ"})
                else:
                    self._update_story_progress({"percent": 79, "stage": "video", "message": "กำลังประกอบวิดีโอต่อจากไฟล์เดิม", "detail": "ไม่สร้างบท ภาพ หรือเสียงซ้ำ"})
                self._render_story()
                return
            job = self.stories.get(job_id)
            checkpoint_count = len(job.get("partial_generated_images") or [])
            active_provider = provider_hint or job.get("image_ai_provider") or "chatgpt"
            provider_name = "Gemini Web" if active_provider == "gemini" else "ChatGPT Web"
            self._update_story_progress({"percent": 15 + round(40 * checkpoint_count / max(1, int(job.get("scene_count") or 1))), "stage": "chatgpt", "message": f"กำลังเชื่อม {provider_name} เพื่อทำฉากที่เหลือ", "detail": f"ใช้ checkpoint เดิม {checkpoint_count}/{job.get('scene_count')} ฉาก"})
            # The previous content-script attempt leaves its terminal error in
            # the shared extension heartbeat.  Clear it before queuing the new
            # attempt; otherwise the monitor consumes every recovery slot from
            # the same stale error before the retry can start.
            self.bridge.clear_ai_progress(job_id)
            self.bridge.queue_extension_command(action, job_id, provider_hint=provider_hint)
            self._story_browser_launches = getattr(self, "_story_browser_launches", {})
            self._story_browser_launches[job_id] = {"resume_sent": True}
            _extension, compatible = self._compatible_extension()
            if not compatible or not self._chrome_window_available():
                self._launch_story_browser(job_id, active_provider, "Chrome ปิดระหว่างการกู้คืน", command_queued=True, action=action)
            else:
                self._activate_or_launch_chrome(self._ai_web_url(active_provider))
            self._story_monitor_after = self.root.after(700, lambda: self._monitor_story_browser_progress(job_id))
        except Exception as exc:
            self.events.put(("story_error", {"job_id": job_id, "cancel_event": cancel_event, "value": str(exc)}))

    @uses_job_files(lambda app, *args, **kwargs: (args, kwargs, getattr(app, '_creation_dispatch_item', {}), app.cfg,
        app.story_main_image.get(), app.voice_reference_file.get()), serialize=True)
    def _create_story_and_run(self, queue_item_id="", drama_context=None, long_video=None, flow_smoke_test=False, creative_context=None, actor_dialogue=False, product_script_options=None, storytelling_options=None, product_runtime_snapshot=None, story_structure_options=None, generated_music_options=None):
        if getattr(self, 'membership', None):
            self.membership.require()
        if queue_item_id:
            creative_context=self._creation_settings().get('creative_context')
            product_script_options=self._creation_settings().get('product_script_options')
            storytelling_options=self._creation_settings().get('storytelling_options')
            story_structure_options=self._creation_settings().get('story_structure_options')
            generated_music_options=self._creation_settings().get('generated_music_options')
        if self._story_pipeline_job_id:
            if self._story_progress_dialog and self._story_progress_dialog.winfo_exists():
                self._story_progress_dialog.lift()
            self.story_status.set(f"กำลังทำงาน {self._story_pipeline_job_id} อยู่")
            return ""
        if self._product_pipeline_job_id:
            if not queue_item_id:
                messagebox.showinfo("มีงานสินค้ากำลังทำอยู่", "ระบบทำงานหน้าเว็บได้ครั้งละหนึ่งงาน กรุณารอให้งานสินค้าจบ หรือยกเลิกงานเดิมก่อนเริ่ม Story Shorts")
            return ""
        api_key = self.voice_api_key.get().strip()
        reference_id = self.voice_reference_id.get().strip()
        reference_file = self.voice_reference_file.get().strip()
        if queue_item_id:
            frozen = self._creation_settings()
            reference_id = str(frozen.get("voice_reference_id", reference_id) or "")
            reference_file = str(frozen.get("voice_reference_file", reference_file) or "")
        elif product_runtime_snapshot is not None:
            reference_id = str(product_runtime_snapshot.get('voice_reference_id') or '')
            reference_file = str(product_runtime_snapshot.get('voice_reference_file') or '')
        if drama_context:
            reference_id = str(drama_context.get('primary_voice_reference_id') or reference_id)
            reference_file = str(drama_context.get('primary_voice_reference_file') or reference_file)
        choices = ((self._creation_settings().get("audio_choices") if queue_item_id else getattr(self, "_story_audio_choices", None))
                   or (drama_context or {}).get("render_options", {}).get("audio_choices"))
        if drama_context and 'audio_choices' in (drama_context.get('render_options') or {}):
            choices = drama_context['render_options']['audio_choices']
        if drama_context:
            generated_music_options = (drama_context.get('render_options') or {}).get('generated_music_options')
        needs_voice = not choices or choices.get("mode") == "api"
        if needs_voice and not api_key:
            if not queue_item_id:
                messagebox.showinfo("ตั้งค่า AI Voice ก่อนเริ่ม", "กรุณาใส่ API Key ในหน้า AI Voice ก่อนกดสร้างอัตโนมัติ")
            return ""
        if needs_voice and not reference_id and not Path(reference_file).is_file():
            if not queue_item_id:
                messagebox.showinfo("ตั้งค่าเสียงต้นแบบก่อนเริ่ม", "กรุณาเลือกเสียงต้นแบบหรือใส่ reference_id ในหน้า AI Voice")
            return ""
        try:
            provider = self._image_provider_key()
            ai_web_model = self._ai_web_model_key(provider)
            video_generation_mode = self._story_video_mode_key(
                self.story_video_mode.get(), drama_context
            )
            _extension, compatible = self._compatible_extension()
            if drama_context:
                if needs_voice and int(drama_context.get('episode_no') or 1) == 1 and not (
                        drama_context.get('primary_voice_reference_id') or drama_context.get('primary_voice_reference_file')):
                    self.drama_series.bind_first_episode_voice(
                        drama_context['series_id'], reference_id, reference_file)
                    drama_context = self.drama_series.episode_context(drama_context['series_id'], 1)
                job = self.stories.create(
                    self.story_topic.get(),
                    self.story_input.get("1.0", "end").strip(),
                    "",
                    self.story_scene_count.get(),
                    provider,
                    ai_web_model,
                    video_generation_mode=video_generation_mode,
                    job_type="drama_episode",
                    source_images=drama_context.get("source_images") or [],
                    source_footage=drama_context.get("footage_paths") or [],
                    series_context=drama_context,
                    storytelling_options=(drama_context.get('render_options') or {}).get('storytelling_options'),
                    **({'generated_music_options': generated_music_options} if generated_music_options is not None else {}),
                    visual_style=drama_context.get("visual_style", "auto"),
                    visual_style_custom=drama_context.get("visual_style_custom", ""),
                )
                self.drama_series.attach_story_job(
                    drama_context["series_id"], drama_context["episode_no"], job["id"]
                )
            else:
                job = self.stories.create(
                    self.story_topic.get(), self.story_input.get("1.0", "end").strip(),
                    self.story_main_image.get(), self.story_scene_count.get(), provider, ai_web_model,
                    video_generation_mode=video_generation_mode,
                    long_video=long_video,
                    meta_scene_sequence=not bool(creative_context),
                    long_source_audio_version=self._creation_settings().get('long_source_audio_version', 0) if queue_item_id else None,
                    flow_smoke_test=flow_smoke_test,
                    actor_dialogue=self._creation_settings().get('actor_dialogue', False) if queue_item_id else actor_dialogue,
                    storytelling_options=storytelling_options,
                    **({'story_structure_options': story_structure_options} if story_structure_options is not None else {}),
                    **({'generated_music_options': generated_music_options} if generated_music_options is not None else {}),
                    meta_prompt_version=self._creation_settings().get('meta_prompt_version', 1) if queue_item_id else None,
                    **({'cast_creation':True} if (creative_context or {}).get('kind')=='cast' else {}),
                    **({'product_short':True} if (creative_context or {}).get('product_short') is True else {}),
                    **({'product_script_options':product_script_options} if product_script_options is not None else {}),
                    visual_style=getattr(self, "_story_visual_style", "auto"),
                    visual_style_custom=getattr(self, "_story_visual_style_custom", ""),
                )
            if queue_item_id:
                self.story_queue.attach_job(queue_item_id, job["id"])
            creative_context = self._creation_settings().get('creative_context') if queue_item_id else creative_context
            if creative_context:
                from core.product_story import attach_context
                attach_context(self.stories,self.products,self.product_cast,job,creative_context)
                self.stories._save(job)
                self.stories._write_request(self.stories.root/job['id'],job)
                if (creative_context.get('kind') == 'product_story'
                        and creative_context.get('source_product_id')):
                    self.products.link_story_job(creative_context['source_product_id'], job['id'])
            confirmation = ((drama_context or {}).get("render_options", {}).get("fictional_ai_characters_confirmed")
                            if drama_context else self._creation_settings().get("fictional_ai_characters_confirmed")
                            if queue_item_id else getattr(self, "_story_fictional_confirmed", False))
            job["fictional_ai_characters_confirmed"] = confirmation is True
            if flow_smoke_test:
                job['flow_smoke_test'] = True
            from core.flow_settings import flow_settings
            render_source = ((drama_context or {}).get('render_options', {}) if drama_context else
                             self._creation_settings() if queue_item_id else product_runtime_snapshot or {})
            if render_source.get('speech_delivery_version') == 1 or (
                    not queue_item_id and not drama_context and product_runtime_snapshot is None):
                job['speech_delivery_version'] = 1
            if job.get('product_story') and (render_source.get('product_editorial_version') == 1 or (
                    not queue_item_id and not drama_context and product_runtime_snapshot is None)):
                job['product_editorial_version'] = 1
            job['render_snapshot'] = copy.deepcopy(
                render_source.get('render_snapshot', {}) if drama_context else
                render_source.get('render', {}) if queue_item_id or product_runtime_snapshot is not None else self._video_render_settings())
            if (creative_context or {}).get('kind') == 'product_story':
                # Rendering may start after all browser scenes finish or after
                # restart. Keep voice settings available beyond queue lifetime.
                job['product_runtime_snapshot'] = copy.deepcopy(render_source)
            flow_source = ((drama_context or {}).get("render_options", {}) if drama_context else
                           self._creation_settings() if queue_item_id else
                           {"flow_settings": getattr(self, "_story_flow_settings", {})})
            job["flow_settings"] = flow_settings(flow_source.get("flow_settings"))
            if flow_smoke_test or job.get('storytelling_options'):
                self.stories._write_request(self.stories.root / job['id'], job)
            from core.ai_cover import ai_cover_options
            job['ai_cover_options'] = ai_cover_options(flow_source.get('ai_cover_options', getattr(self, '_story_ai_cover_options', {}))
                if not queue_item_id and not drama_context else flow_source.get('ai_cover_options'))
            from ui.video_intro import capture_intro
            job['intro_options'] = capture_intro(self, flow_source.get('intro_options') if queue_item_id or drama_context
                else getattr(self, '_story_intro_options', None))
            from ui.green_screen import capture_green
            job['green_options'] = capture_green(self,
                flow_source.get('green_options') if queue_item_id or drama_context else getattr(self,'_story_green_options',None))
            self.stories._save(job)
            if choices:
                from core.story_performance import conversation_only, conversation_audio
                if conversation_only(job) and not job.get('storytelling_options'):
                    choices = conversation_audio(choices)
                job["audio_choices"] = audio_choices(choices, video_generation_mode)
                captured_audio = (self._creation_settings() if queue_item_id else product_runtime_snapshot
                    if product_runtime_snapshot is not None else self._creation_capture_settings({"audio_choices": choices, "video_generation_mode": video_generation_mode}))
                if drama_context and "audio_choices" in (drama_context.get("render_options") or {}):
                    captured_audio = {"audio": drama_context["render_options"].get("audio_mix_choices") or {}, "finish_config": drama_context["render_options"].get("media_finish_config") or {}}
                job["audio_mix_choices"] = dict(captured_audio.get("audio") or {})
                job["media_finish_config"] = dict(captured_audio.get("finish_config") or {})
                self.stories._save(job)
                if job.get('product_presentation_version') == 1 or job.get('actor_dialogue'):
                    # The original request was written before audio choices.
                    # Freeze the on-camera dialogue contract before dispatch.
                    self.stories._write_request(self.stories.root / job['id'], job)
            presenter_selection = ((getattr(self, "_creation_dispatch_item", None) or {}).get("settings", {}).get("presenter", {"enabled": False})
                                   if queue_item_id else getattr(self, "_presenter_story_selection", {"enabled": False}))
            if drama_context and "render_options" in drama_context:
                job["render_options"] = drama_render_options(drama_context["render_options"])
                presenter_selection = job["render_options"]["presenter"]
                self.stories._save(job)
            if presenter_selection.get("enabled") and (not drama_context or "render_options" in drama_context):
                self.presenters.assets(presenter_selection)
                job["presenter"] = dict(presenter_selection)
                self.stories._save(job)
            if generated_music_options is not None:
                from core.generated_music import validate_options, freeze_plan
                job['generated_music_options'] = validate_options(generated_music_options, video_generation_mode, job.get('audio_choices'))
                freeze_plan(job)
                self.stories._save(job)
                self.stories._write_request(self.stories.root / job['id'], job)
            if job.get('speech_delivery_version') == 1:
                self.stories._write_request(self.stories.root / job['id'], job)
            self.stories.mark_running(job["id"], "chatgpt")
            self.story_job_id.set(job["id"])
            self._story_pipeline_job_id = job["id"]
            self._story_cancel_event = threading.Event()
            self.story_run_button.configure(state="disabled")
            self._refresh()
            self._show_story_progress(job["id"])
            provider_name = "Gemini Web" if provider == "gemini" else "ChatGPT Web"
            model_name = ai_web_model_label(provider, ai_web_model)
            self._update_story_progress({"percent": 2, "stage": "chatgpt", "message": "ตรวจข้อมูลเรียบร้อย กำลังสั่ง Chrome Extension", "detail": f"{provider_name} • {model_name} • เตรียมสร้างภาพ {job['scene_count']} ฉาก"})
            self._activate_or_launch_chrome(self._ai_web_url(provider))
            self.bridge.queue_extension_command("open_story_chatgpt", job["id"])
            self._story_browser_launches = getattr(self, "_story_browser_launches", {})
            self._story_browser_launches[job["id"]] = {"resume_sent": True}
            if compatible:
                self._update_story_progress({"percent": 4, "stage": "chatgpt", "message": f"ส่งงานไปยัง {provider_name} แล้ว", "detail": "กำลังรอหน้าเว็บวิเคราะห์บทและเริ่มสร้างภาพ"})
            else:
                self._launch_story_browser(job["id"], provider, "Chrome ยังไม่เปิด • โปรแกรมกำลังเปิดให้เอง", command_queued=True, action="open_story_chatgpt")
            self.story_status.set(f"{job['id']} • ส่งให้ {provider_name} แล้ว • รอ {job['scene_count']} ภาพ")
            self.status.set(f"เปิด {provider_name} ใน Google Chrome แล้ว")
            self._write_console(f"{job['id']} • STORY • ส่งเข้า {provider_name}", "success")
            self._monitor_story_browser_progress(job["id"])
            return job["id"]
        except Exception as exc:
            self._story_pipeline_job_id = ""
            self._story_cancel_event = None
            if hasattr(self, "story_run_button"):
                self.story_run_button.configure(state="normal")
            if self._story_progress_dialog and self._story_progress_dialog.winfo_exists():
                self._finish_story_popup("error", "เริ่มงานไม่สำเร็จ", str(exc))
            elif not queue_item_id:
                messagebox.showerror("เริ่มเรื่องเล่าไม่สำเร็จ", str(exc))
            if queue_item_id:
                self.story_queue.fail_item(queue_item_id, str(exc))
            return ""

    def _resume_story_queue_on_startup(self):
        # Pending queue jobs need an explicit Start after opening the EXE.
        if self.story_queue.snapshot()["paused"]:
            return
        """Resume a persisted batch only after interrupted single-job recovery had a chance to run."""
        if self._story_pipeline_job_id or self._product_pipeline_job_id or self._startup_recovery_claimed:
            return
        self._start_next_story_queue_item()

    def _resume_interrupted_product_on_startup(self):
        """Resume the newest Product Job orphaned by an unexpected app exit."""
        if getattr(self, 'membership', None) and not self.membership.allowed():
            return
        if self.story_queue.snapshot()["active_count"]:
            return
        if self._product_pipeline_job_id or self._story_pipeline_job_id or self._startup_recovery_claimed:
            return
        jobs = self.products.list_jobs()
        job = interrupted_product_candidate(jobs) or recoverable_product_candidate(jobs)
        if not job:
            exhausted = interrupted_product_candidate(jobs, recovery_limit=None)
            if exhausted and int(exhausted.get("runtime_recovery_count") or 0) >= PRODUCT_RUNTIME_RECOVERY_LIMIT:
                job_id = str(exhausted.get("id") or "")
                error = (
                    f"กู้อัตโนมัติครบ {PRODUCT_RUNTIME_RECOVERY_LIMIT} รอบแล้ว • "
                    "เก็บ Checkpoint ไว้ครบ กรุณาเปิด Job เพื่อตรวจแล้วกดทำต่อ"
                )
                try:
                    self.products.set_automation_state(job_id, "error", "recovery_waiting", error)
                except Exception:
                    pass
                self._desktop_set_notice("warning", f"{job_id} • {error}")
                self._write_console(f"{job_id} • STARTUP RECOVERY PAUSED • {error}", "error")
            return
        job_id = str(job.get("id") or "")
        if not job_id:
            return
        self._startup_recovery_claimed = True
        try:
            recovered = self.products.mark_runtime_recovering(
                job_id,
                f"ตรวจพบโปรแกรมหยุดกลางขั้น {job.get('automation_stage') or 'unknown'} • ทำต่อจาก Checkpoint",
            )
            progress = product_progress(
                recovered,
                self.products.root / job_id,
                subtitle_enabled=bool(recovered.get("subtitle_requested", self.subtitle_auto.get())),
                audio_enabled=bool(self.audio_background_enabled.get() or self.audio_sfx_enabled.get()),
            )
            self._write_console(
                f"{job_id} • STARTUP RECOVERY • พบงานค้างจากรอบก่อน • "
                f"ทำต่อจาก {progress}% โดยไม่สร้างไฟล์ที่พร้อมแล้วซ้ำ",
                "log",
            )
            self._desktop_set_notice("info", f"กำลังกู้ {job_id} จาก Checkpoint {progress}% อัตโนมัติ")
            result = self._desktop_execute_action("create_product", {
                "job_id": job_id,
                "provider": str(recovered.get("image_ai_provider") or "chatgpt"),
                "subtitle": bool(recovered.get("subtitle_requested", self.subtitle_auto.get())),
            })
            if not result.get("ok"):
                raise RuntimeError("ระบบยังไม่สามารถเริ่มกู้ Product Job ได้")
            # The active Product worker now owns the job. Releasing this
            # startup-only lock lets queued work continue after it finishes.
            self._startup_recovery_claimed = False
        except Exception as exc:
            self._startup_recovery_claimed = False
            try:
                self.products.set_automation_state(job_id, "error", "recovery_waiting", str(exc))
            except Exception:
                pass
            self._desktop_set_notice("warning", f"พบงานค้าง {job_id} แต่ยังทำต่อไม่ได้ • {exc}")

    def _schedule_product_runtime_recovery(self, job_id, error_message):
        """Resume a transient Product browser failure in the same app session."""
        if not job_id:
            return False
        try:
            job = self.products.get_job(job_id)
        except Exception:
            return False
        if product_runtime_recovery_action(job, error_message) != "resume_pipeline":
            return False
        attempt = int(job.get("runtime_recovery_count") or 0) + 1
        self._write_console(
            f"{job_id} • RUNTIME RECOVERY {attempt}/{PRODUCT_RUNTIME_RECOVERY_LIMIT} • "
            "ผูก Chrome/Extension กลับ แล้วทำต่อจาก Checkpoint เดิมอัตโนมัติ",
            "log",
        )
        self._desktop_set_notice(
            "warning",
            f"{job_id} • ตรวจพบระบบสร้างวิดีโอหลุด • กำลังกู้จาก Checkpoint อัตโนมัติ "
            f"({attempt}/{PRODUCT_RUNTIME_RECOVERY_LIMIT})",
        )
        self._product_progress_event(
            job_id, product_progress(job, self.products.root / job_id), "flow",
            "ระบบสร้างวิดีโอรอบเดิมไม่รับคำสั่ง • กำลังผูก Checkpoint เดิมกลับอัตโนมัติ",
            "เก็บภาพ เสียง และช็อตที่เสร็จแล้วทั้งหมด • ไม่เริ่ม Job ใหม่",
        )
        self.root.after(4500, lambda: self._run_product_runtime_recovery(job_id, error_message))
        return True

    def _run_product_runtime_recovery(self, job_id, error_message):
        queue = getattr(self, "story_queue", None)
        if queue is not None and hasattr(queue, "require_not_trashed"):
            try:
                queue.require_not_trashed(job_id)
            except ValueError:
                return  # A timer from before deletion must not revive this job.
        active_product_worker = bool(
            self._product_pipeline_job_id
            and self._product_cancel_event is not None
            and not self._product_cancel_event.is_set()
        )
        if active_product_worker or self._story_pipeline_job_id:
            self._write_console(f"{job_id} • RUNTIME RECOVERY • มีงานอื่นเริ่มแล้ว จึงไม่เปิดงานซ้ำ", "log")
            return
        # A recovery progress event is UI status only. Older builds let that
        # event repopulate _product_pipeline_job_id after the failed worker had
        # already cleared its cancel event, so this callback mistook its own
        # stale label for another running job and never resumed the checkpoint.
        if self._product_pipeline_job_id and self._product_cancel_event is None:
            self._write_console(
                f"{job_id} • RUNTIME RECOVERY • ปลดสถานะ worker เก่าที่จบแล้วและทำต่อจาก Checkpoint",
                "log",
            )
            self._product_pipeline_job_id = ""
        try:
            job = self.products.get_job(job_id)
            if product_runtime_recovery_action(job, error_message) != "resume_pipeline":
                return
            recovered = self.products.mark_runtime_recovering(
                job_id,
                f"ระบบสร้างวิดีโอหลุดกลางงาน • ทำต่อจาก Checkpoint เดิม: {error_message}",
            )
            result = self._desktop_execute_action("create_product", {
                "job_id": job_id,
                "provider": str(recovered.get("image_ai_provider") or "chatgpt"),
                "subtitle": bool(recovered.get("subtitle_requested", self.subtitle_auto.get())),
            })
            if not result.get("ok"):
                raise RuntimeError("ระบบยังไม่สามารถเริ่มกู้ Product Job ได้")
            self._write_console(f"{job_id} • RUNTIME RECOVERY • เริ่มทำต่อจาก Checkpoint แล้ว", "success")
        except Exception as exc:
            try:
                self.products.set_automation_state(job_id, "error", "recovery_waiting", str(exc))
            except Exception:
                pass
            self._desktop_set_notice("warning", f"{job_id} • เริ่มกู้อัตโนมัติไม่สำเร็จ • {exc}")
            self._write_console(f"{job_id} • RUNTIME RECOVERY FAILED • {exc}", "error")
            self._write_console(f"{job_id} • STARTUP RECOVERY WAITING • {exc}", "error")

    def _schedule_next_story_queue_item(self, delay_ms=2200):
        snapshot = self.story_queue.snapshot()
        if snapshot["paused"] or not snapshot["active_count"]:
            return
        previous = getattr(self, "_creation_tick_after", None)
        if previous is not None:
            try:
                self.root.after_cancel(previous)
            except Exception:
                pass
        self._creation_tick_after = self.root.after(max(250, int(delay_ms)), self._creation_queue_tick)

    @staticmethod
    def _drama_queue_pause_reason(item):
        return f"drama_failure:{item.get('series_id') or ''}:{int(item.get('episode_no') or 0)}"

    def _pause_failed_drama_episode(self, item, error):
        """Stop the series at the failed EP so later episodes never lose continuity."""
        if not item or item.get("mode") != "drama":
            return False
        try:
            series = self.drama_series.mark_episode_failed(
                item.get("series_id"), item.get("episode_no"), str(error), job_id=item.get("job_id", ""))
            if isinstance(series, dict):
                episode = next((row for row in series.get("episodes", [])
                                if int(row.get("episode_no") or 0) == int(item.get("episode_no") or 0)), None)
                if (series.get("status") == "cancelled" or not episode
                        or episode.get("status") != "failed"
                        or (item.get("job_id") and episode.get("story_job_id")
                            and episode["story_job_id"] != item["job_id"])):
                    return False
        except Exception as exc:
            self.log.warning("state=DRAMA_FAILED result=error error=%s", exc)
        self.story_queue.pause(self._drama_queue_pause_reason(item))
        episode_no = int(item.get("episode_no") or 0)
        title = str(item.get("topic") or item.get("series_id") or "ละครสั้น")
        self.status.set(f"พักคิวละครที่ EP {episode_no} • ต้องกู้ตอนนี้ก่อนทำตอนถัดไป")
        self._desktop_set_notice(
            "warning",
            f"{title} หยุดที่ Checkpoint • กดกู้ EP {episode_no} แล้วระบบจะทำตอนถัดไปต่อเอง",
        )
        self._write_console(
            f"{item.get('series_id')} • EP {episode_no} FAILED • พักคิวเพื่อรักษาความต่อเนื่องของซีรีส์",
            "error",
        )
        return True

    def _story_queue_browser_recycled(self):
        """Wait for the previous job's close command before opening a fresh browser session."""
        gate = getattr(self, "_story_queue_browser_recycle", None)
        if not gate:
            return True
        elapsed = time.monotonic() - float(gate.get("requested_at") or 0)
        command = self.bridge.extension_command_status(gate.get("command_id")) if gate.get("command_id") else None
        status = str((command or {}).get("status") or "")
        _extension, compatible = self._compatible_extension()
        if (status == "completed" and elapsed >= 2.5) or (not compatible and elapsed >= 1.5):
            job_id = str(gate.get("job_id") or "STORY")
            self._story_queue_browser_recycle = None
            self._write_console(f"{job_id} • ปิด Chrome/แท็บงานเดิมแล้ว • พร้อมเปิดรอบใหม่", "success")
            return True
        if status == "failed" or elapsed >= 18:
            retries = int(gate.get("retries") or 0)
            if retries < 1:
                try:
                    retried = self.bridge.queue_extension_command("close_automation_browser", gate.get("job_id") or "")
                    gate.update({"command_id": retried["id"], "requested_at": time.monotonic(), "retries": retries + 1})
                    self._story_queue_browser_recycle = gate
                    self._write_console(f"{gate.get('job_id') or 'STORY'} • สั่งปิด Chrome ซ้ำก่อนเริ่มคลิปถัดไป", "log")
                except Exception as exc:
                    self.story_queue.pause()
                    self.status.set(f"พักคิว • ปิด Chrome รอบเดิมไม่สำเร็จ: {exc}")
                    return False
            else:
                self.story_queue.pause()
                self.status.set("พักคิว Story Shorts • ปิด Chrome รอบเดิมไม่สำเร็จ กรุณาปิด Chrome แล้วกดทำคิวต่อ")
                self._desktop_notice = {
                    "kind": "warning",
                    "message": "คิวถูกพักไว้ เพราะยังยืนยันการปิด Chrome รอบเดิมไม่ได้ • ปิด Chrome แล้วกดทำคิวต่อ",
                    "at": datetime.now().isoformat(timespec="seconds"),
                }
                return False
        self.status.set("คิว Story Shorts • รอปิด Chrome ของคลิปก่อนหน้าให้เรียบร้อย")
        self._schedule_next_story_queue_item(700)
        return False

    @uses_job_files(lambda app: app.story_queue.running_item() or app.story_queue.next_queued_item() or {})
    def _start_next_story_queue_item(self):
        if getattr(self, 'membership', None) and not self.membership.allowed():
            return
        self._creation_tick_after = None
        snapshot = self.story_queue.snapshot()
        if snapshot["paused"] or not snapshot["active_count"]:
            if not snapshot["paused"] and snapshot.get("run_series_id"):
                self.story_queue.claim_next()  # Persist scoped completion even when no other queue rows remain.
            return
        if getattr(self, "_manual_multi_flow_job_id", ""):
            self._schedule_next_story_queue_item(1000)
            return
        if self._creation_workers_alive():
            self._schedule_next_story_queue_item(500)
            return
        if self._story_pipeline_job_id:
            return
        if not self._story_queue_browser_recycled():
            return
        if self._product_pipeline_job_id:
            self.status.set("คิว Story Shorts • รอให้งานสินค้าปัจจุบันเสร็จก่อน")
            self._schedule_next_story_queue_item(5000)
            return
        candidate = self.story_queue.running_item() or self.story_queue.next_queued_item()
        if not candidate:
            self.story_queue.claim_next()  # End a selected-series run without starting unrelated work.
            return
        if self._creation_restore_final(candidate):
            return
        # Cover-only work can also be started from the library. Do not dispatch
        # a new topic into its browser lane while that exact request is active.
        from core.ai_cover import AICovers
        covers = getattr(getattr(self, 'bridge', None), 'ai_covers', None)
        if isinstance(covers, AICovers) and covers.active():
            self.status.set('คิวสร้างคลิป • รอปก AI ที่กำลังทำอยู่ก่อนเริ่มหัวข้อถัดไป')
            self._schedule_next_story_queue_item(1000)
            return
        try:
            self._creation_preflight(candidate)
        except Exception as exc:
            self.story_queue.pause("preflight")
            self.story_queue._update(candidate["queue_id"], error=str(exc))
            self._desktop_set_notice("warning", str(exc))
            self._write_console(f"CREATION QUEUE • WAITING • {exc}", "error")
            return

        running = self.story_queue.running_item()
        if running and running.get("mode") == "product":
            self._creation_start_product(running)
            return
        if running and running.get("job_id"):
            job_id = str(running.get("job_id") or "")
            try:
                job = self.stories.get(job_id)
                if job.get("status") == "ready" and job.get("video_status") == "ready":
                    output = self.stories.root / job_id / str(job.get("video_path") or "")
                    if not output.is_file() or output.stat().st_size <= 0:
                        self.story_queue.mark_failed_by_job(job_id, "ไม่พบไฟล์ Final ที่พร้อมใช้งาน")
                        self.story_queue.pause("missing_final")
                        return
                    if not self._creation_cover_gate(job_id, running):
                        return
                    if job.get('series_id'):
                        self.drama_series.mark_episode_ready(
                            {**job, '_folder': str(self.stories.root / job_id)}, output)
                    self.story_queue.mark_completed_by_job(job_id, output)
                    self._schedule_next_story_queue_item(500)
                    return
                if job.get("status") == "cancelled":
                    self.story_queue.mark_cancelled_by_job(job_id)
                    self.story_queue.pause()
                    return
                if job.get("status") == "failed":
                    error = job.get("error") or "Story Job ทำงานไม่สำเร็จ"
                    failed_item = self.story_queue.mark_failed_by_job(job_id, error)
                    if not self._pause_failed_drama_episode(failed_item, error):
                        self._schedule_next_story_queue_item(500)
                    return
                self._write_console(f"STORY QUEUE • ทำต่อ {job_id} จาก Checkpoint", "log")
                self._retry_story_job(job_id)
                return
            except Exception as exc:
                self.story_queue.fail_item(running["queue_id"], f"เปิด Job เดิมไม่สำเร็จ: {exc}")
                if not self._pause_failed_drama_episode(running, exc):
                    self._schedule_next_story_queue_item(500)
                return
        if running:
            self.story_queue.release_running(running["queue_id"], "คืนงานเข้าคิวหลังโปรแกรมเริ่มใหม่")

        item = self.story_queue.claim_next()
        if not item:
            return
        if item.get("mode") == "product":
            self._creation_start_product(item)
            return
        if not self._creation_prepare_dispatch(item):
            return
        if item.get("job_id"):
            self._retry_story_job(item["job_id"])
            return
        drama_context = None
        if item.get("mode") == "drama":
            try:
                drama_context = self.drama_series.episode_context(item.get("series_id"), item.get("episode_no"))
            except Exception as exc:
                self.story_queue.fail_item(item["queue_id"], f"เตรียมข้อมูล EP ไม่สำเร็จ: {exc}")
                self._pause_failed_drama_episode(item, f"เตรียมข้อมูล EP ไม่สำเร็จ: {exc}")
                return
        self.image_ai_provider.set("Gemini Web" if item.get("provider") == "gemini" else "ChatGPT Web")
        self._set_ai_web_model(
            item.get("provider"),
            item.get("ai_web_model") or (drama_context or {}).get("ai_web_model"),
        )
        self.story_topic.set(str((drama_context or item).get("topic") or ""))
        self.story_input.delete("1.0", "end")
        self.story_input.insert("1.0", str((drama_context or item).get("story_text") or ""))
        self.story_scene_count.set(int(item.get("scene_count") or 10))
        self.story_main_image.set(str(item.get("main_image") or ""))
        self._story_visual_style, self._story_visual_style_custom = normalize_story_style(item.get("visual_style"), item.get("visual_style_custom"))
        queued_video_mode = str(
            item.get("video_generation_mode")
            or (drama_context or {}).get("video_generation_mode")
            or ""
        ).strip().lower()
        if queued_video_mode in {"image_motion", "google_flow", "meta_ai"}:
            self.story_video_mode.set(next(
                (label for label, key in STORY_VIDEO_MODES.items() if key == queued_video_mode),
                "ภาพเคลื่อนไหวอัตโนมัติ",
            ))
        snapshot = self.story_queue.snapshot()
        completed = snapshot["counts"]["completed"] + snapshot["counts"]["failed"] + snapshot["counts"]["cancelled"]
        self.status.set(f"คิว Story Shorts • เริ่มคลิป {completed + 1}/{snapshot['total_count']} • {item['topic']}")
        self._write_console(f"STORY QUEUE • เริ่ม {item['queue_id']} • {item['topic']}", "success")
        if item.get('long_video'):
            started_job_id = self._create_story_and_run(queue_item_id=item["queue_id"], drama_context=drama_context, long_video=item['long_video'])
        else:
            started_job_id = self._create_story_and_run(queue_item_id=item["queue_id"], drama_context=drama_context, **({'flow_smoke_test':True} if item.get('flow_smoke_test') else {}))
        if not started_job_id:
            latest = self.story_queue.running_item()
            if latest and latest.get("queue_id") == item["queue_id"]:
                self.story_queue.fail_item(item["queue_id"], "เริ่ม Story Job ไม่สำเร็จ")
            if not self._pause_failed_drama_episode(item, "เริ่ม Story Job ไม่สำเร็จ"):
                self._creation_story_failure(item, "เริ่ม Story Job ไม่สำเร็จ")

    @uses_job_files(lambda app: app.story_job_id.get())
    def _send_story_chatgpt(self):
        job_id = self.story_job_id.get().strip()
        if not job_id:
            messagebox.showinfo("เลือก Story Job", "กรุณาเลือกงานเรื่องเล่าก่อน")
            return
        try:
            job = self.stories.get(job_id)
            provider_name = "Gemini Web" if job.get("image_ai_provider") == "gemini" else "ChatGPT Web"
            self.bridge.queue_extension_command("open_story_chatgpt", job_id)
            _extension, compatible = self._compatible_extension()
            self._activate_or_launch_chrome(self._ai_web_url(job.get("image_ai_provider")))
            self.story_status.set(f"{job_id} • ส่งเข้า {provider_name} แล้ว")
        except Exception as exc:
            messagebox.showerror("ส่ง AI Web ไม่สำเร็จ", str(exc))

    def _load_story_job(self):
        job_id = self.story_job_id.get().strip()
        if not job_id:
            return
        try:
            job = self.stories.get(job_id)
            title = job.get("video_title") or "(รอ ChatGPT ตั้งชื่อคลิป)"
            description = job.get("video_description") or "(รอ ChatGPT เขียนคำอธิบาย)"
            script = spoken_script_for_job(job) or "(รอ ChatGPT เขียนบทพากย์)"
            self.story_result.delete("1.0", "end")
            self.story_result.insert("1.0", f"ชื่อคลิป\n{title}\n\nคำอธิบาย\n{description}\n\nบทพากย์\n{script}")
            checkpoint_count = max(len(job.get("generated_images") or []), len(job.get("partial_generated_images") or []))
            self.story_status.set(f"{job_id} • {job.get('status')} • ภาพ {checkpoint_count}/{job.get('scene_count')}")
            provider_name = "Gemini Web" if job.get("image_ai_provider") == "gemini" else "ChatGPT Web"
            video_mode = ("Google Flow ทุกฉาก" if job.get("video_generation_mode") == "google_flow"
                else "Meta AI ทุกฉาก" if job.get("video_generation_mode") == "meta_ai" else "Motion ในเครื่อง")
            self.story_provider_note.set(f"แหล่งภาพ Job นี้: {provider_name} ผ่าน Chrome\nวิดีโอ: {video_mode} • Checkpoint ทำต่อด้วยโหมดเดิม")
            if hasattr(self, "story_resume_button"):
                finished = job.get("status") == "ready" and job.get("video_status") == "ready"
                self.story_resume_button.configure(state="disabled" if finished else "normal")
        except Exception as exc:
            self.story_status.set(str(exc))

    def _open_story_folder(self):
        job_id = self.story_job_id.get().strip()
        if job_id:
            self._open_folder(self.stories.root / job_id)

    @uses_job_files(lambda app: (app.story_job_id.get(), app.voice_reference_file.get()))
    def _render_story(self):
        job_id = self.story_job_id.get().strip()
        api_key = self.voice_api_key.get().strip()
        reference_id = self.voice_reference_id.get().strip()
        reference_file = self.voice_reference_file.get().strip()
        frozen = self._creation_settings(job_id)
        reference_id = str(frozen.get("voice_reference_id", reference_id) or "")
        reference_file = str(frozen.get("voice_reference_file", reference_file) or "")
        if not job_id:
            messagebox.showinfo("เลือก Story Job", "กรุณาเลือกงานเรื่องเล่าก่อน")
            return
        if self._story_render_active:
            self.story_status.set(f"กำลังประกอบ {self._story_render_active} อยู่")
            return
        try:
            selected_story = self.stories.get(job_id)
        except Exception:
            selected_story = {}
        reference_id = str(selected_story.get('primary_voice_reference_id') or reference_id)
        reference_file = str(selected_story.get('primary_voice_reference_file') or reference_file)
        saved_voice = self.stories.root / job_id / str(selected_story.get("voice_path") or "")
        voice_ready = selected_story.get("voice_status") == "ready" and saved_voice.is_file()
        if selected_story.get('scene_pipeline_version') == 1:
            from core.scene_pipeline import ScenePipeline
            try:
                voice_ready = bool(ScenePipeline(self.stories.root/job_id).segments(int(selected_story['scene_count'])))
            except (ValueError, KeyError, OSError):
                voice_ready = False
        if audio_mode(selected_story) == "api" and not voice_ready:
            if not api_key:
                messagebox.showinfo("AI Voice API Key", "กรุณาบันทึก API Key ในหน้า AI Voice ก่อน")
                return
            if not reference_id and not Path(reference_file).is_file():
                messagebox.showinfo("เสียงต้นแบบ", "กรุณาเลือกเสียงต้นแบบในหน้า AI Voice ก่อน")
                return
        self.story_status.set("กำลังสร้างเสียงพากย์ แล้วประกอบภาพทุกฉากเป็นวิดีโอ..." if audio_mode(selected_story) == "api" else "กำลังประกอบวิดีโอ • ไม่เรียกเสียง API")
        self._story_render_active = job_id
        if self._story_pipeline_job_id != job_id:
            self._story_pipeline_job_id = job_id
            self._story_cancel_event = threading.Event()
            self._show_story_progress(job_id)
        pending_video = selected_story.get('video_generation_mode') in {'google_flow', 'meta_ai'} and selected_story.get('scene_pipeline_version') != 1
        self._update_story_progress({"percent": 60 if pending_video else 61, "stage": "video" if pending_video else "voice" if audio_mode(selected_story) == "api" else "video", "message": "รับภาพครบแล้ว กำลังตรวจและสร้างวิดีโอแต่ละฉาก" if pending_video else "รับบทและภาพครบแล้ว กำลังเตรียมเสียง API SmartSub" if audio_mode(selected_story) == "api" else "รับภาพครบแล้ว • ข้ามเสียง API ตามค่าที่เลือก", "detail": selected_story.get("image_fallback_notice") or "ใช้ค่าที่บันทึกไว้กับงานนี้"})
        worker_cancel_event = self._story_cancel_event
        self._creation_story_worker = guarded_thread(self, job_id, self._story_worker,
            args=(job_id, lambda: self._render_story_worker(job_id, api_key, reference_id, reference_file, cancel_event=worker_cancel_event), worker_cancel_event),
            references=reference_file, daemon=True)

    def _story_worker(self, job_id, func, cancel_event):
        try:
            func()
        except OperationCancelled:
            self.events.put(("story_cancelled", {"job_id": job_id, "cancel_event": cancel_event}))
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                self.events.put(("story_cancelled", {"job_id": job_id, "cancel_event": cancel_event}))
                return
            self.log.exception("state=STORY_RENDER result=error error=%s", exc)
            self.events.put(("story_error", {"job_id": job_id, "cancel_event": cancel_event, "value": str(exc)}))

    def _render_story_worker(self, job_id, api_key, reference_id, reference_file, cancel_event=None):
        if cancel_event is None:
            cancel_event = self._story_cancel_event
        emit_voice = lambda payload: self._queue_story_phase(job_id, cancel_event, 'voice', payload)
        frozen_voice = self._creation_settings(job_id).get("voice") or {}
        check_cancelled(cancel_event)
        job = self.stories.repair_program_cta(job_id)
        if job.get('actor_dialogue'):
            from core.story_performance import validate_option
            validate_option(True, job.get('video_generation_mode'), job.get('audio_choices'),
                            job.get('storytelling_options'), drama=job.get('job_type') == 'drama_episode', music_job=job)
        if job.get("ai_status") != "ready" or len(job.get("generated_images") or []) != int(job.get("scene_count") or 0):
            raise ValueError("Story Job ยังไม่ได้บทและรูปครบจาก AI Web")
        from core.meta_scene_sequence import assert_all_ready
        assert_all_ready(self.stories, job)
        folder = self.stories.root / job_id
        from core.scene_video_plan import enabled as planned_video
        if planned_video(job) and job.get('scene_pipeline_version') == 1:
            for index, state in sorted((job.get('flow_speech_retries') or {}).items(), key=lambda pair: int(pair[0])):
                if state.get('status') == 'pending':
                    self._retry_story_native_speech_scene(job_id, int(index), state, cancel_event)
            from core.scene_video_worker import complete_missing_segments
            complete_missing_segments(self, job_id, api_key, reference_id, reference_file, cancel_event)
        if job.get('scene_pipeline_version') == 1 and (planned_video(job) or job.get('video_generation_mode') == 'google_flow'):
            from core.scene_pipeline import ScenePipeline
            from core.flow_speech_quality import RepeatedNativeSpeechError
            for _ in range(1 + 2 * int(job['scene_count'])):
                check_cancelled(cancel_event)
                current = self.stories.get(job_id)
                pending = [(int(index), state) for index, state in
                           (current.get('flow_speech_retries') or {}).items()
                           if state.get('status') == 'pending']
                if pending:
                    for index, state in sorted(pending):
                        self._retry_story_native_speech_scene(job_id, index, state, cancel_event)
                ScenePipeline(folder).segments(int(job['scene_count']))
                try:
                    return self._compose_story_media(job_id, self.stories.get(job_id), '', cancel_event)
                except RepeatedNativeSpeechError as error:
                    finding = error.audit['findings'][0]
                    self.stories.begin_native_speech_retry(
                        job_id, finding, error.audit['source_sha256'])
                    self._queue_story_phase(job_id, cancel_event, 'source_video', {
                        'percent': 80, 'stage': 'video',
                        'message': f"พบเสียงพูดซ้ำชัดเจน • กำลังสร้างฉาก {finding['scene']} ใหม่",
                        'detail': 'เก็บคลิปเดิมไว้ • ใช้ภาพและบทเดิม สร้าง Flow โปรเจกต์ใหม่เฉพาะฉากนี้',
                    })
            raise ValueError('FLOW_SPEECH_REPEAT_REVIEW • เกินรอบแก้เสียงซ้ำที่กำหนด • เก็บฉากเดิมไว้ตรวจ')
        if planned_video(job):
            from core.scene_video_worker import collect_all
            collect_all(self, job_id, cancel_event)
            check_cancelled(cancel_event)
            job = self.stories.get(job_id)
        elif job.get('video_generation_mode') == 'google_flow':
            # Resolve changed story segments before synthesizing their speech.
            self._collect_story_flow_clips(job_id, cancel_event)
            check_cancelled(cancel_event)
            job = self.stories.activate_flow_story_revision(job_id)
        elif job.get('video_generation_mode') == 'meta_ai':
            if job.get('long_video'):
                # Collection may span many paid scenes. Persist ownership
                # before opening Meta so a desktop restart resumes the same
                # per-scene receipts instead of leaving ready_to_render idle.
                self.stories.mark_running(job_id, 'meta_ai')
            self._collect_story_meta_clips(job_id, cancel_event)
            check_cancelled(cancel_event)
        if audio_mode(job) != "api":
            self.events.put(("story_progress", {"percent": 79, "stage": "video", "message": "ข้ามเสียง API ตามค่าประจำงาน • เตรียมประกอบวิดีโอ"}))
            return self._compose_story_media(job_id, job, "", cancel_event)
        from core.product_editorial import assert_approved
        assert_approved(job)
        existing_voice = folder / str(job.get("voice_path") or "")
        if (job.get("voice_status") == "ready" and existing_voice.is_file()
                and existing_voice.resolve().is_relative_to(folder.resolve())
                and existing_voice.stat().st_size > 0):
            # Narration edits invalidate voice_status in StoryManager. A
            # still-ready saved voice needs no new-synthesis pronunciation
            # review (which may have become stricter since it was generated).
            self.stories.mark_running(job_id, "voice")
            emit_voice({"percent": 79, "stage": "voice", "message": "ใช้เสียงพากย์เดิมที่สร้างสำเร็จแล้ว", "detail": "แก้ภาพหรือเรนเดอร์ใหม่โดยไม่เสียเครดิต AI Voice ซ้ำ"})
            return self._compose_story_media(job_id, job, existing_voice, cancel_event)
        from core.speech_delivery import enabled as speech_enabled, effective_script
        script, issues = (effective_script(job, include_pauses=True) if speech_enabled(job)
                         else prepare_thai_tts_script(spoken_script_for_job(job, include_pauses=True), pronunciation_notes(job)))
        if issues:
            raise ValueError("บทพากย์ยังไม่พร้อมสำหรับ AI Voice: " + " • ".join(issues))
        self.stories.mark_running(job_id, "voice")
        client = ExternalTtsClient(api_key, self.cfg.get("voice_api_base_url", "https://www.catfufu.com"))
        if not reference_id:
            emit_voice({"percent": 63, "stage": "voice", "message": "กำลังอัปโหลดเสียงต้นแบบ", "detail": "รอ reference_id จากระบบเสียง"})
            uploaded = client.upload_reference(reference_file)
            check_cancelled(cancel_event)
            reference_id = str(uploaded["reference_id"])
            self.events.put(("voice_reference", (reference_id, Path(reference_file).name)))
        if job.get("job_type") == "drama_episode" and job.get("dialogue_turns"):
            character_refs = {
                str(character.get("name") or "").strip(): str(character.get("voice_reference_id") or reference_id).strip()
                for character in (job.get("character_bible") or [])
                if str(character.get("name") or "").strip()
            }
            use_character_voices = any(value and value != reference_id for value in character_refs.values())
            if use_character_voices:
                voice = self._render_drama_dialogue_voice(
                    job_id, job, client, reference_id, character_refs, cancel_event
                )
                return self._compose_story_media(job_id, self.stories.get(job_id), voice, cancel_event)
        emit_voice({"percent": 66, "stage": "voice", "message": "กำลังตรวจคิว API SmartSub", "detail": "ถ้าเคยส่งงานแล้ว ระบบจะใช้คิวเดิมโดยไม่เสียเครดิตซ้ำ"})
        if len(script) > MAX_TTS_REQUEST_CHARS:
            revision_part = ('-' + hashlib.sha256(str(job['flow_story_revision']).encode()).hexdigest()[:16]) if job.get('flow_story_revision') else ''
            voice = folder / "audio" / ("narration" + revision_part + ".mp3")
            external_job_id, output_id, reference_id = render_chunked_voice(
                client, script, reference_id, voice, scope=f"story:{job_id}:narration",
                options={"language": frozen_voice.get("language", self.voice_language.get().strip() or "th"),
                         "engine": "auto", "silence_sec": float(frozen_voice.get("silence_sec", self.voice_silence.get()))},
                ffmpeg_path=self.cfg.get("ffmpeg_path"), cancel_event=cancel_event,
                on_progress=lambda message: emit_voice({
                    "percent": 70, "stage": "voice", "message": message,
                    "detail": "ส่งทีละช่วง ไม่เกิน 2,000 ตัวอักษร และเก็บคิวเพื่อทำต่อ"}),
                on_checkpoint=lambda remote, ref: self.stories.save_voice_checkpoint(
                    job_id, external_job_id=remote, reference_id=ref, status="queued"),
                repair_reference=lambda ref: self._repair_chunk_voice_reference(client, ref, reference_file, cancel_event),
                legacy_job_id=str(job.get("voice_job_id") or ""),
                legacy_output_id=str(job.get("voice_output_id") or ""),
            )
            self.stories.save_voice(job_id, voice, external_job_id, output_id, reference_id)
            return self._compose_story_media(job_id, self.stories.get(job_id), voice, cancel_event)
        voice_resubmit_count = int(job.get("voice_resubmit_count") or 0)
        def submit(active_reference_id, revision=None):
            active_revision = max(1, int(revision or (voice_resubmit_count + 1)))
            return client.synthesize(
                script, active_reference_id,
                language=frozen_voice.get("language", self.voice_language.get().strip() or "th"),
                emotion_id=CLIP_VOICE_EMOTION, engine="auto",
                speed=CLIP_VOICE_SPEED, silence_sec=float(frozen_voice.get("silence_sec", self.voice_silence.get())),
                idempotency_key=f"story:{job_id}:narration:v{active_revision}",
            )
        external_job_id = str(job.get("voice_job_id") or "").strip()
        output_id = str(job.get("voice_output_id") or "").strip()
        if external_job_id:
            reference_id = str(job.get("voice_reference_id") or reference_id).strip()
            emit_voice({"percent": 68, "stage": "voice", "message": "พบคิวเสียงเดิม กำลังทำต่อ", "detail": f"คิว {external_job_id} • ไม่ส่งบทซ้ำและไม่เสียเครดิตซ้ำ"})
        else:
            try:
                queued = submit(reference_id)
            except ExternalTtsError as exc:
                missing_reference = "HTTP 404" in str(exc) or "ไม่พบไฟล์เสียงต้นแบบ" in str(exc)
                if missing_reference and reference_id.startswith(("preset:", "custom:")):
                    raise ExternalTtsError("เสียงที่เลือกไม่มีอยู่ในบัญชีแล้ว กรุณากดโหลดรายการเสียงใหม่และเลือกเสียงอีกครั้ง") from None
                source = Path(reference_file) if reference_file else None
                if not missing_reference or not source or not source.is_file():
                    raise
                emit_voice({"percent": 64, "stage": "voice", "message": "เสียงต้นแบบเดิมหมดอายุ กำลังอัปโหลดใหม่", "detail": "ระบบจะบันทึก reference_id ใหม่แล้วลองสร้างเสียงต่ออัตโนมัติ"})
                uploaded = client.upload_reference(source)
                check_cancelled(cancel_event)
                reference_id = str(uploaded["reference_id"])
                self.events.put(("voice_reference", (reference_id, source.name)))
                queued = submit(reference_id)
            check_cancelled(cancel_event)
            external_job_id = str(queued["job_id"])
            # Persist the paid request before the first status poll.  A network
            # timeout can now resume this exact queue instead of charging again.
            self.stories.save_voice_checkpoint(
                job_id, external_job_id=external_job_id,
                reference_id=reference_id, status="queued",
            )
            emit_voice({"percent": 68, "stage": "voice", "message": "API SmartSub รับงานแล้ว", "detail": f"บันทึกคิว {external_job_id} แล้ว • รอสถานะจากเซิร์ฟเวอร์"})
        def voice_status(state, result):
            raw = result.get("progress_percent", result.get("progress"))
            try:
                value = float(str(raw).strip().rstrip("%"))
                if 0 <= value <= 1: value *= 100
                percent = 68 + round(max(0, min(100, value)) * 0.09)
            except (TypeError, ValueError):
                percent = 70
            if state == "connection_retry":
                retry_count = int(result.get("retry_count") or 1)
                message = "AI Voice ตอบช้า • กำลังเชื่อมต่อคิวเดิมใหม่"
                detail = f"คิว {external_job_id} • ลองอ่านสถานะใหม่ครั้งที่ {retry_count} โดยไม่ส่งงานซ้ำ"
            else:
                message = f"AI Voice • {state or 'processing'}"
                detail = f"คิว {external_job_id} • เปอร์เซ็นต์ย่อยใช้ค่าที่ API รายงาน"
            emit_voice({"percent": percent, "stage": "voice", "message": message, "detail": detail})
        if not output_id:
            try:
                _, output_id = client.wait_until_done(external_job_id, on_status=voice_status, cancel_event=cancel_event)
            except ExternalTtsError as exc:
                if not exc.retryable or voice_resubmit_count >= 1:
                    raise
                failed_job_id = external_job_id
                voice_resubmit_count += 1
                self.stories.prepare_voice_resubmit(job_id, failed_job_id, str(exc), max_resubmits=1)
                emit_voice({
                    "percent": 68, "stage": "voice",
                    "message": "AI Voice ทำไฟล์ชั่วคราวหาย • กำลังสร้างคิวทดแทน 1 ครั้ง",
                    "detail": "เก็บบทและภาพเดิมครบ • ใช้รหัสป้องกันงานซ้ำ revision ใหม่และจะไม่วนสร้างไม่จำกัด",
                })
                self.log.warning(
                    "job_id=%s state=STORY_VOICE_TERMINAL_RETRY old_voice_job_id=%s revision=%s error=%s",
                    job_id, failed_job_id, voice_resubmit_count + 1, exc,
                )
                if cancel_event.wait(3):
                    check_cancelled(cancel_event)
                check_cancelled(cancel_event)
                queued = submit(reference_id, revision=voice_resubmit_count + 1)
                external_job_id = str(queued["job_id"])
                output_id = ""
                self.stories.save_voice_checkpoint(
                    job_id, external_job_id=external_job_id,
                    reference_id=reference_id, status="queued",
                )
                emit_voice({
                    "percent": 68, "stage": "voice",
                    "message": "AI Voice รับคิวทดแทนแล้ว",
                    "detail": f"เปลี่ยนจากคิว {failed_job_id} เป็น {external_job_id} • รอผลโดยไม่ย้อนสร้างภาพ",
                })
                _, output_id = client.wait_until_done(external_job_id, on_status=voice_status, cancel_event=cancel_event)
            self.stories.save_voice_checkpoint(
                job_id, external_job_id=external_job_id, output_id=output_id,
                reference_id=reference_id, status="completed",
            )
        check_cancelled(cancel_event)
        voice = folder / "audio" / "narration.mp3"
        emit_voice({"percent": 78, "stage": "voice", "message": "เสียงสร้างเสร็จแล้ว กำลังดาวน์โหลด", "detail": "บันทึกเสียงพากย์เข้า Story Job"})
        client.download(output_id, voice, "mp3", cancel_event=cancel_event)
        check_cancelled(cancel_event)
        self.stories.save_voice(job_id, voice, external_job_id, output_id, reference_id)
        return self._compose_story_media(job_id, job, voice, cancel_event)

    def _retry_story_native_speech_scene(self, job_id, index, state, cancel_event):
        """Resume one durable, fresh Flow attempt; never replay old projects."""
        from core.scene_pipeline import ScenePipeline
        from core.scene_voice import render_scene_asset
        from core.scene_context_revision import render_story
        folder = self.stories.root / job_id
        retry_id = str(state.get('retry_id') or '')
        from core.scene_video_plan import enabled as planned_video, begin_native_retry, apply_at_safe_boundary, finish_scene, effective_job
        planned = planned_video(self.stories.get(job_id))
        if planned:
            begin_native_retry(self.stories, job_id, index, retry_id, state.get('segment_sha256'))
        pipeline = ScenePipeline(folder)
        row = pipeline.begin_speech_retry(index, retry_id, state.get('segment_sha256'))
        if row.get('phase') != 'complete':
            if planned:
                apply_at_safe_boundary(self.stories, job_id, index)
            self._queue_story_phase(job_id, cancel_event, 'source_video', {
                'percent': 80, 'stage': 'video',
                'message': f'กำลังสร้างฉาก {index} ใหม่เพื่อแก้เสียงซ้ำ',
                'detail': f"รอบ {state.get('attempt')} • ไม่แตะฉากอื่นและไม่ใช้ผลจากโปรเจกต์ Flow เดิม",
            })
            clips = self._collect_story_flow_clips(job_id, cancel_event, only_scene=index,
                                                   fresh_scene_attempt=retry_id)
            check_cancelled(cancel_event)
            job = render_story(folder, self.stories.get(job_id))
            if planned:
                job = effective_job(job, index)
            render = job.get('render_snapshot') or self._creation_settings(job_id).get('render') or self._video_render_settings()
            if job.get('long_video'):
                render = {**render, 'width': 1920, 'height': 1080}
            result = render_scene_asset(folder, job, index, clips[0], None, '', render,
                                        self.cfg.get('ffmpeg_path', ''), cancel_event, lambda _message: None)
            check_cancelled(cancel_event)
            pipeline.update(index, row['revision'], phase='complete',
                            message='สร้างฉากทดแทนแล้ว • รอตรวจเสียงจริงอีกครั้ง', **result)
        if planned:
            finish_scene(self.stories, job_id, index)
        self.stories.complete_native_speech_retry(job_id, index, retry_id)

    def _render_drama_dialogue_voice(self, job_id, job, client, default_reference_id, character_refs, cancel_event):
        from core.product_editorial import assert_approved
        assert_approved(job)
        folder = self.stories.root / job_id
        revision_suffix = (":" + hashlib.sha256(str(job['flow_story_revision']).encode()).hexdigest()[:16]) if job.get('flow_story_revision') else ""
        segment_folder = folder / "audio" / ("dialogue" + revision_suffix.replace(':', '-'))
        segment_folder.mkdir(parents=True, exist_ok=True)
        turns = list(job.get("dialogue_turns") or [])
        if not turns:
            raise ValueError("ละครสั้นยังไม่มีบทสนทนาสำหรับสร้างเสียง")
        segment_paths = []
        external_ids = []
        output_ids = []
        voice_checkpoints = dict(job.get("dialogue_voice_checkpoints") or {})
        for index, turn in enumerate(turns, 1):
            check_cancelled(cancel_event)
            target = segment_folder / f"turn_{index:03d}.mp3"
            segment_paths.append(target)
            if target.is_file() and target.stat().st_size > 1024:
                continue
            speaker = str(turn.get("speaker") or "ผู้บรรยาย").strip()
            reference_id = character_refs.get(speaker) or default_reference_id
            speech, issues = prepare_thai_tts_script(str(turn.get("text") or ""), pronunciation_notes(job))
            if issues or not speech:
                raise ValueError(f"บทพูดลำดับ {index} ของ {speaker} ยังไม่พร้อม: {' • '.join(issues) if issues else 'ไม่มีข้อความ'}")
            pause_after = max(0.2, min(2.0, float(turn.get("pause_after") or 0.35)))
            speech = f"{speech} [pause:{pause_after:.1f}]"
            self.events.put(("story_progress", {
                "percent": 66 + round(11 * (index - 1) / max(1, len(turns))),
                "stage": "voice",
                "message": f"กำลังสร้างเสียง {speaker} • บท {index}/{len(turns)}",
                "detail": "แยกเสียงตามตัวละครและบันทึก checkpoint ทีละประโยค",
            }))
            checkpoint = dict(voice_checkpoints.get(str(index)) or {})
            resubmit_count = int(checkpoint.get("resubmit_count") or 0)
            external_id = str(checkpoint.get("external_job_id") or "").strip()
            if len(speech) > MAX_TTS_REQUEST_CHARS:
                external_id, output_id, reference_id = render_chunked_voice(
                    client, speech, reference_id, target, scope=f"story:{job_id}:dialogue{revision_suffix}:{index}",
                    options={"language": self.voice_language.get().strip() or "th", "engine": "auto", "silence_sec": 0.0},
                    ffmpeg_path=self.cfg.get("ffmpeg_path"), cancel_event=cancel_event,
                    on_progress=lambda message: self.events.put(("story_progress", {
                        "percent": 70, "stage": "voice", "message": f"บท {index} • {message}", "detail": speaker})),
                    on_checkpoint=lambda remote, ref: self.stories.save_dialogue_voice_checkpoint(
                        job_id, index, speaker=speaker, reference_id=ref, external_job_id=remote, status="queued"),
                    legacy_job_id=external_id, legacy_output_id=str(checkpoint.get("output_id") or ""),
                )
                self.stories.save_dialogue_voice_checkpoint(
                    job_id, index, speaker=speaker, reference_id=reference_id,
                    external_job_id=external_id, output_id=output_id, status="ready", path=str(target.relative_to(folder)))
                external_ids.append(external_id)
                output_ids.append(str(output_id))
                continue
            if external_id:
                self.events.put(("story_progress", {
                    "percent": 66 + round(11 * (index - 1) / max(1, len(turns))),
                    "stage": "voice",
                    "message": f"กำลังทำเสียง {speaker} ต่อจากคิวเดิม • บท {index}/{len(turns)}",
                    "detail": "พบ Job เสียงที่ส่งแล้ว • รอผลเดิมโดยไม่หักเครดิตซ้ำ",
                }))
            else:
                queued = client.synthesize(
                    speech, reference_id, language=self.voice_language.get().strip() or "th",
                    emotion_id=CLIP_VOICE_EMOTION, engine="auto", speed=CLIP_VOICE_SPEED, silence_sec=0.0,
                    idempotency_key=f"story:{job_id}:dialogue{revision_suffix}:{index}:v{resubmit_count + 1}",
                )
                external_id = str(queued["job_id"])
                self.stories.save_dialogue_voice_checkpoint(
                    job_id, index, speaker=speaker, reference_id=reference_id,
                    external_job_id=external_id, status="queued",
                )
            try:
                _, output_id = client.wait_until_done(external_id, cancel_event=cancel_event)
            except ExternalTtsError as exc:
                if not exc.retryable or resubmit_count >= 1:
                    raise
                failed_external_id = external_id
                resubmit_count += 1
                self.stories.save_dialogue_voice_checkpoint(
                    job_id, index, speaker=speaker, reference_id=reference_id,
                    external_job_id="", output_id="", status="resubmitting",
                    resubmit_count=resubmit_count, last_error=str(exc),
                    replaced_external_job_id=failed_external_id,
                )
                queued = client.synthesize(
                    speech, reference_id, language=self.voice_language.get().strip() or "th",
                    emotion_id=CLIP_VOICE_EMOTION, engine="auto", speed=CLIP_VOICE_SPEED, silence_sec=0.0,
                    idempotency_key=f"story:{job_id}:dialogue{revision_suffix}:{index}:v{resubmit_count + 1}",
                )
                external_id = str(queued["job_id"])
                self.stories.save_dialogue_voice_checkpoint(
                    job_id, index, speaker=speaker, reference_id=reference_id,
                    external_job_id=external_id, output_id="", status="queued",
                    resubmit_count=resubmit_count, last_error="",
                    replaced_external_job_id=failed_external_id,
                )
                _, output_id = client.wait_until_done(external_id, cancel_event=cancel_event)
            self.stories.save_dialogue_voice_checkpoint(
                job_id, index, speaker=speaker, reference_id=reference_id,
                external_job_id=external_id, output_id=output_id, status="completed",
            )
            client.download(output_id, target, "mp3", cancel_event=cancel_event)
            self.stories.save_dialogue_voice_checkpoint(
                job_id, index, speaker=speaker, reference_id=reference_id,
                external_job_id=external_id, output_id=output_id, status="ready",
                path=str(target.relative_to(folder)),
            )
            external_ids.append(external_id)
            output_ids.append(str(output_id))
        check_cancelled(cancel_event)
        concat_file = segment_folder / "concat.txt"
        concat_file.write_text(
            "\n".join("file '" + path.resolve().as_posix().replace("'", "'\\''") + "'" for path in segment_paths),
            encoding="utf-8",
        )
        ffmpeg = Path(str(self.cfg.get("ffmpeg_path") or ""))
        if not ffmpeg.is_file():
            found = shutil.which("ffmpeg")
            if not found:
                raise FileNotFoundError("ไม่พบ FFmpeg สำหรับรวมเสียงตัวละคร")
            ffmpeg = Path(found)
        voice = folder / "audio" / "narration.mp3"
        temporary = voice.with_suffix(".rendering.mp3")
        command = [
            str(ffmpeg), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c:a", "libmp3lame", "-q:a", "2", str(temporary),
        ]
        result = run_cancellable(command, cancel_event=cancel_event, timeout=1800)
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size < 1024:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("รวมเสียงตัวละครไม่สำเร็จ: " + (result.stderr or "ไม่ทราบสาเหตุ")[-1200:])
        temporary.replace(voice)
        self.stories.save_voice(
            job_id, voice, "dialogue:" + ",".join(external_ids),
            "dialogue:" + ",".join(output_ids), default_reference_id,
        )
        self.events.put(("story_progress", {
            "percent": 78, "stage": "voice", "message": "รวมเสียงตัวละครเสร็จแล้ว",
            "detail": f"เสียงสนทนา {len(turns)} ช่วง • ใช้เสียงแยก {len(set(character_refs.values()))} ตัวละคร",
        }))
        return voice

    def _collect_story_meta_clips(self, job_id, cancel_event, only_scene=None, _planned_route=False):
        from core.meta_video import MetaVideoManager
        from core.scene_video_plan import enabled as planned_video
        manager = MetaVideoManager(self.stories)
        job = self.stories.get(job_id)
        if only_scene is None:
            from core.meta_scene_sequence import assert_all_ready
            assert_all_ready(self.stories, job)
        clip_paths = []
        for index in ([only_scene] if only_scene is not None else range(1, int(job['scene_count']) + 1)):
            check_cancelled(cancel_event)
            if not _planned_route and planned_video(self.stories.get(job_id)):
                from core.scene_video_worker import collect_scene
                clip_paths.append(collect_scene(self, job_id, index, cancel_event))
                continue
            from core.scene_video_plan import package_binding
            planned_binding = package_binding(self.stories.get(job_id), index)
            request = manager.begin(job_id, index)
            command = None
            if request['stage'] != 'stored':
                _extension, compatible = self._compatible_extension()
                if not compatible:
                    raise ValueError(f'Meta AI ต้องใช้ Extension {self.bridge.REQUIRED_EXTENSION_VERSION} ที่เชื่อมต่อกับโปรแกรม • เก็บฉากเดิมไว้')
                command = self.bridge.queue_extension_command('open_meta_video', job_id, index)
            while True:
                check_cancelled(cancel_event)
                manager.package(job_id, index)
                command_state = self.bridge.extension_command_status(command['id']) if command else None
                if command_state and command_state.get('status') == 'failed':
                    raise ValueError('META_VIDEO_REVIEW • ' + str(command_state.get('error') or 'เปิด Meta ไม่สำเร็จ'))
                receipt = manager.get(job_id, index)
                if receipt.get('stage') == 'stored':
                    break
                if receipt.get('stage') == 'needs_attention':
                    from core.scene_video_worker import retire_meta_terminal, collect_scene
                    if retire_meta_terminal(self, job_id, index, receipt, planned_binding):
                        from core.scene_video_plan import provider_for
                        if provider_for(self.stories.get(job_id), index) != 'meta_ai':
                            clip_paths.append(collect_scene(self, job_id, index, cancel_event))
                            break
                    raise ValueError('META_VIDEO_REVIEW • ' + str(receipt.get('message') or 'ตรวจแท็บ Meta ที่บันทึกไว้'))
                self._queue_story_phase(job_id, cancel_event, 'source_video', {'percent': 60 + int(18 * (index - 1) / int(job['scene_count'])),
                    'stage': 'video', 'message': f'Meta AI • ฉาก {index}/{job["scene_count"]}',
                    'detail': receipt.get('message') or receipt.get('stage', 'รอ Extension')})
                if cancel_event is not None:
                    cancel_event.wait(2)
                else:
                    time.sleep(2)
            if receipt.get('stage') != 'stored':
                continue  # A verified terminal Meta attempt switched at this boundary.
            # Recheck the exact stored receipt, including its bytes. A full
            # Meta-only manifest is not required by a planned mixed job.
            from core.meta_video import digest
            saved = (self.stories.root / job_id / str(receipt.get('path') or '')).resolve()
            if (not saved.is_relative_to((self.stories.root / job_id).resolve()) or not saved.is_file()
                    or digest(saved) != receipt.get('sha256')):
                raise ValueError('ไฟล์ Meta ที่บันทึกไว้เปลี่ยนหรือหายไป')
            clip_paths.append(saved)
        if only_scene is not None or planned_video(self.stories.get(job_id)):
            return clip_paths
        return manager.clips(job_id)

    @story_render
    def _compose_story_media(self, job_id, job, voice, cancel_event):
        self._queue_story_phase(job_id, cancel_event, 'compose', {'percent': 79, 'stage': 'video',
            'message': 'กำลังประกอบคลิปจากไฟล์ที่บันทึกแล้ว', 'detail': 'ใช้เสียงและคำบรรยายตามค่าประจำงาน'})
        folder = self.stories.root / job_id
        job = self.stories.get(job_id)
        saved_job = job
        from core.scene_context_revision import render_story
        job = render_story(folder, job)
        images = [folder / item for item in job["generated_images"]]
        working = working_video_folder(folder)
        final = working / "story_short_final.mp4"
        self.stories.mark_running(job_id, "video")
        frozen = self._creation_settings(job_id)
        render_settings = job.get('render_snapshot') or frozen.get("render") or self._video_render_settings()
        if job.get('long_video'):
            render_settings = {**render_settings, 'width': 1920, 'height': 1080}
        finish_base = {'ffmpeg_path': self.cfg.get('ffmpeg_path', '')} if isinstance(job.get('product_runtime_snapshot'), dict) else self.cfg
        from core.logo_layout import frozen_logo_config
        finish_config = frozen_logo_config({**finish_base, **(job.get("media_finish_config") or {}),
            **(frozen.get("finish_config") or {})}, job.get("media_finish_config"), frozen.get("finish_config"))
        if audio_mode(job) == "flow_original" and (job.get("audio_choices") or {}).get("subtitle"):
            finish_config["native_subtitle_credential"] = self._subtitle_store().load()
        video_generation_mode = str(job.get("video_generation_mode") or "image_motion")
        from core.scene_video_plan import enabled as planned_video, ordered_assets
        if planned_video(job):
            from core.scene_video_worker import provenance
            assets = ordered_assets(folder, saved_job)
            sequential = job.get('scene_pipeline_version') == 1
            if sequential:
                from core.scene_pipeline import ScenePipeline
                clip_paths = ScenePipeline(folder).segments(int(job['scene_count']))
                sound = ({'mode': 'flow_original', 'video_audio_volume': 100, 'allow_silent': True}
                         if audio_mode(job) != 'none' else {'mode': 'none'})
            else:
                from core.story_performance import composition_choices
                clip_paths = [folder / asset['path'] for asset in assets]
                sound = composition_choices(job) if job.get('actor_dialogue') else job.get('audio_choices')
            sources = provenance(assets)
            actual_source_type = sources['source_type']
            self.events.put(('story_progress', {'percent': 88, 'stage': 'video',
                'message': 'คลิปทุกฉากพร้อมแล้ว • รวมตามลำดับจากไฟล์เดิม',
                'detail': f"Flow {sources['flow_clip_count']} • Meta {sources['meta_clip_count']} • ในเครื่อง {sources['flow_fallback_count']} ฉาก"}))
            result = MultiFlowComposer(self.cfg.get('ffmpeg_path', '')).compose(
                clip_paths, final, voice_path='' if sequential else voice,
                width=render_settings['width'], height=render_settings['height'], fps=render_settings['fps'],
                crf=render_settings['crf'], transition_sec=0 if sequential else render_settings['transition_sec'],
                timing_mode=(job.get('render_options') or {}).get('timing_mode', 'voice_fit'),
                tail_seconds=0 if sequential else (job.get('render_options') or {}).get('tail_seconds', .75),
                scene_durations=job.get('scene_durations'), audio_choices=sound, cancel_event=cancel_event)
            plan = {key: str(value) if isinstance(value, Path) else value for key, value in result.items()}
            plan.update(sources)
        elif video_generation_mode == "google_flow":
            # Policy fallback is explicit per scene. Real Flow clips and local
            # motion clips live in separate manifest maps and are never
            # presented as the same source.
            sequential = job.get('scene_pipeline_version') == 1
            if sequential:
                from core.scene_pipeline import ScenePipeline
                clip_paths = ScenePipeline(folder).segments(int(job['scene_count']))
            else:
                clip_paths = self._collect_story_flow_clips(job_id, cancel_event)
            check_cancelled(cancel_event)
            collected_job = self.stories.get(job_id)
            real_flow_count = len(clip_paths) if sequential else len(collected_job.get("flow_clips") or {})
            fallback_scenes = sorted(
                int(index) for index in (collected_job.get("flow_fallback_clips") or {})
                if str(index).isdigit()
            )
            fallback_count = len(fallback_scenes)
            actual_source_type = (
                "google_flow_story_hybrid_fallback" if fallback_count
                else "google_flow_story_composite"
            )
            self.stories.mark_running(job_id, "video")
            self.events.put(("story_progress", {
                "percent": 88, "stage": "video",
                "message": (
                    "คลิปทุกฉากพร้อมแล้ว กำลังประกอบเรื่อง"
                    if fallback_count else "คลิป Google Flow ครบแล้ว กำลังประกอบเรื่อง"
                ),
                "detail": (
                    f"Google Flow จริง {real_flow_count}/{job.get('scene_count')} ฉาก • "
                    f"ภาพเคลื่อนไหวสำรองในเครื่อง {fallback_count} ฉาก ({', '.join(map(str, fallback_scenes))}) • พร้อมเสียงพากย์"
                    if fallback_count else
                    f"เรียงคลิป Google Flow จริง {real_flow_count}/{job.get('scene_count')} ฉากตามลำดับ พร้อมเสียงพากย์"
                ),
            }))
            if (job.get('long_video') or {}).get('version') == 2:
                from core.long_video_render import LongFlowBatchComposer
                def flow_chapter_progress(number, total, start, end, reused):
                    self.events.put(('story_progress', {'percent': 80 + round(7 * number / total),
                        'stage': 'video', 'message': f'รวมคลิป Flow ชุด {number}/{total} • ฉาก {start}–{end}',
                        'detail': 'ใช้ชุดที่บันทึกไว้ ไม่สร้างคลิป Flow ซ้ำ' if reused else 'บันทึกวิดีโอช่วงนี้ก่อนทำชุดถัดไป'}))
                flow_result = LongFlowBatchComposer(self.cfg.get('ffmpeg_path', '')).compose(
                    clip_paths, final, job.get('scene_durations'), voice,
                    target_seconds=job['long_video']['duration_seconds'],
                    width=render_settings['width'], height=render_settings['height'], fps=render_settings['fps'],
                    crf=render_settings['crf'], transition_sec=render_settings['transition_sec'],
                    audio_choices=job.get('audio_choices'), cancel_event=cancel_event,
                    source_audio_version=job.get('long_source_audio_version', 0),
                    progress=flow_chapter_progress)
            else:
                flow_result = MultiFlowComposer(self.cfg.get("ffmpeg_path", "")).compose(
                    clip_paths, final, voice_path=voice,
                    width=render_settings["width"], height=render_settings["height"], fps=render_settings["fps"],
                    crf=render_settings["crf"], transition_sec=render_settings["transition_sec"],
                    timing_mode=(job.get("render_options") or {}).get("timing_mode", "voice_fit"),
                    tail_seconds=(job.get("render_options") or {}).get("tail_seconds", 0.75),
                    scene_durations=job.get("scene_durations"),
                    extend_mode="loop" if job.get("long_video") else "smooth",
                    audio_choices=({'mode':'flow_original','video_audio_volume':100,'allow_silent':True}
                        if sequential and audio_mode(job) != 'none' else job.get("audio_choices")), cancel_event=cancel_event,
                )
            self.events.put(("log", f"{job_id} • VIDEO TIMING • เสียง {flow_result.get('voice_duration', 0):.2f} วิ • "
                                f"ภาพต้นฉบับ {flow_result.get('source_duration', 0):.2f} วิ • "
                                f"ผลลัพธ์ {flow_result.get('duration', 0):.2f} วิ • จัดเวลาครบทุกฉาก"))
            plan = {
                key: (str(value) if isinstance(value, Path) else value)
                for key, value in flow_result.items()
            }
            plan.update({
                "source_type": actual_source_type,
                "flow_clip_count": real_flow_count,
                "flow_fallback_count": fallback_count,
                "flow_fallback_scenes": fallback_scenes,
                "scene_source_count": len(clip_paths),
            })
        elif video_generation_mode == 'meta_ai':
            from core.story_performance import composition_choices
            clip_paths = self._collect_story_meta_clips(job_id, cancel_event)
            actual_source_type = 'meta_ai_story_composite'
            self.events.put(('story_progress', {'percent': 88, 'stage': 'video',
                'message': 'คลิป Meta AI ครบแล้ว กำลังประกอบเรื่อง'}))
            meta_sound = (composition_choices(job) if job.get('actor_dialogue')
                          else audio_choices(job.get('audio_choices') or {'mode': 'api'}, 'meta_ai'))
            if job.get('long_video'):
                from core.long_video_render import LongMetaBatchComposer
                def meta_chapter_progress(number, total, start, end, reused):
                    self.events.put(('story_progress', {'percent': 80 + round(7 * number / total),
                        'stage': 'video', 'message': f'รวมคลิป Meta ชุด {number}/{total} • ฉาก {start}–{end}',
                        'detail': 'ใช้ชุดที่บันทึกไว้ ไม่สร้างคลิป Meta ซ้ำ' if reused else 'บันทึกวิดีโอช่วงนี้ก่อนทำชุดถัดไป'}))
                result = LongMetaBatchComposer(self.cfg.get('ffmpeg_path', '')).compose(
                    clip_paths, final, job.get('scene_durations'), voice,
                    target_seconds=job['long_video']['duration_seconds'],
                    width=render_settings['width'], height=render_settings['height'], fps=render_settings['fps'],
                    crf=render_settings['crf'], transition_sec=render_settings['transition_sec'],
                    audio_choices=meta_sound, cancel_event=cancel_event,
                    source_audio_version=job.get('long_source_audio_version', 0),
                    progress=meta_chapter_progress)
            else:
                result = MultiFlowComposer(self.cfg.get('ffmpeg_path', '')).compose(
                    clip_paths, final, voice_path=voice, width=render_settings['width'], height=render_settings['height'],
                    fps=render_settings['fps'], crf=render_settings['crf'], transition_sec=render_settings['transition_sec'],
                    timing_mode=(job.get('render_options') or {}).get('timing_mode', 'voice_fit'),
                    tail_seconds=(job.get('render_options') or {}).get('tail_seconds', .75),
                    scene_durations=job.get('scene_durations'), audio_choices=meta_sound,
                    cancel_event=cancel_event)
            plan = {key: str(value) if isinstance(value, Path) else value for key, value in result.items()}
            plan.update(source_type=actual_source_type, meta_clip_count=len(clip_paths), scene_source_count=len(clip_paths))
        else:
            actual_source_type = "story_image_sequence"
            self.events.put(("story_progress", {
                "percent": 80,
                "stage": "video",
                "message": "กำลังประกอบภาพทีละชุด 10 ฉาก" if (job.get('long_video') or {}).get('version') == 2 else "กำลังประกอบภาพทุกฉากเป็นวิดีโอ",
                "detail": f"ใช้ภาพจริง {len(images)}/{job.get('scene_count')} ฉาก พร้อมเสียงพากย์",
            }))
            if (job.get('long_video') or {}).get('version') == 2:
                from core.long_video_render import LongVideoBatchComposer
                def chapter_progress(number, total, start, end, reused):
                    self.events.put(('story_progress', {'percent': 80 + round(7 * number / total),
                        'stage': 'video', 'message': f'ประกอบชุด {number}/{total} • ภาพ {start}–{end}',
                        'detail': 'ใช้ไฟล์ชุดที่บันทึกไว้ ไม่เรนเดอร์ซ้ำ' if reused else 'บันทึกไฟล์ช่วงนี้ก่อนทำชุดถัดไป'}))
                plan = LongVideoBatchComposer(self.cfg.get('ffmpeg_path', '')).compose(
                    images, final, job.get('scene_durations'), voice,
                    target_seconds=job['long_video']['duration_seconds'],
                    width=render_settings['width'], height=render_settings['height'], fps=render_settings['fps'],
                    crf=render_settings['crf'], motion_strength=render_settings['motion_strength'],
                    transition_sec=render_settings['transition_sec'], cancel_event=cancel_event,
                    progress=chapter_progress)
            else:
                plan = StoryVideoComposer(self.cfg.get("ffmpeg_path", "")).compose(
                    images, final, job.get("scene_durations"), voice,
                    width=render_settings["width"], height=render_settings["height"], fps=render_settings["fps"],
                    crf=render_settings["crf"], motion_strength=render_settings["motion_strength"],
                    transition_sec=render_settings["transition_sec"], cancel_event=cancel_event,
                )
            plan["source_type"] = actual_source_type
        footage_paths = [folder / value for value in (job.get("source_footage") or [])]
        if job.get("job_type") == "drama_episode" and footage_paths:
            self.events.put(("story_progress", {"percent": 86, "stage": "video", "message": "กำลังแทรกฟุตเทจจริง", "detail": f"จัดวางฟุตเทจเคลื่อนไหว {len(footage_paths)} ไฟล์โดยคงเสียงพากย์เดิม"}))
            mixed_target = working / "drama_with_footage.mp4"
            final, footage_plan = DramaFootageMixer(self.cfg.get("ffmpeg_path", "")).mix(
                final, footage_paths, mixed_target, duration=plan.get("duration"),
                width=render_settings["width"], height=render_settings["height"], fps=render_settings["fps"],
                crf=render_settings["crf"], cancel_event=cancel_event,
            )
            plan.update(footage_plan)
        check_cancelled(cancel_event)
        self.stories.mark_running(job_id, "finishing")
        from core.render_backend import render_phase
        render_phase('finish')
        self._queue_story_phase(job_id, cancel_event, 'finish', {"percent": 88, "stage": "finishing", "message": "วิดีโอหลักเสร็จแล้ว กำลังเก็บรายละเอียด", "detail": "ใส่ซับ โลโก้ เพลง และเสียงประกอบตามค่าที่บันทึกไว้"})
        complete, finish_plan = finish_story_media(
            ROOT, self.stories, job_id, final, finish_config, cancel_event=cancel_event,
            progress=lambda percent, stage, message: self._queue_story_phase(job_id, cancel_event, 'finish', {"percent": percent, "stage": stage, "message": message, "detail": "เสร็จจริงทีละขั้นและตรวจไฟล์ก่อนเดินหน้าต่อ"}),
        )
        check_cancelled(cancel_event)
        plan.update(finish_plan)
        # finish_story_media reports what it processed; retain the acquisition
        # source so the library/result popup never claims fallback is Flow.
        plan["source_type"] = actual_source_type
        if (job.get('ai_cover_options') or {}).get('enabled') is True:
            self._queue_story_phase(job_id, cancel_event, 'cover', {"percent": 97, "stage": "cover", "message": "กำลังบันทึกวิดีโอก่อนสร้างปก AI", "detail": "ใช้ AI เดิม พร้อมรูปอ้างอิงและชื่อคลิป • ไม่ทำปกแปะข้อความในเครื่อง"})
        elif job.get("job_type") == "drama_episode" and images:
            self.events.put(("story_progress", {"percent": 99, "stage": "finishing", "message": "กำลังสร้างปกละคร Shorts", "detail": "เรนเดอร์ปกแนวตั้ง 9:16 จากภาพฉากจริงและธีมประจำซีรีส์"}))
        elif images:
            self.events.put(("story_progress", {"percent": 99, "stage": "finishing", "message": "กำลังสร้างปก Story Shorts", "detail": "เรนเดอร์ปกแนวตั้ง 9:16 จากภาพฉากจริงพร้อมชื่อเรื่อง"}))
        # StoryManager owns the completion gate: it checkpoints the rendered
        # video as waiting_cover, creates a real 9:16 cover, and only then marks
        # the Job complete. This prevents the library from exposing a half-ready
        # video when cover rendering fails or the app exits between both steps.
        saved = self.stories.save_video(job_id, complete, plan)
        from ui.ai_cover import finish_ai_cover
        finish_ai_cover(self, job_id, cancel_event, lambda message: self.events.put(('story_progress',
            {'percent':97,'stage':'cover','message':message,'detail':'วิดีโอบันทึกแล้ว • ไม่สร้างฉากซ้ำ'})))
        saved = self.stories.get(job_id)
        check_cancelled(cancel_event)
        self.events.put(("story_ready", {"job_id": job_id, "cancel_event": cancel_event, "value": (saved, complete, plan)}))

    @uses_job_files(lambda app, payload: payload)
    def _start_story_scene_worker(self, payload):
        job_id, index, revision = payload['job_id'], payload['index'], payload['revision']
        key = (job_id, index)
        prior = self._story_scene_threads.get(key)
        if prior and prior.is_alive():
            return
        if self._story_pipeline_job_id and self._story_pipeline_job_id != job_id:
            return
        api_key = self.voice_api_key.get().strip()
        frozen = self._creation_settings(job_id)
        reference_id = str(frozen.get('voice_reference_id', self.voice_reference_id.get().strip()) or '')
        reference_file = str(frozen.get('voice_reference_file', self.voice_reference_file.get().strip()) or '')
        saved_job = self.stories.get(job_id)
        reference_id = str(saved_job.get('primary_voice_reference_id') or reference_id)
        reference_file = str(saved_job.get('primary_voice_reference_file') or reference_file)
        render = saved_job.get('render_snapshot') or frozen.get('render') or self._video_render_settings()
        if self._story_cancel_event is None:
            self._story_cancel_event = threading.Event()
        self._story_pipeline_job_id = job_id
        cancel_event = self._story_cancel_event
        worker = guarded_thread(self, job_id, self._run_story_scene_worker,
            args=(payload, api_key, reference_id, reference_file, render, cancel_event), daemon=True)
        self._story_scene_threads[key] = worker

    def _run_story_scene_worker(self, payload, api_key, reference_id, reference_file, render, cancel_event):
        from core.scene_pipeline import ScenePipeline
        from core.scene_voice import render_scene_asset
        from core.scene_context_revision import render_story
        job_id, index, revision = payload['job_id'], payload['index'], payload['revision']
        folder = self.stories.root / job_id
        pipeline = ScenePipeline(folder)
        def progress(message):
            check_cancelled(cancel_event)
            pipeline.update(index, revision, message=message)
            self.events.put(('story_progress', {'stage':'voice','percent':15+round(70*index/max(1,int(self.stories.get(job_id)['scene_count']))),
                'message':f'ฉาก {index} • {message}','detail':'บันทึกรายฉาก ก่อนสร้างภาพฉากถัดไป'}))
        try:
            check_cancelled(cancel_event)
            if payload.get('desktop_saved_resume') or payload.get('desktop_plan_render'):
                if (self._story_pipeline_job_id != job_id or cancel_event is not self._story_cancel_event
                        or pipeline.get(index).get('run_id') != payload['run_id']):
                    raise ValueError('รอบทำต่อจากสื่อที่บันทึกเปลี่ยนแล้ว')
            else:
                expected = self.bridge._extension_runs.get(('ai',job_id,0)) or {}
                if expected.get('run_id') != payload['run_id']:
                    raise ValueError('รอบงานรายฉากเปลี่ยนแล้ว')
            if pipeline.get(index).get('phase') == 'complete':
                return
            from core.scene_video_plan import enabled as planned_video, effective_job
            planned = planned_video(self.stories.get(job_id))
            pipeline.update(index,revision,phase='video',message=(
                'กำลังเริ่มฉากที่ล้มเหลวใหม่ • ให้ AI เตรียมภาพและพรอมต์ใหม่'
                if payload.get('desktop_scene_rebuild') else 'กำลังเตรียมวิดีโอตามแผนรายฉาก • เก็บฉากเดิมไว้'
                if planned else 'กำลังเตรียม Google Flow • ภาพและพรอมต์พร้อมแล้ว'))
            if planned:
                from core.scene_video_worker import collect_scene
                clips = [collect_scene(self, job_id, index, cancel_event)]
            else:
                clips = self._collect_story_flow_clips(job_id,cancel_event,only_scene=index)
            job = render_story(folder,self.stories.get(job_id))
            if planned:
                job = effective_job(job, index)
            if job.get('long_video'):
                render = {**render,'width':1920,'height':1080}
            pipeline.update(index,revision,phase='voice',message='วิดีโอผ่านแล้ว กำลังทำเสียงของฉากนี้')
            client = None
            if audio_mode(job) == 'api':
                if not api_key:
                    raise ValueError('ยังไม่มี API Key เสียง')
                client = ExternalTtsClient(api_key,self.cfg.get('voice_api_base_url','https://www.catfufu.com'))
                reference_id = str(job.get('scene_voice_reference_id') or reference_id)
                if not reference_id:
                    reference_id = str(client.upload_reference(reference_file)['reference_id'])
                    current = self.stories.get(job_id)
                    current['scene_voice_reference_id'] = reference_id
                    self.stories._save(current)
            result = render_scene_asset(folder,job,index,clips[0],client,reference_id,render,
                self.cfg.get('ffmpeg_path',''),cancel_event,progress)
            check_cancelled(cancel_event)
            pipeline.update(index,revision,phase='complete',message='ภาพ วิดีโอ และเสียงฉากนี้พร้อมแล้ว',**result)
            if planned:
                from core.scene_video_plan import finish_scene
                finish_scene(self.stories, job_id, index)
            if payload.get('desktop_saved_resume'):
                self.events.put(('story_saved_scene_done', {**payload, 'cancel_event': cancel_event}))
        except Exception as error:
            if payload.get('desktop_saved_resume') and pipeline.get(index).get('run_id') != payload['run_id']:
                return  # An old direct-resume worker cannot fail its successor.
            pipeline.update(index,revision,phase='cancelled' if cancel_event and cancel_event.is_set() else 'error',error=str(error))
            if payload.get('desktop_saved_resume'):
                self.events.put(('story_error', {'job_id': job_id, 'cancel_event': cancel_event, 'value': str(error)}))

    def _collect_story_flow_clips(self, job_id, cancel_event, only_scene=None, fresh_scene_attempt="", _planned_route=False):
        """Create/download only missing Story scenes and retain every completed checkpoint."""
        folder = self.stories.root / job_id
        job = self.stories.get(job_id)
        total = int(job.get("scene_count") or 0)
        if total < 1 or (total == 1 and job.get('flow_smoke_test') is not True):
            raise ValueError("FLOW_SCENE_COUNT_INVALID • งานปกติต้องมีอย่างน้อย 2 ฉาก; โหมดทดสอบใช้ 1 ฉากได้")
        self.stories.mark_running(job_id, "google_flow")
        clip_paths = []

        for shot_index in ([only_scene] if only_scene is not None else range(1, total + 1)):
            check_cancelled(cancel_event)
            current = self.stories.get(job_id)
            from core.scene_video_plan import enabled as planned_video
            if not _planned_route and not fresh_scene_attempt and planned_video(current):
                from core.scene_video_worker import collect_scene
                clip_paths.append(collect_scene(self, job_id, shot_index, cancel_event))
                continue
            from core.scene_video_plan import package_binding
            planned_binding = package_binding(current, shot_index)
            relative = str((current.get("flow_clips") or {}).get(str(shot_index)) or "")
            fallback_relative = str((current.get("flow_fallback_clips") or {}).get(str(shot_index)) or "")
            existing = folder / relative
            if relative and existing.is_file() and existing.stat().st_size > 1024:
                clip_paths.append(existing)
                self.events.put(("story_progress", {
                    "percent": 79 + round(8 * shot_index / total), "stage": "video",
                    "message": f"ใช้คลิป Google Flow เดิม • ฉาก {shot_index}/{total}",
                    "detail": "Checkpoint นี้เสร็จแล้ว จึงไม่สร้างซ้ำและไม่ใช้เครดิตเพิ่ม",
                }))
                continue
            # Historical fallback files remain available in the library, but are
            # not real Flow output. Do not reopen old denied requests on resume.
            attachment_history = StoryManager._authenticated_flow_attachment_history(current, shot_index)
            policy_history = list((current.get("flow_policy_failure_history") or {}).get(str(shot_index)) or [])
            if fallback_relative or attachment_history or policy_history:
                raise FlowVideoReviewError(shot_index, "พบภาพสำรองหรือประวัติฉากเดิมที่ยังไม่มีคลิป Flow")

            accepted = False
            reuse_remote_result = False
            attempt = 1
            while attempt <= 3:
                check_cancelled(cancel_event)
                self.events.put(("story_progress", {
                    "percent": 79 + round(8 * (shot_index - 1) / total), "stage": "video",
                    "message": f"Google Flow • กำลังทำฉาก {shot_index}/{total}",
                    "detail": f"ส่งรูปฉากนี้เข้า Flow ทีละรูป • รอบ {attempt}/3 • ฉากที่เสร็จแล้วจะไม่ทำซ้ำ",
                }))
                self._ensure_flow_extension(job_id, shot_index, cancel_event=cancel_event)
                if fresh_scene_attempt:
                    clients = self.bridge.extension_status().get('clients') or []
                    if not any(str(client.get('version') or '') == self.bridge.REQUIRED_EXTENSION_VERSION
                               and client.get('speech_retry_protocol') == 1 for client in clients):
                        raise RuntimeError('FLOW_SPEECH_RETRY_UPDATE_REQUIRED • กรุณาโหลด SmartFlow Extension รุ่นปัจจุบันซ้ำก่อนทำฉากเสียงซ้ำต่อ')
                remote_checkpoint = False
                from core.atomic_json import AtomicJsonFile
                manual_repair = AtomicJsonFile(folder / 'prompts' / 'flow_manual_resume.json').read({})
                if fresh_scene_attempt:
                    # Speech-quality repair is a new, explicitly owned request.
                    # Inspecting the old project would rediscover the rejected
                    # playable result and falsely mark the retry complete.
                    remote_checkpoint = False
                elif attempt == 1 and manual_repair.get('index') == shot_index:
                    self.bridge.clear_flow_progress(job_id, shot_index)
                    self.bridge.queue_extension_command('resume_flow_workspace', job_id, shot_index)
                    remote_checkpoint = True
                elif attempt == 1 or reuse_remote_result:
                    self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                    inspect_deadline = time.monotonic() + (20 if reuse_remote_result else 12)
                    while time.monotonic() < inspect_deadline:
                        check_cancelled(cancel_event)
                        status = self.bridge.extension_status()
                        client = next((item for item in status.get("clients") or []
                            if str(item.get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION
                            and item.get("flow_job_id") == job_id and int(item.get("flow_shot_index") or 0) == shot_index), None)
                        if client:
                            step = str(client.get("flow_step") or "")
                            if str(client.get("flow_failure_code") or "") in {"FLOW_REPAIR_REVIEW", "FLOW_SEND_REVIEW", "FLOW_VIDEO_SETTINGS_REVIEW"}:
                                remote_checkpoint = True
                                break
                            if (str(client.get("flow_failure_code") or "") == "FLOW_POLICY_BLOCKED"
                                    and client.get("flow_run_id") and client.get("flow_failure_card_fingerprint")):
                                # Preserve the terminal result for _wait_flow_step;
                                # never clear it and open this rejected scene again.
                                remote_checkpoint = True
                                break
                            if step in {"generation_complete", "generation_in_progress", "awaiting_credit_approval", "awaiting_rights_confirmation"}:
                                remote_checkpoint = True
                                break
                            if step in {"checkpoint_missing", "checkpoint_mismatch", "generation_failed", "submission_blocked", "generate_button_missing", "error"}:
                                break
                        if cancel_event is not None and cancel_event.wait(2):
                            check_cancelled(cancel_event)
                if reuse_remote_result:
                    remote_checkpoint = True
                if not remote_checkpoint:
                    self.bridge.clear_flow_progress(job_id, shot_index)
                    fresh_run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}" if fresh_scene_attempt and attempt == 1 else ""
                    command = self.bridge.queue_extension_command("open_flow", job_id, shot_index, run_id=fresh_run_id)
                generation_ready = False
                try:
                    self._wait_flow_step(job_id, shot_index, cancel_event=cancel_event, total_shots=total,
                                         expected_run_id=command['run_id'] if fresh_scene_attempt and not remote_checkpoint else "",
                                         **({'scene_video_plan': planned_binding} if planned_binding else {}))
                    generation_ready = True
                    download_started_at = time.time()
                    self.bridge.queue_extension_command("download_flow_result", job_id, shot_index)
                    downloaded = self._wait_download(
                        job_id, shot_index, cancel_event=cancel_event,
                        started_at=download_started_at, total_shots=total,
                        expected_run_id=command['run_id'] if fresh_scene_attempt and not remote_checkpoint else "",
                        **({'scene_video_plan': planned_binding} if planned_binding else {}),
                    )
                    if planned_video(self.stories.get(job_id)):
                        from core.scene_video_worker import download_receipt
                        download_sha = download_receipt(self, job_id, shot_index, planned_binding, downloaded) if planned_binding else None
                        checkpoint = self.stories.attach_flow_clip(job_id, shot_index, downloaded,
                            scene_video_plan=planned_binding, expected_sha256=download_sha)
                    else:
                        checkpoint = self.stories.attach_flow_clip(job_id, shot_index, downloaded)
                    saved = folder / str((checkpoint.get("flow_clips") or {}).get(str(shot_index)) or "")
                    self._close_saved_flow_tab(job_id, shot_index, saved)
                    clip_paths.append(saved)
                    accepted = True
                    self.events.put(("story_progress", {
                        "percent": 79 + round(8 * shot_index / total), "stage": "video",
                        "message": f"ดาวน์โหลดฉาก {shot_index}/{total} สำเร็จ",
                        "detail": "บันทึก Checkpoint แล้ว • หาก Chrome หลุดจะเริ่มต่อจากฉากถัดไป",
                    }))
                    break
                except OperationCancelled:
                    raise
                except Exception as exc:
                    failure_text = str(exc)
                    terminal_proof = getattr(exc, 'scene_video_terminal_proof', None)
                    if terminal_proof and planned_video(self.stories.get(job_id)):
                        from core.scene_video_plan import retire_terminal, provider_for
                        retire_terminal(self.stories, job_id, shot_index, terminal_proof,
                                        scene_video_plan=planned_binding)
                        if provider_for(self.stories.get(job_id), shot_index) != 'google_flow':
                            from core.scene_video_worker import collect_scene
                            clip_paths.append(collect_scene(self, job_id, shot_index, cancel_event))
                            accepted = True
                            break
                    if getattr(exc, "flow_retry_forbidden", False):
                        raise
                    if planned_video(self.stories.get(job_id)):
                        from core.scene_video_worker import SceneVideoReviewError
                        raise SceneVideoReviewError(
                            'SCENE_VIDEO_REVIEW • เก็บคำขอเดิมไว้ • ไม่หยุดหรือส่งซ้ำจากผลที่ยังไม่ยืนยัน • ' + failure_text) from exc
                    if (getattr(exc, "flow_attachment_terminal", False)
                            or getattr(exc, "flow_policy_terminal", False)):
                        raise FlowVideoReviewError(shot_index, failure_text) from exc
                    if any(marker in failure_text for marker in (
                        "ลองแนบรูปแล้วหนึ่งครั้ง",
                        "หยุดเพื่อป้องกันการอัปโหลดรูปซ้ำ",
                        "หยุดอย่างปลอดภัยหลังลองแนบรูปหนึ่งครั้ง",
                        "เปิดโหมดแก้ภาพนิ่งแทนโหมดสร้างวิดีโอ",
                    )):
                        raise RuntimeError(
                            f"Google Flow ฉาก {shot_index}/{total} หยุดอย่างปลอดภัย • "
                            "ไม่เปิดโปรเจกต์ใหม่และไม่อัปโหลดรูปซ้ำ • "
                            f"{failure_text}"
                        ) from exc
                    if attempt >= 3:
                        raise RuntimeError(f"Google Flow ฉาก {shot_index}/{total} ไม่สำเร็จหลังลอง 3 รอบ • {exc}") from exc
                    reuse_remote_result = generation_ready
                    self._write_console(
                        f"{job_id} • STORY FLOW RETRY • scene {shot_index}/{total} • attempt {attempt}/3 • {exc}",
                        "error",
                    )
                    if not reuse_remote_result:
                        self.bridge.queue_extension_command("stop_flow_generation", job_id, shot_index)
                    self.bridge.clear_flow_progress(job_id, shot_index)
                    if cancel_event is not None and cancel_event.wait(3):
                        check_cancelled(cancel_event)
                    attempt += 1
            if not accepted:
                raise RuntimeError(f"Google Flow ไม่ได้ส่งคลิปฉาก {shot_index}/{total}")
        return clip_paths

    def _build_voice(self):
        page = self._page("voice")
        self._heading(page, "AI Voice และบทพูดสินค้า", "AI Web สร้างบทพูด → catfufu.com สร้างเสียง → บันทึกเข้า Product Job")

        selector = self._panel(page, fill="x", pady=(0, 12))
        tk.Label(selector, text="Product Job", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 10)).pack(side="left", padx=(15, 8), pady=12)
        self.voice_job_combo = ttk.Combobox(selector, textvariable=self.voice_job_id, state="readonly", width=25)
        self.voice_job_combo.pack(side="left", padx=(0, 8), pady=10)
        self.voice_job_combo.bind("<<ComboboxSelected>>", lambda event: self._load_voice_job())
        tk.Label(selector, textvariable=self.voice_status, bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI", 9)).pack(side="left", padx=8)
        ttk.Button(selector, text="เปิดโฟลเดอร์เสียง", style="Ghost.TButton", command=self._open_voice_folder).pack(side="right", padx=(5, 12), pady=7)

        content = tk.Frame(page, bg=COLORS["bg"]); content.pack(fill="both", expand=True)
        _settings_viewport, settings = self._scroll_panel(content, width=365, side="left", fill="y")
        tk.Label(settings, text="เชื่อมต่อ AI VOICE", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=16, pady=(10, 4))
        tk.Label(settings, text="API Key เก็บใน Windows Credential Manager และไม่แสดงใน Log", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=16, pady=(0, 6))
        key_row = tk.Frame(settings, bg=COLORS["panel"]); key_row.pack(fill="x", padx=16)
        self.voice_key_entry = tk.Entry(key_row, textvariable=self.voice_api_key, show="•", bg="#080D1E", fg=COLORS["text"], insertbackground="white", relief="flat", font=("Segoe UI", 10))
        self.voice_key_entry.pack(side="left", fill="x", expand=True, ipady=6)
        ttk.Button(key_row, text="บันทึกและเชื่อมต่อ", style="Primary.TButton", command=self._save_voice_key).pack(side="left", padx=(6, 0))
        key_actions = tk.Frame(settings, bg=COLORS["panel"]); key_actions.pack(fill="x", padx=16, pady=(5, 3))
        ttk.Checkbutton(key_actions, text="แสดง API Key", variable=self.voice_show_key, style="Dark.TCheckbutton", command=self._toggle_voice_key).pack(side="left")
        tk.Label(key_actions, textvariable=self.voice_key_saved, bg=COLORS["panel"], fg=COLORS["green"], font=("Segoe UI", 8)).pack(side="left", padx=8)
        disconnect_row = tk.Frame(settings, bg=COLORS["panel"])
        disconnect_row.pack(fill="x", padx=16, pady=(0, 6))
        tk.Button(disconnect_row, text="ยกเลิกการเชื่อมต่อ", command=self._delete_voice_key, relief="flat", bd=0, bg=COLORS["panel"], fg=COLORS["danger"], activebackground=COLORS["panel"], activeforeground="#FF8BA0", font=("Segoe UI", 8), cursor="hand2").pack(side="right")

        voice_catalog_head = tk.Frame(settings, bg=COLORS["panel"]); voice_catalog_head.pack(fill="x", padx=16, pady=(0, 5))
        tk.Label(voice_catalog_head, text="เลือกเสียงจากระบบ API", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Button(voice_catalog_head, text="↻ โหลดเสียง", command=self._refresh_voice_catalog, relief="flat", bd=0, bg=COLORS["panel"], fg=COLORS["cyan"], activebackground=COLORS["panel"], activeforeground="#8DEBFA", font=("Segoe UI Semibold", 8), cursor="hand2").pack(side="right")
        self.voice_catalog_combo = ttk.Combobox(settings, textvariable=self.voice_catalog_choice, state="readonly", style="Dark.TCombobox")
        self.voice_catalog_combo.pack(fill="x", padx=16, ipady=2)
        self.voice_catalog_combo.bind("<<ComboboxSelected>>", lambda event: self._select_catalog_voice())
        tk.Label(settings, textvariable=self.voice_catalog_info, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=330, justify="left").pack(anchor="w", padx=16, pady=(3, 6))

        tk.Label(settings, text="หรืออัปโหลดเสียงอ้างอิงใหม่ 5-30 วินาที", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=16)
        ref_file = tk.Frame(settings, bg=COLORS["panel"]); ref_file.pack(fill="x", padx=16, pady=(4, 5))
        tk.Entry(ref_file, textvariable=self.voice_reference_file, state="readonly", readonlybackground="#080D1E", fg=COLORS["muted"], relief="flat").pack(side="left", fill="x", expand=True, ipady=7)
        ttk.Button(ref_file, text="เลือกไฟล์", style="Ghost.TButton", command=self._select_reference_audio).pack(side="left", padx=(6, 0))
        ttk.Button(settings, text="อัปโหลดและใช้เสียงไฟล์นี้", style="Primary.TButton", command=self._upload_voice_reference).pack(fill="x", padx=16, pady=(0, 6))

        tk.Label(settings, text="reference_id ที่จะใช้", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=16)
        tk.Entry(settings, textvariable=self.voice_reference_id, bg="#080D1E", fg=COLORS["text"], insertbackground="white", relief="flat").pack(fill="x", padx=16, ipady=5, pady=(3, 6))

        options = tk.Frame(settings, bg=COLORS["panel"]); options.pack(fill="x", padx=16)
        for column in range(2): options.columnconfigure(column, weight=1)
        self._voice_option(options, "ภาษา", self.voice_language, ("th", "en", "ja", "zh"), 0, 0)
        self.voice_emotion_combo = self._voice_option(options, "อารมณ์ (ล็อกเพื่อเสียงไม่เพี้ยน)", self.voice_emotion, (CLIP_VOICE_EMOTION,), 0, 1)
        self.voice_emotion_combo.configure(state="disabled")
        self.voice_speed_entry = self._voice_option(options, "ความเร็ว (ล็อก)", self.voice_speed, None, 1, 0)
        self.voice_speed_entry.configure(state="disabled")
        self._voice_option(options, "เว้นท้าย 0-3 วิ", self.voice_silence, None, 1, 1)
        self._voice_option(options, "ชนิดไฟล์", self.voice_format, ("mp3", "wav", "mp4"), 2, 0)
        ttk.Button(settings, text="บันทึกการตั้งค่าเสียง", style="Ghost.TButton", command=self._save_voice_preferences).pack(fill="x", padx=16, pady=(3, 12))

        script_panel = self._panel(content, side="left", fill="both", expand=True, padx=(12, 0))
        title = tk.Frame(script_panel, bg=COLORS["panel"]); title.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(title, text="บทพูดจาก AI Web", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 11)).pack(side="left")
        tk.Label(title, text="แก้ข้อความได้ก่อนสร้างเสียง", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="right")
        actions = tk.Frame(script_panel, bg=COLORS["panel"]); actions.pack(side="bottom", fill="x", padx=16, pady=(4, 16))
        ttk.Button(actions, text="2 • สร้างและดาวน์โหลดเสียง", style="Accent.TButton", command=self._create_voice).pack(side="bottom", fill="x", pady=(7, 0))
        voice_helpers = tk.Frame(actions, bg=COLORS["panel"]); voice_helpers.pack(fill="x")
        ttk.Button(voice_helpers, text="ให้ AI Web สร้างบทพูด", style="Ghost.TButton", command=self._prepare_voice_chatgpt).pack(side="left")
        ttk.Button(voice_helpers, text="โหลดบทพูดจาก Job", style="Ghost.TButton", command=self._load_voice_job).pack(side="left", padx=7)
        ttk.Button(actions, text="บันทึกค่าและบทพูด", style="Ghost.TButton", command=self._save_voice_preferences).pack(fill="x", pady=(5, 0))
        self.voice_script = tk.Text(script_panel, bg="#080D1E", fg=COLORS["text"], insertbackground="white", selectbackground="#284A91", relief="flat", wrap="word", font=("Segoe UI", 11), padx=14, pady=12)
        self.voice_script.pack(fill="both", expand=True, padx=16, pady=(0, 8))

    def _voice_option(self, parent, label, variable, values, row, column):
        frame = tk.Frame(parent, bg=COLORS["panel"]); frame.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 5, 5 if column == 0 else 0), pady=(0, 5))
        tk.Label(frame, text=label, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        if values:
            control = ttk.Combobox(frame, textvariable=variable, values=values, state="readonly", width=12)
            control.pack(fill="x", pady=(3, 0))
        else:
            control = tk.Entry(frame, textvariable=variable, bg="#080D1E", fg=COLORS["text"], insertbackground="white", relief="flat")
            control.pack(fill="x", ipady=6, pady=(3, 0))
        return control

    def _build_subtitle(self):
        page = self._page("subtitle")
        self._heading(page, "AI Subtitle", "เชื่อมต่อครั้งเดียว แล้วสร้างคำบรรยายจากเสียงของ Product Job ได้ในปุ่มเดียว")

        steps = self._panel(page, fill="x", pady=(0, 12))
        for index, text in enumerate(("1  เชื่อม Token", "2  เลือก Product Job", "3  ส่งเสียงและรอผล", "4  บันทึก SRT + Transcript")):
            cell = tk.Frame(steps, bg=COLORS["panel"]); cell.pack(side="left", fill="x", expand=True, padx=(14 if index == 0 else 5, 14 if index == 3 else 5), pady=11)
            tk.Label(cell, text=text, bg=COLORS["panel"], fg=COLORS["cyan"] if index < 2 else COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w")

        content = tk.Frame(page, bg=COLORS["bg"]); content.pack(fill="both", expand=True)
        _subtitle_left_viewport, left = self._scroll_panel(content, width=390, side="left", fill="y")
        tk.Label(left, text="เชื่อมต่อ SmartSub Online", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(left, text="ใช้ Token SOT เฉพาะครั้งแรก • โปรแกรมจะเก็บ SOD ใน Windows อย่างปลอดภัย", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=350, justify="left").pack(anchor="w", padx=16, pady=(0, 10))
        token_row = tk.Frame(left, bg=COLORS["panel"]); token_row.pack(fill="x", padx=16)
        self.subtitle_token_entry = tk.Entry(token_row, textvariable=self.subtitle_token, show="•", bg="#080D1E", fg=COLORS["text"], insertbackground="white", relief="flat", font=("Segoe UI", 10))
        self.subtitle_token_entry.pack(side="left", fill="x", expand=True, ipady=8)
        ttk.Button(token_row, text="เชื่อมต่อ", style="Primary.TButton", command=self._redeem_subtitle).pack(side="left", padx=(6, 0))
        token_actions = tk.Frame(left, bg=COLORS["panel"]); token_actions.pack(fill="x", padx=16, pady=(6, 15))
        ttk.Checkbutton(token_actions, text="แสดง Token", variable=self.subtitle_show_token, style="Dark.TCheckbutton", command=self._toggle_subtitle_token).pack(side="left")
        tk.Label(token_actions, textvariable=self.subtitle_credential_saved, bg=COLORS["panel"], fg=COLORS["green"], font=("Segoe UI", 8)).pack(side="left", padx=8)
        tk.Button(token_actions, text="ยกเลิกการเชื่อมต่อ", command=self._delete_subtitle_credential, relief="flat", bd=0, bg=COLORS["panel"], fg=COLORS["danger"], activebackground=COLORS["panel"], activeforeground="#FF8BA0", font=("Segoe UI", 8), cursor="hand2").pack(side="right")

        tk.Frame(left, bg=COLORS["line"], height=1).pack(fill="x", padx=16, pady=(0, 14))
        tk.Label(left, text="สร้างคำบรรยาย", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=16, pady=(0, 8))
        selector = tk.Frame(left, bg=COLORS["panel"]); selector.pack(fill="x", padx=16)
        self.subtitle_job_combo = ttk.Combobox(selector, textvariable=self.subtitle_job_id, state="readonly")
        self.subtitle_job_combo.pack(side="left", fill="x", expand=True)
        self.subtitle_job_combo.bind("<<ComboboxSelected>>", lambda event: self._load_subtitle_job())
        ttk.Combobox(selector, textvariable=self.subtitle_language, values=("th", "en"), state="readonly", width=7).pack(side="left", padx=(6, 0))
        tk.Label(left, textvariable=self.subtitle_audio_label, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=350, justify="left").pack(anchor="w", padx=16, pady=(8, 4))
        syllable_row = tk.Frame(left, bg=COLORS["panel"]); syllable_row.pack(fill="x", padx=16, pady=(5, 8))
        tk.Label(syllable_row, text="จำนวนพยางค์ต่อช่วง", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        syllable_combo = ttk.Combobox(syllable_row, textvariable=self.subtitle_syllables, values=("1", "2", "3", "4", "5"), state="readonly", width=5)
        syllable_combo.pack(side="right"); syllable_combo.bind("<<ComboboxSelected>>", lambda event: self._subtitle_segmentation_changed())
        tk.Label(syllable_row, text="3 พยางค์จริง • สระไม่แยก", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI", 8)).pack(side="right", padx=8)
        ttk.Checkbutton(left, text="เอา Subtitle ทุกงาน • ติ๊กครั้งเดียวและจำค่าไว้", variable=self.subtitle_auto, style="Dark.TCheckbutton", command=self._subtitle_option_changed).pack(anchor="w", padx=16, pady=(4, 3))
        tk.Label(left, textvariable=self.subtitle_preference_status, bg=COLORS["panel"], fg=COLORS["green"], font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=35, pady=(0, 10))
        ttk.Button(left, text="สร้างคำบรรยายจากเสียงของ Job", style="Accent.TButton", command=self._create_subtitle).pack(fill="x", padx=16, pady=(0, 8))
        ttk.Button(left, text="เปิดโฟลเดอร์คำบรรยาย", style="Ghost.TButton", command=self._open_subtitle_folder).pack(fill="x", padx=16, pady=(0, 7))

        _subtitle_right_viewport, right = self._scroll_panel(content, side="left", fill="both", expand=True, padx=(12, 0))
        head = tk.Frame(right, bg=COLORS["panel"]); head.pack(fill="x", padx=16, pady=(13, 3))
        tk.Label(head, text="รูปแบบข้อความและพรีวิว", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 11)).pack(side="left")
        tk.Label(right, textvariable=self.subtitle_status, bg="#0D2030", fg=COLORS["cyan"], font=("Segoe UI", 8), wraplength=520, justify="left", anchor="w", padx=9, pady=4).pack(fill="x", padx=16, pady=(0, 7))

        style_box = tk.Frame(right, bg=COLORS["panel_2"], highlightbackground=COLORS["line"], highlightthickness=1)
        style_box.pack(fill="x", padx=16, pady=(0, 9))
        theme_row = tk.Frame(style_box, bg=COLORS["panel_2"]); theme_row.pack(fill="x", padx=10, pady=(9, 4))
        tk.Label(theme_row, text="ธีม", bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="left")
        tk.Button(theme_row, text="สุ่มธีม", command=self._random_subtitle_theme, relief="flat", bd=0, bg=COLORS["panel_3"], fg=COLORS["text"], activebackground="#25345C", activeforeground="#FFFFFF", font=("Segoe UI Semibold", 8), padx=8, pady=6, cursor="hand2").pack(side="right")
        ttk.Checkbutton(theme_row, text="สุ่มทุกงาน", variable=self.subtitle_theme_random, style="Dark.TCheckbutton", command=self._subtitle_style_changed).pack(side="right", padx=(4, 6))
        theme_combo = ttk.Combobox(theme_row, textvariable=self.subtitle_theme, values=[item["label"] for item in SUBTITLE_THEMES.values()], state="readonly")
        theme_combo.pack(side="left", fill="x", expand=True, padx=(5, 3)); theme_combo.bind("<<ComboboxSelected>>", lambda event: self._apply_subtitle_theme())
        animation_row = tk.Frame(style_box, bg=COLORS["panel_2"]); animation_row.pack(fill="x", padx=10, pady=(2, 4))
        tk.Label(animation_row, text="แอนิเมชัน", bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="left", padx=(0, 3))
        animation_combo = ttk.Combobox(animation_row, textvariable=self.subtitle_animation, values=list(SUBTITLE_ANIMATIONS.values()), state="readonly", width=20)
        animation_combo.pack(side="left"); animation_combo.bind("<<ComboboxSelected>>", lambda event: self._subtitle_style_changed())
        ttk.Checkbutton(animation_row, text="สุ่ม", variable=self.subtitle_animation_random, style="Dark.TCheckbutton", command=self._subtitle_style_changed).pack(side="left", padx=(6, 0))
        row1 = tk.Frame(style_box, bg=COLORS["panel_2"]); row1.pack(fill="x", padx=10, pady=(9, 5))
        tk.Label(row1, text="ฟอนต์", bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="left")
        ttk.Button(row1, text="อัปโหลดฟอนต์", style="Ghost.TButton", command=self._upload_subtitle_font).pack(side="right")
        self.subtitle_font_combo = ttk.Combobox(row1, textvariable=self.subtitle_font_label, state="readonly")
        self.subtitle_font_combo.pack(side="left", fill="x", expand=True, padx=7)
        self.subtitle_font_combo.configure(values=[record.label for record in self._subtitle_font_records])
        self.subtitle_font_combo.bind("<<ComboboxSelected>>", lambda event: self._subtitle_style_changed())

        row2 = tk.Frame(style_box, bg=COLORS["panel_2"]); row2.pack(fill="x", padx=10, pady=3)
        self._subtitle_slider(row2, "ขนาด", self.subtitle_font_size, 14, 72, 1)
        row2b = tk.Frame(style_box, bg=COLORS["panel_2"]); row2b.pack(fill="x", padx=10, pady=3)
        self._subtitle_slider(row2b, "ช่องไฟสระ–วรรณยุกต์", self.subtitle_thai_mark_gap, 0, 20, 1)
        row2c = tk.Frame(style_box, bg=COLORS["panel_2"]); row2c.pack(fill="x", padx=10, pady=3)
        self._subtitle_slider(row2c, "เส้นขอบ", self.subtitle_outline_width, 0, 8, 1)
        position_row = tk.Frame(style_box, bg=COLORS["panel_2"]); position_row.pack(fill="x", padx=10, pady=4)
        tk.Label(position_row, text="ตำแหน่ง", bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="left", padx=(0, 3))
        position_combo = ttk.Combobox(position_row, textvariable=self.subtitle_position, values=("ด้านบน", "กึ่งกลาง", "ด้านล่าง"), state="readonly", width=8)
        position_combo.pack(side="left"); position_combo.bind("<<ComboboxSelected>>", lambda event: self._subtitle_position_preset_changed())
        self._subtitle_slider(position_row, "สูง–ต่ำ", self.subtitle_position_y, 5, 95, 1, compact=True)

        row3 = tk.Frame(style_box, bg=COLORS["panel_2"]); row3.pack(fill="x", padx=10, pady=(5, 8))
        self._subtitle_color_button(row3, "สีข้อความ", self.subtitle_text_color)
        self._subtitle_color_button(row3, "สีไฮไลต์", self.subtitle_highlight_color)
        self._subtitle_color_button(row3, "สีขอบ", self.subtitle_outline_color)
        self._subtitle_color_button(row3, "สีพื้น", self.subtitle_background_color)
        ttk.Checkbutton(row3, text="พื้นหลัง", variable=self.subtitle_background_enabled, style="Dark.TCheckbutton", command=self._subtitle_style_changed).pack(side="left", padx=(8, 2))
        render_row = tk.Frame(style_box, bg=COLORS["panel_2"]); render_row.pack(fill="x", padx=10, pady=(0, 8))
        self._subtitle_slider(render_row, "ความทึบพื้นหลัง", self.subtitle_background_opacity, 0, 100, 5, compact=True)
        ttk.Button(render_row, text="บันทึกและสร้างใหม่", style="Primary.TButton", command=self._apply_subtitle_style).pack(side="right")

        result = tk.Frame(right, bg=COLORS["panel"]); result.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        preview_box = tk.Frame(result, bg="#080D1E", width=280, height=185, highlightbackground=COLORS["line"], highlightthickness=1)
        preview_box.pack(side="left", fill="y"); preview_box.pack_propagate(False)
        tk.Label(preview_box, text="พรีวิวจริง 720 × 1280", bg="#080D1E", fg=COLORS["cyan"], font=("Segoe UI Semibold", 8)).pack(pady=(8, 2))
        tk.Label(preview_box, textvariable=self.subtitle_preview_meta, bg="#080D1E", fg=COLORS["muted"], font=("Segoe UI", 7), wraplength=250, justify="center").pack(pady=(0, 5))
        self.subtitle_visual_preview = tk.Label(preview_box, bg="#080D1E", bd=0)
        self.subtitle_visual_preview.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.subtitle_visual_preview.bind("<Configure>", self._resize_subtitle_visual_preview)
        self.subtitle_preview = tk.Text(result, bg="#080D1E", fg=COLORS["text"], insertbackground="white", selectbackground="#284A91", relief="flat", wrap="word", font=("Segoe UI", 10), padx=12, pady=10, state="disabled")
        self.subtitle_preview.pack(side="left", fill="both", expand=True, padx=(9, 0))

        def layout_subtitle_result(event=None):
            compact = result.winfo_width() < 520
            if compact:
                self.subtitle_preview.pack_forget()
                preview_box.pack_configure(side="left", fill="both", expand=True, padx=0)
                preview_box.configure(width=max(280, result.winfo_width()))
            else:
                preview_box.pack_configure(side="left", fill="y", expand=False, padx=0)
                preview_box.configure(width=280)
                if not self.subtitle_preview.winfo_manager():
                    self.subtitle_preview.pack(side="left", fill="both", expand=True, padx=(9, 0))

        result.bind("<Configure>", layout_subtitle_result)
        self.root.after(150, self._update_subtitle_style_preview)

    def _load_subtitle_fonts(self, selected_path=""):
        self._subtitle_font_records = self.fonts.scan()
        selected = self.fonts.resolve(selected_path) if selected_path else None
        record = next((item for item in self._subtitle_font_records if selected and item.path == selected), None)
        if not record:
            record = next((item for item in self._subtitle_font_records if item.path.name.lower() == "prompt-extrabold.ttf"), None)
        if not record and self._subtitle_font_records:
            record = self._subtitle_font_records[0]
        self.subtitle_font_label.set(record.label if record else "ฟอนต์ระบบ")

    def _resize_subtitle_visual_preview(self, event=None):
        source = self._subtitle_preview_source_image
        if source is None or not hasattr(self, "subtitle_visual_preview"):
            return
        available_width = max(1, self.subtitle_visual_preview.winfo_width() - 4)
        available_height = max(1, self.subtitle_visual_preview.winfo_height() - 4)
        if available_width < 20 or available_height < 20:
            return
        scale = min(248 / source.width, 441 / source.height, available_width / source.width, available_height / source.height)
        dimensions = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
        if dimensions == self._subtitle_preview_dimensions:
            return
        preview = source.resize(dimensions, Image.Resampling.LANCZOS)
        self._subtitle_preview_photo = ImageTk.PhotoImage(preview)
        self._subtitle_preview_dimensions = dimensions
        self.subtitle_visual_preview.configure(image=self._subtitle_preview_photo, text="")

    def _selected_subtitle_font(self):
        label = self.subtitle_font_label.get().strip()
        return next((item for item in self._subtitle_font_records if item.label == label), None)

    def _subtitle_number_control(self, parent, label, variable, minimum, maximum):
        tk.Label(parent, text=label, bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="left", padx=(4, 3))
        widget = tk.Spinbox(
            parent, from_=minimum, to=maximum, width=4, textvariable=variable,
            command=self._subtitle_style_changed, bg="#080D1E", fg=COLORS["text"],
            buttonbackground=COLORS["panel_2"], relief="flat",
        )
        widget.pack(side="left")
        widget.bind("<FocusOut>", lambda event: self._subtitle_style_changed())
        widget.bind("<Return>", lambda event: self._subtitle_style_changed())

    def _subtitle_slider(self, parent, label, variable, minimum, maximum, step=1, compact=False):
        holder = tk.Frame(parent, bg=COLORS["panel_2"])
        holder.pack(side="left", padx=(0, 5))
        tk.Label(holder, text=label, bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="left", padx=(0, 2))
        def change(delta):
            value = max(minimum, min(maximum, float(variable.get()) + delta))
            variable.set(round(value))
            self._subtitle_style_changed()
        tk.Button(holder, text="−", command=lambda: change(-step), width=1, relief="flat", bd=0, bg="#0A1022", fg=COLORS["text"], activebackground="#25345C", activeforeground="white").pack(side="left")
        scale = tk.Scale(
            holder, from_=minimum, to=maximum, resolution=step, orient="horizontal", variable=variable,
            command=lambda value: self._subtitle_style_changed(), showvalue=False,
            length=55 if compact else 72, sliderlength=12, width=8, bg=COLORS["panel_2"],
            troughcolor="#25345C", activebackground=COLORS["purple"], highlightthickness=0, bd=0,
        )
        scale.pack(side="left")
        tk.Button(holder, text="+", command=lambda: change(step), width=1, relief="flat", bd=0, bg="#0A1022", fg=COLORS["text"], activebackground="#25345C", activeforeground="white").pack(side="left")
        tk.Label(holder, textvariable=variable, width=3, bg=COLORS["panel_2"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 8)).pack(side="left", padx=(2, 0))

    def _apply_subtitle_theme(self, schedule_preview=True):
        selected = theme_by_label(self.subtitle_theme.get())
        if not selected:
            return
        _, theme = selected
        record = next((item for item in self._subtitle_font_records if item.path.name.lower() == theme["font_file"].lower()), None)
        if record:
            self.subtitle_font_label.set(record.label)
        self.subtitle_font_size.set(theme["font_size"])
        self.subtitle_letter_spacing.set(int(theme.get("letter_spacing", 0)))
        self.subtitle_thai_mark_gap.set(int(theme.get("thai_mark_gap", 14)))
        self.subtitle_text_color.set(theme["text_color"])
        self.subtitle_outline_color.set(theme["outline_color"])
        self.subtitle_outline_width.set(theme["outline_width"])
        self.subtitle_background_enabled.set(theme["background_enabled"])
        self.subtitle_background_color.set(theme["background_color"])
        self.subtitle_background_opacity.set(round(theme["background_opacity"] * 100))
        if schedule_preview:
            self._subtitle_style_changed()

    def _random_subtitle_theme(self):
        _, theme = random_theme()
        self.subtitle_theme.set(theme["label"])
        self._apply_subtitle_theme()

    def _random_subtitle_animation(self):
        key = random_animation()
        self.subtitle_animation.set(SUBTITLE_ANIMATIONS[key])
        self._subtitle_style_changed()

    def _subtitle_position_preset_changed(self):
        self.subtitle_position_y.set({"ด้านบน": 10, "กึ่งกลาง": 50, "ด้านล่าง": 90}.get(self.subtitle_position.get(), 90))
        self._subtitle_style_changed()

    def _subtitle_color_button(self, parent, label, variable):
        def choose():
            selected = colorchooser.askcolor(variable.get(), title=f"เลือก{label}", parent=self.root)[1]
            if selected:
                variable.set(selected.upper())
                button.configure(bg=selected, activebackground=selected)
                self._subtitle_style_changed()
        button = tk.Button(
            parent, text=label, command=choose, bg=variable.get(), fg="#FFFFFF",
            activeforeground="#FFFFFF", relief="flat", bd=0, padx=7, pady=4,
            font=("Segoe UI Semibold", 8), cursor="hand2",
        )
        button.pack(side="left", padx=(0, 5))

    def _upload_subtitle_font(self):
        source = filedialog.askopenfilename(
            title="เลือกฟอนต์ TTF หรือ OTF", filetypes=(("ไฟล์ฟอนต์", "*.ttf *.otf"), ("ทุกไฟล์", "*.*")),
        )
        if not source:
            return
        try:
            uploaded = self.fonts.upload(source)
            self._load_subtitle_fonts(uploaded.path)
            self.subtitle_font_combo.configure(values=[record.label for record in self._subtitle_font_records])
            self._subtitle_style_changed()
            self.subtitle_status.set(f"เพิ่มฟอนต์ {uploaded.family} แล้ว • พร้อมใช้ทุกงาน")
        except Exception as exc:
            messagebox.showerror("เพิ่มฟอนต์ไม่สำเร็จ", str(exc))

    def _subtitle_style_settings(self, for_render=False, job_id=""):
        record = self._selected_subtitle_font()
        position = {"ด้านบน": "top", "กึ่งกลาง": "center", "ด้านล่าง": "bottom"}.get(self.subtitle_position.get(), "bottom")
        font_size = max(10, min(96, int(self.subtitle_font_size.get())))
        letter_spacing = max(0, min(20, int(self.subtitle_letter_spacing.get())))
        thai_mark_gap = max(0, min(20, int(self.subtitle_thai_mark_gap.get())))
        outline_width = max(0, min(10, int(self.subtitle_outline_width.get())))
        margin_v = max(0, min(140, int(self.subtitle_margin_v.get())))
        opacity = max(0, min(100, int(self.subtitle_background_opacity.get()))) / 100
        settings = {
            "font_name": record.family if record else "Leelawadee UI",
            "font_path": str(record.path) if record else "",
            "font_size": font_size,
            "letter_spacing": letter_spacing,
            "thai_mark_gap": thai_mark_gap,
            "text_color": self.subtitle_text_color.get().upper(),
            "outline_color": self.subtitle_outline_color.get().upper(),
            "outline_width": outline_width,
            "background_enabled": bool(self.subtitle_background_enabled.get()),
            "background_color": self.subtitle_background_color.get().upper(),
            "background_opacity": opacity,
            "position": position,
            "position_y_percent": max(5, min(95, int(self.subtitle_position_y.get()))),
            "margin_v": margin_v,
            "highlight_color": self.subtitle_highlight_color.get().upper(),
            "animation": animation_by_label(self.subtitle_animation.get()),
        }
        if for_render:
            rng = random.Random(str(job_id or time.time_ns()))
            if self.subtitle_theme_random.get():
                _, theme = random_theme(rng)
                theme_record = next((item for item in self._subtitle_font_records if item.path.name.lower() == theme["font_file"].lower()), None)
                settings.update({
                    "font_name": theme_record.family if theme_record else settings["font_name"],
                    "font_path": str(theme_record.path) if theme_record else settings["font_path"],
                    "font_size": theme["font_size"], "text_color": theme["text_color"],
                    "letter_spacing": int(theme.get("letter_spacing", settings["letter_spacing"])),
                    "thai_mark_gap": int(theme.get("thai_mark_gap", settings["thai_mark_gap"])),
                    "outline_color": theme["outline_color"], "outline_width": theme["outline_width"],
                    "background_enabled": theme["background_enabled"], "background_color": theme["background_color"],
                    "background_opacity": theme["background_opacity"],
                })
            if self.subtitle_animation_random.get():
                settings["animation"] = random_animation(rng)
        return settings

    def _save_subtitle_style(self):
        settings = self._subtitle_style_settings()
        record = self._selected_subtitle_font()
        saved_values = {
            "subtitle_font_file": self.fonts.portable_path(record.path) if record else "",
            "subtitle_font_size": settings["font_size"],
            "subtitle_letter_spacing": settings["letter_spacing"],
            "subtitle_thai_mark_gap": settings["thai_mark_gap"],
            "subtitle_text_color": settings["text_color"],
            "subtitle_outline_color": settings["outline_color"],
            "subtitle_outline_width": settings["outline_width"],
            "subtitle_background_enabled": settings["background_enabled"],
            "subtitle_background_color": settings["background_color"],
            "subtitle_background_opacity": settings["background_opacity"],
            "subtitle_highlight_color": settings["highlight_color"],
            "subtitle_theme": theme_by_label(self.subtitle_theme.get())[0] if theme_by_label(self.subtitle_theme.get()) else "standard",
            "subtitle_theme_random": bool(self.subtitle_theme_random.get()),
            "subtitle_animation": settings["animation"],
            "subtitle_animation_random": bool(self.subtitle_animation_random.get()),
            "subtitle_position": settings["position"],
            "subtitle_position_y_percent": settings["position_y_percent"],
            "subtitle_margin_v": settings["margin_v"],
        }
        save_subtitle_settings(saved_values)
        self.cfg.update(saved_values)
        return settings

    def _set_subtitle_style_from_payload(self, payload, apply_theme=False):
        self.subtitle_job_id.set(str(payload.get("job_id") or self.subtitle_job_id.get()))
        self.subtitle_language.set(str(payload.get("language") or "th"))
        self.subtitle_syllables.set(str(max(1, min(5, int(payload.get("syllables") or 3)))))
        self.subtitle_auto.set(bool(payload.get("auto", self.subtitle_auto.get())))
        self.subtitle_theme.set(str(payload.get("theme") or self.subtitle_theme.get()))
        self.subtitle_animation.set(str(payload.get("animation") or self.subtitle_animation.get()))
        if apply_theme:
            self._apply_subtitle_theme(schedule_preview=False)
            return
        requested_font = str(payload.get("font") or self.subtitle_font_label.get())
        if requested_font and any(record.label == requested_font for record in self._subtitle_font_records):
            self.subtitle_font_label.set(requested_font)
        self.subtitle_font_size.set(max(14, min(72, int(payload.get("font_size") or 28))))
        self.subtitle_thai_mark_gap.set(max(0, min(20, int(payload.get("thai_mark_gap", 14)))))
        self.subtitle_outline_width.set(max(0, min(8, int(payload.get("outline_width", 2)))))
        self.subtitle_position_y.set(max(5, min(95, int(payload.get("position_y") or 90))))
        self.subtitle_text_color.set(str(payload.get("text_color") or "#FFFFFF"))
        self.subtitle_highlight_color.set(str(payload.get("highlight_color") or "#FACC15"))
        self.subtitle_outline_color.set(str(payload.get("outline_color") or "#101010"))
        self.subtitle_background_enabled.set(bool(payload.get("background_enabled", False)))
        self.subtitle_background_color.set(str(payload.get("background_color") or "#000000"))
        self.subtitle_background_opacity.set(max(0, min(100, int(payload.get("background_opacity") if payload.get("background_opacity") is not None else 45))))

    def _subtitle_style_changed(self):
        if self._subtitle_style_after:
            try:
                self.root.after_cancel(self._subtitle_style_after)
            except Exception:
                pass
        self._subtitle_style_after = self.root.after(120, self._commit_subtitle_style_changed)

    def _commit_subtitle_style_changed(self):
        self._subtitle_style_after = None
        try:
            self._save_subtitle_style()
            self._update_subtitle_style_preview()
        except Exception as exc:
            self.subtitle_status.set(f"ตรวจรูปแบบข้อความอีกครั้ง • {exc}")

    def _preview_subtitle_text(self):
        job_id = self.subtitle_job_id.get().strip()
        srt = self.products.root / job_id / "captions" / "subtitle.srt" if job_id else None
        if srt and srt.exists():
            lines = [line.strip() for line in srt.read_text(encoding="utf-8-sig").splitlines()]
            text = next((line for line in lines if line and not line.isdigit() and "-->" not in line), "")
            if text:
                return text
        return "เก้าอี้ นี่น้ำปั่น"

    def _update_subtitle_style_preview(self):
        try:
            settings = self._subtitle_style_settings()
            record = self._selected_subtitle_font()
            if self.hybrid_engine:
                if not getattr(self, "_subtitle_preview_service", None):
                    self._subtitle_preview_service = SubtitlePreviewService(ROOT / "workspace" / "preview", self.cfg.get("ffmpeg_path", ""))
                self._subtitle_preview_token = self._subtitle_preview_service.request(self._preview_subtitle_text(), settings)
                return
            self._subtitle_preview_token += 1
            token = self._subtitle_preview_token
            self._subtitle_preview_busy = True
            self._subtitle_preview_error_message = ""
            self.subtitle_preview_meta.set(
                f"{record.family if record else settings['font_name']} • {settings['font_size']} px • ช่องไฟสระ–วรรณยุกต์ {settings['thai_mark_gap']}% • Y {settings['position_y_percent']}%"
            )
            preview_name = f"subtitle_preview_hybrid_{os.getpid()}_{token}.png" if self.hybrid_engine else f"subtitle_preview_{token}.png"
            target = ROOT / "workspace" / "preview" / preview_name
            video_target = target.with_suffix(".mp4")
            if self.hybrid_engine:
                for pattern in ("subtitle_preview_hybrid_*.png", "subtitle_preview_hybrid_*.mp4"):
                    for previous in target.parent.glob(pattern):
                        if previous not in {target, video_target}:
                            previous.unlink(missing_ok=True)
            if hasattr(self, "subtitle_visual_preview"):
                try:
                    self.subtitle_visual_preview.configure(image="", text="กำลังเรนเดอร์พรีวิวจริง...", fg=COLORS["muted"])
                except tk.TclError:
                    pass
            threading.Thread(
                target=self._subtitle_preview_worker,
                args=(token, target, video_target, self._preview_subtitle_text(), settings), daemon=True,
            ).start()
        except Exception as exc:
            self._subtitle_preview_busy = False
            self._subtitle_preview_error_message = str(exc)
            if hasattr(self, "subtitle_visual_preview"):
                try:
                    self.subtitle_visual_preview.configure(image="", text=f"แสดงพรีวิวไม่ได้\n{exc}", fg=COLORS["danger"])
                except tk.TclError:
                    pass
            self.subtitle_status.set(f"สร้างพรีวิว Subtitle ไม่สำเร็จ • {exc}")

    def _subtitle_preview_worker(self, token, target, video_target, text, settings):
        try:
            renderer = SubtitleVideoRenderer(self.cfg.get("ffmpeg_path", ""))
            renderer.render_preview_image(target, text=text, **settings)
            renderer.render_preview_video(video_target, text=text, **settings)
            self.events.put(("subtitle_preview_ready", (token, target, video_target)))
        except Exception as exc:
            self.events.put(("subtitle_preview_error", (token, str(exc), target, video_target)))

    def _apply_subtitle_style(self):
        try:
            self._save_subtitle_style()
            self._update_subtitle_style_preview()
            job_id = self.subtitle_job_id.get().strip()
            if not job_id:
                self.subtitle_status.set("บันทึกรูปแบบข้อความแล้ว • งานใหม่จะใช้ค่านี้อัตโนมัติ")
                return
            self.products.mark_subtitle_video_needs_render(job_id)
            self.subtitle_status.set(f"{job_id} • บันทึกรูปแบบแล้ว • กำลังสร้างวิดีโอใหม่")
            settings = self._subtitle_style_settings(for_render=True, job_id=f"{job_id}-{time.time_ns()}")
            self._maybe_render_subtitles(job_id, force=True, settings=settings)
        except Exception as exc:
            messagebox.showerror("บันทึกรูปแบบ Subtitle ไม่สำเร็จ", str(exc))

    @staticmethod
    def _background_mode_key(label):
        return {
            "อัตโนมัติ • ยำ 3 ช่วง": "auto", "อัตโนมัติ • ยำท่อนสั้น V2": "auto",
            "สุ่มใหม่ทุกงาน": "random", "สุ่มท่อนสั้นทุกงาน": "random",
            "เลือกเพลงเดียว": "selected", "เลือกเพลงเดียว • ตัดเป็นท่อน": "selected",
        }.get(label, "auto")

    @staticmethod
    def _sfx_mode_key(label):
        return {"อัตโนมัติ • เว้นจังหวะ": "auto", "สุ่มเสียงทุกจุด": "random", "เลือกเสียงเดียว": "selected"}.get(label, "auto")

    def _audio_assets(self, kind):
        return AudioMixer.scan_audio(self._audio_asset_folder(kind))

    @staticmethod
    def _audio_asset_folder(kind):
        if kind not in {"background", "sfx"}:
            raise ValueError("ประเภทคลังเสียงไม่ถูกต้อง")
        target = ROOT / "assets" / "audio" / kind
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _open_audio_asset_folder(self, kind):
        target = self._audio_asset_folder(kind)
        self._open_folder(target)
        label = "เพลงพื้นหลัง" if kind == "background" else "เสียงเน้นข้อความ"
        self.audio_status.set(f"เปิดโฟลเดอร์{label}แล้ว • กลับมาหน้านี้เพื่อเลือกรายการที่เพิ่ม")
        return target

    def _build_audio(self):
        page = self._page("audio")
        self._heading(page, "เสียงประกอบอัตโนมัติ", "เพลงพื้นหลังคลอเบา ๆ + เสียงเน้นข้อความที่เว้นจังหวะอย่างมืออาชีพ")
        selector = self._panel(page, fill="x", pady=(0, 12))
        tk.Label(selector, text="Product Job", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 10)).pack(side="left", padx=(15, 8), pady=12)
        self.audio_job_combo = ttk.Combobox(selector, textvariable=self.audio_job_id, state="readonly", width=26)
        self.audio_job_combo.pack(side="left", pady=10); self.audio_job_combo.bind("<<ComboboxSelected>>", lambda event: self._load_audio_job())
        tk.Label(selector, textvariable=self.audio_status, bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI", 9), wraplength=560).pack(side="left", padx=12)
        ttk.Button(selector, text="เปิดโฟลเดอร์วิดีโอ", style="Ghost.TButton", command=self._open_audio_folder).pack(side="right", padx=(5, 12), pady=7)

        action = self._panel(page, side="bottom", fill="x", pady=(12, 0))
        tk.Label(action, text="ค่าเริ่มต้นเหมาะกับคลิปขายสินค้า: เพลง 12% • SFX 22% • เว้น 6 วินาที • ไม่เกิน 6 จุด", bg=COLORS["panel"], fg=COLORS["muted"], wraplength=680, justify="left", font=("Segoe UI", 9)).pack(fill="x", anchor="w", padx=16, pady=(10, 4))
        action_buttons = tk.Frame(action, bg=COLORS["panel"])
        action_buttons.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Button(action_buttons, text="สุ่มตัวเลือกใหม่", style="Ghost.TButton", command=self._randomize_audio_choices).pack(side="right", padx=(5, 12), pady=7)
        ttk.Button(action_buttons, text="สร้างวิดีโอพร้อมเสียงประกอบ", style="Accent.TButton", command=lambda: self._maybe_mix_audio(self.audio_job_id.get().strip(), force=True)).pack(side="right", pady=7)

        content = tk.Frame(page, bg=COLORS["bg"]); content.pack(fill="both", expand=True)
        _background_viewport, background = self._scroll_panel(content, side="left", fill="both", expand=True, padx=(0, 6))
        _sfx_viewport, sfx = self._scroll_panel(content, side="left", fill="both", expand=True, padx=(6, 0))

        tk.Label(background, text="เพลงพื้นหลัง", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=18, pady=(18, 4))
        tk.Label(background, text=f"คลังเริ่มต้น {len(self._audio_assets('background'))} เพลง • ค่าเริ่มต้นคลอเบา 12%", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(0, 12))
        ttk.Checkbutton(background, text="ใส่เพลงพื้นหลังให้ทุกงานอัตโนมัติ", variable=self.audio_background_enabled, style="Dark.TCheckbutton", command=self._save_audio_options).pack(anchor="w", padx=18, pady=(0, 10))
        tk.Label(background, text="วิธีเลือกเพลง", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=18)
        bg_mode = ttk.Combobox(background, textvariable=self.audio_background_mode, values=("อัตโนมัติ • ยำท่อนสั้น V2", "สุ่มท่อนสั้นทุกงาน", "เลือกเพลงเดียว • ตัดเป็นท่อน"), state="readonly")
        bg_mode.pack(fill="x", padx=18, pady=(5, 10)); bg_mode.bind("<<ComboboxSelected>>", lambda event: self._save_audio_options())
        bg_row = tk.Frame(background, bg=COLORS["panel"]); bg_row.pack(fill="x", padx=18)
        self.audio_background_combo = ttk.Combobox(bg_row, textvariable=self.audio_background_file, state="readonly", values=["สุ่มจากคลัง"] + [path.name for path in self._audio_assets("background")])
        self.audio_background_combo.pack(side="left", fill="x", expand=True); self.audio_background_combo.bind("<<ComboboxSelected>>", lambda event: self._save_audio_options())
        ttk.Button(bg_row, text="เปิดคลังเพลง", style="Ghost.TButton", command=lambda: self._open_audio_asset_folder("background")).pack(side="left", padx=(7, 0))
        self._audio_slider(background, "ระดับเพลงคลอ", self.audio_background_volume, 3, 35, 1, "%")
        self._audio_slider(background, "ท่อนเพลงยาวไม่เกิน", self.audio_background_segment_max, 8, 12, 1, " วินาที")
        self._audio_slider(background, "ช่วงมีเสียงพูด ลดเพลงเหลือ", self.audio_background_duck_percent, 20, 65, 1, "%")
        info = tk.Frame(background, bg="#111A34", highlightbackground=COLORS["line"], highlightthickness=1); info.pack(fill="x", padx=18, pady=14)
        tk.Label(info, text="AUTO MIX", bg="#111A34", fg=COLORS["green"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=12, pady=(10, 3))
        tk.Label(info, text="ตัดเพลงเป็นท่อนสั้น 4–8 วินาที สลับเพลงไม่ให้ซ้ำติดกัน ลดเสียงใต้บทพูด และต่อด้วย Crossfade นุ่ม ๆ", bg="#111A34", fg=COLORS["muted"], wraplength=410, justify="left", font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(0, 10))

        tk.Label(sfx, text="เสียงเน้นข้อความ", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=18, pady=(18, 4))
        tk.Label(sfx, text=f"คลังเริ่มต้น {len(self._audio_assets('sfx'))} เสียง • เว้นจังหวะ ไม่ยิงทุกคำ", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(0, 12))
        ttk.Checkbutton(sfx, text="ใส่เสียงข้อความอัตโนมัติ", variable=self.audio_sfx_enabled, style="Dark.TCheckbutton", command=self._save_audio_options).pack(anchor="w", padx=18, pady=(0, 10))
        tk.Label(sfx, text="รูปแบบเสียง", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=18)
        sfx_mode = ttk.Combobox(sfx, textvariable=self.audio_sfx_mode, values=("อัตโนมัติ • เว้นจังหวะ", "สุ่มเสียงทุกจุด", "เลือกเสียงเดียว"), state="readonly")
        sfx_mode.pack(fill="x", padx=18, pady=(5, 10)); sfx_mode.bind("<<ComboboxSelected>>", lambda event: self._save_audio_options())
        sfx_row = tk.Frame(sfx, bg=COLORS["panel"]); sfx_row.pack(fill="x", padx=18)
        self.audio_sfx_combo = ttk.Combobox(sfx_row, textvariable=self.audio_sfx_file, state="readonly", values=["สุ่มจากคลัง"] + [path.name for path in self._audio_assets("sfx")])
        self.audio_sfx_combo.pack(side="left", fill="x", expand=True); self.audio_sfx_combo.bind("<<ComboboxSelected>>", lambda event: self._save_audio_options())
        ttk.Button(sfx_row, text="เปิดคลังเสียง", style="Ghost.TButton", command=lambda: self._open_audio_asset_folder("sfx")).pack(side="left", padx=(7, 0))
        self._audio_slider(sfx, "ระดับเสียงข้อความ", self.audio_sfx_volume, 5, 60, 1, "%")
        self._audio_slider(sfx, "เว้นอย่างน้อย", self.audio_sfx_min_interval, 4, 15, 1, " วินาที")
        self._audio_slider(sfx, "จำนวนสูงสุด", self.audio_sfx_max_count, 1, 12, 1, " จุด")


    def _audio_slider(self, parent, title, variable, minimum, maximum, step, suffix):
        frame = tk.Frame(parent, bg=COLORS["panel"]); frame.pack(fill="x", padx=18, pady=(13, 0))
        tk.Label(frame, text=title, bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        value_label = tk.Label(frame, bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 9), width=9)
        value_label.pack(side="right")
        def changed(_=None):
            value_label.configure(text=f"{round(float(variable.get()))}{suffix}")
            self._save_audio_options()
        controls = tk.Frame(parent, bg=COLORS["panel"]); controls.pack(fill="x", padx=18)
        tk.Button(controls, text="−", command=lambda: (variable.set(max(minimum, float(variable.get()) - step)), changed()), relief="flat", bd=0, bg="#0A1022", fg="white", width=3).pack(side="left")
        scale = tk.Scale(controls, from_=minimum, to=maximum, resolution=step, orient="horizontal", variable=variable, command=changed, showvalue=False, bg=COLORS["panel"], troughcolor="#25345C", activebackground=COLORS["purple"], highlightthickness=0, bd=0)
        scale.pack(side="left", fill="x", expand=True)
        tk.Button(controls, text="+", command=lambda: (variable.set(min(maximum, float(variable.get()) + step)), changed()), relief="flat", bd=0, bg="#0A1022", fg="white", width=3).pack(side="left")
        changed()

    def _save_audio_options(self):
        try:
            values = {
                "audio_background_enabled": bool(self.audio_background_enabled.get()),
                "audio_background_mode": self.audio_background_mode.get(),
                "audio_background_file": self.audio_background_file.get(),
                "audio_background_volume": max(0, min(50, int(self.audio_background_volume.get()))) / 100,
                "audio_background_segment_max_sec": max(8, min(12, float(self.audio_background_segment_max.get()))),
                "audio_background_duck_percent": max(20, min(65, int(self.audio_background_duck_percent.get()))),
                "audio_sfx_enabled": bool(self.audio_sfx_enabled.get()),
                "audio_sfx_mode": self.audio_sfx_mode.get(),
                "audio_sfx_file": self.audio_sfx_file.get(),
                "audio_sfx_volume": max(0, min(80, int(self.audio_sfx_volume.get()))) / 100,
                "audio_sfx_min_interval": int(self.audio_sfx_min_interval.get()),
                "audio_sfx_max_count": int(self.audio_sfx_max_count.get()),
            }
            save_audio_settings(values)
            self.cfg.update(values)
            return values
        except Exception:
            return None

    def _add_audio_asset(self, kind):
        source = filedialog.askopenfilename(title="เลือกไฟล์เสียง", filetypes=(("ไฟล์เสียง", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("ทุกไฟล์", "*.*")))
        if not source:
            return
        try:
            source_path = Path(source)
            if source_path.suffix.lower() not in AudioMixer.AUDIO_EXTENSIONS:
                raise ValueError("รองรับ MP3, WAV, M4A, AAC และ OGG")
            target_folder = ROOT / "assets" / "audio" / kind; target_folder.mkdir(parents=True, exist_ok=True)
            target = target_folder / source_path.name
            if source_path.resolve() != target.resolve():
                shutil.copy2(source_path, target)
            if kind == "background":
                self.audio_background_combo.configure(values=["สุ่มจากคลัง"] + [path.name for path in self._audio_assets(kind)])
                self.audio_background_file.set(target.name)
                self.audio_background_mode.set("เลือกเพลงเดียว")
            else:
                self.audio_sfx_combo.configure(values=["สุ่มจากคลัง"] + [path.name for path in self._audio_assets(kind)])
                self.audio_sfx_file.set(target.name)
                self.audio_sfx_mode.set("เลือกเสียงเดียว")
            self._save_audio_options()
            self.audio_status.set(f"เพิ่ม {target.name} แล้ว")
        except Exception as exc:
            messagebox.showerror("เพิ่มไฟล์เสียงไม่สำเร็จ", str(exc))

    def _randomize_audio_choices(self):
        backgrounds, effects = self._audio_assets("background"), self._audio_assets("sfx")
        if backgrounds:
            self.audio_background_file.set(random.choice(backgrounds).name)
        if effects:
            self.audio_sfx_file.set(random.choice(effects).name)
        self.audio_status.set("สุ่มตัวเลือกใหม่แล้ว • กดสร้างวิดีโอได้เลย")
        self._save_audio_options()

    def _load_audio_job(self):
        job_id = self.audio_job_id.get().strip()
        job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
        if not job:
            return
        state = "ผสมเสียงแล้ว" if job.get("audio_mix_status") == "ready" else "พร้อมผสมเสียง"
        self.audio_status.set(f"{job_id} • {state}")

    def _audio_source(self, job):
        folder = self.products.root / job["id"]
        relative = job.get("video_without_audio_mix_path") or job.get("subtitle_video_path") or job.get("video_path") or ""
        source = folder / str(relative)
        if not source.is_file():
            raise ValueError("Job นี้ยังไม่มีวิดีโอพร้อมใช้งาน")
        return source

    def _selected_audio_files(self, kind, selected_name, selected_mode):
        files = self._audio_assets(kind)
        if kind == "background" and self.cfg.get("audio_background_selection") is not None:
            from core.music_library import selected_paths
            return selected_paths(files, self.cfg["audio_background_selection"])
        if selected_mode == "selected" and selected_name != "สุ่มจากคลัง":
            selected = next((path for path in files if path.name == selected_name), None)
            if not selected:
                raise ValueError("ไม่พบไฟล์เสียงที่เลือก")
            return [selected]
        return files

    @uses_job_files(lambda app, job_id, **kwargs: job_id)
    def _maybe_mix_audio(self, job_id, force=False):
        if not job_id or self._audio_render_active:
            return
        job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
        if not job or job.get("video_status") != "ready":
            if force:
                messagebox.showinfo("ยังผสมเสียงไม่ได้", "กรุณาเลือก Product Job ที่มีวิดีโอก่อน")
            return
        if not force and job.get("audio_mix_status") == "ready":
            return
        if not self.audio_background_enabled.get() and not self.audio_sfx_enabled.get():
            return
        try:
            settings = self._save_audio_options() or {}
            source = self._audio_source(job)
            bg_mode = self._background_mode_key(self.audio_background_mode.get())
            sfx_mode = self._sfx_mode_key(self.audio_sfx_mode.get()) if self.audio_sfx_enabled.get() else "off"
            backgrounds = self._selected_audio_files("background", self.audio_background_file.get(), bg_mode) if self.audio_background_enabled.get() else []
            effects = self._selected_audio_files("sfx", self.audio_sfx_file.get(), sfx_mode) if self.audio_sfx_enabled.get() else []
            subtitle = self.products.root / job_id / "captions" / "subtitle.srt"
            cue_times = AudioMixer.cue_times(subtitle)
            output = self.products.root / job_id / "videos" / "final_with_audio.mp4"
            options = {
                "background_files": backgrounds, "background_mode": bg_mode,
                "music_track_count": self.cfg.get("audio_background_track_count"),
                "background_volume": float(self.audio_background_volume.get()) / 100,
                "music_segment_max_sec": float(self.audio_background_segment_max.get()),
                "music_duck_ratio": float(self.audio_background_duck_percent.get()) / 100,
                "sfx_files": effects, "sfx_mode": sfx_mode, "sfx_volume": float(self.audio_sfx_volume.get()) / 100,
                "cue_times": cue_times, "min_sfx_interval": float(self.audio_sfx_min_interval.get()),
                "max_sfx_count": int(self.audio_sfx_max_count.get()), "seed": f"{job_id}-{time.time_ns() if force else 'auto'}",
            }
            self._audio_render_active = job_id
            self.audio_status.set(f"{job_id} • กำลังยำเพลงและวางเสียงข้อความ")
            guarded_thread(self, job_id, self._audio_mix_worker, args=(job_id, source, output, settings, options), daemon=True)
        except Exception as exc:
            messagebox.showerror("เตรียมเสียงประกอบไม่สำเร็จ", str(exc))

    def _audio_mix_worker(self, job_id, source, output, settings, options):
        try:
            plan = AudioMixer(self.cfg.get("ffmpeg_path", "")).render(source, output, **options)
            job = self.products.save_audio_mix_result(job_id, output, source, settings, plan)
            self.events.put(("audio_mix_ready", (job, plan)))
        except Exception as exc:
            self.events.put(("audio_mix_error", (job_id, str(exc))))

    def _open_audio_folder(self):
        job_id = self.audio_job_id.get().strip()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self._open_folder(self.products.root / job_id / "videos")

    def _build_logo(self):
        page = self._page("logo")
        self._heading(page, "โลโก้บนวิดีโอ", "เลือกโลโก้ ปรับความทึบ ขนาด ตำแหน่ง และดูตัวอย่างก่อนสร้างไฟล์ Final")

        selector = self._panel(page, fill="x", pady=(0, 12))
        tk.Label(selector, text="Product Job", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 10)).pack(side="left", padx=(15, 8), pady=12)
        self.logo_job_combo = ttk.Combobox(selector, textvariable=self.logo_job_id, state="readonly", width=25)
        self.logo_job_combo.pack(side="left", padx=(0, 8), pady=10)
        self.logo_job_combo.bind("<<ComboboxSelected>>", lambda event: self._load_logo_job())
        tk.Label(selector, textvariable=self.logo_status, bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI", 9)).pack(side="left", padx=8)
        ttk.Button(selector, text="เปิดโฟลเดอร์วิดีโอ", style="Ghost.TButton", command=self._open_logo_folder).pack(side="right", padx=(5, 12), pady=7)

        content = tk.Frame(page, bg=COLORS["bg"]); content.pack(fill="both", expand=True)
        settings = self._panel(content, side="left", fill="y")
        settings.configure(width=370); settings.pack_propagate(False)
        tk.Label(settings, text="ตั้งค่าโลโก้", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=16, pady=(16, 10))

        tk.Label(settings, text="ไฟล์โลโก้ PNG / JPG / WEBP", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=16)
        logo_row = tk.Frame(settings, bg=COLORS["panel"]); logo_row.pack(fill="x", padx=16, pady=(5, 13))
        tk.Entry(logo_row, textvariable=self.logo_file, state="readonly", readonlybackground="#080D1E", fg=COLORS["muted"], relief="flat").pack(side="left", fill="x", expand=True, ipady=7)
        ttk.Button(logo_row, text="เลือก", style="Ghost.TButton", command=self._select_logo_file).pack(side="left", padx=(6, 0))

        self._logo_slider(settings, "ความทึบ / ความโปร่งแสง", self.logo_opacity, self.logo_opacity_text, 5, 100, 1)
        self._logo_slider(settings, "ขนาดเทียบความกว้างวิดีโอ", self.logo_size, self.logo_size_text, 3, 60, 1)

        tk.Label(settings, text="ตำแหน่ง", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=16, pady=(2, 4))
        position = ttk.Combobox(settings, textvariable=self.logo_position, values=list(POSITIONS.values()), state="readonly")
        position.pack(fill="x", padx=16, pady=(0, 12)); position.bind("<<ComboboxSelected>>", lambda event: self._update_logo_preview_from_cache())

        self._logo_slider(settings, "ระยะห่างจากขอบ", self.logo_margin, self.logo_margin_text, 0, 200, 2)

        actions = tk.Frame(settings, bg=COLORS["panel"]); actions.pack(side="bottom", fill="x", padx=16, pady=16)
        ttk.Button(actions, text="ดูตัวอย่าง", style="Primary.TButton", command=self._preview_logo).pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="สร้างวิดีโอใส่โลโก้", style="Accent.TButton", command=self._render_logo_video).pack(fill="x")

        preview_panel = self._panel(content, side="left", fill="both", expand=True, padx=(12, 0))
        preview_title = tk.Frame(preview_panel, bg=COLORS["panel"]); preview_title.pack(fill="x", padx=16, pady=(15, 8))
        tk.Label(preview_title, text="ตัวอย่างองค์ประกอบ", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 11)).pack(side="left")
        tk.Label(preview_title, text="ไฟล์ต้นฉบับจะไม่ถูกเขียนทับ", bg=COLORS["panel"], fg=COLORS["green"], font=("Segoe UI", 8)).pack(side="right")
        self.logo_preview = tk.Label(preview_panel, text="ยังไม่มีภาพตัวอย่าง", bg="#080D1E", fg=COLORS["muted"], font=("Segoe UI", 11))
        self.logo_preview.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._update_logo_labels()

    def _logo_slider(self, parent, title, variable, textvariable, minimum, maximum, resolution):
        row = tk.Frame(parent, bg=COLORS["panel"]); row.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(row, text=title, bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Label(row, textvariable=textvariable, bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI", 9)).pack(side="right")
        scale = tk.Scale(parent, from_=minimum, to=maximum, resolution=resolution, orient="horizontal", variable=variable, command=lambda value: self._logo_scale_changed(), showvalue=False, bg=COLORS["panel"], fg=COLORS["text"], troughcolor="#25345C", activebackground=COLORS["purple"], highlightthickness=0, bd=0)
        scale.pack(fill="x", padx=16, pady=(0, 8))

    def _build_video_settings(self):
        page = self._page("video")
        self._heading(page, "ตั้งค่าวิดีโอ", "เลือกผู้สร้างวิดีโอสินค้า และกำหนดความละเอียด ความลื่นไหล และคุณภาพไฟล์")

        summary = self._panel(page, fill="x", pady=(0, 12))
        tk.Label(summary, text="VIDEO OUTPUT", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=18, pady=(15, 4))
        tk.Label(summary, text="ค่าชุดนี้ใช้กับการประกอบวิดีโอรอบถัดไป รวมถึงการกดทำต่อจาก Checkpoint", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=18)
        tk.Label(summary, textvariable=self.video_settings_status, bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(4, 15))

        actions = tk.Frame(page, bg=COLORS["bg"]); actions.pack(side="bottom", fill="x", pady=(12, 0))
        ttk.Button(actions, text="บันทึกและใช้กับงานถัดไป", style="PrimaryLarge.TButton", command=self._save_video_options).pack(side="right")
        ttk.Button(actions, text="คืนค่าแนะนำ 720p / 30 FPS", style="Ghost.TButton", command=self._reset_video_options).pack(side="right", padx=8)
        ttk.Button(actions, text="จัดการไฟล์เรนเดอร์", style="Ghost.TButton", command=lambda: self._show_page("library")).pack(side="left")
        self._update_video_setting_labels()

        content = tk.Frame(page, bg=COLORS["bg"]); content.pack(fill="both", expand=True)
        _basic_viewport, basic = self._scroll_panel(content, side="left", fill="both", expand=True, padx=(0, 6))
        _smooth_viewport, smooth = self._scroll_panel(content, side="left", fill="both", expand=True, padx=(6, 0))

        tk.Label(basic, text="ความคมชัดและเฟรมเรต", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=18, pady=(18, 5))
        tk.Label(basic, text="720p / 30 FPS เหมาะกับงานทั่วไป • 1080p / 60 FPS ใช้เวลานานและไฟล์ใหญ่ขึ้น", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=400, justify="left").pack(anchor="w", padx=18, pady=(0, 16))
        tk.Label(basic, text="ผู้สร้างวิดีโอสินค้า 3 ช็อต", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=18)
        ttk.Combobox(basic, textvariable=self.video_ai_provider, values=tuple(VIDEO_AI_PROVIDERS), state="readonly", style="Dark.TCombobox").pack(fill="x", padx=18, pady=(5, 14), ipady=3)
        tk.Label(basic, text="ความละเอียดแนวตั้ง 9:16", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=18)
        ttk.Combobox(basic, textvariable=self.video_resolution, values=tuple(VIDEO_RESOLUTIONS), state="readonly", style="Dark.TCombobox").pack(fill="x", padx=18, pady=(5, 14), ipady=3)
        tk.Label(basic, text="เฟรมต่อวินาที (FPS)", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=18)
        ttk.Combobox(basic, textvariable=self.video_fps, values=("0", "24", "30", "50", "60"), state="readonly", style="Dark.TCombobox").pack(fill="x", padx=18, pady=(5, 14), ipady=3)
        ttk.Label(basic, text='0 = ตามต้นฉบับ • ตัวเข้ารหัสสำหรับงานใหม่', style='Dark.TLabel').pack(anchor='w', padx=18)
        ttk.Combobox(basic, textvariable=self.video_encoder, values=('auto', 'gpu', 'cpu'), state='readonly', style='Dark.TCombobox').pack(fill='x', padx=18, pady=(5,14))
        tk.Label(basic, text="คุณภาพการเข้ารหัส", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=18)
        ttk.Combobox(basic, textvariable=self.video_quality, values=tuple(VIDEO_QUALITIES), state="readonly", style="Dark.TCombobox").pack(fill="x", padx=18, pady=(5, 14), ipady=3)

        tk.Label(smooth, text="การเคลื่อนไหวและความสมูท", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=18, pady=(18, 5))
        tk.Label(smooth, text="ใช้ Ease-in/Ease-out และ Crossfade ระหว่างฉาก โดยไม่กระพริบดำ", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=400, justify="left").pack(anchor="w", padx=18, pady=(0, 16))
        self.video_motion_label = tk.StringVar()
        self.video_transition_label = tk.StringVar()
        motion_head = tk.Frame(smooth, bg=COLORS["panel"]); motion_head.pack(fill="x", padx=18)
        tk.Label(motion_head, text="ระดับการแพนและซูม", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Label(motion_head, textvariable=self.video_motion_label, bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI", 9)).pack(side="right")
        tk.Scale(smooth, from_=0, to=150, resolution=5, orient="horizontal", variable=self.video_motion_strength, command=lambda value: self._update_video_setting_labels(), showvalue=False, bg=COLORS["panel"], troughcolor="#25345C", activebackground=COLORS["purple"], highlightthickness=0, bd=0).pack(fill="x", padx=18, pady=(4, 16))
        transition_head = tk.Frame(smooth, bg=COLORS["panel"]); transition_head.pack(fill="x", padx=18)
        tk.Label(transition_head, text="Crossfade ระหว่างฉาก", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Label(transition_head, textvariable=self.video_transition_label, bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI", 9)).pack(side="right")
        tk.Scale(smooth, from_=0, to=600, resolution=20, orient="horizontal", variable=self.video_transition_ms, command=lambda value: self._update_video_setting_labels(), showvalue=False, bg=COLORS["panel"], troughcolor="#25345C", activebackground=COLORS["purple"], highlightthickness=0, bd=0).pack(fill="x", padx=18, pady=(4, 16))
        tk.Label(smooth, text="แนะนำ 180–300 ms เพื่อให้ภาพต่อเนื่องแต่ยังตัดต่อกระชับ", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=18)


    def _update_video_setting_labels(self):
        if hasattr(self, "video_motion_label"):
            self.video_motion_label.set(f"{int(self.video_motion_strength.get())}%")
        if hasattr(self, "video_transition_label"):
            self.video_transition_label.set(f"{int(self.video_transition_ms.get())} ms")

    def _image_provider_key(self):
        return IMAGE_AI_PROVIDERS.get(self.image_ai_provider.get(), "chatgpt")

    @staticmethod
    def _story_video_mode_key(selected_label="", context=None):
        return story_video_mode_key(selected_label, context, STORY_VIDEO_MODES)

    def _ai_web_model_key(self, provider=""):
        provider = str(provider or self._image_provider_key()).strip().lower()
        source = self.gemini_web_model if provider == "gemini" else self.chatgpt_web_model
        return normalize_ai_web_model(provider, source.get())

    def _set_ai_web_model(self, provider, model, persist=False):
        provider = str(provider or "chatgpt").strip().lower()
        model = normalize_ai_web_model(provider, model)
        target = self.gemini_web_model if provider == "gemini" else self.chatgpt_web_model
        target.set(model)
        if persist:
            key = "gemini_web_model" if provider == "gemini" else "chatgpt_web_model"
            self.cfg[key] = model
            save_video_settings({key: model})
        return model

    def _image_provider_changed(self):
        provider = self._image_provider_key()
        self.cfg["image_ai_provider"] = provider
        save_video_settings({"image_ai_provider": provider})
        self.story_provider_note.set(f"แหล่งภาพ: {self.image_ai_provider.get()} ผ่าน Chrome\nStory เลือก Motion ในเครื่องหรือ Google Flow ทุกฉากได้")
        self.status.set(f"ผู้สร้างภาพ • {self.image_ai_provider.get()} • ใช้กับงานถัดไป")

    def _video_provider_key(self):
        return VIDEO_AI_PROVIDERS.get(self.video_ai_provider.get(), "flow")

    def _video_provider_label(self, provider=""):
        return "Meta AI (ทดลอง)" if provider == 'meta_ai' else "Google Flow"

    def _video_render_settings(self):
        return video_render_settings(self.cfg, VIDEO_RESOLUTIONS)

    def _save_video_options(self):
        try:
            values = {
                "image_ai_provider": self._image_provider_key(),
                "chatgpt_web_model": self._ai_web_model_key("chatgpt"),
                "gemini_web_model": self._ai_web_model_key("gemini"),
                "video_ai_provider": self._video_provider_key(),
                "video_resolution": VIDEO_RESOLUTIONS[self.video_resolution.get()],
                "video_fps": int(self.video_fps.get()),
                'video_encoder': self.video_encoder.get(),
                "video_quality": VIDEO_QUALITIES[self.video_quality.get()],
                "video_motion_strength": round(float(self.video_motion_strength.get()) / 100, 2),
                "video_transition_sec": round(float(self.video_transition_ms.get()) / 1000, 3),
            }
            save_video_settings(values)
            self.cfg.update(values)
            settings = self._video_render_settings()
            self.video_settings_status.set(f"บันทึกแล้ว • {settings['width']}×{settings['height']} • {settings['fps']} FPS • Crossfade {round(settings['transition_sec']*1000)} ms")
            self.status.set("บันทึกการตั้งค่าวิดีโอแล้ว")
            self._write_console(f"VIDEO SETTINGS • {settings['width']}x{settings['height']} • {settings['fps']} FPS • CRF {settings['crf']}", "success")
        except Exception as exc:
            messagebox.showerror("บันทึกการตั้งค่าวิดีโอไม่สำเร็จ", str(exc))

    def _reset_video_options(self):
        self.video_resolution.set("720p HD • 720 × 1280")
        self.video_fps.set("30")
        self.video_encoder.set('auto')
        self.video_quality.set("คมชัดสูง • แนะนำ")
        self.video_motion_strength.set(100)
        self.video_transition_ms.set(220)
        self._update_video_setting_labels()
        self._save_video_options()

    def _build_video_library(self):
        page = self._page("library")
        self._heading(page, "คลังวิดีโอ", "รวมเฉพาะผลงานหลักที่ทำเสร็จแล้ว พร้อมเปิดดูและนำไฟล์ไปใช้งาน")
        toolbar = self._panel(page, fill="x", pady=(0, 12))
        open_actions = tk.Frame(toolbar, bg=COLORS["panel"]); open_actions.pack(fill="x", padx=10, pady=(8, 3))
        tk.Label(open_actions, text="ผลงาน", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 8), width=10, anchor="w").pack(side="left", padx=(4, 2))
        ttk.Button(open_actions, text="ดูรายละเอียดผลงาน", style="Primary.TButton", command=self._show_selected_library_detail).pack(side="left", padx=3)
        ttk.Button(open_actions, text="เปิดดูวิดีโอ", style="Ghost.TButton", command=self._open_library_video).pack(side="left", padx=3)
        ttk.Button(open_actions, text="เปิดโฟลเดอร์", style="Ghost.TButton", command=self._open_library_folder).pack(side="left", padx=3)
        ttk.Button(open_actions, text="รีเฟรช", style="Ghost.TButton", command=self._refresh_video_library).pack(side="left", padx=3)
        ttk.Button(open_actions, text="จัดการโฟลเดอร์โปรเจกต์", style="Accent.TButton", command=self._show_project_manager).pack(side="left", padx=3)

        cleanup_actions = tk.Frame(toolbar, bg=COLORS["panel"]); cleanup_actions.pack(fill="x", padx=10, pady=(3, 8))
        tk.Label(cleanup_actions, text="ลบ / เคลียร์", bg=COLORS["panel"], fg=COLORS["danger"], font=("Segoe UI Semibold", 8), width=10, anchor="w").pack(side="left", padx=(4, 2))
        self.library_delete_main_button = tk.Button(cleanup_actions, text="ลบไฟล์หลัก", command=self._delete_library_video, relief="flat", bd=0, bg=COLORS["panel"], fg=COLORS["danger"], activebackground=COLORS["panel_2"], activeforeground="#FF8BA0", font=("Segoe UI Semibold", 9), padx=10, pady=9, cursor="hand2")
        self.library_delete_main_button.pack(side="left", padx=3)
        self.library_delete_job_button = tk.Button(cleanup_actions, text="ลบเฉพาะวิดีโอหัวข้อนี้", command=self._delete_library_job_renders, relief="flat", bd=0, bg=COLORS["panel"], fg=COLORS["danger"], activebackground=COLORS["panel_2"], activeforeground="#FF8BA0", font=("Segoe UI Semibold", 9), padx=11, pady=9, cursor="hand2")
        self.library_delete_job_button.pack(side="left", padx=3)
        self.library_clear_all_button = tk.Button(cleanup_actions, text="ลบเฉพาะวิดีโอทั้งหมด", command=self._delete_all_library_renders, relief="flat", bd=0, bg="#351929", fg="#FF9AAF", activebackground="#482035", activeforeground="#FFFFFF", font=("Segoe UI Semibold", 9), padx=12, pady=9, cursor="hand2")
        self.library_clear_all_button.pack(side="left", padx=3)
        self.library_delete_completed_button = tk.Button(cleanup_actions, text="ลบโปรเจกต์ที่เสร็จแล้วทั้งหมด", command=self._delete_completed_projects, relief="flat", bd=0, bg="#681B2E", fg="#FFFFFF", activebackground="#84243C", activeforeground="#FFFFFF", font=("Segoe UI Semibold", 9), padx=12, pady=9, cursor="hand2")
        self.library_delete_completed_button.pack(side="right", padx=(3, 4))

        info = tk.Frame(page, bg="#111A34", highlightbackground=COLORS["line"], highlightthickness=1)
        info.pack(fill="x", pady=(0, 12))
        tk.Label(info, textvariable=self.library_status, bg="#111A34", fg=COLORS["cyan"], font=("Segoe UI Semibold", 9)).pack(side="left", padx=14, pady=10)
        tk.Label(info, text="แสดงเฉพาะไฟล์หลักที่พร้อมใช้", bg="#111A34", fg=COLORS["muted"], font=("Segoe UI", 9)).pack(side="right", padx=14)

        holder = self._panel(page, fill="both", expand=True)
        columns = ("type", "title", "file", "job", "updated", "size")
        self.library_table = ttk.Treeview(holder, columns=columns, show="headings", style="Dark.Treeview", selectmode="browse")
        for key, title, width in zip(columns, ("ประเภท", "ชื่อผลงาน", "ไฟล์หลัก", "รหัสงาน", "เสร็จล่าสุด", "ขนาด"), (120, 275, 180, 165, 145, 78)):
            self.library_table.heading(key, text=title)
            self.library_table.column(key, width=width, anchor="w", stretch=key == "title")
        self.library_table.pack(fill="both", expand=True, padx=10, pady=10)
        self.library_table.bind("<ButtonRelease-1>", self._library_table_clicked)
        self.library_table.bind("<Double-1>", lambda event: self._show_selected_library_detail())
        self.library_table.bind("<Return>", lambda event: self._show_selected_library_detail())

    def _selected_library_item(self, show_message=True):
        if not hasattr(self, "library_table"):
            return None
        selected = self.library_table.selection()
        item = self._library_items.get(selected[0]) if selected else None
        if not item and show_message:
            messagebox.showinfo("เลือกวิดีโอ", "กรุณาเลือกผลงานหนึ่งรายการก่อน")
        return item

    def _library_table_clicked(self, event):
        row_id = self.library_table.identify_row(event.y)
        region = self.library_table.identify_region(event.x, event.y)
        if not row_id or region not in {"cell", "tree"}:
            return
        self.library_table.selection_set(row_id)
        self.library_table.focus(row_id)
        self.root.after_idle(lambda selected_item=row_id: self._show_library_detail(selected_item))

    def _show_selected_library_detail(self):
        item = self._selected_library_item()
        if item:
            self._show_library_detail(item["item_id"])

    def _show_library_detail(self, item_id):
        try:
            detail = self.video_library.item_detail(item_id)
        except Exception as exc:
            self._refresh_video_library()
            messagebox.showerror("เปิดรายละเอียดไม่ได้", str(exc))
            return

        previous = self._library_detail_dialog
        if previous and previous.winfo_exists():
            previous.destroy()

        video_path = Path(detail["path"])
        job_folder = Path(detail["job_folder"])
        affiliate_link = detail["affiliate_link"]
        dialog = tk.Toplevel(self.root)
        self._library_detail_dialog = dialog
        dialog.title(f"รายละเอียดผลงาน • {detail['job_id']}")
        dialog.geometry("980x740")
        dialog.minsize(860, 660)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)

        header = tk.Frame(dialog, bg=COLORS["sidebar"], highlightbackground=COLORS["line"], highlightthickness=1)
        header.pack(fill="x")
        header_copy = tk.Frame(header, bg=COLORS["sidebar"])
        header_copy.pack(side="left", fill="x", expand=True, padx=22, pady=15)
        tk.Label(header_copy, text="VIDEO LIBRARY • READY", bg=COLORS["sidebar"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 8)).pack(anchor="w")
        tk.Label(header_copy, text=detail["title"], bg=COLORS["sidebar"], fg=COLORS["text"], font=("Segoe UI Semibold", 16), wraplength=680, justify="left").pack(anchor="w", pady=(4, 2))
        tk.Label(header_copy, text=f"{detail['kind_label']}  •  {detail['job_id']}  •  {detail['file_name']}", bg=COLORS["sidebar"], fg=COLORS["subtle"], font=("Segoe UI", 8)).pack(anchor="w")
        tk.Label(header, text="●  พร้อมใช้งาน", bg="#102A28", fg=COLORS["green"], font=("Segoe UI Semibold", 9), padx=13, pady=8).pack(side="right", padx=22)

        body = tk.Frame(dialog, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=18)
        media = tk.Frame(body, bg=COLORS["panel"], width=300, highlightbackground=COLORS["line"], highlightthickness=1)
        media.pack(side="left", fill="y")
        media.pack_propagate(False)
        tk.Label(media, text="ตัวอย่างวิดีโอ", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(17, 3))
        tk.Label(media, text=detail["file_name"], bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=255, justify="left").pack(anchor="w", padx=16)

        def play_video():
            if not video_path.is_file():
                messagebox.showerror("เปิดวิดีโอไม่ได้", "ไม่พบไฟล์วิดีโอหลักแล้ว", parent=dialog)
                return
            os.startfile(str(video_path))
            self.status.set(f"เปิดวิดีโอ • {detail['title']}")

        preview_box = tk.Frame(media, bg="#080D1E", height=320, highlightbackground=COLORS["line_soft"], highlightthickness=1)
        preview_box.pack(fill="x", padx=16, pady=13)
        preview_box.pack_propagate(False)
        preview_button = tk.Button(preview_box, text="▶", command=play_video, bg="#080D1E", fg=COLORS["blue"], activebackground="#101A35", activeforeground=COLORS["cyan"], relief="flat", bd=0, font=("Segoe UI", 48), cursor="hand2")
        preview_button.pack(fill="both", expand=True)
        preview_path = Path(detail["preview_path"]) if detail["preview_path"] else None
        if preview_path and preview_path.is_file():
            try:
                with Image.open(preview_path) as source:
                    preview = source.convert("RGB")
                    preview.thumbnail((255, 290), Image.Resampling.LANCZOS)
                preview_photo = ImageTk.PhotoImage(preview)
                dialog.library_preview_photo = preview_photo
                preview_button.configure(image=preview_photo, text="")
            except Exception:
                pass
        ttk.Button(media, text="▶  เปิดดูวิดีโอ", style="PrimaryLarge.TButton", command=play_video).pack(fill="x", padx=16, pady=(0, 8))
        ttk.Button(media, text="เปิดโฟลเดอร์ผลงาน", style="Ghost.TButton", command=lambda: self._open_folder(job_folder)).pack(fill="x", padx=16)

        content = tk.Frame(body, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        content.pack(side="left", fill="both", expand=True, padx=(14, 0))

        def copy_value(value, label):
            if not value:
                messagebox.showwarning("ยังไม่มีข้อมูล", f"งานนี้ยังไม่มี{label}", parent=dialog)
                return
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.status.set(f"คัดลอก{label}แล้ว")

        def field_header(label, color, button_text, value):
            row = tk.Frame(content, bg=COLORS["panel"])
            row.pack(fill="x", padx=18, pady=(9, 4))
            tk.Label(row, text=label, bg=COLORS["panel"], fg=color, font=("Segoe UI Semibold", 9)).pack(side="left")
            ttk.Button(row, text=button_text, style="Ghost.TButton", command=lambda: copy_value(value, label)).pack(side="right")

        field_header("ชื่อคลิป", COLORS["cyan"], "คัดลอกชื่อ", detail["title"])
        tk.Label(content, text=detail["title"], bg=COLORS["panel_3"], fg=COLORS["text"], font=("Segoe UI Semibold", 11), wraplength=555, justify="left", padx=12, pady=9).pack(fill="x", padx=18)

        field_header("คำอธิบาย / แคปชั่นโพสต์", COLORS["purple"], "คัดลอกคำอธิบาย", detail["description"])
        description_box = tk.Text(content, height=5, bg=COLORS["panel_3"], fg=COLORS["text"], relief="flat", wrap="word", font=("Segoe UI", 10), padx=12, pady=9)
        description_box.pack(fill="x", padx=18)
        description_box.insert("1.0", detail["description"] or "ยังไม่มีคำอธิบาย")
        description_box.configure(state="disabled")

        field_header("แฮชแท็ก", COLORS["orange"], "คัดลอกแฮชแท็ก", detail["hashtags"])
        hashtag_box = tk.Text(content, height=2, bg=COLORS["panel_3"], fg=COLORS["orange"], relief="flat", wrap="word", font=("Segoe UI Semibold", 9), padx=12, pady=8)
        hashtag_box.pack(fill="x", padx=18)
        hashtag_box.insert("1.0", detail["hashtags"] or "ยังไม่มีแฮชแท็ก")
        hashtag_box.configure(state="disabled")

        field_header("ลิงก์", COLORS["green"], "คัดลอกลิงก์", affiliate_link)
        link_box = tk.Entry(content, bg=COLORS["panel_3"], fg=COLORS["text"], readonlybackground=COLORS["panel_3"], relief="flat", font=("Segoe UI", 9))
        link_box.pack(fill="x", padx=18, ipady=8)
        link_box.insert(0, affiliate_link or "ไม่มีลิงก์สินค้าในผลงานนี้")
        link_box.configure(state="readonly")

        actions = tk.Frame(content, bg=COLORS["panel"])
        actions.pack(fill="x", padx=18, pady=10)
        ttk.Button(actions, text="คัดลอกข้อมูลโพสต์ทั้งหมด", style="Primary.TButton", command=lambda: copy_value(detail["post_text"], "ข้อมูลโพสต์ทั้งหมด")).pack(side="left")
        open_link = ttk.Button(actions, text="เปิดลิงก์", style="Accent.TButton", command=lambda: self._open_url(affiliate_link))
        open_link.pack(side="left", padx=7)
        if not affiliate_link:
            open_link.configure(state="disabled")
        ttk.Button(actions, text="ปิด", style="Ghost.TButton", command=dialog.destroy).pack(side="right")

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()

    def _refresh_video_library(self, preferred_item_id=""):
        if not hasattr(self, "library_table"):
            return
        selected = self.library_table.selection()
        previous_latest = getattr(self, "_library_latest_item_id", "")
        for row in self.library_table.get_children():
            self.library_table.delete(row)
        self._library_items = {}
        items = self.video_library.list_items()
        for item in items:
            item_id = item["item_id"]
            self._library_items[item_id] = item
            updated = str(item.get("updated_at") or "—").replace("T", " ")
            size = f"{item['size_bytes'] / (1024 * 1024):.1f} MB"
            self.library_table.insert("", "end", iid=item_id, values=(item["kind_label"], item["title"], item["file_name"], item["job_id"], updated, size))
        latest_item_id = items[0]["item_id"] if items else ""
        if preferred_item_id and preferred_item_id in self._library_items:
            self.library_table.selection_set(preferred_item_id)
            self.library_table.focus(preferred_item_id)
            self.library_table.see(preferred_item_id)
        elif previous_latest and latest_item_id != previous_latest and latest_item_id in self._library_items:
            self.library_table.selection_set(latest_item_id)
            self.library_table.focus(latest_item_id)
            self.library_table.see(latest_item_id)
        elif selected and selected[0] in self._library_items:
            self.library_table.selection_set(selected[0])
            self.library_table.focus(selected[0])
        elif items:
            self.library_table.selection_set(items[0]["item_id"])
            self.library_table.focus(items[0]["item_id"])
        if items:
            self.library_status.set(f"พร้อมใช้ {len(items)} วิดีโอ • คลิกแถวเพื่อดูรายละเอียดและเปิดคลิป")
        else:
            self.library_status.set("ยังไม่มีวิดีโอที่ทำเสร็จ")
        self._library_latest_item_id = latest_item_id

    def _open_library_video(self):
        item = self._selected_library_item()
        if not item:
            return
        path = Path(item["path"])
        if not path.is_file():
            self._refresh_video_library()
            messagebox.showerror("เปิดวิดีโอไม่ได้", "ไม่พบไฟล์นี้แล้ว กรุณากดรีเฟรช")
            return
        os.startfile(str(path))
        self.status.set(f"เปิดวิดีโอ • {item['title']}")

    def _open_library_folder(self):
        item = self._selected_library_item()
        if not item:
            return
        self._open_folder(item["folder"])
        self.status.set(f"เปิดโฟลเดอร์ • {item['job_id']}")

    def _delete_library_video(self):
        item = self._selected_library_item()
        if not item:
            return
        confirmed = messagebox.askyesno(
            "ลบวิดีโอผลงาน",
            f"ต้องการลบไฟล์ผลงานหลักนี้หรือไม่?\n\n{item['title']}\n{Path(item['path']).name}\n\nรูป บท เสียง และข้อมูลโปรเจกต์จะยังอยู่ครบ\nวิดีโอจะถูกย้ายไปถังรีไซเคิลของ Windows",
            icon="warning",
        )
        if not confirmed:
            return
        try:
            deleted = self.video_library.delete_item(item["item_id"])
            self._refresh()
            self.status.set(f"ย้ายวิดีโอไปถังรีไซเคิลแล้ว • {deleted['job_id']}")
            self._write_console(f"{deleted['job_id']} • ลบเฉพาะผลงานหลัก • เก็บไฟล์โปรเจกต์ไว้", "success")
            messagebox.showinfo("ลบวิดีโอแล้ว", "ย้ายไฟล์ไปถังรีไซเคิลของ Windows แล้ว\nรูป บท เสียง และไฟล์โปรเจกต์อื่นยังอยู่ครบ")
        except Exception as exc:
            self._write_console(f"VIDEO LIBRARY DELETE • {exc}", "error")
            messagebox.showerror("ลบวิดีโอไม่สำเร็จ", str(exc))

    @staticmethod
    def _format_file_size(size_bytes):
        size = max(0, int(size_bytes or 0))
        if size >= 1024 ** 3:
            return f"{size / (1024 ** 3):.2f} GB"
        return f"{size / (1024 ** 2):.1f} MB"

    def _show_project_manager(self):
        dialog = self._project_manager_dialog
        if dialog and dialog.winfo_exists():
            dialog.deiconify()
            dialog.lift()
            dialog.focus_force()
            self._refresh_project_manager()
            return

        dialog = tk.Toplevel(self.root)
        self._project_manager_dialog = dialog
        dialog.title("จัดการโฟลเดอร์โปรเจกต์")
        dialog.geometry("980x640")
        dialog.minsize(840, 540)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", self._close_project_manager)

        header = tk.Frame(dialog, bg=COLORS["sidebar"], highlightbackground=COLORS["line"], highlightthickness=1)
        header.pack(fill="x")
        header_copy = tk.Frame(header, bg=COLORS["sidebar"]); header_copy.pack(side="left", fill="x", expand=True, padx=22, pady=15)
        tk.Label(header_copy, text="PROJECT FOLDER MANAGER", bg=COLORS["sidebar"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 8)).pack(anchor="w")
        tk.Label(header_copy, text="ลบงานเก่าแล้วเอาแถว Job ออกจากโปรแกรม", bg=COLORS["sidebar"], fg=COLORS["text"], font=("Segoe UI Semibold", 16)).pack(anchor="w", pady=(3, 2))
        tk.Label(header_copy, text="ลบทั้งโฟลเดอร์: รูป บทพูด เสียง ซับ วิดีโอ และข้อมูล Job • กู้คืนได้จากถังขยะ Windows", bg=COLORS["sidebar"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w")

        warning = tk.Frame(dialog, bg="#351929", highlightbackground="#6E2940", highlightthickness=1)
        warning.pack(fill="x", padx=16, pady=(14, 10))
        tk.Label(warning, text="สำคัญ", bg="#351929", fg="#FF9AAF", font=("Segoe UI Semibold", 9)).pack(side="left", padx=(13, 8), pady=9)
        tk.Label(warning, text="ปุ่มลบโปรเจกต์จะทำให้หัวข้อและข้อความ JOB / สินค้า / Product ID / ลิงก์ / AI หายจากรายการหลังรีเฟรช", bg="#351929", fg="#FFDDE4", font=("Segoe UI", 9)).pack(side="left", pady=9)

        self.project_manager_status = tk.StringVar(value="กำลังอ่านโฟลเดอร์โปรเจกต์...")
        tk.Label(dialog, textvariable=self.project_manager_status, bg=COLORS["bg"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 9), anchor="w").pack(fill="x", padx=18, pady=(0, 7))

        actions = tk.Frame(dialog, bg=COLORS["bg"]); actions.pack(side="bottom", fill="x", padx=16, pady=14)
        ttk.Button(actions, text="เปิดโฟลเดอร์", style="Ghost.TButton", command=self._open_selected_project_folder).pack(side="left", padx=(0, 5))
        self.project_refresh_button = ttk.Button(actions, text="รีเฟรช", style="Ghost.TButton", command=self._refresh_project_manager)
        self.project_refresh_button.pack(side="left", padx=5)
        self.project_delete_selected_button = tk.Button(actions, text="ลบโปรเจกต์ที่เลือก", command=self._delete_selected_project_from_manager, relief="flat", bd=0, bg="#551827", fg="#FFFFFF", activebackground="#722238", activeforeground="#FFFFFF", font=("Segoe UI Semibold", 9), padx=14, pady=10, cursor="hand2")
        self.project_delete_selected_button.pack(side="right", padx=(5, 0))
        self.project_delete_completed_button = tk.Button(actions, text="ลบโปรเจกต์ที่เสร็จแล้วทั้งหมด", command=self._delete_completed_projects, relief="flat", bd=0, bg="#681B2E", fg="#FFFFFF", activebackground="#84243C", activeforeground="#FFFFFF", font=("Segoe UI Semibold", 9), padx=14, pady=10, cursor="hand2")
        self.project_delete_completed_button.pack(side="right", padx=5)
        ttk.Button(actions, text="ปิด", style="Ghost.TButton", command=self._close_project_manager).pack(side="right", padx=5)

        holder = tk.Frame(dialog, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        holder.pack(fill="both", expand=True, padx=16)
        columns = ("type", "title", "job", "state", "created", "files", "size")
        table = ttk.Treeview(holder, columns=columns, show="headings", style="Dark.Treeview", selectmode="browse")
        self._project_manager_table = table
        for key, title, width in zip(columns, ("ประเภท", "ชื่อโปรเจกต์", "รหัส Job", "สถานะ", "สร้างเมื่อ", "จำนวนไฟล์", "ขนาด"), (115, 250, 165, 95, 145, 75, 80)):
            table.heading(key, text=title)
            table.column(key, width=width, anchor="w", stretch=key == "title")
        table.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=table.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 9), pady=10)
        table.configure(yscrollcommand=scrollbar.set)
        table.bind("<Double-1>", lambda event: self._open_selected_project_folder())
        self._refresh_project_manager()

    def _close_project_manager(self):
        dialog = self._project_manager_dialog
        if dialog and dialog.winfo_exists():
            dialog.destroy()
        self._project_manager_dialog = None
        self._project_manager_table = None
        self._project_manager_items = {}

    def _refresh_project_manager(self, preferred_item_id=""):
        table = self._project_manager_table
        dialog = self._project_manager_dialog
        if not table or not dialog or not dialog.winfo_exists():
            return
        selected = table.selection()
        for row in table.get_children():
            table.delete(row)
        self._project_manager_items = {}
        try:
            summary = self.video_library.project_summary()
        except Exception as exc:
            self.project_manager_status.set(f"อ่านโฟลเดอร์ไม่สำเร็จ • {exc}")
            return
        for item in summary["groups"]:
            item_id = item["item_id"]
            self._project_manager_items[item_id] = item
            created = str(item.get("created_at") or item.get("updated_at") or "—").replace("T", " ")
            state = "เสร็จแล้ว" if item.get("completed") else "กำลังทำ/ค้าง"
            table.insert("", "end", iid=item_id, values=(item["kind_label"], item["title"], item["job_id"], state, created, item["file_count"], self._format_file_size(item["size_bytes"])))
        choice = preferred_item_id if preferred_item_id in self._project_manager_items else (selected[0] if selected and selected[0] in self._project_manager_items else "")
        if not choice and summary["groups"]:
            choice = summary["groups"][0]["item_id"]
        if choice:
            table.selection_set(choice)
            table.focus(choice)
            table.see(choice)
        completed = sum(bool(item.get("completed")) for item in summary["groups"])
        self.project_manager_status.set(f"มี {summary['job_count']} โปรเจกต์ • ทำเสร็จแล้ว {completed} • {summary['file_count']} ไฟล์ • {self._format_file_size(summary['size_bytes'])}")

    def _selected_project_item(self, show_message=True):
        table = self._project_manager_table
        selected = table.selection() if table else ()
        item = self._project_manager_items.get(selected[0]) if selected else None
        if not item and show_message:
            messagebox.showinfo("เลือกโปรเจกต์", "กรุณาเลือกโปรเจกต์หนึ่งรายการก่อน")
        return item

    def _open_selected_project_folder(self):
        item = self._selected_project_item()
        if item:
            self._open_folder(item["folder"])

    def _delete_selected_project_from_manager(self):
        item = self._selected_project_item()
        if item:
            self._confirm_delete_project(item["item_id"], item["title"])

    def _delete_selected_product_project(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        values = self.product_table.item(self.product_table.selection()[0], "values")
        title = values[1] if len(values) > 1 else job_id
        self._confirm_delete_project(f"product:{job_id}", title)

    def _delete_all_product_projects(self):
        if self._project_delete_active:
            return
        try:
            summary = self.video_library.project_summary(kind="product")
        except Exception as exc:
            messagebox.showerror("ตรวจรายการสินค้าไม่สำเร็จ", str(exc))
            return
        if not summary["job_count"]:
            messagebox.showinfo("ไม่มีรายการสินค้า", "ไม่มี Product Job ให้ลบ")
            return
        confirmed = messagebox.askyesno(
            "ลบรายการสินค้าทั้งหมด",
            f"ต้องการลบ Product Job ทั้งหมดจริงหรือไม่?\n\n{summary['job_count']} รายการ • {summary['file_count']} ไฟล์ • {self._format_file_size(summary['size_bytes'])}\n\nทุกแถวในตารางนี้และโฟลเดอร์สินค้าเหล่านี้จะถูกนำออก\nไฟล์ทั้งหมดจะย้ายลงถังขยะ Windows และยังกู้คืนได้",
            icon="warning",
        )
        if confirmed:
            self._start_project_delete("all_products")

    def _delete_selected_story_project(self):
        job_id = self.story_job_id.get().strip()
        if not job_id:
            messagebox.showinfo("เลือก Story", "กรุณาเลือก Story Job ก่อน")
            return
        try:
            story = self.stories.get(job_id)
            title = story.get("video_title") or story.get("topic") or job_id
        except Exception:
            title = job_id
        self._confirm_delete_project(f"story:{job_id}", title)

    def _active_project_ids(self):
        active = set()
        if self._product_pipeline_job_id:
            active.add(f"product:{self._product_pipeline_job_id}")
        if self._story_pipeline_job_id:
            active.add(f"story:{self._story_pipeline_job_id}")
        return active

    def _confirm_delete_project(self, item_id, title=""):
        if self._project_delete_active:
            return
        if item_id in self._active_project_ids():
            messagebox.showwarning("โปรเจกต์กำลังทำงาน", "ยกเลิกหรือรอให้งานนี้หยุดก่อน จึงจะลบทั้งโปรเจกต์ได้")
            return
        try:
            summary = self.video_library.project_summary(item_id=item_id)
        except Exception as exc:
            messagebox.showerror("ตรวจโปรเจกต์ไม่สำเร็จ", str(exc))
            return
        if not summary["groups"]:
            messagebox.showinfo("ไม่พบโปรเจกต์", "โปรเจกต์นี้ถูกลบไปแล้ว")
            self._refresh()
            return
        group = summary["groups"][0]
        display_title = str(title or group.get("title") or group.get("job_id") or "โปรเจกต์ที่เลือก")
        confirmed = messagebox.askyesno(
            "ลบทั้งโปรเจกต์และเอา Job ออกจากรายการ",
            f"ต้องการลบโปรเจกต์นี้จริงหรือไม่?\n\n{display_title}\n{group['job_id']}\n{summary['file_count']} ไฟล์ • {self._format_file_size(summary['size_bytes'])}\n\nรูป บทพูด เสียง ซับ วิดีโอ และข้อมูล Job ทั้งหมดจะถูกย้ายลงถังขยะ Windows\nแถว JOB / สินค้า / Product ID / ลิงก์ / AI จะหายจากโปรแกรม",
            icon="warning",
        )
        if confirmed:
            self._start_project_delete("selected", item_id)

    def _delete_completed_projects(self):
        if self._project_delete_active:
            return
        try:
            summary = self.video_library.project_summary(completed_only=True)
        except Exception as exc:
            messagebox.showerror("ตรวจโปรเจกต์ไม่สำเร็จ", str(exc))
            return
        if not summary["job_count"]:
            messagebox.showinfo("ไม่มีโปรเจกต์ที่เสร็จแล้ว", "ไม่พบโปรเจกต์ที่เสร็จแล้วให้เคลียร์")
            return
        confirmed = messagebox.askyesno(
            "ลบโปรเจกต์ที่เสร็จแล้วทั้งหมด",
            f"ต้องการลบโปรเจกต์ที่เสร็จแล้วทั้งหมดจริงหรือไม่?\n\n{summary['job_count']} โปรเจกต์ • {summary['file_count']} ไฟล์ • {self._format_file_size(summary['size_bytes'])}\n\nโฟลเดอร์ทั้งหมดและแถว Job จะหายจากหน้าสินค้า/Story\nไฟล์จะถูกย้ายลงถังขยะ Windows และยังกู้คืนได้",
            icon="warning",
        )
        if confirmed:
            self._start_project_delete("completed")

    def _set_project_delete_state(self, active, message=""):
        self._project_delete_active = bool(active)
        state = "disabled" if active else "normal"
        for name in ("product_delete_all_button", "library_delete_completed_button", "project_delete_selected_button", "project_delete_completed_button", "project_refresh_button"):
            button = getattr(self, name, None)
            if button and button.winfo_exists():
                button.configure(state=state)
        if message:
            self.status.set(message)
            if hasattr(self, "project_manager_status"):
                self.project_manager_status.set(message)

    def _start_project_delete(self, mode, item_id=""):
        if self._library_delete_active:
            messagebox.showinfo("กำลังเคลียร์วิดีโอ", "รอให้การเคลียร์วิดีโอรอบปัจจุบันเสร็จก่อน")
            return
        try:
            claim = self._reserve_file_deletion({'selected': 'project', 'completed': 'completed_projects'}.get(mode, mode), item_id)
        except ValueError as exc:
            messagebox.showwarning('ยังลบไม่ได้', str(exc))
            return
        delete_label = {
            "selected": "โปรเจกต์ที่เลือก",
            "all_products": "Product Job ทั้งหมด",
            "completed": "โปรเจกต์ที่เสร็จแล้วทั้งหมด",
        }.get(mode, "โปรเจกต์")
        try:
            self._set_project_delete_state(True, "กำลังย้ายทั้งโฟลเดอร์โปรเจกต์ลงถังขยะ Windows...")
            self._write_console(f"PROJECT CLEANUP • เริ่มลบ{delete_label}", "log")
        except BaseException:
            claim.release()
            raise

        def worker():
            try:
                if mode == "selected":
                    result = self.video_library.delete_project(item_id)
                elif mode == "all_products":
                    result = self.video_library.delete_all_projects(kind="product")
                else:
                    result = self.video_library.delete_completed_projects()
                self.events.put(("projects_deleted", result))
            except Exception as exc:
                self.events.put(("project_delete_error", str(exc)))

        try:
            threading.Thread(target=lambda: claim.guard.run_delete(claim, worker), daemon=True).start()
        except BaseException:
            claim.release()
            self._set_project_delete_state(False)
            raise

    def _set_library_delete_state(self, active, message=""):
        self._library_delete_active = bool(active)
        state = "disabled" if active else "normal"
        for name in ("library_delete_main_button", "library_delete_job_button", "library_clear_all_button"):
            button = getattr(self, name, None)
            if button:
                button.configure(state=state)
        if message:
            self.library_status.set(message)
            self.status.set(message)

    def _delete_library_job_renders(self):
        if self._library_delete_active:
            return
        item = self._selected_library_item()
        if not item:
            return
        self._confirm_delete_rendered_job(item["item_id"], item["title"])

    def _confirm_delete_rendered_job(self, item_id, title=""):
        if self._library_delete_active:
            return
        try:
            summary = self.video_library.rendered_summary(item_id)
        except Exception as exc:
            messagebox.showerror("ตรวจไฟล์ไม่สำเร็จ", str(exc))
            return
        if not summary["file_count"]:
            messagebox.showinfo("ไม่มีไฟล์เรนเดอร์", "หัวข้อนี้ไม่มีไฟล์วิดีโอที่เรนเดอร์แล้ว")
            return
        group = summary["groups"][0]
        display_title = str(title or group.get("title") or group.get("job_id") or "หัวข้อที่เลือก")
        confirmed = messagebox.askyesno(
            "ลบไฟล์เรนเดอร์ทั้งหัวข้อ",
            f"ต้องการย้ายไฟล์วิดีโอทั้งหมดของหัวข้อนี้ลงถังขยะ Windows หรือไม่?\n\n{display_title}\n{summary['file_count']} ไฟล์ • {self._format_file_size(summary['size_bytes'])}\n\nรูป บทพูด เสียง และข้อมูลโปรเจกต์จะไม่ถูกลบ",
            icon="warning",
        )
        if confirmed:
            self._start_library_delete("job", item_id)

    def _delete_selected_product_renders(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        values = self.product_table.item(self.product_table.selection()[0], "values")
        title = values[1] if len(values) > 1 else job_id
        self._confirm_delete_rendered_job(f"product:{job_id}", title)

    def _delete_selected_story_renders(self):
        job_id = self.story_job_id.get().strip()
        if not job_id:
            messagebox.showinfo("เลือก Story", "กรุณาเลือก Story Job ก่อน")
            return
        try:
            title = self.stories.get(job_id).get("video_title") or self.stories.get(job_id).get("topic") or job_id
        except Exception:
            title = job_id
        self._confirm_delete_rendered_job(f"story:{job_id}", title)

    def _delete_product_job_renders(self, variable):
        job_id = variable.get().strip()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        try:
            title = self.products.get_job(job_id).get("product_name") or job_id
        except Exception:
            title = job_id
        self._confirm_delete_rendered_job(f"product:{job_id}", title)

    def _delete_all_library_renders(self):
        if self._library_delete_active:
            return
        try:
            summary = self.video_library.rendered_summary()
        except Exception as exc:
            messagebox.showerror("ตรวจไฟล์ไม่สำเร็จ", str(exc))
            return
        if not summary["file_count"]:
            messagebox.showinfo("ไม่มีไฟล์เรนเดอร์", "ไม่มีไฟล์วิดีโอที่เรนเดอร์ให้เคลียร์")
            return
        confirmed = messagebox.askyesno(
            "เคลียร์ไฟล์เรนเดอร์ทั้งหมด",
            f"ต้องการย้ายไฟล์วิดีโอที่เรนเดอร์ทั้งหมดลงถังขยะ Windows จริงหรือไม่?\n\n{summary['job_count']} หัวข้อ • {summary['file_count']} ไฟล์ • {self._format_file_size(summary['size_bytes'])}\n\nรายการในคลังจะถูกล้าง แต่รูป บทพูด เสียง และข้อมูลโปรเจกต์จะยังอยู่ครบ",
            icon="warning",
        )
        if confirmed:
            self._start_library_delete("all")

    def _start_library_delete(self, mode, item_id=""):
        if self._project_delete_active:
            messagebox.showinfo("กำลังลบโปรเจกต์", "รอให้การลบโปรเจกต์รอบปัจจุบันเสร็จก่อน")
            return
        try:
            claim = self._reserve_file_deletion('video' if mode == 'job' else 'all_renders', item_id)
        except ValueError as exc:
            messagebox.showwarning('ยังลบไม่ได้', str(exc))
            return
        try:
            self._set_library_delete_state(True, "กำลังย้ายไฟล์เรนเดอร์ลงถังขยะ Windows...")
            self._write_console(f"VIDEO LIBRARY • เริ่มลบ{'ทั้งหัวข้อ' if mode == 'job' else 'ทั้งหมด'} • ย้ายลงถังขยะ", "log")
        except BaseException:
            claim.release()
            raise

        def worker():
            try:
                result = self.video_library.delete_job_renders(item_id) if mode == "job" else self.video_library.delete_all_renders()
                self.events.put(("library_renders_deleted", result))
            except Exception as exc:
                self.events.put(("library_delete_error", str(exc)))

        try:
            threading.Thread(target=lambda: claim.guard.run_delete(claim, worker), daemon=True).start()
        except BaseException:
            claim.release()
            self._set_library_delete_state(False)
            raise

    def _build_queue(self):
        page = self._page("queue")
        self._heading(page, "คิววิดีโอ Android", "เตรียมวิดีโอ Caption และสินค้า ก่อนส่งเข้าโทรศัพท์")
        toolbar = self._panel(page, fill="x", pady=(0, 12))
        ttk.Button(toolbar, text="+ เพิ่มคลิป", style="Primary.TButton", command=self._add).pack(side="left", padx=(12, 5), pady=9)
        ttk.Button(toolbar, text="เพิ่มโฟลเดอร์", style="Ghost.TButton", command=self._add_folder).pack(side="left", pady=9)
        ttk.Button(toolbar, text="รีเฟรช", style="Ghost.TButton", command=self._refresh).pack(side="left", padx=5, pady=9)
        ttk.Button(toolbar, text="จัดการไฟล์เรนเดอร์", style="Ghost.TButton", command=lambda: self._show_page("library")).pack(side="left", pady=9)
        ttk.Checkbutton(toolbar, text="Dry Run", variable=self.dry, style="Dark.TCheckbutton").pack(side="right", padx=(5, 16))
        ttk.Checkbutton(toolbar, text="ยืนยันก่อนโพสต์", variable=self.confirm, style="Dark.TCheckbutton").pack(side="right", padx=5)

        holder = self._panel(page, fill="both", expand=True)
        columns = ("id", "video", "caption", "product", "status", "step")
        self.queue_table = ttk.Treeview(holder, columns=columns, show="headings", style="Dark.Treeview")
        for key, title, width in zip(columns, ("JOB", "วิดีโอ", "Caption", "สินค้า", "สถานะ", "ขั้นตอน"), (145, 260, 250, 160, 105, 145)):
            self.queue_table.heading(key, text=title); self.queue_table.column(key, width=width, anchor="w")
        self.queue_table.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_logs(self):
        page = self._page("logs")
        self._heading(page, "ระบบและ Log", "ตรวจสถานะเครื่องมือ การเชื่อมต่อ และข้อผิดพลาด")
        actions = self._panel(page, fill="x", pady=(0, 12))
        ttk.Button(actions, text="ตรวจ Connection", style="Primary.TButton", command=lambda: self._bg(self._check)).pack(side="left", padx=(12, 5), pady=9)
        ttk.Button(actions, text="เปิด scrcpy", style="Ghost.TButton", command=self._scrcpy).pack(side="left", pady=9)
        ttk.Button(actions, text="เปิด Shopee", style="Ghost.TButton", command=lambda: self._bg(self._shopee)).pack(side="left", padx=5, pady=9)
        ttk.Button(actions, text="บันทึก UI Hierarchy", style="Ghost.TButton", command=lambda: self._bg(self._dump)).pack(side="left", pady=9)
        ttk.Button(actions, text="เปิดโฟลเดอร์ Log", style="Ghost.TButton", command=lambda: self._open_folder(ROOT / "logs")).pack(side="right", padx=12, pady=9)
        live = tk.Frame(page, bg="#101C32", highlightbackground=COLORS["line"], highlightthickness=1)
        live.pack(fill="x", pady=(0, 12))
        tk.Label(live, text="●  LIVE ACTIVITY", bg="#101C32", fg=COLORS["green"], font=("Segoe UI Semibold", 9)).pack(side="left", padx=(14, 10), pady=10)
        tk.Label(live, textvariable=self.log_activity, bg="#101C32", fg=COLORS["text"], font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True, pady=10)
        tk.Label(live, text="เวลา • Job • เปอร์เซ็นต์ • ขั้นตอน", bg="#101C32", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="right", padx=14)
        console_holder = self._panel(page, fill="both", expand=True)
        self.console = tk.Text(console_holder, bg="#080C19", fg="#CFE2FF", insertbackground="white", selectbackground="#284A91", relief="flat", borderwidth=0, font=("Cascadia Mono", 10), padx=16, pady=14, state="disabled")
        self.console.pack(fill="both", expand=True, padx=1, pady=1)
        self._write_console("SmartFlow AI เริ่มทำงาน • Safe Dry Run เปิดอยู่", "success")

    def _show_page(self, name):
        self.pages[name].tkraise()
        for key, button in self.nav_buttons.items():
            active = key == name
            button.configure(bg="#17213A" if active else COLORS["sidebar"], fg=COLORS["text"] if active else COLORS["muted"])
            if key in self.nav_markers:
                self.nav_markers[key].configure(bg=COLORS["cyan"] if active else COLORS["sidebar"])
        if name == "voice" and self.voice_job_id.get():
            self.root.after_idle(self._load_voice_job)
        if name == "subtitle" and self.subtitle_job_id.get():
            self.root.after_idle(self._load_subtitle_job)
        if name == "audio" and self.audio_job_id.get():
            self.root.after_idle(self._load_audio_job)
        if name == "logo" and self.logo_job_id.get():
            self.root.after_idle(self._load_logo_job)
        if name == "library":
            self.root.after_idle(self._refresh_video_library)
        if name == "guide":
            self.root.after_idle(self._refresh_guide_status)

    def _bg(self, func):
        threading.Thread(target=self._worker, args=(func,), daemon=True).start()

    def _worker(self, func):
        try:
            func()
        except Exception as exc:
            self.log.exception("state=ACTION result=error error=%s", exc)
            try: self.adb.screenshot()
            except Exception: pass
            self.events.put(("error", str(exc)))

    def _voice_bg(self, func):
        guarded_thread(self, self.voice_job_id.get(), self._voice_worker, args=(func,),
            references=self.voice_reference_file.get(), daemon=True)

    def _voice_worker(self, func):
        try:
            func()
        except Exception as exc:
            self.log.exception("state=AI_VOICE result=error error=%s", exc)
            self.events.put(("voice_error", str(exc)))

    def _subtitle_bg(self, func):
        guarded_thread(self, self.subtitle_job_id.get(), self._subtitle_worker, args=(func,), daemon=True)

    def _subtitle_worker(self, func):
        try:
            func()
        except Exception as exc:
            self.log.exception("state=AI_SUBTITLE result=error error=%s", exc)
            self.events.put(("subtitle_error", str(exc)))

    def _logo_bg(self, func):
        guarded_thread(self, self.logo_job_id.get(), self._logo_worker, args=(func,),
            references=self.logo_file.get(), daemon=True)

    def _logo_worker(self, func):
        try:
            func()
        except Exception as exc:
            self.log.exception("state=VIDEO_LOGO result=error error=%s", exc)
            self.events.put(("logo_error", str(exc)))

    def _check(self):
        # Do not silently switch to the first phone when a saved device disappears.
        return self.android_wifi.action('android_wifi_refresh')

    def _scrcpy(self):
        try:
            subprocess.Popen([str(self.cfg["scrcpy_path"]), "-s", self.adb.serial])
            self.status.set("เปิดหน้าจอมือถือแล้ว")
        except Exception as exc:
            messagebox.showerror("เปิดหน้าจอไม่สำเร็จ", str(exc))

    def _shopee(self):
        with self.android_wifi.verified_device() as device:
            result = device.open_package(self.cfg["shopee_package"])
        text = (result.stdout + result.stderr).strip()
        if result.returncode or "error" in text.lower(): raise RuntimeError(text or "เปิด Shopee ไม่สำเร็จ")
        self.events.put(("log", "สั่งเปิด Shopee สำเร็จ"))

    def _dump(self):
        with self.android_wifi.verified_device() as device:
            self.events.put(("log", f"บันทึก UI hierarchy: {device.dump_ui().name}"))

    def _add(self):
        for path in filedialog.askopenfilenames(filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi")]): self.jobs.add(path)
        self._refresh()

    def _add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for path in Path(folder).iterdir():
                if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi"}: self.jobs.add(path)
            self._refresh()

    def _attach_video(self):
        selected = self.product_table.selection()
        if not selected:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน"); return
        job_id = self.product_table.item(selected[0], "values")[0]
        path = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi")])
        if path:
            self._bg(lambda: self._copy_video(job_id, path))

    def _attach_product_images(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน"); return
        paths = filedialog.askopenfilenames(filetypes=[("Product images", "*.jpg *.jpeg *.png *.webp")])
        if paths: self._bg(lambda: self._copy_product_images(job_id, paths))

    def _copy_product_images(self, job_id, paths):
        job = self.products.attach_images(job_id, paths)
        self.events.put(("product", f"เพิ่มรูปสินค้า {len(paths)} รูปให้ {job['id']} แล้ว"))

    def _open_voice_for_selected(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self.voice_job_id.set(job_id)
        self._show_page("voice")
        self._load_voice_job()

    def _open_subtitle_for_selected(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self.subtitle_job_id.set(job_id)
        self._show_page("subtitle")
        self._load_subtitle_job()

    def _open_logo_for_selected(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self.logo_job_id.set(job_id)
        self._show_page("logo")
        self._load_logo_job()

    def _logo_scale_changed(self):
        self._update_logo_labels()
        self._update_logo_preview_from_cache()

    def _update_logo_labels(self):
        if not hasattr(self, "logo_opacity_text"):
            return
        opacity = max(5, min(100, round(float(self.logo_opacity.get()))))
        self.logo_opacity_text.set(f"ทึบ {opacity}% • โปร่ง {100-opacity}%")
        self.logo_size_text.set(f"{round(float(self.logo_size.get()))}%")
        self.logo_margin_text.set(f"{int(float(self.logo_margin.get()))} px")

    def _logo_position_key(self):
        label = self.logo_position.get()
        if label in POSITIONS:
            return label
        return next((key for key, value in POSITIONS.items() if value == label), "bottom_right")

    def _logo_options(self):
        options = {
            "opacity": float(self.logo_opacity.get()) / 100,
            "size_percent": float(self.logo_size.get()),
            "position": self._logo_position_key(),
            "margin": int(float(self.logo_margin.get())),
        }
        layout = normalize_logo_layout(getattr(self, 'logo_layout', None))
        if layout is not None:
            options['layout'] = layout
        return options

    def _job_logo_config(self, job):
        frozen = self._creation_settings(job['id'])
        sources = (job, job.get('media_finish_config'), frozen.get('finish_config'))
        config = frozen_logo_config(self.cfg, *sources)
        if config.get('logo_layout') is not None:
            for source in sources:
                if isinstance(source, dict):
                    config.update({key: copy.deepcopy(value) for key, value in source.items() if key.startswith('logo_')})
            logo = Path(config.get('logo_file') or '')
            if not logo.is_absolute():
                config['logo_file'] = str(self.products.root / job['id'] / logo)
        return config

    def _job_logo_options(self, job):
        return logo_render_options(self._job_logo_config(job))

    def _job_logo_file(self, job):
        return Path(self._job_logo_config(job).get('logo_file') or '')

    @staticmethod
    def _logo_asset_id(path):
        resolved = str(Path(path).resolve()).casefold()
        return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]

    def _logo_library_entries(self):
        """Return every reusable logo without exposing arbitrary paths to the web UI."""
        candidates = [
            ("SmartFlow • โลโก้เต็มต้นฉบับ", ROOT / "assets" / "smartflow_logo.png", True),
            ("SmartFlow • ไอคอนย่อ", ROOT / "assets" / "smartflow_icon.png", True),
        ]
        job = self._logo_job()
        if job:
            job_logo = self.products.root / job["id"] / str(job.get("logo_file") or "")
            if job_logo.is_file():
                candidates.append((f"โลโก้ของ {job['id']}", job_logo, False))
        active = Path(self.logo_file.get().strip()) if self.logo_file.get().strip() else None
        if active and active.is_file():
            candidates.append((active.stem, active, False))
        user_root = ROOT / "assets" / "logos" / "user"
        if user_root.is_dir():
            for path in sorted(user_root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    display_name = re.sub(r"-[0-9a-f]{10}$", "", path.stem, flags=re.IGNORECASE).replace("-", " ").strip()
                    candidates.append((display_name or path.stem, path, False))
        entries, seen = [], set()
        for name, path, builtin in candidates:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            key = str(resolved).casefold()
            if key in seen or not resolved.is_file():
                continue
            seen.add(key)
            entries.append({
                "id": self._logo_asset_id(resolved),
                "name": str(name),
                "path": resolved,
                "builtin": bool(builtin),
            })
        return entries

    def _logo_library_payload(self):
        active = str(Path(self.logo_file.get().strip()).resolve()).casefold() if self.logo_file.get().strip() and Path(self.logo_file.get().strip()).is_file() else ""
        return [{
            "id": item["id"],
            "name": item["name"],
            "filename": item["path"].name,
            "builtin": item["builtin"],
            "selected": str(item["path"]).casefold() == active,
            "url": f"/api/desktop/media?item_id=logo%3A{item['id']}&kind=preview",
        } for item in self._logo_library_entries()]

    def _resolve_logo_asset(self, asset_id):
        clean = str(asset_id or "").strip()
        return next((item["path"] for item in self._logo_library_entries() if item["id"] == clean), None)

    def _save_desktop_logo(self, payload):
        """Import a logo into the persistent library while preserving PNG transparency."""
        encoded = str(payload.get("data_url") or "")
        if not encoded.startswith("data:image/") or "," not in encoded:
            raise ValueError("ข้อมูลโลโก้ไม่ถูกต้อง")
        try:
            raw = base64.b64decode(encoded.split(",", 1)[1], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("อ่านข้อมูลโลโก้ไม่สำเร็จ") from exc
        if not raw or len(raw) > 12 * 1024 * 1024:
            raise ValueError("โลโก้ต้องมีขนาดไม่เกิน 12 MB")
        try:
            with Image.open(BytesIO(raw)) as opened:
                image_format = str(opened.format or "").upper()
                width, height = opened.size
                opened.verify()
        except (OSError, ValueError) as exc:
            raise ValueError("ไฟล์ที่เลือกไม่ใช่รูป PNG, JPG หรือ WEBP ที่สมบูรณ์") from exc
        extension = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(image_format)
        if not extension or width < 32 or height < 32:
            raise ValueError("โลโก้ต้องเป็น PNG, JPG หรือ WEBP และมีขนาดอย่างน้อย 32 × 32")
        source_stem = Path(str(payload.get("filename") or "logo")).stem
        safe_stem = re.sub(r"[^\wก-๙-]+", "-", source_stem, flags=re.UNICODE).strip("-_")[:48] or "logo"
        digest = hashlib.sha256(raw).hexdigest()[:10]
        folder = ROOT / "assets" / "logos" / "user"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{safe_stem}-{digest}{extension}"
        if not target.is_file():
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(raw)
            os.replace(temporary, target)
        self.logo_file.set(str(target.resolve()))
        self._logo_preview_asset_id = ""
        self._logo_editor_request = ''
        self._logo_editor_preview = {}
        self.logo_status.set(f"เพิ่ม {source_stem} เข้าคลังแล้ว • กดบันทึกเพื่อใช้เป็นค่าเริ่มต้น")
        return {
            "ok": True,
            "asset_id": self._logo_asset_id(target),
            "name": source_stem,
            "width": width,
            "height": height,
        }

    def _import_logo_file(self, path):
        source = Path(path)
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(source.suffix.lower())
        if not mime or not source.is_file():
            raise ValueError("รองรับโลโก้ PNG, JPG และ WEBP เท่านั้น")
        return self._save_desktop_logo({
            "filename": source.name,
            "data_url": f"data:{mime};base64,{base64.b64encode(source.read_bytes()).decode('ascii')}",
        })

    def _apply_logo_payload(self, payload):
        if 'layout' in payload:
            self.logo_layout = normalize_logo_layout(payload['layout'])
        previous = str(self.logo_file.get().strip())
        asset_id = str(payload.get("asset_id") or "").strip()
        if asset_id:
            asset = self._resolve_logo_asset(asset_id)
            if not asset:
                raise ValueError("ไม่พบโลโก้ที่เลือกในคลัง")
            self.logo_file.set(str(asset))
        elif str(payload.get("file") or "").strip():
            self.logo_file.set(str(payload.get("file")).strip())
        if str(self.logo_file.get().strip()) != previous:
            self._logo_preview_asset_id = ""
        self.logo_opacity.set(max(5, min(100, float(payload.get("opacity") or 80))))
        self.logo_size.set(max(3, min(60, float(payload.get("size") or 18))))
        self.logo_position.set(str(payload.get("position") or POSITIONS["bottom_right"]))
        self.logo_margin.set(max(0, min(120, int(payload.get("margin", 28)))))

    def _save_logo_preferences(self, extra=None):
        logo = Path(self.logo_file.get().strip())
        if not logo.is_file():
            raise ValueError("กรุณาเลือกโลโก้จากคลังก่อนบันทึก")
        options = self._logo_options()
        settings = {
            "logo_file": str(logo.resolve()),
            "logo_opacity": options["opacity"],
            "logo_size_percent": options["size_percent"],
            "logo_position": options["position"],
            "logo_margin": options["margin"],
            "logo_layout": options.get('layout'),
        }
        if isinstance(extra, dict):
            settings.update(extra)
        save_logo_settings(settings)
        self.cfg.update(settings)
        self.logo_status.set(f"บันทึกแล้ว • {logo.stem} จะเป็นโลโก้เริ่มต้นของงานใหม่")
        return settings

    def _logo_job(self):
        job_id = self.logo_job_id.get().strip()
        return next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)

    def _logo_source_video(self, job):
        folder = self.products.root / job["id"]
        relative = job.get("video_without_logo_path") or job.get("video_path") or ""
        source = folder / relative
        if not source.is_file():
            raise ValueError("Job นี้ยังไม่มีวิดีโอ กรุณาสร้างหรือเพิ่มวิดีโอก่อน")
        return source

    def _load_logo_job(self):
        self._logo_editor_request = ''
        self._logo_editor_preview = {}
        self._logo_frame_cache = None
        self._logo_preview_asset_id = ""
        self.logo_preview.configure(image="", text="กด ดูตัวอย่าง เพื่อจัดวางโลโก้")
        job = self._logo_job()
        if not job:
            self.logo_layout = normalize_logo_layout(self.cfg.get('logo_layout'))
            self.logo_status.set("ใช้ภาพพื้นหลังตัวอย่าง • จัดวางได้ทั้งแนวตั้งและแนวนอน")
            return
        try:
            source = self._logo_source_video(job)
            saved_logo = self.products.root / job["id"] / str(job.get("logo_file") or "")
            if saved_logo.is_file():
                self.logo_file.set(str(saved_logo))
            if job.get("logo_status") == "ready":
                self.logo_layout = normalize_logo_layout(job.get('logo_layout'))
                self.logo_opacity.set(float(job.get("logo_opacity", 0.8)) * 100)
                self.logo_size.set(float(job.get("logo_size_percent", 18)))
                self.logo_position.set(POSITIONS.get(str(job.get("logo_position", "bottom_right")), POSITIONS["bottom_right"]))
                self.logo_margin.set(int(job.get("logo_margin", 28)))
            self._update_logo_labels()
            self.logo_status.set(f"{job['id']} • ต้นฉบับ {source.name}")
        except Exception as exc:
            self.logo_status.set(str(exc))

    def _select_logo_file(self):
        path = filedialog.askopenfilename(filetypes=[("Logo image", "*.png *.jpg *.jpeg *.webp")])
        if path:
            self._import_logo_file(path)
            self._update_logo_preview_from_cache()

    @uses_job_files(lambda app: (app.logo_job_id.get(), app.logo_file.get()))
    def _preview_logo(self):
        job = self._logo_job()
        logo = Path(self.logo_file.get().strip())
        if not job:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        if not logo.is_file():
            messagebox.showinfo("เลือกโลโก้", "กรุณาเลือกไฟล์โลโก้ก่อน")
            return
        self.logo_status.set("กำลังสร้างภาพตัวอย่าง...")
        options = self._logo_options()
        self._logo_bg(lambda: self._preview_logo_worker(job, logo, options))

    def _preview_logo_worker(self, job, logo, options):
        renderer = VideoLogoRenderer(self.cfg.get("ffmpeg_path", ""))
        source = self._logo_source_video(job)
        frame = renderer.extract_preview_frame(source)
        preview = renderer.compose_preview(frame, logo, **options)
        preview_target = ROOT / "workspace" / "preview" / "logo_preview.png"
        preview_target.parent.mkdir(parents=True, exist_ok=True)
        preview.save(preview_target, format="PNG")
        self.events.put(("logo_preview", (frame, preview, source.name, self._logo_asset_id(logo))))

    def _preview_logo_editor(self, payload):
        request = str(payload.get('preview_request') or '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,96}', request):
            raise ValueError('คำขอพรีวิวโลโก้ไม่ถูกต้อง')
        profile = str(payload.get('profile') or 'portrait')
        if profile not in PROFILE_SIZES:
            raise ValueError('อัตราส่วนพรีวิวไม่ถูกต้อง')
        job_id = str(payload.get('job_id') or '')
        job = self.products.get_job(job_id) if job_id else None
        self.logo_job_id.set(job_id)
        self._apply_logo_payload(payload)
        logo = Path(self.logo_file.get().strip())
        if not logo.is_file():
            raise ValueError('เลือกโลโก้ก่อนดูพรีวิว')
        options = self._logo_options()
        self._logo_editor_request = request
        self._logo_editor_preview = {}
        self.logo_status.set('กำลังตรวจพรีวิวตำแหน่งโลโก้…')
        self._logo_bg(lambda: self._preview_logo_editor_worker(job, logo, options, profile, request,
            follow_source=payload.get('follow_source') is True))
        return {'ok': True, 'accepted': True, 'preview_request': request}

    def _preview_logo_editor_worker(self, job, logo, options, profile, request, follow_source=False):
        targets = ()
        try:
            renderer = VideoLogoRenderer(self.cfg.get('ffmpeg_path', ''))
            source = self._logo_source_video(job) if job else None
            frame = None
            source_profile = ''
            if source:
                info = renderer.video_info(source)
                source_profile = logo_profile(info['width'], info['height'])
                if follow_source:
                    profile = source_profile
                if source_profile == profile:
                    frame = renderer.extract_preview_frame(source)
            if frame is None:
                frame = Image.new('RGB', PROFILE_SIZES[profile], '#172444')
            preview = renderer.compose_preview(frame, logo, **options)
            folder = ROOT / 'workspace' / 'preview'
            folder.mkdir(parents=True, exist_ok=True)
            stem = f'logo_editor_{os.getpid()}_{uuid.uuid4().hex}'
            targets = (folder / f'{stem}_frame.png', folder / f'{stem}_result.png')
            frame.save(targets[0]); preview.save(targets[1])
            self.events.put(('logo_editor_preview', {
                'request': request, 'job_id': job['id'] if job else '',
                'asset_id': self._logo_asset_id(logo), 'profile': profile,
                'width': frame.width, 'height': frame.height, 'source_profile': source_profile,
                'real_frame': bool(source and source_profile == profile), 'files': targets,
            }))
        except Exception:
            for target in targets:
                target.unlink(missing_ok=True)
            self.events.put(('logo_editor_preview', {'request': request, 'error': True}))

    def _accept_logo_editor_preview(self, payload):
        files = payload.get('files') or ()
        if payload.get('request') != getattr(self, '_logo_editor_request', ''):
            for target in files:
                target.unlink(missing_ok=True)
            return
        if payload.get('error'):
            self.logo_status.set('สร้างพรีวิวไม่ได้ • ตรวจไฟล์โลโก้และวิดีโอแล้วลองใหม่')
            return
        previous = getattr(self, '_logo_editor_files', ())
        self._logo_editor_files = files
        self._logo_editor_preview = {key: value for key, value in payload.items() if key != 'files'}
        for target in previous:
            target.unlink(missing_ok=True)
        self.logo_status.set('ตรวจพรีวิวแล้ว • กดบันทึกเพื่อใช้กับงานใหม่')

    def _update_logo_preview_from_cache(self):
        self._update_logo_labels()
        if self._logo_frame_cache is None or not Path(self.logo_file.get().strip()).is_file():
            return
        try:
            renderer = VideoLogoRenderer(self.cfg.get("ffmpeg_path", ""))
            preview = renderer.compose_preview(self._logo_frame_cache, self.logo_file.get().strip(), **self._logo_options())
            preview_target = ROOT / "workspace" / "preview" / "logo_preview.png"
            preview_target.parent.mkdir(parents=True, exist_ok=True)
            preview.save(preview_target, format="PNG")
            self._logo_preview_asset_id = self._logo_asset_id(self.logo_file.get().strip())
            self._logo_preview_token += 1
            self._display_logo_preview(preview)
        except Exception as exc:
            self.logo_status.set(f"ตัวอย่างผิดพลาด • {exc}")

    def _display_logo_preview(self, image):
        preview = image.copy()
        preview.thumbnail((520, 500), Image.Resampling.LANCZOS)
        self._logo_preview_photo = ImageTk.PhotoImage(preview)
        self.logo_preview.configure(image=self._logo_preview_photo, text="")

    @uses_job_files(lambda app: (app.logo_job_id.get(), app.logo_file.get()))
    def _render_logo_video(self):
        job = self._logo_job()
        logo = Path(self.logo_file.get().strip())
        if not job:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        if not logo.is_file():
            messagebox.showinfo("เลือกโลโก้", "กรุณาเลือกไฟล์โลโก้ก่อน")
            return
        self.logo_status.set("กำลังสร้างวิดีโอใส่โลโก้...")
        options = self._logo_options()
        self._logo_bg(lambda: self._render_logo_worker(job, logo, options))

    def _render_logo_worker(self, job, logo, options):
        renderer = VideoLogoRenderer(self.cfg.get("ffmpeg_path", ""))
        source = self._logo_source_video(job)
        output = self.products.root / job["id"] / "videos" / "final_with_logo.mp4"
        result = renderer.render(source, logo, output, crf=self._video_render_settings()["crf"], **options)
        saved = self.products.save_logo_video(job["id"], output, source, logo, options)
        self._save_logo_preferences({"ffmpeg_path": str(renderer.ffmpeg)})
        self.events.put(("logo_ready", (saved, result)))

    def _open_logo_folder(self):
        job_id = self.logo_job_id.get().strip()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self._open_folder(self.products.root / job_id / "videos")

    def _toggle_voice_key(self):
        self.voice_key_entry.configure(show="" if self.voice_show_key.get() else "•")

    def _load_saved_voice_key(self):
        try:
            saved = WindowsCredentialStore().load()
            if saved:
                self.voice_api_key.set(saved)
                self.voice_key_saved.set("✓ เชื่อมต่อแล้ว • เก็บคีย์ใน Windows")
        except Exception as exc:
            self.log.warning("state=VOICE_KEY_LOAD result=error error=%s", exc)

    def _save_voice_key(self):
        try:
            WindowsCredentialStore().save(self.voice_api_key.get())
            self.voice_key_saved.set("✓ เชื่อมต่อแล้ว • เก็บคีย์ใน Windows")
            self.status.set("บันทึก AI Voice API Key แบบเข้ารหัสแล้ว")
            self._write_console("AI Voice • บันทึก API Key ใน Windows Credential Manager แล้ว", "success")
            self._refresh_voice_catalog()
            self._refresh_service_credits(force=True, silent=True)
        except Exception as exc:
            messagebox.showerror("บันทึก API Key ไม่สำเร็จ", str(exc))

    def _delete_voice_key(self):
        if not messagebox.askyesno(
            "ยกเลิก AI Voice?",
            "API Key ที่เก็บไว้ใน Windows จะถูกลบออก\nคุณสามารถเชื่อมต่อใหม่ได้ด้วย API Key เดิม",
            parent=self.root,
        ):
            return
        try:
            WindowsCredentialStore().delete()
            self.voice_api_key.set("")
            self.voice_key_saved.set("○ ยังไม่ได้เชื่อมต่อ")
            self.voice_catalog_choice.set("กดโหลดรายการเสียง")
            self.voice_catalog_info.set("ใส่ API Key เพื่อโหลดเสียงที่บัญชีนี้ใช้งานได้")
            self._voice_catalog_by_label = {}
            if hasattr(self, "voice_catalog_combo"):
                self.voice_catalog_combo.configure(values=())
            self.status.set("ลบ AI Voice API Key ที่บันทึกไว้แล้ว")
            self._service_credit_state["voice"] = self._credit_state(False, "ยังไม่ได้เชื่อม AI Voice")
            self._refresh()
        except Exception as exc:
            messagebox.showerror("ลบ API Key ไม่สำเร็จ", str(exc))

    @staticmethod
    def _credit_state(configured=False, message="ยังไม่ได้เชื่อมต่อ", **values):
        return credit_state(configured, message, **values)

    def _refresh_service_credits(self, force=False, silent=True):
        now = time.monotonic()
        if self._service_credit_refreshing:
            return False
        if not force and now - self._service_credit_last_requested < 60:
            return False
        voice_key = self.voice_api_key.get().strip()
        try:
            subtitle_credential = self._subtitle_store().load() or ""
        except Exception:
            subtitle_credential = ""
        if not voice_key:
            self._service_credit_state["voice"] = self._credit_state(False, "ยังไม่ได้เชื่อม AI Voice")
        else:
            previous = dict(self._service_credit_state.get("voice") or {})
            previous.update({"configured": True, "loading": True, "message": "กำลังตรวจเครดิตเสียง..."})
            self._service_credit_state["voice"] = previous
        if not subtitle_credential:
            self._service_credit_state["subtitle"] = self._credit_state(False, "ยังไม่ได้เชื่อม AI Subtitle")
        else:
            previous = dict(self._service_credit_state.get("subtitle") or {})
            previous.update({"configured": True, "loading": True, "message": "กำลังตรวจเครดิตซับไตเติล..."})
            self._service_credit_state["subtitle"] = previous
        self._service_credit_last_requested = now
        if not voice_key and not subtitle_credential:
            self._refresh()
            return False
        self._service_credit_refreshing = True
        self._refresh()
        threading.Thread(
            target=self._service_credit_worker,
            args=(voice_key, subtitle_credential, bool(silent)),
            daemon=True,
        ).start()
        return True

    def _service_credit_worker(self, voice_key, subtitle_credential, silent=True):
        states = {}
        if voice_key:
            try:
                status = ExternalTtsClient(
                    voice_key,
                    self.cfg.get("voice_api_base_url", "https://www.catfufu.com"),
                ).get_status()
                states["voice"] = self._credit_state(
                    True,
                    "เชื่อมต่อแล้ว",
                    connected=bool(status.get("connected")),
                    credits=status.get("credits"),
                    unlimited=bool(status.get("unlimited")),
                    expires_at=str(status.get("expires_at") or ""),
                    plan_name=str(status.get("plan_name") or status.get("plan_code") or ""),
                )
            except Exception as exc:
                states["voice"] = self._credit_state(True, str(exc), error=True)
        if subtitle_credential:
            try:
                status = SmartSubOnlineClient(
                    subtitle_credential,
                    self.cfg.get("subtitle_api_base_url", "https://www.catfufu.com/api/smartsub-online/v2"),
                ).get_status()
                states["subtitle"] = self._credit_state(
                    True,
                    "เชื่อมต่อแล้ว",
                    connected=bool(status.get("connected")),
                    credits=status.get("credits"),
                    trial_remaining=int(status.get("trial_remaining") or 0),
                    job_credit_cost=int(status.get("job_credit_cost") or 0),
                    expires_at=str(status.get("expires_at") or ""),
                    requires_token=bool(status.get("requires_token")),
                )
            except Exception as exc:
                states["subtitle"] = self._credit_state(True, str(exc), error=True)
        self.events.put(("service_credits", (states, bool(silent))))

    def _select_reference_audio(self):
        path = filedialog.askopenfilename(filetypes=[("Reference audio", "*.wav *.mp3 *.m4a *.aac *.ogg *.flac *.mp4")])
        if path:
            self.voice_reference_file.set(path)
            save_voice_settings({"voice_reference_file": path})
            if not self.voice_reference_id.get().strip():
                self.voice_status.set("เลือกเสียงอ้างอิงแล้ว • กดสร้างเสียงได้เลย ระบบจะอัปโหลดให้อัตโนมัติ")

    def _voice_client(self):
        return ExternalTtsClient(self.voice_api_key.get(), self.cfg.get("voice_api_base_url", "https://www.catfufu.com"))

    def _refresh_voice_catalog(self, silent=False):
        api_key = self.voice_api_key.get().strip()
        if not api_key:
            if not silent:
                messagebox.showinfo("AI Voice API Key", "กรุณาใส่และบันทึก API Key ก่อนโหลดรายการเสียง")
            return
        self.voice_catalog_info.set("กำลังโหลดเสียงจากบัญชี API...")
        threading.Thread(target=self._voice_catalog_worker, args=(api_key, bool(silent)), daemon=True).start()

    def _voice_catalog_worker(self, api_key, silent=False):
        try:
            client = ExternalTtsClient(api_key, self.cfg.get("voice_api_base_url", "https://www.catfufu.com"))
            self.events.put(("voice_catalog", client.list_voices()))
        except Exception as exc:
            self.events.put(("voice_catalog_error", (str(exc), bool(silent))))

    @staticmethod
    def _voice_catalog_label(voice):
        source = "เสียงของฉัน" if voice.get("source") == "custom" else "เสียงพื้นฐาน"
        name = str(voice.get("name") or voice.get("reference_id") or "เสียงไม่มีชื่อ").strip()
        return f"{source} • {name}"

    def _apply_voice_catalog(self, payload):
        voices = list((payload or {}).get("voices") or [])
        labels = []
        mapping = {}
        for voice in voices:
            label = self._voice_catalog_label(voice)
            if label in mapping:
                label = f"{label} • {str(voice.get('id') or '')[:10]}"
            labels.append(label)
            mapping[label] = voice
        self._voice_catalog_by_label = mapping
        self.voice_catalog_combo.configure(values=labels)
        current_reference = self.voice_reference_id.get().strip()
        selected_label = next((label for label, voice in mapping.items() if voice.get("reference_id") == current_reference), "")
        if not selected_label and not current_reference and labels:
            selected_label = labels[0]
        if selected_label:
            self.voice_catalog_choice.set(selected_label)
            self._select_catalog_voice()
        elif current_reference:
            self.voice_catalog_choice.set("เสียงอัปโหลดเดิม • ใช้ reference_id ปัจจุบัน")
        else:
            self.voice_catalog_choice.set("ไม่พบเสียงที่ใช้งานได้")
        preset_count = int((payload or {}).get("preset_count") or 0)
        custom_count = int((payload or {}).get("custom_count") or 0)
        if not selected_label:
            self.voice_catalog_info.set(f"โหลดแล้ว {len(voices)} เสียง • พื้นฐาน {preset_count} • ของฉัน {custom_count}")
        self.status.set(f"AI Voice • โหลดรายการเสียงแล้ว {len(voices)} เสียง")

    def _select_catalog_voice(self):
        voice = self._voice_catalog_by_label.get(self.voice_catalog_choice.get())
        if not voice:
            return
        reference_id = str(voice.get("reference_id") or "").strip()
        if not reference_id:
            return
        self.voice_reference_id.set(reference_id)
        allowed = (CLIP_VOICE_EMOTION,)
        if hasattr(self, "voice_emotion_combo"):
            self.voice_emotion_combo.configure(values=allowed)
        self.voice_emotion.set(CLIP_VOICE_EMOTION)
        self.voice_speed.set(str(CLIP_VOICE_SPEED))
        description = str(voice.get("description") or voice.get("note") or "พร้อมใช้งาน").strip()
        source = "เสียงที่บันทึกในบัญชี" if voice.get("source") == "custom" else "เสียงพื้นฐานของระบบ"
        self.voice_catalog_info.set(f"{source} • {description} • เสียงคงที่: Normal / 1.0x")
        save_voice_settings({"voice_reference_id": reference_id, "voice_emotion_id": CLIP_VOICE_EMOTION, "voice_speed": CLIP_VOICE_SPEED})
        self.voice_status.set(f"เลือก {voice.get('name') or reference_id} แล้ว • พร้อมสร้างเสียง")

    def _upload_voice_reference(self):
        api_key = self.voice_api_key.get().strip()
        source = self.voice_reference_file.get().strip()
        if not api_key:
            messagebox.showinfo("AI Voice API Key", "กรุณาใส่ API Key ก่อน")
            return
        if not source:
            messagebox.showinfo("เสียงอ้างอิง", "กรุณาเลือกไฟล์เสียงพูดคนเดียว 5-30 วินาที")
            return
        self.voice_status.set("กำลังอัปโหลดเสียงอ้างอิง...")
        self._voice_bg(lambda: self._upload_voice_reference_worker(api_key, source))

    def _upload_voice_reference_worker(self, api_key, source):
        client = ExternalTtsClient(api_key, self.cfg.get("voice_api_base_url", "https://www.catfufu.com"))
        result = client.upload_reference(source)
        self.events.put(("voice_reference", (str(result["reference_id"]), Path(source).name)))

    def _load_voice_job(self):
        job_id = self.voice_job_id.get().strip()
        if not job_id:
            return
        try:
            job, script = self.products.spoken_script(job_id)
            self.voice_script.delete("1.0", "end")
            self.voice_script.insert("1.0", script)
            if job.get("voice_reference_id") and not self.voice_reference_id.get().strip():
                self.voice_reference_id.set(job["voice_reference_id"])
            state = "มีเสียงพร้อมแล้ว" if job.get("voice_status") == "ready" else ("พร้อมสร้างเสียง" if script else "ยังไม่มีบทพูด • ให้ AI Web สร้างก่อน")
            self.voice_status.set(f"{job_id} • {state}")
        except Exception as exc:
            messagebox.showerror("โหลดบทพูดไม่สำเร็จ", str(exc))

    def _voice_preferences_payload(self):
        self.voice_emotion.set(CLIP_VOICE_EMOTION)
        self.voice_speed.set(str(CLIP_VOICE_SPEED))
        return {
            "voice_reference_id": self.voice_reference_id.get().strip(),
            "voice_reference_file": self.voice_reference_file.get().strip(),
            "voice_language": self.voice_language.get().strip() or "th",
            "voice_emotion_id": CLIP_VOICE_EMOTION,
            "voice_engine": "auto",
            "voice_speed": CLIP_VOICE_SPEED,
            "voice_silence_sec": float(self.voice_silence.get()),
            "voice_output_format": self.voice_format.get().strip() or "mp3",
        }

    def _save_voice_preferences(self, script_override=None):
        try:
            settings = self._voice_preferences_payload()
            save_voice_settings(settings)
            self.cfg.update(settings)
            job_id = self.voice_job_id.get().strip()
            changed = False
            if job_id:
                if script_override is None:
                    script_raw = self.voice_script.get("1.0", "end").strip()
                else:
                    script_raw = str(script_override or "").strip()
                if script_raw:
                    _job, prepared, changed = self.products.save_spoken_script(job_id, script_raw)
                    if script_override is None and prepared != script_raw:
                        self.voice_script.delete("1.0", "end")
                        self.voice_script.insert("1.0", prepared)
            suffix = " • บทเปลี่ยนแล้ว กรุณาสร้างเสียงใหม่" if changed else " • งานถัดไปจะใช้ค่านี้"
            self.voice_status.set("บันทึกการตั้งค่าเสียงแล้ว" + suffix)
            self.status.set("AI Voice • บันทึกค่า Normal / 1.0 และบทพูดแล้ว")
            return {"ok": True, "job_id": job_id, "script_changed": changed}
        except ValueError as exc:
            if script_override is None:
                messagebox.showerror("บันทึกการตั้งค่าไม่สำเร็จ", str(exc))
                return None
            raise

    def _prepare_voice_chatgpt(self):
        job_id = self.voice_job_id.get().strip()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self._prepare_chatgpt_for_job(job_id)

    @uses_job_files(lambda app: (app.voice_job_id.get(), app.voice_reference_file.get()))
    def _create_voice(self):
        if getattr(self, 'membership', None):
            self.membership.require()
        job_id = self.voice_job_id.get().strip()
        api_key = self.voice_api_key.get().strip()
        reference_id = self.voice_reference_id.get().strip()
        reference_file = self.voice_reference_file.get().strip()
        script_raw = self.voice_script.get("1.0", "end").strip()
        script, script_issues = prepare_thai_tts_script(script_raw)
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        if not api_key:
            messagebox.showinfo("AI Voice API Key", "กรุณาใส่ API Key ก่อน")
            return
        if not reference_id and (not reference_file or not Path(reference_file).is_file()):
            messagebox.showinfo("เสียงอ้างอิง", "กรุณาเลือกไฟล์เสียงอ้างอิงก่อน ระบบจะอัปโหลดและรับ reference_id ให้อัตโนมัติ")
            return
        if not script:
            messagebox.showinfo("บทพูด", "ยังไม่มีบทพูด กรุณาให้ AI Web สร้างหรือพิมพ์บทพูดก่อน")
            return
        if script_issues:
            messagebox.showwarning("ตรวจบทพูดก่อนสร้างเสียง", "\n".join(script_issues))
            return
        if script != script_raw:
            self.voice_script.delete("1.0", "end")
            self.voice_script.insert("1.0", script)
            self.voice_status.set("ปรับบทพูดเป็นรูปแบบภาษาไทยสำหรับ Voice AI แล้ว")
        try:
            options = {
                "language": self.voice_language.get().strip() or "th",
                "emotion_id": CLIP_VOICE_EMOTION,
                "engine": "auto",
                "speed": CLIP_VOICE_SPEED,
                "silence_sec": float(self.voice_silence.get()),
                "output_format": self.voice_format.get().strip() or "mp3",
            }
        except ValueError:
            messagebox.showerror("ตั้งค่าไม่ถูกต้อง", "กรุณาตรวจค่าความเร็วและเวลาว่างท้ายเสียง")
            return
        try:
            self.products.save_spoken_script(job_id, script_raw)
        except ValueError as exc:
            messagebox.showerror("บันทึกบทพูดไม่สำเร็จ", str(exc))
            return
        self.products.set_subtitle_requested(job_id, bool(self.subtitle_auto.get()))
        self.voice_status.set("กำลังส่งงานสร้างเสียง...")
        self._voice_bg(lambda: self._create_voice_worker(job_id, api_key, reference_id, reference_file, script, options))

    def _repair_chunk_voice_reference(self, client, reference_id, reference_file, cancel_event):
        check_cancelled(cancel_event)
        if reference_id.startswith(("preset:", "custom:")):
            raise ExternalTtsError("เสียงที่เลือกไม่มีอยู่ในบัญชีแล้ว กรุณาโหลดรายการเสียงและเลือกใหม่")
        source = Path(reference_file) if reference_file else None
        if not source or not source.is_file():
            raise ExternalTtsError("ไม่พบไฟล์เสียงต้นแบบ กรุณาเลือกเสียงอ้างอิงใหม่")
        uploaded = client.upload_reference(source)
        reference_id = str(uploaded["reference_id"])
        self.events.put(("voice_reference", (reference_id, source.name)))
        return reference_id

    def _create_voice_worker(self, job_id, api_key, reference_id, reference_file, script, options, cancel_event=None, emit_event=True, on_progress=None):
        check_cancelled(cancel_event)
        def voice_progress(message):
            self.events.put(("voice_progress", message))
            if on_progress is not None:
                on_progress(message)

        script, script_issues = prepare_thai_tts_script(script)
        if script_issues:
            raise ExternalTtsError("บทพูดยังไม่พร้อมสำหรับ Voice AI: " + " • ".join(script_issues))
        client = ExternalTtsClient(api_key, self.cfg.get("voice_api_base_url", "https://www.catfufu.com"))
        if not reference_id:
            source = Path(reference_file)
            voice_progress("กำลังอัปโหลดเสียงต้นแบบและรับ reference_id")
            uploaded = client.upload_reference(source)
            check_cancelled(cancel_event)
            reference_id = str(uploaded["reference_id"])
            self.events.put(("voice_reference", (reference_id, source.name)))
        if len(script) > MAX_TTS_REQUEST_CHARS:
            saved = self.products.get_job(job_id)
            target = self.products.root / job_id / "audio" / f"voiceover.{options['output_format']}"
            external_job_id, output_id, reference_id = render_chunked_voice(
                client, script, reference_id, target, scope=f"product:{job_id}:narration",
                options={"language": options["language"], "engine": options["engine"], "silence_sec": options["silence_sec"]},
                ffmpeg_path=self.cfg.get("ffmpeg_path"), cancel_event=cancel_event,
                on_progress=voice_progress,
                on_checkpoint=lambda remote, ref: self.products.mark_voice_queued(job_id, remote, ref),
                repair_reference=lambda ref: self._repair_chunk_voice_reference(client, ref, reference_file, cancel_event),
                legacy_job_id=str(saved.get("voice_job_id") or ""),
                legacy_output_id=str(saved.get("voice_output_id") or ""),
            )
            return self._save_voice_worker_result(job_id, target, external_job_id, reference_id, output_id, reference_file, options, emit_event)
        def submit(active_reference_id):
            return client.synthesize(
                script,
                active_reference_id,
                language=options["language"],
                emotion_id=CLIP_VOICE_EMOTION,
                engine=options["engine"],
                speed=CLIP_VOICE_SPEED,
                silence_sec=options["silence_sec"],
                idempotency_key=f"product:{job_id}:narration:v1",
            )
        try:
            queued = submit(reference_id)
        except ExternalTtsError as exc:
            missing_reference = "HTTP 404" in str(exc) or "ไม่พบไฟล์เสียงต้นแบบ" in str(exc)
            if not missing_reference:
                raise
            if reference_id.startswith(("preset:", "custom:")):
                raise ExternalTtsError("เสียงที่เลือกไม่มีอยู่ในบัญชีแล้ว กรุณากดโหลดรายการเสียงใหม่และเลือกเสียงอีกครั้ง") from None
            source = Path(reference_file) if reference_file else None
            if not source or not source.is_file():
                raise ExternalTtsError("reference_id นี้ไม่มีไฟล์ต้นแบบแล้ว กรุณาเลือกไฟล์เสียงอ้างอิง โปรแกรมจะอัปโหลดใหม่ให้อัตโนมัติ") from None
            voice_progress("reference_id เดิมใช้ไม่ได้ • กำลังอัปโหลดเสียงต้นแบบใหม่")
            uploaded = client.upload_reference(source)
            check_cancelled(cancel_event)
            reference_id = str(uploaded["reference_id"])
            self.events.put(("voice_reference", (reference_id, source.name)))
            queued = submit(reference_id)
        voice_attempt = 1
        while True:
            external_job_id = str(queued["job_id"])
            self.products.mark_voice_queued(job_id, external_job_id, reference_id)
            voice_progress(f"คิว {external_job_id} • กำลังประมวลผล")
            wait_options = {"on_status": lambda status, result: voice_progress(f"คิว {external_job_id} • {status}")}
            if cancel_event is not None:
                wait_options["cancel_event"] = cancel_event
            try:
                _, output_id = client.wait_until_done(external_job_id, **wait_options)
                break
            except ExternalTtsError as exc:
                if not exc.retryable or voice_attempt >= 2:
                    raise
                voice_attempt += 1
                voice_progress(f"AI Voice เปิดไฟล์ชั่วคราวไม่สำเร็จ • ลองสร้างเสียงใหม่อัตโนมัติ {voice_attempt}/2 โดยเก็บรูปและบทเดิม")
                self.log.warning(
                    "job_id=%s state=VOICE_TRANSIENT_RETRY attempt=%s/2 error=%s",
                    job_id,
                    voice_attempt,
                    exc,
                )
                if cancel_event is not None:
                    if cancel_event.wait(3):
                        check_cancelled(cancel_event)
                else:
                    time.sleep(3)
                check_cancelled(cancel_event)
                queued = submit(reference_id)
        output_format = options["output_format"]
        target = self.products.root / job_id / "audio" / f"voiceover.{output_format}"
        voice_progress("สร้างเสียงแล้ว • กำลังดาวน์โหลดและบันทึกไฟล์เสียงพากย์")
        if cancel_event is None:
            client.download(output_id, target, output_format)
        else:
            client.download(output_id, target, output_format, cancel_event=cancel_event)
        return self._save_voice_worker_result(job_id, target, external_job_id, reference_id, output_id, reference_file, options, emit_event)

    def _save_voice_worker_result(self, job_id, target, external_job_id, reference_id, output_id, reference_file, options, emit_event):
        job = self.products.save_voice_result(job_id, target, external_job_id, reference_id, output_id)
        save_voice_settings({
            "voice_reference_id": reference_id,
            "voice_reference_file": reference_file,
            "voice_language": options["language"],
            "voice_emotion_id": CLIP_VOICE_EMOTION,
            "voice_engine": options["engine"],
            "voice_speed": CLIP_VOICE_SPEED,
            "voice_silence_sec": options["silence_sec"],
            "voice_output_format": options["output_format"],
        })
        if emit_event:
            self.events.put(("voice_ready", (job, target)))
        return job, target

    def _open_voice_folder(self):
        job_id = self.voice_job_id.get().strip()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self._open_folder(self.products.root / job_id / "audio")

    @staticmethod
    def _subtitle_store():
        return WindowsCredentialStore("SmartPostAI/CatfufuSmartSubOnlineSOD")

    def _load_saved_subtitle_credential(self):
        try:
            if self._subtitle_store().load():
                self.subtitle_credential_saved.set("✓ เชื่อมต่อแล้ว • เก็บรหัสใน Windows")
                self.subtitle_status.set("พร้อมสร้างคำบรรยาย")
        except Exception as exc:
            self.log.warning("state=SUBTITLE_CREDENTIAL_LOAD result=error error=%s", exc)

    def _toggle_subtitle_token(self):
        self.subtitle_token_entry.configure(show="" if self.subtitle_show_token.get() else "•")

    def _redeem_subtitle(self):
        token = self.subtitle_token.get().strip()
        if not token:
            messagebox.showinfo("Subtitle Token", "กรุณาวาง Token ที่ขึ้นต้นด้วย SOT ก่อน")
            return
        language = self.subtitle_language.get().strip() or "th"
        syllables_per_cue = int(self.subtitle_syllables.get() or 3)
        auto_after_voice = bool(self.subtitle_auto.get())
        self.subtitle_status.set("กำลังเชื่อม Token กับเครื่องนี้...")
        self._subtitle_bg(lambda: self._redeem_subtitle_worker(token, language, auto_after_voice, syllables_per_cue))

    def _redeem_subtitle_worker(self, token, language, auto_after_voice, syllables_per_cue):
        client = SmartSubOnlineClient("", self.cfg.get("subtitle_api_base_url", "https://www.catfufu.com/api/smartsub-online/v2"))
        _, credential = client.redeem(self.subtitle_client_id, token)
        self._subtitle_store().save(credential)
        save_subtitle_settings({
            "subtitle_client_id": self.subtitle_client_id,
            "subtitle_language": language,
            "subtitle_auto_after_voice": auto_after_voice,
            "subtitle_syllables_per_cue": syllables_per_cue,
            "subtitle_api_base_url": client.base_url,
        })
        self.events.put(("subtitle_connected", self.subtitle_client_id))

    def _delete_subtitle_credential(self):
        if not messagebox.askyesno(
            "ยกเลิก AI Subtitle?",
            "รหัสอุปกรณ์ที่เก็บไว้ใน Windows จะถูกลบ\nหลังจากนี้อาจต้องใช้ Token SOT ใหม่เพื่อเชื่อมเครื่องอีกครั้ง",
            parent=self.root,
        ):
            return
        try:
            self._subtitle_store().delete()
            self.subtitle_token.set("")
            self.subtitle_credential_saved.set("○ ยังไม่ได้เชื่อมต่อ")
            self.subtitle_status.set("ลบรหัสอุปกรณ์แล้ว • ใช้ Token ใหม่เพื่อเชื่อมต่อ")
            self._service_credit_state["subtitle"] = self._credit_state(False, "ยังไม่ได้เชื่อม AI Subtitle")
            self._refresh()
        except Exception as exc:
            messagebox.showerror("ลบรหัส Subtitle ไม่สำเร็จ", str(exc))

    def _save_subtitle_options(self):
        enabled = bool(self.subtitle_auto.get())
        syllables_per_cue = max(1, min(5, int(self.subtitle_syllables.get() or 3)))
        save_subtitle_settings({
            "subtitle_client_id": self.subtitle_client_id,
            "subtitle_language": self.subtitle_language.get().strip() or "th",
            "subtitle_auto_after_voice": enabled,
            "subtitle_syllables_per_cue": syllables_per_cue,
            "subtitle_api_base_url": self.cfg.get("subtitle_api_base_url", "https://www.catfufu.com/api/smartsub-online/v2"),
        })
        self.cfg["subtitle_auto_after_voice"] = enabled
        self.cfg["subtitle_syllables_per_cue"] = syllables_per_cue
        self.subtitle_preference_status.set("เปิดใช้งานถาวร • งานต่อไปทำให้อัตโนมัติ" if enabled else "ปิดใช้งาน • งานต่อไปจะไม่สร้าง Subtitle")

    def _subtitle_option_changed(self):
        try:
            self._save_subtitle_options()
            enabled = bool(self.subtitle_auto.get())
            job_id = self._selected_product_job()
            if job_id:
                job = self.products.set_subtitle_requested(job_id, enabled)
                if enabled and job.get("voice_status") == "ready" and job.get("subtitle_status") not in {"ready", "queued"}:
                    self.subtitle_job_id.set(job_id)
                    self.root.after(200, lambda: self._start_subtitle_for_job(job_id))
                elif enabled and job.get("subtitle_status") == "ready":
                    self.root.after(200, lambda active_job=job_id: self._maybe_render_subtitles(active_job))
            self.status.set("เปิด Subtitle อัตโนมัติถาวรแล้ว" if enabled else "ปิด Subtitle อัตโนมัติแล้ว")
            self._write_console(f"AI Subtitle • {'เปิด' if enabled else 'ปิด'}ตัวเลือกถาวร", "success")
        except Exception as exc:
            messagebox.showerror("บันทึกตัวเลือก Subtitle ไม่สำเร็จ", str(exc))

    def _resume_pending_subtitles(self):
        if getattr(self, 'membership', None) and not self.membership.allowed():
            return
        if not self.subtitle_auto.get() or self._subtitle_active_job:
            return
        try:
            if not self._subtitle_store().load():
                return
            active_product_job = str(getattr(self, "_product_pipeline_job_id", "") or "")
            pending = next((job for job in self.products.list_jobs() if job.get("id") != active_product_job and job.get("subtitle_requested") and job.get("voice_status") == "ready" and job.get("subtitle_status") in {"not_generated", "queued"}), None)
            if pending:
                self.subtitle_job_id.set(pending["id"])
                self._start_subtitle_for_job(pending["id"])
                return
            render_pending = next((job for job in self.products.list_jobs() if job.get("subtitle_requested") and job.get("subtitle_status") == "ready" and job.get("video_status") == "ready" and job.get("subtitle_video_status") != "ready"), None)
            if render_pending:
                self._maybe_render_subtitles(render_pending["id"])
        except Exception as exc:
            self.log.warning("state=SUBTITLE_RESUME result=skip error=%s", exc)

    def _subtitle_job_audio(self, job_id):
        job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
        if not job:
            raise ValueError("ไม่พบ Product Job")
        relative = str(job.get("voice_path") or "")
        source = self.products.root / job_id / relative if relative else None
        if not source or not source.is_file():
            raise ValueError("Job นี้ยังไม่มีเสียงพากย์ กรุณาสร้าง AI Voice ก่อน")
        return job, source

    def _load_subtitle_job(self):
        job_id = self.subtitle_job_id.get().strip()
        if not job_id:
            return
        try:
            job, source = self._subtitle_job_audio(job_id)
            self.subtitle_audio_label.set(f"ใช้เสียงอัตโนมัติ: {source.name}")
            status = str(job.get("subtitle_status") or "not_generated")
            labels = {"ready": "คำบรรยายพร้อมแล้ว", "queued": "กำลังประมวลผล", "error": "งานล่าสุดผิดพลาด", "not_generated": "พร้อมส่งเสียงสร้างคำบรรยาย"}
            self.subtitle_status.set(f"{job_id} • {labels.get(status, status)}")
            transcript = str(job.get("subtitle_transcript") or "")
            subtitle_path = self.products.root / job_id / "captions" / "subtitle.srt"
            if subtitle_path.exists():
                subtitle_lines = [line.strip() for line in subtitle_path.read_text(encoding="utf-8-sig").splitlines()]
                cleaned = [line for line in subtitle_lines if line and not line.isdigit() and "-->" not in line]
                transcript = "\n".join(cleaned)
            elif not transcript:
                transcript_path = self.products.root / job_id / "captions" / "transcript.txt"
                transcript = transcript_path.read_text(encoding="utf-8") if transcript_path.exists() else "ยังไม่มีผลลัพธ์\n\nกด “สร้างคำบรรยายจากเสียงของ Job” แล้วระบบจะส่งเสียง รอผล และบันทึกไฟล์ให้อัตโนมัติ"
            self.subtitle_preview.configure(state="normal")
            self.subtitle_preview.delete("1.0", "end")
            self.subtitle_preview.insert("1.0", transcript)
            self.subtitle_preview.configure(state="disabled")
            self._update_subtitle_style_preview()
        except Exception as exc:
            self.subtitle_audio_label.set(str(exc))
            self.subtitle_status.set("ยังไม่พร้อมสร้าง Subtitle")

    def _create_subtitle(self):
        job_id = self.subtitle_job_id.get().strip()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self._start_subtitle_for_job(job_id)

    @uses_job_files(lambda app, job_id: job_id)
    def _start_subtitle_for_job(self, job_id):
        if str(getattr(self, "_product_pipeline_job_id", "") or "") == str(job_id or ""):
            self.subtitle_status.set(f"{job_id} • One-click กำลังดูแล Subtitle ให้อัตโนมัติ")
            return
        if self._subtitle_active_job:
            self.subtitle_status.set(f"กำลังสร้าง Subtitle ของ {self._subtitle_active_job} อยู่")
            return
        try:
            credential = self._subtitle_store().load()
            if not credential:
                raise ValueError("ยังไม่ได้เชื่อม Subtitle Token กับเครื่องนี้")
            job, source = self._subtitle_job_audio(job_id)
            language = self.subtitle_language.get().strip() or "th"
            syllables_per_cue = max(1, min(5, int(self.subtitle_syllables.get() or 3)))
            self._save_subtitle_options()
            self.products.set_subtitle_requested(job_id, True)
        except Exception as exc:
            messagebox.showinfo("ยังสร้าง Subtitle ไม่ได้", str(exc))
            return
        existing_job_id = str(job.get("subtitle_job_id") or "") if job.get("subtitle_status") == "queued" else ""
        self._subtitle_active_job = job_id
        self.subtitle_status.set(f"{job_id} • {'กำลังตรวจคิวเดิม' if existing_job_id else 'กำลังส่ง ' + source.name}")
        guarded_thread(self, job_id, self._subtitle_worker,
            args=(lambda: self._create_subtitle_worker(job_id, source, language, credential, existing_job_id, syllables_per_cue),),
            references=source, daemon=True)

    def _create_subtitle_worker(self, job_id, source, language, credential, existing_job_id="", syllables_per_cue=3, cancel_event=None, emit_event=True):
        check_cancelled(cancel_event)
        client = SmartSubOnlineClient(credential, self.cfg.get("subtitle_api_base_url", "https://www.catfufu.com/api/smartsub-online/v2"))
        external_job_id = str(existing_job_id or "")
        if not external_job_id:
            wav_source = self.products.root / job_id / "audio" / "subtitle_source.wav"
            self.events.put(("subtitle_progress", f"{job_id} • กำลังเตรียมเสียง WAV"))
            if cancel_event is None:
                client.prepare_wav(source, wav_source, self.cfg.get("ffmpeg_path", ""))
            else:
                client.prepare_wav(source, wav_source, self.cfg.get("ffmpeg_path", ""), cancel_event=cancel_event)
            fingerprint = f"smartpost:{job_id}:{source.stat().st_size}:{source.stat().st_mtime_ns}"
            created = client.create_job(wav_source, language, str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint)))
            external_job_id = str(created.get("jobId") or created.get("job_id"))
            self.products.mark_subtitle_queued(job_id, external_job_id, language)
            self.events.put(("subtitle_progress", f"{job_id} • ส่งเสียงแล้ว • คิว {external_job_id}"))
        wait_options = {"on_status": lambda status, data: self.events.put(("subtitle_progress", f"{job_id} • {status}"))}
        if cancel_event is not None:
            wait_options["cancel_event"] = cancel_event
        result = client.wait_until_done(external_job_id, **wait_options)
        job, paths = self.products.save_subtitle_result(job_id, external_job_id, result, syllables_per_cue)
        if emit_event:
            self.events.put(("subtitle_ready", (job, paths)))
        return job, paths

    def _subtitle_segmentation_changed(self):
        try:
            syllables_per_cue = max(1, min(5, int(self.subtitle_syllables.get() or 3)))
            self._save_subtitle_options()
            job_id = self.subtitle_job_id.get().strip()
            if not job_id:
                self.subtitle_status.set(f"บันทึกค่า {syllables_per_cue} พยางค์ต่อช่วงแล้ว")
                return
            job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
            if not job or job.get("subtitle_status") != "ready":
                self.subtitle_status.set(f"งานใหม่จะเริ่มที่ {syllables_per_cue} พยางค์ต่อช่วง")
                return
            rebuilt, _ = self.products.rebuild_subtitle_segments(job_id, syllables_per_cue)
            self._load_subtitle_job()
            self.subtitle_status.set(f"{job_id} • แบ่งใหม่ {syllables_per_cue} พยางค์ต่อช่วง • คำครบตามลำดับ")
            if rebuilt.get("subtitle_requested") and rebuilt.get("video_status") == "ready":
                self.root.after(200, lambda active_job=job_id: self._maybe_render_subtitles(active_job))
        except Exception as exc:
            messagebox.showerror("ปรับจำนวนพยางค์ไม่สำเร็จ", str(exc))

    def _open_subtitle_folder(self):
        job_id = self.subtitle_job_id.get().strip()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self._open_folder(self.products.root / job_id / "captions")

    @uses_job_files(lambda app, job_id, **kwargs: job_id)
    def _maybe_render_subtitles(self, job_id, force=False, settings=None):
        if self._subtitle_render_active:
            return
        job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
        if not job or not job.get("subtitle_requested") or job.get("subtitle_status") != "ready" or job.get("video_status") != "ready":
            return
        if not force and job.get("subtitle_video_status") == "ready" and job.get("subtitle_video_path"):
            return
        folder = self.products.root / job_id
        subtitle = folder / "captions" / "subtitle.srt"
        source_relative = job.get("video_without_subtitle_path") or job.get("video_path")
        source = folder / str(source_relative or "")
        if not source.is_file() or not subtitle.is_file():
            return
        output = folder / "videos" / "final_with_subtitles.mp4"
        settings = dict(settings or self._subtitle_style_settings(for_render=True, job_id=job_id))
        settings["crf"] = self._video_render_settings()["crf"]
        self._subtitle_render_active = job_id
        self.subtitle_status.set(f"{job_id} • กำลังใส่ Subtitle ลงวิดีโอ")
        guarded_thread(self, job_id, self._render_subtitle_video_worker, args=(job_id, source, subtitle, output, settings), daemon=True)

    def _render_subtitle_video_worker(self, job_id, source, subtitle, output, settings):
        try:
            renderer = SubtitleVideoRenderer(self.cfg.get("ffmpeg_path", ""))
            result = renderer.render(source, subtitle, output, **settings)
            stored_settings = dict(settings)
            stored_settings["font_path"] = self.fonts.portable_path(stored_settings.get("font_path")) if stored_settings.get("font_path") else ""
            job = self.products.save_subtitled_video(job_id, output, source, subtitle, stored_settings)
            self.events.put(("subtitle_video_ready", (job, result)))
        except Exception as exc:
            self.events.put(("subtitle_video_error", (job_id, str(exc))))

    def _paste_link(self):
        try: self.product_link.set(self.root.clipboard_get().strip())
        except tk.TclError: messagebox.showinfo("Clipboard", "ยังไม่มีข้อความใน Clipboard")

    def _import_link(self):
        value = self.product_link.get().strip()
        if not value:
            messagebox.showinfo("เพิ่มลิงก์สินค้า", "กรุณาวางลิงก์สินค้า Shopee"); return
        self.status.set("กำลังตรวจและนำเข้าลิงก์สินค้า...")
        self._bg(lambda: self._manual_import_link(value))

    def _manual_import_link(self, value):
        job, created = self.products.import_link(value)
        self.events.put(("link_imported", (job, created)))

    def _product_pipeline_options(self, seed="", queued=True):
        subtitle_enabled = bool(self.subtitle_auto.get())
        audio_settings = self._save_audio_options() or {}
        background_enabled = bool(self.audio_background_enabled.get())
        sfx_enabled = bool(self.audio_sfx_enabled.get())
        direct_choices = getattr(self, "_product_audio_choices", None)
        if direct_choices:
            background_enabled, sfx_enabled = direct_choices["music"], direct_choices["sfx"]
        bg_mode = self._background_mode_key(self.audio_background_mode.get())
        sfx_mode = self._sfx_mode_key(self.audio_sfx_mode.get()) if sfx_enabled else "off"
        # Resolve queued sources from their snapshot before consulting the live library.
        # A later global selection (or missing global file) must not block an older queue row.
        frozen = self._creation_pipeline_options({}) if queued else {}
        if "audio" in frozen:
            backgrounds = list(frozen["audio"].get("background_files") or [])
            effects = list(frozen["audio"].get("sfx_files") or [])
        else:
            backgrounds = self._selected_audio_files("background", self.audio_background_file.get(), bg_mode) if background_enabled else []
            effects = self._selected_audio_files("sfx", self.audio_sfx_file.get(), sfx_mode) if sfx_enabled else []
        options = {
            "provider": self._image_provider_key(),
            "presenter": dict(getattr(self, "_presenter_product_selection", {"enabled": False})),
            "ai_web_model": self._ai_web_model_key(),
            "video_provider": self._video_provider_key(),
            "voice_api_key": self.voice_api_key.get().strip(),
            "voice_reference_id": self.voice_reference_id.get().strip(),
            "voice_reference_file": self.voice_reference_file.get().strip(),
            "voice": {
                "language": self.voice_language.get().strip() or "th",
                "emotion_id": CLIP_VOICE_EMOTION,
                "engine": "auto",
                "speed": CLIP_VOICE_SPEED,
                "silence_sec": float(self.voice_silence.get()),
                "output_format": self.voice_format.get().strip() or "mp3",
            },
            "subtitle_enabled": subtitle_enabled,
            "subtitle_credential": self._subtitle_store().load() if subtitle_enabled else "",
            "subtitle_language": self.subtitle_language.get().strip() or "th",
            "subtitle_syllables": max(1, min(5, int(self.subtitle_syllables.get() or 3))),
            "subtitle_style": self._subtitle_style_settings(for_render=True, job_id=seed or "product-auto"),
            "audio_enabled": background_enabled or sfx_enabled,
            "audio_settings": audio_settings,
            "audio": {
                "background_files": backgrounds,
                "music_track_count": self.cfg.get("audio_background_track_count"),
                "background_mode": bg_mode,
                "background_volume": float(self.audio_background_volume.get()) / 100,
                "music_segment_max_sec": float(self.audio_background_segment_max.get()),
                "music_duck_ratio": float(self.audio_background_duck_percent.get()) / 100,
                "sfx_files": effects,
                "sfx_mode": sfx_mode,
                "sfx_volume": float(self.audio_sfx_volume.get()) / 100,
                "min_sfx_interval": float(self.audio_sfx_min_interval.get()),
                "max_sfx_count": int(self.audio_sfx_max_count.get()),
            },
            "render": self._video_render_settings(),
            "finish_config": {key: copy.deepcopy(value) for key, value in self.cfg.items() if key.startswith('logo_')},
        }
        options = self._creation_pipeline_options(options) if queued else options
        selected_choices = options.get("audio_choices") if queued and getattr(self, "_creation_dispatch_item", None) else getattr(self, "_product_audio_choices", None)
        if not (queued and getattr(self, "_creation_dispatch_item", None)):
            options["fictional_ai_characters_confirmed"] = getattr(self, "_product_fictional_confirmed", False) is True
            options["flow_settings"] = copy.deepcopy(getattr(self, "_product_flow_settings", {}))
            options['ai_cover_options'] = copy.deepcopy(getattr(self, '_product_ai_cover_options', {}))
            options['green_options'] = copy.deepcopy(getattr(self, '_product_green_options', {}))
            if getattr(self, '_product_generated_music_options', None) is not None:
                options['generated_music_options'] = copy.deepcopy(self._product_generated_music_options)
        return product_audio_options(options, selected_choices)

    @uses_job_files(lambda app, selected_job_id_override='': (selected_job_id_override or app._selected_product_job(),
        getattr(app, '_creation_dispatch_item', {}), app.cfg, app.voice_reference_file.get()))
    def _create_product_and_run(self, selected_job_id_override=""):
        if getattr(self, 'membership', None):
            self.membership.require()
        if self._product_pipeline_job_id:
            if self._product_progress_dialog and self._product_progress_dialog.winfo_exists():
                self._product_progress_dialog.lift()
            return
        if self._story_pipeline_job_id:
            messagebox.showinfo("มี Story Shorts กำลังทำอยู่", "ระบบทำงานหน้าเว็บได้ครั้งละหนึ่งงาน กรุณารอให้ Story Shorts จบ หรือยกเลิกงานเดิมก่อนเริ่มคลิปสินค้า")
            return
        link = self.product_link.get().strip()
        # Hybrid/API callers already carry the exact Job id.  Do not make a
        # resume depend on the hidden Tk table having finished its latest
        # refresh/selection cycle; that race used to turn a valid resume into
        # the misleading "กรุณาวางลิงก์สินค้า" notice.
        selected_job_id = str(selected_job_id_override or self._selected_product_job() or "").strip()
        queue = getattr(self, "story_queue", None)
        if selected_job_id and queue is not None and hasattr(queue, "require_not_trashed"):
            queue.require_not_trashed(selected_job_id)
        if not link and not selected_job_id:
            messagebox.showinfo("ใส่ลิงก์สินค้า", "วางลิงก์สินค้า Shopee หรือเลือก Product Job ที่ต้องการทำต่อ")
            return
        try:
            if link:
                self.products.validate_shopee_url(link)
            options = self._product_pipeline_options(seed=selected_job_id or link)
            selected_job = self.products.get_job(selected_job_id) if selected_job_id else None
            if selected_job:
                options = product_audio_options(options, selected_job.get("audio_choices"))
                options.pop('generated_music_options', None)
                if selected_job.get('generated_music_options') is not None:
                    options['generated_music_options'] = copy.deepcopy(selected_job['generated_music_options'])
            video_provider = str((selected_job or {}).get("video_ai_provider") or options["video_provider"]).strip().lower()
            if video_provider not in {"flow", "meta_ai"}:
                raise ValueError("ผู้สร้างวิดีโอในงานนี้ไม่รองรับ")
            options["video_provider"] = video_provider
            self.video_ai_provider.set(next(label for label, key in VIDEO_AI_PROVIDERS.items() if key == video_provider))
            voice_ready = bool(selected_job and selected_job.get("voice_status") == "ready")
            if (options.get("audio_choices") or {}).get("mode", "api") == "api" and not voice_ready and not options["voice_api_key"]:
                raise ValueError("กรุณาใส่และบันทึก API Key ในหน้า AI Voice ก่อนเริ่ม")
            if (options.get("audio_choices") or {}).get("mode", "api") == "api" and not voice_ready and not options["voice_reference_id"] and not Path(options["voice_reference_file"]).is_file():
                raise ValueError("กรุณาเลือกเสียงในหน้า AI Voice หรือเลือกไฟล์เสียงต้นแบบก่อนเริ่ม")
            subtitle_ready = bool(selected_job and selected_job.get("subtitle_status") == "ready")
            if (options.get("audio_choices") or {}).get("mode") != "none" and options["subtitle_enabled"] and not subtitle_ready and not options["subtitle_credential"]:
                raise ValueError("เปิด Subtitle ไว้ แต่ยังไม่ได้เชื่อม Token ในหน้า AI Subtitle")
        except Exception as exc:
            messagebox.showinfo("ยังเริ่มสร้างคลิปไม่ได้", str(exc))
            return
        # A valid start/resume supersedes the previous terminal popup.  The
        # bridge heartbeat may already be healthy while Hybrid UI still shows
        # the last failure, which made a recovered Flow job look disconnected.
        self._clear_automation_error_log(selected_job_id)
        self._product_pipeline_job_id = selected_job_id or "กำลังสร้าง Job"
        self._product_cancel_event = threading.Event()
        self.product_run_button.configure(state="disabled")
        self._show_product_progress(selected_job_id or "กำลังตรวจลิงก์")
        provider_name = "Gemini Web" if options["provider"] == "gemini" else "ChatGPT Web"
        _extension, compatible = self._compatible_extension()
        # A Flow checkpoint must open Flow even while Chrome/Extension is
        # currently offline.  Opening the AI provider here strands a ready
        # image+voice Job at 52% until the worker later repairs the browser.
        resume_flow_shot = self._focus_product_flow_checkpoint(
            selected_job_id, selected_job, queue_focus=bool(compatible), video_provider=options["video_provider"]
        )
        if resume_flow_shot:
            self._update_product_progress({
                "percent": 52 + max(0, resume_flow_shot - 1) * 8,
                "stage": "flow",
                "message": f"เปิด {self._video_provider_label(options['video_provider'])} เพื่อทำต่อแล้ว",
                "detail": f"ทำต่อจากช็อต {resume_flow_shot}/3 • ใช้รูป เสียง และคลิปที่เสร็จแล้วทั้งหมด",
            })
        else:
            self._activate_or_launch_chrome(
                "https://affiliate.shopee.co.th/offer/product_offer" if link else self._ai_web_url(options["provider"])
            )
            self._update_product_progress({"percent": 1, "stage": "product", "message": "กำลังเปิด Google Chrome อัตโนมัติ", "detail": "เมื่อ Extension เชื่อมแล้ว ระบบจะรับ Job และทำต่อเอง"})
        self._write_console(f"PRODUCT AUTO • เริ่มงาน • {selected_job_id or 'ลิงก์ใหม่'} • ภาพจาก {provider_name} • Subtitle {'เปิด' if options['subtitle_enabled'] else 'ปิด'}", "success")
        self._creation_product_worker = guarded_thread(self, selected_job_id, self._product_pipeline_worker,
            args=(link, selected_job_id, options, self._product_cancel_event),
            daemon=True,
        )

    def _focus_product_flow_checkpoint(self, job_id, job, queue_focus=True, video_provider=None):
        """Make a resumed video-provider checkpoint visible immediately after one click."""
        if not job_id or not job:
            return 0
        folder = self.products.root / str(job_id)
        if job.get("voice_status") != "ready" or not ai_package_complete(job, folder):
            return 0
        video_provider = str(video_provider or job.get('video_ai_provider') or 'flow')
        if video_provider == 'meta_ai':
            receipts = dict(job.get('meta_clip_receipts') or {})
            completed = {int(index) for index, proof in receipts.items()
                         if proof.get('sha256') and (folder / str((job.get('meta_clips') or {}).get(str(index)) or '')).is_file()}
        else:
            completed = set(completed_product_segments(job, folder))
        count = int(job.get('flow_target_clip_count') or len(job.get('composition_images') or job.get('generated_images') or job.get('source_images') or []) or 3)
        shot_index = next((index for index in range(1, count + 1) if index not in completed), 0)
        if not shot_index:
            return 0
        # When the Extension is online it must own the first navigation. Opening
        # a raw Flow URL before `focus_flow_web` lets the content helper load with
        # shot_index=0, cache the wrong package and later consume an inspect for
        # the next shot against the previous project's result cards. When the
        # Extension is offline, launch only the URL; the worker queues one
        # authoritative `open_flow` after heartbeat returns.
        if video_provider == 'meta_ai':
            self._activate_or_launch_chrome('https://www.meta.ai/')
        else:
            self._activate_or_launch_chrome("https://labs.google/fx/th/tools/flow")
            if queue_focus:
                self.bridge.queue_extension_command("focus_flow_web", job_id, shot_index)
        self._write_console(
            f"{job_id} • RESUME {self._video_provider_label(video_provider).upper()} • เปิด Chrome และทำต่อช็อต {shot_index}/3 จาก Checkpoint",
            "success",
        )
        return shot_index

    def _show_product_progress(self, job_id):
        if self._product_progress_dialog and self._product_progress_dialog.winfo_exists():
            self._product_progress_dialog.destroy()
        self._product_progress_value.set(0)
        self._product_progress_percent.set("0%")
        self._product_progress_message.set("กำลังตรวจลิงก์และเตรียม Product Job")
        self._product_progress_detail.set("เปอร์เซ็นต์เพิ่มจากไฟล์และสถานะที่เสร็จจริง")
        self._product_progress_job.set(job_id)
        self._product_progress_stage_widgets = {}
        if self.hybrid_engine:
            self._product_progress_dialog = None
            return
        dialog = tk.Toplevel(self.root)
        self._product_progress_dialog = dialog
        dialog.title("SmartFlow Product Automation")
        dialog.geometry("590x570")
        dialog.resizable(False, False)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", self._cancel_product_pipeline)
        shell = tk.Frame(dialog, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        shell.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(shell, text="SMARTFLOW • ONE-CLICK PRODUCT", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 9)).pack(pady=(18, 3))
        tk.Label(shell, text="กำลังสร้างคลิปขายสินค้า", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 20)).pack()
        tk.Label(shell, textvariable=self._product_progress_job, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(pady=(3, 6))
        tk.Label(shell, textvariable=self._product_progress_percent, bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 27)).pack()
        style = ttk.Style(dialog)
        style.configure("Product.Horizontal.TProgressbar", troughcolor=COLORS["panel_3"], background=COLORS["blue"], bordercolor=COLORS["panel_3"], lightcolor=COLORS["blue"], darkcolor=COLORS["blue"], thickness=14)
        ttk.Progressbar(shell, variable=self._product_progress_value, maximum=100, style="Product.Horizontal.TProgressbar").pack(fill="x", padx=32, pady=(3, 10))
        tk.Label(shell, textvariable=self._product_progress_message, bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 11), wraplength=500, justify="center").pack()
        tk.Label(shell, textvariable=self._product_progress_detail, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=500, justify="center").pack(pady=(3, 10))
        stages = tk.Frame(shell, bg=COLORS["panel_2"], highlightbackground=COLORS["line"], highlightthickness=1)
        stages.pack(fill="x", padx=32)
        for index, (key, label, _start, _end) in enumerate(PRODUCT_STAGES, 1):
            row = tk.Frame(stages, bg=COLORS["panel_2"]); row.pack(fill="x", padx=14, pady=(7 if index == 1 else 3, 7 if index == len(PRODUCT_STAGES) else 3))
            bullet = tk.Label(row, text="○", width=2, bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI Semibold", 10)); bullet.pack(side="left")
            label_widget = tk.Label(row, text=label, bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 9)); label_widget.pack(side="left", padx=5)
            self._product_progress_stage_widgets[key] = (bullet, label_widget)
        self._product_progress_note = tk.Label(shell, text="ยกเลิกได้ • ระบบเก็บภาพ เสียง และคลิปที่เสร็จแล้วไว้ทำต่อ", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8))
        self._product_progress_note.pack(pady=(10, 5))
        footer = tk.Frame(shell, bg=COLORS["panel"]); footer.pack(fill="x", padx=32, pady=(0, 14))
        self._product_progress_open = ttk.Button(footer, text="เปิดโฟลเดอร์ผลงาน", style="Ghost.TButton")
        self._product_cancel_button = tk.Button(footer, text="ยกเลิกการทำงาน", command=self._cancel_product_pipeline, bg="#3A1730", fg="#FFB2C2", activebackground="#5A1D3A", activeforeground="white", relief="flat", bd=0, padx=18, pady=9, font=("Segoe UI Semibold", 9), cursor="hand2")
        self._product_cancel_button.pack(side="right")
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()

    def _update_product_progress(self, payload):
        percent = max(0, min(100, int(round(float(payload.get("percent", 0))))))
        if self._product_progress_dialog and self._product_progress_dialog.winfo_exists():
            percent = max(int(self._product_progress_value.get()), percent)
        stage = str(payload.get("stage") or "product")
        message = str(payload.get("message") or "กำลังทำงาน")
        detail = str(payload.get("detail") or "ระบบบันทึก Checkpoint อัตโนมัติ")
        job_id = str(payload.get("job_id") or self._product_pipeline_job_id)
        if job_id:
            # Status-only recovery notices must not claim the worker lock. A
            # real Product worker always owns a cancellation event before it
            # publishes progress.
            if self._product_cancel_event is not None:
                self._product_pipeline_job_id = job_id
            self._product_progress_job.set(job_id)
        self._product_progress_value.set(percent)
        self._product_progress_percent.set(f"{percent}%")
        self._product_progress_message.set(message)
        self._product_progress_detail.set(detail)
        self.status.set(f"คลิปสินค้า • {percent}% • {message}")
        self._write_console(f"{job_id or 'PRODUCT'} • {percent}% • {message} • {detail}")
        if payload.get("action_required"):
            provider = str(payload.get("provider") or "gemini").strip().lower()
            action_kind = str(payload.get("action_kind") or "verification_required")
            service_name = "Google Flow" if provider == "flow" else ("Gemini Web" if provider == "gemini" else "ChatGPT Web")
            button_label = (
                "ทำต่อด้วยบัญชี Google Flow ใหม่"
                if action_kind == "credit_exhausted"
                else f"เปิด {service_name} เพื่อเข้าสู่ระบบ"
                if action_kind == "login_required"
                else "เปิด Chrome เพื่อกดยืนยัน"
            )
            self._product_verification_job = job_id
            self._product_web_action = {
                "action_kind": action_kind, "service": provider, "button_label": button_label,
                "shot_index": int(payload.get("shot_index") or 0),
            }
            if self._product_progress_dialog and self._product_progress_dialog.winfo_exists():
                self._product_progress_open.configure(
                    text=button_label,
                    command=lambda: self._focus_product_web_action(job_id),
                )
                if not self._product_progress_open.winfo_manager():
                    self._product_progress_open.pack(side="left")
                self._product_progress_note.configure(
                    text="กำลังหยุดรอคุณ • งานและ Checkpoint ที่เสร็จแล้วไม่หาย",
                    fg=COLORS["yellow"],
                )
                self._product_progress_dialog.lift()
            if not payload.get("already_notified"):
                self.root.bell()
        elif self._product_verification_job == job_id:
            self._product_verification_job = ""
            self._product_web_action = {}
            if self._product_progress_dialog and self._product_progress_dialog.winfo_exists():
                if str(self._product_progress_open.cget("text")).startswith("เปิด "):
                    self._product_progress_open.pack_forget()
                self._product_progress_note.configure(
                    text="ยืนยันเรียบร้อยแล้ว • ระบบกำลังทำต่อจาก Checkpoint เดิม",
                    fg=COLORS["green"],
                )
        for key, _label, start, end in PRODUCT_STAGES:
            bullet, text = self._product_progress_stage_widgets.get(key, (None, None))
            if not bullet:
                continue
            if percent >= end:
                bullet.configure(text="●", fg=COLORS["green"]); text.configure(fg=COLORS["green"])
            elif key == stage or start <= percent < end:
                bullet.configure(text="◉", fg=COLORS["cyan"]); text.configure(fg=COLORS["text"])
            else:
                bullet.configure(text="○", fg=COLORS["muted"]); text.configure(fg=COLORS["muted"])

    def _cancel_product_pipeline(self):
        cancel_event = self._product_cancel_event
        if cancel_event is None:
            # A stale recovery callback can leave the Job id active after its
            # worker has already exited. Give cancellation its own event so the
            # UI can still be finalized instead of waiting forever for a worker
            # acknowledgement that will never arrive.
            cancel_event = threading.Event()
            self._product_cancel_event = cancel_event
        cancel_event.set()
        job_id = self._product_pipeline_job_id
        if job_id.startswith("JOB-"):
            try:
                self.bridge.queue_extension_command("stop_flow_generation", job_id)
            except Exception:
                pass
            try:
                self.bridge.queue_extension_command("cancel_story_chatgpt", job_id)
            except Exception:
                pass
            try:
                self.products.set_automation_state(job_id, "cancelled", "cancelled")
            except Exception:
                pass
        self._product_verification_job = ""
        self._product_web_action = {}
        self._product_progress_message.set("กำลังหยุดงานอย่างปลอดภัย...")
        self._product_progress_detail.set("จะไม่เริ่มขั้นตอนถัดไป และเก็บไฟล์ที่เสร็จแล้วไว้")
        self._write_console(f"{job_id or 'PRODUCT'} • กำลังยกเลิกอย่างปลอดภัย • เก็บ Checkpoint ที่เสร็จแล้ว", "error")
        if hasattr(self, "_product_cancel_button"):
            self._product_cancel_button.configure(state="disabled", text="กำลังยกเลิก...")
        # Do not make the Hybrid UI depend on a possibly wedged browser or
        # worker thread. Normal workers acknowledge via product_pipeline_cancelled;
        # this bounded fallback clears only the same Job+Event pair.
        self.root.after(700, lambda active_job=job_id, active_event=cancel_event: self._finish_product_cancel(active_job, active_event))

    def _finish_product_cancel(self, job_id, cancel_event):
        if cancel_event is not self._product_cancel_event or not cancel_event.is_set():
            return False
        if self._product_pipeline_job_id not in {"", job_id}:
            return False
        self._product_pipeline_job_id = ""
        self._product_cancel_event = None
        self._product_verification_job = ""
        self._product_web_action = {}
        if hasattr(self, "product_run_button"):
            self.product_run_button.configure(state="normal")
        self.status.set(f"ยกเลิกงานแล้ว • {job_id or 'Product Job'}")
        self._finish_product_popup(
            "cancelled", "ยกเลิกการทำงานแล้ว",
            "เก็บรูป เสียง วิดีโอ และ Checkpoint ที่เสร็จแล้วไว้ • กดทำต่อภายหลังได้",
        )
        self._desktop_set_notice("success", "ยกเลิกงานแล้ว • เก็บ Checkpoint และไฟล์ที่เสร็จแล้วไว้ครบ")
        self._write_console(f"{job_id or 'PRODUCT'} • CANCEL CONFIRMED • ปลดสถานะค้างของหน้าโปรแกรมแล้ว", "success")
        self._refresh()
        self._close_automation_browser(job_id, "ยกเลิกงานแล้ว")
        self._creation_product_terminal(job_id, "cancelled", "ผู้ใช้ยกเลิก • เก็บ Checkpoint แล้ว")
        return True

    def _close_product_progress(self):
        if self._product_progress_dialog and self._product_progress_dialog.winfo_exists():
            try: self._product_progress_dialog.grab_release()
            except Exception: pass
            self._product_progress_dialog.destroy()
        self._product_progress_dialog = None

    def _finish_product_popup(self, state, message, detail="", target=None):
        if state == "success":
            self._update_product_progress({"percent": 100, "stage": "audio", "message": message, "detail": detail})
        else:
            self._product_progress_percent.set("ยกเลิก" if state == "cancelled" else "หยุด")
            self._product_progress_message.set(message)
            self._product_progress_detail.set(detail)
        if self._product_progress_dialog and self._product_progress_dialog.winfo_exists():
            try: self._product_progress_dialog.grab_release()
            except Exception: pass
            if target:
                self._product_progress_open.configure(text="เปิดดูวิดีโอ", command=lambda: os.startfile(str(Path(target))))
                self._product_progress_open.pack(side="left")
            elif self._product_pipeline_job_id.startswith("JOB-"):
                checkpoint_job_id = self._product_pipeline_job_id
                self._product_progress_open.configure(text="เปิดโฟลเดอร์ Checkpoint", command=lambda active_job=checkpoint_job_id: self._open_folder(self.products.root / active_job))
                self._product_progress_open.pack(side="left")
            color = COLORS["green"] if state == "success" else COLORS["danger"]
            self._product_progress_note.configure(text="งานเสร็จแล้ว • พบวิดีโอในคลังวิดีโอ" if state == "success" else "ไฟล์ที่เสร็จแล้วไม่ถูกลบ • เลือก Job แล้วกดปุ่มเดิมเพื่อทำต่อ", fg=color)
            self._product_cancel_button.configure(state="normal", text="ปิด", command=self._close_product_progress, bg="#17233F", fg=COLORS["text"])

    def _close_automation_browser(self, job_id, reason="งานจบแล้ว"):
        """Close only SmartPost web tabs; never terminate unrelated Chrome tabs."""
        queue_needs_fresh_browser = bool(self.story_queue.item_for_job(job_id)) and bool(self.story_queue.snapshot()["active_count"])
        if not bool(self.cfg.get("close_chrome_after_job", True)) and not queue_needs_fresh_browser:
            return
        try:
            _extension, compatible = self._compatible_extension()
            if not compatible:
                self._write_console(f"{job_id or 'JOB'} • ไม่พบ Chrome Extension ที่ออนไลน์ • ข้ามการปิดแท็บอัตโนมัติ", "log")
                return
            command = self.bridge.queue_extension_command("close_automation_browser", job_id)
            if queue_needs_fresh_browser:
                self._story_queue_browser_recycle = {
                    "job_id": str(job_id or ""),
                    "command_id": command["id"],
                    "requested_at": time.monotonic(),
                    "retries": 0,
                }
            self._write_console(f"{job_id or 'JOB'} • {reason} • กำลังปิดแท็บ Chrome ของ SmartFlow อัตโนมัติ", "success")
            return command
        except Exception as exc:
            self.log.warning("job_id=%s state=CLOSE_AUTOMATION_BROWSER result=skip error=%s", job_id, exc)

    def _close_saved_flow_tab(self, job_id, shot_index, saved):
        # Cleanup is optional housekeeping AFTER the durable media checkpoint.
        # Failure here must never cause regeneration of an accepted clip.
        if not bool((getattr(self, 'cfg', {}) or {}).get('close_chrome_after_job', True)):
            return
        if not Path(saved).is_file() or Path(saved).stat().st_size <= 0:
            return
        try:
            return self.bridge.queue_extension_command('close_automation_browser', job_id, shot_index)
        except Exception:
            return None  # Whole-job cleanup remains the final retry path.

    def _product_progress_event(self, job_id, percent, stage, message, detail="", **extra):
        payload = {"job_id": job_id, "percent": percent, "stage": stage, "message": message, "detail": detail}
        payload.update(extra)
        self.events.put(("product_pipeline_progress", payload))

    def _wait_product_job(self, job_id, predicate, cancel_event, timeout, stage, message):
        deadline = time.monotonic() + timeout
        last_analysis_update = None
        last_motion_update = None
        last_motion_signature = ""
        last_browser_launch = 0.0
        browser_opened = False
        browser_relaunch_count = 0
        ai_submission_observed = False
        verification_waiting = False
        verification_notified = False
        while time.monotonic() < deadline:
            check_cancelled(cancel_event)
            job = self.products.get_job(job_id)
            if predicate(job):
                return job
            extension = self.bridge.extension_status()
            clients = extension.get("clients") or []
            compatible = next((item for item in clients if str(item.get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION), None)
            now = time.monotonic()
            chrome_missing = not self._chrome_window_available()
            # Focus once while Extension connects. If Chrome stays unavailable,
            # use the same bounded reopen budget as the Story browser monitor.
            may_open_browser = not browser_opened or (chrome_missing and browser_relaunch_count < 4)
            if (not compatible or chrome_missing) and may_open_browser and now - last_browser_launch >= 15:
                provider = str(job.get("image_ai_provider") or "chatgpt")
                target = self._ai_web_url(provider) if stage == "ai" else "https://affiliate.shopee.co.th/offer/product_offer"
                self._activate_or_launch_chrome(target)
                if browser_opened:
                    browser_relaunch_count += 1
                browser_opened = True
                last_browser_launch = now
                provider_name = "Gemini Web" if provider == "gemini" else "ChatGPT Web"
                waiting_for = provider_name if stage == "ai" else "Shopee Affiliate"
                self._product_progress_event(job_id, 3 if stage == "ai" else 2, stage, "กำลังเปิด Google Chrome อัตโนมัติ", f"กำลังเปิด {waiting_for} • Extension เชื่อมแล้วจะทำต่อเอง")
            expected_ai_run = str((getattr(self.bridge, '_extension_runs', {}).get(("ai", job_id, 0)) or {}).get("run_id") or "")
            client = next((item for item in clients
                if str(item.get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION
                and str(item.get("ai_job_id") or "") == job_id
                and (not expected_ai_run or str(item.get("ai_run_id") or "") == expected_ai_run)), None)
            if client:
                locked_provider = str(job.get("image_ai_provider") or "chatgpt").strip().lower()
                client_provider = str(client.get("ai_provider") or locked_provider).strip().lower()
                if stage == "ai" and client_provider != locked_provider:
                    raise RuntimeError(f"Extension เปิด {client_provider} ไม่ตรงกับ Provider ของ Job ({locked_provider})")
                step = str(client.get("ai_step") or "")
                ai_message = str(client.get("ai_message") or "")
                image_count = int(client.get("ai_image_count") or 0)
                if stage == "ai":
                    diagnostics = client.get("ai_send_diagnostics") or {}
                    # Keep the observation even if the client disconnects.
                    # A local deadline cannot authorize a fresh analysis after
                    # an accepted request or a physical Send with unknown result.
                    ai_submission_observed = (
                        ai_submission_observed
                        or step in {"ai_send_accepted", "ai_send_waiting_acceptance", "waiting_for_analysis",
                                    "analysis_ready", "analysis_saved", "repairing_analysis"}
                        or bool(diagnostics.get("submission_proof"))
                        or diagnostics.get("dispatch_completed") is True
                        or diagnostics.get("gesture_phase") in {"pressed", "released", "release_uncertain"}
                    )
                # Only a new owned analysis progress report renews this wait;
                # a heartbeat replaying an old ai_updated_at must not do so.
                if stage == "ai" and step == "waiting_for_analysis":
                    analysis_update = client.get("ai_updated_at")
                    if analysis_update and analysis_update != last_analysis_update:
                        last_analysis_update = analysis_update
                        deadline = max(deadline, now + timeout)
                if stage == "ai" and step == "preparing_flow_prompt":
                    update = client.get("ai_updated_at")
                    signature = str(client.get("ai_response_signature") or "")
                    if update and update != last_motion_update:
                        last_motion_update = update
                        if client.get("ai_response_active") is True or (signature and signature != last_motion_signature):
                            deadline = max(deadline, now + timeout)
                        last_motion_signature = signature
                if step == "user_action_required":
                    provider = locked_provider
                    checkpoint_count = max(len(job.get("generated_images") or []), len(job.get("partial_generated_images") or []))
                    percent = 14 + min(22, round(22 * checkpoint_count / 3))
                    action_kind = str(client.get("ai_action_kind") or "verification_required")
                    provider_name = "Gemini Web" if provider == "gemini" else "ChatGPT Web"
                    verification_waiting = True
                    deadline += 2.5  # Manual login/verification time must not consume the AI timeout.
                    self._product_progress_event(
                        job_id, percent, stage,
                        f"กรุณาเข้าสู่ระบบ {provider_name} ก่อน" if action_kind == "login_required" else "ต้องการให้คุณยืนยันว่าไม่ใช่โปรแกรมอัตโนมัติ",
                        ("กดเปิด Chrome แล้ว Login • ระบบจะทำต่อจาก Checkpoint เดิมเอง" if action_kind == "login_required"
                         else "เปิด Chrome แล้วติ๊ก ‘ฉันไม่ใช่โปรแกรมอัตโนมัติ’ • เสร็จแล้วระบบจะทำต่อเอง"),
                        action_required=True, provider=provider, action_kind=action_kind,
                        already_notified=verification_notified,
                    )
                    verification_notified = True
                    if cancel_event.wait(2):
                        check_cancelled(cancel_event)
                    continue
                if step == "user_action_resolved":
                    provider = locked_provider
                    checkpoint_count = max(len(job.get("generated_images") or []), len(job.get("partial_generated_images") or []))
                    self.bridge.clear_ai_progress(job_id)
                    self.bridge.queue_extension_command("resume_chatgpt", job_id, provider_hint=provider)
                    verification_waiting = False
                    verification_notified = False
                    self._product_progress_event(
                        job_id, 14 + min(22, round(22 * checkpoint_count / 3)), stage,
                        "เข้าสู่ระบบ/ยืนยันสำเร็จแล้ว • กำลังทำงานต่ออัตโนมัติ",
                        f"ใช้รูปจาก Checkpoint เดิม {min(3, checkpoint_count)}/3 รูป",
                    )
                    if cancel_event.wait(2):
                        check_cancelled(cancel_event)
                    continue
                if verification_waiting:
                    verification_waiting = False
                    verification_notified = False
                percent = 14 + min(22, round(22 * image_count / 3)) if stage == "ai" else 8
                detail = f"สร้างภาพแล้ว {min(3, image_count)}/3 รูป" if stage == "ai" else "กำลังอ่านข้อมูลจริงจากหน้าสินค้า"
                if stage == 'ai' and (step in {'preparing_flow_prompt', 'flow_prompt_saved'} or 'FLOW_PLAN_REVIEW' in ai_message):
                    from core.product_visual_contract import product_motion_progress
                    detail = product_motion_progress(self.products.root / job_id, job)
                self._product_progress_event(job_id, percent, stage, ai_message or message, detail)
                if step in {"error", "failed", "cancelled"}:
                    raise RuntimeError(ai_message or "AI Web ทำงานไม่สำเร็จ")
            if cancel_event.wait(2):
                check_cancelled(cancel_event)
        if stage == "ai" and ai_submission_observed:
            raise TimeoutError(f"AI_WEB_WAIT_REVIEW • {message} • เคยส่งคำขอแล้วแต่ยังรับผลไม่ครบ เก็บแท็บเดิมเพื่อตรวจต่อ ไม่เริ่มวิเคราะห์ใหม่อัตโนมัติ")
        raise TimeoutError(message)

    def _wait_product_ai_with_recovery(self, job_id, folder, cancel_event):
        """Resume the same AI analysis and only missing image checkpoints."""
        job = self.products.get_job(job_id)
        action = "resume_chatgpt" if job.get("ai_status") == "ready" or job.get("generated_images") or job.get("partial_generated_images") else "open_chatgpt"
        provider_hint = str(job.get("image_ai_provider") or "chatgpt").strip().lower()
        while True:
            self.bridge.clear_ai_progress(job_id)
            self.bridge.queue_extension_command(action, job_id, provider_hint=provider_hint)
            active_provider = str(provider_hint or job.get("image_ai_provider") or "chatgpt").strip().lower()
            # Layered visibility recovery: the first command creates/reloads
            # the exact AI tab, the second focuses that Job tab after creation,
            # and the Windows-level focus restores Chrome if the browser window
            # was minimized or left behind SmartFlow.
            self.bridge.queue_extension_command("focus_ai_web", job_id, provider_hint=active_provider)
            threading.Thread(target=self._focus_chrome_after_launch, daemon=True).start()
            try:
                completed = self._wait_product_job(
                    job_id,
                    lambda item: ai_package_complete(item, folder),
                    cancel_event,
                    1500,
                    "ai",
                    "หมดเวลารอ AI Web สร้างภาพและคอนเทนต์",
                )
                self.products.reset_ai_recovery_attempts(job_id)
                return completed
            except (RuntimeError, TimeoutError) as exc:
                job = self.products.get_job(job_id)
                failover_action = product_provider_failover_action(job, str(exc))
                recovery_action = product_ai_recovery_action(job, str(exc))
                attempts = int(job.get("ai_auto_recovery_attempts") or 0)
                if (not failover_action and recovery_action != "resume_chatgpt") or attempts >= PRODUCT_AI_AUTO_RECOVERY_LIMIT:
                    raise
                recovered = self.products.mark_ai_recovering(job_id, str(exc))
                if failover_action:
                    recovered = self.products.set_image_ai_provider(job_id, "chatgpt")
                attempt = int(recovered.get("ai_auto_recovery_attempts") or 1)
                checkpoint_count = len(recovered.get("partial_generated_images") or [])
                percent = 14 + round(22 * min(3, checkpoint_count) / 3)
                provider_name = "Gemini Web" if recovered.get("image_ai_provider") == "gemini" else "ChatGPT Web"
                next_action = failover_action or product_ai_recovery_command(recovered, attempt)
                next_provider_hint = str(recovered.get("image_ai_provider") or "chatgpt").strip().lower()
                recovery_detail = (
                    f"Gemini ปฏิเสธ/ส่งข้อมูลไม่ครบ • สลับไป ChatGPT Web โดยเก็บ Checkpoint {checkpoint_count}/3 รูป"
                    if failover_action else
                    f"เก็บภาพแล้ว {checkpoint_count}/3 • วิเคราะห์ Job เดิมใหม่ผ่าน {provider_name}"
                    if next_action == "open_chatgpt"
                    else f"เก็บภาพแล้ว {checkpoint_count}/3 • Reload {provider_name} เดิมโดยใช้ Analysis และ Checkpoint เดิม"
                    if next_action == "restart_chatgpt_images"
                    else f"เก็บภาพแล้ว {checkpoint_count}/3 • Reload {provider_name} เดิมและสร้างเฉพาะรูปที่ขาด"
                )
                self._product_progress_event(
                    job_id,
                    percent,
                    "ai",
                    f"กู้คืนชั้นที่ 2 อัตโนมัติ {attempt}/{PRODUCT_AI_AUTO_RECOVERY_LIMIT}",
                    recovery_detail,
                )
                self._write_console(
                    f"{job_id} • AI RECOVERY L2 {attempt}/{PRODUCT_AI_AUTO_RECOVERY_LIMIT} • checkpoint {checkpoint_count}/3 • {exc}",
                    "log",
                )
                wait_seconds = 3 if attempt == 1 else 6
                if cancel_event.wait(wait_seconds):
                    check_cancelled(cancel_event)
                action = next_action
                provider_hint = next_provider_hint
                job = recovered

    def _prepare_product_narration(self, job_id, folder, options, cancel_event):
        """Expose the existing serial voice step; never open Flow early."""
        check_cancelled(cancel_event)
        started = time.monotonic()
        self.log.info("job_id=%s state=PRODUCT_HANDOFF phase=images_saved_prepare_voice", job_id)
        self._product_progress_event(job_id, 38, "voice", "ภาพครบ 3/3 แล้ว • กำลังเตรียมเสียงพากย์",
            "ต้องเตรียมไฟล์เสียงให้พร้อมก่อนเปิด Google Flow • ยังไม่เริ่มสร้างวิดีโอ")
        job, script = self.products.spoken_script(job_id)
        reused = job.get("voice_status") == "ready" and (folder / str(job.get("voice_path") or "")).is_file()
        previous_message = None

        def progress(message):
            nonlocal previous_message
            check_cancelled(cancel_event)
            if message == previous_message:
                return
            previous_message = message
            elapsed = max(0, int(time.monotonic() - started))
            self._product_progress_event(job_id, 38, "voice", "ภาพครบแล้ว • กำลังสร้างเสียงพากย์ AI",
                f"{message} • ผ่านไป {elapsed} วินาที • เสียงพร้อมแล้วจะเปิด Google Flow อัตโนมัติ")

        if not reused:
            self._create_voice_worker(job_id, options["voice_api_key"], options["voice_reference_id"],
                options["voice_reference_file"], script, options["voice"], cancel_event=cancel_event,
                emit_event=False, on_progress=progress)
        check_cancelled(cancel_event)
        self.log.info("job_id=%s state=PRODUCT_HANDOFF phase=voice_ready reused=%s elapsed_ms=%s",
            job_id, reused, round((time.monotonic() - started) * 1000))
        self._product_progress_event(job_id, 52, "flow", "เสียงพากย์พร้อม • กำลังเข้าสู่ Google Flow",
            "ใช้ไฟล์เสียงเดิมที่พร้อมแล้ว • ไม่สร้างเสียงซ้ำ" if reused
            else "บันทึกไฟล์เสียงแล้ว • ขั้นตอนถัดไปตรวจช็อตเดิมและเปิด Google Flow")

    def _product_pipeline_worker(self, link, selected_job_id, options, cancel_event):
        from contextlib import ExitStack
        from core.render_backend import render_session
        render_scope = ExitStack()
        job_id = selected_job_id
        try:
            check_cancelled(cancel_event)
            guard = app_guard(self)
            with guard.lock:
                if link:
                    # A link may reuse an existing job whose id is not known yet.
                    if any(claim.deleting for claim in guard.claims):
                        raise ValueError('กำลังลบไฟล์ • รอให้เสร็จก่อนตรวจลิงก์เพื่อเริ่มงาน')
                    job, _created = self.products.import_link(link)
                    job_id = job['id']
                else:
                    job = self.products.get_job(job_id)
                render_scope.enter_context(guard.start(job_id, options))
            self._creation_attach_product(options, job_id, cancel_event)
            if link and _created:
                captured_logo = copy.deepcopy((options.get('finish_config') or {}).get('logo_layout'))
                self.products._manifest_store(self.products.root / job_id / 'job.json').update(
                    lambda current: {**current, 'logo_layout': captured_logo,
                        **({'media_finish_config': {key: copy.deepcopy(value) for key, value in
                            (options.get('finish_config') or {}).items() if key.startswith('logo_')}} if captured_logo is not None else {}),
                        **({'generated_music_options': copy.deepcopy(options['generated_music_options'])}
                           if options.get('generated_music_options') is not None else {})})
            if link and _created and "presenter" not in job:
                selection = options.get("presenter") or {"enabled": False}
                if selection.get("enabled"):
                    self.presenters.assets(selection)
                self.products._manifest_store(self.products.root / job_id / "job.json").update(lambda current: {**current, "presenter": selection})
            self.products.reset_ai_recovery_attempts(job_id)
            self.products.set_automation_state(job_id, "running", "product")
            self.products.set_image_ai_provider(job_id, options["provider"])
            self.products.set_ai_web_model(job_id, options["provider"], options["ai_web_model"])
            self.products.set_video_ai_provider(job_id, options["video_provider"])
            self.products.set_subtitle_requested(job_id, options["subtitle_enabled"])
            self.products._manifest_store(self.products.root / job_id / "job.json").update(
                lambda current: {**current, "fictional_ai_characters_confirmed": options.get("fictional_ai_characters_confirmed") is True,
                                 "flow_settings": copy.deepcopy(current.get("flow_settings", options.get("flow_settings", {}))),
                                 "ai_cover_options": copy.deepcopy(current.get('ai_cover_options', options.get('ai_cover_options', {})))})
            self.products._manifest_store(self.products.root / job_id / 'job.json').update(
                lambda current:{**current,'green_options':copy.deepcopy(current.get('green_options',options.get('green_options',{}) if link and _created else {}))})
            self.products._manifest_store(self.products.root / job_id / 'job.json').update(
                lambda current: {**current, 'render_snapshot': copy.deepcopy(current.get('render_snapshot',
                    options.get('render', {}) if link and _created else {}))})
            if options.get("audio_choices"):
                self.products._manifest_store(self.products.root / job_id / "job.json").update(lambda current: {**current, "audio_choices": options["audio_choices"]})
            captured_render = self.products.get_job(job_id).get('render_snapshot')
            render_scope.enter_context(render_session(captured_render,
                lambda message: self._product_progress_event(job_id, 88, 'finishing', message,
                    'ประมวลผลไฟล์ในเครื่อง • ไม่สร้างฉาก AI ซ้ำ'),
                self.products.root/job_id/'logs'/'render-local.json'))
            self._product_progress_event(job_id, 4, "product", "สร้าง Product Job แล้ว", "กำลังตรวจชื่อ รายละเอียด และรูปสินค้าจริง")
            job = self.products.get_job(job_id)
            if not real_product_data(job):
                capture_command = self.bridge.queue_extension_command("capture_shopee_product", job_id)
                capture_command_id = str((capture_command or {}).get("id") or "")
                if not capture_command_id:
                    raise RuntimeError("สร้างคำสั่งอ่านสินค้า Shopee ไม่สำเร็จ • ยังไม่ได้ส่งงานไป AI")

                def product_data_or_capture_error(current):
                    if real_product_data(current):
                        return True
                    outcome = self.bridge.extension_command_status(capture_command_id)
                    if not outcome:
                        raise RuntimeError("คำสั่งอ่านสินค้า Shopee หายไประหว่างทำงาน • ยังไม่ได้ส่งงานไป AI")
                    command_status = str(outcome.get("status") or "pending").lower()
                    if command_status in {"failed", "cancelled", "completed"}:
                        from core.product_pipeline import source_image_capture_detail
                        detail = str(outcome.get("error") or "อ่านชื่อและรูปสินค้าไม่ครบ")[:400]
                        capture_detail = source_image_capture_detail(current)
                        if capture_detail:
                            detail += " • " + capture_detail
                        raise RuntimeError(f"อ่านข้อมูล Shopee ไม่สำเร็จ • {detail} • ยังไม่ได้ส่งงานไป AI")
                    return False

                job = self._wait_product_job(job_id, product_data_or_capture_error, cancel_event, 150, "product", "หมดเวลารอข้อมูลสินค้าจาก Shopee")
            self._product_progress_event(job_id, 12, "ai", "ข้อมูลสินค้าพร้อม", f"ส่งรูปจริงเข้า {'Gemini Web' if options['provider'] == 'gemini' else 'ChatGPT Web'}")
            folder = self.products.root / job_id
            if not ai_package_complete(job, folder):
                job = self._wait_product_ai_with_recovery(job_id, folder, cancel_event)
            self.products.approve_ai_result(job_id)
            self.products.set_automation_state(job_id, "running", "voice")
            if (options.get("audio_choices") or {}).get("mode", "api") == "api":
                self._prepare_product_narration(job_id, folder, options, cancel_event)
            else:
                self._product_progress_event(job_id, 52, "flow", "ข้ามเสียง API ตามค่าประจำงาน", "ใช้เสียงต้นฉบับ Flow หรือไม่ใส่เสียงหลักตามที่เลือก")
            check_cancelled(cancel_event)
            self.log.info("job_id=%s state=PRODUCT_HANDOFF phase=starting_flow", job_id)
            self.products.set_automation_state(job_id, "running", "flow")
            video_name = self._video_provider_label(options["video_provider"])
            self._product_progress_event(job_id, 52, "flow", f"เตรียมงานแล้ว • กำลังเปิด {video_name}",
                "กำลังตรวจช็อตที่ทำไว้ก่อนเริ่มงาน • ใช้คลิปเดิมและสร้างเฉพาะช็อตที่ยังขาด")
            music_job = self.products.get_job(job_id)
            if (music_job.get('generated_music_options') or {}).get('enabled'):
                from core.generated_music import freeze_plan
                music_job['video_provider'] = options['video_provider']
                freeze_plan(music_job)
                self.products._manifest_store(self.products.root / job_id / 'job.json').update(
                    lambda current: {**current, 'generated_music_options': music_job['generated_music_options'],
                        'generated_music_plan': music_job['generated_music_plan'], 'audio_choices': music_job['audio_choices']})
            worker = self._multi_meta_product_worker if options["video_provider"] == "meta_ai" else self._multi_flow_worker
            _job_id, target, result = worker(job_id, cancel_event=cancel_event, emit_event=False, raise_errors=True)
            check_cancelled(cancel_event)
            presenter_job = self.products.get_job(job_id)
            if (presenter_job.get("presenter") or {}).get("enabled"):
                self._product_progress_event(job_id, 85, "presenter", "กำลังวางตัวละครผู้บรรยาย", "ใช้คลิปเดิม • ไม่สร้างภาพหรือเสียงใหม่")
                # This worker has just composed the canonical base. Never reuse
                # a previous overlay merely because its filename still exists.
                source = Path(target)
                output, plan = apply_presenter(ROOT, source, working_video_folder(folder) / "with_presenter.mp4",
                    presenter_job["presenter"], self.cfg.get("ffmpeg_path", ""), cancel_event)
                relative = str(output.relative_to(folder))
                self.products._manifest_store(folder / "job.json").update(lambda current: {
                    **current, "presenter_composite_path": relative, "presenter_render": plan,
                    "video_path": relative, "video_without_subtitle_path": relative,
                    "subtitle_video_status": "pending"})
            self.products.set_automation_state(job_id, "running", "subtitle" if options["subtitle_enabled"] else "audio")
            job = self.products.get_job(job_id)
            if options["subtitle_enabled"]:
                if audio_mode(job) != "api" and job.get("subtitle_status") != "ready":
                    from core.media_audio import native_transcript
                    if audio_mode(job) == "flow_original":
                        result = native_transcript(target, folder, options["subtitle_credential"], self.cfg, cancel_event)
                    else:
                        duration = AudioMixer(self.cfg.get("ffmpeg_path", "")).duration(target)
                        script = str(job.get("spoken_script") or job.get("spoken_script_short") or "")
                        result = {"segments": [{"words": self.products._script_to_timed_words(script, duration)}]}
                    job, _ = self.products.save_subtitle_result(job_id, "local-audio-mode", result, options["subtitle_syllables"])
                self._product_progress_event(job_id, 86, "subtitle", "รวมคลิป เอฟเฟกต์ และโลโก้แล้ว", "กำลังสร้างและตรวจคำบรรยายจากบทพูดที่อนุมัติ")
                if job.get("subtitle_status") != "ready":
                    source = folder / str(job.get("voice_path") or "")
                    existing_job_id = str(job.get("subtitle_job_id") or "") if job.get("subtitle_status") == "queued" else ""
                    self._create_subtitle_worker(
                        job_id, source, options["subtitle_language"], options["subtitle_credential"], existing_job_id,
                        options["subtitle_syllables"], cancel_event=cancel_event, emit_event=False,
                    )
                job = self.products.get_job(job_id)
                if audio_mode(job) == "api" and (
                    job.get("subtitle_alignment_status") != "corrected_from_approved_script"
                    or job.get("subtitle_timing_model") != "api_speech_intervals_v2"
                ):
                    self._product_progress_event(
                        job_id,
                        89,
                        "subtitle",
                        "กำลังแก้คำ Subtitle จากบทพูดต้นฉบับ",
                        "คงเวลาเดิมจาก Subtitle API แต่แทนคำเพี้ยนและคำตกด้วยบทที่ AI อนุมัติแล้ว",
                    )
                    job, _corrected_subtitle = self.products.correct_subtitle_from_script(job_id)
                if job.get("subtitle_video_status") != "ready" or not (folder / str(job.get("subtitle_video_path") or "")).is_file():
                    subtitle = folder / "captions" / "subtitle.srt"
                    source = folder / str(job.get("video_without_subtitle_path") or job.get("video_path") or "")
                    output = (
                        working_video_folder(folder) / "final_with_subtitles.mp4"
                        if options["audio_enabled"]
                        else folder / "videos" / "final_with_subtitles.mp4"
                    )
                    style = dict(options["subtitle_style"])
                    style["crf"] = options["render"]["crf"]
                    render_result = SubtitleVideoRenderer(self.cfg.get("ffmpeg_path", "")).render(source, subtitle, output, cancel_event=cancel_event, **style)
                    stored_style = dict(style)
                    stored_style["font_path"] = self.fonts.portable_path(stored_style.get("font_path")) if stored_style.get("font_path") else ""
                    job = self.products.save_subtitled_video(job_id, output, source, subtitle, stored_style)
                self._product_progress_event(job_id, 94, "audio", "Subtitle พร้อมแล้ว", "กำลังใส่เพลงพื้นหลังและเสียงเน้นข้อความ")
            else:
                self._product_progress_event(job_id, 94, "audio", "วิดีโอหลักพร้อมแล้ว", "กำลังใส่เสียงประกอบและตรวจไฟล์ Final")
            if options["audio_enabled"]:
                job = self.products.get_job(job_id)
                if job.get("audio_mix_status") != "ready" or not (folder / str(job.get("audio_mix_path") or "")).is_file():
                    source = self._audio_source(job)
                    subtitle = folder / "captions" / "subtitle.srt"
                    audio_options = dict(options["audio"])
                    audio_options.update({"cue_times": AudioMixer.cue_times(subtitle), "seed": job_id, "cancel_event": cancel_event})
                    output = folder / "videos" / "final_with_audio.mp4"
                    plan = AudioMixer(self.cfg.get("ffmpeg_path", "")).render(source, output, **audio_options)
                    job = self.products.save_audio_mix_result(job_id, output, source, options["audio_settings"], plan)
            check_cancelled(cancel_event)
            job = self.products.get_job(job_id)
            provisional = (folder / str(job.get("video_path") or "")).resolve()
            working = working_video_folder(folder)
            if working in provisional.parents:
                published = folder / "videos" / "final_product_video.mp4"
                staging = published.with_suffix(".rendering.mp4")
                shutil.copy2(provisional, staging)
                os.replace(staging, published)
                job = self.products.promote_video(job_id, str(published.relative_to(folder)))
            readiness = self.products.check_readiness(job_id)
            if not readiness.get("ready"):
                raise RuntimeError("งานยังไม่ครบ: " + ", ".join(readiness.get("missing") or []))
            target = folder / str(job.get("video_path") or target)
            if not target.is_file() or target.stat().st_size <= 0:
                raise RuntimeError("ไม่พบไฟล์วิดีโอ Final ที่สมบูรณ์")
            from core.green_screen import finish_product_green
            if (self.products.get_job(job_id).get('green_options') or {}).get('enabled'):
                self._product_progress_event(job_id,96,'audio','กำลังใส่กรีนสกรีน • ใช้เฉพาะภาพ','ไม่ใช้เสียงของเอฟเฟกต์')
                target = finish_product_green(self.products,job_id,ROOT,self.cfg.get('ffmpeg_path',''),cancel_event,
                    progress=lambda message: self._product_progress_event(job_id,96,'audio',message,'ไม่ใช้เสียงของเอฟเฟกต์',cancel_event=cancel_event))
            self.products.set_automation_state(job_id, "completed", "complete")
            from ui.ai_cover import finish_ai_cover
            finish_ai_cover(self, job_id, cancel_event, lambda message: self._product_progress_event(job_id,97,'cover',message,'วิดีโอบันทึกแล้ว'))
            cover_state = self.products.get_job(job_id).get('ai_cover_state') or {}
            if cover_state.get('phase') in {'needs_review','cancelled'}:
                result = {**(result or {}), 'ai_cover_notice':' • ปก AI ยังไม่สำเร็จ • ใช้ปกเดิมอยู่'}
            check_cancelled(cancel_event)
            self.events.put(("product_pipeline_ready", {"job_id": job_id, "cancel_event": cancel_event, "value": (job_id, target, result)}))
        except OperationCancelled:
            if job_id and str(job_id).startswith("JOB-"):
                try: self.products.set_automation_state(job_id, "cancelled", "cancelled")
                except Exception: pass
            self.events.put(("product_pipeline_cancelled", {"job_id": job_id or "", "cancel_event": cancel_event, "value": job_id or ""}))
        except Exception as exc:
            if cancel_event.is_set():
                self.events.put(("product_pipeline_cancelled", {"job_id": job_id or "", "cancel_event": cancel_event, "value": job_id or ""}))
                return
            if job_id and str(job_id).startswith("JOB-"):
                try: self.products.set_automation_state(job_id, "error", "stopped", str(exc))
                except Exception: pass
            self.events.put(("product_pipeline_error", {"job_id": job_id or "", "cancel_event": cancel_event, "value": (job_id or "", str(exc))}))
        finally:
            render_scope.close()

    def _selected_product_job(self):
        selected = self.product_table.selection()
        if not selected: return None
        return self.product_table.item(selected[0], "values")[0]

    def _copy_selected_link(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน"); return
        job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
        if not job: return
        link = job.get("posting_product_url") or job.get("product_url") or ""
        self.root.clipboard_clear(); self.root.clipboard_append(link); self.status.set("คัดลอกลิงก์สินค้าแล้ว")

    def _product_table_clicked(self, event):
        row_id = self.product_table.identify_row(event.y)
        region = self.product_table.identify_region(event.x, event.y)
        if not row_id or region not in {"cell", "tree"}:
            return
        self.product_table.selection_set(row_id)
        self.product_table.focus(row_id)
        job_id = str(self.product_table.item(row_id, "values")[0] or "")
        if job_id:
            self.root.after_idle(lambda selected_job=job_id: self._show_product_detail(selected_job))

    def _product_video_path(self, job_id, job):
        relative = str(job.get("video_path") or "").strip()
        if not relative:
            return None
        candidate = Path(relative)
        if not candidate.is_absolute():
            candidate = self.products.root / job_id / candidate
        return candidate.resolve()

    def _product_post_caption(self, job_id, job):
        folder = self.products.root / job_id / "captions"
        caption_file = folder / "caption.txt"
        hashtags_file = folder / "hashtags.txt"
        caption = caption_file.read_text(encoding="utf-8").strip() if caption_file.is_file() else str(job.get("caption") or "").strip()
        hashtags = hashtags_file.read_text(encoding="utf-8").strip() if hashtags_file.is_file() else ""
        if hashtags and hashtags not in caption:
            caption = f"{caption}\n\n{hashtags}".strip()
        return caption

    def _show_selected_product_detail(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน")
            return
        self._show_product_detail(job_id)

    def _show_product_detail(self, job_id):
        job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
        if not job:
            messagebox.showerror("ไม่พบข้อมูล", "ไม่พบ Product Job ที่เลือก")
            return

        previous = getattr(self, "_product_detail_dialog", None)
        if previous and previous.winfo_exists():
            previous.destroy()

        folder = self.products.root / job_id
        video_path = self._product_video_path(job_id, job)
        video_ready = bool(video_path and video_path.is_file() and video_path.stat().st_size > 0)
        affiliate_link = str(job.get("posting_product_url") or job.get("affiliate_url") or job.get("product_url") or "").strip()
        caption = self._product_post_caption(job_id, job)
        video_title = str(job.get("video_title") or job.get("product_name") or (video_path.stem if video_path else job_id)).strip()

        dialog = tk.Toplevel(self.root)
        self._product_detail_dialog = dialog
        dialog.title(f"รายละเอียดผลงาน • {job_id}")
        dialog.geometry("920x650")
        dialog.minsize(780, 580)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)

        header = tk.Frame(dialog, bg=COLORS["sidebar"], highlightbackground=COLORS["line"], highlightthickness=1)
        header.pack(fill="x")
        header_copy = tk.Frame(header, bg=COLORS["sidebar"]); header_copy.pack(side="left", fill="x", expand=True, padx=22, pady=16)
        tk.Label(header_copy, text="PRODUCT VIDEO DETAIL", bg=COLORS["sidebar"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 8)).pack(anchor="w")
        tk.Label(header_copy, text=video_title, bg=COLORS["sidebar"], fg=COLORS["text"], font=("Segoe UI Semibold", 16), wraplength=650, justify="left").pack(anchor="w", pady=(4, 2))
        tk.Label(header_copy, text=job_id, bg=COLORS["sidebar"], fg=COLORS["subtle"], font=("Segoe UI", 8)).pack(anchor="w")
        status_color = COLORS["green"] if video_ready else COLORS["orange"]
        status_text = "●  วิดีโอพร้อมดู" if video_ready else "●  วิดีโอยังไม่พร้อม"
        tk.Label(header, text=status_text, bg="#102A28" if video_ready else "#3A281C", fg=status_color, font=("Segoe UI Semibold", 9), padx=13, pady=8).pack(side="right", padx=22)

        body = tk.Frame(dialog, bg=COLORS["bg"]); body.pack(fill="both", expand=True, padx=18, pady=18)
        media = tk.Frame(body, bg=COLORS["panel"], width=275, highlightbackground=COLORS["line"], highlightthickness=1)
        media.pack(side="left", fill="y"); media.pack_propagate(False)
        tk.Label(media, text="ผลงานวิดีโอ", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(18, 4))
        tk.Label(media, text=(video_path.name if video_path else "ยังไม่มีไฟล์ Final"), bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 8), wraplength=235, justify="left").pack(anchor="w", padx=16)

        preview_box = tk.Frame(media, bg="#080D1E", height=275, highlightbackground=COLORS["line_soft"], highlightthickness=1)
        preview_box.pack(fill="x", padx=16, pady=14); preview_box.pack_propagate(False)
        generated = list(job.get("generated_images") or [])
        source_images = list(job.get("source_images") or [])
        preview_relative = generated[0] if generated else (source_images[0] if source_images else "")
        preview_path = folder / preview_relative if preview_relative else None
        if preview_path and preview_path.is_file():
            try:
                preview_image = Image.open(preview_path).convert("RGB")
                preview_image.thumbnail((235, 245), Image.Resampling.LANCZOS)
                preview_photo = ImageTk.PhotoImage(preview_image)
                dialog.product_preview_photo = preview_photo
                tk.Label(preview_box, image=preview_photo, bg="#080D1E").pack(expand=True)
            except Exception:
                tk.Label(preview_box, text="▶", bg="#080D1E", fg=COLORS["blue"], font=("Segoe UI", 48)).pack(expand=True)
        else:
            tk.Label(preview_box, text="▶", bg="#080D1E", fg=COLORS["blue"], font=("Segoe UI", 48)).pack(expand=True)

        def play_video():
            if not video_ready:
                messagebox.showwarning("วิดีโอยังไม่พร้อม", "งานนี้ยังไม่มีไฟล์วิดีโอ Final ให้เปิด", parent=dialog)
                return
            os.startfile(str(video_path))
            self.status.set(f"เปิดวิดีโอ • {video_title}")

        play_button = ttk.Button(media, text="▶  ดูวิดีโอ", style="PrimaryLarge.TButton", command=play_video)
        play_button.pack(fill="x", padx=16, pady=(0, 8))
        if not video_ready:
            play_button.configure(state="disabled")
        ttk.Button(media, text="เปิดโฟลเดอร์ผลงาน", style="Ghost.TButton", command=lambda: self._open_folder(folder)).pack(fill="x", padx=16)

        detail = tk.Frame(body, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        detail.pack(side="left", fill="both", expand=True, padx=(14, 0))

        def copy_value(value, label):
            if not value:
                messagebox.showwarning("ยังไม่มีข้อมูล", f"งานนี้ยังไม่มี{label}", parent=dialog)
                return
            self.root.clipboard_clear(); self.root.clipboard_append(value)
            self.status.set(f"คัดลอก{label}แล้ว")

        title_row = tk.Frame(detail, bg=COLORS["panel"]); title_row.pack(fill="x", padx=18, pady=(17, 5))
        tk.Label(title_row, text="ชื่อวิดีโอ", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 9)).pack(side="left")
        ttk.Button(title_row, text="คัดลอกชื่อ", style="Ghost.TButton", command=lambda: copy_value(video_title, "ชื่อวิดีโอ")).pack(side="right")
        tk.Label(detail, text=video_title, bg=COLORS["panel_3"], fg=COLORS["text"], font=("Segoe UI Semibold", 11), wraplength=540, justify="left", padx=12, pady=10).pack(fill="x", padx=18)

        caption_row = tk.Frame(detail, bg=COLORS["panel"]); caption_row.pack(fill="x", padx=18, pady=(14, 5))
        tk.Label(caption_row, text="แคปชั่นสำหรับโพสต์", bg=COLORS["panel"], fg=COLORS["purple"], font=("Segoe UI Semibold", 9)).pack(side="left")
        ttk.Button(caption_row, text="คัดลอกแคปชั่น", style="Ghost.TButton", command=lambda: copy_value(caption, "แคปชั่น")).pack(side="right")
        caption_box = tk.Text(detail, height=8, bg=COLORS["panel_3"], fg=COLORS["text"], relief="flat", wrap="word", font=("Segoe UI", 10), padx=12, pady=10)
        caption_box.pack(fill="both", expand=True, padx=18)
        caption_box.insert("1.0", caption or "ยังไม่มีแคปชั่น")
        caption_box.configure(state="disabled")

        link_row = tk.Frame(detail, bg=COLORS["panel"]); link_row.pack(fill="x", padx=18, pady=(14, 5))
        tk.Label(link_row, text="ลิงก์นายหน้าสินค้า", bg=COLORS["panel"], fg=COLORS["green"], font=("Segoe UI Semibold", 9)).pack(side="left")
        ttk.Button(link_row, text="คัดลอกลิงก์", style="Ghost.TButton", command=lambda: copy_value(affiliate_link, "ลิงก์สินค้า")).pack(side="right")
        link_box = tk.Entry(detail, bg=COLORS["panel_3"], fg=COLORS["text"], readonlybackground=COLORS["panel_3"], relief="flat", font=("Segoe UI", 9))
        link_box.pack(fill="x", padx=18, ipady=8)
        link_box.insert(0, affiliate_link or "ยังไม่มีลิงก์นายหน้า")
        link_box.configure(state="readonly")

        actions = tk.Frame(detail, bg=COLORS["panel"]); actions.pack(fill="x", padx=18, pady=16)
        open_link = ttk.Button(actions, text="เปิดหน้าสินค้า", style="Accent.TButton", command=lambda: self._open_url(affiliate_link))
        open_link.pack(side="left")
        if not affiliate_link:
            open_link.configure(state="disabled")
        ttk.Button(actions, text="ปิด", style="Ghost.TButton", command=dialog.destroy).pack(side="right")

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()

    def _prepare_chatgpt_plugin(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน"); return
        self._prepare_chatgpt_for_job(job_id)

    @uses_job_files(lambda app, job_id: job_id)
    def _prepare_chatgpt_for_job(self, job_id):
        try:
            from core.flow_motion_plan import provider_for
            # Repair belongs to this saved job, never the current create form.
            provider = provider_for(self.products.get_job(job_id))
            package = self.products.plugin_request(job_id)
            provider_name = "Gemini Web" if provider == "gemini" else "ChatGPT Web"
            if not package["job"].get("source_images"):
                messagebox.showwarning("ยังไม่มีรูปต้นฉบับ", f"กรุณากด เพิ่มรูปสินค้า และเลือกรูปจริงจากร้านค้าก่อนส่งเข้า {provider_name}"); return
            if package["job"].get("product_name") == "สินค้า Shopee จากลิงก์":
                messagebox.showwarning("ยังไม่ได้ตรวจชื่อสินค้า", f"กรุณากด แก้ข้อมูล และระบุชื่อสินค้าจริงก่อนส่งเข้า {provider_name}"); return
            extension = self.bridge.extension_status()
            command = self.bridge.queue_extension_command("open_chatgpt", job_id)
            self._activate_or_launch_chrome("https://gemini.google.com/app" if provider == "gemini" else "https://chatgpt.com/")
            if not extension.get("connected"):
                state = "เปิด Chrome แล้ว • รอ Extension รับคำสั่ง"
            else:
                state = f"Extension จะเปิด {provider_name} และทำงานอัตโนมัติ"
            image_count = len(package["job"].get("source_images") or [])
            self.status.set(f"{provider_name.upper()} • {job_id} • {state}")
            self._write_console(f"{job_id} • {provider_name} {command['id']} • แนบรูปต้นฉบับ {image_count} ไฟล์ • ไม่ใช้ Codex ImageGen", "success")
        except Exception as exc: messagebox.showerror("เตรียม AI Web ไม่สำเร็จ", str(exc))

    def _send_to_google_flow(self):
        job_id = self._selected_product_job()
        try:
            if not job_id:
                for candidate in self.products.list_jobs():
                    candidate_package = self.products.flow_package(candidate["id"])
                    if candidate_package.get("video_prompt") and candidate_package.get("image_files"):
                        job_id = candidate["id"]
                        break
            if not job_id:
                messagebox.showwarning("ยังไม่มีงานสำหรับ Flow", "ยังไม่มี Product Job ที่มีรูปและพรอมต์ Google Flow"); return
            package = self.products.flow_package(job_id)
            if not package.get("video_prompt") or not package.get("image_files"):
                messagebox.showwarning("ข้อมูล Flow ยังไม่พร้อม", "Job ต้องมีรูปที่สร้างแล้วและพรอมต์ Google Flow ก่อน"); return
            extension = self.bridge.extension_status()
            with app_guard(self).start(job_id):
                command = self.bridge.queue_extension_command("open_flow", job_id)
            self._activate_or_launch_chrome("https://labs.google/fx/tools/flow")
            if not extension.get("connected"):
                state = "เปิด Chrome แล้ว • รอ Extension รับคำสั่ง"
            else:
                state = "Extension รับคำสั่งภายในไม่กี่วินาที"
            review = "งานทดลองยังไม่อนุมัติ AI" if package.get("ai_review_status") != "approved" else "AI อนุมัติแล้ว"
            self.status.set(f"AUTO FLOW • {job_id} • {state}")
            self._write_console(f"{job_id} • AUTO FLOW {command['id']} • {review}", "success")
        except Exception as exc:
            messagebox.showerror("ส่งไป Google Flow ไม่สำเร็จ", str(exc))

    @uses_job_files(lambda app: app._selected_product_job())
    def _start_multi_flow(self):
        active_product = str(getattr(self, "_product_pipeline_job_id", "") or "")
        active_story = str(getattr(self, "_story_pipeline_job_id", "") or "")
        active_manual = str(getattr(self, "_manual_multi_flow_job_id", "") or "")
        if active_product or active_story or active_manual:
            active = active_product or active_story or active_manual
            messagebox.showinfo(
                "มีงานกำลังทำอยู่",
                f"กำลังทำงาน {active} อยู่ • กรุณารอให้จบหรือยกเลิกก่อนเริ่ม MULTI FLOW",
            )
            return False
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ที่มีรูป AI 3 รูปก่อน")
            return False
        try:
            package = self.products.flow_package(job_id)
            if len(package.get("image_files") or []) < 3 or package.get("shot_count", 0) < 3:
                raise ValueError("Job นี้ต้องมีรูป AI 3 รูปและ Prompt Google Flow 3 ช็อต")
            extension = self.bridge.extension_status()
            if not extension.get("connected"):
                raise ValueError("Chrome Extension ยังไม่เชื่อมกับโปรแกรม")
            job = self.products.get_job(job_id)
            video_provider = "flow"
            provider_name = self._video_provider_label(video_provider)
            worker = self._multi_flow_worker
            self.status.set(f"VIDEO AI ×3 • {provider_name} • {job_id} • เริ่มช็อต 1/3")
            self._write_console(f"{job_id} • เริ่มสร้างวิดีโอ 3 ช็อตด้วย {provider_name}", "success")
            self._manual_multi_flow_job_id = job_id
            self._manual_multi_flow_cancel_event = threading.Event()
            guarded_thread(self, job_id, self._manual_multi_flow_worker,
                args=(job_id, self._manual_multi_flow_cancel_event),
                daemon=True,
            )
            return True
        except Exception as exc:
            messagebox.showerror("เริ่มสร้างวิดีโอ AI ไม่สำเร็จ", str(exc))
            self._manual_multi_flow_job_id = ""
            self._manual_multi_flow_cancel_event = None
            return False

    def _manual_multi_flow_worker(self, job_id, cancel_event):
        """Own and release the single browser lane for a manual Flow run."""
        try:
            return self._multi_flow_worker(job_id, cancel_event=cancel_event)
        finally:
            if str(getattr(self, "_manual_multi_flow_job_id", "") or "") == str(job_id):
                self._manual_multi_flow_job_id = ""
                self._manual_multi_flow_cancel_event = None

    @staticmethod
    def _effect_labels(job):
        plan = list(job.get("editing_overlay_plan") or [])
        labels = [str(item.get("focus_label") or "").strip() for item in plan if isinstance(item, dict)]
        defaults = ["ภาพรวมสินค้า", "ดูรายละเอียดใกล้ ๆ", "พร้อมออกทริป"]
        return [(labels[index] if index < len(labels) and labels[index] else defaults[index]) for index in range(3)]

    def _effect_settings(self):
        return {
            "preset": str(self.cfg.get("video_effect_preset", "neon_focus")),
            "accent_color": str(self.cfg.get("video_effect_accent_color", "#2AD8F2")),
            "target_x_percent": float(self.cfg.get("video_effect_target_x_percent", 50)),
            "target_y_percent": float(self.cfg.get("video_effect_target_y_percent", 56)),
            "intensity": int(self.cfg.get("video_effect_intensity", 2)),
        }

    @uses_job_files(lambda app: app._selected_product_job())
    def _render_product_effects(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ที่มีวิดีโอก่อน")
            return
        job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
        if not job or job.get("video_status") != "ready":
            messagebox.showwarning("ยังไม่มีวิดีโอ", "Job นี้ยังไม่มีวิดีโอสำหรับใส่เอฟเฟกต์")
            return
        self.status.set(f"เอฟเฟกต์สินค้า • {job_id} • กำลังตัดต่อ")
        guarded_thread(self, job_id, self._render_product_effects_worker, args=(job,), daemon=True)

    def _render_product_effects_worker(self, job):
        try:
            folder = self.products.root / job["id"]
            relative = job.get("video_before_effects_path") or job.get("flow_video_path") or job.get("video_without_logo_path") or job.get("video_path")
            source = folder / str(relative)
            if not source.is_file():
                raise ValueError("ไม่พบวิดีโอต้นฉบับสำหรับใส่เอฟเฟกต์")
            settings = self._effect_settings()
            settings["crf"] = self._video_render_settings()["crf"]
            effect_output = folder / "videos" / "final_with_product_effects.mp4"
            result = ProductEffectsRenderer(self.cfg.get("ffmpeg_path", "")).render(source, effect_output, labels=self._effect_labels(job), **settings)
            saved = self.products.save_effect_video(job["id"], effect_output, source, settings)
            final = effect_output
            logo = self._job_logo_file(job)
            if logo.is_file():
                final = folder / "videos" / "final_effects_with_logo.mp4"
                logo_options = {
                    **self._job_logo_options(job),
                    "crf": self._video_render_settings()["crf"],
                }
                logo_result = VideoLogoRenderer(self.cfg.get("ffmpeg_path", "")).render(effect_output, logo, final, **logo_options)
                saved = self.products.save_logo_video(job["id"], final, effect_output, logo, logo_options)
            self.events.put(("effect_ready", (saved, final, result)))
        except Exception as exc:
            self.events.put(("effect_error", str(exc)))

    def _ensure_flow_extension(self, job_id, shot_index, cancel_event=None, timeout=75, queue_resume=False):
        """Reopen Chrome when its Extension disappears during a Flow checkpoint."""
        _extension, compatible = self._compatible_extension()
        if compatible and self._chrome_window_available():
            self._product_progress_event(
                job_id, 52 + max(0, shot_index - 1) * 8, "flow",
                "SmartFlow Extension เชื่อมแล้ว • กำลังติดตาม Google Flow",
                f"ช็อต {shot_index}/3 • จะรอผลในโปรเจกต์เดิมและไม่ส่งคำสั่งซ้ำ",
            )
            return compatible
        deadline = time.monotonic() + max(20, float(timeout))
        next_launch_at = 0.0
        launch_attempts = 0
        while time.monotonic() < deadline:
            check_cancelled(cancel_event)
            _extension, compatible = self._compatible_extension()
            if compatible and self._chrome_window_available():
                if queue_resume:
                    self.bridge.clear_flow_progress(job_id, shot_index)
                    self.bridge.queue_extension_command("open_flow", job_id, shot_index)
                self.events.put((
                    "multi_flow_progress",
                    f"ช็อต {shot_index}/3 • Chrome และ Extension กลับมาแล้ว • ทำต่อจาก Checkpoint เดิม",
                ))
                self._product_progress_event(
                    job_id, 52 + max(0, shot_index - 1) * 8, "flow",
                    "SmartFlow Extension กลับมาออนไลน์แล้ว",
                    f"ทำต่อช็อต {shot_index}/3 จาก Checkpoint เดิม • ไม่ย้อนสร้างรูปหรือเสียง",
                )
                return compatible
            now = time.monotonic()
            if now >= next_launch_at and launch_attempts < 4:
                launch_attempts += 1
                self.events.put((
                    "multi_flow_progress",
                    f"ช็อต {shot_index}/3 • Chrome/Extension หลุด • เปิด Google Chrome กลับอัตโนมัติ "
                    f"({launch_attempts}/4)",
                ))
                self._product_progress_event(
                    job_id, 52 + max(0, shot_index - 1) * 8, "flow",
                    "Chrome/Extension หลุด • กำลังเปิดกลับอัตโนมัติ",
                    f"รักษา Checkpoint ช็อต {shot_index}/3 ไว้ • ไม่ย้อนสร้างรูปหรือเสียง",
                )
                self._activate_or_launch_chrome("https://labs.google/fx/th/tools/flow")
                next_launch_at = now + 15
            if cancel_event is not None:
                if cancel_event.wait(2):
                    check_cancelled(cancel_event)
            else:
                time.sleep(2)
        raise RuntimeError(
            f"Chrome/Extension หลุดระหว่าง Google Flow ช็อต {shot_index} • "
            "โปรแกรมลองเปิดกลับ 4 ครั้งแล้ว กรุณาตรวจ Chrome Extension"
        )

    def _wait_flow_step(self, job_id, shot_index, timeout=1800, cancel_event=None, total_shots=3, expected_run_id="", scene_video_plan=None):
        if job_id.startswith('STORY-') and job_id == getattr(self, '_story_pipeline_job_id', ''):
            self._story_flow_progress_owner = (job_id, shot_index)
        deadline = time.monotonic() + timeout
        last_message = ""
        last_change = time.monotonic()
        credit_approval_attempts = 0
        last_credit_approval_at = 0.0
        generation_observed = False
        ambiguous_confirmation_at = None
        web_action_waiting = False
        web_action_notified = False
        rights_confirmation_waiting = False
        last_rights_inspect_at = 0.0
        credit_exhausted_waiting = False
        flow_client_missing_since = None
        flow_client_requeues = 0
        generate_button_recovery_started = None
        generate_button_requeues = 0
        last_generate_button_requeue_at = 0.0
        prompt_recovery_started = None
        prompt_requeues = 0
        last_prompt_requeue_at = 0.0
        prepare_recovery_started = None
        prepare_requeues = 0
        last_prepare_requeue_at = 0.0
        submission_recovery_started = None
        submission_requeues = 0
        last_submission_requeue_at = 0.0
        unknown_state_checks = 0
        unknown_state_total_checks = 0
        unknown_state_requeues = 0
        unknown_active_since = None
        workspace_requeues = 0
        last_workspace_requeue_at = 0.0
        package_ready_since = None
        package_ready_requeues = 0
        last_package_ready_requeue_at = 0.0
        manual_attachment_wait_started = None
        last_manual_attachment_inspect_at = 0.0
        attachment_selection_resume = None
        flow_attempt_identity = None
        last_continuous_inspect_at = 0.0
        while time.monotonic() < deadline:
            check_cancelled(cancel_event)
            if scene_video_plan:
                from core.scene_video_plan import assert_binding
                from core.scene_video_worker import SceneVideoReviewError
                try:
                    assert_binding(self.stories.get(job_id), shot_index, scene_video_plan)
                except ValueError as exc:
                    raise SceneVideoReviewError(str(exc)) from exc
            status = self.bridge.extension_status()
            clients = [item for item in status.get("clients") or []
                if str(item.get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION]
            compatible = next((item for item in clients if str(item.get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION), None)
            if not compatible:
                recovery_started = time.monotonic()
                self._ensure_flow_extension(job_id, shot_index, cancel_event=cancel_event, queue_resume=True)
                deadline += max(0, time.monotonic() - recovery_started)
                last_change = time.monotonic()
                flow_client_missing_since = None
                flow_client_requeues = 0
                continue
            client = next((item for item in clients if item.get("flow_job_id") == job_id
                and int(item.get("flow_shot_index") or 0) == shot_index
                and (not scene_video_plan or item.get('flow_scene_video_plan') == scene_video_plan)
                and (not expected_run_id or str(item.get("flow_run_id") or "") == expected_run_id)), None)
            if client:
                flow_client_missing_since = None
                step = str(client.get("flow_step") or "")
                message = str(client.get("flow_message") or step)
                page_excerpt = str(client.get("flow_page_excerpt") or "")
                failure_code = str(client.get("flow_failure_code") or "").strip().upper()
                policy_failure_category = str(
                    client.get("flow_policy_failure_category") or ""
                ).strip().lower()
                flow_run_id = str(client.get("flow_run_id") or "").strip()
                repair_request_id = str(client.get("flow_repair_request_id") or "")
                project_url = str(client.get("flow_page_url") or "").split("?", 1)[0].split("#", 1)[0]
                attempt_identity = (flow_run_id, repair_request_id, project_url)
                if "/project/" in project_url and attempt_identity != flow_attempt_identity:
                    # A confirmed terminal may lead to many repair rounds. An
                    # old round's unknown polls must not stop a new Send after
                    # only seconds (live 7A343B round7, 2026-09-20).
                    flow_attempt_identity = attempt_identity
                    unknown_state_checks = unknown_state_total_checks = unknown_state_requeues = 0
                    unknown_active_since = None
                    submission_recovery_started = None
                    submission_requeues = 0
                    last_submission_requeue_at = 0.0
                    generation_observed = False
                failure_card_fingerprint = str(
                    client.get("flow_failure_card_fingerprint") or ""
                ).strip()
                if message and message != last_message:
                    self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/{int(total_shots or 3)} • {message}"))
                    if (job_id.startswith('STORY-') and flow_run_id
                            and job_id == getattr(self, '_story_pipeline_job_id', '')):
                        count = max(1, int(total_shots or 3))
                        self.events.put(('story_flow_progress', {
                            'job_id': job_id, 'shot_index': shot_index, 'flow_run_id': flow_run_id,
                            'generation_accepted': bool(client.get('flow_generation_active')) or step == 'generation_complete',
                            'percent': 79 + round(8 * (shot_index - 1) / count), 'stage': 'video',
                            'message': f'Google Flow • ฉาก {shot_index}/{count}',
                            'detail': message,
                        }))
                    last_message = message
                    last_change = time.monotonic()
                if step == "generation_complete":
                    return client
                if failure_code == "FLOW_REPAIR_REVIEW" or "FLOW_REPAIR_REVIEW" in message:
                    raise FlowVideoReviewError(shot_index, message)
                if failure_code in {"FLOW_SEND_REVIEW", "FLOW_VIDEO_SETTINGS_REVIEW"} or any(code in message for code in ("FLOW_SEND_REVIEW", "FLOW_VIDEO_SETTINGS_REVIEW")):
                    review_code = "FLOW_VIDEO_SETTINGS_REVIEW" if "FLOW_VIDEO_SETTINGS_REVIEW" in failure_code + message else "FLOW_SEND_REVIEW"
                    flow_error = RuntimeError(f"{review_code} • ช็อต {shot_index}: หยุดอย่างปลอดภัย • {message}")
                    flow_error.flow_retry_forbidden = True
                    raise flow_error
                if failure_code == "FLOW_ATTACHMENT_UNCONFIRMED":
                    try:
                        evidence = validated_attachment_failure_evidence(
                            client.get("flow_attachment_failure_evidence"), flow_run_id, failure_card_fingerprint,
                        )
                    except ValueError:
                        evidence = {}
                    # This is a different terminal from a policy denial. The
                    # Extension must first retire its single attachment action
                    # and latch submission OFF after the passive grace period.
                    # Never infer this decision from a Thai error/page excerpt.
                    confirmed = (
                        step == "attachment_failed"
                        and not generation_observed
                        and not client.get("flow_generation_active")
                        and not client.get("flow_has_playable_result")
                        and not client.get("flow_confirmation_kind")
                        and bool(evidence)
                    )
                    if confirmed:
                        # Extension advertises only a proven completed upload.
                        # Resume selects that SAME project asset; its background
                        # rechecks ownership, no Send/result and a durable budget.
                        if evidence.get("selection_recovery_available"):
                            if attachment_selection_resume is None:
                                attachment_selection_resume = (failure_card_fingerprint, time.monotonic())
                                self.bridge.queue_extension_command("resume_flow_workspace", job_id, shot_index)
                                self.events.put(("multi_flow_progress", f"ช็อต {shot_index} • กำลังกลับไปเลือกรูปเดิมที่อัปโหลดแล้ว • ไม่อัปโหลดซ้ำ"))
                            if (attachment_selection_resume[0] == failure_card_fingerprint
                                    and time.monotonic() - attachment_selection_resume[1] < 120):
                                time.sleep(0.5)
                                continue
                        attachment_error = RuntimeError(
                            f"FLOW_ATTACHMENT_UNCONFIRMED • ช็อต {shot_index}: "
                            "รอตรวจรูปเดิมครบแล้วแต่ยืนยันรูปแนบไม่ได้ • "
                            "ยังไม่ได้ส่งสร้าง • พักฉากไว้ ไม่ใช้ภาพแทนวิดีโอ"
                        )
                        attachment_error.flow_attachment_terminal = True
                        attachment_error.flow_retry_forbidden = True
                        attachment_error.flow_run_id = flow_run_id
                        attachment_error.failure_card_fingerprint = failure_card_fingerprint
                        attachment_error.attachment_failure_evidence = evidence
                        attachment_error.scene_video_terminal_proof = {
                            'terminal': True, 'busy': False, 'download_pending': False,
                            'kind': 'never_dispatched', 'code': 'FLOW_ATTACHMENT_UNCONFIRMED',
                            'run_id': flow_run_id, 'fingerprint': failure_card_fingerprint}
                        raise attachment_error
                    if not generation_observed and not client.get("flow_generation_active"):
                        unsafe_terminal = RuntimeError(
                            f"ช็อต {shot_index}: หลักฐานหยุดแนบรูปไม่ครบ • "
                            "ไม่อัปโหลดหรือส่งซ้ำ และยังไม่ใช้รูปแทนผลที่อาจกำลังสร้าง"
                        )
                        unsafe_terminal.flow_retry_forbidden = True
                        raise unsafe_terminal
                # The bridge ties this code to the newest failure-card
                # fingerprint. Treat it before visible-step heuristics so a
                # stale approval/login button cannot conceal a terminal policy
                # denial from the current result card.
                if failure_code == "FLOW_POLICY_BLOCKED":
                    self._queue_flow_failure_notice(job_id, shot_index, client, cancel_event)
                    marker = (
                        "FLOW_FACE_POLICY_BLOCKED"
                        if policy_failure_category == "face_or_public_figure"
                        else "FLOW_POLICY_BLOCKED"
                    )
                    policy_error = RuntimeError(
                        f"{marker} • ช็อต {shot_index}: "
                        f"{message or 'Google Flow ปฏิเสธอินพุตตามนโยบาย'}"
                    )
                    policy_error.flow_run_id = flow_run_id
                    policy_error.failure_card_fingerprint = failure_card_fingerprint
                    policy_error.policy_failure_category = policy_failure_category
                    policy_error.flow_policy_terminal = True
                    policy_error.flow_retry_forbidden = True
                    if (step == 'generation_failed' and flow_run_id and failure_card_fingerprint
                            and not client.get('flow_confirmation_kind') and not client.get('flow_has_rights_dialog')):
                        policy_error.scene_video_terminal_proof = {
                            'terminal': True, 'busy': False, 'download_pending': False,
                            'kind': 'provider_failed', 'code': 'FLOW_POLICY_BLOCKED',
                            'run_id': flow_run_id, 'fingerprint': failure_card_fingerprint}
                    raise policy_error
                observation = client.get("flow_observation") or {}
                observation_age = time.time() - float(observation.get("received_at") or 0)
                continuous_wait = (client.get("flow_continuous_wait") is True
                    and step == "generation_in_progress"
                    and 0 <= observation_age < 30
                    and observation.get("acknowledged") is True
                    and observation.get("identity") == [job_id, flow_run_id, client.get("flow_tab_id")]
                    and int(observation.get("scene_index") or 0) == shot_index
                    and bool(flow_run_id) and "/project/" in project_url)
                if continuous_wait:
                    # Extend only while fresh owned Extension observations
                    # arrive. No loop-count/30-minute cap on a live free queue
                    # or confirmed-failure repair; cancel/auth guards still run.
                    deadline = max(deadline, time.monotonic() + 60)
                    if time.monotonic() - last_change >= 180 and time.monotonic() - last_continuous_inspect_at >= 60:
                        last_continuous_inspect_at = time.monotonic()
                        self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                    if cancel_event is not None:
                        if cancel_event.wait(3):
                            check_cancelled(cancel_event)
                    else:
                        time.sleep(3)
                    continue
                if step == "package_ready":
                    # `autoPrepare` intentionally consumes its one-shot token
                    # after an unsuccessful prepare attempt. Previously the
                    # helper then reported package_ready forever while this
                    # worker waited for the 30-minute global timeout. Refresh
                    # the same workspace twice; if no active state returns,
                    # fail only this shot so the outer checkpoint retry can
                    # open a clean project without repeating AI images/voice.
                    now = time.monotonic()
                    package_ready_since = package_ready_since or now
                    if generation_observed:
                        # Flow replaces/reloads its page while a queued render
                        # is alive. A passive package_ready heartbeat at that
                        # moment must never cancel the submitted render or open
                        # a second project. Inspect the same project until the
                        # result/queue state becomes visible again.
                        if now - last_package_ready_requeue_at >= 8:
                            last_package_ready_requeue_at = now
                            self.events.put((
                                "multi_flow_progress",
                                f"ช็อต {shot_index}/{int(total_shots or 3)} • หน้า Flow กำลังโหลดสถานะคิวใหม่ • "
                                "ติดตามโปรเจกต์เดิมโดยไม่กดสร้างซ้ำ",
                            ))
                            self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                        if now - package_ready_since >= 10 * 60:
                            raise RuntimeError(
                                f"ช็อต {shot_index}: สถานะคิวที่ส่งแล้วหายเกิน 10 นาที • เก็บ Checkpoint ไว้และหยุดก่อนสร้างซ้ำ"
                            )
                        if cancel_event is not None:
                            if cancel_event.wait(2):
                                check_cancelled(cancel_event)
                        else:
                            time.sleep(2)
                        continue
                    if (
                        package_ready_requeues < 2
                        and now - last_package_ready_requeue_at >= 6
                    ):
                        package_ready_requeues += 1
                        last_package_ready_requeue_at = now
                        self.events.put((
                            "multi_flow_progress",
                            f"ช็อต {shot_index}/{int(total_shots or 3)} • คำสั่ง AUTO FLOW รอบเดิมสิ้นสุด • "
                            f"เชื่อม Workspace เดิมใหม่ ({package_ready_requeues}/2)",
                        ))
                        self.bridge.queue_extension_command("resume_flow_workspace", job_id, shot_index)
                    if now - package_ready_since >= 35:
                        raise RuntimeError(
                            f"ช็อต {shot_index}: AUTO FLOW สิ้นสุดโดยยังไม่แนบรูปหรือเริ่มสร้าง • "
                            "เปิดโปรเจกต์ใหม่เฉพาะช็อตนี้"
                        )
                    if cancel_event is not None:
                        if cancel_event.wait(2):
                            check_cancelled(cancel_event)
                    else:
                        time.sleep(2)
                    continue
                package_ready_since = None
                package_ready_requeues = 0
                if step == "credit_exhausted":
                    credit_exhausted_waiting = True
                    deadline += 2.5
                    if self._product_pipeline_job_id == job_id:
                        self._product_progress_event(
                            job_id, 52 + max(0, shot_index - 1) * 8, "flow",
                            "เครดิต Google Flow หมดหรือไม่เพียงพอ",
                            "เปลี่ยนบัญชี Google หรือเติมเครดิตใน Chrome แล้วกด “ทำต่อด้วยบัญชีใหม่” • Checkpoint รูปและเสียงยังอยู่ครบ",
                            action_required=True, provider="flow", action_kind="credit_exhausted",
                            shot_index=shot_index, already_notified=web_action_notified,
                        )
                    elif not web_action_notified:
                        self.events.put(("flow_credit_exhausted", (job_id, shot_index, message, int(total_shots or 3))))
                    web_action_notified = True
                    if cancel_event is not None:
                        if cancel_event.wait(2):
                            check_cancelled(cancel_event)
                    else:
                        time.sleep(2)
                    continue
                if credit_exhausted_waiting:
                    credit_exhausted_waiting = False
                    web_action_notified = False
                    self._product_progress_event(
                        job_id, 52 + max(0, shot_index - 1) * 8, "flow",
                        "ตรวจพบบัญชี Google Flow ใหม่แล้ว • กำลังทำต่อ",
                        f"เริ่มโปรเจกต์ใหม่เฉพาะช็อต {shot_index}/3 • ไม่ย้อนสร้างรูปหรือเสียง",
                    )
                if step == "user_action_required":
                    action_kind = str(client.get("flow_action_kind") or "login_required")
                    web_action_waiting = True
                    deadline += 2.5  # Login time must not consume the Flow timeout.
                    login_message = message or "กรุณาเข้าสู่ระบบ Google Flow ก่อน"
                    if self._product_pipeline_job_id == job_id:
                        self._product_progress_event(
                            job_id, 52 + max(0, shot_index - 1) * 8, "flow",
                            "กรุณาเข้าสู่ระบบ Google Flow ก่อน" if action_kind == "login_required" else login_message,
                            "กดเปิด Google Flow แล้ว Login ใน Chrome • ระบบจะทำต่อจากช็อตเดิมเอง",
                            action_required=True, provider="flow", action_kind=action_kind,
                            already_notified=web_action_notified,
                        )
                    elif not web_action_notified:
                        self.events.put(("flow_login_required", (job_id, shot_index, login_message, int(total_shots or 3))))
                    web_action_notified = True
                    if cancel_event is not None:
                        if cancel_event.wait(2):
                            check_cancelled(cancel_event)
                    else:
                        time.sleep(2)
                    continue
                if step == "user_action_resolved":
                    self.bridge.clear_flow_progress(job_id, shot_index)
                    self.bridge.queue_extension_command("open_flow", job_id, shot_index)
                    web_action_waiting = False
                    web_action_notified = False
                    if self._product_pipeline_job_id == job_id:
                        self._product_progress_event(
                            job_id, 52 + max(0, shot_index - 1) * 8, "flow",
                            "เข้าสู่ระบบ Google Flow แล้ว • กำลังทำงานต่อ",
                            f"ทำต่อจากช็อต {shot_index}/3 โดยไม่ย้อนขั้น AI ภาพและเสียง",
                        )
                    if cancel_event is not None:
                        if cancel_event.wait(2):
                            check_cancelled(cancel_event)
                    else:
                        time.sleep(2)
                    continue
                if step == "awaiting_rights_confirmation":
                    rights_confirmation_waiting = True
                    web_action_waiting = True
                    deadline += 2.5  # เวลาที่ผู้ใช้กดยอมรับต้องไม่กิน timeout ของ Flow
                    rights_message = message or "Google Flow รอให้กด “ฉันยอมรับ” เรื่องสิทธิ์ของรูป"
                    if self._product_pipeline_job_id == job_id:
                        self._product_progress_event(
                            job_id, 52 + max(0, shot_index - 1) * 8, "flow",
                            "กรุณากด “ฉันยอมรับ” ใน Google Flow",
                            "โปรแกรมหยุดรอโดยไม่กดยกเลิก • กดยอมรับใน Chrome แล้วงานจะทำต่อจากรูปเดิม",
                            action_required=True, provider="flow", action_kind="legal_rights",
                            shot_index=shot_index, already_notified=web_action_notified,
                        )
                    elif not web_action_notified:
                        self.events.put(("flow_rights_required", (job_id, shot_index, rights_message, int(total_shots or 3))))
                    web_action_notified = True
                    if cancel_event is not None:
                        if cancel_event.wait(2):
                            check_cancelled(cancel_event)
                    else:
                        time.sleep(2)
                    if time.monotonic() - last_rights_inspect_at >= 5:
                        last_rights_inspect_at = time.monotonic()
                        self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                    continue
                if rights_confirmation_waiting:
                    # ผู้ใช้กดยอมรับแล้ว: ผูกตัวช่วยกับ Workspace เดิมและแนบรูป
                    # ต่อ ห้าม stop/retry เพราะจะกดปิดหน้าต่างที่ผู้ใช้เพิ่งยืนยัน
                    rights_confirmation_waiting = False
                    web_action_waiting = False
                    web_action_notified = False
                    self.bridge.clear_flow_progress(job_id, shot_index)
                    self.bridge.queue_extension_command("resume_flow_workspace", job_id, shot_index)
                    if cancel_event is not None:
                        if cancel_event.wait(2):
                            check_cancelled(cancel_event)
                    else:
                        time.sleep(2)
                    continue
                if web_action_waiting:
                    web_action_waiting = False
                    web_action_notified = False
                # Google Flow keeps old approval controls in the conversation
                # history after a request fails.  The Extension can therefore
                # still report `awaiting_credit_approval` while the newest card
                # clearly says "เกิดข้อผิดพลาด • ลองอีกครั้ง".  Treat the
                # explicit failure card as the strongest signal so the outer
                # checkpoint worker discards only this attempt, opens a fresh
                # Flow project and retries the missing shot automatically.
                policy_blocked = failure_code == "FLOW_POLICY_BLOCKED"
                face_policy_blocked = (
                    policy_blocked and policy_failure_category == "face_or_public_figure"
                )
                policy_marker = (
                    "FLOW_FACE_POLICY_BLOCKED • " if face_policy_blocked
                    else "FLOW_POLICY_BLOCKED • "
                )
                current_generation_active = (
                    step in {"generation_started", "generation_in_progress"}
                    or bool(client.get("flow_generation_active"))
                )
                explicit_flow_error = not current_generation_active and (
                    bool(client.get("flow_new_failure")) or bool(re.search(
                        r"(?:(?:เกิดข้อผิดพลาด|โปรดลองอีกครั้ง|something went wrong|"
                        r"an error occurred|please try again)[\s\S]{0,180}"
                        r"(?:ลองอีกครั้ง|try again|retry)|(?:ล้มเหลว|generation failed|failed to generate)"
                        r"[\s\S]{0,320}(?:ไม่ได้เรียกเก็บเงิน|not (?:be )?charged|no credits? (?:were|was) charged))",
                        page_excerpt,
                        flags=re.IGNORECASE,
                    ))
                )
                if explicit_flow_error:
                    self.events.put((
                        "multi_flow_progress",
                        f"ช็อต {shot_index}/{int(total_shots or 3)} • พบข้อผิดพลาดจาก Google Flow • "
                        "กำลังซ่อมอัตโนมัติและลองเฉพาะช็อตนี้ใหม่",
                    ))
                    flow_error = RuntimeError(
                        (policy_marker if policy_blocked else "")
                        + f"ช็อต {shot_index}: Google Flow สร้างไม่สำเร็จและไม่ได้หักเครดิต • แสดงปุ่มลองอีกครั้ง"
                    )
                    if policy_blocked:
                        flow_error.flow_run_id = flow_run_id
                        flow_error.failure_card_fingerprint = failure_card_fingerprint
                        flow_error.flow_policy_terminal = True
                    raise flow_error
                if step == "generation_status_unknown":
                    # Flow Agent sometimes reports the live English text
                    # "Considering Video Generation" (with a Stop button)
                    # instead of a percentage.  That is a real render, not a
                    # silent submission.  Keep observing it, but still bound a
                    # genuinely frozen active screen to eight minutes.
                    unknown_has_activity = bool(re.search(
                        r"Considering\s+Video\s+Generation|กำลังคิด|(?:^|\n)stop(?:\s|\n)|(?:^|\n)หยุด(?:\s|\n)",
                        page_excerpt,
                        flags=re.IGNORECASE,
                    ))
                    if unknown_has_activity:
                        generation_observed = True
                        unknown_state_checks = 0
                        if unknown_active_since is None:
                            unknown_active_since = time.monotonic()
                        if time.monotonic() - unknown_active_since >= 8 * 60:
                            activity_error = RuntimeError(
                                f"ช็อต {shot_index}: Google Flow แสดงว่ากำลังสร้างแต่ไม่มีผลลัพธ์เกิน 8 นาที"
                            )
                            activity_error.flow_retry_forbidden = True
                            raise activity_error
                    else:
                        unknown_active_since = None
                        unknown_state_checks += 1
                        unknown_state_total_checks += 1
                    # Unknown acceptance is not a failed render. Older helpers
                    # may inspect the same saved project twice, but must never
                    # enter the outer Stop/new-project retry on a timer alone.
                    if (
                        not unknown_has_activity
                        and unknown_state_requeues < 2
                        and unknown_state_total_checks in {10, 20}
                    ):
                        unknown_state_requeues += 1
                        self.events.put((
                            "multi_flow_progress",
                            f"ช็อต {shot_index}/{int(total_shots or 3)} • Flow ไม่เริ่มสร้างและไม่มีสถานะ • "
                            f"กำลังตรวจผลในโปรเจกต์เดิม ({unknown_state_requeues}/2)",
                        ))
                        self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                    if (
                        not unknown_has_activity
                        and unknown_state_total_checks >= 30
                    ):
                        unknown_error = RuntimeError(
                            f"ช็อต {shot_index}: Google Flow ไม่เริ่มสร้างภายใน 90 วินาที • หยุดก่อนส่งซ้ำ"
                        )
                        unknown_error.flow_retry_forbidden = True
                        raise unknown_error
                else:
                    unknown_state_checks = 0
                    unknown_active_since = None
                if step == "generation_in_progress":
                    # `generation_in_progress` is also used for the optimistic
                    # "รับ Prompt แล้ว" message.  It is not proof that Flow has
                    # really entered the render queue.  Only a live percentage
                    # or an explicit queue/processing status may suppress the
                    # bounded approval-stall recovery below.
                    generation_observed = generation_observed or bool(re.search(
                        r"\b\d{1,3}%\b|อยู่ในคิว|รอคิว|queued|processing|scheduled",
                        message,
                        flags=re.IGNORECASE,
                    ))
                if step == "generate_button_missing":
                    now = time.monotonic()
                    generate_button_recovery_started = generate_button_recovery_started or now
                    # Flow can show the reference chip and prompt before its
                    # upload backend enables the Generate button. Reattach the
                    # helper to the same workspace instead of discarding the
                    # project and spending three retries immediately.
                    if (
                        generate_button_requeues < 3
                        and now - last_generate_button_requeue_at >= 15
                    ):
                        generate_button_requeues += 1
                        last_generate_button_requeue_at = now
                        self.events.put((
                            "multi_flow_progress",
                            f"ช็อต {shot_index}/{int(total_shots or 3)} • ปุ่มสร้างยังไม่พร้อม • รอ Google ประมวลผลรูป "
                            f"และเชื่อม Workspace เดิมใหม่ ({generate_button_requeues}/3)",
                        ))
                        self.bridge.queue_extension_command("resume_flow_workspace", job_id, shot_index)
                    if now - generate_button_recovery_started < 150:
                        if cancel_event is not None:
                            if cancel_event.wait(3):
                                check_cancelled(cancel_event)
                        else:
                            time.sleep(3)
                        continue
                    raise RuntimeError(f"ช็อต {shot_index}: {message}")
                if step == "prepare_incomplete":
                    image_ready = bool(client.get("flow_image_ready"))
                    prompt_ready = bool(client.get("flow_prompt_ready"))
                    now = time.monotonic()
                    if not image_ready:
                        page_url = str(client.get("flow_page_url") or "")
                        manual_handoff_pending = (
                            prompt_ready
                            and "/project/" in page_url.lower()
                            and bool(re.search(
                                r'FLOW_ATTACH_PROOF_MISSING_AFTER_SINGLE_ACTION|'
                                r'"singleFlightStopped":true|"attachmentGuardBlocked":true',
                                page_excerpt,
                                flags=re.IGNORECASE,
                            ))
                        )
                        if manual_handoff_pending:
                            manual_attachment_wait_started = manual_attachment_wait_started or now
                            if now - last_manual_attachment_inspect_at >= 5:
                                last_manual_attachment_inspect_at = now
                                self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                            if now - manual_attachment_wait_started < 10 * 60:
                                if cancel_event is not None:
                                    if cancel_event.wait(2):
                                        check_cancelled(cancel_event)
                                else:
                                    time.sleep(2)
                                continue
                            raise RuntimeError(
                                f"ช็อต {shot_index}: รอแนบรูปใน Composer เดิมครบ 10 นาทีแล้ว • "
                                "ยังไม่มีหลักฐานรูปและ Prompt พร้อม"
                            )
                        # A failed composer proof is not the same as a failed
                        # upload. Current Flow first stores the image in the
                        # project gallery and only then inserts that existing
                        # asset into the prompt. If the Extension has already
                        # proved that project asset, rebind the same workspace;
                        # never stop the worker and let runtime recovery create
                        # a new project/upload for this transient DOM miss.
                        existing_asset_proven = bool(re.search(
                            r'DEBUG_UPLOAD=.*?(?:"mediaReady":true|"imageCount":[1-9]\d*)',
                            page_excerpt,
                            flags=re.IGNORECASE | re.DOTALL,
                        ))
                        if "/project/" in page_url.lower() and existing_asset_proven:
                            prepare_recovery_started = prepare_recovery_started or now
                            if prepare_requeues < 2 and now - last_prepare_requeue_at >= 10:
                                prepare_requeues += 1
                                last_prepare_requeue_at = now
                                self.events.put((
                                    "multi_flow_progress",
                                    f"ช็อต {shot_index}/{int(total_shots or 3)} • รูปอยู่ในโปรเจกต์แล้ว "
                                    f"แต่ยังไม่ผูกกับช่อง Prompt • เลือกรูปเดิมอีกครั้ง "
                                    f"({prepare_requeues}/2) โดยไม่อัปโหลดซ้ำ",
                                ))
                                self.bridge.queue_extension_command("resume_flow_workspace", job_id, shot_index)
                            if now - prepare_recovery_started < 90:
                                if cancel_event is not None:
                                    if cancel_event.wait(2):
                                        check_cancelled(cancel_event)
                                else:
                                    time.sleep(2)
                                continue
                        raise RuntimeError(
                            f"ช็อต {shot_index}: ระบบลองแนบรูปเดิมจากโปรเจกต์แล้วแต่ยังยืนยันสถานะไม่ได้ • "
                            "หยุดเพื่อป้องกันการอัปโหลดรูปซ้ำ กรุณาตรวจช็อตนี้ก่อนเริ่มใหม่"
                        )
                    # Flow can expose its Slate composer before React has bound
                    # the input handlers.  In the real failure observed on
                    # JOB-20260829-7B0D16 the first helper reported
                    # "Prompt not ready", then the same workspace reached
                    # generation_started eleven seconds later.  Keep this
                    # attempt alive briefly and reattach the helper instead of
                    # spending all three outer retries on one healthy project.
                    if image_ready and not prompt_ready:
                        prompt_recovery_started = prompt_recovery_started or now
                        if prompt_requeues < 2 and now - last_prompt_requeue_at >= 8:
                            prompt_requeues += 1
                            last_prompt_requeue_at = now
                            self.events.put((
                                "multi_flow_progress",
                                f"ช็อต {shot_index}/{int(total_shots or 3)} • รูปพร้อมแล้ว แต่ช่อง Prompt ยังโหลดไม่ครบ • "
                                f"เชื่อมตัวช่วยกับ Workspace เดิมใหม่ ({prompt_requeues}/2)",
                            ))
                            self.bridge.queue_extension_command("resume_flow_workspace", job_id, shot_index)
                        if now - prompt_recovery_started < 45:
                            if cancel_event is not None:
                                if cancel_event.wait(2):
                                    check_cancelled(cancel_event)
                            else:
                                time.sleep(2)
                            continue
                    # The image is already proven ready here. Only the Prompt
                    # helper may be resumed; a missing image is terminal above
                    # so this recovery can never upload the same file again.
                    page_url = str(client.get("flow_page_url") or "")
                    if "/project/" in page_url.lower() and not (image_ready and prompt_ready):
                        prepare_recovery_started = prepare_recovery_started or now
                        if prepare_requeues < 1 and now - last_prepare_requeue_at >= 8:
                            prepare_requeues += 1
                            last_prepare_requeue_at = now
                            missing = "รูป" if not image_ready else "Prompt"
                            self.events.put((
                                "multi_flow_progress",
                                f"ช็อต {shot_index}/{int(total_shots or 3)} • {missing} ยังไม่ผูกกับช่องสร้าง • "
                                f"เชื่อมช่อง Prompt เดิมอีกครั้ง ({prepare_requeues}/1)",
                            ))
                            self.bridge.queue_extension_command("resume_flow_workspace", job_id, shot_index)
                        if now - prepare_recovery_started < 90:
                            if cancel_event is not None:
                                if cancel_event.wait(2):
                                    check_cancelled(cancel_event)
                            else:
                                time.sleep(2)
                            continue
                    raise RuntimeError(f"ช็อต {shot_index}: {message}")
                if step == "submission_blocked":
                    image_ready = bool(client.get("flow_image_ready"))
                    prompt_ready = bool(client.get("flow_prompt_ready"))
                    now = time.monotonic()
                    # The Generate click can be ignored while Flow is binding
                    # the uploaded reference to the composer.  Reattach the
                    # same workspace first; only spend an outer project retry
                    # after a bounded 75-second recovery window.
                    if image_ready and prompt_ready:
                        submission_recovery_started = submission_recovery_started or now
                        if submission_requeues < 3 and now - last_submission_requeue_at >= 12:
                            submission_requeues += 1
                            last_submission_requeue_at = now
                            self.events.put((
                                "multi_flow_progress",
                                f"ช็อต {shot_index}/{int(total_shots or 3)} • Flow ยังไม่รับปุ่มสร้าง • "
                                f"ผูก Workspace เดิมและลองส่งใหม่ ({submission_requeues}/3)",
                            ))
                            self.bridge.queue_extension_command("resume_flow_workspace", job_id, shot_index)
                        if now - submission_recovery_started < 75:
                            if cancel_event is not None:
                                if cancel_event.wait(3):
                                    check_cancelled(cancel_event)
                            else:
                                time.sleep(3)
                            continue
                    raise RuntimeError(f"ช็อต {shot_index}: {message}")
                if step == "image_upload_missing":
                    raise RuntimeError(f"ช็อต {shot_index}: {message}")
                if step == "attachment_selecting":
                    observation = client.get("flow_observation") or {}
                    age = time.time() - float(observation.get("received_at") or 0)
                    if 0 <= age < 30:
                        # Live picker observations, not a generic six-minute
                        # timeout or permission to resend/upload another image.
                        deadline += 2
                        if cancel_event is not None:
                            if cancel_event.wait(2):
                                check_cancelled(cancel_event)
                        else:
                            time.sleep(2)
                        continue
                    raise RuntimeError(f"ช็อต {shot_index}: ไม่ได้รับสถานะเลือกรูปล่าสุดจาก Extension • เก็บรูปและโปรเจกต์เดิม ไม่ส่งซ้ำ")
                if step == "attachment_waiting_manual":
                    # Angular may expose the chip seconds after Animate. Let
                    # the Extension resolve that race without another click.
                    # Only its latched structured terminal above can fall back.
                    now = time.monotonic()
                    manual_attachment_wait_started = manual_attachment_wait_started or now
                    if not generation_observed and now - manual_attachment_wait_started >= 75:
                        raise RuntimeError(
                            f"ช็อต {shot_index}: หยุดอย่างปลอดภัยหลังลองแนบรูปหนึ่งครั้ง • "
                            f"ไม่อัปโหลดรูปซ้ำ • ยังไม่ได้รับหลักฐาน terminal จาก Extension • {message}"
                        )
                    if cancel_event is not None:
                        if cancel_event.wait(2):
                            check_cancelled(cancel_event)
                    else:
                        time.sleep(2)
                    continue
                if step == "attachment_needs_review":
                    now = time.monotonic()
                    manual_attachment_wait_started = manual_attachment_wait_started or now
                    # Includes FLOW_ATTACH_PROOF_MISSING_AFTER_SINGLE_ACTION /
                    # FLOW_ATTACH_SAFE_TARGET_MISSING. They are not themselves
                    # evidence that generation is impossible or safe to skip.
                    if generation_observed or now - manual_attachment_wait_started < 75:
                        if cancel_event is not None:
                            if cancel_event.wait(2):
                                check_cancelled(cancel_event)
                        else:
                            time.sleep(2)
                        continue
                    raise RuntimeError(f"ช็อต {shot_index}: หยุดอย่างปลอดภัยหลังลองแนบรูปหนึ่งครั้ง • {message} • ยังไม่ได้รับหลักฐาน terminal จาก Extension")
                if step == "error" and generation_observed and re.search(
                    r"โหลดช้า|ช้าเกินกำหนด|หมดเวลา|timeout|timed?\s*out|load(?:ing)?\s+too\s+slow",
                    message,
                    flags=re.IGNORECASE,
                ):
                    self.events.put((
                        "multi_flow_progress",
                        f"ช็อต {shot_index}/{int(total_shots or 3)} • หน้า Flow ตอบช้าหลังรับงานแล้ว • "
                        "รอโปรเจกต์เดิมและไม่ยกเลิกการสร้าง",
                    ))
                    self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                    if cancel_event is not None:
                        if cancel_event.wait(3):
                            check_cancelled(cancel_event)
                    else:
                        time.sleep(3)
                    continue
                if step in {"project_open_failed", "checkpoint_missing", "generation_failed", "wrong_output_type", "error"}:
                    prefix = policy_marker if step == "generation_failed" and policy_blocked else ""
                    flow_error = RuntimeError(f"{prefix}ช็อต {shot_index}: {message}")
                    if prefix:
                        flow_error.flow_run_id = flow_run_id
                        flow_error.failure_card_fingerprint = failure_card_fingerprint
                        flow_error.policy_failure_category = policy_failure_category
                        flow_error.flow_policy_terminal = True
                    raise flow_error
                if step == "awaiting_credit_approval":
                    excerpt = page_excerpt.lower()
                    confirmation_kind = str(client.get("flow_confirmation_kind") or "").lower()
                    is_credit_prompt = step == "awaiting_credit_approval" or confirmation_kind == "credit" or "เครดิต" in excerpt or "credit" in excerpt
                    if is_credit_prompt and credit_approval_attempts < 3 and time.monotonic() - last_credit_approval_at >= 12:
                        credit_approval_attempts += 1
                        last_credit_approval_at = time.monotonic()
                        self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/{int(total_shots or 3)} • อนุมัติใช้เครดิตอัตโนมัติและไม่ถามซ้ำ • ครั้งที่ {credit_approval_attempts}/3"))
                        self.bridge.queue_extension_command("approve_flow_credit", job_id, shot_index)
                        ambiguous_confirmation_at = None
                        last_change = time.monotonic()
                        if cancel_event is not None:
                            if cancel_event.wait(4):
                                check_cancelled(cancel_event)
                        else:
                            time.sleep(4)
                        self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                        continue
                    if is_credit_prompt and credit_approval_attempts:
                        if generation_observed:
                            if cancel_event is not None:
                                if cancel_event.wait(2):
                                    check_cancelled(cancel_event)
                            else:
                                time.sleep(2)
                            continue
                        if credit_approval_attempts < 3 or time.monotonic() - last_credit_approval_at < 18:
                            self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                            if cancel_event is not None:
                                if cancel_event.wait(2):
                                    check_cancelled(cancel_event)
                            else:
                                time.sleep(2)
                            continue
                        raise RuntimeError("Google Flow ยังไม่ยอมรับการอนุมัติใช้เครดิตอัตโนมัติ")
                    ambiguous_confirmation_at = ambiguous_confirmation_at or time.monotonic()
                    if time.monotonic() - ambiguous_confirmation_at < 15:
                        if cancel_event is not None:
                            if cancel_event.wait(2):
                                check_cancelled(cancel_event)
                        else:
                            time.sleep(2)
                        continue
                    raise RuntimeError("Google Flow ยังไม่ยอมรับการอนุมัติใช้เครดิตอัตโนมัติ")
                if step == "generation_in_progress" and time.monotonic() - last_change >= 180:
                    self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/{int(total_shots or 3)} • รีเฟรชผลหลังเปอร์เซ็นต์ไม่เปลี่ยน 3 นาที"))
                    self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                    last_change = time.monotonic()
                if (step in {"opening_project", "project_handoff", "package_loaded", "preparing"}
                        and not client.get("flow_repair_handoff")
                        and time.monotonic() - last_change >= 75):
                    now = time.monotonic()
                    if workspace_requeues >= 2:
                        raise RuntimeError(
                            f"ช็อต {shot_index}: Google Flow ค้างระหว่างเปิด Workspace หลังลองกู้อัตโนมัติ 2 ครั้ง"
                        )
                    if now - last_workspace_requeue_at >= 30:
                        workspace_requeues += 1
                        last_workspace_requeue_at = now
                        page_url = str(client.get("flow_page_url") or "")
                        if "/project/" in page_url.lower():
                            action = "resume_flow_workspace"
                            detail = "Workspace โหลดช้า • กำลังผูก Extension กับแท็บโปรเจกต์เดิมอีกครั้ง"
                        else:
                            # A stale `preparing` state can survive after the
                            # landing/project tab disappeared.  Starting a new
                            # Flow project for this same shot is safe because
                            # images, prompt and completed clips remain in the
                            # job checkpoint.
                            action = "open_flow"
                            detail = "ไม่พบหน้าโปรเจกต์ระหว่างเตรียมงาน • กำลังเปิด Flow ใหม่จาก Checkpoint เดิม"
                            self.bridge.clear_flow_progress(job_id, shot_index)
                        self.events.put((
                            "multi_flow_progress",
                            f"ช็อต {shot_index}/{int(total_shots or 3)} • {detail} ({workspace_requeues}/2)",
                        ))
                        self.bridge.queue_extension_command(action, job_id, shot_index)
                        last_change = now
            else:
                flow_client_missing_since = flow_client_missing_since or time.monotonic()
                if time.monotonic() - flow_client_missing_since >= 20:
                    if flow_client_requeues >= 2:
                        raise RuntimeError(
                            f"ช็อต {shot_index}: Extension ออนไลน์แต่ไม่พบแท็บ Google Flow ของ Job นี้"
                        )
                    flow_client_requeues += 1
                    self.events.put((
                        "multi_flow_progress",
                        f"ช็อต {shot_index}/{int(total_shots or 3)} • ไม่พบแท็บงานเดิม • เปิด Flow และผูก Checkpoint ใหม่ "
                        f"({flow_client_requeues}/2)",
                    ))
                    self.bridge.clear_flow_progress(job_id, shot_index)
                    self.bridge.queue_extension_command("open_flow", job_id, shot_index)
                    flow_client_missing_since = time.monotonic()
            if cancel_event is not None:
                if cancel_event.wait(3):
                    check_cancelled(cancel_event)
            else:
                time.sleep(3)
        timeout_error = TimeoutError(f"หมดเวลารอ Google Flow ช็อต {shot_index} • เก็บโปรเจกต์เดิม ไม่ส่งซ้ำ")
        timeout_error.flow_retry_forbidden = True
        raise timeout_error

    def _wait_download(self, job_id, shot_index, timeout=180, cancel_event=None, started_at=None, total_shots=3, expected_run_id="", scene_video_plan=None):
        from core.scene_video_worker import flow_download_path, SceneVideoReviewError
        target = flow_download_path(job_id, shot_index, scene_video_plan)
        downloads = Path.home() / "Downloads"
        expected_target = target.resolve()
        started_at = float(started_at if started_at is not None else time.time() - 5) - 0.5
        deadline = time.monotonic() + timeout
        previous_size = -1
        stable = 0
        retry_count = 0
        next_retry_at = time.monotonic() + 15
        while time.monotonic() < deadline:
            check_cancelled(cancel_event)
            if scene_video_plan:
                from core.scene_video_plan import assert_binding
                try:
                    assert_binding(self.stories.get(job_id), shot_index, scene_video_plan)
                except ValueError as exc:
                    raise SceneVideoReviewError(str(exc)) from exc
            current_target = None
            reported_target = None
            completed_download_receipt = False
            try:
                status = self.bridge.extension_status()
                flow_client = next((item for item in status.get("clients") or []
                    if str(item.get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION
                    and str(item.get("flow_job_id") or "") == job_id
                    and int(item.get("flow_shot_index") or 0) == int(shot_index)
                    and (not scene_video_plan or item.get('flow_scene_video_plan') == scene_video_plan)
                    and (not expected_run_id or str(item.get("flow_run_id") or "") == expected_run_id)), None)
                reported_path = Path(str((flow_client or {}).get("flow_download_path") or "")).resolve()
                downloads_root = downloads.resolve()
                completed_download_receipt = bool(
                    flow_client
                    and str(flow_client.get("flow_step") or "") == "generation_complete"
                    and reported_path == expected_target
                    and (not scene_video_plan or re.fullmatch(r'[a-f0-9]{64}', str(flow_client.get('flow_download_sha256') or '')))
                )
                if target.is_file() and (
                    target.stat().st_mtime >= started_at or completed_download_receipt
                ) and (not scene_video_plan or completed_download_receipt):
                    current_target = target
                if (reported_path.is_file()
                    and reported_path == expected_target
                    and (reported_path.stat().st_mtime >= started_at or completed_download_receipt)
                    and reported_path.suffix.lower() in {".mp4", ".webm"}
                    and downloads_root in reported_path.parents):
                    if not scene_video_plan or completed_download_receipt:
                        reported_target = reported_path
            except (OSError, RuntimeError, ValueError):
                reported_target = None
                if not scene_video_plan and target.is_file() and target.stat().st_mtime >= started_at:
                    current_target = target
            # Never adopt an arbitrary recent MP4 from the user's Downloads
            # folder. The Extension owns one deterministic path per Job/shot;
            # accepting another file can attach a personal video to this job.
            fallback_patterns = (
                f"flow-shot-{shot_index:02d}.mp4",
                f"flow-shot-{shot_index:02d} (",
            )
            safe_fallbacks = [] if scene_video_plan else [
                item for item in target.parent.glob(f"{target.stem}*.mp4")
                if item.stat().st_mtime >= started_at
                and (
                    item.name == fallback_patterns[0]
                    or item.name.startswith(fallback_patterns[1])
                )
            ]
            candidate = current_target or reported_target or (
                max(safe_fallbacks, key=lambda item: item.stat().st_mtime)
                if safe_fallbacks else None
            )
            if candidate and candidate.is_file():
                size = candidate.stat().st_size
                # A matching generation_complete receipt is emitted only after
                # chrome.downloads reports state=complete for this exact
                # Job/shot/path. In that case the file is already closed and we
                # can validate its header immediately instead of adding two
                # extra two-second stability polls. Files discovered without a
                # receipt keep the conservative stability gate.
                stable = 2 if completed_download_receipt else (
                    stable + 1 if size > 0 and size == previous_size else 0
                )
                previous_size = size
                if stable >= 2:
                    try:
                        header = candidate.read_bytes()[:64]
                    except OSError:
                        header = b""
                    probable_mp4 = len(header) >= 12 and b"ftyp" in header[:32]
                    probable_webm = header.startswith(b"\x1aE\xdf\xa3")
                    if size >= 64 * 1024 and (probable_mp4 or probable_webm):
                        return candidate
                    self._write_console(
                        f"{job_id} • FLOW DOWNLOAD REJECTED • shot {shot_index} • "
                        f"invalid video header/size: {candidate.name} ({size} bytes)",
                        "error",
                    )
                    stable = 0
            if time.monotonic() >= next_retry_at and retry_count < 2:
                retry_count += 1
                self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/{int(total_shots or 3)} • ยังไม่พบไฟล์ กำลังสั่งดาวน์โหลดซ้ำ {retry_count}/2"))
                self.bridge.queue_extension_command("open_flow_result", job_id, shot_index)
                self.bridge.queue_extension_command("download_flow_result", job_id, shot_index)
                next_retry_at = time.monotonic() + (20 if retry_count == 1 else 40)
            if cancel_event is not None:
                if cancel_event.wait(2):
                    check_cancelled(cancel_event)
            else:
                time.sleep(2)
        raise TimeoutError(f"ไม่พบไฟล์ดาวน์โหลดของช็อต {shot_index}")

    def _render_product_policy_fallback_segment(self, job_id, shot_index, cancel_event=None):
        """Resume or render one Product local-motion policy checkpoint."""
        check_cancelled(cancel_event)
        folder = self.products.root / str(job_id)
        job = self.products.get_job(job_id)
        fallback = ProductManager.flow_local_fallback_checkpoint(job, shot_index)
        if not fallback:
            raise RuntimeError(f"ช็อต {shot_index} ยังไม่มี Checkpoint ใช้รูปแทนที่ยืนยันแล้ว")
        source_index = int(fallback.get("source_image_index") or shot_index)
        image_files = list(job.get("composition_images") or job.get("generated_images") or job.get("source_images") or [])
        if not 1 <= source_index <= len(image_files):
            raise RuntimeError(f"ไม่พบรูปต้นทางที่ {source_index} สำหรับ Local Motion")
        source_image = folder / str(image_files[source_index - 1])
        if not source_image.is_file():
            raise RuntimeError(f"ไฟล์รูปต้นทางที่ {source_index} หายไป")
        if fallback.get("failure_code") == "USER_APPROVED_IMAGE_REUSE":
            if hashlib.sha256(source_image.read_bytes()).hexdigest() != fallback.get("source_sha256"):
                raise RuntimeError("ภาพสำรองเปลี่ยนจากที่ผู้ใช้อนุมัติ หยุดเพื่อป้องกันการใช้ภาพผิด")

        target = working_video_folder(folder) / f"product_local_motion_shot_{shot_index:02d}.mp4"
        reusable = False
        if target.is_file() and target.stat().st_size >= 64 * 1024:
            try:
                with target.open("rb") as handle:
                    header = handle.read(64)
            except OSError:
                header = b""
            reusable = len(header) >= 12 and b"ftyp" in header[:32]
        if reusable:
            plan = {
                "output": str(target),
                "source_type": (
                    "product_local_motion_attachment_fallback"
                    if fallback.get("failure_code") == "FLOW_ATTACHMENT_UNCONFIRMED"
                    else "product_local_motion_policy_fallback"
                ),
                "checkpoint_recovered": True,
            }
        else:
            render_settings = self._video_render_settings()
            plan = ProductImageVideoComposer(self.cfg.get("ffmpeg_path", "")).render_motion_segment(
                source_image,
                target,
                duration=10.0,
                width=render_settings["width"],
                height=render_settings["height"],
                fps=render_settings["fps"],
                crf=render_settings["crf"],
                motion_strength=(0.30 + shot_index * 0.12) if fallback.get("failure_code") == "USER_APPROVED_IMAGE_REUSE" else 0.55,
                cancel_event=cancel_event,
            )
        plan["source_type"] = (
            "product_local_motion_attachment_fallback"
            if fallback.get("failure_code") == "FLOW_ATTACHMENT_UNCONFIRMED"
            else "product_local_motion_policy_fallback"
        )
        plan["failure_code"] = fallback.get("failure_code")
        if fallback.get("failure_code") == "USER_APPROVED_IMAGE_REUSE":
            plan["source_type"] = "product_local_motion_user_image_reuse"
        checkpoint = self.products.attach_flow_local_motion_clip(
            job_id, shot_index, target, render_plan=plan,
        )
        saved = folder / str((checkpoint.get("flow_local_motion_clips") or {}).get(str(shot_index)) or "")
        if not saved.is_file():
            raise RuntimeError(f"บันทึก Local Motion ช็อต {shot_index} ไม่สำเร็จ")
        return saved, plan

    @product_render
    def _multi_flow_worker(self, job_id, cancel_event=None, emit_event=True, raise_errors=False):
        try:
            folder = self.products.root / job_id
            clip_paths = []
            accepted_hashes = {}
            previous_shot_completed_in_worker = False

            def clip_digest(path):
                digest = hashlib.sha256()
                with Path(path).open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                return digest.hexdigest()

            initial_job = self.products.ensure_product_flow_source_identity(job_id)
            target_clip_count = len(initial_job.get("composition_images") or initial_job.get("generated_images") or initial_job.get("source_images") or []) or 3
            for shot_index in range(1, target_clip_count + 1):
                check_cancelled(cancel_event)
                current = self.products.get_job(job_id)
                policy_fallback = ProductManager.flow_local_fallback_checkpoint(current, shot_index)
                existing_relative = str((current.get("flow_clips") or {}).get(str(shot_index)) or "")
                existing_path = folder / existing_relative
                if policy_fallback and not (existing_relative and existing_path.is_file() and existing_path.stat().st_size > 1024):
                    raise FlowVideoReviewError(shot_index, "พบ Checkpoint ภาพสำรองเดิม ยังไม่มีคลิป Flow จริง")
                existing_relative = str((current.get("flow_clips") or {}).get(str(shot_index)) or "")
                existing_clip = self.products.root / job_id / existing_relative
                duplicate_existing = False
                if existing_relative and existing_clip.is_file():
                    existing_hash = clip_digest(existing_clip)
                    duplicate_of = accepted_hashes.get(existing_hash)
                    if duplicate_of:
                        duplicate_existing = True
                        self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/3 • พบไฟล์ซ้ำกับช็อต {duplicate_of} • จะสร้างช็อตนี้ใหม่"))
                        self._write_console(f"{job_id} • FLOW DUPLICATE BLOCKED • shot {shot_index} == shot {duplicate_of}", "error")
                    else:
                        accepted_hashes[existing_hash] = shot_index
                        clip_paths.append(existing_clip)
                        self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/3 • ใช้ Checkpoint เดิม ไม่สร้างซ้ำ"))
                        self._product_progress_event(job_id, 52 + shot_index * 8, "flow", f"Google Flow พร้อมแล้ว {shot_index}/3 ช็อต", "ใช้ไฟล์เดิมสำหรับช็อตที่เสร็จแล้ว")
                        previous_shot_completed_in_worker = False
                        continue

                accepted = False
                max_generation_attempts = 3
                reuse_remote_result = False
                skip_remote_checkpoint_probe = bool(
                    previous_shot_completed_in_worker and not existing_relative
                )
                for generation_attempt in range(1, max_generation_attempts + 1):
                    current = self.products.get_job(job_id)
                    source_image_index = int((current.get("flow_source_image_map") or {}).get(str(shot_index)) or shot_index)
                    source_variant_index = int((current.get("flow_source_variant_map") or {}).get(str(shot_index)) or 1)
                    force_new = duplicate_existing or (generation_attempt > 1 and not reuse_remote_result)
                    remote_checkpoint = False
                    generation_ready = False
                    self._ensure_flow_extension(job_id, shot_index, cancel_event=cancel_event)
                    if not force_new and skip_remote_checkpoint_probe:
                        # This worker has just downloaded and committed the
                        # previous shot, so the next untouched shot cannot have
                        # a remote checkpoint owned by an earlier run. Go
                        # straight to opening it instead of spending another
                        # inspect/heartbeat round-trip. Resumed workers still
                        # use the full checkpoint probe.
                        self.events.put((
                            "multi_flow_progress",
                            f"ช็อต {shot_index}/3 • เดินต่อจากช็อตก่อนหน้าทันที",
                        ))
                    elif not force_new:
                        self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/3 • ตรวจ Checkpoint ที่ผูกกับโปรเจกต์เดิม"))
                        self.bridge.queue_extension_command("inspect_flow", job_id, shot_index)
                        inspect_deadline = time.monotonic() + 25
                        while time.monotonic() < inspect_deadline:
                            check_cancelled(cancel_event)
                            status = self.bridge.extension_status()
                            client = next((item for item in status.get("clients") or []
                                if str(item.get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION
                                and item.get("flow_job_id") == job_id and int(item.get("flow_shot_index") or 0) == shot_index), None)
                            if client:
                                step = str(client.get("flow_step") or "")
                                if str(client.get("flow_failure_code") or "") in {
                                    "FLOW_REPAIR_REVIEW", "FLOW_SEND_REVIEW", "FLOW_VIDEO_SETTINGS_REVIEW", "FLOW_POLICY_BLOCKED",
                                }:
                                    remote_checkpoint = True
                                    break
                                reusable_playable_result = bool(client.get("flow_has_playable_result")) and not bool(client.get("flow_generation_active"))
                                if step in {"generation_complete", "generation_in_progress", "awaiting_credit_approval", "awaiting_rights_confirmation"} or reusable_playable_result:
                                    remote_checkpoint = True
                                    self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/3 • พบ Checkpoint ของช็อตนี้จริง • ทำต่อโดยไม่สร้างซ้ำ"))
                                    break
                                if step in {"checkpoint_missing", "checkpoint_mismatch", "generation_failed", "submission_blocked", "generate_button_missing", "error"}:
                                    break
                            if cancel_event is not None:
                                if cancel_event.wait(2):
                                    check_cancelled(cancel_event)
                            else:
                                time.sleep(2)
                    if reuse_remote_result and not remote_checkpoint:
                        # A finished video can take time to hydrate after its
                        # project URL is reopened. Keep waiting on that exact
                        # result instead of deleting its checkpoint and paying
                        # for another generation merely because the first
                        # inspect happened too early.
                        remote_checkpoint = True
                        self.events.put((
                            "multi_flow_progress",
                            f"ช็อต {shot_index}/3 • วิดีโอสร้างเสร็จแล้ว • "
                            "กำลังรอผลเดิมพร้อมดาวน์โหลด ไม่สร้างซ้ำ",
                        ))
                    if not remote_checkpoint:
                        if duplicate_existing:
                            action = "กำลังสร้างใหม่เพราะตรวจพบคลิปซ้ำ"
                        elif generation_attempt > 1:
                            action = "กำลังเปิดโปรเจกต์ใหม่หลังรอบก่อนค้างหรือผิดพลาด"
                        else:
                            action = "ส่งรูปและ Prompt เข้า Google Flow"
                        self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/3 • {action}"))
                        self.bridge.clear_flow_progress(job_id, shot_index)
                        self.bridge.queue_extension_command("open_flow", job_id, shot_index)
                    try:
                        self._wait_flow_step(job_id, shot_index, cancel_event=cancel_event)
                        generation_ready = True
                        self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/3 • กำลังดาวน์โหลดผลลัพธ์"))
                        download_started_at = time.time()
                        self.bridge.queue_extension_command("download_flow_result", job_id, shot_index)
                        downloaded = self._wait_download(job_id, shot_index, cancel_event=cancel_event, started_at=download_started_at)
                    except OperationCancelled:
                        raise
                    except Exception as exc:
                        failure_text = str(exc)
                        if getattr(exc, "flow_retry_forbidden", False):
                            raise
                        if (getattr(exc, "flow_attachment_terminal", False)
                                or getattr(exc, "flow_policy_terminal", False)):
                            raise FlowVideoReviewError(shot_index, failure_text) from exc
                        if any(marker in failure_text for marker in (
                            "ลองแนบรูปแล้วหนึ่งครั้ง",
                            "หยุดเพื่อป้องกันการอัปโหลดรูปซ้ำ",
                            "หยุดอย่างปลอดภัยหลังลองแนบรูปหนึ่งครั้ง",
                            "เปิดโหมดแก้ภาพนิ่งแทนโหมดสร้างวิดีโอ",
                        )):
                            raise RuntimeError(
                                f"Google Flow ช็อต {shot_index} หยุดอย่างปลอดภัย • "
                                "ไม่เปิดโปรเจกต์ใหม่และไม่อัปโหลดรูปซ้ำ • "
                                f"{failure_text}"
                            ) from exc
                        if generation_attempt >= max_generation_attempts:
                            raise RuntimeError(
                                f"Google Flow ช็อต {shot_index} ล้มเหลวหลังลองใหม่ "
                                f"{max_generation_attempts} รอบ • {exc}"
                            ) from exc
                        next_attempt = generation_attempt + 1
                        reuse_remote_result = bool(generation_ready)
                        if reuse_remote_result:
                            retry_message = (
                                f"ช็อต {shot_index}/3 • วิดีโอสร้างเสร็จแล้วแต่ไฟล์ยังไม่พร้อม • "
                                f"เปิดผลเดิมและลองดาวน์โหลดใหม่ ({next_attempt}/{max_generation_attempts})"
                            )
                        else:
                            retry_message = (
                                f"ช็อต {shot_index}/3 • รอบ {generation_attempt} ไม่สำเร็จ • "
                                f"สร้างโปรเจกต์ Flow ใหม่และลองเฉพาะช็อตนี้ ({next_attempt}/{max_generation_attempts})"
                            )
                        self.events.put(("multi_flow_progress", retry_message))
                        self._write_console(
                            f"{job_id} • FLOW RETRY • shot {shot_index} • "
                            f"attempt {generation_attempt}/{max_generation_attempts} • {exc}",
                            "error",
                        )
                        if not reuse_remote_result:
                            self.bridge.queue_extension_command("stop_flow_generation", job_id, shot_index)
                        self.bridge.clear_flow_progress(job_id, shot_index)
                        if cancel_event is not None:
                            if cancel_event.wait(3):
                                check_cancelled(cancel_event)
                        else:
                            time.sleep(3)
                        continue
                    downloaded_hash = clip_digest(downloaded)
                    duplicate_of = accepted_hashes.get(downloaded_hash)
                    if duplicate_of:
                        self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/3 • ปฏิเสธผลซ้ำกับช็อต {duplicate_of} • ลองสร้างใหม่ {generation_attempt}/{max_generation_attempts}"))
                        self._write_console(f"{job_id} • FLOW DOWNLOAD REJECTED • shot {shot_index} == shot {duplicate_of}", "error")
                        duplicate_existing = True
                        continue
                    self.events.put(("multi_flow_progress", f"ช็อต {shot_index}/3 • ดาวน์โหลดสำเร็จและไม่ซ้ำ: {downloaded.name}"))
                    checkpoint = self.products.attach_flow_clip(job_id, shot_index, downloaded)
                    saved_clip = folder / str((checkpoint.get("flow_clips") or {}).get(str(shot_index)) or "")
                    self._close_saved_flow_tab(job_id, shot_index, saved_clip)
                    accepted_hashes[downloaded_hash] = shot_index
                    clip_paths.append(saved_clip)
                    self._product_progress_event(job_id, 52 + shot_index * 8, "flow", f"Google Flow พร้อมแล้ว {shot_index}/3 ช็อต", "ตรวจลายนิ้วมือไฟล์แล้ว • ไม่ซ้ำกับช็อตก่อนหน้า")
                    accepted = True
                    previous_shot_completed_in_worker = True
                    break
                if not accepted:
                    raise RuntimeError(f"Google Flow ส่งวิดีโอซ้ำสำหรับช็อต {shot_index} {max_generation_attempts} รอบ • ระบบหยุดก่อนประกอบคลิป")
            check_cancelled(cancel_event)
            if len(clip_paths) < target_clip_count:
                raise RuntimeError(
                    f"ต้องมีช่วงวิดีโอครบ {target_clip_count} ช่วงก่อนประกอบ Final • "
                    "แต่ละรูปต้องเป็น Google Flow หรือ Local Motion ที่มี provenance ชัดเจน"
                )
            job = next(item for item in self.products.list_jobs() if item.get("id") == job_id)
            folder = self.products.root / job_id
            voice = folder / str(job.get("voice_path") or "") if job.get("voice_path") else None
            composer = MultiFlowComposer(self.cfg.get("ffmpeg_path", ""))
            working = working_video_folder(folder)
            joined = working / "multi_flow_joined.mp4"
            render_settings = job.get('render_snapshot') or self._video_render_settings()
            result = composer.compose(
                clip_paths, joined, voice_path=voice if voice and voice.is_file() else "",
                width=render_settings["width"], height=render_settings["height"], fps=render_settings["fps"],
                crf=render_settings["crf"], transition_sec=render_settings["transition_sec"],
                audio_choices=job.get("audio_choices"), cancel_event=cancel_event,
            )
            self.products.promote_video(job_id, str(joined.relative_to(folder)), flow_source_path=str(joined.relative_to(folder)))
            final = joined
            if bool(self.cfg.get("video_effect_enabled", True)):
                effect_output = working / "multi_flow_with_effects.mp4"
                effect_settings = self._effect_settings()
                effect_settings["crf"] = render_settings["crf"]
                effect_result = ProductEffectsRenderer(self.cfg.get("ffmpeg_path", "")).render(joined, effect_output, labels=self._effect_labels(job), **effect_settings)
                self.products.save_effect_video(job_id, effect_output, joined, effect_settings)
                final = effect_output
            logo = self._job_logo_file(job)
            if logo.is_file():
                renderer = VideoLogoRenderer(self.cfg.get("ffmpeg_path", ""))
                source_for_logo = final
                final = working / "multi_flow_final_with_logo.mp4"
                logo_result = renderer.render(
                    source_for_logo, logo, final,
                    **self._job_logo_options(job),
                    crf=render_settings["crf"],
                )
                self.products.save_logo_video(job_id, final, source_for_logo, logo, logo_result)
            if emit_event:
                self.events.put(("multi_flow_ready", (job_id, final, result)))
            return job_id, final, result
        except Exception as exc:
            if emit_event:
                self.events.put(("multi_flow_error", str(exc)))
            if raise_errors:
                raise
            return None

    def _multi_meta_product_worker(self, job_id, cancel_event=None, emit_event=False, raise_errors=False):
        """Create the missing Meta scenes for a legacy Product Job, then compose its saved clips."""
        from core.meta_video import MetaVideoManager
        manager = MetaVideoManager(self.stories, products=self.products)
        job = self.products.get_job(job_id)
        total = int(job.get('flow_target_clip_count') or len(job.get('composition_images') or job.get('generated_images') or job.get('source_images') or []) or 3)
        try:
            if str(job.get('video_ai_provider') or '') != 'meta_ai':
                raise ValueError('งานนี้ยังไม่ได้เลือก Meta AI')
            for index in range(1, total + 1):
                check_cancelled(cancel_event)
                request = manager.begin(job_id, index)
                if request.get('stage') == 'stored':
                    self._product_progress_event(job_id, 52 + int(25 * index / total), 'video',
                        f'Meta AI • ใช้ฉากเดิม {index}/{total}', 'พบไฟล์และใบรับผลเดิม • ไม่สร้างซ้ำ')
                    continue
                command = self.bridge.queue_extension_command('open_meta_video', job_id, index)
                while True:
                    check_cancelled(cancel_event)
                    receipt = manager.get(job_id, index)
                    command_state = self.bridge.extension_command_status(command['id']) if command else None
                    if command_state and command_state.get('status') == 'failed':
                        raise ValueError('META_VIDEO_REVIEW • ' + str(command_state.get('error') or 'เปิด Meta ไม่สำเร็จ'))
                    if receipt.get('stage') == 'stored':
                        break
                    if receipt.get('stage') == 'needs_attention':
                        raise ValueError('META_VIDEO_REVIEW • ' + str(receipt.get('message') or 'ตรวจฉาก Meta ก่อนทำต่อ'))
                    self._product_progress_event(job_id, 52 + int(25 * (index - 1) / total), 'video',
                        f'Meta AI • ฉาก {index}/{total}', receipt.get('message') or receipt.get('stage') or 'รอ Extension')
                    if cancel_event is not None:
                        cancel_event.wait(2)
                    else:
                        time.sleep(2)
            clip_paths = manager.clips(job_id)
            return self._compose_product_video_clips(job_id, clip_paths, cancel_event, source_provider='meta_ai')
        except Exception as exc:
            if emit_event:
                self.events.put(('multi_flow_error', str(exc)))
            if raise_errors:
                raise
            return None

    @product_render
    def _compose_product_video_clips(self, job_id, clip_paths, cancel_event=None, source_provider='flow'):
        """Compose verified scene files from the explicitly selected video provider."""
        check_cancelled(cancel_event)
        job = self.products.get_job(job_id)
        folder = self.products.root / job_id
        voice = folder / str(job.get("voice_path") or "") if job.get("voice_path") else None
        composer = MultiFlowComposer(self.cfg.get("ffmpeg_path", ""))
        working = working_video_folder(folder)
        joined = working / "multi_flow_joined.mp4"
        render_settings = job.get('render_snapshot') or self._video_render_settings()
        result = composer.compose(
            clip_paths, joined, voice_path=voice if voice and voice.is_file() else "",
            audio_choices=job.get("audio_choices"), cancel_event=cancel_event,
            width=render_settings["width"], height=render_settings["height"], fps=render_settings["fps"],
            crf=render_settings["crf"], transition_sec=render_settings["transition_sec"],
        )
        self.products.promote_video(job_id, str(joined.relative_to(folder)),
            flow_source_path=str(joined.relative_to(folder)) if source_provider == 'flow' else '',
            source_provider=source_provider)
        final = joined
        if bool(self.cfg.get("video_effect_enabled", True)):
            effect_output = working / "multi_flow_with_effects.mp4"
            effect_settings = self._effect_settings()
            effect_settings["crf"] = render_settings["crf"]
            ProductEffectsRenderer(self.cfg.get("ffmpeg_path", "")).render(joined, effect_output, labels=self._effect_labels(job), **effect_settings)
            self.products.save_effect_video(job_id, effect_output, joined, effect_settings)
            final = effect_output
        logo = self._job_logo_file(job)
        if logo.is_file():
            source_for_logo = final
            final = working / "multi_flow_final_with_logo.mp4"
            logo_result = VideoLogoRenderer(self.cfg.get("ffmpeg_path", "")).render(
                source_for_logo, logo, final,
                **self._job_logo_options(job),
                crf=render_settings["crf"],
            )
            self.products.save_logo_video(job_id, final, source_for_logo, logo, logo_result)
        return job_id, final, result

    def _edit_selected_product(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน"); return
        job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
        if not job: return
        dialog = tk.Toplevel(self.root); dialog.title("แก้ข้อมูลสินค้า"); dialog.geometry("580x470"); dialog.configure(bg=COLORS["panel"]); dialog.transient(self.root); dialog.grab_set()
        form = tk.Frame(dialog, bg=COLORS["panel"]); form.pack(fill="both", expand=True, padx=22, pady=18)
        tk.Label(form, text="ตรวจข้อมูลสินค้าก่อนส่งเข้า AI", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 16)).pack(anchor="w", pady=(0, 12))
        fields = {}
        for label, key in (("ชื่อสินค้า", "product_name"), ("ราคา", "price"), ("ค่าคอมมิชชัน", "commission")):
            tk.Label(form, text=label, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w")
            entry = tk.Entry(form, bg="#080D1E", fg=COLORS["text"], insertbackground="white", relief="flat", font=("Segoe UI", 10)); entry.pack(fill="x", ipady=7, pady=(3, 9)); entry.insert(0, job.get(key, "")); fields[key] = entry
        tk.Label(form, text="รายละเอียดที่ตรวจสอบแล้ว", bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w")
        description = tk.Text(form, height=5, bg="#080D1E", fg=COLORS["text"], insertbackground="white", relief="flat", font=("Segoe UI", 10)); description.pack(fill="both", expand=True, pady=(3, 12)); description.insert("1.0", job.get("description", ""))
        def save():
            try:
                self.products.update_product_info(job_id, fields["product_name"].get(), fields["price"].get(), fields["commission"].get(), description.get("1.0", "end").strip())
                dialog.destroy(); self._refresh(); self.status.set("บันทึกข้อมูลสินค้าและสร้าง Prompt ใหม่แล้ว")
            except Exception as exc: messagebox.showerror("บันทึกไม่สำเร็จ", str(exc), parent=dialog)
        ttk.Button(form, text="บันทึกข้อมูล", style="Primary.TButton", command=save).pack(anchor="e")

    def _approve_ai(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน"); return
        job = next((item for item in self.products.list_jobs() if item.get("id") == job_id), None)
        if not job: return
        if job.get("ai_status") != "ready":
            messagebox.showwarning("ยังไม่มีผล AI", "กรุณาสร้างรูปและแคปชั่นก่อน"); return
        dialog = tk.Toplevel(self.root); dialog.title(f"AI Review • {job_id}"); dialog.geometry("900x650"); dialog.configure(bg=COLORS["bg"]); dialog.transient(self.root); dialog.grab_set()
        header = tk.Frame(dialog, bg=COLORS["sidebar"]); header.pack(fill="x")
        tk.Label(header, text="ตรวจรูปและแคปชั่นก่อนอนุมัติ", bg=COLORS["sidebar"], fg=COLORS["text"], font=("Segoe UI Semibold", 16)).pack(side="left", padx=18, pady=14)
        source_text = "สร้างจากรูปต้นฉบับใน Job" if job.get("generated_from_source_images") else "ภาพทดลองไม่ได้สร้างจากรูปต้นฉบับใน Job"
        tk.Label(header, text=source_text, bg="#173C37" if job.get("generated_from_source_images") else "#4A2730", fg=COLORS["green"] if job.get("generated_from_source_images") else COLORS["danger"], font=("Segoe UI Semibold", 8), padx=10, pady=5).pack(side="right", padx=18)
        body = tk.Frame(dialog, bg=COLORS["bg"]); body.pack(fill="both", expand=True, padx=18, pady=18)
        preview = tk.Frame(body, bg=COLORS["panel"], width=360, highlightbackground=COLORS["line"], highlightthickness=1); preview.pack(side="left", fill="both"); preview.pack_propagate(False)
        image_paths = job.get("generated_images") or []
        image_target = self.products.root / job_id / image_paths[0] if image_paths else None
        if image_target and image_target.exists():
            image = Image.open(image_target).convert("RGB"); image.thumbnail((330, 470), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(image); dialog.preview_image = photo
            tk.Label(preview, image=photo, bg=COLORS["panel"]).pack(expand=True, padx=12, pady=12)
            ttk.Button(preview, text="เปิดภาพขนาดเต็ม", style="Ghost.TButton", command=lambda: subprocess.Popen(["explorer", str(image_target)])).pack(pady=(0, 12))
        else:
            tk.Label(preview, text="ยังไม่มีภาพที่สร้าง", bg=COLORS["panel"], fg=COLORS["danger"], font=("Segoe UI", 11)).pack(expand=True)
        detail = tk.Frame(body, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1); detail.pack(side="left", fill="both", expand=True, padx=(14, 0))
        tk.Label(detail, text=job.get("product_name", ""), bg=COLORS["panel"], fg=COLORS["text"], wraplength=430, justify="left", font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=16, pady=(16, 10))
        tk.Label(detail, text="แคปชั่น", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=16)
        caption = tk.Text(detail, height=7, bg="#080D1E", fg=COLORS["text"], relief="flat", wrap="word", font=("Segoe UI", 10), padx=10, pady=8); caption.pack(fill="x", padx=16, pady=(5, 12)); caption.insert("1.0", job.get("caption", "")); caption.configure(state="disabled")
        tk.Label(detail, text="คำเตือน", bg=COLORS["panel"], fg=COLORS["orange"], font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=16)
        warnings = "\n".join(f"• {item}" for item in job.get("warnings") or []) or "ไม่มีคำเตือน"
        tk.Label(detail, text=warnings, bg=COLORS["panel"], fg=COLORS["muted"], wraplength=430, justify="left", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(5, 14))
        actions = tk.Frame(detail, bg=COLORS["panel"]); actions.pack(side="bottom", fill="x", padx=16, pady=16)
        ttk.Button(actions, text="ยังไม่อนุมัติ", style="Ghost.TButton", command=dialog.destroy).pack(side="left")
        def approve():
            try:
                self.products.approve_ai_result(job_id); dialog.destroy(); self._refresh(); self.status.set(f"อนุมัติผล AI ของ {job_id} แล้ว")
            except Exception as exc: messagebox.showerror("อนุมัติไม่สำเร็จ", str(exc), parent=dialog)
        ttk.Button(actions, text="ตรวจแล้ว • อนุมัติ", style="Primary.TButton", command=approve).pack(side="right")

    def _check_selected_readiness(self):
        job_id = self._selected_product_job()
        if not job_id:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน"); return
        readiness = self.products.check_readiness(job_id)
        self._refresh()
        if readiness["ready"]:
            messagebox.showinfo("พร้อมส่งเข้ามือถือ", "ลิงก์สินค้า แคปชั่น และวิดีโอพร้อมแล้ว")
        else:
            labels = {"product_link": "ลิงก์สินค้า", "caption": "แคปชั่น", "video": "วิดีโอ", "ai_result": "ผลลัพธ์ AI", "ai_approval": "การอนุมัติผล AI"}
            missing = ", ".join(labels.get(item, item) for item in readiness["missing"])
            messagebox.showwarning("ข้อมูลยังไม่พร้อม", f"ยังขาด: {missing}")

    def _copy_video(self, job_id, path):
        self.products.attach_video(job_id, path)
        self.events.put(("product", f"เพิ่มวิดีโอให้ {job_id} แล้ว"))

    def _open_selected_product(self):
        selected = self.product_table.selection()
        if not selected:
            messagebox.showinfo("เลือกสินค้า", "กรุณาเลือก Product Job ก่อน"); return
        job_id = self.product_table.item(selected[0], "values")[0]
        self._open_folder(self.products.root / job_id)

    def _open_affiliate(self):
        self._open_url("https://affiliate.shopee.co.th/offer/product_offer")

    def _open_extension(self):
        self._open_url("chrome://extensions")
        self._open_folder(ROOT / "browser_extension")

    def _start_browser_connection(self):
        """Open the installed profile once; never dispatch creation or resume work."""
        if os.environ.get("SMARTFLOW_TEST_DATA_ROOT") or getattr(self, "_browser_connection_closing", False):
            return {"phase": "skipped", "message": ""}
        if getattr(self, "_app_update_pending", False):
            return {"phase": "skipped", "message": "กำลังเตรียมอัปเดต"}
        now = time.monotonic()
        state = getattr(self, "_browser_connection", {})
        worker = getattr(self, "_browser_connection_worker", None)
        if state.get("phase") == "connecting" or (worker and worker.is_alive()):
            return dict(state)
        if now - getattr(self, "_browser_connection_requested_at", -60.0) < 5:
            return dict(state)
        self._browser_connection_requested_at = now
        self._browser_connection = {
            "phase": "connecting", "message": "กำลังเปิด Chrome ที่มี SmartFlow Extension • รอเชื่อมต่อ",
        }
        self._browser_connection_result = None

        def launch():
            try:
                if getattr(self, "_browser_connection_closing", False):
                    return
                if getattr(self, "_app_update_pending", False):
                    result = {"ok": False, "skipped": True}
                else:
                    self._activate_or_launch_chrome("about:blank")
                    result = {"ok": True}
            except Exception as exc:
                # A profile/Chrome failure must not escape into the job worker
                # or trigger its unrelated ADB screenshot/error path.
                result = {"ok": False, "message": str(exc)}
            self._browser_connection_result = result

        self._browser_connection_worker = threading.Thread(target=launch, name="smartflow-browser-connect", daemon=True)
        self._browser_connection_worker.start()
        self.root.after(1000, self._check_browser_connection)
        return dict(self._browser_connection)

    def _check_browser_connection(self):
        if getattr(self, "_browser_connection_closing", False):
            return
        if getattr(self, "_browser_connection", {}).get("phase") != "connecting":
            return
        result = getattr(self, "_browser_connection_result", None)
        if result and result.get("skipped"):
            self._browser_connection = {"phase": "skipped", "message": ""}
            return
        extension, compatible = self._compatible_extension()
        if result and result.get("ok") and extension.get("connected") and compatible and self._chrome_window_available():
            self._browser_connection = {"phase": "ready", "message": "Chrome และ SmartFlow Extension เชื่อมต่อแล้ว"}
            return
        message = ""
        if result is not None and not result.get("ok"):
            message = "เปิด Chrome อัตโนมัติไม่ได้ • " + result.get("message", "กรุณาตรวจการติดตั้ง Chrome")
        elif result is not None and extension.get("connected") and not compatible:
            message = f"Extension รุ่นไม่ตรง • กรุณาโหลด SmartFlow Extension v{self.bridge.REQUIRED_EXTENSION_VERSION} แล้วโหลดซ้ำ"
        elif time.monotonic() - self._browser_connection_requested_at >= 60:
            message = "ยังเชื่อม Extension ไม่สำเร็จ • เปิด chrome://extensions ในโปรไฟล์ SmartFlow แล้วเปิดใช้งานหรือโหลดซ้ำ"
        if message:
            self._browser_connection = {"phase": "needs_attention", "message": message}
            self.extension_status.set(message)
            self._write_console(message, "warning")
            return
        self.root.after(1000, self._check_browser_connection)

    def _open_url(self, url):
        from core.chrome_profile import resolve_profile, launch_arguments
        from core.config import save_chrome_profile
        profile_args = []
        # Keep the first-install entry accessible before any Extension exists.
        if url != 'chrome://extensions':
            profile = resolve_profile(getattr(self, 'cfg', {}) or {})
            save_chrome_profile(profile)
            self.cfg.update(profile)
            profile_args = launch_arguments(profile)
        configured = str((getattr(self, "cfg", {}) or {}).get("chrome_path") or "").strip()
        candidates = [
            Path(configured) if configured else None,
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
        ]
        chrome_on_path = shutil.which("chrome") or shutil.which("chrome.exe")
        if chrome_on_path:
            candidates.append(Path(chrome_on_path))
        chrome = next((path for path in candidates if path and path.is_file()), None)
        # Chrome owns this browser-level bubble, so a content script cannot
        # reliably click it. Suppress only the crash-restore prompt at launch;
        # normal tabs, sessions, login state and the user's profile stay intact.
        if not chrome:
            raise RuntimeError(
                "ไม่พบ Google Chrome ในเครื่อง • กรุณาติดตั้ง Chrome หรือกำหนด chrome_path ในไฟล์ตั้งค่า"
            )
        try:
            subprocess.Popen([
                str(chrome),
                "--hide-crash-restore-bubble",
                "--start-maximized",
                *profile_args,
                url,
            ])
        except OSError as exc:
            raise RuntimeError(f"เปิด Google Chrome ไม่สำเร็จ: {exc}") from exc
        threading.Thread(target=self._focus_chrome_after_launch, daemon=True).start()
        return True

    @staticmethod
    def _chrome_window_available():
        """Return whether a real visible Chrome window exists right now.

        Extension heartbeats deliberately have a grace period. Without this
        live-window check, clicking Create/Continue just after Chrome closes can
        enqueue a command against a stale heartbeat and appear to do nothing.
        """
        if os.name != "nt":
            return False
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            found = []

            def collect(handle, _lparam):
                if not user32.IsWindowVisible(handle):
                    return True
                class_name = ctypes.create_unicode_buffer(128)
                user32.GetClassNameW(handle, class_name, len(class_name))
                if class_name.value != "Chrome_WidgetWin_1":
                    return True
                length = user32.GetWindowTextLengthW(handle)
                title = ctypes.create_unicode_buffer(max(2, length + 1))
                user32.GetWindowTextW(handle, title, len(title))
                if "Google Chrome" in title.value:
                    found.append(handle)
                    return False
                return True

            user32.EnumWindows(callback_type(collect), 0)
            return bool(found)
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def _activate_or_launch_chrome(self, url):
        """Focus an existing Chrome window or launch exactly one new window."""
        def connected_window():
            # Extension heartbeat can lag behind an already-open Chrome window.
            # Launching a URL during that gap adds another provider tab.
            return self._chrome_window_available()
        if connected_window():
            if hasattr(self, 'bridge') and self._compatible_extension()[1]:
                self.bridge.queue_extension_command('focus_browser')
                return 'focus_requested'
            threading.Thread(target=self._focus_chrome_after_launch, daemon=True).start()
            return "focused"
        lock = getattr(self, "_chrome_launch_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._chrome_launch_lock = lock
        with lock:
            if connected_window():
                if hasattr(self, 'bridge') and self._compatible_extension()[1]:
                    self.bridge.queue_extension_command('focus_browser')
                    return 'focus_requested'
                threading.Thread(target=self._focus_chrome_after_launch, daemon=True).start()
                return "focused"
            now = time.monotonic()
            # Product/Story workers can notice the same disconnect at nearly the
            # same time. Let the first launch finish instead of creating tabs.
            if now - float(getattr(self, "_chrome_launch_requested_at", 0.0) or 0.0) < 5:
                return "launching"
            self._chrome_launch_requested_at = now
            self._open_url(url)
            return "launched"

    @staticmethod
    def _focus_chrome_window():
        """Restore and focus a visible Chrome window without clicking page coordinates."""
        if os.name != "nt":
            return False
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            handles = []

            def collect(handle, _lparam):
                if not user32.IsWindowVisible(handle):
                    return True
                class_name = ctypes.create_unicode_buffer(128)
                user32.GetClassNameW(handle, class_name, len(class_name))
                if class_name.value != "Chrome_WidgetWin_1":
                    return True
                length = user32.GetWindowTextLengthW(handle)
                title = ctypes.create_unicode_buffer(max(2, length + 1))
                user32.GetWindowTextW(handle, title, len(title))
                if "Google Chrome" in title.value:
                    handles.append(handle)
                return True

            user32.EnumWindows(callback_type(collect), 0)
            if not handles:
                return False
            handle = handles[0]
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            current_thread = kernel32.GetCurrentThreadId()
            foreground = user32.GetForegroundWindow()
            foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
            target_thread = user32.GetWindowThreadProcessId(handle, None)
            attached_threads = []
            try:
                for thread_id in (foreground_thread, target_thread):
                    if thread_id and thread_id != current_thread and thread_id not in attached_threads:
                        if user32.AttachThreadInput(current_thread, thread_id, True):
                            attached_threads.append(thread_id)
                # Flow's responsive controls move or collapse in a narrow
                # Chrome window. Always maximize the user's existing Chrome
                # window before handing a browser job to the Extension.
                user32.ShowWindow(handle, 3)  # SW_MAXIMIZE
                user32.BringWindowToTop(handle)
                user32.SetForegroundWindow(handle)
                user32.SetFocus(handle)
                return user32.GetForegroundWindow() == handle
            finally:
                for thread_id in reversed(attached_threads):
                    user32.AttachThreadInput(current_thread, thread_id, False)
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def _focus_chrome_after_launch(self):
        # An existing Chrome process may accept the URL but leave its window
        # behind SmartFlow. Retry briefly while the new tab/window is created.
        for delay in (0.35, 0.8, 1.6):
            time.sleep(delay)
            if self._focus_chrome_window():
                return

    def _open_folder(self, path):
        Path(path).mkdir(parents=True, exist_ok=True); subprocess.Popen(["explorer", str(path)])

    def _product_imported(self, job, created):
        self.events.put(("product", f"{'นำเข้าสินค้าใหม่' if created else 'อัปเดตสินค้า'} • {job['product_name']}"))

    def _story_ai_ready(self, job):
        self.events.put(("story_ai_ready", job))

    def _desktop_product_preparations(self, stories):
        linked_source_ids = {
            str((row.get('product_story') or {}).get('product_id') or '')
            for row in stories if isinstance(row.get('product_story'), dict)
        }
        queued_source_ids = set()
        try:
            for item in self.story_queue.snapshot().get('items') or []:
                context = ((item.get('settings') or {}).get('creative_context') or {})
                if context.get('kind') == 'product_story':
                    queued_source_ids.add(str(context.get('source_product_id') or ''))
        except Exception:
            pass
        return [
            row for row in self.products.story_source_preparations()
            if row.get('id') not in linked_source_ids and row.get('id') not in queued_source_ids
        ]

    def _refresh(self):
        if hasattr(self, "queue_table"):
            for item in self.queue_table.get_children(): self.queue_table.delete(item)
            for row in self.jobs.load():
                self.queue_table.insert("", "end", values=(row["id"], Path(row["video_path"]).name, row["caption"], row["product"], row["status"], row["last_step"]))
        products = [row for row in self.products.list_jobs() if not row.get('story_source_only')]
        stories = [row for row in self.stories.list_jobs() if not row.get('cast_creation')]
        product_preparations = self._desktop_product_preparations(stories)
        if hasattr(self, "library_table"):
            self._refresh_video_library()
        if self._project_manager_dialog and self._project_manager_dialog.winfo_exists():
            self._refresh_project_manager()
        if hasattr(self, "story_job_combo"):
            story_ids = [row.get("id") for row in stories]
            self.story_job_combo.configure(values=story_ids)
            if self.story_job_id.get() not in story_ids:
                self.story_job_id.set(story_ids[0] if story_ids else "")
            if self.story_job_id.get():
                self.root.after(10, self._load_story_job)
        if hasattr(self, "voice_job_combo"):
            job_ids = [row.get("id") for row in products]
            self.voice_job_combo.configure(values=job_ids)
            if not self.voice_job_id.get() and job_ids:
                self.voice_job_id.set(job_ids[0])
        if hasattr(self, "subtitle_job_combo"):
            subtitle_job_ids = [row.get("id") for row in products if row.get("voice_status") == "ready" and row.get("voice_path")]
            self.subtitle_job_combo.configure(values=subtitle_job_ids)
            if self.subtitle_job_id.get() not in subtitle_job_ids:
                self.subtitle_job_id.set(subtitle_job_ids[0] if subtitle_job_ids else "")
                if subtitle_job_ids:
                    self.root.after(10, self._load_subtitle_job)
        if hasattr(self, "logo_job_combo"):
            video_job_ids = [row.get("id") for row in products if row.get("video_status") == "ready" and row.get("video_path")]
            self.logo_job_combo.configure(values=video_job_ids)
            if self.logo_job_id.get() not in video_job_ids:
                self.logo_job_id.set(video_job_ids[0] if video_job_ids else "")
        if hasattr(self, "audio_job_combo"):
            audio_job_ids = [row.get("id") for row in products if row.get("video_status") == "ready" and row.get("video_path")]
            self.audio_job_combo.configure(values=audio_job_ids)
            if self.audio_job_id.get() not in audio_job_ids:
                self.audio_job_id.set(audio_job_ids[0] if audio_job_ids else "")
                if audio_job_ids:
                    self.root.after(10, self._load_audio_job)
        if hasattr(self, "product_table"):
            selected_product = self.product_table.selection()
            selected_job_id = self.product_table.item(selected_product[0], "values")[0] if selected_product else ""
            for item in self.product_table.get_children(): self.product_table.delete(item)
            first_product_item = ""
            selected_product_item = ""
            for row in products:
                readiness = row.get("readiness") or {}
                ready_text = "READY" if readiness.get("ready") else "รอข้อมูล"
                ai_text = row.get("ai_status") or "—"
                if row.get("ai_review_status") == "needs_review": ai_text = "รอตรวจ"
                voice_text = "พร้อม" if row.get("voice_status") == "ready" else "ยังไม่มี"
                subtitle_text = "พร้อม" if row.get("subtitle_status") == "ready" else ("กำลังทำ" if row.get("subtitle_status") == "queued" else "ยังไม่มี")
                video_text = row.get("video_status") or "ยังไม่มี"
                if video_text in {"collecting_clips", "clips_ready"}:
                    remote_count = int(row.get("flow_remote_clip_count") or row.get("flow_clip_count") or 0)
                    local_count = int(row.get("flow_local_motion_clip_count") or 0)
                    target_count = int(row.get("flow_target_clip_count") or 3)
                    video_text = (
                        f"Flow {remote_count} + Local {local_count}/{target_count}"
                        if local_count else f"Flow {remote_count}/{target_count}"
                    )
                item_id = self.product_table.insert("", "end", values=(row.get("id"), row.get("product_name"), row.get("product_id") or "—", "พร้อม" if row.get("posting_product_url") else "ไม่มี", ai_text, voice_text, subtitle_text, video_text, ready_text, row.get("post_status")))
                if not first_product_item:
                    first_product_item = item_id
                if row.get("id") == selected_job_id:
                    selected_product_item = item_id
            focus_item = selected_product_item or first_product_item
            if focus_item:
                self.product_table.selection_set(focus_item)
                self.product_table.focus(focus_item)
                self.product_table.see(focus_item)
        self.stat_products.set(str(len(products)))
        self.stat_ai.set(str(sum(row.get("ai_status") == "ready" for row in products)))
        self.stat_videos.set(str(sum(row.get("video_status") == "ready" for row in products)))
        self.stat_posts.set(str(sum(row.get("post_status") == "posted" for row in products)))
        extension = self.bridge.extension_status()
        self._sync_extension_trace_log(extension)
        if extension.get("connected"):
            client = extension.get("client") or {}
            version = client.get("version") or "?"
            if version != self.bridge.REQUIRED_EXTENSION_VERSION:
                self.extension_status.set(f"CHROME EXTENSION • UPDATE v{version} → v{self.bridge.REQUIRED_EXTENSION_VERSION}")
            else:
                self.extension_status.set(f"CHROME EXTENSION • ONLINE v{version} • {client.get('page') or 'ready'}")
        else:
            self.extension_status.set(getattr(self, "_browser_connection", {}).get("message")
                                      if getattr(self, "_browser_connection", {}).get("phase") in {"connecting", "needs_attention"}
                                      else "CHROME EXTENSION • OFFLINE / RELOAD")

    def _sync_extension_trace_log(self, extension):
        for item in list((extension or {}).get("trace") or [])[-200:]:
            sequence = int(item.get("sequence") or 0)
            key = sequence or (
                str(item.get("at") or ""), str(item.get("job_id") or ""),
                str(item.get("action") or ""), str(item.get("message") or ""),
            )
            if key in self._extension_trace_seen:
                continue
            self._extension_trace_seen.add(key)
            if len(self._extension_trace_seen) > 1000:
                self._extension_trace_seen = set(list(self._extension_trace_seen)[-500:])
            service = str(item.get("service") or "EXTENSION").upper()
            job_id = str(item.get("job_id") or "-")
            shot = int(item.get("shot_index") or 0)
            action = str(item.get("action") or "progress")
            message = str(item.get("message") or "").strip() or "อัปเดตสถานะ"
            shot_text = f" • SHOT {shot}" if shot else ""
            level = str(item.get("level") or "info").lower()
            kind = "error" if level == "error" else "log"
            self._write_console(
                f"EXTENSION • {service} • {job_id}{shot_text} • [{action}] {message}",
                kind,
            )

    def _write_console(self, text, kind="log"):
        text = " ".join(str(text or "").split())
        if not text:
            return
        now = time.monotonic()
        if text == self._console_last_line and now - self._console_last_at < 15:
            return
        self._console_last_line = text
        self._console_last_at = now
        timestamp = time.strftime("%H:%M:%S")
        self.log_activity.set(f"{timestamp} • {text}")
        if not hasattr(self, "console"):
            return
        colors = {"error": COLORS["danger"], "success": COLORS["green"], "log": "#CFE2FF"}
        self.console.configure(state="normal")
        tag = f"tag_{kind}"; self.console.tag_configure(tag, foreground=colors.get(kind, "#CFE2FF"))
        self.console.insert("end", f"[{timestamp}]  › {text}\n", tag)
        line_count = int(self.console.index("end-1c").split(".")[0])
        if line_count > 1200:
            self.console.delete("1.0", f"{line_count - 1000}.0")
        self.console.see("end"); self.console.configure(state="disabled")

    # ------------------------------------------------------------------
    # Hybrid Desktop adapter
    # ------------------------------------------------------------------
    # The browser-facing bridge never touches Tk directly. Requests are put
    # on this queue and handled by the Tk event loop so the proven automation
    # pipeline remains the single source of truth during the UI migration.
    def _capture_product_prepare_settings(self, payload):
        options = dict(payload or {})
        options.pop('product_runtime_snapshot', None)
        # Product script validation needs the form kind before a source job
        # exists. No source ID means this cannot resolve a saved runtime yet.
        options['creative_context'] = {'kind': 'product_story', 'product_short': True}
        return self._creation_capture_settings(options)

    def _desktop_request(self, kind, payload=None, timeout=20):
        if threading.get_ident() == self._ui_thread_id:
            if kind == "state":
                return self._desktop_state_payload(str((payload or {}).get("mode") or "full"))
            if kind == "media":
                return self._desktop_media_path(payload or {})
            if kind == 'product_settings':
                return self._capture_product_prepare_settings(payload)
            return self._desktop_execute_action(str((payload or {}).get("action") or ""), (payload or {}).get("payload") or {})
        completed = threading.Event()
        result = {}
        self._desktop_requests.put((kind, payload or {}, completed, result))
        if not completed.wait(timeout):
            raise TimeoutError("หน้าจอ Hybrid รอระบบหลักนานเกินไป")
        if result.get("error"):
            raise RuntimeError(str(result["error"]))
        return result.get("value")

    def _desktop_state_request(self, mode="full"):
        return self._desktop_request("state", {"mode": str(mode or "full")}, timeout=8)

    def _desktop_action_request(self, action, payload):
        from core.membership import guard_action
        from ui.update_guard import direct_action
        guard_action(self, action)
        if action in {'shopee_post_status', 'shopee_post_library', 'shopee_post_add', 'shopee_post_edit',
                      'shopee_post_check', 'shopee_post_pause', 'shopee_post_account', 'shopee_post_start',
                      'shopee_post_defaults', 'shopee_post_apply_options', 'shopee_post_reconcile', 'shopee_post_reset_unsent', 'shopee_post_skip_unavailable'}:
            return direct_action(self, action, lambda: self.shopee_posting.action(action, payload or {}))
        if action in {'android_wifi_status', 'android_wifi_refresh', 'android_wifi_pair',
                      'android_wifi_connect', 'android_wifi_select'}:
            # Worker is independent of Tk; a slow phone cannot block the clip engine.
            return direct_action(self, action, lambda: self.android_wifi.action(action, payload))
        if action == 'product_cast_state':
            return {'ok':True,'assets':self.product_cast.state()}
        if action == 'product_cast_upload':
            return {'ok':True,'asset':self.product_cast.add(payload.get('name'),payload.get('image'))}
        if action == 'product_cast_outfit_upload':
            return {'ok':True,'asset':self.product_cast.set_outfit(payload.get('id'),payload.get('image'))}
        if action == 'product_cast_outfit_clear':
            self.product_cast.clear_outfit(payload.get('id'))
            return {'ok':True}
        if action == 'product_cast_save':
            self.product_cast.approve(str(payload.get('id') or ''))
            return {'ok':True}
        if action == 'product_cast_edit':
            self.product_cast.edit(str(payload.get('id') or ''),payload.get('name'),payload.get('hidden') is True)
            return {'ok':True}
        if action == 'product_story_prepare':
            from ui.product_jobs import prepare_product_source
            if not payload.get('product_id'):
                # Capture Tk-backed voice/render options on the UI thread before
                # Shopee navigation; never accept browser-supplied runtime config.
                payload = {**payload, 'product_runtime_snapshot': self._desktop_request(
                    'product_settings', payload, timeout=20)}
            return prepare_product_source(self, payload)
        if action in {'facebook_status','facebook_connect','facebook_disconnect','facebook_check','facebook_publish',
                      'facebook_planner_add','facebook_planner_edit','facebook_planner_start','facebook_planner_pause'}:
            return direct_action(self, action, lambda: self.facebook_post.action(action, payload or {}))
        if action in {'green_status','green_save','green_preview','green_remove'}:
            library=self.bridge.desktop_green_library
            if action=='green_status':
                return {'ok':True,**library.state()}
            if action=='green_save':
                return {'ok':True,**library.save((payload or {}).get('settings'),(payload or {}).get('targets',{}))}
            if action=='green_remove':
                return {'ok':True,**library.remove_from_library((payload or {}).get('file',''))}
            return library.preview((payload or {}).get('settings') or {})
        # Intro settings are file-backed and do not touch Tk. A browser file
        # picker/upload must never wait behind a native modal or the UI queue.
        if action in {'intro_status', 'intro_save'}:
            from ui.video_intro import intro_action
            return intro_action(self, action, payload or {})
        if action == 'intro_choose_file':
            raise ValueError('กรุณารีเฟรชหน้าอินโทร แล้วเลือกไฟล์จากบราวเซอร์')
        dialog_actions = {
            "choose_story_image", "choose_drama_image", "choose_drama_footage", "product_add_images", "product_add_video",
            "voice_choose_reference", "subtitle_upload_font", "audio_add_asset",
            "logo_choose_file", "queue_add_video", "queue_add_folder",
        }
        wait = 180 if action in dialog_actions else 20
        return self._desktop_request("action", {"action": action, "payload": payload or {}}, timeout=wait)

    def _desktop_media_request(self, item_id, kind="preview"):
        return self._desktop_request("media", {"item_id": item_id, "kind": kind}, timeout=8)

    def _poll_desktop_requests(self):
        for _ in range(30):
            try:
                kind, payload, completed, result = self._desktop_requests.get_nowait()
            except queue.Empty:
                break
            try:
                if kind == "state":
                    result["value"] = self._desktop_state_payload(str(payload.get("mode") or "full"))
                elif kind == 'product_settings':
                    result['value'] = self._capture_product_prepare_settings(payload)
                elif kind == "media":
                    result["value"] = self._desktop_media_path(payload)
                else:
                    result["value"] = self._desktop_execute_action(str(payload.get("action") or ""), payload.get("payload") or {})
            except Exception as exc:
                result["error"] = str(exc)
            finally:
                completed.set()

    def _desktop_product_row(self, job):
        readiness = job.get("readiness") or {}
        flow_count = int(job.get("flow_remote_clip_count") or job.get("flow_clip_count") or 0)
        local_motion_count = int(job.get("flow_local_motion_clip_count") or 0)
        meta_count = int(job.get("meta_clip_count") or len(dict(job.get("meta_clips") or {})))
        selected_video_provider = str(job.get("video_ai_provider") or "flow")
        segment_count = int(job.get("video_segment_count") or (
            meta_count if selected_video_provider == "meta_ai" else flow_count + local_motion_count
        ))
        target_count = int(job.get("flow_target_clip_count") or 3)
        video_status = str(job.get("video_status") or "missing")
        if video_status in {"collecting_clips", "clips_ready"}:
            if selected_video_provider == "meta_ai":
                video_status = f"Meta AI {meta_count}/{target_count}"
            else:
                video_status = (f"Flow {flow_count} + Local {local_motion_count}/{target_count}"
                    if local_motion_count else f"Flow {flow_count}/{target_count}")
        generated = list(job.get("generated_images") or [])
        source = list(job.get("source_images") or [])
        preview_url = f"/api/desktop/media?item_id=product%3A{job.get('id')}&kind=preview" if (generated or source) else ""
        return {
            "status": str(job.get("status") or ""),
            "created_at": str(job.get("created_at") or ""),
            "id": str(job.get("id") or ""),
            "title": str(job.get("product_name") or job.get("id") or "สินค้า Shopee"),
            "product_id": str(job.get("product_id") or ""),
            "link": str(job.get("posting_product_url") or job.get("product_url") or ""),
            "provider": str(job.get("image_ai_provider") or "chatgpt"),
            "ai_status": str(job.get("ai_status") or "—"),
            "voice_status": str(job.get("voice_status") or "missing"),
            "subtitle_status": str(job.get("subtitle_status") or "missing"),
            "video_status": video_status,
            "flow_count": flow_count,
            "flow_remote_count": flow_count,
            "local_motion_count": local_motion_count,
            "meta_clip_count": meta_count,
            "video_ai_provider": selected_video_provider,
            "segment_count": segment_count,
            "segment_target_count": target_count,
            "video_source_type": str(job.get("video_source_type") or ""),
            "segment_provenance": dict(job.get("flow_segment_provenance") or {}),
            "ready": bool(readiness.get("ready")),
            "post_status": str(job.get("post_status") or "pending"),
            "updated_at": str(job.get("updated_at") or job.get("created_at") or ""),
            "automation_status": str(job.get("automation_status") or ""),
            "runtime_recovery_count": int(job.get("runtime_recovery_count") or 0),
            "automation_failure_total": int(job.get("automation_failure_total") or 0),
            "last_runtime_recovery_reason": str(job.get("last_runtime_recovery_reason") or ""),
            "last_error": str(job.get("last_error") or job.get("automation_error") or ""),
            "price": str(job.get("price") or ""),
            "commission": str(job.get("commission") or ""),
            "description": str(job.get("description") or ""),
            "caption": str(job.get("caption") or ""),
            "spoken_script": str(job.get("spoken_script") or ""),
            "ai_review_status": str(job.get("ai_review_status") or "pending"),
            "generated_from_source_images": bool(job.get("generated_from_source_images")),
            "warnings": [str(value) for value in (job.get("warnings") or [])],
            "source_image_count": len(source),
            "reference_image_count": len(job.get("ai_reference_images", source)),
            "excluded_reference_count": sum(1 for item in (job.get("source_image_selection") or []) if item.get("decision") == "exclude"),
            "reused_image_count": int(job.get("reused_image_count") or 0),
            "generated_image_count": len(generated),
            "preview_url": preview_url,
        }

    @staticmethod
    def _desktop_story_row(job, folder=None):
        from core.story_recovery_summary import story_recovery_summary

        brief = job.get('creative_brief')
        public_brief = ({'title': str(brief.get('title') or '')[:100],
            'description': str(brief.get('description') or '')[:600]} if isinstance(brief, dict) else None)
        images = max(len(job.get("generated_images") or []), len(job.get("partial_generated_images") or []))
        flow_count = int(job.get("flow_clip_count") or 0)
        fallback_count = int(job.get("flow_fallback_count") or len(job.get("flow_fallback_clips") or {}))
        scene_source_count = int(job.get("flow_scene_count") or (flow_count + fallback_count))
        target_count = int(job.get("scene_count") or 0)
        video_mode = str(job.get("video_generation_mode") or "image_motion")
        video_status = str(job.get("video_status") or "missing")
        video_plan_summary = None
        if folder is not None:
            from core.scene_video_plan import enabled as planned_video, summary
            if planned_video(job):
                video_plan_summary = summary(folder, job)['counts']
                scene_source_count = video_plan_summary['completed']
        if video_mode == "google_flow" and video_status in {"images_ready", "collecting_clips", "clips_ready"}:
            video_status = (
                f"Flow {flow_count} + Local {fallback_count}/{target_count}"
                if fallback_count else f"Flow {flow_count}/{target_count}"
            )
        if video_plan_summary is not None and video_status not in {'ready', 'complete', 'completed', 'waiting_cover'}:
            video_status = (f"Flow {video_plan_summary['flow']} + Meta {video_plan_summary['meta']}"
                            f" • เก็บแล้ว {video_plan_summary['completed']}/{target_count} ฉาก")
        return {
            **({'recovery': story_recovery_summary(job, folder)} if folder is not None else {}),
            **({'video_plan_summary': video_plan_summary} if video_plan_summary is not None else {}),
            "meta_clip_count": int(job.get('meta_clip_count') or 0),
            "meta_scene_sequence_version": int(job.get('meta_scene_sequence_version') or 0),
            "content_kind": "product" if job.get("product_story") else "story",
            "long_video": bool(job.get("long_video")),
            "created_at": str(job.get("created_at") or ""),
            "preview_url": f"/api/desktop/media?item_id=story%3A{job.get('id')}&kind=preview" if images else "",
            "id": str(job.get("id") or ""),
            "job_type": str(job.get("job_type") or "story_short"),
            "series_id": str(job.get("series_id") or ""),
            "series_title": str(job.get("series_title") or ""),
            "episode_no": int(job.get("episode_no") or 0),
            "title": str(job.get("video_title") or job.get("topic") or job.get("id") or "Story Shorts"),
            "topic": str(job.get("topic") or ""),
            **({'creative_brief': public_brief} if public_brief else {}),
            "description": str(job.get("video_description") or ""),
            "provider": str(job.get("image_ai_provider") or "chatgpt"),
            "status": str(job.get("status") or ""),
            "pipeline_stage": str(job.get("pipeline_stage") or ""),
            "cancel_reason": str(job.get("cancel_reason") or ""),
            "scene_count": int(job.get("scene_count") or 0),
            "image_count": images,
            "voice_status": str(job.get("voice_status") or "missing"),
            "voice_review_issues": list(job.get("voice_review_issues") or []),
            "visual_style": str(job.get("visual_style") or "auto"),
            "video_status": video_status,
            "video_generation_mode": video_mode,
            "flow_clip_count": flow_count,
            "flow_remote_count": flow_count,
            "flow_fallback_count": fallback_count,
            "flow_scene_count": scene_source_count,
            "flow_target_count": target_count,
            "video_source_type": str(job.get("video_source_type") or ""),
            "flow_fallback_metadata": dict(job.get("flow_fallback_metadata") or {}),
            "updated_at": str(job.get("updated_at") or job.get("created_at") or ""),
            "last_error": str(job.get("last_error") or ""),
        }

    def _desktop_library_rows(self):
        rows = []
        # All lightweight summaries are searchable; full captions are read on click only.
        for item in self.video_library.list_items():
            detail = dict(item)
            detail.pop("flow_segment_provenance", None)
            item_id = str(detail.get("item_id") or "")
            detail["preview_url"] = f"/api/desktop/media?item_id={item_id.replace(':', '%3A')}&kind=preview" if detail.get("preview_path") else ""
            detail["cover_url"] = f"/api/desktop/media?item_id={item_id.replace(':', '%3A')}&kind=cover" if detail.get("cover_path") else ""
            if detail["cover_url"] and detail.get("cover_revision"):
                detail["cover_url"] += "&v=" + re.sub(r"[^a-zA-Z0-9]", "", str(detail["cover_revision"]))[:64]
            detail["video_url"] = f"/api/desktop/media?item_id={item_id.replace(':', '%3A')}&kind=video" if detail.get("path") else ""
            detail["thumbnail_url"] = f"/api/desktop/media?item_id={item_id.replace(':', '%3A')}&kind=thumbnail&v={detail.get('cover_revision') or detail.get('updated_at') or ''}" if detail.get("cover_path") or detail.get("preview_path") else ""
            rows.append(detail)
        return rows

    def _desktop_log_lines(self):
        live_lines = []
        if hasattr(self, "console"):
            try:
                live_lines = self.console.get("1.0", "end-1c").splitlines()[-140:]
            except tk.TclError:
                live_lines = []
        try:
            files = sorted((ROOT / "logs").glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
            file_lines = files[0].read_text(encoding="utf-8", errors="replace").splitlines()[-120:] if files else []
        except OSError:
            file_lines = []
        trace_lines = []
        try:
            for item in list(self.bridge.extension_status().get("trace") or [])[-100:]:
                service = str(item.get("service") or "EXTENSION").upper()
                job_id = str(item.get("job_id") or "-")
                shot = int(item.get("shot_index") or 0)
                action = str(item.get("action") or "progress")
                message = " ".join(str(item.get("message") or "").split())
                shot_text = f" • SHOT {shot}" if shot else ""
                trace_lines.append(
                    f"[{str(item.get('at') or '')}] EXTENSION • {service} • {job_id}{shot_text} • [{action}] {message}"
                )
        except Exception:
            trace_lines = []
        combined = []
        for line in [*file_lines, *live_lines, *trace_lines]:
            if line and (not combined or combined[-1] != line):
                combined.append(line)
        return combined[-220:]

    def _desktop_compact_state_payload(self):
        """Return only live fields used by the progress/status heartbeat.

        Product, Story, Drama and Library rows are intentionally excluded.
        Those collections can exceed half a megabyte and do not need to be
        rebuilt every second while FFmpeg or Chrome automation is running.
        """
        extension = self.bridge.extension_status()
        client = extension.get("client") or {}
        extension_version = str(client.get("version") or "")
        try:
            subtitle_connected = bool(self._subtitle_store().load())
        except Exception:
            subtitle_connected = False
        voice_configured = bool(self.voice_api_key.get().strip())
        reference_configured = bool(self.voice_reference_id.get().strip() or Path(self.voice_reference_file.get().strip()).is_file())
        product_job = str(self._product_pipeline_job_id or "")
        story_job = str(self._story_pipeline_job_id or "")
        active_story = {}
        if story_job:
            try:
                active_story = self.stories.get(story_job)
            except (OSError, ValueError):
                active_story = {}
        return {
            "partial": True,
            "product_job_delete_version": 1,
            "automation_observations": public_observations(extension),
            "creation_queue": self._creation_queue_state(),
            "app": {
                "name": "SmartFlow AI",
                "mode": "hybrid",
                "extension_required": self.bridge.REQUIRED_EXTENSION_VERSION,
                "legacy_visible": bool(self.root.state() != "withdrawn"),
            },
            "system": {
                "long_meta_landscape_available": meta_landscape_available(),
                "status": self.status.get(),
                "activity": self.log_activity.get(),
                "bridge_online": bool(self.bridge.server),
                "bridge_port": int(self.cfg.get("bridge_port", 8765)),
                "extension_online": bool(extension.get("connected")),
                "extension_authorized": bool(extension.get("connected") and extension_version == self.bridge.REQUIRED_EXTENSION_VERSION),
                "extension_membership_required": False,
                "extension_compatible": bool(extension.get("connected") and extension_version == self.bridge.REQUIRED_EXTENSION_VERSION),
                "extension_version": extension_version,
                "extension_page": str(client.get("page") or ""),
                "browser_connection": dict(getattr(self, "_browser_connection", {})),
                "android": self.device.get(),
                "android_badge": self.device_badge.get(),
                "android_wifi": self.android_wifi.state(),
                "voice_configured": voice_configured,
                "voice_reference_configured": reference_configured,
                "subtitle_connected": subtitle_connected,
                "safe_mode": bool(self.dry.get() or self.confirm.get()),
            },
            "credits": {
                "voice": dict(self._service_credit_state.get("voice") or self._credit_state()),
                "subtitle": dict(self._service_credit_state.get("subtitle") or self._credit_state()),
                "refreshing": bool(self._service_credit_refreshing),
            },
            "presenter_progress": self._presenter_status(),
            "product_progress": {
                "active": bool(product_job),
                "job_id": product_job or self._product_progress_job.get(),
                "percent": int(round(float(self._product_progress_value.get()))),
                "message": self._product_progress_message.get(),
                "detail": self._product_progress_detail.get(),
                "action_required": bool(product_job and self._product_verification_job == product_job),
                "action_kind": str(self._product_web_action.get("action_kind") or ""),
                "action_service": str(self._product_web_action.get("service") or ""),
                "action_button": str(self._product_web_action.get("button_label") or ""),
            },
            "story_progress": {
                "active": bool(story_job),
                "job_id": story_job or self._story_progress_job.get(),
                "mode": str(active_story.get("job_type") or "story_short"),
                "series_id": str(active_story.get("series_id") or ""),
                "episode_no": int(active_story.get("episode_no") or 0),
                "episode_count": int(active_story.get("episode_count") or 0),
                "percent": int(round(float(self._story_progress_value.get()))),
                "message": self._story_progress_message.get(),
                "detail": self._story_progress_detail.get(),
                "action_required": bool(story_job and self._story_verification_jobs.get(story_job) == "waiting"),
                "action_kind": str((self._story_web_actions.get(story_job) or {}).get("action_kind") or ""),
                "action_service": str((self._story_web_actions.get(story_job) or {}).get("service") or ""),
                "action_button": str((self._story_web_actions.get(story_job) or {}).get("button_label") or ""),
                **self._desktop_scene_progress(active_story,bool(story_job)),
            },
            "notice": dict(self._desktop_notice),
            "automation_error_log": dict(self._automation_error_log),
        }

    def _desktop_scene_progress(self, job, active):
        from core.scene_progress_view import scene_progress_view
        if not job or not job.get('id'):return {}
        view = scene_progress_view(job,self.stories.root/job['id'],active,self._story_progress_value.get())
        owner, rank = getattr(self, '_story_phase_owner', (None, 0))
        current_owner = (getattr(self, '_story_pipeline_job_id', ''), getattr(self, '_story_cancel_event', None))
        if (active and job.get('scene_pipeline_version') != 1 and owner == current_owner
                and current_owner[0] == job['id'] and current_owner[1] is not None
                and not current_owner[1].is_set() and rank in range(1, 6)):
            view.update(pipeline_phase=['', 'source_video', 'voice', 'compose', 'finish', 'cover'][rank],
                        audio_mode=audio_mode(job), source_video_required=job.get('video_generation_mode') in {'google_flow', 'meta_ai'})
        return view

    def _desktop_subtitle_preview_payload(self):
        service = getattr(self, "_subtitle_preview_service", None)
        state = service.snapshot() if service else {
            "preview_token": 0, "preview_ready_token": 0, "preview_busy": False,
            "preview_error": "", "preview_url": "", "preview_video_url": "",
        }
        # Only small style values; never enumerate Products, Stories or Library.
        state["style"] = {
            "font": self.subtitle_font_label.get(), "font_size": self.subtitle_font_size.get(),
            "thai_mark_gap": self.subtitle_thai_mark_gap.get(), "outline_width": self.subtitle_outline_width.get(),
            "position_y": self.subtitle_position_y.get(), "text_color": self.subtitle_text_color.get(),
            "highlight_color": self.subtitle_highlight_color.get(), "outline_color": self.subtitle_outline_color.get(),
            "background_enabled": bool(self.subtitle_background_enabled.get()),
            "background_color": self.subtitle_background_color.get(), "background_opacity": self.subtitle_background_opacity.get(),
        }
        return state

    def _desktop_state_payload(self, mode="full"):
        if mode == "logs":
            state = self._desktop_compact_state_payload()
            state["logs"] = self._desktop_log_lines()
            return state
        if mode == "subtitle_preview":
            return {"subtitle_preview": self._desktop_subtitle_preview_payload()}
        if str(mode or "full").strip().lower() == "compact":
            return self._desktop_compact_state_payload()
        products = [row for row in self.products.list_jobs() if not row.get('story_source_only')]
        stories = [row for row in self.stories.list_jobs() if not row.get('cast_creation')]
        product_preparations = self._desktop_product_preparations(stories)
        library = self._desktop_library_rows()
        extension = self.bridge.extension_status()
        client = extension.get("client") or {}
        extension_version = str(client.get("version") or "")
        try:
            subtitle_connected = bool(self._subtitle_store().load())
        except Exception:
            subtitle_connected = False
        voice_configured = bool(self.voice_api_key.get().strip())
        reference_configured = bool(self.voice_reference_id.get().strip() or Path(self.voice_reference_file.get().strip()).is_file())
        product_job = str(self._product_pipeline_job_id or "")
        story_job = str(self._story_pipeline_job_id or "")
        active_story = next((row for row in stories if str(row.get("id") or "") == story_job), {})
        queue_rows = []
        try:
            for row in self.jobs.load():
                queue_rows.append({key: str(row.get(key) or "") for key in ("id", "video_path", "caption", "product", "status", "last_step", "error")})
        except Exception:
            queue_rows = []
        preview_name = f"subtitle_preview_hybrid_{os.getpid()}_{self._subtitle_preview_token}.png" if self.hybrid_engine else f"subtitle_preview_{self._subtitle_preview_token}.png"
        preview_path = ROOT / "workspace" / "preview" / preview_name
        preview_video_path = preview_path.with_suffix(".mp4")
        voice_catalog = []
        for label, voice in self._voice_catalog_by_label.items():
            voice_catalog.append({
                "label": str(label),
                "reference_id": str(voice.get("reference_id") or ""),
                "name": str(voice.get("name") or ""),
                "source": str(voice.get("source") or "preset"),
                "description": str(voice.get("description") or voice.get("note") or ""),
                "allowed_emotions": [str(value) for value in (voice.get("allowed_emotions") or ["normal"])],
            })
        logo_library = self._logo_library_payload()
        selected_logo = next((item for item in logo_library if item.get("selected")), {})
        logo_preview = ROOT / "workspace" / "preview" / "logo_preview.png"
        selected_logo_url = f"/api/desktop/media?item_id=logo%3A{selected_logo.get('id')}&kind=preview" if selected_logo.get("id") else "/api/desktop/media?item_id=__brand_full__&kind=preview"
        preview_url = "/api/desktop/media?item_id=__logo_preview__&kind=preview" if logo_preview.is_file() and self._logo_preview_asset_id == str(selected_logo.get("id") or "") else selected_logo_url
        return {
            "story_visual_styles": [{k: v for k, v in item.items() if k != "prompt"} for item in STORY_VISUAL_STYLES],
            "automation_observations": public_observations(extension),
            "app": {
                "name": "SmartFlow AI",
                "mode": "hybrid",
                "extension_required": self.bridge.REQUIRED_EXTENSION_VERSION,
                "legacy_visible": bool(self.root.state() != "withdrawn"),
            },
            "system": {
                "status": self.status.get(),
                "activity": self.log_activity.get(),
                "bridge_online": bool(self.bridge.server),
                "bridge_port": int(self.cfg.get("bridge_port", 8765)),
                "extension_online": bool(extension.get("connected")),
                "extension_authorized": bool(extension.get("connected") and extension_version == self.bridge.REQUIRED_EXTENSION_VERSION),
                "extension_membership_required": False,
                "extension_compatible": bool(extension.get("connected") and extension_version == self.bridge.REQUIRED_EXTENSION_VERSION),
                "extension_version": extension_version,
                "extension_page": str(client.get("page") or ""),
                "browser_connection": dict(getattr(self, "_browser_connection", {})),
                "android": self.device.get(),
                "android_badge": self.device_badge.get(),
                "android_wifi": self.android_wifi.state(),
                "voice_configured": voice_configured,
                "voice_reference_configured": reference_configured,
                "subtitle_connected": subtitle_connected,
                "safe_mode": bool(self.dry.get() or self.confirm.get()),
            },
            "stats": {
                "products": len(products),
                "ai_ready": sum(str(row.get("ai_status")) == "ready" for row in products),
                "videos": len(library),
                "posted": sum(str(row.get("post_status")) == "posted" for row in products),
                "stories": len(stories),
            },
            "credits": {
                "voice": dict(self._service_credit_state.get("voice") or self._credit_state()),
                "subtitle": dict(self._service_credit_state.get("subtitle") or self._credit_state()),
                "refreshing": bool(self._service_credit_refreshing),
            },
            "products": [self._desktop_product_row(row) for row in products],
            "workspace_issues": scan_workspace_issues(ROOT),
            "product_preparations": product_preparations,
            "product_job_controls": self.story_queue.product_job_controls(),
            "product_job_delete_version": 1,
            "stories": [self._desktop_story_row(row, self.stories.root / row['id']) for row in stories],
            "drama_series": self.drama_series.snapshot(),
            "library": library,
            "presenter_progress": self._presenter_status(),
            "product_progress": {
                "active": bool(product_job),
                "job_id": product_job or self._product_progress_job.get(),
                "percent": int(round(float(self._product_progress_value.get()))),
                "message": self._product_progress_message.get(),
                "detail": self._product_progress_detail.get(),
                "action_required": bool(product_job and self._product_verification_job == product_job),
                "action_kind": str(self._product_web_action.get("action_kind") or ""),
                "action_service": str(self._product_web_action.get("service") or ""),
                "action_button": str(self._product_web_action.get("button_label") or ""),
            },
            "story_progress": {
                "active": bool(story_job),
                "job_id": story_job or self._story_progress_job.get(),
                "mode": str(active_story.get("job_type") or "story_short"),
                "series_id": str(active_story.get("series_id") or ""),
                "episode_no": int(active_story.get("episode_no") or 0),
                "episode_count": int(active_story.get("episode_count") or 0),
                "percent": int(round(float(self._story_progress_value.get()))),
                "message": self._story_progress_message.get(),
                "detail": self._story_progress_detail.get(),
                "action_required": bool(story_job and self._story_verification_jobs.get(story_job) == "waiting"),
                "action_kind": str((self._story_web_actions.get(story_job) or {}).get("action_kind") or ""),
                "action_service": str((self._story_web_actions.get(story_job) or {}).get("service") or ""),
                "action_button": str((self._story_web_actions.get(story_job) or {}).get("button_label") or ""),
                **self._desktop_scene_progress(active_story,bool(story_job)),
            },
            "story_queue": self.story_queue.snapshot(),
            "creation_queue": self._creation_queue_state(),
            "creative_catalog": __import__('core.creative_brief', fromlist=['public_catalog']).public_catalog(),
            "settings": {
                "provider": self._image_provider_key(),
                "chatgpt_web_model": self._ai_web_model_key("chatgpt"),
                "gemini_web_model": self._ai_web_model_key("gemini"),
                "ai_web_model_options": {
                    provider: [{"value": key, "label": label} for key, label in options.items()]
                    for provider, options in AI_WEB_MODEL_OPTIONS.items()
                },
                "video_provider": self._video_provider_key(),
                "subtitle_auto": bool(self.subtitle_auto.get()),
                "video_resolution": VIDEO_RESOLUTIONS.get(self.video_resolution.get(), "720x1280"),
                "video_fps": int(self.video_fps.get() or 30),
                'video_encoder': self.video_encoder.get(),
                "video_quality": VIDEO_QUALITIES.get(self.video_quality.get(), "high"),
                "motion_percent": int(self.video_motion_strength.get()),
                "transition_ms": int(self.video_transition_ms.get()),
                "extension_path": str((ROOT / "browser_extension").resolve()),
            },
            "voice": {
                "job_id": self.voice_job_id.get(),
                "status": self.voice_status.get(),
                "key_saved": bool(self.voice_api_key.get().strip()),
                "key_state": self.voice_key_saved.get(),
                "reference_file": self.voice_reference_file.get(),
                "reference_id": self.voice_reference_id.get(),
                "language": self.voice_language.get(),
                "emotion": CLIP_VOICE_EMOTION,
                "speed": str(CLIP_VOICE_SPEED),
                "silence": self.voice_silence.get(),
                "format": self.voice_format.get(),
                "catalog_choice": self.voice_catalog_choice.get(),
                "catalog_info": self.voice_catalog_info.get(),
                "catalog": voice_catalog,
                "script": self.voice_script.get("1.0", "end").strip() if hasattr(self, "voice_script") else "",
            },
            "subtitle": {
                "job_id": self.subtitle_job_id.get(),
                "status": self.subtitle_status.get(),
                "credential_saved": bool(subtitle_connected),
                "credential_state": self.subtitle_credential_saved.get(),
                "audio_label": self.subtitle_audio_label.get(),
                "language": self.subtitle_language.get(),
                "syllables": int(self.subtitle_syllables.get() or 3),
                "auto": bool(self.subtitle_auto.get()),
                "theme": self.subtitle_theme.get(),
                "themes": [str(value.get("label") or key) for key, value in SUBTITLE_THEMES.items()],
                "theme_random": bool(self.subtitle_theme_random.get()),
                "animation": self.subtitle_animation.get(),
                "animations": list(SUBTITLE_ANIMATIONS.values()),
                "animation_random": bool(self.subtitle_animation_random.get()),
                "font": self.subtitle_font_label.get(),
                "fonts": [record.label for record in self._subtitle_font_records],
                "font_size": int(self.subtitle_font_size.get()),
                "thai_mark_gap": int(self.subtitle_thai_mark_gap.get()),
                "outline_width": int(self.subtitle_outline_width.get()),
                "position": self.subtitle_position.get(),
                "position_y": int(self.subtitle_position_y.get()),
                "text_color": self.subtitle_text_color.get(),
                "highlight_color": self.subtitle_highlight_color.get(),
                "outline_color": self.subtitle_outline_color.get(),
                "background_enabled": bool(self.subtitle_background_enabled.get()),
                "background_color": self.subtitle_background_color.get(),
                "background_opacity": int(self.subtitle_background_opacity.get()),
                "preview_url": "/api/desktop/media?item_id=__subtitle_preview__&kind=preview" if preview_path.is_file() else "",
                "preview_video_url": "/api/desktop/media?item_id=__subtitle_preview__&kind=video" if preview_video_path.is_file() else "",
                "preview_token": int(self._subtitle_preview_token),
                "preview_busy": bool(self._subtitle_preview_busy),
                "preview_status": self.subtitle_preview_meta.get(),
                "preview_error": str(self._subtitle_preview_error_message or ""),
                **(self._desktop_subtitle_preview_payload() if self.hybrid_engine else {}),
            },
            "audio": {
                "job_id": self.audio_job_id.get(),
                "status": self.audio_status.get(),
                "background_enabled": bool(self.audio_background_enabled.get()),
                "background_mode": self.audio_background_mode.get(),
                "background_file": self.audio_background_file.get(),
                "background_selection": self.cfg.get("audio_background_selection"),
                "background_track_count": self.cfg.get("audio_background_track_count"),
                "background_volume": int(self.audio_background_volume.get()),
                "segment_max_sec": float(self.audio_background_segment_max.get()),
                "duck_percent": int(self.audio_background_duck_percent.get()),
                "background_files": ["สุ่มจากคลัง"] + [path.name for path in self._audio_assets("background")],
                "sfx_enabled": bool(self.audio_sfx_enabled.get()),
                "sfx_mode": self.audio_sfx_mode.get(),
                "sfx_file": self.audio_sfx_file.get(),
                "sfx_volume": int(self.audio_sfx_volume.get()),
                "sfx_interval": int(self.audio_sfx_min_interval.get()),
                "sfx_count": int(self.audio_sfx_max_count.get()),
                "sfx_files": ["สุ่มจากคลัง"] + [path.name for path in self._audio_assets("sfx")],
            },
            "logo": {
                "job_id": self.logo_job_id.get(),
                "status": self.logo_status.get(),
                "file": self.logo_file.get(),
                "opacity": int(round(float(self.logo_opacity.get()))),
                "size": int(round(float(self.logo_size.get()))),
                "position": self.logo_position.get(),
                "positions": list(POSITIONS.values()),
                "margin": int(self.logo_margin.get()),
                "library": logo_library,
                "selected_asset_id": str(selected_logo.get("id") or ""),
                "selected_name": str(selected_logo.get("name") or ""),
                "preview_url": preview_url,
                "preview_token": int(self._logo_preview_token),
                "layout": copy.deepcopy(getattr(self, 'logo_layout', None)),
                "asset_url": selected_logo_url,
                "editor_preview": dict(getattr(self, '_logo_editor_preview', {})),
            },
            "queue": {
                "items": queue_rows,
                "dry_run": bool(self.dry.get()),
                "confirm": bool(self.confirm.get()),
            },
            "workspace_cleanup": self._workspace_cleanup_payload(),
            "logs": self._desktop_log_lines(),
            "notice": dict(self._desktop_notice),
            "automation_error_log": dict(self._automation_error_log),
        }

    def _desktop_media_path(self, payload):
        item_id = str(payload.get("item_id") or "")
        if item_id.startswith("presenter:"):
            return self._presenter_media(item_id)
        if item_id.startswith("product-ref:"):
            _, job_id, index = item_id.split(":", 2)
            return product_image_asset(self.products, job_id, index)
        if item_id.startswith("story-scene:"):
            parts = item_id.split(":")
            if len(parts) != 4:
                raise ValueError("รหัสไฟล์ฉากไม่ถูกต้อง")
            _, job_id, index, kind = parts
            job = self.stories.get(job_id)
            target = scene_asset(self.stories._folder(job_id), job, int(index), kind)
            if not target:
                raise FileNotFoundError("ฉากนี้ยังไม่มีไฟล์ที่พร้อมเปิด")
            return str(target)
        if item_id == "__brand__":
            target = ROOT / "assets" / "smartflow_icon.png"
            if not target.is_file():
                raise FileNotFoundError("ไม่พบโลโก้ SmartFlow")
            return str(target.resolve())
        if item_id == "__brand_full__":
            target = ROOT / "assets" / "smartflow_logo.png"
            if not target.is_file():
                raise FileNotFoundError("ไม่พบโลโก้ SmartFlow ต้นฉบับ")
            return str(target.resolve())
        if str(item_id).startswith("__subtitle_preview__:"):
            service = getattr(self, "_subtitle_preview_service", None)
            if not service:
                raise FileNotFoundError("ยังไม่มีพรีวิว Subtitle")
            return str(service.media(item_id, str(payload.get("kind") or "preview")))
        if item_id == "__subtitle_preview__":
            preview_name = f"subtitle_preview_hybrid_{os.getpid()}_{self._subtitle_preview_token}.png" if self.hybrid_engine else f"subtitle_preview_{self._subtitle_preview_token}.png"
            target = ROOT / "workspace" / "preview" / preview_name
            if str(payload.get("kind") or "preview") == "video":
                target = target.with_suffix(".mp4")
            if not target.is_file():
                raise FileNotFoundError("ยังไม่มีพรีวิว Subtitle")
            return str(target.resolve())
        if item_id == "__logo_preview__":
            target = ROOT / "workspace" / "preview" / "logo_preview.png"
            if not target.is_file():
                raise FileNotFoundError("ยังไม่มีพรีวิวโลโก้")
            return str(target.resolve())
        if item_id.startswith(('__logo_editor_frame__:', '__logo_editor_result__:')):
            kind, request = item_id.split(':', 1)
            preview = getattr(self, '_logo_editor_preview', {})
            files = getattr(self, '_logo_editor_files', ())
            if request != preview.get('request') or len(files) != 2:
                raise FileNotFoundError('พรีวิวนี้มีตำแหน่งใหม่แล้ว')
            return str(files[0 if kind == '__logo_editor_frame__' else 1].resolve())
        if item_id.startswith("logo:"):
            target = self._resolve_logo_asset(item_id.split(":", 1)[1])
            if not target:
                raise FileNotFoundError("ไม่พบโลโก้ในคลัง")
            return str(target.resolve())
        # Product rows use the same item id for their thumbnail, cover, and
        # playable Final.  Only the preview request should be resolved from
        # generated/source images.  Previously this unconditional branch also
        # answered kind=video with a PNG, so WebView showed the poster at 0:00
        # and could never start playback.
        media_kind = str(payload.get("kind") or "preview")
        if media_kind == "thumbnail":
            return self.video_library.thumbnail(item_id)
        if item_id.startswith("product:") and media_kind == "preview":
            job_id = item_id.split(":", 1)[1]
            job = self.products.get_job(job_id)
            values = list(job.get("generated_images") or []) + list(job.get("source_images") or [])
            if not values:
                raise FileNotFoundError("Job นี้ยังไม่มีรูปสินค้า")
            root = (self.products.root / job_id).resolve()
            target = (root / str(values[0])).resolve()
            if root not in target.parents or not target.is_file():
                raise FileNotFoundError("ไม่พบรูปสินค้า")
            return str(target)
        detail = self.video_library.item_detail(item_id)
        key = "path" if media_kind == "video" else "cover_path" if media_kind == "cover" else "preview_path"
        target = Path(str(detail.get(key) or ""))
        if not target.is_file():
            raise FileNotFoundError("ไม่พบไฟล์ผลงาน")
        return str(target.resolve())

    def _save_desktop_reference_image(self, payload):
        """Persist an image selected by the Hybrid UI without opening hidden Tk dialogs."""
        encoded = str(payload.get("data_url") or "")
        if not encoded.startswith("data:image/") or "," not in encoded:
            raise ValueError("ข้อมูลรูปอ้างอิงไม่ถูกต้อง")
        try:
            raw = base64.b64decode(encoded.split(",", 1)[1], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("อ่านข้อมูลรูปอ้างอิงไม่สำเร็จ") from exc
        if not raw or len(raw) > 12 * 1024 * 1024:
            raise ValueError("รูปอ้างอิงต้องมีขนาดไม่เกิน 12 MB")
        try:
            with Image.open(BytesIO(raw)) as opened:
                image_format = str(opened.format or "").upper()
                width, height = opened.size
                opened.verify()
        except (OSError, ValueError) as exc:
            raise ValueError("ไฟล์ที่เลือกไม่ใช่รูป PNG, JPG หรือ WEBP ที่สมบูรณ์") from exc
        extensions = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
        extension = extensions.get(image_format)
        if not extension or width < 64 or height < 64:
            raise ValueError("รูปอ้างอิงต้องเป็น PNG, JPG หรือ WEBP และมีขนาดอย่างน้อย 64 × 64")
        requested_purpose = str(payload.get("purpose") or "")
        purpose = requested_purpose if requested_purpose in {"story", "presenter"} else "drama"
        folder = ROOT / "workspace" / "imports" / "reference_images"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{purpose}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}{extension}"
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(raw)
        os.replace(temporary, target)
        if purpose == "story":
            self.story_main_image.set(str(target))
        return {
            "ok": True,
            "path": str(target.resolve()),
            "asset_id": target.name,
            "name": str(payload.get("filename") or target.name),
            "width": width,
            "height": height,
        }

    @staticmethod
    def _resolve_desktop_reference_image(value):
        value = str(value or "").strip()
        if not value.startswith("asset:"):
            return value
        asset_id = value.split(":", 1)[1]
        if not asset_id or any(token in asset_id for token in ("/", "\\", "..")):
            raise ValueError("รหัสรูปอ้างอิงไม่ถูกต้อง")
        root = (ROOT / "workspace" / "imports" / "reference_images").resolve()
        target = (root / asset_id).resolve()
        if target.parent != root or not target.is_file():
            raise ValueError("ไม่พบรูปอ้างอิงที่นำเข้าไว้")
        return str(target)

    def _desktop_set_notice(self, kind, message):
        self._desktop_notice = {
            "kind": str(kind or "info"),
            "message": str(message or ""),
            "at": datetime.now().isoformat(timespec="milliseconds"),
        }

    def _clear_automation_error_log(self, job_id=""):
        """Clear a stale failure once that same job has resumed successfully."""
        job_id = str(job_id or "").strip()
        current_job_id = str(self._automation_error_log.get("job_id") or "").strip()
        if job_id and current_job_id and current_job_id != job_id:
            return False
        self._automation_error_log = {
            "job_id": "", "service": "", "message": "", "text": "", "at": "",
        }
        if str(self._desktop_notice.get("kind") or "").strip().lower() == "error":
            self._desktop_notice = {"kind": "", "message": "", "at": ""}
        return True

    def _product_error_service(self, job_id, message=""):
        """Name the failing product stage instead of labelling every failure as Flow."""
        message_text = str(message or "").strip().lower()
        if "gemini" in message_text:
            return "Gemini Web / วิเคราะห์และสร้างรูปสินค้า"
        if "chatgpt" in message_text:
            return "ChatGPT Web / วิเคราะห์และสร้างรูปสินค้า"
        if "google flow" in message_text or "flow" in message_text:
            return "Google Flow / สร้างวิดีโอสินค้า"
        try:
            job = self.products.get_job(str(job_id or "").strip())
        except Exception:
            job = {}
        ai_ready = bool(job.get("ai_result")) or str(job.get("ai_status") or "").strip().lower() in {
            "complete", "completed", "ready", "success",
        }
        if not ai_ready:
            provider = str(job.get("image_ai_provider") or "chatgpt").strip().lower()
            provider_name = "Gemini Web" if provider == "gemini" else "ChatGPT Web"
            return f"{provider_name} / วิเคราะห์และสร้างรูปสินค้า"
        return "Google Flow / สร้างวิดีโอสินค้า"

    def _should_keep_story_ai_draft(self, job_id, message):
        """Keep the owned AI conversation when its draft or saved result needs review."""
        job_id = str(job_id or "").strip()
        message = str(message or "").strip()
        cancel_event = getattr(self, "_story_cancel_event", None)
        if (not job_id or not message or job_id != getattr(self, "_story_pipeline_job_id", "")
                or cancel_event is None or cancel_event.is_set()):
            return False
        try:
            status = self.bridge.extension_status()
            clients = list(status.get("clients") or [])
            if not clients and isinstance(status.get("client"), dict):
                clients = [status["client"]]
            for client in clients:
                if (not isinstance(client, dict)
                        or str(client.get("ai_job_id") or "") != job_id
                        or str(client.get("version") or "") != LocalBridge.REQUIRED_EXTENSION_VERSION
                        or str(client.get("ai_step") or "") != "error"
                        or str(client.get("ai_message") or "").strip() != message
                        or type(client.get("ai_tab_id")) is not int or client["ai_tab_id"] <= 0):
                    continue
                if any(code in message for code in (
                    "STORY_IMAGE_RECEIPT_REVIEW", "STORY_IMAGE_DOWNLOAD_PENDING",
                    "STORY_IMAGE_CHECKPOINT_UNREADABLE", "STORY_ANALYSIS_CHECKPOINT_REVIEW", "STORY_IMAGE_FALLBACK_REVIEW", "STORY_IMAGE_STALL_REVIEW",
                    "GEMINI_IMAGE_SEND_REVIEW", "GEMINI_TEXT_SEND_REVIEW", "GEMINI_TEXT_REQUEST_REVIEW",
                    "AI_ANALYSIS_TIMEOUT", "AI_ANALYSIS_FORMAT_REVIEW", "AI_ANALYSIS_JSON_AMBIGUOUS",
                    "ใช้เวลาตอบนานเกิน 6 นาที",
                )):
                    # An empty composer is normal after an accepted answer.
                    # Preserve the conversation, not just an unsent draft.
                    return True
                detail = LocalBridge._safe_ai_send_diagnostics({
                    "detail": client.get("ai_send_diagnostics"),
                })
                if (detail.get("send_method") in {
                        "single_trusted_ai_send", "single_trusted_ai_send_unconfirmed",
                    }
                        and detail.get("draft_still_present") is True
                        and not detail.get("submission_proof")
                        and (detail.get("dispatch_completed") is True
                             or detail.get("gesture_phase") in {"pressed", "released", "release_uncertain"})):
                    return True
        except Exception as exc:
            self.log.warning("job_id=%s state=AI_DRAFT_PRESERVE result=unavailable error=%s", job_id, exc)
        return False

    def _flow_failure_notice_owner(self, payload):
        """A notice belongs to the original desktop worker, even after Flow clears."""
        if not isinstance(payload, dict):
            return False
        mode = payload.get("mode")
        if mode in {"product", "story"}:
            return self._pipeline_event_is_current(mode, payload)
        event = payload.get("cancel_event")
        if event is None or event.is_set():
            return False
        if mode == "manual_flow":
            return (event is getattr(self, "_manual_multi_flow_cancel_event", None)
                    and payload.get("job_id") == getattr(self, "_manual_multi_flow_job_id", ""))
        if mode == "presenter":
            progress = getattr(self, "_presenter_progress", {})
            return (event is getattr(self, "_presenter_cancel", None)
                    and payload.get("job_id") == progress.get("id")
                    and bool(payload.get("presenter_run_id"))
                    and payload["presenter_run_id"] == progress.get("run_id"))
        return False

    def _queue_flow_failure_notice(self, job_id, shot_index, client, cancel_event, presenter_run_id=""):
        """Capture only the bridge's registered current policy terminal; never page text."""
        job_id = str(job_id or "").strip()
        mode = "story" if job_id.startswith("STORY-") else "product"
        if job_id == getattr(self, "_manual_multi_flow_job_id", ""):
            mode = "manual_flow"
        if job_id.startswith("PRESENTER-"):
            mode = "presenter"
        payload = {"job_id": job_id, "mode": mode, "cancel_event": cancel_event,
                   "presenter_run_id": presenter_run_id}
        if not self._flow_failure_notice_owner(payload) or not isinstance(client, dict):
            return False
        run_id = str(client.get("flow_run_id") or "").strip()
        card = str(client.get("flow_failure_card_fingerprint") or "").strip()
        reason = str(client.get("flow_failure_reason") or "").strip()
        client_id = str(client.get("client_id") or "").strip()
        if (not run_id or not card or not reason or not client_id
                or str(client.get("version") or "") != self.bridge.REQUIRED_EXTENSION_VERSION
                or client.get("flow_job_id") != job_id
                or client.get("flow_shot_index") != shot_index
                or client.get("flow_failure_code") != "FLOW_POLICY_BLOCKED"
                or client.get("flow_policy_failure_category") not in {"general_policy", "face_or_public_figure"}
                or client.get("flow_generation_active") or client.get("flow_has_playable_result")):
            return False
        # A client can retain an old terminal while a newer run starts. Check
        # the bridge run registry and exact registered card before publishing.
        try:
            with self.bridge._extension_lock:
                expected = self.bridge._extension_runs.get(("flow", job_id, shot_index)) or {}
                registered = self.bridge._extension_clients.get(client_id) or {}
                if str(expected.get("run_id") or "") != run_id or any(
                    registered.get(key) != client.get(key) for key in (
                        "version", "flow_job_id", "flow_shot_index", "flow_run_id", "flow_failure_code",
                        "flow_failure_card_fingerprint", "flow_failure_reason", "flow_policy_failure_category",
                    )
                ):
                    return False
        except (AttributeError, TypeError):
            return False
        event_id = hashlib.sha256(f"{job_id}\n{run_id}\n{shot_index}\n{card}".encode("utf-8")).hexdigest()
        payload.update(event_id=event_id, run_id=run_id, shot_index=shot_index,
                       client_id=client_id, reason=reason[:1600])
        self.events.put(("flow_failure_notice", payload))
        return True

    def _capture_flow_failure_notice(self, payload):
        """Publish a copyable warning without changing the worker, queue or progress."""
        if not self._flow_failure_notice_owner(payload):
            return False
        event_id = str(payload.get("event_id") or "")
        seen = getattr(self, "_flow_failure_notice_ids", [])
        if not event_id or event_id in seen:
            return False
        self._flow_failure_notice_ids = (seen + [event_id])[-128:]
        job_id = payload["job_id"]
        title = f"สร้างวิดีโอฉาก {payload['shot_index']} ไม่สำเร็จ"
        reason = payload["reason"]
        continuation = ("งานตัวละครหยุดแล้ว • เก็บคลิปที่สำเร็จไว้เพื่อตรวจสอบ"
                        if payload.get("mode") == "presenter"
                        else "พักฉากนี้เพื่อตรวจสอบ • เก็บคลิปเดิม ไม่ใช้ภาพนิ่งแทนวิดีโอ")
        now = datetime.now().isoformat(timespec="milliseconds")
        lines = ["SmartFlow AI • Google Flow", f"เวลา: {now}", f"Job: {job_id}",
                 f"Run: {payload['run_id']}", title, f"สาเหตุ: {reason}",
                 "Flow ระบุว่าไม่ได้เรียกเก็บเงิน", continuation]
        self._automation_error_log = {
            "job_id": job_id, "service": "Google Flow", "kind": "warning",
            "title": title, "message": f"สาเหตุ: {reason}",
            "text": "\n".join(lines), "at": now, "event_id": event_id,
        }
        self._write_console(" • ".join((job_id, title, reason, continuation)), "warning")
        return True

    def _capture_automation_error_log(self, job_id, message, service="automation"):
        """Keep one copy-ready failure report for the Hybrid UI popup."""
        job_id = str(job_id or "").strip()
        message = str(message or "เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ").strip()
        service = str(service or "automation").strip()
        client = {}
        clients = []
        try:
            status = self.bridge.extension_status()
            clients = list(status.get("clients") or [])
            client = next((row for row in clients if job_id and job_id in {
                str(row.get("flow_job_id") or ""), str(row.get("ai_job_id") or "")
            }), status.get("client") or {})
        except Exception as exc:
            self.log.warning("job_id=%s state=ERROR_LOG_CAPTURE result=partial error=%s", job_id, exc)
        # A Story AI worker may relay a downstream Flow exception. Prefer the
        # exact current Flow failure, never an unrelated/older provider snapshot.
        flow_origin = next((row for row in clients
                            if job_id and str(row.get("flow_job_id") or "") == job_id
                            and row.get("flow_step") == "error"
                            and str(row.get("flow_failure_code") or "").startswith("FLOW_")
                            and str(row.get("flow_failure_code")) in message
                            and (not row.get("ai_run_id") or not row.get("flow_run_id")
                                 or row.get("ai_run_id") == row.get("flow_run_id"))), None)
        if flow_origin:
            client = flow_origin
        meta_origin = "META_" in message
        meta_detail = {}
        if meta_origin:
            try:
                from core.meta_error_report import read_meta_error
                meta_detail = read_meta_error(self.stories, job_id, message)
            except (AttributeError, OSError, ValueError, TypeError):
                pass
        ai_error = not meta_origin and not flow_origin and any(token in service.lower() for token in ("gemini", "chatgpt", "ai web"))
        if meta_origin:
            step = f"Meta AI • ฉาก {meta_detail['index']} • {meta_detail['stage']}" if meta_detail else "Meta AI • ไม่พบใบรับฉากที่ตรงข้อผิดพลาด"
            extension_message = str(meta_detail.get('message') or '')
            page_url = str(meta_detail.get('observed_url') or '')
            excerpt = ''
        elif ai_error:
            step = str(client.get("ai_step") or client.get("flow_step") or "").strip()
            extension_message = str(client.get("ai_message") or client.get("flow_message") or "").strip()
            page_url = str(client.get("ai_page_url") or client.get("page_url") or "").strip()
            excerpt = str(client.get("ai_page_excerpt") or "").strip()
        else:
            step = str(client.get("flow_step") or client.get("ai_step") or "").strip()
            extension_message = str(client.get("flow_message") or client.get("ai_message") or "").strip()
            page_url = str(client.get("flow_page_url") or client.get("page_url") or "").strip()
            excerpt = str(client.get("flow_page_excerpt") or "").strip()
        now = datetime.now().isoformat(timespec="milliseconds")
        lines = [
            "SmartFlow AI • Automation Error Log",
            f"เวลา: {now}",
            f"Job: {job_id or '—'}",
            f"บริการ: {service}",
            f"ข้อผิดพลาด: {message}",
        ]
        if step:
            lines.append(f"ขั้นตอน Extension: {step}")
        if extension_message and extension_message != message:
            lines.append(f"ข้อความ Extension: {extension_message}")
        if page_url:
            lines.append(f"หน้าเว็บ: {page_url}")
        if meta_detail.get('expected_url'):
            lines.append(f"ลิงก์ฉาก Meta ที่บันทึกไว้: {meta_detail['expected_url']}")
            if not page_url:
                lines.append("หน้าล่าสุดของ Meta: ใบรับรุ่นเดิมไม่ได้บันทึก URL ที่อ่านได้จริง")
        if (ai_error and job_id and str(client.get("ai_job_id") or "") == job_id
                and str(client.get("version") or "") == LocalBridge.REQUIRED_EXTENSION_VERSION):
            send_diagnostics = LocalBridge._safe_ai_send_diagnostics({
                "detail": client.get("ai_send_diagnostics"),
            })
            if send_diagnostics:
                import json
                if send_diagnostics.get("request_owner_found") is False:
                    lines.append("สถานะคำถาม: ยังยืนยันคำถามของฉากนี้ในแชตไม่ได้ • ไม่ใช้คำตอบฉากก่อนและไม่เริ่มงานซ้ำ")
                    if send_diagnostics.get("draft_still_present") is True:
                        lines.append("พรอมต์ของฉากนี้ยังอยู่ในช่องพิมพ์ • เก็บภาพและแผนฉากที่สำเร็จไว้")
                if (send_diagnostics.get("gesture_phase") == "not_started"
                        and send_diagnostics.get("preflight_reason")):
                    labels = {
                        "job": "เจ้าของงาน", "run": "รอบการทำงาน", "url": "หน้าแชต",
                        "prompt": "ข้อความในช่องพิมพ์", "sourceSignature": "รูปแนบในช่องพิมพ์",
                        "userCount": "จำนวนข้อความผู้ใช้", "userSignature": "ข้อความผู้ใช้ล่าสุด",
                        "assistantCount": "จำนวนคำตอบ", "assistantSignature": "คำตอบล่าสุด",
                        "imageSignature": "ภาพในคำตอบล่าสุด", "send_not_ready": "ปุ่มส่งยังไม่พร้อม",
                        "response_active": "AI ยังตอบอยู่", "upload_busy": "รูปยังอัปโหลดอยู่",
                        "image_expanded": "หน้าดูภาพยังเปิดอยู่",
                    }
                    changed = [labels[key] for key in send_diagnostics.get("changed_fields", []) if key in labels]
                    lines.append("สถานะการส่ง: ยังไม่ได้กดส่ง • เก็บข้อความและรูปเดิมไว้")
                    if changed:
                        lines.append("จุดที่ตรวจพบก่อนส่ง: " + ", ".join(changed))
                lines.append("หลักฐานการส่ง AI: " + json.dumps(
                    send_diagnostics, ensure_ascii=False, sort_keys=True,
                ))
        if excerpt:
            lines.extend(("", "--- หน้าจอล่าสุดที่ Extension อ่านได้ ---", excerpt[:3000]))
        if job_id.startswith("STORY-"):
            from core.story_failure_timeline import story_failure_timeline
            timeline = story_failure_timeline(self.stories.root, job_id)
            if timeline:
                lines.extend(("", timeline, "", "ไฟล์ trace ต้นฉบับ: workspace/stories/" + job_id + "/logs/extension_trace.jsonl"))
        self._automation_error_log = {
            "job_id": job_id,
            "service": service,
            "message": message,
            "text": "\n".join(lines),
            "at": now,
        }
        self._desktop_set_notice("error", f"{job_id or 'Automation'} • พบข้อผิดพลาด • เปิด Log สำหรับส่งให้ Codex ได้")

    def _install_hybrid_messagebox_bridge(self):
        """Keep hidden Tk notifications from blocking every Hybrid UI action."""
        def build_notice(kind):
            def show(title="", message="", **_options):
                title_text = str(title or "").strip()
                message_text = str(message or "").strip()
                combined = " • ".join(part for part in (title_text, message_text) if part)
                self._desktop_set_notice(kind, combined or "มีข้อความแจ้งเตือนจากระบบ")
                if hasattr(self, "status"):
                    self.status.set(title_text or message_text or "มีข้อความแจ้งเตือนจากระบบ")
                if hasattr(self, "log_activity"):
                    level = "error" if kind in {"error", "warning"} else "success"
                    self._write_console(f"HYBRID NOTICE • {combined}", level)
                return "ok"
            return show

        # The Tk workspace is withdrawn in Hybrid mode. Native message boxes
        # would therefore appear behind the HTML window and block Tk's event
        # loop, causing /api/desktop/state and every button to time out.
        messagebox.showinfo = build_notice("success")
        messagebox.showwarning = build_notice("warning")
        messagebox.showerror = build_notice("error")

    def _desktop_select_product(self, job_id):
        if not hasattr(self, "product_table"):
            return False
        self.product_table.selection_remove(*self.product_table.selection())
        if not job_id:
            return False
        for row_id in self.product_table.get_children():
            values = self.product_table.item(row_id, "values")
            if values and str(values[0]) == str(job_id):
                self.product_table.selection_set(row_id)
                self.product_table.focus(row_id)
                return True
        return False

    def _reserve_file_deletion(self, mode, item_id=''):
        guard = app_guard(self)
        if mode == 'project':
            summary = self.video_library.project_summary(item_id=item_id)
        elif mode == 'video':
            summary = self.video_library.rendered_summary(item_id)
        elif mode == 'all_renders':
            summary = self.video_library.rendered_summary()
        elif mode in {'all_products', 'completed_projects'}:
            summary = self.video_library.project_summary(kind='product' if mode == 'all_products' else '',
                completed_only=mode == 'completed_projects')
        else:
            raise ValueError('โหมดลบไม่ถูกต้อง')
        return guard.reserve_delete([row['job_id'] for row in summary['groups']],
            skip_busy=mode in {'all_products', 'all_renders', 'completed_projects'})

    def _start_desktop_delete(self, mode, item_id=''):
        claim = self._reserve_file_deletion(mode, item_id)
        try:
            threading.Thread(target=lambda: claim.guard.run_delete(claim, self._desktop_delete_worker, mode, item_id), daemon=True).start()
        except BaseException:
            claim.release()
            raise

    def _desktop_delete_worker(self, mode, item_id):
        try:
            if mode == "video":
                result = self.video_library.delete_job_renders(item_id)
                count = int(result.get("deleted_count") or 0)
                message = f"ย้ายวิดีโอ {count} ไฟล์ลงถังขยะ Windows แล้ว"
            elif mode == "project":
                result = self.video_library.delete_project(item_id)
                count = int(result.get("deleted_count") or 0)
                message = f"ย้ายโปรเจกต์ {count} รายการลงถังขยะ Windows แล้ว"
            elif mode == "all_renders":
                result = self.video_library.delete_all_renders()
                count = int(result.get("deleted_count") or 0)
                message = f"ย้ายวิดีโอเรนเดอร์ทั้งหมด {count} ไฟล์ลงถังขยะ Windows แล้ว"
            elif mode == "all_products":
                result = self.video_library.delete_all_projects(kind="product")
                count = int(result.get("deleted_count") or 0)
                message = f"ย้าย Product Job ทั้งหมด {count} โปรเจกต์ลงถังขยะ Windows แล้ว"
            elif mode == "completed_projects":
                result = self.video_library.delete_completed_projects()
                count = int(result.get("deleted_count") or 0)
                message = f"ย้ายโปรเจกต์ที่เสร็จแล้ว {count} โปรเจกต์ลงถังขยะ Windows แล้ว"
            else:
                raise ValueError("โหมดลบไม่ถูกต้อง")
            skipped, failed = int(result.get('skipped_count') or 0), int(result.get('failed_count') or 0)
            if skipped or failed:
                message += f' • ข้ามงานที่ยังใช้ไฟล์ {skipped} รายการ • ลบไม่สำเร็จ {failed} รายการ'
            self.events.put(("desktop_operation", ('warning' if skipped or failed else "success", message)))
        except Exception as exc:
            self.events.put(("desktop_operation", ("error", str(exc))))

    def _workspace_cleanup_active_jobs(self):
        return {
            value for value in (
                str(self._product_pipeline_job_id or ""),
                str(self._story_pipeline_job_id or ""),
                str(getattr(self, "_manual_multi_flow_job_id", "") or ""),
            ) if value
        }

    def _workspace_cleanup_payload(self):
        with self._workspace_cleanup_lock:
            state = dict(self._workspace_cleanup_state)
            state["categories"] = [dict(row) for row in state.get("categories") or []]
            state["last_result"] = dict(state.get("last_result") or {})
        state["automation_active"] = bool(self._workspace_cleanup_active_jobs())
        state["auto_cleanup_enabled"] = True
        return state

    def _workspace_cleanup_worker(self, scan_id):
        try:
            result = self.workspace_cleaner.clean(scan_id, self._workspace_cleanup_active_jobs())
            remaining = dict(result.get("remaining") or WorkspaceCleaner.empty_summary())
            remaining.update({"busy": False, "error": "", "last_result": {
                "deleted_count": int(result.get("deleted_count") or 0),
                "failed_count": int(result.get("failed_count") or 0),
                "reclaimed_bytes": int(result.get("reclaimed_bytes") or 0),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }})
            with self._workspace_cleanup_lock:
                self._workspace_cleanup_state = remaining
            count = int(result.get("deleted_count") or 0)
            failed = int(result.get("failed_count") or 0)
            size_text = self._format_file_size(result.get("reclaimed_bytes") or 0)
            message = f"เคลียร์ไฟล์ขยะ {count} ไฟล์ • คืนพื้นที่ {size_text}"
            if failed:
                message += f" • ข้าม {failed} ไฟล์ที่กำลังถูกใช้งาน"
            self.events.put(("desktop_operation", ("success" if not failed else "info", message)))
        except Exception as exc:
            with self._workspace_cleanup_lock:
                self._workspace_cleanup_state.update({"busy": False, "error": str(exc)})
            self.events.put(("desktop_operation", ("error", f"เคลียร์ไฟล์ขยะไม่สำเร็จ • {exc}")))

    def _auto_cleanup_completed_job_worker(self, job_id):
        """Validate the published Final, then recycle only that Job's intermediates."""
        try:
            result = self.workspace_cleaner.cleanup_completed_job(job_id)
            self.events.put(("auto_cleanup_complete", {"ok": True, **result}))
        except Exception as exc:
            self.log.warning(
                "job_id=%s state=AUTO_FINAL_CLEANUP result=protected error=%s",
                job_id,
                exc,
            )
            self.events.put(("auto_cleanup_complete", {
                "ok": False, "job_id": job_id, "error": str(exc),
            }))

    def _start_auto_cleanup_completed_job(self, job_id):
        if not getattr(self, "workspace_cleaner", None):
            return
        guarded_thread(self, job_id, self._auto_cleanup_completed_job_worker,
            args=(str(job_id),),
            daemon=True,
        )

    @uses_job_files(lambda app, action, payload: () if action.startswith('delete_') or
        action == 'product_jobs_delete_status' or (action == 'product_jobs_manage' and payload.get('operation') == 'delete') or
        (action == 'product_tool' and payload.get('tool') == 'delete_project') else payload)
    def _desktop_execute_action(self, action, payload):
        from core.membership import guard_action
        guard_action(self, action)
        if action in {'create_product', 'create_story'}:
            context = payload.get('creative_context') or {}
            if context.get('kind') == 'product_story' and context.get('source_product_id'):
                self.story_queue.require_not_trashed(context['source_product_id'])
        if action=='create_product' and not payload.get('job_id') and (payload.get('creative_context') or {}).get('kind')=='product_story':
            selected_video = 'meta_ai' if payload.get('video_provider') == 'meta_ai' or payload.get('video_generation_mode') == 'meta_ai' else 'google_flow'
            story_payload = {**payload, 'video_generation_mode': selected_video}
            source_id = str((payload.get('creative_context') or {}).get('source_product_id') or '')
            if source_id:
                # A lost UI/bridge response must not dispatch the same captured
                # Shopee source twice. Story creation is serialized by source ID.
                with _PRODUCT_STORY_DISPATCH_LOCK:
                    source = self.products.get_job(source_id)
                    linked_story_id = str(source.get('story_job_id') or '')
                    existing_story = None
                    if linked_story_id:
                        try:
                            existing_story = self.stories.get(linked_story_id)
                        except ValueError:
                            existing_story = None
                    if existing_story is None:
                        existing_story = next((row for row in self.stories.list_jobs()
                            if str((row.get('product_story') or {}).get('product_id') or '') == source_id), None)
                    if existing_story:
                        return {'ok': True, 'job_id': existing_story['id'], 'already_dispatched': True}
                    result = self._desktop_execute_action('create_story', story_payload)
                    story_job_id = str((result or {}).get('job_id') or '')
                    if story_job_id:
                        self.products.link_story_job(source_id, story_job_id)
                    return result
            return self._desktop_execute_action('create_story', story_payload)
        cast_creation = action == 'product_cast_generate'
        if cast_creation:
            payload={**payload,'topic':str(payload.get('topic') or 'นายแบบ / นางแบบ AI'),
                'creative_context':{'kind':'cast'},'audio_choices':{'mode':'none'},'video_generation_mode':'image_motion'}
            action='create_story'
        flow_smoke_test = action == 'create_flow_smoke_test'
        if flow_smoke_test:
            if not payload.get('queue_only') and (self._story_pipeline_job_id or self._product_pipeline_job_id):
                raise ValueError('มีงานกำลังทำอยู่ กรุณารอให้จบก่อนทดสอบ Flow')
            from core.flow_smoke import smoke_payload
            payload = smoke_payload(payload if isinstance(payload, dict) else {})
            if payload.get('queue_only'):
                return self._creation_queue_action('creation_enqueue', {**payload, 'mode':'story', 'values':[payload['topic']], 'flow_smoke_test':True})
            action = 'create_story'
        if action == "prepare_app_update":
            from ui.update_guard import prepare
            return prepare(self, payload or {})
        if action == "reload_extension_after_update":
            import secrets
            with self._app_update_lock:
                nonce = str((payload or {}).get("nonce") or "")
                if (not getattr(self, "_app_update_pending", False) or not nonce
                        or not secrets.compare_digest(nonce, str(getattr(self, "_app_update_nonce", "")))):
                    raise ValueError("ไม่พบการอัปเดต Extension ที่กำลังทำอยู่")
                self.bridge.request_extension_reload(
                    str(payload.get("client_id") or ""), str(payload.get("target_version") or ""))
                return {"ok": True, "reload_requested": True}
        if getattr(self, "_app_update_pending", False) and action != "shutdown":
            raise ValueError("กำลังเตรียมอัปเดต • เปิดโปรแกรมใหม่หากต้องการกลับมาทำงาน")
        product_runtime = None
        if action == 'create_story':
            from core.product_runtime_snapshot import prepared_product_runtime
            product_runtime = prepared_product_runtime(getattr(self, 'products', None), payload)
            if product_runtime is not None:
                payload = {**payload, **product_runtime}
        if action in {"create_product", "create_story", "create_drama_series"} and payload.get("audio_choices"):
            if not (payload.get('generated_music_options') or (payload.get('render_options') or {}).get('generated_music_options') or {}).get('enabled'):
                payload = {**payload, 'audio_choices': {key: value for key, value in payload['audio_choices'].items()
                    if key != 'generated_music_version'}}
            incoming_audio = audio_choices(payload["audio_choices"])
            if not payload.get("enqueue_only") and incoming_audio["mode"] == "flow_original" and incoming_audio["subtitle"] and not self._subtitle_store().load():
                raise ValueError("เปิดซับจากเสียง Flow ไว้ กรุณาเชื่อมต่อ Subtitle API หรือปิดซับก่อนเริ่ม")
        action = str(action or "").strip()
        payload = payload if isinstance(payload, dict) else {}
        if action.startswith("flow_settings_"):
            from ui.flow_settings import flow_settings_action
            return flow_settings_action(self, action, payload)
        if action.startswith('ai_cover_'):
            from ui.ai_cover import ai_cover_action
            return ai_cover_action(self, action, payload)
        if action.startswith('intro_'):
            from ui.video_intro import intro_action
            return intro_action(self, action, payload)
        enqueue_drama_only = action == "create_drama_series" and payload.get("enqueue_only") is True
        if action.startswith("presenter_"):
            return self._presenter_action(action, payload)
        if action == 'product_jobs_manage':
            from ui.product_jobs import manage_product_jobs
            return manage_product_jobs(self, payload)
        if action == 'product_jobs_delete_status':
            from ui.product_jobs import product_jobs_delete_status
            return product_jobs_delete_status(self, payload)
        if action in {'product_continue', 'create_product', 'retry_story'} and payload.get('job_id'):
            self.story_queue.require_not_trashed(payload['job_id'])
        if action == 'product_continue':
            from core.product_continue import product_continue_action
            job_id = str(payload.get('job_id') or '')
            if not re.fullmatch(r'(?:STORY|JOB)-[A-Za-z0-9-]+', job_id):
                raise ValueError('รหัสงานสินค้าไม่ถูกต้อง')
            reason = self._creation_idle_reason()
            if reason:
                raise ValueError(reason)
            job = self.stories.get(job_id) if job_id.startswith('STORY-') else self.products.get_job(job_id)
            action, payload = product_continue_action(job)
        if action in {"create_product", "create_story", "create_drama_series", "retry_story", "creation_resume", "story_queue_resume"} and not enqueue_drama_only and PresenterMixin._presenter_busy(self):
            raise ValueError("กำลังสร้างตัวละคร • รอหรือยกเลิกก่อนเริ่มงานอื่น")
        if action in {"product_image_review", "product_image_reuse"}:
            job_id = str(payload.get("job_id") or "")
            if action == "product_image_reuse":
                if payload.get("confirmed") is not True:
                    raise ValueError("ต้องยืนยันสิทธิ์และการใช้ภาพเดิมก่อน")
                if str(getattr(self, "_product_pipeline_job_id", "") or "") == job_id or str(getattr(self, "_manual_multi_flow_job_id", "") or "") == job_id:
                    raise ValueError("งานกำลังทำอยู่ กรุณารอหรือหยุดก่อน")
                ProductImageRecovery(self.products, job_id).approve_existing_source(payload.get("path"), payload.get("revision"))
                self._write_console(f"IMAGE REUSE • {job_id} • ผู้ใช้อนุมัติภาพเดิมในช่องที่ขาด ไม่ใช่ภาพ AI ใหม่", "log")
                self._refresh()
            return {"ok": True, "review": product_image_review(self.products, job_id)}
        if action.startswith("creation_") or action in {"enqueue_story_batch", "story_queue_resume", "story_queue_pause"}:
            return self._creation_queue_action(action, payload)
        if action in {"story_native_export", "story_native_status", "story_native_cancel", "story_native_open_folder"}:
            from ui.flow_native_audio import native_audio_action
            return native_audio_action(self, action, payload)
        if action == 'story_save_video_plan':
            from core.scene_video_plan import save
            from core.scene_video_worker import active_scenes
            job_id = str(payload.get('job_id') or '')
            if not re.fullmatch(r'STORY-[A-Za-z0-9-]+', job_id):
                raise ValueError('การเปลี่ยนเฉพาะฉากที่เหลือรองรับงาน Shopee แบบ STORY เท่านั้น • งาน JOB เดิมไม่ถูกเปลี่ยน')
            active_indices, unknown_active = active_scenes(self, job_id)
            result = save(self.stories, job_id,
                payload.get('plan_revision', payload.get('expected_plan_revision', -1)),
                payload.get('provider'), payload.get('scene_indices'),
                flow_settings=payload.get('flow_settings'),
                active_scene_indices=active_indices, unknown_active=unknown_active)
            job = result['job']
            active = str(getattr(self, '_story_pipeline_job_id', '') or '') == job_id
            self._write_console(f'{job_id} • SCENE VIDEO PLAN • บันทึกค่าฉากที่เหลือ • ไม่หยุดหรือส่งงานปัจจุบันซ้ำ', 'success')
            return {'ok': True, 'review': story_review(self.stories._folder(job_id), job, active),
                    'video_plan': {key: value for key, value in result.items() if key != 'job'}}
        if action in {"story_review", "story_preview_pronunciation", "story_save_pronunciation", "story_save_scene_prompt", "story_save_flow_scene", "story_set_video_provider"}:
            job_id = str(payload.get("job_id") or "")
            job = self.stories.get(job_id)
            active = str(getattr(self, "_story_pipeline_job_id", "") or "") == job_id
            if action == 'story_set_video_provider':
                if self._story_pipeline_job_id or self._manual_multi_flow_job_id:
                    raise ValueError('มีงานวิดีโอกำลังทำงาน • รอให้จบหรือหยุดก่อนเปลี่ยนผู้สร้าง')
                job = self.stories.set_video_generation_mode(job_id, payload.get('provider'), payload.get('revision', -1))
                self._write_console(f'{job_id} • VIDEO PROVIDER • {job.get("video_generation_mode")} • บันทึกกับงานนี้เท่านั้น', 'success')
            if action == 'story_save_flow_scene':
                if active or str(getattr(self, '_manual_multi_flow_job_id', '') or '') == job_id:
                    raise ValueError('กรุณาหยุดงานก่อนแก้ค่าฉาก')
                from core.flow_scene_edit import save
                job = save(self.stories, job_id, payload.get('scene_index'), payload.get('prompt'), payload.get('model'), payload.get('revision'))
            if action == "story_preview_pronunciation":
                draft = dict(job, user_pronunciation_notes=validate_user_notes(payload.get("notes")))
                return {"ok": True, "voice_review": voice_review(draft)}
            if action == "story_save_pronunciation":
                if active:
                    raise ValueError("งานกำลังทำอยู่ กรุณาหยุดงานก่อนแก้คำอ่าน")
                job = self.stories.save_pronunciation_notes(job_id, payload.get("notes"), payload.get("revision", -1))
                self._write_console(f"STORY REVIEW • {job_id} • บันทึกคำอ่าน ไม่สร้างรูปหรือส่งเสียงซ้ำ", "log")
            if action == "story_save_scene_prompt":
                if active:
                    raise ValueError("งานกำลังทำอยู่ กรุณาหยุดงานก่อนแก้พรอมต์ฉาก")
                job = self.stories.save_scene_prompt(job_id, payload.get("scene_index"), payload.get("prompt"), payload.get("revision", -1))
                self._write_console(f"STORY REVIEW • {job_id} • บันทึก Prompt ฉาก {payload.get('scene_index')} • ยังไม่สร้าง ต้องกดทำต่อเอง", "log")
            return {"ok": True, "review": story_review(self.stories._folder(job_id), job, active)}
        manual_flow_job = str(getattr(self, "_manual_multi_flow_job_id", "") or "")
        if manual_flow_job and action in {"create_product", "create_story", "create_drama_series", "retry_story"} and not enqueue_drama_only:
            raise ValueError(
                f"กำลังสร้างวิดีโอ Google Flow ของ {manual_flow_job} อยู่ • "
                "กรุณารอให้จบหรือกดยกเลิกก่อนเริ่มงานใหม่"
            )
        if action in {"create_product", "create_story", "retry_story", "create_drama_series"} and not enqueue_drama_only:
            queue_state = self.story_queue.snapshot()
            if self._creation_workers_alive() or (queue_state["active_count"] and not queue_state["paused"]):
                raise ValueError("คิวกำลังทำงาน • เพิ่มลงคิว หรือพักคิวและรอคลิปปัจจุบันจบก่อนสร้างทันที")
        if action == "refresh":
            self._refresh()
            return {"ok": True}
        if action == "connect_browser":
            return {"ok": True, "browser_connection": self._start_browser_connection()}
        if action == "check_system_readiness":
            self._refresh_guide_status()
            extension = self.bridge.extension_status()
            compatible = bool(
                extension.get("connected")
                and str((extension.get("client") or {}).get("version") or "") == self.bridge.REQUIRED_EXTENSION_VERSION
            )
            voice_ready = bool(self.voice_api_key.get().strip() and (self.voice_reference_id.get().strip() or Path(self.voice_reference_file.get().strip()).is_file()))
            try:
                subtitle_ready = bool(self._subtitle_store().load())
            except Exception:
                subtitle_ready = False
            ready_count = sum((self.bridge.server is not None, compatible, voice_ready, subtitle_ready))
            return {"ok": True, "ready": ready_count == 4, "ready_count": ready_count}
        if action == "open_web":
            target = str(payload.get("target") or "")
            urls = {
                "shopee": "https://affiliate.shopee.co.th/offer/product_offer",
                "chatgpt": "https://chatgpt.com/",
                "gemini": "https://gemini.google.com/app",
                "flow": "https://flow.google.com/",
                "extensions": "chrome://extensions",
            }
            if target not in urls:
                raise ValueError("ไม่รู้จักหน้าเว็บที่ต้องการเปิด")
            self._open_url(urls[target])
            return {"ok": True}
        if action == "install_extension":
            self._open_extension()
            return {"ok": True, "path": str((ROOT / "browser_extension").resolve())}
        if action == "open_extension_folder":
            self._open_folder(ROOT / "browser_extension")
            return {"ok": True}
        if action == "copy_extension_path":
            self._copy_extension_path()
            return {"ok": True, "path": str((ROOT / "browser_extension").resolve())}
        if action == "open_logs_folder":
            self._open_folder(ROOT / "logs")
            return {"ok": True}
        if action == "open_workspace_issue_folder":
            target = resolve_workspace_issue_folder(
                ROOT, str(payload.get("kind") or ""), str(payload.get("id") or "")
            )
            subprocess.Popen(["explorer", str(target)])
            return {"ok": True}
        if action == "choose_story_image":
            path = filedialog.askopenfilename(parent=self.root, filetypes=[("รูปหลัก", "*.png *.jpg *.jpeg *.webp")])
            if path:
                self.story_main_image.set(path)
            return {"ok": True, "path": path or ""}
        if action == "upload_reference_image":
            return self._save_desktop_reference_image(payload)
        if action == "choose_drama_image":
            path = filedialog.askopenfilename(parent=self.root, filetypes=[("รูปตัวละคร", "*.png *.jpg *.jpeg *.webp")])
            return {"ok": True, "path": path or ""}
        if action == "choose_drama_footage":
            paths = filedialog.askopenfilenames(parent=self.root, filetypes=[("ฟุตเทจวิดีโอ", "*.mp4 *.mov *.mkv *.avi *.webm")])
            return {"ok": True, "paths": list(paths or [])}
        if action == "import_product_link":
            link = str(payload.get("link") or "").strip()
            if not link:
                raise ValueError("กรุณาวางลิงก์สินค้า Shopee")
            self.products.validate_shopee_url(link)
            job, created = self.products.import_link(link)
            self.product_link.set("")
            self._refresh()
            self._desktop_set_notice("success", f"{'สร้าง Product Job ใหม่' if created else 'ลิงก์นี้มีอยู่แล้ว'} • {job.get('product_name') or job['id']}")
            return {"ok": True, "job_id": job["id"], "created": bool(created)}
        if action == "update_product":
            job_id = str(payload.get("job_id") or "")
            if not job_id:
                raise ValueError("กรุณาเลือก Product Job")
            job = self.products.update_product_info(
                job_id,
                str(payload.get("product_name") or "").strip(),
                str(payload.get("price") or "").strip(),
                str(payload.get("commission") or "").strip(),
                str(payload.get("description") or "").strip(),
            )
            self._refresh()
            self._desktop_set_notice("success", f"บันทึกข้อมูล {job_id} และสร้าง Prompt ใหม่แล้ว")
            return {"ok": True, "job_id": job["id"]}
        if action == "approve_product_ai":
            job_id = str(payload.get("job_id") or "")
            job = self.products.get_job(job_id)
            if str(job.get("ai_status") or "") != "ready":
                raise ValueError("Job นี้ยังไม่มีผล AI พร้อมอนุมัติ")
            self.products.approve_ai_result(job_id)
            self._refresh()
            self._desktop_set_notice("success", f"อนุมัติผล AI ของ {job_id} แล้ว")
            return {"ok": True}
        if action == "check_product_readiness":
            job_id = str(payload.get("job_id") or "")
            result = self.products.check_readiness(job_id)
            self._refresh()
            return {"ok": True, "readiness": result}
        if action == 'product_set_video_provider':
            job_id = str(payload.get('job_id') or '').strip()
            provider = str(payload.get('provider') or '').strip().lower()
            if self._product_pipeline_job_id or self._manual_multi_flow_job_id:
                raise ValueError('มีงานสินค้ากำลังสร้างวิดีโออยู่ • รอให้จบหรือหยุดก่อนเปลี่ยนผู้สร้าง')
            job = self.products.get_job(job_id)
            if job.get('video_status') == 'ready':
                raise ValueError('คลิปนี้เสร็จแล้ว • หากต้องการสร้างด้วยผู้สร้างอื่น ให้เริ่มงานใหม่จากภาพเดิม')
            if str(job.get('automation_status') or '') == 'running':
                raise ValueError('งานยังทำงานอยู่ • กรุณาหยุดงานก่อนเปลี่ยนผู้สร้างวิดีโอ')
            self.products.set_video_ai_provider(job_id, provider)
            self._write_console(f'{job_id} • VIDEO PROVIDER • {provider} • บันทึกกับงานนี้เท่านั้น', 'success')
            self._refresh()
            return {'ok': True, 'job_id': job_id, 'video_ai_provider': provider}
        if action in {"product_add_images", "product_add_video", "product_tool"}:
            job_id = str(payload.get("job_id") or "")
            if not job_id or not self._desktop_select_product(job_id):
                raise ValueError("กรุณาเลือก Product Job")
            if action == "product_add_images":
                paths = filedialog.askopenfilenames(parent=self.root, filetypes=[("Product images", "*.jpg *.jpeg *.png *.webp")])
                if not paths:
                    return {"ok": True, "cancelled": True}
                self.products.attach_images(job_id, paths)
                self._refresh()
                return {"ok": True, "count": len(paths)}
            if action == "product_add_video":
                path = filedialog.askopenfilename(parent=self.root, filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi")])
                if not path:
                    return {"ok": True, "cancelled": True}
                self.products.attach_video(job_id, path)
                self._refresh()
                return {"ok": True, "path": path}
            tool = str(payload.get("tool") or "")
            if tool in {"auto_flow", "multi_flow"}:
                selected_video_job = self.products.get_job(job_id)
                if str(selected_video_job.get("video_ai_provider") or "flow").strip().lower() != "flow":
                    raise ValueError("เครื่องมือนี้ใช้กับ Google Flow เท่านั้น • ใช้ทำต่อของงานเดิมเพื่อสร้างด้วยผู้ให้บริการที่บันทึกไว้")
            if tool == "ai_web":
                self._prepare_chatgpt_plugin()
            elif tool == "auto_flow":
                self._send_to_google_flow()
            elif tool == "multi_flow":
                self._start_multi_flow()
            elif tool == "effects":
                self._render_product_effects()
            elif tool == "open_job":
                self._open_selected_product()
            elif tool == "delete_project":
                self._start_desktop_delete('project', f'product:{job_id}')
            else:
                raise ValueError("ไม่รู้จักเครื่องมือสินค้า")
            return {"ok": True, "accepted": True}
        if action == "voice_select_job":
            job_id = str(payload.get("job_id") or "")
            self.products.get_job(job_id)
            self.voice_job_id.set(job_id)
            self._load_voice_job()
            return {"ok": True, "job_id": job_id}
        if action == "voice_save_key":
            api_key = str(payload.get("api_key") or "").strip()
            if not api_key:
                raise ValueError("กรุณาใส่ AI Voice API Key")
            WindowsCredentialStore().save(api_key)
            self.voice_api_key.set(api_key)
            self.voice_key_saved.set("✓ เชื่อมต่อแล้ว • เก็บคีย์ใน Windows")
            self.status.set("บันทึก AI Voice API Key แบบเข้ารหัสแล้ว")
            self._refresh_voice_catalog(silent=True)
            self._refresh_service_credits(force=True, silent=True)
            return {"ok": True}
        if action == "voice_delete_key":
            WindowsCredentialStore().delete()
            self.voice_api_key.set("")
            self.voice_key_saved.set("○ ยังไม่ได้เชื่อมต่อ")
            self.voice_catalog_choice.set("กดโหลดรายการเสียง")
            self.voice_catalog_info.set("ใส่ API Key เพื่อโหลดเสียงที่บัญชีนี้ใช้งานได้")
            self._voice_catalog_by_label = {}
            if hasattr(self, "voice_catalog_combo"):
                self.voice_catalog_combo.configure(values=())
            self.voice_status.set("ยกเลิกการเชื่อมต่อแล้ว • ใส่ API Key เพื่อเชื่อมใหม่")
            self.status.set("ยกเลิกการเชื่อมต่อ AI Voice แล้ว")
            self._service_credit_state["voice"] = self._credit_state(False, "ยังไม่ได้เชื่อม AI Voice")
            self._refresh()
            return {"ok": True}
        if action == "voice_refresh_catalog":
            if not self.voice_api_key.get().strip():
                raise ValueError("กรุณาบันทึก AI Voice API Key ก่อนโหลดเสียง")
            self._refresh_voice_catalog(silent=True)
            return {"ok": True, "accepted": True}
        if action == "refresh_service_credits":
            started = self._refresh_service_credits(force=True, silent=False)
            return {"ok": True, "accepted": bool(started)}
        if action == "voice_select_catalog":
            label = str(payload.get("label") or "")
            if label not in self._voice_catalog_by_label:
                raise ValueError("ไม่พบเสียงที่เลือก กรุณากดโหลดเสียงใหม่")
            self.voice_catalog_choice.set(label)
            self._select_catalog_voice()
            return {"ok": True}
        if action == "voice_choose_reference":
            path = filedialog.askopenfilename(parent=self.root, filetypes=[("Reference audio", "*.wav *.mp3 *.m4a *.aac *.ogg *.flac *.mp4")])
            if path:
                self.voice_reference_file.set(path)
                save_voice_settings({"voice_reference_file": path})
            return {"ok": True, "path": path or ""}
        if action == "voice_upload_reference":
            if not self.voice_api_key.get().strip():
                raise ValueError("กรุณาบันทึก AI Voice API Key ก่อน")
            if not Path(self.voice_reference_file.get().strip()).is_file():
                raise ValueError("กรุณาเลือกไฟล์เสียงอ้างอิงก่อน")
            self.voice_status.set("กำลังอัปโหลดเสียงอ้างอิง...")
            self._voice_bg(lambda: self._upload_voice_reference_worker(self.voice_api_key.get().strip(), self.voice_reference_file.get().strip()))
            return {"ok": True, "accepted": True}
        if action in {"voice_create", "voice_save_settings", "voice_ai_script", "voice_open_folder"}:
            job_id = str(payload.get("job_id") or self.voice_job_id.get()).strip()
            self.products.get_job(job_id)
            self.voice_job_id.set(job_id)
            if action == "voice_ai_script":
                self._prepare_voice_chatgpt()
                return {"ok": True, "accepted": True}
            if action == "voice_open_folder":
                self._open_voice_folder()
                return {"ok": True}
            self.voice_reference_id.set(str(payload.get("reference_id") or self.voice_reference_id.get()).strip())
            self.voice_language.set(str(payload.get("language") or "th"))
            self.voice_emotion.set(CLIP_VOICE_EMOTION)
            self.voice_speed.set(str(CLIP_VOICE_SPEED))
            self.voice_silence.set(str(payload.get("silence") or "0.3"))
            self.voice_format.set(str(payload.get("format") or "mp3"))
            self.voice_script.delete("1.0", "end")
            self.voice_script.insert("1.0", str(payload.get("script") or ""))
            if action == "voice_save_settings":
                return self._save_voice_preferences(script_override=str(payload.get("script") or ""))
            self._create_voice()
            return {"ok": True, "accepted": True}
        if action == "subtitle_select_job":
            job_id = str(payload.get("job_id") or "")
            self.products.get_job(job_id)
            self.subtitle_job_id.set(job_id)
            self._load_subtitle_job()
            return {"ok": True}
        if action == "subtitle_connect":
            token = str(payload.get("token") or "").strip()
            if not token:
                raise ValueError("กรุณาวาง Token ที่ขึ้นต้นด้วย SOT")
            self.subtitle_token.set(token)
            self.subtitle_status.set("กำลังเชื่อม Token กับเครื่องนี้...")
            self._subtitle_bg(lambda: self._redeem_subtitle_worker(token, self.subtitle_language.get().strip() or "th", bool(self.subtitle_auto.get()), int(self.subtitle_syllables.get() or 3)))
            return {"ok": True, "accepted": True}
        if action == "subtitle_delete_credential":
            self._subtitle_store().delete()
            self.subtitle_token.set("")
            self.subtitle_credential_saved.set("○ ยังไม่ได้เชื่อมต่อ")
            self.subtitle_status.set("ลบรหัสอุปกรณ์แล้ว • ใช้ Token ใหม่เพื่อเชื่อมต่อ")
            self.status.set("ยกเลิกการเชื่อมต่อ AI Subtitle แล้ว")
            self._service_credit_state["subtitle"] = self._credit_state(False, "ยังไม่ได้เชื่อม AI Subtitle")
            self._refresh()
            return {"ok": True}
        if action in {"subtitle_preview_style", "subtitle_save_style", "subtitle_apply_style"}:
            self._set_subtitle_style_from_payload(payload, apply_theme=bool(payload.get("apply_theme")))
            if action == "subtitle_preview_style":
                self._update_subtitle_style_preview()
                return {"ok": True, "accepted": True, "preview_token": self._subtitle_preview_token}
            self._save_subtitle_options()
            if action == "subtitle_apply_style":
                self._apply_subtitle_style()
            else:
                self._save_subtitle_style(); self._update_subtitle_style_preview()
                self.subtitle_status.set("บันทึกรูปแบบข้อความแล้ว • งานถัดไปจะใช้ค่านี้")
            return {"ok": True, "accepted": action == "subtitle_apply_style"}
        if action == "subtitle_create":
            job_id = str(payload.get("job_id") or "")
            self.products.get_job(job_id)
            self.subtitle_job_id.set(job_id)
            self.subtitle_language.set(str(payload.get("language") or "th"))
            self.subtitle_syllables.set(str(max(1, min(5, int(payload.get("syllables") or 3)))))
            self.subtitle_auto.set(bool(payload.get("auto", True)))
            self._start_subtitle_for_job(job_id)
            return {"ok": True, "accepted": True}
        if action == "subtitle_upload_font":
            path = filedialog.askopenfilename(parent=self.root, filetypes=[("Font", "*.ttf *.otf")])
            if not path:
                return {"ok": True, "cancelled": True}
            record = self.fonts.upload(path)
            self._load_subtitle_fonts(str(record.path))
            self._subtitle_style_changed()
            return {"ok": True, "font": record.label}
        if action == "subtitle_random_theme":
            self._random_subtitle_theme()
            return {"ok": True}
        if action == "subtitle_open_folder":
            self.subtitle_job_id.set(str(payload.get("job_id") or self.subtitle_job_id.get()))
            self._open_subtitle_folder()
            return {"ok": True}
        if action == "audio_select_job":
            job_id = str(payload.get("job_id") or "")
            self.products.get_job(job_id)
            self.audio_job_id.set(job_id)
            self._load_audio_job()
            return {"ok": True}
        if action == "audio_save":
            if "background_selection" in payload:
                from core.music_library import validate_selection
                names, count = validate_selection(self._audio_asset_folder("background"),
                    payload["background_selection"], payload.get("background_track_count"))
                if payload.get("background_enabled", True) and not names:
                    raise ValueError("เลือกเพลงอย่างน้อยหนึ่งเพลง หรือปิดเพลงพื้นหลัง")
                values = {"audio_background_selection": names, "audio_background_track_count": count}
                save_audio_settings(values)
                self.cfg.update(values)
            self.audio_job_id.set(str(payload.get("job_id") or self.audio_job_id.get()))
            self.audio_background_enabled.set(bool(payload.get("background_enabled", True)))
            self.audio_background_mode.set(str(payload.get("background_mode") or "อัตโนมัติ • ยำท่อนสั้น V2"))
            self.audio_background_file.set(str(payload.get("background_file") or "สุ่มจากคลัง"))
            self.audio_background_volume.set(max(3, min(35, int(payload.get("background_volume") or 12))))
            self.audio_background_segment_max.set(max(8, min(12, float(payload.get("segment_max_sec") or 12))))
            self.audio_background_duck_percent.set(max(20, min(65, int(payload.get("duck_percent") or 38))))
            self.audio_sfx_enabled.set(bool(payload.get("sfx_enabled", True)))
            self.audio_sfx_mode.set(str(payload.get("sfx_mode") or "อัตโนมัติ • เว้นจังหวะ"))
            self.audio_sfx_file.set(str(payload.get("sfx_file") or "สุ่มจากคลัง"))
            self.audio_sfx_volume.set(max(5, min(60, int(payload.get("sfx_volume") or 22))))
            self.audio_sfx_min_interval.set(max(4, min(15, int(payload.get("sfx_interval") or 6))))
            self.audio_sfx_max_count.set(max(1, min(12, int(payload.get("sfx_count") or 6))))
            self._save_audio_options()
            self._desktop_set_notice("success", "บันทึกค่าเสียงประกอบแล้ว")
            return {"ok": True}
        if action == "audio_add_asset":
            kind = str(payload.get("kind") or "")
            if kind not in {"background", "sfx"}:
                raise ValueError("ประเภทเสียงไม่ถูกต้อง")
            source = filedialog.askopenfilename(parent=self.root, title="เลือกไฟล์เสียง", filetypes=(("ไฟล์เสียง", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("ทุกไฟล์", "*.*")))
            if not source:
                return {"ok": True, "cancelled": True}
            source_path = Path(source)
            if source_path.suffix.lower() not in AudioMixer.AUDIO_EXTENSIONS:
                raise ValueError("รองรับ MP3, WAV, M4A, AAC และ OGG")
            target_folder = ROOT / "assets" / "audio" / kind
            target_folder.mkdir(parents=True, exist_ok=True)
            target = target_folder / source_path.name
            if source_path.resolve() != target.resolve():
                shutil.copy2(source_path, target)
            if kind == "background":
                self.audio_background_file.set(target.name); self.audio_background_mode.set("เลือกเพลงเดียว")
            else:
                self.audio_sfx_file.set(target.name); self.audio_sfx_mode.set("เลือกเสียงเดียว")
            self._save_audio_options()
            return {"ok": True, "file": target.name}
        if action == "audio_random":
            self._randomize_audio_choices()
            return {"ok": True}
        if action == "audio_render":
            job_id = str(payload.get("job_id") or "")
            self.products.get_job(job_id)
            self.audio_job_id.set(job_id)
            self._maybe_mix_audio(job_id, force=True)
            return {"ok": True, "accepted": True}
        if action == "audio_open_folder":
            self.audio_job_id.set(str(payload.get("job_id") or self.audio_job_id.get()))
            self._open_audio_folder()
            return {"ok": True}
        if action in {"audio_open_background_folder", "audio_open_sfx_folder"}:
            kind = "background" if action == "audio_open_background_folder" else "sfx"
            target = self._open_audio_asset_folder(kind)
            return {
                "ok": True,
                "kind": kind,
                "path": str(target),
                "file_count": len(self._audio_assets(kind)),
            }
        if action == "logo_select_job":
            job_id = str(payload.get("job_id") or "")
            if job_id:
                self.products.get_job(job_id)
            self.logo_job_id.set(job_id)
            self._load_logo_job()
            return {"ok": True}
        if action == "logo_choose_file":
            path = filedialog.askopenfilename(parent=self.root, filetypes=[("Logo image", "*.png *.jpg *.jpeg *.webp")])
            if path:
                result = self._import_logo_file(path)
                result["path"] = str(self.logo_file.get())
                return result
            return {"ok": True, "cancelled": True, "path": ""}
        if action == "logo_upload":
            return self._save_desktop_logo(payload)
        if action == "logo_select_asset":
            target = self._resolve_logo_asset(payload.get("asset_id"))
            if not target:
                raise ValueError("ไม่พบโลโก้ที่เลือกในคลัง")
            self.logo_file.set(str(target))
            self._logo_preview_asset_id = ""
            self._logo_editor_request = ''
            self._logo_editor_preview = {}
            self.logo_status.set(f"เลือก {target.stem} แล้ว • ตรวจพรีวิวและกดบันทึก")
            self._update_logo_preview_from_cache()
            return {"ok": True, "asset_id": self._logo_asset_id(target), "name": target.stem}
        if action == "logo_save":
            self._apply_logo_payload(payload)
            settings = self._save_logo_preferences()
            self._desktop_set_notice("success", "บันทึกโลโก้เริ่มต้นและตำแหน่งเรียบร้อยแล้ว")
            return {"ok": True, "settings": settings}
        if action == 'logo_editor_preview':
            return self._preview_logo_editor(payload)
        if action in {"logo_preview", "logo_render", "logo_open_folder"}:
            job_id = str(payload.get("job_id") or self.logo_job_id.get()).strip()
            self.products.get_job(job_id)
            self.logo_job_id.set(job_id)
            if action == "logo_open_folder":
                self._open_logo_folder(); return {"ok": True}
            self._apply_logo_payload(payload)
            if action == "logo_preview":
                self._preview_logo()
            else:
                self._render_logo_video()
            return {"ok": True, "accepted": True}
        if action in {"queue_add_video", "queue_add_folder"}:
            added = 0
            if action == "queue_add_video":
                paths = filedialog.askopenfilenames(parent=self.root, filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi")])
                for path in paths:
                    added += int(bool(self.jobs.add(path)))
            else:
                folder = filedialog.askdirectory(parent=self.root)
                if folder:
                    for path in Path(folder).iterdir():
                        if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi"}:
                            added += int(bool(self.jobs.add(path)))
            self._refresh()
            return {"ok": True, "added": added}
        if action == "queue_safety":
            self.dry.set(bool(payload.get("dry_run", True)))
            self.confirm.set(bool(payload.get("confirm", True)))
            self._desktop_set_notice("success", "บันทึกโหมดคิวมือถือสำหรับรอบนี้แล้ว")
            return {"ok": True}
        if action in {"check_connection", "open_scrcpy", "open_android_shopee", "dump_ui"}:
            if action == "check_connection": self._bg(self._check)
            elif action == "open_scrcpy": self._scrcpy()
            elif action == "open_android_shopee": self._bg(self._shopee)
            else: self._bg(self._dump)
            return {"ok": True, "accepted": True}
        if action == "close_automation_browser":
            job_id = str(payload.get("job_id") or "").strip()
            command = self._close_automation_browser(job_id, str(payload.get("reason") or "ปิดแท็บงานอัตโนมัติ"))
            return {"ok": True, "accepted": bool(command), "command_id": str((command or {}).get("id") or "")}
        if action == "create_product":
            if not payload.get("job_id"):
                self._presenter_product_selection = self._presenter_selection(payload.get("presenter"))
            if self._product_pipeline_job_id:
                raise ValueError(f"กำลังทำงาน {self._product_pipeline_job_id} อยู่")
            if self._story_pipeline_job_id:
                raise ValueError(f"กำลังทำ Story {self._story_pipeline_job_id} อยู่ กรุณารอหรือยกเลิกก่อน")
            link = str(payload.get("link") or "").strip()
            job_id = str(payload.get("job_id") or "").strip()
            if not link and not job_id:
                raise ValueError("กรุณาวางลิงก์สินค้า หรือเลือก Product Job ที่ต้องการทำต่อ")
            if link:
                self.products.validate_shopee_url(link)
            if job_id and not any(str(row.get("id")) == job_id for row in self.products.list_jobs()):
                raise ValueError("ไม่พบ Product Job ที่เลือก")
            selected_job = self.products.get_job(job_id) if job_id else None
            # A checkpoint resume belongs to the provider recorded by that Job.
            # The global dropdown is only for a new link; otherwise a previous
            # Gemini selection can silently turn a ChatGPT Job into Gemini.
            provider = str(
                (selected_job or {}).get("image_ai_provider")
                or payload.get("provider")
                or self._image_provider_key()
            ).lower()
            if provider not in {"chatgpt", "gemini"}:
                raise ValueError("ผู้สร้างภาพไม่ถูกต้อง")
            self.image_ai_provider.set("Gemini Web" if provider == "gemini" else "ChatGPT Web")
            ai_web_model = normalize_ai_web_model(
                provider,
                (selected_job or {}).get("ai_web_model") or payload.get("ai_web_model") or self._ai_web_model_key(provider),
            )
            self._set_ai_web_model(provider, ai_web_model, persist=not bool(selected_job))
            video_provider = "flow"
            self.video_ai_provider.set("Google Flow")
            self._product_audio_choices = (selected_job.get("audio_choices") if selected_job else audio_choices(payload.get("audio_choices"), "flow"))
            from core.generated_music import validate_options as validate_product_music
            self._product_generated_music_options = validate_product_music(
                (selected_job or payload).get('generated_music_options'), 'flow', self._product_audio_choices)
            self._product_fictional_confirmed = (selected_job.get("fictional_ai_characters_confirmed") if selected_job else payload.get("fictional_ai_characters_confirmed")) is True
            self._product_flow_settings = snapshot_flow(selected_job or payload, {} if selected_job else self.cfg.get("flow_defaults"))
            from core.ai_cover import ai_cover_options
            self._product_ai_cover_options = ai_cover_options((selected_job or payload).get('ai_cover_options'))
            from core.green_screen import GreenLibrary
            self._product_green_options = GreenLibrary(ROOT,self.cfg.get('ffmpeg_path','')).validate((selected_job or payload).get('green_options'))
            self.subtitle_auto.set(bool((self._product_audio_choices or {}).get("subtitle", payload.get("subtitle", self.subtitle_auto.get()))))
            self.product_link.set(link)
            self._desktop_select_product("" if link else job_id)
            options = self._product_pipeline_options(seed=job_id or link)
            voice_ready = bool(selected_job and selected_job.get("voice_status") == "ready")
            if (options.get("audio_choices") or {}).get("mode", "api") == "api" and not voice_ready and not options["voice_api_key"]:
                raise ValueError("กรุณาตั้งค่า AI Voice API Key ก่อนเริ่ม")
            if (options.get("audio_choices") or {}).get("mode", "api") == "api" and not voice_ready and not options["voice_reference_id"] and not Path(options["voice_reference_file"]).is_file():
                raise ValueError("กรุณาเลือกเสียงในหน้า AI Voice หรือไฟล์เสียงต้นแบบก่อนเริ่ม")
            subtitle_ready = bool(selected_job and selected_job.get("subtitle_status") == "ready")
            if (options.get("audio_choices") or {}).get("mode") != "none" and options["subtitle_enabled"] and not subtitle_ready and not options["subtitle_credential"]:
                raise ValueError("เปิด Subtitle ไว้ แต่ยังไม่ได้เชื่อม Token")
            self._create_product_and_run(job_id)
            return {"ok": bool(self._product_pipeline_job_id), "job_id": self._product_pipeline_job_id}
        if action == "create_drama_series":
            self._story_audio_choices = audio_choices(payload.get("audio_choices"), (payload.get("render_options") or {}).get("video_generation_mode"))
            if self._story_audio_choices:
                payload.setdefault("render_options", {})["audio_choices"] = self._story_audio_choices
            if not self._story_audio_choices or self._story_audio_choices['mode'] == 'api':
                payload.setdefault('render_options', {})['primary_voice_reference_id'] = self.voice_reference_id.get().strip()
                payload['render_options']['primary_voice_reference_file'] = self.voice_reference_file.get().strip()
            if not enqueue_drama_only and (self._story_pipeline_job_id or self._product_pipeline_job_id):
                raise ValueError("มีงานกำลังทำอยู่ กรุณารอให้งานปัจจุบันเสร็จก่อนเริ่มละครสั้น")
            if not enqueue_drama_only and self.story_queue.snapshot().get("active_count"):
                raise ValueError("ยังมีคิว Story/ละครที่รอทำอยู่ กรุณาทำหรือล้างคิวเดิมก่อนเริ่มซีรีส์ใหม่")
            if not enqueue_drama_only and (not self._story_audio_choices or self._story_audio_choices["mode"] == "api"):
                if not self.voice_api_key.get().strip():
                    raise ValueError("กรุณาตั้งค่า AI Voice API Key ก่อนเริ่ม")
            if not enqueue_drama_only and (not self._story_audio_choices or self._story_audio_choices["mode"] == "api") and not self.voice_reference_id.get().strip() and not Path(self.voice_reference_file.get().strip()).is_file():
                raise ValueError("กรุณาเลือกเสียงต้นแบบก่อนเริ่ม")
            title = str(payload.get("title") or "").strip()
            premise = str(payload.get("premise") or "").strip()
            provider = str(payload.get("provider") or self._image_provider_key()).lower()
            ai_web_model = normalize_ai_web_model(provider, payload.get("ai_web_model") or self._ai_web_model_key(provider))
            scene_count = max(6, min(15, int(payload.get("scene_count") or 10)))
            episode_count = max(1, min(20, int(payload.get("episode_count") or 3)))
            characters = payload.get("characters") or []
            footage = payload.get("footage") or []
            plot_board = payload.get("plot_board") or []
            cover_theme = str(payload.get("cover_theme") or "cinematic").strip().lower()
            if not isinstance(characters, list):
                raise ValueError("ข้อมูลตัวละครไม่ถูกต้อง")
            if not isinstance(footage, list):
                raise ValueError("ข้อมูลฟุตเทจไม่ถูกต้อง")
            if not isinstance(plot_board, list):
                raise ValueError("กระดานพล็อต EP ไม่ถูกต้อง")
            characters = [dict(item) for item in characters if isinstance(item, dict)]
            if self._story_audio_choices and self._story_audio_choices['mode'] == 'api':
                known_refs = {str(row.get('reference_id') or '').strip()
                              for row in getattr(self, '_voice_catalog_by_label', {}).values()}
                for character in characters:
                    selected_ref = str(character.get('voice_reference_id') or '').strip()
                    if selected_ref and known_refs and selected_ref not in known_refs:
                        raise ValueError('เสียงตัวละครที่เลือกไม่อยู่ในรายการเสียงปัจจุบัน • โหลดรายการเสียงใหม่ก่อนเริ่ม')
            options = drama_render_options({**(payload.get("render_options") or {}),
                'speech_delivery_version': 1,
                **({'storytelling_options': payload['storytelling_options']} if payload.get('storytelling_options') is not None else {}),
                **({'generated_music_options': payload['generated_music_options']} if payload.get('generated_music_options') is not None else {}),
                'render_snapshot': self._video_render_settings(),
                "flow_settings": snapshot_flow(payload, self.cfg.get("flow_defaults")),
                "ai_cover_options": payload.get('ai_cover_options') or {},
                "fictional_ai_characters_confirmed": payload.get("fictional_ai_characters_confirmed") is True,
                "presenter": self._presenter_selection(payload.get("presenter") or {"enabled": False})})
            from ui.video_intro import capture_intro
            options['intro_options'] = capture_intro(self, payload.get('intro_options', options.get('intro_options')))
            from core.green_screen import GreenLibrary
            options['green_options'] = GreenLibrary(ROOT,self.cfg.get('ffmpeg_path','')).validate(payload.get('green_options',options.get('green_options')))
            if options.get("audio_choices"):
                captured = self._creation_capture_settings({**payload, "video_generation_mode": options["video_generation_mode"]})
                options.update(audio_mix_choices=captured["audio"], media_finish_config=captured["finish_config"])
            if self.story_queue.snapshot().get("active_count", 0) + episode_count > self.story_queue.MAX_ACTIVE_ITEMS:
                raise ValueError("จำนวน EP เกินพื้นที่คิวที่ว่าง • ลดจำนวนตอนก่อนเพิ่ม")
            for character in characters:
                character["image"] = self._resolve_desktop_reference_image(character.get("image"))
            series = self.drama_series.create(
                title, premise, episode_count, scene_count, provider, characters, footage,
                plot_board=plot_board, cover_theme=cover_theme, ai_web_model=ai_web_model,
                visual_style=payload.get("visual_style", "auto"),
                visual_style_custom=payload.get("visual_style_custom", ""),
                render_options=options,
            )
            queued = self.story_queue.enqueue_drama_series(
                series["id"], series["title"], episode_count, provider, scene_count, ai_web_model,
                render_options=options, preserve_state=enqueue_drama_only,
            )
            if payload.get("queue_only") is True:
                self.story_queue.pause()
            if not enqueue_drama_only:
                self.story_queue.resume()
                self._set_ai_web_model(provider, ai_web_model, persist=True)
                self.image_ai_provider.set("Gemini Web" if provider == "gemini" else "ChatGPT Web")
                self.status.set(f"ละครสั้น • เตรียมเริ่ม EP 1/{episode_count}")
            verb = "เพิ่มลงคิว" if enqueue_drama_only else "เริ่มละครสั้น"
            self._desktop_set_notice("success", f"{verb} {title} แล้ว • {episode_count} EP ตามลำดับคิว")
            self._write_console(f"{series['id']} • DRAMA SERIES • {verb} {episode_count} EP • รักษา Character Bible เดิม", "success")
            if not enqueue_drama_only:
                self.root.after(200, self._start_next_story_queue_item)
            return {
                "ok": True,
                "series_id": series["id"],
                "batch_id": queued["batch_id"],
                "queued": len(queued["items"]),
                "enqueue_only": enqueue_drama_only,
                "story_queue": self.story_queue.snapshot(),
            }
        if action == "continue_drama_series":
            if self._story_pipeline_job_id or self._product_pipeline_job_id:
                raise ValueError("มีงานกำลังทำอยู่ กรุณารอให้งานปัจจุบันเสร็จก่อนทำ EP ถัดไป")
            if self.story_queue.snapshot().get("active_count"):
                raise ValueError("ยังมีคิว Story/ละครที่รอทำอยู่ กรุณาทำหรือล้างคิวเดิมก่อน")
            series_audio = (self.drama_series.get(str(payload.get("series_id") or "")).get("render_options") or {}).get("audio_choices") or {}
            if series_audio.get("mode", "api") == "api" and not self.voice_api_key.get().strip():
                raise ValueError("กรุณาตั้งค่า AI Voice API Key ก่อนเริ่ม")
            series_options = (self.drama_series.get(str(payload.get('series_id') or '')).get('render_options') or {})
            series_reference = str(series_options.get('primary_voice_reference_id') or self.voice_reference_id.get()).strip()
            series_file = str(series_options.get('primary_voice_reference_file') or '')
            if series_file and not Path(series_file).is_absolute():
                series_file = str(self.drama_series.folder_path(str(payload.get('series_id') or '')) / series_file)
            series_file = series_file or self.voice_reference_file.get().strip()
            if series_audio.get("mode", "api") == "api" and not series_reference and not Path(series_file).is_file():
                raise ValueError("กรุณาเลือกเสียงต้นแบบก่อนเริ่ม")
            series_id = str(payload.get("series_id") or "").strip()
            appended = self.drama_series.append_episode(
                series_id,
                continuation_prompt=str(payload.get("continuation_prompt") or "").strip(),
                scene_count=payload.get("scene_count"),
            )
            series = appended["series"]
            episode = appended["episode"]
            queued = self.story_queue.enqueue_drama_episode(
                series["id"],
                series["title"],
                episode["episode_no"],
                series["episode_count"],
                series["provider"],
                series["scene_count"],
                ai_web_model=series.get("ai_web_model"),
            )
            self.story_queue.resume()
            self.image_ai_provider.set("Gemini Web" if series["provider"] == "gemini" else "ChatGPT Web")
            self._desktop_set_notice("success", f"เริ่มทำ {series['title']} • EP {episode['episode_no']} ต่อจากข้อมูลเดิมแล้ว")
            self.status.set(f"ละครสั้น • เตรียมเริ่ม EP {episode['episode_no']}/{series['episode_count']}")
            self._write_console(
                f"{series['id']} • CONTINUE SERIES • เริ่ม EP {episode['episode_no']} • ใช้ Character Bible และภาพต่อเนื่องเดิม",
                "success",
            )
            self.root.after(200, self._start_next_story_queue_item)
            return {
                "ok": True,
                "series_id": series["id"],
                "episode_no": episode["episode_no"],
                "batch_id": queued["batch_id"],
                "story_queue": self.story_queue.snapshot(),
            }
        if action == "retry_drama_episode":
            if self._story_pipeline_job_id or self._product_pipeline_job_id:
                raise ValueError("มีงานกำลังทำอยู่ กรุณารอให้งานปัจจุบันเสร็จก่อน")
            if self.story_queue.running_item():
                raise ValueError("มีคิวกำลังทำงานอยู่ กรุณารอให้จบก่อน")
            series_id = str(payload.get("series_id") or "").strip()
            episode_no = int(payload.get("episode_no") or 0)
            reset = self.drama_series.reset_episode_for_retry(series_id, episode_no)
            series = reset["series"]
            episode = reset["episode"]
            provider = str(series.get("last_successful_provider") or series.get("provider") or "chatgpt")
            queued = self.story_queue.enqueue_drama_episode(
                series["id"], series["title"], episode_no, series["episode_count"], provider, series["scene_count"],
                priority=True, ai_web_model=series.get("ai_web_model"),
            )
            self.story_queue.resume()
            self.image_ai_provider.set("Gemini Web" if provider == "gemini" else "ChatGPT Web")
            self._desktop_set_notice("success", f"กำลังกู้ {series['title']} • EP {episode_no} จากโปรเจกต์เดิม")
            self._write_console(
                f"{series['id']} • RETRY EP {episode_no} • กู้ตอนเดิมก่อนเดินคิวต่อ",
                "success",
            )
            self.root.after(200, self._start_next_story_queue_item)
            return {"ok": True, "series_id": series_id, "episode_no": episode_no, "batch_id": queued["batch_id"]}
        if action == "cancel_drama_series":
            series_id = str(payload.get("series_id") or "").strip()
            series = self.drama_series.get(series_id)
            running = self.story_queue.running_item()
            running_job_id = ""
            if running and running.get("mode") == "drama" and running.get("series_id") == series_id:
                running_job_id = str(running.get("job_id") or "")
            if not running_job_id and self._story_pipeline_job_id:
                episode_jobs = {
                    str(episode.get("story_job_id") or "")
                    for episode in series.get("episodes") or []
                }
                if self._story_pipeline_job_id in episode_jobs:
                    running_job_id = self._story_pipeline_job_id
            if running_job_id and running_job_id == self._story_pipeline_job_id:
                self._cancel_story_pipeline()
            queue_result = self.story_queue.cancel_drama_series(series_id)
            series_result = self.drama_series.cancel_series(series_id)
            cancelled = max(int(queue_result.get("cancelled") or 0), int(series_result.get("cancelled") or 0))
            self._desktop_set_notice(
                "success",
                f"ยกเลิกคิว {series.get('title') or series_id} แล้ว {cancelled} EP • ผลงานที่เสร็จแล้วยังอยู่ครบ",
            )
            self.status.set("ละครสั้น AI • ยกเลิกคิวเดิมแล้ว พร้อมสร้างเรื่องใหม่")
            self._write_console(
                f"{series_id} • CANCEL DRAMA SERIES • ยกเลิก {cancelled} EP • เก็บผลงานที่เสร็จแล้ว",
                "success",
            )
            return {
                "ok": True,
                "series_id": series_id,
                "cancelled": cancelled,
                "story_queue": self.story_queue.snapshot(),
                "drama_series": self.drama_series.snapshot(),
            }
        if action == "open_drama_series_folder":
            series_id = str(payload.get("series_id") or "").strip()
            target = self.drama_series.folder_path(series_id)
            if not target.is_dir():
                raise ValueError("ไม่พบโฟลเดอร์โปรเจกต์ละครสั้น")
            self._open_folder(target)
            return {"ok": True}
        if action == "story_queue_clear_finished":
            removed = self.story_queue.clear_finished()
            return {"ok": True, "removed": removed, "story_queue": self.story_queue.snapshot()}
        if action == 'enqueue_long_video':
            from core.long_video import long_video_settings, require_meta_landscape_available
            options = long_video_settings({**(payload.get('long_video') or {}), 'video_generation_mode':payload.get('video_generation_mode','image_motion')})
            if options['video_generation_mode'] == 'meta_ai':
                require_meta_landscape_available()
            result = self.story_queue.enqueue_batch([str(payload.get('topic') or '').strip()],
                story_text=str(payload.get('story_text') or ''), provider=payload.get('provider','chatgpt'),
                video_generation_mode=options['video_generation_mode'], long_video=options, settings=self._creation_capture_settings(payload), queue_only=payload.get('queue_only') is True)
            return {'ok':True, 'queued':True, 'story_queue':self.story_queue.snapshot()}
        if action == "create_story":
            from core.product_script import product_script_options
            script_options = product_script_options(payload.get('product_script_options'), product=bool(
                (payload.get('creative_context') or {}).get('kind') == 'product_story'
                and (payload.get('creative_context') or {}).get('product_short') is True))
            from core.creative_brief import story_structure_options
            structure_options = story_structure_options(payload.get('story_structure_options'))
            if structure_options is not None and (payload.get('long_video') or payload.get('creative_context') or flow_smoke_test):
                raise ValueError('โครงเรื่อง Shorts ใช้กับเรื่องเล่า Shorts ใหม่เท่านั้น')
            from core.generated_music import validate_options as validate_music_options
            music_options = validate_music_options(payload.get('generated_music_options'),
                payload.get('video_generation_mode', 'image_motion'), payload.get('audio_choices'))
            from core.story_performance import validate_option
            from core.storytelling import validate_settings, native_acting
            telling = validate_settings(payload.get('storytelling_options'), payload.get('video_generation_mode', 'image_motion'), payload.get('audio_choices'))
            if telling:
                payload = {**payload, 'actor_dialogue': native_acting(telling)}
            validate_option(payload.get('actor_dialogue', False), payload.get('video_generation_mode', 'image_motion'),
                            payload.get('audio_choices'), telling)
            if payload.get('actor_dialogue') and not telling:
                from core.story_performance import conversation_audio
                payload = {**payload, 'audio_choices': conversation_audio(payload.get('audio_choices'))}
            self._story_fictional_confirmed = payload.get("fictional_ai_characters_confirmed") is True
            self._story_flow_settings = snapshot_flow(payload, self.cfg.get("flow_defaults"))
            from core.ai_cover import ai_cover_options
            self._story_ai_cover_options = ai_cover_options(payload.get('ai_cover_options'))
            from ui.video_intro import capture_intro
            self._story_intro_options = capture_intro(self, payload.get('intro_options'))
            from core.green_screen import GreenLibrary
            self._story_green_options = GreenLibrary(ROOT,self.cfg.get('ffmpeg_path','')).validate(payload.get('green_options'))
            self._story_audio_choices = audio_choices(payload.get("audio_choices"), payload.get("video_generation_mode", "image_motion"))
            self._presenter_story_selection = self._presenter_selection(payload.get("presenter"))
            self._story_visual_style, self._story_visual_style_custom = normalize_story_style(payload.get("visual_style"), payload.get("visual_style_custom"))
            if self._story_pipeline_job_id:
                raise ValueError(f"กำลังทำงาน {self._story_pipeline_job_id} อยู่")
            if self._product_pipeline_job_id:
                raise ValueError(f"กำลังทำสินค้า {self._product_pipeline_job_id} อยู่ กรุณารอหรือยกเลิกก่อน")
            topic = str(payload.get("topic") or "").strip()
            story_text = str(payload.get("story_text") or "").strip()
            if not topic and not story_text:
                raise ValueError("กรุณาใส่หัวข้อหรือรายละเอียดเรื่องอย่างน้อยหนึ่งช่อง")
            if (not self._story_audio_choices or self._story_audio_choices["mode"] == "api") and not self.voice_api_key.get().strip():
                raise ValueError("กรุณาตั้งค่า AI Voice API Key ก่อนเริ่ม")
            selected_reference = str(product_runtime.get('voice_reference_id') or '') if product_runtime is not None else self.voice_reference_id.get().strip()
            selected_reference_file = str(product_runtime.get('voice_reference_file') or '') if product_runtime is not None else self.voice_reference_file.get().strip()
            if (not self._story_audio_choices or self._story_audio_choices["mode"] == "api") and not selected_reference and not Path(selected_reference_file).is_file():
                raise ValueError("กรุณาเลือกเสียงต้นแบบก่อนเริ่ม")
            provider = str(payload.get("provider") or self._image_provider_key()).lower()
            if provider not in {"chatgpt", "gemini"}:
                raise ValueError("ผู้สร้างภาพไม่ถูกต้อง")
            ai_web_model = normalize_ai_web_model(provider, payload.get("ai_web_model") or self._ai_web_model_key(provider))
            self._set_ai_web_model(provider, ai_web_model, persist=True)
            video_generation_mode = str(payload.get("video_generation_mode") or "image_motion").strip().lower()
            if video_generation_mode not in {"image_motion", "google_flow", "meta_ai"}:
                raise ValueError("โหมดสร้างวิดีโอ Story ไม่ถูกต้อง")
            if video_generation_mode == 'meta_ai':
                if payload.get('long_video'):
                    from core.long_video import require_meta_landscape_available
                    require_meta_landscape_available()
                audio_choices(payload.get('audio_choices') or {'mode': 'api'}, 'meta_ai')
            scene_count = max(6, min(15, int(payload.get("scene_count") or 10)))
            if (payload.get('creative_context') or {}).get('product_short') is True:
                from core.product_scene_settings import product_scene_count
                scene_count=product_scene_count(payload.get('scene_count'))
            main_image = self._resolve_desktop_reference_image(payload.get("main_image"))
            if main_image and not Path(main_image).is_file():
                raise ValueError("ไม่พบรูปหลักที่เลือก")
            self.image_ai_provider.set("Gemini Web" if provider == "gemini" else "ChatGPT Web")
            self.story_topic.set(topic)
            self.story_input.delete("1.0", "end"); self.story_input.insert("1.0", story_text)
            self.story_scene_count.set(scene_count)
            self.story_main_image.set(main_image)
            self.story_video_mode.set(next(
                (label for label, key in STORY_VIDEO_MODES.items() if key == video_generation_mode),
                "ภาพเคลื่อนไหวอัตโนมัติ",
            ))
            long_options = payload.get('long_video')
            if long_options is not None:
                from core.long_video import long_video_settings
                long_options = long_video_settings({**long_options, 'video_generation_mode': video_generation_mode})
                self.story_scene_count.set(long_options['scene_count'])
            self._create_story_and_run(long_video=long_options, creative_context=payload.get('creative_context'), actor_dialogue=payload.get('actor_dialogue', False), **({'product_runtime_snapshot':product_runtime} if product_runtime is not None else {}), **({'storytelling_options':telling} if telling is not None else {}), **({'product_script_options':script_options} if script_options is not None else {}), **({'story_structure_options':structure_options} if structure_options is not None else {}), **({'generated_music_options':music_options} if music_options is not None else {}), **({'flow_smoke_test': True} if flow_smoke_test else {}))
            return {"ok": bool(self._story_pipeline_job_id), "job_id": self._story_pipeline_job_id}
        if action == "retry_story":
            job_id = str(payload.get("job_id") or "").strip()
            if not job_id:
                raise ValueError("ไม่พบ Story Job ที่ต้องการทำต่อ")
            self.stories.get(job_id)
            if self._story_pipeline_job_id or self._product_pipeline_job_id:
                raise ValueError("มีงานกำลังทำอยู่ กรุณารอให้งานปัจจุบันเสร็จก่อน")
            self._retry_story_job(job_id, fresh_meta_scene=True)
            return {"ok": bool(self._story_pipeline_job_id == job_id), "job_id": job_id, "accepted": True}
        if action == 'adopt_meta_scene_sequence':
            if payload.get('confirmed') is not True:
                raise ValueError('กรุณายืนยันการเปลี่ยนลำดับรายฉาก')
            reason = self._creation_idle_reason()
            if reason:
                raise ValueError(reason)
            job_id = str(payload.get('job_id') or '')
            self.story_queue.require_not_trashed(job_id)
            from core.meta_scene_sequence import adopt
            job = adopt(self.stories, job_id)
            return {'ok': True, 'job_id': job['id'], 'meta_scene_sequence_version': 1}
        if action == "clear_story_recovery":
            from ui.story_recovery import clear_story_recovery
            return clear_story_recovery(self, payload)
        if action == "dismiss_story_job":
            job_id = str(payload.get("job_id") or "").strip()
            if not job_id:
                raise ValueError("ไม่พบ Story Job ที่ต้องการยกเลิก")
            job = self.stories.get(job_id)
            if str(job.get("job_type") or "story_short") != "story_short":
                raise ValueError("งานละครต้องยกเลิกจากหน้าโปรเจกต์ละครสั้น")
            if job_id == self._story_pipeline_job_id:
                raise ValueError("งานนี้กำลังทำอยู่ กรุณากดยกเลิกจากหน้าความคืบหน้า")
            self.stories.mark_cancelled(job_id, reason="ผู้ใช้ยกเลิกงานเก่าจากหน้ารายการทำต่อ")
            self.story_queue.mark_cancelled_by_job(job_id)
            self._desktop_set_notice("success", "ยกเลิกงานเก่าแล้ว • ไฟล์เดิมยังอยู่และไม่ได้ถูกลบ")
            self._write_console(f"{job_id} • DISMISS STORY • ยกเลิกจากรายการงานที่ต้องทำต่อ", "success")
            return {"ok": True, "job_id": job_id, "status": "cancelled"}
        if action == "cancel_product":
            if manual_flow_job:
                cancel_event = getattr(self, "_manual_multi_flow_cancel_event", None)
                if cancel_event:
                    cancel_event.set()
                try:
                    extension = self.bridge.extension_status()
                    client = next((
                        item for item in list(extension.get("clients") or [])
                        if str(item.get("flow_job_id") or "") == manual_flow_job
                    ), None)
                    shot_index = int((client or {}).get("flow_shot_index") or 0)
                    run_id = str((client or {}).get("flow_run_id") or "")
                    self.bridge.queue_extension_command(
                        "stop_flow_generation", manual_flow_job, shot_index, run_id=run_id
                    )
                except Exception as exc:
                    self._write_console(
                        f"{manual_flow_job} • ขอหยุด Flow แล้ว แต่ส่งคำสั่งปิดหน้าเว็บไม่สำเร็จ • {exc}",
                        "error",
                    )
            if self._product_pipeline_job_id:
                self._cancel_product_pipeline()
            return {"ok": True}
        if action == "cancel_story":
            if self._story_pipeline_job_id:
                running = self.story_queue.running_item()
                if running and running.get("job_id") == self._story_pipeline_job_id:
                    self.story_queue.pause()
                self._cancel_story_pipeline()
            return {"ok": True}
        if action == "focus_verification":
            job_id = str(payload.get("job_id") or self._product_pipeline_job_id or self._story_pipeline_job_id)
            provider = str(payload.get("service") or payload.get("provider") or self._image_provider_key())
            if not job_id:
                raise ValueError("ไม่มีงานที่กำลังรอการยืนยัน")
            if job_id == self._product_verification_job:
                self._focus_product_web_action(job_id)
            else:
                self._focus_ai_verification(job_id, provider)
            return {"ok": True}
        if action == "open_job":
            job_id = str(payload.get("job_id") or "")
            root = self.stories.root if job_id.startswith("STORY-") else self.products.root
            target = (root / job_id).resolve()
            if target.parent != root.resolve() or not target.is_dir():
                raise ValueError("ไม่พบโฟลเดอร์ Job")
            self._open_folder(target)
            return {"ok": True}
        if action == "get_library_detail":
            item_id = str(payload.get("item_id") or "")
            detail = self.video_library.item_detail(item_id)
            base = f"/api/desktop/media?item_id={item_id.replace(':', '%3A')}"
            detail["cover_url"] = base + "&kind=cover&v=" + str(detail.get("cover_revision") or "") if detail.get("cover_path") else ""
            detail["preview_url"] = base + "&kind=preview" if detail.get("preview_path") else ""
            detail["video_url"] = base + "&kind=video"
            return {"ok": True, "detail": detail}
        if action == "save_library_post_metadata":
            item_id = str(payload.get("item_id") or "")
            detail = self.video_library.item_detail(item_id)
            if str(detail.get("job_id") or "") in {
                str(self._product_pipeline_job_id or ""), str(self._story_pipeline_job_id or "")
            }:
                raise ValueError("งานนี้กำลังทำอยู่ กรุณารอให้จบก่อนแก้ข้อความโพสต์")
            self.video_library.save_post_metadata(
                item_id, payload.get("description"), payload.get("hashtags"), payload.get("revision")
            )
            return {"ok": True}
        if action in {"get_cover_editor", "preview_library_cover", "save_library_cover", "download_library_cover"}:
            item_id = str(payload.get("item_id") or "")
            detail = self.video_library.item_detail(item_id)
            if str(detail.get("job_id") or "") in {
                str(self._product_pipeline_job_id or ""), str(self._story_pipeline_job_id or "")
            }:
                raise ValueError("งานนี้กำลังทำอยู่ กรุณารอให้จบก่อนแก้ปก")
            if action == "get_cover_editor":
                return {"ok": True, "editor": self.video_library.cover_editor(item_id)}
            if action == "download_library_cover":
                source = Path(str(detail.get("cover_path") or ""))
                if not source.is_file():
                    raise ValueError("กรุณาบันทึกปกก่อนดาวน์โหลด")
                downloads = Path.home() / "Downloads"
                if not downloads.is_dir():
                    raise ValueError("ไม่พบโฟลเดอร์ Downloads • ใช้ปุ่มเปิดโฟลเดอร์ผลงานแทน")
                target = downloads / f"SmartFlow-cover-{uuid.uuid4().hex[:12]}.jpg"
                shutil.copy2(source, target)
                return {"ok": True, "path": str(target)}
            result = self.video_library.compose_library_cover(item_id, payload.get("settings"),
                payload.get("revision", ""), save=action == "save_library_cover")
            if action == "save_library_cover":
                self._write_console(f"{detail.get('job_id') or item_id} • บันทึกปกใหม่แล้ว • เก็บปกเดิม ไม่สร้างวิดีโอซ้ำ", "info")
            return {"ok": True, **result}
        if action in {"open_library_video", "open_library_cover", "open_library_folder"}:
            detail = self.video_library.item_detail(str(payload.get("item_id") or ""))
            if action == "open_library_video":
                target = Path(detail["path"])
                os.startfile(str(target))
            elif action == "open_library_cover":
                target = Path(str(detail.get("cover_path") or ""))
                if not target.is_file():
                    raise ValueError("ผลงานนี้ยังไม่มีไฟล์ปก Shorts แยก")
                os.startfile(str(target))
            else:
                target = Path(detail["folder"])
                self._open_folder(target)
            return {"ok": True}
        if action == "scan_workspace_junk":
            with self._workspace_cleanup_lock:
                if self._workspace_cleanup_state.get("busy"):
                    raise ValueError("ระบบกำลังเคลียร์ไฟล์อยู่ กรุณารอให้เสร็จก่อน")
                last_result = dict(self._workspace_cleanup_state.get("last_result") or {})
            try:
                summary = self.workspace_cleaner.scan(self._workspace_cleanup_active_jobs())
                summary.update({
                    "busy": False,
                    "error": "",
                    "last_result": last_result,
                    "auto_cleanup_enabled": True,
                })
                with self._workspace_cleanup_lock:
                    self._workspace_cleanup_state = summary
                return {"ok": True, "summary": summary}
            except Exception as exc:
                with self._workspace_cleanup_lock:
                    self._workspace_cleanup_state.update({"busy": False, "error": str(exc)})
                raise
        if action == "clean_workspace_junk":
            if self._workspace_cleanup_active_jobs():
                raise ValueError("มีงานอัตโนมัติกำลังทำอยู่ กรุณารอหรือยกเลิกงานก่อนเคลียร์ไฟล์ขยะ")
            scan_id = str(payload.get("scan_id") or "").strip()
            with self._workspace_cleanup_lock:
                if self._workspace_cleanup_state.get("busy"):
                    raise ValueError("ระบบกำลังเคลียร์ไฟล์อยู่")
                if not scan_id or scan_id != str(self._workspace_cleanup_state.get("scan_id") or ""):
                    raise ValueError("รายการไฟล์ไม่ตรงกับผลสแกนล่าสุด กรุณาสแกนใหม่")
                self._workspace_cleanup_state["busy"] = True
                self._workspace_cleanup_state["error"] = ""
            threading.Thread(target=self._workspace_cleanup_worker, args=(scan_id,), daemon=True).start()
            return {"ok": True, "accepted": True}
        if action in {"delete_library_video", "delete_library_project"}:
            item_id = str(payload.get("item_id") or "")
            self.video_library.item_detail(item_id)
            mode = "project" if action.endswith("project") else "video"
            self._start_desktop_delete(mode, item_id)
            return {"ok": True, "accepted": True}
        if action in {"delete_all_product_projects", "delete_all_library_renders", "delete_completed_projects"}:
            mode = {
                "delete_all_product_projects": "all_products",
                "delete_all_library_renders": "all_renders",
                "delete_completed_projects": "completed_projects",
            }[action]
            self._start_desktop_delete(mode)
            return {"ok": True, "accepted": True}
        if action == "save_quick_settings":
            resolution = str(payload.get("resolution") or "720x1280")
            quality = str(payload.get("quality") or "high")
            fps = int(payload.get('fps', 30))
            encoder = str(payload.get('encoder', self.cfg.get('video_encoder', 'auto')))
            if encoder not in {'auto', 'gpu', 'cpu'}:
                raise ValueError('ตัวเข้ารหัสวิดีโอไม่ถูกต้อง')
            if resolution not in VIDEO_RESOLUTIONS.values() or quality not in VIDEO_QUALITIES.values() or fps not in {0, 24, 30, 50, 60}:
                raise ValueError("ค่าคุณภาพวิดีโอไม่ถูกต้อง")
            self.video_resolution.set(next(label for label, value in VIDEO_RESOLUTIONS.items() if value == resolution))
            self.video_quality.set(next(label for label, value in VIDEO_QUALITIES.items() if value == quality))
            self.video_fps.set(str(fps))
            self.video_encoder.set(encoder)
            self.video_motion_strength.set(max(0, min(200, int(payload.get("motion_percent") or 100))))
            self.video_transition_ms.set(max(0, min(600, int(payload.get("transition_ms") or 220))))
            self.subtitle_auto.set(bool(payload.get("subtitle_auto", self.subtitle_auto.get())))
            provider = str(payload.get("provider") or self._image_provider_key())
            self.image_ai_provider.set("Gemini Web" if provider == "gemini" else "ChatGPT Web")
            self._set_ai_web_model("chatgpt", payload.get("chatgpt_web_model") or self._ai_web_model_key("chatgpt"))
            self._set_ai_web_model("gemini", payload.get("gemini_web_model") or self._ai_web_model_key("gemini"))
            video_provider = "flow"
            self.video_ai_provider.set("Google Flow")
            self._save_video_options(); self._subtitle_option_changed(); self._image_provider_changed()
            self._desktop_set_notice("success", "บันทึกค่าหลักแล้ว งานถัดไปจะใช้ค่านี้")
            return {"ok": True}
        if action == "shutdown":
            self.root.after(120, self._close)
            return {"ok": True}
        raise ValueError("ไม่รู้จักคำสั่งจากหน้าจอ Hybrid")

    def _pipeline_event_is_current(self, mode, payload, allow_cancelled=False):
        """Accept terminal worker output only from its original Job and event."""
        if not isinstance(payload, dict):
            return False
        event = payload.get("cancel_event")
        current_event = getattr(self, f"_{mode}_cancel_event", None)
        if event is None or event is not current_event:
            return False
        job_id = str(payload.get("job_id") or "")
        active_job = str(getattr(self, f"_{mode}_pipeline_job_id", "") or "")
        # Import can fail/cancel before its first progress callback binds the
        # real Product id. Its original event remains the authoritative owner.
        if not active_job or (active_job != job_id and not (
            mode == "product" and active_job == "กำลังสร้าง Job"
        )):
            return False
        return allow_cancelled or not event.is_set()

    def _handle_product_pipeline_ready(self, payload):
        """Finish one Product run without assuming every result has Flow fields."""
        job_id, target, result = payload
        result = dict(result or {})
        if not self._creation_cover_gate(job_id):
            self._product_pipeline_job_id = ""
            self._product_cancel_event = None
            cover = self.bridge.ai_covers.completion(job_id)
            self._finish_product_popup('warning', 'วิดีโอเสร็จแล้ว • '+('รอปก AI' if cover.get('waiting') else 'ปก AI ต้องตรวจสอบ'),
                cover.get('message') or 'เปิดจัดการปกในคลังวิดีโอ • ไม่สร้างคลิปซ้ำ', target)
            if hasattr(self, "product_run_button"):
                self.product_run_button.configure(state="normal")
            return
        self._refresh()
        self._refresh_video_library(f"product:{job_id}")
        self._show_page("library")
        self.status.set(f"คลิปสินค้าพร้อมใช้งาน • {job_id}")
        self._desktop_set_notice("success", f"สร้างคลิปสินค้าสำเร็จ • {job_id}")
        source_type = str(result.get("source_type") or "")
        if source_type == "product_image_sequence_fallback":
            image_count = int(result.get("image_count") or 0)
            summary = f"รูปสินค้าเดิม {image_count} ชุด • {float(result.get('duration') or 0):.1f} วินาที"
        else:
            clip_count = int(result.get("clip_count") or 0)
            summary = f"{clip_count} ช็อต • {float(result.get('duration') or 0):.1f} วินาที"
        self._write_console(f"{job_id} • ONE-CLICK READY • {summary}", "success")
        self._finish_product_popup(
            "success", "สร้างคลิปขายสินค้าสำเร็จ",
            f"แสดงผลงานล่าสุดในคลังแล้ว • {Path(target).name}" + str(result.get('ai_cover_notice') or ''), target,
        )
        self._close_automation_browser(job_id, "สร้างคลิปสำเร็จ")
        self._product_pipeline_job_id = ""
        self._product_cancel_event = None
        self._start_auto_cleanup_completed_job(job_id)
        self._creation_product_terminal(job_id, "completed", output=target)
        self._schedule_next_story_queue_item(500)
        if hasattr(self, "product_run_button"):
            self.product_run_button.configure(state="normal")

    def _poll(self):
        """Keep the UI event loop alive even when one malformed event fails."""
        try:
            self._poll_once()
        except Exception as exc:
            self.log.exception("UI event processing failed")
            self._desktop_set_notice("error", f"อ่านสถานะงานหนึ่งรายการไม่สำเร็จ • {exc}")
            self.status.set("ระบบข้ามสถานะที่ผิดพลาดและทำงานต่อแล้ว")
        finally:
            self.root.after(100, self._poll)

    def _poll_once(self):
        self._poll_desktop_requests()
        while True:
            try: kind, payload = self.events.get_nowait()
            except queue.Empty: break
            if kind in {
                "product_pipeline_ready", "product_pipeline_cancelled", "product_pipeline_error",
                "story_ready", "story_error",
            }:
                mode = "product" if kind.startswith("product_") else "story"
                if not self._pipeline_event_is_current(
                    mode, payload, allow_cancelled=kind == "product_pipeline_cancelled",
                ):
                    continue
                payload = payload.get("value")
            if kind == "device":
                text, badge = payload; self.device.set(text); self.device_badge.set(badge); self.status.set(f"Android • {badge}"); self._write_console(text, "success" if badge == "CONNECTED" else "error")
            elif kind == "desktop_operation":
                level, message = payload
                self._desktop_set_notice(level, message)
                self.status.set(message)
                self._write_console(f"HYBRID • {message}", "success" if level == "success" else "error")
                self._refresh()
            elif kind == "auto_cleanup_complete":
                result = dict(payload or {})
                job_id = str(result.get("job_id") or "JOB")
                if result.get("ok"):
                    deleted = int(result.get("deleted_count") or 0)
                    failed = int(result.get("failed_count") or 0)
                    reclaimed = self._format_file_size(result.get("reclaimed_bytes") or 0)
                    message = f"{job_id} • ตรวจ Final ผ่าน • ล้างไฟล์ขั้นกลาง {deleted} ไฟล์ • คืนพื้นที่ {reclaimed}"
                    if failed:
                        message += f" • ข้ามไฟล์ที่กำลังใช้งาน {failed} ไฟล์"
                    self._write_console(message, "success" if not failed else "log")
                else:
                    self._write_console(
                        f"{job_id} • ไม่ล้างไฟล์อัตโนมัติ เพื่อป้องกันงาน • {result.get('error') or 'Final ยังตรวจไม่ผ่าน'}",
                        "error",
                    )
            elif kind == "product":
                self._refresh(); self.status.set(payload); self._write_console(payload, "success")
            elif kind == "link_imported":
                job, created = payload; self.product_link.set(""); self._refresh(); self._show_page("products")
                message = f"{'สร้าง Product Job ใหม่' if created else 'ลิงก์นี้มีอยู่แล้ว'} • {job['product_name']}"
                self.status.set(message); self._write_console(message, "success")
            elif kind == "voice_reference":
                reference_id, filename = payload
                self.voice_reference_id.set(reference_id)
                save_voice_settings({"voice_reference_id": reference_id})
                if hasattr(self, "voice_catalog_choice"):
                    self.voice_catalog_choice.set(f"เสียงอัปโหลดใหม่ • {filename}")
                    self.voice_catalog_info.set("ใช้ไฟล์เสียงที่อัปโหลดล่าสุด • สามารถกลับไปเลือกเสียงจากระบบได้ทุกเมื่อ")
                self.voice_status.set(f"อัปโหลด {filename} สำเร็จ • ได้ reference_id แล้ว")
                self.status.set("AI Voice • บันทึก reference_id แล้ว")
                self._write_console("AI Voice • อัปโหลดเสียงอ้างอิงสำเร็จ (ไม่บันทึก API Key)", "success")
            elif kind == "voice_catalog":
                self._apply_voice_catalog(payload)
                self._write_console(f"AI Voice • โหลดรายการเสียง {len(payload.get('voices') or [])} เสียง", "success")
            elif kind == "voice_catalog_error":
                message, silent = payload
                self.voice_catalog_info.set(f"โหลดรายการเสียงไม่สำเร็จ • {message}")
                self.status.set("AI Voice • โหลดรายการเสียงไม่สำเร็จ")
                self._write_console(f"AI Voice catalog • {message}", "error")
                if not silent:
                    messagebox.showerror("โหลดรายการเสียงไม่สำเร็จ", message)
            elif kind == "voice_progress":
                self.voice_status.set(payload); self.status.set(f"AI Voice • {payload}"); self._write_console(f"AI Voice • {payload}")
            elif kind == 'story_scene_ready':
                self._start_story_scene_worker(payload)
            elif kind == 'story_saved_scene_done':
                from ui.story_flow_resume import finish_saved_flow_scene
                try:
                    finish_saved_flow_scene(self, payload)
                except Exception as exc:
                    self.events.put(('story_error', {'job_id': payload['job_id'],
                        'cancel_event': payload.get('cancel_event'), 'value': str(exc)}))
            elif kind == "product_pipeline_progress":
                self._update_product_progress(payload)
                self._refresh()
            elif kind == "product_pipeline_ready":
                self._handle_product_pipeline_ready(payload)
            elif kind == "product_pipeline_cancelled":
                job_id = str(payload or self._product_pipeline_job_id)
                if self._product_pipeline_job_id and job_id and self._product_pipeline_job_id != job_id:
                    self._write_console(f"{job_id} • ข้ามผลยกเลิกจาก worker เก่า เพราะมีงาน {self._product_pipeline_job_id} ทำอยู่", "log")
                    continue
                if not self._product_pipeline_job_id and self._product_cancel_event is None:
                    self._write_console(f"{job_id or 'PRODUCT'} • worker ยืนยันการยกเลิกหลังหน้าโปรแกรมปลดสถานะแล้ว", "log")
                    continue
                self._refresh()
                self.status.set(f"ยกเลิกงานแล้ว • {job_id}")
                self._finish_product_popup("cancelled", "ยกเลิกการทำงานแล้ว", "ไฟล์ที่เสร็จแล้วถูกเก็บไว้ กดปุ่มเดิมเพื่อทำต่อได้")
                self._close_automation_browser(job_id, "ยกเลิกงานแล้ว")
                self._product_pipeline_job_id = ""
                self._product_cancel_event = None
                self._creation_product_terminal(job_id, "cancelled", "ผู้ใช้ยกเลิก • เก็บ Checkpoint แล้ว")
                if hasattr(self, "product_run_button"):
                    self.product_run_button.configure(state="normal")
            elif kind == "product_pipeline_error":
                job_id, message = payload
                if job_id:
                    self._product_pipeline_job_id = job_id
                self._refresh()
                self.status.set(f"คลิปสินค้าหยุดที่ Checkpoint • {message}")
                self._write_console(f"{job_id or 'PRODUCT'} • ONE-CLICK STOPPED • {message}", "error")
                # Keep the provider tab open on every failure. Google Flow can
                # still be rendering after a transient extension message, and
                # closing Chrome here destroyed the only recoverable result.
                self._write_console(f"{job_id or 'PRODUCT'} • เก็บแท็บสร้างวิดีโอไว้เพื่อกู้ Checkpoint/ดาวน์โหลดต่อ", "log")
                self._product_pipeline_job_id = ""
                self._product_cancel_event = None
                if hasattr(self, "product_run_button"):
                    self.product_run_button.configure(state="normal")
                queued_failure = self._creation_product_terminal(job_id, "failed", str(message))
                if queued_failure or not self._schedule_product_runtime_recovery(job_id, str(message)):
                    self._capture_automation_error_log(job_id, message, self._product_error_service(job_id, message))
                    self._finish_product_popup("error", "สร้างคลิปยังไม่สำเร็จ", str(message))
            elif kind == "library_renders_deleted":
                self._set_library_delete_state(False)
                self._refresh()
                deleted_count = int(payload.get("deleted_count") or 0)
                failed_count = int(payload.get("failed_count") or 0)
                skipped_count = int(payload.get('skipped_count') or 0)
                job_count = int(payload.get("job_count") or 0)
                if failed_count or skipped_count:
                    message = f"ย้ายลงถังขยะแล้ว {deleted_count} ไฟล์ • ลบไม่สำเร็จ {failed_count} ไฟล์ • ข้ามงานที่ยังใช้ไฟล์ {skipped_count} รายการ"
                    self.library_status.set(message)
                    self.status.set(message)
                    self._write_console(f"VIDEO LIBRARY • {message}", "error")
                    messagebox.showwarning("เคลียร์ไฟล์ได้บางส่วน", f"{message}\n\nไฟล์ที่ลบสำเร็จอยู่ในถังขยะ Windows")
                else:
                    message = f"ย้ายไฟล์เรนเดอร์ {deleted_count} ไฟล์ จาก {job_count} หัวข้อลงถังขยะแล้ว"
                    self.library_status.set(message)
                    self.status.set(message)
                    self._write_console(f"VIDEO LIBRARY • {message}", "success")
                    messagebox.showinfo("เคลียร์ไฟล์เรนเดอร์แล้ว", f"{message}\n\nรูป บทพูด เสียง และข้อมูลโปรเจกต์ยังอยู่ครบ")
            elif kind == "library_delete_error":
                self._set_library_delete_state(False)
                self._refresh_video_library()
                self._write_console(f"VIDEO LIBRARY DELETE • {payload}", "error")
                messagebox.showerror("เคลียร์ไฟล์เรนเดอร์ไม่สำเร็จ", str(payload))
            elif kind == "projects_deleted":
                self._set_project_delete_state(False)
                self._refresh()
                deleted_count = int(payload.get("deleted_count") or 0)
                failed_count = int(payload.get("failed_count") or 0)
                skipped_count = int(payload.get('skipped_count') or 0)
                file_count = int(payload.get("deleted_file_count") or 0)
                size_text = self._format_file_size(payload.get("deleted_size_bytes") or 0)
                if failed_count or skipped_count:
                    message = f"ลบสำเร็จ {deleted_count} โปรเจกต์ • ไม่สำเร็จ {failed_count} โปรเจกต์ • ข้ามงานที่ยังใช้ไฟล์ {skipped_count} รายการ"
                    failures = payload.get("failures") or []
                    reason_lines = [
                        f"• {row.get('job_id', 'ไม่ทราบ Job')}: {row.get('error', 'ไม่ทราบสาเหตุ')}"
                        for row in failures[:5]
                    ]
                    reason_text = "\n\nสาเหตุที่ตรวจพบ:\n" + "\n".join(reason_lines) if reason_lines else ""
                    if failed_count > len(reason_lines):
                        reason_text += f"\n• และอีก {failed_count - len(reason_lines)} โปรเจกต์ (ดูรายละเอียดในหน้า Log)"
                    self.status.set(message)
                    self._write_console(f"PROJECT CLEANUP • {message}{reason_text}", "error")
                    if deleted_count:
                        messagebox.showwarning(
                            "ลบโปรเจกต์ได้บางส่วน",
                            f"{message}{reason_text}\n\nโปรเจกต์ที่ลบสำเร็จถูกย้ายลงถังขยะ Windows แล้ว",
                        )
                    else:
                        messagebox.showerror(
                            "ลบโปรเจกต์ไม่สำเร็จ",
                            f"{message}{reason_text}\n\nรอให้งานที่ใช้ไฟล์จบ และนำงานที่ยังอยู่ในคิวออกก่อนลบ",
                        )
                else:
                    message = f"ย้าย {deleted_count} โปรเจกต์ • {file_count} ไฟล์ • {size_text} ลงถังขยะแล้ว"
                    self.status.set(message)
                    self._write_console(f"PROJECT CLEANUP • {message} • แถว Job ถูกนำออกแล้ว", "success")
                    messagebox.showinfo("ลบโปรเจกต์เรียบร้อย", f"{message}\n\nแถว Job ถูกนำออกจากหน้าสินค้า/Story แล้ว\nสามารถกู้คืนโฟลเดอร์ได้จากถังขยะ Windows")
            elif kind == "project_delete_error":
                self._set_project_delete_state(False)
                self._refresh()
                self._write_console(f"PROJECT CLEANUP • {payload}", "error")
                messagebox.showerror("ลบโปรเจกต์ไม่สำเร็จ", str(payload))
            elif kind == "story_progress":
                self._update_story_progress(payload)
            elif kind == "story_flow_progress":
                self._update_story_flow_progress(payload)
            elif kind == "story_ai_ready":
                job = payload
                if job.get('cast_creation'):
                    self.product_cast.save_generated(self.stories.root/job['id'],job)
                    job['status']='asset_ready'
                    self.stories._save(job)
                    self._story_pipeline_job_id=''
                    self.story_run_button.configure(state='normal')
                    self._update_story_progress({'percent':100,'stage':'complete','message':'ภาพนายแบบ / นางแบบพร้อมแล้ว','detail':'ไปที่ตกแต่งคลิป → นายแบบ / นางแบบสินค้า เพื่อกดบันทึก'})
                    self._close_automation_browser(job['id'],'บันทึกภาพนายแบบ/นางแบบแล้ว')
                    continue
                if job.get("series_id"):
                    try:
                        series_job = dict(job)
                        series_job["_folder"] = str(self.stories.root / job["id"])
                        self.drama_series.update_from_story(series_job)
                        self._write_console(
                            f"{job['series_id']} • EP {job.get('episode_no')} • บันทึก Character Bible และ Continuity สำหรับตอนถัดไป",
                            "success",
                        )
                    except Exception as exc:
                        self.log.warning("job_id=%s state=DRAMA_CONTINUITY result=error error=%s", job.get("id"), exc)
                provider_name = "Gemini Web" if job.get("image_ai_provider") == "gemini" else "ChatGPT Web"
                self._refresh(); self.story_job_id.set(job["id"]); self._load_story_job()
                if self._story_pipeline_job_id == job["id"] and self._story_cancel_event and not self._story_cancel_event.is_set():
                    self._update_story_progress({"percent": 60, "stage": "voice", "message": "บทและภาพประกอบครบแล้ว", "detail": job.get("image_fallback_notice") or f"ได้รับภาพจริง {len(job.get('generated_images') or [])}/{job.get('scene_count')} ฉาก • เริ่มสร้างเสียงอัตโนมัติ"})
                    self.root.after(300, self._render_story)
                else:
                    self.story_status.set(f"{job['id']} • รับผลจาก {provider_name} แล้ว แต่ไม่ได้เริ่มขั้นต่อไปเพราะงานถูกยกเลิก")
            elif kind == "story_ready":
                job, target, plan = payload
                if not Path(target).is_file() or Path(target).stat().st_size <= 0:
                    self.events.put(("story_error", {"job_id": job["id"], "cancel_event": self._story_cancel_event, "value": "ไม่พบไฟล์ Final ที่พร้อมใช้งาน"}))
                    continue
                if not self._creation_cover_gate(job["id"]):
                    self._story_render_active = None
                    self._story_pipeline_job_id = ""
                    self._story_cancel_event = None
                    cover = self.bridge.ai_covers.completion(job['id'])
                    self._finish_story_popup('warning', 'วิดีโอเสร็จแล้ว • '+('รอปก AI' if cover.get('waiting') else 'ปก AI ต้องตรวจสอบ'),
                        cover.get('message') or 'เปิดจัดการปกในคลังวิดีโอ • ไม่สร้างคลิปซ้ำ', target)
                    if hasattr(self, "story_run_button"):
                        self.story_run_button.configure(state="normal")
                    continue
                queue_item = self.story_queue.mark_completed_by_job(job["id"], target)
                self._creation_dispatch_item = None
                if job.get("series_id"):
                    try:
                        series_job = dict(job)
                        series_job["_folder"] = str(self.stories.root / job["id"])
                        self.drama_series.mark_episode_ready(series_job, target)
                        self._write_console(
                            f"{job['series_id']} • EP {job.get('episode_no')} READY • ตอนถัดไปจะใช้ภาพอ้างอิงและข้อมูลต่อเนื่องชุดล่าสุด",
                            "success",
                        )
                    except Exception as exc:
                        self.log.warning("job_id=%s state=DRAMA_READY result=error error=%s", job.get("id"), exc)
                if queue_item and queue_item.get("mode") == "drama":
                    snapshot = self.story_queue.snapshot()
                    if snapshot.get("pause_reason") == self._drama_queue_pause_reason(queue_item):
                        self.story_queue.resume()
                        self._write_console(
                            f"{queue_item.get('series_id')} • EP {queue_item.get('episode_no')} RECOVERED • ทำ EP ถัดไปต่ออัตโนมัติ",
                            "success",
                        )
                self._story_render_active = None
                self._refresh(); self.story_job_id.set(job["id"]); self._load_story_job()
                self.story_status.set(f"{job['id']} • พร้อมแล้ว {plan['scene_count']} ฉาก • {plan['duration']:.1f} วินาที")
                self.status.set("Story Shorts พร้อมใช้งาน")
                self._write_console(f"{job['id']} • STORY READY • {plan['scene_count']} ฉาก • มีเสียงพากย์", "success")
                fallback_notice = str(job.get("image_fallback_notice") or "")
                if (job.get('ai_cover_state') or {}).get('phase') in {'needs_review','cancelled'}:
                    fallback_notice += ' • วิดีโอเสร็จแล้ว แต่ปก AI ยังไม่สำเร็จ • ใช้ปกเดิมอยู่'
                if fallback_notice:
                    self._write_console(f"{job['id']} • STORY IMAGE FALLBACK • {fallback_notice}", "warning")
                self._finish_story_popup("success", "สร้าง Story Shorts สำเร็จ", f"{plan['scene_count']} ฉาก • {plan['duration']:.1f} วินาที • {Path(target).name}" + (f" • {fallback_notice}" if fallback_notice else ""), target)
                self._close_automation_browser(job["id"], "สร้าง Story Shorts สำเร็จ")
                self._story_pipeline_job_id = ""
                self._story_cancel_event = None
                self._start_auto_cleanup_completed_job(job["id"])
                if hasattr(self, "story_run_button"):
                    self.story_run_button.configure(state="normal")
                if queue_item:
                    snapshot = self.story_queue.snapshot()
                    done = snapshot["counts"]["completed"]
                    self.status.set(f"คิวสร้างคลิป • สำเร็จ {done}/{snapshot['total_count']} คลิป")
                self._schedule_next_story_queue_item(2200)
            elif kind == "story_error":
                job_id = self._story_pipeline_job_id or self.story_job_id.get().strip()
                self._story_render_active = None
                raw_error = str(payload.get("value") or "") if isinstance(payload, dict) else str(payload)
                trace = (self.bridge.extension_status().get("trace") or []) if job_id else []
                review_notice = (story_existing_draft_notice(job_id, raw_error, trace)
                    or story_image_refusal_notice(job_id, raw_error, trace)) if job_id else ""
                reported_error = review_notice or str(payload)
                keep_ai_draft_open = (bool(review_notice)
                    or any(code in raw_error for code in ("AI_WEB_WAIT_REVIEW", "AI_WEB_RESUME_REVIEW",
                                                        "STORY_IMAGE_PROGRESS_STALLED", "STORY_IMAGE_STALL_REVIEW"))
                    or self._should_keep_story_ai_draft(job_id, payload))
                if job_id and not keep_ai_draft_open and self._schedule_story_recovery(job_id, reported_error):
                    continue
                try:
                    error_job = self.stories.get(job_id)
                except Exception:
                    error_job = {}
                from core.meta_error_report import story_service_label
                self._capture_automation_error_log(job_id, reported_error, story_service_label(error_job))
                if job_id:
                    try:
                        stage = str(self.stories.get(job_id).get("pipeline_stage") or "")
                        self.stories.mark_failed(job_id, stage, reported_error)
                    except Exception as exc:
                        self.log.warning("job_id=%s state=STORY_MARK_FAILED result=error error=%s", job_id, exc)
                self.story_status.set(f"Story Shorts ผิดพลาด • {reported_error}")
                self.status.set("Story Shorts ทำงานไม่สำเร็จ")
                self._write_console(f"STORY • {reported_error}", "error")
                queue_item = self.story_queue.mark_failed_by_job(job_id, reported_error) if job_id else None
                self._creation_story_failure(queue_item, reported_error)
                if queue_item and queue_item.get("mode") == "drama":
                    self._pause_failed_drama_episode(queue_item, reported_error)
                self._finish_story_popup("error", "สร้าง Story Shorts ไม่สำเร็จ", reported_error)
                keep_flow_open = False
                if job_id:
                    try:
                        keep_flow_open = str(self.stories.get(job_id).get("video_generation_mode") or "") == "google_flow"
                    except Exception:
                        keep_flow_open = False
                if keep_ai_draft_open:
                    self._write_console(
                        f"{job_id} • AI CHECKPOINT REVIEW • คงแท็บ AI คำตอบและ Prompt เดิมไว้ให้ตรวจ • ไม่ส่งซ้ำอัตโนมัติ",
                        "log",
                    )
                elif keep_flow_open:
                    self._write_console(
                        f"{job_id} • GOOGLE FLOW CHECKPOINT • คง Chrome ไว้ให้ตรวจและกดทำต่อ",
                        "log",
                    )
                else:
                    self._close_automation_browser(job_id, "Story Shorts หยุดที่ Checkpoint")
                self._story_pipeline_job_id = ""
                self._story_cancel_event = None
                if hasattr(self, "story_run_button"):
                    self.story_run_button.configure(state="normal")
                if queue_item:
                    if queue_item.get("mode") == "drama":
                        self._write_console(f"DRAMA QUEUE • หยุดที่ {job_id} • ไม่ข้ามไป EP ถัดไป", "error")
                    else:
                        self._write_console(f"CREATION QUEUE • พักที่ {job_id} • ตรวจข้อผิดพลาดแล้วกดทำต่อ", "error")
                if not queue_item or queue_item.get("mode") != "drama":
                    self._schedule_next_story_queue_item(2500)
            elif kind == "story_cancelled":
                self._handle_story_cancelled(payload)
            elif kind == "service_credits":
                states, silent = payload
                self._service_credit_refreshing = False
                for service in ("voice", "subtitle"):
                    if service in states:
                        self._service_credit_state[service] = states[service]
                connected = [name for name, state in states.items() if state.get("connected")]
                failed = [name for name, state in states.items() if state.get("configured") and not state.get("connected")]
                if connected:
                    self._write_console("CREDIT • อัปเดตยอด AI Voice / Subtitle แล้ว", "success")
                if failed and not silent:
                    self._desktop_set_notice("error", "ตรวจเครดิตบางบริการไม่สำเร็จ กรุณาตรวจการเชื่อมต่อ")
                self._refresh()
            elif kind == "voice_ready":
                job, target = payload
                self._refresh()
                self.voice_status.set(f"{job['id']} • สร้างเสียงเสร็จแล้ว")
                self.status.set(f"AI Voice พร้อม • {target.name}")
                self._write_console(f"{job['id']} • AI Voice พร้อม • {target.name}", "success")
                self.root.after(250, lambda: self._refresh_service_credits(force=True, silent=True))
                if self.subtitle_auto.get() and job.get("subtitle_status") not in {"queued", "ready"}:
                    try:
                        if self._subtitle_store().load():
                            self.subtitle_job_id.set(job["id"])
                            self.root.after(300, lambda job_id=job["id"]: self._start_subtitle_for_job(job_id))
                    except Exception as exc:
                        self.log.warning("state=SUBTITLE_AUTO result=skip error=%s", exc)
            elif kind == "voice_error":
                self.voice_status.set(f"ผิดพลาด • {payload}")
                self.status.set("AI Voice สร้างไม่สำเร็จ • ตรวจข้อความแจ้งเตือน")
                self._write_console(f"AI Voice • {payload}", "error")
                messagebox.showerror("AI Voice สร้างไม่สำเร็จ", payload)
            elif kind == "subtitle_connected":
                self.subtitle_token.set("")
                self.subtitle_credential_saved.set("✓ เชื่อมต่อแล้ว • เก็บรหัสใน Windows")
                self.subtitle_status.set("เชื่อมต่อสำเร็จ • พร้อมสร้างคำบรรยาย")
                self.status.set("AI Subtitle • บันทึกรหัสอุปกรณ์ใน Windows แล้ว")
                self._write_console("AI Subtitle • เชื่อมต่อ SmartSub Online สำเร็จ (ไม่บันทึก Token)", "success")
                self.root.after(120, lambda: self._refresh_service_credits(force=True, silent=True))
                self.root.after(300, self._resume_pending_subtitles)
            elif kind == "subtitle_preview_ready":
                token, target, video_target = payload
                target = Path(target)
                video_target = Path(video_target)
                if token == self._subtitle_preview_token and target.is_file() and video_target.is_file():
                    self._subtitle_preview_busy = False
                    self._subtitle_preview_error_message = ""
                    if self.hybrid_engine:
                        self.subtitle_preview_meta.set("พรีวิวจริงพร้อมแล้ว • แอนิเมชันและฟอนต์เดียวกับวิดีโอ")
                    else:
                        with Image.open(target) as source:
                            self._subtitle_preview_source_image = source.convert("RGB").copy()
                        self._subtitle_preview_dimensions = None
                        self._resize_subtitle_visual_preview()
                elif self.hybrid_engine:
                    target.unlink(missing_ok=True)
                    video_target.unlink(missing_ok=True)
                if not self.hybrid_engine:
                    target.unlink(missing_ok=True)
                    video_target.unlink(missing_ok=True)
            elif kind == "subtitle_preview_error":
                token, message, target, video_target = payload
                if token == self._subtitle_preview_token:
                    self._subtitle_preview_busy = False
                    self._subtitle_preview_error_message = str(message)
                    self._subtitle_preview_source_image = None
                    self._subtitle_preview_dimensions = None
                    self.subtitle_status.set(f"สร้างพรีวิว Subtitle ไม่สำเร็จ • {message}")
                    self._write_console(f"SUBTITLE PREVIEW • {message}", "error")
                    if hasattr(self, "subtitle_visual_preview"):
                        try:
                            self.subtitle_visual_preview.configure(image="", text=f"แสดงพรีวิวไม่ได้\n{message}", fg=COLORS["danger"])
                        except tk.TclError:
                            pass
                else:
                    Path(target).unlink(missing_ok=True)
                    Path(video_target).unlink(missing_ok=True)
            elif kind == "subtitle_progress":
                self.subtitle_status.set(payload)
                self.status.set(f"AI Subtitle • {payload}")
                self._write_console(f"AI Subtitle • {payload}")
            elif kind == "subtitle_ready":
                job, paths = payload
                self._subtitle_active_job = None
                self._refresh()
                self.subtitle_job_id.set(job["id"])
                self._load_subtitle_job()
                self.subtitle_status.set(f"{job['id']} • คำบรรยายพร้อมแล้ว")
                self.status.set("AI Subtitle พร้อม • บันทึกในโฟลเดอร์ captions แล้ว")
                self._write_console(f"{job['id']} • Subtitle พร้อม • {', '.join(paths)}", "success")
                self.root.after(120, lambda: self._refresh_service_credits(force=True, silent=True))
                messagebox.showinfo("สร้างคำบรรยายสำเร็จ", "บันทึก Transcript และไฟล์คำบรรยายไว้ในโฟลเดอร์ captions แล้ว")
                self.root.after(200, lambda job_id=job["id"]: self._maybe_render_subtitles(job_id))
                self.root.after(500, self._resume_pending_subtitles)
            elif kind == "subtitle_error":
                job_id = self._subtitle_active_job or self.subtitle_job_id.get().strip()
                self._subtitle_active_job = None
                if job_id:
                    self.products.mark_subtitle_error(job_id, payload)
                self.subtitle_status.set(f"ผิดพลาด • {payload}")
                self.status.set("AI Subtitle สร้างไม่สำเร็จ")
                self._write_console(f"AI Subtitle • {payload}", "error")
                messagebox.showerror("สร้าง Subtitle ไม่สำเร็จ", payload)
                self.root.after(500, self._resume_pending_subtitles)
            elif kind == "subtitle_video_ready":
                job, result = payload
                self._subtitle_render_active = None
                self._refresh()
                self.subtitle_status.set(f"{job['id']} • Subtitle พร้อมและใส่ในวิดีโอแล้ว")
                self.status.set("วิดีโอพร้อม Subtitle แล้ว")
                self._write_console(f"{job['id']} • ใส่ Subtitle ลง {Path(result['output']).name} สำเร็จ", "success")
                self.audio_job_id.set(job["id"])
                if self.audio_background_enabled.get() or self.audio_sfx_enabled.get():
                    self.root.after(250, lambda job_id=job["id"]: self._maybe_mix_audio(job_id, force=True))
                self.root.after(500, self._resume_pending_subtitles)
            elif kind == "subtitle_video_error":
                job_id, message = payload
                self._subtitle_render_active = None
                self.products.mark_subtitle_video_error(job_id, message)
                self.subtitle_status.set(f"{job_id} • ใส่ Subtitle ในวิดีโอไม่สำเร็จ")
                self._write_console(f"AI Subtitle Video • {message}", "error")
            elif kind == "audio_mix_ready":
                job, plan = payload
                self._audio_render_active = None
                self._refresh()
                self.audio_job_id.set(job["id"])
                self.audio_status.set(f"{job['id']} • ผสมเพลง {len(plan['music_plan'])} ช่วง + เสียงข้อความ {len(plan['sfx_events'])} จุดแล้ว")
                self.status.set("วิดีโอพร้อมเพลงพื้นหลังและเสียงข้อความแล้ว")
                self._write_console(f"{job['id']} • AUDIO MIX • เพลง {len(plan['music_plan'])} ช่วง • SFX {len(plan['sfx_events'])} จุด", "success")
            elif kind == "audio_mix_error":
                job_id, message = payload
                self._audio_render_active = None
                self.products.mark_audio_mix_error(job_id, message)
                self.audio_status.set(f"{job_id} • ผสมเสียงไม่สำเร็จ")
                self._write_console(f"AUDIO MIX • {message}", "error")
                messagebox.showerror("ผสมเสียงประกอบไม่สำเร็จ", message)
            elif kind == 'logo_editor_preview':
                self._accept_logo_editor_preview(payload)
            elif kind == "logo_preview":
                frame, preview, source_name, asset_id = payload
                self._logo_frame_cache = frame
                self._logo_preview_asset_id = asset_id
                self._logo_preview_token += 1
                self._display_logo_preview(preview)
                self.logo_status.set(f"ตัวอย่างจาก {source_name} • ปรับค่าได้ทันที")
                self.status.set("พร้อมจัดวางโลโก้")
            elif kind == "logo_ready":
                job, result = payload
                self._refresh()
                self.logo_status.set(f"{job['id']} • สร้าง {Path(result['output']).name} สำเร็จ")
                self.status.set("วิดีโอใส่โลโก้พร้อมแล้ว")
                self._write_console(f"{job['id']} • ใส่โลโก้ {result['position_label']} • ทึบ {round(result['opacity']*100)}%", "success")
                messagebox.showinfo("ใส่โลโก้สำเร็จ", f"บันทึกเป็น {Path(result['output']).name}\nไฟล์ต้นฉบับยังอยู่ครบ")
            elif kind == "logo_error":
                self.logo_status.set(f"ผิดพลาด • {payload}")
                self.status.set("สร้างวิดีโอใส่โลโก้ไม่สำเร็จ")
                self._write_console(f"VIDEO LOGO • {payload}", "error")
                messagebox.showerror("ใส่โลโก้ไม่สำเร็จ", payload)
            elif kind == "presenter_trace":
                self._write_console(payload, "log")
            elif kind == "flow_failure_notice":
                self._capture_flow_failure_notice(payload)
            elif kind == "multi_flow_progress":
                self.status.set(f"MULTI FLOW ×3 • {payload}")
                self._write_console(payload)
            elif kind == "flow_login_required":
                job_id, shot_index, message, *total_value = payload
                total_shots = int(total_value[0]) if total_value else 3
                self.status.set(f"Google Flow • รอเข้าสู่ระบบ • {job_id}")
                self._write_console(f"{job_id} • ช็อต {shot_index}/{total_shots} • {message}", "error")
                messagebox.showwarning(
                    "กรุณาเข้าสู่ระบบ Google Flow",
                    f"{message}\n\nChrome เปิดหน้าที่ต้องดำเนินการไว้แล้ว\nเมื่อล็อกอินเสร็จ ระบบจะทำช็อต {shot_index}/{total_shots} ต่อเอง",
                )
            elif kind == "flow_rights_required":
                job_id, shot_index, message, *total_value = payload
                total_shots = int(total_value[0]) if total_value else 3
                self.status.set(f"Google Flow • รอกดยอมรับสิทธิ์รูป • {job_id}")
                self._write_console(f"{job_id} • ช็อต {shot_index}/{total_shots} • {message}", "error")
                self._show_story_verification_required(job_id, "flow", "legal_rights", message)
                self.bridge.queue_extension_command("focus_flow_web", job_id, shot_index)
                messagebox.showwarning(
                    "กรุณากด “ฉันยอมรับ” ใน Google Flow",
                    f"{message}\n\nโปรแกรมหยุดรออยู่และจะไม่กดยกเลิก\n"
                    f"กด “ฉันยอมรับ” ใน Chrome แล้วระบบจะทำช็อต {shot_index}/{total_shots} ต่อจากรูปเดิมอัตโนมัติ",
                )
            elif kind == "flow_credit_exhausted":
                job_id, shot_index, message, *total_value = payload
                total_shots = int(total_value[0]) if total_value else 3
                self.status.set(f"Google Flow • เครดิตหมด • {job_id}")
                self._write_console(f"{job_id} • ช็อต {shot_index}/{total_shots} • {message}", "error")
                messagebox.showwarning(
                    "เครดิต Google Flow หมดหรือไม่เพียงพอ",
                    f"{message}\n\nเปลี่ยนบัญชี Google หรือเติมเครดิตก่อน แล้วกดทำต่อ Job เดิม\nรูป เสียง และช็อตที่เสร็จแล้วไม่ถูกลบ",
                )
            elif kind == "multi_flow_ready":
                job_id, target, result = payload
                self._refresh()
                self.status.set(f"MULTI FLOW ×3 พร้อม • {job_id}")
                self._write_console(f"{job_id} • รวม {result['clip_count']} ช็อต • {result['duration']:.1f} วินาที", "success")
                messagebox.showinfo("MULTI FLOW ×3 เสร็จแล้ว", f"รวมวิดีโอ 3 ช็อตเรียบร้อย\nไฟล์: {Path(target).name}\nระยะเวลา: {result['duration']:.1f} วินาที")
                self.root.after(200, lambda active_job=job_id: self._maybe_render_subtitles(active_job))
            elif kind == "multi_flow_error":
                self.status.set(f"MULTI FLOW ×3 ผิดพลาด • {payload}")
                self._write_console(f"MULTI FLOW ×3 • {payload}", "error")
                messagebox.showerror("MULTI FLOW ×3 ไม่สำเร็จ", payload)
            elif kind == "effect_ready":
                job, target, result = payload
                self._refresh()
                self.status.set(f"เอฟเฟกต์สินค้าพร้อม • {job['id']}")
                self._write_console(f"{job['id']} • {result['preset_label']} • วงแหวน + ลูกศร + การ์ดข้อมูล", "success")
                messagebox.showinfo("ใส่เอฟเฟกต์สำเร็จ", f"สร้างกราฟิกเน้นสินค้าเรียบร้อย\nไฟล์: {Path(target).name}")
            elif kind == "effect_error":
                self.status.set(f"เอฟเฟกต์สินค้าผิดพลาด • {payload}")
                self._write_console(f"VIDEO EFFECT • {payload}", "error")
                messagebox.showerror("ใส่เอฟเฟกต์ไม่สำเร็จ", payload)
            elif kind == "error":
                self.status.set(f"ผิดพลาด • {payload}"); self._write_console(payload, "error")
            else:
                self.status.set(payload); self._write_console(payload)

    def _periodic_refresh(self):
        self._refresh_service_credits(force=False, silent=True)
        self._refresh(); self.root.after(15000, self._periodic_refresh)

    def _hide_legacy(self):
        """Hide the compatibility workspace without stopping the Hybrid app."""
        if self.hybrid_engine:
            self.root.withdraw()
            self._desktop_set_notice("info", "ปิดเครื่องมือแบบละเอียดแล้ว หน้าหลักยังทำงานต่อ")
        else:
            self._close()

    def _close(self):
        self._browser_connection_closing = True
        if getattr(self, "_native_audio_cancel", None):
            self._native_audio_cancel.set()
            worker = getattr(self, "_native_audio_worker", None)
            if worker is not None and worker.is_alive():
                worker.join(timeout=3)
        if getattr(self, "_presenter_cancel", None):
            self._presenter_cancel.set()
        if self._story_cancel_event:
            self._story_cancel_event.set()
        if self._product_cancel_event:
            self._product_cancel_event.set()
        try:
            if getattr(self, 'membership', None):
                self.membership.close()
            self.bridge.stop()
        finally:
            try:
                self.root.destroy()
            except tk.TclError:
                pass

    def run(self):
        self.root.mainloop()
