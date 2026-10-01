/* Headless, local files only. Does not connect to or launch SmartFlow. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../..');
const entry=pathToFileURL(path.join(__dirname,'index.html')).href;
async function main(){
 const browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1,serviceWorkers:'block'});
  await context.route('**/*',route=>route.request().url().startsWith('file:')?route.continue():route.abort());
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const snap=async(name)=>{
   await page.evaluate(()=>document.fonts.ready);
   await page.evaluate(()=>{window.captureAnimations=document.getAnimations().filter(a=>a.playState==='running');window.captureAnimations.forEach(a=>{a.pause();a.currentTime=1900;});});
   const modalOpen=await page.evaluate(()=>Boolean(document.querySelector('dialog[open]')));
   // A backdrop covers the viewport, not off-screen document content.
   await page.screenshot({path:path.join(__dirname,name),fullPage:!modalOpen});
   await page.evaluate(()=>window.captureAnimations.forEach(a=>a.play()));
  };
  await page.goto(entry);await snap('01-workspace.png');
  const brand=await page.locator('.brand img').evaluate(img=>({fit:getComputedStyle(img).objectFit,natural:[img.naturalWidth,img.naturalHeight],width:img.clientWidth,height:img.clientHeight}));
  assert.equal(brand.fit,'contain');assert.ok(brand.natural[0]>1000);
  await page.getByRole('button',{name:'ดูความคืบหน้า',exact:false}).click();
  await page.locator('#progress-dialog').waitFor({state:'visible'});await page.waitForTimeout(350);await snap('02-progress-video.png');
  const backdrop=await page.locator('#progress-dialog').evaluate(el=>({modal:el.matches(':modal'),blur:getComputedStyle(el,'::backdrop').backdropFilter,background:getComputedStyle(el,'::backdrop').backgroundColor,height:innerHeight}));
  assert.ok(backdrop.modal);assert.equal(backdrop.blur,'blur(12px)');
  await page.locator('[data-state-button="attention"]').click();assert.ok(await page.locator('#attention-action').isVisible());assert.equal(await page.locator('#percent').textContent(),'36%');await snap('03-needs-attention.png');
  await page.locator('[data-state-button="paused"]').click();assert.ok(await page.locator('#demo-cancel').isDisabled());assert.equal(await page.locator('.motion-art[data-state="paused"] .particles i').first().evaluate(el=>getComputedStyle(el).animationName),'none');
  await page.locator('[data-state-button="video"]').click();await page.keyboard.press('Escape');assert.ok(await page.locator('#floating-progress').isVisible());assert.ok(!await page.locator('#progress-dialog').isVisible());
  await page.locator('#floating-progress').click();await page.locator('[data-state-button="complete"]').click();assert.ok(!await page.locator('#progress-dialog').isVisible());assert.ok(await page.getByRole('status').last().isVisible());
  await page.goto(entry+'?view=extension');await page.waitForTimeout(350);await snap('04-extension-panel.png');assert.equal(await page.locator('#extension-dialog details[open]').count(),0);
  await page.goto(entry+'?view=states');await snap('05-motion-states.png');
  await page.setViewportSize({width:390,height:844});await page.goto(entry+'?view=progress');await page.waitForTimeout(350);await snap('06-mobile-progress.png');
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile horizontal overflow');
  const mobile=await page.locator('#progress-dialog').boundingBox();assert.ok(mobile.x>=0&&mobile.width<=390&&mobile.y>=0&&mobile.y+mobile.height<=845);
  await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('.art-core').first().evaluate(el=>getComputedStyle(el).animationName),'none');
  await page.emulateMedia({reducedMotion:'no-preference'});await page.setViewportSize({width:1366,height:768});await page.goto(entry+'?view=progress');await snap('07-1366-progress.png');
  const small=await page.locator('#progress-dialog').boundingBox();assert.ok(small.height<=768&&small.y>=0);
  // Reproduce only the relevant shipped CSS cascade with a synthetic modal.
  // Production app.js is never loaded and no API is contacted.
  const sourceCSS=['styles.css','workspace.css','usability.css'].map(file=>fs.readFileSync(path.join(root,'web_ui',file),'utf8')).join('\n');
  await page.setViewportSize({width:1890,height:995});await page.setContent(`<style>${sourceCSS}</style><main style="height:1400px;background:repeating-linear-gradient(0deg,#52677f 0 30px,#d0a876 30px 60px)"></main><dialog class="modal" id="legacy"><div class="modal-card progress-card">Synthetic CSS reproduction</div></dialog>`);
  await page.evaluate(()=>document.querySelector('#legacy').showModal());
  const legacy=await page.locator('#legacy').evaluate(el=>({height:el.getBoundingClientRect().height,viewport:innerHeight,maxHeight:getComputedStyle(el).maxHeight,backdrop:getComputedStyle(el,'::backdrop').backgroundColor,blur:getComputedStyle(el).backdropFilter}));
  assert.ok(Math.abs(legacy.height-995*.94)<1);assert.equal(legacy.backdrop,'rgba(0, 0, 0, 0)');
  assert.equal(errors.length,0,errors.join('\n'));
  console.log(JSON.stringify({pass:true,sourceCssReproduction:legacy,prototypeBackdrop:backdrop,originalLogo:brand,checks:['full logo contained','top-layer blur','state switch','attention CTA','pause stops motion','Escape minimizes only','restore','Final closes modal','extension details collapsed','390px no overflow','1366x768 fit','reduced motion','zero page errors','no network or app actions']}));
  await context.close();
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
