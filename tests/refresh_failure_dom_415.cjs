const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const background=fs.readFileSync('browser_extension/background.js','utf8');
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const section=(source,name,indent='')=>{
 const at=source.search(new RegExp('(?:async )?function '+name+'\\('));assert(at>=0,name);
 return source.slice(at,source.indexOf('\n'+indent+'}',at)+indent.length+2);
};
const fixture=new Function('require',fs.readFileSync('tests/story_image_wait_342_harness.js','utf8').split('(async()=>')[0]+';return fixture;')(require);
const failure='Something went wrong while generating your image. Sorry about that.';
(async()=>{
 let cases=0,probe;
 const ctx=vm.createContext({Date,setTimeout,chrome:{scripting:{executeScript:async({func})=>{probe=func;return [{result:{ready:true}}];}}}});
 vm.runInContext(section(background,'waitForAIRefreshReady'),ctx);
 await ctx.waitForAIRefreshReady(1,async()=>{});
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();await page.route('**/*',route=>route.abort());
  const html=`<textarea style="display:none"></textarea><div id="prompt-textarea" contenteditable="true" role="textbox" style="width:300px;height:50px"></div>
   <section data-testid="conversation-turn-0"><div data-message-author-role="user">Original image request</div></section>
   <section data-testid="conversation-turn-1"><div data-message-author-role="assistant"><p>${failure}</p></div><button data-testid="copy-turn-action">Copy</button></section>`;
  await page.setContent(html);
  const read=()=>page.evaluate('('+probe.toString()+')()');
  let state=await read();assert.equal(state.ready,true,'hidden legacy textarea cannot mask visible composer');assert.equal(state.draft,false);cases++;
  await page.locator('#prompt-textarea').fill('user draft');assert.equal((await read()).draft,true);cases++;
  await page.locator('#prompt-textarea').fill('');
  await page.locator('[data-testid="conversation-turn-1"]').evaluate(n=>n.setAttribute('aria-busy','true'));
  assert.equal((await read()).busy,true,'streaming on response frame must block fresh replay');cases++;
  await page.locator('[data-testid="conversation-turn-1"]').evaluate(n=>n.removeAttribute('aria-busy'));
  await page.locator('[data-message-author-role="assistant"]').evaluate(n=>n.innerHTML='<video width="300" height="300"></video>');
  assert.equal((await read()).has_media,true);cases++;
  await page.setContent(html);
  const observation=await page.evaluate(({source,failure})=>{
   window.visible=n=>{const r=n?.getBoundingClientRect();return r?.width>0&&r?.height>0;};
   window.stopButtonVisible=()=>false;window.storyImageMissingRequestEvidence=()=>null;
   window.chatGPTStoryRequest=()=>({frame:document.querySelector('[data-testid="conversation-turn-0"]')});
   window.chatGPTStoryImageSnapshot=()=>({reason:'no_image',images:[],turn:document.querySelector('[data-testid="conversation-turn-1"]')});
   window.retryableCompletedImageText=()=>false;
   (0,eval)(source);
   const first=window.storyImageWaitObservation('original',{});
   document.querySelector('[data-message-author-role="assistant"]').textContent='I cannot help with that request because of policy';
   const refused=window.storyImageWaitObservation('original',{});
   return {first:{failureText:first.failureText,stalledReason:first.stalledReason,busy:first.busy},refused:refused.failureText};
  },{source:content.slice(content.indexOf('  function chatGPTConversationFrames('),content.indexOf('  function assistantTurns('))
    +section(content,'confirmedStoryImageServiceError','  ')+'\n'+section(content,'storyImageWaitObservation','  '),failure});
  assert.deepEqual(observation.first,{failureText:failure,stalledReason:'completed_service_error',busy:false});assert.equal(observation.refused,'');cases+=2;
  // Observed ChatGPT 2026 semantic text/gallery DOM (no legacy role wrappers).
  const editor='<div id="prompt-textarea" contenteditable="true" role="textbox" style="width:300px;height:50px"></div>';
  const user='<div data-chatgpt-search-unit-key="fallback-turn-0:0:user"><div data-user-message-bubble="true">Original image request</div></div>';
  const semantic='<div data-chatgpt-search-unit-key="fallback-turn-0:2:assistant" data-chatgpt-search-message-ids="reply"><p>Upload reference image</p></div>';
  await page.setContent(editor+user+semantic);
  state=await read();assert.equal(state.ready,true);assert.equal(state.busy,false);assert.equal(state.has_media,false);cases++;
  await page.locator('[data-chatgpt-search-unit-key$=":assistant"]').evaluate(n=>n.setAttribute('data-is-streaming','true'));
  assert.equal((await read()).busy,true,'semantic streaming remains protected');cases++;
  // The live "Worked 57s" marker is an earlier block, not a direct sibling
  // of the completed assistant gallery.
  const gallery='<div><h4 data-conversation-role="assistant">ChatGPT</h4><div data-chatgpt-search-message-ids="generated-reply"><div data-testid="generated-image-gallery"><button data-testid="generated-image-preview"><img width="300" height="300" src="blob:https://chatgpt.com/test"></button></div></div></div>';
  await page.setContent(editor+user+gallery);
  state=await read();assert.equal(state.ready,true);assert.equal(state.has_media,true,'generated gallery after Worked block remains visible after refresh');cases++;
  await page.setContent(editor+user+'<div data-user-message-bubble="true">'+gallery+'</div>');
  assert.equal((await read()).has_media,false,'user-owned gallery cannot be recovered assistant media');cases++;
  await page.setContent(editor+user+'<div data-chatgpt-search-message-ids="upload"><img width="300" height="300"></div>');
  assert.equal((await read()).has_media,false,'arbitrary attachment is not an assistant result');cases++;
  await page.setContent(editor);assert.equal((await read()).ready,false,'empty shell is not a recovered chat');cases++;
 }finally{await browser.close();}
 // Production monitor: terminal proof survives transport and is rechecked at
 // the last possible moment. A briefly flashed error never authorizes replay.
 const f=fixture();
 for(const ms of [100,1000,2000,6000]){f.set(ms,{signature:'native-error',stalledReason:'completed_service_error',failureText:failure,state:{reason:'no_image',images:[]}});await f.tick();}
 assert.equal(f.messages.length,0);cases++;
 f.set(7200);await f.tick();assert.equal(f.messages.length,1);assert.equal(f.messages[0].failure_text,failure);cases++;
 const late=fixture();late.c.chrome.runtime.sendMessage=async message=>{
  assert.equal(late.c.storyImageRefreshGuard(message),true);
  assert.equal(late.c.storyImageRefreshGuard({...message,failure_text:'changed'}),false);
  late.set(9000,{failureText:'changed'});assert.equal(late.c.storyImageRefreshGuard(message),false);
  return {ok:false};
 };
 for(const ms of [100,4000,8200]){late.set(ms,{signature:'native-error',stalledReason:'completed_service_error',failureText:failure,state:{reason:'no_image',images:[]}});await late.tick();}cases++;
 console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
