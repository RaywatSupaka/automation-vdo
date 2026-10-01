"""Transfer one explicit Final into its own album, verify bytes and MediaStore."""
import re
import shlex
import time
from pathlib import Path

from core.shopee_posting.store import file_hash
from core.shopee_posting.device import ReviewRequired


def transfer(adb, row, stop=None):
    if not re.fullmatch('[a-f0-9]{32}', row['id']):
        raise ValueError('รหัสงานโอนไฟล์ไม่ถูกต้อง')
    # Shared readable stem; keep an existing transferred album immutable on resume.
    title = re.sub(r'[^\w\u0E00-\u0E7F-]+', '_', str(row.get('title') or 'Product'), flags=re.UNICODE).strip('_')[:28]
    album = (row.get('transfer') or {}).get('album') or 'SF_' + title + '_' + row['id'][:8]
    if not re.fullmatch(r'[\w\u0E00-\u0E7F-]{1,80}', album):
        raise ValueError('ชื่ออัลบั้มไม่ถูกต้อง')
    base = '/sdcard/Movies/' + album
    result = adb.shell('mkdir', '-p', shlex.quote(base))
    if result.returncode:
        raise ReviewRequired('สร้างอัลบั้มบนมือถือไม่ได้')
    # New posts transfer video only. Preserve proof of a previously transferred
    # cover for legacy album recognition, without touching or re-uploading it.
    outputs = {}
    old_cover = ((row.get('transfer') or {}).get('files') or {}).get('cover')
    if old_cover and str(old_cover.get('path', '')).startswith(base + '/'):
        outputs['cover'] = dict(old_cover)
    for kind, field in [('video', 'video_path')]:
        local = row.get(field)
        if not local:
            continue
        local = Path(local)
        if not local.is_file():
            raise ReviewRequired('ไม่พบไฟล์ ' + kind)
        if stop and stop.is_set():
            raise ReviewRequired('พักก่อนโอนไฟล์ถัดไป')
        digest = file_hash(local)
        if kind == 'video' and row.get('video_sha256') != digest:
            raise ReviewRequired('ไฟล์ Final เปลี่ยนหลังตรวจ')
        existing = ((row.get('transfer') or {}).get('files') or {}).get(kind) or {}
        remote = existing.get('path') or base + '/' + album + '_' + kind + local.suffix.lower()
        if not remote.startswith(base+'/') or '..' in remote:
            raise ValueError('ปลายทางไฟล์ไม่ตรงกับอัลบั้มงาน')
        checked = adb.shell('sha256sum', shlex.quote(remote))
        if checked.returncode or not checked.stdout.startswith(digest+' '):
            pushed = adb.run('push', str(local), remote, serial=True, timeout=180)
            if pushed.returncode:
                raise ReviewRequired('โอนไฟล์ไม่สำเร็จ ยังไม่เลือกหรือส่งโพสต์')
        checked = adb.shell('sha256sum', shlex.quote(remote))
        if checked.returncode or not checked.stdout.startswith(digest + ' '):
            raise ReviewRequired('ไฟล์บนมือถือไม่ตรงกับต้นฉบับ')
        scanned = adb.shell('am', 'broadcast', '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE', '-d', shlex.quote('file://' + remote))
        if scanned.returncode:
            raise ReviewRequired('มือถือยังไม่ได้ลงทะเบียนไฟล์ในคลังภาพ')
        # Android MediaStore reports /storage/emulated/0, not the /sdcard alias.
        canonical = remote.replace('/sdcard/', '/storage/emulated/0/', 1)
        uri = 'content://media/external/' + ('video' if kind == 'video' else 'images') + '/media'
        deadline = time.monotonic() + 25
        evidence = ''
        while time.monotonic() < deadline:
            query = adb.shell('content', 'query', '--uri', uri, '--projection', '_id:_display_name:_size:_data',
                              '--where', shlex.quote("_data='" + canonical + "'"))
            if query.returncode == 0 and canonical in query.stdout and ('_size=' + str(local.stat().st_size)) in query.stdout:
                evidence = query.stdout.strip(); break
            if stop and stop.wait(.5):
                break
            if stop is None:
                time.sleep(.5)
        if not evidence:
            raise ReviewRequired('โอนไฟล์แล้ว แต่คลังภาพยังไม่ยืนยันไฟล์ หยุดก่อนเลือกผิดคลิป')
        outputs[kind] = dict(path=remote, sha256=digest, bytes=local.stat().st_size, media_store=evidence)
    return dict(album=album, files=outputs)
