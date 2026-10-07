// Real creation wrapper order and native form controls. Every request is synthetic.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),read=file=>fs.readFileSync(path.join(root,'web_ui',file),'utf8');
const files=new Set(['product_snapshot.js','status_vocabulary.js','creation_queue.js','presenter.js','media_audio.js',
  'flow_settings.js','flow_motion.js','ai_cover.js','video_intro.js','green_screen.js',
  'queue_choice.js','product_story.js','storytelling.js']);

async function fixture(browser){
  const page=await browser.newPage();const errors=[],network=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{network.push(route.request().url());return route.abort();});
  const html=read('index.html');
  await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
  await page.addScriptTag({content:`
    const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
    const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const ui={state:{},activePage:'products',aiModelDrafts:{},dramaImages:{},dramaFootage:[]};
    const pageMeta={},calls=[],notices=[];let prepareGate=null,prepareRelease=null;
    const toast=(message,kind)=>notices.push({message,kind}),poll=async()=>{},renderSystem=()=>{};
    const showPage=name=>{ui.activePage=name;$$('[data-view]').forEach(n=>n.classList.toggle('active',n.dataset.view===name));};
    window.fetch=async(url,options)=>{
      if(url!=='/api/desktop/action')throw Error('Unexpected fixture URL: '+url);
      const {action,payload}=JSON.parse(options.body);calls.push({action,payload});let data={ok:true};
      if(action==='flow_settings_get')data.settings={model:'Omni 1.1 Flash',duration:'4s',display:'compact'};
      else if(action==='intro_status')data={ok:true,settings:{enabled:false,file:'assets/intro/'+ 'a'.repeat(64)+'.mp4',targets:{story:true,drama:false}},assets:[{file:'assets/intro/'+ 'a'.repeat(64)+'.mp4',name:'Fixture intro',duration:2}]};
      else if(action==='green_status')data={ok:true,settings:{enabled:true,clips:[{file:'assets/screenfx/'+ 'b'.repeat(64)+'.mp4',color:'#00ff00',similarity:.15,blend:.08}],opacity:.5,fit:'contain'},targets:{story:false,product:true},assets:[]};
      else if(action==='presenter_state')data={ok:true,ui_version:2,jobs:[],defaults:{available:true,name:'Fixture presenter',settings:{enabled:true,id:'PRESENTER-FIXTURE',x:50,y:90,size:30}}};
      else if(action==='product_cast_state')data={ok:true,assets:[]};
      else if(action==='product_story_prepare'){
        if(prepareGate)await prepareGate;
        data={ok:true,topic:'Synthetic product',creative_context:{kind:'product_story',snapshot_id:'fixture-snapshot',source_product_id:payload.product_id||'JOB-FIXTURE'},prepare_options:window.savedPreparation||payload};
      }
      else if(action==='creation_enqueue')data={ok:true,queued:1,duplicates:0};
      else if(action==='create_product')data={ok:true,job_id:'STORY-FIXTURE'};
      return {ok:true,json:async()=>JSON.parse(JSON.stringify(data))};
    };
  `});
  const app=read('app.js');
  await page.addScriptTag({content:app.slice(app.indexOf('async function postAction('),app.indexOf('function readBlobAsDataUrl('))});
  await page.addScriptTag({content:app.slice(app.indexOf('function safeUiError('),app.indexOf('function showPage('))});
  const helpers=app.indexOf('const fallbackAiModelOptions =');
  await page.addScriptTag({content:app.slice(helpers,app.indexOf('function bindAiModelSelect(',helpers))});
  const order=[...html.matchAll(/<script[^>]+src="\/desktop\/([^?"/]+)(?:\?[^" ]*)?"/g)].map(m=>m[1]).filter(f=>files.has(f));
  for(const file of order)await page.addScriptTag({content:read(file)});
  await page.evaluate(async()=>{
    await new Promise(r=>setTimeout(r,20));
    $('#product-video-provider').value='flow';$('#product-video-provider').dispatchEvent(new Event('change'));
    $('#creation-product-video-provider').value='google_flow';
    setMediaAudioChoice('product',{mode:'api',subtitle:true,music:true,sfx:false,keep_video_audio:false,video_audio_volume:35});
    setMediaAudioChoice('product-batch',{mode:'flow_original',subtitle:false,music:false,sfx:true,keep_video_audio:false,video_audio_volume:70});
    setMediaAudioChoice('story',{mode:'none',subtitle:false,music:false,sfx:false,keep_video_audio:false,video_audio_volume:35});
    for(const box of $('#story-video-mode').closest('label').parentElement.querySelectorAll('.ai-cover-options'))box.querySelector('[data-cover-enable]').checked=false;
  });
  assert.deepEqual(errors,[],'Full participating modules initialize without native DOM errors');
  return {page,errors,network,order};
}

(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  let scenarios=0;const backendDrama=[];
  try{
    for(const route of ['direct','batch','direct-queued']){
      const batch=route==='batch';
      const f=await fixture(browser),p=f.page;
      try{
        await p.evaluate(({batch,route})=>{
          if(batch)$('#creation-editor').showModal();
          if(route==='direct-queued')$('#product-queue-only').checked=true;
          prepareGate=new Promise(r=>prepareRelease=r);
          window.pendingCreation=postAction(batch?'creation_enqueue':'create_product',batch
            ?{mode:'product',values:['https://s.shopee.co.th/FIXTURE'],provider:'gemini',video_generation_mode:'google_flow'}
            :{link:'https://s.shopee.co.th/FIXTURE',provider:'gemini',video_provider:'flow'});
        },{batch,route});
        await p.waitForFunction(()=>calls.some(c=>c.action==='product_story_prepare'));
        const prep=await p.evaluate(()=>calls.find(c=>c.action==='product_story_prepare').payload);
        assert.equal(prep.audio_choices?.mode,batch?'flow_original':'api','Shopee preparation must already contain the selected Product audio');
        assert.equal(prep.ai_cover_options?.enabled,true,'Product cover choice is captured before Shopee');
        assert.equal(prep.product_option_snapshot.form,batch?'product-batch':'product');
        assert.equal(prep.product_option_snapshot.version,1);
        assert.equal(prep.intro_options.enabled,false,'Product does not inherit the enabled Story intro');
        assert.equal(prep.green_options.enabled,true,'Product green settings are captured separately');
        await p.evaluate(()=>{
          setMediaAudioChoice('product',{mode:'none',subtitle:false});setMediaAudioChoice('product-batch',{mode:'none',subtitle:false});
          setMediaAudioChoice('story',{mode:'flow_original',subtitle:true});
          document.querySelectorAll('[data-cover-enable]').forEach(n=>n.checked=false);
          document.querySelectorAll('[data-green-enable]').forEach(n=>n.checked=false);
          $('#product-queue-only').checked=!$('#product-queue-only').checked;
          prepareRelease();
        });
        await p.evaluate(()=>pendingCreation);
        const result=await p.evaluate(()=>calls.filter(c=>['create_product','creation_enqueue'].includes(c.action)).at(-1));
        assert.equal(result.action,route==='direct'?'create_product':'creation_enqueue','Queue routing is also frozen before Shopee');
        assert.equal(result.payload.audio_choices.mode,prep.audio_choices.mode);
        assert.deepEqual(result.payload.ai_cover_options,prep.ai_cover_options);
        assert.deepEqual(result.payload.flow_settings,prep.flow_settings);
        assert.deepEqual(result.payload.green_options,prep.green_options);
        assert.deepEqual(result.payload.intro_options,prep.intro_options);
        assert.deepEqual(result.payload.presenter,prep.presenter);
        assert.deepEqual(f.errors,[]);scenarios++;
      }finally{await p.close();}
    }
    for(const queue of [false,true]){
      const f=await fixture(browser),p=f.page;
      try{
        await p.evaluate(queue=>{
          const options={provider:'gemini',ai_web_model:'flash',video_generation_mode:'meta_ai',scene_count:6,
            audio_choices:{mode:'none',subtitle:false,music:true,sfx:true},flow_settings:{model:'Veo 3.1 - Fast',duration:'6s'},
            ai_cover_options:{enabled:true,scene_index:2},intro_options:{enabled:false,file:''},
            green_options:{enabled:true,clips:[{file:'frozen-green.mp4'}],opacity:.3,fit:'cover'},
            presenter:{enabled:false},fictional_ai_characters_confirmed:true,actor_dialogue:false,
            handoff_mode:queue?'queue':'immediate'};
          // One case also covers explicit legacy choices with no marker.
          if(!queue)options.product_option_snapshot={version:1,form:'product'};
          window.savedPreparation=JSON.parse(JSON.stringify(options));
          ui.state.product_preparations=[{id:'JOB-RESUME',request_id:'PSP-resume',prepare_options:options}];
          $('#product-queue-only').checked=!queue;
          window.dispatchEvent(new CustomEvent('smartflow:resume-product-source',{detail:{product_id:'JOB-RESUME',request_id:'PSP-resume'}}));
        },queue);
        await p.waitForFunction(()=>calls.some(c=>['create_product','creation_enqueue'].includes(c.action)));
        const result=await p.evaluate(()=>calls.filter(c=>['create_product','creation_enqueue'].includes(c.action)).at(-1));
        const saved=await p.evaluate(()=>savedPreparation);
        assert.equal(result.action,queue?'creation_enqueue':'create_product');
        for(const key of ['audio_choices','flow_settings','ai_cover_options','intro_options','green_options','presenter'])
          assert.deepEqual(result.payload[key],saved[key],`Resume preserves ${key}`);
        assert.equal(result.payload.fictional_ai_characters_confirmed,true);
        assert.equal(result.payload.provider,'gemini');assert.equal(result.payload.video_generation_mode,'meta_ai');
        assert.deepEqual(f.errors,[]);scenarios++;
      }finally{await p.close();}
    }
    {
      const f=await fixture(browser),p=f.page;
      try{
        await p.evaluate(()=>{
          savedPreparation={provider:'gemini',handoff_mode:'immediate'};
          ui.state.product_preparations=[{id:'JOB-LEGACY',request_id:'PSP-legacy',prepare_options:savedPreparation}];
          window.dispatchEvent(new CustomEvent('smartflow:resume-product-source',{detail:{product_id:'JOB-LEGACY',request_id:'PSP-legacy'}}));
        });
        await p.waitForFunction(()=>document.querySelector('.product-preparation')?.dataset.state==='error');
        assert.match(await p.locator('.product-preparation').textContent(),/ตัวเลือกเสียง.*ไม่ครบ/);
        assert.equal(await p.evaluate(()=>calls.filter(c=>['create_product','creation_enqueue'].includes(c.action)).length),0);
        const frozen=await p.evaluate(()=>{
          const row=productOptionSnapshot.restore({audio_choices:{mode:'none',subtitle:false}});
          return Object.isFrozen(row)&&Object.isFrozen(row.audio_choices)&&Object.isFrozen(row.green_options.clips);
        });assert.equal(frozen,true);scenarios++;
      }finally{await p.close();}
    }
    {
      const f=await fixture(browser),p=f.page;
      try{
        for(const [action,extra,key] of [['create_story',{},'story'],['create_story',{long_video:{version:2}},'long']]){
          await p.evaluate(async({action,extra,key})=>{
            const selector=key==='long'?'#long-mode':'#story-video-mode';$(selector).value='google_flow';
            setMediaAudioChoice(key,{mode:'api',subtitle:true,music:true,sfx:false,video_audio_volume:35});
            await postAction(action,{...extra,video_generation_mode:'google_flow',audio_choices:{mode:'none'}});
          },{action,extra,key});
          const last=await p.evaluate(()=>calls.at(-1));assert.equal(last.payload.audio_choices.mode,'api');
          assert.equal(last.payload.product_option_snapshot,undefined);scenarios++;
        }
        for(const enqueue of [false,true])for(const [mode,count,accept] of [
          ['narrator',0,true],['solo',0,false],['solo',1,true],['visual',0,false],['visual',1,true],['dialogue',1,false],['dialogue',2,true]]){
          const result=await p.evaluate(async({enqueue,mode,count})=>{
            const modeInput=document.querySelector('select[name="storytelling-drama"]');
            modeInput.value=mode;modeInput.dispatchEvent(new Event('change',{bubbles:true}));
            const previous=calls.length;let error='';
            try{await postAction('create_drama_series',{enqueue_only:enqueue,characters:Array.from({length:count},(_,i)=>({name:'Fixture '+i})),render_options:{video_generation_mode:'google_flow'}});}
            catch(e){error=e.message;}
            return {error,submitted:calls.slice(previous).some(c=>c.action==='create_drama_series'),last:calls.at(-1)};
          },{enqueue,mode,count});
          assert.equal(result.submitted,accept,`${enqueue?'Enqueue':'Create'} ${mode}/${count}`);
          if(accept){assert.equal(result.error,'');assert.equal(result.last.payload.storytelling_options.mode,mode);backendDrama.push(result.last.payload);}
          else assert.match(result.error,/ตัวละครอย่างน้อย/);
          scenarios++;
        }
        assert.deepEqual(f.errors,[]);
      }finally{await p.close();}
    }
    console.log('BACKEND_DRAMA='+JSON.stringify(backendDrama));
    console.log('PASS Product snapshot actual wrapper stack: '+scenarios+' scenarios');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
