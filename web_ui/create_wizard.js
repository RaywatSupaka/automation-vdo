/* A presentation layer over the existing creation fields and submit buttons. */
(() => {
  const entry = document.getElementById('open-create-wizard');
  if (!entry) return;
  const kinds = {
    product:{label:'คลิปสินค้า',page:'products',main:'#product-link',video:'#product-video-provider',scenes:'#ps-count',provider:'#product-provider',submit:'#create-product'},
    story:{label:'เรื่องเล่า Shorts',page:'story',main:'#story-topic',video:'#story-video-mode',scenes:'#story-scenes',provider:'#story-provider',submit:'#create-story'},
    drama:{label:'ละครสั้น',page:'drama',main:'#drama-title',video:'#drama-video-mode',scenes:'#drama-scenes',provider:'#drama-provider',submit:'#create-drama-series'},
    long:{label:'คลิปยาว',page:'longvideo',main:'#long-topic',video:'#long-mode',scenes:'#long-scenes',provider:'#long-provider',submit:'#create-longvideo'},
  };
  const names = ['ประเภทงาน','เนื้อหา','คนพูด','ภาพและวิดีโอ','เสียงและตกแต่ง','ตรวจแล้วเริ่ม'];
  const dialog = document.createElement('dialog');
  dialog.id = 'create-wizard'; dialog.className = 'create-wizard';
  dialog.setAttribute('aria-labelledby','create-wizard-title');
  dialog.innerHTML = `<div class="create-wizard-card"><header><h2 id="create-wizard-title">สร้างงานใหม่</h2><span id="create-wizard-position" aria-live="polite"></span><button type="button" class="button ghost" data-wizard-close aria-label="ปิดฟอร์มสร้างงาน">✕</button></header><nav id="create-wizard-steps" aria-label="ขั้นตอนสร้างงาน"></nav><div id="create-wizard-body"></div><p id="create-wizard-error" role="alert" aria-live="polite"></p><footer><button type="button" class="button ghost" data-wizard-back>ย้อนกลับ</button><button type="button" class="button secondary" data-wizard-full>ปรับรายละเอียดในฟอร์มเต็ม</button><span class="create-wizard-spacer"></span><button type="button" class="button secondary" data-wizard-queue hidden>เพิ่มเข้าคิวไว้ก่อน</button><button type="button" class="button primary" data-wizard-next>ถัดไป</button></footer></div>`;
  document.body.append(dialog);
  const q = selector => dialog.querySelector(selector);
  const original = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let kind = 'story', step = 1;
  const def = () => kinds[kind];
  const value = selector => original(selector)?.value || '';
  function setField(selector,next) {
    const node = original(selector);
    if (!node) return false;
    node.value = String(next);
    node.dispatchEvent(new Event('input',{bubbles:true}));
    node.dispatchEvent(new Event('change',{bubbles:true}));
    return true;
  }
  function setCheckbox(node,next) {
    if (!node || node.disabled) return false;
    node.checked = Boolean(next);
    node.dispatchEvent(new Event('input',{bubbles:true}));
    node.dispatchEvent(new Event('change',{bubbles:true}));
    return true;
  }
  function formPanel() { return original(`[data-view="${def().page}"]`); }
  function audio() { return window.mediaAudioChoice?.(kind); }
  function extraControl(name) {
    if (name==='presenter') return original(`#presenter-use-${kind}`);
    const panel = formPanel();
    if (!panel) return null;
    const selector = {cover:'[data-cover-enable]',green:'[data-green-enable]',intro:'[data-intro-enable]'}[name];
    return selector ? panel.querySelector(selector) : null;
  }
  function optionList(selector) {
    const node = original(selector);
    return node ? [...node.options].filter(item=>!item.disabled).map(item=>`<option value="${esc(item.value)}" ${item.value===node.value?'selected':''}>${esc(item.textContent)}</option>`).join('') : '';
  }
  function render() {
    q('#create-wizard-error').textContent = '';
    q('#create-wizard-position').textContent = `ขั้น ${step} จาก 6 · ${names[step-1]}`;
    q('#create-wizard-steps').innerHTML = names.map((name,index)=>`<span class="${index+1===step?'active':''}" aria-label="ขั้น ${index+1} ${name}"></span>`).join('');
    const panel = q('#create-wizard-body');
    if (step === 1) panel.innerHTML = `<h3>อยากสร้างอะไร</h3><p>เลือกประเภทงานที่จะทำ</p><div class="create-wizard-grid">${Object.entries(kinds).map(([id,info])=>`<button type="button" class="create-wizard-option" data-wizard-kind="${id}" aria-pressed="${kind===id}">${info.label}</button>`).join('')}</div>`;
    if (step === 2) {
      const main = def().main;
      const label = kind==='product'?'ลิงก์สินค้า Shopee':kind==='drama'?'ชื่อเรื่องละคร':'หัวข้อคลิป';
      panel.innerHTML = `<h3>${label}</h3><p>ค่าที่ใส่จะใช้กับงานใหม่นี้</p><label class="field">${label}<input id="wizard-main" value="${esc(value(main))}" autocomplete="off"></label>${kind==='drama'?`<label class="field">จำนวนตอน <output id="wizard-episodes-value">${esc(value('#drama-episodes'))}</output><input id="wizard-episodes" type="range" min="${esc(original('#drama-episodes')?.min||1)}" max="${esc(original('#drama-episodes')?.max||10)}" value="${esc(value('#drama-episodes'))}"></label>`:''}`;
    }
    if (step === 3) {
      const speaker = formPanel()?.querySelector('[data-storytelling] [data-telling="mode"]');
      panel.innerHTML = `<h3>ใครเป็นคนพูดในคลิป</h3>${speaker?`<label class="field">วิธีเล่า<select id="wizard-speaker">${[...speaker.options].map(item=>`<option value="${esc(item.value)}" ${item.value===speaker.value?'selected':''}>${esc(item.textContent)}</option>`).join('')}</select></label>`:'<p>ใช้วิธีเล่าและเสียงที่เลือกไว้ในฟอร์มของงานนี้</p>'}`;
    }
    if (step === 4) {
      const scene = original(def().scenes);
      const sceneInput = scene?.type==='range'
        ? `<input id="wizard-scenes" type="range" min="${esc(scene.min)}" max="${esc(scene.max)}" value="${esc(scene.value)}"><output id="wizard-scenes-value">${esc(scene.value)}</output>`
        : `<select id="wizard-scenes">${optionList(def().scenes)}</select>`;
      panel.innerHTML = `<h3>ภาพและวิดีโอ</h3><label class="field">สร้างภาพด้วย<select id="wizard-provider">${optionList(def().provider)}</select></label><label class="field">สร้างวิดีโอด้วย<select id="wizard-video">${optionList(def().video)}</select></label>${scene?`<label class="field">${kind==='long'?'จำนวนภาพ':'จำนวนฉาก'} ${sceneInput}</label>`:''}<p id="wizard-video-warning" role="status"></p>`;
      refreshVideoWarning();
    }
    if (step === 5) {
      const choice = audio();
      const toggles = [['subtitle','คำบรรยาย',choice?.subtitle],['music','เพลงพื้นหลัง',choice?.music],['cover','ปกด้วย AI',extraControl('cover')?.checked],['presenter','ผู้บรรยาย',extraControl('presenter')?.checked],['green','กรีนสกรีน',extraControl('green')?.checked],['intro','อินโทร',extraControl('intro')?.checked]];
      panel.innerHTML = `<h3>เสียงและการตกแต่ง</h3>${choice?`<label class="field">เสียงหลัก<select id="wizard-audio"><option value="api" ${choice.mode==='api'?'selected':''}>เสียงพากย์ AI</option><option value="flow_original" ${choice.mode==='flow_original'?'selected':''}>เสียงต้นฉบับจากคลิป</option><option value="none" ${choice.mode==='none'?'selected':''}>ไม่มีเสียงหลัก</option></select></label>`:'<p>ใช้งานเสียงตามตัวเลือกเดิม</p>'}<div class="create-wizard-grid">${toggles.filter(([key])=>key==='subtitle'||key==='music'||extraControl(key)).map(([key,label,checked])=>`<label class="create-wizard-switch"><input type="checkbox" data-wizard-extra="${key}" ${checked?'checked':''} ${extraControl(key)?.disabled?'disabled':''}>${label}</label>`).join('')}</div><p>ค่าเหล่านี้มีผลกับงานใหม่ งานในคิวใช้ค่าที่บันทึกไว้ตอนเพิ่ม</p>`;
    }
    if (step === 6) {
      const sys = ui.state?.system || {};
      const voice = audio()?.mode==='api';
      panel.innerHTML = `<h3>ตรวจแล้วเริ่ม</h3><p><b>${def().label}</b> · ${esc(value(def().main))}</p><ul><li>${sys.extension_compatible?'ส่วนเสริม Chrome พร้อมและรุ่นตรงกัน':'โปรดตรวจส่วนเสริม Chrome และรุ่นที่ใช้อยู่'}</li>${voice?`<li>${sys.voice_configured && sys.voice_reference_configured?'เสียงพากย์ AI พร้อม':'ตั้งค่าเสียงพากย์ AI และเสียงต้นแบบก่อนเริ่ม'}</li>`:''}${audio()?.subtitle?`<li>${sys.subtitle_connected?'เชื่อมบริการคำบรรยายแล้ว':'ตรวจการเชื่อมต่อบริการคำบรรยายก่อนเริ่ม'}</li>`:''}</ul><p>ก่อนเริ่ม ให้เข้าสู่ระบบ ChatGPT ใน Chrome ตัวที่ติดตั้งส่วนเสริมไว้${['google_flow','flow'].includes(value(def().video))?' และเข้าสู่ระบบ Google Flow ด้วย':''}</p><p>ระบบจะใช้การตรวจสอบและข้อความแจ้งก่อนเริ่มงานตามฟอร์มเดิม</p>`;
    }
    q('[data-wizard-back]').hidden = step===1;
    q('[data-wizard-full]').hidden = step===1;
    q('[data-wizard-queue]').hidden = step!==6;
    q('[data-wizard-next]').textContent = step===6?'เริ่มสร้างเลย':'ถัดไป';
    const sys = ui.state?.system || {};
    const ready = sys.extension_compatible === true && (!audio()?.subtitle || sys.subtitle_connected === true)
      && (audio()?.mode !== 'api' || sys.voice_configured === true && sys.voice_reference_configured === true);
    q('[data-wizard-next]').disabled = step===6 && !ready;
    q('[data-wizard-queue]').disabled = step===6 && !ready;
  }
  function refreshVideoWarning() {
    const speaker = formPanel()?.querySelector('[data-storytelling] [data-telling="mode"]')?.value;
    const video = q('#wizard-video')?.value || value(def().video);
    const unsupported = ['solo','dialogue'].includes(speaker) && !['google_flow','meta_ai'].includes(video);
    const warning = q('#wizard-video-warning');
    if (warning) warning.textContent = unsupported?'ตัวละครพูดเองหรือสนทนาต้องใช้ Google Flow หรือ Meta AI':'';
    return unsupported;
  }
  function canAdvance() {
    if (step===2) {
      const text = value(def().main).trim();
      if (!text) {q('#create-wizard-error').textContent='กรุณากรอกเนื้อหาก่อน';return false;}
      if (kind==='product') {try {const url=new URL(text);if (!['shopee.co.th','s.shopee.co.th'].includes(url.hostname.toLowerCase())) throw Error();}catch {q('#create-wizard-error').textContent='กรุณาใช้ลิงก์ shopee.co.th หรือ s.shopee.co.th';return false;}}
    }
    if (step===4 && refreshVideoWarning()) {q('#create-wizard-error').textContent='เลือก Google Flow หรือ Meta AI สำหรับโหมดตัวละครพูด';return false;}
    return true;
  }
  function submit(queue) {
    const button=original(def().submit);
    if (!button) {q('#create-wizard-error').textContent='ยังไม่พบปุ่มเริ่มงานของประเภทนี้';return;}
    if (button.disabled) {q('#create-wizard-error').textContent='ยังเริ่มงานไม่ได้ กรุณาตรวจความพร้อมในฟอร์มเต็ม';return;}
    const queueOnly=original(`#${kind}-queue-only`);
    if (queueOnly) setCheckbox(queueOnly,queue);
    dialog.close();
    if (queue && kind==='drama') original('#enqueue-drama-series')?.click();
    else button.click();
  }
  entry.addEventListener('click',()=>{kind='story';step=1;render();dialog.showModal();});
  dialog.addEventListener('click',event=>{
    const target=event.target;
    if (target.closest('[data-wizard-close]')) {dialog.close();return;}
    const choose=target.closest('[data-wizard-kind]');
    if (choose) {kind=choose.dataset.wizardKind;step=2;render();q('#wizard-main')?.focus();return;}
    if (target.closest('[data-wizard-back]')) {step=Math.max(1,step-1);render();return;}
    if (target.closest('[data-wizard-full]')) {dialog.close();showPage(def().page);return;}
    if (target.closest('[data-wizard-queue]')) {if (canAdvance()) submit(true);return;}
    if (target.closest('[data-wizard-next]')) {if (!canAdvance()) return;if (step===6) submit(false);else {step++;render();} }
  });
  dialog.addEventListener('input',event=>{
    const target=event.target;
    if (target.id==='wizard-main') setField(def().main,target.value);
    if (target.id==='wizard-scenes') {setField(def().scenes,target.value);const output=q('#wizard-scenes-value');if(output)output.textContent=target.value;}
    if (target.id==='wizard-episodes') {setField('#drama-episodes',target.value);q('#wizard-episodes-value').textContent=target.value;}
  });
  dialog.addEventListener('change',event=>{
    const target=event.target;
    if (target.id==='wizard-provider') setField(def().provider,target.value);
    if (target.id==='wizard-video') {setField(def().video,target.value);refreshVideoWarning();}
    if (target.id==='wizard-scenes') setField(def().scenes,target.value);
    if (target.id==='wizard-speaker') {const speaker=formPanel()?.querySelector('[data-storytelling] [data-telling="mode"]');if(speaker){speaker.value=target.value;speaker.dispatchEvent(new Event('change',{bubbles:true}));}}
    if (target.id==='wizard-audio' && audio()) window.setMediaAudioChoice?.(kind,{...audio(),mode:target.value});
    const extra=target.dataset.wizardExtra;
    if (extra==='subtitle'||extra==='music') {const choice=audio();if(choice) window.setMediaAudioChoice?.(kind,{...choice,[extra]:target.checked});}
    else if (extra) setCheckbox(extraControl(extra),target.checked);
  });
})();
