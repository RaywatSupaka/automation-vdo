import unittest

from ui.main_window import MainWindow


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class StoryProgressTests(unittest.TestCase):
    def _window(self):
        window = MainWindow.__new__(MainWindow)
        window._story_progress_value = DummyVar(92)
        window._story_progress_percent = DummyVar("92%")
        window._story_progress_message = DummyVar("กำลังใส่โลโก้")
        window._story_progress_detail = DummyVar("ขั้นตอนสุดท้าย")
        window._story_progress_stage_widgets = {}
        window._story_pipeline_job_id = "STORY-TEST"
        window.story_job_id = DummyVar("STORY-TEST")
        window.story_status = DummyVar("")
        window.status = DummyVar("")
        window._write_console = lambda *args, **kwargs: None
        return window

    def test_stale_browser_progress_cannot_replace_later_render_progress(self):
        window = self._window()

        window._update_story_progress({
            "percent": 60,
            "stage": "voice",
            "message": "ผลจาก Browser มาถึงช้า",
            "detail": "ภาพครบแล้ว",
        })

        self.assertEqual(window._story_progress_value.get(), 92)
        self.assertEqual(window._story_progress_percent.get(), "92%")
        self.assertEqual(window._story_progress_message.get(), "กำลังใส่โลโก้")
        self.assertEqual(window._story_progress_detail.get(), "ขั้นตอนสุดท้าย")

    def test_newer_progress_still_updates_without_tk_dialog(self):
        window = self._window()

        window._update_story_progress({
            "percent": 96,
            "stage": "finishing",
            "message": "กำลังเก็บไฟล์",
            "detail": "ตรวจไฟล์วิดีโอ",
        })

        self.assertEqual(window._story_progress_value.get(), 96)
        self.assertEqual(window._story_progress_percent.get(), "96%")
        self.assertEqual(window._story_progress_message.get(), "กำลังเก็บไฟล์")


if __name__ == "__main__":
    unittest.main()
