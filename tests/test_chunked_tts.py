import json
import queue
import shutil
import struct
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.cancellable_process import OperationCancelled
from core.chunked_tts import merge_voice_chunks, render_chunked_voice, split_tts_text
from core.external_tts import ExternalTtsClient, ExternalTtsError


class FakeClient:
    def __init__(self):
        self.actions = []
        self.fail_poll = False
        self.fail_download = False

    def synthesize(self, text, reference_id, **options):
        assert 0 < len(text.strip()) <= 2000
        remote = f"remote-{sum(a[0] == 'send' for a in self.actions) + 1}"
        self.actions.append(("send", remote, text, options["idempotency_key"]))
        return {"job_id": remote}

    def wait_until_done(self, remote, **kwargs):
        self.actions.append(("poll", remote))
        if self.fail_poll:
            self.fail_poll = False
            raise ExternalTtsError("poll timeout", retryable=True, payload={"status": "poll_timeout"})
        return {"status": "done"}, "output-" + remote

    def download(self, output, target, fmt, **kwargs):
        self.actions.append(("download", output))
        if self.fail_download:
            self.fail_download = False
            raise ExternalTtsError("download timeout", retryable=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(output.encode())


def fake_merge(paths, target, ffmpeg_path, **kwargs):
    target.write_bytes(b"|".join(p.read_bytes() for p in paths))


class ChunkedTtsTests(unittest.TestCase):
    def test_boundaries_and_exact_text(self):
        for text in ("ก" * 2000, "ก" * 2001, "เล่าเรื่องต่อไป [pause:0.5] " * 1100,
                     "ก" * 1997 + " [pause:0.5] ข้อความ", "กำ" * 2300):
            chunks = split_tts_text(text)
            self.assertEqual("".join(chunks), text.strip())
            self.assertTrue(all(0 < len(x) <= 2000 for x in chunks))
            self.assertEqual(sum(x.count("[pause:0.5]") for x in chunks), text.count("[pause:0.5]"))
        self.assertEqual(len(split_tts_text("ก" * 6000)), 3)
        self.assertTrue(all(x.strip() for x in split_tts_text("ก" * 2000 + " " * 5000 + "ข" * 2000)))

    def test_api_enforces_ceiling_before_network(self):
        client = ExternalTtsClient("test-only")
        with patch.object(client, "_form") as post:
            with self.assertRaises(ValueError):
                client.synthesize("ก" * 2001, "ref")
            post.assert_not_called()

    def run_batch(self, root, client, **kwargs):
        return render_chunked_voice(client, "ก" * 4500, "ref", root / "voice.mp3",
                                    scope="test:narration", options={"language": "th"}, **kwargs)

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_sequential_and_resume_downloaded_chunks(self, merge):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = FakeClient()
            messages = []
            self.run_batch(root, client, on_progress=messages.append)
            self.assertEqual([a[0] for a in client.actions], ["send", "poll", "download"] * 3)
            self.assertEqual([len(a[2]) for a in client.actions if a[0] == "send"], [2000, 2000, 500])
            self.assertEqual((root / "voice.mp3").read_bytes(), b"output-remote-1|output-remote-2|output-remote-3")
            self.run_batch(root, client)
            self.assertEqual(len(client.actions), 9)
            self.assertTrue(any("3/3" in message for message in messages))
            ledger = json.loads((root / ".tts_chunks/voice/batch.json").read_text(encoding="utf-8"))
            self.assertEqual(len(ledger["chunks"]), 3)
            self.assertNotIn("ก", json.dumps(ledger, ensure_ascii=False))

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_poll_timeout_keeps_same_job_without_resubmit(self, merge):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient()
            client.fail_poll = True
            with self.assertRaises(ExternalTtsError):
                self.run_batch(Path(temp), client)
            self.assertEqual([a[0] for a in client.actions], ["send", "poll"])
            self.run_batch(Path(temp), client)
            self.assertEqual(client.actions[2], ("poll", "remote-1"))
            self.assertEqual(sum(a[0] == "send" for a in client.actions), 3)

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_download_failure_does_not_submit_next_chunk(self, merge):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient()
            client.fail_download = True
            with self.assertRaises(ExternalTtsError):
                self.run_batch(Path(temp), client)
            self.run_batch(Path(temp), client)
            self.assertEqual(client.actions[3], ("download", "output-remote-1"))
            self.assertEqual(sum(a[0] == "poll" for a in client.actions), 3)

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_cancel_between_chunks_and_resume(self, merge):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient()
            stop = threading.Event()
            original = client.download
            def download(*args, **kwargs):
                original(*args, **kwargs)
                stop.set()
            client.download = download
            with self.assertRaises(OperationCancelled):
                self.run_batch(Path(temp), client, cancel_event=stop)
            self.assertEqual(len(client.actions), 3)
            stop.clear()
            client.download = original
            self.run_batch(Path(temp), client, cancel_event=stop)
            self.assertEqual(sum(a[0] == "send" for a in client.actions), 3)

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_changed_script_stops_instead_of_replacing_checkpoint(self, merge):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient()
            self.run_batch(Path(temp), client)
            with self.assertRaises(ExternalTtsError):
                render_chunked_voice(client, "ข" * 4500, "ref", Path(temp) / "voice.mp3",
                                     scope="test:narration", options={"language": "th"})
            self.assertEqual(len(client.actions), 9)

    def test_legacy_already_paid_job_is_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient()
            self.run_batch(Path(temp), client, legacy_job_id="old-job")
            self.assertEqual([a[0] for a in client.actions], ["poll", "download"])

    def test_missing_batch_ledger_never_treats_last_chunk_as_full_narration(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient()
            with self.assertRaises(ExternalTtsError):
                self.run_batch(Path(temp), client, legacy_job_id="chunked:remote-2")
            self.assertEqual(client.actions, [])

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_terminal_replacement_budget_survives_resume(self, merge):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient()
            def fail(remote, **kwargs):
                raise ExternalTtsError("temporary file lost", retryable=True, payload={"status": "error"})
            client.wait_until_done = fail
            for _ in range(2):
                with self.assertRaises(ExternalTtsError):
                    self.run_batch(Path(temp), client)
            sends = [a for a in client.actions if a[0] == "send"]
            self.assertEqual(len(sends), 2)
            self.assertNotEqual(sends[0][3], sends[1][3])

    def test_real_ffmpeg_merge_duration_order_and_all_formats(self):
        from core.config import load_config
        ffmpeg = shutil.which("ffmpeg") or load_config().get("ffmpeg_path")
        if not ffmpeg or not Path(ffmpeg).is_file():
            self.skipTest("FFmpeg unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = []
            for index, value in enumerate((1000, 4000, 7000)):
                path = root / f"part-{index}.wav"
                with wave.open(str(path), "wb") as out:
                    out.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
                    out.writeframes(struct.pack("<h", value) * 2 * 4800)
                paths.append(path)
            for extension in ("wav", "mp3", "mp4"):
                target = root / f"merged.{extension}"
                merge_voice_chunks(paths, target, ffmpeg)
                self.assertGreater(target.stat().st_size, 500)
            with wave.open(str(root / "merged.wav"), "rb") as result:
                self.assertEqual(result.getnframes(), 14400)
                for offset, value in ((100, 1000), (4900, 4000), (9700, 7000)):
                    result.setpos(offset)
                    self.assertEqual(struct.unpack("<hh", result.readframes(1)), (value, value))
            self.assertEqual(list(root.glob(".voice-*")), [])

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_unknown_submit_reuses_exact_idempotency_key(self, merge):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeClient()
            original = client.synthesize
            keys = []
            def submit(text, ref, **options):
                keys.append(options["idempotency_key"])
                if len(keys) == 1:
                    raise ExternalTtsError("response lost", retryable=True)
                return original(text, ref, **options)
            client.synthesize = submit
            with self.assertRaises(ExternalTtsError):
                self.run_batch(Path(temp), client)
            self.run_batch(Path(temp), client)
            self.assertEqual(keys[0], keys[1])
            self.assertEqual(len(set(keys)), 3)

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_product_worker_routes_long_script_and_saves_merged_voice(self, merge):
        from ui.main_window import MainWindow
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            window = MainWindow.__new__(MainWindow)
            window.cfg = {}
            window.events = queue.Queue()
            saved = []
            window.products = SimpleNamespace(root=root, get_job=lambda _: {},
                mark_voice_queued=lambda *args: None,
                save_voice_result=lambda *args: saved.append(args) or {"voice_status": "ready"})
            options = {"language": "th", "engine": "auto", "silence_sec": 0.3, "output_format": "mp3"}
            with patch("ui.main_window.ExternalTtsClient", return_value=FakeClient()), patch("ui.main_window.save_voice_settings"):
                job, target = window._create_voice_worker("JOB-TEST", "not-real", "ref", "", "ก" * 4500, options)
            self.assertEqual(job["voice_status"], "ready")
            self.assertTrue(target.is_file())
            self.assertEqual(len(saved), 1)

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_story_worker_long_narration_preserves_images(self, merge):
        from ui.main_window import MainWindow
        with tempfile.TemporaryDirectory() as temp:
            job = {"ai_status": "ready", "generated_images": ["one.png"], "scene_count": 1}
            window = MainWindow.__new__(MainWindow)
            window.cfg = {}
            window.events = queue.Queue()
            window._creation_settings = Mock(return_value={})
            window.voice_language = SimpleNamespace(get=lambda: "th")
            window.voice_silence = SimpleNamespace(get=lambda: "0.3")
            window._compose_story_media = Mock(return_value="composed")
            window.stories = SimpleNamespace(root=Path(temp), repair_program_cta=lambda _: dict(job),
                get=lambda _: dict(job), mark_running=Mock(), save_voice_checkpoint=Mock(), save_voice=Mock())
            client = FakeClient()
            with patch("ui.main_window.ExternalTtsClient", return_value=client), patch("ui.main_window.spoken_script_for_job", return_value="ก" * 4500):
                result = window._render_story_worker("STORY-TEST", "test-key", "ref", "", threading.Event())
            self.assertEqual(result, "composed")
            self.assertEqual(sum(a[0] == "send" for a in client.actions), 3)
            self.assertEqual(window.stories.save_voice.call_count, 1)
            self.assertEqual(job["generated_images"], ["one.png"])
            self.assertTrue(window.stories.save_voice.call_args.args[2].startswith("chunked:"))

    @patch("core.chunked_tts.merge_voice_chunks", side_effect=fake_merge)
    def test_drama_long_turn_uses_same_sequential_chunk_pipeline(self, merge):
        from ui.main_window import MainWindow
        with tempfile.TemporaryDirectory() as temp:
            window = MainWindow.__new__(MainWindow)
            window.cfg = {"ffmpeg_path": __file__}  # process mocked below
            window.events = queue.Queue()
            window.voice_language = SimpleNamespace(get=lambda: "th")
            window.stories = SimpleNamespace(root=Path(temp), save_dialogue_voice_checkpoint=Mock(), save_voice=Mock())
            job = {"dialogue_turns": [{"speaker": "ผู้บรรยาย", "text": "ก" * 4500}]}
            def concat(command, **kwargs):
                Path(command[-1]).write_bytes(b"audio" * 300)
                return SimpleNamespace(returncode=0)
            client = FakeClient()
            with patch("ui.main_window.run_cancellable", side_effect=concat):
                target = window._render_drama_dialogue_voice("STORY-TEST", job, client, "ref", {}, threading.Event())
            self.assertTrue(target.is_file())
            self.assertEqual(sum(a[0] == "send" for a in client.actions), 3)
            self.assertEqual(window.stories.save_voice.call_count, 1)


if __name__ == "__main__":
    unittest.main()
