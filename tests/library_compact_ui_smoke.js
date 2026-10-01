// Actual app render/click handlers, synthetic library and mocked transport only.
const fs=require('fs'), assert=require('assert/strict'), path=require('path');
const {chromium}=require('playwright');
const output='docs/reports/library-compact-1'; fs.mkdirSync(output,{recursive:true});
const html=fs.readFileSync('web_ui/index.html','utf8');
const app=fs.readFileSync('web_ui/app.js','utf8').split('showPage(ui.activePage,false); updateRangeLabels(); updateToolLabels(); poll(true);')[0];
const image=JSON.parse(fs.readFileSync('docs/reports/clip-cover-272/visual-fixture/fixture.json','utf8')).preview;
const video='data:video/mp4;base64,'+fs.readFileSync(`${output}/player-fixture.mp4`).toString('base64');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try {
    const page=await browser.newPage(); const errors=[];
    await page.route('http://smartflow.test/**', route=>route.fulfill({status:200,contentType:'text/html',body:'<html></html>'}));
    page.on('pageerror',e=>errors.push(e.message));
    for(const width of [1440,1024,600]) {
      await page.goto('http://smartflow.test/');
      await page.setViewportSize({width,height:950});
      await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
      for(const name of ['styles.css','workspace.css','studio.css','creation_queue.css','presenter.css','presenter_library.css','usability.css','clip_cover.css','library.css'])await page.addStyleTag({path:'web_ui/'+name});
      await page.addScriptTag({content:app});
      await page.evaluate(({image,video})=>{
        window.calls=[];
        ui.state={library:Array.from({length:125},(_,i)=>({item_id:`story:STORY-${i}`,job_id:`STORY-${i}`,title:i===124?'งานเก่าที่ต้องค้นเจอ':'ความลับหลังประตูบานนั้น เรื่องราวที่ยังไม่มีใครรู้ ตอนที่ '+i,
          kind:'story',content_kind:i%5===0?'drama':'story',kind_label:i%5===0?'ละครสั้น AI':i%7===0?'คลิปยาว':'Story Shorts',
          series_id:i%5===0?'SERIES-DEMO':'',series_title:'เรื่องเล่าแห่งประตู',episode_no:i%5===0?i+1:0,
          aspect_ratio:i%7===0?'16:9':'9:16',cover_url:image,thumbnail_url:image,preview_url:image,updated_at:'2026-09-08T12:00:00',size_bytes:1234567}))};
        postAction=async(action,payload)=>{
          window.calls.push({action,payload});
          if(action==='get_library_detail')return {ok:true,detail:{...ui.state.library.find(x=>x.item_id===payload.item_id),video_url:video,description:'คำอธิบายคลิปฉบับเต็ม',hashtags:'#เรื่องเล่า',post_text:'ข้อความโพสต์ฉบับเต็ม',file_name:'final.mp4'}};
          if(action==='get_cover_editor')return {ok:true,editor:{item_id:payload.item_id,title:'ปก',revision:'',aspect_ratio:'9:16',images:[{index:1,url:image}],settings:{headline:'ประตูบานนั้น',alternatives:[],scene_index:1,emphasis:'',theme:'bold',position:'bottom'}}};
          if(action==='preview_library_cover')return {ok:true,preview:image};
          return {ok:true};
        };
        copyText=text=>{window.copied=text;};
        document.querySelectorAll('.page').forEach(el=>{el.classList.toggle('active',el.dataset.view==='library');});
        document.body.dataset.page='library';
      },{image,video});
      await page.addScriptTag({path:'web_ui/clip_cover.js'});
      await page.addScriptTag({path:'web_ui/library_view.js'});
      await page.evaluate(()=>{ui.libraryFilter='all';ui.libraryQuery='';ui.libraryVisibleCount=24;renderLibrary(ui.state.library);});
      assert.equal(await page.locator('#library-grid .video-card').count(),24);
      assert.ok(await page.locator('#library-grid .video-cover').first().evaluate(el=>el.getBoundingClientRect().height<=210));
      const unchanged=await page.evaluate(()=>{const node=document.querySelector('#library-grid .video-card');renderLibrary(ui.state.library);return node===document.querySelector('#library-grid .video-card');});assert.equal(unchanged,true);
      const preserved=await page.evaluate(()=>{const node=document.querySelectorAll('#library-grid .video-card')[1];ui.state.library[0].title='แก้ชื่อเฉพาะรายการแรก';renderLibrary(ui.state.library);return node===document.querySelectorAll('#library-grid .video-card')[1];});assert.equal(preserved,true);
      await page.locator('[data-library-view=list]').click();
      assert.equal(await page.locator('#library-grid').getAttribute('data-mode'),'list');
      assert.equal(await page.evaluate(()=>localStorage.getItem('smartflow.library.view')),'list');
      await page.locator('#library-search').fill('งานเก่าที่ต้องค้นเจอ');
      assert.equal(await page.locator('#library-grid .video-card').count(),1, JSON.stringify(await page.evaluate(()=>({query:ui.libraryQuery,filter:ui.libraryFilter,length:ui.state.library.length,last:ui.state.library.at(-1).title}))) + JSON.stringify(errors));
      await page.locator('#library-search').fill('');
      await page.locator('[data-library-view=grid]').click();
      await page.screenshot({path:`${output}/library-${width}.png`});
      await page.locator('#library-grid [data-library-id]').nth(1).click();
      await page.getByRole('tab',{name:'รายละเอียดไฟล์',exact:true}).waitFor();
      await page.locator('#detail-content video').evaluate(async element=>{await element.play();});
      await page.waitForFunction(()=>document.querySelector('#detail-content video').currentTime>0);
      await page.getByRole('tab',{name:'รายละเอียดไฟล์',exact:true}).click();
      assert.equal(await page.locator('#library-tab-panel-2').isVisible(),true);
      await page.getByRole('tab',{name:'ข้อมูลโพสต์',exact:true}).click();
      await page.locator('#detail-content [data-copy-key=post_text]').click();
      assert.equal(await page.evaluate(()=>window.copied),'ข้อความโพสต์ฉบับเต็ม');
      await page.getByRole('tab',{name:'ปกคลิป',exact:true}).click();
      await page.getByRole('button',{name:'✦ แก้ไขปกคลิป',exact:true}).click();
      await page.locator('.clip-cover-dialog').waitFor({state:'visible'});
      assert.equal(await page.locator('#detail-modal').evaluate(el=>el.open),false);
      assert.equal(await page.locator('#detail-content video').evaluate(el=>el.paused),true);
      await page.locator('[data-cover-close]').click();
      await page.locator('#detail-modal').waitFor({state:'visible'});
      await page.screenshot({path:`${output}/detail-${width}.png`});
      await page.locator('#detail-modal [data-close-modal]').click();
      await page.evaluate(()=>{
        const original=postAction;
        postAction=(action,payload)=>action==='get_library_detail'?new Promise(resolve=>{window.releaseDetail=()=>resolve({ok:true,detail:ui.state.library[1]});}):original(action,payload);
        window.restoreAction=()=>{postAction=original;}; openDetail(ui.state.library[1].item_id);
      });
      await page.locator('#detail-modal [data-close-modal]').click();
      await page.evaluate(async()=>{window.releaseDetail();await Promise.resolve();window.restoreAction();});
      assert.equal(await page.locator('#detail-modal').evaluate(el=>el.open),false);
      await page.locator('[data-filter=longvideo]').click();
      assert.ok(await page.locator('#library-grid .video-card').count()>0);
      await page.locator('[data-filter=drama]').click();
      const group=page.locator('#library-grid details').first();
      assert.equal(await group.getAttribute('open'),null);
      await group.locator('summary').click();
      await page.evaluate(()=>renderLibrary(ui.state.library));
      assert.equal(await group.evaluate(el=>el.open),true);
    }
    assert.deepEqual(errors,[]); console.log('Library UI passed:3 sizes,24/page,125 searchable,stable nodes,grid/list,detail tabs,copy,cover return,series grouping; browser closed.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
