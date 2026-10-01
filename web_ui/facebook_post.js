(() => {
  pageMeta.facebook=['FACEBOOK PAGE','Auto Post เพจ Facebook'];
  const page=document.createElement('section');page.className='page';page.dataset.view='facebook';
  page.innerHTML=`<section class="page-intro"><span class="eyebrow">FACEBOOK PAGE</span><h1>Auto Post เพจ Facebook</h1><p>เลือกคลิปที่ทำเสร็จแล้ว แล้วกดโพสต์ไปยังเพจ • ไม่โพสต์เองระหว่างสร้างคลิป</p></section>
  <section class="panel" style="padding:24px;max-width:850px"><h2>1. เชื่อมต่อเพจ</h2>
  <p id="fb-page">ยังไม่ได้เชื่อมต่อ</p><label>Page Access Token<input id="fb-token" type="password" autocomplete="new-password" placeholder="วาง Token ของเพจ" style="width:100%"></label>
  <p><button class="button primary" id="fb-connect">ตรวจสอบและบันทึก</button> <button class="button ghost" id="fb-disconnect">ยกเลิกการเชื่อมต่อ</button></p>
  <small>เก็บ Token ใน Windows Credential Manager ไม่แสดงในประวัติและไม่ส่งให้ Extension</small>
  <h2>2. เลือกคลิปที่ทำเสร็จ</h2><select id="fb-video" style="width:100%"><option value="">เลือกคลิปจากคลัง</option></select>
  <p><button class="button ghost" id="fb-refresh">รีเฟรชคลังและสถานะ</button></p>
  <label>ข้อความโพสต์<textarea id="fb-caption" rows="6" maxlength="5000" style="width:100%"></textarea></label>
  <p><button class="button primary" id="fb-publish">โพสต์คลิปนี้ไปยังเพจ</button></p>
  <p id="fb-status" role="status"></p><small>โพสต์วิดีโอไปยังเพจทันทีเมื่อกด • ยังไม่ใช่โหมดตั้งเวลาหรือ Reels โดยเฉพาะ</small>
  <h2>ประวัติการโพสต์</h2><div id="fb-history"></div></section>`;
  document.querySelector('[data-view="settings"]').after(page);
  const q=s=>page.querySelector(s),notice=t=>q('#fb-status').textContent=t;
  let saved={},busy=false;
  async function call(action,payload={}) {
    const r=await fetch('/api/desktop/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,payload})});
    const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'ทำรายการไม่ได้');return d;
  }
  async function refresh(){
    saved=await call('facebook_status');q('#fb-page').textContent=saved.page?`เพจ: ${saved.page.name} (${saved.page.id})`:'ยังไม่ได้เชื่อมต่อ';
    const chosen=q('#fb-video').value;
    q('#fb-video').innerHTML='<option value="">เลือกคลิปจากคลัง</option>';
    for(const row of ui.state?.library||[]){const o=document.createElement('option');o.value=row.item_id;o.textContent=row.title;q('#fb-video').append(o);}
    q('#fb-video').value=chosen;q('#fb-history').replaceChildren();
    const labels={uploading:'กำลังอัปโหลด',processing:'รอ Facebook ประมวลผล',published:'เผยแพร่แล้ว',review:'ต้องตรวจผลเดิมก่อน'};
    for(const row of saved.posts||[]){
      const el=document.createElement('p');el.textContent=`${row.title} → ${row.page_name}: ${labels[row.status]||row.status} `;
      if(row.video_id){const b=document.createElement('button');b.className='button ghost';b.textContent='ตรวจผล';b.onclick=()=>run(async()=>{await call('facebook_check',{id:row.id});await refresh();});el.append(b);}
      if(/^https:\/\/(www\.)?facebook\.com\//.test(row.url||'')){const a=document.createElement('a');a.href=row.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=' เปิดโพสต์';el.append(a);}
      if(row.message){const s=document.createElement('small');s.textContent=' '+row.message;el.append(s);}q('#fb-history').append(el);
    }
  }
  async function run(fn){if(busy)return;busy=true;page.querySelectorAll('button').forEach(b=>b.disabled=true);try{await fn();}catch(e){notice(e.message);}finally{busy=false;page.querySelectorAll('button').forEach(b=>b.disabled=false);}}
  q('#fb-connect').onclick=()=>run(async()=>{const token=q('#fb-token').value;q('#fb-token').value='';notice('กำลังตรวจสอบเพจ…');await call('facebook_connect',{token});await refresh();notice('บันทึกเพจแล้ว');});
  q('#fb-disconnect').onclick=()=>run(async()=>{await call('facebook_disconnect');await refresh();notice('ยกเลิกการเชื่อมต่อแล้ว');});
  q('#fb-refresh').onclick=()=>run(refresh);
  q('#fb-video').onchange=()=>run(async()=>{if(!q('#fb-video').value)return;const d=await call('get_library_detail',{item_id:q('#fb-video').value});q('#fb-caption').value=(d.detail||d.item||d).post_text||'';});
  q('#fb-publish').onclick=()=>run(async()=>{
    if(!saved.page||!q('#fb-video').value)throw Error('เชื่อมต่อเพจและเลือกคลิปก่อน');
    if(!confirm(`โพสต์คลิปที่เลือกไปยังเพจ ${saved.page.name} ตอนนี้?`))return;
    const d=await call('facebook_publish',{page_id:saved.page.id,item_id:q('#fb-video').value,caption:q('#fb-caption').value});
    notice(d.duplicate?'รายการนี้เคยส่งแล้ว กรุณาตรวจประวัติ ไม่ส่งซ้ำ':'รับรายการแล้ว ดูผลในประวัติ');await refresh();
  });
  document.querySelector('[data-page="facebook"]').addEventListener('click',()=>run(refresh));
  if(location.hash==='#facebook'){showPage('facebook');run(refresh);}
})();
