"""Read-only recovery proof for 270's completed-image/Stop failure. Never permits Send."""
import json
import re
from pathlib import Path


def story_image_result_review(message):
    """Explain receipt inspection without declaring an empty UI a failed Send."""
    text = str(message or '')
    if 'STORY_IMAGE_RECEIPT_REVIEW' not in text:
        return None
    match = re.search(r'CHATGPT_IMAGE_RESULT_([A-Z_]+)', text)
    reason = match.group(1).lower() if match else 'unconfirmed'
    descriptions = {
        'send_unconfirmed': 'คลิกส่งแล้ว แต่ยังยืนยันข้อความของฉากนี้ในแชตไม่ได้ ไม่ใช่สถานะกำลังรอภาพ ตรวจคำสั่งเดิมก่อนส่งเพิ่ม',
        'send_not_started': 'ตรวจพบปัญหาก่อนเริ่มคลิกส่ง กดทำต่อเพื่อเตรียมคำสั่งฉากเดิมใหม่ โดยไม่เปลี่ยนภาพที่บันทึกแล้ว',
        'no_image': 'พบพรอมต์ของฉากนี้ แต่คำตอบเดิมยังไม่มีภาพให้ดึงเข้าโปรแกรม ไม่ใช่หลักฐานว่าส่งไม่สำเร็จ',
        'waiting_response': 'พบพรอมต์เดิม แต่คำตอบของฉากนี้ยังไม่ปรากฏบนหน้าเว็บ',
        'image_loading': 'พบภาพของฉากนี้แล้ว แต่ไฟล์ยังโหลดไม่ครบ',
        'multiple_images': 'พบภาพต่างกันหลายภาพในคำตอบเดียว จึงยังเลือกภาพแทนผู้ใช้ไม่ได้',
        'request_missing': 'ยังไม่พบพรอมต์ของฉากนี้บนหน้าที่เปิดอยู่ ตรวจว่าเป็นแชตเดิมและโหลดประวัติครบ',
        'request_ambiguous': 'พบพรอมต์เหมือนกันหลายครั้ง ต้องตรวจว่าคำตอบใดเป็นของฉากนี้',
        'wrong_conversation': 'หน้าที่เปิดอยู่ยังไม่ใช่หน้าบทสนทนา ChatGPT ที่ตรวจคำขอได้ เมื่อเป็นแชตอื่น ระบบตรวจพรอมต์เต็มของฉากนี้ก่อนดึงภาพ',
        'request_not_latest': 'พบพรอมต์ของฉากนี้ในแชตอื่น แต่มีคำขอใหม่ต่อท้ายแล้ว จึงยังไม่เลือกภาพข้ามคำขอ',
        'conversation_pending': 'เว็บยังไม่กำหนดลิงก์บทสนทนาใหม่ให้คำขอเดิม รอตรวจแชตเดิมโดยไม่ส่งซ้ำ',
        'generating': 'เว็บยังแสดงว่ากำลังสร้างภาพ รอผลเดิมก่อนกดทำต่อ',
        'image_ready': 'ภาพเปลี่ยนระหว่างตรวจ จึงยังไม่บันทึกไฟล์ที่ไม่แน่นอน',
        'unconfirmed': 'มีคำขอภาพเดิมที่ยังยืนยันผลไม่ได้ ต้องตรวจคำตอบของฉากนั้น ไม่ใช่เริ่มเรื่องใหม่',
    }
    if reason not in descriptions:
        reason = 'unconfirmed'
    return {'reason': reason, 'message': descriptions[reason] +
            ' • ภาพฉากที่บันทึกแล้วคงเดิม กดทำต่อเพื่อรีเฟรชตรวจผล หากหน้าเว็บพร้อมและไม่มีผลจริง ระบบจะเริ่มฉากนี้ใหม่อัตโนมัติ'}


def completed_image_result_proofs(folder, job_id, provider):
    if provider != 'chatgpt':
        return {}
    try:
        path = Path(folder) / 'logs' / 'extension_trace.jsonl'
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        if any(type(row.get('sequence')) is not int for row in rows):
            return {}
        if any(a['sequence'] >= b['sequence'] for a, b in zip(rows, rows[1:])):
            return {}
        candidate, accepted, proofs = None, False, {}
        for row in rows:
            if row.get('job_id') != job_id or row.get('service') != provider:
                candidate = None
                continue
            if row.get('action') == 'image_prompt_ready':
                candidate, accepted = row, False
                proofs.pop(str((row.get('detail') or {}).get('scene_index')), None)
            if not candidate:
                continue
            if any(row.get(k) != candidate.get(k) for k in ('run_id', 'client_id', 'tab_id')):
                candidate = None
                continue
            if row.get('action') == 'ai_send_accepted':
                accepted = True
            detail = candidate.get('detail') or {}
            index = detail.get('scene_index')
            expected = f'พบภาพที่ {index} สมบูรณ์แล้ว แต่สถานะสร้างยังหมุนค้าง • กำลังเก็บภาพเดิมโดยไม่ส่ง Prompt ซ้ำ'
            if accepted and row.get('action') == 'recovering_stalled_image' and row.get('message') == expected:
                url = candidate.get('page_url', '')
                prompt = detail.get('composer_text') or detail.get('prompt')
                if (candidate.get('version') != '0.15.270' or type(index) is not int or not 1 <= index <= 50
                        or not isinstance(prompt, str) or not prompt or len(prompt) > 30000
                        or detail.get('composer_matches') is not True
                        or not re.fullmatch(r'https://chatgpt\.com/c/[^/?#]+', url)):
                    continue
                proofs[str(index)] = {'job_id': job_id, 'scene_index': index, 'run_id': row['run_id'],
                    'client_id': row['client_id'], 'conversation_url': url, 'prompt': prompt}
        return proofs
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}
