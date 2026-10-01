import csv
import tempfile
import unittest
from pathlib import Path

from core.job_manager import FIELDS, JobManager


class JobManagerTests(unittest.TestCase):
    def test_migrates_old_csv_and_prevents_active_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); csv_path = root / "jobs.csv"; video = root / "video.mp4"; video.write_bytes(b"video")
            csv_path.write_text("video_file,caption,status\nold.mp4,test,pending\n", encoding="utf-8")
            jobs = JobManager(csv_path)
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(next(csv.reader(handle)), FIELDS)
            self.assertTrue(jobs.add(video))
            self.assertFalse(jobs.add(video))
            self.assertEqual(len(jobs.load()), 2)


if __name__ == "__main__": unittest.main()
