(() => {
  const page=document.querySelector('[data-view="products"]');if(!page)return;
  const panel=document.createElement('aside');panel.className='panel product-continue';panel.setAttribute('aria-label','จัดการงานคลิปสินค้า');
  panel.innerHTML='<h2 id="product-jobs-heading">งานที่ยังไม่เสร็จ</h2><button class="button danger" id="product-jobs-clear-all" aria-describedby="product-jobs-clear-help" disabled>ลบงานค้างทั้งหมด</button><p id="product-jobs-clear-help" class="product-jobs-help">ลบถาวรทั้งงานและไฟล์ในงาน กู้คืนไม่ได้<br>รวมรายการที่ยังไม่แสดง • ไม่ลบคลิปสำเร็จ</p><p id="product-continue-notice" role="status" aria-live="polite"></p><details class="product-jobs-drawer"><summary>ดูรายการ / ทำต่อ</summary><div class="product-job-tabs" aria-label="รายการงานสินค้า"><button class="button secondary" data-job-view="pending">งานค้าง</button><button class="button secondary" data-job-view="hidden">ซ่อนไว้</button></div><div class="product-job-bulk"><label><input type="checkbox" id="product-jobs-select-all"> เลือกที่แสดง</label><button class="button secondary" id="product-jobs-bulk" disabled>ลบที่เลือกถาวร</button></div><div id="product-continue-latest"></div><div class="product-job-pagination"><small id="product-jobs-count"></small><button class="button secondary" id="product-jobs-more" hidden>แสดงเพิ่ม 5 รายการ</button></div></details><div class="product-jobs-legacy" hidden><button class="button secondary" id="product-jobs-clear-legacy" aria-describedby="product-jobs-legacy-help">ลบรายการเก่าถาวร</button><p id="product-jobs-legacy-help" class="product-jobs-help">เฉพาะรายการในถังขยะเดิม • กู้คืนไม่ได้</p></div>';
  const form=page.querySelector('.create-panel');
  if(form){const title=document.createElement('h2');title.textContent='สร้างคลิปใหม่';form.prepend(title);
    const layout=document.createElement('div');layout.className='product-workspace';form.before(layout);layout.append(form,panel);
  }else page.append(panel);
  // Keep the summary discoverable without forcing a long recovery list open.
  const drawer=panel.querySelector('.product-jobs-drawer'),drawerKey='smartflow.productJobsExpanded';
  try{drawer.open=localStorage.getItem(drawerKey)==='true';}catch(_){/* Storage may be unavailable in the desktop host. */}
  drawer.addEventListener('toggle',()=>{try{localStorage.setItem(drawerKey,String(drawer.open));}catch(_){}});
  // The product planning control owns the count. Resume uses the saved job,
  // never the current new-job selection.
  const source=page.querySelector('.product-source-row');
  if(source){const controls=[...source.children].filter(n=>!n.classList.contains('product-link-field'));
    const settings=document.createElement('details');settings.className='product-options';settings.innerHTML='<summary>เลือก AI และโมเดลที่ใช้สร้าง</summary><div class="product-option-grid"></div>';
    settings.querySelector('div').append(...controls);source.after(settings);}
  const create=document.querySelector('#create-product');if(create)create.textContent='✦ สร้างคลิปใหม่';
  const enqueue=document.querySelector('#enqueue-product');if(enqueue)enqueue.textContent='＋ เพิ่มเข้าคิว';
  const old=page.querySelector('.affiliate-tools');if(old){const tools=document.createElement('details');tools.className='product-options';tools.innerHTML='<summary>เครื่องมือจัดการงานสินค้าแบบเดิม</summary>';old.before(tools);tools.append(old);}
  const pageSize=5;
  let sending=false,lastMarkup='',view='pending',visible=[],pending=[],legacyTrash=[],selected=new Set(),displayLimit=pageSize;
  const deleted=new Set(); // Receipt-backed removals cannot reappear in an older in-flight poll.
  const deletionKey='smartflow.productDeletionRequest';
  let pendingDeletion=null;
  try{const saved=JSON.parse(sessionStorage.getItem(deletionKey)||'null');if(saved?.request_id&&Array.isArray(saved.job_ids))pendingDeletion=saved;}catch(_){}
  const deletionActions=document.createElement('div');deletionActions.className='product-deletion-actions';
  deletionActions.innerHTML='<button class="button secondary" id="product-jobs-delete-status" hidden>ตรวจผลการลบ</button><button class="button secondary" id="product-jobs-delete-retry" hidden>ลองลบส่วนที่เหลือ</button>';
  panel.querySelector('#product-continue-notice').after(deletionActions);
  const esc=value=>escapeHtml(String(value??''));
  const finished=j=>j.ready || (j.status==='ready'&&j.video_status==='ready');
  const canDelete=state=>state.product_job_delete_version===1;
  const workBusy=state=>!!window.productPreparationActive||[state.product_progress,state.story_progress,state.presenter_progress].some(p=>p?.active);
  const busy=state=>sending||!!pendingDeletion||workBusy(state);
  function rows(state){
    const map=new Map();
    for(const j of [...(state.products||[]),...(state.stories||[]).filter(j=>j.content_kind==='product')]){
      if(!j.id||deleted.has(j.id)||['deleted','video_deleted'].includes(j.status)||['deleted','video_deleted'].includes(j.video_status))continue;
      map.set(j.id,j);
    }
    for(const j of state.product_preparations||[]){
      if(!j.id||deleted.has(j.id)||map.has(j.id)||['deleted','video_deleted'].includes(j.status))continue;
      map.set(j.id,{...j,title:j.product_name||'สินค้าจาก Shopee',sourcePreparation:true});
    }
    return [...map.values()].sort((a,b)=>String(b.created_at||b.updated_at||'').localeCompare(String(a.created_at||a.updated_at||''))||b.id.localeCompare(a.id));
  }
  function card(j,state){
    const active=[state.product_progress,state.story_progress].find(p=>p?.active&&p.job_id===j.id);
    const blocked=busy(state);
    const done=finished(j),cancelled=['cancelled','canceled'].includes(j.status)||j.automation_status==='cancelled';
    const status=active?'กำลังสร้าง':done?'เสร็จแล้ว':cancelled?'หยุดไว้':j.last_error?SmartFlowStatus.RESUMABLE_FAILED:'หยุดไว้';
     const total=Number(j.scene_count||j.segment_target_count||j.flow_target_clip_count||3),images=Number(j.image_count||j.generated_image_count||0),provider=(j.video_generation_mode||j.video_ai_provider)==='meta_ai'?'Meta AI':'Google Flow',videos=Number(provider==='Meta AI'?j.meta_clip_count||0:j.flow_clip_count||j.flow_count||0);
    const plan=j.video_plan_summary;
    const videoSummary=plan?`วิดีโอ ${Number(plan.completed||0)}/${total} • Flow ${Number(plan.flow||0)} / Meta ${Number(plan.meta||0)}${plan.local?` / ภาพเคลื่อนไหว ${Number(plan.local)}`:''}`:`${provider} ${videos}/${total}`;
    const preview=String(j.preview_url||'').startsWith('/api/desktop/media?')?`<img src="${esc(j.preview_url)}" alt="ภาพตัวอย่าง" loading="lazy">`:'<div class="product-continue-placeholder" aria-hidden="true">▶</div>';
    const primary=active?'<button class="button primary" data-product-running>ดูงานที่กำลังทำ</button>':`<button class="button primary" data-product-continue="${esc(j.id)}" ${blocked?'disabled':''}>▶ ทำต่อ</button>`;
    const detail=j.id.startsWith('STORY-')?`data-review-story="${esc(j.id)}"`:`data-product-detail="${esc(j.id)}"`;
    const manage=(op,label)=>`<button class="button secondary" data-job-operation="${op}" data-job-id="${esc(j.id)}" ${blocked||(op==='delete'&&!canDelete(state))?'disabled':''}>${label}</button>`;
    const select=`<label class="product-job-select"><input type="checkbox" data-job-select="${esc(j.id)}" aria-label="เลือก ${esc(j.title)}" ${selected.has(j.id)?'checked':''} ${blocked?'disabled':''}></label>`;
    if(j.sourcePreparation){
      const readiness=j.capture_ready?`พร้อมทำต่อ • รูป ${Number(j.source_image_count||0)} รูป`:'ชื่อหรือรูปยังไม่ครบ • ทำต่อเพื่อลองอ่านใหม่';
      const resume=`<button class="button primary" data-resume-product-source="${esc(j.id)}" data-source-request-id="${esc(j.request_id||'')}" ${blocked?'disabled':''}>ทำต่อ</button>`;
      return `<article class="product-continue-card product-source-preparation">${select}<div class="product-job-info"><h3>${esc(j.title)}</h3><p class="product-continue-badge">สินค้าเตรียมไว้ • ยังไม่ส่งเข้า AI</p><p>${esc(readiness)}</p><div class="product-continue-actions">${resume+manage('delete','ลบถาวร')}</div><details class="product-job-details"><summary>รายละเอียด</summary><small>${esc(j.id)}</small>${manage(view==='hidden'?'show':'hide',view==='hidden'?'แสดงในงานค้าง':'ซ่อนรายการ')}</details></div></article>`;
    }
    return `<article class="product-continue-card">${select}${preview}<div class="product-job-info"><h3>${esc(j.title)}</h3><p class="product-continue-badge">${status}</p><p>ภาพ ${images}/${total} • ${videoSummary}</p><small>${esc(j.id)}</small>${active?`<p>${esc(active.message)}</p>`:''}<div class="product-continue-actions">${primary}<button class="button secondary" ${detail}>ดูงาน</button></div><div class="product-continue-actions">${manage(view==='hidden'?'show':'hide',view==='hidden'?'แสดงในงานค้าง':'ซ่อน')+manage('delete','ลบถาวร')}</div></div></article>`;
  }
  function bulk(){const btn=panel.querySelector('#product-jobs-bulk'),all=panel.querySelector('#product-jobs-select-all');
    const blocked=busy(ui.state||{});
    const clearAll=panel.querySelector('#product-jobs-clear-all');
    const compatible=canDelete(ui.state||{});
    clearAll.disabled=blocked||!compatible||!pending.length;clearAll.textContent=`ลบงานค้างทั้งหมด (${pending.length})`;
    panel.querySelector('#product-jobs-clear-help').textContent=compatible?'ลบถาวรทั้งงานและไฟล์ในงาน กู้คืนไม่ได้ • รวมรายการที่ยังไม่แสดง ไม่ลบคลิปสำเร็จ':'เปิดโปรแกรมใหม่เพื่อใช้การลบถาวร';
    const cleanup=panel.querySelector('#product-jobs-clear-legacy');
    cleanup.closest('.product-jobs-legacy').hidden=!legacyTrash.length;
    cleanup.disabled=blocked||!compatible||!legacyTrash.length;cleanup.textContent=`ลบรายการเก่าถาวร (${legacyTrash.length})`;
    const check=panel.querySelector('#product-jobs-delete-status'),retry=panel.querySelector('#product-jobs-delete-retry');
    check.hidden=!pendingDeletion;check.disabled=sending;
    retry.hidden=pendingDeletion?.status!=='partial';retry.disabled=sending||!compatible||workBusy(ui.state||{});
    btn.disabled=blocked||!compatible||!selected.size;btn.textContent='ลบที่เลือกถาวร'+(selected.size?` (${selected.size})`:'');
    all.disabled=blocked||!visible.length;
    all.checked=!!visible.length&&visible.every(j=>selected.has(j.id));all.indeterminate=selected.size>0&&!all.checked;
  }
  window.renderProductContinue=state=>{
    const all=rows(state),controls=state.product_job_controls||{};
    const groups={pending:[],hidden:[]};legacyTrash=[];
    for(const j of all){const c=controls[j.id]||{};if(c.permanently_deleted||c.deleted||finished(j))continue;if(c.trashed)legacyTrash.push(j);else groups[c.hidden?'hidden':'pending'].push(j);}
    pending=groups.pending;
    visible=groups[view].slice(0,displayLimit);selected=new Set([...selected].filter(id=>visible.some(j=>j.id===id)));
    panel.querySelector('#product-jobs-heading').textContent=`งานที่ยังไม่เสร็จ · ${groups.pending.length}`;
    for(const b of panel.querySelectorAll('[data-job-view]')){b.setAttribute('aria-pressed',String(b.dataset.jobView===view));b.textContent=({pending:'งานค้าง',hidden:'ซ่อนไว้'})[b.dataset.jobView]+` (${groups[b.dataset.jobView].length})`;}
    const main=visible.map(j=>card(j,state)).join('')||'<p class="product-jobs-empty">ไม่มีงานในรายการนี้</p>';
    if(main!==lastMarkup){lastMarkup=main;panel.querySelector('#product-continue-latest').innerHTML=main;}
    panel.querySelector('#product-jobs-count').textContent=groups[view].length?`แสดง ${visible.length} จาก ${groups[view].length} รายการ`:'';
    panel.querySelector('#product-jobs-more').hidden=visible.length>=groups[view].length;
    bulk();
  };
  panel.addEventListener('error',e=>{if(e.target.tagName==='IMG'){const p=document.createElement('div');p.className='product-continue-placeholder';p.textContent='▶';p.setAttribute('aria-label','ไม่มีภาพตัวอย่าง');e.target.replaceWith(p);}},true);
  panel.addEventListener('change',e=>{if(e.target.matches('[data-job-select]')){const id=e.target.dataset.jobSelect;e.target.checked?selected.add(id):selected.delete(id);bulk();}
    if(e.target.id==='product-jobs-select-all'){selected=new Set(e.target.checked?visible.map(j=>j.id):[]);lastMarkup='';renderProductContinue(ui.state||{});}
  });
  function rememberDeletion(){try{pendingDeletion?sessionStorage.setItem(deletionKey,JSON.stringify({request_id:pendingDeletion.request_id,job_ids:pendingDeletion.job_ids,scope:pendingDeletion.scope})):sessionStorage.removeItem(deletionKey);}catch(_){} }
  function deletionId(){
    if(crypto.randomUUID)return crypto.randomUUID();
    const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
    return [...bytes].map((n,i)=>([4,6,8,10].includes(i)?'-':'')+n.toString(16).padStart(2,'0')).join('');
  }
  function acceptDeletion(result){
    const receipt=result?.deletion;
    if(receipt?.request_id===pendingDeletion?.request_id&&receipt.accepted===false&&['rejected','not_found'].includes(receipt.status))return receipt;
    if(result?.ok===false)throw Error(result.error||'ตรวจผลการลบไม่สำเร็จ');
    if(!receipt||receipt.request_id!==pendingDeletion?.request_id||!['deleting','complete','partial'].includes(receipt.status))throw Error('ยังยืนยันผลการลบไม่ได้');
    if(result.product_job_controls)ui.state.product_job_controls=result.product_job_controls;
    const confirmed=new Set((receipt.deleted_ids||[]).filter(id=>pendingDeletion.job_ids.includes(id)));
    for(const id of confirmed)deleted.add(id);
    for(const key of ['products','stories','product_preparations'])if(Array.isArray(ui.state[key]))ui.state[key]=ui.state[key].filter(j=>!confirmed.has(j.id));
    pendingDeletion.status=receipt.status;rememberDeletion();selected.clear();lastMarkup='';renderProductContinue(ui.state||{});
    return receipt;
  }
  async function deleteRequest(submit=false){
    if(sending||!pendingDeletion||(submit&&!canDelete(ui.state||{})))return;
    const notice=panel.querySelector('#product-continue-notice');
    sending=true;lastMarkup='';renderProductContinue(ui.state||{});notice.textContent='กำลังลบงานและไฟล์ในงานถาวร…';
    try{
      let result;
      if(submit){
        try{result=await postAction('product_jobs_manage',{operation:'delete',confirmed:true,request_id:pendingDeletion.request_id,job_ids:[...pendingDeletion.job_ids],...(pendingDeletion.scope?{scope:pendingDeletion.scope}:{})});}
        catch(_){notice.textContent='ยังไม่ได้รับผลยืนยัน • กำลังตรวจคำขอลบเดิม ไม่ส่งคำสั่งลบซ้ำ';}
      }
      while(pendingDeletion){
        if(!result)result=await postAction('product_jobs_delete_status',{request_id:pendingDeletion.request_id});
        const receipt=acceptDeletion(result),count=(receipt.deleted_ids||[]).length,total=pendingDeletion.job_ids.length;
        if(receipt.accepted===false&&['rejected','not_found'].includes(receipt.status)){
          notice.textContent=receipt.error?(window.smartflowSafeError?.(receipt.error)||'โปรแกรมไม่รับคำขอลบ • ยังไม่ได้ลบงาน'):'โปรแกรมยืนยันว่าไม่ได้รับคำขอลบ • ยังไม่ได้ลบงาน';
          // A rejected retry cannot erase an earlier accepted partial batch.
          if(!pendingDeletion.status)pendingDeletion=null;
          rememberDeletion();toast(notice.textContent,'error');break;
        }
        if(receipt.status==='complete'){
          notice.textContent=`ลบถาวรแล้ว ${count} รายการ • งานและไฟล์ในงานกู้คืนไม่ได้`;
          pendingDeletion=null;rememberDeletion();
          try{await poll(true);}catch(_){notice.textContent+=' • โหลดรายการล่าสุดไม่สำเร็จ';}
          break;
        }
        if(receipt.status==='partial'){
          const failed=receipt.failed||[];
          notice.textContent=`ลบถาวรแล้ว ${count}/${total} รายการ • ลบไม่สำเร็จ ${failed.length} รายการ • ตรวจงานที่ยังค้างก่อนลองอีกครั้ง`;
          toast(notice.textContent,'error');break;
        }
        notice.textContent=`กำลังลบถาวร ${count}/${total} รายการ • รอผลเดิม ไม่ส่งคำสั่งซ้ำ`;
        await new Promise(resolve=>setTimeout(resolve,500));result=null;
      }
    }catch(error){notice.textContent=`${window.smartflowSafeError?.(error.message)||'ตรวจผลเดิมไม่สำเร็จ'} • ตรวจผลการลบเดิมก่อน ไม่ส่งคำสั่งซ้ำ`;toast(notice.textContent,'error');}
    finally{sending=false;lastMarkup='';renderProductContinue(ui.state||{});}
  }
  async function manage(operation,ids,scope=''){
    if(busy(ui.state||{})||!ids.length)return;
    ids=[...ids]; // Freeze the exact confirmation set, never a later inventory.
    if(operation==='delete'){
      if(!canDelete(ui.state||{}))return;
      const target=scope==='all_pending'?`งานค้างทั้งหมด ${ids.length} รายการ`:scope==='legacy_trash'?`รายการในถังขยะเดิม ${ids.length} รายการ`:`งานที่เลือก ${ids.length} รายการ`;
      const excludes=scope==='all_pending'?'ไม่รวมงานซ่อนไว้ คลิปสำเร็จ หรืองานอื่น':'ไม่รวมคลิปสำเร็จหรืองานอื่นที่ไม่ได้เลือก';
      if(!await window.smartflowConfirm(`ลบ${target}ถาวร?\nลบข้อมูลรายการงาน พร้อมรูป เสียง และคลิปที่อยู่ในโฟลเดอร์งานที่เลือก\n${excludes}\nกู้คืนไม่ได้ และนำงานเหล่านี้ออกจากคิว`,{title:'ลบงานสินค้า?',acceptLabel:'ลบถาวร'}))return;
      pendingDeletion={request_id:deletionId(),job_ids:ids,scope};rememberDeletion();await deleteRequest(true);return;
    }
    sending=true;lastMarkup='';renderProductContinue(ui.state||{});const notice=panel.querySelector('#product-continue-notice');notice.textContent='กำลังบันทึก…';
    try{const result=await postAction('product_jobs_manage',{operation,job_ids:ids,confirmed:false});
      if(result?.ok===false)throw Error(result.error||'บันทึกไม่สำเร็จ');
      if(result.product_job_controls)ui.state.product_job_controls=result.product_job_controls;
      selected.clear();notice.textContent='บันทึกแล้ว';await poll(true);
    }catch(error){notice.textContent=window.smartflowSafeError?.(error.message)||'ทำรายการไม่สำเร็จ';toast(error.message,'error');}
    finally{sending=false;lastMarkup='';renderProductContinue(ui.state||{});}
  }
  panel.addEventListener('click',async e=>{
    if(e.target.closest('#product-jobs-delete-status')){await deleteRequest();return;}
    if(e.target.closest('#product-jobs-delete-retry')){
      if(sending||workBusy(ui.state||{})||pendingDeletion?.status!=='partial')return;
      if(await window.smartflowConfirm('ลองลบส่วนที่เหลือจากคำขอเดิมถาวร?\nลบข้อมูลรายการงาน พร้อมรูป เสียง และคลิปในงาน กู้คืนไม่ได้\nไม่เพิ่มงานใหม่และไม่ลบคลิปสำเร็จหรืองานอื่น',{title:'ลองลบส่วนที่เหลือ?',acceptLabel:'ลบถาวร'}))await deleteRequest(true);
      return;
    }
    if(e.target.closest('#product-jobs-clear-all')){await manage('delete',pending.map(j=>j.id),'all_pending');return;}
    if(e.target.closest('#product-jobs-clear-legacy')){await manage('delete',legacyTrash.map(j=>j.id),'legacy_trash');return;}
    const resumeSource=e.target.closest('[data-resume-product-source]');
    if(resumeSource){
      if(resumeSource.disabled||busy(ui.state||{}))return;
      window.dispatchEvent(new CustomEvent('smartflow:resume-product-source',{detail:{product_id:resumeSource.dataset.resumeProductSource,request_id:resumeSource.dataset.sourceRequestId||''}}));
      return;
    }
    const tab=e.target.closest('[data-job-view]');if(tab&&!sending){view=tab.dataset.jobView;displayLimit=pageSize;selected.clear();lastMarkup='';renderProductContinue(ui.state||{});return;}
    if(e.target.closest('#product-jobs-more')){displayLimit+=pageSize;renderProductContinue(ui.state||{});return;}
    const operation=e.target.closest('[data-job-operation]');if(operation){await manage(operation.dataset.jobOperation,[operation.dataset.jobId]);return;}
    if(e.target.closest('#product-jobs-bulk')){await manage('delete',[...selected]);return;}
    if(e.target.closest('[data-product-running]')){restoreProgress();return;}
    const button=e.target.closest('[data-product-continue]');if(!button||button.disabled||busy(ui.state||{}))return;
    sending=true;button.disabled=true;const notice=panel.querySelector('#product-continue-notice');notice.textContent='กำลังตรวจงานและไฟล์เดิม…';
    try{
      const result=await postAction('product_continue',{job_id:button.dataset.productContinue});
      if(result?.ok===false)throw Error(result.error||'ยังเริ่มทำต่อไม่ได้ กรุณาตรวจสถานะงาน');
      notice.textContent='รับคำสั่งทำต่อจากงานเดิมแล้ว';await poll(true);
      if(ui.state?.product_progress?.active||ui.state?.story_progress?.active)restoreProgress();
    }catch(error){notice.textContent=window.smartflowSafeError?.(error.message)||'ทำรายการไม่สำเร็จ';toast(error.message,'error');}
    finally{sending=false;lastMarkup='';window.renderProductContinue(ui.state||{});}
  });
  window.renderProductContinue(ui.state||{});
  if(pendingDeletion)deleteRequest(); // Read-only reconciliation after a page reload.
})();
