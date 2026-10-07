// Actual HTML/CSS + production progress controllers. All network fulfilled locally.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),read=n=>fs.readFileSync(path.join(root,n),'utf8');
const html=read('web_ui/index.html').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
const app=read('web_ui/app.js');
const shots=process.env.SF_UX_SCREENSHOTS;
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];let writes=0;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
   const request=route.request(),url=new URL(request.url());
   if(request.method()!=='GET'){writes++;return route.abort();}
   if(url.hostname!=='smartflow.test')return route.abort();
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   if(/^\/desktop\/[\w.-]+\.css$/.test(url.pathname))return route.fulfill({contentType:'text/css',body:read('web_ui/'+path.basename(url.pathname))});
   if(url.pathname==='/api/desktop/media')return route.fulfill({contentType:'image/png',body:fs.readFileSync(path.join(root,'assets',url.searchParams.get('item_id')==='__brand_full__'?'smartflow_logo.png':'smartflow_icon.png'))});
   return route.abort();
  });
  await page.goto('http://smartflow.test/');
  await page.addScriptTag({path:path.join(root,'web_ui/ux_2026.js')});
  await page.addScriptTag({path:path.join(root,'web_ui/automation_status.js')});
  await page.addScriptTag({content:`const ui={state:{},progressMinimized:false};const $=s=>document.querySelector(s);const toast=()=>{};
    ${app.slice(app.indexOf('function progressSteps('),app.indexOf('function renderNotice(state)'))}
    window.paint=(p,kind='story')=>{const idle={active:false,job_id:'',percent:0};ui.state={app:{extension_required:'0.15.384'},system:{extension_online:true,bridge_online:true,extension_compatible:true,extension_version:'0.15.384'},product_progress:idle,story_progress:idle,presenter_progress:{},[kind+'_progress']:p};renderProgress(ui.state);return ui.state;};
    $('#progress-close').onclick=minimizeProgress;$('#progress-minimized').onclick=restoreProgress;
    $('#progress-modal').addEventListener('cancel',e=>{e.preventDefault();minimizeProgress();});`});
  await page.addScriptTag({path:path.join(root,'web_ui/presenter_progress.js')});
  await page.addScriptTag({path:path.join(root,'web_ui/shopee_post_progress.js')});
  let cases=0;
  const ok=(condition,message)=>{assert(condition,message);cases++;};
  const phases=await page.evaluate(()=>{
    const d=SmartFlowUX.deriveProgressVisualState,base={active:true,job_id:'UI-FIXTURE'};
    return [d({...base,stage:'scene',scene_phase:'video'}),d({...base,stage:'video'}),d({...base,stage:'scene',scene_phase:'image'},{job_id:'OTHER',offline:true}),d({...base,stage:'scene',scene_phase:'image'},{job_id:'UI-FIXTURE',offline:true}),d({...base,percent:100,stage:'not-known'}),d({...base,action_required:true}),d({...base,stage:'voice'}),d({...base,pipeline_phase:'compose'}),d({...base,status:'image_review'}),d({...base,status:'error'}),d({...base,stage:'cancelling'}),d({...base,active:false,percent:100})];
  });
  assert.deepEqual(phases,['video','render','image','offline','neutral','attention','voice','render','review','error','cancelling','paused']);cases+=12;
  const connections=await page.evaluate(()=>{
    const c=SmartFlowUX.connectionModel,sys={bridge_online:true,extension_online:true,extension_compatible:true};
    return [c({system:sys},true).kind,c({system:sys},false).kind,c({system:sys}).kind,c({system:{...sys,extension_compatible:false}},true).kind,c({system:{...sys,extension_online:false}},true).kind,c({system:{...sys,bridge_online:false}},true).kind];
  });
  assert.deepEqual(connections,['ready','ready','ready','warning','offline','offline']);cases+=6;
  const sidebar=await page.locator('.navigation .nav-item').evaluateAll(nodes=>nodes.map(n=>({route:n.dataset.page,icons:n.querySelectorAll('i svg').length})));
  assert.deepEqual(sidebar.map(n=>n.route),['dashboard','products','story','longvideo','drama','creation','library','ai-chat','queue','facebook','presenter','presenter-settings','product-cast','intro','green','settings','voice','subtitle','audio','logo','guide','logs'],'sidebar groups every page, including long video, voice, subtitle, audio, logo and guide');cases++;
  ok(sidebar.every(n=>n.icons===1),'every current sidebar route retains one local SVG icon');
  ok(await page.locator('.brand img').getAttribute('src').then(x=>x.includes('__brand_full__')),'full original brand route');
  await page.evaluate(()=>{
    window.refreshes=0;window.connectionFixture={system:{bridge_online:true,extension_online:true,extension_compatible:true,extension_authorized:true,extension_version:'0.15.384'},app:{extension_required:'0.15.384'}};SmartFlowUX.renderSystem(connectionFixture,async()=>{window.refreshes++;});
  });
  await page.locator('#extension-status-open').click();
  ok(await page.locator('#extension-status-modal').evaluate(n=>n.open),'panel opens');
  await page.locator('#extension-status-refresh').click();
  ok(await page.evaluate(()=>refreshes)===1,'one read-only refresh');
  await page.evaluate(()=>SmartFlowUX.renderSystem(connectionFixture,async()=>{throw Error('offline');}));
  await page.locator('#extension-status-refresh').click();
  ok((await page.locator('#extension-check-note').innerText()).includes('ยังอ่านสถานะไม่ได้'),'failed refresh is not success');
  await page.evaluate(()=>SmartFlowUX.renderSystem({...connectionFixture,system:{...connectionFixture.system,extension_authorized:false}}));
  ok((await page.locator('#side-status-dot').getAttribute('class')||'').includes('ready'),'legacy license field cannot block Extension connection');
  ok((await page.locator('#extension-license-value').textContent()).includes('ไม่ต้องใช้ API Token'),'no Extension membership check');
  if(shots){fs.mkdirSync(shots,{recursive:true});await page.screenshot({path:path.join(shots,'extension-panel.png')});}
  await page.keyboard.press('Escape');
  ok(await page.locator('#extension-status-open').evaluate(n=>document.activeElement===n),'dialog restores focus');
  const base={job_id:'UI-FIXTURE',active:true,stage:'scene',scene_phase:'video',scene_index:3,scene_total:7,scenes_complete:2,percent:36,message:'ฉาก 3/7 • กำลังสร้างวิดีโอ',detail:'สถานะจำลองสำหรับทดสอบหน้าตา • ไม่ได้เรียก AI'};
  await page.evaluate(p=>paint(p),base);
  const same=await page.evaluate(p=>{const node=document.querySelector('#progress-motion svg');paint(p);return node===document.querySelector('#progress-motion svg');},base);
  ok(same,'heartbeat preserves animation DOM');
  for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[1093,614],[960,540],[390,844]]){
    await page.setViewportSize({width,height});
    const metrics=await page.locator('#progress-modal').evaluate(n=>{const r=n.getBoundingClientRect(),c=n.querySelector('.modal-card').getBoundingClientRect(),b=getComputedStyle(n,'::backdrop');return {x:r.x,y:r.y,width:r.width,height:r.height,card:{x:c.x,y:c.y,right:c.right,bottom:c.bottom},blur:b.backdropFilter,bg:b.backgroundColor};});
    ok(Math.abs(metrics.width-width)<2&&Math.abs(metrics.height-height)<2&&metrics.x===0&&metrics.y===0,`full viewport backdrop owner ${width}`);
    ok(metrics.card.x>=0&&metrics.card.y>=0&&metrics.card.right<=width+1&&metrics.card.bottom<=height+1,`card within viewport ${width}`);
    ok(metrics.blur==='blur(12px)'&&metrics.bg!=='rgba(0, 0, 0, 0)',`native backdrop ${width}`);
    if(shots&&[1440,1366,390].includes(width))await page.screenshot({path:path.join(shots,`progress-${width}.png`)});
  }
  await page.setViewportSize({width:1440,height:900});
  await page.locator('#progress-close').click();await page.evaluate(p=>paint(p),base);
  ok(!(await page.locator('#progress-modal').evaluate(n=>n.open)),'minimize persists across heartbeat');
  ok(await page.locator('#progress-motion .sf-frame-front').evaluate(n=>getComputedStyle(n).animationPlayState==='paused'),'minimized motion pauses');
  await page.locator('#progress-minimized').click();await page.keyboard.press('Escape');
  ok(!(await page.locator('#progress-modal').evaluate(n=>n.open)),'Escape minimizes, never cancels');
  await page.locator('#progress-minimized').click();
  await page.evaluate(p=>paint({...p,action_required:true,action_button:'เปิด Chrome เพื่อยืนยัน'}),base);
  ok(await page.locator('#progress-modal').getAttribute('data-visual')==='attention','actual action required');
  ok(await page.locator('#progress-motion .sf-frame-front').evaluate(n=>getComputedStyle(n).animationName==='none'),'attention is static');
  if(shots)await page.screenshot({path:path.join(shots,'needs-attention.png')});
  await page.evaluate(p=>paint({...p,percent:100}),base);
  ok(await page.locator('#progress-modal').evaluate(n=>n.open),'active 100 is not final completion');
  await page.evaluate(p=>paint({...p,percent:100,active:false}),base);
  ok(!(await page.locator('#progress-modal').evaluate(n=>n.open)),'desktop final closes immediately');
  await page.evaluate(()=>paint({job_id:'P-FIXTURE',run_id:'1',active:false,status:'clip_review',clips:2},'presenter'));
  ok(await page.locator('#progress-modal').getAttribute('data-visual')==='review','Presenter review stays review');
  ok(await page.locator('#automation-observation').innerText()==='','Presenter does not inherit previous observations');
  await page.evaluate(()=>paint({job_id:'P-FIXTURE',run_id:'1',active:false,status:'ready',clips:3},'presenter'));
  const run={id:'POST-FIXTURE',status:'running',started_at:Date.now()/1000,sequence:1,total:5,completed:1,remaining:4,review_count:0,current_id:'post-2',current_index:2,current:{title:'คลิปสินค้า • สถานะจำลอง',step:'transfer',message:'กำลังส่งคลิปเข้าโทรศัพท์'},events:[]};
  await page.evaluate(r=>SmartFlowPostProgress.update(r),run);
  ok(await page.locator('#sp-run-modal').getAttribute('data-visual')==='video','Shopee uses its real step');
  ok(await page.locator('#sp-run-meter').getAttribute('aria-valuenow')==='20','Shopee completion metric unchanged');
  ok(await page.evaluate(r=>{const icon=document.querySelector('#sp-run-icon svg');SmartFlowPostProgress.update(r);return icon===document.querySelector('#sp-run-icon svg');},run),'Shopee heartbeat preserves icon DOM');
  if(shots)await page.screenshot({path:path.join(shots,'shopee-progress.png')});
  await page.evaluate(()=>SmartFlowPostProgress.update(null));
  await page.evaluate(p=>{ui.progressMinimized=false;paint(p);},base);
  await page.emulateMedia({reducedMotion:'reduce'});
  ok(await page.locator('#progress-motion .sf-frame-front').evaluate(n=>getComputedStyle(n).animationName==='none'),'reduced motion');
  await page.evaluate(()=>document.documentElement.classList.add('sf-motion-hidden'));
  ok(await page.locator('#progress-motion .sf-frame-front').evaluate(n=>getComputedStyle(n).animationPlayState==='paused'),'background window pauses');
  await page.evaluate(()=>document.querySelector('#progress-modal').close());
  if(shots)await page.screenshot({path:path.join(shots,'workspace.png')});
  // Every native modal gets a non-transparent full-screen backdrop; cards remain scrollable.
  const ids=await page.locator('dialog.modal').evaluateAll(nodes=>nodes.map(n=>n.id));
  for(const id of ids){
    const m=await page.evaluate(id=>{const el=document.getElementById(id);el.showModal();const r=el.getBoundingClientRect(),style=getComputedStyle(el,'::backdrop');el.close();return {width:r.width,height:r.height,bg:style.backgroundColor};},id);
    ok(Math.abs(m.width-1440)<2&&Math.abs(m.height-900)<2&&m.bg!=='rgba(0, 0, 0, 0)',`modal ${id}`);
  }
  assert.equal(writes,0);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({ok:true,cases,modals:ids.length,externalRequests:0,providerSubmissions:0}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
