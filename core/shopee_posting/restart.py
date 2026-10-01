"""Reset preparation state only; never erase a Send or publication receipt."""
import copy
import time

UNSENT_PHASES = {'draft','queued','checking','transferring','prepared','editing','settings','ready','review'}
PREPARATION_FIELDS = {'posting_run_id','run_contract','latest_baseline','observed_options',
                      'device_observation','waiting_for_device','preflight_version','dispatch_state',
                      'upload_notice_absent','attached_product_title','evidence_folder','cover_mode',
                      'account','message','last_step','step'}


def restartable(row):
    return (row.get('phase') in UNSENT_PHASES and not row.get('publish_intent')
            and row.get('dispatch_state') != 'press_committed'
            and not row.get('published_at') and not row.get('receipt'))


def reset_preparation(state, ids):
    """Caller holds the idle-worker lock and performs one atomic store change."""
    rows = {row['id']: row for row in state['items']}
    if not ids or any(row_id not in rows or not restartable(rows[row_id]) for row_id in ids):
        raise ValueError('ล้างได้เฉพาะคลิปที่ยังไม่เริ่มส่ง • เก็บผลโพสต์เดิมไว้')
    old = state.get('posting_run')
    # Keep the old evidence recoverable, but outside the current UI counters.
    state.setdefault('restart_history', []).append(dict(
        reset_at=time.time(), posting_run=copy.deepcopy(old),
        rows={row_id:{key:copy.deepcopy(value) for key,value in rows[row_id].items()
                      if key in PREPARATION_FIELDS or key == 'phase'} for row_id in ids}))
    for row_id in ids:
        row = rows[row_id]
        for key in PREPARATION_FIELDS:
            row.pop(key, None)
        row.update(phase='draft', revision=row['revision']+1, updated_at=time.time(),
                   message='พร้อมเริ่มใหม่ • ยังไม่ได้โพสต์', waiting_for_device=False)
    state.pop('posting_run', None)
    # Transfer metadata/media/hash are reusable only through the usual fresh
    # file/phone validation; do not delete files or treat them as posted.
