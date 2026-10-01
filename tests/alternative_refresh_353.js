const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),{chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
async function dom(){
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  const fn=source.slice(source.indexOf('  function alternativeEmptyImageProof('),source.indexOf('  function extractAlternativeJson('));
  const adapter=source.slice(source.indexOf('  function chatGPTConversationFrames('),source.indexOf('  function assistantTurns('));
  async function check({busy=false,cancel=false,draft='',image=false,text='',toolbar=true,request='current',loading=false}={}){
   await page.setContent(`<main><section data-testid="conversation-turn-1"><div data-message-author-role="user">current</div></section><section data-testid="conversation-turn-2" data-turn-id="result-1"><div class="agent-turn"><div class="flex grow"><div>${text}${image?'<img>':''}${loading?'<div role="progressbar">Loading</div>':''}</div></div>${toolbar?'<button data-testid="good-image-turn-action-button">Like image</button>':''}</div></section></main>`);
   return page.evaluate(({fn,adapter,busy,cancel,draft,request})=>{
    const IS_GEMINI=false,cancelRequested=cancel,stopButtonVisible=()=>busy,composerText=()=>draft;
    const userTurns=()=>[...document.querySelectorAll('[data-message-author-role="user"]')];
    const motionRequestIsLatestUser=r=>userTurns().at(-1).textContent===r,visible=e=>!!e.getBoundingClientRect().height;
    return !!eval('(function(){'+adapter+';return '+fn+';})()')(request);
   },{fn,adapter,busy,cancel,draft,request});
  }
  assert.equal(await check(),true);
  for(const args of [{busy:true},{cancel:true},{draft:'typing'},{image:true},{text:'refusal'},
      {toolbar:false},{request:'other'},{loading:true}])assert.equal(await check(args),false,JSON.stringify(args));
 }finally{await browser.close();}
}
async function background(){
 const bg=fs.readFileSync('browser_extension/background.js','utf8');
 const code=bg.slice(bg.indexOf('const alternativeRefreshLocks='),bg.indexOf('chrome.runtime.onMessage.addListener('));
 async function check({used=false,live=false,wrong=false,claimRace=false}={}){
  let row={alternative:true,provider:'chatgpt',phase:'rewrite_sent',alternative_stage:'image_sent',request_id:'r',
   helper_tab:2,owner_tab:1,job_id:'j',index:3,run_id:'run',request:'current',
   empty_image_observation:{signature:'s',conversation_url:'https://chatgpt.com/c/abc',samples:3},
   ...(used?{empty_image_refresh:{}}:{})};
  const events=[];
  const context=vm.createContext({Set,String,Error,Date,crypto:{randomUUID:()=> 'challenge'},
   assertFlowRepairOwner:async()=>{if(wrong)throw Error('wrong owner');},waitForTabComplete:async()=>{},
   chrome:{storage:{local:{get:async()=>({key:row}),set:async data=>{events.push('claim');row=data.key;}}},
    tabs:{get:async id=>({id,url:'https://chatgpt.com/c/abc'}),reload:async()=>events.push('reload'),
     sendMessage:async(id,m,options)=>{
      if(m.type==='VERIFY_FLOW_ALTERNATIVE_EMPTY')return {ok:!live && !(claimRace && events.includes('claim')),challenge:m.challenge};
      assert(options.documentId);assert.equal(m.request_id,'r');assert.equal(m.run_id,'run');events.push('resume');
      return {ok:true,started:true,key:m.key,request_id:m.request_id,run_id:m.run_id};}},
    scripting:{executeScript:async()=>events.push('inject')}}});
  require('./shared_refresh_fixture_439.cjs').install(context);
  vm.runInContext(code,context);
  const message={key:'key',request_id:'r',signature:'s',conversation_url:'https://chatgpt.com/c/abc'};
  const run=()=>context.refreshAlternativeEmpty(message,{tab:{id:2}},()=>events.push('ack'));
  if(live||wrong||claimRace)await assert.rejects(run);else{await run();await run();}
  assert.equal(events.filter(x=>x==='reload').length,used||live||wrong||claimRace?0:1);
  if(events.includes('reload')){assert(events.indexOf('claim')<events.indexOf('reload'));assert(events.includes('resume'));}
 }
 for(const arg of [{},{used:true},{live:true},{wrong:true},{claimRace:true}])await check(arg);
}
(async()=>{await dom();await background();
 const start=source.indexOf('    if (alternateWait) return await alternateWait();');
 assert(start>source.indexOf('async function submitImagePrompt('));
 assert(start<source.indexOf('    while (storyWait ||'));
 console.log('9 DOM + 5 reload/ownership/race cases passed; alternate collector bypasses legacy Stop/timeout');
})().catch(e=>{console.error(e);process.exitCode=1});
