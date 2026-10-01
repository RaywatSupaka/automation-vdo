/* Silent reusable character UI. All provider actions use SmartFlow's bridge. */
(() => {
  let jobs=[], signature='', fetching=false, lastPoll=0, creating=false, animation=0;
  let saved={settings:{enabled:false},available:false}, loaded=false, draftLoaded=false, returnPage='products', returnDialog=null, defaultsEpoch=0;
  function returnToCreation(){
    const dialog=returnDialog;returnDialog=null;showPage(returnPage);
    if(dialog?.isConnected&&!dialog.open){dialog.showModal();dialog.querySelector('.presenter-check input')?.focus();}
  }
  const url=(id,kind)=>'/api/desktop/media?item_id='+encodeURIComponent(`presenter:${id}:${kind}`)+'&kind=video';
  const node=(tag,text,cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
  const status={draft:'พร้อมเริ่ม',running:'กำลังทำ',image_review:'รอตรวจภาพ',clip_review:'รอตรวจคลิป',ready:'พร้อมใช้',error:'หยุดตรวจสอบ',cancelled:'ยกเลิกแล้ว'};
  async function refresh(){
    if(fetching||document.hidden)return;fetching=true;lastPoll=Date.now();const readEpoch=defaultsEpoch;
    try{
      const response=await fetch('/api/desktop/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'presenter_state',payload:{}})});
      const data=await response.json();if(!data.ok)throw new Error(/ไม่รู้จักคำสั่ง/.test(data.error||'')?'โปรแกรมที่เปิดอยู่ยังเป็นรุ่นเดิม • เมื่อไม่มีงานรัน ให้ปิดแล้วเปิด SmartFlow AI.exe ใหม่':data.error||'อ่านคลังตัวละครไม่ได้');
      if(data.ui_version!==2)throw new Error('ต้องปิด–เปิด SmartFlow AI.exe ใหม่เมื่อไม่มีงานรัน เพื่อใช้หน้าตั้งค่าผู้บรรยายรุ่นนี้');
      jobs=data.jobs||[];if(readEpoch===defaultsEpoch)saved=data.defaults;loaded=true;$('#presenter-progress').textContent=data.progress?.message||'ยังไม่มีงานกำลังทำ';$('#presenter-cancel').hidden=!data.active;
      const next=JSON.stringify(jobs);if(next!==signature){signature=next;renderCards();updateChoices();}
      if(!draftLoaded){loadDraft(saved.settings);draftLoaded=true;}updateToggles();
      $('#presenter-settings-status').textContent=saved.available?'ค่าที่บันทึกไว้: '+saved.name+' • ใช้ร่วมกับสินค้าและ Story Shorts':(saved.error||'เลือกตัวละครที่พร้อมใช้ แล้วบันทึกก่อนติ๊กใส่ผู้บรรยาย');
    }catch(error){
      $('#presenter-progress').textContent=error.message;
      $('#presenter-settings-status').textContent=error.message;
      const note=$('.presenter-save-note');if(note)note.textContent=error.message;
      if(!loaded)for(const t of Object.values(toggles)){t.check.disabled=true;t.info.textContent=error.message;}
    }finally{fetching=false;}
  }
  let librarySearch='',libraryFilter='all';
  const libraryToolbar=node('div','','presenter-library-toolbar');
  const search=node('input','');search.type='search';search.placeholder='ค้นหาชื่อตัวละคร';search.setAttribute('aria-label','ค้นหาชื่อตัวละคร');
  const filter=node('select','');filter.setAttribute('aria-label','กรองคลังตัวละคร');
  for(const [value,label] of [['all','ทั้งหมด'],['ready','พร้อมใช้'],['unfinished','ยังไม่เสร็จ'],['hidden','ซ่อนไว้'],['trash','ถังขยะ']])filter.add(new Option(label,value));
  search.oninput=()=>{librarySearch=search.value.trim().toLocaleLowerCase();renderCards();};
  filter.onchange=()=>{libraryFilter=filter.value;renderCards();};
  libraryToolbar.append(search,filter);$('#presenter-cards').before(libraryToolbar);
  const detail=node('dialog','','presenter-detail-dialog');document.body.append(detail);
  const stopDetail=()=>{for(const video of detail.querySelectorAll('video')){video.pause();video.removeAttribute('src');video.load();}};
  detail.addEventListener('close',stopDetail);
  detail.addEventListener('cancel',stopDetail);
  function button(label,fn,cls='button secondary compact'){
    const b=node('button',label,cls);b.type='button';b.onclick=fn;return b;
  }
  async function libraryChange(job,state){
    const message=state==='trash'?`นำ “${job.name}” ไปถังขยะ?\nกู้คืนได้ ไฟล์ยังเก็บไว้ให้งานเก่าและคิวเดิมใช้งานต่อ ไม่ลบวิดีโอ Final`:
      state==='hidden'?`ซ่อน “${job.name}” จากคลังหลัก? งานเก่าไม่เปลี่ยน`:`นำ “${job.name}” กลับเข้าคลัง?`;
    if(!window.confirm(message))return;
    try{await postAction('presenter_library_state',{id:job.id,state,confirmed:true});await refresh();toast(state==='trash'?'ย้ายเข้าถังขยะแล้ว • กู้คืนได้':'ปรับคลังแล้ว');}
    catch(e){toast(e.message,'error');}
  }
  function showDetail(job){
    stopDetail();detail.replaceChildren();
    const head=node('div','','presenter-detail-head');head.append(node('h2',job.name),button('ปิด ×',()=>detail.close()));detail.append(head);
    detail.append(node('p',`${status[job.status]||job.status} • คลิป ${Object.keys(job.clips||{}).length}/3`));
    const choices=[];if(job.status==='ready')choices.push(['export','คลิปรวม']);
    for(const index of Object.keys(job.clips||{}))choices.push([index,'คลิป '+index]);
    if(choices.length){
      const select=node('select','');select.setAttribute('aria-label','เลือกคลิปพรีวิว');for(const [value,label]of choices)select.add(new Option(label,value));
      const video=node('video','');video.controls=true;video.muted=true;video.preload='metadata';video.setAttribute('aria-label','พรีวิว '+job.name);video.src=url(job.id,choices[0][0]);
      const note=node('p','','presenter-media-note');note.setAttribute('role','status');
      video.onerror=()=>{note.textContent='เปิดพรีวิวไม่ได้ • ลองเปิดไฟล์จากโฟลเดอร์ตัวละคร';};
      select.onchange=()=>{video.pause();note.textContent='';video.src=url(job.id,select.value);video.load();};detail.append(select,video,note);
    }else if(job.image){const im=node('img','');im.src=url(job.id,'image');im.alt=job.name;detail.append(im);}
    const actions=node('div','','actions');actions.append(button('เปิดโฟลเดอร์',()=>postAction('presenter_open_folder',{id:job.id}).catch(e=>toast(e.message,'error'))));
    if(job.status==='ready'){const a=node('a','ดาวน์โหลดคลิปรวม','button secondary compact');a.href=url(job.id,'export');a.download=job.name+'-green-screen.mp4';actions.append(a);}
    actions.append(button('คัดลอก Log',()=>navigator.clipboard.writeText(JSON.stringify({service:'SmartFlow Presenter',id:job.id,status:job.status,stage:job.stage,error:job.error,intents:job.intents,clips:job.clips},null,2)).then(()=>toast('คัดลอก Log แล้ว')).catch(e=>toast(e.message,'error'))));detail.append(actions);
    if(job.error){const more=node('details','');more.append(node('summary','รายละเอียดจุดที่หยุด'),node('p',job.error));detail.append(more);}
    if(!detail.open)detail.showModal();
  }
  function renderCards(){
    const root=$('#presenter-cards');root.replaceChildren();
    const visible=jobs.filter(j=>{
      const state=j.library_state||'visible';
      return String(j.name||'').toLocaleLowerCase().includes(librarySearch)&&
        (libraryFilter==='trash'?state==='trash':libraryFilter==='hidden'?state==='hidden':state==='visible'&&
          (libraryFilter==='all'||(libraryFilter==='ready'?j.status==='ready':j.status!=='ready')));
    });
    if(!visible.length){root.append(node('p','ไม่มีตัวละครในรายการนี้ • เปลี่ยนตัวกรอง หรือสร้างตัวละครด้านบน'));return;}
    for(const job of visible){
      const card=node('article','','presenter-card');
      if(job.image){const im=node('img','');im.src=url(job.id,'image');im.alt=job.name;im.loading='lazy';card.append(im);}
      else card.append(node('div','ยังไม่มีภาพตัวละคร','presenter-cover-empty'));
      card.append(node('h3',job.name),node('small',`${status[job.status]||job.status} • คลิป ${Object.keys(job.clips||{}).length}/3`));
      const actions=node('div','','actions');
      actions.append(button(job.status==='ready'?'ดูวิดีโอ':'ดูรายละเอียด',()=>showDetail(job)));
      if(job.status==='ready'&&job.library_state!=='trash')actions.append(button('เลือกใช้งาน',()=>{
        showPage('presenter-settings');const select=$('[data-p="id"]',panels.settings.panel);select.value=job.id;select.onchange();
        toast('เลือกตัวละครแล้ว • ปรับตำแหน่งและกดบันทึกเพื่อใช้กับงานใหม่');
      }));
      if(job.library_state!=='trash'&&job.status!=='ready'&&job.status!=='running'){
        const review=['image_review','clip_review'].includes(job.status),button=node('button',review?'ตรวจแล้ว ทำต่อ':'เริ่ม / ทำต่อ','button secondary compact');button.type='button';
        button.onclick=async()=>{try{await postAction(review?'presenter_approve':'presenter_run',{id:job.id,confirmed:review});await refresh();}catch(e){toast(e.message,'error');}};actions.append(button);
      }
      card.append(actions);
      const menu=node('details','','presenter-card-menu');menu.append(node('summary','จัดการตัวละคร ⋯'));
      if(job.library_state==='trash')menu.append(button('กู้คืน',()=>libraryChange(job,'visible')));
      else{
        menu.append(button(job.library_state==='hidden'?'แสดงในคลัง':'ซ่อนจากคลัง',()=>libraryChange(job,job.library_state==='hidden'?'visible':'hidden')));
        menu.append(button('ลบเข้าถังขยะ',()=>libraryChange(job,'trash'),'button ghost compact presenter-trash'));
      }
      card.append(menu);
      root.append(card);
    }
  }
  const panels={};
  for(const mode of ['settings']){
    const panel=document.createElement('section');panel.className='presenter-controls';
    panel.innerHTML=`<h2>เลือกตัวละครและจัดตำแหน่ง</h2><div class="presenter-options"><div class="presenter-fields"><label class="field"><span>ตัวละครที่พร้อมใช้</span><select data-p="id"><option value="">ยังไม่มีตัวละครพร้อมใช้</option></select></label><div class="presenter-position-buttons"><button type="button" class="button secondary compact" data-x="5">ล่างซ้าย</button><button type="button" class="button secondary compact" data-x="50">ล่างกลาง</button><button type="button" class="button secondary compact" data-x="95">ล่างขวา</button></div><label class="field"><span>ขนาดตัวละคร</span><input data-p="size" type="range" min="15" max="60" value="32"></label><label class="field"><span>แสดงช่วงไหน</span><select data-p="timing"><option value="all">ตลอดคลิป</option><option value="intro_outro">5 วินาทีแรกและท้าย</option></select></label><label class="field"><span>วิดีโอพื้นหลังสำหรับทดลองตำแหน่ง</span><select data-p="background"><option value="">พื้นตัวอย่าง</option></select></label><details><summary>ปรับขอบพื้นสี</summary><label class="field"><span>ความแรงในการตัดสี</span><input data-p="similarity" type="range" min="0.01" max="0.5" step="0.01" value="0.18"></label><label class="field"><span>ความนุ่มขอบ</span><input data-p="blend" type="range" min="0" max="0.3" step="0.01" value="0.08"></label></details><small>ลากตัวละครในพรีวิวเพื่อย้ายตำแหน่ง ระวังไม่ทับซับ โลโก้ และสินค้าหลัก<br>พรีวิวนี้ประมาณขอบสีเพื่อจัดตำแหน่ง ผลเรนเดอร์ใช้การตัดสีและลดขอบเขียวในโปรแกรม</small></div><div class="presenter-preview"><canvas width="270" height="480" aria-label="พรีวิวตำแหน่งผู้บรรยาย"></canvas><button type="button" class="button secondary compact" data-play>▶ เล่นพรีวิว</button><video muted loop playsinline></video><video data-bg muted loop playsinline></video><small class="presenter-preview-note">เส้นล่าง = พื้นที่ซับโดยประมาณ</small></div></div>`;
    $('#presenter-settings-panel').append(panel);
    const footer=node('div','','actions presenter-settings-footer');
    const save=node('button','บันทึกการตั้งค่า','button primary'),back=node('button','กลับไปสร้างคลิป','button secondary');save.type=back.type='button';
    const feedback=node('span','ยังไม่มีการเปลี่ยนแปลง','presenter-save-note');feedback.setAttribute('role','status');
    footer.append(save,back,feedback);panel.append(footer);
    save.onclick=async()=>{save.disabled=true;defaultsEpoch++;try{const result=await postAction('presenter_save_settings',{settings:settingsValue()});saved={settings:result.settings,available:true,name:jobs.find(j=>j.id===result.settings.id)?.name||''};feedback.textContent='บันทึกแล้ว • ใช้กับงานใหม่ งานเดิมไม่เปลี่ยน';$('#presenter-settings-status').textContent='บันทึกแล้ว: '+saved.name;updateToggles();}catch(e){feedback.textContent=e.message;toast(e.message,'error');}finally{defaultsEpoch++;save.disabled=false;}};
    back.onclick=returnToCreation;
    panel.addEventListener('input',()=>{feedback.textContent='มีการเปลี่ยนแปลง • ยังไม่บันทึก';});
    const model={panel,x:95,y:95,video:$('video',panel),bg:$('video[data-bg]',panel),canvas:$('canvas',panel),playing:false,stamp:0};panels[mode]=model;
    model.video.crossOrigin='anonymous';model.bg.crossOrigin='anonymous';
    for(const b of $$('[data-x]',panel))b.onclick=()=>{feedback.textContent='มีการเปลี่ยนแปลง • ยังไม่บันทึก';model.x=Number(b.dataset.x);model.y=95;draw(model);};
    $('select[data-p="id"]',panel).onchange=()=>{const id=$('[data-p="id"]',panel).value;model.video.pause();model.playing=false;if(id)model.video.src=url(id,'export');else model.video.removeAttribute('src');draw(model);};
    $('[data-p="background"]',panel).onchange=e=>{model.bg.pause();if(e.target.value)model.bg.src='/api/desktop/media?item_id='+encodeURIComponent(e.target.value)+'&kind=video';else model.bg.removeAttribute('src');draw(model);};
    for(const field of $$('input,select',panel))field.addEventListener('input',()=>draw(model));
    $('[data-play]',panel).onclick=async()=>{try{if(model.playing){model.video.pause();model.bg.pause();model.playing=false;$('[data-play]',panel).textContent='▶ เล่นพรีวิว';return;}if(!model.video.getAttribute('src'))throw new Error('เลือกตัวละครที่พร้อมใช้ก่อน');await model.video.play();if(model.bg.getAttribute('src'))await model.bg.play();model.playing=true;$('[data-play]',panel).textContent='❚❚ หยุดพรีวิว';if(!animation)animation=requestAnimationFrame(frame);}catch(e){model.video.pause();model.bg.pause();model.playing=false;toast(e.message,'error');}};
    for(const video of [model.video,model.bg])video.addEventListener('loadeddata',()=>draw(model));
    const move=e=>{feedback.textContent='มีการเปลี่ยนแปลง • ยังไม่บันทึก';const rect=model.canvas.getBoundingClientRect(),scale=Number($('[data-p="size"]',panel).value)/100;model.x=Math.max(0,Math.min(100,((e.clientX-rect.left)/rect.width-scale/2)/(1-scale)*100));model.y=Math.max(0,Math.min(100,((e.clientY-rect.top)/rect.height-scale/2)/(1-scale)*100));draw(model);};
    model.canvas.onpointerdown=e=>{model.canvas.setPointerCapture(e.pointerId);move(e);};model.canvas.onpointermove=e=>{if(model.canvas.hasPointerCapture(e.pointerId))move(e);};
    const sizeField=$('[data-p="size"]',panel),sizeOutput=node('output',sizeField.value+'%');sizeField.before(sizeOutput);sizeField.addEventListener('input',()=>{sizeOutput.textContent=sizeField.value+'%';});
    model.sizeOutput=sizeOutput;draw(model);
  }
  function draw(m){
    const c=m.canvas,ctx=c.getContext('2d');ctx.fillStyle='#1a273d';ctx.fillRect(0,0,c.width,c.height);
    if(m.bg.readyState>=2&&m.bg.getAttribute('src'))ctx.drawImage(m.bg,0,0,c.width,c.height);
    if(m.video.readyState>=2&&m.video.getAttribute('src')){
      const layer=m.layer||(m.layer=document.createElement('canvas'));layer.width=135;layer.height=240;const lc=layer.getContext('2d',{willReadFrequently:true});lc.drawImage(m.video,0,0,135,240);
      const pixels=lc.getImageData(0,0,135,240),id=$('[data-p="id"]',m.panel).value,ch=jobs.find(j=>j.id===id)?.screen==='blue'?2:1;
      const similarity=Number($('[data-p="similarity"]',m.panel).value),blend=Math.max(.0001,Number($('[data-p="blend"]',m.panel).value));
      const keyU=ch===1?-.331264:.5,keyV=ch===1?-.418688:-.081312;
      for(let i=0;i<pixels.data.length;i+=4){
        const r=pixels.data[i]/255,g=pixels.data[i+1]/255,b=pixels.data[i+2]/255;
        const du=-.168736*r-.331264*g+.5*b-keyU,dv=.5*r-.418688*g-.081312*b-keyV;
        pixels.data[i+3]=255*Math.max(0,Math.min(1,(Math.sqrt((du*du+dv*dv)/2)-similarity)/blend));
      }
      lc.putImageData(pixels,0,0);const w=c.width*Number($('[data-p="size"]',m.panel).value)/100,h=w*240/135;ctx.drawImage(layer,(c.width-w)*m.x/100,(c.height-h)*m.y/100,w,h);
    }else{ctx.fillStyle='#8696b3';ctx.font='14px sans-serif';ctx.fillText('เลือกตัวละครจากคลัง',45,220);}
    ctx.strokeStyle='#72dfea';ctx.setLineDash([4,4]);ctx.strokeRect(12,c.height*.84,c.width-24,c.height*.12);ctx.setLineDash([]);
  }
  function updateChoices(){for(const m of Object.values(panels)){const select=$('[data-p="id"]',m.panel),value=select.value;select.replaceChildren(new Option('เลือกตัวละครที่พร้อมใช้',''));for(const j of jobs.filter(j=>j.status==='ready'&&j.library_state!=='trash'))select.add(new Option(j.name,j.id));select.value=value;}}
  function settingsValue(){
    const m=panels.settings,value=key=>$('[data-p="'+key+'"]',m.panel).value;
    return {enabled:true,id:value('id'),x:m.x,y:m.y,size:Number(value('size')),timing:value('timing'),similarity:Number(value('similarity')),blend:Number(value('blend'))};
  }
  function loadDraft(value){
    if(!value?.enabled)return;const m=panels.settings;
    for(const key of ['id','size','timing','similarity','blend'])$('[data-p="'+key+'"]',m.panel).value=value[key];
    m.x=value.x;m.y=value.y;m.sizeOutput.textContent=value.size+'%';$('[data-p="id"]',m.panel).onchange();
  }
  const toggles={};
  for(const mode of ['product','story','story-batch','product-batch','drama']){
    const batch=mode.endsWith('-batch'),base=mode.split('-')[0];
    const box=node('div','','presenter-quick-choice'),label=node('label','','presenter-check'),check=node('input');
    box.id='presenter-choice-'+mode;if(batch)box.dataset.batch=base;
    check.id='presenter-use-'+mode;check.setAttribute('aria-describedby','presenter-info-'+mode);
    check.type='checkbox';check.disabled=true;label.append(check,document.createTextNode('ใส่ตัวละครผู้บรรยาย'));
    const info=node('small','กำลังอ่านค่าที่บันทึกไว้'),change=node('button','เปลี่ยนการตั้งค่า','button ghost compact');change.type='button';
    info.id='presenter-info-'+mode;info.setAttribute('aria-live','polite');
    change.onclick=()=>{
      returnPage=ui.activePage;returnDialog=batch?$(base==='story'?'#story-batch-modal':'#creation-editor'):null;
      if(returnDialog?.open)returnDialog.close();showPage('presenter-settings');
    };
    box.append(label,info,change);toggles[mode]={check,info,box};
    if(batch){box.append(node('small','ใช้ตัวเลือกนี้กับทุกคลิปในชุด • บันทึกแยกกับแต่ละงาน ไม่เปลี่ยนคิวเก่า','presenter-batch-note'));}
    const anchor=mode==='drama'?$('#drama-presenter-anchor'):mode==='product'?$('.create-submit-stack')?.parentElement:mode==='story'?$('.story-submit-bar'):mode==='story-batch'?$('#story-batch-provider')?.closest('.field'):$('#creation-editor-settings');
    anchor?.before(box);
  }
  // New modal drafts inherit the visible single-clip choice once, then stay independent.
  window.preparePresenterQueue=(mode,{editing=false}={})=>{
    const t=toggles[mode];if(!t||!mode.endsWith('-batch'))return;
    t.box.hidden=editing;
    if(!editing)t.check.checked=toggles[mode.split('-')[0]].check.checked;
    updateToggles();refresh();
  };
  function updateToggles(){
    for(const t of Object.values(toggles)){
      t.check.disabled=!loaded||!saved.available;
      const v=saved.settings||{};
      t.info.textContent=saved.available
        ?'ใช้: '+saved.name+' • '+(v.x<=10?'ล่างซ้าย':v.x>=90?'ล่างขวา':v.x===50&&v.y>=90?'ล่างกลาง':'ตำแหน่งที่บันทึก')+' • ขนาด '+v.size+'%'
        :(saved.error||'ยังไม่มีผู้บรรยายที่บันทึกไว้ • ไปเลือกและบันทึกก่อน');
    }
  }
  window.presenterPayload=(action,payload)=>{
    if(window.productOptionSnapshot?.isFrozen(payload)||payload.creative_context?.kind==='product_story')return payload;
    if(!['create_product','create_story','create_drama_series','creation_enqueue','enqueue_story_batch'].includes(action)||payload.job_id)return payload;
    if(action==='creation_enqueue'&&payload.mode&&!['product','story'].includes(payload.mode))return payload;
    const mode=action==='create_drama_series'?'drama':action==='enqueue_story_batch'?'story-batch'
      :action==='create_story'||payload.mode==='story'?'story'
      :action==='creation_enqueue'&&$('#creation-editor')?.open?'product-batch':'product';
    const enabled=toggles[mode].check.checked;
    if(enabled&&(!loaded||!saved.available))throw new Error('ผู้บรรยายที่บันทึกไว้ไม่พร้อม • ตรวจการตั้งค่าก่อนเริ่มงาน');
    return {...payload,presenter:enabled?JSON.parse(JSON.stringify(saved.settings)):{enabled:false}};
  };
  let libraryStamp='';window.renderPresenter=state=>{
    if((['presenter','presenter-settings','products','story','drama'].includes(ui.activePage)||$('#story-batch-modal')?.open||$('#creation-editor')?.open)&&Date.now()-lastPoll>5000)refresh();
    const lib=state.library||[],stamp=JSON.stringify(lib.map(i=>i.item_id));if(stamp!==libraryStamp){libraryStamp=stamp;for(const m of Object.values(panels)){const select=$('[data-p="background"]',m.panel),value=select.value;select.replaceChildren(new Option('พื้นตัวอย่าง',''));for(const item of lib)if(item.item_id)select.add(new Option(item.title||item.item_id,item.item_id));select.value=value;}}
  };
  $('#presenter-form').onsubmit=async e=>{
    e.preventDefault();if(creating)return;creating=true;
    const button=$('button[type="submit"]',e.currentTarget);button.disabled=true;
    try{
      const file=$('#presenter-reference').files[0];let reference='';
      if(file){
        if(!$('#presenter-consent').checked)throw new Error('ยืนยันสิทธิ์ใช้รูปอ้างอิงก่อน');
        const uploaded=await postAction('upload_reference_image',{data_url:await prepareReferenceImage(file),purpose:'presenter',filename:file.name});
        reference='asset:'+uploaded.asset_id;
      }
      const created=await postAction('presenter_create',{name:$('#presenter-name').value,description:$('#presenter-description').value,provider:$('#presenter-provider').value,style:$('#presenter-style').value,screen:$('#presenter-screen').value,reference,consent:$('#presenter-consent').checked,review:$('#presenter-review').checked});
      await refresh();await postAction('presenter_run',{id:created.job.id});await refresh();
    }catch(error){toast(error.message,'error');}finally{creating=false;button.disabled=false;}
  };
  $('#presenter-refresh').onclick=refresh;$('#presenter-cancel').onclick=()=>postAction('presenter_cancel').then(refresh).catch(e=>toast(e.message,'error'));
  const frame=now=>{animation=0;for(const [mode,m] of Object.entries(panels)){const visible=!document.hidden&&ui.activePage==='presenter-settings'&&true;if(!visible&&m.playing){m.video.pause();m.bg.pause();m.playing=false;$('[data-play]',m.panel).textContent='▶ เล่นพรีวิว';}if(visible&&m.playing&&now-m.stamp>80){draw(m);m.stamp=now;}}if(Object.values(panels).some(m=>m.playing))animation=requestAnimationFrame(frame);};
  document.addEventListener('visibilitychange',()=>{if(document.hidden){for(const m of Object.values(panels)){m.video.pause();m.bg.pause();m.playing=false;}cancelAnimationFrame(animation);animation=0;}});
})();
