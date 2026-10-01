"""Read exact bilingual display names without rewriting plans or resending to AI."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.story_content import (
    StoryContentError,
    _story_bilingual_display_parts,
    _story_unambiguous_display_aliases,
    validate_story_content,
)
from core.story_manager import StoryManager


ROOT = Path(__file__).resolve().parents[1]


class StoryBilingualNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.response = json.loads(
            (ROOT / "tests/fixtures/story_bilingual_names_6E3623.json").read_text(encoding="utf-8")
        )

    @staticmethod
    def entity(name="เจ้าด่าง (Chao Dang)", aliases=None, entity_id="dog"):
        return {"id": entity_id, "name": name, "aliases": aliases or [],
                "visual_identity": "The same tan dog with a white chest and red collar"}

    def simple_plan(self, name="เจ้าด่าง (Chao Dang)", prompt="Chao Dang walks home.", aliases=None):
        job = {"scene_count": 1, "story_content_contract": {"version": 1}}
        result = {"story_entities": [self.entity(name, aliases)], "scene_entities": [["dog"]],
                  "scene_prompts": [prompt], "visual_bible": {}}
        return job, result

    def test_exact_user_response_passes_all_ten_scenes_without_rewriting(self):
        job = {"scene_count": 10, "story_content_contract": {"version": 1}}
        before = copy.deepcopy(self.response)
        result = validate_story_content(job, self.response)
        self.assertEqual(result["scene_entities"], self.response["scene_entities"])
        self.assertEqual(result["story_entities"], self.response["story_entities"])
        self.assertEqual(self.response, before)
        self.assertNotIn("story_content_name_repair", result)
        self.assertNotIn("Chao Dang", result["story_entities"][0]["aliases"])
        result["story_entities"][0]["aliases"].append("changed only in returned copy")
        self.assertEqual(self.response, before)

    def test_both_display_orders_and_thai_or_latin_prompt_are_supported(self):
        for name in ("เจ้าด่าง (Chao Dang)", "Chao Dang (เจ้าด่าง)"):
            for prompt in ("Chao Dang walks home.", "เจ้าด่างเดินกลับบ้าน"):
                with self.subTest(name=name, prompt=prompt):
                    job, plan = self.simple_plan(name, prompt)
                    self.assertEqual(validate_story_content(job, plan)["story_entities"], plan["story_entities"])

    def test_nfkc_display_forms_do_not_change_saved_spelling(self):
        name = "เจ้าด่าง （Ｃｈａｏ Ｄａｎｇ）"
        job, plan = self.simple_plan(name)
        self.assertEqual(validate_story_content(job, plan)["story_entities"][0]["name"], name)

    def test_supported_proper_name_punctuation_and_token_limit(self):
        for latin in ("O'Neil", "O’Neil", "Jean-Luc", "A B C D E F", "Chao  Dang"):
            with self.subTest(latin=latin):
                self.assertEqual(_story_bilingual_display_parts(f"เจ้าด่าง ({latin})"), ["เจ้าด่าง", latin])
                job, plan = self.simple_plan(f"เจ้าด่าง ({latin})", f"{latin} walks home.")
                validate_story_content(job, plan)

    def test_descriptions_malformed_parentheses_and_non_names_are_not_inferred(self):
        names = (
            "เจ้าด่าง (a generic hero)", "เจ้าด่าง (golden tan dog)", "เจ้าด่าง (chao Dang)",
            "เจ้าด่าง (Chao Dang) extra", "เจ้าด่าง (Chao (Dang))", "เจ้าด่าง (Chao) (Dang)",
            "เจ้าด่าง ()", "(Chao Dang)", "เจ้าด่าง Chao Dang", "Chao Dang (Golden Dog)",
            "เจ้าด่าง (ด่าง)", "เจ้าด่าง2 (Chao Dang)", "เจ้าด่าง๒ (Chao Dang)",
            "เจ้าด่าง (Chao Dang 2)", "เจ้าด่าง (Chao/Dang)", "เจ้าด่าง (A B C D E F G)",
            "เจ้าด่าง (Chao\nDang)", "เจ้าด่าง (Chao\tDang)", "เจ้าด่าง (Chao_Dang)",
            "เจ้าด่าง (Chao-Dang!)", "เจ้าด่าง (" + "A" * 200 + ")",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(_story_bilingual_display_parts(name), [])
                job, plan = self.simple_plan(name)
                with self.assertRaises(StoryContentError):
                    validate_story_content(job, plan)

    def test_explicit_aliases_and_full_names_remain_valid_without_display_inference(self):
        for name, aliases, prompt in (
            ("เจ้าด่าง (golden tan dog)", ["Chao Dang"], "Chao Dang walks home."),
            ("เจ้าด่าง (golden tan dog)", [], "เจ้าด่าง (golden tan dog) walks home."),
            ("เจ้าด่าง (Chao Dang)", ["ด่าง"], "ด่างเดินกลับบ้าน"),
        ):
            with self.subTest(name=name, prompt=prompt):
                job, plan = self.simple_plan(name, prompt, aliases)
                validate_story_content(job, plan)

    def test_collision_with_other_canonical_name_suppresses_inferred_alias(self):
        job, plan = self.simple_plan()
        plan["story_entities"].append(self.entity("Chao Dang", entity_id="other"))
        with self.assertRaises(StoryContentError) as caught:
            validate_story_content(job, plan)
        self.assertEqual(caught.exception.issues[0]["code"], "ENTITY_MISSING_FROM_PROMPT")
        self.assertEqual(_story_unambiguous_display_aliases(plan["story_entities"])["dog"], ["เจ้าด่าง"])

    def test_collision_with_other_alias_uses_existing_normalization(self):
        for alias in ("Chao Dang", "chao dang", "CHAO-DANG", "Ｃｈａｏ Ｄａｎｇ"):
            with self.subTest(alias=alias):
                job, plan = self.simple_plan()
                plan["story_entities"].append(self.entity("another dog", [alias], "other"))
                with self.assertRaises(StoryContentError):
                    validate_story_content(job, plan)

    def test_collision_with_another_inferred_display_part_is_symmetric(self):
        job, plan = self.simple_plan()
        plan["story_entities"].append(self.entity("สมชาย (Chao Dang)", entity_id="other"))
        derived = _story_unambiguous_display_aliases(plan["story_entities"])
        self.assertEqual(derived["dog"], ["เจ้าด่าง"])
        self.assertEqual(derived["other"], ["สมชาย"])
        for entity_id in ("dog", "other"):
            with self.subTest(entity_id=entity_id):
                plan["scene_entities"] = [[entity_id]]
                with self.assertRaises(StoryContentError):
                    validate_story_content(job, plan)

    def test_thai_collision_ignores_spaces_like_existing_name_matcher(self):
        job, plan = self.simple_plan("เจ้า ด่าง (Chao Dang)", "เจ้าด่างเดินกลับบ้าน")
        plan["story_entities"].append(self.entity("เจ้าด่าง", entity_id="other"))
        with self.assertRaises(StoryContentError):
            validate_story_content(job, plan)
        self.assertEqual(_story_unambiguous_display_aliases(plan["story_entities"])["dog"], ["Chao Dang"])

    def test_ambiguous_inferred_alias_does_not_remove_preexisting_explicit_alias(self):
        job, plan = self.simple_plan(aliases=["Chao Dang"])
        plan["story_entities"].append(self.entity("Chao Dang", entity_id="other"))
        validate_story_content(job, plan)
        self.assertEqual(plan["story_entities"][0]["aliases"], ["Chao Dang"])

    def test_hard_anchor_requires_existing_approved_alias_not_display_inference(self):
        job, plan = self.simple_plan(aliases=["Chao Dang"])
        job["character_bible"] = [{"name": "เจ้าด่าง (Chao Dang)", "aliases": []}]
        with self.assertRaises(StoryContentError):
            validate_story_content(job, plan)
        job["character_bible"][0]["aliases"] = ["Chao Dang"]
        validate_story_content(job, plan)

    def test_generated_display_name_cannot_replace_user_canonical_anchor(self):
        for name in ("เจ้าด่าง (Chao Dang)", "คนทั่วไป (Chao Dang)", "A Generic Hero (เจ้าด่าง)"):
            with self.subTest(name=name):
                job, plan = self.simple_plan(name)
                job["character_bible"] = [{"name": "Chao Dang", "aliases": []}]
                with self.assertRaises(StoryContentError) as caught:
                    validate_story_content(job, plan)
                self.assertIn("REQUESTED_NAME_MISSING", [row["code"] for row in caught.exception.issues])

    def test_inferred_latin_name_keeps_word_boundary_not_fuzzy_substring(self):
        job, plan = self.simple_plan("ธอร์ (Thor)", "An author writes a story.")
        with self.assertRaises(StoryContentError):
            validate_story_content(job, plan)
        plan["scene_prompts"] = ["Thor raises a hammer."]
        validate_story_content(job, plan)

    def test_missing_ids_and_wrong_scene_count_remain_errors(self):
        job, plan = self.simple_plan()
        plan["scene_entities"][0].append("unknown")
        with self.assertRaises(StoryContentError) as caught:
            validate_story_content(job, plan)
        self.assertEqual(caught.exception.issues[0]["code"], "UNKNOWN_SCENE_ENTITY")
        plan["scene_entities"] = []
        with self.assertRaises(StoryContentError) as caught:
            validate_story_content(job, plan)
        self.assertEqual(caught.exception.issues[0]["code"], "INVALID_SCENE_ENTITIES")

    def test_checkpoint_and_resume_preserve_title_narration_registry_and_prompts(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = StoryManager(folder)
            job = manager.create("เจ้าด่างกลับบ้าน", "ให้เล่าเรื่องสุนัขกลับบ้าน", scene_count=10)
            response = copy.deepcopy(self.response)
            response["job_id"] = job["id"]
            before = copy.deepcopy(response)
            saved = manager.save_analysis_checkpoint(job["id"], response)
            checkpoint = manager.plugin_request(job["id"])["analysis_checkpoint"]
            for field in ("video_title", "narration_script", "scene_narrations", "scene_prompts",
                          "story_entities", "scene_entities", "visual_bible"):
                self.assertEqual(saved[field], response[field], field)
                self.assertEqual(checkpoint[field], response[field], field)
            self.assertEqual(response, before)
            self.assertNotIn("story_content_name_repair", checkpoint)
            self.assertEqual(list((manager.root / job["id"] / "generated").iterdir()), [])

    def name_repair_plan(self, phrase, before=None):
        job, plan = self.simple_plan(aliases=["ด่าง"])
        plan["story_entities"].append({"id": "third_signal", "name": "สัญญาณที่สาม", "aliases": [],
                                       "visual_identity": "a third blue light signal"})
        before = before or phrase
        after = before.replace(phrase, phrase + " (สัญญาณที่สาม)", 1)
        plan["scene_entities"] = [["dog", "third_signal"]]
        plan["scene_prompts"] = [after]
        plan["story_content_name_repair"] = {"version": 1, "changes": [{
            "scene_index": 1, "entity_id": "third_signal", "name": "สัญญาณที่สาม",
            "phrase": phrase, "before": before, "after": after,
        }]}
        return job, plan

    def test_name_repair_cannot_relabel_another_bilingual_entity(self):
        for name in ("เจ้าด่าง (Chao Dang)", "ด่าง", "Chao Dang"):
            with self.subTest(name=name):
                phrase = f"{name} walks across the floor"
                job, plan = self.name_repair_plan(phrase)
                before = copy.deepcopy(plan)
                with self.assertRaises(StoryContentError) as caught:
                    validate_story_content(job, plan)
                self.assertEqual(caught.exception.issues[0]["code"], "INVALID_NAME_REPAIR")
                self.assertEqual(plan, before)

    def test_name_repair_allows_separate_unnamed_phrase_beside_bilingual_entity(self):
        phrase = "a third blue light shines by the door"
        job, plan = self.name_repair_plan(phrase, f"Chao Dang looks up. In the distance, {phrase}.")
        clean = validate_story_content(job, plan)
        self.assertEqual(clean["story_content_name_repair"], plan["story_content_name_repair"])


if __name__ == "__main__":
    unittest.main()
