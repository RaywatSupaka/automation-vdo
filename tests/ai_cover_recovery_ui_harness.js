const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true});try{
  const page=await browser.newPage();await page.route('**/*',r=>r.abort());
  await page.setContent('<div id="detail-modal"><video class="detail-video"></video></div>');
  await page.evaluate(()=>{
    window.calls=[];window.item={};window.libraryItem=()=>item;window.done=false;
    window.postAction=async(action,payload)=>{calls.push({action,payload});
      if(action==='get_cover_editor')return{editor:{item_id:'story:STORY-TEST',aspect_ratio:'9:16',revision:done?'new-cover':'old',
        ai_cover_state:{request_id:'a'.repeat(32),phase:done?'ready':'needs_review'},images:[],
        settings:{headline:'test',emphasis:'',theme:'bold',position:'top',alternatives:[],scene_index:1}}};
      if(action==='preview_library_cover')return{preview:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg=='};
      if(action==='ai_cover_recover')return{request:{request_id:'a'.repeat(32),phase:'queued',collect_only:true}};
      if(action==='ai_cover_status'){done=true;return{request:{request_id:'a'.repeat(32),phase:'ready'}};}
      throw Error('Unexpected action '+action);
    };
  });
  await page.addScriptTag({path:path.join(__dirname,'../web_ui/clip_cover.js')});
  await page.evaluate(()=>openClipCover('story:STORY-TEST'));
  await page.getByRole('button',{name:'ดึงปกเดิมจากเว็บ',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.cover-editor-status').textContent.includes('บันทึกปกแล้ว'));
  const state=await page.evaluate(()=>({calls,item,src:document.querySelector('.cover-preview-box img').getAttribute('src'),
    poster:document.querySelector('video').poster,recoverHidden:document.querySelector('[data-cover-ai-recover]').hidden}));
  assert.equal(state.calls.filter(c=>c.action==='ai_cover_recover').length,1);
  assert.equal(state.calls.find(c=>c.action==='ai_cover_recover').payload.request_id,'a'.repeat(32));
  assert(!state.calls.some(c=>['ai_cover_regenerate','save_library_cover'].includes(c.action)));
  assert(state.src.includes('v=new-cover'));assert.equal(state.item.cover_url,state.src);assert(state.poster.endsWith('v=new-cover'));assert(state.recoverHidden);
  await page.getByRole('button',{name:'ปิดหน้าปก',exact:true}).click();
  console.log('Cover recovery UI: existing request only, save ACK updates preview/poster, no regenerate, close passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
