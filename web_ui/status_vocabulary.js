/* One user-facing status vocabulary for every page.
   Presentation only: it never changes job, queue or provider state. */
(() => {
  'use strict';
  // The six states a customer sees. `tone` is read by foundation.css.
  const STATES = {
    queued: {label: 'รอคิว', tone: 'queued'},
    running: {label: 'กำลังสร้าง', tone: 'running'},
    waiting: {label: 'รอคุณ', tone: 'waiting'},
    failed: {label: 'สะดุด', tone: 'failed'},
    paused: {label: 'หยุดไว้', tone: 'paused'},
    done: {label: 'เสร็จแล้ว', tone: 'done'},
  };
  // Shown only on a page that really offers a resume button for that job.
  const RESUMABLE_FAILED = 'สะดุด · ทำต่อได้';

  // Backend codes that map straight onto one of the six states.
  const CODES = {
    queued: 'queued', pending: 'queued', waiting: 'queued',
    running: 'running', active: 'running', processing: 'running',
    action_required: 'waiting', user_action_required: 'waiting', needs_attention: 'waiting',
    review: 'waiting', image_review: 'waiting',
    error: 'failed', failed: 'failed', interrupted: 'failed',
    paused: 'paused', stopped: 'paused',
    completed: 'done', complete: 'done', success: 'done', succeeded: 'done',
  };
  // Codes whose meaning is narrower than a state, so they keep their own label.
  const SPECIFIC = {
    ready: {label: 'พร้อม', tone: 'done'},
    posted: {label: 'โพสต์แล้ว', tone: 'done'},
    request_ready: {label: 'พร้อมส่ง AI', tone: 'queued'},
    cancelled: {label: 'ยกเลิกแล้ว', tone: 'paused'},
    canceled: {label: 'ยกเลิกแล้ว', tone: 'paused'},
    login_required: {label: 'รอคุณ · ต้องเข้าสู่ระบบ', tone: 'waiting'},
    credit_exhausted: {label: 'รอคุณ · เครดิตหมด', tone: 'waiting'},
    missing: {label: 'ยังไม่มี', tone: 'none'},
    deleted: {label: 'ลบแล้ว', tone: 'none'},
    video_deleted: {label: 'ลบวิดีโอแล้ว', tone: 'none'},
  };
  // Why a queue paused by itself. Keys come from ui/creation_queue.py and ui/update_guard.py.
  const PAUSE_REASONS = {
    startup_review: 'กู้คิวจากครั้งก่อนแล้ว กด “เริ่มคิว” เพื่อทำต่อจากไฟล์เดิม',
    awaiting_user_start: 'รอคุณกด “เริ่มคิว”',
    job_needs_attention: 'คิวพักไว้ เพราะมีงานรอคุณ แก้ที่งานนั้นแล้วกดทำต่อ',
    ai_cover_needs_attention: 'คิวพักไว้ เพราะปก AI ของงานหนึ่งต้องตรวจ',
    preflight: 'คิวพักไว้ เพราะตรวจความพร้อมไม่ผ่าน ดูข้อความที่งานแรกในคิว',
    start_failed: 'คิวพักไว้ เพราะเริ่มงานถัดไปไม่สำเร็จ',
    dispatch_error: 'คิวพักไว้ เพราะส่งงานถัดไปไม่สำเร็จ',
    extension_update: 'คิวพักไว้ เพราะต้องอัปเดตส่วนเสริม Chrome ก่อน',
    app_update: 'คิวพักไว้ เพราะกำลังอัปเดตโปรแกรม',
    user: 'คุณพักคิวไว้ กด “เริ่มคิว” เมื่อพร้อมทำต่อ',
    user_cancel: 'คุณยกเลิกงานปัจจุบัน คิวพักไว้ กด “เริ่มคิว” เพื่อทำงานถัดไป',
    user_cancel_all: 'คุณยกเลิกคิวทั้งหมดไว้',
    missing_final: 'คิวพักไว้ เพราะไม่พบไฟล์วิดีโอที่ทำเสร็จของงานล่าสุด',
    state_cleared: 'ล้างสถานะค้างแล้ว กด “เริ่มคิว” เมื่อพร้อม',
  };

  const key = code => String(code ?? '').trim().toLowerCase();

  function resolve(code, {resumable = false} = {}) {
    const k = key(code);
    if (SPECIFIC[k]) return {state: k, ...SPECIFIC[k]};
    const state = CODES[k];
    if (!state) return {state: '', label: String(code ?? '').trim() || '—', tone: 'none'};
    const info = STATES[state];
    return {state, label: state === 'failed' && resumable ? RESUMABLE_FAILED : info.label, tone: info.tone};
  }

  function pauseReason(reason) {
    const k = String(reason ?? '').trim();
    if (!k) return '';
    if (PAUSE_REASONS[k]) return PAUSE_REASONS[k];
    if (k.startsWith('drama_failure')) return 'คิวพักไว้ เพราะละครสั้นตอนหนึ่งสะดุด เปิดโปรเจกต์ละครเพื่อทำต่อ';
    return '';
  }

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));

  // `extraClass` keeps page-specific hooks such as `status-pill` or `cq-status running`.
  function pill(code, {label, extraClass = '', resumable = false} = {}) {
    const info = resolve(code, {resumable});
    return `<span class="sf-status ${esc(extraClass)}" data-tone="${esc(info.tone)}">${esc(label || info.label)}</span>`;
  }

  window.SmartFlowStatus = Object.freeze({
    STATES, RESUMABLE_FAILED, resolve, pauseReason, pill,
    label: (code, options) => resolve(code, options).label,
    tone: code => resolve(code).tone,
  });
})();
