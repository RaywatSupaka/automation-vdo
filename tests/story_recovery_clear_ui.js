const fs=require('fs'),assert=require('assert/strict'),{chromium}=require('playwright');
(async()=>{
 const source=fs.readFileSync('web_ui/app.js','utf8'),html=fs.readFileSync('web_ui/index.html','utf8');
 assert(html.includes('id="story-recovery-clear"'));
 assert(source.includes("await clearStoryRecovery(); return;"));
 const code=source.slice(source.indexOf('let storyRecoveryClearing ='),source.indexOf('let dramaQueuePending'));
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:600,height:800}});
  // Select the Shorts panel by identity, not the first reusable panel class.
  const start=html.lastIndexOf('<section', html.indexOf('id="story-recovery-panel"'));
  await page.setContent(html.slice(start,html.indexOf('</section>',start)+10));
  await page.addStyleTag({content:fs.readFileSync('web_ui/styles.css','utf8')});
  await page.addScriptTag({content:`
   const $=s=>document.querySelector(s),escapeHtml=s=>String(s||''),videoSourcePresentation=()=>({label:'Flow'});
   let calls=[],accepted=false,hold=null,fail=false,notices=[];
   const ui={state:{stories:Array.from({length:11},(_,i)=>({id:'STORY-'+i,status:'error',title:'เรื่อง '+i})),story_progress:{}}};
   ui.state.stories.push({id:'product',content_kind:'product'},{id:'drama',job_type:'drama'},{id:'long',long_video:true},{id:'done',status:'ready',video_status:'ready'});
   window.confirm=()=>accepted;
   const toast=(...v)=>notices.push(v),poll=async()=>{};
   const postAction=async(...v)=>{calls.push(v);await new Promise(resolve=>hold=resolve);if(fail)return {ok:false,error:'busy'};ui.state.stories=[];return {ok:true,cleared:11};};
   ${code}
   document.querySelector('button').onclick=()=>clearStoryRecovery();
   setStoryView('old');
   renderStories(ui.state.stories,{});
  `});
  assert.equal(await page.locator('#story-recovery-count').textContent(),'11 งาน');
  assert.equal(await page.locator('article').count(),11);
  assert.equal(await page.locator('#story-list').evaluate(el=>getComputedStyle(el).overflowY),'auto');
  assert.equal(await page.locator('#story-recovery-panel').isVisible(),true);
  assert.equal(await page.locator('#story-list').evaluate(el=>el.scrollHeight>el.clientHeight),true);
  const bounds=await page.locator('#story-recovery-clear').boundingBox();
  assert(bounds.x>=0 && bounds.x+bounds.width<=600);
  if(process.env.STORY_CLEAR_SCREENSHOT)await page.screenshot({path:process.env.STORY_CLEAR_SCREENSHOT});
  await page.evaluate(()=>clearStoryRecovery());
  assert.equal(await page.evaluate(()=>calls.length),0);
  await page.evaluate(()=>{accepted=true;window.pending=clearStoryRecovery();});
  assert.equal(await page.locator('#story-recovery-clear').isDisabled(),true);
  await page.evaluate(()=>clearStoryRecovery());
  assert.equal(await page.evaluate(()=>calls.length),1);
  await page.evaluate(async()=>{hold();await window.pending;});
  assert.equal(await page.locator('#story-recovery-panel').isVisible(),true);
  assert.match(await page.locator('#story-list').textContent(),/ไม่มีงานเรื่องเล่าที่ต้องทำต่อ/);
  await page.evaluate(()=>{ui.state.stories=[{id:'STORY-x'}];fail=true;window.pending=clearStoryRecovery();});
  await page.evaluate(async()=>{hold();await window.pending;});
  assert.equal(await page.locator('#story-recovery-clear').isDisabled(),false);
  assert.equal(await page.evaluate(()=>notices.at(-1)[1]),'error');
  await page.evaluate(()=>renderStories(ui.state.stories,{active:true,job_id:'STORY-x'}));
  assert.equal(await page.locator('#story-recovery-clear').isDisabled(),true);
  await page.evaluate(()=>{
   const stopped={id:'STORY-stopped',title:'งานที่หยุด',status:'cancelled',video_status:'cancelled',
    pipeline_stage:'user_cancel',cancel_reason:'ผู้ใช้ยกเลิกการทำงาน',updated_at:'2026-09-22T10:04:50'};
   renderStories([...Array.from({length:12},(_,i)=>({id:'OLD-'+i,status:'error',updated_at:'2026-09-21'})),
    stopped,{...stopped,id:'DISMISSED',cancel_reason:'ผู้ใช้ยกเลิกงานเก่าจากหน้ารายการทำต่อ'}],{});
  });
  assert.equal(await page.locator('#story-recovery-count').textContent(),'13 งาน');
  assert.equal(await page.locator('[data-retry-story="STORY-stopped"]').count(),1);
  assert.equal(await page.locator('article').first().locator('[data-retry-story]').getAttribute('data-retry-story'),'STORY-stopped');
  assert.equal(await page.locator('[data-retry-story="DISMISSED"]').count(),0);
  console.log(JSON.stringify({ok:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
