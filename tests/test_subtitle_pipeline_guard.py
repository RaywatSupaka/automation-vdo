import unittest

from ui.main_window import MainWindow


class _Var:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class SubtitlePipelineGuardTests(unittest.TestCase):
    def test_pending_subtitle_does_not_compete_with_active_product_pipeline(self):
        active_job = {
            "id": "JOB-ACTIVE",
            "subtitle_requested": True,
            "voice_status": "ready",
            "subtitle_status": "not_generated",
        }
        window = MainWindow.__new__(MainWindow)
        window.subtitle_auto = _Var(True)
        window.subtitle_job_id = _Var("")
        window._subtitle_active_job = None
        window._product_pipeline_job_id = "JOB-ACTIVE"
        window.products = type("Products", (), {"list_jobs": lambda self: [active_job]})()
        window._subtitle_store = lambda: type("Store", (), {"load": lambda self: "credential"})()
        started = []
        window._start_subtitle_for_job = started.append

        window._resume_pending_subtitles()

        self.assertEqual(started, [])
        self.assertEqual(window.subtitle_job_id.get(), "")

    def test_manual_subtitle_start_defers_to_active_product_pipeline(self):
        window = MainWindow.__new__(MainWindow)
        window._product_pipeline_job_id = "JOB-ACTIVE"
        window._subtitle_active_job = None
        window.subtitle_status = _Var("")

        window._start_subtitle_for_job("JOB-ACTIVE")

        self.assertIn("One-click", window.subtitle_status.get())
        self.assertIsNone(window._subtitle_active_job)


if __name__ == "__main__":
    unittest.main()
