const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,
  ...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>r.abort());
 const html=fs.readFileSync('web_ui/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
 await page.setContent(html);
 for(const file of ['styles.css','creation_queue.css','creator_ux.css'])await page.addStyleTag({content:fs.readFileSync('web_ui/'+file,'utf8')});
 await page.addScriptTag({content:`
 const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
 const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const calls=[],ui={state:{}},toast=()=>{},poll=async()=>{};
 const postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true};};
 const showPage=name=>$$('[data-view]').forEach(n=>n.classList.toggle('active',n.dataset.view===name));
 `});
 await page.addScriptTag({content:fs.readFileSync('web_ui/status_vocabulary.js','utf8')});
 await page.addScriptTag({content:fs.readFileSync('web_ui/creation_queue.js','utf8')});
 assert.deepEqual(await page.locator('#creation-product-outfit-mode option').evaluateAll(nodes=>nodes.map(n=>n.value)),['auto','product','saved']);
 await page.evaluate(()=>{
  const jobs=Array.from({length:35},(_,n)=>({job_id:'JOB-OLD-'+n,mode:'product',title:'งานเก่าที่ไม่ต้องการ '+n}));
  ui.state={creation_queue:{paused:true,counts:{failed:1},items:[{queue_id:'CQ-STOPPED',job_id:'STORY-STOPPED',status:'failed',mode:'story',topic:'งานเก่าที่ค้างในคิว'}],
   recoverable_jobs:jobs.slice(0,30),recoverable_job_count:35,removable_old_queue_ids:['CQ-STOPPED'],
   removable_old_job_ids:jobs.map(r=>r.job_id),can_remove_old_entries:true},story_progress:{active:false}};
  renderCreationQueue(ui.state);showPage('creation');
 });
 assert.match(await page.locator('#creation-remove-old').textContent(),/36/);
 assert.match(await page.locator('#creation-old-hint').textContent(),/30 จาก 35/);
 await page.locator('#creation-remove-old').click();
 assert.equal(await page.locator('#creation-confirm').evaluate(n=>n.open),true);
 assert.equal(await page.evaluate(()=>calls.length),0);
 assert.match(await page.locator('#creation-confirm-message').textContent(),/เก็บไฟล์คลิป/);
 await page.locator('#creation-confirm-close').click();
 assert.equal(await page.evaluate(()=>calls.length),0);
 await page.locator('[data-dismiss-job="JOB-OLD-0"]').click();
 await page.locator('#creation-confirm-accept').click();
 assert.deepEqual(await page.evaluate(()=>calls[0]),{action:'creation_remove_old',payload:{queue_ids:[],job_ids:['JOB-OLD-0'],confirmed:true}});
 await page.locator('[data-cq="remove"][data-id="CQ-STOPPED"]').click();
 await page.locator('#creation-confirm-accept').click();
 assert.deepEqual(await page.evaluate(()=>calls[1].payload),{queue_ids:['CQ-STOPPED'],job_ids:[],confirmed:true});
 await page.locator('#creation-remove-old').click();
 await page.evaluate(()=>{ui.state.creation_queue.removable_old_job_ids.push('JOB-ADDED-LATER');renderCreationQueue(ui.state);});
 await page.locator('#creation-confirm-accept').click();
 assert.equal(await page.evaluate(()=>calls[2].payload.job_ids.length),35,'Confirmation snapshots exact IDs, not newly added jobs');
 await page.evaluate(()=>{ui.state.creation_queue.can_remove_old_entries=false;renderCreationQueue(ui.state);});
 assert.equal(await page.locator('#creation-remove-old').isDisabled(),true);
 assert.equal(await page.locator('[data-dismiss-job="JOB-OLD-0"]').isDisabled(),true);
 await page.evaluate(()=>{ui.state.creation_queue.can_remove_old_entries=true;renderCreationQueue(ui.state);});
 for(const width of [1440,600,360]){
  await page.setViewportSize({width,height:960});
  const overflow=await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(n=>n.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(n=>({tag:n.tagName,id:n.id,cls:n.className,width:n.getBoundingClientRect().width})));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'overflow '+width+' '+JSON.stringify(overflow));
  if(process.env.CREATION_REMOVE_SCREENSHOT && width===1440)await page.screenshot({path:process.env.CREATION_REMOVE_SCREENSHOT});
 }
 await page.evaluate(()=>{
  ui.state.creation_queue={paused:true,counts:{queued:1},items:[{queue_id:'CQ-LONG',job_id:'',status:'queued',
   mode:'story',topic:'เรื่องเล่ายาว',scene_count:50,long_video:{version:2,scene_count:50},
   settings:{audio_choices:{subtitle:true}},subtitle:false}],recoverable_jobs:[],
   removable_old_queue_ids:[],removable_old_job_ids:[],can_remove_old_entries:true};
  renderCreationQueue(ui.state);
 });
 assert.match(await page.locator('#creation-list').textContent(),/คลิปยาว/);
 assert.match(await page.locator('#creation-list').textContent(),/50 ฉาก.*เปิดซับ/s);
 await page.locator('#creation-filter').selectOption('story');
 assert.equal(await page.locator('#creation-list .cq-row').count(),0);
 await page.locator('#creation-filter').selectOption('long_video');
 assert.equal(await page.locator('#creation-list .cq-row').count(),1);
 await page.evaluate(()=>{ui.state.creation_queue={paused:true,counts:{},items:[],recoverable_jobs:[],removable_old_queue_ids:[],removable_old_job_ids:[],can_remove_old_entries:true};renderCreationQueue(ui.state);});
 assert.equal(await page.locator('#creation-remove-old').isDisabled(),true);
 assert.equal(await page.locator('#creation-old-panel').isVisible(),false);
 assert.deepEqual(errors,[]);
 console.log('Queue old removal: individual/bulk confirmation, snapshot, busy/empty guards, 35 orphans and three widths passed; no live writes');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
