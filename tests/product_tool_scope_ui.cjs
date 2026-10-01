const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>r.abort());
  await page.setContent(read('web_ui/index.html').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
  await page.evaluate(()=>{
   window.$=s=>document.querySelector(s);window.$$=s=>[...document.querySelectorAll(s)];
   window.ui={selectedProductId:'saved',state:{products:[{id:'saved',video_ai_provider:'meta_ai'}]}};
   window.sent=[];window.postAction=async(action,payload)=>sent.push({action,payload});
   window.poll=async()=>{};window.toast=()=>{};window.escapeHtml=String;
  });
  const app=read('web_ui/app.js');
  await page.addScriptTag({content:app.slice(app.indexOf('function productItem('),app.indexOf('function openProductDetail('))});
  await page.addScriptTag({content:app.slice(app.indexOf('function renderProducts('),app.indexOf('function jobOptions('))});
  const handler=app.slice(app.indexOf("  const productTool = event.target.closest('[data-product-tool]');"),app.indexOf('  const openSeries ='));
  await page.addScriptTag({content:`document.addEventListener('click',async event=>{${handler}});`});
  await page.evaluate(()=>renderProducts(ui.state.products));
  assert.equal(await page.locator('[data-product-tool="multi_flow"]').isDisabled(),true);
  await page.evaluate(()=>{
   $('#product-provider').value='gemini';$('#product-video-provider').value='flow';
   $('[data-product-tool="ai_web"]').click();
  });
  assert.deepEqual(await page.evaluate(()=>sent),[{action:'product_tool',payload:{job_id:'saved',tool:'ai_web'}}]);
  await page.evaluate(()=>{ui.state.products[0].video_ai_provider='flow';renderProducts(ui.state.products)});
  assert.equal(await page.locator('[data-product-tool="multi_flow"]').isDisabled(),false);
  assert.equal(await page.locator('#queue-dry,#queue-confirm').count(),0);
  assert.match(await page.locator('#footer-safe').innerText(),/ต้องยืนยันแยก/);
  assert.deepEqual(errors,[]);
  console.log('Product repair: job-id-only payload, provider-scoped controls, no legacy posting safety UI passed.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
