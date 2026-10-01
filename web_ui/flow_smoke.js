/* Dedicated navigation reuses the same mounted Shorts controls and handlers. */
(() => {
  const story=document.querySelector('[data-view="story"]');if(!story)return;
  const test=document.createElement('section');test.className='page';test.dataset.view='flowtest';story.after(test);
  for(const link of document.querySelectorAll('[data-page="longvideo"]')){
    link.dataset.page='flowtest';link.querySelector('strong').textContent='ทดสอบ AI → Flow';
    link.querySelector('small').textContent='1 ภาพ • 1 วิดีโอ • จบครบทุกขั้นตอน';
  }
  const note=document.createElement('p');note.className='usability-note';
  note.textContent='ทดสอบครบขั้นตอน: กรอกหัวข้อและคำอธิบาย เลือก ChatGPT หรือ Gemini → สร้าง 1 ภาพ → Google Flow 1 วิดีโอ → ประกอบพร้อมเสียง ซับ และตัวเลือกที่คุณเปิดไว้ • ใช้เครดิตบริการจริง';
  const button=document.querySelector('#create-story');
  const heading=story.querySelector('h1'),headingText=heading?.textContent;
  let active=false,saved=null;
  window.prepareFlowTestPage=page=>{
    const next=page==='flowtest';if(next===active)return;
    const scenes=document.querySelector('#story-scenes'),mode=document.querySelector('#story-video-mode');
    if(next){
      saved={scenes:scenes.value,min:scenes.min,mode:mode.value,html:button.innerHTML};
      while(story.firstChild)test.append(story.firstChild);
      test.prepend(note);scenes.min='1';scenes.value='1';scenes.disabled=true;mode.value='google_flow';mode.disabled=true;
      button.innerHTML='เริ่มทดสอบครบทุกขั้นตอน';
      if(heading)heading.textContent='ทดสอบ AI Web → Google Flow จนจบคลิป';
    }else{
      note.remove();while(test.firstChild)story.append(test.firstChild);
      scenes.min=saved.min;scenes.value=saved.scenes;scenes.disabled=false;mode.value=saved.mode;mode.disabled=false;button.innerHTML=saved.html;
      if(heading)heading.textContent=headingText;
    }
    active=next;mode.dispatchEvent(new Event('change'));scenes.dispatchEvent(new Event('input'));
    const sceneLabel=document.getElementById('story-scene-label');if(sceneLabel)sceneLabel.textContent=scenes.value+' ฉาก';
    for(const id of ['open-story-batch','enqueue-story']){const n=document.getElementById(id);if(n)n.hidden=next;}
  };
  window.routeFlowTest=(action,payload)=>{
    if(!active||action!=='create_story'||payload.job_id)return {action,payload};
    return {action:'create_flow_smoke_test',payload:{...payload,queue_only:!!document.querySelector('#story-queue-only')?.checked}};
  };
  if(typeof ui!=='undefined'&&ui.activePage==='flowtest'){window.prepareFlowTestPage('flowtest');test.classList.add('active');}
})();
