/* Presentation-only observer. Never starts a queue, clicks Android, or resends. */
(() => {
  'use strict';
  const modal=document.querySelector('#sp-run-modal'), pill=document.querySelector('#sp-run-pill');
  if(!modal||!pill)return;
  const q=s=>modal.querySelector(s), active=r=>r&&['running','pausing'].includes(r.status);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const steps=[['checking','ตรวจไฟล์'],['transfer','โอนวิดีโอ'],['restart_app','ปิด Shopee เดิมแล้วเปิดใหม่'],['prepare_post','เตรียมหน้าโพสต์'],['select_video','เลือกคลิป'],['caption','ใส่แคปชัน'],['product','แนบสินค้า'],['settings','ตั้งค่าสวิตช์'],['preflight','ตรวจขั้นสุดท้ายก่อนโพสต์'],['sending','ส่งโพสต์'],['verify','รอ Shopee ยืนยันอัปโหลด']];
  let run=null, callbacks={}, minimized=false, dismissed=false, closeTimer=null, celebrationTimer=null, lastResponse=0, lastEvent=0, pausePending=false;
  const memo=()=>{try{sessionStorage.setItem('smartflow-shopee-progress',JSON.stringify({id:run?.id,minimized,dismissed}));}catch(_){}};
  const readMemo=()=>{try{return JSON.parse(sessionStorage.getItem('smartflow-shopee-progress')||'null');}catch(_){return null;}};
  function open(){
    if(!run)return;
    dismissed=false;minimized=false;memo();pill.hidden=true;
    // Do not stack on top of a creation/error dialog belonging to another job.
    if(document.querySelector('dialog[open]:not(#sp-run-modal)')){minimized=true;memo();pill.hidden=false;return;}
    if(!modal.open)modal.showModal();
  }
  function minimize(){minimized=true;memo();modal.close();pill.hidden=!run||dismissed;}
  function dismiss(){dismissed=true;memo();clearTimeout(closeTimer);closeTimer=null;modal.close();pill.hidden=true;}
  function elapsed(){
    if(!run)return;
    const end=run.finished_at||Date.now()/1000, sec=Math.max(0,Math.floor(end-run.started_at));
    q('#sp-run-elapsed').textContent=`เวลารอบนี้ ${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')} นาที`;
    const stale=active(run)&&lastResponse&&Date.now()-lastResponse>6500;
    q('#sp-run-stale').hidden=!stale;modal.classList.toggle('is-stale',Boolean(stale));pill.classList.toggle('is-stale',Boolean(stale));
  }
  function update(next){
    lastResponse=Date.now();q('#sp-run-stale').hidden=true;
    if(!next){if(run){clearTimeout(closeTimer);clearTimeout(celebrationTimer);modal.close();pill.hidden=true;run=null;}return;}
    const changed=run?.id!==next.id, wasActive=active(run), oldStatus=run?.status;
    if(changed){
      clearTimeout(closeTimer);closeTimer=null;clearTimeout(celebrationTimer);q('#sp-run-celebrate').hidden=true;
      const saved=readMemo();minimized=saved?.id===next.id?Boolean(saved.minimized):false;dismissed=saved?.id===next.id?Boolean(saved.dismissed):['complete','paused'].includes(next.status);
      lastEvent=0;modal.close();
    }
    const oldItem=run?.current_id;run=next;
    if(oldItem!==run.current_id){q('.sp-current-card').classList.remove('sp-enter');void q('.sp-current-card').offsetWidth;q('.sp-current-card').classList.add('sp-enter');}
    const waiting=run.status==='running'&&run.current?.waiting_for_device;
    modal.dataset.state=waiting?'waiting':run.status;pill.dataset.state=waiting?'waiting':run.status;
    const complete=run.status==='complete', trouble=['review','interrupted'].includes(run.status);
    const skipped=Number(run.skipped_count||0), completeLabel=skipped?`คิวจบแล้ว • ข้าม ${skipped} สินค้า`:'โพสต์ครบแล้ว';
    const unsentStop=trouble&&run.uncertain_count===0;
    q('#sp-run-title').textContent=run.status==='ready'?'พร้อมเริ่มใหม่ • ยังไม่สั่งโพสต์':complete?completeLabel:waiting?'รอมือถือพร้อม • ยังไม่กดต่อ':unsentStop?(run.completed?'หยุดคิวแล้ว • คลิปที่เหลือยังไม่ส่ง':'หยุดก่อนส่ง • ยังไม่ได้โพสต์'):trouble?'คิวหยุดแล้ว • ต้องตรวจผลโพสต์เดิม':run.status==='paused'?'พักคิวแล้ว':run.status==='pausing'?'กำลังพักคิว':'กำลังโพสต์คลิปของคุณ';
    q('#sp-run-identity').textContent=`บัญชี ${run.account||'—'} · ${run.phone||'มือถือที่เลือก'}`;
    q('#sp-run-index').textContent=run.current_index?`คลิปที่ ${run.current_index} จาก ${run.total}`:`เตรียม ${run.total} คลิป`;
    q('#sp-run-clip').textContent=run.current?.title||'คิวที่คุณเลือก';
    const message=(run.status==='running'?run.current?.message:'')||run.message||'กำลังรับสถานะจากโปรแกรม';
    if(q('#sp-run-message').textContent!==message)q('#sp-run-message').textContent=message;
    if(window.SmartFlowUX)window.SmartFlowUX.renderPosting(run);
    else q('#sp-run-icon').textContent=complete?'✓':trouble?'!':'▶';
    const preview=q('#sp-run-image'), itemId=run.current?.item_id;
    if(preview.dataset.item!==itemId){preview.dataset.item=itemId||'';preview.hidden=!itemId;if(itemId)preview.src='/api/desktop/media?item_id='+encodeURIComponent(itemId)+'&kind=preview';else preview.removeAttribute('src');}
    q('#sp-run-done').textContent=run.completed;q('#sp-run-left').textContent=run.remaining;q('#sp-run-review').textContent=run.review_count;
    const percent=run.total?Math.round(run.completed*100/run.total):0;
    q('#sp-run-meter').setAttribute('aria-valuenow',String(percent));q('#sp-run-meter').setAttribute('aria-valuetext',`ตรวจสำเร็จ ${run.completed} จาก ${run.total} คลิป`);q('#sp-run-meter i').style.width=percent+'%';
    q('#sp-run-count-label').textContent=`ตรวจสำเร็จจริง ${run.completed} / ${run.total} คลิป${skipped?` · ข้าม ${skipped} สินค้า (ไม่ได้โพสต์)`:''} · ไม่ใช่เปอร์เซ็นต์อัปโหลด`;
    const key=['review','unknown'].includes(run.current?.step)?run.current?.last_step:run.current?.step, position=key==='done'?steps.length:steps.findIndex(([k])=>k===(['baseline','account'].includes(key)?'prepare_post':key));
    const stepList=q('#sp-run-steps'), signature=run.id+':'+run.current_id+':'+position+':'+key+':'+run.status;
    if(stepList.dataset.signature!==signature){stepList.dataset.signature=signature;stepList.innerHTML=steps.map(([k,label],i)=>{
      const stopped=position===i&&!active(run), text=k==='prepare_post'&&key==='baseline'?'ตรวจโพสต์เดิม (รอบก่อน)':k==='prepare_post'&&key==='account'?'ตรวจบัญชี (รอบก่อน)':label;
      return `<li class="${position>i?'done':position===i?'current':''}${stopped?' stopped':''}" ${position===i?'aria-current="step"':''}><span>${position>i?'✓':i+1}</span>${stopped?'หยุดที่: ':''}${text}</li>`;
    }).join('');}
    const events=run.events||[];
    const history=q('#sp-run-events'), eventSignature=run.id+':'+run.sequence;
    if(history.dataset.signature!==eventSignature){history.dataset.signature=eventSignature;history.innerHTML=events.slice(-8).reverse().map(e=>`<li><time>${new Date(e.at*1000).toLocaleTimeString('th-TH',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</time><span>${esc(e.title)}<small>${esc(e.message)}</small></span>${e.phase==='published'?'<b>✓</b>':''}</li>`).join('');}
    const finished=events.filter(e=>e.sequence>lastEvent&&e.phase==='published');lastEvent=Math.max(lastEvent,run.sequence||0);
    if(finished.length&&!dismissed){
      clearTimeout(celebrationTimer);const banner=q('#sp-run-celebrate');banner.textContent=`✓ โพสต์สำเร็จแล้ว: ${finished.at(-1).title}`;banner.hidden=false;
      const id=run.id;celebrationTimer=setTimeout(()=>{if(run?.id===id)banner.hidden=true;},3500);
    }
    q('[data-post-progress="pause"]').hidden=!active(run);q('[data-post-progress="pause"]').disabled=pausePending||run.status==='pausing';
    q('[data-post-progress="pause"]').textContent=run.status==='pausing'?'กำลังพัก…':'พักคิว';
    q('[data-post-progress="close"]').hidden=active(run);
    q('#sp-run-footer-note').textContent=run.status==='ready'?'ล้างรอบเก่าแล้ว • กดออโตโพสต์เพื่อเริ่มคลิปแรกของรอบใหม่':complete?'สรุปจะปิดอัตโนมัติใน 5 วินาที · ผลยังอยู่ในคิว':unsentStop?'ตัวทำงานหยุดแล้ว • แก้สาเหตุ แล้วเลือกคลิปที่ยังไม่ส่งในคิวเพื่อทำต่อ':trouble?'ตัวทำงานหยุดแล้ว • ตรวจผลเดิมก่อน ไม่โพสต์ซ้ำ':run.status==='paused'?'ตัวทำงานหยุดแล้ว • คลิปที่ยังไม่ส่งยังอยู่ในคิว':waiting?'กำลังรอหน้าเดิม • ไม่สั่งโพสต์ซ้ำ':'ย่อหน้าต่างได้ งานยังทำต่อ';
    document.querySelector('#sp-pill-text').textContent=`Shopee · ${run.status==='ready'?'พร้อมเริ่มใหม่':complete?completeLabel:active(run)?waiting?'รอมือถือ':'กำลังทำงาน':'หยุดแล้ว'} · ${run.completed}/${run.total} สำเร็จ · ${message}`;
    if(changed&&active(run)&&!minimized&&!dismissed)open();
    if(!active(run)&&oldStatus!==run.status&&wasActive&&!dismissed&&!minimized)open();
    pill.hidden=dismissed||modal.open;
    if(complete&&!dismissed&&!closeTimer){const id=run.id;closeTimer=setTimeout(()=>{if(run?.id===id&&run.status==='complete')dismiss();},5000);}
    elapsed();
  }
  previewError();
  function previewError(){q('#sp-run-image').addEventListener('error',e=>e.target.hidden=true);}
  modal.addEventListener('cancel',e=>{e.preventDefault();minimize();});
  modal.addEventListener('click',async e=>{
    const button=e.target.closest('[data-post-progress]');if(!button||button.disabled)return;
    const action=button.dataset.postProgress;
    if(action==='minimize')minimize();
    if(action==='close')dismiss();
    if(action==='queue'){minimize();callbacks.showQueue?.();}
    if(action==='pause'&&active(run)&&!pausePending){
      const id=run.id;pausePending=true;button.disabled=true;
      try{await callbacks.pause?.(id);}catch(error){if(run?.id===id){q('#sp-run-stale').textContent=error.message;q('#sp-run-stale').hidden=false;}}
      finally{pausePending=false;if(run?.id===id)button.disabled=run.status==='pausing';}
    }
  });
  pill.addEventListener('click',open);setInterval(elapsed,1000);
  window.SmartFlowPostProgress={configure:value=>callbacks=value,update,open,tracking:()=>Boolean(active(run)||modal.open||!pill.hidden),disconnected:()=>{if(run){q('#sp-run-stale').hidden=false;modal.classList.add('is-stale');}}};
})();
