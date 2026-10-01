"""Dismiss unfinished Shorts without deleting media or touching provider receipts."""


def stopped_short(job):
    """Only ordinary user Stop is resumable; deliberate dismiss stays hidden."""
    return (str(job.get('status') or '').lower() in {'cancelled', 'canceled'}
            and job.get('pipeline_stage') == 'user_cancel'
            and job.get('cancel_reason') == 'ผู้ใช้ยกเลิกการทำงาน')


def pending_short(job):
    status = str(job.get('status') or '').lower()
    video = str(job.get('video_status') or '').lower()
    finished = {'ready', 'complete', 'completed', 'success', 'succeeded'}
    return (str(job.get('job_type') or 'story_short') == 'story_short'
            and not any(job.get(key) for key in
                        ('product_story', 'cast_creation', 'series_id', 'long_video', 'story_source_only'))
            and (status not in {'cancelled', 'canceled', 'deleted', 'video_deleted'} or stopped_short(job))
            and video not in {'deleted', 'video_deleted'}
            and not (status in finished and video in finished))


def clear_story_recovery(app, payload):
    if payload.get('confirmed') is not True:
        raise ValueError('กรุณายืนยันการล้างงานที่ต้องดำเนินการต่อทั้งหมด')
    queue = app.story_queue
    with queue._lock, queue._store.locked():
        reason = app._creation_idle_reason()
        if reason:
            raise ValueError(reason)
        jobs = [job for job in app.stories.list_jobs() if pending_short(job)]
        ids = [job['id'] for job in jobs]
        if ids and app.bridge.pending_job_commands(ids):
            raise ValueError('ยังมีคำสั่งรอ Extension ยืนยัน • รอหรือยกเลิกงานก่อน')
        from ui.creation_queue import REMOTE_TERMINAL_STEPS
        for client in app.bridge.extension_status().get('clients', []):
            for scope in ('ai', 'flow'):
                if client.get(f'{scope}_job_id') in ids and str(client.get(f'{scope}_step') or '') not in REMOTE_TERMINAL_STEPS:
                    raise ValueError('Extension ยังทำงานนี้อยู่ • รอหรือยกเลิกงานก่อนล้าง')
        cleared = []
        # One durable queue write includes queued/failed rows and duplicate
        # references; ordinary result callbacks intentionally only update running rows.
        queue.dismiss_story_jobs(ids)
        for ident in ids:
            # Cancel queue first: an interrupted clear must never dispatch this
            # job. Existing checkpoints remain intact and the operation is retryable.
            app.stories.mark_cancelled(ident, reason='ผู้ใช้ล้างรายการทำต่อทั้งหมดจากหน้าเล่าเรื่อง Shorts')
            cleared.append(ident)
    return {'ok': True, 'cleared': len(cleared)}
