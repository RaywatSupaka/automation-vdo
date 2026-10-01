const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');
const {chromium} = require('playwright');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/src/platforms/meta-ai/video.js'), 'utf8');
const sandbox = {URL, Date, console};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../browser_extension/single_answer.js'), 'utf8'), sandbox);
vm.runInNewContext(source.replaceAll('export ', '') + '\nthis.Adapter=MetaVideoAdapter;this.inspect=inspectMetaDOM;', sandbox);
const clone = x => JSON.parse(JSON.stringify(x));
const pixel='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN1sAAAAASUVORK5CYII=';
const fixturePrompt=process.argv.includes('--package')?JSON.parse(fs.readFileSync(0,'utf8')).prompt:'A cup steams';
const normalizedPrompt=fixturePrompt.replace(/\s+/g,' ').trim();
(async()=>{
  const browser=await chromium.launch({headless:true,
    ...(process.env.SMARTFLOW_TEST_CHROMIUM ? {executablePath:process.env.SMARTFLOW_TEST_CHROMIUM} : {})});
  try {
    const page=await browser.newPage({viewport:{width:1100,height:900}});
    await page.route('**/*',route=>route.abort());
    await page.setContent(`<main><div id="visible"><div role="textbox" contenteditable="true" data-lexical-editor="true" style="width:600px;height:150px">A cup steams</div><div><button aria-label="เพิ่มไฟล์แนบ">+</button><input type="file" accept="image/png" hidden></div></div><div style="display:none"><div role="textbox" contenteditable="true" data-lexical-editor="true"></div><input type="file" accept="image/png"></div><button aria-label="ส่ง">Send</button></main><div role="dialog" aria-label="เพิ่มสื่อและไฟล์"><h2>เพิ่มสื่อและไฟล์</h2></div>`);
    await page.locator('#visible [contenteditable]').fill(fixturePrompt);
    let state;
    // Evaluate the exact production function with its real two-argument signature.
    const scan=()=>page.evaluate(({fn,prompt})=>new Function('return ('+fn+')')()(prompt,'scene.png'),{fn:sandbox.inspect.toString(),prompt:fixturePrompt});
    state=await scan(); assert.equal(state.fileInput,true); assert.equal(state.composerText,normalizedPrompt);
    assert.equal(await page.locator('[data-smartflow-meta-file]').count(),1);
    assert.equal(await page.locator('#visible [data-smartflow-meta-file]').count(),1);
    await page.evaluate(pixel=>{
      document.querySelector('[role="dialog"]').remove();
      const img=document.createElement('img'); img.src=pixel; img.alt='scene.png';
      Object.defineProperties(img,{complete:{value:false},naturalWidth:{value:720},naturalHeight:{value:1280}});
      document.querySelector('[contenteditable]').append(img);
    },pixel);
    state=await scan(); assert.equal(state.imageReady,false); assert.equal(state.composerText,normalizedPrompt);
    await page.evaluate(({pixel,prompt})=>{
      const img=document.querySelector('img'); img.remove();
      const user=document.createElement('div'); user.setAttribute('role','article');user.setAttribute('aria-label','ข้อความของคุณ');
      user.textContent=prompt; const ref=document.createElement('img');ref.src=pixel;ref.alt='scene.png';
      Object.defineProperties(ref,{complete:{value:true},naturalWidth:{value:720}});user.append(ref);document.body.append(user);
      const result=document.createElement('div');result.setAttribute('role','article');result.setAttribute('aria-label','การตอบกลับของ Meta AI');
      result.innerHTML='<video src="https://media.invalid/this-video.mp4"></video>';document.body.append(result);
      Object.defineProperties(result.querySelector('video'),{readyState:{value:4},videoWidth:{value:720},duration:{value:10}});
    },{pixel,prompt:fixturePrompt});
    state=await scan();assert.equal(state.matchedUser,true);assert.equal(state.videoReady,true);
    await page.evaluate(()=>{const btn=document.createElement('button');btn.setAttribute('aria-label','หยุด');btn.textContent='Stop';document.body.append(btn);});
    assert.equal((await scan()).videoReady,false);
    await page.evaluate(()=>{document.querySelector('button[aria-label="หยุด"]').remove();document.querySelector('[role="article"]').appendChild(document.createTextNode(''));const clone=document.querySelector('[role="article"]').cloneNode(true);document.body.append(clone);});
    assert.equal((await scan()).matchedUser,false);

    let receipt={job_id:'STORY-TEST',index:1,request_id:'abc123',context_id:'ctx',stage:'ready_to_send',prompt:fixturePrompt,image_name:'scene.png'};
    const storage={}, session={}, events=[], physical=[], closed=[];
    const api=async(route,body)=>{if(!body)return {ok:true,package:clone(receipt)};events.push(body.stage);receipt={...receipt,...body};return {ok:true,receipt:clone(receipt)};};
    let dom={composerFound:true,documentReady:true,documentId:'document-fixture',observedURL:'https://www.meta.ai/prompt/test',
      composerText:normalizedPrompt,imageReady:true,imageCount:1,imageName:'scene.png',imageSource:'blob:scene',sendTarget:'send-node',send:{x:1,y:2},busy:false,userCount:0};
    const chrome={runtime:{id:'extension'},storage:{local:{get:async()=>clone(storage),set:async obj=>Object.assign(storage,clone(obj))},
      session:{get:async()=>clone(session),set:async obj=>Object.assign(session,clone(obj))}},
      tabs:{get:async()=>({url:'https://www.meta.ai/prompt/test',status:'complete'}),remove:async id=>closed.push(id)},
      downloads:{download:async()=>{physical.push('download');return 7;},search:async()=>[{id:7,state:'complete',filename:'C:/Downloads/meta.mp4',exists:true}]},
      debugger:{attach:async()=>{},detach:async()=>{},sendCommand:async(target,method,params)=>{
        assert.equal(method,'Input.dispatchMouseEvent');if(params.type==='mouseReleased')physical.push('send');return {};}}};
    const adapter=new sandbox.Adapter({api,chromeAPI:chrome});adapter.inspect=async()=>({...dom,composerWireText:dom.composerText?sandbox.SmartFlowSingleAnswer.wrap(dom.composerText):''});adapter.click=async()=>physical.push('send');
    let row={...receipt,tabId:11};await adapter.save(row);await adapter.own(row);
    await adapter.step(row);assert.deepEqual(physical,['send']);assert.equal(receipt.stage,'send_intent');
    await adapter.step(row);assert.deepEqual(physical,['send']); // Unknown Send is NOT repeated.
    dom={...dom,userCount:1,matchedUser:true,conversation:'https://www.meta.ai/prompt/test'};
    await adapter.step(row);assert.equal(receipt.stage,'send_intent','Echo with unchanged draft is not acceptance');
    dom={...dom,composerText:'',imageCount:0};
    await adapter.step(row);assert.equal(receipt.stage,'submitted');
    await adapter.step(row);assert.equal(receipt.stage,'generating');
    dom={...dom,stop:true,videoReady:false};await adapter.step(row);assert.equal(receipt.stage,'generating');
    dom={...dom,stop:false,videoReady:true,videoSrc:'https://media.invalid/this-video.mp4'};
    await adapter.step(row);assert.equal(receipt.stage,'downloading');assert.deepEqual(closed,[]);
    // Simulate worker restart: durable row, no duplicate Send/download.
    const restarted=new sandbox.Adapter({api,chromeAPI:chrome});restarted.inspect=async()=>dom;
    row=(await restarted.records()).abc123;await restarted.step(row);assert.equal(receipt.stage,'stored');assert.deepEqual(closed,[]);
    await restarted.step(row);assert.deepEqual(closed,[11]);assert.deepEqual(physical,['send','download']);
    assert(!JSON.stringify(storage).includes('media.invalid'),'signed media source must not be persisted');
    assert(events.indexOf('stored')>events.indexOf('downloading'));
    console.log('Meta DOM and controller: 18 assertions passed; no live network or provider generations');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
