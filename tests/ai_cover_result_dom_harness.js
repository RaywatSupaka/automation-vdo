const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
const root=path.join(__dirname,'..'),src=fs.readFileSync(path.join(root,'browser_extension/chatgpt.js'),'utf8');
const part=(a,b)=>src.slice(src.indexOf(a),src.indexOf(b,src.indexOf(a)+a.length));
(async()=>{const browser=await chromium.launch({headless:true});try{
  const page=await browser.newPage();await page.route('**/*',r=>r.abort());
  const fixture=fs.readFileSync(path.join(__dirname,'fixtures/chatgpt-cover-sibling-327.html'),'utf8');
  await page.setContent(fixture);await page.addStyleTag({content:'img{width:320px;height:570px}'});
  await page.addScriptTag({content:`let IS_GEMINI=false;const visible=()=>true;`+
    part('  function chatGPTConversationFrames(','  function explicitImageFailure(')+
    part('  function generatedImageElements(','  function generatedImageUrls(')+
    part('  function coverResultScope(','  async function collectCoverImage(')});
  await page.evaluate(()=>{for(const image of document.images){Object.defineProperties(image,{
    complete:{value:true,configurable:true},naturalWidth:{value:941,configurable:true},naturalHeight:{value:1672,configurable:true}});}});
  const current=await page.evaluate(()=>({old:generatedImageElements(latestAssistantStrictlyAfterLatestUser()).length,
    scope:coverResultScope().getAttribute('data-testid'),count:coverResultImages(coverResultScope()).length,
    owned:coverRecoveryOwnsReferences({request_id:'a'.repeat(32),sources:['1.jpg','2.jpg']}),
    wrong:coverRecoveryOwnsReferences({request_id:'b'.repeat(32),sources:['1.jpg','2.jpg']})}));
  assert.deepEqual(current,{old:0,scope:'conversation-turn-2',count:1,owned:true,wrong:false});
  await page.evaluate(()=>{for(const image of document.images)image.getBoundingClientRect=()=>({width:0,height:0});});
  assert.equal(await page.evaluate(()=>generatedImageElements(coverResultScope()).length),3,'Decoded owned image layers survive collapsed layout; cover collector still deduplicates');
  assert.equal(await page.evaluate(()=>coverResultImages(coverResultScope()).length),1,'Loaded owned cover survives background/collapsed layout');
  await page.addScriptTag({content:part('  function motionRequestIsLatestUser(', '  function geminiTextRequestHash(')+
    part('  async function collectCoverImage(', '  async function runAICover(')+`
    const assertNotCancelled=()=>{}, analysisResponseStopButton=()=>null;
    const coverEvent=async event=>{window.coverEvents.push(event);return {phase:event.phase};};
    let testClock=1000;const sleep=async ms=>{testClock+=ms;};
    `});
  const collected=await page.evaluate(async()=>{
    window.coverEvents=[];const realNow=Date.now;Date.now=()=>testClock;
    try{const image=await collectCoverImage({request_id:'a'.repeat(32),title:'เรื่องทดสอบ',aspect_ratio:'9:16',
      collect_only:true,sources:['1.jpg','2.jpg']},0);
      return {width:image.naturalWidth,height:image.naturalHeight,elapsed:Date.now()-1000};
    }finally{Date.now=realNow;}
  });
  assert.deepEqual(collected,{width:941,height:1672,elapsed:3500},'Actual collector recovers hidden existing result without any Send/upload helpers');
  await page.evaluate(()=>{for(const image of document.querySelectorAll('#image-cover-fixture img')){
    image.setAttribute('width','941');image.setAttribute('height','1672');
    Object.defineProperties(image,{complete:{value:false,configurable:true},naturalWidth:{value:0,configurable:true},naturalHeight:{value:0,configurable:true}});
  }});
  assert.deepEqual(await page.evaluate(()=>{const imgs=coverResultImages(coverResultScope());return {candidates:imgs.length,loaded:imgs.filter(i=>i.complete&&i.naturalWidth>=256).length};}),
    {candidates:1,loaded:0},'Hidden declared image stays loading, never no-image completion');
  await page.evaluate(()=>{for(const image of document.images)Object.defineProperties(image,{
    complete:{value:true,configurable:true},naturalWidth:{value:941,configurable:true},naturalHeight:{value:1672,configurable:true}});});
  await page.evaluate(()=>{for(const image of document.images)delete image.getBoundingClientRect;});
  assert.equal(await page.evaluate(()=>coverResultImages(coverResultScope(),new Set(['https://chatgpt.com/backend-api/estuary/content?id=file_cover'])).length),0);
  await page.evaluate(()=>document.querySelector('#image-cover-fixture img').src='https://chatgpt.com/backend-api/estuary/content?id=other_cover');
  assert.equal(await page.evaluate(()=>coverResultImages(coverResultScope()).length),2,'Different assets must not collapse');
  await page.evaluate(()=>document.querySelector('[data-message-author-role=assistant]').remove());
  assert.equal(await page.evaluate(()=>coverResultScope().getAttribute('data-testid')),'conversation-turn-2','Image-only answer');
  await page.evaluate(()=>{const e=document.createElement('div');e.dataset.messageAuthorRole='user';e.textContent='new unrelated request';document.body.append(e);});
  assert.equal(await page.evaluate(()=>coverResultScope()),null,'Never recover a previous answer after a new user turn');
  await page.setContent('<user-query>current request</user-query><model-response><img style="width:320px;height:570px" src="https://lh3.googleusercontent.com/fixture"><span>done</span></model-response>');
  assert.equal(await page.evaluate(()=>{IS_GEMINI=true;return coverResultImages(coverResultScope()).length;}),1,'Gemini scope preserved');
  console.log('Cover observed DOM: sibling media, three duplicate layers, exact references, prior assets, two outputs, image-only, wrong-turn and Gemini passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
