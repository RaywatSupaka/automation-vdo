const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),source=file=>fs.readFileSync(path.join(root,'web_ui',file),'utf8');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:1000},deviceScaleFactor:2});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',route=>route.abort());
  await page.setContent(source('index.html').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
  for(const file of ['styles.css','logo_editor.css'])await page.addStyleTag({content:source(file)});
  await page.addScriptTag({content:source('logo_editor.js')});
  await page.evaluate(()=>{
   document.querySelectorAll('.page').forEach(el=>el.classList.toggle('active',el.dataset.view==='logo'));
   window.calls=[];window.$=selector=>document.querySelector(selector);window.ui={selectedLogoAssetId:'brand'};window.toast=()=>{};window.poll=async()=>{};
   window.postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true};};
   $('select#logo-job').innerHTML='<option value="">พื้นหลังตัวอย่าง</option><option value="JOB-X">Job X</option>';
   $('#logo-position').innerHTML='<option value="bottom_right">ล่างขวา</option><option value="top_left">บนซ้าย</option>';
   const image='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="red"/></svg>');
   window.logoState={job_id:'',selected_asset_id:'brand',asset_url:image,opacity:80,size:18,margin:28,position:'bottom_right'};
  });
  const app=source('app.js');
  assert(app.slice(app.indexOf('function renderTools('),app.indexOf('function updateToolLabels(')).includes('SmartFlowLogo?.render(logo)'));
  await page.addScriptTag({content:app.slice(app.indexOf('function logoPayload()'),app.indexOf('\n',app.indexOf('function logoPayload()')))});
  await page.addScriptTag({content:app.slice(app.indexOf("$('#logo-preview-button').addEventListener"),app.indexOf("$('#save-settings').addEventListener"))});
  await page.evaluate(()=>{SmartFlowLogo.bind({payload:logoPayload,request:payload=>postAction('logo_editor_preview',payload),error:error=>{throw error;}});SmartFlowLogo.render(logoState);});
  await page.waitForFunction(()=>$('#logo-overlay-image').naturalWidth===400);
  const fixtures=JSON.parse(fs.readFileSync(path.join(root,'tests/logo_geometry_cases.json'),'utf8'));
  for(const row of fixtures){const got=await page.evaluate(r=>SmartFlowLogo.geometry({version:1,portrait:r.profile,landscape:r.profile},...r.video,...r.image),row);assert.deepEqual(got,row.expected,row.name);}
  const before=await page.evaluate(()=>SmartFlowLogo.payload());
  const handle=page.locator('#logo-drag-handle');await handle.scrollIntoViewIfNeeded();let box=await handle.boundingBox();
  await page.mouse.move(box.x+box.width/3,box.y+box.height/3);await page.mouse.down();await page.mouse.move(box.x-65,box.y-120,{steps:6});
  assert.equal(await page.evaluate(()=>calls.length),0,'pointermove must not dispatch');
  await page.mouse.up();assert.equal(await page.evaluate(()=>calls.length),1);
  const dragged=await page.evaluate(()=>SmartFlowLogo.payload());assert(dragged.layout.portrait.x<before.layout.portrait.x);assert(dragged.layout.portrait.y<before.layout.portrait.y);
  box=await handle.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x-60,box.y-70);
  await handle.dispatchEvent('pointercancel',{pointerId:1});await page.mouse.up();
  assert.deepEqual(await page.evaluate(()=>SmartFlowLogo.payload()),dragged,'pointercancel restores the original position');
  await page.evaluate(()=>SmartFlowLogo.render({...logoState,layout:{version:1,portrait:{x:.1,y:.1,size_percent:3},landscape:{x:.1,y:.1,size_percent:3}}}));
  assert.deepEqual(await page.evaluate(()=>SmartFlowLogo.payload()),dragged,'poll cannot overwrite draft');
  await page.locator('[data-logo-profile=landscape]').click();await page.locator('#logo-fine-controls > summary').click();await page.locator('#logo-x').fill('25');await page.locator('#logo-x').press('Tab');
  assert.equal(await page.evaluate(()=>SmartFlowLogo.payload().layout.landscape.x),.25);
  await page.locator('[data-logo-profile=portrait]').click();assert.deepEqual(await page.evaluate(()=>SmartFlowLogo.payload().layout.portrait),dragged.layout.portrait);
  await handle.focus();await page.keyboard.press('Shift+ArrowLeft');const keyboard=await page.evaluate(()=>SmartFlowLogo.payload().layout.portrait.x);assert(keyboard<dragged.layout.portrait.x);
  await page.evaluate(()=>SmartFlowLogo.render({...logoState,editor_preview:{request:'stale',profile:'portrait',asset_id:'brand',job_id:'',width:720,height:1280,real_frame:true}}));
  assert.equal(await page.locator('#logo-render-check').isVisible(),false);
  for(const width of [1080,600,360]){await page.setViewportSize({width,height:1000});await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));const bounded=await page.evaluate(()=>{const f=$('#logo-editor-frame').getBoundingClientRect(),l=$('#logo-drag-handle').getBoundingClientRect();return l.left>=f.left-.1&&l.top>=f.top-.1&&l.right<=f.right+.1&&l.bottom<=f.bottom+.1;});assert(bounded,`bounded at ${width}`);}
  await page.locator('#logo-save').click();const calls=await page.evaluate(()=>window.calls);
  assert.equal(calls.filter(c=>c.action==='logo_save').length,1);assert(calls.every(c=>['logo_save','logo_editor_preview'].includes(c.action)));
  assert(calls.find(c=>c.action==='logo_save').payload.layout.landscape.x===.25);
  assert.equal(await page.locator('#logo-render').isDisabled(),true);
  await page.locator('#logo-fine-controls > summary').click();
  if(process.env.LOGO_EDITOR_SCREENSHOT)await page.screenshot({path:process.env.LOGO_EDITOR_SCREENSHOT,fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS native logo editor: shared geometry, DPR2, drag, keyboard, profiles, dirty poll, stale preview, 4 widths, save without render');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
