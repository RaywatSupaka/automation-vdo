/* Guided presentation of existing readiness and setup actions. */
(() => {
  const root=document.getElementById('setup-wizard');
  if(!root)return;
  const body=root.querySelector('#setup-wizard-body');
  const dashboard=document.querySelector('[data-view="dashboard"]');
  const banner=document.createElement('div');banner.className='panel setup-progress-banner';banner.id='dashboard-setup-progress';
  if(dashboard)dashboard.querySelector('.hero')?.after(banner);
  const names=['ยินดีต้อนรับ','ส่วนเสริม Chrome','เข้าสู่ระบบเว็บ','เสียงพากย์ AI','คำบรรยาย','มือถือ (ไม่บังคับ)','พร้อมเริ่ม'];
  let step=0,confirmedWeb=false,current={};
  const ready=sys=>[sys.extension_compatible,sys.voice_configured,sys.voice_reference_configured,sys.subtitle_connected].filter(Boolean).length;
  function render(state){
    current=state||current;
    const sys=current.system||{};
    const count=ready(sys);
    root.querySelector('#setup-progress').textContent=`ขั้น ${step+1} จาก 7 · ${names[step]} · ตั้งค่าครบ ${count} จาก 4 ข้อ`;
    banner.hidden=count===4;
    banner.innerHTML=`<span>ตั้งค่าครบ ${count} จาก 4 ข้อ</span><button type="button" class="button secondary" data-page="guide">ตั้งค่าต่อ</button>`;
    const pieces=[
      '<h3>ยินดีต้อนรับสู่ SmartFlow AI</h3><p>ทำตามขั้นตอนที่จำเป็นก่อนเริ่มงาน แล้วกลับมาแก้ภายหลังได้</p>',
      `<h3>ติดตั้งส่วนเสริม SmartFlow ใน Chrome</h3><p>${sys.extension_compatible?'ส่วนเสริมเชื่อมต่อและรุ่นตรงกัน':'ยังไม่ยืนยันว่ารุ่นส่วนเสริมตรงกัน'}</p><button type="button" class="button secondary" id="setup-extension">เปิดหน้าจัดการส่วนเสริม</button>`,
      `<h3>เข้าสู่ระบบเว็บที่ใช้สร้างงาน</h3><p>ระบบยังไม่มีข้อมูลยืนยันว่าเข้าสู่ระบบเว็บแล้ว โปรดเปิดเว็บไซต์ใน Chrome ตัวที่ติดตั้งส่วนเสริมไว้</p><div class="setup-web-actions"><button type="button" class="button secondary" data-setup-web="open-chatgpt">เปิด ChatGPT</button><button type="button" class="button secondary" data-setup-web="open-gemini">เปิด Gemini</button><button type="button" class="button secondary" data-setup-web="open-flow">เปิด Google Flow</button></div><button type="button" class="button ghost" id="setup-confirm-web">${confirmedWeb?'คุณยืนยันขั้นนี้แล้ว · ระบบไม่ได้ตรวจการเข้าสู่ระบบ':'ฉันเข้าสู่ระบบแล้ว'}</button>`,
      `<h3>ตั้งค่าเสียงพากย์ AI</h3><p>${sys.voice_configured&&sys.voice_reference_configured?'คีย์และเสียงต้นแบบพร้อม':'ตั้งค่าคีย์และเสียงต้นแบบก่อนใช้งานเสียงพากย์ AI'}</p><button type="button" class="button secondary" data-page="voice">เปิดตั้งค่าเสียง</button>`,
      `<h3>เชื่อมต่อคำบรรยายอัตโนมัติ</h3><p>${sys.subtitle_connected?'เชื่อมต่อบริการคำบรรยายแล้ว':'ยังไม่ยืนยันการเชื่อมต่อบริการคำบรรยาย'}</p><button type="button" class="button secondary" data-page="subtitle">เปิดตั้งค่าคำบรรยาย</button>`,
      '<h3>จับคู่มือถือสำหรับโพสต์ Shopee</h3><p>ขั้นนี้ไม่บังคับสำหรับการสร้างคลิป สามารถตั้งค่าผ่านหน้าจับคู่ Android Wi-Fi ภายหลัง</p><button type="button" class="button secondary" id="setup-mobile">เปิดหน้าจับคู่มือถือ</button>',
      `<h3>พร้อมเริ่มงาน</h3><p>ตั้งค่าทางเทคนิคครบ ${count} จาก 4 ข้อ${count===4?'':' · กลับไปทำข้อที่ยังไม่พร้อมได้'}</p><p>ก่อนเริ่ม ให้ตรวจว่าเข้าสู่ระบบเว็บที่ใช้ใน Chrome ตัวเดิมแล้ว</p><button type="button" class="button primary" data-page="creation">ไปหน้างานของฉัน</button>`,
    ];
    body.innerHTML=pieces[step];
    root.querySelector('#setup-back').disabled=step===0;
    root.querySelector('#setup-next').textContent=step===names.length-1?'กลับไปขั้นแรก':'ถัดไป';
  }
  root.querySelector('#setup-back').addEventListener('click',()=>{step=Math.max(0,step-1);render();});
  root.querySelector('#setup-next').addEventListener('click',()=>{step=(step+1)%names.length;render();});
  body.addEventListener('click',event=>{
    if(event.target.closest('#setup-extension'))document.getElementById('install-extension')?.click();
    if(event.target.closest('#setup-confirm-web')){confirmedWeb=true;render();}
    const web=event.target.closest('[data-setup-web]');
    if(web)document.querySelector(`.web-login-grid [data-action="${web.dataset.setupWeb}"]`)?.click();
    if(event.target.closest('#setup-mobile')){showPage('queue');document.getElementById('android-wifi')?.scrollIntoView({block:'start'});}
  });
  window.renderSetupWizard=render;
  render(window.ui?.state||{});
})();
