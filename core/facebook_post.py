"""Explicit library-to-Page publishing. Never retry an ambiguous POST."""
import hashlib
import re
import threading
import time
from pathlib import Path
import requests
from core.atomic_json import AtomicJsonFile
from core.facebook_planner import FacebookPlanner, validate_time
from core.facebook_upload import VideoMultipart
from datetime import datetime


class FacebookPost:
    VERSION = 'v25.0'

    def __init__(self, root, library, credentials, session=None):
        self.library, self.credentials = library, credentials
        self.store = AtomicJsonFile(Path(root)/'workspace'/'facebook_posts.json')
        self.http = session or requests.Session()  # No POST retry adapter.
        self.lock = threading.RLock()
        self.workers = {}
        self.planner = FacebookPlanner(self)
        self.planner.recover()

    def _request(self, method, path, token, **kwargs):
        try:
            headers = kwargs.pop('headers', {})
            response = self.http.request(method, f'https://graph.facebook.com/{self.VERSION}/{path}',
                headers={**headers, 'Authorization':'Bearer '+token}, timeout=(15,900 if method=='POST' else 30),
                allow_redirects=False, **kwargs)
            data = response.json()
        except Exception:
            raise ValueError('ติดต่อ Facebook ไม่สำเร็จ ตรวจการเชื่อมต่อและสถานะเดิมก่อนส่งใหม่') from None
        if not response.ok or not isinstance(data,dict) or data.get('error'):
            error = data.get('error') if isinstance(data,dict) else None
            code = error.get('code') if isinstance(error,dict) else None
            raise ValueError(f'Facebook ไม่ยืนยันคำขอ (รหัส {code if isinstance(code,int) else response.status_code}) ตรวจสิทธิ์เพจและ Token')
        return data

    def connect(self, token):
        token = str(token or '').strip()
        if not token or len(token)>1280:
            raise ValueError('กรุณาใส่ Page Access Token ที่ถูกต้อง')
        with self.lock:
            if any(w.is_alive() for w in self.workers.values()) or self.state()['planner']['batch'].get('active'):
                raise ValueError('รออัปโหลดปัจจุบันก่อนเปลี่ยนเพจ')
            page = self._request('GET','me',token,params={'fields':'id,name,category'})
            if not str(page.get('id','')).isdigit() or not page.get('category'):
                raise ValueError('ต้องใช้ Token ของเพจ ไม่ใช่บัญชีบุคคล')
            self.credentials.save(token)
            with self.store.locked():
                data=self.store.read_unlocked({'posts':{}})
                data['page']={'id':str(page['id']),'name':str(page.get('name') or page['id'])}
                self.store.write_unlocked(data)
        return self.state()

    def disconnect(self):
        with self.lock:
            if any(w.is_alive() for w in self.workers.values()) or self.state()['planner']['batch'].get('active'):
                raise ValueError('รออัปโหลดปัจจุบันก่อนตัดการเชื่อมต่อ')
            self.credentials.delete()
            with self.store.locked():
                data=self.store.read_unlocked({'posts':{}});data.pop('page',None);self.store.write_unlocked(data)
        return self.state()

    def state(self):
        data=self.store.read({'posts':{}})
        return {'ok':True,'page':data.get('page'), 'posts':list(data.get('posts',{}).values())[::-1],
                'planner': self.planner.view(data)}

    def _update(self,key,**patch):
        with self.store.locked():
            data=self.store.read_unlocked({'posts':{}});data['posts'][key].update(patch)
            self.store.write_unlocked(data)

    def publish(self,item_id,caption,page_id):
        if getattr(self, 'membership', None):
            self.membership.require()
        caption=str(caption or '').strip()
        if len(caption)>5000:raise ValueError('ข้อความยาวเกิน 5,000 ตัวอักษร')
        with self.lock:
            if self.state()['planner']['batch'].get('active'):
                raise ValueError('รอหรือพักชุดโพสต์ปัจจุบันก่อน')
            page=self.state().get('page')
            if not page or page['id']!=str(page_id):raise ValueError('เพจเปลี่ยนแล้ว กรุณาตรวจเพจอีกครั้ง')
            token=self.credentials.load()
            if not token:raise ValueError('กรุณาบันทึก Token ของเพจก่อน')
            item=self.library.item_detail(str(item_id))
            path=Path(item['path'])
            if not path.is_file() or path.stat().st_size<1024:raise ValueError('ไม่พบไฟล์ Final ที่พร้อมโพสต์')
            digest=self._hash(path)
            # Caption edits are NOT permission to duplicate the same video on this Page.
            key=self.post_key(page['id'],str(item_id),digest)
            with self.store.locked():
                data=self.store.read_unlocked({'posts':{}})
                if key in data['posts']:return {'ok':True,'post':data['posts'][key],'duplicate':True}
                row={'id':key,'item_id':str(item_id),'page_id':page['id'],'page_name':page['name'],
                     'title':item['title'],'caption':caption,'sha256':digest,'status':'uploading','created_at':time.time()}
                data['posts'][key]=row;self.store.write_unlocked(data)
            worker=threading.Thread(target=self._upload,args=(key,path,token,caption,item['title']),daemon=True)
            self.workers[key]=worker;worker.start()
            return {'ok':True,'post':row}

    @staticmethod
    def post_key(page_id, item_id, digest):
        return hashlib.sha256((page_id+'|'+item_id+'|'+digest).encode()).hexdigest()

    @staticmethod
    def _hash(path):
        with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

    def _upload(self,key,path,token,caption,title):
        try:
            if getattr(self, 'membership', None):
                self.membership.require()
            row=self.store.read()['posts'][key]
            if self._hash(path)!=row['sha256']:raise ValueError('ไฟล์คลิปเปลี่ยนหลังเลือก ยังไม่ส่ง')
            fields={'description':caption,'title':str(title)[:250],'published':'true'}
            if row.get('send_mode') == 'schedule':
                validate_time(row['scheduled_at'])
                fields.update(published='false', scheduled_publish_time=str(row['scheduled_at']), unpublished_content_type='SCHEDULED')
            with path.open('rb') as stream:
                body=VideoMultipart(stream, fields)
                data=self._request('POST',row['page_id']+'/videos',token, data=body,
                                   headers={'Content-Type':body.content_type})
            video_id=str(data.get('id') or '')
            if not video_id.isdigit():raise ValueError('Facebook ยังไม่ส่งรหัสวิดีโอกลับมา')
            self._update(key,status='processing',video_id=video_id)
            self.check(key)
        except Exception as error:
            # A request may have reached Facebook. Do not repeat it automatically.
            self._update(key,status='review',message=str(error) if isinstance(error,ValueError) else 'ต้องตรวจผลเดิมก่อน ไม่ส่งซ้ำ')

    def check(self,key):
        row=self.store.read({'posts':{}})['posts'].get(str(key))
        if not row:raise ValueError('ไม่พบรายการโพสต์')
        if not row.get('video_id'):return {'ok':True,'post':row}
        page=self.state().get('page') or {}
        if page.get('id')!=row['page_id']:raise ValueError('เชื่อมต่อ Token ของเพจเดิมก่อนตรวจผล')
        token=self.credentials.load()
        if not token:raise ValueError('เชื่อมต่อ Token ของเพจเดิมก่อนตรวจผล')
        result=self._request('GET',row['video_id'],token,params={'fields':'status,published,permalink_url,scheduled_publish_time'})
        ready=(result.get('status') or {}).get('video_status')=='ready'
        published=result.get('published') is True
        url=str(result.get('permalink_url') or '')
        if url.startswith('/'):url='https://www.facebook.com'+url
        if not re.match(r'^https://(?:www\.)?facebook\.com/',url):url=''
        status='published' if ready and published else 'processing'
        message='เผยแพร่แล้ว' if status=='published' else 'Facebook กำลังประมวลผล / ยังไม่ยืนยันเผยแพร่'
        remote = self._remote_time(result.get('scheduled_publish_time'))
        if row.get('send_mode') == 'schedule' and ready:
            if published and row['scheduled_at'] > time.time() + 60:
                status, message = 'review', 'Facebook เผยแพร่ก่อนเวลาที่ขอ โปรดตรวจโพสต์จริง • ไม่ส่งซ้ำ'
            elif not published and result.get('published') is False and remote == row['scheduled_at'] and remote > time.time():
                status, message = 'scheduled', 'Facebook ยืนยันตั้งเวลาแล้ว • ปิดโปรแกรมได้สำหรับรายการนี้'
            elif not published:
                status, message = 'review', 'รับวิดีโอแล้ว แต่ยังยืนยันเวลาใน Facebook ไม่ตรงกับแผน • ตรวจผลเดิม ไม่อัปโหลดซ้ำ'
        if (result.get('status') or {}).get('video_status') == 'error':
            status, message = 'review', 'Facebook ประมวลผลวิดีโอไม่สำเร็จ • ตรวจรายการเดิมในเพจ'
        self._update(key,status=status,url=url,remote_scheduled_at=remote,checked_at=time.time(),message=message)
        return {'ok':True,'post':self.store.read()['posts'][key]}

    @staticmethod
    def _remote_time(value):
        try:
            if isinstance(value, bool) or value is None:return None
            if str(value).isdigit():return int(value)
            dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
            return int(dt.timestamp()) if dt.tzinfo else None
        except (ValueError,OverflowError,TypeError):return None

    def action(self,action,payload):
        if action.startswith('facebook_planner_'):return self.planner.action(action,payload)
        if action=='facebook_status':return self.state()
        if action=='facebook_connect':return self.connect(payload.get('token'))
        if action=='facebook_disconnect':return self.disconnect()
        if action=='facebook_check':return self.check(payload.get('id'))
        if action=='facebook_publish':return self.publish(payload.get('item_id'),payload.get('caption'),payload.get('page_id'))
        raise ValueError('คำสั่ง Facebook ไม่ถูกต้อง')
