// Actual native export UI block, mocked desktop transport, no customer app.
const fs=require('fs'), assert=require('assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('web_ui/studio.js','utf8');
const start=source.indexOf('    if (review.scenes?.length) {');
const end=source.indexOf('\n  async function openReview', start);
const block=source.slice(start,end).replace(/\n  }\s*$/, '');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try {
    const page=await browser.newPage();
    await page.setContent('<div id="studio-review-body"></div>');
    await page.addScriptTag({content:`const $=s=>document.querySelector(s);const el=(tag,c,html='')=>{const n=document.createElement(tag);n.className=c;n.innerHTML=html;return n;};const review={job_id:'STORY-TEST',scenes:[{}]};window.calls=[];window.toast=()=>{};window.postAction=async(action,payload)=>{calls.push({action,payload});return {state:{job_id:review.job_id,status:'complete',message:'พร้อม',silent_scenes:[],result:{output:'test.mp4'}}};};${block}`});
    assert.equal(await page.locator('[data-native-music]').isChecked(),false);
    assert.equal(await page.locator('[data-native-silent]').isChecked(),false);
    await page.locator('.studio-native-extra > summary').click();
    await page.locator('[data-native-export]').click();
    await page.waitForFunction(()=>document.querySelector('[data-native-status]').textContent.includes('test.mp4'));
    const calls=await page.evaluate(()=>window.calls);
    assert.deepEqual(calls[0],{action:'story_native_export',payload:{job_id:'STORY-TEST',music:false,allow_silent:false}});
    await page.locator('[data-native-music]').check();await page.locator('[data-native-silent]').check();
    await page.locator('[data-native-export]').click();
    await page.waitForFunction(()=>calls.filter(c=>c.action==='story_native_export').length===2);
    assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='story_native_export')[1].payload.allow_silent),true);
    await page.locator('[data-native-cancel]').click();
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.job_id),'STORY-TEST');
    console.log('PASS: actual native UI defaults, export payload, consent, progress, owner-bound cancellation. Browser closed.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
