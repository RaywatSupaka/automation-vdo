"""Compact storytelling UI keeps the existing text, queue and Extension contract.

Only temporary Jobs/queues are written. No desktop, browser or provider is opened.
"""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.creation_queue import CreationQueue
from core.story_manager import StoryManager
from core.storytelling import storytelling_options
from ui.creation_queue import CreationQueueMixin


ROOT = Path(__file__).resolve().parents[1]
MODES = ('narrator', 'solo', 'dialogue', 'visual')
BRIEF = 'เริ่มจากพบกุญแจแล้วค่อยย้อนเหตุ เล่าอย่างอบอุ่น\nจบด้วยการคืนของ ห้ามเพิ่มเหตุการณ์ขายสินค้า'


def options(mode):
    return storytelling_options(dict(version=1, mode=mode, tone='warm', hook='event',
                                     ending='resolved', cta_enabled=False))


class StorytellingFreeTextContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = StoryManager(self.root)

    def package(self, mode, provider='chatgpt', brief=BRIEF):
        job = self.manager.create('คืนกุญแจ', story_text=brief, scene_count=6,
            image_ai_provider=provider, video_generation_mode='google_flow',
            storytelling_options=options(mode))
        return job, self.manager.plugin_request(job['id'])

    def test_existing_free_text_reaches_each_mode_and_provider_without_new_fields(self):
        for provider in ('chatgpt', 'gemini'):
            for mode in MODES:
                with self.subTest(provider=provider, mode=mode):
                    job, package = self.package(mode, provider)
                    self.assertEqual(job['story_input'], BRIEF)
                    self.assertIn(json.dumps(BRIEF, ensure_ascii=False), package['prompt'])
                    self.assertEqual(package['request']['storytelling_options'], options(mode))
                    self.assertEqual(package['request']['image_count'], 6)
                    self.assertNotIn('custom_instructions', package['request'])
                    restored = StoryManager(self.root).plugin_request(job['id'])
                    self.assertEqual(restored['request'], package['request'])
                    self.assertEqual(restored['prompt'], package['prompt'])

    def test_free_text_does_not_select_a_different_audio_or_delivery_mode(self):
        # Words that resemble the other mode's label are story data. The saved
        # explicit mode remains the source of speaker/audio behavior.
        job, package = self.package('visual', brief='เล่าเรื่องเกี่ยวกับนักพากย์และบทสนทนา แต่ใช้ภาพเท่านั้น')
        self.assertEqual(package['request']['storytelling_options']['mode'], 'visual')
        self.assertEqual(job['audio_choices']['mode'], 'none')
        self.assertFalse(job['audio_choices']['subtitle'])
        self.assertIn('VISUAL ONLY:', package['prompt'])
        job, package = self.package('narrator', brief='ผู้บรรยายเล่าว่าตัวละครพูดคนเดียวในใจ')
        self.assertEqual(package['request']['storytelling_options']['mode'], 'narrator')
        self.assertFalse(job.get('actor_dialogue', False))
        self.assertIn('NARRATED MODE:', package['prompt'])

    def test_queue_text_and_options_survive_live_draft_changes_edit_and_restart(self):
        for mode in MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                queue = CreationQueue(folder)
                settings = dict(storytelling_options=options(mode),
                    audio_choices=dict(mode='flow_original', subtitle=False, music=False, sfx=False),
                    voice_reference_id='saved-synthetic-voice')
                saved = copy.deepcopy(settings)
                row = queue.enqueue('story', ['คืนกุญแจ'], story_text=BRIEF,
                    provider='gemini', scene_count=6, video_generation_mode='google_flow',
                    settings=settings)['items'][0]
                settings['storytelling_options'].update(mode='narrator', tone='mystery')
                settings['voice_reference_id'] = 'new-live-form-voice'
                row['story_text'] = 'new live form story'
                row['settings']['storytelling_options']['tone'] = 'drama'
                queue.edit(row['queue_id'], 'เปลี่ยนเฉพาะชื่อเรื่อง')
                restored = CreationQueue(folder)
                restored.recover_on_startup()
                restored.resume()
                claimed = restored.claim_next()
                self.assertEqual(claimed['story_text'], BRIEF)
                self.assertEqual(claimed['provider'], 'gemini')
                self.assertEqual(claimed['settings']['storytelling_options'], saved['storytelling_options'])
                owner = SimpleNamespace(story_queue=restored,
                    _story_audio_choices={'mode': 'api'},
                    cfg={'storytelling_options': options('narrator')})
                captured = CreationQueueMixin._creation_settings(owner)
                self.assertEqual(captured['storytelling_options'], saved['storytelling_options'])
                self.assertEqual(captured['audio_choices'], saved['audio_choices'])
                self.assertEqual(captured['voice_reference_id'], 'saved-synthetic-voice')
                captured['storytelling_options']['tone'] = 'comedy'
                self.assertEqual(restored.running_item()['settings']['storytelling_options'], saved['storytelling_options'])

    def test_legacy_free_text_job_and_queue_are_not_upgraded_on_read(self):
        job = self.manager.create('งานเดิม', story_text=BRIEF, scene_count=6)
        first = self.manager.plugin_request(job['id'])
        second = StoryManager(self.root).plugin_request(job['id'])
        self.assertNotIn('storytelling_options', first['request'])
        self.assertEqual(first['request'], second['request'])
        self.assertEqual(first['prompt'], second['prompt'])
        queue = CreationQueue(self.root)
        row = queue.enqueue('story', ['งานเดิม'], story_text=BRIEF, scene_count=6)['items'][0]
        queue.edit(row['queue_id'], 'แก้ชื่อของงานเดิม')
        saved = CreationQueue(self.root).get_item(row['queue_id'])
        self.assertEqual(saved['story_text'], BRIEF)
        self.assertNotIn('storytelling_options', saved['settings'])

    def test_actual_extension_accepts_existing_packages_and_preserves_repair_contract(self):
        cases = []
        for provider in ('chatgpt', 'gemini'):
            for mode in MODES:
                job, package = self.package(mode, provider)
                cases.append(dict(provider=provider, mode=mode, brief=BRIEF,
                                  package=package))
        result = subprocess.run(['node', 'tests/storytelling_free_text_contract_20260927.cjs'],
            cwd=ROOT, input=json.dumps(cases, ensure_ascii=False), capture_output=True,
            text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary['cases'], 8)
        self.assertEqual(summary['providerRequests'], 0)
        self.assertGreaterEqual(summary['checks'], 80)


if __name__ == '__main__':
    unittest.main()
