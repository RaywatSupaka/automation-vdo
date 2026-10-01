import json
import queue
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from core.external_tts import ExternalTtsClient, ExternalTtsError
from core.product_manager import ProductManager
from core.thai_tts import prepare_thai_tts_script, thai_number_words
from ui.main_window import MainWindow


class _TtsHandler(BaseHTTPRequestHandler):
    polls = 0
    seen_auth = []
    seen_idempotency = []
    synthesize_bodies = []

    def log_message(self, format, *args):
        pass

    def _send_json(self, payload):
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        self.__class__.seen_auth.append(self.headers.get("X-API-Key"))
        self.__class__.seen_idempotency.append(self.headers.get("Idempotency-Key"))
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path.endswith("/upload-reference"):
            assert b'name="file"' in body
            self._send_json({"reference_id": "REF-TEST-1", "filename": "sample.wav"})
        elif self.path.endswith("/synthesize"):
            assert self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded")
            assert b"text=" in body and b"reference_id=" in body
            self.__class__.synthesize_bodies.append(body.decode("utf-8"))
            self._send_json({"job_id": "TTS-JOB-1", "status": "queued"})
        else:
            self.send_error(404)

    def do_GET(self):
        self.__class__.seen_auth.append(self.headers.get("X-API-Key"))
        if self.path.endswith("/external/voices"):
            self._send_json({
                "voices": [
                    {"id": "warm_male", "reference_id": "preset:warm_male", "source": "preset", "name": "ชายอบอุ่น", "allowed_emotions": ["normal", "sad"]},
                    {"id": "brand_voice", "reference_id": "custom:brand_voice", "source": "custom", "custom": True, "name": "เสียงร้านของฉัน", "allowed_emotions": ["normal"]},
                ],
                "count": 2, "preset_count": 1, "custom_count": 1,
            })
        elif self.path.endswith("/external/status"):
            self._send_json({
                "ok": True,
                "connected": True,
                "creditsRemaining": 245,
                "unlimited": False,
                "creditPeriodEnd": "2026-09-30T00:00:00Z",
                "planCode": "creator",
                "planName": "Creator",
            })
        elif "/job/" in self.path:
            self.__class__.polls += 1
            if self.__class__.polls < 2:
                self._send_json({"job_id": "TTS-JOB-1", "status": "processing"})
            else:
                self._send_json({"job_id": "TTS-JOB-1", "status": "done", "output_id": "OUT-1"})
        elif "/download/" in self.path:
            raw = b"ID3\x04mock-audio"
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_error(404)


class ExternalTtsTests(unittest.TestCase):
    def setUp(self):
        _TtsHandler.polls = 0
        _TtsHandler.seen_auth = []
        _TtsHandler.seen_idempotency = []
        _TtsHandler.synthesize_bodies = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _TtsHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_complete_reference_synthesis_poll_and_download_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sample = root / "sample.wav"
            sample.write_bytes(b"RIFFmock-wave")
            client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)

            uploaded = client.upload_reference(sample)
            queued = client.synthesize("สวัสดีครับ [pause:0.5] ทดลองเสียง", uploaded["reference_id"])
            _, output_id = client.wait_until_done(queued["job_id"], timeout=3, poll_interval=0.01)
            target = client.download(output_id, root / "voice.mp3", "mp3")

            self.assertEqual(uploaded["reference_id"], "REF-TEST-1")
            self.assertEqual(output_id, "OUT-1")
            self.assertTrue(target.read_bytes().startswith(b"ID3"))
            self.assertTrue(_TtsHandler.seen_auth)
            self.assertEqual(set(_TtsHandler.seen_auth), {"vc_live_secret"})
            self.assertNotIn("vc_live_secret", repr(client))

    def test_lists_preset_and_owner_custom_voices(self):
        client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)
        catalog = client.list_voices()

        self.assertEqual(catalog["count"], 2)
        self.assertEqual(catalog["preset_count"], 1)
        self.assertEqual(catalog["custom_count"], 1)
        self.assertEqual(catalog["voices"][0]["reference_id"], "preset:warm_male")
        self.assertEqual(catalog["voices"][1]["reference_id"], "custom:brand_voice")
        self.assertEqual(set(_TtsHandler.seen_auth), {"vc_live_secret"})

    def test_reads_voice_credit_status_without_exposing_key(self):
        client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)
        status = client.get_status()

        self.assertTrue(status["connected"])
        self.assertEqual(status["credits"], 245)
        self.assertFalse(status["unlimited"])
        self.assertEqual(status["plan_name"], "Creator")
        self.assertNotIn("vc_live_secret", repr(status))

    def test_selected_catalog_reference_is_sent_to_synthesize(self):
        client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)
        queued = client.synthesize("ทดสอบเสียง", "custom:brand_voice", emotion_id="normal")

        self.assertEqual(queued["job_id"], "TTS-JOB-1")
        self.assertTrue(_TtsHandler.synthesize_bodies)
        self.assertIn("reference_id=custom%3Abrand_voice", _TtsHandler.synthesize_bodies[-1])

    def test_synthesis_forces_stable_normal_speed_profile(self):
        client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)
        client.synthesize(
            "ทดสอบเสียงคงที่",
            "custom:brand_voice",
            emotion_id="angry",
            speed=1.75,
        )

        body = parse_qs(_TtsHandler.synthesize_bodies[-1])
        self.assertEqual(body["emotion_id"], ["normal"])
        self.assertEqual(body["speed"], ["1.0"])

    def test_synthesis_sends_deterministic_idempotency_key(self):
        client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)
        client.synthesize(
            "ทดสอบไม่สร้างเสียงซ้ำ", "custom:brand_voice",
            idempotency_key="story:STORY-ONE:narration:v1",
        )

        body = parse_qs(_TtsHandler.synthesize_bodies[-1])
        self.assertEqual(body["idempotency_key"], ["story:STORY-ONE:narration:v1"])
        self.assertEqual(_TtsHandler.seen_idempotency[-1], "story:STORY-ONE:narration:v1")

    def test_voice_failure_exposes_server_detail_and_marks_temporary_file_error_retryable(self):
        client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)
        server_detail = "Error opening 'online_data/user_files/58/uploads/job.wav': System error."

        with patch.object(client, "get_job", return_value={
            "job_id": "TTS-FAILED",
            "status": "error",
            "stage": "สร้างเสียงไม่สำเร็จ",
            "detail": server_detail,
        }):
            with self.assertRaises(ExternalTtsError) as caught:
                client.wait_until_done("TTS-FAILED", timeout=1, poll_interval=0.01)

        self.assertIn(server_detail, str(caught.exception))
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(caught.exception.payload["status"], "error")

    def test_missing_server_temporary_wav_is_retryable(self):
        client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)
        server_detail = "[Errno 2] No such file or directory: 'online_data/user_files/58/uploads/job-voice.wav'"

        with patch.object(client, "get_job", return_value={
            "job_id": "TTS-MISSING-WAV",
            "status": "error",
            "detail": server_detail,
        }):
            with self.assertRaises(ExternalTtsError) as caught:
                client.wait_until_done("TTS-MISSING-WAV", timeout=1, poll_interval=0.01)

        self.assertTrue(caught.exception.retryable)
        self.assertIn("No such file or directory", str(caught.exception))

    def test_voice_permanent_failure_is_not_retried(self):
        client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)

        with patch.object(client, "get_job", return_value={
            "job_id": "TTS-FAILED",
            "status": "error",
            "detail": "โมเดลเสียงนี้ไม่มีอยู่ในบัญชี",
        }):
            with self.assertRaises(ExternalTtsError) as caught:
                client.wait_until_done("TTS-FAILED", timeout=1, poll_interval=0.01)

        self.assertFalse(caught.exception.retryable)

    def test_wait_retries_transient_status_timeout_without_resubmitting(self):
        client = ExternalTtsClient("vc_live_secret", self.base_url, allow_localhost=True)
        statuses = []
        with patch.object(client, "get_job", side_effect=[
            ExternalTtsError("AI Voice ตอบช้า", retryable=True),
            {"job_id": "TTS-SAVED", "status": "done", "output_id": "OUT-SAVED"},
        ]) as get_job:
            _, output_id = client.wait_until_done(
                "TTS-SAVED", timeout=2, poll_interval=0.01,
                on_status=lambda state, result: statuses.append((state, result)),
            )

        self.assertEqual(output_id, "OUT-SAVED")
        self.assertEqual(get_job.call_count, 2)
        self.assertEqual(statuses[0][0], "connection_retry")
        self.assertEqual(statuses[0][1]["job_id"], "TTS-SAVED")

    def test_ui_catalog_selection_updates_reference_and_allowed_emotions(self):
        class FakeVar:
            def __init__(self, value=""): self.value = value
            def get(self): return self.value
            def set(self, value): self.value = value

        class FakeCombo:
            def __init__(self): self.options = {}
            def configure(self, **kwargs): self.options.update(kwargs)

        window = MainWindow.__new__(MainWindow)
        window.voice_catalog_choice = FakeVar()
        window.voice_catalog_info = FakeVar()
        window.voice_reference_id = FakeVar("custom:brand_voice")
        window.voice_emotion = FakeVar("angry")
        window.voice_speed = FakeVar("0.92")
        window.voice_status = FakeVar()
        window.status = FakeVar()
        window.voice_catalog_combo = FakeCombo()
        window.voice_emotion_combo = FakeCombo()
        window._voice_catalog_by_label = {}
        payload = {
            "voices": [
                {"id": "warm", "reference_id": "preset:warm", "source": "preset", "name": "เสียงอบอุ่น", "allowed_emotions": ["normal", "sad"]},
                {"id": "brand_voice", "reference_id": "custom:brand_voice", "source": "custom", "name": "เสียงร้าน", "allowed_emotions": ["normal"]},
            ],
            "preset_count": 1, "custom_count": 1,
        }
        with patch("ui.main_window.save_voice_settings") as save_settings:
            window._apply_voice_catalog(payload)

        self.assertEqual(window.voice_catalog_choice.get(), "เสียงของฉัน • เสียงร้าน")
        self.assertEqual(window.voice_reference_id.get(), "custom:brand_voice")
        self.assertEqual(window.voice_emotion.get(), "normal")
        self.assertEqual(window.voice_speed.get(), "1.0")
        self.assertEqual(window.voice_emotion_combo.options["values"], ("normal",))
        save_settings.assert_called_once()

    def test_rejects_untrusted_api_host(self):
        with self.assertRaises(ValueError):
            ExternalTtsClient("secret", "https://example.com")

    def test_product_job_stores_spoken_script_and_voice_without_api_key(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "สินค้าทดลอง", "product_url": "https://shopee.co.th/product/1/2"})
            manager.apply_ai_result({
                "job_id": job["id"],
                "caption_short": "แคปชั่น",
                "spoken_script": "บทพูดสินค้า [pause:0.5] ซื้อได้เลย",
                "video_prompt": "วิดีโอแนวตั้ง",
            })
            source = Path(temp) / "download.mp3"
            source.write_bytes(b"ID3mock")
            queued = manager.mark_voice_queued(job["id"], "TTS-JOB-1", "REF-1")
            saved = manager.save_voice_result(job["id"], source, "TTS-JOB-1", "REF-1", "OUT-1")
            request = manager.plugin_request(job["id"])

            self.assertEqual(saved["spoken_script"], "บทพูดสินค้า [pause:0.5] ซื้อได้เลย")
            self.assertEqual(queued["voice_status"], "queued")
            self.assertEqual(saved["voice_status"], "ready")
            self.assertTrue((manager.root / job["id"] / saved["voice_path"]).is_file())
            self.assertNotIn("api_key", json.dumps(saved).lower())
            self.assertEqual(request["request"]["schema_version"], 7)
            self.assertIn("spoken_script", request["request"]["required_fields"])
            self.assertIn("spoken_script_short", request["request"]["required_fields"])
            self.assertIn("spoken_script_segments", request["request"]["required_fields"])
            self.assertIn("flow_shot_prompts", request["request"]["required_fields"])
            self.assertIn("flow_gui_design", request["request"]["required_fields"])
            self.assertIn("ลิงก์สินค้าต้นทาง", request["prompt"])
            self.assertIn("ตัวเลขเป็นคำไทยทั้งหมด", request["prompt"])
            self.assertIn("น้ำเสียงผู้รีวิวมืออาชีพ", request["prompt"])
            self.assertIn("CGI ทุกชิ้นต้องสื่อคุณสมบัติจริง", request["prompt"])
            self.assertIn("ห้ามใช้ HUD เทคโนโลยี", request["prompt"])
            self.assertIn("ให้ใส่ข้อจำกัดของข้อมูลไว้ใน warnings เท่านั้น", request["prompt"])
            self.assertNotIn("เตือนสิ่งที่ต้องตรวจถ้าเป็นสินค้ามือสอง", request["prompt"])
            self.assertIn("ห้ามพูดเรื่องสินค้ามือสอง", request["prompt"])

            prompt_path = manager.root / job["id"] / "prompts" / "chatgpt_request.txt"
            prompt_path.write_text("เตือนสิ่งที่ต้องตรวจถ้าเป็นสินค้ามือสอง", encoding="utf-8")
            refreshed = manager.plugin_request(job["id"])
            self.assertNotIn("เตือนสิ่งที่ต้องตรวจถ้าเป็นสินค้ามือสอง", refreshed["prompt"])
            self.assertIn("น้ำเสียงผู้รีวิวมืออาชีพ", refreshed["prompt"])

    def test_saved_product_script_invalidates_stale_voice_and_subtitle(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "สินค้าทดลอง", "product_url": "https://shopee.co.th/product/1/2"})
            manager.apply_ai_result({
                "job_id": job["id"],
                "caption_short": "แคปชั่น",
                "spoken_script": "บทพูดเดิมสำหรับสินค้า",
                "video_prompt": "วิดีโอแนวตั้ง",
            })
            source = Path(temp) / "voice.mp3"
            source.write_bytes(b"ID3voice")
            manager.save_voice_result(job["id"], source, "VOICE-1", "REF-1", "OUT-1")
            manifest_path = manager.root / job["id"] / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"subtitle_status": "ready", "subtitle_path": "subtitles/old.srt"})
            manager._save_manifest_file(manifest_path, manifest)

            saved, script, changed = manager.save_spoken_script(job["id"], "บทพูดใหม่สำหรับสินค้า")

            self.assertTrue(changed)
            self.assertEqual(script, "บทพูดใหม่สำหรับสินค้า")
            self.assertEqual(saved["voice_status"], "not_generated")
            self.assertEqual(saved["subtitle_status"], "not_generated")
            self.assertNotIn("voice_path", saved)
            self.assertNotIn("subtitle_path", saved)
            self.assertTrue(saved["stale_voice_path"].endswith("voiceover.mp3"))

    def test_prepares_thai_script_for_voice_ai(self):
        script, issues = prepare_thai_tts_script(
            "GoPro MAX 360 ราคา ฿13,980 คะแนน 4.9 ขายแล้ว 19 ชิ้น 🤩 "
            "[pause:0.5] ดูที่ https://s.shopee.co.th/test [laughter]"
        )

        self.assertEqual(
            script,
            "โกโปร แม็กซ์ สามร้อยหกสิบ ราคา หนึ่งหมื่นสามพันเก้าร้อยแปดสิบบาท "
            "คะแนน สี่จุดเก้า ขายแล้ว สิบเก้า ชิ้น [pause:0.5] ดูที่ ลิงก์สินค้า [laughter]",
        )
        self.assertEqual(issues, [])
        self.assertEqual(thai_number_words("13980"), "หนึ่งหมื่นสามพันเก้าร้อยแปดสิบ")

    def test_prepares_common_device_terms_and_ai_pronunciation_notes(self):
        script, issues = prepare_thai_tts_script(
            "ช่อง AUX ไฟ LED ต่อ USB และ CODEC",
            {"AUX": "เอ-ยู-เอ็กซ์", "CODEC": "โคเด็ก"},
        )
        self.assertEqual(script, "ช่อง เอ ยู เอ็กซ์ ไฟ แอลอีดี ต่อ ยูเอสบี และ โคเด็ก")
        self.assertEqual(issues, [])

    def test_prepares_drama_episode_label_without_blocking_voice(self):
        script, issues = prepare_thai_tts_script("ร้านกาแฟคืนฝนตก EP 2")

        self.assertEqual(script, "ร้านกาแฟคืนฝนตก อีพี สอง")
        self.assertEqual(issues, [])

    def test_prepares_story_proper_names_without_blocking_voice(self):
        script, issues = prepare_thai_tts_script("Doctor Doom Supreme มีพลังเหนือใคร")

        self.assertEqual(script, "ด็อกเตอร์ ดูม ซูพรีม มีพลังเหนือใคร")
        self.assertEqual(issues, [])

    def test_unknown_english_story_name_is_passed_to_voice_engine(self):
        script, issues = prepare_thai_tts_script("UnknownHero ปรากฏตัว")

        self.assertEqual(script, "UnknownHero ปรากฏตัว")
        self.assertEqual(issues, [])

    def test_ai_result_keeps_raw_script_and_saves_tts_ready_script(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "กล้อง", "product_url": "https://shopee.co.th/product/1/2"})
            saved = manager.apply_ai_result({
                "job_id": job["id"],
                "caption_short": "แคปชั่น",
                "spoken_script": "GoPro MAX 360 ราคา ฿13,980 [pause:0.5] กดดูได้เลย",
                "spoken_script_short": "GoPro 360 ราคา ฿13,980",
                "pronunciation_notes": {"GoPro": "โกโปร"},
                "video_prompt": "วิดีโอแนวตั้ง",
            })
            folder = manager.root / job["id"] / "captions"

            self.assertIn("โกโปร แม็กซ์ สามร้อยหกสิบ", saved["spoken_script"])
            speech_without_pause = saved["spoken_script"].replace("[pause:0.5]", "")
            self.assertNotRegex(speech_without_pause, r"[A-Za-z0-9฿]")
            self.assertEqual(saved["tts_script_issues"], [])
            self.assertIn("GoPro MAX 360", (folder / "spoken_script_raw.txt").read_text(encoding="utf-8"))
            self.assertEqual((folder / "spoken_script.txt").read_text(encoding="utf-8"), saved["spoken_script"])
            self.assertTrue((folder / "spoken_script_short.txt").exists())
            self.assertTrue((folder / "pronunciation_notes.json").exists())
            self.assertEqual(saved["pronunciation_notes"]["GoPro"], "โกโปร")

    def test_ui_reuploads_missing_reference_and_retries_synthesis(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "reference.wav"
            source.write_bytes(b"RIFFtest")

            class FakeClient:
                synth_refs = []
                uploaded = False

                def __init__(self, *args, **kwargs): pass
                def synthesize(self, text, reference_id, **kwargs):
                    self.__class__.synth_refs.append(reference_id)
                    if len(self.__class__.synth_refs) == 1:
                        raise ExternalTtsError("AI Voice HTTP 404: ไม่พบไฟล์เสียงต้นแบบ")
                    return {"job_id": "JOB-VOICE-2"}
                def upload_reference(self, path):
                    self.__class__.uploaded = True
                    return {"reference_id": "REF-NEW"}
                def wait_until_done(self, job_id, on_status=None):
                    return {"status": "done"}, "OUT-NEW"
                def download(self, output_id, target, output_format):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"ID3voice")

            class FakeProducts:
                def __init__(self):
                    self.root = root / "products"
                    self.saved_reference = ""
                def mark_voice_queued(self, job_id, external_job_id, reference_id):
                    self.queued_reference = reference_id
                def save_voice_result(self, job_id, target, external_job_id, reference_id, output_id):
                    self.saved_reference = reference_id
                    return {"id": job_id, "voice_status": "ready"}

            window = MainWindow.__new__(MainWindow)
            window.cfg = {"voice_api_base_url": "https://www.catfufu.com"}
            window.products = FakeProducts()
            window.events = queue.Queue()
            options = {"language": "th", "emotion_id": "normal", "engine": "auto", "speed": 0.92, "silence_sec": 0.3, "output_format": "mp3"}
            with patch("ui.main_window.ExternalTtsClient", FakeClient), patch("ui.main_window.save_voice_settings"):
                window._create_voice_worker("JOB-TEST", "secret", "REF-OLD", str(source), "บทพูด", options)

            self.assertTrue(FakeClient.uploaded)
            self.assertEqual(FakeClient.synth_refs, ["REF-OLD", "REF-NEW"])
            self.assertEqual(window.products.saved_reference, "REF-NEW")
            event_names = [window.events.get_nowait()[0] for _ in range(window.events.qsize())]
            self.assertIn("voice_reference", event_names)
            self.assertIn("voice_ready", event_names)

    def test_ui_uploads_reference_when_id_is_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "reference.wav"
            source.write_bytes(b"RIFFtest")

            class FakeClient:
                synth_ref = ""
                def __init__(self, *args, **kwargs): pass
                def upload_reference(self, path): return {"reference_id": "REF-AUTO"}
                def synthesize(self, text, reference_id, **kwargs):
                    self.__class__.synth_ref = reference_id
                    return {"job_id": "JOB-AUTO"}
                def wait_until_done(self, job_id, on_status=None): return {"status": "done"}, "OUT-AUTO"
                def download(self, output_id, target, output_format):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"ID3voice")

            class FakeProducts:
                def __init__(self): self.root = root / "products"
                def mark_voice_queued(self, job_id, external_job_id, reference_id): self.queued_reference = reference_id
                def save_voice_result(self, job_id, target, external_job_id, reference_id, output_id):
                    return {"id": job_id, "voice_status": "ready", "voice_reference_id": reference_id}

            window = MainWindow.__new__(MainWindow)
            window.cfg = {"voice_api_base_url": "https://www.catfufu.com"}
            window.products = FakeProducts()
            window.events = queue.Queue()
            options = {"language": "th", "emotion_id": "normal", "engine": "auto", "speed": 0.92, "silence_sec": 0.3, "output_format": "mp3"}
            with patch("ui.main_window.ExternalTtsClient", FakeClient), patch("ui.main_window.save_voice_settings"):
                window._create_voice_worker("JOB-TEST", "secret", "", str(source), "บทพูด", options)

            self.assertEqual(FakeClient.synth_ref, "REF-AUTO")
            event_names = [window.events.get_nowait()[0] for _ in range(window.events.qsize())]
            self.assertIn("voice_reference", event_names)
            self.assertIn("voice_ready", event_names)

    def test_ui_retries_one_temporary_voice_file_failure_without_losing_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            class FakeClient:
                synth_jobs = []
                waits = []

                def __init__(self, *args, **kwargs): pass
                def synthesize(self, text, reference_id, **kwargs):
                    job_id = f"VOICE-{len(self.__class__.synth_jobs) + 1}"
                    self.__class__.synth_jobs.append((job_id, text, reference_id))
                    return {"job_id": job_id}
                def wait_until_done(self, job_id, on_status=None):
                    self.__class__.waits.append(job_id)
                    if job_id == "VOICE-1":
                        raise ExternalTtsError(
                            "สร้างเสียงไม่สำเร็จ: Error opening temporary.wav: System error.",
                            retryable=True,
                        )
                    return {"status": "done"}, "OUT-2"
                def download(self, output_id, target, output_format):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"ID3voice")

            class FakeProducts:
                def __init__(self):
                    self.root = root / "products"
                    self.queued = []
                def mark_voice_queued(self, job_id, external_job_id, reference_id):
                    self.queued.append((external_job_id, reference_id))
                def save_voice_result(self, job_id, target, external_job_id, reference_id, output_id):
                    return {"id": job_id, "voice_status": "ready", "voice_path": str(target)}

            window = MainWindow.__new__(MainWindow)
            window.cfg = {"voice_api_base_url": "https://www.catfufu.com"}
            window.products = FakeProducts()
            window.events = queue.Queue()
            window.log = unittest.mock.Mock()
            options = {"language": "th", "emotion_id": "normal", "engine": "auto", "speed": 0.92, "silence_sec": 0.3, "output_format": "mp3"}
            with patch("ui.main_window.ExternalTtsClient", FakeClient), patch("ui.main_window.save_voice_settings"), patch("ui.main_window.time.sleep"):
                job, target = window._create_voice_worker("JOB-TEST", "secret", "custom:voice", "", "บทพูด", options)

            self.assertEqual([item[0] for item in FakeClient.synth_jobs], ["VOICE-1", "VOICE-2"])
            self.assertEqual([item[2] for item in FakeClient.synth_jobs], ["custom:voice", "custom:voice"])
            self.assertEqual(FakeClient.waits, ["VOICE-1", "VOICE-2"])
            self.assertEqual(window.products.queued, [("VOICE-1", "custom:voice"), ("VOICE-2", "custom:voice")])
            self.assertEqual(job["voice_status"], "ready")
            self.assertTrue(target.is_file())
            progress = [payload for name, payload in list(window.events.queue) if name == "voice_progress"]
            self.assertTrue(any("ลองสร้างเสียงใหม่อัตโนมัติ 2/2" in item for item in progress))

    def test_story_replaces_one_terminal_missing_wav_queue_without_recreating_images(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            story_root = root / "stories"
            job_id = "STORY-VOICE-RETRY"
            (story_root / job_id / "audio").mkdir(parents=True)
            original_images = [f"generated/scene_{index:02d}.png" for index in range(1, 7)]

            class FakeStories:
                def __init__(self):
                    self.root = story_root
                    self.job = {
                        "id": job_id,
                        "ai_status": "ready",
                        "scene_count": 6,
                        "generated_images": list(original_images),
                        "narration_script": "นี่คือบทพากย์ภาษาไทย",
                        "voice_status": "queued",
                        "voice_job_id": "VOICE-BROKEN",
                        "voice_reference_id": "custom:voice",
                        "voice_resubmit_count": 0,
                        "job_type": "story_short",
                    }
                    self.prepared = []
                    self.checkpoints = []
                def get(self, _job_id): return dict(self.job)
                def repair_program_cta(self, _job_id): return dict(self.job)
                def mark_running(self, _job_id, stage): self.job.update(status="running", pipeline_stage=stage); return dict(self.job)
                def prepare_voice_resubmit(self, _job_id, failed_job_id, reason, max_resubmits=1):
                    self.prepared.append((failed_job_id, reason, max_resubmits))
                    self.job.update(voice_resubmit_count=1, voice_job_id="", voice_output_id="", voice_status="resubmitting")
                    return dict(self.job)
                def save_voice_checkpoint(self, _job_id, external_job_id="", output_id="", reference_id="", status="queued"):
                    if external_job_id: self.job["voice_job_id"] = external_job_id
                    if output_id: self.job["voice_output_id"] = output_id
                    if reference_id: self.job["voice_reference_id"] = reference_id
                    self.job["voice_status"] = status
                    self.checkpoints.append((external_job_id, output_id, status))
                    return dict(self.job)
                def save_voice(self, _job_id, source, external_job_id, output_id, reference_id):
                    self.job.update(voice_status="ready", voice_path=str(source), voice_job_id=external_job_id, voice_output_id=output_id, voice_reference_id=reference_id)
                    return dict(self.job)

            class FakeVar:
                def __init__(self, value): self.value = value
                def get(self): return self.value

            class FakeClient:
                waits = []
                submits = []
                def __init__(self, *args, **kwargs): pass
                def synthesize(self, text, reference_id, **kwargs):
                    self.__class__.submits.append((text, reference_id, kwargs.get("idempotency_key")))
                    return {"job_id": "VOICE-REPLACEMENT"}
                def wait_until_done(self, external_job_id, on_status=None, cancel_event=None):
                    self.__class__.waits.append(external_job_id)
                    if external_job_id == "VOICE-BROKEN":
                        raise ExternalTtsError(
                            "สร้างเสียงไม่สำเร็จ: [Errno 2] No such file or directory: temporary.wav",
                            retryable=True,
                        )
                    return {"status": "done"}, "OUTPUT-REPLACEMENT"
                def download(self, output_id, target, output_format, cancel_event=None):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"ID3replacement")

            stories = FakeStories()
            window = MainWindow.__new__(MainWindow)
            window.cfg = {"voice_api_base_url": "https://www.catfufu.com"}
            window._creation_settings = unittest.mock.Mock(return_value={})
            window.stories = stories
            window.events = queue.Queue()
            window.log = unittest.mock.Mock()
            window.voice_language = FakeVar("th")
            window.voice_silence = FakeVar("0.3")
            window._story_cancel_event = threading.Event()
            window._compose_story_media = unittest.mock.Mock(return_value="COMPOSED")

            with patch("ui.main_window.ExternalTtsClient", FakeClient):
                result = window._render_story_worker(job_id, "secret", "custom:voice", "")

            self.assertEqual(result, "COMPOSED")
            self.assertEqual(FakeClient.waits, ["VOICE-BROKEN", "VOICE-REPLACEMENT"])
            self.assertEqual(FakeClient.submits[0][2], f"story:{job_id}:narration:v2")
            self.assertEqual(stories.job["voice_job_id"], "VOICE-REPLACEMENT")
            self.assertEqual(stories.job["voice_status"], "ready")
            self.assertEqual(stories.job["generated_images"], original_images)
            self.assertEqual(len(stories.prepared), 1)


if __name__ == "__main__":
    unittest.main()
