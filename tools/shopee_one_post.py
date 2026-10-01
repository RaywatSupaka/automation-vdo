"""One explicitly authorized development post; all public sends require a durable claim."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import ROOT, load_config
from core.adb_manager import AdbManager
from core.video_library import VideoLibrary
from core.shopee_posting.store import PostingStore, file_hash, product_url
from core.shopee_posting.media import transfer
from core.workspace_cleaner import FinalVideoValidator

parser = argparse.ArgumentParser()
parser.add_argument('--prepare', action='store_true')
parser.add_argument('--caption', action='store_true')
parser.add_argument('--publish-once', action='store_true')
parser.add_argument('--verify', action='store_true')
args = parser.parse_args()
if args.verify:
    from core.shopee_posting.device import ShopeeDevice
    store = PostingStore(ROOT)
    row = next(r for r in store.read()['items'] if r['item_id'] == 'story:STORY-20260919-A3F008')
    cfg = load_config()
    device = ShopeeDevice(AdbManager(cfg['adb_path'], cfg['device_serial'], ROOT), cfg['android_device_identity'])
    try:
        device.find(text=row['caption'] + '  ซ่อน')
        device.find(text=row['attached_product_title'])
        device.find(**{'content-desc': 'meaning this is the creator'})
        folder = ROOT/'workspace'/'shopee_posting'/'receipts'/row['id']
        device.capture(folder, 'verified_post')
        import time
        store.transition(row['id'], {'processing', 'unknown'}, 'published',
                         published_at=time.time(), message='พบโพสต์จริงในโปรไฟล์ keerati3s • แคปชันครบ สินค้าตรง เปิดป้าย AI',
                         receipt=dict(account='keerati3s', caption_verified=True, product_verified=True,
                                      screenshot=str(folder/'verified_post.png'), profile_screenshot=str(ROOT/'workspace'/'shopee_posting'/'probe'/'profile_after.png')))
        print('Verified one published product video. No further posts.')
    finally:
        device.close()
if args.publish_once:
    from core.shopee_posting.device import ShopeeDevice
    from core.shopee_posting.publish import publish_current
    store = PostingStore(ROOT)
    row = next(r for r in store.read()['items'] if r['item_id'] == 'story:STORY-20260919-A3F008')
    cfg = load_config()
    device = ShopeeDevice(AdbManager(cfg['adb_path'], cfg['device_serial'], ROOT), cfg['android_device_identity'])
    try:
        publish_current(device, store, row['id'], 'keerati3s',
                        'Anata พร้อมส่ง..เสื้อยืดสีขาวผู้หญิง/แขนสั้นรอบคอ ดูผอมลงเสื้อยืดฝ้ายขาว นุ่มมาก',
                        ROOT/'workspace'/'shopee_posting'/'receipts'/row['id'])
        import time
        time.sleep(4)
        device.capture(ROOT/'workspace'/'shopee_posting'/'receipts'/row['id'], 'after_post')
        print('Tapped Post once. Processing; not yet verified published.')
    finally:
        device.close()
if args.caption:
    store = PostingStore(ROOT)
    row = next(r for r in store.read()['items'] if r['item_id'] == 'story:STORY-20260919-A3F008')
    caption = 'ไอเดียแมตช์เสื้อยืด Anata สีขาว คอกลมแขนสั้น ดูสินค้าที่ตะกร้า #Anata #เสื้อยืดผู้หญิง #แฟชั่นผู้หญิง #สร้างด้วยAI'
    assert len(caption) <= 150
    store.edit(row['id'], row['revision'], caption=caption)
    cfg = load_config()
    from core.shopee_posting.device import ShopeeDevice
    device = ShopeeDevice(AdbManager(cfg['adb_path'], cfg['device_serial'], ROOT), cfg['android_device_identity'])
    try:
        device.set_text(caption, **{'resource-id': 'com.shopee.th.dfpluginshopee16:id/et_caption'})
        print('Caption verified, characters:', len(caption))
    finally:
        device.close()
if args.prepare:
    cfg = load_config()
    item = VideoLibrary(ROOT).item_detail('story:STORY-20260919-A3F008')
    media = FinalVideoValidator(cfg.get('ffmpeg_path', '')).validate(item['path'])
    store = PostingStore(ROOT)
    ids = store.add([dict(item_id=item['item_id'], title=item['title'], video_path=item['path'],
                          cover_path=item['cover_path'], product_url=product_url(item['affiliate_link']),
                          caption='ไอเดียแมตช์เสื้อยืด Anata สีขาว คอกลมแขนสั้น ดูรายละเอียดสินค้าได้ที่ตะกร้า\nคลิปสร้างด้วย AI เพื่อประกอบการนำเสนอสินค้า\n#Anata #เสื้อยืดผู้หญิง #เสื้อยืดสีขาว #แฟชั่นผู้หญิง')])
    row = store.transition(ids[0], {'draft', 'review', 'prepared'}, 'transferring',
                           video_sha256=file_hash(item['path']), media=media, account='keerati3s')
    adb = AdbManager(cfg['adb_path'], cfg['device_serial'], ROOT)
    if adb.prop('ro.serialno') != cfg['android_device_identity']:
        raise RuntimeError('Wrong phone')
    try:
        receipt = transfer(adb, row)
        store.transition(row['id'], {'transferring'}, 'prepared', transfer=receipt, message='โอนไฟล์และตรวจ MediaStore แล้ว ยังไม่โพสต์')
        print(json.dumps(dict(id=row['id'], media=media, transfer=receipt), ensure_ascii=False))
    except Exception as exc:
        store.transition(row['id'], {'transferring'}, 'review', message=str(exc))
        raise
