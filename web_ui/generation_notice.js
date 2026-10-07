/* One reminder per explicit creation/start action, never per automatic scene. */
(() => {
  const original=postAction;
  const starts=new Set(['create_product','create_story','create_long_video','create_drama_series',
    'create_drama_episode','continue_drama_series','creation_start','creation_resume','creation_start_series',
    'start_story_batch','start_story_queue','product_cast_generate','retry_story','product_continue',
    'creation_retry','creation_resume_unfinished','creation_resume_jobs','story_queue_resume',
    'presenter_create','retry_drama_episode']);
  const dialog=document.createElement('dialog');dialog.className='modal';dialog.id='generation-notice';
  dialog.setAttribute('aria-labelledby','generation-notice-title');
  dialog.innerHTML='<div class="modal-card confirm-card"><h2 id="generation-notice-title">ก่อนเริ่มสร้างคลิป</h2>'+
    '<p>แนะนำใช้รูปนายแบบ / นางแบบที่แต่งกายมิดชิด และมุมภาพสุภาพ เพื่อช่วยลดปัญหา AI ไม่รับสร้างวิดีโอ</p>'+
    '<p>งานสินค้าสามารถเลือกชุดให้ AI จัดให้ หรือใช้รูปชุดจากคลังได้ ผลการสร้างขึ้นอยู่กับผู้ให้บริการ</p>'+
    '<div class="modal-actions"><button type="button" class="button ghost" data-notice-cancel>กลับไปปรับ</button>'+
    '<button type="button" class="button primary" data-notice-start>เริ่มสร้าง</button></div></div>';
  document.body.append(dialog);
  let pending=null;
  const finish=value=>{const resolve=pending;pending=null;dialog.close();resolve?.(value);};
  dialog.querySelector('[data-notice-cancel]').onclick=()=>finish(false);
  dialog.querySelector('[data-notice-start]').onclick=()=>finish(true);
  dialog.addEventListener('cancel',event=>{event.preventDefault();finish(false);});
  window.smartflowConfirmGeneration=action=>{
    if(pending)throw Error('กรุณายืนยันรายการที่กำลังเปิดอยู่ก่อน');
    const lines=dialog.querySelectorAll('.modal-card > p');
    if(action==='create_product'||action==='product_continue'){
      lines[0].textContent='ตรวจลิงก์สินค้า จำนวนฉาก และวิธีสร้างวิดีโอก่อนเริ่ม';
      lines[1].textContent='ถ้าใช้นายแบบ / นางแบบ แนะนำรูปที่แต่งกายมิดชิดและมุมภาพสุภาพ ผลการสร้างขึ้นอยู่กับผู้ให้บริการ';
    }else if(action==='create_drama_series'||action==='create_drama_episode'||action==='continue_drama_series'){
      lines[0].textContent='ตรวจชื่อเรื่อง จำนวนตอน ตัวละคร และวิธีสร้างวิดีโอก่อนเริ่ม';
      lines[1].textContent='ระบบจะทำทีละตอนและบันทึกความคืบหน้าไว้สำหรับทำต่อ';
    }else{
      lines[0].textContent='ตรวจหัวข้อ จำนวนฉาก เสียง และวิธีสร้างวิดีโอก่อนเริ่ม';
      lines[1].textContent='ระบบจะบันทึกความคืบหน้าไว้ หากงานสะดุดสามารถกลับมาดูและทำต่อได้';
    }
    return new Promise(resolve=>{pending=resolve;dialog.showModal();});
  };
  postAction=async(action,payload={})=>{
    if(starts.has(action)&&!payload.queue_only){
      const accepted=await window.smartflowConfirmGeneration(action);
      if(!accepted)throw Error('ยังไม่ได้เริ่มงาน • ปรับตัวเลือกแล้วเริ่มได้อีกครั้ง');
    }
    return original(action,payload);
  };
})();
