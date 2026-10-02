(() => {
  'use strict';
  const nav = document.getElementById('ai-chat-nav');
  const host = document.getElementById('ai-chat-host');
  const status = document.getElementById('ai-chat-status');
  if (!nav || !host || !status) return;
  let api, enabled = false, pending = false, lastBounds = '';

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
      } else status.textContent = result.error || 'เปิด AI Chat ไม่สำเร็จ';
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
    const observer = new MutationObserver(() => { void sync(); });
    observer.observe(document.body, {attributes:true, attributeFilter:['data-page']});
    window.addEventListener('resize', () => { void sync(); });
    window.addEventListener('scroll', () => { void sync(); }, {passive:true});
    new ResizeObserver(() => { void sync(); }).observe(host);
    if (location.hash === '#ai-chat' && typeof showPage === 'function') showPage('ai-chat');
    void sync();
  }

  if (window.pywebview?.api) initialize();
  else window.addEventListener('pywebviewready', initialize, {once: true});
})();
