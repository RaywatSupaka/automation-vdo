"""Durable UI observations only. No device actions, retries, or percent estimates."""
import time
import uuid

PHASE_STEP = {'queued':'queued', 'checking':'checking', 'transferring':'transfer',
              'prepared':'prepare_post', 'editing':'select_video', 'settings':'settings',
              'ready':'preflight', 'send_pending':'sending', 'processing':'verify',
              'published':'done', 'skipped':'skipped', 'review':'review', 'unknown':'unknown', 'draft':'pending'}
STEPS = {'queued','checking','transfer','restart_app','baseline','account','prepare_post','select_video','caption','product',
         'settings','preflight','sending','verify','done','skipped','review','unknown','pending'}
ACTIVE = {'running', 'pausing'}


def selection_ids(value):
    # Queue membership bounds the operation, not the old arbitrary 30-row limit.
    if (not isinstance(value, list) or not value or
            any(not isinstance(i, str) or not i for i in value) or len(set(value)) != len(value)):
        raise ValueError('ติ๊กเลือกงานในคิวอย่างน้อยหนึ่งคลิป โดยไม่มีรายการซ้ำ')
    return value


def start_run(state, ids, account, phone):
    now = time.time()
    run = dict(id=uuid.uuid4().hex, status='running', ids=list(ids), account=account,
               phone=phone, started_at=now, updated_at=now, finished_at=None,
               current_id=None, rows={}, events=[], sequence=0, message='กำลังเริ่มคิวที่ยืนยัน')
    state['posting_run'] = run
    for row in state['items']:
        if row['id'] in ids:
            row['posting_run_id'] = run['id']
            run['rows'][row['id']] = dict(id=row['id'], item_id=row['item_id'], title=row['title'],
                                         phase='queued', step='queued', message='รอเริ่ม', updated_at=now)
    return run['id']


def observe(state, row, step=None):
    run = state.get('posting_run') or {}
    if run.get('status') not in ACTIVE or row.get('posting_run_id') != run.get('id') or row['id'] not in run.get('rows', {}):
        return
    step = step or PHASE_STEP.get(row['phase'], 'review')
    if step not in STEPS:
        raise ValueError('ไม่รู้จักขั้นตอนติดตามโพสต์')
    now = time.time()
    previous = run['rows'][row['id']]
    result = dict(id=row['id'], item_id=row['item_id'], title=row['title'], phase=row['phase'],
                  step=step, message=row.get('message', ''), updated_at=now,
                  waiting_for_device=bool(row.get('waiting_for_device')),
                  send_started=bool(row.get('publish_intent')))
    if step in {'review','unknown'}:
        result['last_step'] = previous.get('last_step') or previous.get('step')
    run['rows'][row['id']] = result
    if row['phase'] not in {'draft', 'queued'}:
        run['current_id'] = row['id']
        run['message'] = result['message']
    run['updated_at'] = now
    if any(previous.get(k) != result[k] for k in ('phase','step','message','waiting_for_device','send_started')):
        run['sequence'] += 1
        run['events'].append(dict(result, sequence=run['sequence'], at=now))
        run['events'] = run['events'][-80:]


def finish_run(state, run_id, message='', paused=False, interrupted=False):
    run = state.get('posting_run') or {}
    if run.get('id') != run_id or run.get('status') not in ACTIVE:
        return
    phases = [r['phase'] for r in run['rows'].values()]
    if interrupted:
        status = 'interrupted'
    elif any(p in {'review','unknown'} for p in phases):
        status = 'review'
    elif phases and all(p in {'published','skipped'} for p in phases):
        status = 'complete'
    else:
        status = 'paused' if paused else 'review'
    run.update(status=status, message=message or ('โพสต์ครบแล้ว' if status=='complete' else 'พักคิวแล้ว กรุณาตรวจสถานะก่อนทำต่อ'),
               finished_at=time.time(), updated_at=time.time())


def snapshot(run):
    if not run:
        return None
    rows = list(run['rows'].values())
    done = sum(r['phase']=='published' for r in rows)
    skipped = sum(r['phase']=='skipped' for r in rows)
    review = sum(r['phase'] in {'review','unknown'} for r in rows)
    current = run['rows'].get(run.get('current_id'))
    return dict(run, total=len(run['ids']), completed=done, skipped_count=skipped, review_count=review,
                uncertain_count=sum(r['phase'] in {'unknown','send_pending','processing'} or (bool(r.get('send_started')) and r['phase']!='published') for r in rows),
                remaining=len(run['ids'])-done-skipped-review,
                current=current, current_index=run['ids'].index(current['id'])+1 if current else 0)
