/* Local cover editor. No generation request, polling or automatic overwrite. */
(() => {
  const dialog = document.createElement('dialog');
  dialog.className = 'clip-cover-dialog';
  dialog.setAttribute('aria-labelledby', 'clip-cover-title');
  dialog.innerHTML = `<header><div><span class="eyebrow">สร้างและแก้ปก</span><h2 id="clip-cover-title">แก้ปกเอง หรือสร้างปกใหม่ด้วย AI</h2></div><button class="button ghost" data-cover-close aria-label="ปิดหน้าปก">✕</button></header>
    <p class="cover-hint">แก้ปกเองใช้ภาพที่มีอยู่ ไม่ใช้เครดิต AI • ปุ่มสร้างปกใหม่ด้วย AI ใช้โควตาสร้างภาพ • ทั้งสองแบบไม่สร้างวิดีโอใหม่</p>
    <div class="cover-editor-grid"><section class="cover-preview-box"><img alt="พรีวิวปกคลิป" hidden><p>กำลังเตรียมพรีวิว…</p></section>
    <section class="cover-controls"><label class="field"><span>ข้อความปก <small data-cover-count></small></span><input data-cover-headline placeholder="วลีสั้นที่ชวนติดตาม"><small>ปกทำเองสูงสุด 60 ตัวอักษร • ปก AI สูงสุด 40 ตัวอักษร • เว้นว่างเพื่อให้ AI ออกแบบจากชื่อคลิป</small></label>
    <div class="cover-alternatives" aria-label="ตัวเลือกข้อความปก"></div>
    <label class="field"><span>คำที่ต้องการเน้นสี</span><input data-cover-emphasis maxlength="40" placeholder="ต้องเป็นคำที่อยู่ในข้อความปก"></label>
    <div class="cover-options"><label class="field"><span>รูปแบบ</span><select data-cover-theme><option value="bold">ตัวใหญ่ชัด</option><option value="mystery">ลึกลับชวนดู</option><option value="product">สินค้าเด่น</option><option value="romance">โรแมนติก</option></select></label>
    <label class="field"><span>ตำแหน่งข้อความ</span><select data-cover-position><option value="top">ด้านบน</option><option value="center">ตรงกลาง</option><option value="bottom">ด้านล่าง</option></select></label></div>
    <label class="field"><span>เลือกภาพฉาก • เลือกภาพที่ตัวแบบเด่นและมีพื้นที่วางข้อความ</span></label><div class="cover-images"></div>
    </section></div><p class="cover-editor-status" role="status" aria-live="polite"></p>
    <footer><button class="button secondary" data-cover-preview>ดูพรีวิวจริง</button><button class="button ghost" data-cover-download>ดาวน์โหลดปกที่บันทึก</button><button class="button primary" data-cover-save>บันทึกปก</button><button class="button secondary" data-cover-ai-recover hidden>ดึงปกเดิมจากเว็บ</button><button class="button secondary" data-cover-ai>สร้างปกใหม่ด้วย AI</button><button class="button ghost" data-cover-ai-cancel hidden>ยกเลิกปก AI</button></footer>`;
  document.body.append(dialog);
  const q = s => dialog.querySelector(s);
  let editor = null, busy = false, epoch = 0;
  const status = (text, error = false) => { q('.cover-editor-status').textContent = text; q('.cover-editor-status').classList.toggle('error', error); };
  // Unicode code points, matching Python len(): astral emoji count once;
  // combining marks and emoji components each retain their own code point.
  const headlineCount = text => Array.from(String(text || '').trim()).length;
  const updateHeadlineCount = () => {
    const count=headlineCount(q('[data-cover-headline]').value);
    q('[data-cover-count]').textContent=`${count}/60 • AI ${count}/40`;
  };
  function coverRecoveryState(state = {}) {
    const preparation = state.preparation_state || {}, detail = state.send_diagnostics || {};
    const sent = ['accepted','unconfirmed'].includes(state.send_state)
      || ['dispatch_completed','trusted_click_seen','release_on_send_target'].some(key=>detail[key]===true)
      || ['pressed','released','release_uncertain'].includes(detail.gesture_phase)
      || Boolean(state.result_proof) || state.collector_state?.owned===true
      || Number(state.collector_state?.candidates || 0)>0;
    const unsent = preparation.stage==='image_tool' && preparation.request_id===state.request_id
      && Boolean(state.request_id) && preparation.not_dispatched===true && !sent;
    return {unsent, collect:sent || !state.preparation_state};
  }
  function updateAIControls() {
    const state=editor?.ai_cover_state || {}, recovery=coverRecoveryState(state);
    const review=state.phase==='needs_review' && Boolean(state.request_id);
    q('[data-cover-ai]').textContent=review && recovery.unsent?'ทำปกต่อ':'สร้างปกใหม่ด้วย AI';
    q('[data-cover-ai-recover]').hidden=!review || !recovery.collect || recovery.unsent;
    q('[data-cover-ai-cancel]').hidden=!state.request_id || ['ready','needs_review','cancelled'].includes(state.phase);
  }
  function settings() {
    return { ...editor.settings, headline: q('[data-cover-headline]').value.trim(),
      emphasis: q('[data-cover-emphasis]').value.trim(), theme: q('[data-cover-theme]').value,
      position: q('[data-cover-position]').value };
  }
  function changed() {
    updateHeadlineCount();
    status('มีการแก้ไข • กดดูพรีวิวจริงเพื่อตรวจตำแหน่งก่อนบันทึก');
  }
  async function run(action) {
    if (!editor || busy) return;
    if (action !== 'download_library_cover' && headlineCount(q('[data-cover-headline]').value)>60) {
      status('ปกทำเองรับข้อความได้ไม่เกิน 60 ตัวอักษร • กรุณาย่อข้อความก่อนบันทึก',true);return;
    }
    const ticket = epoch;
    busy = true;
    dialog.classList.add('is-working');
    dialog.querySelectorAll('input,select,button:not([data-cover-close])').forEach(el => { el.disabled = true; });
    status(action === 'save_library_cover' ? 'กำลังบันทึกปกใหม่…' : action === 'download_library_cover' ? 'กำลังคัดลอกปกไป Downloads…' : 'กำลังจัดข้อความและพรีวิว…');
    try {
      const result = await postAction(action, { item_id: editor.item_id, settings: settings(), revision: editor.revision });
      if (ticket !== epoch || !dialog.open) return;
      if (result.preview) {
        q('.cover-preview-box img').src = result.preview;
        q('.cover-preview-box img').hidden = false;
        q('.cover-preview-box p').hidden = true;
        status(`พรีวิวจริง ${editor.aspect_ratio} • ตรวจว่าไม่บังใบหน้าหรือสินค้าก่อนบันทึก`);
      } else if (result.revision) {
        editor.revision = result.revision;
        const item = libraryItem(editor.item_id);
        if (item) { item.cover_url = `/api/desktop/media?item_id=${encodeURIComponent(editor.item_id)}&kind=cover&v=${encodeURIComponent(result.revision)}`; }
        status('บันทึกปกใหม่แล้ว • ปกเดิมยังอยู่ในโฟลเดอร์ covers • วิดีโอและเสียงไม่เปลี่ยน');
        const visiblePreview = document.querySelector('#detail-modal .detail-video');
        if (visiblePreview && item) visiblePreview.poster = item.cover_url;
      } else if (result.path) status(`ดาวน์โหลดแล้ว: ${result.path}`);
    } catch (error) { if (ticket === epoch) status(error.message, true); }
    finally {
      busy = false;
      dialog.classList.remove('is-working');
      dialog.querySelectorAll('input,select,button').forEach(el => { el.disabled = false; });
    }
  }
  window.openClipCover = async itemId => {
    if (busy) return;
    const ticket = ++epoch;
    editor = null;
    q('.cover-preview-box img').hidden = true;
    q('.cover-preview-box p').hidden = false;
    q('.cover-preview-box p').textContent = 'กำลังอ่านภาพที่บันทึกไว้…';
    dialog.showModal();
    status('กำลังเปิดข้อมูลปก…');
    try {
      const result = await postAction('get_cover_editor', { item_id: itemId });
      if (ticket !== epoch || !dialog.open) return;
      editor = result.editor;
      updateAIControls();
      q('[data-cover-headline]').value = editor.settings.headline;
      q('[data-cover-emphasis]').value = editor.settings.emphasis;
      q('[data-cover-theme]').value = editor.settings.theme;
      q('[data-cover-position]').value = editor.settings.position;
      updateHeadlineCount();
      const alternatives = q('.cover-alternatives'); alternatives.replaceChildren();
      for (const headline of [editor.settings.headline, ...editor.settings.alternatives]) {
        const button = document.createElement('button'); button.className = 'button ghost'; button.type = 'button';
        button.textContent = headline; button.onclick = () => { q('[data-cover-headline]').value = headline; q('[data-cover-emphasis]').value = ''; changed(); };
        alternatives.append(button);
      }
      const images = q('.cover-images'); images.replaceChildren();
      for (const image of editor.images) {
        const button = document.createElement('button'); button.type = 'button'; button.setAttribute('aria-label', `เลือกภาพฉาก ${image.index}`);
        button.setAttribute('aria-pressed', String(image.index === editor.settings.scene_index));
        const thumbnail = document.createElement('img'); thumbnail.src = image.url; thumbnail.alt = `ฉาก ${image.index}`;
        const label = document.createElement('span'); label.textContent = `ฉาก ${image.index}`; button.append(thumbnail, label);
        button.onclick = () => { editor.settings.scene_index = image.index; images.querySelectorAll('button').forEach(el => el.setAttribute('aria-pressed', String(el === button))); changed(); };
        images.append(button);
      }
      await run('preview_library_cover');
      if(ticket===epoch && dialog.open && editor){
        const state=editor.ai_cover_state || {};
        if(['preparing','recovering'].includes(state.phase))status(state.message || 'วิดีโอเสร็จแล้ว • กำลังเตรียมสร้างปก');
        else if(state.phase==='needs_review' && coverRecoveryState(state).unsent)
          status('ยังไม่ส่งคำขอสร้างปก • กดทำปกต่อเพื่อเตรียมใหม่ • วิดีโอเดิมยังอยู่');
      }
    } catch (error) { if (ticket === epoch) status(error.message, true); }
  };
  q('[data-cover-close]').onclick = () => dialog.close();
  dialog.addEventListener('close', () => { ++epoch; editor = null; });
  dialog.querySelectorAll('input,select').forEach(el => el.addEventListener('input', changed));
  q('[data-cover-preview]').onclick = () => run('preview_library_cover');
  q('[data-cover-save]').onclick = () => run('save_library_cover');
  q('[data-cover-download]').onclick = () => run('download_library_cover');
  async function startAICover(collectOnly=false){
    if(!editor || busy)return;
    if(!collectOnly && headlineCount(q('[data-cover-headline]').value)>40){
      status('ปก AI รับข้อความได้ไม่เกิน 40 ตัวอักษร • ย่อข้อความหรือเว้นว่างให้ AI ออกแบบจากชื่อคลิป • ปกทำเองยังรับได้ 60 ตัวอักษร',true);return;
    }
    busy=true;const ticket=epoch;
    try{
      const result=await postAction(collectOnly?'ai_cover_recover':'ai_cover_regenerate',{
        item_id:editor.item_id,request_id:editor.ai_cover_state?.request_id,settings:settings()});
      if(ticket!==epoch || !dialog.open)return;
      editor.ai_cover_state=result.request;updateAIControls();
      status(collectOnly?'กำลังดึงปกจากแท็บเดิม • ไม่ส่งพรอมต์และไม่สร้างภาพซ้ำ':'เริ่มเตรียมสร้างปกแล้ว • ใช้ AI เดิมและภาพที่เลือก • วิดีโอไม่เปลี่ยน');
      while(dialog.open && ticket===epoch){
        await new Promise(resolve=>setTimeout(resolve,2500));
        if(!dialog.open || ticket!==epoch)break;
        const current=await postAction('ai_cover_status',{request_id:result.request.request_id});
        if(ticket!==epoch || !dialog.open)return;
        editor.ai_cover_state=current.request;updateAIControls();status(current.request.message || 'กำลังเตรียมปก AI');
        if(['ready','needs_review','cancelled'].includes(current.request.phase)){
          if(current.request.phase==='ready'){
            const latest=await postAction('get_cover_editor',{item_id:editor.item_id});
            if(ticket!==epoch || !dialog.open)return;
            editor.revision=latest.editor.revision;
            const url=`/api/desktop/media?item_id=${encodeURIComponent(editor.item_id)}&kind=cover&v=${encodeURIComponent(editor.revision)}`;
            q('.cover-preview-box img').src=url;q('.cover-preview-box img').hidden=false;q('.cover-preview-box p').hidden=true;
            const item=libraryItem(editor.item_id);if(item)item.cover_url=url;
            const preview=document.querySelector('#detail-modal .detail-video');if(preview)preview.poster=url;
            status('บันทึกปกแล้ว • แสดงภาพที่บันทึกในโปรแกรม • กดเริ่มคิวเพื่อทำงานต่อได้');
          }
          break;
        }
      }
    }catch(error){if(ticket===epoch)status(error.message,true);}finally{busy=false;}
  }
  q('[data-cover-ai]').onclick=()=>startAICover(false);
  q('[data-cover-ai-recover]').onclick=()=>startAICover(true);
  q('[data-cover-ai-cancel]').onclick=async()=>{
    const rid=editor?.ai_cover_state?.request_id;if(!rid)return;
    try{await postAction('ai_cover_cancel',{request_id:rid});status('ยกเลิกปกแล้ว • เก็บวิดีโอและปกเดิมไว้');q('[data-cover-ai-cancel]').hidden=true;}
    catch(error){status(error.message,true);}
  };
})();
