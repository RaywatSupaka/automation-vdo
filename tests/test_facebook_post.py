import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from core.facebook_post import FacebookPost


class FacebookPostTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.file=self.root/'final.mp4';self.file.write_bytes(b'x'*2048)
        self.creds=Mock();self.creds.load.return_value='FAKE-TEST-ONLY'
        self.library=Mock();self.library.item_detail.return_value={'path':str(self.file),'title':'Test'}
        self.session=Mock()
        self.fb=FacebookPost(self.root,self.library,self.creds,self.session)
        self.reply({'id':'123','name':'Test Page','category':'Test'})
        self.fb.connect('FAKE-TEST-ONLY')

    def reply(self,value):
        self.session.request.return_value=SimpleNamespace(ok=True,status_code=200,json=lambda:value)

    def test_token_not_in_saved_history(self):
        self.assertNotIn('FAKE-TEST-ONLY',self.fb.store.path.read_text())
        self.creds.save.assert_called_once_with('FAKE-TEST-ONLY')

    def test_same_clip_new_caption_does_not_post_twice(self):
        with patch('core.facebook_post.threading.Thread') as thread:
            a=self.fb.publish('story:A','one','123');b=self.fb.publish('story:A','two','123')
            self.assertEqual(a['post']['id'],b['post']['id']);self.assertTrue(b['duplicate'])
            self.assertEqual(thread.call_count,1)

    def test_wrong_page_never_uploads(self):
        with self.assertRaises(ValueError):self.fb.publish('story:A','','456')
        self.library.item_detail.assert_not_called()

    def test_unknown_post_never_retries_or_leaks_error(self):
        with patch('core.facebook_post.threading.Thread'):
            key=self.fb.publish('story:A','','123')['post']['id']
        self.session.request.side_effect=RuntimeError('FAKE-TEST-ONLY')
        self.fb._upload(key,self.file,'FAKE-TEST-ONLY','','Title')
        row=self.fb.state()['posts'][0];self.assertEqual(row['status'],'review')
        self.assertNotIn('FAKE-TEST-ONLY',str(row))
        self.assertEqual(self.session.request.call_count,2) # connect plus one POST

    def test_restart_requires_review_not_new_upload(self):
        with patch('core.facebook_post.threading.Thread'):
            self.fb.publish('story:A','','123')
        resumed=FacebookPost(self.root,self.library,self.creds,self.session)
        self.assertEqual(resumed.state()['posts'][0]['status'],'review')
        self.assertTrue(resumed.publish('story:A','','123')['duplicate'])

    def test_ready_is_not_published_until_confirmed(self):
        with patch('core.facebook_post.threading.Thread'):
            key=self.fb.publish('story:A','','123')['post']['id']
        self.fb._update(key,video_id='999')
        self.reply({'status':{'video_status':'ready'},'published':False})
        self.assertEqual(self.fb.check(key)['post']['status'],'processing')
        self.reply({'status':{'video_status':'ready'},'published':True,'permalink_url':'/reel/999'})
        result=self.fb.check(key)['post'];self.assertEqual(result['status'],'published')
        self.assertEqual(result['url'],'https://www.facebook.com/reel/999')

    def test_person_token_is_rejected(self):
        self.reply({'id':'777','name':'Person'})
        with self.assertRaises(ValueError):self.fb.connect('NOT-A-PAGE')

    def test_video_changed_before_send_is_not_uploaded(self):
        with patch('core.facebook_post.threading.Thread'):
            key=self.fb.publish('story:A','','123')['post']['id']
        self.file.write_bytes(b'z'*2048)
        self.fb._upload(key,self.file,'FAKE-TEST-ONLY','','Title')
        self.assertEqual(self.session.request.call_count,1)
        self.assertEqual(self.fb.state()['posts'][0]['status'],'review')
