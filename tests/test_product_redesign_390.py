import unittest
import test_product_prompt_repair_389 as legacy
from test_product_image_recovery import encoded


class ProductRedesign390(unittest.TestCase):
    setUp = legacy.ProductPromptRepair389.setUp
    fail = legacy.ProductPromptRepair389.fail

    def op(self, operation, **extra):
        return legacy.ProductPromptRepair389.op(self, operation, **dict(contract_version=2, **extra))

    def proposal(self, number=1):
        return dict(legacy.ProductPromptRepair389.proposal(self, number),
            visual_concept=f'Product in a completely new studio composition with camera setup number {number}.',
            visual_changes=['Use overhead camera instead of front view.', 'Use plain daylight staging instead of the original scene.'],
            substantive_redesign=True, product_facts_preserved=True)

    approved = legacy.ProductPromptRepair389.approved

    def test_requires_substantive_typed_design_not_just_new_words(self):
        for changes in [dict(visual_concept=''), dict(visual_changes=['new words']), dict(substantive_redesign=False),
                        dict(substantive_redesign='true'), dict(product_facts_preserved=False),
                        dict(visual_changes=['Same camera changes twice.']*2)]:
            with self.subTest(changes=changes):
                self.recovery.store.write({}); self.recovery.start(self.analysis); self.fail()
                repair = self.approved(dict(self.proposal(), **changes))
                self.assertEqual(repair['phase'], 'needs_review')
                with self.assertRaises(ValueError): self.op('reserve_repaired', request_id=repair['request_id'])

    def test_technical_rounds_change_concept_and_reject_source_pixels(self):
        from PIL import Image
        Image.new('RGB', (320, 500), 'white').save(self.recovery.folder / 'original/a.png')
        self.recovery.store.write({})
        self.revision = self.recovery.start(self.analysis)['revision']
        self.fail()
        repair = self.approved()
        reserved = self.op('reserve_repaired', request_id=repair['request_id'])
        source = self.recovery.folder / 'original/a.png'
        import base64
        copied = 'data:image/png;base64,'+base64.b64encode(source.read_bytes()).decode()
        self.op('finish', token=reserved['token'], outcome='succeeded', image=copied)
        slot = self.recovery.state()['slots']['1']
        self.assertEqual(slot['status'], 'failed')
        self.assertEqual(slot['reason'], 'redesign_reused_image')
        self.assertFalse(self.recovery._file(1).exists())
        repair = self.approved(dict(self.proposal(2), visual_concept=self.proposal()['visual_concept']))
        self.assertEqual(repair['phase'], 'needs_review')

    def test_reencoded_prior_failed_candidate_is_not_new_image(self):
        r = self.recovery.reserve(self.revision, 2, 'RUN-1', 'saved-other-slot')
        self.recovery.finish(self.revision, 2, 'RUN-1', r['token'], 'succeeded', encoded('red'))
        self.fail()
        for number in [1, 2]:
            repair = self.approved(self.proposal(number))
            reserved = self.op('reserve_repaired', request_id=repair['request_id'])
            self.op('finish', token=reserved['token'], outcome='succeeded', image=encoded('red'))
            slot = self.recovery.state()['slots']['1']
            self.assertEqual(slot['status'], 'failed')
            self.assertEqual(slot['reason'], 'duplicate_image' if number == 1 else 'redesign_reused_image')
        self.assertEqual(len(slot['candidate_images']), 2)
        self.assertEqual(self.recovery.state()['slots']['2']['status'], 'succeeded')

    def test_history_new_real_media_and_idempotent_approval(self):
        self.fail()
        for number in range(1, 5):
            repair = self.approved(self.proposal(number))
            self.assertEqual(repair['phase'], 'approved')
            again = self.op('approve_repair', request_id=repair['request_id'], candidate=self.proposal(number))
            self.assertEqual(again['repair'], repair)
            reserved = self.op('reserve_repaired', request_id=repair['request_id'])
            if number < 4: self.fail(reservation=reserved)
            else: self.op('finish', token=reserved['token'], outcome='succeeded', image=encoded('red'))
        state = self.recovery.state(); slot = state['slots']['1']
        self.assertEqual(slot['status'], 'succeeded')
        self.assertEqual(len(slot['prompt_repair_history']), 3)
        self.assertEqual(slot['candidate_images'][0]['pixel_sha256'], slot['pixel_sha256'])
        self.assertEqual(state['analysis'], self.analysis)

    def test_pending_legacy_proposal_not_reinterpreted_or_reissued(self):
        self.fail()
        legacy_repair = self.recovery.request(dict(operation='prepare_repair', revision=self.revision,index=1,run_id='RUN-1'))['repair']
        adopted = self.op('prepare_repair')['repair']
        self.assertEqual(adopted, legacy_repair)
        self.assertEqual(adopted['contract_version'],1)
