/* No credentials in local/session storage, URLs, notices or analytics. */
(() => {
  const panel = document.getElementById('membership-gate');
  const shell = document.querySelector('.app-shell');
  const form = panel.querySelector('form');
  const input = panel.querySelector('input');
  const submit = panel.querySelector('[type=submit]');
  const message = panel.querySelector('[data-member-message]');
  const account = document.getElementById('membership-account');
  let busy = false, polling = false, current = null, revision = 0;
  function render(state) {
    const wasAllowed = current?.required === true && current.desktop?.allowed === true;
    current = state;
    const allowed = state?.required === true && state.desktop?.allowed === true;
    panel.hidden = allowed;
    shell.inert = !allowed;
    document.body.classList.toggle('membership-locked', !allowed);
    form.hidden = !state || Boolean(state.desktop?.restoring);
    if (!busy) message.textContent = state?.desktop?.message || 'กำลังเชื่อมต่อโปรแกรม เพื่อตรวจสิทธิ์ของคุณ…';
    account.textContent = state?.dev_mode ? '◉ DEV MODE' : allowed ? '◉ บัญชี SmartFlow' : '◉ เข้าสู่ระบบ';
    account.title = state?.dev_mode ? 'โหมดพัฒนา • ไม่ตรวจ API Token' : allowed && state.desktop.expires_at
      ? `ใช้งานได้ถึง ${new Date(state.desktop.expires_at * 1000).toLocaleString('th-TH')}` : 'เข้าสู่ระบบด้วย Token ที่แอดมินออกให้';
    if (allowed && !wasAllowed) window.dispatchEvent(new Event('smartflow-membership-ready'));
  }
  async function status() {
    if (polling || busy) return;
    polling = true;
    const ownRevision = revision;
    try {
      const response = await fetch('/api/membership/status', {cache:'no-store', signal:AbortSignal.timeout(12000)});
      const value = await response.json();
      if (!response.ok || value.required !== true) throw Error();
      if (ownRevision === revision && !busy) render(value);
    } catch { if (ownRevision === revision && !busy) render(null); }
    finally { polling = false; }
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const token = input.value.trim();
    if (!token) { input.focus(); return; }
    revision++;
    busy = true; submit.disabled = true; input.value = ''; input.disabled = true;
    panel.setAttribute('aria-busy', 'true'); message.textContent = 'กำลังตรวจ Token กับเซิร์ฟเวอร์…';
    try {
      const response = await fetch('/api/membership/desktop/login', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token}),
        signal:AbortSignal.timeout(20000)
      });
      const value = await response.json();
      if (response.ok && value.ok) render(value);
      else message.textContent = value.error || 'เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่';
    } catch { message.textContent = 'ยังติดต่อโปรแกรมไม่ได้ กรุณารอสักครู่แล้วลองใหม่'; }
    finally { busy = false; input.disabled = false; submit.disabled = false; panel.removeAttribute('aria-busy'); }
  });
  panel.querySelector('[data-member-recheck]').onclick = status;
  panel.querySelector('[data-member-update]').onclick = () => window.dispatchEvent(new Event('smartflow-open-updates'));
  account.onclick = async () => {
    if (!current?.desktop?.allowed) { await status(); return; }
    if (current.dev_mode) return;
    const expires = new Date(current.desktop.expires_at * 1000).toLocaleString('th-TH');
    if (!window.confirm(`สิทธิ์ใช้งานถึง ${expires}\n\nต้องการออกจากระบบหรือไม่? งานที่ส่งแล้วจะเก็บผลไว้ งานใหม่จะรอเข้าสู่ระบบ`)) return;
    revision++;
    try {
      await fetch('/api/membership/desktop/logout', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    } finally { await status(); }
  };
  render(null); status();
  const timer = setInterval(status, 3000);
  window.addEventListener('pagehide', () => clearInterval(timer), {once:true});
})();
