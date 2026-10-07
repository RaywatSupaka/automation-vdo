/* Presentation only: no job commands, provider requests, timers or persisted state.
   Original local SVG artwork. Controllers remain owners of progress and actions. */
(() => {
  'use strict';
  const shapes = {
    home:'<path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/>',
    bag:'<rect x="4" y="7" width="16" height="14" rx="3"/><path d="M8 8V6a4 4 0 0 1 8 0v2"/>',
    story:'<rect x="6" y="2" width="12" height="20" rx="3"/><path d="m10 8 5 4-5 4Z"/>',
    video:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m10 8 5 4-5 4ZM3 7h3m12 0h3M3 17h3m12 0h3"/>',
    clapper:'<path d="m3 8 17-5 2 6-17 5ZM5 14v7h17V9M6 7l4 5m3-7 4 5"/>',
    queue:'<rect x="3" y="4" width="5" height="5" rx="1"/><path d="M12 6h9M12 13h9M12 20h9M4 13h3m-3 7h3"/>',
    library:'<rect x="3" y="7" width="18" height="14" rx="3"/><path d="M7 3h10m-7 8 5 3-5 3Z"/>',
    users:'<circle cx="9" cy="7" r="3"/><path d="M3 20v-3a6 6 0 0 1 12 0v3M17 4a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5v2"/>',
    sparkle:'<path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6ZM20 2v4m-2-2h4"/>',
    settings:'<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="8" cy="18" r="2"/>',
    send:'<path d="m3 3 19 9-19 9 4-9Zm4 9h15"/>',
    facebook:'<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M14 7h-1a3 3 0 0 0-3 3v11m-3-9h9"/>',
    terminal:'<rect x="2" y="4" width="20" height="16" rx="3"/><path d="m6 9 3 3-3 3m7 0h5"/>',
    voice:'<path d="M3 10v4m4-7v10m5-14v18m5-16v14m4-9v4"/>',
    image:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="9" cy="8" r="2"/><path d="m3 17 5-4 4 3 5-7 4 5"/>',
    analysis:'<path d="m5 15 11-11 4 4L9 19l-6 2Zm8-8 4 4"/>',
    render:'<path d="m12 3 9 5-9 5-9-5Zm-9 9 9 5 9-5m-18 5 9 5 9-5"/>',
    attention:'<path d="m12 3 10 18H2Zm0 5v6m0 3v1"/>',
    offline:'<path d="M2 7a16 16 0 0 1 20 0M5 11a11 11 0 0 1 14 0m-11 4a6 6 0 0 1 8 0m-4 4v1"/>',
    paused:'<path d="M8 5v14M16 5v14"/>',
    complete:'<path d="m5 12 5 5L20 7"/>',
    text:'<path d="M4 7V5h16v2M12 5v14M9 19h6"/>',
    music:'<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
    badge:'<rect x="3" y="3" width="18" height="18" rx="4"/><path d="m8 15 4-8 4 8m-6-3h4"/>',
    help:'<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.7M12 17h.01"/>',
  };
  const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${shapes[name] || shapes.sparkle}</svg>`;
  const routes = {dashboard:'home',products:'bag',story:'story',drama:'clapper',presenter:'users',longvideo:'video',creation:'queue',library:'library','product-cast':'users',intro:'sparkle',green:'render','presenter-settings':'users',settings:'settings',facebook:'facebook',queue:'send',logs:'terminal',voice:'voice',subtitle:'text',audio:'music',logo:'badge',guide:'help','ai-chat':'sparkle'};
  const $ = selector => document.querySelector(selector);
  document.querySelectorAll('.navigation .nav-item').forEach(button => {
    const el=button.querySelector('i');
    if(el && routes[button.dataset.page]) { el.innerHTML=icon(routes[button.dataset.page]); el.setAttribute('aria-hidden','true'); }
  });

  // Never infer completion from percent or another job's browser observations.
  function deriveProgressVisualState(current={}, observation={}) {
    const stage=String(current.stage||''), status=String(current.status||'');
    if(stage==='cancelling'||status==='pausing'||/กำลังหยุด|กำลังยกเลิก/.test(current.message||''))return 'cancelling';
    if(current.action_required||stage==='user_action_required'||current.waiting_for_device)return 'attention';
    if(/review/.test(status)||status==='interrupted')return 'review';
    if(['error','failed'].includes(status)||['error','failed'].includes(stage))return 'error';
    if(current.active===false)return 'paused';
    if(status==='paused'||status==='ready')return 'paused';
    const phase=current.pipeline_phase || (stage==='scene'?current.scene_phase:stage);
    const map={script:'analysis',planning:'analysis',analysis:'analysis',chatgpt:'analysis',image:'image',images:'image',repair:'image',source_video:'video',google_flow:'video',requested:'video',voice:'voice',compose:'render',finish:'render',finishing:'render',cover:'image',render:'render'};
    // Desktop stage video = local composition; scene/Presenter video = provider video.
    let visual=phase==='video'?(stage==='scene'||current.type==='presenter'?'video':'render'):(map[phase]||'neutral');
    if(observation.job_id===current.job_id && observation.offline===true && ['analysis','image','video'].includes(visual))visual='offline';
    return visual;
  }
  const staticStates=new Set(['attention','offline','paused','cancelling','error','review','complete','neutral']);
  function drawMotion(host,visual) {
    if(!host || host.dataset.visual===visual)return;
    host.dataset.visual=visual;
    host.classList.toggle('sf-motion-static',staticStates.has(visual));
    const art=['error','review','cancelling'].includes(visual)?'attention':visual;
    // This markup is decorative and consists only of fixed local strings.
    host.innerHTML=`<span class="sf-orbit"></span><span class="sf-frame sf-frame-back"></span><span class="sf-frame sf-frame-front">${icon(art)}<i class="sf-scan"></i></span><span class="sf-spark sf-spark-one"></span><span class="sf-spark sf-spark-two"></span>`;
  }
  function renderProgress(state,current) {
    const modal=$('#progress-modal'); if(!modal)return;
    const visual=deriveProgressVisualState(current,{job_id:current.job_id,offline:state.system?.extension_online===false});
    modal.dataset.visual=visual;
    drawMotion($('#progress-motion'),visual);
    // Detailed diagnostics remain available without dominating the primary status.
    const details=modal.querySelector('.sf-progress-details');
    const observation=$('#automation-observation');
    if(details && observation && observation.parentElement!==details)details.append(observation);
    if(current.type==='presenter' && observation)observation.textContent='';
  }
  function renderPosting(run) {
    const modal=$('#sp-run-modal');if(!modal)return;
    const state=run.status, step=run.current?.step;
    const visual=run.current?.waiting_for_device&&state==='running'?'attention':state==='complete'?'complete':['review','interrupted'].includes(state)?'review':['paused','ready'].includes(state)?'paused':state==='pausing'?'cancelling':step==='transfer'?'video':['sending','verify'].includes(step)?'send':'neutral';
    modal.dataset.visual=visual;
    const host=$('#sp-run-icon');if(host&&host.dataset.visual!==visual){host.dataset.visual=visual;host.classList.add('sf-post-icon');host.innerHTML=icon(['review','cancelling'].includes(visual)?'attention':visual);}
  }

  let systemState=null, refresh=null;
  function connectionModel(state={}) {
    const sys=state.system||{};
    if(!sys.bridge_online)return {kind:'offline',short:'โปรแกรมยังไม่เชื่อมต่อ',message:'รอการเชื่อมต่อจากโปรแกรม งานเดิมยังไม่ถูกเปลี่ยน'};
    if(!sys.extension_online)return {kind:'offline',short:'ยังไม่เชื่อมต่อ',message:'เปิด Chrome ที่ติดตั้ง SmartFlow Extension แล้วตรวจอีกครั้ง'};
    if(!sys.extension_compatible)return {kind:'warning',short:'ต้องอัปเดต Extension',message:'รุ่น Extension ไม่ตรงกับโปรแกรม กรุณาตรวจรุ่นก่อนเริ่มงานใหม่'};
    return {kind:'ready',short:'เชื่อมต่อแล้ว',message:'Extension เชื่อมต่อและรุ่นตรงกับโปรแกรม'};
  }
  const put=(selector,value)=>{const node=$(selector);if(node&&node.textContent!==value)node.textContent=value;};
  function paintConnection() {
    if(!systemState)return;
    const sys=systemState.system||{}, model=connectionModel(systemState);
    put('#side-status-text',model.short);
    const dot=$('#side-status-dot');if(dot)dot.classList.toggle('ready',model.kind==='ready');
    const button=$('#extension-status-open');if(button)button.dataset.state=model.kind;
    put('#extension-status-summary',model.message);
    put('#extension-bridge-value',sys.bridge_online?'เชื่อมต่อแล้ว':'ยังไม่เชื่อมต่อ');
    put('#extension-online-value',sys.extension_online?'เชื่อมต่อแล้ว':'ออฟไลน์');
    put('#extension-version-value',String(sys.extension_version||'ไม่พบรุ่น'));
    put('#extension-required-value',String(systemState.app?.extension_required||'ยังไม่ทราบ'));
    put('#extension-license-value','ไม่ต้องใช้ API Token');
    put('#side-extension','แผงนี้แสดงสถานะเท่านั้น ไม่เริ่มงานหรือส่งคำขอสร้างซ้ำ');
  }
  const panel=$('#extension-status-modal');
  $('#extension-status-open')?.addEventListener('click',()=>{if(panel&&!panel.open)panel.showModal();});
  $('#extension-status-close')?.addEventListener('click',()=>panel.close());
  $('#extension-guide-open')?.addEventListener('click',()=>panel.close());
  $('#extension-status-refresh')?.addEventListener('click',async event=>{
    const button=event.currentTarget;if(!refresh||button.disabled)return;
    button.disabled=true;
    put('#extension-check-note','กำลังตรวจการเชื่อมต่อ…');
    try{await refresh();put('#extension-check-note','อ่านสถานะล่าสุดแล้ว • ไม่มีการสั่งงานเพิ่ม');}
    catch{put('#extension-check-note','ยังอ่านสถานะไม่ได้ กรุณาตรวจว่าโปรแกรมยังเปิดอยู่');}
    finally{button.disabled=false;}
  });
  const visibility=()=>document.documentElement.classList.toggle('sf-motion-hidden',document.hidden);
  document.addEventListener('visibilitychange',visibility);visibility();
  window.SmartFlowUX={deriveProgressVisualState,connectionModel,renderProgress,renderPosting,
    renderSystem(state,readOnlyRefresh){systemState=state;refresh=readOnlyRefresh;paintConnection();}
  };
})();
