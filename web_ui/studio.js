/* Review and navigation only. Physical AI Web / Flow automation stays in the Extension. */
(() => {
  const studio = {review:null, opener:null, request:0, query:'', service:'all', errors:false, dirty:false, saving:false};
  const el = (tag, className, html = '') => {const node=document.createElement(tag);node.className=className;node.innerHTML=html;return node;};
  const workspace = el('section','panel studio-now');
  workspace.id='studio-now'; workspace.setAttribute('aria-label','งานปัจจุบันและขั้นตอนถัดไป');
  $('[data-view="dashboard"] .hero').before(workspace);

  for (const page of ['story','drama']) {
    const panel=el('section','panel studio-review-launcher', `<div><span class="eyebrow">STORYBOARD & VOICE CHECK</span><h2>ตรวจฉากและคำอ่าน</h2><p>ดูภาพ บท และไฟล์แต่ละฉาก โดยไม่เริ่มสร้างซ้ำ</p></div><label class="field"><span>เลือกงานที่ต้องการตรวจ</span><select id="${page}-review-job"></select></label><button class="button secondary" data-open-studio="${page}">เปิด Storyboard</button>`);
    if(page==='drama')$('.drama-series-panel').before(panel);
    else $('[data-view="'+page+'"] .page-intro').after(panel);
  }

  const modal=el('dialog','modal studio-review-modal',`<div class="modal-card studio-review-card"><button class="modal-close" data-close-modal="studio-review-modal" aria-label="ปิด Storyboard">×</button><span class="eyebrow">STORYBOARD / CHECKPOINT</span><h2 id="studio-review-title">กำลังอ่านงาน…</h2><p id="studio-review-subtitle"></p><div id="studio-review-body" aria-live="polite"></div></div>`);
  modal.id='studio-review-modal';modal.setAttribute('aria-labelledby','studio-review-title');document.body.append(modal);
  modal.addEventListener('close',()=>{studio.request++;studio.dirty=false;$$('video',modal).forEach(v=>v.pause());if(studio.opener?.isConnected)studio.opener.focus({preventScroll:true});});
  modal.addEventListener('cancel',event=>{if(studio.dirty){event.preventDefault();toast('มีข้อความที่ยังไม่บันทึก กดบันทึก หรือปิดด้วยปุ่ม × เพื่อทิ้งการแก้ไข','warning');}});

  const logTools=el('div','studio-log-tools',`<label class="field"><span>ค้นหา Job / ขั้นตอน / ข้อความ</span><input id="studio-log-query" type="search" placeholder="เช่น STORY-… หรือ download"></label><label class="field"><span>บริการ</span><select id="studio-log-service"><option value="all">ทั้งหมด</option><option value="flow">Google Flow</option><option value="gemini">Gemini</option><option value="chatgpt">ChatGPT</option><option value="voice">เสียง</option><option value="subtitle">Subtitle</option></select></label><label class="studio-log-errors"><input id="studio-log-errors" type="checkbox"> เฉพาะข้อผิดพลาด</label><button class="button secondary compact" id="studio-log-copy">คัดลอกที่กรองแล้ว</button><small id="studio-log-count" aria-live="polite"></small>`);
  $('#log-console').before(logTools);
  for(const id of ['studio-log-query','studio-log-service','studio-log-errors'])$('#'+id).addEventListener('input',()=>renderLogs(ui.state||{}));
  window.filterStudioLogs=lines=>{
    const query=$('#studio-log-query').value.trim().toLowerCase(),service=$('#studio-log-service').value,errors=$('#studio-log-errors').checked;
    const patterns={flow:/flow/i,gemini:/gemini/i,chatgpt:/chatgpt/i,voice:/voice|เสียง/i,subtitle:/subtitle|ซับ|คำบรรยาย/i};
    const filtered=lines.filter(line=>(!query||String(line).toLowerCase().includes(query))&&(service==='all'||patterns[service]?.test(line))&&(!errors||/error|failed|exception|ผิดพลาด|ล้มเหลว/i.test(line)));
    $('#studio-log-count').textContent=`${filtered.length} / ${lines.length} บรรทัดล่าสุด`;
    return filtered;
  };
  $('#studio-log-copy').addEventListener('click',()=>{copyText(`SmartFlow AI • Extension ${ui.state?.app?.extension_required||'—'}\n${$('#log-console').textContent}`);toast('คัดลอก Log ที่กรองแล้ว','success');});

  function readNotes(){
    const notes={};
    for(const line of $('#studio-notes').value.split(/\r?\n/)){
      if(!line.trim())continue;
      const split=line.indexOf('=');
      if(split<1)throw new Error('ใช้รูปแบบ คำต้นฉบับ = คำอ่าน หนึ่งคู่ต่อบรรทัด');
      const key=line.slice(0,split).trim(),value=line.slice(split+1).trim();
      if(Object.hasOwn(notes,key))throw new Error(`คำ “${key}” ซ้ำ กรุณาเหลือบรรทัดเดียว`);
      Object.defineProperty(notes,key,{value,writable:true,enumerable:true,configurable:true});
    }
    return notes;
  }
  function paintVoice(review){
    $('#studio-voice-result').className='studio-voice-result '+(review.ready?'ready':'needs-review');
    $('#studio-voice-result').textContent=review.ready?'✓ บทพร้อมสำหรับสร้างเสียง (ยังไม่ได้ส่งคำขอเสียง)':review.issues.join('\n');
    $('#studio-voice-script').textContent=review.script||'ยังไม่มีบท';
  }
  function storyContentMarkup(review){
    const content=review.content_review||{status:'legacy',issues:[],entities:[]};
    const labels={ready:'ตรวจชื่อและโครงสร้างแผนภาพแล้ว',needs_review:'แผนภาพมีจุดที่ต้องตรวจ',legacy:'งานเดิม — ยังไม่มีข้อมูลผูกตัวละครกับฉาก',pending:'รอแผนภาพจาก AI'};
    const status=Object.hasOwn(labels,content.status)?content.status:'legacy';
    const entities=Array.isArray(content.entities)?content.entities:[];
    const issues=Array.isArray(content.issues)?content.issues:[];
    return `<section class="studio-content-review ${status==='needs_review'?'needs-review':''}" aria-label="ความตรงของแผนภาพกับเรื่อง"><h3>${labels[status]}</h3><p>สไตล์เปลี่ยนเฉพาะวิธีวาด ตัวละคร สถานที่ และเหตุการณ์ต้องยึดเรื่องเดิม</p>${entities.length?`<details><summary>ตัวละครและองค์ประกอบที่ต้องรักษา (${entities.length})</summary><ul>${entities.map(entity=>`<li><b>${escapeHtml(entity.name||entity.id)}</b>${entity.visual_identity?` — ${escapeHtml(typeof entity.visual_identity==='string'?entity.visual_identity:JSON.stringify(entity.visual_identity))}`:''}</li>`).join('')}</ul></details>`:''}${issues.length?`<ul class="studio-content-issues">${issues.map(issue=>`<li>${issue.scene?`ฉาก ${escapeHtml(String(issue.scene))}: `:''}${escapeHtml(issue.message||issue.code||'กรุณาตรวจแผนภาพ')}</li>`).join('')}</ul>`:''}<small>ตรวจจากข้อมูลและพรอมต์ ไม่ใช่การยืนยันว่าภาพ AI ตรงทั้งหมด • งานเดิมและไฟล์ที่สร้างแล้วไม่ถูกแก้หรือสร้างทับ</small></section>`;
  }
  function storySceneIdentityMarkup(review,scene){
    const content=review.content_review;
    const ids=content?.scene_entities?.[scene.index-1];
    if(!Array.isArray(ids)||!Array.isArray(content?.entities))return '';
    const names=ids.map(id=>content.entities.find(entity=>entity.id===id)?.name).filter(Boolean);
    return names.length?`<p class="studio-scene-identities">ในฉาก: ${names.map(escapeHtml).join(' · ')}</p>`:'';
  }
  function storyScenePromptMarkup(scene){
    if(studio.review?.video_plan?.supported)return imageScenePromptMarkup(scene)+(scene.flow_editable?`<details><summary>แก้พรอมต์วิดีโอฉากนี้</summary><label class="field"><span>พรอมต์วิดีโอ (ไม่เปลี่ยนบทพากย์)</span><textarea rows="5" maxlength="12000" data-flow-prompt="${scene.index}">${escapeHtml(scene.flow_prompt||'')}</textarea></label><input type="hidden" data-flow-model="${scene.index}" value="${escapeHtml(scene.flow_model||'')}"><button class="button secondary compact" data-save-flow="${scene.index}">บันทึกพรอมต์ฉากนี้</button><small>โมเดลและรายละเอียดเลือกได้ใน “การสร้างวิดีโอที่เหลือ” ด้านบน</small></details>`:'');
    const models=['','Omni 1.1 Flash','Veo 3.1 - Lite','Veo 3.1 - Fast','Veo 3.1 - Quality','Veo 3.1 - Lite [Lower Priority]'];
    if(scene.flow_model&&!models.includes(scene.flow_model))models.push(scene.flow_model);
    return imageScenePromptMarkup(scene)+(scene.flow_editable?`<details><summary>แก้พรอมต์วิดีโอ / โมเดล Flow</summary><label class="field"><span>พรอมต์วิดีโอฉากนี้ (ไม่เปลี่ยนบทพากย์)</span><textarea rows="5" maxlength="12000" data-flow-prompt="${scene.index}">${escapeHtml(scene.flow_prompt||'')}</textarea></label><label class="field"><span>โมเดล Google Flow ของฉากนี้</span><select data-flow-model="${scene.index}">${models.map(model=>`<option value="${escapeHtml(model)}" ${model===(scene.flow_model||'')?'selected':''}>${escapeHtml(model||'ใช้ค่าที่เลือกอยู่ในเว็บ Flow')}</option>`).join('')}</select></label><p>ใช้ภาพเดิม • มีผลเฉพาะการส่งครั้งถัดไปของฉากนี้ ไม่เปลี่ยนคลิปที่เสร็จแล้ว หากยังไม่ทราบผลการส่งเดิม ระบบต้องตรวจผลก่อน ไม่ส่งซ้ำทันที</p><button class="button secondary compact" data-save-flow="${scene.index}">บันทึกค่าฉากนี้</button><small>บันทึกแล้วกดทำต่อที่หน้างาน • โมเดลต้องมีให้ใช้ในบัญชี Flow ของคุณ</small></details>`:'');
  }
  function imageScenePromptMarkup(scene){
    const index=Number(scene.index);
    if(!Number.isSafeInteger(index)||index<1)return '';
    return `<details><summary>พรอมต์ฉากนี้${scene.prompt_revised?' • แก้ไขแล้ว':''}</summary>${scene.prompt_editable?`<label class="field"><span>สิ่งที่ให้แสดงในภาพ (ไม่เปลี่ยนบทพากย์)</span><textarea rows="6" maxlength="12000" data-scene-prompt="${index}">${escapeHtml(scene.prompt||'')}</textarea></label><p>คงตัวละครและสถานที่เดิม หากเป็นฉากต่อสู้ ให้เลือกภาพก่อนปะทะหรือผลหลังเหตุการณ์ที่ไม่แสดงเลือดหรือบาดแผล ไม่รับประกันว่า AI จะอนุมัติ</p><button class="button secondary compact" data-save-scene="${index}">บันทึก Prompt ฉากนี้</button><small>บันทึกอย่างเดียว ไม่สร้างอัตโนมัติ • ตรวจแล้วกด “ทำต่อ” ที่หน้างาน</small>`:`<p>${escapeHtml(scene.prompt||'')}</p>`}<button class="button ghost compact" data-copy-scene="${index}">คัดลอกพรอมต์</button></details>`;
  }
  function storyFailureMarkup(review){
    if(!review.last_error)return '';
    const explanation=review.image_result_review?.message || (/STORY_IMAGE_REFUSED/.test(review.last_error)
      ?'เว็บตอบปฏิเสธภาพแล้ว ไม่ใช่ปุ่มส่งค้าง • ระบบไม่ส่งคำขอเดิมซ้ำอัตโนมัติ ตรวจและแก้สิ่งที่ให้แสดงในพรอมต์ฉากก่อนกดทำต่อ'
      :/STORY_REFERENCE_REQUIRED/.test(review.last_error)
        ?'เว็บขอภาพอ้างอิงเพิ่ม ยังไม่ได้สร้างภาพ และไม่ใช่การปฏิเสธนโยบาย • ตรวจว่าพรอมต์ฉากอธิบายตัวละครและฉากได้ครบโดยไม่ต้องใช้ภาพที่ไม่มีอยู่ ระบบหยุด ไม่ส่งข้อความเดิมซ้ำ'
        :/STORY_IMAGE_RESPONSE_REVIEW/.test(review.last_error)
          ?'เว็บตอบข้อความแล้ว แต่ยังไม่พบภาพใหม่ที่ยืนยันได้ • ไม่สรุปว่าสร้างล้มเหลวหรือถูกปฏิเสธ ระบบไม่ส่งซ้ำและไม่เริ่มงานใหม่อัตโนมัติ ตรวจคำตอบและผลในแชตเดิมก่อนกดทำต่อ บทและภาพที่บันทึกแล้วคงเดิม'
          :'');
    return `<section class="studio-content-review needs-review" role="status"><h3>เหตุที่งานหยุด</h3><p>${escapeHtml(review.last_error)}</p>${explanation?`<p>${escapeHtml(explanation)}</p>`:''}</section>`;
  }
  function pendingReviewDrafts(){
    return {videoPlan:studio.planEditor?.readDraft(),flow:$$('[data-flow-prompt],[data-flow-model]',modal).map(node=>[node.hasAttribute('data-flow-prompt')?'prompt':'model',node.dataset.flowPrompt||node.dataset.flowModel,node.value]),notes:$('#studio-notes').value, prompts:$$('[data-scene-prompt]',modal).filter(node=>node.value!==studio.review.scenes.find(scene=>scene.index===Number(node.dataset.scenePrompt))?.prompt).map(node=>[node.dataset.scenePrompt,node.value])};
  }
  function restoreReviewDrafts(drafts, savedScene, savedNotes=false){
    for(const [kind,index,value] of drafts.flow||[]){const node=$(`[data-flow-${kind}="${index}"]`,modal);if(node)node.value=value;}
    if(!savedNotes)$('#studio-notes').value=drafts.notes;
    for(const [index,value] of drafts.prompts)if(Number(index)!==savedScene){const node=$(`[data-scene-prompt="${index}"]`,modal);if(node)node.value=value;}
    studio.dirty=pendingReviewDrafts().prompts.length>0||$('#studio-notes').value!==Object.entries(studio.review.user_notes).map(([key,value])=>`${key} = ${value}`).join('\n');
    studio.dirty ||= (drafts.flow||[]).some(([kind,index,value])=>value!==(studio.review.scenes.find(s=>s.index===Number(index))?.['flow_'+kind]||''));
    studio.planEditor?.restore(drafts.videoPlan);
  }
  function freezeReviewInputs(){
    const inputs=$$('input,textarea,select,button',modal).map(node=>[node,node.disabled]);
    inputs.forEach(([node])=>{node.disabled=true;});
    return ()=>inputs.forEach(([node,disabled])=>{node.disabled=disabled;});
  }
  function paintReview(review){
    studio.review=review;studio.dirty=false;
    $('#studio-review-title').textContent=review.title||review.job_id;
    $('#studio-review-subtitle').textContent=`${review.job_id} • อัปเดต ${formatDate(review.updated_at)} • สไตล์ ${ui.state?.story_visual_styles?.find(x=>x.value===review.visual_style)?.label||review.visual_style}`;
    const selectedVideo=['google_flow','meta_ai'].includes(review.video_generation_mode)?review.video_generation_mode:'google_flow';
    const longMetaPending=Boolean(review.long_video&&!review.meta_landscape_available);
    const providerControl=review.video_plan?.supported?'<section data-scene-video-plan></section>':review.video_generation_mode==='image_motion'
      ? '<section class="studio-video-provider"><div><span class="eyebrow">VIDEO CREATOR</span><h3>ภาพเคลื่อนไหวในเครื่อง</h3><p>งานนี้ไม่ได้ใช้ Google Flow หรือ Meta AI และเปลี่ยนผู้สร้างจากหน้านี้ไม่ได้</p></div></section>'
      : `<section class="studio-video-provider"><div><span class="eyebrow">VIDEO CREATOR</span><h3>ผู้สร้างวิดีโอของงานนี้</h3><p>ใช้ภาพ บท และเสียงเดิมกับผู้สร้างที่เลือก • คลิปเดิมยังอยู่ในงาน</p></div><label class="field"><span>ผู้สร้างวิดีโอ</span><select data-story-video-provider ${review.video_provider_editable?'':'disabled'}><option value="google_flow" ${selectedVideo==='google_flow'?'selected':''}>Google Flow</option><option value="meta_ai" ${selectedVideo==='meta_ai'?'selected':''} ${longMetaPending?'disabled':''}>Meta AI (ทดลอง)${review.long_video?' • 16:9':''}${longMetaPending?' • รอยืนยัน':''}</option></select></label><small>${longMetaPending?'Meta AI คลิปยาวยังรอพิสูจน์ไฟล์แนวนอน 16:9 จริง • งาน Flow และคลิปเดิมไม่เปลี่ยน':'ใช้เฉพาะคลิปจากผู้สร้างที่เลือกและตรงกับภาพ/บทปัจจุบัน คลิปจากผู้สร้างเดิมยังเก็บไว้แต่ไม่เอามาปนใน Final รอบใหม่ • สร้างเฉพาะฉากที่ยังขาด'}</small><button class="button secondary compact" data-save-story-provider ${review.video_provider_editable?'':'disabled'}>บันทึกผู้สร้าง</button></section>`;
    $('#studio-review-body').innerHTML=`<ol class="studio-checkpoints">${review.stages.map(stage=>`<li class="${stage.ready?'done':''}"><b>${stage.ready?'✓':'○'} ${escapeHtml(stage.label)}</b><small>${escapeHtml(stage.detail)}</small></li>`).join('')}</ol>
      ${providerControl}
      ${storyContentMarkup(review)}
      ${storyFailureMarkup(review)}
      <div class="studio-review-tools"><span>แสดงตามไฟล์จริง ไม่ถือว่ารูปครบเท่ากับวิดีโอเสร็จ</span><button class="button ghost compact" data-refresh-studio>↻ อ่านสถานะใหม่</button></div>
      <div class="studio-scene-grid">${review.scenes.map(scene=>`<article class="studio-scene"><div class="studio-scene-media">${scene.image_url?`<img loading="lazy" src="${escapeHtml(scene.image_url)}" alt="ภาพฉาก ${scene.index}">`:'<span>ยังไม่มีภาพ</span>'}</div><div class="studio-scene-copy"><header><b>ฉาก ${scene.index}</b><span class="status-pill ${scene.source==='pending'?'':'ready'}">${scene.source==='flow'?'Flow จริง':scene.source==='meta'?'Meta AI จริง':scene.source==='local'?'ภาพเคลื่อนไหวในเครื่อง':'รอวิดีโอ'}</span></header>${storySceneIdentityMarkup(review,scene)}<p>${escapeHtml(scene.narration||'ยังไม่มีบทฉาก')}</p>${storyScenePromptMarkup(scene)}${scene.video_url?`<video controls preload="none" src="${escapeHtml(scene.video_url)}" aria-label="วิดีโอฉาก ${scene.index}"></video>`:''}</div></article>`).join('')}</div>
      <section class="studio-pronunciation"><div><span class="eyebrow">PRONUNCIATION CHECK</span><h3>คำอ่านเฉพาะงานนี้</h3><p>แทนคำในเสียงและซับร่วมกัน ไม่เปลี่ยนภาพหรือส่งงานสร้างเสียงอัตโนมัติ</p></div><label class="field"><span>คำต้นฉบับ = คำอ่านภาษาไทย (หนึ่งคู่ต่อบรรทัด)</span><textarea id="studio-notes" rows="4" placeholder="UnknownHero = ฮีโร่ลึกลับ" ${review.editable?'':'readonly'}></textarea></label><div class="studio-review-tools"><span id="studio-note-state">${escapeHtml(review.locked_reason||'บันทึกมีผลเฉพาะงานนี้ ไม่เปลี่ยนค่าเริ่มต้นของงานอื่น')}</span><button class="button secondary compact" data-preview-notes>ตรวจคำอ่าน</button><button class="button primary compact" data-save-notes ${review.editable?'':'disabled'}>บันทึกคำอ่าน</button></div><div id="studio-voice-result" role="status"></div><details><summary>ดูข้อความที่จะส่งให้ AI Voice (ไม่ใช้เครดิต)</summary><p id="studio-voice-script"></p></details></section>`;
    $('#studio-notes').value=Object.entries(review.user_notes).map(([key,value])=>`${key} = ${value}`).join('\n');
    $('#studio-notes').addEventListener('input',()=>{studio.dirty=true;$('#studio-note-state').textContent='● มีคำอ่านที่ยังไม่บันทึก';});
    $$('[data-scene-prompt]',modal).forEach(node=>node.addEventListener('input',()=>{studio.dirty=true;}));
    paintVoice(review.voice_review);
    studio.planEditor=null;
    if(review.video_plan?.supported){
      const token=studio.request;
      studio.planEditor=window.SmartFlowVideoPlan?.mount($('[data-scene-video-plan]',modal),review,{
        onDirty:()=>{studio.dirty=true;},onSaving:saving=>{studio.saving=saving;},
        onSaved:next=>{if(token!==studio.request||!modal.open)return;const drafts=pendingReviewDrafts();drafts.videoPlan=null;paintReview(next);restoreReviewDrafts(drafts,0);poll(true).catch(()=>{});}
      });
    }
    $$('[data-flow-prompt],[data-flow-model]',modal).forEach(node=>node.addEventListener('input',()=>{studio.dirty=true;}));
    if (review.scenes?.length&&!review.video_plan?.enabled) {
      const native = el('section', 'studio-voice-editor', '<h3>รวมคลิปเดิมด้วยเสียง Google Flow</h3><p>ไม่สร้างคลิปซ้ำ ไม่เรียกเสียง API และไม่ใส่ซับ • เสียงหรือเพลงที่ติดมากับ Flow จะคงอยู่</p><label><input type="checkbox" data-native-music> เพิ่มเพลงพื้นหลังตามค่าที่ตั้งไว้</label><br><label><input type="checkbox" data-native-silent> ยอมรับช่วงเงียบในฉากที่ไม่มีแทร็กเสียง</label><p data-native-status role="status"></p><button class="button primary" data-native-export>รวมคลิปพร้อมเสียงต้นฉบับ</button> <button class="button secondary" data-native-cancel>ยกเลิกการรวม</button>');
      const extra = el('details', 'studio-native-extra');
      extra.append(el('summary', '', 'เครื่องมือเพิ่มเติม • รวมคลิปเดิมด้วยเสียงต้นฉบับ'), native);
      $('#studio-review-body').append(extra);
      native.querySelector('[data-native-export]').onclick = async () => {
        const button = native.querySelector('[data-native-export]'); button.disabled = true;
        try {
          await postAction('story_native_export', {job_id: review.job_id, music: native.querySelector('[data-native-music]').checked, allow_silent: native.querySelector('[data-native-silent]').checked});
          while (true) {
            const {state} = await postAction('story_native_status', {});
            if (state.job_id !== review.job_id) break;
            native.querySelector('[data-native-status]').textContent = state.message + (state.silent_scenes?.length ? ' • ฉากไม่มีเสียง: ' + state.silent_scenes.join(', ') : '') + (state.result?.output ? '\nไฟล์: ' + state.result.output : '');
            if (state.status !== 'running') { toast(state.message, state.status === 'complete' ? 'success' : 'info'); break; }
            await new Promise(resolve => setTimeout(resolve, 1000));
          }
        } catch (error) { native.querySelector('[data-native-status]').textContent = error.message; toast(error.message, 'error'); }
        finally { button.disabled = false; }
      };
      native.querySelector('[data-native-cancel]').onclick = async () => {
        try { await postAction('story_native_cancel', {job_id: review.job_id}); } catch (error) { toast(error.message, 'error'); }
      };
      const folderButton = el('button', 'button secondary', 'เปิดโฟลเดอร์วิดีโอ');
      folderButton.onclick = async () => {
        try { await postAction('story_native_open_folder', {job_id: review.job_id}); } catch (error) { toast(error.message, 'error'); }
      };
      native.append(folderButton);
    }
  }
  async function openReview(jobId, refresh=false){
    if(!jobId){toast('ยังไม่มีงานให้ตรวจ','info');return;}
    if(!refresh){studio.opener=document.activeElement;$('#studio-review-body').innerHTML='<div class="studio-loading" role="status">กำลังอ่านบท ภาพ และไฟล์ของงาน…</div>';$('#studio-review-title').textContent='กำลังอ่านงาน…';$('#studio-review-subtitle').textContent='';modal.showModal();}
    const token=++studio.request;
    try{const data=await postAction('story_review',{job_id:jobId});if(token===studio.request&&modal.open)paintReview(data.review);}
    catch(error){if(token===studio.request){$('#studio-review-body').textContent=error.message;toast(error.message,'error');}}
  }
  window.addEventListener('smartflow-story-provider-saved',event=>{
    if(modal.open&&event.detail?.jobId===studio.review?.job_id)openReview(event.detail.jobId,true);
  });
  document.addEventListener('click',async event=>{
    const target=event.target.closest('button');if(!target)return;
    if(target.closest('.studio-scene-plan'))return;
    if(target.dataset.openStudio){await openReview($('#'+target.dataset.openStudio+'-review-job').value);return;}
    if(target.dataset.reviewStory){await openReview(target.dataset.reviewStory);return;}
    if(studio.saving&&modal.contains(target)){toast('กำลังบันทึก กรุณารอสักครู่','info');return;}
    if(target.hasAttribute('data-refresh-studio')){if(studio.dirty){toast('บันทึกข้อความก่อนอ่านสถานะใหม่','warning');return;}await openReview(studio.review.job_id,true);return;}
    if(target.dataset.copyScene){copyText($(`[data-scene-prompt="${Number(target.dataset.copyScene)}"]`,modal)?.value??studio.review.scenes.find(x=>x.index===Number(target.dataset.copyScene))?.prompt??'');toast('คัดลอกพรอมต์แล้ว','success');return;}
    if(target.dataset.saveScene){
      const index=Number(target.dataset.saveScene), drafts=pendingReviewDrafts(), token=studio.request;
      const thaw=freezeReviewInputs();studio.saving=true;
      try{
        const data=await postAction('story_save_scene_prompt',{job_id:studio.review.job_id,revision:studio.review.revision,scene_index:index,prompt:$(`[data-scene-prompt="${index}"]`,modal).value});
        if(token===studio.request&&modal.open){paintReview(data.review);restoreReviewDrafts(drafts,index);toast('บันทึก Prompt แล้ว • ยังไม่สร้าง กดทำต่อที่หน้างานเมื่อพร้อม','success');}
      }catch(error){toast(error.message,'error');}finally{studio.saving=false;thaw();}
      return;
    }
     if(target.dataset.saveFlow){
      const index=Number(target.dataset.saveFlow), token=studio.request;
      const thaw=freezeReviewInputs();studio.saving=true;
      try{
        const data=await postAction('story_save_flow_scene',{job_id:studio.review.job_id,revision:studio.review.revision,scene_index:index,prompt:$(`[data-flow-prompt="${index}"]`,modal).value,model:$(`[data-flow-model="${index}"]`,modal).value});
        if(token===studio.request&&modal.open){studio.review.revision=data.review.revision;const saved=data.review.scenes.find(s=>s.index===index);Object.assign(studio.review.scenes.find(s=>s.index===index),saved);toast('บันทึกค่าฉากแล้ว ยังไม่เริ่มสร้าง • กดทำต่อเมื่อพร้อม','success');}
      }catch(error){toast(error.message,'error');}finally{studio.saving=false;thaw();}
       return;
     }
     if(target.hasAttribute('data-save-story-provider')){
       const provider=$('[data-story-video-provider]',modal).value,current=studio.review.video_generation_mode||'google_flow';
       if(provider==='meta_ai'&&studio.review.long_video&&!studio.review.meta_landscape_available){toast('Meta AI คลิปยาว 16:9 ยังรอยืนยันผลจริง','warning');return;}
       if(provider===current){toast('งานนี้ใช้ผู้สร้างวิดีโอนี้อยู่แล้ว','info');return;}
       const total=studio.review.scenes.length,from=current==='meta_ai'?'Meta AI':'Google Flow',to=provider==='meta_ai'?'Meta AI':'Google Flow';
       openConfirm('เปลี่ยนผู้สร้างวิดีโอของงานนี้?',`จาก ${from} เป็น ${to}\nเมื่อกดทำต่อ ระบบจะสร้างวิดีโอใหม่ครบ ${total} ฉากด้วย ${to} จากภาพและบทเดิม คลิปเดิมยังเก็บไว้แต่ไม่รวมปนใน Final รอบใหม่`,{mode:'story_video_provider',jobId:studio.review.job_id,provider,revision:studio.review.revision},'เปลี่ยนผู้สร้างวิดีโอ');
       return;
     }
    if(target.hasAttribute('data-preview-notes')||target.hasAttribute('data-save-notes')){
      const thaw=freezeReviewInputs();
      try{
        const save=target.hasAttribute('data-save-notes'), drafts=pendingReviewDrafts(), token=studio.request;
        studio.saving=true;
        const data=await postAction(save?'story_save_pronunciation':'story_preview_pronunciation',{job_id:studio.review.job_id,revision:studio.review.revision,notes:readNotes()});
        if(token===studio.request&&modal.open){if(save){paintReview(data.review);restoreReviewDrafts(drafts,0,true);toast('บันทึกคำอ่านแล้ว ไม่ได้สร้างรูปหรือเสียงซ้ำ','success');await poll(true);}else paintVoice(data.voice_review);}
      }catch(error){toast(error.message,'error');}finally{studio.saving=false;thaw();}
    }
  });
  window.renderStudio=(state,partial=false)=>{
    const active=state.product_progress?.active?state.product_progress:state.story_progress?.active?state.story_progress:null;
    const stories=(state.stories||[]).filter(x=>!['deleted','cancelled','canceled','video_deleted'].includes(x.status));
    const pending=stories.filter(x=>!['ready','complete','completed'].includes(x.video_status));
    const productPending=(state.products||[]).filter(x=>!x.ready&&!['deleted','cancelled','canceled','video_deleted'].includes(x.status));
    const name=active?(state.products||[]).concat(stories).find(x=>x.id===active.job_id)?.title:'';
    const next=pending.find(x=>x.last_error)||pending[0];
    const view=active?(state.product_progress?.active?'products':state.story_progress?.mode==='drama'?'drama':'story'):next?(next.job_type==='drama_episode'?'drama':'story'):'products';
    const title=active?(active.action_required?'งานกำลังรอคุณ':'กำลังทำงาน'):pending.length+productPending.length?'มีงานที่ทำต่อได้':'พร้อมเริ่มเรื่องใหม่';
    const detail=active?`${name||active.job_id} • ${active.message||'กำลังดำเนินการ'}`:pending.length+productPending.length?`สินค้า ${productPending.length} งาน • เรื่องเล่า/ละคร ${pending.length} งาน • เก็บไฟล์เดิมไว้`:'เลือกคลิปสินค้า เรื่องเล่า หรือละคร ระบบจะบันทึกงานเป็นขั้นตอน';
    const markup=`<div><span class="eyebrow">YOUR WORKSPACE</span><h2>${escapeHtml(title)}</h2><p>${escapeHtml(detail)}</p>${active?.detail?`<small>${escapeHtml(active.detail)}</small>`:''}</div><div class="studio-now-actions">${active?`<span class="studio-running">${Math.round(Number(active.percent)||0)}% ตามผลงานจริง</span>`:''}<button class="button ${active?'primary':'secondary'}" data-page="${view}">${active?'ดูงานที่กำลังทำ':'ไปหน้างาน'} →</button></div>`;
    if(workspace.innerHTML!==markup)workspace.innerHTML=markup;
    const sys=state.system||{};
    const status=!sys.bridge_online?'ระบบหลักยังไม่พร้อม':!sys.extension_online?'รอเชื่อม Extension':!sys.extension_compatible?'รุ่น Extension ไม่ตรง':active?'กำลังทำงาน':'พร้อมทำงาน';
    $('#side-status-text').textContent=status;
    if(sys.extension_online&&!sys.extension_compatible)$('#side-extension').textContent=`ติดตั้ง ${sys.extension_version||'?'} • โปรแกรมต้องการ ${state.app.extension_required}`;
    const ready=!!(sys.bridge_online&&sys.extension_online&&sys.extension_compatible);
    const heroStatus=$('.phone-screen strong');heroStatus.textContent=active?'WORKING':ready?'READY':'SETUP';
    $('.hero-proof span:last-child').textContent=sys.safe_mode?'✓ Safe Mode เปิดอยู่':'• โหมดโพสต์จริง';
    $('.float-a b').textContent=active?'กำลังทำตามขั้นตอน':'สร้างบทและภาพด้วย AI';
    if(!partial)for(const page of ['story','drama']){
      const select=$('#'+page+'-review-job'),selected=select.value;
      const list=stories.filter(x=>page==='drama'?x.job_type==='drama_episode':x.job_type!=='drama_episode');
      const options=list.map(x=>`<option value="${escapeHtml(x.id)}">${escapeHtml(x.title)} • ${escapeHtml(x.id)}</option>`).join('')||'<option value="">ยังไม่มีงาน</option>';
      if(select.innerHTML!==options){select.innerHTML=options;if(list.some(x=>x.id===selected))select.value=selected;}
      $(`[data-open-studio="${page}"]`).disabled=!list.length;
    }
    // Recovery cards are recreated by the old renderer. Add review affordance once.
    $$('[data-retry-story]').forEach(button=>{const footer=button.parentElement;if(!footer.querySelector('[data-review-story]')){const review=el('button','button secondary compact','ตรวจฉาก / คำอ่าน');review.dataset.reviewStory=button.dataset.retryStory;button.before(review);}});
  };
  if(ui.state)window.renderStudio(ui.state);
})();
