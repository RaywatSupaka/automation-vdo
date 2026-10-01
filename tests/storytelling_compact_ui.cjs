// Actual compact Story / batch / Drama controls in an isolated temporary browser.
// Every request is blocked; only the inert action recorder receives submissions.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),read=file=>fs.readFileSync(path.join(root,'web_ui',file),'utf8');
const catalog=JSON.parse(process.env.SMARTFLOW_CREATIVE_CATALOG);
const texts={
  'story-text':'  เรื่องของฉัน — คงข้อความนี้\nบรรทัดที่สอง “อย่าแทนที่”  ',
  'story-batch-direction':'แนวทางร่วมที่เขียนเอง\n  จบตามต้นฉบับ ไม่เติมคำ  ',
  'drama-premise':'  พล็อตละครของฉัน\nตัวละครพบความลับ แล้วกลับบ้าน  ',
};
const forms=[['story','story-text','.story-main-fields'],['story-batch','story-batch-direction','.story-batch-main-fields'],['drama','drama-premise','.drama-main-fields']];
const modes=['narrator','solo','dialogue','visual'];
let checks=0;
const equal=(actual,expected,message)=>{assert.deepEqual(actual,expected,message);checks++;};
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],network=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',route=>{network.push(route.request().url());return route.abort();});
    await page.setContent(read('index.html').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
    for(const file of ['styles.css','media_audio.css','storytelling.css','creative_controls.css','function_controls.css'])await page.addStyleTag({content:read(file)});
    await page.evaluate(()=>{
      window.ui={state:{},dramaImages:{}};window.toast=()=>{};window.calls=[];
      window.postAction=async(action,payload={})=>{calls.push({action,payload:JSON.parse(JSON.stringify(payload))});return {ok:true};};
      window.showPage=key=>document.querySelectorAll('.page').forEach(node=>node.classList.toggle('active',node.dataset.view===key));
    });
    for(const file of ['creative_controls.js','media_audio.js','storytelling.js','creator_ux.js','function_controls.js'])await page.addScriptTag({content:read(file)});
    await page.evaluate(({catalog,texts})=>{
      renderCreativeCatalog(catalog);
      for(const [id,text] of Object.entries(texts))document.getElementById(id).value=text;
    },{catalog,texts});
    async function show(key){
      await page.evaluate(key=>{
        document.querySelector('#story-batch-modal').close();showPage(key==='drama'?'drama':'story');
        if(key==='story-batch')document.querySelector('#story-batch-modal').showModal();
      },key);
    }
    async function unchanged(message){
      equal(await page.evaluate(ids=>Object.fromEntries(ids.map(id=>[id,document.getElementById(id).value])),Object.keys(texts)),texts,message);
    }
    async function submit(key){
      return page.evaluate(async key=>{
        const action=key==='drama'?'create_drama_series':key==='story-batch'?'enqueue_story_batch':'create_story';
        const payload=key==='drama'?{characters:[{name:'มะลิ'},{name:'ต้น'}],render_options:{video_generation_mode:'google_flow'}}:
          {video_generation_mode:'google_flow',...(key==='story-batch'?{topics:['หนึ่ง','สอง']}:{topic:'เรื่องตัวอย่าง'})};
        await postAction(action,payload);return calls.at(-1).payload;
      },key);
    }
    equal(await page.locator('[data-storytelling]').count(),3,'All three existing forms receive the shared control');
    equal(await page.locator('.storytelling-advanced[open]').count(),0,'All advanced helpers start closed');
    for(const [key,textarea] of forms){
      await show(key);
      const panel=page.locator(`[data-storytelling="${key}"]`),select=panel.locator('select[data-telling=mode]'),advanced=panel.locator('.storytelling-advanced');
      equal(await select.getAttribute('name'),'storytelling-'+key);
      equal(await select.locator('option').evaluateAll(nodes=>nodes.map(node=>node.value)),modes,'The four persisted mode values are unchanged');
      equal(await panel.locator('input[type=radio]').count(),0,'No duplicate mode writer remains');
      equal((await advanced.locator('summary').textContent()).trim(),'ปรับแต่งเพิ่มเติม');
      equal(await panel.evaluate((node,id)=>Boolean(document.getElementById(id).compareDocumentPosition(node)&Node.DOCUMENT_POSITION_FOLLOWING),textarea),true,'Authored text appears before optional controls');
      equal(await advanced.locator('[data-telling=tone]').isVisible(),false,'Tone is hidden with the other helpers');
      if(key!=='drama')equal(await advanced.locator('#'+key+'-structure').isVisible(),false,'Structure is inside the closed helper disclosure');
      await page.selectOption('#'+key+'-video-mode','google_flow');
      const callsBefore=await page.evaluate(()=>calls.length);
      const examples=[];
      for(const mode of modes){
        await select.selectOption(mode);
        equal(await page.evaluate(key=>storytellingModeFor(key),key),mode,'Existing mode API follows the compact select');
        examples.push(await panel.evaluate(node=>node.previousElementSibling.querySelector('.storytelling-example').textContent));
        await unchanged(key+' / '+mode+' does not rewrite authored text');
      }
      equal(new Set(examples).size,4,'Each mode has a distinct optional writing example');
      await select.selectOption('narrator');
      await advanced.locator('summary').click();
      await advanced.locator('[data-telling=tone]').selectOption('warm');
      await advanced.locator('[data-telling=hook]').selectOption('question');
      await advanced.locator('[data-telling=ending]').selectOption('twist');
      await advanced.locator('[data-telling=cta_enabled]').check();
      if(key!=='drama'){
        await advanced.locator('#'+key+'-structure').click();
        await page.locator('.creative-dialog[open] [data-creative-value=countdown]').click();
      }
      await advanced.locator('summary').click();
      equal(await advanced.evaluate(node=>node.open),false);
      equal(await advanced.locator('.storytelling-advanced-state').textContent(),`ตั้งไว้ ${key==='drama'?4:5} รายการ`,'Collapsed summary exposes selected helper count');
      await unchanged('Helper changes and collapse preserve every authored field');
      equal(await page.evaluate(()=>calls.length),callsBefore,'Editing controls never dispatches creation');
      const payload=await submit(key);
      equal(payload.storytelling_options,{version:1,mode:'narrator',tone:'warm',hook:'question',ending:'twist',cta_enabled:true},'Closed helpers retain their selected payload');
      if(key!=='drama')equal(payload.story_structure_options,{version:1,structure:'countdown'});
      else equal(payload.render_options.storytelling_options,payload.storytelling_options);
      // Return from character/visual roles to the exact chosen narrator mix.
      await page.evaluate(key=>setMediaAudioChoice(key,{mode:'api',subtitle:true,music:true,sfx:true,keep_video_audio:true,allow_silent:false,video_audio_volume:22}),key);
      const narrator=await page.evaluate(key=>mediaAudioChoice(key),key);
      await select.selectOption('dialogue');
      equal((await page.evaluate(key=>mediaAudioChoice(key),key)).mode,'flow_original');
      if(key==='drama')await page.check('[name=audio-mode-drama][value=api]');
      const speaking=await page.evaluate(key=>mediaAudioChoice(key),key);
      await select.selectOption('visual');
      const visual=await page.evaluate(key=>mediaAudioChoice(key),key);
      equal([visual.mode,visual.subtitle],['none',false]);
      await select.selectOption('dialogue');
      equal((await page.evaluate(key=>mediaAudioChoice(key),key)).mode,speaking.mode,'Leaving visual restores the speaking audio choice');
      await select.selectOption('narrator');
      equal(await page.evaluate(key=>mediaAudioChoice(key),key),narrator,'Returning to narrator restores the full previous mix');
      await unchanged('Audio restoration does not rewrite text');
      // Examples are inserted only by an explicit click and retain all draft bytes.
      const help=page.locator('#'+textarea).locator('..').locator('..').locator('.storytelling-writing-help');
      equal(await help.evaluate(node=>node.open),false,'Writing help also starts closed');
      await help.locator('summary').click();
      const example=await help.locator('.storytelling-example').textContent();
      const helperCallsBefore=await page.evaluate(()=>calls.length);
      await page.evaluate(id=>{window.exampleInputEvents=0;document.getElementById(id).addEventListener('input',()=>window.exampleInputEvents++);},textarea);
      await help.locator('button').click();texts[textarea]+='\n\n'+example;
      await unchanged('Explicit example appends after the complete original draft');
      equal(await page.locator('#'+textarea).evaluate(node=>document.activeElement===node),true);
      await help.locator('button').click();await unchanged('The same example is never appended twice');
      equal(await page.evaluate(()=>exampleInputEvents),1,'Duplicate click emits no artificial text edit');
      await select.selectOption('solo');await unchanged('Changing role updates the sample without inserting it');
      const soloExample=await help.locator('.storytelling-example').textContent();
      assert.notEqual(soloExample,example);checks++;
      await help.locator('button').click();texts[textarea]+='\n\n'+soloExample;
      await unchanged('A different explicit example also preserves the existing draft');
      equal(await page.evaluate(()=>calls.length),helperCallsBefore,'Writing examples never submit an AI request');
      await help.locator('summary').click();await select.selectOption('narrator');
    }
    // A new batch copies helper values and audio while both panels stay closed.
    await show('story');
    await page.selectOption('[name=storytelling-story]','solo');
    const copied=await page.evaluate(()=>{
      prepareStorytellingBatch();prepareStorytellingBatch();
      return {source:mediaAudioChoice('story'),batch:mediaAudioChoice('story-batch'),mode:storytellingModeFor('story-batch'),open:document.querySelectorAll('.storytelling-advanced[open]').length};
    });
    equal(copied.batch,copied.source);equal(copied.mode,'solo');equal(copied.open,0);
    const sourcePayload=await submit('story'),batchPayload=await submit('story-batch');
    equal(batchPayload.storytelling_options,sourcePayload.storytelling_options,'Batch inherits selected hidden helpers');
    equal(batchPayload.story_structure_options,sourcePayload.story_structure_options,'Batch inherits selected hidden structure');
    await unchanged('Batch preparation keeps its separately authored direction');
    // Saved/legacy work must never acquire the current new-form choices.
    for(const [action,payload] of [
      ['create_story',{job_id:'STORY-LEGACY'}],
      ['create_story',{job_id:'STORY-SAVED',storytelling_options:{version:1,mode:'narrator'},audio_choices:{mode:'api',subtitle:true},story_structure_options:{version:1,structure:'two_viewpoints'}}],
      ['create_drama_series',{job_id:'DRAMA-SAVED',render_options:{storytelling_options:{version:1,mode:'visual'},audio_choices:{mode:'none'}}}],
      ['continue_drama_series',{series_id:'SERIES-SAVED',continuation_prompt:'ข้อความที่บันทึกไว้',scene_count:6}],
    ]){
      const sent=await page.evaluate(async({action,payload})=>{await postAction(action,payload);return calls.at(-1);},{action,payload});
      equal(sent,{action,payload},'Resume/continuation payload does not inherit new-form state');
    }
    // Actual layout at desktop, tablet and narrow phone widths, all three forms.
    const screenshots=[];
    for(const width of [1440,980,390]){
      await page.setViewportSize({width,height:1100});
      for(const [key,textarea,container] of forms){
        await show(key);
        const geometry=await page.locator(`[data-storytelling="${key}"]`).evaluate((panel,textarea)=>{
          const box=panel.getBoundingClientRect(),select=panel.querySelector('[data-telling=mode]').getBoundingClientRect(),input=document.getElementById(textarea).getBoundingClientRect();
          return {overflow:panel.scrollWidth>panel.clientWidth+1,selectInside:select.left>=box.left&&select.right<=box.right+1,textFirst:input.bottom<=box.top+1,textWidth:input.width,modeHeight:select.height};
        },textarea);
        equal(geometry.overflow,false,key+' has no compact-panel overflow at '+width);
        equal(geometry.selectInside,true);equal(geometry.textFirst,true);
        assert(geometry.textWidth>120&&geometry.modeHeight>=36,'Text and mode remain usable at '+width);checks++;
        if(process.env.SMARTFLOW_COMPACT_SCREENSHOTS==='1'){
          const directory=path.join(root,'build','storytelling-compact-ui');fs.mkdirSync(directory,{recursive:true});
          const file=path.join(directory,key+'-'+width+'.png');
          await page.locator(container).screenshot({path:file});screenshots.push(file);
        }
      }
    }
    await unchanged('Responsive reflow preserves text');equal(errors,[]);equal(network,[]);
    console.log(JSON.stringify({ok:true,checks,forms:3,modes,viewports:[1440,980,390],networkRequests:0,providerRequests:0,screenshots}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
