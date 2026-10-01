// Native DOM regression: real page/modal markup and click handlers, no bridge or provider.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const source = file => fs.readFileSync(path.join(root, 'web_ui', file), 'utf8');

(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.SMARTFLOW_TEST_CHROMIUM ? {executablePath:process.env.SMARTFLOW_TEST_CHROMIUM} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1366, height:900}});
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {requests.push(route.request().url()); return route.abort();});
    await page.setContent(source('index.html')
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
      .replace(/<link\b[^>]*>/gi, ''));
    for (const file of ['styles.css', 'creation_queue.css', 'media_audio.css'])
      await page.addStyleTag({content:source(file)});
    await page.addScriptTag({content:`
      const $=(selector,root=document)=>root.querySelector(selector);
      const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
      const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const ui={state:{},aiModelDrafts:{}},calls=[],notices=[];
      let postAction=async(action,payload)=>{calls.push({action,payload});throw new Error('Unexpected action in editor-only test');};
      const toast=(message,kind)=>notices.push({message,kind}),poll=async()=>{};
      const showPage=name=>$$('[data-view]').forEach(node=>node.classList.toggle('active',node.dataset.view===name));
    `});
    // These are the actual model helpers; selector misses always remain native nulls.
    const app = source('app.js');
    const helperStart = app.indexOf('const fallbackAiModelOptions =');
    const helperEnd = app.indexOf('function bindAiModelSelect(', helperStart);
    assert(helperStart >= 0 && helperEnd > helperStart);
    await page.addScriptTag({content:app.slice(helperStart, helperEnd)});
    await page.addScriptTag({content:source('creation_queue.js')});
    await page.addScriptTag({content:source('media_audio.js')});
    await page.evaluate(() => {
      $('#product-link').value='https://s.shopee.co.th/EDITOR-FIXTURE';
      $('#product-provider').value='gemini';
      fillAiModelSelect('#product-provider','#product-model','flash');
      setMediaAudioChoice('product',{mode:'api',subtitle:true,music:true,sfx:false,keep_video_audio:false,video_audio_volume:35});
      showPage('creation');
    });
    assert.deepEqual(errors, [], 'The actual queue and audio modules must initialize');

    await page.locator('#queue-add-products').click();
    const firstOpen = await page.locator('#creation-editor').evaluate(node => node.open);
    assert.equal(firstOpen, true,
      `+ product links must open the real dialog; native page errors: ${JSON.stringify(errors)}`);
    assert.deepEqual(errors, []);
    assert.equal(await page.locator('#creation-values').inputValue(), 'https://s.shopee.co.th/EDITOR-FIXTURE');
    assert.equal(await page.locator('#creation-product-provider').inputValue(), 'gemini');
    assert.equal(await page.locator('#creation-product-model').inputValue(), 'flash');
    assert.equal(await page.locator('#creation-product-settings').evaluate(node => node.open), false);
    const extras = page.locator('#creation-product-extra-settings');
    assert.equal(await extras.count(), 1, 'The collapse target must exist exactly once in actual modal markup');
    assert.equal(await extras.evaluate(node => node.open), false);
    assert.equal(await extras.locator('.media-audio-controls').count(), 1, 'Move the actual audio panel into extras');
    await extras.locator(':scope > summary').click();
    assert.equal(await extras.evaluate(node => node.open), true);
    assert.equal(await extras.locator('[data-audio-music]').isVisible(), true);
    assert.equal(await extras.locator('[data-audio-music]').isChecked(), true);
    assert.equal(await extras.locator('[data-audio-subtitle]').isChecked(), true);
    await page.locator('#creation-editor-close').click();
    assert.equal(await page.locator('#creation-editor').evaluate(node => node.open), false);

    await page.locator('#queue-add-products').click();
    assert.equal(await page.locator('#creation-editor').evaluate(node => node.open), true);
    assert.equal(await extras.evaluate(node => node.open), false, 'Every new opening resets expanded extras');
    if (process.env.QUEUE_EDITOR_SCREENSHOT)
      await page.screenshot({path:process.env.QUEUE_EDITOR_SCREENSHOT});
    await page.locator('#creation-editor-close').click();
    await page.evaluate(() => showPage('products'));
    await page.locator('#enqueue-product').click();
    assert.equal(await page.locator('#creation-editor').evaluate(node => node.open), true,
      'The Product page entry uses the same working modal');
    await page.locator('#creation-editor-close').click();

    await page.evaluate(() => {
      ui.state={creation_queue:{paused:true,counts:{queued:1},items:[{
        queue_id:'CQ-EDITOR-FIXTURE',job_id:'',status:'queued',mode:'product',
        link:'https://s.shopee.co.th/SAVED-EDITOR-FIXTURE',provider:'gemini',ai_web_model:'pro',
        video_generation_mode:'meta_ai',scene_count:8,
        settings:{audio_choices:{mode:'none',subtitle:false,music:false,sfx:false,video_audio_volume:35}}
      }]}};
      window.fixtureQueueBefore=JSON.stringify(ui.state);
      renderCreationQueue(ui.state);showPage('creation');
    });
    await page.locator('[data-cq="edit"][data-id="CQ-EDITOR-FIXTURE"]').click();
    assert.equal(await page.locator('#creation-editor').evaluate(node => node.open), true);
    assert.match(await page.locator('#creation-editor-title').textContent(), /แก้ไขรายการ/);
    assert.equal(await page.locator('#creation-values').inputValue(), 'https://s.shopee.co.th/SAVED-EDITOR-FIXTURE');
    assert.equal(await page.locator('#creation-product-settings').evaluate(node => node.hidden), true);
    assert.deepEqual(await page.evaluate(() => mediaAudioChoice('product-batch')),
      {mode:'none',subtitle:false,music:false,sfx:false,allow_silent:false,keep_video_audio:false,video_audio_volume:35});
    await page.locator('#creation-editor-close').click();

    await page.evaluate(() => {window.productPreparationActive=true;});
    for (const selector of ['#queue-add-products','[data-cq="edit"][data-id="CQ-EDITOR-FIXTURE"]']) {
      await page.locator(selector).click();
      assert.equal(await page.locator('#creation-editor').evaluate(node => node.open), false);
    }
    await page.evaluate(() => showPage('products'));
    await page.locator('#enqueue-product').click();
    assert.equal(await page.locator('#creation-editor').evaluate(node => node.open), false);
    assert.equal(await page.evaluate(() => notices.length), 3, 'Existing preparation guard must block all three entry paths');
    await page.evaluate(() => {window.productPreparationActive=false;showPage('creation');});
    await page.locator('#queue-add-products').click();
    assert.equal(await page.locator('#creation-editor').evaluate(node => node.open), true,
      'Opening recovers after the existing preparation guard clears');
    await page.locator('#creation-editor-close').click();
    assert.equal(await page.evaluate(() => JSON.stringify(ui.state)===fixtureQueueBefore), true);
    assert.deepEqual(await page.evaluate(() => calls), [], 'Opening and cancelling must never dispatch a queue action');
    assert.deepEqual(requests, [], 'No browser network or live bridge requests');
    assert.deepEqual(errors, [], 'All entry paths must be free of native DOM errors');
    console.log('PASS native Product editor: queue/Product entry, saved edit, reopen/collapse, actual audio controls, preparation guard, zero actions/network; browser closed');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error);process.exitCode=1;});
