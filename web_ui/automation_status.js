(() => {
  const detail=document.querySelector('#progress-detail');if(!detail)return;
  const view=document.createElement('div');view.id='automation-observation';view.setAttribute('role','status');view.style.cssText='margin:10px 0;font-size:12px;color:#a5ddea;white-space:pre-line';detail.after(view);
  window.renderAutomationObservation=(state,current)=>{
    const rows=(state.automation_observations||[]).filter(r=>r.job_id===current.job_id);
    if(!current.active){view.textContent='';return;}
    if(!rows.length){view.textContent=state.system?.extension_online===false?'Extension ขาดการเชื่อมต่อ • รอเชื่อมต่อกลับ ไม่สั่งสร้างซ้ำ':'';return;}
    // Browser stage is supporting evidence, not a replacement for desktop percent/Final.
    const latest=rows[0],age=Math.max(0,Math.floor(Date.now()/1000-latest.received_at));
    view.textContent=`${latest.provider}${latest.channel==='cover'?' / ปกคลิป':latest.channel==='repair'?' / กำลังแก้ไข':''} • ${latest.message||latest.label}${latest.scene_index?' • ฉาก '+latest.scene_index:''}\nตรวจล่าสุด ${age} วินาทีที่แล้ว${age>30?' • ยังไม่มีรายงานใหม่ ไม่ได้หมายความว่างานล้มเหลว':''}`;
  };
})();
