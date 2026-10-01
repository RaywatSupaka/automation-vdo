import tempfile
import unittest
from pathlib import Path

from core.story_queue import StoryBatchQueue


class StoryBatchQueueTests(unittest.TestCase):
    def test_ten_topics_run_in_fifo_order_and_persist(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = StoryBatchQueue(temporary)
            topics = [f"เรื่องที่ {index}" for index in range(1, 11)]
            created = queue.enqueue_batch(topics, "แนวทางร่วม", "chatgpt", 8)
            self.assertEqual(len(created["items"]), 10)
            self.assertTrue(queue.snapshot()["paused"])
            self.assertIsNone(queue.claim_next())
            queue.resume()
            first = queue.claim_next()
            self.assertEqual(first["topic"], topics[0])
            queue.attach_job(first["queue_id"], "STORY-ONE")
            self.assertIsNone(queue.claim_next())
            queue.mark_completed_by_job("STORY-ONE", "final.mp4")
            second = StoryBatchQueue(temporary).claim_next()
            self.assertEqual(second["topic"], topics[1])
            self.assertEqual(StoryBatchQueue(temporary).snapshot()["counts"]["completed"], 1)

    def test_failed_item_does_not_block_next_item(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = StoryBatchQueue(temporary)
            queue.enqueue_batch(["หนึ่ง", "สอง"])
            queue.resume()
            first = queue.claim_next()
            queue.attach_job(first["queue_id"], "STORY-FAIL")
            queue.mark_failed_by_job("STORY-FAIL", "ทดสอบผิดพลาด")
            self.assertEqual(queue.claim_next()["topic"], "สอง")

    def test_batch_keeps_story_video_mode_for_every_queued_clip(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = StoryBatchQueue(temporary)
            created = queue.enqueue_batch(
                ["หนึ่ง", "สอง"], video_generation_mode="google_flow"
            )
            self.assertTrue(all(item["video_generation_mode"] == "google_flow" for item in created["items"]))
            queue.resume()
            self.assertEqual(queue.claim_next()["video_generation_mode"], "google_flow")

    def test_pause_resume_clear_and_batch_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = StoryBatchQueue(temporary)
            queue.enqueue_batch(["หนึ่ง"])
            queue.pause()
            self.assertIsNone(queue.claim_next())
            queue.resume()
            item = queue.claim_next()
            queue.fail_item(item["queue_id"], "หยุด")
            self.assertEqual(queue.clear_finished(), 1)
            self.assertEqual(queue.snapshot()["total_count"], 0)
            with self.assertRaisesRegex(ValueError, "สูงสุดครั้งละ 10"):
                queue.enqueue_batch([str(index) for index in range(11)])

    def test_pause_reason_persists_until_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = StoryBatchQueue(temporary)
            queue.enqueue_batch(["หนึ่ง"])
            self.assertEqual(queue.snapshot()["pause_reason"], "awaiting_user_start")
            queue.pause("drama_failure:SERIES-TEST:2")
            restored = StoryBatchQueue(temporary).snapshot()
            self.assertTrue(restored["paused"])
            self.assertEqual(restored["pause_reason"], "drama_failure:SERIES-TEST:2")
            queue.resume()
            self.assertFalse(queue.snapshot()["paused"])
            self.assertEqual(queue.snapshot()["pause_reason"], "")

    def test_drama_series_is_queued_by_episode_and_stays_paused_until_started(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = StoryBatchQueue(temporary)
            result = queue.enqueue_drama_series("SERIES-20260828-ABCDEF", "ร้านกาแฟ", 3, "gemini", 8)
            self.assertEqual(len(result["items"]), 3)
            self.assertTrue(queue.snapshot()["paused"])
            self.assertIsNone(queue.claim_next())
            queue.resume()
            first = queue.claim_next()
            self.assertEqual(first["mode"], "drama")
            self.assertEqual(first["episode_no"], 1)
            self.assertEqual(first["topic"], "ร้านกาแฟ • EP 1")

    def test_appended_drama_episode_keeps_real_episode_number(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = StoryBatchQueue(temporary)
            result = queue.enqueue_drama_episode("SERIES-20260828-ABCDEF", "ร้านกาแฟ", 4, 4, "chatgpt", 9)
            self.assertEqual(len(result["items"]), 1)
            self.assertTrue(queue.snapshot()["paused"])
            queue.resume()
            item = queue.claim_next()
            self.assertEqual(item["mode"], "drama")
            self.assertEqual(item["episode_no"], 4)
            self.assertEqual(item["episode_count"], 4)
            self.assertEqual(item["topic"], "ร้านกาแฟ • EP 4")

    def test_failed_episode_retry_is_placed_before_later_series_episode(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = StoryBatchQueue(temporary)
            queue.enqueue_drama_series("SERIES-20260828-ABCDEF", "ร้านกาแฟ", 3, "chatgpt", 8)
            queue.resume()
            first = queue.claim_next()
            queue.fail_item(first["queue_id"], "เตรียมข้อมูลไม่สำเร็จ")
            queue.enqueue_drama_episode(
                "SERIES-20260828-ABCDEF", "ร้านกาแฟ", 1, 3, "chatgpt", 8, priority=True
            )
            queue.resume()
            retried = queue.claim_next()
            self.assertEqual(retried["episode_no"], 1)

    def test_cancel_drama_series_releases_old_queue_without_touching_other_series(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = StoryBatchQueue(temporary)
            first = queue.enqueue_drama_series("SERIES-20260828-ABCDEF", "เรื่องเก่า", 3)
            queue.resume()
            running = queue.claim_next()
            queue.attach_job(running["queue_id"], "STORY-RUNNING")
            queue.enqueue_drama_episode("SERIES-20260828-OTHER1", "เรื่องอื่น", 1, 1)
            result = queue.cancel_drama_series("SERIES-20260828-ABCDEF")
            self.assertEqual(result["cancelled"], 3)
            self.assertEqual(result["running_job_ids"], ["STORY-RUNNING"])
            snapshot = queue.snapshot()
            old = [item for item in snapshot["items"] if item.get("series_id") == "SERIES-20260828-ABCDEF"]
            other = [item for item in snapshot["items"] if item.get("series_id") == "SERIES-20260828-OTHER1"]
            self.assertTrue(all(item["status"] == "cancelled" for item in old))
            self.assertEqual(other[0]["status"], "queued")
            self.assertEqual(snapshot["active_count"], 1)


if __name__ == "__main__":
    unittest.main()
