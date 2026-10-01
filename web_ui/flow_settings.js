/* Shared pre-create choices. A saved queue/job never follows changing defaults. */
(() => {
  let defaults={}, capabilities=null, loaded=false, saving=false, loading=null, loadError='';
  // Starting choices are taken from the supplied Flow DOM and the recorded
  // live comparison, NOT an account-wide capability or price guarantee.
  // The extension independently verifies every requested value before Generate.
  const profiles={
    'Omni 1.1 Flash':{video_type:['Frames','Ingredients'],resolution:['360p','720p'],duration:['4s','6s','8s','10s']},
    'Veo 3.1 - Lite':{video_type:['Frames','Ingredients'],resolution:['720p'],duration:['4s','6s','8s']},
    'Veo 3.1 - Fast':{video_type:['Frames','Ingredients'],resolution:['720p'],duration:['4s','6s','8s']},
    'Veo 3.1 - Quality':{video_type:['Frames','Ingredients'],resolution:['720p'],duration:['4s','6s','8s']},
    'Veo 3.1 - Lite [Lower Priority]':{video_type:['Frames','Ingredients'],resolution:['720p'],duration:['4s','6s','8s']}
  };
  const labelOf=(key,value)=>key==='duration'?value.replace(/s$/,' วินาที'):key==='video_type'?({Frames:'เฟรมต้นจากภาพ',Ingredients:'องค์ประกอบจากภาพ'}[value]||value):value;
  function modelLabel(value){
    if(!capabilities)return value+' • ยังไม่ตรวจบนบัญชีนี้';
    if(!capabilities.model_menu_open)return value+' • ยังไม่เห็นเมนูโมเดลทั้งหมด';
    return value+(capabilities.model?.includes(value)?' • ตรวจพบใน Flow':' • ไม่พบในเมนูตอนนี้');
  }
  function choicesFor(key,value){
    if(key==='model')return [...new Set([...Object.keys(profiles),...(capabilities?.model||[])])];
    const model=value.model||'Omni 1.1 Flash';
    const context=capabilities?.context||{};
    const observedMatches=context.model===model && (!value.video_type||context.video_type===value.video_type);
    if(observedMatches && Array.isArray(capabilities?.[key]))return capabilities[key];
    return profiles[model]?.[key]||[];
  }
  const panels=new Map();
  const fields={model:'โมเดลวิดีโอ',video_type:'รูปแบบอ้างอิง',resolution:'ความละเอียดจาก Flow',duration:'เวลาต่อฉาก (ไม่ใช่ความยาวรวม)'};
  const clone=v=>({...JSON.parse(JSON.stringify(v||{})),display:'compact'});
  const root=document.querySelector('[data-view="settings"] .page-intro');
  if(!root)return;
  const section=document.createElement('section');section.className='panel flow-settings';
  section.innerHTML='<h2>ตั้งค่า Google Flow</h2><p>ใช้กับงานใหม่เท่านั้น • คลิปยาวแนวนอน 16:9 งานอื่นแนวตั้ง 9:16 • ครั้งละ 1 คลิป</p><p>เปิดแท็บ Flow แล้วกดอ่านตัวเลือก โปรแกรมเปิดเมนูให้ ไม่กดสร้างและไม่ใช้เครดิตสร้างวิดีโอ</p><button class="button secondary" data-flow-read>อ่านตัวเลือกจาก Flow</button><small data-flow-status role="status">ยังไม่ได้อ่านตัวเลือก • ไม่ทราบค่าเครดิต</small><div data-flow-editor></div><button class="button primary" data-flow-save>บันทึกใช้กับงานใหม่</button>';
  root.after(section);
  const status=section.querySelector('[data-flow-status]');
  function editor(host,value,changed,strict=false){
    host.replaceChildren();
    value.display='compact';
    for(const [key,label] of Object.entries(fields)){
      const field=document.createElement('label');field.className='field';
      const title=document.createElement('span');title.textContent=label;
      const select=document.createElement('select');select.dataset.flowField=key;
      const add=(v,label)=>{const option=document.createElement('option');option.value=v;option.textContent=label;select.append(option);};
      add('','ใช้ค่าที่เลือกอยู่ในเว็บ Flow');
      const choices=choicesFor(key,value);
      for(const v of choices)add(v,key==='model'?modelLabel(v):labelOf(key,v));
      if(value[key] && !choices.includes(value[key]))add(value[key],value[key]+' • ค่าที่บันทึกไว้ ต้องตรวจบนเว็บ');
      select.value=value[key]||'';
      if(strict&&key!=='model'&&!value.model)select.disabled=true;
      select.addEventListener('change',()=>{
        if(select.value)value[key]=select.value;else delete value[key];
        // Choosing a concrete option is a program-owned request, not a hidden
        // dependence on whichever model happened to be selected in Chrome.
        if(select.value && key!=='model' && !value.model)value.model='Omni 1.1 Flash';
        if(!strict&&(key==='model'||key==='video_type')){
          for(const dependent of ['video_type','resolution','duration']){
            if(dependent===key)continue;
            const available=choicesFor(dependent,value);
            if(value[dependent]&&!available.includes(value[dependent]))delete value[dependent];
          }
        }
        editor(host,value,changed,strict);
        changed();
      });
      field.append(title,select);host.append(field);
    }
    const displayNote=document.createElement('small');
    displayNote.textContent='Google Flow ใช้หน้าจอมือถืออัตโนมัติตลอดงาน';
    host.append(displayNote);
    const note=document.createElement('small');note.textContent=value.model && capabilities?.model_menu_open && !capabilities.model?.includes(value.model)
      ? 'โมเดลที่เลือกไม่พบในเมนู Flow ล่าสุด • เก็บค่างานเดิมไว้และตรวจบัญชี/โมเดลก่อนสร้าง ไม่เปลี่ยนเป็นรุ่นอื่นเอง'
      : strict?'ใช้กับฉากที่เลือกในงานนี้เท่านั้น • ตรวจค่าบนเว็บอีกครั้งก่อนสร้าง ไม่เปลี่ยนค่าเริ่มต้นของงานใหม่':'ใช้ค่าที่เลือกเมื่อสร้างหรือเพิ่มลงคิว • หาก Flow ไม่รองรับ ระบบจะแจ้งก่อนสร้าง';host.append(note);
  }
  // Saved-scene editing shares labels/options, but never writes new-job defaults.
  window.SmartFlowSettingsEditor={
    mount(host,initial,changed=()=>{}){
      const value=clone(initial);
      const refresh=()=>editor(host,value,changed,true);
      refresh();
      return {read:()=>clone(value),refresh,set(next){for(const key of Object.keys(value))delete value[key];Object.assign(value,clone(next));refresh();},validate(){
        if(capabilities?.model_menu_open&&value.model&&!capabilities.model?.includes(value.model))
          throw new Error('โมเดลนี้ไม่พบในเมนู Flow ล่าสุด เลือกโมเดลที่มีหรืออ่านตัวเลือกใหม่');
        const context=capabilities?.context||{};
        if(context.model===value.model&&(!value.video_type||context.video_type===value.video_type)){
          for(const key of ['video_type','resolution','duration']){
            if(value[key]&&['selectable','fixed_from_summary'].includes(capabilities.states?.[key])&&!capabilities[key]?.includes(value[key]))
              throw new Error(`${fields[key]}ไม่ตรงกับตัวเลือก Flow ที่อ่านได้ กรุณาตรวจค่าใหม่`);
          }
        }
      }};
    },
    async readCapabilities(){
      const request=await original('flow_settings_read',{});
      if(request?.ok===false||!request?.command_id)throw new Error(request?.error||'ยังไม่ได้เริ่มอ่านเมนู Flow');
      for(let attempt=0;attempt<25;attempt++){
        await new Promise(resolve=>setTimeout(resolve,1200));
        const result=await original('flow_settings_result',{command_id:request.command_id});
        if(result.status==='failed')throw new Error(result.error||'อ่านเมนู Flow ไม่สำเร็จ');
        if(result.status==='completed'){
          capabilities=result.capabilities;refresh();return result;
        }
      }
      throw new Error('ยังไม่ได้รับผลอ่านเมนู ยังไม่ยืนยันตัวเลือกของบัญชีนี้');
    }
  };
  let draft={};
  const summarize=(value,key='')=>`${key==='long'?'16:9':'9:16'} • 1 คลิปต่อฉาก • `+(Object.entries(value).filter(([k,v])=>k!=='display'&&v).map(([k,v])=>labelOf(k,v)).join(' • ')||'ใช้ค่าหน้าเว็บ Flow');
  function refresh(){
    section.querySelector('[data-flow-save]').disabled=!loaded||saving;
    editor(section.querySelector('[data-flow-editor]'),draft,()=>{});
    for(const entry of panels.values())entry.refresh();
  }
  function mount(key,selector,fixed=false){
    const anchor=document.querySelector(selector);if(!anchor)return;
    const box=document.createElement('details');box.className='flow-job-settings';
    box.open=false;
    box.innerHTML='<summary></summary><div class="flow-value-tools"><small data-flow-value-status role="status"></small><button type="button" class="button primary" data-flow-job-save>บันทึกเป็นค่าเริ่มต้น</button><button type="button" class="button secondary" data-flow-reset>คืนค่าตั้งต้น</button></div><small>ใช้กับงานใหม่ทุกหน้า • ไม่เปลี่ยนงานเก่าหรือคิวที่บันทึกไว้</small><small data-flow-save-status role="status"></small><div data-flow-options></div>';
    (anchor.closest('label')||anchor).after(box);
    let custom=null;
    const reset=box.querySelector('[data-flow-reset]'),valueStatus=box.querySelector('[data-flow-value-status]'),host=box.querySelector('[data-flow-options]');
    const save=box.querySelector('[data-flow-job-save]'),saveStatus=box.querySelector('[data-flow-save-status]');
    const entry={active:()=>fixed || anchor.value==='google_flow' || anchor.value==='flow',read:()=>clone(custom===null?defaults:custom),set(value){custom=clone(value);entry.refresh();},refresh(){
      box.querySelector('summary').textContent='ตั้งค่า Google Flow'+(entry.active()?'':' (ใช้เมื่อเลือก Flow)')+' • '+summarize(entry.read(),key);
      valueStatus.textContent=custom===null?'ใช้ค่าตั้งต้น':'ตั้งค่าเฉพาะงานนี้';
      reset.disabled=!loaded||custom===null;
      save.disabled=!loaded||saving;
      host.hidden=false;
      box.hidden=!entry.active();
      const editable=entry.read();
      editor(host,editable,()=>{custom=clone(editable);valueStatus.textContent='ตั้งค่าเฉพาะงานนี้';reset.disabled=false;box.querySelector('summary').textContent='Google Flow • '+summarize(custom,key);});
    }};
    reset.addEventListener('click',()=>{if(!loaded)return;custom=null;entry.refresh();});
    save.addEventListener('click',async()=>{
      if(!loaded||saving)return;
      const selected=entry.read();saving=true;refresh();saveStatus.textContent='กำลังบันทึก…';
      try{
        const result=await original('flow_settings_save',{settings:selected});
        if(JSON.stringify(draft)===JSON.stringify(defaults))draft=clone(result.settings);
        defaults=clone(result.settings);
        if(JSON.stringify(entry.read())===JSON.stringify(selected))custom=null;
        saveStatus.textContent='บันทึกแล้ว • เปิดโปรแกรมครั้งหน้าจะใช้ค่านี้';
      }catch(e){saveStatus.textContent='บันทึกไม่สำเร็จ: '+e.message;}
      finally{saving=false;refresh();}
    });
    anchor.addEventListener('change',()=>entry.refresh());panels.set(key,entry);entry.refresh();
  }
  mount('product','#product-video-provider');mount('product-batch','#creation-product-video-provider');
  mount('story','#story-video-mode');mount('story-batch','#story-batch-video-mode');mount('drama','#drama-video-mode');mount('long','#long-mode');mount('presenter','#presenter-screen',true);
  window.smartflowReadStoryFlowSettings=()=>{
    if(!loaded)throw new Error(loadError||'กำลังอ่านค่าตั้ง Flow จากโปรแกรม กรุณารอสักครู่');
    return panels.get('story').read();
  };
  const prepare=window.prepareAudioQueue;
  window.prepareAudioQueue=item=>{prepare?.(item);panels.get('product-batch')?.set(item ? item.settings?.flow_settings||{} : panels.get('product')?.read());};
  const original=postAction;
  function ensureSettings(){
    if(loaded)return Promise.resolve();
    if(loading)return loading;
    loadError='';status.textContent='กำลังอ่านค่าตั้ง Flow จากโปรแกรม…';
    // Only this read is retried. Never replay create/enqueue/save or silently
    // replace stored defaults with an empty object after a failed first login.
    loading=(async()=>{
      let timer;
      try{
        const result=await Promise.race([
          original('flow_settings_get',{}),
          new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('โปรแกรมยังไม่ตอบกลับ กรุณาลองกดสร้างอีกครั้ง')),12000);})
        ]);
        if(!result?.ok || !result.settings || typeof result.settings!=='object' || Array.isArray(result.settings)){
          throw new Error(result?.error||'ได้รับค่าตั้ง Flow ไม่ครบ กรุณาลองกดสร้างอีกครั้ง');
        }
        defaults=clone(result.settings);draft=clone(defaults);loaded=true;
        status.textContent='โหลดค่าตั้ง Flow แล้ว • ยังไม่ได้อ่านเมนูจากเว็บ';
        refresh();
      }catch(error){
        loadError='โหลดค่าตั้ง Flow ไม่สำเร็จ: '+error.message;
        status.textContent=loadError;
        throw new Error(loadError);
      }finally{clearTimeout(timer);}
    })().finally(()=>{loading=null;});
    return loading;
  }
  window.addEventListener('smartflow-membership-ready',()=>{
    // Login can finish while the pre-login read is still being rejected.
    // Wait for it, then issue one fresh authenticated read if still needed.
    Promise.resolve(loading).catch(()=>{}).then(()=>ensureSettings()).catch(()=>{});
  });
  postAction=async(action,payload={})=>{
    const key=action==='presenter_create'?'presenter':window.smartflowCreationFormKey?.(action,payload);
    if(key && panels.has(key) && panels.get(key).active() && !payload.job_id){
      await ensureSettings();
      const value=panels.get(key).read();
      payload={...payload,flow_settings:value};
      if(payload.render_options)payload.render_options={...payload.render_options,flow_settings:value};
    }
    return original(action,payload);
  };
  section.querySelector('[data-flow-save]').addEventListener('click',async()=>{
    if(!loaded||saving)return;
    saving=true;const selected=clone(draft);refresh();
    try{const result=await original('flow_settings_save',{settings:selected});defaults=clone(result.settings);status.textContent='บันทึกแล้ว • ไม่เปลี่ยนงานเก่าหรือคิวที่เพิ่มไว้';}catch(e){status.textContent=e.message;}finally{saving=false;refresh();}
  });
  section.querySelector('[data-flow-read]').addEventListener('click',async event=>{
    const button=event.currentTarget;button.disabled=true;
    try{
      status.textContent='รอ Extension อ่านเมนู Flow • ไม่สั่งสร้าง';
      const request=await original('flow_settings_read',{});
      if(request?.ok===false || !request?.command_id)throw new Error(request?.error||'ยังไม่ได้เริ่มอ่านเมนู Flow');
      for(let attempt=0;attempt<25;attempt++){
        await new Promise(resolve=>setTimeout(resolve,1200));
        const result=await original('flow_settings_result',{command_id:request.command_id});
        if(result.status==='failed')throw new Error(result.error||'อ่านเมนู Flow ไม่สำเร็จ');
        if(result.status==='completed'){
          capabilities=result.capabilities;
          status.textContent='อ่านล่าสุด '+new Date(result.checked_at*1000).toLocaleString('th-TH')+' • '+(capabilities?.credit_notice||'ไม่พบยอดเครดิต ไม่ใช่ 0 เครดิต')+' • ตรวจอีกครั้งก่อนสร้าง';
          refresh();return;
        }
      }
      throw new Error('ยังไม่ได้รับผลอ่านเมนู ตรวจว่าโปรแกรมและ Extension เป็นรุ่นเดียวกัน แล้วลองอ่านใหม่');
    }catch(e){status.textContent=e.message;}finally{button.disabled=false;}
  });
  refresh();
  ensureSettings().catch(()=>{});
})();
