(() => {
  pageMeta.intro=['อินโทรคลิป','อินโทรคลิป'];
  const page=document.createElement('section');page.className='page';page.dataset.view='intro';
  page.innerHTML=`<section class="page-intro"><div><span class="eyebrow">อินโทรคลิป</span><h1>แทรกอินโทรระหว่างคลิป</h1><p>เล่าเรื่องช่วงแรก → สุ่มจังหวะใส่อินโทร → เล่าต่อ</p></div></section>
    <section class="panel" style="padding:24px;max-width:760px"><h2>วิดีโออินโทรที่ใช้ซ้ำ</h2>
    <p>ปล่อยให้เล่าไปก่อน แล้วสุ่มจุดแทรกช่วงต้น โดยเลือกจังหวะพักเสียงก่อนถ้ามี ไม่ล็อกวินาทีเดิมทุกคลิป เสียงและซับจะเล่นต่อหลังอินโทรจบ</p>
    <small>ช่วงประมาณวินาทีที่ 4–12 • คลิปสั้นจะปรับช่วงให้เหมาะสม • ถ้าไม่มีช่วงพักเสียงก็ยังแทรกได้ • ทำงานเดิมซ้ำใช้จุดเดิม</small>
    <label class="field"><span>เลือกวิดีโอที่นำเข้าไว้</span><select id="intro-file"><option value="">ยังไม่ได้เลือกอินโทร</option></select></label>
    <button type="button" class="button secondary" id="intro-import">＋ นำเข้าวิดีโออินโทร</button>
    <input type="file" id="intro-upload" accept=".mp4,.mov,.mkv,.webm,.m4v,.avi" hidden>
    <p id="intro-info" aria-live="polite">รองรับ MP4, MOV, MKV, WebM, M4V และ AVI • ใช้เสียงของอินโทรเอง</p>
    <fieldset style="margin:20px 0;padding:16px;border:1px solid #34415d;border-radius:12px"><legend>ใช้อินโทรกับงานประเภทไหน</legend>
    <label style="display:flex;align-items:center;gap:10px;margin:12px 0"><input type="checkbox" id="intro-story-default" style="width:18px;height:18px;flex:0 0 18px"><span>เรื่องเล่า Shorts (รวมเพิ่มหลายหัวข้อลงคิว)</span></label>
    <label style="display:flex;align-items:center;gap:10px;margin:12px 0"><input type="checkbox" id="intro-drama-default" style="width:18px;height:18px;flex:0 0 18px"><span>ละครสั้น AI</span></label>
    <small>เลือกอย่างใดอย่างหนึ่ง ทั้งสองอย่าง หรือไม่เลือกเลยก็ได้</small></fieldset>
    <button type="button" class="button primary" id="intro-save">บันทึกใช้รอบหน้า</button>
    <p id="intro-status" role="status"></p><small>เลือกเปิด–ปิดเฉพาะงานได้ก่อนสร้างหรือเพิ่มลงคิว คิวที่บันทึกไว้แล้วจะใช้ไฟล์และค่าเดิม</small></section>`;
  document.querySelector('[data-view="settings"]').after(page);
  if(ui.activePage==='intro')page.classList.add('active');
  const panels=new Map();let library={settings:{enabled:false,file:''},assets:[]},loaded=false;
  for(const [key,selector] of [['story','#story-video-mode'],['story-batch','#story-batch-video-mode'],['drama','#drama-video-mode'],['long','#long-mode']]){
    const anchor=document.querySelector(selector);if(!anchor)continue;
    const box=document.createElement('section');box.className='intro-options';box.style.cssText='margin:14px 0;padding:12px;border:1px solid #34415d;border-radius:12px';
    box.innerHTML='<label><input type="checkbox" data-intro-enable> สุ่มแทรกอินโทรหลังเริ่มเล่าเรื่อง</label><small data-intro-note style="display:block;margin-top:6px">ยังไม่ได้เลือกวิดีโออินโทร</small><button type="button" class="button ghost compact" data-intro-settings>ตั้งค่าอินโทร</button>';
    (anchor.closest('label')||anchor).after(box);
    const item={box,dirty:false};panels.set(key,item);
    box.querySelector('[data-intro-enable]').addEventListener('change',()=>item.dirty=true);
    box.querySelector('[data-intro-settings]').addEventListener('click',()=>showPage('intro'));
  }
  function render(value){
    library=value;loaded=true;
    const select=page.querySelector('#intro-file');select.replaceChildren(new Option('ไม่เลือกอินโทร',''));
    for(const asset of library.assets)select.add(new Option(asset.name+' • '+asset.duration.toFixed(1)+' วินาที',asset.file));
    select.value=library.settings.file;
    page.querySelector('#intro-story-default').checked=library.settings.targets?.story??library.settings.enabled;
    page.querySelector('#intro-drama-default').checked=library.settings.targets?.drama??library.settings.enabled;
    for(const [key,item] of panels){
      const target=key==='drama'?'drama':'story';
      const enabled=key==='long'?library.settings.enabled:(library.settings.targets?.[target]??library.settings.enabled);
      if(!item.dirty)item.box.querySelector('[data-intro-enable]').checked=enabled;
      const asset=library.assets.find(a=>a.file===library.settings.file);
      item.box.querySelector('[data-intro-note]').textContent=asset?'อินโทร: '+asset.name:'ยังไม่ได้เลือกวิดีโออินโทร • กดตั้งค่าอินโทร';
    }
  }
  const original=postAction;
  const status=text=>page.querySelector('#intro-status').textContent=text;
  const ready=original('intro_status',{}).then(result=>{if(!result.ok)throw Error(result.error||'อ่านค่าอินโทรไม่ได้');render(result);})
    .catch(error=>status(window.smartflowSafeError?.(error.message)||'อ่านค่าอินโทรไม่สำเร็จ'));
  const picker=page.querySelector('#intro-upload'),importButton=page.querySelector('#intro-import');
  let uploading=false;
  importButton.addEventListener('click',()=>{
    if(uploading)return;
    picker.value='';status('เลือกวิดีโออินโทรจากเครื่อง');picker.click();
  });
  picker.addEventListener('cancel',()=>status('ยกเลิกการเลือกไฟล์'));
  picker.addEventListener('change',async()=>{
    const file=picker.files[0];if(!file||uploading)return;
    if(!/\.(mp4|mov|mkv|webm|m4v|avi)$/i.test(file.name)||file.size<=0||file.size>500*1024*1024){
      status('กรุณาเลือกวิดีโอที่รองรับ ขนาดไม่เกิน 500 MB และไม่ใช่ไฟล์ว่าง');picker.value='';return;
    }
    uploading=true;importButton.disabled=true;page.querySelector('#intro-save').disabled=true;
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),180000);
    try{status('กำลังอัปโหลดและตรวจสอบวิดีโอ…');
      const response=await fetch('/api/desktop/intro-upload',{method:'POST',body:file,
        headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},signal:controller.signal});
      const result=await response.json();
      if(!response.ok||!result.ok)throw Error(result.error||'นำเข้าไม่ได้');
      const selectedTargets=['story','drama'].map(k=>page.querySelector('#intro-'+k+'-default').checked);
      render(result);page.querySelector('#intro-file').value=result.asset.file;
      ['story','drama'].forEach((k,i)=>page.querySelector('#intro-'+k+'-default').checked=selectedTargets[i]);
      status('นำเข้าแล้ว • กดบันทึกเพื่อเลือกใช้ไฟล์นี้');
    }catch(error){status(error.name==='AbortError'?'หมดเวลารอนำเข้า ตรวจไฟล์ในรายการก่อนลองใหม่':(window.smartflowSafeError?.(error.message)||'นำเข้าไม่สำเร็จ'));}
    finally{clearTimeout(timeout);uploading=false;importButton.disabled=false;page.querySelector('#intro-save').disabled=false;picker.value='';}
  });
  page.querySelector('#intro-save').addEventListener('click',async()=>{
    try{const settings={enabled:library.settings.enabled,file:page.querySelector('#intro-file').value,
        targets:{story:page.querySelector('#intro-story-default').checked,drama:page.querySelector('#intro-drama-default').checked}};
      const result=await original('intro_save',{settings});if(!result.ok)throw Error(result.error||'บันทึกไม่ได้');
      render(result);status('บันทึกแล้ว • ใช้กับงานใหม่ ไม่เปลี่ยนคิวที่บันทึกไว้');
    }catch(error){status(window.smartflowSafeError?.(error.message)||'บันทึกไม่สำเร็จ');}
  });
  postAction=async(action,payload={})=>{
    const key=window.smartflowCreationFormKey?.(action,payload),item=panels.get(key);
    if(item&&!payload.job_id){
      await ready;
      const enabled=item.box.querySelector('[data-intro-enable]').checked;
      if(enabled&&(!loaded||!library.settings.file))throw Error('กรุณาเลือกไฟล์ในหมวดตกแต่งคลิป → อินโทรคลิปก่อน');
      const options={enabled,file:library.settings.file};payload={...payload,intro_options:options};
      if(payload.render_options)payload.render_options={...payload.render_options,intro_options:options};
    }
    return original(action,payload);
  };
})();
