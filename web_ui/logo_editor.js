/* Local logo geometry; no provider, queue or render dispatch while dragging. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const sizes = {portrait:[720,1280],landscape:[1920,1080]};
  const anchors = ['top_left','top_center','top_right','center_left','center','center_right','bottom_left','bottom_center','bottom_right'];
  const labels = ['บนซ้าย','บนกลาง','บนขวา','กลางซ้าย','กึ่งกลาง','กลางขวา','ล่างซ้าย','ล่างกลาง','ล่างขวา'];
  const clamp = (n, low, high) => Math.max(low, Math.min(high, n));
  const clone = value => JSON.parse(JSON.stringify(value));
  function geometry(layout, width, height, lw, lh) {
    const row=layout[width>height?'landscape':'portrait'];
    const desired=Math.max(8,Math.round(width*row.size_percent/100));
    const scale=Math.min(desired/lw,width/lw,height/lh);
    const w=Math.max(1,Math.min(width,Math.round(lw*scale))),h=Math.max(1,Math.min(height,Math.round(lh*scale)));
    return {x:clamp(Math.round(row.x*width-w/2),0,width-w),y:clamp(Math.round(row.y*height-h/2),0,height-h),width:w,height:h};
  }
  const state={profile:'portrait',layout:null,context:null,jobId:'',followSource:false,dirty:false,request:'',revision:0,session:Math.random().toString(36).slice(2),frame:null,asset:null,drag:null,callbacks:null,opacity:80,legacy:null};
  function dimensions(){return state.frame?.profile===state.profile?[state.frame.width,state.frame.height]:sizes[state.profile];}
  function imageSize(){const img=$('logo-overlay-image');return [img?.naturalWidth||100,img?.naturalHeight||100];}
  function preset(profile, position, margin, size){
    const [w,h]=state.frame?.profile===profile?[state.frame.width,state.frame.height]:sizes[profile],[lw,lh]=imageSize();
    const layout={portrait:{x:.5,y:.5,size_percent:size},landscape:{x:.5,y:.5,size_percent:size}};
    const rect=geometry(layout,w,h,lw,lh),key=anchors.includes(position)?position:anchors[labels.indexOf(position)]||'bottom_right';
    const x=key.endsWith('left')?margin:key.endsWith('right')?w-rect.width-margin:(w-rect.width)/2;
    const y=key.startsWith('top')?margin:key.startsWith('bottom')?h-rect.height-margin:(h-rect.height)/2;
    return {x:clamp((x+rect.width/2)/w,0,1),y:clamp((y+rect.height/2)/h,0,1),size_percent:size};
  }
  function legacyLayout(){const l=state.legacy||{};return {version:1,portrait:preset('portrait',l.position,l.margin??28,l.size??18),landscape:preset('landscape',l.position,l.margin??28,l.size??18)};}
  function paint(){
    if(!state.layout||!$('logo-editor-stage'))return;
    const [w,h]=dimensions(),[lw,lh]=imageSize(),rect=geometry(state.layout,w,h,lw,lh),stage=$('logo-editor-stage');
    const scale=Math.min(Math.max(1,stage.clientWidth-16)/w,Math.max(1,stage.clientHeight-16)/h);
    const frame=$('logo-editor-frame');frame.style.width=`${w*scale}px`;frame.style.height=`${h*scale}px`;
    const handle=$('logo-drag-handle');Object.assign(handle.style,{left:`${rect.x/w*100}%`,top:`${rect.y/h*100}%`,width:`${rect.width/w*100}%`,height:`${rect.height/h*100}%`,opacity:state.opacity/100});
    const row=state.layout[state.profile];
    $('logo-size').value=row.size_percent;$('logo-size-label').textContent=`${row.size_percent}%`;
    $('logo-opacity').value=state.opacity;$('logo-opacity-label').textContent=`${state.opacity}%`;
    if(document.activeElement!==$('logo-x'))$('logo-x').value=(row.x*100).toFixed(1);
    if(document.activeElement!==$('logo-y'))$('logo-y').value=(row.y*100).toFixed(1);
    document.querySelectorAll('[data-logo-profile]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.logoProfile===state.profile)));
    const real=state.frame?.profile===state.profile&&state.frame.real_frame;
    $('logo-frame-image').hidden=!real;
    $('logo-canvas-caption').textContent=real?'เฟรมจากวิดีโอที่เลือก • ใช้อัตราส่วนจริงของวิดีโอ':'ภาพพื้นหลังตัวอย่าง • การสลับตัวอย่างไม่เปลี่ยนขนาดวิดีโอ';
    $('logo-render').disabled=!$('logo-job').value;
    handle.disabled=!state.asset;
  }
  function changed(){state.dirty=true;state.request='';state.revision++;$('logo-render-check').hidden=true;paint();}
  function move(x,y){
    const [w,h]=dimensions(),[lw,lh]=imageSize(),row=state.layout[state.profile],rect=geometry(state.layout,w,h,lw,lh);
    row.x=clamp(x,rect.width/(2*w),1-rect.width/(2*w));row.y=clamp(y,rect.height/(2*h),1-rect.height/(2*h));changed();
  }
  async function preview(){
    if(!state.callbacks||!state.asset||!state.layout)return;
    const request=`${state.session}_${++state.revision}`;state.request=request;
    try{await state.callbacks.request({...state.callbacks.payload(),profile:state.profile,follow_source:state.followSource,preview_request:request});}
    catch(error){if(state.request===request)state.callbacks.error(error);}
  }
  function render(logo){
    if(!$('logo-editor-stage'))return;
    const context=`${logo.job_id||''}:${logo.selected_asset_id||''}`;
    if(context!==state.context){
      state.followSource=Boolean(logo.job_id)&&state.jobId!==logo.job_id;state.jobId=logo.job_id||'';
      state.context=context;state.dirty=false;state.request='';state.frame=null;state.drag=null;
      state.legacy=clone(logo);state.layout=logo.layout?clone(logo.layout):legacyLayout();state.opacity=logo.opacity??80;
    }else if(!state.dirty&&logo.layout){state.layout=clone(logo.layout);state.opacity=logo.opacity??80;}
    state.asset=logo.selected_asset_id||'';
    const img=$('logo-overlay-image');
    if(logo.asset_url&&img.dataset.url!==logo.asset_url){img.dataset.url=logo.asset_url;img.src=logo.asset_url;}
    const result=logo.editor_preview;
    if(result?.request&&result.request===state.request&&(result.profile===state.profile||state.followSource)&&result.job_id===($('logo-job').value||'')&&result.asset_id===state.asset){
      state.profile=result.profile;state.followSource=false;
      state.frame=result;
      const url=kind=>`/api/desktop/media?item_id=${encodeURIComponent(`__logo_editor_${kind}__:${result.request}`)}&kind=preview`;
      if($('logo-frame-image').dataset.request!==result.request){$('logo-frame-image').dataset.request=result.request;$('logo-frame-image').src=url('frame');$('logo-preview').src=url('result');}
      $('logo-render-check').hidden=false;
    }
    paint();
  }
  function bind(callbacks){
    if(state.callbacks||!$('logo-editor-stage'))return;state.callbacks=callbacks;
    new ResizeObserver(paint).observe($('logo-editor-stage'));
    $('logo-overlay-image').addEventListener('load',()=>{if(!state.dirty&&!state.legacy?.layout)state.layout=legacyLayout();paint();});
    document.querySelectorAll('[data-logo-profile]').forEach(button=>button.addEventListener('click',()=>{state.profile=button.dataset.logoProfile;state.followSource=false;state.request='';$('logo-render-check').hidden=true;paint();preview();}));
    $('logo-size').addEventListener('input',()=>{if(!state.layout)return;state.layout[state.profile].size_percent=Number($('logo-size').value);changed();});
    $('logo-opacity').addEventListener('input',()=>{state.opacity=Number($('logo-opacity').value);changed();});
    for(const id of ['logo-size','logo-opacity'])$(id).addEventListener('change',preview);
    const anchor=()=>{if(!state.layout)return;state.layout[state.profile]=preset(state.profile,$('logo-position').value,Number($('logo-margin').value),state.layout[state.profile].size_percent);changed();preview();};
    $('logo-position').addEventListener('change',anchor);$('logo-margin').addEventListener('change',anchor);
    $('logo-reset').addEventListener('click',()=>{state.layout[state.profile]=preset(state.profile,'bottom_right',28,18);changed();preview();});
    for(const axis of ['x','y'])$('logo-'+axis).addEventListener('change',()=>{const value=Number($('logo-'+axis).value);if(!Number.isFinite(value)){paint();return;}const row=state.layout[state.profile];move(axis==='x'?value/100:row.x,axis==='y'?value/100:row.y);preview();});
    const handle=$('logo-drag-handle');
    handle.addEventListener('pointerdown',event=>{if(event.button!==0||!state.layout)return;event.preventDefault();handle.focus();const frame=$('logo-editor-frame').getBoundingClientRect(),box=handle.getBoundingClientRect();state.drag={id:event.pointerId,dx:event.clientX-(box.left+box.width/2),dy:event.clientY-(box.top+box.height/2),row:clone(state.layout[state.profile])};handle.setPointerCapture(event.pointerId);});
    handle.addEventListener('pointermove',event=>{if(state.drag?.id!==event.pointerId)return;const box=$('logo-editor-frame').getBoundingClientRect();move((event.clientX-state.drag.dx-box.left)/box.width,(event.clientY-state.drag.dy-box.top)/box.height);});
    handle.addEventListener('pointerup',event=>{if(state.drag?.id!==event.pointerId)return;state.drag=null;if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);preview();});
    handle.addEventListener('pointercancel',()=>{if(!state.drag)return;state.layout[state.profile]=state.drag.row;state.drag=null;changed();});
    handle.addEventListener('lostpointercapture',()=>{state.drag=null;});
    handle.addEventListener('keydown',event=>{const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];if(!delta||!state.layout)return;event.preventDefault();const [w,h]=dimensions(),row=state.layout[state.profile],step=event.shiftKey?10:1;move(row.x+delta[0]*step/w,row.y+delta[1]*step/h);});
    handle.addEventListener('keyup',event=>{if(event.key.startsWith('Arrow'))preview();});
  }
  window.SmartFlowLogo={geometry,render,bind,preview,payload:()=>({layout:state.layout?clone(state.layout):null,opacity:state.opacity,profile:state.profile}),saved:()=>{state.dirty=false;},resetContext:()=>{state.context=null;state.request='';state.frame=null;},debug:()=>clone({...state,callbacks:null,drag:null})};
})();
