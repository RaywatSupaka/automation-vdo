const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const part=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)+a.length));
const production=part('  function visible(', '  const dismissedDiscoveryCards')+
 part('  function chatGPTConversationFrames(', '  async function revealChatGPTAnswer(')+
 part('  function motionRequestIsLatestUser(', '  function geminiTextRequestHash(')+
 part('  function analysisResponseStopButton(', '  function analysisStopLabel(')+
 part('  function generatedImageElements(', '  function generatedImageUrls(')+
 part('  function coverResultScope(', '  function coverDraftSnapshot(')+
 part('  function coverPromptForRequest(', '  async function runAICover(');
(async()=>{
 const browser=await chromium.launch({headless:true});let checks=0;
 try{for(const variant of ['accepted','pending','wrong_id','wrong_ref','newer_user','wrong_prompt','wrong_url','wrong_request','legacy']){
  const page=await browser.newPage();let network=0;await page.route('**/*',r=>{network++;return r.abort();});
  await page.setContent(fs.readFileSync('tests/fixtures/chatgpt-cover-choice-450.html','utf8'));
  await page.addScriptTag({content:`
   const IS_GEMINI=false, Node=window.Node;
   let clock=1000;Date.now=()=>clock;const sleep=async ms=>{clock+=ms;};
   const assertNotCancelled=()=>{},events=[],coverEvent=async event=>{events.push(structuredClone(event));return {...request,...event};};
   const confirmedStoryImageServiceError=()=>false,storyImageRefusal=()=>false;
   ${production}
   const request={request_id:'a'.repeat(32),title:'เรื่องทดสอบ',aspect_ratio:'9:16',collect_only:true,sources:['reference.jpg'],retry_count:1,
    reference_chain:{version:1,request_id:'a'.repeat(32),provider:'chatgpt',conversation_url:'https://chatgpt.com/c/fixture',reference_count:1,
     reference_user:{index:0,id:'fixture-user-450'},retry_user:{index:1,id:'retry-user-451'}}};
   // Only the URL accessor is stubbed: this isolated page has no provider URL.
   coverConversationURL=()=> 'https://chatgpt.com/c/fixture';
  `});
  await page.evaluate(variant=>{
   const original=document.querySelector('[data-chatgpt-search-unit-key]'),retry=original.cloneNode(true);
   retry.setAttribute('data-chatgpt-search-unit-key','retry:0:user');retry.setAttribute('data-chatgpt-search-message-ids','retry-user-451');
   retry.querySelector('img').remove();retry.querySelector('#owned-prompt').id='retry-prompt';
   const exchange=document.querySelector('#current-exchange'),previous=document.createElement('section');
   exchange.before(previous);previous.append(original);exchange.prepend(retry);
   for(const image of document.images)Object.defineProperties(image,{complete:{value:true},naturalWidth:{value:941},naturalHeight:{value:1672}});
   if(variant==='pending')request.reference_chain.retry_user=null;
   if(variant==='wrong_id')request.reference_chain.reference_user.id='wrong';
   if(variant==='wrong_ref')document.querySelector('[data-asset=reference]').alt='another.jpg';
   if(variant==='wrong_prompt')document.querySelector('#owned-prompt').textContent='Other prompt';
   if(variant==='wrong_url')request.reference_chain.conversation_url='https://chatgpt.com/c/foreign';
   if(variant==='wrong_request')request.reference_chain.request_id='b'.repeat(32);
   if(variant==='legacy')delete request.reference_chain;
   if(variant==='newer_user'){const newer=retry.cloneNode(true);newer.textContent='another request';document.querySelector('main').append(newer);}
  },variant);
  const result=await page.evaluate(async()=>{try{const image=await collectCoverImage(request,0);return{ok:true,asset:image.dataset.asset,events};}catch(error){return{ok:false,message:error.message,events};}});
  assert.equal(result.ok,['accepted','pending'].includes(variant),variant+': '+JSON.stringify({ok:result.ok,message:result.message}));
  if(result.ok){assert.equal(result.asset,'first');if(variant==='pending')assert(result.events.some(e=>e.reference_chain?.retry_user?.id==='retry-user-451'));}
  assert.equal(network,0);checks++;await page.close();
 }
 console.log(JSON.stringify({ok:true,checks,extraSends:0,extraUploads:0,providerNetworkRequests:0}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
