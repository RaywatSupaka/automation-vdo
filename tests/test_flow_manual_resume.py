import unittest
import tempfile
from pathlib import Path
from core.atomic_json import AtomicJsonFile
from core.flow_review import request_scene_repair_resume


class ManualFlowResumeTests(unittest.TestCase):
    def test_exact_failed_scene_and_duplicate_click_preserve_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            clip=folder/'scene1.mp4'; clip.write_bytes(b'existing clip')
            ledger=AtomicJsonFile(folder/'prompts'/'flow_recovery.json')
            ledger.write({'scenes':{'6':[{'phase':'needs_review','request_id':'r1','digest':'d1','at':'2026-09-11'}]}})
            job={'id':'STORY-X','status':'error','last_error':'FLOW_REPAIR_REVIEW'}
            first=request_scene_repair_resume(folder,job)
            self.assertEqual(first['index'],6)
            self.assertEqual(first,request_scene_repair_resume(folder,job))
            self.assertEqual(clip.read_bytes(),b'existing clip')
            self.assertIsNone(request_scene_repair_resume(folder,{**job,'status':'running'}))
            ledger.write({'scenes':{'6':[{'phase':'needs_review','request_id':'r2','digest':'d2','at':'2026-09-12'}]}})
            self.assertNotEqual(first['token'],request_scene_repair_resume(folder,job)['token'])

    def test_unknown_send_does_not_authorize_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            AtomicJsonFile(folder/'prompts'/'flow_recovery.json').write({'scenes':{'6':[{'phase':'rewrite_sent'}]}})
            self.assertIsNone(request_scene_repair_resume(folder,{'id':'STORY-X','status':'error','last_error':'FLOW_REPAIR_REVIEW'}))
