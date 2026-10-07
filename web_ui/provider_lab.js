(() => {
  'use strict';
  const nav = document.getElementById('ai-chat-nav');
  const host = document.getElementById('ai-chat-host');
  const status = document.getElementById('ai-chat-status');
  if (!nav || !host || !status) return;
  const prompt = document.getElementById('ai-chat-test-prompt');
  const probeButton = document.getElementById('ai-chat-test-probe');
  const sendButton = document.getElementById('ai-chat-test-send');
  const testStatus = document.getElementById('ai-chat-test-status');
  const answer = document.getElementById('ai-chat-test-answer');
  let api, enabled = false, pending = false, lastBounds = '';

  async function testProgress() {
    if (!enabled || document.body.dataset.page !== 'ai-chat') return;
    try {
      const row = await api.provider_lab_test_status();
      const phase = row.phase || '';
      const labels = {prepared:'เตรียมข้อความ',dispatching:'ตรวจว่าหน้าเว็บรับคำขอแล้วหรือไม่',
        accepted:'ChatGPT รับคำขอแล้ว กำลังรอคำตอบ',completed:'รับคำตอบแล้ว',
        reviewed_completed:'ผู้ใช้ตรวจยืนยันคำตอบเดิมแล้ว',
        needs_review:'ยังยืนยันผลไม่ได้ • ตรวจคำขอเดิมในแชต ไม่ส่งซ้ำ',
        failed_before_send:'ยังไม่ได้ส่ง • ตรวจช่องข้อความในแชต'};
      if (row.error) testStatus.textContent = row.error;
      else if (phase) {
        const evidence = phase === 'needs_review' && row.observed_url_kind ?
          ` • หน้า ${row.observed_url_kind} • พบคำขอ ${row.observed_user_matches ? 'ตรง' : 'ยังไม่ตรง'} • ข้อความ ${row.observed_user_count || 0}` : '';
        testStatus.textContent = `${row.request_id || ''} • ${labels[phase] || phase}${evidence}`;
      }
      sendButton.disabled = row.running || ['prepared','dispatching','accepted','needs_review'].includes(phase);
      if (phase === 'completed' && row.answer) {
        answer.textContent = row.answer;
        answer.hidden = false;
      }
    } catch (_) { testStatus.textContent = 'อ่านสถานะคำขอทดสอบไม่ได้'; }
  }

  async function sync() {
    if (!enabled || !api || pending) return;
    const active = document.body.dataset.page === 'ai-chat';
    if (!active) {
      lastBounds = '';
      await api.provider_lab_hide();
      return;
    }
    const rect = host.getBoundingClientRect();
    const bounds = {left:rect.left, top:rect.top, width:rect.width, height:rect.height,
      viewport_width:innerWidth, viewport_height:innerHeight};
    const key = JSON.stringify(bounds);
    if (key === lastBounds) return;
    pending = true;
    try {
      const result = await api.provider_lab_show(bounds);
      if (result.ok) {
        lastBounds = key;
        status.textContent = '';
      } else status.textContent = result.error ? (window.smartflowSafeError?.(result.error)||'เปิด AI Chat ไม่สำเร็จ') : 'เปิด AI Chat ไม่สำเร็จ';
    } catch (_) { status.textContent = 'เปิด AI Chat ไม่สำเร็จ'; }
    finally {
      pending = false;
      if (document.body.dataset.page !== 'ai-chat') void api.provider_lab_hide();
    }
  }

  async function initialize() {
    api = window.pywebview?.api;
    if (!api?.provider_lab_available || !api?.provider_lab_show || !api?.provider_lab_hide) return;
    try { enabled = !!await api.provider_lab_available(); } catch (_) { return; }
    if (!enabled) return;
    nav.classList.remove('hidden');
    probeButton.addEventListener('click', async () => {
      probeButton.disabled = true;
      try {
        const result = await api.provider_lab_probe();
        testStatus.textContent = result.ready ? 'หน้า ChatGPT พร้อมรับคำขอทดสอบ' :
          (result.reason || 'หน้า ChatGPT ยังไม่พร้อม');
      } catch (_) { testStatus.textContent = 'ตรวจหน้า ChatGPT ไม่สำเร็จ'; }
      finally { probeButton.disabled = false; }
    });
    sendButton.addEventListener('click', async () => {
      if (sendButton.disabled) return;
      sendButton.disabled = true;
      try {
        const result = await api.provider_lab_start_test(prompt.value);
        testStatus.textContent = result.error ? (window.smartflowSafeError?.(result.error)||'เริ่มคำขอไม่สำเร็จ') : result.message || 'เริ่มคำขอไม่สำเร็จ';
      } catch (_) { testStatus.textContent = 'เริ่มคำขอไม่สำเร็จ'; }
      finally { void testProgress(); }
    });
    setInterval(() => { void testProgress(); }, 2000);
    const observer = new MutationObserver(() => { void sync(); });
    observer.observe(document.body, {attributes:true, attributeFilter:['data-page']});
    window.addEventListener('resize', () => { void sync(); });
    window.addEventListener('scroll', () => { void sync(); }, {passive:true});
    new ResizeObserver(() => { void sync(); }).observe(host);
    if (location.hash === '#ai-chat' && typeof showPage === 'function') showPage('ai-chat');
    void sync();
    void testProgress();
  }

  if (window.pywebview?.api) initialize();
  else window.addEventListener('pywebviewready', initialize, {once: true});
})();
