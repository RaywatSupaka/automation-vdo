"""Route an explicit Product resume without inheriting a new-clip form."""
def product_continue_action(job):
    ident=str(job.get('id') or '')
    if job.get('story_source_only') or job.get('status') in {'deleted','video_deleted'}:
        raise ValueError('งานนี้ถูกลบหรือเป็นข้อมูลสินค้าต้นทาง ไม่ใช่คลิปที่ทำต่อได้')
    if job.get('video_status')=='deleted':
        raise ValueError('วิดีโองานนี้ถูกลบแล้ว')
    if (job.get('readiness') or {}).get('ready') or (job.get('status')=='ready' and job.get('video_status')=='ready'):
        raise ValueError('คลิปนี้เสร็จแล้ว เปิดดูได้ในคลังวิดีโอ')
    if ident.startswith('STORY-') and job.get('product_story') and not job.get('series_id'):
        return 'retry_story', {'job_id':ident}
    if ident.startswith('JOB-'):
        return 'create_product', {'job_id':ident}
    raise ValueError('เลือกได้เฉพาะงานคลิปสินค้า Shopee')
