(() => {
  pageMeta.green=['กรีนสกรีน','กรีนสกรีน / แสง'];
  const page=document.createElement('section');page.className='page';page.dataset.view='green';
  page.innerHTML=`<section class="page-intro"><div><span class="eyebrow">กรีนสกรีน</span><h1>เพิ่มแสงและประกายให้คลิป</h1><p>ลบพื้นเขียว • วนภาพเอฟเฟกต์ชั้นบนสุด • ไม่ใช้เสียงของกรีนสกรีน</p></div></section>
  <section class="panel" style="padding:24px;max-width:860px">
    <h2>1. เลือกเอฟเฟกต์ 1–3 ไฟล์</h2><button class="button secondary" type="button" id="green-upload-button">＋ อัปโหลดกรีนสกรีน</button>
    <input id="green-upload" type="file" accept=".mp4,.mov,.mkv,.webm,.m4v,.avi" hidden>
    <p>เก็บได้หลายไฟล์ • เลือกใช้ครั้งละไม่เกิน 3 ไฟล์ • ขนาดไฟล์ไม่เกิน 500 MB</p>
    <div id="green-assets"></div><h2>2. ลำดับและความเข้ม</h2><div id="green-order"></div>
    <p>เล่นทีละไฟล์จนจบ แล้ววนกลับไฟล์แรก หยุดพร้อมคลิปหลัก • อยู่เหนือซับ โลโก้ และอินโทร</p>
    <label class="field"><span>ความเข้มเอฟเฟกต์ <output id="green-opacity-label">50%</output></span><input id="green-opacity" type="range" min="1" max="100" value="50"></label>
    <label class="field"><span>จัดภาพ</span><select id="green-fit"><option value="contain">แสดงครบภาพ ไม่ยืด</option><option value="cover">เต็มเฟรม ตัดส่วนเกิน</option></select></label>
    <button class="button secondary" type="button" id="green-preview-button">ดูตัวอย่างหลังลบพื้นเขียว</button>
    <p>พรีวิวสดบนพื้นหลังสาธิต ไม่ต้องรอเรนเดอร์ • ประมาณขอบสีเพื่อปรับค่า คลิปจริงใช้ตัวประกอบคุณภาพเต็ม • ไม่มีเสียงเอฟเฟกต์</p>
    <canvas id="green-preview" width="270" height="480" hidden aria-label="พรีวิวแสงหลังลบพื้นเขียว" style="width:100%;max-width:270px"></canvas>
    <video id="green-preview-source" muted playsinline hidden preload="auto"></video>
    <h2>3. ใช้เป็นค่าเริ่มต้นกับงานไหน</h2>
    <div id="green-targets"></div><p>เลือกได้หลายประเภท ปิดเฉพาะงานได้ก่อนสร้าง • ไม่เปลี่ยนคิวเก่า</p>
    <button class="button primary" type="button" id="green-save">บันทึกใช้รอบหน้า</button>
    <p id="green-status" role="status" aria-live="polite"></p>
  </section>`;
  document.querySelector('[data-view="settings"]').after(page);
  if(ui.activePage==='green')page.classList.add('active');
  const q=s=>page.querySelector(s),status=t=>q('#green-status').textContent=t;
  const original=postAction,panels=new Map();
  let saved={settings:{enabled:false,clips:[],opacity:.5,fit:'contain'},targets:{},assets:[]},draft=[],busy=false,loaded=false;
  const clone=x=>JSON.parse(JSON.stringify(x));
  for(const [key,label] of [['story','เรื่องเล่า Shorts (รวมหลายหัวข้อลงคิว)'],['drama','ละครสั้น AI'],['product','คลิปสินค้า']]){
    const el=document.createElement('label');el.style.cssText='display:flex;align-items:center;gap:10px;margin:14px 0';
    el.innerHTML=`<input type="checkbox" data-green-target="${key}" style="width:18px;height:18px;flex:0 0 18px"><span>${label}</span>`;q('#green-targets').append(el);
  }
  for(const [key,selector] of [['product','#product-video-provider'],['product-batch','#creation-form .cq-buttons'],['story','#story-video-mode'],['story-batch','#story-batch-video-mode'],['drama','#drama-video-mode']]){
    const anchor=document.querySelector(selector);if(!anchor)continue;
    const box=document.createElement('section');box.className='green-options';box.style.cssText='margin:14px 0;padding:12px;border:1px solid #34415d;border-radius:12px';
    box.innerHTML='<label><input type="checkbox" data-green-enable> ใส่กรีนสกรีน / แสง (ไม่มีเสียง)</label><small data-green-note style="display:block;margin:8px 0"></small><button type="button" class="button ghost compact">ตั้งค่าเอฟเฟกต์</button>';
    (anchor.closest('label')||anchor).after(box);const item={box,dirty:false};panels.set(key,item);
    box.querySelector('input').addEventListener('change',()=>item.dirty=true);
    box.querySelector('button').addEventListener('click',()=>showPage('green'));
  }
  const name=file=>saved.assets.find(a=>a.file===file)?.name||'ไฟล์เอฟเฟกต์';
  function syncPanels(){
    for(const [key,item] of panels){
      const options=item.row?.settings?.green_options||{enabled:false,clips:[]};
      const selection=item.row?options:saved.settings;
      const clips=selection.clips||[];
      if(!item.dirty)item.box.querySelector('input').checked=item.row?options.enabled===true:Boolean(saved.targets[key.replace('-batch','')]);
      item.readOnly=Boolean(item.locked||(item.row&&!clips.length));
      item.box.querySelector('input').disabled=item.readOnly;
      item.box.querySelector('button').disabled=Boolean(item.row);
      const note=clips.length?clips.map((c,i)=>`${i+1}. ${name(c.file)}`).join(' → ')+' • วนจนจบคลิป':'ยังไม่ได้บันทึกเอฟเฟกต์';
      item.box.querySelector('[data-green-note]').textContent=item.locked?'อ่านอย่างเดียว • รายการเริ่มทำแล้วหรือประเภทนี้ไม่รองรับการแก้กรีนสกรีน'
        :item.row&&!clips.length?'อ่านอย่างเดียว • รายการนี้ไม่มีเอฟเฟกต์ที่บันทึกไว้ • เลือกใช้ค่าปัจจุบันทั้งชุดหากต้องการเปลี่ยน'
        :(item.row?'ค่าของรายการนี้ • เปิด/ปิดโดยเก็บไฟล์และความเข้มเดิม • ':'')+note;
    }
  }
  window.prepareGreenQueue=(row=null,{useCurrentSettings=false}={})=>{
    const item=panels.get('product-batch');if(!item)return;
    item.queueId=row?.queue_id||'';
    item.locked=Boolean(row&&(row.status!=='queued'||row.job_id||!['product','story'].includes(row.mode)||row.long_video));
    item.row=row&&(!useCurrentSettings||item.locked)?clone(row):null;
    item.dirty=false;syncPanels();
  };
  function renderLists(){
    stopPreview();
    q('#green-assets').replaceChildren();q('#green-order').replaceChildren();
    if(!saved.assets.length)q('#green-assets').textContent='ยังไม่มีไฟล์ • อัปโหลดวิดีโอพื้นเขียวก่อน';
    for(const asset of saved.assets){
      const row=document.createElement('label');row.style.cssText='display:flex;gap:12px;align-items:center;padding:10px;border-bottom:1px solid #34415d;overflow-wrap:anywhere';
      const check=document.createElement('input');check.type='checkbox';check.checked=draft.some(c=>c.file===asset.file);check.disabled=!check.checked&&draft.length>=3;
      const video=document.createElement('video');video.src='/api/desktop/green-asset?file='+encodeURIComponent(asset.file);video.muted=true;video.preload='metadata';video.style.cssText='width:70px;height:70px;object-fit:contain;flex-shrink:0';
      const text=document.createElement('span');text.textContent=`${asset.name} • ${Number(asset.duration).toFixed(1)} วินาที`;
      check.addEventListener('change',()=>{if(check.checked&&draft.length<3)draft.push({file:asset.file,color:'#00ff00',similarity:.15,blend:.08});else draft=draft.filter(c=>c.file!==asset.file);renderLists();});
      const remove=document.createElement('button');remove.type='button';remove.className='button ghost compact';remove.textContent='เอาออกจากคลัง';remove.title='เก็บไฟล์ที่งานเก่าใช้อยู่ ไม่ลบต้นฉบับ';
      remove.onclick=async event=>{event.preventDefault();event.stopPropagation();if(busy)return;if(draft.some(c=>c.file===asset.file)){status('ยกเลิกเลือกไฟล์นี้และบันทึกก่อนเอาออกจากคลัง');return;}lock(true);try{const result=await original('green_remove',{file:asset.file});if(!result.ok)throw Error(result.error||'เอาออกไม่ได้');saved.assets=result.assets;renderLists();status('เอาออกจากรายการแล้ว • เก็บไฟล์สำหรับงานเก่าไว้');}catch(e){status(window.smartflowSafeError?.(e.message)||'เอาออกไม่สำเร็จ');}finally{lock(false);}};
      row.append(check,video,text,remove);q('#green-assets').append(row);
    }
    draft.forEach((clip,index)=>{
      const row=document.createElement('div');row.style.cssText='padding:12px;margin:8px 0;border:1px solid #34415d;border-radius:10px;overflow-wrap:anywhere';
      const title=document.createElement('strong');title.textContent=`${index+1}. ${name(clip.file)}`;row.append(title);
      for(const [label,offset] of [[' ↑ ', -1],[' ↓ ',1]]){
        const button=document.createElement('button');button.type='button';button.className='button ghost compact';button.textContent=label;button.setAttribute('aria-label',label.trim()==='↑'?'เลื่อนขึ้น':'เลื่อนลง');button.disabled=index+offset<0||index+offset>=draft.length;
        button.onclick=()=>{[draft[index],draft[index+offset]]=[draft[index+offset],draft[index]];renderLists();};row.append(button);
      }
      const detail=document.createElement('details');const summary=document.createElement('summary');summary.textContent='ตั้งค่าเพิ่มเติม: สีพื้นและขอบ';detail.append(summary);
      for(const [key,label,type,min,max,step] of [['color','สีพื้น','color'],['similarity','ระดับลบพื้น','range','.01','1','.01'],['blend','ความนุ่มขอบ','range','0','1','.01']]){
        const field=document.createElement('label');field.className='field';field.textContent=label;const input=document.createElement('input');input.type=type;input.value=clip[key];if(min){input.min=min;input.max=max;input.step=step;}input.oninput=()=>clip[key]=type==='color'?input.value:Number(input.value);field.append(input);detail.append(field);
      }row.append(detail);q('#green-order').append(row);
    });
  }
  function load(result){saved=clone(result);loaded=true;draft=clone(saved.settings.clips);q('#green-opacity').value=saved.settings.opacity*100;q('#green-opacity-label').textContent=Math.round(saved.settings.opacity*100)+'%';q('#green-fit').value=saved.settings.fit;
    q('#green-targets').querySelectorAll('input').forEach(e=>e.checked=Boolean(saved.targets[e.dataset.greenTarget]));renderLists();syncPanels();}
  const options=()=>({enabled:draft.length>0,clips:clone(draft),opacity:Number(q('#green-opacity').value)/100,fit:q('#green-fit').value});
  const ready=original('green_status',{}).then(r=>{if(!r.ok)throw Error(r.error||'อ่านค่าไม่ได้');load(r);}).catch(e=>status(window.smartflowSafeError?.(e.message)||'อ่านค่าไม่สำเร็จ'));
  q('#green-opacity').oninput=()=>q('#green-opacity-label').textContent=q('#green-opacity').value+'%';
  function lock(value){busy=value;for(const id of ['#green-upload-button','#green-save','#green-preview-button'])q(id).disabled=value;}
  q('#green-upload-button').onclick=()=>{if(!busy){q('#green-upload').value='';q('#green-upload').click();}};
  q('#green-upload').addEventListener('cancel',()=>status('ยกเลิกการเลือกไฟล์'));
  q('#green-upload').onchange=async()=>{
    const file=q('#green-upload').files[0];if(!file||busy)return;
    if(!/\.(mp4|mov|mkv|webm|m4v|avi)$/i.test(file.name)||file.size<=0||file.size>500*1024*1024){status('เลือกไฟล์วิดีโอที่รองรับ ขนาดไม่เกิน 500 MB');return;}
    lock(true);const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),180000);
    try{status('กำลังอัปโหลดและตรวจวิดีโอ…');const response=await fetch('/api/desktop/green-upload',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file,signal:controller.signal});const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'อัปโหลดไม่สำเร็จ');saved.assets=result.assets;renderLists();status('อัปโหลดแล้ว • ติ๊กเลือกไฟล์ที่ต้องการ');}
    catch(e){status(e.name==='AbortError'?'หมดเวลารออัปโหลด กรุณาตรวจรายการก่อนลองใหม่':(window.smartflowSafeError?.(e.message)||'อัปโหลดไม่สำเร็จ'));}finally{clearTimeout(timer);lock(false);q('#green-upload').value='';}
  };
  q('#green-save').onclick=async()=>{if(busy)return;lock(true);try{const targets={};q('#green-targets').querySelectorAll('input').forEach(e=>targets[e.dataset.greenTarget]=e.checked);const result=await original('green_save',{settings:options(),targets});if(!result.ok)throw Error(result.error||'บันทึกไม่ได้');load(result);status('บันทึกแล้ว • ใช้กับงานใหม่ ไม่เปลี่ยนคิวเก่า');}catch(e){status(window.smartflowSafeError?.(e.message)||'บันทึกไม่สำเร็จ');}finally{lock(false);}};
  // Settings preview deliberately avoids the offline FFV1 + MP4 final compositor.
  // One decoder and a small canvas bound CPU/memory, including for 4K source files.
  const preview=q('#green-preview'),source=q('#green-preview-source');
  const layer=document.createElement('canvas');layer.width=270;layer.height=480;
  const context=preview.getContext('2d'),lc=layer.getContext('2d',{willReadFrequently:true});
  let previewRunning=false,previewIndex=0,previewFrame=0,previewEpoch=0,previewTimer=0,lastFrame=0;
  function stopPreview(message){
    previewRunning=false;previewEpoch++;clearTimeout(previewTimer);cancelAnimationFrame(previewFrame);
    source.pause();source.onloadeddata=null;source.onerror=null;source.onended=null;
    source.removeAttribute('src');source.load();
    q('#green-preview-button').textContent='ดูตัวอย่างหลังลบพื้นเขียว';
    if(message)status(message);
  }
  function drawPreview(){
    if(source.readyState<2||!draft[previewIndex])return;
    const clip=draft[previewIndex],w=layer.width,h=layer.height;
    const scale=(q('#green-fit').value==='cover'?Math.max:Math.min)(w/source.videoWidth,h/source.videoHeight);
    lc.clearRect(0,0,w,h);lc.drawImage(source,(w-source.videoWidth*scale)/2,(h-source.videoHeight*scale)/2,source.videoWidth*scale,source.videoHeight*scale);
    const pixels=lc.getImageData(0,0,w,h),data=pixels.data;
    const rgb=clip.color.match(/[a-f0-9]{2}/gi).map(v=>parseInt(v,16)/255);
    const keyU=-.168736*rgb[0]-.331264*rgb[1]+.5*rgb[2],keyV=.5*rgb[0]-.418688*rgb[1]-.081312*rgb[2];
    const blend=Math.max(.0001,clip.blend),opacity=Number(q('#green-opacity').value)/100;
    for(let i=0;i<data.length;i+=4){
      if(!data[i+3])continue;
      const r=data[i]/255,g=data[i+1]/255,b=data[i+2]/255;
      const du=-.168736*r-.331264*g+.5*b-keyU,dv=.5*r-.418688*g-.081312*b-keyV;
      data[i+3]*=opacity*Math.max(0,Math.min(1,(Math.sqrt((du*du+dv*dv)/2)-clip.similarity)/blend));
    }
    lc.putImageData(pixels,0,0);context.fillStyle='#273650';context.fillRect(0,0,w,h);context.drawImage(layer,0,0);
  }
  function previewTick(now){
    if(!previewRunning)return;
    if(now-lastFrame>=1000/24){lastFrame=now;drawPreview();}
    previewFrame=requestAnimationFrame(previewTick);
  }
  function playPreviewClip(index){
    const epoch=++previewEpoch;previewIndex=index;clearTimeout(previewTimer);
    source.pause();source.muted=true;source.defaultMuted=true;source.volume=0;source.loop=false;
    const failed=()=>{if(epoch===previewEpoch)stopPreview('เบราว์เซอร์ยังเล่นไฟล์นี้ไม่ได้หรือโหลดช้า • ลองใช้ MP4 (H.264) สำหรับพรีวิว การเรนเดอร์จริงยังรองรับไฟล์เดิม');};
    source.onerror=failed;
    source.onloadeddata=async()=>{
      if(epoch!==previewEpoch)return;
      clearTimeout(previewTimer);
      try{await source.play();if(epoch!==previewEpoch)return;drawPreview();status('พรีวิวสด • '+(index+1)+'/'+draft.length+' '+name(draft[index].file)+' • ปรับค่าได้ทันที ไม่มีเสียง');}
      catch(e){if(epoch===previewEpoch)stopPreview('เล่นพรีวิวไม่ได้: '+e.message);}
    };
    source.onended=()=>{if(previewRunning&&epoch===previewEpoch)playPreviewClip((index+1)%draft.length);};
    previewTimer=setTimeout(failed,15000);
    source.src='/api/desktop/green-asset?file='+encodeURIComponent(draft[index].file);source.load();
  }
  q('#green-preview-button').onclick=()=>{
    if(previewRunning){stopPreview('หยุดพรีวิวแล้ว');return;}if(busy)return;
    if(!draft.length){status('เลือกเอฟเฟกต์ก่อนดูตัวอย่าง');return;}
    preview.hidden=false;previewRunning=true;lastFrame=0;
    q('#green-preview-button').textContent='หยุดพรีวิว';status('กำลังเปิดไฟล์พรีวิว…');
    playPreviewClip(0);previewFrame=requestAnimationFrame(previewTick);
  };
  new MutationObserver(()=>{if(!page.classList.contains('active'))stopPreview();}).observe(page,{attributes:true,attributeFilter:['class']});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stopPreview();});
  window.addEventListener('pagehide',()=>stopPreview());
  postAction=async(action,payload={})=>{
    const key=window.smartflowCreationFormKey?.(action,payload),item=panels.get(key);
    if(item&&!payload.job_id){
      if(action==='creation_edit'&&!payload.use_current_settings){
        // No global library reads (including a late load) may replace this row.
        if(item.queueId===payload.queue_id&&item.row&&!item.readOnly&&item.dirty)
          payload={...payload,green_options:{enabled:item.box.querySelector('input').checked}};
      }else if(!item.locked){
        await ready;const enabled=item.box.querySelector('input').checked;
        if(enabled&&(!loaded||!saved.settings.clips.length))throw Error('บันทึกกรีนสกรีนในหมวดตกแต่งคลิปก่อน');
        const selection={...clone(saved.settings),enabled};payload={...payload,green_options:selection};
        if(payload.render_options)payload.render_options={...payload.render_options,green_options:selection};
      }
    }
    return original(action,payload);
  };
})();
