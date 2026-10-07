// Actual queue editor, routing, cover and green modules; all bridge actions mocked.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=file=>fs.readFileSync(path.join(__dirname,'../web_ui',file),'utf8');
const backendState=process.argv[2]?JSON.parse(process.argv[2]):null;
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>route.abort());
  await page.setContent(source('index.html').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
  await page.addScriptTag({content:`
   const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
   const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
   const ui={state:{},activePage:'creation',aiModelDrafts:{}},pageMeta={},calls=[];
   const toast=()=>{},poll=async()=>{},showPage=()=>{};
   const clip=n=>({file:'assets/screenfx/'+n.repeat(64)+'.mp4',color:'#00ff00',similarity:.2,blend:.1});
   const greenState={settings:{enabled:true,clips:[clip('b')],opacity:.9,fit:'contain'},targets:{product:true},assets:[]};
   let postAction=async(action,payload={})=>{calls.push({action,payload});
    if(action==='green_status')return new Promise(resolve=>window.releaseGreen=()=>resolve({ok:true,...greenState}));
    return action==='green_save'?{ok:true,...greenState}:{ok:true};};
   const makeRow=(id,enabled)=>({queue_id:id,status:'queued',mode:'product',job_id:'',link:'https://s.shopee.co.th/'+id,
    provider:'gemini',ai_web_model:'pro',video_generation_mode:'meta_ai',scene_count:6,
    settings:{ai_cover_options:{enabled:true,headline:'Saved custom headline',scene_index:2},
      green_options:{enabled,clips:[clip('a')],opacity:.35,fit:'cover'}}});
   window.rowA=makeRow('A',false);window.rowB=makeRow('B',true);
  `});
  const app=source('app.js'),start=app.indexOf('const fallbackAiModelOptions ='),end=app.indexOf('function bindAiModelSelect(',start);
  await page.addScriptTag({content:app.slice(start,end)});
  for(const file of ['status_vocabulary.js','creation_queue.js','media_audio.js','ai_cover.js','green_screen.js'])await page.addScriptTag({content:source(file)});
  if(backendState)await page.evaluate(state=>{
    window.rowA={...state.items[0],queue_id:'A'};window.rowB={...state.items[1],queue_id:'B'};
  },backendState);
  await page.evaluate(()=>{ui.state={creation_queue:{paused:true,counts:{queued:2},items:[rowA,rowB]}};renderCreationQueue(ui.state);});
  const open=async id=>page.locator('[data-cq="edit"][data-id="'+id+'"]').click();
  const green=page.locator('#creation-form [data-green-enable]');
  await open('A');
  assert.equal(await green.isChecked(),false,'edit must hydrate saved false rather than global true');
  assert.equal(await green.isEnabled(),true);
  await page.evaluate(async()=>{await postAction('creation_edit',{queue_id:'A',value:rowA.link,use_current_settings:false});});
  let sent=await page.evaluate(()=>calls.at(-1).payload);
  assert.equal(Object.hasOwn(sent.ai_cover_options,'headline'),false,'unchanged hidden headline must not be sent as a clear');
  assert.equal(sent.ai_cover_options.scene_index,2);
  assert.equal(Object.hasOwn(sent,'green_options'),false,'unchanged row green must not be replaced by global defaults');
  await green.check();
  await page.evaluate(()=>releaseGreen());
  assert.equal(await green.isChecked(),true,'late global loading cannot replace a row edit');
  await page.evaluate(async()=>{await document.querySelector('#green-save').onclick();});
  assert.equal(await green.isChecked(),true,'saving global defaults cannot replace a row edit');
  await page.evaluate(async()=>{await postAction('creation_edit',{queue_id:'A',value:rowA.link,use_current_settings:false});});
  sent=await page.evaluate(()=>calls.at(-1).payload);
  assert.deepEqual(sent.green_options,{enabled:true},'targeted edit must not send global clips/opacity');
  await page.locator('#creation-editor-close').click();await open('B');
  assert.equal(await green.isChecked(),true,'switching rows resets dirty state');
  assert.match(await page.locator('#creation-form [data-green-note]').textContent(),/ค่าของรายการนี้/);
  await green.uncheck();
  await page.locator('#creation-recapture').check();
  assert.equal(await green.isChecked(),true,'explicit recapture selects current defaults');
  await page.evaluate(async()=>{await postAction('creation_edit',{queue_id:'B',value:rowB.link,use_current_settings:true});});
  sent=await page.evaluate(()=>calls.at(-1).payload);
  assert.deepEqual(sent.green_options,await page.evaluate(()=>greenState.settings));
  await page.locator('#creation-recapture').uncheck();
  assert.equal(await green.isChecked(),true,'leaving recapture restores saved row, not its previous global value');
  // Read-only guards remain effective even if a stale editor entry were invoked.
  for(const change of [{status:'running'},{job_id:'JOB-BOUND'},{long_video:{version:2}},{mode:'drama'}]){
   await page.evaluate(change=>prepareGreenQueue({...rowA,...change}),change);
   assert.equal(await green.isDisabled(),true);
   assert.match(await page.locator('#creation-form [data-green-note]').textContent(),/อ่านอย่างเดียว/);
  }
  await page.evaluate(()=>prepareGreenQueue({...rowA,settings:{}}));
  assert.equal(await green.isDisabled(),true,'legacy row without saved effects cannot silently adopt current library');
  await page.locator('#creation-editor-close').click();
  await page.locator('#queue-add-products').click();
  assert.equal(await green.isEnabled(),true,'new modal clears old read-only state');
  assert.equal(await green.isChecked(),true);
  await page.evaluate(async()=>{await postAction('creation_enqueue',{mode:'product',values:['fixture']});});
  sent=await page.evaluate(()=>calls.at(-1).payload);
  assert.equal(sent.ai_cover_options.headline,'','new covers still choose text automatically');
  assert.deepEqual(sent.green_options,await page.evaluate(()=>greenState.settings));
  await page.evaluate(async()=>{await postAction('create_story',{job_id:'STORY-OLD'});});
  sent=await page.evaluate(()=>calls.at(-1).payload);
  assert.equal(sent.green_options,undefined);assert.equal(sent.ai_cover_options,undefined);
  assert.deepEqual(errors,[]);
  console.log('PASS queue addons: saved rows, targeted toggle, headline omission, recapture, locked/unsupported, new/resume; browser closed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
