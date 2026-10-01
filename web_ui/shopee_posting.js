/* Explicit selection only. Polling never sends, resumes or republishes. */
(() => {
  'use strict';
  const panel=document.querySelector('#shopee-posting'); if(!panel)return;
  const q=s=>panel.querySelector(s), picks=new Set(), queued=new Set(), dirty=new Set();
  const names={draft:'ร่าง',queued:'เข้าคิวแล้ว',checking:'กำลังตรวจไฟล์ / มือถือ',transferring:'กำลังโอนไฟล์',prepared:'เตรียมไฟล์แล้ว',editing:'กำลังจัดโพสต์',settings:'กำลังตรวจสวิตช์',ready:'ตรวจพร้อมแล้ว',send_pending:'เริ่มส่งแล้ว',processing:'ส่งแล้ว • รอตรวจผล',published:'โพสต์สำเร็จ',review:'พักก่อนส่ง • รอตรวจ',unknown:'เริ่มส่งแล้ว • ต้องตรวจผลเดิม'};
  names.skipped='ข้ามสินค้า • ยังไม่ได้โพสต์';
  const editable=new Set(['draft','review','prepared','skipped']);
  let items=[], state={items:[],revision:-1}, sending=false, renderedRevision=-1, defaultsDirty=false, defaultsRevision=0, requestSerial=0, acceptedSerial=0, polling=false;
  const defaultOptions={schema:1,allow_reuse:false,ai_label:true};
  const summary=o=>o?`ใช้ซ้ำ: ${o.allow_reuse?'เปิด':'ปิด'} • ป้าย AI: ${o.ai_label?'เปิด':'ปิด'}${o.allow_missing_controls==null?'':` • สวิตช์ที่ไม่มี: ${o.allow_missing_controls?'ข้ามและโพสต์ต่อ':'พักให้ตรวจ'}`}`:'งานเก่า • ไม่ได้บันทึกตัวเลือก';
  const formOptions=()=>({schema:1,allow_reuse:q('#sp-default-reuse').checked,ai_label:q('#sp-default-ai').checked,allow_missing_controls:q('#sp-default-available').checked});
  function optionFields(o){return `<div class="sp-option-grid"><label class="sp-switch"><input type="checkbox" role="switch" data-option="allow_reuse" ${o.allow_reuse?'checked':''}><span>อนุญาตใช้ซ้ำ / เผยแพร่ต่อ<br><small>แบบแยก: ตั้ง Duet และตัดต่อด้วย</small></span><strong>${o.allow_reuse?'เปิด':'ปิด'}</strong></label><label class="sp-switch"><input type="checkbox" role="switch" data-option="ai_label" ${o.ai_label?'checked':''}><span>เพิ่มป้ายกำกับ AI</span><strong>${o.ai_label?'เปิด':'ปิด'}</strong></label><label class="sp-switch"><input type="checkbox" role="switch" data-option="allow_missing_controls" ${o.allow_missing_controls!==false?'checked':''}><span>ข้ามสวิตช์ที่ไม่มี แล้วโพสต์ต่อ</span><strong>${o.allow_missing_controls!==false?'เปิด':'ปิด'}</strong></label></div>`;}
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const media=(id,kind)=>'/api/desktop/media?item_id='+encodeURIComponent(id)+'&kind='+kind;
  const visible=()=>!document.hidden&&panel.closest('.page').classList.contains('active');
  const message=s=>{q('#sp-message').textContent=s||'';};
  async function call(action,payload={}){
    const serial=++requestSerial;
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),20000);
    try{
      const r=await fetch('/api/desktop/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,payload}),signal:controller.signal});
      const data=await r.json(); if(!r.ok||!data.ok)throw Error(data.error||'คำสั่งไม่สำเร็จ');
      if(data.posting&&(data.posting.revision>state.revision||(data.posting.revision===state.revision&&serial>=acceptedSerial))){const changedRun=state.posting_run?.id!==data.posting.posting_run?.id;state=data.posting;acceptedSerial=serial;if(changedRun){message(state.message||'');if(state.posting_run?.status==='ready'&&!state.busy){queued.clear();const available=new Set(eligible().map(x=>x.id));for(const id of state.posting_run.ids||[])if(available.has(id))queued.add(id);}}renderQueue();window.SmartFlowPostProgress?.update(state.posting_run);}
      return data;
    }finally{clearTimeout(timer);}
  }
  function shown(){const text=q('#sp-search').value.trim().toLowerCase();return items.filter(x=>x.title.toLowerCase().includes(text));}
  function renderLibrary(){
    q('#sp-library').innerHTML=shown().map(x=>`<article class="sp-card"><input type="checkbox" data-pick="${esc(x.item_id)}" aria-label="เลือก ${esc(x.title)}" ${picks.has(x.item_id)?'checked':''}><img loading="lazy" src="${esc(media(x.item_id,'preview'))}" alt="ปก"><div><h4>${esc(x.title)}</h4><button type="button" class="button ghost compact" data-preview="${esc(x.item_id)}">▶ ดูคลิป</button></div></article>`).join('')||'<p>ไม่พบคลิปสินค้า Final ที่มีลิงก์ Shopee</p>';
    q('#sp-count').textContent=picks.size;
  }
  function renderQueue(){
    q('#sp-account').textContent=state.account?.name?'บัญชีที่จะโพสต์: '+state.account.name:'ยังไม่ได้อ่านบัญชีจากมือถือ';
    if(state.message)message(state.message);
    panel.querySelectorAll('[data-sp]').forEach(b=>b.disabled=sending||Boolean(state.busy)&&!['pause','refresh','progress'].includes(b.dataset.sp));
    syncSelection();
    if(!defaultsDirty){const o=state.defaults||defaultOptions;q('#sp-default-reuse').checked=o.allow_reuse;q('#sp-default-ai').checked=o.ai_label;q('#sp-default-available').checked=o.allow_missing_controls!==false;defaultsRevision=state.revision;}
    q('#sp-default-reuse').disabled=q('#sp-default-ai').disabled=q('#sp-default-available').disabled=Boolean(state.busy)||sending;
    q('[data-default-state="allow_reuse"]').textContent=q('#sp-default-reuse').checked?'เปิด':'ปิด';
    q('[data-default-state="ai_label"]').textContent=q('#sp-default-ai').checked?'เปิด':'ปิด';
    q('[data-default-state="allow_missing_controls"]').textContent=q('#sp-default-available').checked?'เปิด':'ปิด';
    q('#sp-default-status').textContent=defaultsDirty?'มีตัวเลือกที่ยังไม่บันทึก • บันทึกค่าเริ่มต้น หรือใช้กับคลิปที่เลือกก่อนเริ่ม':'ค่าเริ่มต้นใช้กับคลิปที่เพิ่มเข้าคิวใหม่ ไม่เปลี่ยนงานเดิม';
    lockRows();
    if(renderedRevision===state.revision||dirty.size||q('#sp-queue').contains(document.activeElement))return;
    renderedRevision=state.revision;
    const rows=(state.items||[]).filter(x=>x.phase!=='removed');
    q('#sp-queue').innerHTML=rows.map(x=>{const can=editable.has(x.phase)&&!state.busy;const o=x.post_options||(can?defaultOptions:null);return `<article class="sp-draft" data-row="${esc(x.id)}" data-revision="${x.revision}" data-phase="${esc(x.phase)}"><header><input type="checkbox" data-queued="${esc(x.id)}" aria-label="โพสต์ ${esc(x.title)}" ${queued.has(x.id)?'checked':''} ${can?'':'disabled'}><h4>${esc(x.title)}</h4><span class="sp-state">${esc(names[x.phase]||x.phase)}</span></header><p>${esc(x.message)}</p><p class="sp-summary">${esc(summary(o))}</p>${can?`${optionFields(o)}<p class="sp-dirty" role="status"></p><label>แคปชัน<textarea data-caption maxlength="150">${esc(x.caption)}</textarea><span class="sp-counter">${x.caption.length}/150 ตัวอักษร</span></label><label>ลิงก์สินค้า<input type="url" data-url value="${esc(x.product_url)}"></label><div class="sp-controls"><button class="button secondary compact" type="button" data-save>บันทึกแคปชัน / ลิงก์ / ตัวเลือก</button><button class="button ghost compact" type="button" data-remove>เอาออกจากคิว</button><button class="button ghost compact" type="button" data-preview="${esc(x.item_id)}">▶ ตรวจคลิป</button></div>`:`<p>${esc(x.caption)}</p><p class="sp-note">${esc(x.product_url)}</p>`}${x.transfer?`<p class="sp-note">อัลบั้มบนมือถือ: ${esc(x.transfer.album)}</p>`:''}${x.phase==='unknown'?'<p class="sp-note">ห้ามส่งซ้ำ: เปิดโปรไฟล์ Shopee ตรวจโพสต์เดิมก่อน ระบบจะไม่เริ่มงานนี้ใหม่อัตโนมัติ</p>':''}</article>`;}).join('')||'<p>ติ๊กเลือกคลิปด้านบน แล้วกดเพิ่มเข้าคิว</p>';
    q('#sp-queue').querySelectorAll('[data-phase="unknown"]').forEach(row=>row.insertAdjacentHTML('beforeend','<button class="button secondary compact" type="button" data-reconcile>ตรวจหลักฐานอัปโหลดเดิม (ไม่โพสต์ซ้ำ)</button>'));
    lockRows();
  }
  function lockRows(){
    const rows=new Map((state.items||[]).map(x=>[x.id,x]));
    panel.querySelectorAll('[data-row]').forEach(row=>{const data=rows.get(row.dataset.row);const locked=sending||Boolean(state.busy)||!data||!editable.has(data.phase)||Boolean(data.publish_intent);row.querySelectorAll('button,input,textarea').forEach(el=>el.disabled=el.hasAttribute('data-reconcile')?sending||Boolean(state.busy)||data?.phase!=='unknown':locked);});
    const canPick=new Set(eligible().map(x=>x.id));panel.querySelectorAll('[data-queued]').forEach(el=>el.disabled=sending||Boolean(state.busy)||!canPick.has(el.dataset.queued));
  }
  function eligible(){const ids=Array.isArray(state.restartable_ids)?new Set(state.restartable_ids):null;return (state.items||[]).filter(x=>ids?ids.has(x.id):x.phase!=='skipped'&&editable.has(x.phase)&&!x.publish_intent&&!x.receipt);}
  function syncSelection(){
    const ids=new Set(eligible().map(x=>x.id));for(const id of queued)if(!ids.has(id))queued.delete(id);
    const all=q('#sp-queue-all');all.checked=ids.size>0&&queued.size===ids.size;all.indeterminate=queued.size>0&&queued.size<ids.size;all.disabled=sending||Boolean(state.busy)||!ids.size;
    q('#sp-queue-count').textContent=`เลือกแล้ว ${queued.size} / ${ids.size} คลิปที่ยังไม่โพสต์`;
    q('[data-sp="start"]').textContent=queued.size?`▶ ออโตโพสต์ ${queued.size} คลิปที่เลือก`:'▶ ออโตโพสต์คลิปที่ติ๊ก';
    q('[data-sp="start"]').disabled=sending||Boolean(state.busy)||!queued.size;
    q('[data-sp="reset-unsent"]').disabled=sending||Boolean(state.busy)||!ids.size;
    panel.querySelectorAll('[data-queued]').forEach(el=>el.checked=queued.has(el.dataset.queued));
    lockRows();
  }
  async function refresh(){try{const data=await call('shopee_post_library');items=data.items||[];renderLibrary();}catch(e){message(e.message);}}
  panel.addEventListener('input',e=>{if(e.target.matches('[data-caption],[data-url],[data-option]')){const row=e.target.closest('[data-row]');dirty.add(row.dataset.row);row.querySelector('.sp-dirty').textContent='ยังไม่ได้บันทึก';if(e.target.matches('[data-option]'))e.target.closest('label').querySelector('strong').textContent=e.target.checked?'เปิด':'ปิด';}if(e.target.matches('[data-caption]'))e.target.nextElementSibling.textContent=e.target.value.length+'/150 ตัวอักษร';if(e.target.matches('#sp-default-reuse,#sp-default-ai,#sp-default-available')){if(!defaultsDirty)defaultsRevision=state.revision;defaultsDirty=true;renderQueue();}});
  q('#sp-search').addEventListener('input',renderLibrary);
  panel.addEventListener('change',e=>{if(e.target.id==='sp-queue-all'){queued.clear();if(e.target.checked)eligible().forEach(x=>queued.add(x.id));syncSelection();return;}const key=e.target.dataset.pick||e.target.dataset.queued;if(!key)return;const set=e.target.dataset.pick?picks:queued;e.target.checked?set.add(key):set.delete(key);q('#sp-count').textContent=picks.size;syncSelection();});
  panel.addEventListener('click',async e=>{
    const b=e.target.closest('button');if(!b||b.disabled||sending)return;
    if(b.dataset.preview){q('#sp-preview').hidden=false;q('#sp-preview').innerHTML=`<video controls playsinline preload="metadata" src="${esc(media(b.dataset.preview,'video'))}"></video><button class="button ghost" type="button" data-sp="close-preview">ปิดตัวอย่าง</button>`;return;}
    const action=b.dataset.sp;
    if(action==='close-preview'){q('#sp-preview video')?.pause();q('#sp-preview').hidden=true;return;}
    if(action==='select-all'){shown().slice(0,30).forEach(x=>picks.add(x.item_id));renderLibrary();return;}
    if(action==='clear'){picks.clear();renderLibrary();return;}
    if(action==='clear-queue'){queued.clear();syncSelection();return;}
    if(action==='progress'){window.SmartFlowPostProgress?.open();return;}
    sending=true;renderQueue();
    try{
      const row=b.closest('[data-row]');
      if(b.hasAttribute('data-save')){await call('shopee_post_edit',{id:row.dataset.row,revision:Number(row.dataset.revision),caption:row.querySelector('[data-caption]').value,product_url:row.querySelector('[data-url]').value,post_options:{schema:1,allow_reuse:row.querySelector('[data-option="allow_reuse"]').checked,ai_label:row.querySelector('[data-option="ai_label"]').checked,allow_missing_controls:row.querySelector('[data-option="allow_missing_controls"]').checked}});dirty.delete(row.dataset.row);}
      else if(b.hasAttribute('data-remove')){await call('shopee_post_edit',{id:row.dataset.row,revision:Number(row.dataset.revision),removed:true});queued.delete(row.dataset.row);dirty.delete(row.dataset.row);}
      else if(b.hasAttribute('data-reconcile'))await call('shopee_post_reconcile',{id:row.dataset.row,revision:Number(row.dataset.revision)});
      else if(action==='refresh')await refresh();
      else if(action==='add'){if(!picks.size)throw Error('ติ๊กเลือกคลิปก่อน');await call('shopee_post_add',{item_ids:[...picks]});picks.clear();renderLibrary();}
      else if(action==='account')await call('shopee_post_account');
      else if(action==='pause')await call('shopee_post_pause');
      else if(action==='reset-unsent'){
        if(dirty.size||defaultsDirty)throw Error('บันทึกแคปชัน ลิงก์ และตัวเลือกที่แก้ไว้ก่อนล้างสถานะ');
        const count=eligible().length;if(!count)throw Error('ไม่มีคลิปที่ยังไม่ส่งให้เริ่มใหม่');
        if(!confirm(`ล้างสถานะค้าง แล้วเริ่มนับใหม่ 0/${count} คลิป?\nเก็บคลิปและตัวเลือกเดิม • ไม่แตะโพสต์สำเร็จหรือโพสต์ที่ยังไม่รู้ผล\nขั้นตอนนี้ยังไม่สั่งโพสต์`))return;
        await call('shopee_post_reset_unsent',{run_id:state.posting_run?.id,revision:state.revision,confirm:true});
        queued.clear();for(const id of state.posting_run?.ids||[])queued.add(id);
        syncSelection();window.SmartFlowPostProgress?.open();
      }
      else if(action==='reset-options'){
        if(defaultsDirty&&!confirm('ทิ้งตัวเลือกด้านบนที่ยังไม่บันทึก และโหลดค่าเริ่มต้นล่าสุด?'))return;
        await call('shopee_post_status');defaultsDirty=false;
      }
      else if(action==='save-defaults'){await call('shopee_post_defaults',{revision:defaultsRevision,post_options:formOptions()});defaultsDirty=false;}
      else if(action==='apply-options'){
        if(dirty.size)throw Error('บันทึกการแก้รายคลิปก่อนใช้ตัวเลือกทั้งชุด');
        const ids=[...queued];if(!ids.length)throw Error('ติ๊กเลือกงานในคิวก่อน');
        if(!confirm(`ใช้ตัวเลือกนี้กับ ${ids.length} คลิปที่เลือก?\n${summary(formOptions())}\nยังไม่เผยแพร่ และไม่เปลี่ยนค่าเริ่มต้น`))return;
        await call('shopee_post_apply_options',{ids,revision:state.revision,post_options:formOptions()});defaultsDirty=false;
      }
      else if(action==='check'||action==='start'){
        if(dirty.size||defaultsDirty)throw Error('มีแคปชัน ลิงก์ หรือตัวเลือกที่ยังไม่ได้บันทึก กรุณาบันทึกก่อนเริ่ม');
        const ids=[...queued];
        if(!ids.length)throw Error('ติ๊กเลือกงานในคิวก่อน');
        if(action==='start'){
          if(!state.account?.name)throw Error('อ่านบัญชีจากมือถือก่อนเริ่ม');
          const groups=new Map();for(const x of state.items.filter(x=>queued.has(x.id))){const o=x.post_options||defaultOptions;const key=summary({...o,allow_missing_controls:o.allow_missing_controls!==false});groups.set(key,(groups.get(key)||0)+1);}
          const choices=[...groups].map(([key,count])=>`${count} คลิป — ${key}`).join('\n');
          if(!confirm(`โพสต์จริง ${ids.length} คลิป ไปบัญชี ${state.account.name}?\n${choices}\nตรวจว่ามือถือเปิดบัญชีนี้อยู่ • โปรแกรมจะเข้าหน้าโพสต์โดยไม่เปิดโปรไฟล์ตรวจซ้ำ\nส่งเฉพาะวิดีโอ • ใช้ปกอัตโนมัติของ Shopee • ไม่แชร์ต่อแอปอื่น`))return;
          await call('shopee_post_start',{ids,revision:state.revision,confirm:true});
          ids.forEach(id=>queued.delete(id));
        }else await call('shopee_post_check',{ids});
      }
    }catch(error){message(error.name==='AbortError'?'ยังยืนยันคำสั่งไม่ได้ กดโหลดคิวเพื่อตรวจสถานะ ห้ามกดเริ่มซ้ำ':error.message);}
    finally{sending=false;renderedRevision=-1;if(!dirty.size)document.activeElement?.blur();renderQueue();}
  });
  async function poll(){
    const tracking=window.SmartFlowPostProgress?.tracking();
    if(!polling&&!sending&&!document.hidden&&(visible()||tracking)){
      polling=true;try{await call('shopee_post_status');}catch(e){message(e.message);window.SmartFlowPostProgress?.disconnected();}finally{polling=false;}
    }
    setTimeout(poll,tracking?1000:2500);
  }
  window.SmartFlowPostProgress?.configure({pause:run_id=>call('shopee_post_pause',{run_id}),showQueue:()=>{document.querySelector('.nav-item[data-page="queue"]')?.click();q('#sp-queue').scrollIntoView({block:'start'});}});
  polling=true;
  call('shopee_post_status').catch(()=>{}).finally(()=>{polling=false;setTimeout(poll,1000);}); // Recover status only, never start/replay.
  window.SmartFlowShopee={refresh,busy:()=>Boolean(state.busy)};
  document.addEventListener('click',e=>{if(e.target.closest('[data-page="queue"]')&&!items.length)refresh();});
})();
