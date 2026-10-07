const fs=require('fs'),assert=require('assert/strict'),{chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:600,height:1000}});
 await page.route('**/*',route=>route.abort());
 const html=fs.readFileSync('web_ui/index.html','utf8');
 const markup=html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
 await page.route('http://smartflow-ui.test/**',route=>route.fulfill({contentType:'text/html',body:markup}));
 await page.goto('http://smartflow-ui.test/sidebar');
 const styles=[...html.matchAll(/<link\b[^>]*href="\/desktop\/([^"?]+\.css)(?:\?[^" ]*)?"/g)].map(m=>m[1]);
 await page.addStyleTag({content:styles.map(n=>fs.readFileSync('web_ui/'+n,'utf8')).join('\n')+'\n.page:not([data-view="products"]){display:none!important}.page[data-view="products"]{display:block}'});
 await page.evaluate(()=>{
  window.baseState=()=>({product_job_delete_version:1,products:[],stories:[],product_preparations:[],product_job_controls:{}});
  window.ui={state:{...baseState(),products:[{id:'JOB-OLD',title:'สินค้าเดิม',status:'cancelled'}],stories:[
   {id:'STORY-NEW',title:'สินค้าทดสอบคลิปผสม',content_kind:'product',status:'cancelled',scene_count:4,image_count:4,video_plan_summary:{completed:3,flow:2,meta:1}},
   {id:'STORY-OTHER',content_kind:'story'}]}};
  window.calls=[];window.receipts={};window.submitCounts={};window.slowReads=0;window.loseAck=false;window.failStatus=false;window.partial=false;window.reject=false;
  window.escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  window.toast=()=>{};window.restoreProgress=()=>{};window.poll=async()=>{};
  window.confirmAnswers=[];window.confirmMessages=[];
  window.smartflowConfirm=async message=>{confirmMessages.push(message);return confirmAnswers.shift()??false;};
  window.resumeSourceEvent=null;window.addEventListener('smartflow:resume-product-source',e=>resumeSourceEvent=e.detail);
  window.responseFor=receipt=>{
   const controls=structuredClone(ui.state.product_job_controls||{});
   for(const id of receipt.job_ids)controls[id]={permanently_deleted:true,deleted:true,hidden:false,trashed:false,delete_status:receipt.deleted_ids.includes(id)?'deleted':receipt.status==='partial'?'failed':'deleting'};
   return {ok:true,product_job_controls:controls,deletion:structuredClone(receipt)};
  };
  window.postAction=async(action,payload)=>{
   calls.push({action,payload:structuredClone(payload)});await new Promise(r=>setTimeout(r,40));
   if(action==='product_jobs_delete_status'){
    if(failStatus)throw Error('status connection failed');
    const receipt=receipts[payload.request_id];
    if(!receipt)return {ok:true,deletion:{request_id:payload.request_id,status:'not_found',accepted:false,error:'request not accepted'}};
    if(receipt.status==='deleting'&&--slowReads<=0)Object.assign(receipt,{status:'complete',deleted_ids:[...receipt.job_ids]});
    return responseFor(receipt);
   }
   if(action==='product_jobs_manage'){
    if(payload.operation!=='delete'){
     const controls=structuredClone(ui.state.product_job_controls||{});for(const id of payload.job_ids)controls[id]={hidden:payload.operation==='hide'};
     return {ok:true,product_job_controls:controls};
    }
    if(reject)return {ok:false,error:'active job',deletion:{request_id:payload.request_id,status:'rejected',accepted:false,error:'active job'}};
    const submissions=submitCounts[payload.request_id]=(submitCounts[payload.request_id]||0)+1;
    const status=partial&&submissions===1?'partial':slowReads>0?'deleting':'complete';
    const deleted_ids=status==='complete'?[...payload.job_ids]:status==='partial'?payload.job_ids.slice(0,1):[];
    const receipt=receipts[payload.request_id]={request_id:payload.request_id,status,job_ids:[...payload.job_ids],deleted_ids,failed:status==='partial'?payload.job_ids.slice(1).map(job_id=>({job_id,error:'fixture file locked'})):[]};
    if(loseAck){loseAck=false;throw Error('lost ACK');}return responseFor(receipt);
   }return {ok:true};
  };
 });
 await page.addScriptTag({content:fs.readFileSync('web_ui/product_continue.js','utf8')});
 const settle=()=>page.waitForFunction(()=>!document.querySelector('#product-jobs-delete-status').disabled);
 const complete=()=>page.waitForFunction(()=>!sessionStorage.getItem('smartflow.productDeletionRequest'));
 const manageCalls=()=>page.evaluate(()=>calls.filter(c=>c.action==='product_jobs_manage'&&c.payload.operation==='delete'));
 const accept=()=>page.evaluate(()=>confirmAnswers.push(true));
 const reset=async data=>page.evaluate(data=>{ui.state={...baseState(),...data};calls=[];slowReads=0;partial=false;failStatus=false;reject=false;document.querySelector('#product-continue-notice').textContent='';renderProductContinue(ui.state);},data);
 assert.equal(await page.locator('.product-jobs-drawer').getAttribute('open'),null);
 assert.equal(await page.locator('#product-jobs-clear-all').isVisible(),true);
 assert.equal(await page.locator('[data-job-view]').count(),2);
 assert.equal(await page.locator('[data-job-view="trash"],[data-job-operation="restore"]').count(),0);
 assert.equal(await page.locator('#product-jobs-clear-legacy').isVisible(),false);
 assert.match(await page.locator('#product-jobs-heading').innerText(),/2$/);
 await page.locator('#product-link').fill('https://shopee.co.th/draft-not-submitted');
 await page.locator('.product-jobs-drawer > summary').click();
 assert.match(await page.locator('#product-continue-latest').innerText(),/วิดีโอ 3\/4 • Flow 2 \/ Meta 1/);
 assert.equal(await page.locator('[data-product-continue="STORY-OTHER"]').count(),0);
 assert.equal(await page.locator('[data-review-story="STORY-NEW"]').count(),1);
 await page.evaluate(()=>{delete ui.state.product_job_delete_version;renderProductContinue(ui.state);});
 assert.equal(await page.locator('#product-jobs-clear-all').isDisabled(),true);
 assert.equal(await page.locator('[data-job-operation="delete"]').first().isDisabled(),true);
 assert.equal(await page.locator('[data-product-continue="STORY-NEW"]').isDisabled(),false);
 assert.equal(await page.locator('[data-job-operation="hide"]').first().isDisabled(),false);
 assert.match(await page.locator('#product-jobs-clear-help').innerText(),/เปิดโปรแกรมใหม่/);
 await page.locator('#product-jobs-clear-all').evaluate(b=>b.dispatchEvent(new MouseEvent('click',{bubbles:true})));
 assert.equal((await manageCalls()).length,0);
 await page.evaluate(()=>{ui.state.product_job_delete_version=1;renderProductContinue(ui.state);});
 await page.locator('[data-product-continue="STORY-NEW"]').evaluate(b=>{b.click();b.click();});await page.waitForTimeout(100);
 assert.deepEqual(await page.evaluate(()=>calls),[{action:'product_continue',payload:{job_id:'STORY-NEW'}}]);
 await page.evaluate(()=>{ui.state.story_progress={active:true,job_id:'STORY-NEW',message:'กำลังทำฉาก4'};renderProductContinue(ui.state);});
 assert.equal(await page.locator('[data-product-running]').count(),1);assert.equal(await page.locator('#product-jobs-clear-all').isDisabled(),true);
 await page.evaluate(()=>{ui.state.story_progress={active:false};ui.state.product_preparations=[{id:'JOB-SOURCE',request_id:'PSP-owned',product_name:'กระเป๋าทดสอบ',capture_ready:true,source_image_count:6}];renderProductContinue(ui.state);});
 await page.locator('[data-resume-product-source="JOB-SOURCE"]').click();assert.deepEqual(await page.evaluate(()=>resumeSourceEvent),{product_id:'JOB-SOURCE',request_id:'PSP-owned'});
 await page.evaluate(()=>{window.productPreparationActive=true;renderProductContinue(ui.state);});
 assert.equal(await page.locator('[data-job-operation="delete"][data-job-id="JOB-SOURCE"]').isDisabled(),true);
 await page.evaluate(()=>{window.productPreparationActive=false;renderProductContinue(ui.state);});
 await page.locator('.product-source-preparation summary').click();await page.locator('[data-job-operation="hide"][data-job-id="JOB-SOURCE"]').click();await page.waitForTimeout(100);
 await page.locator('[data-job-view="hidden"]').click();await page.locator('.product-source-preparation summary').click();
 await page.locator('[data-job-operation="show"][data-job-id="JOB-SOURCE"]').click();await page.waitForTimeout(100);await page.locator('[data-job-view="pending"]').click();
 await page.locator('[data-resume-product-source="JOB-SOURCE"]').click();assert.deepEqual(await page.evaluate(()=>resumeSourceEvent),{product_id:'JOB-SOURCE',request_id:'PSP-owned'});
 await page.evaluate(()=>confirmAnswers.push(false));await page.locator('[data-job-operation="delete"][data-job-id="JOB-SOURCE"]').click();assert.equal((await manageCalls()).length,0);
 await accept();await page.locator('[data-job-operation="delete"][data-job-id="JOB-SOURCE"]').click();await complete();
 const single=(await manageCalls())[0].payload;assert.deepEqual(single.job_ids,['JOB-SOURCE']);assert.equal(single.confirmed,true);assert.match(single.request_id,/^[a-f0-9-]{36}$/);
 assert.equal(await page.locator('[data-resume-product-source="JOB-SOURCE"]').count(),0);
 await page.evaluate(()=>{ui.state.product_preparations.push({id:'JOB-SOURCE',product_name:'stale poll'});renderProductContinue(ui.state);});
 assert.equal(await page.locator('[data-resume-product-source="JOB-SOURCE"]').count(),0);
 assert.equal(await page.locator('#product-link').inputValue(),'https://shopee.co.th/draft-not-submitted');

 const legacy=Array.from({length:54},(_,i)=>({id:'JOB-LEGACY'+i,product_name:'รายการเก่า '+i}));
 const controls=Object.fromEntries(legacy.map(j=>[j.id,{trashed:true}]));
 await reset({product_preparations:legacy,products:[{id:'JOB-FINAL',ready:true}],product_job_controls:{...controls,'JOB-FINAL':{trashed:true}}});
 assert.match(await page.locator('#product-jobs-clear-legacy').innerText(),/\(54\)/);assert.equal(await page.locator('.product-continue-card').count(),0);
 assert.equal((await manageCalls()).length,0);await page.evaluate(()=>confirmAnswers.push(false));await page.locator('#product-jobs-clear-legacy').click();assert.equal((await manageCalls()).length,0);
 await accept();await page.locator('#product-jobs-clear-legacy').click();await complete();
 const cleanup=(await manageCalls())[0].payload;assert.equal(cleanup.scope,'legacy_trash');assert.deepEqual(new Set(cleanup.job_ids),new Set(legacy.map(j=>j.id)));
 assert(!cleanup.job_ids.includes('JOB-FINAL'));assert.equal(await page.locator('#product-jobs-clear-legacy').isVisible(),false);
 await reset({product_preparations:Array.from({length:12},(_,i)=>({id:'JOB-PAGE'+i,product_name:'สินค้าทดสอบ '+i}))});
 assert.equal(await page.locator('.product-source-preparation').count(),5);
 await page.locator('#product-jobs-select-all').check();await accept();await page.locator('#product-jobs-bulk').click();await complete();
 assert.equal((await manageCalls())[0].payload.job_ids.length,5);assert.match(await page.locator('#product-jobs-heading').innerText(),/7$/);
 await page.locator('#product-jobs-more').click();assert.equal(await page.locator('.product-source-preparation').count(),7);
 await page.locator('[data-job-view="hidden"]').click();await page.locator('[data-job-view="pending"]').click();assert.equal(await page.locator('.product-source-preparation').count(),5);

 const many=Array.from({length:201},(_,i)=>({id:'JOB-MANY'+i,product_name:'สินค้าจำนวนมาก '+i}));
 await reset({product_preparations:[...many,{id:'JOB-HIDDEN'},{id:'JOB-LEGACY-EXCLUDED'}],products:[{id:'JOB-DONE',ready:true}],stories:[{id:'STORY-ALL',content_kind:'product',title:'สินค้า'},{id:'STORY-UNRELATED',content_kind:'story'}],product_job_controls:{'JOB-HIDDEN':{hidden:true},'JOB-LEGACY-EXCLUDED':{trashed:true}}});
 await page.locator('.product-jobs-drawer').evaluate(el=>{el.open=false;});
 await accept();
 await page.locator('#product-jobs-clear-all').evaluate(b=>{b.click();ui.state.product_preparations.push({id:'JOB-ARRIVED-LATER'});b.click();});await complete();
 const allCalls=await manageCalls();assert.equal(allCalls.length,1);assert.equal(allCalls[0].payload.scope,'all_pending');assert.equal(allCalls[0].payload.job_ids.length,202);
 for(const id of ['JOB-HIDDEN','JOB-LEGACY-EXCLUDED','JOB-DONE','STORY-UNRELATED','JOB-ARRIVED-LATER'])assert(!allCalls[0].payload.job_ids.includes(id));
 assert.match(await page.locator('#product-jobs-heading').innerText(),/1$/);
 await reset({products:[{id:'JOB-ACK',title:'ผลตอบกลับหาย'}]});await page.evaluate(()=>{slowReads=2;loseAck=true;});await accept();await page.locator('#product-jobs-clear-all').click();
 await page.waitForFunction(()=>calls.some(c=>c.action==='product_jobs_delete_status'));assert.equal(await page.locator('#product-jobs-clear-all').isDisabled(),true);await complete();
 const ackCalls=await page.evaluate(()=>calls);assert.equal(ackCalls.filter(c=>c.action==='product_jobs_manage').length,1);assert(ackCalls.filter(c=>c.action==='product_jobs_delete_status').length>=2);assert(ackCalls.every(c=>c.payload.request_id===ackCalls[0].payload.request_id));

 await reset({products:[{id:'JOB-STATUS',title:'รอตรวจผล'}]});await page.evaluate(()=>{slowReads=1;loseAck=true;failStatus=true;});await accept();await page.locator('#product-jobs-clear-all').click();await settle();
 assert.match(await page.locator('#product-continue-notice').innerText(),/ตรวจผลเดิมไม่สำเร็จ/);assert.doesNotMatch(await page.locator('#product-continue-notice').innerText(),/status connection failed/);assert.equal(await page.locator('#product-jobs-delete-status').isVisible(),true);assert.equal(await page.locator('#product-jobs-clear-all').isDisabled(),true);
 await page.evaluate(()=>{failStatus=false;});await page.locator('#product-jobs-delete-status').click();await complete();assert.equal((await manageCalls()).length,1);
 await reset({products:[{id:'JOB-REJECT',title:'งานมีเจ้าของใหม่'}]});await page.evaluate(()=>{reject=true;});await accept();await page.locator('#product-jobs-clear-all').click();await complete();
 assert.match(await page.locator('#product-continue-notice').innerText(),/โปรแกรมไม่รับคำขอลบ/);assert.doesNotMatch(await page.locator('#product-continue-notice').innerText(),/active job/);assert.equal(await page.locator('#product-jobs-clear-all').isDisabled(),false);
 await reset({products:[{id:'JOB-PART1',title:'ลบได้'},{id:'JOB-PART2',title:'ไฟล์ล็อก'}]});await page.evaluate(()=>{partial=true;});await accept();await page.locator('#product-jobs-clear-all').click();await settle();
 assert.match(await page.locator('#product-continue-notice').innerText(),/1\/2.*ลบไม่สำเร็จ 1 รายการ/);assert.doesNotMatch(await page.locator('#product-continue-notice').innerText(),/fixture file locked/);assert.equal(await page.locator('[data-job-operation="restore"],[data-product-continue]').count(),0);assert.equal((await manageCalls()).length,1);
 await page.evaluate(()=>{reject=true;confirmAnswers.push(true);});await page.locator('#product-jobs-delete-retry').click();await settle();
 assert.equal(await page.locator('#product-jobs-delete-retry').isVisible(),true,'a rejected retry retains the accepted partial batch');
 await page.evaluate(()=>{reject=false;});
 await accept();await page.locator('#product-jobs-delete-retry').click();await complete();const partialCalls=await manageCalls();assert.equal(partialCalls.length,3);assert.deepEqual(partialCalls[0].payload,partialCalls[1].payload);assert.deepEqual(partialCalls[0].payload,partialCalls[2].payload);

 await reset({products:[{id:'JOB-SCREEN',title:'กระเป๋าเดินทางสำหรับวันหยุด',scene_count:4,image_count:4,video_plan_summary:{completed:3,flow:2,meta:1}}],product_preparations:Array.from({length:54},(_,i)=>({id:'JOB-SCREEN-OLD'+i,product_name:'รายการเก่า'})),product_job_controls:Object.fromEntries(Array.from({length:54},(_,i)=>['JOB-SCREEN-OLD'+i,{trashed:true}]))});
 await page.locator('.product-jobs-drawer').evaluate(el=>{el.open=true;});
 for(const width of [390,600,1100,1600]){
  await page.setViewportSize({width,height:1000});const box=await page.locator('.product-continue').boundingBox();
  assert(box.x>=0&&box.x+box.width<=width+1);assert(await page.locator('.product-continue').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
 }
 const card=await page.locator('.product-continue').boundingBox(),form=await page.locator('.create-panel').boundingBox();
 assert(card.x>form.x+form.width);assert(Math.abs(card.y-form.y)<2);assert(card.width<350);assert.equal(await page.locator('#product-link').inputValue(),'https://shopee.co.th/draft-not-submitted');
 if(process.env.SMARTFLOW_UI_SCREENSHOT){await page.screenshot({path:process.env.SMARTFLOW_UI_SCREENSHOT,fullPage:true});await page.locator('.product-continue').screenshot({path:process.env.SMARTFLOW_UI_SCREENSHOT.replace(/\.png$/,'-sidebar.png')});}
 await page.evaluate(()=>sessionStorage.setItem('smartflow.productDeletionRequest',JSON.stringify({request_id:'11111111-1111-4111-8111-111111111111',job_ids:['JOB-RELOAD'],scope:'all_pending'})));
 await page.reload();await page.evaluate(()=>{
  window.ui={state:{product_job_delete_version:1}};window.calls=[];window.escapeHtml=s=>String(s);window.poll=async()=>{};window.toast=()=>{};
  window.postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true,deletion:{request_id:payload.request_id,status:'complete',job_ids:['JOB-RELOAD'],deleted_ids:['JOB-RELOAD'],failed:[]}};};
 });
 await page.addScriptTag({content:fs.readFileSync('web_ui/product_continue.js','utf8')});await complete();
 assert.deepEqual(await page.evaluate(()=>calls),[{action:'product_jobs_delete_status',payload:{request_id:'11111111-1111-4111-8111-111111111111'}}],'reload only reconciles saved request, never deletes again');
 for(const expanded of [true,false]){
  await page.locator('.product-jobs-drawer').evaluate((el,value)=>{el.open=value;},expanded);await page.waitForFunction(value=>localStorage.getItem('smartflow.productJobsExpanded')===String(value),expanded);
  await page.reload();await page.evaluate(()=>{window.ui={state:{}};window.escapeHtml=s=>String(s);});await page.addScriptTag({content:fs.readFileSync('web_ui/product_continue.js','utf8')});
  assert.equal(await page.locator('.product-jobs-drawer').evaluate(el=>el.open),expanded);
 }
 console.log('Product permanent-delete UI passed: actual page + '+styles.length+' CSS, 2 tabs, legacy54 cleanup, source identity, mixed counts, old-backend guard, irreversible confirmation, exact202 IDs, frozen arrivals, busy, slow/lost ACK, read-only status retry, explicit rejection, same-UUID partial retry, draft/persistence, 390/600/1100/1600px.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
