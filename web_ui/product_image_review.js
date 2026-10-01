/* On-demand review: no heartbeat image decoding or automatic generation. */
(() => {
  const parent = document.querySelector('#product-detail-modal .form-footer');
  if (!parent) return;
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'button secondary';
  button.textContent = 'ตรวจภาพ / ภาพสำรอง'; button.id = 'product-image-review-open';
  parent.prepend(button);
  const dialog = document.createElement('dialog'); dialog.className = 'modal';
  dialog.id = 'product-image-review-modal';
  const card = document.createElement('div'); card.className = 'modal-card';
  card.style.cssText = 'max-width:900px;max-height:85vh;overflow:auto';
  dialog.append(card); document.body.append(dialog);
  const names = {accept:'ใช้เป็นภาพอ้างอิง', exclude:'ไม่นำไปใช้', review:'รอตรวจสอบ',
    confirmed_shopee_promotion_overlay:'แถบโปรโมชัน Shopee ที่ยืนยันแล้ว', duplicate_product_image:'รูปซ้ำ',
    sparse_edge_image_needs_review:'ภาพโปร่งใส/กราฟิกแถบขอบ ต้องตรวจ', product_reference:'ภาพสินค้า',
    saved_ai_image:'ภาพ AI ที่บันทึกแล้ว', succeeded:'บันทึกแล้ว', failed:'สร้างไม่สำเร็จ',
    missing:'ยังไม่มีภาพ', policy_blocked:'ถูกปฏิเสธตามนโยบาย', uncertain:'ยังไม่ทราบผล ห้ามส่งซ้ำ',
    reserved:'มีคำขอค้าง', download_pending:'รอดาวน์โหลดภาพเดิม', blocked:'ต้องตรวจสอบ', fallback:'ใช้ภาพเดิม'};
  let data;
  const label = (text, tag='p') => { const node=document.createElement(tag); node.textContent=text; return node; };
  function render(review) {
    data=review; card.replaceChildren();
    const close=label('ปิด','button'); close.className='button ghost'; close.onclick=()=>dialog.close(); card.append(close);
    const copy=label('คัดลอก Log ภาพ','button'); copy.className='button secondary';
    copy.onclick=()=>copyText('SmartFlow AI • Product Image Review\n'+JSON.stringify({job_id:review.job_id,revision:review.revision,
      slots:review.slots,images:review.images.map(({path,decision,reason})=>({path,decision,reason}))},null,2));
    card.append(copy);
    card.append(label('ตรวจภาพสินค้าและการกู้ภาพ','h2'));
    card.append(label('ภาพที่ไม่นำไปใช้ยังเก็บต้นฉบับไว้ ไม่มีการลบหรือสร้างภาพใหม่จากหน้านี้'));
    for(const slot of review.slots) card.append(label(`ภาพ ${slot.index}: ${names[slot.status]||slot.status} • ใช้สิทธิ์ ${slot.attempts||0}/2${slot.donor_index?' • อ้างอิงภาพ '+slot.donor_index:''}`));
    const grid=document.createElement('div'); grid.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px';
    for(const item of review.images){
      const tile=document.createElement('div'); const img=document.createElement('img');
      img.src=item.preview_url; img.alt=item.path; img.loading='lazy'; img.style.cssText='width:100%;height:150px;object-fit:contain;background:#192237';
      tile.append(img,label(`${names[item.decision]||item.decision} • ${names[item.reason]||item.reason}`)); grid.append(tile);
    }
    card.append(grid);
    if(review.can_reuse){
      card.append(label('ใช้ภาพเดิมประกอบคลิปเฉพาะช่องที่ขาด (Local Motion ไม่ใช่ภาพ AI หรือคลิป Flow ใหม่)','h3'));
      const select=document.createElement('select'); select.className='input';
      for(const item of review.images.filter(i=>i.decision==='accept')){const option=document.createElement('option');option.value=item.path;option.textContent=item.path;select.append(option);}
      const consent=document.createElement('input'); consent.type='checkbox';
      const consentLabel=label(' ฉันตรวจว่าภาพตรงกับสินค้าและบทพูด มีสิทธิ์ใช้ และยอมรับใช้ภาพนี้แทนช่องที่ขาด','label'); consentLabel.prepend(consent);
      const save=label('ยืนยันใช้ภาพเดิม','button'); save.className='button primary'; save.disabled=true;
      consent.onchange=()=>{save.disabled=!consent.checked||!select.value;};
      save.onclick=async()=>{save.disabled=true;try{const result=await postAction('product_image_reuse',{job_id:data.job_id,revision:data.revision,path:select.value,confirmed:consent.checked});render(result.review);toast('บันทึกภาพสำรองแล้ว กดทำต่อที่งานเดิมเพื่อประกอบคลิป','success');await poll();}catch(e){toast(e.message,'error');save.disabled=false;}};
      card.append(select,consentLabel,save);
    }
  }
  button.onclick=async()=>{button.disabled=true;try{const result=await postAction('product_image_review',{job_id:document.querySelector('#product-detail-id').value});render(result.review);dialog.showModal();}catch(e){toast(e.message,'error');}finally{button.disabled=false;}};
})();
