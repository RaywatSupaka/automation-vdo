import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from core import config as config_module
from core.atomic_json import AtomicJsonFile, JsonPersistenceError, runtime_backup_path
from core.story_queue import StoryBatchQueue


class AtomicJsonTests(unittest.TestCase):
    def test_peek_reads_backup_without_repairing_primary(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'job.json'
            store = AtomicJsonFile(target)
            store.write({'id': 'JOB-READ-ONLY'})
            target.write_text('{broken', encoding='utf-8')
            self.assertEqual(store.peek(), {'id': 'JOB-READ-ONLY'})
            self.assertEqual(target.read_text(encoding='utf-8'), '{broken')
            self.assertEqual(store.read(), {'id': 'JOB-READ-ONLY'})
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'id': 'JOB-READ-ONLY'})

    def test_missing_primary_with_corrupt_backup_cannot_reset_existing_queue(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'queue.json'
            backup = root / 'queue.backup.json'
            backup.write_text('{broken-existing-queue', encoding='utf-8')
            store = AtomicJsonFile(target, backup_path=backup)
            with self.assertRaises(JsonPersistenceError):
                store.update(lambda value: value, default={'items': []})
            self.assertFalse(target.exists())
            self.assertEqual(backup.read_text(encoding='utf-8'), '{broken-existing-queue')

    def test_missing_primary_recovers_valid_backup_but_new_store_can_use_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'queue.json'
            store = AtomicJsonFile(target)
            self.assertEqual(store.read({'items': []}), {'items': []})
            store.backup_path.write_text('{"items":["saved-job"]}', encoding='utf-8')
            self.assertEqual(store.read({'items': []}), {'items': ['saved-job']})
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'items': ['saved-job']})

    def test_parallel_config_panels_preserve_both_updates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config.json").write_text(
                json.dumps({"logo_opacity": 0.5, "video_fps": 30}),
                encoding="utf-8",
            )
            barrier = threading.Barrier(3)
            failures = []

            def save_logo():
                try:
                    barrier.wait()
                    config_module.save_logo_settings({"logo_opacity": 0.77})
                except Exception as exc:  # pragma: no cover - asserted below
                    failures.append(exc)

            def save_video():
                try:
                    barrier.wait()
                    config_module.save_video_settings({"video_fps": 60})
                except Exception as exc:  # pragma: no cover - asserted below
                    failures.append(exc)

            with mock.patch.object(config_module, "ROOT", root):
                threads = [threading.Thread(target=save_logo), threading.Thread(target=save_video)]
                for thread in threads:
                    thread.start()
                barrier.wait()
                for thread in threads:
                    thread.join(timeout=5)

            self.assertEqual(failures, [])
            saved = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["logo_opacity"], 0.77)
            self.assertEqual(saved["video_fps"], 60)

    def test_story_queue_instances_do_not_lose_parallel_enqueues(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = StoryBatchQueue(temporary)
            second = StoryBatchQueue(temporary)
            barrier = threading.Barrier(3)
            failures = []

            def enqueue(queue, topic):
                try:
                    barrier.wait()
                    queue.enqueue_batch([topic])
                except Exception as exc:  # pragma: no cover - asserted below
                    failures.append(exc)

            threads = [
                threading.Thread(target=enqueue, args=(first, "เรื่องแรก")),
                threading.Thread(target=enqueue, args=(second, "เรื่องที่สอง")),
            ]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join(timeout=5)

            self.assertEqual(failures, [])
            topics = {item["topic"] for item in StoryBatchQueue(temporary).snapshot()["items"]}
            self.assertEqual(topics, {"เรื่องแรก", "เรื่องที่สอง"})

    def test_story_queue_recovers_last_known_good_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = StoryBatchQueue(root)
            queue.enqueue_batch(["คิวที่ต้องไม่หาย"])
            queue.path.write_text("{broken", encoding="utf-8")

            restored = StoryBatchQueue(root).snapshot()

            self.assertEqual([item["topic"] for item in restored["items"]], ["คิวที่ต้องไม่หาย"])
            self.assertIsInstance(json.loads(queue.path.read_text(encoding="utf-8")), dict)

    def test_existing_corrupt_queue_without_backup_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue_path = root / "workspace" / "story_batch_queue.json"
            queue_path.parent.mkdir(parents=True)
            queue_path.write_text("not-json", encoding="utf-8")

            queue = StoryBatchQueue(root)
            with self.assertRaises(JsonPersistenceError):
                queue.snapshot()

            self.assertEqual(queue_path.read_text(encoding="utf-8"), "not-json")

    def test_atomic_store_keeps_backup_outside_runtime_folder_and_cleans_temps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "workspace" / "products" / "JOB-ONE" / "job.json"
            backup = runtime_backup_path(root, target)
            store = AtomicJsonFile(target, backup_path=backup)

            store.write({"id": "JOB-ONE", "revision": 1})

            self.assertEqual(store.read()["id"], "JOB-ONE")
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8"))["revision"], 1)
            self.assertEqual(list(root.rglob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
