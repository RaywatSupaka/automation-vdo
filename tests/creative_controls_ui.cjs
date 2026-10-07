// Native DOM + actual option wrappers; no server/provider or user workspace files.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),read=file=>fs.readFileSync(path.join(root,'web_ui',file),'utf8');
const catalog=JSON.parse(process.env.SMARTFLOW_CREATIVE_CATALOG);
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  try{
    const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],network=[];
    page.on('pageerror',error=>errors.push(error.message));await page.route('**/*',route=>{network.push(route.request().url());return route.abort();});
    const html=read('index.html');await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
    for(const file of ['styles.css','creation_queue.css','media_audio.css','storytelling.css','creative_controls.css'])await page.addStyleTag({content:read(file)});
    await page.addScriptTag({content:`
      const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
      const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const ui={state:{},activePage:'products',aiModelDrafts:{},dramaImages:{},dramaFootage:[]},pageMeta={},calls=[];
      const toast=()=>{},poll=async()=>{},renderSystem=()=>{},showPage=name=>{ui.activePage=name;$$('[data-view]').forEach(n=>n.classList.toggle('active',n.dataset.view===name));};
      let prepareGate=null,prepareRelease=null;
      let postAction=async(action,payload={})=>{
        const capture=window.productOptionSnapshot?.finish(action,payload);if(capture)return capture;
        calls.push({action,payload:JSON.parse(JSON.stringify(payload))});
        if(action==='product_story_prepare'){
          if(prepareGate)await prepareGate;
          return {ok:true,topic:'โคมไฟ',creative_context:{kind:'product_story',product_short:true,snapshot_id:'fixture',source_product_id:'JOB-FIXTURE'},prepare_options:payload};
        }
        if(action==='product_cast_state')return {ok:true,assets:[]};
        return {ok:true,queued:1,duplicates:0};
      };
    `});
    const app=read('app.js'),begin=app.indexOf('const fallbackAiModelOptions =');
    await page.addScriptTag({content:app.slice(begin,app.indexOf('function bindAiModelSelect(',begin))});
    for(const file of ['creative_controls.js','product_snapshot.js','status_vocabulary.js','creation_queue.js','media_audio.js','product_story.js','storytelling.js','creator_ux.js'])await page.addScriptTag({content:read(file)});
    await page.evaluate(catalog=>{renderCreativeCatalog(catalog);showPage('products');setMediaAudioChoice('product',{mode:'api',subtitle:false,music:false,sfx:false,keep_video_audio:false});},catalog);
    assert.deepEqual(errors,[]);
    await page.locator('#ps-creative-style').click();assert.equal(await page.locator('.creative-dialog[open] [data-creative-value]').count(),catalog.product.length);
    await page.locator('.creative-dialog[open] input[type=search]').fill('นิ้วชี้');
    assert.equal(await page.locator('.creative-dialog[open] [data-creative-value]').count(),1);
    await page.locator('.creative-dialog[open] [data-creative-value=pointing_review]').click();
    assert.match(await page.locator('#ps-creative-style').textContent(),/นิ้วชี้/);
    await page.locator('#ps-creative-style').click();
    await page.locator('.creative-dialog[open] input[type=search]').fill('ก่อนออก');
    assert.equal(await page.locator('.creative-dialog[open] [data-creative-value]').count(),1);
    await page.locator('.creative-dialog[open] [data-creative-value=before_leaving]').click();
    assert.match(await page.locator('#ps-creative-style').textContent(),/ก่อนออกจากบ้าน/);
    assert.equal(await page.locator('.ps-style-grid').isVisible(),false);
    const productSummary=page.locator('[data-view=products] .creator-review p');
    assert.match(await productSummary.textContent(),/แนวบท: ก่อนออกจากบ้าน/);
    assert.match(await productSummary.textContent(),/ไม่เพิ่มเพลง/);
    const summaryBefore=await page.evaluate(()=>({calls:calls.length,audio:JSON.stringify(mediaAudioChoice('product'))}));
    await page.evaluate(()=>{setGeneratedMusicChoice('product',{version:1,enabled:true,mood:'auto',frequency:'moderate'});document.dispatchEvent(new Event('change'));});
    assert.match(await productSummary.textContent(),/ขอดนตรี AI บางฉาก/);
    assert.doesNotMatch(await productSummary.textContent(),/ไม่เพิ่มเพลง/);
    await page.evaluate(()=>{setGeneratedMusicChoice('product',{version:1,enabled:false,mood:'auto',frequency:'moderate'});document.dispatchEvent(new Event('change'));});
    assert.match(await productSummary.textContent(),/ไม่เพิ่มเพลง/);
    assert.doesNotMatch(await productSummary.textContent(),/ขอดนตรี AI/);
    assert.deepEqual(await page.evaluate(()=>({calls:calls.length,audio:JSON.stringify(mediaAudioChoice('product'))})),summaryBefore,'Summary refresh never dispatches or changes audio choices');
    await page.evaluate(()=>{
      prepareGate=new Promise(resolve=>prepareRelease=resolve);
      window.pendingProduct=postAction('create_product',{link:'https://s.shopee.co.th/CREATIVE-FIXTURE',provider:'chatgpt',video_provider:'flow'});
    });
    await page.waitForFunction(()=>calls.some(call=>call.action==='product_story_prepare'));
    await page.locator('#ps-creative-style').click();await page.locator('.creative-dialog[open] [data-creative-value=auto]').click();
    await page.evaluate(async()=>{prepareRelease();await pendingProduct;prepareGate=null;});
    const frozen=await page.evaluate(()=>calls.filter(call=>['product_story_prepare','create_product'].includes(call.action)));
    assert.equal(frozen[0].payload.product_script_options.style,'before_leaving');
    assert.equal(frozen.at(-1).payload.product_script_options.style,'before_leaving');
    assert.equal(frozen.at(-1).payload.product_script_options.version,3);
    // Batch inherits the chosen NEW style, not the legacy radio fallback.
    await page.evaluate(()=>showPage('creation'));await page.locator('#queue-add-products').click();
    assert.equal(await page.locator('[name=creation-product-script]:checked').inputValue(),'auto');
    await page.locator('#creation-editor-close').click();
    for(const choice of catalog.product.filter(item=>!['standard','story_first_review','short_film_ad'].includes(item.value))){
      await page.evaluate(()=>showPage('products'));await page.locator('#ps-creative-style').click();
      await page.locator(`.creative-dialog[open] [data-creative-value="${choice.value}"]`).click();
      await page.evaluate(()=>showPage('creation'));await page.locator('#queue-add-products').click();
      assert.equal(await page.locator('[name=creation-product-script]:checked').inputValue(),choice.value);
      assert.match(await page.locator('#creation-product-style').textContent(),new RegExp(choice.label.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
      await page.locator('#creation-editor-close').click();
    }
    // Saved queued Story can change and explicitly clear only its own structure.
    await page.evaluate(()=>{
      const item={queue_id:'QUEUE-FIXTURE',mode:'story',status:'queued',topic:'เรื่องเดิม',scene_count:6,provider:'chatgpt',video_generation_mode:'google_flow',settings:{story_structure_options:{version:1,structure:'countdown'},audio_choices:{mode:'flow_original',subtitle:false,music:false,sfx:false}}};
      ui.state.creation_queue={items:[item],paused:true};renderCreationQueue(ui.state);
    });
    await page.locator('[data-cq=edit]').click();
    assert.match(await page.locator('#creation-saved-story-structure').textContent(),/ภารกิจก่อนหมดเวลา/);
    await page.locator('#creation-saved-story-structure').click();await page.locator('.creative-dialog[open] [data-creative-value=legacy]').click();
    await page.locator('#creation-editor-submit').click();
    const edited=await page.evaluate(()=>calls.filter(call=>call.action==='creation_edit').at(-1));
    assert.equal(edited.payload.story_structure_options,null);
    await page.evaluate(()=>showPage('story'));
    await page.locator('[data-storytelling=story] .storytelling-advanced > summary').click();
    await page.locator('#story-structure').click();
    assert.equal(await page.locator('.creative-dialog[open] [data-creative-value]').count(),12);
    await page.locator('.creative-dialog[open] [data-creative-value=two_viewpoints]').click();
    assert.match(await page.locator('[data-view=story] .creator-review p').textContent(),/โครงเรื่อง: เรื่องเดียว สองมุมมอง/);
    await page.evaluate(async()=>{
      await postAction('create_story',{topic:'เรื่องเดิม',video_generation_mode:'image_motion'});
      prepareStorytellingBatch();await postAction('enqueue_story_batch',{topics:['หนึ่ง','สอง'],video_generation_mode:'image_motion'});
    });
    const story=await page.evaluate(()=>calls.find(call=>call.action==='create_story'));
    const batch=await page.evaluate(()=>calls.find(call=>call.action==='enqueue_story_batch'));
    assert.equal(story.payload.story_structure_options.structure,'two_viewpoints');
    assert.equal(story.payload.storytelling_options.mode,'narrator');
    assert.equal(batch.payload.story_structure_options.structure,'two_viewpoints');
    await page.locator('#story-structure').click();await page.keyboard.press('Escape');
    assert.equal(await page.locator('#story-structure').evaluate(node=>document.activeElement===node),true);
    assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
    console.log(JSON.stringify({ok:true,productChoices:catalog.product.length,storyChoices:12,freeze:true,queueEdit:true,narrowViewport:true,networkRequests:0}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
