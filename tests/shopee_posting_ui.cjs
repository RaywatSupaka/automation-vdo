const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.join(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();const sent=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let state={revision:0,busy:false,items:[],defaults:{schema:1,allow_reuse:false,ai_label:true},account:{name:'testuser'},auto_available:true};
  const item={item_id:'story:STORY-TEST',title:'เสื้อ Anata <script>window.bad=true</script>',product_url:'https://s.shopee.co.th/test'};
  const html=fs.readFileSync(path.join(root,'web_ui/index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
  await page.route('http://smartflow.test/**',async route=>{
   const url=new URL(route.request().url());
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   if(url.pathname==='/api/desktop/action'){
    const d=route.request().postDataJSON();sent.push(d);
    if(d.action==='shopee_post_add'){state.revision++;state.items=[{...item,id:'test-row',caption:'เสื้อ Anata',phase:'draft',revision:0,message:'รอตรวจ',post_options:{...state.defaults}}];}
    if(d.action==='shopee_post_edit'){Object.assign(state.items[0],d.payload,{revision:state.items[0].revision+1});state.revision++;}
    if(d.action==='shopee_post_defaults'){state.defaults={...d.payload.post_options};state.revision++;}
    if(d.action==='shopee_post_apply_options'){for(const x of state.items)if(d.payload.ids.includes(x.id)){x.post_options={...d.payload.post_options};x.revision++;}state.revision++;}
    if(d.action==='shopee_post_start'){state.items[0].phase='queued';state.revision++;state.busy=true;}
    return route.fulfill({json:{ok:true,posting:state,items:[item]}});
   }
   const file=path.join(root,'web_ui',path.basename(url.pathname));
   if(url.pathname.startsWith('/desktop/')&&fs.existsSync(file))return route.fulfill({body:fs.readFileSync(file),contentType:url.pathname.endsWith('.css')?'text/css':'text/javascript'});
   return route.abort();
  });
  await page.goto('http://smartflow.test/');
  await page.evaluate(()=>{window.confirmAnswers=[];window.confirmMessages=[];window.smartflowConfirm=async message=>{confirmMessages.push(message);return confirmAnswers.shift()??false;};});
  assert.equal(await page.locator('#queue-dry,#queue-confirm').count(),0,'Legacy safety controls must not imply new posting is a dry run');
  await page.evaluate(()=>document.querySelectorAll('.page').forEach(el=>el.classList.toggle('active',el.dataset.view==='queue')));
  await page.addScriptTag({path:path.join(root,'web_ui/shopee_posting.js')});
  await page.locator('[data-sp="refresh"]').click();
  await page.locator('[data-pick]').waitFor();
  assert.equal(await page.evaluate(()=>window.bad),undefined);
  await page.locator('[data-pick]').check();
  assert.equal(sent.filter(x=>x.action==='shopee_post_start').length,0);
  await page.locator('[data-sp="add"]').click();await page.locator('[data-queued]').waitFor();
  await page.locator('[data-queued]').check();
  await page.locator('[data-caption]').fill('ทดสอบไทย 😀');
  await page.locator('[data-sp="start"]').click();
  assert.equal(sent.filter(x=>x.action==='shopee_post_start').length,0,'Unsaved caption must block publishing');
  assert.equal(await page.locator('[data-caption]').inputValue(),'ทดสอบไทย 😀');
  await page.locator('[data-save]').click();
  await page.waitForFunction(()=>document.querySelector('[data-row]').dataset.revision==='1');
  assert.equal(sent.find(x=>x.action==='shopee_post_edit').payload.caption,'ทดสอบไทย 😀');
  assert.deepEqual(sent.find(x=>x.action==='shopee_post_edit').payload.post_options,{schema:1,allow_reuse:false,ai_label:true,allow_missing_controls:true});
  assert.equal(await page.locator('[data-option="allow_missing_controls"]').isChecked(),true);
  await page.locator('#sp-default-reuse').check();
  await page.locator('[data-sp="start"]').click();
  assert.equal(sent.filter(x=>x.action==='shopee_post_start').length,0,'Unsaved defaults block start');
  await page.locator('[data-sp="save-defaults"]').click();
  assert.equal(sent.find(x=>x.action==='shopee_post_defaults').payload.post_options.allow_reuse,true);
  assert.equal(await page.locator('[data-option="allow_reuse"]').isChecked(),false,'New defaults do not mutate row');
  await page.evaluate(()=>confirmAnswers.push(true));await page.locator('[data-sp="apply-options"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-option="allow_reuse"]').checked);
  assert.deepEqual(sent.find(x=>x.action==='shopee_post_apply_options').payload.ids,['test-row']);
  await page.locator('[data-option="ai_label"]').uncheck();
  await page.locator('[data-sp="start"]').click();
  assert.equal(sent.filter(x=>x.action==='shopee_post_start').length,0,'Unsaved row options block start');
  await page.locator('[data-save]').click();
  assert.equal(sent.filter(x=>x.action==='shopee_post_edit').at(-1).payload.post_options.ai_label,false);
  await page.locator('[data-option="allow_missing_controls"]').uncheck();
  await page.locator('[data-sp="start"]').click();
  assert.equal(sent.filter(x=>x.action==='shopee_post_start').length,0,'Unsaved availability policy blocks Start');
  await page.locator('[data-save]').click();
  assert.equal(sent.filter(x=>x.action==='shopee_post_edit').at(-1).payload.post_options.allow_missing_controls,false);
  await page.evaluate(()=>confirmAnswers.push(false));await page.locator('[data-sp="start"]').click();
  assert.equal(sent.filter(x=>x.action==='shopee_post_start').length,0);
  await page.evaluate(()=>confirmAnswers.push(true));await page.locator('[data-sp="start"]').click();assert.match(await page.evaluate(()=>confirmMessages.at(-1)),/โพสต์จริง/);assert.match(await page.evaluate(()=>confirmMessages.at(-1)),/ใช้ซ้ำ: เปิด • ป้าย AI: ปิด/);
  assert.equal(sent.filter(x=>x.action==='shopee_post_start').length,1);
  assert.equal(sent.find(x=>x.action==='shopee_post_start').payload.confirm,true);
  await page.waitForFunction(()=>!document.querySelector('[data-sp="pause"]').disabled);
  assert.equal(await page.locator('[data-sp="start"]').isDisabled(),true);
  assert.equal(await page.locator('[data-sp="pause"]').isEnabled(),true);
  for(const width of [1440,600,360]){
   await page.setViewportSize({width,height:1000});
   const overflow=await page.locator('#shopee-posting').evaluate(el=>el.scrollWidth>el.clientWidth+2);
   assert.equal(overflow,false,'Panel overflow '+width);
  }
  assert.deepEqual(errors,[]);console.log('Shopee actual-source UI: defaults, selected options, frozen confirm, Unicode, unsaved guard, busy/pause, 1440/600/360 passed. No phone actions.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
