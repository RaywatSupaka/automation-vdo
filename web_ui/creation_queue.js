/* Shared desktop FIFO UI and saved-cover navigation; never controls AI tabs. */
(() => {
  const esc = escapeHtml;
  const labels = {queued:'รอทำงาน', running:'กำลังทำ', completed:'สำเร็จ', failed:'ต้องตรวจสอบ', cancelled:'ยกเลิกแล้ว'};
  const kinds = {product:'คลิปสินค้า', story:'STORY SHORTS', drama:'ละครสั้น'};
  const kindLabel = row => row.long_video ? 'คลิปยาว' : kinds[row.mode || 'story'] || 'งานเดิม';
  const subtitleEnabled = row => {
    const choices = row.settings?.audio_choices;
    if (typeof choices?.subtitle === 'boolean') return choices.subtitle;
    if (typeof row.settings?.subtitle_enabled === 'boolean') return row.settings.subtitle_enabled;
    return row.subtitle === true;
  };
  let listSignature = '';
  let requestId = '';
  let editing = '';
  let queueBusy = false;
  let oldSignature = '';
  let confirmation = null;
  const modal = document.createElement('dialog');
  modal.className = 'modal'; modal.id = 'creation-editor';
  modal.setAttribute('aria-labelledby', 'creation-editor-title');
  modal.innerHTML = `<form class="modal-card cq-modal-card" id="creation-form">
    <span class="eyebrow">CREATION QUEUE</span><h2 id="creation-editor-title">เพิ่มลิงก์สินค้าเข้าคิว</h2>
    <p id="creation-editor-description"></p>
    <label for="creation-values" id="creation-value-label">ลิงก์สินค้า • หนึ่งลิงก์ต่อบรรทัด</label>
    <textarea id="creation-values" required maxlength="40000" placeholder="https://s.shopee.co.th/…"></textarea>
    <p class="cq-batch-count" id="creation-batch-count" role="status" aria-live="polite"></p>
    <p class="cq-batch-progress" id="creation-batch-progress" role="status" aria-live="polite" hidden></p>
    <details class="cq-product-settings" id="creation-product-settings">
      <summary><span><b>ตั้งค่าคลิปสินค้า</b><small>ใช้ชุดเดียวกันกับทุกลิงก์ • เปิดเมื่ออยากปรับค่า</small></span><strong id="creation-product-settings-summary"></strong></summary>
      <div class="cq-product-settings-grid">
        <label>สร้างภาพด้วย<select id="creation-product-provider"><option value="chatgpt">ChatGPT Web</option><option value="gemini">Gemini Web</option></select></label>
        <label class="field" id="creation-product-model-field">โมเดล AI Web<select id="creation-product-model"></select></label>
        <label>สร้างวิดีโอด้วย<select id="creation-product-video-provider"><option value="flow">Google Flow</option><option value="meta_ai">Meta AI • แนวตั้ง</option></select></label>
        <label>จำนวนฉาก<select id="creation-product-scenes"></select></label>
      </div>
      <fieldset class="cq-product-script"><legend>แนวบทของทุกคลิป</legend>
        <div class="cq-product-script-options" role="radiogroup" aria-label="แนวบทสินค้า">
          <label><input type="radio" name="creation-product-script" value="standard"><span><b>แบบเดิม</b><small>เล่าเรื่องและนำเสนอสินค้า</small></span></label>
          <label><input type="radio" name="creation-product-script" value="story_first_review"><span><b>เล่าเรื่องก่อนรีวิว</b><small>เชื่อมเหตุการณ์กับสินค้าอย่างเป็นธรรมชาติ</small></span></label>
          <label><input type="radio" name="creation-product-script" value="short_film_ad"><span><b>หนังสั้นโฆษณา</b><small>เรื่องนำ • สินค้าตาม • ปิดด้วยตะกร้าได้</small></span></label>
        </div>
        <div class="cq-product-film-options" id="creation-product-film-options" hidden>
          <label>โทนหนังสั้น<select id="creation-product-film-genre"><option value="auto">ให้ AI เลือก</option><option value="warm">อบอุ่น</option><option value="comedy">ตลก</option><option value="twist">หักมุม</option></select></label>
          <label class="cq-inline-check"><input type="checkbox" id="creation-product-film-cta"><span>ชวนดูสินค้าที่ตะกร้าตอนจบ</span></label>
        </div>
      </fieldset>
      <label class="cq-product-direction">แนวทางร่วมสำหรับทุกสินค้า <small>ไม่บังคับ • ระบุเหตุการณ์/สิ่งที่อยากเน้น</small><textarea id="creation-product-direction" rows="3" placeholder="เว้นว่างให้ AI คิดแนวทางจากข้อมูลสินค้า"></textarea></label>
      <details id="creation-cast-options"><summary>นายแบบ / นางแบบและเสื้อผ้า • เลือกเพิ่มเติม</summary>
      <label class="cq-product-cast-field">ตัวละครจากคลัง<select id="creation-product-cast"><option value="">ไม่เลือก • ให้ AI วางตัวละคร</option></select><small>ถ้าเลือก จะใช้ตัวละครนี้กับสินค้าทั้งชุด</small></label>
      <label class="cq-product-cast-field">ชุดของตัวละคร<select id="creation-product-outfit-mode"><option value="auto">ให้ AI เลือกชุดสุภาพ</option><option value="product">สวมเสื้อผ้าที่เป็นสินค้า</option><option value="saved">ใช้รูปชุดที่บันทึกกับตัวละคร</option></select><small>ใช้ตัวเลือกเดียวกันกับสินค้าทั้งชุด • โหมดรูปชุดต้องเลือกตัวละครที่มีรูปชุด</small></label>
      </details>
    </details>
    <details class="cq-product-extra-settings" id="creation-product-extra-settings"><summary>เสียงและตัวเลือกเสริม</summary><div id="creation-product-extra-content"></div></details>
    <label class="cq-check" id="creation-recapture-wrap" hidden><input type="checkbox" id="creation-recapture">เปลี่ยนเป็นค่าเสียง ซับ และการเรนเดอร์ปัจจุบัน</label>
    <p id="creation-editor-settings"></p><div class="cq-inline-error" id="creation-editor-error" role="alert"></div>
    <div class="cq-buttons"><button type="button" class="button ghost" id="creation-editor-close">ยกเลิก</button><button type="submit" class="button primary" id="creation-editor-submit">เพิ่มลงคิว</button></div>
  </form>`;
  document.body.append(modal);
  const productCreativePicker=window.mountCreativeRadioPicker?.({host:modal.querySelector('.cq-product-script'),id:'creation-product-style',radioName:'creation-product-script',grid:'.cq-product-script-options'});
  const queueCreativeHost=document.createElement('div');queueCreativeHost.className='creative-queue-pickers';queueCreativeHost.hidden=true;
  $('#creation-editor-settings').before(queueCreativeHost);
  const queueProductPicker=window.mountCreativePicker?.({host:queueCreativeHost,kind:'product',id:'creation-saved-product-style',value:'standard',label:'แนวบทของงานนี้'});
  const queueStoryPicker=window.mountCreativePicker?.({host:queueCreativeHost,kind:'story',id:'creation-saved-story-structure',value:'legacy',label:'โครงเรื่องของงานนี้'});
  const confirm = document.createElement('dialog');
  confirm.className = 'modal'; confirm.id = 'creation-confirm';
  confirm.setAttribute('aria-labelledby', 'creation-confirm-title');
  confirm.innerHTML = `<div class="modal-card cq-modal-card"><h2 id="creation-confirm-title"></h2><p class="cq-confirm-message" id="creation-confirm-message"></p><div class="cq-buttons"><button type="button" class="button ghost" id="creation-confirm-close">กลับ</button><button type="button" class="button danger" id="creation-confirm-accept">ยืนยัน</button></div></div>`;
  document.body.append(confirm);
  function askQueueAction(action, title, message, label, payload={}) {
    if (queueBusy || confirm.open) return;
    confirmation = {action, payload, trigger:document.activeElement};
    $('#creation-confirm-title').textContent = title;
    $('#creation-confirm-message').textContent = message;
    $('#creation-confirm-accept').textContent = label;
    confirm.showModal(); $('#creation-confirm-close').focus();
  }
  $('#creation-confirm-close').addEventListener('click', () => confirm.close());
  confirm.addEventListener('close', () => {const previous = confirmation; confirmation = null; previous?.trigger?.focus?.();});
  $('#creation-confirm-accept').addEventListener('click', async () => {
    const target = confirmation; if (!target || queueBusy) return;
    confirmation = null; confirm.close();
    const result = await command(target.action, target.payload, target.action === 'creation_remove_old'
      ? 'ลบรายการงานเก่าจากหน้าคิวแล้ว • รูป เสียง คลิป และประวัติในไฟล์ยังอยู่'
      : target.action === 'creation_cancel_all'
      ? 'พักคิวและส่งคำขอยกเลิกทั้งหมดแล้ว • เก็บ Job และไฟล์เดิมไว้'
      : 'ล้างแคชสถานะค้างแล้ว • ไม่ลบไฟล์งาน');
    if (result && target.action === 'creation_clear_stuck_state') {
      // Clear presentation state only AFTER the engine confirms it is idle.
      ui.progressWasActive = false; ui.progressType = ''; ui.progressJobId = '';
      dismissProgressResult();
      if ($('#automation-error-modal').open) $('#automation-error-modal').close();
      await poll(true);
    }
    target.trigger?.focus?.();
  });
  const storyButton = document.createElement('button');
  storyButton.type = 'button'; storyButton.className = 'button secondary'; storyButton.id = 'enqueue-story';
  storyButton.textContent = '＋ เพิ่มเรื่องนี้ลงคิว';
  $('#create-story')?.before(storyButton);
  $('#open-story-batch b').textContent = 'เพิ่มหลายเรื่องลงคิว';

  function productSettings() {
    const provider=$('#creation-product-provider').value;
    const style=document.querySelector('[name="creation-product-script"]:checked')?.value || 'standard';
    const audio=window.mediaAudioChoice?.('product-batch') || window.mediaAudioChoice?.('product') || {};
    return {provider, ai_web_model:selectedAiModel('#creation-product-provider','#creation-product-model'),
      video_provider:$('#creation-product-video-provider').value, video_generation_mode:$('#creation-product-video-provider').value,
      scene_count:Number($('#creation-product-scenes').value),
      product_script_options:window.creativeProductOptions?window.creativeProductOptions(style,$('#creation-product-film-genre').value,$('#creation-product-film-cta').checked):style==='short_film_ad'
        ? {version:2,style,genre:$('#creation-product-film-genre').value,ending_cta:$('#creation-product-film-cta').checked}
        : {version:1,style}, product_story_text:$('#creation-product-direction').value.trim(),
      product_cast_id:$('#creation-product-cast').value, product_outfit_mode:$('#creation-product-outfit-mode').value,
      subtitle:Boolean(audio.subtitle), audio_choices:audio};
  }
  function updateProductBatchSettings() {
    const video=$('#creation-product-video-provider').value==='meta_ai'?'Meta AI':'Google Flow';
    const provider=$('#creation-product-provider').value==='gemini'?'Gemini Web':'ChatGPT Web';
    const model=$('#creation-product-model').selectedOptions[0]?.textContent?.trim();
    const scenes=Number($('#creation-product-scenes').value||3);
    const script=document.querySelector('[name="creation-product-script"]:checked')?.value||'standard';
    const scriptLabel=window.creativeLabel?.('product',script)||{standard:'แบบเดิม',story_first_review:'เล่าเรื่องก่อนรีวิว',short_film_ad:'หนังสั้นโฆษณา'}[script];
    const audio=window.mediaAudioChoice?.('product-batch');
    const audioLabel=audio?`${audio.mode==='api'?'เสียงพากย์':audio.mode==='none'?'ไม่มีเสียง':'เสียงต้นฉบับ'}${audio.subtitle?' + ซับ':' ไม่มีซับ'}`:'';
    const cast=$('#creation-product-cast').selectedOptions[0]?.textContent;
    const outfit=$('#creation-product-outfit-mode').selectedOptions[0]?.textContent;
    $('#creation-product-settings-summary').textContent=[`${provider}${model?` / ${model}`:''}`,video,`${scenes} ฉาก`,scriptLabel,audioLabel,cast&&$('#creation-product-cast').value?`ตัวละคร ${cast}`:'',outfit].filter(Boolean).join(' • ');
    $('#creation-product-film-options').hidden=script!=='short_film_ad';
  }
  function compactProductExtras() {
    const target=$('#creation-product-extra-content');
    for(const node of [$('#presenter-choice-product-batch'),modal.querySelector('.media-audio-controls')])
      if(node&&node.parentElement!==target)target.append(node);
  }
  function updateBatchCount() {
    const values=$('#creation-values').value.split(/\r?\n/).map(value=>value.trim()).filter(Boolean);
    const seen=new Set();let duplicates=0;
    for(const value of values){if(seen.has(value))duplicates++;else seen.add(value);}
    $('#creation-batch-count').textContent=editing?'แก้ไขรายการเดียว • ค่าตั้งเดิมจะคงไว้':`${seen.size} ลิงก์ไม่ซ้ำ${duplicates?` • ลิงก์ที่ซ้ำกัน ${duplicates} บรรทัดจะข้ามก่อนอ่านสินค้า`:''} • สูงสุด 10 บรรทัด`;
    $('#creation-batch-count').classList.toggle('invalid',values.length>10);
  }
  function copyProductCastOptions() {
    const source=$('#ps-cast'), target=$('#creation-product-cast'); if(!source||!target)return;
    const selected=target.value||$('#ps-use-cast')?.checked&&source.value||'';
    target.innerHTML='<option value="">ไม่เลือก • ให้ AI วางตัวละคร</option>';
    for(const option of [...source.options].filter(item=>item.value))target.append(new Option(option.textContent,option.value));
    target.value=[...target.options].some(option=>option.value===selected)?selected:'';
  }
  function queueCoverState(row, state) {
    const mode = row.mode || 'story';
    if (!['product','story','drama'].includes(mode) || !['queued','running','failed'].includes(row.status)) return null;
    const product = mode === 'product';
    if (!(product ? /^JOB-[A-Z0-9-]+$/ : /^STORY-[A-Z0-9-]+$/).test(row.job_id || '')) return null;
    const itemId = `${product ? 'product' : 'story'}:${row.job_id}`;
    // Library rows prove a ready, existing Final; Drama uses the Story library.
    const item = (state?.library || []).find(value => value.item_id === itemId && value.job_id === row.job_id);
    if (!item || !(Number(item.size_bytes) > 0)) return null;
    const cover = item.ai_cover_state || {};
    return {item_id:itemId, attention:['needs_review','cancelled'].includes(cover.phase),
      recovered:cover.phase === 'ready' && Boolean(cover.request_id) && item.cover_revision === cover.request_id
        && Boolean(item.cover_url) && String(row.error || '').startsWith('วิดีโอเสร็จแล้ว • พักคิวรอปก AI •')};
  }
  function openEditor(item = null) {
    if(window.productPreparationActive){toast('กำลังเตรียมสินค้าอยู่ • ดูความคืบหน้าที่แผงคิวก่อนเปิดชุดใหม่','info');return;}
    editing = item?.queue_id || '';
    requestId = globalThis.crypto?.randomUUID?.() || `queue-${Date.now()}-${Math.random()}`;
    $('#creation-editor-title').textContent = item ? 'แก้ไขรายการที่ยังไม่เริ่ม' : 'เพิ่มลิงก์สินค้าเข้าคิว';
    $('#creation-editor-description').textContent = item ? 'แก้ข้อความของรายการที่ยังไม่เริ่ม • ค่าที่บันทึกไว้จะไม่เปลี่ยน' : 'เพิ่มครั้งละ 1–10 ลิงก์ ตั้งค่าชุดเดียวให้ทุกสินค้า แล้วตรวจรายการก่อนเพิ่มลงคิว';
    $('#creation-value-label').textContent = item ? (item.mode === 'product' ? 'ลิงก์สินค้า' : 'หัวข้อเรื่องเล่า') : 'ลิงก์สินค้า • หนึ่งลิงก์ต่อบรรทัด';
    $('#creation-values').value = item ? item.link || item.topic || '' : $('#product-link').value.trim();
    $('#creation-values').maxLength = item ? 4000 : 40000;
    $('#creation-recapture-wrap').hidden = !item;
    $('#creation-recapture').checked = false;
    const provider = item?.provider || $('#product-provider').value;
    $('#creation-editor-settings').textContent = `${provider === 'gemini' ? 'Gemini Web' : 'ChatGPT Web'} • ${item ? 'ค่าที่บันทึกกับรายการนี้' : 'ค่าด้านล่างจะถูกบันทึกแยกกับทุกสินค้า'} • ไม่เปลี่ยนระหว่างรัน`;
    $('#creation-editor-submit').textContent = item ? 'บันทึกรายการ' : 'เพิ่มลงคิว';
    $('#creation-editor-error').textContent = '';
    $('#creation-batch-progress').textContent='';$('#creation-batch-progress').hidden=true;
    $('#creation-batch-progress').dataset.state='working';
    $('#creation-product-settings').hidden=Boolean(item);
    const sourceProvider=$('#product-provider')?.value||'chatgpt';
    $('#creation-product-provider').value=item?.provider||sourceProvider;
    fillAiModelSelect('#creation-product-provider','#creation-product-model',item?.ai_web_model||selectedAiModel('#product-provider','#product-model'));
    $('#creation-product-video-provider').value=item?.video_generation_mode||item?.video_provider||$('#product-video-provider')?.value||'flow';
    $('#creation-product-scenes').innerHTML=Array.from({length:13},(_,i)=>`<option value="${i+3}">${i+3} ฉาก</option>`).join('');
    $('#creation-product-scenes').value=String(item?.scene_count||$('#ps-count')?.value||3);
    const sourceStyle=document.querySelector('[name="ps-script-style"]:checked')?.value||'standard';
    const savedStyle=item?.settings?.product_script_options?.style||sourceStyle;
    document.querySelectorAll('[name="creation-product-script"]').forEach(input=>input.checked=input.value===savedStyle);
    productCreativePicker?.set(savedStyle);
    const productStory=item?.settings?.creative_context?.kind==='product_story';
    const plainStory=item?.mode==='story'&&!productStory&&!item?.long_video;
    queueCreativeHost.hidden=!item||(!productStory&&!plainStory);
    if(queueProductPicker){queueProductPicker.element.hidden=!productStory;queueProductPicker.set(item?.settings?.product_script_options?.style||'standard');}
    if(queueStoryPicker){queueStoryPicker.element.hidden=!plainStory;queueStoryPicker.set(item?.settings?.story_structure_options?.structure||'legacy');}
    if(item&&window.setGeneratedMusicChoice)window.setGeneratedMusicChoice('product-batch',item.settings?.generated_music_options);
    let film={};try{film=JSON.parse(localStorage.getItem('smartflow.product.short-film.v2')||'{}');}catch{}
    $('#creation-product-film-genre').value=film.genre||'auto';$('#creation-product-film-cta').checked=film.ending_cta!==false;
    $('#creation-product-direction').value=$('#ps-details')?.value||'';
    copyProductCastOptions();
    $('#creation-product-outfit-mode').value=item?.settings?.product_outfit_mode||$('#ps-outfit-mode')?.value||'auto';
    updateProductBatchSettings();updateBatchCount();
    window.preparePresenterQueue?.('product-batch', {editing:Boolean(item)});
    window.prepareAudioQueue?.(item);
    window.prepareGreenQueue?.(item);
    compactProductExtras();
    updateProductBatchSettings();
    $('#creation-product-settings').open=false;
    $('#creation-product-extra-settings').open=false;
    modal.showModal(); $('#creation-values').focus();
    if(!item)Promise.resolve(window.loadProductCastLibrary?.()).then(copyProductCastOptions).catch(()=>{});
  }
  let batchStatusTimer=0;
  window.addEventListener('smartflow:product-batch-progress',event=>{
    const {title='',detail='',state='working'}=event.detail||{};
    const text=[title,detail].filter(Boolean).join(' • ');
    const global=$('#creation-queue-batch-progress');global.hidden=false;global.dataset.state=state;global.textContent=text;
    clearTimeout(batchStatusTimer);
    if(state==='ready')batchStatusTimer=setTimeout(()=>{global.hidden=true;},12000);
    if(!modal.open||editing)return;
    const progress=$('#creation-batch-progress');progress.hidden=false;progress.dataset.state=state;
    progress.textContent=state==='error'?title:text;
    if(state==='working')$('#creation-editor-submit').textContent='กำลังเตรียมสินค้า…';
  });
  async function command(action, payload, message) {
    if (queueBusy) return null;
    queueBusy = true; window.renderCreationQueue?.(ui.state || {});
    try { const result = await postAction(action, payload); if (message) toast(message, 'success'); await poll(true); return result; }
    catch (error) { toast(error.message, 'error'); return null; }
    finally {queueBusy = false; window.renderCreationQueue?.(ui.state || {});}
  }
  $('#enqueue-product').addEventListener('click', () => openEditor());
  $('#queue-add-products').addEventListener('click', () => openEditor());
  $('#queue-add-stories').addEventListener('click', () =>
    $('#open-story-batch').dispatchEvent(new CustomEvent('click', {detail:{source:'creation_queue'}})));
  $('#creation-editor-close').addEventListener('click', () => modal.close());
  $('#creation-form').addEventListener('submit', async event => {
    event.preventDefault();
    const button = $('#creation-editor-submit'); if (button.disabled) return;
    const submittedWithDialogOpen=modal.open;
    button.disabled = true; $('#creation-editor-error').textContent = '';
    if(!editing)button.textContent='กำลังเตรียมสินค้า…';
    try {
      let result;
      if (editing) {
        const row = ui.state?.creation_queue?.items.find(item => item.queue_id === editing);
        const creative={};
        if(!queueCreativeHost.hidden&&queueProductPicker&&!queueProductPicker.element.hidden){
          const old=row?.settings?.product_script_options||{};
          creative.product_script_options=window.creativeProductOptions(queueProductPicker.get(),old.genre||'auto',old.ending_cta!==false);
        }
        if(!queueCreativeHost.hidden&&queueStoryPicker&&!queueStoryPicker.element.hidden){
          const structure=queueStoryPicker.get();creative.story_structure_options=structure==='legacy'?null:{version:1,structure};
        }
        result = await postAction('creation_edit', {queue_id:editing, value:$('#creation-values').value.trim(),
          provider:row?.provider, ...creative, use_current_settings:$('#creation-recapture').checked});
      } else {
        const entered = $('#creation-values').value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);
        if (!entered.length || entered.length > 10) throw new Error('เพิ่มได้ครั้งละ 1–10 บรรทัด');
        const values=[...new Set(entered)];
        const inputDuplicates=entered.length-values.length;
        result = await postAction('creation_enqueue', {...productSettings(), mode:'product', values, request_id:requestId, _batch_duplicate_count:inputDuplicates});
        if(inputDuplicates)window.dispatchEvent(new CustomEvent('smartflow:product-batch-progress',{detail:{title:'ข้ามลิงก์สินค้าที่ซ้ำ',detail:`อ่านเฉพาะ ${values.length} ลิงก์ที่ไม่ซ้ำ • ข้าม ${inputDuplicates} บรรทัด`,state:'ready'}}));
      }
      if(modal.open)modal.close();
      if(submittedWithDialogOpen)showPage('creation');
      toast(editing ? 'บันทึกรายการแล้ว' : `เพิ่ม ${result.queued} รายการ • ข้ามรายการซ้ำ ${result.duplicates || 0} • ${result.paused ? 'กดเริ่มคิวเมื่อพร้อม' : 'ต่อท้ายคิวแล้ว'}`, 'success');
      await poll();
    } catch(error) { $('#creation-editor-error').textContent = error.message; }
    finally { button.disabled = false; button.textContent=editing?'บันทึกรายการ':'เพิ่มลงคิว'; }
  });
  $('#creation-values').addEventListener('input',updateBatchCount);
  for(const selector of ['#creation-product-provider','#creation-product-video-provider','#creation-product-scenes','#creation-product-film-genre','#creation-product-film-cta'])$(selector).addEventListener('change',updateProductBatchSettings);
  document.querySelectorAll('[name="creation-product-script"]').forEach(input=>input.addEventListener('change',updateProductBatchSettings));
  $('#creation-product-provider').addEventListener('change',()=>{fillAiModelSelect('#creation-product-provider','#creation-product-model');updateProductBatchSettings();});
  $('#creation-product-video-provider').addEventListener('change',()=>window.setMediaAudioProvider?.('product-batch',$('#creation-product-video-provider').value==='meta_ai'?'meta_ai':'google_flow'));
  $('#creation-form').addEventListener('change',event=>{if(event.target.closest('.media-audio-controls')||['creation-product-cast','creation-product-outfit-mode'].includes(event.target.id))updateProductBatchSettings();});
  $('#creation-recapture').addEventListener('change',()=>{
    const row=ui.state?.creation_queue?.items.find(item=>item.queue_id===editing);
    if(row)window.prepareGreenQueue?.(row,{useCurrentSettings:$('#creation-recapture').checked});
  });
  modal.querySelector('.cq-product-script').addEventListener('change',updateProductBatchSettings);
  $('#creation-product-model').addEventListener('change',updateProductBatchSettings);
  storyButton.addEventListener('click', async () => {
    if (storyButton.disabled) return;
    const topic = $('#story-topic').value.trim();
    if (!topic) { toast('ใส่หัวข้อเรื่องก่อนเพิ่มลงคิว', 'error'); $('#story-topic').focus(); return; }
    storyButton.disabled = true;
    const result = await command('creation_enqueue', {mode:'story', values:[topic], ...storyStylePayload('story'),
      story_text:$('#story-text').value.trim(), provider:$('#story-provider').value,
      ai_web_model:selectedAiModel('#story-provider','#story-model'), video_generation_mode:$('#story-video-mode').value,
      scene_count:Number($('#story-scenes').value), main_image:ui.storyImage || $('#story-image-path').value}, 'บันทึกเรื่องลงคิวแล้ว');
    storyButton.disabled = false;
    if (result) { showPage('creation'); if (!result.queued) toast('เรื่องนี้อยู่ในคิวแล้ว • ไม่เพิ่มซ้ำ', 'info'); }
  });
  $('#creation-start').addEventListener('click', () => command('creation_start', {}, 'เริ่มคิวแล้ว • กำลังตรวจความพร้อม'));
  $('#creation-pause').addEventListener('click', () => command('creation_pause', {}, 'พักคิวแล้ว • คลิปปัจจุบันยังทำต่อจนจบ'));
  $('#creation-cancel').addEventListener('click', () => command('creation_cancel_current', {}, 'ส่งคำขอยกเลิกและพักคิวแล้ว • เก็บไฟล์และ Checkpoint ไว้'));
  $('#creation-resume-unfinished').addEventListener('click', () => command('creation_resume_unfinished', {}, 'รับคำสั่งทำต่อคิวที่ค้างแล้ว • ใช้ Job และไฟล์เดิม'));
  $('#creation-cancel-all').addEventListener('click', () => askQueueAction('creation_cancel_all', 'ยกเลิกคิวทั้งหมด?', 'หยุดรับงานถัดไปและขอยกเลิกงานที่กำลังทำในคิวนี้\nรูป เสียง วิดีโอ และ Checkpoint ยังคงอยู่ สามารถกดทำต่อเป็นรายงานได้ภายหลัง', 'ยกเลิกคิวทั้งหมด'));
  $('#creation-clear-cache').addEventListener('click', () => askQueueAction('creation_clear_stuck_state', 'ล้างแคชสถานะค้าง?', 'ล้างเฉพาะสถานะชั่วคราวที่ค้างในโปรแกรมและพักคิว\nไม่ลบไฟล์งาน ประวัติ การเข้าสู่ระบบ หรือหลักฐานป้องกันการสร้างซ้ำ\nหากยังมีงานกำลังทำ ระบบจะไม่ล้าง ให้ยกเลิกและรอหยุดก่อน', 'ล้างแคชสถานะค้าง'));
  function askRemoveOld(queueIds=[], jobIds=[]) {
    const count=queueIds.length+jobIds.length;
    if(!count)return;
    askQueueAction('creation_remove_old', `ลบรายการงานเก่า ${count} รายการ?`,
      'นำรายการที่เลือกออกจากหน้าคิว และไม่แสดงซ้ำหลังเปิดโปรแกรมใหม่\nเก็บไฟล์คลิป รูป เสียง และหลักฐานงานไว้ครบ\nไม่รวมงานรอทำ งานกำลังทำ งานสำเร็จ หรือ EP ละคร',
      `ลบ ${count} รายการ`, {queue_ids:[...queueIds],job_ids:[...jobIds],confirmed:true});
  }
  $('#creation-remove-old').addEventListener('click', () => {
    if($('#creation-remove-old').disabled)return;
    const queue=ui.state?.creation_queue || {};
    askRemoveOld(queue.removable_old_queue_ids || [],queue.removable_old_job_ids || []);
  });
  $('#creation-old-list').addEventListener('click', async event => {
    const remove=event.target.closest('button[data-dismiss-job]');
    if(remove){
      if(!remove.disabled && !queueBusy)askRemoveOld([],[remove.dataset.dismissJob]);
      return;
    }
    const button = event.target.closest('button[data-resume-job]');
    if (!button || button.disabled || queueBusy) return;
    await command('creation_resume_jobs', {job_ids:[button.dataset.resumeJob]}, 'นำงานเดิมเข้าคิวเพื่อทำต่อแล้ว • ไม่สร้าง Job ใหม่');
  });
  $('#creation-filter').addEventListener('change', () => {listSignature = ''; window.renderCreationQueue(ui.state || {});});
  $('#creation-status-filter').addEventListener('change', () => {listSignature = ''; window.renderCreationQueue(ui.state || {});});
  $('#creation-list').addEventListener('click', async event => {
    const button = event.target.closest('button[data-cq]'); if (!button || button.disabled) return;
    const row = ui.state?.creation_queue?.items.find(item => item.queue_id === button.dataset.id); if (!row) return;
    if (button.dataset.cq === 'cover') {
      const cover = queueCoverState(row, ui.state);
      if (cover?.attention) await window.openClipCover?.(cover.item_id);
      return; // Even a stale button must never become a queue/provider command.
    }
    if (button.dataset.cq === 'edit') { openEditor(row); return; }
    if (button.dataset.cq === 'result') { showPage('library'); await poll(); openDetail(`${row.mode === 'product' ? 'product' : 'story'}:${row.job_id}`); return; }
    if (button.dataset.cq === 'logs') { showPage('logs'); return; }
    if(button.dataset.cq === 'remove' && ['failed','cancelled'].includes(row.status)){
      askRemoveOld([row.queue_id],[]);return;
    }
    button.disabled = true;
    const payload = {queue_id:row.queue_id, direction:Number(button.dataset.direction || 0)};
    await command(`creation_${button.dataset.cq}`, payload, button.dataset.cq === 'retry' ? 'รับคำสั่งทำต่อแล้ว • ใช้ Job และไฟล์เดิม' : 'อัปเดตคิวแล้ว');
    button.disabled = false;
  });
  window.renderCreationQueue = state => {
    const queue = state.creation_queue || {items:[], counts:{}, paused:true};
    const items = queue.items || []; const counts = queue.counts || {};
    const busyJob = state.story_progress?.active || state.product_progress?.active || state.presenter_progress?.active;
    const active = Number(counts.queued || 0) + Number(counts.running || 0);
    $('#nav-creation-count').textContent = active;
    $('#creation-state').textContent = counts.running ? (queue.paused ? 'กำลังทำคลิปปัจจุบัน • พักก่อนงานถัดไป' : 'กำลังทำงานตามคิว') : active ? (queue.paused ? 'พักคิว • รอเริ่ม' : 'กำลังตรวจความพร้อม') : 'พร้อมเพิ่มงาน';
    $('#creation-summary').textContent = items.length ? `สำเร็จ ${counts.completed || 0} • รอ ${counts.queued || 0} • ต้องตรวจสอบ ${counts.failed || 0} • ยกเลิก ${counts.cancelled || 0}` : 'ยังไม่มีรายการในคิว';
    $('#creation-hint').textContent = active && queue.pause_reason === 'startup_review' ? 'กู้คิวจากครั้งก่อนแล้ว • กดเริ่มคิวเพื่อใช้ Job เดิมและไฟล์ที่เสร็จแล้ว' : 'งานที่กดหยุดไว้: กด “ทำต่อจากเดิม” ที่รายการนั้น • เริ่มคิวไม่คืนงานที่ยกเลิกให้อัตโนมัติ';
    $('#creation-start').disabled = queueBusy || !active || !queue.paused;
    $('#creation-pause').disabled = queueBusy || !active || queue.paused;
    $('#creation-cancel').disabled = queueBusy || !counts.running;
    $('#creation-resume-unfinished').disabled = queueBusy || !queue.unfinished_count;
    $('#creation-cancel-all').disabled = queueBusy || !queue.cancelable_count;
    $('#creation-clear-cache').disabled = queueBusy || queue.can_clear_stuck_state !== true;
    const oldCount=(queue.removable_old_queue_ids || []).length+(queue.removable_old_job_ids || []).length;
    $('#creation-remove-old').disabled=queueBusy || !oldCount || queue.can_remove_old_entries !== true;
    $('#creation-remove-old').textContent=oldCount ? `ลบงานค้างเก่าทั้งหมด (${oldCount})` : 'ลบงานค้างเก่าทั้งหมด';
    $('#creation-remove-old').title=queue.can_remove_old_entries === false
      ? queue.stuck_state_blocked_reason || 'รอให้งานปัจจุบันหยุดก่อนลบรายการ'
      : 'ทุกประเภท • ลบเฉพาะรายการงานเก่าที่หยุดแล้ว ไม่ลบไฟล์';
    $('#creation-clear-hint').textContent = queue.can_clear_stuck_state === true
      ? 'ล้างเฉพาะแคชสถานะ • ไม่ลบรูป เสียง วิดีโอ หรือประวัติงาน'
      : 'ยังมีงานหรือคำสั่งกำลังทำอยู่ • ยกเลิกแล้วรอหยุดก่อนล้างสถานะ';
    const oldJobs = queue.recoverable_jobs || [];
    const oldTotal=Number(queue.recoverable_job_count || oldJobs.length);
    $('#creation-old-hint').textContent=`${oldTotal>oldJobs.length ? `แสดง ${oldJobs.length} จาก ${oldTotal} งาน • ` : ''}ทำต่อจากไฟล์เดิม หรือกดลบรายการที่ไม่ต้องการ • ไฟล์งานยังอยู่`;
    $('#creation-old-panel').classList.toggle('hidden', !oldJobs.length);
    const oldKey = JSON.stringify(oldJobs);
    if (oldKey !== oldSignature) {
      oldSignature = oldKey;
      $('#creation-old-list').innerHTML = oldJobs.map(row => `<article class="cq-row" role="listitem"><div class="cq-order">↻</div><div><span class="cq-kind">${kindLabel(row)}</span><h3>${esc(row.title || row.topic || row.job_id)}</h3><div class="cq-meta">${esc(row.job_id)} • เก็บไฟล์เดิมไว้ทำต่อ</div></div><div class="cq-row-actions"><button class="button ghost compact cq-remove-old" data-dismiss-job="${esc(row.job_id)}">ลบรายการ</button><button class="button secondary compact" data-resume-job="${esc(row.job_id)}">ทำต่อจากเดิม</button></div></article>`).join('');
    }
    $$('#creation-old-list button').forEach(button => {button.disabled = queueBusy
      || (Boolean(button.dataset.dismissJob) && queue.can_remove_old_entries !== true);});
    const filter = $('#creation-filter').value;
    const statusFilter = $('#creation-status-filter').value || 'unfinished';
    const rank = {running:0, queued:1, failed:2, cancelled:2, completed:3};
    const pending = items.filter(row=>['queued','running'].includes(row.status));
    const visible = items.filter(row => filter === 'all' || (filter === 'long_video' ? Boolean(row.long_video)
      : (row.mode || 'story') === filter && !(filter === 'story' && row.long_video)))
      .filter(row => statusFilter === 'all' || (statusFilter === 'completed' ? row.status === 'completed'
        : ['queued','running','failed'].includes(row.status) || (row.status === 'cancelled' && row.job_id)))
      .sort((a,b)=>(rank[a.status]??3)-(rank[b.status]??3) ||
        (['failed','cancelled'].includes(a.status) && ['failed','cancelled'].includes(b.status)
          ? String(b.finished_at || b.created_at || '').localeCompare(String(a.finished_at || a.created_at || '')) : 0));
    const coverStates = new Map(visible.map(row => [row.queue_id, queueCoverState(row, state)]));
    const creativeStates = new Map(visible.map(row => [row.queue_id, window.creativeJobLabel?.(row,state)||'']));
    const signature = JSON.stringify([filter, statusFilter, visible, [...coverStates], [...creativeStates]]);
    // Polling progress must not replace controls under the user's pointer.
    if (signature !== listSignature) {
      listSignature = signature;
      $('#creation-list').innerHTML = visible.length ? visible.map(row => {
        const id = esc(row.queue_id); const status = labels[row.status] ? row.status : 'queued';
        const position = pending.some(item=>item.queue_id===row.queue_id) ? pending.findIndex(item=>item.queue_id===row.queue_id)+1 : '✓';
        const editable = status === 'queued' && !row.job_id && row.mode !== 'drama';
        const cover = coverStates.get(row.queue_id);
        const btn = (action, text, extra='') => `<button class="button ${action === 'retry' ? 'secondary' : 'ghost'} compact" data-cq="${action}" data-id="${id}" ${extra}>${text}</button>`;
        let actions = '';
        if (editable) actions += btn('move','↑','data-direction="-1" aria-label="เลื่อนขึ้น"') + btn('move','↓','data-direction="1" aria-label="เลื่อนลง"') + btn('edit','แก้ไข');
        if (status !== 'running' && row.mode !== 'drama') actions += btn('remove','นำออกจากคิว');
        if (['failed','cancelled'].includes(status) && row.mode !== 'drama') actions += btn('retry','ทำต่อจากเดิม');
        if (status === 'completed' && row.job_id) actions += btn('result','ดูวิดีโอ');
        if (status === 'failed') actions += btn('logs','ดู Log');
        if (cover?.attention) actions += btn('cover','จัดการปก AI');
        const creativeNote=creativeStates.get(row.queue_id)?`<div class="cq-meta">${esc(creativeStates.get(row.queue_id))}</div>`:'';
        const notice = creativeNote+(cover?.recovered ? '<div class="cq-meta">ปก AI บันทึกแล้ว • กด Run Queue เพื่อทำคิวต่อ</div>'
          : status === 'cancelled' && row.job_id ? '<div class="cq-meta">หยุดไว้ • บท ภาพ และคลิปที่บันทึกแล้วจะใช้ต่อจากงานเดิม</div>'
          : row.error ? `<div class="cq-error">${esc(row.error)}</div>` : '');
        return `<article class="cq-row" role="listitem"><div class="cq-order">${status==='failed' ? '!' : status==='cancelled' ? '–' : position}</div><div><span class="cq-status ${status}">${status === 'cancelled' && row.job_id ? 'หยุดไว้ • ทำต่อได้' : labels[status]}</span><span class="cq-kind">${kindLabel(row)}</span><h3>${esc(row.topic || row.link || '')}</h3><div class="cq-meta">${row.provider === 'gemini' ? 'Gemini Web' : 'ChatGPT Web • โมเดลปัจจุบัน'} • ${row.mode === 'product' ? '3 ช็อต' : Number(row.scene_count || 10)+' ฉาก'} • ${subtitleEnabled(row) ? 'เปิดซับ' : 'ปิดซับ'}<br>${id}${row.job_id ? ' • '+esc(row.job_id) : ''}</div>${notice}${status === 'running' ? `<div class="cq-meta" data-cq-stage="${id}"></div><progress data-cq-progress="${id}" max="100" value="0" aria-label="ความคืบหน้าคลิป"></progress>` : ''}</div><div class="cq-row-actions">${actions}</div></article>`;
      }).join('') : items.length ? '<div class="cq-empty"><strong>ไม่มีงานในตัวกรองนี้</strong>ดูงานเก่าได้ที่ “ประวัติทั้งหมด” • ไม่มีรายการถูกลบ</div>' : '<div class="cq-empty"><strong>คิวนี้ยังว่าง</strong>เพิ่มลิงก์สินค้าหรือหัวข้อ Shorts ได้เลย<br>ยังไม่เริ่มใช้บริการ AI จนกว่าจะกดเริ่มคิว</div>';
    }
    $$('#creation-list button[data-cq]').forEach(button => {
      const waiting = button.dataset.cq === 'retry' && Boolean(busyJob);
      const row=items.find(item=>item.queue_id===button.dataset.id);
      const removingBlocked=button.dataset.cq==='remove' && ['failed','cancelled'].includes(row?.status)
        && queue.can_remove_old_entries!==true;
      button.disabled = queueBusy || waiting || removingBlocked;
      button.title = waiting ? 'รอคลิปปัจจุบันเสร็จหรือหยุดงานนั้นก่อน แล้วทำงานนี้ต่อได้' : '';
    });
    for (const row of visible.filter(item => item.status === 'running')) {
      const progress = row.mode === 'product' ? state.product_progress : state.story_progress;
      const node = document.querySelector(`[data-cq-progress="${CSS.escape(row.queue_id)}"]`);
      const stage = document.querySelector(`[data-cq-stage="${CSS.escape(row.queue_id)}"]`);
      const matching = progress && progress.job_id === row.job_id;
      if (node) node.value = matching ? Math.min(100, Math.max(0, Number(progress.percent || 0))) : 0;
      if (stage) stage.textContent = matching ? progress.message || progress.stage || 'กำลังทำงาน' : 'กำลังเตรียมงาน';
    }
  };
  if (ui.state) window.renderCreationQueue(ui.state);
})();
