"""Read saved scene phases for display only; never mutate running jobs/receipts."""
from core.atomic_json import AtomicJsonFile


def scene_progress_view(job,folder,active,legacy_percent):
    result={'content_kind':'product' if job.get('product_story') else 'story'}
    if not active or job.get('scene_pipeline_version')!=1:
        return result
    count=int(job.get('scene_count') or 0)
    if count<1:return result
    data=AtomicJsonFile(folder/'prompts'/'scene_pipeline.json').read({'scenes':{}})
    rows=data.get('scenes') or {}
    done=sum(rows.get(str(i),{}).get('phase')=='complete' for i in range(1,count+1))
    result.update(scene_total=count,scenes_complete=done)
    # Final rendering/cover and explicit failures retain their own status messages.
    if job.get('status') in {'failed','error','cancelled','waiting_review'}:
        return result
    if done==count:
        result.update(stage='finishing',percent=max(90,int(legacy_percent)))
        if legacy_percent<90:result.update(message='ทุกฉากพร้อมแล้ว • กำลังเตรียม Final',detail=f'ภาพ วิดีโอ และเสียงครบ {count}/{count} ฉาก')
        return result
    index=next(i for i in range(1,count+1) if rows.get(str(i),{}).get('phase')!='complete')
    row=rows.get(str(index),{});phase=row.get('phase','image')
    replacement=AtomicJsonFile(folder/'prompts'/'flow_replacement.json').read({'scenes':{}}).get('scenes',{}).get(str(index),{})
    if phase=='video' and replacement.get('phase') in {'requested','image_saved'}:
        events=AtomicJsonFile(folder/'prompts'/'flow_recovery.json').read({'scenes':{}}).get('scenes',{}).get(str(index),[])
        recovery=events[-1] if events else {}
        if replacement.get('request_id') and recovery.get('request_id')==replacement['request_id'] and recovery.get('phase') in {'needs_review','cancelled'}:
            label='หยุดซ่อมฉากแล้ว' if recovery['phase']=='cancelled' else 'คำตอบซ่อมฉากยังต้องตรวจสอบ'
            result.update(stage='scene',scene_index=index,scene_phase='repair_review',percent=10+int(80*done/count),
                          message=f'ฉาก {index}/{count} • {label}',
                          detail=str(recovery.get('pause_reason') or recovery.get('error') or label)[:700])
            return result
        label='กำลังรับภาพทดแทนจาก AI Web' if replacement['phase']=='requested' else 'บันทึกภาพทดแทนแล้ว • กำลังขอพรอมต์วิดีโอ'
        if replacement['phase']=='requested':
            label={'checking_empty':'ตรวจคำตอบภาพว่าง • กำลังกู้แชตเดิม',
                   'empty_after_refresh':'รีเฟรชแล้ว • รอภาพจากคำตอบเดิม ไม่ส่งซ้ำ'}.get(replacement.get('image_wait_state'),label)
        result.update(stage='scene',scene_index=index,scene_phase='repair',percent=10+int(80*done/count),
                      message=f'ฉาก {index}/{count} • {label}',detail='กำลังซ่อมฉากก่อนกลับไป Google Flow • ไม่ใช่กำลังสร้างวิดีโอ')
        return result
    if phase in {'error','cancelled'}:return result
    if not rows:return result
    label={'image':'กำลังเตรียมภาพ','requested':'กำลังเตรียมวิดีโอ','video':'กำลังสร้างวิดีโอ','voice':'กำลังทำเสียงและประกอบฉาก'}.get(phase,'กำลังทำฉาก')
    if phase=='video' and str(row.get('message') or '').startswith(('กำลังเตรียม Google Flow', 'ส่งสร้างวิดีโอแล้ว')):
        label=row['message']
    fraction={'image':0,'requested':.25,'video':.35,'voice':.7}.get(phase,0)
    result.update(stage='scene',scene_index=index,scene_phase=phase,
                  percent=min(89,10+int(80*(done+fraction)/count)),
                  message=f'ฉาก {index}/{count} • {label}',
                  detail=f'ภาพ → วิดีโอ → เสียง • เสร็จครบแล้ว {done}/{count} ฉาก')
    return result
