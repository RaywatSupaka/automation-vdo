import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.product_manager import ProductManager
from core.smartsub_online import SmartSubOnlineClient


class SmartSubOnlineTests(unittest.TestCase):
    def client(self, credential="SOD-test"):
        return SmartSubOnlineClient(credential, "http://127.0.0.1:9999/api/smartsub-online/v2", allow_localhost=True)

    def test_redeems_token_without_exposing_it(self):
        client = self.client("")
        with patch.object(client, "_json_request", return_value={"deviceCredential": "SOD-secret"}) as request:
            result, credential = client.redeem("smartpost-device-1", "SOT-once")
        self.assertEqual(credential, "SOD-secret")
        self.assertNotIn("SOT-once", repr(client))
        self.assertEqual(json.loads(request.call_args.args[2])["clientId"], "smartpost-device-1")

    def test_creates_job_with_idempotency_key(self):
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / "voice.wav"
            audio.write_bytes(b"RIFFaudio")
            client = self.client()
            with patch.object(client, "_multipart", return_value={"jobId": "SUB-1"}) as upload:
                created = client.create_job(audio, "th", "fixed-key")
            self.assertEqual(created["jobId"], "SUB-1")
            self.assertEqual(upload.call_args.args[3], "fixed-key")

    def test_reads_subtitle_credit_status(self):
        client = self.client()
        response = {
            "ok": True,
            "creditBalance": 180,
            "trialRemaining": 3,
            "jobCreditCost": 2,
            "creditUnitSeconds": 60,
            "creditExpiresAt": "2026-09-30T00:00:00Z",
            "requiresToken": False,
        }
        with patch.object(client, "_json_request", return_value=response) as request:
            status = client.get_status()

        self.assertTrue(status["connected"])
        self.assertEqual(status["credits"], 180)
        self.assertEqual(status["trial_remaining"], 3)
        self.assertEqual(status["job_credit_cost"], 2)
        self.assertEqual(request.call_args.args[1], "/status")
        self.assertNotIn("SOD-test", repr(status))

    def test_extracts_nested_transcript_and_builds_srt(self):
        result = {"status": "done", "result": {"text": "สวัสดีครับ", "segments": [{"start": 0, "end": 1.25, "text": "สวัสดีครับ"}]}}
        extracted = SmartSubOnlineClient.extract_artifacts(result)
        self.assertEqual(extracted["transcript"], "สวัสดีครับ")
        self.assertEqual(len(extracted["segments"]), 1)
        self.assertIn("00:00:01,250", ProductManager._segments_to_srt(extracted["segments"]))

    def test_product_job_saves_subtitle_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "สินค้า", "product_url": "https://shopee.co.th/product/123/456"})
            manager.mark_subtitle_queued(job["id"], "SUB-1", "th")
            saved, paths = manager.save_subtitle_result(job["id"], "SUB-1", {
                "status": "done",
                "result": {"text": "ทดสอบคำบรรยาย", "segments": [{"start": 0, "end": 2, "text": "ทดสอบคำบรรยาย"}]},
            }, 3)
            folder = manager.root / job["id"]
            self.assertEqual(saved["subtitle_status"], "ready")
            self.assertTrue(saved["subtitle_requested"])
            self.assertEqual(saved["subtitle_syllables_per_cue"], 3)
            self.assertTrue((folder / paths["subtitle.srt"]).is_file())
            self.assertNotIn("SOD", (folder / "job.json").read_text(encoding="utf-8"))

    def test_persists_user_subtitle_choice_per_job(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "สินค้า", "product_url": "https://shopee.co.th/product/123/789"})
            enabled = manager.set_subtitle_requested(job["id"], True)
            self.assertTrue(enabled["subtitle_requested"])
            disabled = manager.set_subtitle_requested(job["id"], False)
            self.assertFalse(disabled["subtitle_requested"])

    def test_groups_one_to_five_timed_words_without_dropping_any(self):
        words = [{"text": text, "start": index, "end": index + 0.5} for index, text in enumerate("กขคงจฉช")]
        srt = ProductManager._segments_to_srt([{"text": "กขคงจฉช", "start": 0, "end": 7, "words": words}], 3)
        blocks = srt.split("\n\n")
        self.assertEqual(len(blocks), 3)
        cue_text = "".join(block.splitlines()[-1] for block in blocks)
        self.assertEqual(cue_text, "กขคงจฉช")
        self.assertEqual([block.splitlines()[-1] for block in blocks], ["กขค", "งจฉ", "ช"])
        for value in range(1, 6):
            self.assertTrue(ProductManager._segments_to_srt([{"words": words}], value))

    def test_keeps_price_and_decimal_numbers_as_complete_units(self):
        words = []
        for index, text in enumerate(("ราคา", "13", ",", "9", "80", "บาท", "คะแนน", "4", ".", "9")):
            words.append({"text": text, "start": index * 0.2, "end": index * 0.2 + 0.2})
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        self.assertIn("13,980", srt)
        self.assertIn("4.9", srt)
        self.assertNotIn("\n,", srt)
        self.assertNotIn("\n.", srt)

    def test_splits_long_thai_words_by_real_syllables_without_detaching_marks(self):
        words = [{"text": "บรรยากาศ", "start": 0, "end": 1.5}, {"text": "รอบตัว", "start": 1.5, "end": 2.5}]
        units = ProductManager._split_subtitle_syllable_units(words)
        self.assertEqual([unit["text"] for unit in units[:3]], ["บรร", "ยา", "กาศ"])
        self.assertEqual("".join(unit["text"] for unit in units), "บรรยากาศรอบตัว")
        self.assertFalse(any(re.match(r"^[\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]", unit["text"]) for unit in units))
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        self.assertEqual(srt.splitlines()[2], "บรรยากาศ")

    def test_keeps_whole_words_when_they_fit_syllable_limit(self):
        words = [
            {"text": "อยาก", "start": 0, "end": 0.3},
            {"text": "เก็บ", "start": 0.3, "end": 0.6},
            {"text": "บรรยากาศ", "start": 0.6, "end": 1.5},
        ]
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        texts = [block.splitlines()[-1] for block in srt.split("\n\n")]
        self.assertEqual(texts, ["อยากเก็บ", "บรรยากาศ"])

    def test_story_script_never_splits_complete_thai_words_or_drops_text(self):
        script = "ถ้าเป็นคุณ จะรับมันมาเป็นสมาชิกในบ้านไหม กดหัวใจแล้วคอมเมนต์"
        words = ProductManager._script_to_timed_words(script, 12.0)
        self.assertTrue(any("สมาชิก" in word["text"] for word in words))
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        cue_texts = [block.splitlines()[-1] for block in srt.split("\n\n")]
        self.assertTrue(any("สมาชิก" in cue for cue in cue_texts))
        self.assertNotIn("สมา", cue_texts)
        self.assertNotIn("ชิก", cue_texts)
        self.assertEqual(re.sub(r"\s+", "", "".join(cue_texts)), re.sub(r"\s+", "", script))

    def test_story_cues_respect_authored_phrases_and_do_not_leave_prefixes_dangling(self):
        script = "ถ้าคืนนั้นเจ้าทองไม่อยู่ คุณตาสมชายอาจไม่ได้กลับมา ทุกคืนหลังขายเสร็จ"
        words = ProductManager._script_to_timed_words(script, 12.0)
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        cue_texts = [block.splitlines()[-1] for block in srt.split("\n\n")]
        self.assertNotIn("เจ้าทองไม่", cue_texts)
        self.assertIn("ไม่อยู่", cue_texts)
        self.assertFalse(any("อยู่คุณตา" in cue for cue in cue_texts))
        self.assertFalse(any("มาทุก" in cue for cue in cue_texts))
        self.assertEqual(re.sub(r"\s+", "", "".join(cue_texts)), re.sub(r"\s+", "", script))

    def test_thai_repetition_mark_stays_with_previous_word(self):
        words = ProductManager._script_to_timed_words("นั่งรอเงียบ ๆ คุณตาเดินมา", 6.0)
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        cue_texts = [block.splitlines()[-1] for block in srt.split("\n\n")]
        self.assertTrue(any("เงียบๆ" in cue for cue in cue_texts))
        self.assertFalse(any(cue.startswith("ๆ") for cue in cue_texts))

    def test_ellipsis_attaches_to_previous_cue_instead_of_flashing_alone(self):
        words = ProductManager._script_to_timed_words("นานขนาดนี้ ... ตอนผมอายุแปดขวบ", 6.0)
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        cue_texts = [block.splitlines()[-1] for block in srt.split("\n\n")]
        self.assertNotIn("...", cue_texts)
        self.assertTrue(any(cue.endswith("...") for cue in cue_texts))
        self.assertNotIn("นานขนาด", cue_texts)
        self.assertIn("ขนาดนี้...", cue_texts)

    def test_story_character_names_remain_complete_lexical_words(self):
        script = "คุณตาสมชายอาจไม่ได้กลับมา คุณตาเรียกมันว่าเจ้าทอง"
        words = ProductManager._script_to_timed_words(script, 8.0)
        texts = [word["text"] for word in words]
        self.assertIn("สมชาย", texts)
        self.assertIn("เจ้าทอง", texts)
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        cues = [block.splitlines()[-1] for block in srt.split("\n\n")]
        self.assertFalse(any(cue.endswith("สม") or cue.endswith("เจ้า") for cue in cues))
        self.assertIn("อาจไม่ได้", cues)

    def test_drama_speaker_name_stays_complete_inside_running_thai_text(self):
        script = "ผู้บรรยาย: ลูกค้าคนหนึ่งที่มินไม่คิดว่าจะได้ยินความจริง มิน: ฉันไม่เคยรู้"
        words = ProductManager._script_to_timed_words(script, 8.0)
        texts = [word["text"] for word in words]
        self.assertGreaterEqual(texts.count("มิน"), 2)
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        cues = [block.splitlines()[-1] for block in srt.split("\n\n")]
        self.assertFalse(any(cue.endswith("มิ") or cue.startswith("นไม่คิด") for cue in cues))
        self.assertEqual(re.sub(r"\s+", "", "".join(cues)), re.sub(r"\s+", "", script))

    def test_character_bible_name_can_be_protected_after_speaker_labels_are_removed(self):
        script = "ลูกค้าคนหนึ่งที่มินไม่คิดว่าจะได้ยินความจริง"
        words = ProductManager._script_to_timed_words(script, 5.0, protected_terms=["มิน"])
        self.assertIn("มิน", [word["text"] for word in words])
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        cues = [block.splitlines()[-1] for block in srt.split("\n\n")]
        self.assertFalse(any(cue.endswith("มิ") or cue.startswith("นไม่คิด") for cue in cues))
        self.assertEqual("".join(cues), script)

    def test_long_word_may_exceed_target_but_remains_complete(self):
        words = ProductManager._script_to_timed_words("ประชาธิปไตยมีความสำคัญ", 5.0)
        srt = ProductManager._segments_to_srt([{"words": words}], 2)
        cue_texts = [block.splitlines()[-1] for block in srt.split("\n\n")]
        self.assertIn("ประชาธิปไตย", cue_texts)
        self.assertEqual("".join(cue_texts), "ประชาธิปไตยมีความสำคัญ")

    def test_story_timing_skips_real_voice_pauses_and_keeps_exact_text(self):
        script = "คำแรก คำที่สอง คำที่สาม คำสุดท้าย"
        words = ProductManager._script_to_timed_words(
            script, 10.0, speech_intervals=[(0.0, 2.0), (7.0, 10.0)], lead_seconds=0.12,
        )
        self.assertEqual("".join(word["text"] for word in words), script.replace(" ", ""))
        self.assertTrue(any(word["start"] >= 6.8 for word in words))
        self.assertFalse(any(2.1 < word["start"] < 6.8 for word in words))
        self.assertEqual(words[0]["start"], 0.0)
        self.assertLessEqual(words[-1]["end"], 10.0)

    def test_repairs_overlapping_api_word_times_between_cues(self):
        words = [
            {"text": "อยาก", "start": 0, "end": 0.4},
            {"text": "เก็บ", "start": 0.3, "end": 0.64},
            {"text": "บรรยากาศ", "start": 0.52, "end": 1.04},
        ]
        srt = ProductManager._segments_to_srt([{"words": words}], 3)
        stamps = re.findall(r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", srt)
        self.assertEqual(stamps[0][1], stamps[1][0])

    def test_corrects_api_words_from_approved_script_without_dropping_text(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "PANZO", "product_url": "https://shopee.co.th/product/123/999"})
            folder = manager.root / job["id"]
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"spoken_script": "แพนโซ ตู้เป่าขนสำหรับน้องหมา [pause:0.5] กดดูรายละเอียดได้เลย", "subtitle_syllables_per_cue": 3})
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            api_srt = (
                "1\n00:00:00,000 --> 00:00:01,000\nP an so\n\n"
                "2\n00:00:01,000 --> 00:00:02,200\nตู้เป่าขนสำหรับหนองหมา\n\n"
                "3\n00:00:02,300 --> 00:00:03,500\nกดดูรายละเอียดได้เลย\n"
            )
            (folder / "captions" / "subtitle.srt").write_text(api_srt, encoding="utf-8")
            saved, corrected = manager.correct_subtitle_from_script(job["id"])
            text = corrected.read_text(encoding="utf-8")
            cue_texts = [block.splitlines()[-1] for block in text.strip().split("\n\n")]
            expected = re.sub(r"\s+|\[pause:[^\]]+\]", "", manifest["spoken_script"])
            self.assertEqual(re.sub(r"\s+", "", "".join(cue_texts)), expected)
            self.assertNotIn("P an so", text)
            self.assertNotIn("หนองหมา", text)
            self.assertEqual(saved["subtitle_alignment_status"], "corrected_from_approved_script")
            self.assertTrue((folder / "captions" / "subtitle_api_raw.srt").is_file())
            self.assertEqual(saved["subtitle_video_status"], "needs_render")
            previous_end = "00:00:00,000"
            for start, end in re.findall(r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", text):
                self.assertGreaterEqual(start, previous_end)
                previous_end = end

    def test_correction_preserves_api_speech_gaps_and_is_stable_on_rerun(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "สินค้า", "product_url": "https://shopee.co.th/product/123/1001"})
            folder = manager.root / job["id"]
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({
                "spoken_script": "เริ่มรีวิว สินค้าน่าใช้ [pause:0.5] จุดเด่นชัดเจน ใช้งานง่าย",
                "subtitle_syllables_per_cue": 3,
            })
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            api_srt = (
                "1\n00:00:00,000 --> 00:00:01,000\nเริ่มรีวิวสินค้าน่าใช้\n\n"
                "2\n00:00:01,600 --> 00:00:03,000\nจุดเด่นชัดเจนใช้งานง่าย\n"
            )
            subtitle = folder / "captions" / "subtitle.srt"
            subtitle.write_text(api_srt, encoding="utf-8")

            saved, corrected = manager.correct_subtitle_from_script(job["id"])
            first = corrected.read_text(encoding="utf-8")
            stamps = re.findall(r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", first)

            def seconds(value):
                hours, minutes, rest = value.replace(",", ".").split(":")
                return int(hours) * 3600 + int(minutes) * 60 + float(rest)

            gaps = [seconds(stamps[index + 1][0]) - seconds(stamps[index][1]) for index in range(len(stamps) - 1)]
            self.assertGreaterEqual(max(gaps), 0.45)
            self.assertEqual(saved["subtitle_timing_model"], "api_speech_intervals_v2")
            self.assertEqual(saved["subtitle_sync_lead_ms"], 120)
            raw_path = folder / "captions" / "subtitle_api_raw.srt"
            self.assertEqual(raw_path.read_text(encoding="utf-8"), api_srt)

            _saved_again, corrected_again = manager.correct_subtitle_from_script(job["id"])
            self.assertEqual(corrected_again.read_text(encoding="utf-8"), first)
            self.assertEqual(raw_path.read_text(encoding="utf-8"), api_srt)

    def test_save_subtitle_result_automatically_uses_approved_script_as_word_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job, _ = manager.import_product({"product_name": "PANZO", "product_url": "https://shopee.co.th/product/123/1000"})
            folder = manager.root / job["id"]
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            approved = "แพนโซ ตู้เป่าขนสำหรับน้องหมา กดดูรายละเอียดได้เลย"
            manifest.update({"spoken_script": approved, "subtitle_syllables_per_cue": 3})
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            saved, paths = manager.save_subtitle_result(job["id"], "SUB-AUTO", {
                "status": "done",
                "result": {
                    "text": "พานโซ ตู้เป่าขนสำหรับหนองหมา กดดูรายละเอียดได้เลย",
                    "segments": [
                        {"start": 0, "end": 1, "text": "พานโซ"},
                        {"start": 1, "end": 2.5, "text": "ตู้เป่าขนสำหรับหนองหมา"},
                        {"start": 2.5, "end": 4, "text": "กดดูรายละเอียดได้เลย"},
                    ],
                },
            }, 3)

            corrected = (folder / paths["subtitle.srt"]).read_text(encoding="utf-8")
            raw = (folder / paths["subtitle_api_raw.srt"]).read_text(encoding="utf-8")
            corrected_words = "".join(block.splitlines()[-1] for block in corrected.strip().split("\n\n"))
            raw_words = "".join(block.splitlines()[-1] for block in raw.strip().split("\n\n"))
            self.assertEqual(re.sub(r"\s+", "", corrected_words), re.sub(r"\s+", "", approved))
            self.assertIn("หนองหมา", raw_words)
            self.assertNotIn("หนองหมา", corrected_words)
            self.assertEqual(saved["subtitle_alignment_status"], "corrected_from_approved_script")
            self.assertEqual(saved["subtitle_reference_source"], "spoken_script")
            self.assertTrue(saved["subtitle_correction_enabled"])


if __name__ == "__main__":
    unittest.main()
