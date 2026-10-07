/* Read-only recovery guidance. No replay or provider-send path lives here. */
(() => {
  const modal=document.getElementById('automation-error-modal');
  if(!modal)return;
  const body=document.getElementById('recovery-wizard-body');
  const back=document.getElementById('recovery-back');
  const next=document.getElementById('recovery-next');
  let report={},step=0;
  const cases=[
    {match:/SEND_UNCERTAIN|SEND_UNCONFIRMED|AI_WEB_RESUME_REVIEW|REQUEST_NOT_LATEST|PRIOR_RUN_UNCONFIRMED/i,
      title:'ส่งคำขอแล้ว แต่ยังไม่รู้ผล',what:'ระบบยังยืนยันผลจากผู้ให้บริการไม่ได้ จึงพักงานไว้เพื่อป้องกันภาพซ้ำ',fix:'เปิดแท็บเดิมแล้วตรวจว่ามีภาพตอบกลับหรือไม่ ห้ามส่งคำขอเดิมซ้ำเอง',resume:'เก็บงานและคำขอเดิมไว้แล้ว การส่งใหม่ต้องผ่านกลไกที่เจ้าของอนุญาตหลังตรวจหลักฐาน ไม่พบปุ่มที่ผูกกลไกนั้นกับหน้านี้ จึงไม่มีปุ่มส่งใหม่',web:'open-chatgpt'},
    {match:/AI_WEB_WAIT_REVIEW|draft_present|composer_not_ready|conversation_present/i,
      title:'มีข้อความหรือแท็บที่ต้องตรวจ',what:'โปรแกรมพบข้อความหรือสถานะใน Chrome ที่ยังระบุเจ้าของไม่ได้',fix:'เปิดแท็บเดิมและตรวจข้อความก่อน อย่าลบข้อความที่ไม่ใช่ของงานนี้',resume:'เมื่อแน่ใจแล้ว กลับไปที่งานเดิมเพื่อใช้การกู้คืนที่ระบบอนุญาต',web:'open-chatgpt'},
    {match:/STORY_IMAGE_REFUSED|IMAGE_REFUSED/i,
      title:'ผู้ให้บริการไม่รับสร้างภาพ',what:'คำขอภาพฉากนี้ไม่ผ่านการพิจารณาของผู้ให้บริการ',fix:'กลับไปแก้คำขอของฉากนั้นก่อน ไม่ส่งคำขอเดิมซ้ำ',resume:'ใช้หน้าตรวจงานเดิมเพื่อส่งคำขอที่แก้ไขแล้วเท่านั้น',web:'open-chatgpt'},
    {match:/FLOW_CREDIT|CREDIT_EXHAUSTED/i,
      title:'เครดิต Google Flow ไม่พอ',what:'งานวิดีโอหยุดเพราะบัญชีที่ใช้อยู่ไม่มีเครดิตพอ',fix:'เปลี่ยนบัญชี Google ที่มีเครดิตใน Chrome แล้วทำต่อด้วย Google Flow',resume:'กลับไปงานเดิมเพื่อทำต่อด้วย Google Flow เท่านั้น',web:'open-flow'},
    {match:/FLOW_TERMS|FLOW_CONSENT|FLOW.*ACCEPT/i,
      title:'Google Flow รอให้คุณยอมรับ',what:'มีขั้นตอนใน Google Flow ที่ต้องให้เจ้าของบัญชีดำเนินการ',fix:'เปิดแท็บ Google Flow อ่านและกดยอมรับด้วยตนเอง',resume:'เมื่อดำเนินการแล้ว กลับไปงานเดิมเพื่อทำต่อ',web:'open-flow'},
    {match:/EXTENSION_UPDATE|EXTENSION_VERSION|INCOMPATIBLE/i,
      title:'ต้องอัปเดตส่วนเสริม Chrome',what:'รุ่นส่วนเสริมที่เชื่อมอยู่ไม่ตรงกับโปรแกรม',fix:'เปิดหน้าตั้งค่าส่วนเสริมและอัปเดตตัวเดิมตามคู่มือ',resume:'เมื่อตรวจว่ารุ่นตรงกันแล้ว กลับไปเริ่มคิวเดิม',web:'extension'},
    {match:/LOGIN_REQUIRED|CAPTCHA|NOT_LOGGED_IN/i,
      title:'ต้องเข้าสู่ระบบใน Chrome',what:'งานรอให้คุณเข้าสู่ระบบหรือยืนยันว่าไม่ใช่บอท',fix:'เปิดเว็บไซต์ใน Chrome ที่ติดตั้งส่วนเสริม แล้วเข้าสู่ระบบด้วยบัญชีเดิม',resume:'เมื่อทำแล้ว กลับไปงานเดิมเพื่อทำต่อ',web:'open-chatgpt'},
  ];
  function scenario(){const value=`${report.message||''} ${report.text||''}`;return cases.find(item=>item.match.test(value))||{title:'งานนี้ต้องตรวจสอบ',what:'โปรแกรมหยุดงานไว้เมื่อพบสถานะที่ต้องตรวจ',fix:'เปิดงานเดิมและตรวจขั้นตอนที่ค้างอยู่',resume:'เก็บข้อมูลเดิมไว้แล้ว กลับไปงานเดิมหลังตรวจสอบ'};}
  function render(){
    const item=scenario();
    const headings=['เกิดอะไรขึ้น','ต้องทำอะไร','ทำต่อ'];
    const text=[item.what,item.fix,item.resume][step];
    body.innerHTML=`<div class="recovery-step"><span>ขั้น ${step+1} จาก 3 · ${headings[step]}</span><h3>${item.title}</h3><p>${text}</p>${step===1&&item.web?`<button type="button" class="button secondary" id="recovery-open-web">${item.web==='extension'?'เปิดหน้าจัดการส่วนเสริม':'เปิดเว็บไซต์ใน Chrome'}</button>`:''}</div>`;
    back.disabled=step===0;next.textContent=step===2?'กลับไปขั้นแรก':'ถัดไป';
  }
  window.renderRecoveryWizard=value=>{report=value||{};step=0;render();};
  window.openRecoveryWizardForRow=row=>{
    report={message:String(row.error||''),text:String(row.error||'')};step=0;render();
    document.getElementById('automation-error-log').textContent=String(row.error||'');
    document.getElementById('automation-error-title').textContent='งานหยุดไว้และรอให้ตรวจสอบ';
    document.getElementById('automation-error-message').textContent='ดูสิ่งที่ต้องทำในแต่ละขั้น แล้วกลับไปที่งานเดิม';
    if(!modal.open)modal.showModal();
  };
  back.addEventListener('click',()=>{step=Math.max(0,step-1);render();});
  next.addEventListener('click',()=>{step=(step+1)%3;render();});
  body.addEventListener('click',event=>{
    if(!event.target.closest('#recovery-open-web'))return;
    const web=scenario().web;
    if(web==='extension')document.getElementById('install-extension')?.click();
    else document.querySelector(`.web-login-grid [data-action="${web}"]`)?.click();
  });
  render();
})();
