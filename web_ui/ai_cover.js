(() => {
  const panels=new Map();
  function mount(key,selector){
    const anchor=document.querySelector(selector);if(!anchor)return;
    const box=document.createElement('section');box.className='ai-cover-options';
    box.style.cssText='margin:14px 0;padding:12px;border:1px solid #34415d;border-radius:12px';
    box.innerHTML='<label><input type="checkbox" data-cover-enable checked> สร้างปกด้วย AI เมื่อคลิปเสร็จ</label><small style="display:block;margin:6px 0">ใช้ชื่อคลิปและภาพที่สร้างแล้ว 1 รูป • AI ตัวเดิม • ใช้โควตาสร้างภาพเพิ่ม</small><details><summary>ตั้งค่าปกเพิ่มเติม</summary><label>ข้อความบนปก (ไม่จำเป็น) <input data-cover-title maxlength="40" placeholder="เว้นว่างให้เลือกวลีสั้นจากเรื่อง"></label><label>ภาพอ้างอิง <select data-cover-scene><option value="0">เลือกภาพอัตโนมัติ</option></select></label><small>หลังคลิปเสร็จ เลือกภาพตัวอย่างและทำปกใหม่ได้ในคลังวิดีโอ</small></details>';
    (anchor.closest('label')||anchor).after(box);
    box.querySelector('small').textContent='ใช้ชื่อคลิป/ชื่อสินค้าและภาพที่สร้างแล้ว 2 รูป • ถ้ามีเพียงรูปเดียวใช้รูปนั้น • AI ตัวเดิม • คิวรอจนปกพร้อมก่อนเริ่มหัวข้อถัดไป';
    box.querySelector('[data-cover-title]').closest('label').hidden=true;
    const entry={read:()=>({enabled:box.querySelector('[data-cover-enable]').checked,
      headline:'',scene_index:Number(box.querySelector('[data-cover-scene]').value)}),
      set(v={}){
        box.querySelector('[data-cover-enable]').checked=v.enabled===true;
        box.querySelector('[data-cover-title]').value=v.headline||'';
        const select=box.querySelector('[data-cover-scene]');
        select.querySelectorAll('[data-saved-scene]').forEach(el=>el.remove());
        const index=Number(v.scene_index||0);
        if(index>0){const option=document.createElement('option');option.value=String(index);option.textContent=`ใช้ภาพที่ ${index} ตามค่าที่บันทึกไว้`;option.dataset.savedScene='true';select.append(option);}
        select.value=String(index);
      }};
    panels.set(key,entry);
  }
  mount('product','#product-video-provider');mount('product-batch','#creation-form .cq-buttons');
  mount('story','#story-video-mode');mount('story-batch','#story-batch-video-mode');mount('drama','#drama-video-mode');mount('long','#long-mode');
  const prepare=window.prepareAudioQueue;
  window.prepareAudioQueue=item=>{prepare?.(item);panels.get('product-batch')?.set(item?item.settings?.ai_cover_options||{}:panels.get('product')?.read());};
  const original=postAction;
  postAction=async(action,payload={})=>{
    const key=window.smartflowCreationFormKey?.(action,payload);
    if(key && panels.has(key) && !payload.job_id){
      const options=panels.get(key).read();
      // The hidden legacy headline is not an editable field in this modal.
      // Omission preserves it; an explicit caller-supplied blank still clears it.
      if(action==='creation_edit'){
        delete options.headline;
        if(Object.prototype.hasOwnProperty.call(payload.ai_cover_options||{},'headline'))options.headline=payload.ai_cover_options.headline;
      }
      payload={...payload,ai_cover_options:options};
      if(payload.render_options)payload.render_options={...payload.render_options,ai_cover_options:options};
    }
    return original(action,payload);
  };
})();
