// Isolated UI only; all network aborted and provider actions replaced by fixtures.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage();await page.route('**/*',route=>route.abort());
    await page.setContent('<main></main>');
    await page.evaluate(()=>{
      window.calls=[];window.cover={};window.libraryItem=()=>({});
      window.postAction=async(action,payload)=>{
        calls.push({action,payload});
        if(action==='get_cover_editor')return{editor:{item_id:'story:STORY-COVER',revision:'old',
          aspect_ratio:'9:16',ai_cover_state:cover,images:[],settings:{headline:'ปก',emphasis:'',
            theme:'bold',position:'top',alternatives:[],scene_index:1}}};
        if(action==='preview_library_cover')return{};
        if(action==='ai_cover_regenerate')return{request:{request_id:'new-request',phase:'queued'}};
        if(action==='ai_cover_status')return{request:{request_id:'new-request',phase:'needs_review',
          preparation_state:{stage:'image_tool',reason:'opener_missing',attempt:1,
            request_id:'new-request',not_dispatched:true}}};
        throw Error('Unexpected action '+action);
      };
    });
    await page.addScriptTag({path:'web_ui/clip_cover.js'});
    const base={request_id:'old-request',phase:'needs_review'};
    const preparation={stage:'image_tool',reason:'opener_disabled',attempt:2,
      not_dispatched:true,request_id:base.request_id};
    async function open(state){
      await page.evaluate(state=>{document.querySelector('dialog').close();cover=state;return openClipCover('story:STORY-COVER');},state);
      return await page.evaluate(()=>({label:document.querySelector('[data-cover-ai]').textContent,
        collectHidden:document.querySelector('[data-cover-ai-recover]').hidden,
        cancelHidden:document.querySelector('[data-cover-ai-cancel]').hidden,
        message:document.querySelector('.cover-editor-status').textContent}));
    }
    let state=await open({...base,preparation_state:preparation});
    assert.equal(state.label,'ทำปกต่อ');assert(state.collectHidden);assert(state.message.includes('ยังไม่ส่งคำขอ'));
    await page.getByRole('button',{name:'ทำปกต่อ',exact:true}).click();
    await page.waitForFunction(()=>calls.some(call=>call.action==='ai_cover_status'));
    assert.equal(await page.locator('[data-cover-ai]').textContent(),'ทำปกต่อ');
    assert.equal(await page.locator('[data-cover-ai-recover]').isHidden(),true);
    const calls=await page.evaluate(()=>window.calls);
    assert.equal(calls.filter(call=>call.action==='ai_cover_regenerate').length,1);
    assert.equal(calls.find(call=>call.action==='ai_cover_regenerate').payload.request_id,base.request_id);
    assert(!calls.some(call=>call.action==='ai_cover_recover'));
    for(const evidence of [{send_state:'accepted'},{send_state:'unconfirmed'},
      {send_diagnostics:{gesture_phase:'pressed'}},{result_proof:{images:1}}]){
      state=await open({...base,preparation_state:preparation,...evidence});
      assert.equal(state.label,'สร้างปกใหม่ด้วย AI');assert.equal(state.collectHidden,false);
    }
    state=await open(base);assert.equal(state.collectHidden,false,'legacy unknown requests keep read-only collection');
    state=await open({...base,preparation_state:{...preparation,request_id:'wrong'}});
    assert.equal(state.label,'สร้างปกใหม่ด้วย AI');assert(state.collectHidden,'wrong proof never suggests pre-send continuation');
    for(const phase of ['preparing','recovering']){
      state=await open({...base,phase,preparation_state:preparation});
      assert(state.collectHidden);assert.equal(state.cancelHidden,false);assert(state.message.includes('กำลังเตรียมสร้างปก'));
    }
    await page.getByRole('button',{name:'ปิดหน้าปก',exact:true}).click();
    console.log('Cover preparation UI passed: explicit unsent continuation, accepted/unknown collection, legacy and active states.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
