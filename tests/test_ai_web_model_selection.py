import tempfile
import unittest
from pathlib import Path

from core.ai_web_models import AI_WEB_MODEL_OPTIONS, normalize_ai_web_model
from core.story_manager import StoryManager
from core.story_queue import StoryBatchQueue


ROOT = Path(__file__).resolve().parents[1]


class AiWebModelSelectionTests(unittest.TestCase):
    def test_provider_models_have_stable_keys_and_safe_defaults(self):
        self.assertEqual(normalize_ai_web_model("chatgpt", "Thinking"), "thinking")
        self.assertEqual(normalize_ai_web_model("gemini", "Flash Extended"), "long_thinking")
        self.assertEqual(normalize_ai_web_model("chatgpt", "unknown"), "auto")
        self.assertEqual(normalize_ai_web_model("gemini", "unknown"), "long_thinking")
        self.assertIn("pro", AI_WEB_MODEL_OPTIONS["chatgpt"])
        self.assertIn("flash_lite", AI_WEB_MODEL_OPTIONS["gemini"])

    def test_story_and_queue_persist_model_with_the_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            story = StoryManager(root).create(
                "เรื่องทดสอบโมเดล",
                scene_count=6,
                image_ai_provider="gemini",
                ai_web_model="flash",
            )
            self.assertEqual(story["image_ai_provider"], "gemini")
            self.assertEqual(story["ai_web_model"], "flash")

            queued = StoryBatchQueue(root).enqueue_batch(
                ["เรื่องในคิว"],
                provider="chatgpt",
                ai_web_model="pro",
            )
            self.assertEqual(queued["items"][0]["ai_web_model"], "pro")

    def test_hybrid_ui_sends_model_for_each_creation_mode(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        for element_id in ("product-model", "story-model", "story-batch-model", "drama-model"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("ai_web_model:selectedAiModel('#product-provider','#product-model')", script)
        self.assertIn("ai_web_model:selectedAiModel('#story-provider','#story-model')", script)
        self.assertIn("ai_web_model:selectedAiModel('#drama-provider','#drama-model')", script)

    def test_extension_selects_before_each_fresh_meta_step(self):
        content = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn('type: "SELECT_AI_MODEL"', content)
        self.assertIn('message?.type === "SELECT_AI_MODEL"', background)
        cover = content.split('async function runAICover(',1)[1].split('async function runMetaRedesignHelper(',1)[0]
        redesign = content.split('async function runMetaRedesignHelper(',1)[1].split('async function runSceneRepairHelper(',1)[0]
        self.assertEqual(cover.count("await ensureAiWebModel("), 1)
        # Meta's new image and video-prompt requests are separate stages.
        # A fresh helper tab selects the job model before its first Send.
        self.assertEqual(redesign.count("await ensureAiWebModel("), 2)
        self.assertEqual(content.replace(cover,'').replace(redesign,'').count("await ensureAiWebModel("), 1)
        run_position = content.index("await ensureAiWebModel(")
        analysis_position = content.index("analysisTurn = await submitPrompt", run_position)
        self.assertLess(run_position, analysis_position)
        self.assertIn("ระบบยังไม่ส่ง Prompt เพื่อป้องกันงานผิดโมเดล", content)

    def test_product_prompt_is_compact_but_keeps_required_contract(self):
        source = (ROOT / "core" / "product_manager.py").read_text(encoding="utf-8")
        start = source.index('prompt = f"""นี่เป็นงานเขียนข้อความและ JSON เท่านั้น')
        end = source.index('"""', start + len('prompt = f"""'))
        template = source[start:end]
        self.assertLess(len(template), 3000)
        for field in ("image_prompts", "flow_gui_design", "flow_shot_prompts", "spoken_script_segments"):
            self.assertIn(field, template)
        self.assertIn("ตัวเลขเป็นคำไทยทั้งหมด", template)
        self.assertIn("ไม่ต้องสร้างรูป ไม่ต้องสร้างวิดีโอ", template)


if __name__ == "__main__":
    unittest.main()
