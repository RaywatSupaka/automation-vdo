// Native isolated Chromium; real production ownership, image discovery, Stop,
// deduplication and collector functions. Only decoded metadata/time/bridge are
// simulated. No user profile, media download, upload, preference vote or Send.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.SMARTFLOW_TEST_PLAYWRIGHT_PACKAGE||'playwright');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'browser_extension/chatgpt.js'),'utf8');
const markup=fs.readFileSync(path.join(__dirname,'fixtures/chatgpt-cover-choice-450.html'),'utf8');
const part=(start,end)=>{
  const from=source.indexOf(start),to=source.indexOf(end,from+start.length);
  assert(from>=0&&to>from,`actual production boundary: ${start}`);
  return source.slice(from,to);
};
const production=[
  part('  function visible(', '  const dismissedDiscoveryCards'),
  part('  function chatGPTConversationFrames(', '  async function revealChatGPTAnswer('),
  part('  function motionRequestIsLatestUser(', '  function geminiTextRequestHash('),
  part('  function analysisResponseStopButton(', '  function analysisStopLabel('),
  part('  function generatedImageElements(', '  function generatedImageUrls('),
  part('  function coverResultScope(', '  function coverDraftSnapshot('),
  source.includes('  function coverPromptForRequest(')?part('  function coverPromptForRequest(', '  async function collectCoverImage('):'',
  part('  async function collectCoverImage(', '  async function runAICover(')
].join('\n');
let checks=0,scenarios=0,providerNetworkRequests=0,providerActions=0;
const eq=(actual,expected,message)=>{assert.deepEqual(actual,expected,message);checks++;};
const yes=(condition,message)=>{assert(condition,message);checks++;};
async function fixture(browser,config={}){
  const page=await browser.newPage();
  let networkRequests=0;
  await page.route('**/*',route=>{networkRequests++;return route.abort();});
  await page.setContent(markup);
  await page.addScriptTag({content:`
    let IS_GEMINI=${!!config.gemini};
    const fixture={clock:1000,start:1000,sleeps:0,events:[],forbidden:[],clicks:[],config:${JSON.stringify(config)}};
    const request={request_id:'a'.repeat(32),title:'เรื่องทดสอบ',aspect_ratio:'9:16',collect_only:true,sources:['reference.jpg']};
    Date.now=()=>fixture.clock;
    const coverEvent=async event=>{fixture.events.push(structuredClone(event));return {phase:event.phase};};
    const assertNotCancelled=()=>{};
    const forbid=name=>()=>{fixture.forbidden.push(name);throw Error('fixture forbids '+name);};
    const waitForResponseIdle=forbid('waitForResponseIdle'),prepareCoverImageTool=forbid('prepareCoverImageTool');
    const waitForComposer=forbid('waitForComposer'),attachSourceImages=forbid('attachSourceImages');
    const setComposerText=forbid('setComposerText'),waitForStableSendDraft=forbid('waitForStableSendDraft');
    const sendCoverAndVerify=forbid('sendCoverAndVerify'),sendGeminiImageAndVerify=forbid('sendGeminiImageAndVerify');
    window.fetch=forbid('fetch');XMLHttpRequest.prototype.open=forbid('xhr');
    document.addEventListener('click',event=>fixture.clicks.push(event.target.id||event.target.tagName),true);
    const decoded=(image,loaded=true)=>Object.defineProperties(image,{
      complete:{value:loaded,configurable:true},naturalWidth:{value:loaded?Number(image.getAttribute('width'))||941:0,configurable:true},
      naturalHeight:{value:loaded?Number(image.getAttribute('height'))||1672:0,configurable:true}
    });
    const sleep=async ms=>{
      fixture.clock+=ms;if(++fixture.sleeps>1100)throw Error('fixture wait bound exceeded');
      const elapsed=fixture.clock-fixture.start,c=fixture.config;
      if(c.firstReadyAt&&elapsed>=c.firstReadyAt)decoded(document.querySelector('[data-asset=first]'));
      if(c.stopUntil&&elapsed>=c.stopUntil)document.querySelector('[data-testid=stop-button]')?.remove();
      if(c.newUserAt&&elapsed>=c.newUserAt&&!fixture.newUser){
        fixture.newUser=true;const node=document.createElement('div');
        node.setAttribute('data-chatgpt-search-unit-key','later-fixture:0:user');
        node.textContent='A different later request';document.querySelector('main').append(node);
      }
    };
    ${production}
  `});
  await page.evaluate(config=>{
    if(config.gemini){
      const user=document.createElement('user-query');
      user.innerHTML=document.querySelector('[data-user-message-bubble]').innerHTML;
      const response=document.createElement('model-response');response.innerHTML=document.querySelector('#owned-answer').innerHTML;
      document.querySelector('main').replaceChildren(user,response);
      for(const image of response.querySelectorAll('img'))image.src=image.src.replace('https://chatgpt.com/','https://gemini.google.com/');
    }
    for(const image of document.images)decoded(image,!config.firstLoading||image.dataset.asset!=='first');
    if(config.duplicate){
      const first=document.querySelector('[data-asset=first]'),copy=first.cloneNode(true);
      copy.dataset.asset='first-duplicate';first.parentElement.append(copy);decoded(copy);
    }
    if(config.single)document.querySelector('[data-asset=second]').closest('[data-testid=generated-image-gallery]').remove();
    if(config.noImages){
      document.querySelector('#owned-answer').replaceChildren();
    }
    if(config.wrongLatest)document.querySelector('#owned-prompt').textContent='Different request';
    if(config.wrongReference)document.querySelector('[data-asset=reference]').alt='smartflow-cover-'+ 'b'.repeat(32)+'-1.jpg';
    if(config.stopUntil){
      const stop=document.createElement('button');stop.dataset.testid='stop-button';
      stop.setAttribute('aria-label','หยุดการสร้าง');stop.textContent='หยุด';document.querySelector('form').append(stop);
    }
  },config);
  return {page,networkRequests:()=>networkRequests,run:()=>page.evaluate(async()=>{
    try{
      const image=await collectCoverImage(request,0);
      return {ok:true,asset:image.dataset.asset,key:coverImageKey(image),width:image.naturalWidth,height:image.naturalHeight,elapsed:fixture.clock-fixture.start};
    }catch(error){return {ok:false,error:error.message,elapsed:fixture.clock-fixture.start};}
  }),state:()=>page.evaluate(()=>({clicks:fixture.clicks,forbidden:fixture.forbidden,events:fixture.events,
    candidates:coverResultImages(coverResultScope()).map(image=>image.dataset.asset),
    owns:motionRequestIsLatestUser('สร้างปกคลิป Shorts\nชื่อคลิป: เรื่องทดสอบ')&&coverRecoveryOwnsReferences(request)}))};
}
async function scenario(browser,config,verify){
  const f=await fixture(browser,config);
  try{
    await verify(f);const state=await f.state();
    eq(state.clicks,[],'no preference vote, Skip, Stop or Send click');
    eq(state.forbidden,[],'collect_only never prepares, attaches, sends or fetches');
    eq(f.networkRequests(),0,'synthetic blob fixture makes no network request');
    providerNetworkRequests+=f.networkRequests();providerActions+=state.clicks.length+state.forbidden.length;
    scenarios++;
  }finally{await f.page.close();}
}
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.SMARTFLOW_TEST_CHROMIUM||undefined});
  try{
    await scenario(browser,{},async f=>{
      const state=await f.state();eq(state.candidates,['first','second'],'only two owned gallery assets; no old/reference');eq(state.owns,true);
      const result=await f.run();
      if(process.argv.includes('--reproduce-449')){
        eq(result.ok,false);yes(/6 นาที/.test(result.error),'old collector stalls on two decoded covers');eq(result.elapsed,360500);
        yes((await f.state()).events.some(event=>event.collector_state?.stage==='multiple_images'),'old multiple_images status observed');
        console.log(JSON.stringify({ok:true,reproduced:'449 rejects two loaded covers',nativeDom:true,result,checks}));return;
      }
      eq(result.ok,true,JSON.stringify(result));eq(result.asset,'first','first decoded image is deterministic');eq(result.elapsed,3500,'two covers do not wait six minutes');
      eq([result.width,result.height],[941,1672]);
    });
    if(process.argv.includes('--reproduce-449'))return;
    await scenario(browser,{firstLoading:true},async f=>{const result=await f.run();eq(result.ok,true,JSON.stringify(result));eq(result.asset,'second');eq(result.elapsed,3500);});
    await scenario(browser,{firstLoading:true,firstReadyAt:700},async f=>{const result=await f.run();eq(result.ok,true);eq(result.asset,'second','later first image cannot replace selected decoded second');eq(result.elapsed,3500);});
    await scenario(browser,{duplicate:true},async f=>{eq((await f.state()).candidates,['first','second'],'layers are deduplicated by asset key');const result=await f.run();eq(result.asset,'first');eq(result.elapsed,3500);});
    await scenario(browser,{single:true},async f=>{const result=await f.run();eq(result.asset,'first','legacy one-image cover preserved');eq(result.elapsed,3500);});
    await scenario(browser,{stopUntil:4200},async f=>{const result=await f.run();eq(result.asset,'first');eq(result.elapsed,7700,'idle plus full stability window required');});
    await scenario(browser,{stopUntil:364700},async f=>{const result=await f.run();eq(result.asset,'first');eq(result.elapsed,368200,'real active generation may exceed six minutes without Stop or timeout');yes((await f.state()).events.some(event=>event.collector_state?.stage==='generating'));});
    await scenario(browser,{wrongLatest:true},async f=>{const result=await f.run();eq(result.ok,false);eq(result.elapsed,0);yes(/ยังยืนยันคำขอ/.test(result.error));});
    await scenario(browser,{wrongReference:true},async f=>{const result=await f.run();eq(result.ok,false);eq(result.elapsed,0);yes(/ยังยืนยันคำขอ/.test(result.error));});
    await scenario(browser,{newUserAt:1400},async f=>{const result=await f.run();eq(result.ok,false);yes(/6 นาที/.test(result.error));eq((await f.state()).owns,false,'later user revokes result ownership');});
    await scenario(browser,{noImages:true},async f=>{const result=await f.run();eq(result.ok,false);yes(/6 นาที/.test(result.error));eq(result.elapsed,360500,'idle no-result inactivity guard remains');});
    await scenario(browser,{gemini:true},async f=>{const result=await f.run();eq(result.ok,true,JSON.stringify(result));eq(result.asset,'first','Gemini also returns one usable cover');eq(result.elapsed,3500);});
    console.log(JSON.stringify({ok:true,nativeDom:true,checks,scenarios,providerNetworkRequests,providerActions}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
