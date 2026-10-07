/* ADB only. This panel never uploads, opens Shopee, or publishes a post. */
(() => {
  'use strict';
  const panel = document.querySelector('#android-wifi');
  if (!panel) return;
  const q = selector => panel.querySelector(selector);
  let sending = false, state = {}, lastScan = 0;
  const visible = () => !document.hidden && panel.closest('[data-view]').classList.contains('active');
  function message(text) { q('#android-wifi-message').textContent = text; }
  function rowButton(label, action, value) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'button ghost compact'; button.textContent = label;
    button.dataset.wifiAction = action; button.dataset.value = value;
    return button;
  }
  function render(next) {
    if (!next) return;
    state = next;
    const busy = sending || state.busy;
    const fresh = state.checked_at && Date.now()/1000 - state.checked_at < 35;
    const connected = state.phase === 'connected' && fresh && !busy;
    q('#android-wifi-badge').textContent = busy ? 'กำลังดำเนินการ' : connected ? 'เชื่อมต่อแล้ว' : state.phase === 'paired' ? 'จับคู่แล้ว • รอเชื่อมต่อ' : 'รอตรวจ / เชื่อมต่อ';
    q('#android-wifi-badge').classList.toggle('connected', Boolean(connected));
    panel.setAttribute('aria-busy', String(Boolean(busy)));
    message(state.error ? (window.smartflowSafeError?.(state.error)||'ตรวจมือถือไม่สำเร็จ') : state.message || 'กดตรวจมือถือเพื่อเริ่มต้น');
    const legacyStatus = document.querySelector('#queue-device');
    if (legacyStatus) legacyStatus.textContent = state.error ? (window.smartflowSafeError?.(state.error)||'ตรวจมือถือไม่สำเร็จ') : state.message || 'กดตรวจมือถือเพื่อเริ่มต้น';
    const selected = state.selected;
    q('#android-wifi-selected').textContent = selected ? `${selected.model} • Android ${selected.android} • ${selected.serial} • ${selected.shopee_installed ? 'พบ Shopee' : 'ยังตรวจไม่พบ Shopee'}` : 'ยังไม่มีมือถือที่ยืนยันพร้อมใช้งาน';
    q('#android-wifi-time').textContent = state.checked_at ? `ตรวจล่าสุด ${new Date(state.checked_at*1000).toLocaleTimeString('th-TH')}${fresh ? '' : ' • กดตรวจใหม่'}` : '';
    q('#android-wifi-warning').textContent = state.discovery_warning || '';
    const discovery = q('#android-wifi-discovery'); discovery.replaceChildren();
    for (const item of state.services || []) {
      discovery.append(rowButton(`${item.kind === 'pairing' ? 'ใช้พอร์ตจับคู่' : 'ใช้พอร์ตเชื่อมต่อ'} ${item.endpoint}`, item.kind, item.endpoint));
    }
    const devices = q('#android-wifi-devices'); devices.replaceChildren();
    for (const item of state.devices || []) {
      const row = document.createElement('div'); row.className = 'android-device-row';
      const label = document.createElement('span');
      const status = ({device:'พร้อมเลือก',offline:'ออฟไลน์',unauthorized:'รออนุญาตบนมือถือ'})[item.state] || item.state;
      label.textContent = `${item.model} • ${item.transport} • ${status} • ${item.serial}`;
      const button = rowButton(selected && item.aliases.includes(selected.serial) ? 'เลือกอยู่' : 'ใช้เครื่องนี้', 'select', item.serial);
      button.dataset.unavailable = String(item.state !== 'device' || Boolean(selected && item.aliases.includes(selected.serial)));
      row.append(label, button); devices.append(row);
    }
    panel.querySelectorAll('button, input').forEach(el => { el.disabled = Boolean(busy || el.dataset.unavailable === 'true'); });
  }
  window.renderAndroidWifi = snapshot => render(snapshot?.system?.android_wifi);
  async function call(action, payload = {}) {
    if (sending || state.busy) return;
    sending = true; render(state);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('/api/desktop/action', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({action,payload}), signal:controller.signal});
      delete payload.code;
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || 'ยังยืนยันการเชื่อมต่อไม่ได้');
      state = result.android_wifi || state;
      return result;
    } catch (error) {
      // Never echo the submitted code or retry a potentially accepted pairing operation.
      state = {...state, error:error.name === 'AbortError' ? 'ยังยืนยันผลไม่ได้ กดตรวจมือถือก่อนลองจับคู่อีกครั้ง' : error.message};
    } finally {
      delete payload.code; clearTimeout(timer); sending = false; render(state);
    }
  }
  q('#android-wifi-pair-form').addEventListener('submit', event => {
    event.preventDefault();
    if (sending || state.busy) return;
    const payload = {endpoint:q('#android-wifi-pair-endpoint').value.trim(), code:q('#android-wifi-code').value.trim()};
    q('#android-wifi-code').value = ''; // Clear before sending; never save in browser storage.
    call('android_wifi_pair', payload);
  });
  q('#android-wifi-connect-form').addEventListener('submit', event => {
    event.preventDefault(); call('android_wifi_connect', {endpoint:q('#android-wifi-connect-endpoint').value.trim()});
  });
  panel.addEventListener('click', event => {
    const button = event.target.closest('[data-wifi-action]');
    if (!button || button.disabled) return;
    const action = button.dataset.wifiAction;
    if (action === 'refresh') { lastScan = Date.now(); call('android_wifi_refresh'); }
    if (action === 'select') call('android_wifi_select', {serial:button.dataset.value});
    if (action === 'pairing' || action === 'connect') {
      q(action === 'pairing' ? '#android-wifi-pair-endpoint' : '#android-wifi-connect-endpoint').value = button.dataset.value;
      message('เลือกพอร์ตแล้ว • ตรวจว่าตรงกับมือถือของคุณก่อนกดดำเนินการ');
    }
  });
  document.querySelector('[data-page="queue"]')?.addEventListener('click', () => {
    lastScan = Date.now(); call('android_wifi_refresh');
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) q('#android-wifi-code').value = ''; });
  setInterval(() => {
    if (!visible() || sending || state.busy || window.SmartFlowShopee?.busy()) return;
    if (state.phase === 'connected' && Date.now() - lastScan > 15000) {
      lastScan = Date.now(); call('android_wifi_refresh');
    }
  }, 3000);
  render({message:'กดตรวจมือถือ หรือกรอกข้อมูลจับคู่จากหน้าจอโทรศัพท์'});
})();
