const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const {chromium} = require('playwright');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/src/platforms/meta-ai/video.js'), 'utf8');
const sandbox = {URL, Date};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../browser_extension/single_answer.js'), 'utf8'), sandbox);
vm.runInNewContext(source.replaceAll('export ', '') + '\nthis.Adapter=MetaVideoAdapter;this.inspect=inspectMetaDOM;', sandbox);
const clone = x => JSON.parse(JSON.stringify(x));
const prompt = 'บทสนทนาของฉากนี้ '.repeat(180).trim();
let cases = 0;
function controller(dom, changes = {}) {
  let receipt = {job_id:'STORY-FIXTURE', index:1, request_id:'request', context_id:'context',
    stage:'prepared', prompt, image_name:'scene.png', ...changes};
  const storage = {}, events = [], physical = [];
  const api = async (route, body) => {
    if (!body) return {package:clone(receipt)};
    events.push(clone(body)); receipt = {...receipt,...body};
    return {receipt:clone(receipt)};
  };
  const chrome = {storage:{local:{get:async()=>clone(storage),set:async value=>Object.assign(storage,clone(value))}},
    tabs:{get:async()=>({url:'https://www.meta.ai/?locale=th_TH',status:'complete'})}};
  const adapter = new sandbox.Adapter({api,chromeAPI:chrome});
  adapter.owns = async()=>true;
  adapter.inspect = async()=>({...dom,composerWireText:dom.composerText?sandbox.SmartFlowSingleAnswer.wrap(dom.composerText):''});
  adapter.click = async()=>physical.push('click');
  adapter.debug = async(id,fn)=>fn(async(method,params)=>{
    if(method==='Input.dispatchMouseEvent'){if(params.type==='mouseReleased')physical.push('click');}
    else physical.push(method);
  });
  return {adapter,row:{...receipt,tabId:1,textIntent:true},events,physical,
    receipt:()=>receipt, setDOM:value=>dom=value};
}
(async()=>{
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1920,height:889}});
    await page.route('**/*',route=>route.abort());
    // Live 54B287 geometry: center(1088,63) hits the header, not the editor.
    await page.setContent('<div id="editor" role="textbox" contenteditable="true" data-lexical-editor="true" style="position:fixed;left:724px;top:-423px;width:728px;height:972px;overflow:hidden"></div><div id="header" style="position:fixed;top:0;left:0;right:0;height:120px;background:white"></div>');
    await page.locator('#editor').evaluate((n,text)=>{n.textContent=text;},prompt);
    const scan=()=>page.evaluate(({fn,prompt})=>new Function('return ('+fn+')')()(prompt,'scene.png'),{fn:sandbox.inspect.toString(),prompt});
    let state=await scan();
    assert.equal(state.composer,null,'378 center-hit guard must reproduce the observed blocker');
    assert.equal(state.composerFound,true); assert.equal(state.composerText,prompt);
    let c=controller(state); await c.adapter.step(c.row);
    assert.equal(c.receipt().stage,'uploading'); assert.deepEqual(c.physical,[]); cases++;
    // Existing filled draft is sufficient even when textIntent was not persisted.
    c=controller(state); delete c.row.textIntent; await c.adapter.step(c.row);
    assert.equal(c.receipt().stage,'uploading'); assert.deepEqual(c.physical,[]); cases++;
    // Completely off-screen center and compact viewport do not erase DOM text.
    await page.setViewportSize({width:360,height:740});
    state=await scan(); assert.equal(state.composer,null);
    c=controller(state); await c.adapter.step(c.row); assert.equal(c.receipt().stage,'uploading'); cases++;
    // A wrong draft must not be accepted merely because a readable editor exists.
    c=controller({...state,composerText:'another prompt'}); await c.adapter.step(c.row);
    assert.equal(c.receipt().stage,'needs_attention'); assert.deepEqual(c.physical,[]); cases++;
    // More than one visible editor: do not choose the first or edit either.
    await page.evaluate(()=>{const n=document.querySelector('#editor').cloneNode(true);n.id='second';document.body.append(n);});
    state=await scan(); assert.equal(state.composerFound,false); assert.equal(state.composerCount,2);
    c=controller(state); await c.adapter.step(c.row); await c.adapter.step(c.row);
    assert.equal(c.receipt().stage,'prepared'); assert.equal(c.events.length,1);
    assert.match(c.receipt().message,/รอช่องข้อความ/); assert.deepEqual(c.physical,[]); cases++;
    await page.evaluate(()=>{document.querySelector('#second').remove();document.querySelector('#editor').style.display='none';});
    state=await scan(); assert.equal(state.composerFound,false);
    c=controller(state); await c.adapter.step(c.row); assert.equal(c.receipt().stage,'prepared'); cases++;
    const ready={composerFound:true,composerText:prompt,composer:null,userCount:0,busy:false,stop:false,
      documentReady:true,documentId:'document-fixture',observedURL:'https://www.meta.ai/',sendTarget:'send-node'};
    for(const blocker of ['busy','stop']){
      c=controller({...ready,[blocker]:true}); await c.adapter.step(c.row); await c.adapter.step(c.row);
      assert.equal(c.receipt().stage,'prepared'); assert.equal(c.events.length,1); assert.deepEqual(c.physical,[]);
      c.setDOM(ready); await c.adapter.step(c.row); assert.equal(c.receipt().stage,'uploading'); cases++;
    }
    c=controller({...ready,userCount:1}); await c.adapter.step(c.row);
    assert.equal(c.receipt().stage,'needs_attention'); cases++;
    // Empty editor still needs a real click target; never type into another app.
    c=controller({...ready,composerText:''}); delete c.row.textIntent;
    await c.adapter.step(c.row); await c.adapter.step(c.row);
    assert.equal(c.events.length,1); assert.match(c.receipt().message,/คลิกไม่ได้/); assert.deepEqual(c.physical,[]);
    c.setDOM({...ready,composerText:'',composer:{x:30,y:30}}); await c.adapter.step(c.row);
    assert.deepEqual(c.physical,['click','Input.insertText']);
    c.setDOM(ready); await c.adapter.step(c.row); assert.equal(c.receipt().stage,'uploading'); cases++;
    // Lost text after a durable insertion intent must not be blindly retyped.
    c=controller({...ready,composerText:''}); await c.adapter.step(c.row);
    assert.equal(c.receipt().stage,'needs_attention'); assert.deepEqual(c.physical,[]); cases++;
    // Send remains blocked until the exact attached image is fully loaded.
    for(const extra of [{imageReady:false},{busy:true},{imageName:'wrong.png'}]){
      c=controller({...ready,imageCount:1,imageName:'scene.png',imageReady:true,send:{x:1,y:2},...extra},{stage:'ready_to_send'});
      await c.adapter.step(c.row); assert.deepEqual(c.physical,[]); assert.equal(c.receipt().stage,'ready_to_send'); cases++;
    }
    c=controller({...ready,imageCount:1,imageName:'scene.png',imageReady:true,send:{x:1,y:2}},{stage:'ready_to_send'});
    await c.adapter.step(c.row); await c.adapter.step(c.row);
    assert.equal(c.receipt().stage,'send_intent'); assert.deepEqual(c.physical,['click']); cases++;
    // Context mismatch remains a hard no-action boundary.
    c=controller(ready); c.row.context_id='old'; await c.adapter.step(c.row);
    assert.equal(c.events.length,0); assert.deepEqual(c.physical,[]); cases++;
    console.log(`Meta prepared379: ${cases} cases passed; actual DOM geometry, no retyping/resend, wait reasons and guards`);
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
