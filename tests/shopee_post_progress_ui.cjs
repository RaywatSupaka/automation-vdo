const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),{chromium}=require('playwright');
const root=path.join(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],actions=[];
  page.on('pageerror',e=>errors.push(e.message));
  const options={schema:1,allow_reuse:false,ai_label:true};
  let state={revision:1,busy:false,account:{name:'fixture'},items:[],defaults:options}, fail=false, staleReply=null;
  state.items=Array.from({length:35},(_,i)=>({id:'r'+i,item_id:'fixture:'+i,title:'คลิปทดสอบ '+i,caption:'Test',product_url:'https://s.shopee.co.th/test',revision:0,phase:'draft',post_options:options}));
  state.items.push({id:'old',title:'Old published',phase:'published',caption:'old',revision:0},{id:'unknown',title:'Unknown',phase:'unknown',caption:'unknown',revision:0,publish_intent:{id:'old'}},{id:'review-sent',title:'Review with intent',phase:'review',caption:'do not repeat',revision:0,publish_intent:{id:'intent'}});
  const html=fs.readFileSync(path.join(root,'web_ui/index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
  function makeRun(id,ids){return {id,status:'running',ids,total:ids.length,completed:0,remaining:ids.length,review_count:0,current_index:1,current_id:ids[0],account:'fixture',phone:'Fixture phone',started_at:Date.now()/1000,updated_at:Date.now()/1000,sequence:0,events:[],message:'checking',current:{id:ids[0],item_id:'fixture:0',title:'คลิปทดสอบ <img src=x onerror=alert(1)>',step:'checking',phase:'checking',message:'กำลังตรวจมือถือ'}};}
  await page.route('http://smartflow.test/**',async route=>{
   const url=new URL(route.request().url());if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   if(url.pathname==='/api/desktop/action'){
    const d=route.request().postDataJSON();actions.push(d);
    if(fail&&d.action==='shopee_post_status')return route.abort();
    if(d.action==='shopee_post_start'){state.busy=true;state.revision++;state.posting_run=makeRun('batch-1',d.payload.ids);state.items.forEach(r=>{if(d.payload.ids.includes(r.id))r.phase='queued';});}
    if(d.action==='shopee_post_reset_unsent'){
     assert.equal(d.payload.run_id,state.posting_run.id);assert.equal(d.payload.revision,state.revision);assert.equal(d.payload.confirm,true);
     const ids=state.restartable_ids;state.revision++;state.busy=false;state.message='ล้างสถานะเดิมแล้ว';
     state.items.forEach(r=>{if(ids.includes(r.id)){r.phase='draft';r.message='พร้อมเริ่มใหม่';}});
     state.posting_run={...makeRun('reset-ready',ids),status:'ready',current:null,current_id:null,current_index:0,finished_at:Date.now()/1000};
    }
    if(d.action==='shopee_post_pause'){assert.equal(d.payload.run_id,state.posting_run.id);state.posting_run.status='pausing';state.posting_run.message='กำลังพักคิว';state.revision++;}
    const reply=staleReply||state;staleReply=null;
    return route.fulfill({json:{ok:true,posting:reply,items:[]}});
   }
   const file=path.join(root,'web_ui',path.basename(url.pathname));
   if(url.pathname.startsWith('/desktop/')&&fs.existsSync(file))return route.fulfill({body:fs.readFileSync(file),contentType:url.pathname.endsWith('.css')?'text/css':'text/javascript'});
   return route.abort();
  });
  await page.goto('http://smartflow.test/');
  await page.evaluate(()=>document.querySelectorAll('.page').forEach(el=>el.classList.toggle('active',el.dataset.view==='queue')));
  await page.addScriptTag({path:path.join(root,'web_ui/shopee_post_progress.js')});await page.addScriptTag({path:path.join(root,'web_ui/shopee_posting.js')});
  await page.locator('[data-row="r0"]').waitFor();
  await page.locator('[data-row="unknown"] [data-reconcile]').click();
  assert.equal(actions.filter(a=>a.action==='shopee_post_reconcile').length,1);
  assert.equal(actions.filter(a=>a.action==='shopee_post_start').length,0,'Evidence recovery must never publish');
  await page.locator('#sp-queue-all').check();
  assert.match(await page.locator('#sp-queue-count').textContent(),/35 \/ 35/);
  assert.equal(await page.locator('[data-queued]:checked').count(),35);
  await page.locator('[data-queued="r1"]').uncheck();assert.equal(await page.locator('#sp-queue-all').evaluate(e=>e.indeterminate),true);
  await page.locator('#sp-queue-all').check();assert.equal(await page.locator('[data-queued]:checked').count(),35);
  await page.locator('[data-sp="clear-queue"]').click();assert.equal(await page.locator('[data-queued]:checked').count(),0);
  await page.locator('#sp-queue-all').check();
  page.once('dialog',d=>{assert.match(d.message(),/35 คลิป/);assert.match(d.message(),/ไม่เปิดโปรไฟล์ตรวจซ้ำ/);d.accept();});await page.locator('[data-sp="start"]').click();
  await page.waitForFunction(()=>document.querySelector('#sp-run-modal').open);
  assert.doesNotMatch(await page.locator('#sp-run-steps').textContent(),/ยืนยันบัญชีครั้งเดียวต่อคิว/);
  assert.doesNotMatch(await page.locator('#sp-run-steps').textContent(),/ตรวจบัญชี \/ โพสต์เดิม/);
  state.posting_run.current.step='restart_app';state.posting_run.current.message='ปิด Shopee เดิมแล้วเปิดใหม่';state.revision++;
  await page.waitForFunction(()=>document.querySelector('.sp-run-steps .current').textContent.includes('ปิด Shopee เดิมแล้วเปิดใหม่'));
  assert.equal(actions.filter(a=>a.action==='shopee_post_start').length,1);assert.equal(actions.find(a=>a.action==='shopee_post_start').payload.ids.length,35);
  assert.equal(await page.locator('#sp-run-done').textContent(),'0');assert.equal(await page.locator('#sp-run-clip img').count(),0);
  state.posting_run.current.step='preflight';state.posting_run.current.message='ตรวจขั้นสุดท้ายก่อนโพสต์';state.revision++;
  await page.waitForFunction(()=>document.querySelector('.sp-run-steps .current').textContent.includes('ตรวจขั้นสุดท้ายก่อนโพสต์'));
  assert.doesNotMatch(await page.locator('.sp-run-steps .current').textContent(),/ตั้งค่าสวิตช์/);
  assert.equal(await page.locator('#sp-run-done').textContent(),'0','Preflight is not publication');
  for(const width of [1440,600,360]){await page.setViewportSize({width,height:900});assert.equal(await page.locator('#sp-run-modal').evaluate(e=>e.scrollWidth>e.clientWidth+2),false);}
  await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('.sp-run-steps .current>span').evaluate(e=>getComputedStyle(e).animationName),'none');
  await page.locator('[data-post-progress="minimize"]').click();assert.equal(await page.locator('#sp-run-pill').isVisible(),true);
  await page.evaluate(()=>document.querySelectorAll('.page').forEach(el=>el.classList.toggle('active',el.dataset.view==='dashboard')));
  const previous=JSON.parse(JSON.stringify(state));state.posting_run.current.step='product';state.posting_run.current.message='กำลังแนบสินค้า';state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-pill-text').textContent.includes('กำลังแนบสินค้า'));
  assert.equal(await page.locator('#sp-run-modal').evaluate(e=>e.open),false);
  staleReply=previous;await page.waitForTimeout(1400);assert.match(await page.locator('#sp-pill-text').textContent(),/กำลังแนบสินค้า/);
  fail=true;await page.waitForTimeout(7200);await page.locator('#sp-run-pill').click();assert.equal(await page.locator('#sp-run-stale').isVisible(),true);assert.equal(await page.locator('#sp-run-done').textContent(),'0');fail=false;
  state.posting_run.current.step='verify';state.posting_run.current.phase='processing';state.posting_run.current.message='ส่งแล้ว กำลังตรวจผล';state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-run-message').textContent.includes('ส่งแล้ว'));
  assert.equal(await page.locator('#sp-run-done').textContent(),'0');
  state.posting_run.completed=1;state.posting_run.remaining=34;state.posting_run.sequence=1;state.posting_run.events=[{id:'r0',title:'คลิปแรก',phase:'published',message:'ตรวจสำเร็จ',at:Date.now()/1000,sequence:1}];state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-run-done').textContent==='1');assert.equal(await page.locator('#sp-run-celebrate').isVisible(),true);
  state.posting_run.status='complete';state.posting_run.completed=35;state.posting_run.remaining=0;state.posting_run.finished_at=Date.now()/1000;state.busy=false;state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-run-title').textContent==='โพสต์ครบแล้ว');
  assert.match(await page.locator('#sp-pill-text').textContent(),/โพสต์ครบแล้ว/);
  state.posting_run=makeRun('batch-2',['next']);state.busy=true;state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-run-done').textContent==='0');await page.waitForTimeout(5300);
  assert.equal(await page.locator('#sp-run-modal').evaluate(e=>e.open),true,'Old completion timer cannot close next run');
  await page.locator('[data-post-progress="pause"]').click();await page.waitForFunction(()=>document.querySelector('#sp-run-title').textContent==='กำลังพักคิว');
  assert.equal(actions.filter(a=>a.action==='shopee_post_pause').length,1);
  state.posting_run.status='review';state.posting_run.review_count=1;state.posting_run.remaining=0;state.posting_run.message='ผลไม่ชัด ต้องตรวจโพสต์เดิม';state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-run-title').textContent.includes('ต้องตรวจผลโพสต์เดิม'));await page.waitForTimeout(5300);
  assert.equal(await page.locator('#sp-run-modal').evaluate(e=>e.open),true,'Review never auto-dismisses');
  state.posting_run.uncertain_count=0;state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-run-title').textContent.includes('ยังไม่ได้โพสต์'));
  assert.match(await page.locator('#sp-run-footer-note').textContent(),/ตัวทำงานหยุดแล้ว/);
  await page.emulateMedia({reducedMotion:'no-preference'});
  assert.equal(await page.locator('.sp-live-dot').evaluate(e=>getComputedStyle(e).animationName),'none');
  assert.equal(await page.locator('.sp-run-steps .current').evaluate(e=>e.classList.contains('stopped')),true,'Same-position running→review must repaint');
  state.posting_run.current.step='review';state.posting_run.current.last_step='baseline';state.revision++;
  await page.waitForFunction(()=>document.querySelector('.sp-run-steps .current').textContent.includes('ตรวจโพสต์เดิม (รอบก่อน)'));
  assert.match(await page.locator('.sp-run-steps .current').textContent(),/หยุดที่:/);
  assert.equal(await page.locator('.sp-run-steps').textContent().then(s=>s.includes('เตรียมหน้าโพสต์')),false,'Old baseline is not new prepare work');
  state.posting_run.current.last_step='account';state.revision++;
  await page.waitForFunction(()=>document.querySelector('.sp-run-steps .current').textContent.includes('ตรวจบัญชี (รอบก่อน)'));
  assert.match(await page.locator('.sp-run-steps .current').textContent(),/หยุดที่:/);
  state.posting_run=makeRun('batch-3',['final']);state.revision++;await page.waitForFunction(()=>document.querySelector('#sp-run-title').textContent==='กำลังโพสต์คลิปของคุณ');
  assert.doesNotMatch(await page.locator('.sp-run-steps').textContent(),/ตรวจบัญชี|ยืนยันบัญชี/);
  state.posting_run.current.waiting_for_device=true;state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-run-title').textContent.includes('รอมือถือพร้อม'));
  assert.equal(await page.locator('.sp-run-steps .current>span').evaluate(e=>getComputedStyle(e).animationName),'none');
  state.posting_run.current.waiting_for_device=false;
  state.posting_run.status='complete';state.posting_run.completed=1;state.posting_run.remaining=0;state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-run-title').textContent==='โพสต์ครบแล้ว');await page.waitForTimeout(5500);
  assert.equal(await page.locator('#sp-run-modal').evaluate(e=>e.open),false);assert.equal(await page.locator('#sp-run-pill').isVisible(),false);
  assert.equal(actions.filter(a=>a.action==='shopee_post_start').length,1,'No replay from polling/minimize/next run');assert.deepEqual(errors,[]);
  // Reproduce 13 published +17 unsent with an old account-stage error. Reset
  // must select only17, show0/17, clear old errors, and never trigger a Post.
  state.busy=false;state.items=Array.from({length:30},(_,i)=>({id:'reset-'+i,item_id:'fixture:'+i,title:'Clip '+i,
   caption:'caption',product_url:'https://s.shopee.co.th/test',revision:0,post_options:options,
   phase:i<13?'published':'review',...(i<13?{publish_intent:{id:'sent-'+i},receipt:{upload_confirmed:true}}:{})}));
  state.restartable_ids=state.items.slice(13).map(r=>r.id);state.message='old stuck error';state.revision++;
  state.posting_run={...makeRun('old-stuck',state.items.map(r=>r.id)),status:'review',completed:13,remaining:17,uncertain_count:0};
  state.posting_run.current.step='review';state.posting_run.current.last_step='account';
  await page.evaluate(()=>document.querySelectorAll('.page').forEach(el=>el.classList.toggle('active',el.querySelector('#shopee-posting')!==null)));
  await page.waitForFunction(()=>document.querySelector('#sp-message').textContent==='old stuck error');
  if(await page.locator('#sp-run-modal').evaluate(e=>e.open))await page.locator('[data-post-progress="minimize"]').click();
  const beforePublished=JSON.stringify(state.items.slice(0,13));
  page.once('dialog',d=>{assert.match(d.message(),/0\/17/);d.accept();});
  await page.locator('[data-sp="reset-unsent"]').click();
  await page.waitForFunction(()=>document.querySelector('#sp-run-title').textContent==='พร้อมเริ่มใหม่ • ยังไม่สั่งโพสต์');
  assert.equal(await page.locator('#sp-run-done').textContent(),'0');assert.equal(await page.locator('#sp-run-left').textContent(),'17');
  assert.equal(await page.locator('#sp-run-steps .current').count(),0);
  assert.equal(await page.locator('[data-queued]:checked').count(),17);
  assert.doesNotMatch(await page.locator('#sp-message').textContent(),/old stuck/);
  assert.equal(JSON.stringify(state.items.slice(0,13)),beforePublished);
  assert.equal(actions.filter(a=>a.action==='shopee_post_start').length,1,'Reset is not Post');
  await page.locator('[data-post-progress="minimize"]').click();
  await page.locator('[data-sp="clear-queue"]').click();
  assert.equal(await page.locator('[data-queued]:checked').count(),0);
  // A ready round restored from the desktop must also restore its selection,
  // not require a second reset click or silently start posting.
  state.posting_run.id='restored-ready';state.revision++;
  await page.waitForFunction(()=>document.querySelectorAll('[data-queued]:checked').length===17);
  assert.equal(actions.filter(a=>a.action==='shopee_post_start').length,1);
  if(await page.locator('#sp-run-modal').evaluate(e=>e.open))await page.locator('[data-post-progress="minimize"]').click();
  page.once('dialog',d=>{assert.match(d.message(),/17 คลิป/);d.accept();});await page.locator('[data-sp="start"]').click();
  await page.waitForFunction(()=>document.querySelector('#sp-run-index').textContent==='คลิปที่ 1 จาก 17');
  assert.equal(actions.filter(a=>a.action==='shopee_post_start').length,2);
  assert.deepEqual(actions.filter(a=>a.action==='shopee_post_start').at(-1).payload.ids,state.restartable_ids);
  // Skipped products finish the round without being counted as publications.
  state.posting_run={...makeRun('with-skips',['one','two']),status:'complete',completed:1,skipped_count:1,remaining:0,finished_at:Date.now()/1000};state.busy=false;state.revision++;
  await page.waitForFunction(()=>document.querySelector('#sp-run-title').textContent.includes('ข้าม 1 สินค้า'));
  assert.equal(await page.locator('#sp-run-done').textContent(),'1');
  assert.match(await page.locator('#sp-run-count-label').textContent(),/ไม่ได้โพสต์/);
  assert.doesNotMatch(await page.locator('#sp-pill-text').textContent(),/โพสต์ครบแล้ว/);
  assert.deepEqual(errors,[]);
  console.log('Progress UI: 35 select-all, exclusions, partial selection, owned popup, cross-page poll, stale response, disconnect, sent!=done, timer ownership, pause, review, auto-close, reduced motion and 1440/600/360 passed. Simulated only.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
