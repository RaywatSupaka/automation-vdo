import base64
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from core.product_story import ProductCast,attach_context,story_brief
from core.atomic_json import AtomicJsonFile
from core.story_manager import StoryManager
from core.creation_queue import clean_settings
from unittest.mock import Mock, patch
from core.product_story import prepare_link
from core.product_manager import ProductManager


class ProductStoryTests(unittest.TestCase):
    def source_product(self, with_image=False):
        manager = ProductManager(self.root)
        product, _ = manager.import_product({
            'product_id': '123', 'product_name': 'Bag',
            'product_url': 'https://shopee.co.th/item/123', 'images': [],
        }, force_new=True)
        manager._manifest_store(manager.root / product['id'] / 'job.json').update(
            lambda row: {**row, 'story_source_only': True}
        )
        if with_image:
            path = manager.root / product['id'] / 'original' / 'product_01.jpg'
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (256, 400), 'blue').save(path, format='JPEG')
            product = manager._manifest_store(manager.root / product['id'] / 'job.json').update(
                lambda row: {**row, 'source_images': ['original/product_01.jpg']}
            )
        return manager, product

    def test_link_only_uses_existing_extension_capture_once_then_snapshots(self):
        products,product=self.source_product()
        cast=Mock();cast.snapshot.return_value={'kind':'product_story','snapshot_id':'saved'}
        bridge=Mock()
        bridge.queue_extension_command.return_value={'id':'CMD-X'}
        bridge.extension_command_status.return_value={'status':'pending'}
        first=prepare_link(products,cast,bridge,{'product_id':product['id'],'cast_id':'person'})
        self.assertTrue(first['pending']);cast.snapshot.assert_not_called()
        self.assertEqual(first['product_id'],product['id'])
        bridge.queue_extension_command.assert_called_once_with('capture_shopee_product',product['id'])
        def download(_url, folder, index):
            target=Path(folder)/f'product_{index:02d}.jpg';target.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGB',(256,400),'blue').save(target,format='JPEG');return target
        with patch.object(products,'_download_image',side_effect=download):
            captured,_=products.import_product({'product_id':'123','product_name':'Bag',
                'product_url':'https://shopee.co.th/item/123','images':['https://img.example/p.jpg']},
                target_job_id=product['id'],target_capture_command_id='CMD-X')
        bridge.extension_command_status.return_value={'status':'completed'}
        result=prepare_link(products,cast,bridge,{'product_id':product['id'],'cast_id':'person'})
        self.assertEqual(result['creative_context']['snapshot_id'],'saved')
        self.assertEqual(result['creative_context']['source_product_id'],product['id'])
        cast.snapshot.assert_called_once_with(products,captured,'person')

    def test_ready_link_never_requests_upload_or_browser_capture(self):
        products,product=self.source_product(with_image=True)
        bridge=Mock();cast=Mock()
        cast.snapshot.return_value={'kind':'product_story','snapshot_id':'saved'}
        result=prepare_link(products,cast,bridge,{'product_id':product['id']})
        self.assertNotIn('pending',result);bridge.queue_extension_command.assert_not_called()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.cast=ProductCast(self.root)
        buf=io.BytesIO();Image.new('RGB',(256,400),'blue').save(buf,format='PNG')
        self.raw=buf.getvalue();self.data='data:image/png;base64,'+base64.b64encode(self.raw).decode()

    def test_upload_persist_and_hide_preserves_original(self):
        row=self.cast.add('Model',self.data);path=self.cast.reference(row['id']);self.assertTrue(path.is_file())
        self.cast.edit(row['id'],name='New');self.assertEqual(self.cast.state()[0]['name'],'New')
        self.cast.edit(row['id'],hidden=True);self.assertEqual(self.cast.state(),[]);self.assertTrue(path.is_file())

    def test_saved_outfit_is_frozen_with_product_and_person_references(self):
        row=self.cast.add('Model',self.data)
        self.cast.set_outfit(row['id'],self.data)
        self.assertTrue(self.cast.state()[0]['outfit_preview'].startswith('data:image/jpeg;base64,'))
        product_folder=self.root/'products'/'JOB-CLOTHES';product_folder.mkdir(parents=True)
        source=product_folder/'product.png';source.write_bytes(self.raw)
        second=product_folder/'detail.png';second.write_bytes(self.raw)
        product={'id':'JOB-CLOTHES','product_name':'Bag','source_images':['product.png','detail.png']}
        products=SimpleNamespace(root=product_folder.parent)
        context=self.cast.snapshot(products,product,row['id'],'saved')
        self.cast.set_outfit(row['id'],'data:image/png;base64,'+base64.b64encode(
            self._image_bytes('red')).decode())
        stories=StoryManager(self.root);job=stories.create('Bag',video_generation_mode='meta_ai')
        attach_context(stories,products,self.cast,job,context);stories._save(job)
        stories._write_request(stories.root/job['id'],job)
        self.assertEqual(job['product_story']['reference_roles'],['product','product','person','outfit'])
        self.assertEqual(job['product_story']['outfit_mode'],'saved')
        self.assertEqual(len(stories.plugin_request(job['id'])['request']['image_files']),4)
        self.assertIn('outfit', (stories.root/job['id']/'prompts/chatgpt_request.txt').read_text(encoding='utf8'))
        self.assertNotEqual((stories.root/job['id']/job['source_images'][-1]).read_bytes(),
                            self.cast.outfit_reference(row['id']).read_bytes())

    @staticmethod
    def _image_bytes(color):
        output=io.BytesIO();Image.new('RGB',(256,400),color).save(output,format='PNG');return output.getvalue()

    def test_saved_outfit_requires_approved_model_and_product_mode_reuses_product(self):
        product_folder=self.root/'products'/'JOB-SHIRT';product_folder.mkdir(parents=True)
        (product_folder/'shirt.png').write_bytes(self.raw)
        product={'id':'JOB-SHIRT','product_name':'Shirt','source_images':['shirt.png']}
        products=SimpleNamespace(root=product_folder.parent)
        with self.assertRaisesRegex(ValueError,'นายแบบ'):
            self.cast.snapshot(products,product,'','saved')
        context=self.cast.snapshot(products,product,'','product')
        data=AtomicJsonFile(self.cast.root/'snapshots'/context['snapshot_id']/'input.json').read()
        self.assertEqual(data['reference_roles'],['product'])
        self.assertEqual(data['outfit_mode'],'product')

    def test_clearing_outfit_hides_choice_without_deleting_saved_file(self):
        row=self.cast.add('Model',self.data)
        saved=self.cast.set_outfit(row['id'],self.data)
        source=self.cast.root/row['id']/saved['outfit_file']
        self.cast.clear_outfit(row['id'])
        self.assertTrue(source.is_file())
        self.assertEqual(self.cast.state()[0]['outfit_preview'],'')
        with self.assertRaisesRegex(ValueError,'รูปชุด'):
            self.cast.outfit_reference(row['id'])

    def test_new_product_meta_prompt_preserves_clothed_starting_image(self):
        from core.meta_video import MetaVideoManager
        stories=StoryManager(self.root)
        job=stories.create('Shirt',video_generation_mode='meta_ai')
        folder=stories.root/job['id'];(folder/'generated').mkdir(exist_ok=True)
        Image.new('RGB',(256,400),'blue').save(folder/'generated/scene.png')
        job.update(product_story={'outfit_mode':'product'},generated_images=['generated/scene.png'],
                   scene_prompts=['adult wearing the shirt']*job['scene_count'],
                   scene_narrations=['shows the shirt']*job['scene_count'])
        stories._save(job)
        prompt=MetaVideoManager(stories).package(job['id'],1)['prompt']
        self.assertIn('Clothing continuity',prompt)
        self.assertIn('actual playable',prompt)

    def test_generated_requires_save_and_is_idempotent(self):
        folder=self.root/'job';folder.mkdir();(folder/'image.png').write_bytes(self.raw)
        job={'id':'STORY-TEST','topic':'Model','generated_images':['image.png']}
        self.cast.save_generated(folder,job);self.cast.save_generated(folder,job)
        self.assertEqual(len(self.cast.state()),1);ident=self.cast.state()[0]['id']
        with self.assertRaises(ValueError):self.cast.reference(ident)
        self.cast.approve(ident);self.assertTrue(self.cast.reference(ident).is_file())

    def test_immutable_product_cast_snapshot_and_story_prompt(self):
        row=self.cast.add('Model',self.data)
        product_folder=self.root/'products'/'JOB-X';product_folder.mkdir(parents=True)
        source=product_folder/'product.png';source.write_bytes(self.raw)
        product={'id':'JOB-X','product_name':'Bag','source_images':['product.png'],'description':'blue bag','posting_product_url':'https://example.invalid/item'}
        products=SimpleNamespace(root=product_folder.parent)
        context=self.cast.snapshot(products,product,row['id'])
        self.assertEqual(clean_settings({'creative_context':context})['creative_context'],context)
        source.write_bytes(b'changed');self.cast.edit(row['id'],hidden=True)
        stories=StoryManager(self.root);job=stories.create('Bag',video_generation_mode='google_flow')
        attach_context(stories,products,self.cast,job,context);stories._save(job)
        stories._write_request(stories.root/job['id'],job)
        self.assertEqual(job['product_story']['reference_roles'],['product','person'])
        self.assertEqual((stories.root/job['id']/job['source_images'][0]).read_bytes(),self.raw)
        prompt=(stories.root/job['id']/'prompts/chatgpt_request.txt').read_text(encoding='utf8')
        self.assertIn('PRODUCT STORY SHORTS',prompt);self.assertIn('คนถือหรือใช้สินค้าได้',prompt)
        self.assertEqual(job['source_url'],product['posting_product_url'])
        package=stories.plugin_request(job['id'])
        self.assertEqual(len(package['request']['image_files']),2)

    def test_legacy_story_prompt_unchanged(self):
        self.assertEqual(story_brief({}),'')
        self.assertIn('single reusable',story_brief({'cast_creation':True,'id':'TEST'}))

    def test_cast_only_one_image_no_flow_gate(self):
        stories=StoryManager(self.root);job=stories.create('Model',cast_creation=True,video_generation_mode='image_motion')
        attach_context(stories,None,self.cast,job,{'kind':'cast'})
        stories._save(job);stories._write_request(stories.root/job['id'],job)
        self.assertEqual(job['scene_count'],1);self.assertEqual(job['scene_pipeline_version'],0)
        self.assertTrue(job['cast_creation'])

    def test_missing_product_images_rejected(self):
        with self.assertRaises(ValueError):self.cast.snapshot(SimpleNamespace(root=self.root),{'id':'JOB-X'})

    def test_new_product_three_scenes_old_story_keeps_ten(self):
        stories=StoryManager(self.root)
        old=stories.create('Old',scene_count=10,video_generation_mode='google_flow')
        new=stories.create('Product',scene_count=10,product_short=True,video_generation_mode='google_flow')
        self.assertEqual(new['scene_count'],10)
        self.assertEqual(stories.get(old['id'])['scene_count'],10)
        self.assertEqual(stories.plugin_request(new['id'])['job']['scene_count'],10)

    def test_product_queue_three_scenes_and_edit(self):
        from core.creation_queue import CreationQueue
        queue=CreationQueue(self.root)
        result=queue.enqueue('story',['Bag'],settings={'creative_context':{'kind':'product_story','product_short':True}},scene_count=10,video_generation_mode='google_flow')
        item=result['items'][0];self.assertEqual(item['scene_count'],10)
        queue.edit(item['queue_id'],'Bag',scene_count=3)
        queue.edit(item['queue_id'],'Bag',scene_count=10)
        with self.assertRaises(ValueError):queue.edit(item['queue_id'],'Bag',scene_count=16)

    def test_progress_uses_scene_ledger_not_old_83_percent(self):
        from core.scene_progress_view import scene_progress_view
        from core.atomic_json import AtomicJsonFile
        job={'id':'S','scene_count':3,'scene_pipeline_version':1,'product_story':{'name':'Bag'}}
        store=AtomicJsonFile(self.root/'prompts'/'scene_pipeline.json')
        store.write({'scenes':{'1':{'phase':'complete'},'2':{'phase':'voice'}}})
        result=scene_progress_view(job,self.root,True,83)
        self.assertEqual(result['scene_index'],2);self.assertEqual(result['scene_phase'],'voice')
        self.assertEqual(result['scenes_complete'],1);self.assertLess(result['percent'],83)
        self.assertEqual(result['content_kind'],'product')
        self.assertNotIn('percent',scene_progress_view(job,self.root,False,83))

    def test_progress_preserves_errors_and_final(self):
        from core.scene_progress_view import scene_progress_view
        from core.atomic_json import AtomicJsonFile
        job={'id':'S','scene_count':3,'scene_pipeline_version':1}
        store=AtomicJsonFile(self.root/'prompts'/'scene_pipeline.json')
        store.write({'scenes':{'1':{'phase':'error'}}})
        self.assertNotIn('message',scene_progress_view(job,self.root,True,83))
        store.write({'scenes':{str(i):{'phase':'complete'} for i in range(1,4)}})
        result=scene_progress_view(job,self.root,True,99)
        self.assertEqual(result['percent'],99);self.assertNotIn('message',result)
