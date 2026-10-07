// Isolated real desktop markup and styles. No bridge, provider or customer data.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1360,height:860}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => route.abort());
    const html = fs.readFileSync('web_ui/index.html','utf8')
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
    await page.setContent(html);
    for (const file of ['styles.css','creation_queue.css','foundation.css','jobs_page.css']) {
      await page.addStyleTag({content:fs.readFileSync(`web_ui/${file}`,'utf8')});
    }
    await page.addScriptTag({content:`
      const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
      const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const calls=[],ui={state:{}},toast=()=>{},poll=async()=>{},restoreProgress=()=>{window.progressOpened=true};
      const postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true};};
      const showPage=name=>{window.lastPage=name;$$('[data-view]').forEach(n=>n.classList.toggle('active',n.dataset.view===name));};
    `});
    await page.addScriptTag({content:fs.readFileSync('web_ui/status_vocabulary.js','utf8')});
    await page.addScriptTag({content:fs.readFileSync('web_ui/creation_queue.js','utf8')});
    await page.evaluate(() => {
      ui.state = {creation_queue:{paused:true,pause_reason:'job_needs_attention',counts:{queued:1,running:1,failed:1,completed:1},items:[
        {queue_id:'CQ-RUN',job_id:'JOB-RUN',mode:'story',status:'running',topic:'กำลังทำ'},
        {queue_id:'CQ-FAIL',job_id:'JOB-FAIL',mode:'product',status:'failed',topic:'สะดุด',scene_count:8,error:'Traceback: secret'},
        {queue_id:'CQ-QUEUE',mode:'product',status:'queued',topic:'รอคิว',scene_count:5},
        {queue_id:'CQ-DONE',job_id:'JOB-DONE',mode:'story',status:'completed',topic:'เสร็จแล้ว'}
      ]},story_progress:{active:true,job_id:'JOB-RUN',percent:33,message:'กำลังสร้างภาพ'},
      products:[{id:'PRODUCT-OLD',title:'สินค้าค้าง',status:'paused',scene_count:6,image_count:2}],
      stories:[{id:'STORY-OLD',title:'เรื่องเก่า',status:'failed',video_status:'pending'}],
      drama_series:{items:[{id:'SERIES-1',title:'ละครหนึ่ง',status:'queued',episode_count:3,episodes:[]}]}};
      renderCreationQueue(ui.state);showPage('creation');
    });
    assert.match(await page.locator('#creation-hint').textContent(),/มีงานรอคุณ/);
    assert.equal(await page.locator('.job-row').count(),6);
    assert.equal(await page.locator('.job-row .jobs-primary').count(),6);
    assert.equal(await page.locator('.job-row [data-cq="remove"].jobs-primary').count(),0);
    assert.match(await page.locator('[data-id="CQ-FAIL"]').first().locator('xpath=ancestor::article').textContent(),/8 ฉาก/);
    assert.doesNotMatch(await page.locator('#creation-list').textContent(),/Traceback|secret|3 ช็อต|Run Queue/);
    assert.equal(await page.locator('#jobs-filters [data-jobs-filter="attention"] span').textContent(),'2');
    await page.locator('[data-product-in-jobs="PRODUCT-OLD"]').click();
    assert.equal(await page.evaluate(() => window.lastPage),'products');
    await page.evaluate(() => showPage('creation'));
    await page.locator('#jobs-filters [data-jobs-filter="done"]').click();
    assert.equal(await page.locator('#creation-list .job-row').count(),1);
    assert.equal(await page.locator('#creation-other-jobs .job-row').count(),0);
    await page.locator('#jobs-filters [data-jobs-filter="open"]').click();
    await page.locator('#creation-list .job-row').first().locator('.jobs-primary').click();
    assert.equal(await page.evaluate(() => window.progressOpened),true);
    const heights=await page.locator('.job-row .jobs-primary, .jobs-filter, .jobs-more summary').evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().height));
    assert(Math.min(...heights)>=44,`job controls too small: ${Math.min(...heights)}`);
    const contrast=await page.locator('.job-row .sf-status').evaluateAll(nodes=>{
      const luminance = value => { const values=value.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*values[0]+.7152*values[1]+.0722*values[2]; };
      return nodes.map(node=>{const style=getComputedStyle(node),a=luminance(style.color),b=luminance(style.backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)});
    });
    assert(Math.min(...contrast)>=4.5,`status contrast too low: ${Math.min(...contrast)}`);
    if (process.env.JOBS_PAGE_SCREENSHOT) {
      await page.waitForTimeout(1100);
      await page.screenshot({path:process.env.JOBS_PAGE_SCREENSHOT,fullPage:true});
    }
    assert.equal(await page.evaluate(() => calls.length),0);
    assert.deepEqual(errors,[]);
    console.log('Jobs page: six shared rows, one primary each, filters, truthful scenes, pause reason, safe detail and 44px controls passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
