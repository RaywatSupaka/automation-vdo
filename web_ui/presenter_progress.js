/* Presenter status uses the existing app dialog. Rendering is read-only. */
function presenterProgressModel(p) {
  const clips=Math.max(0,Math.min(3,Number(p.clips)||0));
  const ready=p.status==='ready',review=['image_review','clip_review'].includes(p.status);
  const completed=ready?6:(p.image_ready?2:0)+clips;
  return {clips,ready,review,completed,percent:Math.floor(completed/6*100),
    waiting:Boolean(p.active&&!ready&&!review),
    token:[p.job_id,p.run_id,p.status,p.stage].join(':'),
    steps:['เตรียมงาน / สร้างภาพ','ภาพพื้นสีพร้อม','คลิป 1 บันทึกแล้ว','คลิป 2 บันทึกแล้ว','คลิป 3 บันทึกแล้ว','รวมคลิปพร้อมใช้']};
}
(() => {
  let dismissed='',lastRun='';
  const copy=document.createElement('button');copy.id='progress-copy-log';copy.type='button';
  copy.className='button secondary hidden';copy.textContent='คัดลอก Log';
  document.querySelector('#progress-modal .modal-actions').append(copy);
  copy.onclick=async()=>{try{const p=ui.state?.presenter_progress||{};
    await navigator.clipboard.writeText(JSON.stringify({service:'SmartFlow Presenter',...p,
      logs:(ui.state?.logs||[]).filter(line=>String(line).includes(p.job_id)).slice(-30)},null,2));toast('คัดลอกสถานะและ Log แล้ว');
  }catch(e){toast(e.message,'error');}};
  window.dismissPresenterProgress=()=>{const p=ui.state?.presenter_progress;if(p?.job_id)dismissed=presenterProgressModel(p).token;};
  window.renderPresenterProgress=state=>{
    const p=state.presenter_progress||{};
    if(state.product_progress?.active||state.story_progress?.active||!p.job_id)return false;
    const m=presenterProgressModel(p),run=p.job_id+':'+p.run_id;
    if(m.ready&&!p.active){
      dismissed=m.token;
      // A historical ready presenter must not take over or close a clip's UI.
      if(ui.progressType==='presenter'&&ui.progressJobId===p.job_id){
        ui.progressWasActive=false;
        dismissProgressResult();
        $('#progress-modal').classList.remove('presenter-running');
      }
      return false;
    }
    if(dismissed===m.token&&!p.active)return false;
    if(run!==lastRun){lastRun=run;ui.progressMinimized=false;dismissed='';}
    clearTimeout(ui.progressCloseTimer);ui.progressCloseTimer=null;
    ui.progressType='presenter';ui.progressJobId=p.job_id;
    ui.progressWasActive=Boolean(p.active);ui.progressResultReady=!p.active;
    const modal=$('#progress-modal');modal.classList.toggle('presenter-running',m.waiting);
    $('#progress-kicker').textContent='SMARTFLOW • PRESENTER';
    $('#progress-title').textContent=m.ready?'ตัวละครพร้อมใช้':m.review?'รอตรวจตัวละคร':p.active?'กำลังสร้างตัวละครผู้บรรยาย':'งานตัวละครหยุดแล้ว';
    $('#progress-job').textContent=(p.name||'')+' • '+p.job_id;
    $('#progress-percent').textContent=m.ready?'พร้อมใช้':m.clips+'/3 คลิป';
    $('#progress-percent').setAttribute('aria-valuenow',String(m.percent));
    $('#progress-bar').style.width=m.percent+'%';
    $('#progress-message').textContent=p.message||p.stage||'กำลังเตรียมงาน';
    const age=p.updated_at?Math.max(0,Math.floor(Date.now()/1000-p.updated_at)):0;
    $('#progress-detail').textContent='เวลา '+Math.floor((p.elapsed||0)/60)+' นาที '+((p.elapsed||0)%60)+' วินาที • สถานะล่าสุด '+age+' วินาทีก่อน • นับเฉพาะภาพ/คลิปที่บันทึกแล้ว';
    $('#progress-steps').replaceChildren(...m.steps.map((label,i)=>{const el=document.createElement('span');el.className='progress-step '+(i<m.completed?'done':i===m.completed?'current':'');el.textContent=(i<m.completed?'✓ ':'')+label;return el;}));
    $('#progress-cancel').classList.toggle('hidden',!p.active);
    $('#progress-cancel').disabled=p.stage==='cancelling';
    $('#progress-cancel').textContent=p.stage==='cancelling'?'กำลังยกเลิก...':'ยกเลิกการทำงาน';
    $('#progress-result').classList.toggle('hidden',Boolean(p.active));
    $('#progress-result').textContent=m.review?'เปิดตรวจภาพ / คลิป':m.ready?'เปิดตัวละครที่เสร็จแล้ว':'ดูงานและจุดที่หยุด';
    $('#progress-focus').classList.toggle('hidden',p.stage!=='user_action_required');
    $('#progress-focus').textContent='เปิด Chrome เพื่อเข้าสู่ระบบ / ตรวจสอบ';
    copy.classList.remove('hidden');
    window.SmartFlowUX?.renderProgress(state, {...p,type:'presenter'});
    $('#progress-minimized').textContent=(p.active?'● ':'')+m.clips+'/3 คลิป • '+(p.message||'ตัวละครผู้บรรยาย');
    $('#progress-minimized').classList.toggle('hidden',!ui.progressMinimized);
    if(ui.progressMinimized){if(modal.open)modal.close();}else if(!modal.open)modal.showModal();
    return true;
  };
})();
