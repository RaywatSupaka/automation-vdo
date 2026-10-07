const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict'),path=require('path'),os=require('os');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100},timezoneId:'America/New_York'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
   if(route.request().resourceType()==='image')return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="90" height="160"><rect width="90" height="160" fill="#204968"/><circle cx="45" cy="55" r="22" fill="#5ee3e7"/><path d="M10 160V105Q45 60 80 105V160" fill="#5960dd"/></svg>'});
   return route.fulfill({contentType:'text/html',body:'<button data-page="facebook">Facebook</button><main style="padding:20px"><section data-view="settings"></section></main>'});
  });
  await page.goto('http://smartflow.test/');
  for(const file of ['web_ui/styles.css','web_ui/facebook_post.css'])await page.addStyleTag({content:fs.readFileSync(file,'utf8')});
  await page.evaluate(()=>{
   window.pageMeta={};window.ui={state:{library:[
    {item_id:'story:P1',content_kind:'product',title:'รีวิวเก้าอี้ ด้วยตัวละคร',kind_label:'สินค้า Shopee'},
    {item_id:'story:P2',content_kind:'product',title:'แก้วเก็บความเย็น',kind_label:'สินค้า Shopee'},
    {item_id:'story:S',content_kind:'story',title:'เรื่องเล่าทดสอบ <img src=x onerror=alert(1)>',kind_label:'Shorts'},
    {item_id:'story:D',content_kind:'drama',title:'ละครทดสอบ',kind_label:'ละครสั้น AI'},
    {item_id:'story:L',content_kind:'story',aspect_ratio:'16:9',title:'คลิปยาวทดสอบ',kind_label:'คลิปยาว'}]}};
   window.showPage=()=>document.querySelector('[data-view="facebook"]').classList.add('active');
   window.confirmations=[];window.allowConfirm=true;window.smartflowConfirm=async t=>{confirmations.push(t);return allowConfirm;};window.calls=[];
   window.fixture={ok:true,page:{id:'123',name:'เพจตัวอย่าง'},posts:[],planner:{rows:[],revision:0,batch:{active:false}}};
   const result=()=>JSON.parse(JSON.stringify(fixture));
   window.fetch=async(url,options)=>{
    const b=JSON.parse(options.body);calls.push(b);const p=b.payload,plan=fixture.planner;
    if(b.action==='facebook_planner_add'){
     assertRevision(p);for(const id of p.ids)if(!plan.rows.some(r=>r.item_id===id)){const item=ui.state.library.find(r=>r.item_id===id);plan.rows.push({id:'row'+plan.rows.length,item_id:id,title:item.title,page_id:'123',page_name:'เพจตัวอย่าง',caption:'ข้อความจากคลัง '+id,status:'draft',scheduled_at:null});}plan.revision++;
    }
    if(b.action==='facebook_planner_edit'){
     assertRevision(p);const rows=plan.rows.filter(r=>p.ids.includes(r.id));
     if(p.preview){return {ok:true,json:async()=>({ok:true,preview:rows.map(r=>({id:r.id,title:r.title,time:'2030-01-01T09:00'}))})};}
     if(p.operation==='save')for(const r of rows){r.caption=p.updates[r.id].caption;r.scheduled_at=p.updates[r.id].time?Date.parse(p.updates[r.id].time+'+07:00')/1000:null;}
     if(p.operation==='spread')rows.forEach((r,i)=>r.scheduled_at=Date.parse(p.start+'+07:00')/1000+i*p.minutes*60);
     if(p.operation==='shift')rows.forEach(r=>r.scheduled_at+=p.minutes*60);
     if(p.operation==='remove')plan.rows=plan.rows.filter(r=>!p.ids.includes(r.id));
     if(p.operation==='move'){const i=plan.rows.findIndex(r=>r.id===p.ids[0]),j=i+p.direction;if(j>=0&&j<plan.rows.length)[plan.rows[i],plan.rows[j]]=[plan.rows[j],plan.rows[i]];}
     plan.revision++;
    }
    if(b.action==='facebook_planner_start'){assertRevision(p);plan.rows.filter(r=>p.ids.includes(r.id)).forEach(r=>r.status='queued');plan.batch.active=true;plan.revision++;}
    if(b.action==='facebook_planner_pause')plan.batch.paused=true;
    if(b.action==='facebook_disconnect')fixture.page=null;
    return {ok:true,json:async()=>result()};
    function assertRevision(p){if(p.revision!==plan.revision)throw Error('stale fixture revision');}
   };
  });
  await page.addScriptTag({content:fs.readFileSync('web_ui/facebook_planner.js','utf8')});
  await page.evaluate(()=>showPage());await page.click('[data-page="facebook"]');
  await page.waitForFunction(()=>document.querySelectorAll('[data-clip]').length===5);
  const idle=()=>page.waitForFunction(()=>!document.querySelector('[data-view="facebook"]').hasAttribute('aria-busy'));
  for(const [value,count] of [['product',2],['story',1],['drama',1],['long',1],['all',5]]){
   await page.selectOption('#fb-category',value);assert.equal(await page.locator('[data-clip]').count(),count);
  }
  assert.equal(await page.locator('[onerror]').count(),0);
  await page.fill('#fb-search','ไม่มีชื่อนี้');assert.equal(await page.locator('[data-clip]').count(),0);await page.fill('#fb-search','');
  await page.fill('#fb-random-count','3');await page.click('#fb-random');assert.equal(await page.locator('[data-clip]:checked').count(),3);
  await page.click('#fb-unselect');await page.selectOption('#fb-category','product');await page.click('#fb-select-visible');
  await page.click('#fb-add');await idle();assert.equal(await page.locator('[data-row]').count(),2);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='facebook_planner_start').length),0);
  await page.click('#fb-check-drafts');await page.fill('#fb-start','2030-01-01T09:00');await page.click('#fb-spread');await idle();
  let times=await page.locator('[data-time]').evaluateAll(es=>es.map(e=>e.value));assert.deepEqual(times,['2030-01-01T09:00','2030-01-02T09:00']);
  await page.click('[data-shift="30"]');await idle();times=await page.locator('[data-time]').evaluateAll(es=>es.map(e=>e.value));assert.deepEqual(times,['2030-01-01T09:30','2030-01-02T09:30']);
  await page.locator('[data-caption]').first().fill('แก้ข้อความเอง');await page.click('#fb-save');await idle();
  assert.equal(await page.evaluate(()=>fixture.planner.rows[0].caption),'แก้ข้อความเอง');
  await page.evaluate(()=>allowConfirm=false);await page.click('#fb-schedule');await idle();assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='facebook_planner_start').length),0);
  await page.evaluate(()=>allowConfirm=true);
  // Preserve a dirty draft during refresh cancellation.
  await page.locator('[data-caption]').first().fill('ยังไม่บันทึก');await page.evaluate(()=>allowConfirm=false);
  await page.click('#fb-refresh');await idle();assert.equal(await page.locator('[data-caption]').first().inputValue(),'ยังไม่บันทึก');
  await page.evaluate(()=>allowConfirm=true);await page.click('#fb-save');await idle();
  await page.locator('[data-preview]').first().click();assert(await page.locator('#fb-preview').isVisible());await page.click('#fb-close-preview');assert(!(await page.locator('#fb-preview').isVisible()));
  const out=process.env.FACEBOOK_UI_CAPTURE_DIR;
  if(out)fs.mkdirSync(out,{recursive:true});
  for(const width of [1440,600,360]){
   await page.setViewportSize({width,height:1100});await page.evaluate(()=>window.scrollTo(0,0));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'outer overflow at '+width);
   if(out)await page.screenshot({path:path.join(out,'planner-'+width+'.png'),fullPage:true});
  }
  await page.click('#fb-schedule');await idle();
  const start=await page.evaluate(()=>calls.filter(c=>c.action==='facebook_planner_start'));
  assert.equal(start.length,1);assert.equal(start[0].payload.mode,'schedule');assert.equal(start[0].payload.page_id,'123');assert.equal(start[0].payload.ids.length,2);
  await page.click('#fb-pause');await idle();assert(await page.evaluate(()=>fixture.planner.batch.paused));
  assert.equal(await page.locator('[data-row-check]:enabled').count(),0);
  await page.locator('.fb-connection summary').click();await page.fill('#fb-token','FAKE-TOKEN');await page.click('#fb-connect');await idle();
  assert.equal(await page.locator('#fb-token').inputValue(),'');assert(!await page.locator('body').innerText().then(x=>x.includes('FAKE-TOKEN')));
  assert.deepEqual(errors,[]);
  console.log('Facebook Planner actual-source UI: 5 categories, safe text, search/random/check, add, draft, spread, shift, cancel confirmation, preview, 3 widths, explicit batch/pause, token cleared passed; no real network.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
