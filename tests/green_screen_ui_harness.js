const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1000,height:850}});
  const root=path.join(__dirname,'../web_ui');
  const html=fs.readFileSync(path.join(root,'index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
  await page.route('**/*',r=>r.request().url().includes('/api/desktop/green-asset?')
    ?r.fulfill({status:200,contentType:'video/mp4',body:fs.readFileSync(process.argv[2])})
    :r.request().url()==='http://smartflow.test/'?r.fulfill({contentType:'text/html',body:html}):r.abort());
  await page.goto('http://smartflow.test/');
  for(const match of html.matchAll(/href="\/desktop\/([^"?]+\.css)(?:\?[^" ]*)?"/g))await page.addStyleTag({content:fs.readFileSync(path.join(root,match[1]),'utf8')});
  await page.evaluate(()=>{document.querySelectorAll('.page').forEach(n=>n.classList.remove('active'));const box=document.createElement('div');box.id='creation-form';box.innerHTML='<div class="cq-buttons"></div>';document.body.append(box);});
  await page.addScriptTag({content:`const pageMeta={},ui={activePage:'green'};let calls=[];
    const files=['a','b','c','d'].map(c=>'assets/screenfx/'+c.repeat(64)+'.mp4');
    let state={settings:{enabled:false,clips:[],opacity:.5,fit:'contain'},targets:{story:false,drama:false,product:false},assets:files.map((file,i)=>({file,name:'แสง '+(i+1)+'.mp4',duration:i+1}))};
    function showPage(p){ui.activePage=p;}
    let postAction=async(action,payload={})=>{calls.push({action,payload});if(action==='green_status')return{ok:true,...state};
      if(action==='green_save'){state={...state,settings:{...payload.settings,enabled:Object.values(payload.targets).some(Boolean)},targets:payload.targets};return{ok:true,...state};}
      if(action==='green_preview')return{ok:true,url:'/api/desktop/green-preview?token='+('f'.repeat(32)),duration:6};return{ok:true};};
    let uploaded=[];window.fetch=async(url,opts)=>{uploaded.push({url,name:opts.body.name});return{ok:true,json:async()=>({ok:true,...state})};};`});
  const audio=fs.readFileSync(path.join(root,'media_audio.js'),'utf8');
  await page.addScriptTag({content:audio.slice(audio.indexOf('window.smartflowCreationFormKey'),audio.indexOf('  const panels'))});
  await page.addScriptTag({content:fs.readFileSync(path.join(root,'green_screen.js'),'utf8')});
  await page.waitForFunction(()=>document.querySelectorAll('#green-assets input').length===4);
  const chooser=page.waitForEvent('filechooser');await page.locator('#green-upload-button').click();
  await(await chooser).setFiles({name:'ไฟเขียว.mp4',mimeType:'video/mp4',buffer:Buffer.from('test video')});
  await page.waitForFunction(()=>document.querySelector('#green-status').textContent.includes('อัปโหลดแล้ว'));
  assert.equal(await page.evaluate(()=>uploaded[0].url),'/api/desktop/green-upload');
  for(let i=0;i<3;i++)await page.locator('#green-assets input').nth(i).check();
  assert.equal(await page.locator('#green-assets input').nth(3).isEnabled(),false);
  await page.locator('#green-order button').nth(1).click(); // A down: B,A,C
  await page.locator('[data-green-target="story"]').check();
  await page.locator('[data-green-target="product"]').check();
  await page.locator('#green-save').click();
  await page.waitForFunction(()=>document.querySelector('#green-status').textContent.includes('บันทึกแล้ว'));
  assert.deepEqual(await page.evaluate(()=>state.settings.clips.map(c=>c.file)),await page.evaluate(()=>[files[1],files[0],files[2]]));
  const rows=await page.evaluate(async()=>{
    const result=[];for(const [action,mode] of [['create_story','story'],['enqueue_story_batch','story'],['create_drama_series','drama'],['create_product','product'],['creation_enqueue','product']]){
      await postAction(action,{mode,render_options:{}});result.push(calls.at(-1));
    }await postAction('create_story',{job_id:'OLD'});result.push(calls.at(-1));return result;
  });
  assert.deepEqual(rows.slice(0,5).map(r=>r.payload.green_options.enabled),[true,true,false,true,true]);
  for(const row of rows.slice(0,5))assert.deepEqual(row.payload.render_options.green_options,row.payload.green_options);
  assert.equal(rows.at(-1).payload.green_options,undefined,'resume must not adopt new defaults');
  const started=Date.now();
  await page.locator('#green-preview-button').click();
  await page.waitForFunction(()=>document.querySelector('#green-preview-source').currentTime>.05);
  console.log('First moving browser preview (local fixture): '+(Date.now()-started)+' ms');
  assert.equal(await page.locator('#green-preview-source').evaluate(e=>e.muted&&e.volume===0),true);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='green_preview').length),0,'live preview must not encode an offline video');
  const pixel=()=>page.locator('#green-preview').evaluate(c=>Array.from(c.getContext('2d').getImageData(30,185,1,1).data));
  await page.waitForFunction(()=>document.querySelector('#green-preview').getContext('2d').getImageData(30,185,1,1).data[0]>90);
  const before=await pixel();
  await page.locator('#green-opacity').evaluate(e=>{e.value='100';e.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(()=>document.querySelector('#green-preview').getContext('2d').getImageData(30,185,1,1).data[0]>200);
  assert((await pixel())[0]>before[0],'opacity changes the real decoded frame without a render');
  assert.deepEqual(await page.locator('#green-preview').evaluate(c=>Array.from(c.getContext('2d').getImageData(200,185,1,1).data)),[39,54,80,255],'green pixels become the demo background');
  await page.waitForFunction(()=>document.querySelector('#green-status').textContent.includes('2/3'));
  await page.waitForFunction(()=>document.querySelector('#green-status').textContent.includes('3/3'));
  await page.waitForFunction(()=>document.querySelector('#green-status').textContent.includes('1/3'));
  await page.locator('#green-preview-button').click();
  assert.equal(await page.locator('#green-preview-source').evaluate(e=>e.paused&&!e.getAttribute('src')),true);
  await page.locator('#green-preview-button').click();
  await page.waitForFunction(()=>document.querySelector('#green-preview-source').currentTime>.05);
  await page.evaluate(()=>document.querySelector('[data-view="green"]').classList.remove('active'));
  await page.waitForFunction(()=>!document.querySelector('#green-preview-source').getAttribute('src'));
  await page.evaluate(()=>document.querySelector('[data-view="green"]').classList.add('active'));
  await page.locator('#green-preview-button').click();
  await page.evaluate(()=>document.querySelector('#green-preview-source').dispatchEvent(new Event('error')));
  await page.waitForFunction(()=>document.querySelector('#green-status').textContent.includes('MP4'));
  assert.equal(await page.locator('#green-preview-button').isEnabled(),true,'decode failure must not lock settings');
  for(const width of [1000,600]){
    await page.setViewportSize({width,height:850});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  }
  console.log('Green screen UI: browser picker, 3-file limit, order, defaults, five routes, old resume, silent preview, 600px passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
