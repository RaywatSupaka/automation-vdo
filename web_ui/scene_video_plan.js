/* Saved-job scene choices only. This editor never stops a provider or changes defaults. */
(() => {
  const names={google_flow:'Google Flow',meta_ai:'Meta AI'};
  const esc=value=>escapeHtml(String(value??''));
  const stateLabel={completed:'เก็บคลิปเดิม',pending:'ยังไม่เริ่ม',active:'กำลังทำขั้นเดิม',deferred:'รอใช้ค่าใหม่',needs_review:'ต้องตรวจผลเดิมก่อน'};
  function mount(host,review,hooks={}){
    const plan=review.video_plan;
    if(!plan?.supported)return;
    const selected=new Set(plan.remaining_indices||[]);
    let saving=false,confirm=null,readToken=0;
    const count=plan.counts||{};
    const current=names[plan.provider]?plan.provider:'google_flow';
    host.className='studio-scene-plan';
    host.innerHTML=`<header><h3>การสร้างวิดีโอที่เหลือ</h3><p>เก็บคลิปเดิม ${Number(count.completed||0)} ฉาก · ยังไม่มีคลิป ${selected.size} ฉาก</p><small>Flow ${Number(count.flow||0)} · Meta ${Number(count.meta||0)}${count.local?` · ภาพเคลื่อนไหว ${Number(count.local)}`:''}</small></header>
      <p class="scene-plan-note">เปลี่ยนเฉพาะฉากที่เลือก ไม่สร้างภาพ บท เสียง หรือคลิปที่เสร็จแล้วซ้ำ</p>
      <div class="scene-plan-controls"><label class="field"><span>ผู้สร้างวิดีโอสำหรับฉากที่เหลือ</span><select data-plan-provider><option value="google_flow">Google Flow</option><option value="meta_ai">Meta AI</option></select></label><p data-plan-scope></p></div>
      <details class="scene-plan-flow"><summary>ตั้งค่าโมเดลและรายละเอียด Google Flow</summary><p>สัดส่วนตามงานเดิม · 1 คลิปต่อฉาก · ค่าที่เลือกต้องมีให้ใช้ในบัญชีของคุณ</p><div data-plan-flow-editor></div><button type="button" class="button secondary compact" data-plan-read>อ่านตัวเลือกจาก Flow</button><small data-plan-capabilities>ยังไม่ได้อ่านตัวเลือกสด การบันทึกไม่สั่งสร้างวิดีโอ</small></details>
      <details class="scene-plan-scenes"><summary>เลือกฉากเอง / ดูผู้สร้างรายฉาก</summary><label class="scene-plan-check"><input type="checkbox" data-plan-all checked> เลือกฉากที่ยังไม่มีคลิปทั้งหมด</label><div class="scene-plan-rows">${(plan.scenes||[]).map(scene=>`<label class="scene-plan-check"><input type="checkbox" data-plan-scene="${Number(scene.index)}" ${selected.has(scene.index)?'checked':''} ${scene.state==='completed'||scene.editable===false?'disabled':''}><span><b>ฉาก ${Number(scene.index)}</b> ${esc(names[scene.provider]||scene.provider||'')}<small>${esc(stateLabel[scene.state]||scene.state||'')}${scene.pending_provider?` · รอใช้ ${esc(names[scene.pending_provider]||scene.pending_provider)}`:''}${scene.reason?` · ${esc(scene.reason)}`:''}</small></span></label>`).join('')}</div></details>
      <p class="scene-plan-note">${review.active?'งานกำลังทำอยู่: เก็บขั้นที่ส่งไปแล้วให้จบก่อน แล้วใช้ค่าใหม่กับฉากที่ยังไม่เริ่ม':'ฉากที่ส่งแล้วหรือยังไม่ทราบผลต้องตรวจผลเดิมก่อน ไม่ส่งซ้ำเพียงเพราะเปลี่ยนผู้สร้าง'}</p>
      <p class="scene-plan-status" data-plan-status role="status">${esc(plan.reason||'')}</p>
      <div class="scene-plan-actions"><button type="button" class="button primary" data-plan-save>${review.active?'บันทึกสำหรับฉากถัดไป':'บันทึกค่าฉากที่เลือก'}</button><button type="button" class="button secondary" data-plan-resume ${review.active?'hidden':''}>บันทึกและทำต่อ</button></div>
      <div class="scene-plan-confirm" data-plan-confirm hidden><h4>ยืนยันค่าที่จะใช้</h4><p data-plan-confirm-text></p><button type="button" class="button primary" data-plan-confirm-save>ยืนยันบันทึก</button><button type="button" class="button secondary" data-plan-confirm-cancel>กลับไปแก้ไข</button></div>`;
    const q=selector=>host.querySelector(selector);
    const provider=q('[data-plan-provider]');provider.value=current;
    const status=q('[data-plan-status]');
    const flow=window.SmartFlowSettingsEditor?.mount(q('[data-plan-flow-editor]'),plan.flow_settings||{},()=>{status.textContent=plan.reason||'';hooks.onDirty?.();});
    const snapshot=()=>({revision:plan.revision,provider:provider.value,indices:[...selected].sort((a,b)=>a-b),settings:flow?.read()||{}});
    const initial=JSON.stringify(snapshot());
    if(!flow)q('[data-plan-flow-editor]').textContent='ตัวตั้งค่า Flow ยังไม่พร้อม กรุณาเปิดหน้างานใหม่';
    function update(){
      q('.scene-plan-flow').hidden=provider.value!=='google_flow';
      q('[data-plan-scope]').textContent=`มีผลกับ ${selected.size} ฉากที่เลือก · เก็บคลิปสำเร็จ ${Number(count.completed||0)} ฉาก`;
      const locked=!plan.editable||saving||!!confirm;
      for(const node of host.querySelectorAll('input,select,button')){
        if(node.closest('[data-plan-confirm]'))continue;
        node.disabled=locked||(node.hasAttribute('data-plan-scene')&&(plan.scenes||[]).find(s=>s.index===Number(node.dataset.planScene))?.editable===false);
        if(node.hasAttribute('data-plan-scene')&&(plan.scenes||[]).find(s=>s.index===Number(node.dataset.planScene))?.state==='completed')node.disabled=true;
        if(node.hasAttribute('data-flow-field')&&node.dataset.flowField!=='model'&&!flow?.read().model)node.disabled=true;
      }
      q('[data-plan-read]').disabled=locked||!!review.active||!flow;
      if(review.active)q('[data-plan-read]').title='ไม่เปิดเมนูแทรกขณะงานกำลังทำ ใช้ตัวเลือกที่อ่านไว้ก่อน';
      q('[data-plan-save]').disabled=locked||!selected.size||(provider.value==='google_flow'&&!flow);
      q('[data-plan-resume]').disabled=q('[data-plan-save]').disabled;
      const all=q('[data-plan-all]'),indices=plan.remaining_indices||[];
      all.checked=!!indices.length&&indices.every(i=>selected.has(i));all.indeterminate=selected.size>0&&!all.checked;
    }
    provider.addEventListener('change',()=>{status.textContent=plan.reason||'';hooks.onDirty?.();update();});
    host.addEventListener('change',event=>{
      const input=event.target;
      if(input.hasAttribute('data-plan-all')){
        selected.clear();if(input.checked)for(const i of plan.remaining_indices||[])selected.add(i);
        for(const node of host.querySelectorAll('[data-plan-scene]'))node.checked=selected.has(Number(node.dataset.planScene));
      }else if(input.hasAttribute('data-plan-scene')){
        const i=Number(input.dataset.planScene);if(input.checked)selected.add(i);else selected.delete(i);
      }else return;
      hooks.onDirty?.();update();
    });
    q('[data-plan-read]').onclick=async()=>{
      const token=++readToken;q('[data-plan-read]').disabled=true;
      try{
        q('[data-plan-capabilities]').textContent='กำลังอ่านเมนู ไม่กดสร้างและไม่ใช้เครดิตสร้างวิดีโอ';
        const result=await window.SmartFlowSettingsEditor.readCapabilities();
        if(!host.isConnected||token!==readToken)return;
        flow.refresh();q('[data-plan-capabilities]').textContent=`อ่านล่าสุด ${new Date(result.checked_at*1000).toLocaleString('th-TH')} · ตรวจค่าซ้ำก่อนสร้างจริง`;
      }catch(error){if(host.isConnected&&token===readToken)q('[data-plan-capabilities]').textContent=window.smartflowSafeError?.(error.message)||'ตรวจความพร้อมไม่สำเร็จ';}
      finally{if(host.isConnected&&token===readToken)update();}
    };
    function prepare(resume){
      if(saving||confirm||!plan.editable||!selected.size)return;
      try{
        if(provider.value==='google_flow')flow.validate();
        confirm={payload:{job_id:review.job_id,plan_revision:plan.revision,provider:provider.value,scene_indices:[...selected].sort((a,b)=>a-b),flow_settings:provider.value==='google_flow'?flow.read():{}},resume};
        const pending=confirm.payload.scene_indices;
        q('[data-plan-confirm-text]').textContent=`ใช้ ${names[provider.value]} กับฉาก ${pending.join(', ')}\nเก็บคลิปสำเร็จ ${Number(count.completed||0)} ฉากไว้เหมือนเดิม\n${resume?'บันทึกแล้วเริ่มทำต่อจากส่วนที่ยังขาด':'บันทึกอย่างเดียว ไม่เริ่มงานใหม่'}${review.active?'\nงานที่ส่งไปแล้วจะไม่ถูกหยุดหรือส่งซ้ำ':''}`;
        q('[data-plan-confirm]').hidden=false;update();q('[data-plan-confirm-save]').focus();
      }catch(error){status.textContent=window.smartflowSafeError?.(error.message)||'ทำรายการไม่สำเร็จ';}
    }
    q('[data-plan-save]').onclick=()=>prepare(false);
    q('[data-plan-resume]').onclick=()=>prepare(true);
    q('[data-plan-confirm-cancel]').onclick=()=>{if(saving)return;confirm=null;q('[data-plan-confirm]').hidden=true;update();q('[data-plan-save]').focus();};
    q('[data-plan-confirm-save]').onclick=async()=>{
      if(saving||!confirm)return;
      saving=true;hooks.onSaving?.(true);update();
      const request=confirm;
      q('[data-plan-confirm-save]').disabled=true;q('[data-plan-confirm-cancel]').disabled=true;
      status.textContent='กำลังบันทึกค่าฉาก…';
      try{
        const data=await postAction('story_save_video_plan',request.payload);
        if(data?.ok===false||!data?.review)throw new Error(data?.error||'ยังยืนยันการบันทึกไม่ได้ อ่านสถานะงานก่อนลองใหม่');
        if(request.resume){
          try{const started=await postAction('retry_story',{job_id:review.job_id});if(started?.ok===false)throw new Error(started.error||'ยังเริ่มงานไม่ได้');}
          catch(error){toast('บันทึกแล้ว แต่ยังทำต่อไม่ได้: '+error.message,'warning');hooks.onSaved?.(data.review);return;}
        }
        toast(request.resume?'บันทึกแล้วและส่งคำสั่งทำต่อ':'บันทึกค่าฉากแล้ว คลิปที่เสร็จยังอยู่ครบ','success');
        hooks.onSaved?.(data.review);
      }catch(error){status.textContent=(window.smartflowSafeError?.(error.message)||'ทำรายการไม่สำเร็จ')+' • ไม่ได้ส่งคำสั่งสร้างซ้ำอัตโนมัติ';}
      finally{
        saving=false;hooks.onSaving?.(false);confirm=null;
        if(host.isConnected){q('[data-plan-confirm]').hidden=true;q('[data-plan-confirm-save]').disabled=false;q('[data-plan-confirm-cancel]').disabled=false;update();}
      }
    };
    update();
    return {readDraft(){const draft=snapshot();return JSON.stringify(draft)!==initial?draft:null;},restore(draft){
      if(!draft||draft.revision!==plan.revision)return;
      if(names[draft.provider])provider.value=draft.provider;
      selected.clear();for(const i of draft.indices||[])if(plan.remaining_indices?.includes(i))selected.add(i);
      for(const node of host.querySelectorAll('[data-plan-scene]'))node.checked=selected.has(Number(node.dataset.planScene));
      flow?.set?.(draft.settings);update();hooks.onDirty?.();
    }};
  }
  window.SmartFlowVideoPlan={mount};
})();
