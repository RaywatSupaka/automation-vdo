const ui = {
  state: null,
  activePage: (location.hash || '#dashboard').slice(1),
  libraryFilter: 'all',
  libraryQuery: '',
  librarySort: 'newest',
  settingsHydrated: false,
  formsHydrated: false,
  lastNoticeAt: '',
  lastAutomationErrorAt: '',
  polling: false,
  pendingFullPoll: false,
  progressType: '',
  progressJobId: '',
  progressResultReady: false,
  progressWasActive: false,
  progressCloseTimer: null,
  progressMinimized: false,
  confirmAction: null,
  selectedProductId: '',
  toolsHydrated: false,
  dramaFootage: [],
  dramaImages: {},
  dramaPlotBoard: [],
  storyImage: '',
  storyBatchImage: '',
  storyBatchDirty: false,
  continueSeriesId: '',
  aiModelDrafts: {},
  pollFailures: 0,
  subtitlePreviewTimer: null,
  subtitlePreviewSequence: 0,
  subtitlePreviewMode: 'detail',
  selectedLogoAssetId: '',
  libraryVisibleCount: 24,
  libraryDetail: null,
  libraryDetailTicket: 0,
  lastClickedButton: null,
  lastClickAt: 0,
  automationErrorPage: 'products',
};

const pageMeta = {
  intro: ['VIDEO INTRO', 'อินโทรคลิป'],
  presenter: ['PRESENTER STUDIO', 'ตัวละครผู้บรรยาย'],
  'presenter-settings': ['PRESENTER SETTINGS', 'ตั้งค่าผู้บรรยาย'],
  dashboard: ['SMARTFLOW CONTROL CENTER', 'หน้าแรก'],
  products: ['SHOPEE VIDEO', 'คลิปสินค้า Shopee'],
  story: ['STORY SHORTS STUDIO', 'เล่าเรื่อง Shorts'],
  drama: ['AI DRAMA SERIES STUDIO', 'ละครสั้น AI'],
  library: ['FINAL OUTPUTS', 'คลังวิดีโอ'],
  creation: ['CREATION QUEUE', 'คิวสร้างคลิป'],
  voice: ['AI VOICE', 'เสียงพากย์ AI'],
  subtitle: ['AI SUBTITLE', 'ซับไตเติล'],
  audio: ['AUDIO MIX', 'เพลงและเสียงประกอบ'],
  logo: ['BRANDING', 'โลโก้'],
  queue: ['SHOPEE • ANDROID', 'โพสต์ Shopee'],
  settings: ['WORKSPACE SETTINGS', 'ค่าเริ่มต้นและคุณภาพ'],
  guide: ['SETUP CENTER', 'ตั้งค่าครั้งแรกและคู่มือ'],
  'ai-chat': ['WEBVIEW2 PROTOTYPE', 'AI Chat'],
  logs: ['LIVE ACTIVITY', 'ช่วยเหลือและบันทึกระบบ'],
  longvideo: ['LONG VIDEO', 'สร้างคลิปยาว 16:9'],
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
document.addEventListener('click', event => {
  ui.lastClickedButton = event.target.closest?.('button') || null;
  ui.lastClickAt = Date.now();
}, true);
const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const formatBytes = bytes => {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
};
const formatDate = value => {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString('th-TH', {dateStyle:'short', timeStyle:'short'});
};
const formatDuration = seconds => {
  const value = Math.max(0, Math.round(Number(seconds || 0)));
  if (!value) return '—';
  const minutes = Math.floor(value / 60), remain = value % 60;
  return minutes ? `${minutes} นาที ${remain} วินาที` : `${remain} วินาที`;
};
const providerLabel = value => value === 'gemini' ? 'Gemini Web' : 'ChatGPT Web';
const fallbackAiModelOptions = {
  chatgpt: [
    {value:'auto', label:'ใช้โมเดลปัจจุบัน'},
    {value:'instant', label:'Instant • เร็ว'},
    {value:'thinking', label:'Thinking • คิดละเอียด'},
    {value:'pro', label:'Pro • เหตุผลขั้นสูง'},
  ],
  gemini: [
    {value:'auto', label:'ใช้โมเดลปัจจุบัน'},
    {value:'flash_lite', label:'Flash-Lite • เร็วที่สุด'},
    {value:'flash', label:'Flash • รอบด้าน'},
    {value:'pro', label:'Pro • เหตุผลขั้นสูง'},
    {value:'long_thinking', label:'การคิดที่นานขึ้น • ปัญหาซับซ้อน'},
  ],
};
const aiModelOptions = provider => {
  const key = provider === 'gemini' ? 'gemini' : 'chatgpt';
  const remote = ui.state?.settings?.ai_web_model_options?.[key];
  return Array.isArray(remote) && remote.length ? remote : fallbackAiModelOptions[key];
};
const savedAiModel = provider => {
  const key = provider === 'gemini' ? 'gemini' : 'chatgpt';
  return String(ui.state?.settings?.[`${key}_web_model`] || (key === 'gemini' ? 'long_thinking' : 'auto'));
};
function fillAiModelSelect(providerId, modelId, preferred = '') {
  const provider = String($(providerId)?.value || 'chatgpt');
  const select = $(modelId); if (!select) return;
  const oldProvider = String(select.dataset.provider || '');
  if (oldProvider && select.value) ui.aiModelDrafts[oldProvider] = select.value;
  const options = provider === 'chatgpt'
    ? [{value:'auto', label:'ใช้โมเดลปัจจุบัน'}, ...aiModelOptions(provider).filter(item => item.value !== 'auto')]
    : aiModelOptions(provider);
  select.innerHTML = options.map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join('');
  const wanted = provider === 'chatgpt' ? 'auto' : String(preferred || ui.aiModelDrafts[provider] || savedAiModel(provider));
  select.value = options.some(item => item.value === wanted) ? wanted : String(options[0]?.value || 'auto');
  select.dataset.provider = provider;
  ui.aiModelDrafts[provider] = select.value;
  const locked = provider === 'chatgpt';
  select.disabled = locked;
  select.classList.toggle('model-locked', locked);
  select.setAttribute('aria-readonly', String(locked));
  select.hidden = locked;
  const field = select.closest('.field');
  if (field) {
    // ChatGPT uses its current web model; do not occupy a full setting row
    // with a disabled selector that the user cannot change.
    field.hidden = locked;
    let note = $('.model-current-note', field);
    if (!note) { note = document.createElement('span'); note.className = 'model-current-note'; select.after(note); }
    note.textContent = '✓ ใช้โมเดลที่เปิดอยู่ใน ChatGPT'; note.hidden = !locked;
    const help = $('small', field); if (help) help.hidden = locked;
  }
}
function selectedAiModel(providerId, modelId) {
  const provider = String($(providerId)?.value || 'chatgpt');
  const select = $(modelId);
  return String(select?.value || savedAiModel(provider));
}
function bindAiModelSelect(providerId, modelId) {
  $(providerId)?.addEventListener('change', () => fillAiModelSelect(providerId, modelId));
  $(modelId)?.addEventListener('change', event => {
    ui.aiModelDrafts[String($(providerId)?.value || 'chatgpt')] = String(event.target.value || 'auto');
  });
}
const coverThemeLabel = value => ({cinematic:'Cinematic Neon',romance:'Romance Rose',thriller:'Thriller Red',clean:'Clean Premium'}[value] || 'Cinematic Neon');
const statusReady = value => ['ready','READY','complete','completed','posted'].includes(String(value || ''));

function currentDramaPlotBoard() {
  return $$('.drama-plot-row', $('#drama-plot-board')).map((row, index) => ({
    episode_no:index + 1,
    summary:$('[data-drama-plot-summary]', row)?.value.trim() || '',
    hook:$('[data-drama-plot-hook]', row)?.value.trim() || '',
  }));
}

function renderDramaPlotBoard(reset = false) {
  const board = $('#drama-plot-board');
  if (!board) return;
  if (reset) ui.dramaPlotBoard = [];
  else currentDramaPlotBoard().forEach((row, index) => { ui.dramaPlotBoard[index] = row; });
  const count = Math.max(1, Number($('#drama-episodes')?.value || 3));
  const premise = $('#drama-premise')?.value.trim() || '';
  board.innerHTML = Array.from({length:count}, (_, index) => {
    const number = index + 1, saved = ui.dramaPlotBoard[index] || {};
    const defaultSummary = number === 1
      ? (premise || 'เปิดเรื่อง แนะนำตัวละคร และวางปมหลัก')
      : number === count ? 'คลี่คลายปมหลักและปิดเรื่องให้ครบ' : `ขยายความขัดแย้งจาก EP ${number - 1} และสร้างจุดเปลี่ยนใหม่`;
    const defaultHook = number === count ? 'ปิดตอนอย่างสมบูรณ์' : `ทิ้งเหตุการณ์ชวนติดตาม EP ${number + 1}`;
    return `<article class="drama-plot-row"><i>EP ${number}</i><label><span>เป้าหมายของตอน</span><input data-drama-plot-summary value="${escapeHtml(saved.summary || defaultSummary)}" placeholder="ตอนนี้เกิดอะไรขึ้นและพาเรื่องไปทางไหน"></label><label><span>จุดจบ / Hook</span><input data-drama-plot-hook value="${escapeHtml(saved.hook || defaultHook)}" placeholder="ทิ้งอะไรไว้ให้ติดตามตอนต่อไป"></label></article>`;
  }).join('');
}

async function getState(compact = false) {
  const response = await fetch(`/api/desktop/state${compact ? (ui.activePage === 'logs' ? '?mode=logs' : '?mode=compact') : ''}`, {cache:'no-store'});
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || 'อ่านสถานะระบบไม่สำเร็จ');
  return data;
}

async function postAction(action, payload = {}) {
  payload = window.presenterPayload?.(action, payload) || payload;
  const captured=window.productOptionSnapshot?.finish(action,payload);
  if(captured)return captured;
  const queueRoute=window.routeCreationQueue?.(action,payload);
  if(queueRoute){action=queueRoute.action;payload=queueRoute.payload;}
  const button = ui.lastClickedButton && Date.now() - ui.lastClickAt < 700 ? ui.lastClickedButton : null;
  const originalHtml = button && !button.dataset.busy ? button.innerHTML : '';
  if (button && !button.dataset.busy) {
    button.dataset.busy = '1';
    button.classList.add('is-busy');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.dataset.originalHtml = originalHtml;
  }
  let response;
  try {
    response = await fetch('/api/desktop/action', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action, payload}),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || data.message || 'ทำรายการไม่สำเร็จ');
    if(queueRoute?.queued){showPage('creation');toast('บันทึกเข้าคิวแล้ว • กดเริ่มคิวเมื่อพร้อม','success');}
    return queueRoute?.queued ? {...data,queued_only:true} : data;
  } finally {
    if (button && button.dataset.busy) {
      button.classList.remove('is-busy');
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.innerHTML = button.dataset.originalHtml || originalHtml;
      delete button.dataset.busy;
      delete button.dataset.originalHtml;
    }
  }
}

function readBlobAsDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('อ่านไฟล์รูปไม่สำเร็จ'));
    reader.readAsDataURL(blob);
  });
}

async function prepareReferenceImage(file) {
  if (!file || !/^image\/(png|jpeg|webp)$/i.test(file.type || '')) throw new Error('รองรับรูป PNG, JPG และ WEBP เท่านั้น');
  if (file.size <= 1.5 * 1024 * 1024) return readBlobAsDataUrl(file);
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 2048 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext('2d');
    context.fillStyle = '#ffffff'; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    const resized = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .9));
    if (!resized) throw new Error('ย่อรูปไม่สำเร็จ');
    return readBlobAsDataUrl(resized);
  } catch (error) {
    if (file.size > 12 * 1024 * 1024) throw new Error('รูปมีขนาดใหญ่เกินไป กรุณาใช้ไฟล์ไม่เกิน 12 MB');
    return readBlobAsDataUrl(file);
  }
}

async function uploadReferenceImage(file, purpose = 'drama') {
  const dataUrl = await prepareReferenceImage(file);
  const result = await postAction('upload_reference_image', {purpose, filename:file.name, data_url:dataUrl});
  return {...result, dataUrl};
}

async function prepareLogoImage(file) {
  if (!file || !/^image\/(png|jpeg|webp)$/i.test(file.type || '')) throw new Error('รองรับโลโก้ PNG, JPG และ WEBP เท่านั้น');
  if (file.size > 12 * 1024 * 1024) throw new Error('โลโก้มีขนาดใหญ่เกินไป กรุณาใช้ไฟล์ไม่เกิน 12 MB');
  return readBlobAsDataUrl(file);
}

function toast(message, kind = 'info') {
  const node = $('#toast');
  node.className = `toast ${kind}`;
  node.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  node.setAttribute('aria-live', kind === 'error' ? 'assertive' : 'polite');
  $('span', node).textContent = message;
  requestAnimationFrame(() => node.classList.add('show'));
  clearTimeout(node._timer);
  node._timer = setTimeout(() => node.classList.remove('show'), kind === 'error' ? 12000 : 4200);
}

function showPage(page, updateHash = true) {
  if (page === 'video') page = 'settings';
  if (!pageMeta[page]) page = 'dashboard';
  ui.activePage = page;
  document.body.dataset.page = page;
  setNewJobMenu(false);
  $$('.page').forEach(node => node.classList.toggle('active', node.dataset.view === page));
  $$('.nav-item').forEach(node => {
    const active = node.dataset.page === page;
    node.classList.toggle('active', active);
    if (active) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current');
  });
  $$('.nav-group').forEach(group => { if (group.querySelector('.nav-item.active')) group.open = true; });
  $('.nav-item.active')?.scrollIntoView({block:'nearest'});
  $('#page-kicker').textContent = pageMeta[page][0];
  $('#page-title').textContent = pageMeta[page][1];
  if (updateHash && location.hash !== `#${page}`) history.replaceState(null, '', `#${page}`);
  if (typeof setSidebarOpen === 'function') setSidebarOpen(false);
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  window.scrollTo({top:0, behavior:reduceMotion ? 'auto' : 'smooth'});
  if (ui.state) poll(true);
}

function setNewJobMenu(open) {
  const menu = $('#new-job-menu');
  const toggle = $('#new-job-toggle');
  if (!menu || !toggle) return;
  menu.hidden = !open;
  toggle.setAttribute('aria-expanded', String(open));
}

function bindLibraryOpenControls(root = document) {
  $$('[data-library-id]', root).forEach(button => {
    if (button.dataset.libraryOpenBound === '1') return;
    button.dataset.libraryOpenBound = '1';
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      if ($('#detail-modal').open && $('#detail-content').dataset.itemId === button.dataset.libraryId) return;
      openDetail(button.dataset.libraryId);
    });
  });
}

function bindModalCloseControls(root = document) {
  $$('[data-close-modal]', root).forEach(button => {
    if (button.dataset.modalCloseBound === '1') return;
    button.dataset.modalCloseBound = '1';
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      const modal = document.getElementById(button.dataset.closeModal);
      if (!modal?.open) return;
      if (button.dataset.closeModal === 'detail-modal') $('#detail-content video')?.pause();
      modal.close();
      if (button.dataset.closeModal === 'confirm-modal') ui.confirmAction = null;
    });
  });
}

function bindNavigationFallbacks(root = document) {
  $$('[data-page]', root).forEach(button => {
    if (button.dataset.pageFallbackBound === '1') return;
    button.dataset.pageFallbackBound = '1';
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      if (ui.activePage === button.dataset.page) return;
      showPage(button.dataset.page);
    });
  });
  $$('.filter-chip[data-filter]', root).forEach(button => {
    if (button.dataset.filterFallbackBound === '1') return;
    button.dataset.filterFallbackBound = '1';
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      if (ui.libraryFilter === button.dataset.filter && button.classList.contains('active')) return;
      ui.libraryFilter = button.dataset.filter;
      ui.libraryVisibleCount = 24;
      $$('.filter-chip[data-filter]').forEach(node => {
        const active = node === button;
        node.classList.toggle('active', active);
        node.setAttribute('aria-pressed', String(active));
      });
      renderLibrary(ui.state?.library || []);
    });
  });
}

function updateFxMode() {
  const active = Boolean(ui.state?.product_progress?.active || ui.state?.story_progress?.active || ui.state?.presenter_progress?.active);
  document.body.dataset.fxMode = document.hidden ? 'off' : active ? 'lite' : 'full';
}

function statusCard(icon, title, message, ready) {
  return `<article class="health-card ${ready ? 'ready' : ''}"><i>${icon}</i><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(message)}</small></div><b>${ready ? 'พร้อม' : 'ต้องตั้งค่า'}</b></article>`;
}

function formatCredits(value) {
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat('th-TH').format(Math.max(0, number)) : '—';
}

function creditPresentation(service, kind) {
  if (!service?.configured) return {
    state:'disconnected', value:'ยังไม่เชื่อม', mini:'—', note:kind === 'voice' ? 'ใส่ API Key เพื่อดูยอด' : 'เชื่อม Token เพื่อดูยอด',
  };
  if (service.loading) return {state:'loading', value:'กำลังตรวจ...', mini:'…', note:'กำลังอ่านยอดจริงจากบัญชี'};
  if (!service.connected) return {state:'error', value:'ตรวจเครดิตไม่ได้', mini:'!', note:service.message || 'กรุณาตรวจการเชื่อมต่อ'};
  if (kind === 'voice' && service.unlimited) return {
    state:'connected', value:'ไม่จำกัด', mini:'∞', note:service.plan_name ? `แพ็กเกจ ${service.plan_name}` : 'เชื่อม AI Voice แล้ว',
  };
  const credits = formatCredits(service.credits);
  if (kind === 'subtitle') {
    const trial = Number(service.trial_remaining || 0);
    const cost = Number(service.job_credit_cost || 0);
    const details = [];
    if (trial > 0) details.push(`ทดลองฟรีเหลือ ${formatCredits(trial)} งาน`);
    if (cost > 0) details.push(`ใช้ ${formatCredits(cost)} เครดิต/งาน`);
    return {state:'connected', value:`${credits} เครดิต`, mini:credits, note:details.join(' • ') || 'เชื่อม AI Subtitle แล้ว'};
  }
  return {state:'connected', value:`${credits} เครดิต`, mini:credits, note:service.plan_name ? `แพ็กเกจ ${service.plan_name}` : 'เชื่อม AI Voice แล้ว'};
}

function applyCreditView(cardSelector, valueSelector, noteSelector, view, mini = false) {
  const card = $(cardSelector); if (!card) return;
  card.classList.remove('connected', 'disconnected', 'loading', 'error');
  card.classList.add(view.state);
  $(valueSelector).textContent = mini ? view.mini : view.value;
  $(noteSelector).textContent = view.note;
}

function renderCredits(credits = {}) {
  const voice = creditPresentation(credits.voice || {}, 'voice');
  const subtitle = creditPresentation(credits.subtitle || {}, 'subtitle');
  applyCreditView('#credit-voice-mini', '#credit-voice-value', '#credit-voice-note', voice, true);
  applyCreditView('#credit-subtitle-mini', '#credit-subtitle-value', '#credit-subtitle-note', subtitle, true);
  applyCreditView('#dashboard-credit-voice', '#dashboard-credit-voice-value', '#dashboard-credit-voice-note', voice);
  applyCreditView('#dashboard-credit-subtitle', '#dashboard-credit-subtitle-value', '#dashboard-credit-subtitle-note', subtitle);
  applyCreditView('#voice-page-credit', '#voice-page-credit-value', '#voice-page-credit-note', voice);
  applyCreditView('#subtitle-page-credit', '#subtitle-page-credit-value', '#subtitle-page-credit-note', subtitle);
}

function renderSystem(state) {
  const sys = state.system;
  const ready = sys.bridge_online && sys.extension_compatible;
  const versionMismatch = sys.extension_online && !sys.extension_compatible;
  const browserConnection = sys.browser_connection || {};
  const browserMessage = ['connecting', 'needs_attention'].includes(browserConnection.phase) ? browserConnection.message : '';
  $('#side-status-dot').classList.toggle('ready', ready);
  $('#side-status-text').textContent = ready ? 'พร้อมทำงาน' : versionMismatch ? `รุ่น ${sys.extension_version || '?'} ไม่ตรง` : browserConnection.phase === 'connecting' ? 'กำลังเชื่อม Chrome' : browserConnection.phase === 'needs_attention' ? 'ตรวจการเชื่อม Extension' : 'กำลังรอระบบ';
  $('#side-extension').textContent = sys.extension_online
    ? `Extension v${sys.extension_version || '?'} • ${sys.extension_page || 'online'}`
    : browserMessage || `Extension offline • ต้องใช้ v${state.app.extension_required}`;
  $('#top-live-dot').classList.toggle('ready', ready);
  $('#top-live-text').textContent = ready ? 'พร้อมทำงาน' : versionMismatch ? 'ส่วนเสริม Chrome รุ่นไม่ตรง' : 'ตรวจการเชื่อมต่อ';
  $('#footer-dot').classList.toggle('ready', ready);
  $('#footer-status').textContent = sys.status || 'SmartFlow AI พร้อม';
  $('#footer-safe').textContent = 'สร้างคลิปไม่โพสต์อัตโนมัติ • โพสต์ Shopee ต้องยืนยันแยก';
  $('#nav-library-count').textContent = state.stats.videos;
  $('#stat-products').textContent = state.stats.products;
  $('#stat-ai').textContent = state.stats.ai_ready;
  $('#stat-videos').textContent = state.stats.videos;
  $('#stat-stories').textContent = state.stats.stories;
  renderCredits(state.credits || {});
  const voiceCredit = creditPresentation(state.credits?.voice || {}, 'voice');
  const subtitleCredit = creditPresentation(state.credits?.subtitle || {}, 'subtitle');
  $('#health-grid').innerHTML = [
    statusCard('↔', 'Local Bridge', sys.bridge_online ? `ออนไลน์ที่พอร์ต ${sys.bridge_port}` : 'ระบบหลังบ้านยังไม่พร้อม', sys.bridge_online),
    statusCard('⌁', 'Chrome Extension', sys.extension_compatible ? `รุ่น ${sys.extension_version} เชื่อมแล้ว` : `ต้องใช้รุ่น ${state.app.extension_required}`, sys.extension_compatible),
    statusCard('◉', 'AI Voice', sys.voice_configured ? voiceCredit.value : 'ยังไม่ได้เชื่อม API Key', Boolean(state.credits?.voice?.connected)),
    statusCard('字', 'AI Subtitle', sys.subtitle_connected ? subtitleCredit.value : 'ยังไม่ได้เชื่อม Subtitle Token', Boolean(state.credits?.subtitle?.connected)),
  ].join('');
  const latest = state.library[0];
  $('#latest-output').className = latest ? 'latest-output' : 'latest-output empty-state';
  $('#latest-output').innerHTML = latest ? `<button class="video-card-button" aria-label="ดูผลงานล่าสุด" data-library-id="${escapeHtml(latest.item_id)}"></button><div class="latest-mini"><img src="${escapeHtml(latest.preview_url || '')}" alt="" onerror="this.style.opacity=.08"><div><span>${escapeHtml(latest.kind_label)}</span><strong>${escapeHtml(latest.title)}</strong><small>${escapeHtml(videoSourcePresentation(latest).label)} • ${escapeHtml(formatDate(latest.updated_at))} • ${formatBytes(latest.size_bytes)}</small></div></div>` : 'ยังไม่มีวิดีโอที่พร้อมใช้';
  bindLibraryOpenControls($('#latest-output'));
  const audioChoice=window.mediaAudioChoice?.('product');
  const needsVoice=!audioChoice || audioChoice.mode==='api';
  const needsSubtitle=audioChoice ? audioChoice.subtitle && audioChoice.mode!=='none' : $('#product-subtitle').checked;
  $('#product-readiness').classList.toggle('ready', sys.extension_compatible && (!needsVoice || (sys.voice_configured && sys.voice_reference_configured)) && (!needsSubtitle || sys.subtitle_connected));
  const readiness = [];
  readiness.push(sys.extension_compatible ? '✓ Extension พร้อม' : `• Extension ต้องเป็น v${state.app.extension_required}`);
  readiness.push(!needsVoice ? '✓ ไม่ใช้เสียง API' : sys.voice_configured && sys.voice_reference_configured ? '✓ AI Voice พร้อม' : '• ยังต้องตั้งค่า AI Voice');
  if (needsSubtitle) readiness.push(sys.subtitle_connected ? '✓ Subtitle พร้อม' : '• ยังต้องเชื่อม Subtitle');
  $('#product-readiness').textContent = readiness.join('   ');
  window.SmartFlowUX?.renderSystem(state, async () => {
    // Read-only status refresh; unlike the toolbar, never refreshes credits or sends actions.
    const latest = await getState();
    render(latest);
  });
}

function pill(value) {
  // One shared vocabulary (status_vocabulary.js). `status-pill` keeps the old layout hooks.
  return SmartFlowStatus.pill(value, {extraClass: 'status-pill'});
}

function renderWorkspaceIssues(snapshot = {}) {
  const banner = $('#workspace-issues');
  if (!banner) return;
  snapshot = snapshot && typeof snapshot === 'object' ? snapshot : {};
  const count = Math.max(0, Number(snapshot.count) || 0);
  const rows = Array.isArray(snapshot.items) ? snapshot.items : [];
  banner.hidden = count === 0;
  if (!count) return;
  $('#workspace-issues-summary').textContent = `พบ ${count} งานที่ต้องตรวจไฟล์สถานะ`;
  $('#workspace-issue-list').innerHTML = rows.map(row => `
    <div class="workspace-issue-row">
      <span><b>${escapeHtml(row.label)} · ${escapeHtml(row.id)}</b><small>${escapeHtml(row.reason)}</small></span>
      <button type="button" class="button secondary compact" data-issue-kind="${escapeHtml(row.kind)}" data-issue-id="${escapeHtml(row.id)}">เปิดโฟลเดอร์</button>
    </div>`).join('') + (count > rows.length ? `<small>แสดง ${rows.length} จาก ${count} รายการ</small>` : '');
}

$('#workspace-issue-list').addEventListener('click', async event => {
  const button = event.target.closest?.('[data-issue-kind][data-issue-id]');
  if (!button) return;
  try {
    await postAction('open_workspace_issue_folder', {kind: button.dataset.issueKind, id: button.dataset.issueId});
  } catch (error) { toast(error.message, 'error'); }
});

function videoSourcePresentation(item = {}) {
  const sourceType = String(item.video_source_type || '').trim();
  const remote = Math.max(0, Number(item.source_remote_count ?? item.flow_remote_count ?? item.flow_remote_clip_count ?? item.flow_clip_count ?? 0) || 0);
  const local = Math.max(0, Number(item.source_local_count ?? item.local_motion_count ?? item.flow_local_motion_clip_count ?? item.flow_fallback_count ?? 0) || 0);
  const total = Math.max(0, Number(item.source_total_count ?? item.segment_count ?? item.flow_scene_count ?? (remote + local)) || 0);
  const target = Math.max(0, Number(item.source_target_count ?? item.segment_target_count ?? item.scene_count ?? total) || 0);
  const kind = String(item.content_kind || item.kind || item.job_type || '').toLowerCase();
  const unit = kind === 'product' || String(item.id || item.job_id || '').startsWith('JOB-') ? 'ช็อต' : 'ฉาก';
  const metaSelected = item.video_ai_provider === 'meta_ai' || item.video_generation_mode === 'meta_ai';
  let label = String(item.video_source_label || '').trim();
  if (item.video_plan_summary) {
    const plan=item.video_plan_summary;
    label=`วิดีโอ ${Number(plan.completed||0)}/${target} ${unit} • Flow ${Number(plan.flow||0)} / Meta ${Number(plan.meta||0)}${plan.local?` / ภาพเคลื่อนไหว ${Number(plan.local)}`:''}`;
  } else if (metaSelected) {
    label = `Meta AI ${Number(item.meta_clip_count || Object.keys(item.meta_clips || {}).length)}/${target} ${unit}`;
  } else if (local || sourceType.includes('hybrid')) {
    label = `เสร็จพร้อมข้อสังเกต • วิดีโอ Flow ${remote} ${unit} • ใช้ภาพแทน ${local} ${unit}`;
  }
  if (!label) {
    if (local || sourceType.includes('hybrid')) {
      label = `Hybrid • Google Flow ${remote} + Local Motion ${local} / ${target || total} ${unit}`;
    } else if (sourceType.startsWith('meta_ai')) {
      label = `Meta AI ${Number(item.meta_clip_count || Object.keys(item.meta_clips || {}).length)}/${target} ${unit}`;
    } else if (remote || sourceType.includes('google_flow') || item.video_generation_mode === 'google_flow') {
      label = `Google Flow ${remote}/${target || remote} ${unit}`;
    } else if (sourceType === 'manual_uploaded_video') {
      label = 'วิดีโอจากไฟล์';
    } else if (sourceType === 'story_image_sequence' || sourceType === 'drama_mixed_media') {
      label = `Motion ในเครื่อง${target ? ` • ${target} ${unit}` : ''}`;
    } else {
      label = 'วิดีโอ Final';
    }
  }
  return {sourceType, remote, local, total, target, unit, label};
}

function renderProducts(products) {
  if (!ui.selectedProductId || !products.some(job => job.id === ui.selectedProductId)) ui.selectedProductId = products[0]?.id || '';
  const selected = $('#product-selected-job');
  const previous = ui.selectedProductId;
  selected.innerHTML = products.length ? products.map(job => `<option value="${escapeHtml(job.id)}">${escapeHtml(job.id)} • ${escapeHtml(job.title)}</option>`).join('') : '<option value="">ยังไม่มี Product Job</option>';
  selected.value = previous;
  renderProductToolScope();
}

function renderProductToolScope() {
  const job = productItem(currentProductJobId());
  const flow = Boolean(job) && String(job.video_ai_provider || 'flow').toLowerCase() === 'flow';
  for (const button of $$('[data-product-tool="multi_flow"], [data-product-tool="auto_flow"]')) {
    button.disabled = !flow;
    button.title = flow ? 'ใช้ผู้ให้บริการที่บันทึกกับงานนี้' : 'เครื่องมือเฉพาะ Google Flow • งาน Meta ให้ใช้ทำต่อของงานเดิม';
  }
}

function jobOptions(products, selectedValue = '') {
  if (!products.length) return '<option value="">ยังไม่มี Product Job</option>';
  return products.map(job => `<option value="${escapeHtml(job.id)}" ${job.id === selectedValue ? 'selected' : ''}>${escapeHtml(job.id)} • ${escapeHtml(job.title)}</option>`).join('');
}

function setSelectOptions(selector, values, selectedValue) {
  const node = $(selector); if (!node) return;
  const current = selectedValue ?? node.value;
  node.innerHTML = values.map(value => typeof value === 'string' ? `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>` : `<option value="${escapeHtml(value.value)}">${escapeHtml(value.label)}</option>`).join('');
  if ([...node.options].some(option => option.value === String(current ?? ''))) node.value = String(current ?? '');
}

let storyRecoveryClearing = false;
let storyView = 'new';
function setStoryView(view) {
  storyView = view === 'old' ? 'old' : 'new';
  const old = storyView === 'old';
  const newPanel = $('#story-new-panel');
  const oldPanel = $('#story-recovery-panel');
  if (newPanel) newPanel.hidden = old;
  if (oldPanel) oldPanel.hidden = !old;
  $('#story-new-tab')?.setAttribute('aria-selected', String(!old));
  $('#story-old-tab')?.setAttribute('aria-selected', String(old));
}

function updateStorySetupPosition() {
  const scroller = $('#story-setup-scroll');
  const progress = $('.story-setup-progress');
  const position = $('#story-setup-position');
  if (!scroller || !progress || !position) return;
  const sections = [...scroller.querySelectorAll('[data-story-setup-section]')];
  if (!sections.length) return;
  let index = 0;
  if (scroller.scrollTop > 2) {
    const edge = scroller.getBoundingClientRect().top + scroller.clientHeight * .35;
    sections.forEach((section, current) => {
      if (section.getBoundingClientRect().top <= edge) index = current;
    });
  }
  if (scroller.scrollTop >= scroller.scrollHeight - scroller.clientHeight - 2 && scroller.scrollTop > 2)
    index = sections.length - 1;
  const step = index + 1;
  position.textContent = `ขั้นที่ ${step} จาก ${sections.length}`;
  progress.setAttribute('aria-valuemax', String(sections.length));
  progress.setAttribute('aria-valuenow', String(step));
  $('#story-setup-progress-fill').style.width = `${step / sections.length * 100}%`;
  document.querySelectorAll('[data-story-setup]').forEach(button => {
    if (button.dataset.storySetup === sections[index].dataset.storySetupSection)
      button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
  });
}

function initStorySetupScroller() {
  const scroller = $('#story-setup-scroll');
  if (!scroller) return;
  scroller.addEventListener('scroll', updateStorySetupPosition, {passive:true});
  document.querySelectorAll('[data-story-setup]').forEach(button => button.addEventListener('click', () => {
    const section = scroller.querySelector(`[data-story-setup-section="${button.dataset.storySetup}"]`);
    if (!section) return;
    const top = section.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
    scroller.scrollTo({top, behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  }));
  window.addEventListener('resize', updateStorySetupPosition);
  updateStorySetupPosition();
}
async function clearStoryRecovery() {
  if (storyRecoveryClearing) return;
  if (!window.confirm('ล้างงานที่ต้องดำเนินการต่อทั้งหมดในหน้าเล่าเรื่อง Shorts?\nรวมงานที่ไม่ได้แสดงใน 8 รายการแรก และนำงานเหล่านี้ออกจากคิว\nรูป บท เสียง วิดีโอ และ Checkpoint เดิมยังอยู่ ไม่ลบไฟล์ และไม่กระทบงานสินค้า/ละครสั้น')) return;
  storyRecoveryClearing = true;
  renderStories(ui.state?.stories || [], ui.state?.story_progress || {});
  try {
    const result = await postAction('clear_story_recovery', {confirmed:true});
    if (result?.ok === false) throw Error(result.error || 'ล้างรายการไม่สำเร็จ');
    toast(`ล้างแล้ว ${Number(result.cleared || 0)} งาน • ไฟล์เดิมยังอยู่ครบ`, 'success');
  } catch (error) { toast(error.message, 'error'); }
  finally {
    storyRecoveryClearing = false;
    await poll();
    renderStories(ui.state?.stories || [], ui.state?.story_progress || {});
  }
}

function metaSequenceAction(job, active) {
  if (active || job.provider !== 'chatgpt' || job.video_generation_mode !== 'meta_ai'
      || job.meta_scene_sequence_version === 1 || job.video_plan_summary
      || job.content_kind === 'product' || job.job_type === 'drama_episode'
      || ['cancelled','canceled','deleted','complete','completed','ready'].includes(job.status)) return '';
  return `<button class="button ghost compact" data-adopt-meta-sequence="${escapeHtml(job.id)}">เปลี่ยนเป็นภาพ → วิดีโอทีละฉาก</button>`;
}

function renderLongVideoRecovery(stories, storyProgress = {}) {
  const panel = $('#long-recovery-panel'), list = $('#long-recovery-list');
  if (!panel || !list) return;
  const finished = new Set(['ready','complete','completed','success','succeeded']);
  const pending = (Array.isArray(stories) ? stories : []).filter(job => {
    if (!job.long_video || job.series_id || job.product_story || job.story_source_only || job.cast_creation) return false;
    const status = String(job.status || '').toLowerCase(), video = String(job.video_status || '').toLowerCase();
    const stopped = ['cancelled','canceled'].includes(status) && job.pipeline_stage === 'user_cancel'
      && job.cancel_reason === 'ผู้ใช้ยกเลิกการทำงาน';
    if (['deleted','video_deleted'].includes(status) || ['deleted','video_deleted'].includes(video)) return false;
    if (['cancelled','canceled'].includes(status) && !stopped) return false;
    return !(finished.has(status) && finished.has(video));
  }).sort((a,b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  panel.hidden = !pending.length;
  $('#long-recovery-count').textContent = `${pending.length} งาน`;
  const stages = {chatgpt:'สร้างบทและภาพ',meta_ai:'สร้างวิดีโอด้วย Meta AI',google_flow:'สร้างวิดีโอด้วย Google Flow',voice:'สร้างเสียงพากย์',video:'ประกอบวิดีโอ',finishing:'ตรวจและบันทึกผลงาน'};
  list.innerHTML = pending.map(job => {
    const active = storyProgress.active && String(storyProgress.job_id) === String(job.id);
    const total = Number(job.scene_count || 0), images = Number(job.image_count || 0);
    const mode = job.video_generation_mode;
    const clips = mode === 'meta_ai' ? ` • คลิป Meta ${Number(job.meta_clip_count || 0)}/${total}`
      : mode === 'google_flow' ? ` • คลิป Flow ${Number(job.flow_clip_count || 0)}/${total}` : '';
    const stage = stages[job.pipeline_stage] || 'ทำส่วนที่เหลือต่อ';
return `<article class="story-recovery-item"><header><div><small>${escapeHtml(job.id)}</small><h3>${escapeHtml(job.title || job.topic || 'คลิปยาว')}</h3></div><span class="story-recovery-badge sf-status ${active ? 'running' : 'paused'}" data-tone="${active ? 'running' : 'paused'}">${active ? 'กำลังสร้าง' : 'หยุดไว้'}</span></header><div class="story-recovery-checkpoint"><b>${escapeHtml(stage)}</b><span>ภาพ ${images}/${total}${clips}</span></div>${job.last_error ? `<div class="story-recovery-error">${escapeHtml(job.last_error)}</div>` : ''}<footer><button class="button ghost compact" data-open-job="${escapeHtml(job.id)}">เปิดโฟลเดอร์งาน</button><button class="button primary compact" data-retry-story="${escapeHtml(job.id)}" ${storyProgress.active ? 'disabled' : ''}>${active ? 'กำลังดำเนินการ' : '↻ ทำส่วนที่เหลือต่อ'}</button>${metaSequenceAction(job, Boolean(storyProgress.active))}</footer></article>`;
  }).join('');
}

function storyRecoveryTimeline(job, failed) {
  const total = Math.max(0, Number(job.scene_count || 0));
  const recovery = job.recovery || {};
  const saved = new Set((Array.isArray(recovery.saved_image_scenes) ? recovery.saved_image_scenes : [])
    .map(Number).filter(index => Number.isInteger(index) && index >= 1 && index <= total));
  const verifiedCount = saved.size;
  const reportedCount = Number(job.image_count || 0);
  const countLabel = Array.isArray(recovery.saved_image_scenes)
    ? `${verifiedCount}/${total} ฉาก` : `${reportedCount}/${total} ฉาก`;
  const failedScene = Number(recovery.failed_image_scene || 0);
  const analysisReady = recovery.analysis_ready === true;
  const stage = String(job.pipeline_stage || '').toLowerCase();
  const imageChips = Array.from({length: Math.min(total, 15)}, (_, offset) => {
    const index = offset + 1;
    const state = saved.has(index) ? 'done' : failed && index === failedScene ? 'failed' : 'pending';
    const label = state === 'done' ? 'บันทึกแล้ว' : state === 'failed' ? 'หยุดที่นี่' : 'ยังไม่เริ่ม';
    return `<span class="story-recovery-scene ${state}" title="ภาพฉาก ${index}: ${label}">ฉาก ${index} · ${label}</span>`;
  }).join('');
  const failureLabel = failedScene
    ? `ภาพฉาก ${failedScene}${recovery.send_not_started ? ' • ยังไม่ส่งคำขอ' : ' • ต้องตรวจสอบ'}`
    : stage === 'chatgpt' ? 'ขั้นเชื่อมต่อหรือสร้างบท' : stage === 'voice' ? 'ขั้นเสียงพากย์'
      : stage === 'video' ? 'ขั้นประกอบวิดีโอ' : 'ขั้นทำงานล่าสุด';
  return `<div class="story-recovery-timeline" aria-label="สถานะขั้นตอนงาน">
    <div class="story-recovery-step ${analysisReady ? 'done' : failed && stage === 'chatgpt' && !failedScene ? 'failed' : 'pending'}"><b>บทและรายละเอียด</b><span>${analysisReady ? 'บันทึกแล้ว' : 'ยังไม่ยืนยันว่าครบ'}</span></div>
    <div class="story-recovery-step ${verifiedCount === total && total ? 'done' : 'pending'}"><b>ภาพประกอบ</b><span>บันทึกแล้ว ${countLabel}</span></div>
    ${imageChips ? `<div class="story-recovery-scenes">${imageChips}</div>` : ''}
    ${failed ? `<div class="story-recovery-step failed"><b>จุดที่หยุด</b><span>${escapeHtml(failureLabel)}</span></div>` : ''}
    <div class="story-recovery-step ${job.voice_status === 'ready' ? 'done' : 'pending'}"><b>เสียงและวิดีโอ</b><span>${job.voice_status === 'ready' ? 'เสียงบันทึกแล้ว' : 'ยังไม่ถึงขั้นนี้หรือยังไม่เสร็จ'}</span></div>
  </div>`;
}

function storyRecoveryProgress(job, storyProgress, isActive) {
  const livePercent = Number(storyProgress.percent);
  const live = isActive && Number.isFinite(livePercent);
  const total = Math.max(0, Number(job.scene_count || 0));
  const saved = new Set((Array.isArray(job.recovery?.saved_image_scenes) ? job.recovery.saved_image_scenes : [])
    .map(Number).filter(index => Number.isInteger(index) && index >= 1 && index <= total));
  const percent = live ? Math.max(0, Math.min(100, Math.round(livePercent)))
    : total ? Math.round(saved.size / total * 100) : 0;
  const label = live ? 'ความคืบหน้างานปัจจุบัน' : 'ภาพฉากที่บันทึกแล้ว';
  const detail = live ? `${percent}%` : total ? `${saved.size}/${total} ฉาก` : 'รอข้อมูลจำนวนฉาก';
  return `<div class="story-recovery-progress"><div class="story-recovery-progress-label"><b>${label}</b><span>${detail}</span></div><div class="story-recovery-progress-track" role="progressbar" aria-label="${label}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><i style="width:${percent}%"></i></div></div>`;
}

function renderStories(stories, storyProgress = {}) {
  renderLongVideoRecovery(stories, storyProgress);
  const list = $('#story-list');
  const panel = $('#story-recovery-panel');
  if (!list || !panel) return;
  const finished = new Set(['ready','complete','completed','success','succeeded']);
  const cancelled = new Set(['cancelled','canceled','deleted']);
  const activeJobId = storyProgress.active ? String(storyProgress.job_id || '') : '';
  const pending = (Array.isArray(stories) ? stories : []).filter(job => {
    const status = String(job.status || '').toLowerCase();
    const video = String(job.video_status || '').toLowerCase();
    if (String(job.job_type || 'story_short') !== 'story_short') return false;
    if (job.content_kind === 'product' || job.product_story || job.series_id || job.cast_creation || job.long_video || job.story_source_only) return false;
    const stopped = ['cancelled','canceled'].includes(status) && job.pipeline_stage === 'user_cancel'
      && job.cancel_reason === 'ผู้ใช้ยกเลิกการทำงาน';
    if (cancelled.has(status) && !stopped) return false;
    if (status === 'video_deleted' || video === 'video_deleted' || video === 'deleted') return false;
    return !(finished.has(status) && finished.has(video));
  }).sort((a, b) => {
    const rank = job => {
      const status = String(job.status || '').toLowerCase();
      if (['cancelled','canceled'].includes(status) && job.pipeline_stage === 'user_cancel') return 0;
      if (['error','failed'].includes(status) || String(job.last_error || '').trim()) return 0;
      if (String(job.id || '') === activeJobId) return 1;
      return 2;
    };
    return rank(a) - rank(b) || String(b.updated_at || '').localeCompare(String(a.updated_at || ''));
  });
  panel.hidden = storyView !== 'old';
  const count = $('#story-recovery-count');
  if (count) count.textContent = `${pending.length} งาน`;
  const tabCount = $('#story-recovery-tab-count');
  if (tabCount) tabCount.textContent = String(pending.length);
  const clear = $('#story-recovery-clear');
  if (clear) {
    clear.disabled = storyRecoveryClearing || !pending.length || Boolean(storyProgress.active);
    clear.textContent = storyRecoveryClearing ? 'กำลังล้างรายการ…' : 'ล้างงานที่ต้องทำต่อทั้งหมด';
  }
  if (!pending.length) { list.innerHTML = '<div class="story-recovery-empty">ไม่มีงานเรื่องเล่าที่ต้องทำต่อ • ผลงานที่เสร็จแล้วดูได้ในคลังวิดีโอ</div>'; return; }
  const stageLabels = {chatgpt:'สร้างบทและภาพ',voice:'สร้างเสียงพากย์',google_flow:'เตรียมช่วงวิดีโอ',video:'ประกอบวิดีโอ',finishing:'ตรวจและบันทึกผลงาน'};
  const previousScroll = list.scrollTop;
  list.innerHTML = pending.map(job => {
    const mode = ['google_flow','meta_ai'].includes(job.video_generation_mode)
      ? videoSourcePresentation(job).label
      : 'Motion ในเครื่อง';
    const isActive = String(job.id || '') === activeJobId;
    const status = String(job.status || '').toLowerCase();
    const failed = ['error','failed'].includes(status) || Boolean(String(job.last_error || '').trim());
    const stage = stageLabels[String(job.pipeline_stage || '').toLowerCase()] || 'ทำ Story Shorts ต่อ';
    const error = String(job.last_error || '').trim();
    const creativeLabel=window.creativeJobLabel?.(job)||'';
    const badge = isActive ? '<span class="story-recovery-badge sf-status running" data-tone="running">กำลังสร้าง</span>' : failed ? '<span class="story-recovery-badge sf-status failed" data-tone="failed">สะดุด · ทำต่อได้</span>' : '<span class="story-recovery-badge sf-status paused" data-tone="paused">หยุดไว้</span>';
    const action = isActive
      ? '<button class="button secondary compact" disabled>กำลังดำเนินการ</button>'
      : `<button class="button primary compact" data-retry-story="${escapeHtml(job.id)}">↻ ทำต่อจากจุดเดิม</button>`;
    const dismiss = isActive ? '' : `<button class="button danger compact" data-dismiss-story="${escapeHtml(job.id)}" data-story-title="${escapeHtml(job.title)}">ยกเลิกงานนี้</button>`;
    return `<article class="story-recovery-item" role="listitem"><header><div><small>${escapeHtml(job.id)}</small><h3>${escapeHtml(job.title)}</h3></div>${badge}</header><p>${escapeHtml(job.topic || job.description || 'รอข้อมูลเรื่อง')}</p>${creativeLabel?`<p class="creative-saved-label">${escapeHtml(creativeLabel)}</p>`:''}<div class="story-recovery-checkpoint"><b>Checkpoint: ${escapeHtml(stage)}</b><span>${escapeHtml(mode)}</span></div>${storyRecoveryProgress(job, storyProgress, isActive)}${storyRecoveryTimeline(job, failed)}${error ? `<details class="story-recovery-error"><summary>ดูรายละเอียดข้อผิดพลาด</summary><p>${escapeHtml(error)}</p></details>` : ''}<footer><button class="button ghost compact" data-open-job="${escapeHtml(job.id)}">เปิดโฟลเดอร์งาน</button>${dismiss}${action}${metaSequenceAction(job, Boolean(storyProgress.active))}</footer></article>`;
  }).join('');
  list.scrollTop = previousScroll;
}

let dramaQueuePending = false;
const dramaSeriesPending = new Set();
function dramaQueuedAction(series, activeJobId = '') {
  const first = [...(series.episodes || [])].sort((a,b) => Number(a.episode_no)-Number(b.episode_no))
    .find(ep => ep.status !== 'completed');
  if (series.status === 'cancelled' || first?.status !== 'queued') return '';
  const pending = dramaSeriesPending.has(series.id);
  const disabled = pending || Boolean(activeJobId);
  const label = pending ? 'กำลังเริ่ม…' : `${first.story_job_id ? 'ทำ' : 'เริ่ม'} EP ${Number(first.episode_no)}${first.story_job_id ? ' ต่อจากจุดเดิม' : ''}`;
  return `<button class="button primary compact" data-start-drama-series="${escapeHtml(series.id)}" ${disabled ? 'disabled' : ''}>${label}</button>`;
}
async function toggleDramaQueue() {
  if (dramaQueuePending) return;
  dramaQueuePending = true;
  const button = $('#drama-queue-toggle');
  if (button) button.disabled = true;
  const paused = Boolean(ui.state?.story_queue?.paused);
  try {
    await postAction(paused ? 'story_queue_resume' : 'story_queue_pause');
    toast(paused ? 'ทำคิวต่อแล้ว' : 'พักคิวหลังจบคลิปปัจจุบันแล้ว', 'success');
    await poll();
  } catch (error) { toast(error.message, 'error'); }
  finally {
    dramaQueuePending = false;
    renderDramaSeries(ui.state?.drama_series || {}, ui.state?.story_progress || {});
  }
}

function renderDramaSeries(snapshot = {}, storyProgress = {}) {
  const queueToggle = $('#drama-queue-toggle');
  if (queueToggle) {
    const pending = (ui.state?.story_queue?.items || []).filter(item => item.mode === 'drama' && ['queued', 'running'].includes(item.status)).length;
    queueToggle.textContent = pending ? (ui.state?.story_queue?.paused ? `▶ ทำคิวต่อ • เหลือ ${pending} EP` : 'พักคิวหลังจบคลิปปัจจุบัน') : 'ไม่มี EP รอในคิว';
    queueToggle.disabled = dramaQueuePending || pending === 0;
  }
  const list = $('#drama-series-list');
  if (!list) return;
  const rows = Array.isArray(snapshot.items) ? snapshot.items : [];
  const summaryParts = [`${rows.length} ซีรีส์`];
  if (Number(snapshot.running_count || snapshot.active_count || 0)) summaryParts.push(`กำลังทำ ${Number(snapshot.running_count || snapshot.active_count || 0)}`);
  if (Number(snapshot.needs_attention_count || 0)) summaryParts.push(`ต้องแก้ ${Number(snapshot.needs_attention_count || 0)}`);
  $('#drama-series-summary').textContent = rows.length ? summaryParts.join(' • ') : 'ยังไม่มีโปรเจกต์';
  list.innerHTML = rows.length ? rows.map(series => {
    const episodes = Array.isArray(series.episodes) ? series.episodes : [];
    const done = episodes.filter(item => item.status === 'completed').length;
    const running = episodes.find(item => item.status === 'running');
    const failed = episodes.find(item => item.status === 'failed');
    const activeJobId = storyProgress.active ? String(storyProgress.job_id || '') : '';
    const runningJobId = String(running?.story_job_id || '');
    const runningIsLive = Boolean(runningJobId && runningJobId === activeJobId);
    const runningNeedsRecovery = Boolean(runningJobId && !runningIsLive);
    const cancellable = ['queued','running','needs_attention'].includes(String(series.status || '')) || episodes.some(item => ['queued','running','failed'].includes(String(item.status || '')));
    const characterNames = (series.characters || []).map(item => item.name).filter(Boolean).join(' • ');
    const percent = Math.round((done * 100) / Math.max(1, Number(series.episode_count || episodes.length || 1)));
    const canContinue = series.status === 'completed' && done === Number(series.episode_count || 0) && Number(series.episode_count || 0) < 20;
    const nextQueued = episodes.find(item => item.status === 'queued');
    const queueNote = nextQueued ? `เสร็จแล้ว ${done} ตอน • EP ${Number(nextQueued.episode_no)} รอเริ่ม${ui.state?.story_queue?.paused ? ' • คิวกำลังพัก' : ''}` : 'รอคิวทำงาน';
    const detail = series.status === 'cancelled' ? 'ยกเลิกคิวแล้ว • ผลงาน EP ที่เสร็จยังอยู่ครบ' : runningNeedsRecovery ? `EP ${Number(running.episode_no || 1)} หยุดกลางงาน • กู้ไฟล์เดิมแล้วทำต่อได้` : running ? `กำลังทำ EP ${Number(running.episode_no || 1)}` : failed ? `EP ${Number(failed.episode_no || 1)} หยุดแล้ว • เลือกกู้หรือยกเลิกคิวได้` : done === Number(series.episode_count || 0) ? 'สร้างครบแล้ว • พร้อมเพิ่มตอนใหม่ในโปรเจกต์เดิม' : queueNote;
    const retryAction = failed?.story_job_id
      ? (String(failed.story_job_id) === activeJobId
        ? '<button class="button secondary compact" disabled>กำลังกู้คืน</button>'
        : `<button class="button secondary compact" data-retry-story="${escapeHtml(failed.story_job_id)}">↻ กู้คืนไฟล์ EP ${Number(failed.episode_no || 1)}</button>`)
      : failed ? `<button class="button secondary compact" data-retry-drama-episode="${Number(failed.episode_no || 1)}" data-series-id="${escapeHtml(series.id)}">↻ เริ่ม EP ${Number(failed.episode_no || 1)} ใหม่</button>` : '';
    const action = runningNeedsRecovery
      ? `<button class="button primary compact" data-retry-story="${escapeHtml(runningJobId)}">↻ กู้คืนไฟล์ EP ${Number(running.episode_no || 1)}</button>`
      : failed
      ? retryAction
      : canContinue ? `<button class="button secondary compact" data-continue-series="${escapeHtml(series.id)}">＋ เพิ่ม EP ${Number(series.episode_count || 0) + 1} ใหม่</button>` : dramaQueuedAction(series, activeJobId);
    const cancelAction = cancellable ? `<button class="button danger compact" data-cancel-drama-series="${escapeHtml(series.id)}" data-series-title="${escapeHtml(series.title || 'ละครสั้น')}">ยกเลิกคิว</button>` : '';
    return `<article class="drama-series-item"><div class="drama-series-number">${escapeHtml(String(done).padStart(2,'0'))}<small>/${escapeHtml(String(series.episode_count || episodes.length || 0).padStart(2,'0'))}</small></div><div><header><strong>${escapeHtml(series.title || 'ละครสั้น')}</strong>${pill(series.status || 'queued')}</header><p>${escapeHtml(characterNames || 'กำลังเตรียม Character Bible')}</p><div class="mini-progress"><i style="width:${percent}%"></i></div><footer><small>${detail}</small><span class="drama-series-actions"><button class="button ghost compact" data-open-series="${escapeHtml(series.id)}">เปิดโปรเจกต์</button>${action}${cancelAction}</span></footer></div></article>`;
  }).join('') : '<div class="empty-state">ยังไม่มีละครสั้น • เริ่มซีรีส์แรกจากแบบฟอร์มด้านบน</div>';
}

function openDramaProject(seriesId) {
  const series = (ui.state?.drama_series?.items || []).find(item => item.id === seriesId);
  if (!series) { toast('ไม่พบโปรเจกต์ซีรีส์', 'error'); return; }
  const episodes = Array.isArray(series.episodes) ? series.episodes : [];
  const storyProgress = ui.state?.story_progress || {};
  const activeJobId = storyProgress.active ? String(storyProgress.job_id || '') : '';
  const storyJobs = Array.isArray(ui.state?.stories) ? ui.state.stories : [];
  const characters = (series.characters || []).map(item => `<span>${escapeHtml(item.name || 'ตัวละคร')}<small>${escapeHtml(item.role || item.description || '')}</small></span>`).join('');
  const episodeRows = episodes.map(episode => {
    const status = String(episode.status || 'queued');
    const jobId = String(episode.story_job_id || '');
    const isLive = Boolean(jobId && jobId === activeJobId);
    const orphanedRunning = status === 'running' && jobId && !isLive;
    const storyJob = storyJobs.find(item => String(item.id || '') === jobId) || {};
    const checkpointText = jobId ? ` • ไฟล์ภาพ ${Number(storyJob.image_count || 0)}/${Number(storyJob.scene_count || series.scene_count || 0)}` : '';
    const retry = orphanedRunning
      ? `<button class="button primary compact" data-retry-story="${escapeHtml(jobId)}">↻ กู้คืนไฟล์และทำต่อ</button>`
      : status === 'failed' && jobId && !isLive
      ? `<button class="button secondary compact" data-retry-story="${escapeHtml(jobId)}">↻ กู้คืนไฟล์จาก Checkpoint</button>`
      : status === 'failed' && isLive
        ? '<button class="button secondary compact" disabled>กำลังกู้คืน</button>'
      : status === 'failed'
        ? `<button class="button secondary compact" data-retry-drama-episode="${Number(episode.episode_no || 0)}" data-series-id="${escapeHtml(series.id)}">↻ เริ่ม EP นี้ใหม่</button>`
        : jobId ? `<button class="button ghost compact" data-open-job="${escapeHtml(jobId)}">เปิด Job</button>` : '';
    const note = status === 'completed'
      ? (episode.summary || 'วิดีโอตอนนี้เสร็จแล้ว')
      : status === 'failed' ? (episode.error || 'ตอนนี้ต้องกู้ก่อนทำตอนถัดไป')
      : status === 'cancelled' ? 'ยกเลิกแล้ว • ระบบจะไม่ทำ EP นี้ต่อ'
      : orphanedRunning ? `งานหยุดกลางทาง • ไฟล์เดิมยังอยู่และพร้อมกู้คืน${checkpointText}`
      : status === 'running' ? `กำลังสร้างบท ภาพ เสียง หรือวิดีโอ${checkpointText}` : 'รอทำตามลำดับคิว';
    const validation = episode.continuity_validation || {};
    const retryTotal = Number(episode.retry_count || 0) + Number(episode.automation_retry_count || 0);
    const validationText = validation.score == null
      ? 'รอตรวจภาพ'
      : `ตรวจข้อมูลอ้างอิง ${Number(validation.score)}/100${validation.status === 'needs_review' ? ' • ควรตรวจดู' : ' • ผ่าน'} • ยังไม่ยืนยันใบหน้า/เสียง`;
    const warnings = Array.isArray(validation.warnings) ? validation.warnings.filter(Boolean).join(' • ') : '';
    return `<article class="drama-episode-row ${escapeHtml(status)}"><i>${Number(episode.episode_no || 0)}</i><div><header><strong>EP ${Number(episode.episode_no || 0)}${episode.title ? ` • ${escapeHtml(episode.title)}` : ''}</strong>${pill(status)}</header><p class="drama-episode-plan"><b>พล็อตที่ล็อก:</b> ${escapeHtml(episode.planned_summary || 'ดำเนินเรื่องตามโครงหลัก')}${episode.planned_hook ? ` • <b>ปลายตอน:</b> ${escapeHtml(episode.planned_hook)}` : ''}</p><p>${escapeHtml(note)}</p>${episode.next_episode_hook ? `<small>จุดต่อเรื่องจริง: ${escapeHtml(episode.next_episode_hook)}</small>` : ''}<small class="drama-episode-metrics"><span>เวลา <b>${escapeHtml(formatDuration(episode.duration_seconds))}</b></span><span>Retry <b>${retryTotal} รอบ</b></span><span class="continuity-score ${validation.status === 'needs_review' ? 'review' : ''}" title="${escapeHtml(warnings)}">${escapeHtml(validationText)}</span></small></div>${retry}</article>`;
  }).join('');
  const completed = episodes.filter(item => item.status === 'completed').length;
  const canContinue = series.status === 'completed' && completed === episodes.length && episodes.length < 20;
  const provider = providerLabel(series.last_successful_provider || series.provider);
  const totalDuration = episodes.reduce((sum, item) => sum + Number(item.duration_seconds || 0), 0);
  const totalRetries = episodes.reduce((sum, item) => sum + Number(item.retry_count || 0) + Number(item.automation_retry_count || 0), 0);
  const cancellable = ['queued','running','needs_attention'].includes(String(series.status || '')) || episodes.some(item => ['queued','running','failed'].includes(String(item.status || '')));
  const cancelAction = cancellable ? `<button class="button danger" data-cancel-drama-series="${escapeHtml(series.id)}" data-series-title="${escapeHtml(series.title || 'ละครสั้น')}">ยกเลิกคิวซีรีส์นี้</button>` : '';
  $('#drama-project-content').innerHTML = `<header class="drama-project-head"><div><span class="eyebrow">SERIES PROJECT</span><h2>${escapeHtml(series.title || 'ละครสั้น')}</h2><p>${escapeHtml(series.premise || 'โปรเจกต์ละครสั้นต่อเนื่อง')}</p></div>${pill(series.status || 'queued')}</header><section class="drama-project-bible five"><div><span>รหัสโปรเจกต์</span><strong>${escapeHtml(series.id)}</strong></div><div><span>ผู้สร้างภาพ</span><strong>${escapeHtml(provider)} • ${Number(series.scene_count || 10)} ฉาก/EP</strong></div><div><span>ธีมปกซีรีส์</span><strong>${escapeHtml(coverThemeLabel(series.cover_theme))}</strong></div><div><span>เวลารวม</span><strong>${escapeHtml(formatDuration(totalDuration))}</strong></div><div><span>Retry รวม</span><strong>${totalRetries} รอบ</strong></div></section><section class="drama-character-strip">${characters || '<span>ยังไม่มี Character Bible</span>'}</section><div class="drama-timeline">${episodeRows}</div><footer class="drama-project-actions"><button class="button ghost" data-open-series-folder="${escapeHtml(series.id)}">เปิดโฟลเดอร์โปรเจกต์</button><span class="drama-series-actions">${cancelAction}${canContinue ? `<button class="button primary" data-continue-series="${escapeHtml(series.id)}">＋ สร้าง EP ${episodes.length + 1} ต่อในธีมเดิม</button>` : ''}</span></footer>`;
  $('#drama-project-content').querySelector('.drama-project-actions .drama-series-actions')
    ?.insertAdjacentHTML('afterbegin', dramaQueuedAction(series, activeJobId));
  $('#drama-project-modal').showModal();
}

function renderLibrary(items) {
  const category = item => item.aspect_ratio === '16:9' ? 'longvideo' : item.content_kind || (item.kind_label === 'ละครสั้น AI' ? 'drama' : item.kind);
  const query = ui.libraryQuery.trim().toLocaleLowerCase('th-TH');
  const filteredByCategory = ui.libraryFilter === 'all' ? [...items] : items.filter(item => category(item) === ui.libraryFilter);
  const filtered = filteredByCategory.filter(item => {
    if (!query) return true;
    return [item.title,item.product_name,item.series_title,item.job_id,item.description,item.caption,item.kind_label,item.video_source_type,item.video_source_label]
      .filter(Boolean).join(' ').toLocaleLowerCase('th-TH').includes(query);
  }).sort((a,b) => {
    if (ui.librarySort === 'name') return String(a.title || '').localeCompare(String(b.title || ''), 'th');
    const difference = new Date(a.updated_at || 0).getTime() - new Date(b.updated_at || 0).getTime();
    return ui.librarySort === 'oldest' ? difference : -difference;
  });
  $('#library-summary').textContent = `${filtered.length} วิดีโอพร้อมใช้`;
  const signature = JSON.stringify([ui.libraryFilter, ui.librarySort, ui.libraryVisibleCount, window.libraryView?.mode(), filtered]);
  if ($('#library-grid')._signature === signature) return;
  $('#library-grid')._signature = signature;
  const visible = filtered.slice(0, ui.libraryVisibleCount);
  const more = filtered.length > visible.length
    ? `<div class="library-load-more"><span>แสดง ${visible.length} จาก ${filtered.length} รายการ</span><button class="button secondary compact" data-library-more>โหลดรายการเพิ่ม</button></div>`
    : '';
  const card = item => {
    if (window.libraryView) return window.libraryView.card(item);
    const posterUrl = item.cover_url || item.preview_url || '';
    const episode = Number(item.episode_no || 0);
    const source = videoSourcePresentation(item);
    return `<article class="video-card"><div class="video-cover">${posterUrl ? `<img loading="lazy" decoding="async" src="${escapeHtml(posterUrl)}" alt="ปกคลิป ${escapeHtml(item.title)}" onerror="this.style.opacity=.05">` : ''}<span class="video-kind">${escapeHtml(item.kind_label)}${episode ? ` • EP ${episode}` : ''}</span><span class="play-mark">▶</span></div><div class="video-card-body"><h3>${escapeHtml(item.title)}</h3><div class="video-meta"><span>${escapeHtml(source.label)}</span><span>${escapeHtml(formatDate(item.updated_at))} • ${formatBytes(item.size_bytes)}</span></div></div><button class="video-card-button" data-library-id="${escapeHtml(item.item_id)}" aria-label="ดูรายละเอียด ${escapeHtml(item.title)}"></button></article>`;
  };
  if (!filtered.length) {
    $('#library-grid').innerHTML = `<div class="empty-state library-empty">${query ? 'ไม่พบวิดีโอที่ตรงกับคำค้น' : 'ยังไม่มีวิดีโอ Final ในหมวดนี้'}</div>`;
    return;
  }
  if (ui.libraryFilter === 'drama') {
    const groups = new Map();
    filtered.forEach(item => {
      const key = item.series_id || item.series_title || item.job_id;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    });
    const groupMarkup = [...groups.values()].slice(0, ui.libraryVisibleCount).map(group => {
      const ordered = [...group].sort((a,b) => Number(a.episode_no || 0) - Number(b.episode_no || 0));
      const title = ordered[0].series_title || ordered[0].title || 'ละครสั้น AI';
      const key = String(ordered[0].series_id || title);
      return `<details class="library-series-group" data-series-group="${escapeHtml(key)}" ${window.libraryView?.seriesOpen(key) ? 'open' : ''}><summary><strong>${escapeHtml(title)}</strong><span>${ordered.length} EP • กดเพื่อดูตอน</span></summary><div class="library-series-grid">${ordered.map(card).join('')}</div></details>`;
    }).join('') + (groups.size > ui.libraryVisibleCount ? `<div class="library-load-more"><button class="button secondary" data-library-more>โหลดซีรีส์เพิ่ม</button></div>` : '');
    if (window.libraryView) window.libraryView.updateGrid(groupMarkup);
    else $('#library-grid').innerHTML = groupMarkup;
    bindLibraryOpenControls($('#library-grid'));
    return;
  }
  const cardMarkup = visible.map(card).join('') + more;
  if (window.libraryView) window.libraryView.updateGrid(cardMarkup);
  else $('#library-grid').innerHTML = cardMarkup;
  bindLibraryOpenControls($('#library-grid'));
}

function renderGuide(state) {
  const sys = state.system;
  const rows = [
    ['1', 'Local Bridge', sys.bridge_online ? `ออนไลน์ที่พอร์ต ${sys.bridge_port}` : 'กำลังเริ่มระบบหลังบ้าน', sys.bridge_online],
    ['2', 'Chrome Extension', sys.extension_compatible ? `รุ่น ${sys.extension_version} พร้อมใช้งาน` : `ติดตั้งหรือ Reload รุ่น ${state.app.extension_required}`, sys.extension_compatible],
    ['3', 'AI Voice', sys.voice_configured && sys.voice_reference_configured ? 'API Key และเสียงต้นแบบพร้อม' : 'เปิดหน้าตั้งค่าเสียงแล้วบันทึก Key/เสียง', sys.voice_configured && sys.voice_reference_configured],
    ['4', 'AI Subtitle', sys.subtitle_connected ? 'เชื่อมรหัสเครื่องแล้ว' : 'เชื่อม Token หากต้องการ Subtitle', sys.subtitle_connected],
  ];
  $('#setup-list').innerHTML = rows.map(([icon,title,message,ready]) => `<article class="setup-row ${ready ? 'ready' : ''}"><i>${icon}</i><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(message)}</small></div><b>${ready ? 'พร้อม' : 'รอดำเนินการ'}</b></article>`).join('');
  $('#extension-path').textContent = state.settings.extension_path;
}

function renderLogs(state) {
  $('#activity-text').textContent = state.system.activity || state.system.status || 'รอรับงาน';
  $('#activity-time').textContent = new Date().toLocaleTimeString('th-TH', {hour:'2-digit',minute:'2-digit'});
  const lines = window.filterStudioLogs ? window.filterStudioLogs(state.logs || []) : state.logs || [];
  const consoleNode = $('#log-console');
  const atBottom = consoleNode.scrollTop + consoleNode.clientHeight >= consoleNode.scrollHeight - 40;
  consoleNode.textContent = lines.length ? lines.join('\n') : 'ยังไม่มีข้อความ Log ในวันนี้';
  if (atBottom) consoleNode.scrollTop = consoleNode.scrollHeight;
}

function renderWorkspaceCleanup(cleanup = {}) {
  const panel = $('.cleanup-panel');
  if (!panel) return;
  const scanned = Boolean(cleanup.scanned_at);
  const busy = Boolean(cleanup.busy);
  const active = Boolean(cleanup.automation_active);
  const count = Number(cleanup.file_count || 0);
  panel.classList.toggle('cleaning', busy);
  $('#cleanup-size').textContent = busy ? 'กำลังเคลียร์…' : scanned ? formatBytes(cleanup.size_bytes) : 'ยังไม่ได้สแกน';
  const protectedJobs = Number(cleanup.invalid_final_jobs || 0) + Number(cleanup.recent_jobs || 0);
  $('#cleanup-summary').textContent = scanned
    ? (count ? `พบ ${count.toLocaleString('th-TH')} ไฟล์ที่สร้างใหม่ได้และลบอย่างปลอดภัย${protectedJobs ? ` • กันงานไว้ ${protectedJobs} งาน` : ''}` : 'พื้นที่สะอาดแล้ว ไม่พบไฟล์ขยะที่ต้องลบ')
    : 'กดสแกนเพื่อดูรายการที่ลบได้อย่างปลอดภัย';
  $('#cleanup-count').textContent = scanned ? count.toLocaleString('th-TH') : '—';
  $('#cleanup-jobs').textContent = scanned ? Number(cleanup.job_count || 0).toLocaleString('th-TH') : '—';
  $('#cleanup-protected').textContent = scanned ? Number(cleanup.protected_final_count || 0).toLocaleString('th-TH') : '—';
  $('#cleanup-categories').innerHTML = (cleanup.categories || []).map(category => {
    const categoryCount = Number(category.file_count || 0);
    return `<article class="cleanup-category ${categoryCount ? '' : 'empty'}"><span>${escapeHtml(category.label)}</span><b>${categoryCount.toLocaleString('th-TH')} ไฟล์ • ${formatBytes(category.size_bytes)}</b></article>`;
  }).join('');
  const status = $('#cleanup-status');
  status.classList.toggle('error', Boolean(cleanup.error));
  if (cleanup.error) status.textContent = cleanup.error;
  else if (busy) status.textContent = 'กำลังย้ายไฟล์ขยะลงถังขยะ Windows • กรุณาอย่าปิดโปรแกรม';
  else if (active) status.textContent = 'มีงานกำลังรัน • สแกนได้ แต่จะเคลียร์ได้หลังงานจบเท่านั้น';
  else if (cleanup.last_result?.finished_at) status.textContent = `เคลียร์ล่าสุด ${formatDate(cleanup.last_result.finished_at)} • คืนพื้นที่ ${formatBytes(cleanup.last_result.reclaimed_bytes)}`;
  else if (scanned) status.textContent = `สแกนล่าสุด ${formatDate(cleanup.scanned_at)} • ไฟล์จะย้ายลงถังขยะ Windows และกู้คืนได้`;
  else status.textContent = 'ยังไม่ได้สแกนพื้นที่';
  $('#cleanup-scan').disabled = busy;
  $('#cleanup-scan').textContent = busy ? 'กำลังดำเนินการ…' : 'สแกนไฟล์ขยะ';
  $('#cleanup-run').disabled = busy || active || !scanned || count === 0;
}

function applyCredentialState({saved, badge, input, connect, disconnect, savedPlaceholder, emptyPlaceholder}) {
  const badgeNode = $(badge), inputNode = $(input), connectNode = $(connect), disconnectNode = $(disconnect);
  badgeNode.textContent = saved ? '✓ เชื่อมต่อแล้ว' : '○ ยังไม่ได้เชื่อมต่อ';
  badgeNode.classList.toggle('connected', saved);
  badgeNode.classList.toggle('disconnected', !saved);
  inputNode.disabled = saved;
  inputNode.placeholder = saved ? savedPlaceholder : emptyPlaceholder;
  connectNode.hidden = saved;
  disconnectNode.hidden = !saved;
}

function renderTools(state) {
  const products = state.products || [];
  const voice = state.voice || {}, subtitle = state.subtitle || {}, audio = state.audio || {}, logo = state.logo || {}, queue = state.queue || {};
  for (const [selector, selectedValue] of [['#voice-job',voice.job_id],['#subtitle-job',subtitle.job_id],['#audio-job',audio.job_id],['#logo-job',logo.job_id]]) {
    const node = $(selector); if (!node) continue;
    const keep = selector === '#logo-job' ? (node.value || selectedValue || '') : (node.value || selectedValue || ui.selectedProductId);
    node.innerHTML = jobOptions(products, keep);
    if (selector === '#logo-job') node.innerHTML='<option value="">ใช้ภาพพื้นหลังตัวอย่าง</option>'+products.map(job=>`<option value="${escapeHtml(job.id)}">${escapeHtml(job.id)} • ${escapeHtml(job.title)}</option>`).join('');
    if ([...node.options].some(option => option.value === keep)) node.value = keep;
  }
  $('#voice-status').textContent = voice.status || 'พร้อมตั้งค่าเสียง';
  applyCredentialState({saved:Boolean(voice.key_saved),badge:'#voice-key-state',input:'#voice-key',connect:'#voice-save-key',disconnect:'#voice-delete-key',savedPlaceholder:'••••••••  API Key เก็บไว้ใน Windows แล้ว',emptyPlaceholder:'วาง API Key ใหม่ (โปรแกรมไม่ส่งกลับมาที่หน้าเว็บ)'});
  $('#voice-refresh-catalog').disabled = !voice.key_saved;
  $('#voice-catalog-info').textContent = voice.catalog_info || 'กดโหลดเสียงจากระบบ API';
  const catalogKeep = $('#voice-catalog').value || voice.catalog_choice;
  setSelectOptions('#voice-catalog', (voice.catalog || []).map(item => ({value:item.label,label:item.label})), catalogKeep);
  if (!$('#voice-catalog').options.length) $('#voice-catalog').innerHTML = '<option value="">กดโหลดรายการเสียง</option>';
  const dramaVoiceOptions = [{value:'',label:'ใช้เสียงหลักในหน้า AI Voice'}, ...(voice.catalog || []).map(item => ({value:item.reference_id,label:item.label}))];
  for (const selector of ['#drama-character-1-voice','#drama-character-2-voice','#drama-character-3-voice','#drama-character-4-voice']) {
    const node = $(selector); if (!node) continue;
    const selected = node.value;
    setSelectOptions(selector, selected&&!dramaVoiceOptions.some(item=>item.value===selected)
      ? [...dramaVoiceOptions,{value:selected,label:'เสียงที่เลือกไว้ไม่อยู่ในรายการ • ตรวจหน้า AI Voice'}]
      : dramaVoiceOptions, selected);
  }

  applyCredentialState({saved:Boolean(subtitle.credential_saved),badge:'#subtitle-token-state',input:'#subtitle-token',connect:'#subtitle-connect',disconnect:'#subtitle-delete-credential',savedPlaceholder:'••••••••  รหัสอุปกรณ์เก็บไว้ใน Windows แล้ว',emptyPlaceholder:'SOT-...'});
  $('#subtitle-credential').textContent = `${subtitle.credential_state || 'ยังไม่เชื่อมต่อ'}${subtitle.audio_label ? ` • ${subtitle.audio_label}` : ''}`;
  $('#subtitle-status').textContent = subtitle.status || 'ยังไม่พร้อมสร้าง Subtitle';
  setSelectOptions('#subtitle-theme', subtitle.themes || [], $('#subtitle-theme').value || subtitle.theme);
  setSelectOptions('#subtitle-animation', subtitle.animations || [], $('#subtitle-animation').value || subtitle.animation);
  setSelectOptions('#subtitle-font', subtitle.fonts || [], $('#subtitle-font').value || subtitle.font);
  renderSubtitlePreview(subtitle);

  $('#audio-status').textContent = audio.status || 'พร้อมผสมเสียง';
  window.SmartFlowMusic?.render(audio);
  setSelectOptions('#audio-background-file', audio.background_files || [], $('#audio-background-file').value || audio.background_file);
  setSelectOptions('#audio-sfx-file', audio.sfx_files || [], $('#audio-sfx-file').value || audio.sfx_file);
  $('#logo-status').textContent = logo.status || 'พร้อมตั้งค่าโลโก้';
  setSelectOptions('#logo-position', logo.positions || [], $('#logo-position').value || logo.position);
  ui.selectedLogoAssetId = logo.selected_asset_id || '';
  const logoLibrary = Array.isArray(logo.library) ? logo.library : [];
  const librarySignature = JSON.stringify(logoLibrary.map(item => [item.id,item.name,item.selected]));
  if ($('#logo-library').dataset.signature !== librarySignature) {
    $('#logo-library').dataset.signature = librarySignature;
    $('#logo-library').innerHTML = logoLibrary.length ? logoLibrary.map(item => `<button type="button" class="logo-library-item ${item.selected ? 'selected' : ''}" data-logo-asset="${escapeHtml(item.id)}" aria-pressed="${Boolean(item.selected)}"><span class="logo-library-thumb"><img src="${escapeHtml(item.url)}" alt="${escapeHtml(item.name)}"></span><span class="logo-library-copy"><b>${escapeHtml(item.name)}</b><small>${item.builtin ? 'มากับโปรแกรม' : 'อัปโหลดไว้ในเครื่อง'}</small></span><i>✓</i></button>`).join('') : '<div class="logo-library-empty">ยังไม่มีโลโก้ • กด “อัปโหลดโลโก้” เพื่อเพิ่มไฟล์แรก</div>';
  }
  $('#logo-selected-summary').innerHTML = logo.selected_name ? `<i>✓</i><span><b>เลือกแล้ว</b><small>${escapeHtml(logo.selected_name)}</small></span>` : 'ยังไม่ได้เลือกโลโก้';
  $('#logo-preview-name').textContent = logo.selected_name || 'โลโก้ที่เลือก';
  const logoPreviewToken = String(logo.preview_token || 0);
  if (!window.SmartFlowLogo && logo.preview_url && ($('#logo-preview').dataset.url !== logo.preview_url || $('#logo-preview').dataset.token !== logoPreviewToken)) {
    $('#logo-preview').dataset.url=logo.preview_url;
    $('#logo-preview').dataset.token=logoPreviewToken;
    $('#logo-preview').src=`${logo.preview_url}&v=${logoPreviewToken}`;
  }
  $('#queue-device').textContent = state.system.android_wifi?.message || state.system.android || 'ยังไม่พบโทรศัพท์ Android';
  $('#queue-table').innerHTML = (queue.items || []).length ? queue.items.map(item => `<tr><td>${escapeHtml(item.id)}</td><td class="job-cell">${escapeHtml(item.video_path)}</td><td>${escapeHtml(item.caption || '—')}</td><td>${escapeHtml(item.product || '—')}</td><td>${pill(item.status)}</td><td>${escapeHtml(item.last_step || '—')}</td></tr>`).join('') : '<tr><td colspan="6"><div class="empty-state">ยังไม่มีวิดีโอในคิวมือถือ</div></td></tr>';

  if (!ui.toolsHydrated) {
    $('#voice-reference-file').value=voice.reference_file || ''; $('#voice-reference-id').value=voice.reference_id || ''; $('#voice-language').value=voice.language || 'th'; $('#voice-emotion').value='normal'; $('#voice-speed').value='1'; $('#voice-silence').value=voice.silence || '0.3'; $('#voice-format').value=voice.format || 'mp3'; $('#voice-script').value=voice.script || '';
    $('#subtitle-language').value=subtitle.language || 'th'; $('#subtitle-syllables').value=String(subtitle.syllables || 3); $('#subtitle-auto').checked=Boolean(subtitle.auto); $('#subtitle-theme').value=subtitle.theme || ''; $('#subtitle-animation').value=subtitle.animation || ''; $('#subtitle-font').value=subtitle.font || ''; $('#subtitle-font-size').value=subtitle.font_size || 28; $('#subtitle-mark-gap').value=subtitle.thai_mark_gap ?? 14; $('#subtitle-outline').value=subtitle.outline_width ?? 2; $('#subtitle-y').value=subtitle.position_y ?? 90; $('#subtitle-text-color').value=subtitle.text_color || '#ffffff'; $('#subtitle-highlight-color').value=subtitle.highlight_color || '#facc15'; $('#subtitle-outline-color').value=subtitle.outline_color || '#101010'; $('#subtitle-background-enabled').checked=Boolean(subtitle.background_enabled); $('#subtitle-background-color').value=subtitle.background_color || '#000000'; $('#subtitle-background-opacity').value=subtitle.background_opacity ?? 45;
    $('#audio-background-enabled').checked=Boolean(audio.background_enabled); $('#audio-background-mode').value=audio.background_mode || 'อัตโนมัติ • ยำท่อนสั้น V2'; $('#audio-background-file').value=audio.background_file || 'สุ่มจากคลัง'; $('#audio-background-volume').value=audio.background_volume ?? 12; $('#audio-segment-max').value=audio.segment_max_sec ?? 12; $('#audio-duck-percent').value=audio.duck_percent ?? 38; $('#audio-sfx-enabled').checked=Boolean(audio.sfx_enabled); $('#audio-sfx-mode').value=audio.sfx_mode || 'อัตโนมัติ • เว้นจังหวะ'; $('#audio-sfx-file').value=audio.sfx_file || 'สุ่มจากคลัง'; $('#audio-sfx-volume').value=audio.sfx_volume ?? 22; $('#audio-sfx-interval').value=audio.sfx_interval ?? 6; $('#audio-sfx-count').value=audio.sfx_count ?? 6;
    $('#logo-file').value=logo.file || ''; ui.selectedLogoAssetId=logo.selected_asset_id || ''; $('#logo-opacity').value=logo.opacity ?? 80; $('#logo-size').value=logo.size ?? 18; $('#logo-position').value=logo.position || ''; $('#logo-margin').value=logo.margin ?? 28;
    ui.toolsHydrated=true;
  }
  updateToolLabels();
  window.SmartFlowLogo?.render(logo);
}

function updateToolLabels() {
  $('#subtitle-font-size-label').textContent=`${$('#subtitle-font-size').value} px`; $('#subtitle-mark-gap-label').textContent=`${$('#subtitle-mark-gap').value}%`; $('#subtitle-outline-label').textContent=$('#subtitle-outline').value; $('#subtitle-y-label').textContent=`${$('#subtitle-y').value}%`; $('#subtitle-background-opacity-label').textContent=`${$('#subtitle-background-opacity').value}%`;
  $('#audio-background-volume-label').textContent=`${$('#audio-background-volume').value}%`; $('#audio-segment-max-label').textContent=`${$('#audio-segment-max').value} วินาที`; $('#audio-duck-percent-label').textContent=`${$('#audio-duck-percent').value}%`; $('#audio-sfx-volume-label').textContent=`${$('#audio-sfx-volume').value}%`;
  $('#logo-opacity-label').textContent=`${$('#logo-opacity').value}%`; $('#logo-size-label').textContent=`${$('#logo-size').value}%`; $('#logo-margin-label').textContent=`${$('#logo-margin').value}px`;
  applySubtitlePreviewMode(ui.subtitlePreviewMode);
}

function applySubtitlePreviewMode(mode = 'detail') {
  const frame = $('#subtitle-live-preview');
  if (!frame) return;
  const selectedMode = mode === 'frame' ? 'frame' : 'detail';
  const positionY = Math.max(5, Math.min(95, Number($('#subtitle-y')?.value || 50)));
  ui.subtitlePreviewMode = selectedMode;
  frame.dataset.mode = selectedMode;
  for (const media of [$('#subtitle-preview-video'), $('#subtitle-preview-image')]) {
    if (media) media.style.objectPosition = `50% ${positionY}%`;
  }
  for (const button of document.querySelectorAll('[data-subtitle-preview-mode]')) {
    const active = button.dataset.subtitlePreviewMode === selectedMode;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', String(active));
  }
  const badge = $('#subtitle-preview-focus-badge');
  if (badge) badge.textContent = selectedMode === 'detail'
    ? `ซูมจุดวางข้อความ • ตำแหน่ง ${positionY}% ตามจริง`
    : 'เต็มเฟรมวิดีโอ Shorts • 9:16';
}

function mountStoryStylePickers(styles = []) {
  for (const prefix of ['story', 'story-batch', 'drama']) {
    const anchor = $(`#${prefix}-model`)?.closest('.field');
    if (!anchor || $(`#${prefix}-visual-style`)) continue;
    const section = document.createElement('section');
    section.className = 'visual-style-card';
    section.innerHTML = `<label class="field"><span>สไตล์ภาพ</span><select id="${prefix}-visual-style" aria-describedby="${prefix}-style-description">${styles.map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join('')}</select></label><p id="${prefix}-style-description" class="visual-style-description" aria-live="polite"></p><details><summary>แนวภาพเพิ่มเติม</summary><label class="field"><span>โทนสี แสง หรือบรรยากาศ</span><textarea id="${prefix}-visual-style-custom" maxlength="400" rows="2" placeholder="เช่น แสงยามเย็น โทนอุ่น บรรยากาศชนบท"></textarea><small>ใช้กับทุกฉาก • สูงสุด 400 ตัวอักษร</small></label></details>`;
    anchor.after(section);
    const update = () => {
      const value = $(`#${prefix}-visual-style`).value;
      section.dataset.style = value;
      $(`#${prefix}-style-description`).textContent = (styles.find(item => item.value === value)?.description || '') + ' • เปลี่ยนเฉพาะวิธีวาด ไม่เปลี่ยนตัวละครหรือเนื้อเรื่อง • บันทึกติดกับงาน';
      const custom = value === 'custom';
      $(`#${prefix}-visual-style-custom`).required = custom;
      if (custom) $('details', section).open = true;
    };
    $(`#${prefix}-visual-style`).addEventListener('change', update); update();
  }
}

function storyStylePayload(prefix) {
  return {visual_style:$(`#${prefix}-visual-style`)?.value || 'auto', visual_style_custom:$(`#${prefix}-visual-style-custom`)?.value.trim() || ''};
}

function hydrateForms(state) {
  mountStoryStylePickers(state.story_visual_styles || [{value:'auto',label:'ตามเนื้อเรื่อง',description:'ใช้แนวภาพเดียวกันทั้งเรื่อง'}]);
  if (!ui.formsHydrated) {
    $('#product-provider').value = state.settings.provider;
    $('#product-video-provider').value = 'flow';
    $('#story-provider').value = state.settings.provider;
    $('#drama-provider').value = state.settings.provider;
    $('#story-batch-provider').value = state.settings.provider;
    fillAiModelSelect('#product-provider','#product-model');
    fillAiModelSelect('#story-provider','#story-model');
    fillAiModelSelect('#drama-provider','#drama-model');
    fillAiModelSelect('#story-batch-provider','#story-batch-model');
    if(!window.hydrateMediaAudioDefaults)$('#product-subtitle').checked = state.settings.subtitle_auto;
    ui.formsHydrated = true;
  }
  window.hydrateMediaAudioDefaults?.(state.settings);
  if (!ui.settingsHydrated) {
    $('#setting-provider').value = state.settings.provider;
    const chatgptOptions = [{value:'auto', label:'ใช้โมเดลปัจจุบัน'}, ...aiModelOptions('chatgpt').filter(item => item.value !== 'auto')];
    const geminiOptions = aiModelOptions('gemini');
    $('#setting-chatgpt-model').innerHTML = chatgptOptions.map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join('');
    $('#setting-gemini-model').innerHTML = geminiOptions.map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join('');
    $('#setting-chatgpt-model').value = 'auto';
    $('#setting-chatgpt-model').disabled = true;
    $('#setting-gemini-model').value = savedAiModel('gemini');
    $('#setting-video-provider').value = 'flow';
    $('#setting-resolution').value = state.settings.video_resolution;
    $('#setting-fps').value = String(state.settings.video_fps);
    $('#setting-encoder').value = state.settings.video_encoder || 'auto';
    $('#setting-quality').value = state.settings.video_quality;
    $('#setting-motion').value = state.settings.motion_percent;
    $('#setting-transition').value = state.settings.transition_ms;
    $('#setting-subtitle').checked = state.settings.subtitle_auto;
    updateRangeLabels();
    ui.settingsHydrated = true;
  }
}

function updateRangeLabels() {
  $('#story-scene-label').textContent = `${$('#story-scenes').value} ฉาก`;
  $('#drama-episode-label').textContent = `${$('#drama-episodes').value} EP`;
  $('#drama-scene-label').textContent = `${$('#drama-scenes').value} ฉาก`;
  renderDramaPlotBoard();
  $('#motion-label').textContent = `${$('#setting-motion').value}%`;
  $('#transition-label').textContent = `${$('#setting-transition').value} ms`;
}

function updateCreationAvailability() {
  const productInput = $('#product-link');
  const productValue = productInput?.value.trim() || '';
  const productValid = /^https?:\/\/(?:[^/]+\.)?shopee\.co\.th(?:\/|$)/i.test(productValue);
  const rules = [
    ['#create-product', productValid, productValue ? 'ลิงก์นี้ไม่ใช่ Shopee' : 'วางลิงก์ Shopee ก่อนเริ่มสร้าง'],
    ['#create-story', Boolean($('#story-topic')?.value.trim()), 'ใส่หัวข้อเรื่องก่อนเริ่มสร้าง'],
    ['#create-drama-series', Boolean($('#drama-title')?.value.trim()), 'ใส่ชื่อเรื่องละครก่อนเริ่มสร้าง'],
  ];
  rules.forEach(([selector, ready, reason]) => {
    const button = $(selector); if (!button || button.dataset.busy) return;
    button.disabled = !ready;
    button.setAttribute('aria-disabled', String(!ready));
    if (!ready) button.title = reason; else button.removeAttribute('title');
  });
  const validation = [
    [productInput, $('#product-link-error'), productValid],
    [$('#story-topic'), $('#story-topic-error'), Boolean($('#story-topic')?.value.trim())],
    [$('#drama-title'), $('#drama-title-error'), Boolean($('#drama-title')?.value.trim())],
  ];
  validation.forEach(([input,error,valid]) => {
    if (!input || !error) return;
    const show = !valid && (input.dataset.touched === 'true' || Boolean(input.value.trim()));
    input.setAttribute('aria-invalid', String(show));
    error.hidden = !show;
  });
}

function updateStoryVideoMode() {
  if ($('#story-video-mode').value === 'meta_ai') {
    $('#story-video-mode-note').textContent='Meta AI รุ่นทดลอง • สร้างคลิปแนวตั้งจากภาพทีละฉาก • เลือกเสียงต้นฉบับจากคลิป เสียง API หรือไม่มีเสียง • ต้องเข้าสู่ระบบ Meta ใน Chrome';
    $('#story-video-mode-feature').textContent='✓ ตรวจไฟล์ Meta ทุกฉาก บันทึกแล้วจึงปิดแท็บและประกอบคลิป';
    return;
  }
  const flow = $('#story-video-mode').value === 'google_flow';
  $('#story-video-mode-note').textContent = flow
    ? `สร้างภาพให้ครบก่อน แล้วส่ง Google Flow ทีละฉาก • ใช้เครดิตสูงสุด ${Number($('#story-scenes').value || 10)} ครั้ง`
    : 'รวดเร็ว ประกอบภาพด้วย Motion และ Transition ในเครื่อง';
  $('#story-video-mode-feature').textContent = flow
    ? '✓ ส่งภาพเข้า Google Flow ทีละฉากและบันทึก Checkpoint'
    : '✓ ประกอบภาพเป็นคลิปในเครื่อง';
}

function progressSteps(type, percent, current = {}) {
  if(current.pipeline_phase){
    const phases=[['images','ภาพพร้อม'],...(current.source_video_required||current.pipeline_phase==='source_video'?[['source_video','สร้างวิดีโอ']]:[]),...(current.audio_mode==='api'?[['voice','เสียง SmartSub']]:[]),['compose','ประกอบคลิป'],['finish','ซับ / ตกแต่ง'],['cover','ปก / บันทึก']];
    const at=phases.findIndex(([phase])=>phase===current.pipeline_phase);
    if(at>=0)return phases.map(([_,label],i)=>`<span class="progress-step ${i<at?'done':i===at?'current':''}">${i<at?'✓ ':''}${label}</span>`).join('');
  }
  if(current.stage==='finishing'&&current.scene_total&&current.scenes_complete===current.scene_total){return `<span class="progress-step done">✓ ครบ ${Number(current.scene_total)} ฉาก</span><span class="progress-step ${percent>=100?'done':'current'}">Final / ปกคลิป</span>`;}
  if(current.stage==='scene'){
    const n=Number(current.scene_index||1),total=Number(current.scene_total||0),done=Number(current.scenes_complete||0);
    const phase=current.scene_phase;
    if(phase==='repair')return `<span class="progress-step">ครบ ${done}/${total} ฉาก</span><span class="progress-step current">ฉาก ${n} • ภาพทดแทน / พรอมต์ใหม่</span><span class="progress-step">Google Flow</span><span class="progress-step">Final</span>`;
    const parts=[['สร้างภาพ',phase==='image'],['วิดีโอ',phase==='requested'||phase==='video'],['เสียง/ประกอบฉาก',phase==='voice']];
    return `<span class="progress-step">ครบ ${done}/${total} ฉาก</span>`+parts.map(([label,active])=>`<span class="progress-step ${active?'current':''}">ฉาก ${n} • ${label}</span>`).join('')+'<span class="progress-step">Final</span>';
  }
  const product = [['รับสินค้า',0,8],['สร้างภาพ',8,38],['วิดีโอ AI ×3',38,68],['เสียง/ซับ',68,92],['Final',92,100]];
  const story = [['เขียนบท',0,12],['สร้างภาพ',12,60],['เสียงพากย์',60,80],['ประกอบฉาก',80,90],['Final',90,100]];
  return (type === 'product' ? product : story).map(([label,start,end]) => `<span class="progress-step ${percent >= end ? 'done' : percent >= start ? 'current' : ''}">${percent >= end ? '✓ ' : ''}${label}</span>`).join('');
}

function minimizeProgress() {
  ui.progressMinimized = true;
  clearTimeout(ui.progressCloseTimer); ui.progressCloseTimer = null;
  $('#progress-modal').close();
  $('#progress-minimized').classList.toggle('hidden', !ui.progressWasActive && !ui.progressResultReady);
}

function restoreProgress() {
  ui.progressMinimized = false;
  $('#progress-minimized').classList.add('hidden');
  if ((ui.progressWasActive || ui.progressResultReady) && !$('#progress-modal').open) $('#progress-modal').showModal();
}

function dismissProgressResult() {
  clearTimeout(ui.progressCloseTimer); ui.progressCloseTimer = null;
  ui.progressResultReady = false;
  $('#progress-modal').close();
  $('#progress-minimized').classList.add('hidden');
}

function renderProgress(state) {
  if (window.renderPresenterProgress?.(state)) return;
  $('#progress-modal').classList.remove('presenter-running');
  $('#progress-copy-log')?.classList.add('hidden');
  $('#progress-result').textContent = 'เปิดผลงานในคลัง';
  const product = state.product_progress;
  const story = state.story_progress;
  const current = product.active ? {...product,type:'product'} : story.active ? {...story,type:'story'} : null;
  const modal = $('#progress-modal');
  if (!current) {
    // A finished result must belong to the Job this popup was following.
    // A previous Product at 100% cannot finish a cancelled Story (or vice versa).
    const last = ui.progressType === 'product' ? product : story;
    const completed = ui.progressWasActive && ui.progressJobId && last.job_id === ui.progressJobId && last.percent >= 100
      ? {...last, type:ui.progressType} : null;
    if (completed) {
      // Final desktop completion, not an Extension scene/image "complete".
      // Remove both full/minimized UI immediately. No delayed close callback
      // may survive to dismiss the next queue item; results stay in Library.
      dismissProgressResult();
    } else if (ui.progressWasActive) {
      dismissProgressResult();
      ui.progressType = ''; ui.progressJobId = '';
    }
    $('#progress-minimized').classList.toggle('hidden', !ui.progressMinimized || !ui.progressResultReady);
    if (ui.progressWasActive) {
      const status = state.system.status || 'งานหยุดทำงานแล้ว';
      toast(status, /สำเร็จ|พร้อม/.test(status) ? 'success' : 'info');
    }
    ui.progressWasActive = false;
    return;
  }
  if (ui.progressCloseTimer) { clearTimeout(ui.progressCloseTimer); ui.progressCloseTimer=null; }
  ui.progressWasActive = true; ui.progressType = current.type; ui.progressJobId = current.job_id || '';
  ui.progressResultReady = false;
  $('#progress-result').classList.add('hidden');
  $('#progress-cancel').classList.remove('hidden');
  $('#progress-minimized')?.classList.toggle('hidden', !ui.progressMinimized);
  $('#progress-minimized').textContent = `● ${Math.max(0, Math.min(100, Number(current.percent || 0)))}% • ${current.message || 'กำลังทำงาน'} • เปิดรายละเอียด`;
  $('#progress-minimized').setAttribute('aria-label', 'เปิดรายละเอียดงานที่กำลังทำ');
  const drama = current.type === 'story' && current.mode === 'drama_episode';
  $('#progress-kicker').textContent = current.type === 'product' ? 'SMARTFLOW • ONE-CLICK PRODUCT' : drama ? 'SMARTFLOW • AI DRAMA SERIES' : 'SMARTFLOW • STORY AUTOMATION';
  $('#progress-title').textContent = current.type === 'product' || current.content_kind==='product' ? 'กำลังสร้างคลิปสั้นสินค้า' : drama ? `กำลังสร้างละคร EP ${Number(current.episode_no || 1)}/${Number(current.episode_count || 1)}` : 'กำลังสร้าง Story Shorts';
  $('#progress-job').textContent = current.job_id || 'กำลังสร้าง Job';
  $('#progress-percent').textContent = `${current.percent}%`;
  $('#progress-percent').setAttribute('aria-valuenow', String(Math.max(0, Math.min(100, Number(current.percent || 0)))));
  $('#progress-bar').style.width = `${current.percent}%`;
  $('#progress-message').textContent = current.message;
  $('#progress-detail').textContent = current.detail;
  window.renderAutomationObservation?.(state, current);
  window.SmartFlowUX?.renderProgress(state, current);
  $('#progress-steps').innerHTML = progressSteps(current.type, current.percent, current);
  const cancelling = /กำลังหยุด|กำลังยกเลิก/.test(String(current.message || ''));
  $('#progress-cancel').disabled = cancelling;
  $('#progress-cancel').textContent = cancelling ? 'กำลังยกเลิก...' : 'ยกเลิกการทำงาน';
  $('#progress-focus').classList.toggle('hidden', !current.action_required);
  $('#progress-focus').textContent = current.action_button || (current.action_kind === 'login_required' ? 'เปิด Chrome เพื่อเข้าสู่ระบบ' : 'เปิด Chrome เพื่อยืนยัน');
  // Minimizing is a user choice, not a transient state to undo on heartbeat.
  if (ui.progressMinimized) { if (modal.open) modal.close(); }
  else if (!modal.open) modal.showModal();
}

function renderNotice(state) {
  const notice = state.notice || {};
  if (notice.at && notice.at !== ui.lastNoticeAt) {
    ui.lastNoticeAt = notice.at;
    toast(notice.message, notice.kind || 'info');
  }
}

function renderAutomationError(state) {
  const report = state.automation_error_log || {};
  const modal = $('#automation-error-modal');
  $('#automation-error-open').classList.toggle('hidden', !report.text);
  if (!report.at || !report.text) {
    ui.lastAutomationErrorAt = '';
    if (modal.open) modal.close();
    return;
  }
  const reportId = report.event_id || report.at;
  if (reportId === ui.lastAutomationErrorAt) return;
  ui.lastAutomationErrorAt = reportId;
  const context = `${report.job_id || ''} ${report.service || ''} ${report.message || ''}`;
  ui.automationErrorPage = /^PRESENTER-/i.test(String(report.job_id || '')) ? 'presenter'
    : /^STORY/i.test(String(report.job_id || '')) || /story|ละคร/i.test(context) ? 'story' : 'products';
  $('#automation-error-title').textContent = report.title || 'งานหยุดเพราะพบข้อผิดพลาด';
  $('#automation-error-message').textContent = `${report.job_id || 'Automation'} • ${report.message || 'พบข้อผิดพลาด'}`;
  $('#automation-error-log').textContent = report.text;
  if (report.kind === 'warning' && report.event_id) {
    // The same authenticated terminal can replay after an Extension or UI
    // reload. Remember identifiers only, never the reason or user log text.
    let seen = [];
    try { const saved = JSON.parse(sessionStorage.getItem('smartflow-flow-failure-notices') || '[]'); if (Array.isArray(saved)) seen = saved; } catch (_) {}
    if (seen.includes(report.event_id)) return;
    try { sessionStorage.setItem('smartflow-flow-failure-notices', JSON.stringify([...seen, report.event_id].slice(-128))); } catch (_) {}
    const activeJobs = [state.product_progress, state.story_progress, state.presenter_progress].filter(p => p?.active && p.job_id);
    if (activeJobs.length && !activeJobs.some(p => p.job_id === report.job_id)) return;
    if (ui.progressMinimized) toast(`${report.title} • ดูสาเหตุในระบบและ Log`, 'warning');
  }
  if (!modal.open && !ui.progressMinimized) modal.showModal();
}

function render(state) {
  const partial = Boolean(state.partial && ui.state);
  const previousActive = Boolean(ui.state?.product_progress?.active || ui.state?.story_progress?.active || ui.state?.presenter_progress?.active);
  ui.state = partial ? {
    ...ui.state,
    ...state,
    app:{...(ui.state.app || {}),...(state.app || {})},
    system:{...(ui.state.system || {}),...(state.system || {})},
    credits:{...(ui.state.credits || {}),...(state.credits || {})},
    product_progress:{...(ui.state.product_progress || {}),...(state.product_progress || {})},
    story_progress:{...(ui.state.story_progress || {}),...(state.story_progress || {})},
  } : state;
  state = ui.state;
  window.renderCreativeCatalog?.(state.creative_catalog);
  updateLongVideoCapability(state);
  window.renderAndroidWifi?.(state);
  window.renderCreationQueue?.(state);
  window.renderProductContinue?.(state);
  window.renderPresenter?.(state);
  updateFxMode();
  if (partial) {
    renderSystem(state);
    renderProgress(state);
    renderNotice(state); renderAutomationError(state);
    if (state.logs && ui.activePage === 'logs') renderLogs(state);
    window.renderStudio?.(state, true);
    const currentActive = Boolean(state.product_progress?.active || state.story_progress?.active || state.presenter_progress?.active);
    if (previousActive && !currentActive) setTimeout(() => poll(true), 120);
    return;
  }
  hydrateForms(state);
  renderSystem(state); renderWorkspaceIssues(state.workspace_issues); renderProducts(state.products); renderStories(state.stories, state.story_progress || {}); renderDramaSeries(state.drama_series || {}, state.story_progress || {}); renderLibrary(state.library); renderGuide(state); renderLogs(state); renderWorkspaceCleanup(state.workspace_cleanup || {}); renderTools(state); renderProgress(state); renderNotice(state); renderAutomationError(state);
  window.renderStudio?.(state);
}

async function poll(full = true) {
  if (ui.polling) { ui.pendingFullPoll ||= full; return; }
  ui.polling = true;
  try {
    render(await getState(!full));
    ui.lastPollAt = Date.now();
    ui.pollFailures = 0;
  } catch (error) {
    ui.pollFailures += 1;
    $('#top-live-text').textContent = ui.pollFailures >= 3 ? 'โปรแกรมเบื้องหลังหยุดตอบสนอง' : 'โปรแกรมเบื้องหลังกำลังยุ่ง';
    if (ui.pollFailures >= 3) $('#top-live-dot').classList.remove('ready');
    $('#footer-status').textContent = ui.pollFailures >= 3 ? error.message : 'กำลังรอระบบหลักตอบกลับ • โปรแกรมจะลองใหม่อัตโนมัติ';
  } finally {
    ui.polling = false;
    if (ui.pendingFullPoll) { ui.pendingFullPoll = false; queueMicrotask(() => poll(true)); }
  }
}

function libraryItem(itemId) { return ui.libraryDetail?.item_id === itemId ? ui.libraryDetail : (ui.state?.library || []).find(item => item.item_id === itemId); }
function productItem(jobId) { return (ui.state?.products || []).find(item => item.id === jobId); }
function currentProductJobId() { return $('#product-selected-job').value || ui.selectedProductId || ''; }

function openProductDetail(jobId) {
  const job=productItem(jobId); if(!job)return;
  ui.selectedProductId=jobId; $('#product-selected-job').value=jobId;
  $('#product-detail-id').value=job.id; $('#product-detail-title').textContent=job.title; $('#product-detail-name').value=job.title; $('#product-detail-product-id').value=job.product_id || ''; $('#product-detail-price').value=job.price || ''; $('#product-detail-commission').value=job.commission || ''; $('#product-detail-description').value=job.description || ''; $('#product-detail-caption').value=job.caption || '';
  const source = videoSourcePresentation(job);
  const sourceText = source.remote || source.local || source.sourceType ? ` • ${source.label}` : '';
  $('#product-detail-status').textContent=`AI ${job.ai_status} • อนุมัติ ${job.ai_review_status} • รูปต้นฉบับ ${job.source_image_count} • รูป AI ${job.generated_image_count}${sourceText} • ${job.ready ? 'พร้อมใช้' : 'ยังรอข้อมูล'}`;
  $('#product-detail-status').textContent += ` • ภาพอ้างอิงที่ใช้ ${job.reference_image_count ?? job.source_image_count} • คัดออก ${job.excluded_reference_count || 0} • ใช้ภาพเดิม ${job.reused_image_count || 0}`;
  const provider=$('#product-detail-video-provider');
  provider.value=job.video_ai_provider==='meta_ai'?'meta_ai':'flow';
  const active=[ui.state?.product_progress,ui.state?.story_progress].some(p=>p?.active&&p.job_id===jobId);
  provider.disabled=active||job.video_status==='ready'||job.automation_status==='running';
  $('#product-detail-provider-save').disabled=provider.disabled;
  $('#product-detail-modal').showModal();
}

function subtitlePayload() { return {job_id:$('#subtitle-job').value,language:$('#subtitle-language').value,syllables:Number($('#subtitle-syllables').value),auto:$('#subtitle-auto').checked,theme:$('#subtitle-theme').value,animation:$('#subtitle-animation').value,font:$('#subtitle-font').value,font_size:Number($('#subtitle-font-size').value),thai_mark_gap:Number($('#subtitle-mark-gap').value),outline_width:Number($('#subtitle-outline').value),position_y:Number($('#subtitle-y').value),text_color:$('#subtitle-text-color').value,highlight_color:$('#subtitle-highlight-color').value,outline_color:$('#subtitle-outline-color').value,background_enabled:$('#subtitle-background-enabled').checked,background_color:$('#subtitle-background-color').value,background_opacity:Number($('#subtitle-background-opacity').value)}; }
function renderSubtitlePreview(subtitle) {
  const token = Number(subtitle.preview_ready_token ?? subtitle.preview_token ?? 0);
  const video = $('#subtitle-preview-video'), image = $('#subtitle-preview-image'), state = $('#subtitle-preview-state');
  // A delayed full snapshot must not replace a newer preview with an older one.
  if (Number(subtitle.preview_token || 0) < Number(ui.subtitlePreviewLatestToken || 0)) return;
  if (token < Number(video.dataset.token || 0)) return;
  ui.subtitlePreviewLatestToken = Number(subtitle.preview_token || 0);
  if (subtitle.preview_url && Number(image.dataset.token || 0) !== token) {
    image.dataset.token = String(token); image.src = subtitle.preview_url;
  }
  if (subtitle.preview_video_url && Number(video.dataset.token || 0) !== token) {
    video.dataset.token = String(token);
    video.oncanplay = () => {
      video.hidden = false; image.hidden = true;
      video.play().catch(() => { video.hidden = true; image.hidden = false; });
    };
    video.onerror = () => { video.hidden = true; image.hidden = !subtitle.preview_url; };
    video.src = subtitle.preview_video_url; video.load();
  }
  state.classList.toggle('error', Boolean(subtitle.preview_error));
  state.hidden = Boolean(subtitle.preview_video_url || subtitle.preview_url) && !subtitle.preview_busy && !subtitle.preview_error;
  $('#subtitle-live-preview').setAttribute('aria-busy', String(Boolean(subtitle.preview_busy)));
  $('span', state).textContent = subtitle.preview_error ? `พรีวิวไม่สำเร็จ • ${subtitle.preview_error}` : 'กำลังอัปเดตพรีวิว…';
  $('#subtitle-preview-meta').textContent = subtitle.preview_status || 'พรีวิวจริง • บันทึกเพื่อใช้กับวิดีโอ';
  applySubtitlePreviewMode(ui.subtitlePreviewMode);
}

function hydrateSubtitlePreviewStyle(style) {
  const fields = {font:'font',font_size:'font-size',thai_mark_gap:'mark-gap',outline_width:'outline',position_y:'y',text_color:'text-color',highlight_color:'highlight-color',outline_color:'outline-color',background_color:'background-color',background_opacity:'background-opacity'};
  for (const [key, suffix] of Object.entries(fields)) if (style[key] != null) $(`#subtitle-${suffix}`).value = style[key];
  $('#subtitle-background-enabled').checked = Boolean(style.background_enabled);
  updateToolLabels();
}

async function waitSubtitlePreview(sequence, expectedToken, applyTheme = false) {
  const deadline = Date.now() + 20000;
  while (sequence === ui.subtitlePreviewSequence && Date.now() < deadline) {
    const response = await fetch('/api/desktop/state?mode=subtitle_preview', {cache:'no-store'});
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'อ่านสถานะพรีวิวไม่สำเร็จ');
    if (sequence !== ui.subtitlePreviewSequence) return;
    const preview = data.subtitle_preview;
    if (!preview || Number(preview.preview_token) < Number(expectedToken)) {
      await new Promise(resolve => setTimeout(resolve, 180)); continue;
    }
    if (applyTheme) { hydrateSubtitlePreviewStyle(preview.style || {}); applyTheme = false; }
    renderSubtitlePreview(preview);
    if (!preview.preview_busy) return;
    await new Promise(resolve => setTimeout(resolve, 180));
  }
  if (sequence === ui.subtitlePreviewSequence) throw new Error('พรีวิวใช้เวลานาน • ลองปรับค่าอีกครั้ง ไฟล์งานเดิมยังอยู่');
}

function scheduleSubtitlePreview({applyTheme=false, immediate=false} = {}) {
  clearTimeout(ui.subtitlePreviewTimer);
  const sequence = ++ui.subtitlePreviewSequence;
  const stateNode = $('#subtitle-preview-state');
  stateNode.hidden = false;
  stateNode.classList.remove('error');
  $('span', stateNode).textContent = 'กำลังเรนเดอร์พรีวิวจริง…';
  ui.subtitlePreviewTimer = setTimeout(async () => {
    try {
      const result = await postAction('subtitle_preview_style', {...subtitlePayload(), apply_theme:applyTheme});
      if (sequence !== ui.subtitlePreviewSequence) return;
      await waitSubtitlePreview(sequence, result.preview_token, applyTheme);
    } catch(error) {
      if (sequence !== ui.subtitlePreviewSequence) return;
      stateNode.hidden = false;
      stateNode.classList.add('error');
      $('span', stateNode).textContent = error.message;
    }
  }, immediate ? 0 : 360);
}
function audioPayload() { return {...(window.SmartFlowMusic?.payload() || {}),job_id:$('#audio-job').value,background_enabled:$('#audio-background-enabled').checked,background_mode:$('#audio-background-mode').value,background_file:$('#audio-background-file').value,background_volume:Number($('#audio-background-volume').value),segment_max_sec:Number($('#audio-segment-max').value),duck_percent:Number($('#audio-duck-percent').value),sfx_enabled:$('#audio-sfx-enabled').checked,sfx_mode:$('#audio-sfx-mode').value,sfx_file:$('#audio-sfx-file').value,sfx_volume:Number($('#audio-sfx-volume').value),sfx_interval:Number($('#audio-sfx-interval').value),sfx_count:Number($('#audio-sfx-count').value)}; }
function logoPayload() { return {job_id:$('#logo-job').value,asset_id:ui.selectedLogoAssetId,file:$('#logo-file').value,opacity:Number($('#logo-opacity').value),size:Number($('#logo-size').value),position:$('#logo-position').value,margin:Number($('#logo-margin').value),...(window.SmartFlowLogo?.payload()||{})}; }
function copyText(text) {
  const value = String(text || '');
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(value).then(() => toast('คัดลอกแล้ว', 'success'));
  const area = document.createElement('textarea'); area.value = value; document.body.append(area); area.select(); document.execCommand('copy'); area.remove(); toast('คัดลอกแล้ว', 'success');
}

function openConfirm(title, message, confirmAction, acceptLabel = 'ย้ายลงถังขยะ') {
  $('#confirm-title').textContent = title;
  $('#confirm-message').textContent = message;
  $('#confirm-accept').textContent = acceptLabel;
  ui.confirmAction = confirmAction;
  $('#confirm-modal').showModal();
}

async function openDetail(itemId) {
  const ticket = ++ui.libraryDetailTicket;
  let item = libraryItem(itemId); if (!item) return;
  const content = $('#detail-content');
  content.querySelector('video')?.pause();
  content.dataset.itemId = itemId;
  content.innerHTML = '<p role="status" class="empty-state">กำลังอ่านรายละเอียดคลิป…</p>';
  $('#detail-modal').showModal();
  try {
    const result = await postAction('get_library_detail', {item_id: itemId});
    if (ticket !== ui.libraryDetailTicket || !$('#detail-modal').open) return;
    item = result.detail;
    ui.libraryDetail = item;
  } catch (error) { if (ticket === ui.libraryDetailTicket) { $('#detail-modal').close(); toast(error.message, 'error'); } return; }
  const coverUrl = item.cover_url || item.preview_url || '';
  const videoUrl = item.video_url || '';
  const hasDedicatedCover = Boolean(item.cover_url);
  const coverLabel = item.aspect_ratio === '16:9' ? 'คลิปยาวแนวนอน 16:9' : 'วิดีโอ Final แนวตั้ง 9:16';
  content.classList.toggle('landscape-result', item.aspect_ratio === '16:9');
  const coverNote = videoUrl ? 'กดเล่นและตรวจผลงานได้ในโปรแกรม โดยไม่ต้องเปิดหน้าต่างอื่น' : 'ไม่พบไฟล์วิดีโอสำหรับเล่นในโปรแกรม';
  const source = videoSourcePresentation(item);
  const fields = [
    ['ชื่อวิดีโอ', item.title || '—', 'title'],
    ['แหล่งวิดีโอ', source.label, 'video_source_label'],
    ['คำอธิบาย / แคปชั่น', item.description || '—', 'description'],
    ['แฮชแท็ก', item.hashtags || '—', 'hashtags'],
    ['ลิงก์สินค้านายหน้า', item.affiliate_link || 'ไม่มีลิงก์สำหรับผลงานนี้', 'affiliate_link'],
  ];
  const media = videoUrl
    ? `<video class="detail-video" controls playsinline preload="metadata" ${coverUrl ? `poster="${escapeHtml(coverUrl)}"` : ''}><source src="${escapeHtml(videoUrl)}" type="video/mp4">โปรแกรมไม่สามารถเล่นไฟล์นี้ในหน้าต่างได้</video>`
    : coverUrl ? `<img src="${escapeHtml(coverUrl)}" alt="ภาพตัวอย่าง ${escapeHtml(item.title)}">` : '<div class="detail-cover-empty">ยังไม่มีวิดีโอ Final</div>';
  content.innerHTML = `<div class="detail-layout"><section class="detail-cover-panel"><header><div><span>${coverLabel}</span><b>${item.aspect_ratio === '16:9' ? '16:9' : '9:16'}</b></div><small>${coverNote}</small></header><div class="detail-preview">${media}</div>${hasDedicatedCover ? `<button class="button secondary detail-cover-button" data-detail-cover="${escapeHtml(item.item_id)}">▣ เปิดดูปกคลิป${item.aspect_ratio === '16:9' ? 'ยาว' : ' Shorts'}เต็ม</button>` : ''}</section><div class="detail-info"><span>${escapeHtml(item.kind_label)}${Number(item.episode_no || 0) ? ` • EP ${Number(item.episode_no)}` : ''}</span><h2>${escapeHtml(item.title)}</h2>${fields.map(([label,value,key]) => `<section class="detail-field"><header><span>${label}</span><button class="copy-button" data-copy-key="${key}">คัดลอก</button></header><p>${escapeHtml(value)}</p></section>`).join('')}<div class="detail-actions"><button class="button primary" data-copy-key="post_text">คัดลอกข้อมูลโพสต์ทั้งหมด</button>${item.kind === 'story' ? `<button class="button secondary" data-edit-post-copy="${escapeHtml(item.item_id)}">แก้ข้อความโพสต์</button>` : ''}<button class="button secondary" data-detail-folder="${escapeHtml(item.item_id)}">เปิดโฟลเดอร์</button><button class="button ghost" data-detail-play="${escapeHtml(item.item_id)}">↗ เปิดวิดีโอภายนอก</button><button class="button danger" data-detail-delete-video="${escapeHtml(item.item_id)}">ลบเฉพาะวิดีโอ</button><button class="button danger" data-detail-delete-project="${escapeHtml(item.item_id)}">ลบโปรเจกต์</button></div></div></div>`;
  content.dataset.itemId = item.item_id;
  if ((item.content_kind || item.kind) === 'product' && item.affiliate_link) {
    const shopee = document.createElement('button');
    shopee.type = 'button'; shopee.className = 'button primary'; shopee.textContent = 'ส่งคลิปนี้ไปคิว Shopee';
    shopee.onclick = async () => {
      try {
        await postAction('shopee_post_add', {item_ids:[item.item_id]});
        $('#detail-content video')?.pause(); $('#detail-modal').close(); showPage('queue');
        window.SmartFlowShopee?.refresh();
      } catch (error) { toast(error.message, 'error'); }
    };
    content.querySelector('.detail-actions').prepend(shopee);
  }
  const editCover = document.createElement('button');
  editCover.type = 'button';
  editCover.className = 'button secondary detail-cover-button';
  editCover.textContent = '✦ แก้ไขปกคลิป';
  editCover.onclick = () => {
    $('#detail-content video')?.pause();
    $('#detail-modal').close();
    window.libraryView?.returnFromCover(item.item_id);
    window.openClipCover?.(item.item_id);
  };
  content.querySelector('.detail-cover-panel').append(editCover);
  window.libraryView?.decorateDetail(content, item);
  $('#detail-modal').showModal();
}

function askDelete(mode, itemId) {
  const item = libraryItem(itemId); if (!item) return;
  const isProject = mode === 'project';
  const message = isProject
    ? `ระบบจะย้ายทั้ง Job “${item.title}” พร้อมรูป บท เสียง ซับ และวิดีโอ ลงถังขยะ Windows และนำแถวออกจากโปรแกรม`
    : `ระบบจะย้ายเฉพาะไฟล์วิดีโอของ “${item.title}” ลงถังขยะ Windows โดยเก็บรูป บท เสียง และข้อมูล Job ไว้`;
  openConfirm(isProject ? 'ลบโปรเจกต์นี้?' : 'ลบเฉพาะวิดีโอหัวข้อนี้?', message, {mode,itemId});
}

function openPostCopyEditor(itemId) {
  const item = libraryItem(itemId);
  if (!item || item.kind !== 'story' || !item.post_revision) return;
  const modal = $('#post-copy-modal');
  modal.dataset.itemId = itemId;
  modal.dataset.revision = item.post_revision;
  $('#post-copy-description').value = item.description || '';
  $('#post-copy-hashtags').value = item.hashtags || '';
  $('#detail-content video')?.pause();
  $('#detail-modal').close();
  modal.showModal();
  $('#post-copy-description').focus();
}

// Capture delegated controls before a WebView/browser overlay can stop bubbling.
document.addEventListener('click', async event => {
  event.smartflowDelegated = true;
  const newJobToggle = event.target.closest('#new-job-toggle');
  if (newJobToggle) {
    setNewJobMenu($('#new-job-menu').hidden);
    return;
  }
  if (!event.target.closest('.new-job-launcher')) setNewJobMenu(false);
  // `body[data-page]` stores the active page for styling. A broad
  // `[data-page]` selector therefore swallowed every click in the app before
  // modal/library actions could run. Only interactive navigation controls are
  // valid page buttons.
  const pageButton = event.target.closest('button[data-page], a[data-page], [role="button"][data-page]');
  if (pageButton) { showPage(pageButton.dataset.page); return; }
  const library = event.target.closest('[data-library-id]');
  if (library) { openDetail(library.dataset.libraryId); return; }
  const openJob = event.target.closest('[data-open-job]');
  if (openJob) { try{await postAction('open_job',{job_id:openJob.dataset.openJob})}catch(e){toast(e.message,'error')} return; }
  const productDetail = event.target.closest('[data-product-detail]');
  if (productDetail) { openProductDetail(productDetail.dataset.productDetail); return; }
  const productTool = event.target.closest('[data-product-tool]');
  if (productTool) {
    const tool=productTool.dataset.productTool, jobId=currentProductJobId(), job=productItem(jobId);
    if(!jobId){toast('กรุณาเลือก Product Job','error');return}
    if(tool==='edit'){openProductDetail(jobId);return}
    if(tool==='delete_project'){openConfirm('ลบโปรเจกต์สินค้านี้?',`รูป บท เสียง ซับ วิดีโอ และแถว ${jobId} จะถูกย้ายลงถังขยะ Windows`,{mode:'product_project',jobId});return}
    if(tool==='delete_all_products'){openConfirm('ลบ Product Job ทั้งหมด?','ทุกแถวสินค้าและโฟลเดอร์ Product Job จะถูกย้ายลงถังขยะ Windows แต่ยังกู้คืนได้',{mode:'all_products'});return}
    try{if(tool==='add_images')await postAction('product_add_images',{job_id:jobId});else if(tool==='add_video')await postAction('product_add_video',{job_id:jobId});else await postAction('product_tool',{job_id:jobId,tool});toast('รับคำสั่งแล้ว','success');ui.toolsHydrated=false;await poll()}catch(e){toast(e.message,'error')}return;
  }
  const openSeries = event.target.closest('[data-open-series]');
  if (openSeries) { openDramaProject(openSeries.dataset.openSeries); return; }
  const cancelDrama = event.target.closest('[data-cancel-drama-series]');
  if (cancelDrama) {
    const seriesId = cancelDrama.dataset.cancelDramaSeries;
    const title = cancelDrama.dataset.seriesTitle || 'ละครสั้น';
    openConfirm(
      `ยกเลิกคิว “${title}”?`,
      'ระบบจะหยุด EP ที่กำลังทำและยกเลิก EP ที่ยังรอหรือล้มเหลว โดยเก็บวิดีโอ รูป เสียง และไฟล์ของ EP ที่ทำเสร็จแล้วไว้ครบ จากนั้นคุณสามารถสร้างละครเรื่องใหม่ได้ทันที',
      {mode:'cancel_drama_series',seriesId},
      'ยกเลิกคิวนี้',
    );
    return;
  }
  const openSeriesFolder = event.target.closest('[data-open-series-folder]');
  if (openSeriesFolder) { try { await postAction('open_drama_series_folder',{series_id:openSeriesFolder.dataset.openSeriesFolder}); } catch(e) { toast(e.message,'error'); } return; }
  const startDrama = event.target.closest('[data-start-drama-series]');
  if (startDrama) {
    const seriesId = startDrama.dataset.startDramaSeries;
    if (dramaSeriesPending.has(seriesId)) return;
    dramaSeriesPending.add(seriesId);
    startDrama.disabled = true;
    try {
      await postAction('creation_start_series', {series_id:seriesId});
      $('#drama-project-modal')?.close();
      toast('เริ่มทำเฉพาะซีรีส์นี้ • เก็บตอนที่เสร็จแล้ว • งานอื่นยังอยู่ในคิว', 'success');
      await poll();
    } catch (error) { toast(error.message, 'error'); }
    finally {
      dramaSeriesPending.delete(seriesId);
      startDrama.disabled = false;
      renderDramaSeries(ui.state?.drama_series || {}, ui.state?.story_progress || {});
    }
    return;
  }
  const retryDrama = event.target.closest('[data-retry-drama-episode]');
  if (retryDrama) {
    retryDrama.disabled = true;
    try {
      await postAction('retry_drama_episode',{series_id:retryDrama.dataset.seriesId,episode_no:Number(retryDrama.dataset.retryDramaEpisode)});
      $('#drama-project-modal')?.close();
      toast(`กำลังกู้ EP ${Number(retryDrama.dataset.retryDramaEpisode)} ก่อนทำตอนถัดไป`, 'success');
      await poll();
    } catch(error) { toast(error.message,'error'); retryDrama.disabled=false; }
    return;
  }
  const continueSeries = event.target.closest('[data-continue-series]');
  if (continueSeries) {
    const series = (ui.state?.drama_series?.items || []).find(item => item.id === continueSeries.dataset.continueSeries);
    if (!series) { toast('ไม่พบโปรเจกต์ซีรีส์', 'error'); return; }
    ui.continueSeriesId = series.id;
    $('#drama-continue-series-id').value = series.id;
    $('#drama-continue-summary').textContent = `${series.title} • ตอนล่าสุด EP ${Number(series.episode_count || 0)} • ตอนใหม่จะใช้ตัวละครและเหตุการณ์เดิมทั้งหมด`;
    $('#drama-continue-provider').value = series.last_successful_provider || series.provider || 'chatgpt';
    $('#drama-continue-provider-label').textContent = providerLabel(series.last_successful_provider || series.provider);
    $('#drama-continue-scenes').value = String(series.scene_count || 10);
    $('#drama-continue-prompt').value = '';
    $('#drama-project-modal')?.close();
    $('#drama-continue-modal').showModal();
    $('#drama-continue-prompt').focus();
    return;
  }
  const adoptMeta = event.target.closest('[data-adopt-meta-sequence]');
  if (adoptMeta) {
    openConfirm('เปลี่ยนงานนี้เป็นภาพ → วิดีโอทีละฉาก?',
      'เก็บภาพและคลิปเดิมไว้ ไม่เริ่มงานทันที หากมีคำขอเดิมค้างจะต้องตรวจผลเดิมก่อนเปลี่ยน', async () => {
        adoptMeta.disabled = true;
        try {
          await postAction('adopt_meta_scene_sequence', {job_id: adoptMeta.dataset.adoptMetaSequence, confirmed: true});
          toast('เปลี่ยนลำดับแล้ว • กดทำต่อเมื่อพร้อม', 'success');
          await poll();
        } catch (error) { toast(error.message, 'error'); adoptMeta.disabled = false; }
      }, 'เปลี่ยนลำดับ');
    return;
  }
  const retryStory = event.target.closest('[data-retry-story]');
  if (retryStory) {
    retryStory.disabled = true;
    try {
      await postAction('retry_story', {job_id: retryStory.dataset.retryStory});
      $('#drama-project-modal')?.close();
      toast('กำลังทำต่อจาก Checkpoint เดิม', 'success');
      await poll();
    } catch (error) { toast(error.message, 'error'); retryStory.disabled = false; }
    return;
  }
  const dismissStory = event.target.closest('[data-dismiss-story]');
  if (event.target.closest('#story-recovery-clear')) { await clearStoryRecovery(); return; }
  if (dismissStory) {
    openConfirm(
      `ยกเลิกงาน “${dismissStory.dataset.storyTitle || 'Story Shorts'}”?`,
      'งานนี้จะหายจากรายการ “งานที่ต้องดำเนินการต่อ” แต่รูป บท เสียง และไฟล์ Checkpoint จะยังอยู่ในโฟลเดอร์เดิมและไม่ได้ถูกลบ',
      {mode:'dismiss_story',jobId:dismissStory.dataset.dismissStory},
      'ยกเลิกงานนี้',
    );
    return;
  }
  const libraryClean=event.target.closest('[data-library-clean]')?.dataset.libraryClean;
  if(libraryClean){
    const completed=libraryClean==='completed';
    openConfirm(completed?'ลบโปรเจกต์ที่เสร็จแล้วทั้งหมด?':'ลบวิดีโอเรนเดอร์ทั้งหมด?',completed?'โฟลเดอร์และแถว Job ที่ทำเสร็จแล้วจะถูกย้ายลงถังขยะ Windows':'ลบเฉพาะไฟล์วิดีโอในคลังทั้งหมด โดยรูป บท เสียง และข้อมูล Job ยังอยู่ครบ',{mode:completed?'completed_projects':'all_renders'});return;
  }
  const toolAction=event.target.closest('[data-tool]')?.dataset.tool;
  if(toolAction){
    const toolPayload={voice_open_folder:{job_id:$('#voice-job').value},subtitle_open_folder:{job_id:$('#subtitle-job').value},audio_open_folder:{job_id:$('#audio-job').value},logo_open_folder:{job_id:$('#logo-job').value}}[toolAction]||{};
    try{
      const result=await postAction(toolAction,toolPayload);
      if(toolAction==='audio_open_folder')toast('เปิดโฟลเดอร์วิดีโอของงานที่เลือกแล้ว','success');
      if(toolAction==='audio_open_background_folder')toast(`เปิดคลังเพลงพื้นหลังแล้ว • ${Number(result.file_count||0)} ไฟล์`,'success');
      if(toolAction==='audio_open_sfx_folder')toast(`เปิดคลังเสียงเน้นข้อความแล้ว • ${Number(result.file_count||0)} ไฟล์`,'success');
      if(toolAction.startsWith('audio_open_')){ui.toolsHydrated=false;await poll()}
      if(toolAction.startsWith('queue_')){ui.toolsHydrated=false;await poll()}
    }catch(e){toast(e.message,'error')}return;
  }
  const close = event.target.closest('[data-close-modal]');
  if (close) {
    if (close.dataset.closeModal === 'detail-modal') $('#detail-content video')?.pause();
    document.getElementById(close.dataset.closeModal).close();
    if (close.dataset.closeModal === 'confirm-modal') ui.confirmAction = null;
    return;
  }
  const filter = event.target.closest('[data-filter]');
  if (filter) { ui.libraryFilter=filter.dataset.filter; ui.libraryVisibleCount=24; $$('.filter-chip[data-filter]').forEach(node=>{const active=node===filter;node.classList.toggle('active',active);node.setAttribute('aria-pressed',String(active));}); renderLibrary(ui.state?.library||[]); return; }
  const moreLibrary = event.target.closest('[data-library-more]');
  if (moreLibrary) { ui.libraryVisibleCount += 24; renderLibrary(ui.state?.library || []); return; }
  const play = event.target.closest('[data-detail-play]');
  if (play) { try{await postAction('open_library_video',{item_id:play.dataset.detailPlay})}catch(e){toast(e.message,'error')} return; }
  const cover = event.target.closest('[data-detail-cover]');
  if (cover) { try{await postAction('open_library_cover',{item_id:cover.dataset.detailCover})}catch(e){toast(e.message,'error')} return; }
  const folder = event.target.closest('[data-detail-folder]');
  if (folder) { try{await postAction('open_library_folder',{item_id:folder.dataset.detailFolder})}catch(e){toast(e.message,'error')} return; }
  const editPost = event.target.closest('[data-edit-post-copy]');
  if (editPost) { openPostCopyEditor(editPost.dataset.editPostCopy); return; }
  const delVideo = event.target.closest('[data-detail-delete-video]');
  if (delVideo) { askDelete('video',delVideo.dataset.detailDeleteVideo); return; }
  const delProject = event.target.closest('[data-detail-delete-project]');
  if (delProject) { askDelete('project',delProject.dataset.detailDeleteProject); return; }
  const copy = event.target.closest('[data-copy-key]');
  if (copy) { const item=libraryItem($('#detail-content').dataset.itemId); if(item) copyText(item[copy.dataset.copyKey]||''); return; }
  const action = event.target.closest('[data-action]')?.dataset.action;
  const map = {'open-shopee':'shopee','open-chatgpt':'chatgpt','open-gemini':'gemini','open-flow':'flow'};
  if (map[action]) { try{await postAction('open_web',{target:map[action]})}catch(e){toast(e.message,'error')} }
}, true);

$('#create-product').addEventListener('click', async () => {
  try {
    await postAction('create_product',{link:$('#product-link').value.trim(),provider:$('#product-provider').value,ai_web_model:selectedAiModel('#product-provider','#product-model'),video_provider:$('#product-video-provider').value,subtitle:$('#product-subtitle').checked});
    $('#product-link').value=''; await poll();
  } catch (error) { toast(error.message,'error'); }
});
$('#save-product-link').addEventListener('click',async()=>{try{const result=await postAction('import_product_link',{link:$('#product-link').value.trim()});$('#product-link').value='';ui.selectedProductId=result.job_id;toast(result.created?'สร้าง Product Job แล้ว':'ลิงก์นี้มีอยู่แล้ว','success');await poll()}catch(e){toast(e.message,'error')}});
$('#product-selected-job').addEventListener('change',event=>{ui.selectedProductId=event.target.value;renderProductToolScope()});
$('#product-detail-save').addEventListener('click',async()=>{try{await postAction('update_product',{job_id:$('#product-detail-id').value,product_name:$('#product-detail-name').value,price:$('#product-detail-price').value,commission:$('#product-detail-commission').value,description:$('#product-detail-description').value});toast('บันทึกข้อมูลสินค้าแล้ว','success');$('#product-detail-modal').close();await poll()}catch(e){toast(e.message,'error')}});
$('#save-post-copy').addEventListener('click', async () => {
  const modal = $('#post-copy-modal'), button = $('#save-post-copy');
  if (button.disabled) return;
  button.disabled = true;
  try {
    await postAction('save_library_post_metadata', {
      item_id: modal.dataset.itemId,
      revision: modal.dataset.revision,
      description: $('#post-copy-description').value,
      hashtags: $('#post-copy-hashtags').value,
    });
    const itemId = modal.dataset.itemId;
    modal.close();
    toast('บันทึกข้อความโพสต์แล้ว • วิดีโอเดิมไม่เปลี่ยน', 'success');
    await openDetail(itemId);
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; }
});
$('#product-detail-provider-save').addEventListener('click',()=>{const jobId=$('#product-detail-id').value,job=productItem(jobId),provider=$('#product-detail-video-provider').value;if(!job)return;const from=job.video_ai_provider==='meta_ai'?'Meta AI':'Google Flow',to=provider==='meta_ai'?'Meta AI':'Google Flow';if(from===to){toast('งานนี้ใช้ผู้สร้างวิดีโอนี้อยู่แล้ว','info');return}const total=Number(job.flow_target_clip_count||job.segment_target_count||3);openConfirm('เปลี่ยนผู้สร้างวิดีโอของงานนี้?',`จาก ${from} เป็น ${to}\nใช้เฉพาะคลิปจาก ${to} ที่ตรงกับภาพ/บทปัจจุบัน คลิปจากผู้สร้างเดิมยังเก็บไว้แต่ไม่เอามาปนใน Final รอบใหม่ • สร้างเฉพาะช็อตที่ยังขาด (สูงสุด ${total} ช็อต)`,{mode:'product_video_provider',jobId,provider},'เปลี่ยนผู้สร้างวิดีโอ')});
$('#product-detail-copy-link').addEventListener('click',()=>copyText(productItem($('#product-detail-id').value)?.link||''));
$('#product-detail-approve').addEventListener('click',async()=>{try{await postAction('approve_product_ai',{job_id:$('#product-detail-id').value});toast('อนุมัติผล AI แล้ว','success');await poll();openProductDetail($('#product-detail-id').value)}catch(e){toast(e.message,'error')}});
$('#product-detail-check').addEventListener('click',async()=>{try{const r=await postAction('check_product_readiness',{job_id:$('#product-detail-id').value});toast(r.readiness?.ready?'ข้อมูลพร้อมแล้ว':`ยังขาด: ${(r.readiness?.missing||[]).join(', ')}`,r.readiness?.ready?'success':'info')}catch(e){toast(e.message,'error')}});
function storyBatchTopics() {
  return $('#story-batch-topics').value.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
}
function updateStoryBatchDialog() {
  const topics = storyBatchTopics();
  const valid = topics.length > 0 && topics.length <= 10;
  const seen=new Set();let duplicates=0;
  for(const topic of topics){const key=topic.normalize('NFKC').toLocaleLowerCase();if(seen.has(key))duplicates++;else seen.add(key);}
  $('#story-batch-count').textContent = `${topics.length} / 10 คลิป`;
  $('#story-batch-count').classList.toggle('invalid', topics.length > 10);
  $('#story-batch-preview').textContent = topics.length
    ? `เตรียม ${topics.length-duplicates} คลิปใหม่${duplicates?` • พบหัวข้อซ้ำ ${duplicates} บรรทัด จะข้ามรายการซ้ำ`:''} • แต่ละบรรทัดเป็น 1 คลิป`
    : 'พิมพ์หัวข้อเพื่อดูจำนวนคลิปและรายการซ้ำ';
  $('#story-batch-preview').classList.toggle('has-duplicates',duplicates>0);
  $('#story-batch-submit').disabled = !valid;
  $('#story-batch-scene-label').textContent = `${Number($('#story-batch-scenes').value || 10)} ฉาก`;
}
for (const type of ['input','change']) $('#story-batch-modal').addEventListener(type, event => {
  if (event.isTrusted) ui.storyBatchDirty = true;
});
$('#open-story-batch').addEventListener('click', event => {
  const modal = $('#story-batch-modal');
  const fromQueue = event.detail?.source === 'creation_queue';
  const inheritSingleStory = !fromQueue && !ui.storyBatchDirty;
  // Opening from the queue must not replace its draft with unrelated values
  // from the single-Story form on a different page.
  if (inheritSingleStory) {
    const currentTopic = $('#story-topic').value.trim();
    if (!$('#story-batch-topics').value.trim() && currentTopic) $('#story-batch-topics').value = currentTopic;
    if (!$('#story-batch-direction').value.trim()) $('#story-batch-direction').value = $('#story-text').value.trim();
    $('#story-batch-provider').value = $('#story-provider').value;
    fillAiModelSelect('#story-batch-provider','#story-batch-model',selectedAiModel('#story-provider','#story-model'));
    $('#story-batch-video-mode').value = $('#story-video-mode').value;
    $('#story-batch-visual-style').value = $('#story-visual-style').value;
    $('#story-batch-visual-style-custom').value = $('#story-visual-style-custom').value;
    $('#story-batch-scenes').value = $('#story-scenes').value;
    if (!ui.storyBatchImage && ui.storyImage) {
      ui.storyBatchImage = ui.storyImage;
      $('#story-batch-image-path').value = ui.storyImage;
      $('#story-batch-image-name').textContent = $('#story-image-name').textContent;
    }
  }
  $('#story-batch-visual-style').dispatchEvent(new Event('change'));
  updateStoryBatchDialog();
  if (inheritSingleStory) {
    window.preparePresenterQueue?.('story-batch');
    window.prepareStoryAudioBatch?.();
  }
  modal.showModal();
  $('#story-batch-topics').focus();
});
$('#story-batch-topics').addEventListener('input', updateStoryBatchDialog);
$('#story-batch-scenes').addEventListener('input', updateStoryBatchDialog);
$('#choose-story-batch-image').addEventListener('click', async () => {
  const input=$('#story-batch-image-file'); input.value=''; input.click();
});
$('#story-batch-image-file').addEventListener('change', async event => {
  const file=event.target.files?.[0]; if(!file)return;
  try{toast('กำลังนำเข้ารูปหลัก…','info');const result=await uploadReferenceImage(file,'story');ui.storyBatchImage=result.asset_id ? `asset:${result.asset_id}` : result.path;$('#story-batch-image-path').value=ui.storyBatchImage;$('#story-batch-image-name').textContent=`✓ ${file.name}`;toast('นำเข้ารูปหลักแล้ว','success')}catch(error){toast(error.message,'error')}
});
$('#story-batch-submit').addEventListener('click', async () => {
  const enteredTopics = storyBatchTopics();
  if (!enteredTopics.length || enteredTopics.length > 10) { updateStoryBatchDialog(); return; }
  const seenTopics=new Set();
  const topics=enteredTopics.filter(topic=>{const key=topic.normalize('NFKC').toLocaleLowerCase();if(seenTopics.has(key))return false;seenTopics.add(key);return true;});
  const inputDuplicates=enteredTopics.length-topics.length;
  const submit = $('#story-batch-submit');
  submit.disabled = true;
  try {
    const result = await postAction('enqueue_story_batch',{topics,...storyStylePayload('story-batch'),story_text:$('#story-batch-direction').value.trim(),provider:$('#story-batch-provider').value,ai_web_model:selectedAiModel('#story-batch-provider','#story-batch-model'),video_generation_mode:$('#story-batch-video-mode').value,scene_count:Number($('#story-batch-scenes').value),main_image:ui.storyBatchImage || $('#story-batch-image-path').value});
    $('#story-batch-modal').close();
    $('#story-batch-topics').value = '';
    $('#story-batch-direction').value = '';
    ui.storyBatchDirty = false;
      toast(`เพิ่มคิว ${Number(result.queued ?? topics.length)} คลิป • ข้ามรายการซ้ำ ${Number(result.duplicates || 0)+inputDuplicates} • ${result.paused ? 'กดเริ่มคิวเมื่อพร้อม' : 'ต่อท้ายคิวที่กำลังทำงานแล้ว'}`, 'success');
    showPage('creation');
    await poll();
  } catch(error) { toast(error.message,'error'); }
  finally { submit.disabled = false; }
});
$('#create-story').addEventListener('click', async () => {
  try {
    await postAction('create_story',{...storyStylePayload('story'),topic:$('#story-topic').value.trim(),story_text:$('#story-text').value.trim(),provider:$('#story-provider').value,ai_web_model:selectedAiModel('#story-provider','#story-model'),video_generation_mode:$('#story-video-mode').value,scene_count:Number($('#story-scenes').value),main_image:ui.storyImage || $('#story-image-path').value});
    await poll();
  } catch(error){toast(error.message,'error')}
});
$('#story-video-mode').addEventListener('change', updateStoryVideoMode);
$('#story-scenes').addEventListener('input', updateStoryVideoMode);
updateStoryVideoMode();
$('#choose-story-image').addEventListener('click', async () => {
  const input=$('#story-image-file'); input.value=''; input.click();
});
$('#story-image-file').addEventListener('change', async event => {
  const file=event.target.files?.[0]; if(!file)return;
  try{toast('กำลังนำเข้ารูปหลัก…','info');const result=await uploadReferenceImage(file,'story');ui.storyImage=result.asset_id ? `asset:${result.asset_id}` : result.path;$('#story-image-path').value=ui.storyImage;$('#story-image-name').textContent=`✓ ${file.name}`;toast('นำเข้ารูปหลักแล้ว','success')}catch(error){toast(error.message,'error')}
});
$$('[data-drama-image]').forEach(button => button.addEventListener('click', async () => {
  const index = button.dataset.dramaImage;
  const input=$(`#drama-character-${index}-file`); input.value=''; input.click();
}));
for (const index of [1,2]) $(`#drama-character-${index}-file`).addEventListener('change', async event => {
  const file=event.target.files?.[0]; if(!file)return;
  try {
    toast(`กำลังนำเข้ารูปตัวละคร ${index}…`, 'info');
    const result=await uploadReferenceImage(file,'drama');
    ui.dramaImages[index]=result.asset_id ? `asset:${result.asset_id}` : result.path;
    $(`#drama-character-${index}-image`).value=ui.dramaImages[index];
    $(`#drama-character-${index}-image-name`).textContent=`✓ ${file.name}`;
    const preview=$(`#drama-character-${index}-preview`); preview.src=result.dataUrl; preview.hidden=false;
    toast(`นำเข้ารูปตัวละคร ${index} แล้ว`, 'success');
  } catch(error) { toast(error.message,'error'); }
});
$('#choose-drama-footage').addEventListener('click', async () => {
  try {
    const result = await postAction('choose_drama_footage');
    ui.dramaFootage = Array.isArray(result.paths) ? result.paths : [];
    $('#drama-footage-name').textContent = ui.dramaFootage.length ? `เลือกแล้ว ${ui.dramaFootage.length} ไฟล์ • แทรกอัตโนมัติ` : 'ไม่บังคับ • แทรกเป็นภาพเคลื่อนไหวจริง';
    if (ui.dramaFootage.length) toast(`เลือกฟุตเทจ ${ui.dramaFootage.length} ไฟล์แล้ว`, 'success');
  } catch(error) { toast(error.message, 'error'); }
});
let dramaSubmitting = false;
function clearDramaDraftAfterSubmit() {
  $('#drama-title').value=''; $('#drama-premise').value='';
  ui.dramaImages={}; ui.dramaFootage=[];
  $('#drama-footage-name').textContent='ไม่บังคับ • แทรกเป็นภาพเคลื่อนไหวจริง';
  for(const index of [1,2,3,4]){
    for(const field of ['name','description','image','file'])$(`#drama-character-${index}-${field}`).value='';
    $(`#drama-character-${index}-voice`).value='';
    $(`#drama-character-${index}-image-name`).textContent=index===1?'แนะนำ • ช่วยล็อกใบหน้า':'ไม่บังคับ';
    const preview=$(`#drama-character-${index}-preview`);
    if(preview.dataset.objectUrl)URL.revokeObjectURL(preview.dataset.objectUrl);
    preview.removeAttribute('src');delete preview.dataset.objectUrl;preview.hidden=true;
    if(index>1)preview.closest('.character-card').hidden=true;
  }
  const cast=document.querySelector('.drama-character-disclosure');if(cast)cast.open=false;
  const add=cast?.querySelector('.character-grid + button');if(add)add.disabled=false;
  renderDramaPlotBoard(true);
  updateCreationAvailability();
}
async function submitDramaSeries(enqueueOnly = false) {
  const button = $('#create-drama-series');
  if(dramaSubmitting)return;
  if(!$('#drama-title').value.trim()){toast('ใส่ชื่อเรื่องละครก่อน','error');return;}
  const characters = [1,2,3,4].filter(index=>$(`#drama-character-${index}-name`)).map(index => ({
    name:$(`#drama-character-${index}-name`).value.trim(),
    description:$(`#drama-character-${index}-description`).value.trim(),
    image:ui.dramaImages[index] || $(`#drama-character-${index}-image`).value,
    voice_reference_id:$(`#drama-character-${index}-voice`).value,
    voice_label:$(`#drama-character-${index}-voice`).selectedOptions[0]?.textContent || '',
    role:index === 1 ? 'ตัวละครหลัก' : 'ตัวละครร่วม',
  })).filter(item => item.name || item.description || item.image);
  dramaSubmitting = true;
  button.dataset.busy='true';button.disabled = true;
  $('#enqueue-drama-series').disabled = true;
  try {
    const result = await postAction('create_drama_series',{
      enqueue_only:enqueueOnly,
      render_options:{video_generation_mode:$('#drama-video-mode').value,timing_mode:$('#drama-timing').value,
        tail_seconds:Number($('#drama-tail').value),subtitle_enabled:$('#drama-subtitle').checked},
      ...storyStylePayload('drama'),
      title:$('#drama-title').value.trim(),
      premise:$('#drama-premise').value.trim(),
      provider:$('#drama-provider').value,
      ai_web_model:selectedAiModel('#drama-provider','#drama-model'),
      episode_count:Number($('#drama-episodes').value),
      scene_count:Number($('#drama-scenes').value),
      characters,
      footage:ui.dramaFootage,
      plot_board:currentDramaPlotBoard(),
      cover_theme:$('#drama-cover-theme').value,
    });
    toast(`${enqueueOnly||result.queued_only?'เพิ่มลงคิว':'เริ่มละครสั้น'} ${Number(result.queued || 0)} EP แล้ว • ระบบทำทีละตอน`, 'success');
    clearDramaDraftAfterSubmit();
    await poll();
  } catch(error) { toast(error.message, 'error'); }
  finally { dramaSubmitting=false;delete button.dataset.busy;$('#enqueue-drama-series').disabled = false;updateCreationAvailability(); }
}
$('#create-drama-series').addEventListener('click',()=>submitDramaSeries(false));
$('#enqueue-drama-series').addEventListener('click',()=>submitDramaSeries(true));
$('#drama-continue-submit').addEventListener('click', async () => {
  const button=$('#drama-continue-submit'); button.disabled=true;
  try {
    const result=await postAction('continue_drama_series',{series_id:$('#drama-continue-series-id').value,continuation_prompt:$('#drama-continue-prompt').value.trim(),scene_count:Number($('#drama-continue-scenes').value)});
    $('#drama-continue-modal').close();
    toast(`เริ่มทำ EP ${Number(result.episode_no || 0)} ต่อจากซีรีส์เดิมแล้ว`,'success');
    await poll();
  } catch(error) { toast(error.message,'error'); }
  finally { button.disabled=false; }
});
$('#story-scenes').addEventListener('input',updateRangeLabels); $('#drama-episodes').addEventListener('input',updateRangeLabels); $('#drama-scenes').addEventListener('input',updateRangeLabels); $('#setting-motion').addEventListener('input',updateRangeLabels); $('#setting-transition').addEventListener('input',updateRangeLabels); $('#product-subtitle').addEventListener('change',()=>ui.state&&renderSystem(ui.state));
for(const selector of ['#audio-background-volume','#audio-segment-max','#audio-duck-percent','#audio-sfx-volume','#logo-opacity','#logo-size','#logo-margin']) $(selector)?.addEventListener('input',updateToolLabels);
for(const selector of ['#subtitle-font-size','#subtitle-mark-gap','#subtitle-outline','#subtitle-y','#subtitle-text-color','#subtitle-highlight-color','#subtitle-outline-color','#subtitle-background-enabled','#subtitle-background-color','#subtitle-background-opacity']) $(selector)?.addEventListener('input',()=>{updateToolLabels();scheduleSubtitlePreview()});
$('#subtitle-theme').addEventListener('change',()=>scheduleSubtitlePreview({applyTheme:true,immediate:true}));
$('#subtitle-animation').addEventListener('change',()=>scheduleSubtitlePreview({immediate:true}));
$('#subtitle-font').addEventListener('change',()=>scheduleSubtitlePreview({immediate:true}));
for(const button of document.querySelectorAll('[data-subtitle-preview-mode]')) button.addEventListener('click',()=>applySubtitlePreviewMode(button.dataset.subtitlePreviewMode));
$('#subtitle-preview-replay').addEventListener('click',()=>{
  const video=$('#subtitle-preview-video');
  if(!video || video.hidden || !video.src){toast('พรีวิวยังไม่พร้อม','info');return;}
  video.currentTime=0;
  video.play().then(()=>toast('เริ่มเล่นแอนิเมชันใหม่แล้ว','success')).catch(()=>toast('กดเล่นบนพรีวิวอีกครั้ง','info'));
});
$('#voice-job').addEventListener('change',async()=>{try{await postAction('voice_select_job',{job_id:$('#voice-job').value});ui.toolsHydrated=false;await poll()}catch(e){toast(e.message,'error')}});
$('#voice-save-key').addEventListener('click',async()=>{try{await postAction('voice_save_key',{api_key:$('#voice-key').value.trim()});$('#voice-key').value='';toast('บันทึก API Key ใน Windows แล้ว','success');ui.toolsHydrated=false;await poll()}catch(e){toast(e.message,'error')}});
$('#voice-delete-key').addEventListener('click',()=>openConfirm('ยกเลิก AI Voice?','API Key ที่เก็บไว้ใน Windows จะถูกลบออก คุณสามารถเชื่อมต่อใหม่ได้ด้วย API Key เดิม','voice_disconnect','ยกเลิกการเชื่อมต่อ'));
$('#voice-refresh-catalog').addEventListener('click',async()=>{try{await postAction('voice_refresh_catalog');toast('กำลังโหลดรายการเสียง','info');setTimeout(async()=>{ui.toolsHydrated=false;await poll()},900)}catch(e){toast(e.message,'error')}});
$('#voice-catalog').addEventListener('change',async()=>{try{await postAction('voice_select_catalog',{label:$('#voice-catalog').value});ui.toolsHydrated=false;await poll()}catch(e){toast(e.message,'error')}});
$('#voice-choose-reference').addEventListener('click',async()=>{try{const r=await postAction('voice_choose_reference');if(r.path){$('#voice-reference-file').value=r.path;toast('เลือกเสียงอ้างอิงแล้ว','success')}}catch(e){toast(e.message,'error')}});
$('#voice-upload-reference').addEventListener('click',async()=>{try{await postAction('voice_upload_reference');toast('กำลังอัปโหลดเสียงอ้างอิง','info');setTimeout(async()=>{ui.toolsHydrated=false;await poll()},1000)}catch(e){toast(e.message,'error')}});
$('#voice-load-script').addEventListener('click',()=>$('#voice-job').dispatchEvent(new Event('change')));
$('#voice-ai-script').addEventListener('click',async()=>{try{await postAction('voice_ai_script',{job_id:$('#voice-job').value});toast('ส่งงานไป AI Web แล้ว','success')}catch(e){toast(e.message,'error')}});
function voicePayload(){return {job_id:$('#voice-job').value,reference_id:$('#voice-reference-id').value,language:$('#voice-language').value,emotion:'normal',speed:1,silence:$('#voice-silence').value,format:$('#voice-format').value,script:$('#voice-script').value}}
$('#voice-save-settings').addEventListener('click',async()=>{try{const result=await postAction('voice_save_settings',voicePayload());$('#voice-save-state').textContent=result.script_changed?'บันทึกแล้ว • บทเปลี่ยน กรุณาสร้างเสียงใหม่':'บันทึกแล้ว • งานถัดไปจะใช้ค่านี้';toast('บันทึกการตั้งค่าเสียงและบทพูดแล้ว','success');ui.toolsHydrated=false;await poll()}catch(e){toast(e.message,'error')}});
$('#voice-create').addEventListener('click',async()=>{try{await postAction('voice_create',voicePayload());toast('เริ่มสร้างเสียงแล้ว • Normal / 1.0x','success');await poll()}catch(e){toast(e.message,'error')}});

$('#subtitle-job').addEventListener('change',async()=>{try{await postAction('subtitle_select_job',{job_id:$('#subtitle-job').value});ui.toolsHydrated=false;await poll()}catch(e){toast(e.message,'error')}});
$('#subtitle-connect').addEventListener('click',async()=>{try{await postAction('subtitle_connect',{token:$('#subtitle-token').value.trim()});$('#subtitle-token').value='';toast('กำลังเชื่อม Subtitle Token','info');setTimeout(async()=>{ui.toolsHydrated=false;await poll()},900)}catch(e){toast(e.message,'error')}});
$('#subtitle-delete-credential').addEventListener('click',()=>openConfirm('ยกเลิก AI Subtitle?','รหัสอุปกรณ์ที่เก็บไว้ใน Windows จะถูกลบ หลังจากนี้อาจต้องใช้ Token SOT ใหม่เพื่อเชื่อมเครื่องอีกครั้ง','subtitle_disconnect','ยกเลิกการเชื่อมต่อ'));
$('#subtitle-create').addEventListener('click',async()=>{try{await postAction('subtitle_create',subtitlePayload());toast('เริ่มสร้าง Subtitle แล้ว','success');await poll()}catch(e){toast(e.message,'error')}});
$('#subtitle-upload-font').addEventListener('click',async()=>{try{const r=await postAction('subtitle_upload_font');if(!r.cancelled){toast(`เพิ่มฟอนต์ ${r.font}`,'success');ui.toolsHydrated=false;await poll()}}catch(e){toast(e.message,'error')}});
$('#subtitle-random-theme').addEventListener('click',async()=>{try{await postAction('subtitle_random_theme');ui.toolsHydrated=false;await poll();toast('สุ่มธีมแล้ว','success')}catch(e){toast(e.message,'error')}});
$('#subtitle-save-style').addEventListener('click',async()=>{try{await postAction('subtitle_save_style',subtitlePayload());toast('บันทึกรูปแบบ Subtitle แล้ว','success');setTimeout(poll,500)}catch(e){toast(e.message,'error')}});
$('#subtitle-apply-style').addEventListener('click',async()=>{try{await postAction('subtitle_apply_style',subtitlePayload());toast('บันทึกแล้ว กำลังสร้างวิดีโอใหม่','success');await poll()}catch(e){toast(e.message,'error')}});

$('#audio-job').addEventListener('change',async()=>{try{await postAction('audio_select_job',{job_id:$('#audio-job').value});ui.toolsHydrated=false;await poll()}catch(e){toast(e.message,'error')}});
$('#audio-save').addEventListener('click',async()=>{try{await postAction('audio_save',audioPayload());window.SmartFlowMusic?.saved();toast('บันทึกค่าเสียงประกอบแล้ว','success');await poll()}catch(e){toast(e.message,'error')}});
$('#audio-random').addEventListener('click',async()=>{try{await postAction('audio_random');ui.toolsHydrated=false;await poll();toast('สุ่มเสียงชุดใหม่แล้ว','success')}catch(e){toast(e.message,'error')}});
$('#audio-render').addEventListener('click',async()=>{try{await postAction('audio_save',audioPayload());await postAction('audio_render',{job_id:$('#audio-job').value});toast('กำลังสร้างวิดีโอพร้อมเสียงประกอบ','success')}catch(e){toast(e.message,'error')}});

window.SmartFlowLogo?.bind({payload:logoPayload,request:async payload=>{await postAction('logo_editor_preview',payload);setTimeout(poll,500);setTimeout(poll,1500);},error:error=>toast(error.message,'error')});
$('#logo-job').addEventListener('change',async()=>{try{window.SmartFlowLogo?.resetContext();await postAction('logo_select_job',{job_id:$('#logo-job').value});ui.toolsHydrated=false;await poll();await window.SmartFlowLogo?.preview()}catch(e){toast(e.message,'error')}});
$('#logo-library').addEventListener('click',async event=>{
  const button=event.target.closest('[data-logo-asset]'); if(!button)return;
  try {
    const result=await postAction('logo_select_asset',{asset_id:button.dataset.logoAsset});
    ui.selectedLogoAssetId=result.asset_id; ui.toolsHydrated=false; await poll();
    toast(`เลือก ${result.name} แล้ว`,'success');
    await window.SmartFlowLogo?.preview();
  } catch(e){toast(e.message,'error')}
});
$('#logo-upload-file').addEventListener('change',async event=>{
  const file=event.target.files?.[0]; if(!file)return;
  try {
    toast('กำลังเพิ่มโลโก้เข้าคลัง…','info');
    const dataUrl=await prepareLogoImage(file);
    const result=await postAction('logo_upload',{filename:file.name,data_url:dataUrl});
    ui.selectedLogoAssetId=result.asset_id; ui.toolsHydrated=false; await poll();
    toast(`เพิ่ม ${result.name} เข้าคลังแล้ว • อย่าลืมกดบันทึก`,'success');
    await window.SmartFlowLogo?.preview();
  } catch(e){toast(e.message,'error')}
  finally {event.target.value=''}
});
$('#logo-preview-button').addEventListener('click',async()=>{try{await window.SmartFlowLogo?.preview();toast('กำลังสร้างพรีวิวจริง','info')}catch(e){toast(e.message,'error')}});
$('#logo-save').addEventListener('click',async()=>{try{await postAction('logo_save',logoPayload());window.SmartFlowLogo?.saved();ui.toolsHydrated=false;toast('บันทึกโลโก้เริ่มต้นและตำแหน่งแล้ว','success');await poll()}catch(e){toast(e.message,'error')}});
$('#logo-render').addEventListener('click',async()=>{try{await postAction('logo_render',logoPayload());toast('กำลังสร้างวิดีโอใส่โลโก้','success')}catch(e){toast(e.message,'error')}});

$('#save-settings').addEventListener('click',async()=>{try{await postAction('save_quick_settings',{provider:$('#setting-provider').value,chatgpt_web_model:$('#setting-chatgpt-model').value,gemini_web_model:$('#setting-gemini-model').value,video_provider:$('#setting-video-provider').value,resolution:$('#setting-resolution').value,fps:Number($('#setting-fps').value),encoder:$('#setting-encoder').value,quality:$('#setting-quality').value,motion_percent:Number($('#setting-motion').value),transition_ms:Number($('#setting-transition').value),subtitle_auto:$('#setting-subtitle').checked});ui.formsHydrated=false;ui.settingsHydrated=false;toast('บันทึกค่าหลักและโมเดล AI Web แล้ว','success');await poll()}catch(e){toast(e.message,'error')}});
$$('[data-credit-refresh]').forEach(button=>button.addEventListener('click',async()=>{try{button.disabled=true;await postAction('refresh_service_credits');toast('กำลังตรวจยอดเครดิตจริง','info');setTimeout(poll,700)}catch(e){toast(e.message,'error')}finally{setTimeout(()=>{button.disabled=false},900)}}));
$('#refresh-button').addEventListener('click',async()=>{try{await postAction('refresh');await postAction('refresh_service_credits');await poll();toast('อัปเดตข้อมูลและเครดิตแล้ว','success')}catch(e){toast(e.message,'error')}});
$('#check-system').addEventListener('click',async()=>{try{const result=await postAction('check_system_readiness');await poll();toast(result.ready?'ระบบพร้อมสร้างงานแล้ว':`ระบบพร้อม ${result.ready_count}/4 รายการ`,result.ready?'success':'info')}catch(e){toast(e.message,'error')}});
$('#install-extension').addEventListener('click',async()=>{try{await postAction('install_extension');toast('เปิด Chrome Extensions และโฟลเดอร์แล้ว','success')}catch(e){toast(e.message,'error')}});
$('#copy-extension').addEventListener('click',()=>copyText(ui.state?.settings.extension_path||''));
$('#open-log-folder').addEventListener('click',async()=>{try{await postAction('open_logs_folder')}catch(e){toast(e.message,'error')}});
$('#cleanup-scan').addEventListener('click',async()=>{try{const result=await postAction('scan_workspace_junk');await poll();const summary=result.summary||{};toast(Number(summary.file_count||0)?`พบไฟล์ขยะ ${Number(summary.file_count).toLocaleString('th-TH')} ไฟล์ • ${formatBytes(summary.size_bytes)}`:'พื้นที่สะอาดแล้ว ไม่พบไฟล์ขยะ','success')}catch(e){toast(e.message,'error')}});
$('#cleanup-run').addEventListener('click',async()=>{try{const result=await postAction('scan_workspace_junk');await poll();const summary=result.summary||{};const count=Number(summary.file_count||0);if(!count){toast('พื้นที่สะอาดแล้ว ไม่พบไฟล์ขยะ','success');return}openConfirm('ยืนยันเคลียร์ไฟล์ขยะ?',`ระบบจะย้ายไฟล์ขยะ ${count.toLocaleString('th-TH')} ไฟล์ (${formatBytes(summary.size_bytes)}) ลงถังขยะ Windows\n\nFinal, รูป, เสียง, Subtitle, ปก และข้อมูลโปรเจกต์จะไม่ถูกลบ งานที่กำลังทำ งานล้มเหลว และ Checkpoint ที่ยังต้องทำต่อจะถูกข้าม`,{mode:'workspace_cleanup',scanId:summary.scan_id},'ลบไฟล์ขยะทั้งหมด')}catch(e){toast(e.message,'error')}});
$('#progress-cancel').addEventListener('click',async event=>{
  const button=event.currentTarget;
  if(button.disabled)return;
  button.disabled=true;
  button.textContent='กำลังยกเลิก...';
  try{
    await postAction(ui.progressType==='presenter'?'presenter_cancel':ui.progressType==='product'?'cancel_product':'cancel_story');
    toast('รับคำสั่งยกเลิกแล้ว • กำลังเก็บ Checkpoint','info');
    await poll(true);
  }catch(e){
    button.disabled=false;
    button.textContent='ยกเลิกการทำงาน';
    toast(e.message,'error');
  }
});
async function submitLongVideo(enqueueOnly = false) {
  const button = $('#create-longvideo');
  if (button.disabled) return;
  if ($('#long-mode')?.value === 'meta_ai' && !ui.state?.system?.long_meta_landscape_available) {
    $('#long-status').textContent = 'Meta AI คลิปยาว 16:9 ยังรอยืนยันไฟล์วิดีโอจริง';
    return;
  }
  button.disabled = true;
  try {
    const result = await postAction(enqueueOnly ? 'enqueue_long_video' : 'create_story', {topic:$('#long-topic').value.trim(), story_text:$('#long-text').value.trim(),
      provider:$('#long-provider').value, video_generation_mode:$('#long-mode').value,
      long_video:{version:2,duration_seconds:Number($('#long-duration').value),scene_count:$('#long-scenes').value}});
    if (!result.ok) throw Error('ยังเริ่มงานไม่ได้ กรุณาตรวจสถานะโปรแกรม');
    const queued=enqueueOnly || result.queued_only || result.queued;
    const paused=result.queued_only || result.story_queue?.paused===true || result.paused===true;
    $('#long-status').textContent = queued
      ? paused ? 'เพิ่มลงคิวแล้ว • กดเริ่มคิวเมื่อพร้อม'
        : result.story_queue?.paused===false || result.paused===false ? 'เพิ่มต่อท้ายคิวที่กำลังทำแล้ว • งานปัจจุบันทำต่อจนจบ' : 'เพิ่มลงคิวแล้ว • ดูสถานะที่หน้าคิวสร้างคลิป'
      : `เริ่มงาน ${result.job_id} แล้ว • ดูสถานะและผลงานในโปรแกรม`;
    await poll();
  } catch(error) { $('#long-status').textContent = error.message; toast(error.message,'error'); }
  finally { button.disabled = false; }
}
$('#create-longvideo')?.addEventListener('click', () => submitLongVideo(false));
function updateLongVideoCapability(state) {
  const option = $('#long-mode option[value="meta_ai"]');
  if (!option) return;
  const verified = Boolean(state?.system?.long_meta_landscape_available);
  option.disabled = !verified;
  option.textContent = verified ? 'Meta AI (ทดลอง) • แนวนอน 16:9' : 'Meta AI (ทดลอง) • 16:9 รอยืนยัน';
  const note = $('#long-mode-note');
  if (note) note.textContent = verified
    ? 'Meta AI เป็นโหมดทดลอง • ตรวจรับเฉพาะคลิปแนวนอน 16:9 ที่เล่นได้จริง • ความยาวจริงขึ้นกับบทและเสียงพากย์ • อาจใช้เครดิตต่อฉาก'
    : 'Meta AI คลิปยาวยังรอพิสูจน์ไฟล์แนวนอน 16:9 จริง • ความยาวจริงขึ้นกับบทและเสียงพากย์ • ผู้สร้างวิดีโอออนไลน์อาจใช้เครดิตต่อฉาก';
}
function updateLongVideoPreview() {
  const seconds = Number($('#long-duration')?.value || 180);
  const selected = $('#long-scenes')?.value || 'auto';
  const count = selected === 'auto' ? Math.min(50, Math.ceil(seconds / 8)) : Number(selected);
  const batches = Math.ceil(count / 10);
  const preview = $('#long-plan-preview');
  if (preview) preview.textContent = `${count} ภาพแนวนอน 16:9 • ทำทีละ 10 ภาพ (${batches} ชุด) • ประกอบเป็น 1920×1080`;
}
$('#long-duration')?.addEventListener('change', updateLongVideoPreview);
$('#long-scenes')?.addEventListener('change', updateLongVideoPreview);
updateLongVideoPreview();
$('#drama-queue-toggle')?.addEventListener('click', toggleDramaQueue);
function updateDramaTimingControls() {
  const selected = $('#drama-video-mode')?.value;
  const timed = selected === 'google_flow' || selected === 'meta_ai';
  const flow = selected === 'google_flow';
  if ($('#drama-timing')) $('#drama-timing').disabled = !timed;
  if ($('#drama-tail')) $('#drama-tail').disabled = !flow || $('#drama-timing').value !== 'voice_fit';
}
$('#drama-video-mode')?.addEventListener('change', updateDramaTimingControls);
$('#drama-timing')?.addEventListener('change', updateDramaTimingControls);
updateDramaTimingControls();
$('#progress-focus').addEventListener('click',async()=>{if(ui.progressType==='presenter'){try{await postAction('presenter_focus',{id:ui.progressJobId})}catch(e){toast(e.message,'error')}return;}const progress=ui.progressType==='product'?ui.state.product_progress:ui.state.story_progress;try{await postAction('focus_verification',{job_id:progress.job_id,provider:ui.state.settings.provider,service:progress.action_service})}catch(e){toast(e.message,'error')}});
$('#progress-result').addEventListener('click',()=>{const presenter=ui.progressType==='presenter';window.dismissPresenterProgress?.();dismissProgressResult();showPage(presenter?'presenter':'library')});
$('#progress-close').addEventListener('click',()=>{if(ui.progressType==='presenter'&&!ui.state?.presenter_progress?.active){window.dismissPresenterProgress?.();dismissProgressResult();}else minimizeProgress()});
$('#progress-minimized').addEventListener('click',restoreProgress);
$('#progress-modal').addEventListener('cancel',event=>{event.preventDefault();minimizeProgress()});
$('#automation-error-copy').addEventListener('click',()=>{copyText($('#automation-error-log').textContent);toast('คัดลอกรายละเอียดสำหรับทีมช่วยเหลือแล้ว','success')});
$('#automation-error-open').addEventListener('click',()=>{if(ui.state?.automation_error_log?.text&&!$('#automation-error-modal').open)$('#automation-error-modal').showModal()});
$('#automation-error-return').addEventListener('click',()=>{$('#automation-error-modal').close();showPage(ui.automationErrorPage)});
$('#confirm-accept').addEventListener('click',async()=>{
  const target=ui.confirmAction;if(!target)return;$('#confirm-modal').close();if($('#detail-modal').open)$('#detail-modal').close();
  try{
    if(target==='voice_disconnect'){await postAction('voice_delete_key');$('#voice-key').value='';ui.toolsHydrated=false;toast('ยกเลิกการเชื่อมต่อ AI Voice แล้ว','success');await poll()}
    else if(target==='subtitle_disconnect'){await postAction('subtitle_delete_credential');$('#subtitle-token').value='';ui.toolsHydrated=false;toast('ยกเลิกการเชื่อมต่อ AI Subtitle แล้ว','success');await poll()}
    else if(target.mode==='cancel_drama_series'){const result=await postAction('cancel_drama_series',{series_id:target.seriesId});if($('#drama-project-modal').open)$('#drama-project-modal').close();toast(`ยกเลิกคิวแล้ว ${Number(result.cancelled || 0)} EP • พร้อมสร้างเรื่องใหม่`,'success');await poll()}
    else if(target.mode==='dismiss_story'){await postAction('dismiss_story_job',{job_id:target.jobId});toast('ยกเลิกงานเก่าแล้ว • ไฟล์เดิมยังอยู่ครบ','success');await poll()}
    else if(target.mode==='product_video_provider'){await postAction('product_set_video_provider',{job_id:target.jobId,provider:target.provider});toast('บันทึกผู้สร้างวิดีโอแล้ว • กดทำต่อในงานค้างเมื่อพร้อม','success');await poll(true);openProductDetail(target.jobId)}
    else if(target.mode==='story_video_provider'){await postAction('story_set_video_provider',{job_id:target.jobId,provider:target.provider,revision:target.revision});toast('บันทึกผู้สร้างวิดีโอแล้ว • คลิปเดิมยังอยู่ในงาน','success');await poll(true);window.dispatchEvent(new CustomEvent('smartflow-story-provider-saved',{detail:{jobId:target.jobId}}))}
    else if(target.mode==='workspace_cleanup'){await postAction('clean_workspace_junk',{scan_id:target.scanId});toast('กำลังย้ายไฟล์ขยะลงถังขยะ Windows','info');setTimeout(poll,500)}
    else{if(target.mode==='product_project')await postAction('product_tool',{job_id:target.jobId,tool:'delete_project'});else if(target.mode==='all_products')await postAction('delete_all_product_projects');else if(target.mode==='all_renders')await postAction('delete_all_library_renders');else if(target.mode==='completed_projects')await postAction('delete_completed_projects');else await postAction(target.mode==='project'?'delete_library_project':'delete_library_video',{item_id:target.itemId});toast('รับคำสั่งแล้ว กำลังย้ายลงถังขยะ Windows','info');setTimeout(poll,700)}
  }catch(e){toast(e.message,'error')}finally{ui.confirmAction=null}
});
function setSidebarOpen(open) {
  $('#sidebar').classList.toggle('open', open);
  $('#sidebar-backdrop').classList.toggle('show', open);
  $('#mobile-menu').setAttribute('aria-expanded', String(open));
  if (open) $('.nav-item', $('#sidebar'))?.focus();
}
$$('.nav-group').forEach(group => group.addEventListener('toggle', () => { if (group.open) group.lastElementChild?.scrollIntoView({block:'nearest'}); }));
$('#mobile-menu').addEventListener('click',()=>setSidebarOpen(true));
$('#sidebar-backdrop').addEventListener('click',()=>setSidebarOpen(false));
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if ($('#sidebar').classList.contains('open')) setSidebarOpen(false);
  setNewJobMenu(false);
});
document.addEventListener('visibilitychange', updateFxMode);
window.addEventListener('hashchange',()=>showPage((location.hash||'#dashboard').slice(1),false));

bindAiModelSelect('#product-provider','#product-model');
bindAiModelSelect('#story-provider','#story-model');
bindAiModelSelect('#drama-provider','#drama-model');
bindAiModelSelect('#story-batch-provider','#story-batch-model');
bindModalCloseControls();
bindNavigationFallbacks();
$('#story-new-tab')?.addEventListener('click', () => setStoryView('new'));
$('#story-old-tab')?.addEventListener('click', () => setStoryView('old'));
setStoryView('new');
initStorySetupScroller();

for (const selector of ['#product-link', '#story-topic', '#drama-title']) {
  $(selector)?.addEventListener('input', updateCreationAvailability);
  $(selector)?.addEventListener('blur', event => { event.target.dataset.touched='true'; updateCreationAvailability(); });
}
$('#library-search').addEventListener('input',event=>{ui.libraryQuery=event.target.value;ui.libraryVisibleCount=24;renderLibrary(ui.state?.library||[])});
$('#library-sort').addEventListener('change',event=>{ui.librarySort=event.target.value;ui.libraryVisibleCount=24;renderLibrary(ui.state?.library||[])});
updateCreationAvailability();

showPage(ui.activePage,false); updateRangeLabels(); updateToolLabels(); poll(true);
setInterval(() => {
  const active = Boolean(ui.state?.product_progress?.active || ui.state?.story_progress?.active || ui.state?.presenter_progress?.active);
  const interval = active ? 1000 : 5000;
  if (!ui.lastPollAt || Date.now() - ui.lastPollAt >= interval) poll(false);
}, 1000);
