"""Read-only browser observations, never a substitute for desktop completion ACK."""
import time

PHASES = {
    'attachment_selecting': ('preparing', 'กำลังรอรูปเดิมพร้อมเลือกใน Google Flow'),
    'preparing': ('preparing', 'กำลังเตรียมคำขอ'),
    'image_prompt_ready': ('preparing', 'เตรียมพรอมต์แล้ว'),
    'submission_sent': ('sent_unconfirmed', 'ส่งแล้ว กำลังตรวจการรับคำขอ'),
    'submission_unconfirmed': ('sent_unconfirmed', 'กำลังตรวจคำขอเดิม ยังไม่ส่งซ้ำ'),
    'waiting_for_analysis': ('waiting', 'กำลังตรวจคำตอบเดิม'),
    'waiting_for_image': ('waiting', 'กำลังตรวจภาพของคำขอเดิม'),
    'generating_images': ('generating', 'กำลังสร้างภาพ'),
    'generation_in_progress': ('generating', 'กำลังประมวลผลวิดีโอ'),
    'analysis_ready': ('verifying', 'พบคำตอบ กำลังตรวจข้อมูล'),
    'image_result_verified': ('transferring', 'ตรวจภาพผ่าน กำลังบันทึกเข้าโปรแกรม'),
    'generation_complete': ('result_detected', 'พบวิดีโอบนเว็บ รอตรวจและบันทึก'),
    'submitting': ('transferring', 'กำลังส่งผลเข้าโปรแกรม'),
    'analysis_saved': ('desktop_saved', 'โปรแกรมยืนยันบันทึกบทแล้ว'),
    'image_checkpoint_saved': ('desktop_saved', 'โปรแกรมยืนยันบันทึกภาพแล้ว'),
    'flow_prompt_saved': ('desktop_saved', 'บันทึกพรอมต์วิดีโอแล้ว'),
    'recovering_images': ('recovering', 'กำลังกู้ผลเดิม'),
    'recovering_result': ('recovering', 'กำลังรีเฟรชเพื่อตรวจผลเดิม'),
    'image_refresh_check': ('recovering', 'กำลังตรวจผลหลังรีเฟรช'),
    'image_restart_pending': ('recovering', 'ยังไม่มีผล กำลังเตรียมเริ่มฉากนี้ใหม่'),
    'image_restart_started': ('recovering', 'กำลังเริ่มฉากนี้ใหม่ โดยเก็บฉากที่สำเร็จแล้ว'),
    'recovering_response': ('recovering', 'กำลังตรวจจุดบันทึกก่อนรีเฟรชคำตอบเดิม'),
    'waiting_for_previous_response': ('waiting', 'รอเว็บจบคำตอบเดิมก่อนส่งขั้นต่อไป'),
    'downloading_image': ('transferring', 'พบภาพแล้ว กำลังดาวน์โหลดไฟล์เดิม'),
    'preparing_flow_prompt': ('preparing', 'กำลังเตรียมหรือตรวจพรอมต์วิดีโอ'),
    'waiting_scene_assets': ('waiting_desktop', 'รอโปรแกรมทำวิดีโอและเสียงของฉาก'),
    'complete': ('step_complete', 'ขั้นตอน AI เสร็จแล้ว ยังไม่ใช่ Final'),
    'user_action_required': ('waiting_user', 'รอผู้ใช้ดำเนินการ'),
    'error': ('needs_attention', 'มีรายละเอียดที่ต้องตรวจสอบ'),
    'generation_failed': ('failed', 'เว็บแจ้งสร้างไม่สำเร็จ'),
    'cancelled': ('cancelled', 'ยกเลิกแล้ว'),
}


def attach_observation(client, progress, body, prefix, now=None):
    """Called after ownership checks, under bridge lock. Reject reordered reports."""
    value = body.get('observed_at_ms')
    if value is None:  # old receipt/legacy test events keep the existing protocol
        return True
    if type(value) not in (int, float) or not 0 < value < 1e16:
        return False
    previous = client.get(prefix + '_observation') or {}
    identity = (progress.get(prefix + '_job_id'), progress.get(prefix + '_run_id'), progress.get(prefix + '_tab_id'))
    if list(identity) == previous.get('identity'):
        prior_stamp = previous.get('observed_at_ms', 0)
        if value < prior_stamp or (value == prior_stamp and previous.get('acknowledged', True)):
            return False
    step = progress.get(prefix + '_step', '')
    phase, label = PHASES.get(step, ('checking', 'กำลังตรวจขั้นตอนปัจจุบัน'))
    if body.get('response_active') is True:
        phase, label = 'generating', 'เว็บยังแสดงกำลังประมวลผล'
    progress[prefix + '_observation'] = {
        'identity': list(identity), 'observed_at_ms': value, 'acknowledged': False,
        'received_at': time.time() if now is None else now,
        'phase': phase, 'label': label, 'step': step,
        'scene_index': body.get('scene_index', body.get('shot_index', 0)),
        'result_reason': str(body.get('result_reason') or '')[:100],
        'desktop_saved': phase == 'desktop_saved',
    }
    return True


def public_observations(extension):
    result=[]
    for client in extension.get('clients', []):
        for prefix in ('ai', 'flow'):
            row=client.get(prefix+'_observation')
            if row:
                result.append({**row, 'job_id': client.get(prefix+'_job_id'),
                    'provider': client.get('ai_provider', 'AI Web') if prefix=='ai' else 'Google Flow'})
        for row in (client.get('aux_observations') or {}).values():
            result.append(dict(row))
    return sorted(result, key=lambda x:x['received_at'], reverse=True)[:12]
