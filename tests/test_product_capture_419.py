"""Shopee source-preparation command handoff; no network/provider generation."""
import tempfile
import unittest
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from PIL import Image
from core.atomic_json import AtomicJsonFile
from core.product_story import prepare_link


class ProductCapture419Tests(unittest.TestCase):
    def test_actual_extension_capture_block(self):
        if not (Path(__file__).resolve().parents[1] / 'deliverables/SmartFlow_AI_Extension_0.15.418/background.js').is_file():
            self.skipTest('Historical 418 Extension is not available in this checkout')
        result=subprocess.run(['node','tests/product_capture_419.cjs'],cwd=Path(__file__).resolve().parents[1],
                              capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_product_preparation_ui(self):
        result=subprocess.run(['node','tests/product_story_ui.js'],cwd=Path(__file__).resolve().parents[1],
                              capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.store=AtomicJsonFile(root/'JOB-X'/'job.json')
        self.product={'id':'JOB-X','product_name':'Bag','source_images':[],'story_source_only':True}
        self.store.write(self.product)
        self.products=SimpleNamespace(root=root,project_root=root,_manifest_store=lambda _path:self.store,
            import_link=lambda *_a,**_k:(self.store.read({}),True),get_job=lambda _id:self.store.read({}))
        self.command={'id':'CMD-X','status':'pending','lease_token':'MUST-NOT-PERSIST'}
        self.bridge=Mock();self.bridge.queue_extension_command.return_value=self.command
        self.bridge.extension_command_status.side_effect=lambda _id:dict(self.command) if self.command else None
        self.cast=Mock();self.cast.snapshot.return_value={'kind':'product_story','snapshot_id':'saved'}

    def start(self):
        return prepare_link(self.products,self.cast,self.bridge,{'link':'https://shopee.co.th/item'})

    def poll(self):
        return prepare_link(self.products,self.cast,self.bridge,{'product_id':'JOB-X'})

    def save_real_image(self):
        target=Path(self.temp.name)/'JOB-X'/'original'/'product.jpg'
        target.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(24,32),'navy').save(target,format='JPEG')
        self.store.update(lambda row:{**row,'source_images':['original/product.jpg']})

    def test_pending_persists_exact_command_id_without_lease_or_duplicate_dispatch(self):
        self.assertTrue(self.start()['pending'])
        for _ in range(5):self.assertTrue(self.poll()['pending'])
        self.bridge.queue_extension_command.assert_called_once()
        self.assertEqual(self.store.read({})['story_capture_command_id'],'CMD-X')
        self.assertNotIn('MUST-NOT-PERSIST',self.store.path.read_text())
        self.cast.snapshot.assert_not_called()

    def test_capture_failure_is_not_silent_pending(self):
        self.start();self.command.update(status='failed',error='Shopee login required')
        with self.assertRaisesRegex(ValueError,'Shopee login required'):self.poll()
        self.cast.snapshot.assert_not_called()

    def test_completed_without_local_image_cannot_dispatch_ai(self):
        self.start();self.command.update(status='completed')
        with self.assertRaisesRegex(ValueError,'ไฟล์รูปในเครื่องยังไม่พร้อมใช้งาน'):self.poll()
        self.cast.snapshot.assert_not_called()

    def test_lost_command_after_restart_requeues_same_saved_product(self):
        self.start();self.command.clear()
        self.bridge.queue_extension_command.return_value={'id':'CMD-Y','status':'pending'}
        self.assertTrue(self.poll()['pending'])
        self.assertEqual(self.store.read({})['story_capture_command_id'],'CMD-Y')
        self.assertEqual(self.bridge.queue_extension_command.call_count,2)

    def test_real_saved_data_can_continue_before_delayed_ack(self):
        self.start()
        self.save_real_image()
        self.assertEqual(self.poll()['creative_context']['snapshot_id'],'saved')
        self.cast.snapshot.assert_called_once()
        self.bridge.queue_extension_command.assert_called_once()

    def test_import_completes_between_manifest_read_and_command_ack(self):
        self.start()
        def completed_during_poll(_id):
            self.save_real_image()
            return {**self.command,'status':'completed'}
        self.bridge.extension_command_status.side_effect=completed_during_poll
        self.assertEqual(self.poll()['creative_context']['snapshot_id'],'saved')
        self.cast.snapshot.assert_called_once()
        self.bridge.queue_extension_command.assert_called_once()

    def test_legacy_preparation_without_command_requeues_for_same_product(self):
        self.assertTrue(self.poll()['pending'])
        self.bridge.extension_command_status.assert_called_once_with('CMD-X')
        self.bridge.queue_extension_command.assert_called_once_with('capture_shopee_product','JOB-X')


if __name__=='__main__':unittest.main()
