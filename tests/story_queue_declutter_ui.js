const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const html = fs.readFileSync('web_ui/index.html', 'utf8');
  const app = fs.readFileSync('web_ui/app.js', 'utf8');
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // Isolated HTML/actual controllers only. No user bridge, browser or provider.
    await page.route('**/*', route => route.abort());
    await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '').replace(/<link\b[^>]*>/gi, ''));
    for (const file of ['styles.css','creation_queue.css','creator_ux.css']) {
      if (fs.existsSync(`web_ui/${file}`)) await page.addStyleTag({content:fs.readFileSync(`web_ui/${file}`,'utf8')});
    }
    await page.addScriptTag({content:`
      const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
      const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const calls=[],ui={state:{}},toast=()=>{},poll=async()=>{};
      const postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true};};
      const showPage=name=>$$('[data-view]').forEach(node=>node.classList.toggle('active',node.dataset.view===name));
      const videoSourcePresentation=()=>({label:'Google Flow'});
      document.addEventListener('click',event=>{const b=event.target.closest('[data-page]');if(b)showPage(b.dataset.page);});
      ${app.slice(app.indexOf('let storyRecoveryClearing ='),app.indexOf('let dramaQueuePending'))}
    `});
    await page.addScriptTag({content:fs.readFileSync('web_ui/creation_queue.js','utf8')});
    await page.evaluate(() => {
      const done = Array.from({length:68},(_,i)=>({queue_id:'DONE-'+i,job_id:'STORY-DONE-'+i,status:'completed',mode:'story',topic:'งานสำเร็จ '+i}));
      ui.state = {creation_queue:{paused:true,can_clear_stuck_state:true,items:[...done,
        {queue_id:'EMPTY',status:'cancelled',mode:'story',topic:'ยกเลิกก่อนเริ่ม'},
        {queue_id:'OLD',job_id:'STORY-OLD',status:'cancelled',mode:'story',topic:'งานเก่า',finished_at:'2026-09-19'},
        {queue_id:'PHILIPS',job_id:'STORY-PHILIPS',status:'cancelled',mode:'story',scene_count:7,topic:'Philips งานที่หยุดไว้',finished_at:'2026-09-20'}
      ],counts:{completed:68,cancelled:3},recoverable_jobs:[]},story_progress:{active:false}};
      window.originalQueue = JSON.stringify(ui.state.creation_queue);
      renderStories([{id:'STORY-OUTSIDE',title:'เรื่องเก่า',status:'error'}]);
      renderCreationQueue(ui.state);
      showPage('story');
    });
    assert.equal(await page.locator('#story-queue-panel').count(),0);
    assert.equal(await page.locator('#story-recovery-details').getAttribute('open'),null);
    if(process.env.STORY_SHORTS_SCREENSHOT) {
      await page.setViewportSize({width:1440,height:1000});
      await page.locator('.story-queue-link').scrollIntoViewIfNeeded();
      await page.screenshot({path:process.env.STORY_SHORTS_SCREENSHOT});
    }
    await page.locator('.story-queue-link [data-page="creation"]').click();
    assert.equal(await page.locator('[data-view="creation"]').isVisible(),true);
    assert.equal(await page.locator('.cq-recovery').getAttribute('open'),null);
    assert.equal(await page.locator('#creation-list .cq-row').count(),2);
    assert.match(await page.locator('#creation-list .cq-row').first().textContent(),/Philips/);
    await page.locator('[data-cq="retry"][data-id="PHILIPS"]').click();
    assert.deepEqual(await page.evaluate(()=>calls),[{action:'creation_retry',payload:{queue_id:'PHILIPS',direction:0}}]);
    assert.equal(await page.evaluate(()=>JSON.stringify(ui.state.creation_queue)===originalQueue),true);
    await page.evaluate(()=>{ui.state.story_progress={active:true,job_id:'STORY-OTHER'};renderCreationQueue(ui.state);});
    assert.equal(await page.locator('[data-cq="retry"][data-id="PHILIPS"]').isDisabled(),true);
    await page.evaluate(()=>{ui.state.story_progress.active=false;renderCreationQueue(ui.state);});
    assert.equal(await page.locator('[data-cq="retry"][data-id="PHILIPS"]').isEnabled(),true);
    await page.selectOption('#creation-status-filter','completed');
    assert.equal(await page.locator('#creation-list .cq-row').count(),68);
    await page.selectOption('#creation-status-filter','all');
    assert.equal(await page.locator('#creation-list .cq-row').count(),71);
    await page.selectOption('#creation-filter','product');
    assert.equal(await page.locator('#creation-list .cq-row').count(),0);
    assert.match(await page.locator('#creation-list').textContent(),/ไม่มีรายการถูกลบ/);
    await page.selectOption('#creation-filter','all');
    await page.selectOption('#creation-status-filter','unfinished');
    for (const width of [1440,600,360]) {
      await page.setViewportSize({width,height:1000});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`overflow ${width}`);
      if(process.env.STORY_QUEUE_SCREENSHOT && width===1440) await page.screenshot({path:process.env.STORY_QUEUE_SCREENSHOT});
    }
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({ok:true,cases:14,providerSends:0}));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
