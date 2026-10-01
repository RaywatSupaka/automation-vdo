(() => {
  'use strict';
  let api, result, state, checking = false, lastCheck = 0;
  const checkInterval = 15 * 60 * 1000;
  const newer = (candidate, current) => {
    const pattern = /^(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$/;
    const values = value => { const m = pattern.exec(String(value || '')); return m && [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : 0, +(m[4] || 0)]; };
    const next = values(candidate), prior = values(current);
    if (!next || !prior) return false;
    for (let i = 0; i < next.length; i++) { if (next[i] !== prior[i]) return next[i] > prior[i]; }
    return false;
  };
  const button = document.createElement('button');
  button.className = 'button ghost'; button.textContent = 'เวอร์ชัน / อัปเดต';
  button.style.cssText = 'position:fixed;bottom:10px;right:18px;z-index:90;font-size:12px';
  const dialog = document.createElement('dialog'); dialog.className = 'modal';
  dialog.innerHTML = '<div class="modal-card" style="max-width:650px"><h2>เวอร์ชันและการอัปเดต</h2><p data-version></p><p data-extension></p><p data-notes style="white-space:pre-wrap"></p><p data-status role="status"></p><div class="modal-actions" style="flex-wrap:wrap"><button class="button" data-check>ตรวจสอบอีกครั้ง</button><button class="button" data-download="extension">ดาวน์โหลด Extension ใหม่</button><button class="button" data-download="patch">ดาวน์โหลดแพตช์โปรแกรม</button><button class="button primary" data-install hidden>ติดตั้งและเปิดใหม่</button><button class="button ghost" data-close>ไว้ภายหลัง</button></div><details style="margin-top:18px"><summary>วิธีเปลี่ยน Extension</summary><p>รอให้งานจบก่อน แตกไฟล์ ZIP ใหม่ แล้วอัปเดตไฟล์ในโฟลเดอร์ Extension เดิม เปิด chrome://extensions และกด Reload ของ SmartFlow AI ไม่ต้องถอนติดตั้ง จากนั้นกลับมากดตรวจสอบอีกครั้ง</p><p>ดาวน์โหลดแล้วไม่เท่ากับติดตั้งสำเร็จ โปรแกรมตรวจจากรุ่นที่ Extension เชื่อมต่อกลับมาจริง</p></details></div>';
  const el = selector => dialog.querySelector(selector);
  const bundled = document.createElement('button');
  bundled.className = 'button'; bundled.textContent = 'เปิดไฟล์ Extension ที่มากับโปรแกรม';
  dialog.querySelector('.modal-actions').prepend(bundled);
  bundled.onclick = async () => { const reply = await api.update_bundled_extension(); el('[data-status]').textContent = reply.message || reply.error; };
  const busy = () => Boolean(state?.product_progress?.active || state?.story_progress?.active || state?.presenter_progress?.active || state?.creation_queue?.stuck_state_blocked_reason);
  async function check(show = true) {
    if (checking || !api) return;
    checking = true;
    lastCheck = Date.now();
    if (show && !dialog.open) dialog.showModal();
    el('[data-status]').textContent = 'กำลังตรวจสอบ…';
    try {
      [result, state] = await Promise.all([api.update_check(), fetch('/api/desktop/state?mode=compact').then(r => r.json())]);
      if (!result.ok) {
        el('[data-install]').hidden = true;
        el('[data-version]').textContent = `โปรแกรม ${result.local?.version || 'ชุดพัฒนา'}`;
        el('[data-extension]').textContent = `Extension ที่ต้องใช้: ${result.local?.extension_version || 'ดูสถานะระบบ'} • ที่เชื่อมต่อ: ${state?.system?.extension_version || 'ยังไม่พบ'}`;
        el('[data-download="patch"]').hidden = true;
        el('[data-download="extension"]').hidden = true;
        el('[data-status]').textContent = result.error; return;
      }
      el('[data-version]').textContent = `โปรแกรม ${result.local.version} • รุ่นเผยแพร่ ${result.release.version}`;
      const actual = state?.system?.extension_online ? state.system.extension_version : '';
      const target = result.release.extension_version;
      const extensionUpdate = newer(target, actual || result.local.extension_version);
      el('[data-extension]').textContent = `Extension ที่เชื่อมต่อ: ${actual || 'ยังไม่พบ'} • รุ่นที่เผยแพร่: ${target}` + (actual === target ? ' ✓ ตรงรุ่น' : ' • รอเปลี่ยน / Reload แล้วตรวจสอบอีกครั้ง');
      el('[data-notes]').textContent = result.release.notes || '';
      el('[data-status]').textContent = busy() ? 'มีงานกำลังทำอยู่ ดาวน์โหลดไว้ก่อนได้ แต่ให้เปลี่ยนหลังจบงาน' : 'ตรวจสอบเสร็จแล้ว';
      el('[data-download="patch"]').hidden = !result.app_update || !result.release.patch;
      el('[data-download="extension"]').hidden = !result.release.extension;
      const releaseId = result.release.version + '/' + target;
      if (result.app_update || extensionUpdate) {
        button.textContent = 'มีอัปเดต • โปรแกรม / Extension';
        if (!show && !busy() && !sessionStorage.getItem('update-dismiss-' + releaseId)) dialog.showModal();
      } else button.textContent = 'เวอร์ชัน / อัปเดต';
    } catch (error) { el('[data-status]').textContent = String(error); }
    finally { checking = false; }
  }
  button.onclick = () => check(true);
  window.addEventListener('smartflow-open-updates', () => check(true));
  el('[data-check]').onclick = () => check(true);
  el('[data-close]').onclick = () => {
    if (result?.ok) sessionStorage.setItem('update-dismiss-' + result.release.version + '/' + result.release.extension_version, '1');
    dialog.close();
  };
  dialog.querySelectorAll('[data-download]').forEach(b => b.onclick = async () => {
    b.disabled = true;
    const timer = setInterval(async () => { const p = await api.update_progress(); if (p.busy) el('[data-status]').textContent = `ดาวน์โหลด ${p.percent || 0}%`; }, 800);
    try {
      const reply = await api.update_download(b.dataset.download);
      el('[data-status]').textContent = reply.message || reply.error;
      if (reply.ok && b.dataset.download === 'patch') el('[data-install]').hidden = false;
    } finally { clearInterval(timer); b.disabled = false; }
  });
  el('[data-install]').onclick = async () => {
    if (!confirm('ติดตั้งอัปเดตและเปิดโปรแกรมใหม่? ระบบจะตรวจว่าไม่มีงานกำลังทำก่อน')) return;
    const install = el('[data-install]');
    if (install.disabled) return;
    install.disabled = true;
    try {
      const reply = await api.update_install(); el('[data-status]').textContent = reply.message || reply.error;
      if (!reply.ok) install.disabled = false;
    } catch (error) {
      el('[data-status]').textContent = String(error);
      install.disabled = false;
    }
  };
  window.addEventListener('pywebviewready', () => {
    api = window.pywebview.api;
    document.body.append(button, dialog);
    setTimeout(() => check(false), 7000);
    // Poll metadata only; never install or reload while an automation is active.
    setInterval(() => { if (!document.hidden) void check(false); }, checkInterval);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && Date.now() - lastCheck >= checkInterval) void check(false);
    });
  });
})();
