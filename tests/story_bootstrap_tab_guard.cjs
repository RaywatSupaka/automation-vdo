// Actual background routing with a fake Chrome API; never touches live tabs.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const part=(start,end)=>{
  const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
  assert(a>=0 && b>a,start);
  return source.slice(a,b);
};
const helpers=part('function inspectEmptyCoverPreparation()','async function restartCoverPreparation(');
const start=part('async function startAIWebJob(','async function cancelChatGPTJob(');
const root='https://chatgpt.com/';
let passed=0;

async function scenario(name,initial,options,verify) {
  const tabs=initial.map(row=>({...row,url:row.url||root,status:row.status||'complete'}));
  const actions=[],storage={};
  let nextId=100;
  const context=vm.createContext({
    setTimeout:callback=>{callback();return 0;},
    AI_WEB:{chatgpt:{url:root,matches:['https://chatgpt.com/*'],name:'ChatGPT Web'},
      gemini:{url:'https://gemini.google.com/app',matches:['https://gemini.google.com/app*'],name:'Gemini Web'}},
    BRIDGE:'http://fixture',normalizeAIProvider:value=>value||'chatgpt',
    bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,package:{job:{id:'STORY-BOOTSTRAP',image_ai_provider:options.provider||'chatgpt'},
      ...(options.resume?{ai_resume:options.resume}:{})}})}),
    focusOpenedBrowserTab:async tab=>actions.push(['focus',tab.id]),
    rememberAutomationTabs:async id=>actions.push(['remember',id]),
    rememberedAutomationTabIds:async()=>options.rememberedIds||[],
    openAIWebTab:async provider=>{
      const tab={id:++nextId,url:provider==='chatgpt'?root:'https://gemini.google.com/app',status:'complete',
        empty:options.freshEmpty!==false,readyAfter:options.freshReadyAfter||0,
        reason:options.freshReason||'draft_present',documentId:`doc-${nextId}`};
      tabs.push(tab);actions.push(['create',tab.id]);return tab.id;
    },
    waitForTabComplete:async()=>{},isWebLoginUrl:()=>false,isGoogleVerificationUrl:()=>false,
    chrome:{storage:{local:{get:async key=>key===null?{...storage}:typeof key==='string'?{[key]:storage[key]}:{},
      set:async value=>Object.assign(storage,value),remove:async()=>{}}},
      tabs:{query:async()=>tabs.slice(),get:async id=>tabs.find(tab=>tab.id===id),
        create:async({url})=>{const tab={id:++nextId,url,status:'complete'};tabs.push(tab);actions.push(['create',tab.id]);return tab;},
        update:async(id)=>{actions.push(['activate',id]);return tabs.find(tab=>tab.id===id);},
        sendMessage:async(id,message)=>{actions.push(['start',id,message.type]);return {ok:true};}},
      scripting:{executeScript:async details=>{
        if(details.files){actions.push(['inject',details.target.tabId]);return [];}
        if(details.args){actions.push(['notice',details.target.tabId,details.args[0]]);return [];}
        const tab=tabs.find(row=>row.id===details.target.tabId);
        if(details.func?.name==='clearOwnedChatGPTBootstrapDraft'){
          actions.push(['clear',tab.id]);
          if(options.clearFails)return [{documentId:tab.documentId,result:{cleared:false,reason:'draft_still_present'}}];
          tab.empty=true;tab.clearCount=(tab.clearCount||0)+1;
          return [{documentId:tab.documentId,result:{cleared:true,reason:'cleared'}}];
        }
        actions.push(['probe',tab.id]);
        if(tab.probeError)throw Error('document unavailable');
        tab.probes=(tab.probes||0)+1;
        if(options.restoreAfterFirstClear && tab.clearCount===1 && !tab.restoredOnce){
          tab.empty=false;tab.restoredOnce=true;
        }
        const empty=tab.id===1 && tab.probes>1 && options.changeAfterFirst ? false
          : tab.readyAfter ? tab.probes>=tab.readyAfter : tab.empty===true;
        const documentId=tab.id===1 && tab.probes>1 && options.replaceDocument ? `replacement-${tab.id}` : tab.documentId||`doc-${tab.id}`;
        const reason=empty?'ready':tab.readyAfter?'composer_not_ready':tab.reason||'draft_present';
        return [{frameId:0,documentId,result:{empty,reason}}];
      }}}
  });
  vm.runInContext(helpers+start,context);
  let outcome;
  try {outcome=await context.startAIWebJob('STORY-BOOTSTRAP',!!options.reuse,options.provider||'chatgpt');}
  catch(error){outcome=error;}
  await verify({tabs,actions,storage,outcome});
  passed++;
  process.stdout.write(`PASS ${name}\n`);
}

(async()=>{
  const savedConversation='https://chatgpt.com/c/6abea014-ed90-83ec-bc08-38f5d5ff8055';
  const resume={required:true,stage:'image',provider:'chatgpt',index:3,conversation_url:savedConversation};
  await scenario('resume adopts one already open exact conversation',[
    {id:1,url:root},{id:2,url:savedConversation}],{reuse:true,resume},({actions,outcome})=>{
    assert.equal(outcome.tabId,2);
    assert.equal(actions.filter(a=>a[0]==='create').length,0);
    assert.equal(actions.filter(a=>a[0]==='start').length,1);
  });
  await scenario('resume opens saved conversation only when absent',[
    {id:1,url:root}],{reuse:true,resume},({actions,outcome,tabs})=>{
    assert.equal(outcome.tabId,101);
    assert.equal(tabs[1].url,savedConversation);
    assert.equal(actions.filter(a=>a[0]==='create').length,1);
  });
  await scenario('ambiguous duplicate saved conversations stop before Start',[
    {id:1,url:savedConversation},{id:2,url:savedConversation}],{reuse:true,resume},({actions,outcome})=>{
    assert.match(String(outcome.message),/AI_WEB_RESUME_REVIEW/);
    assert.equal(actions.filter(a=>a[0]==='create').length,0);
    assert.equal(actions.filter(a=>a[0]==='start').length,0);
  });
  await scenario('draft tab preserved and empty tab reused',[
    {id:1,empty:false},{id:2,empty:true}],{},({actions,outcome})=>{
    assert.equal(outcome.tabId,2);
    assert.equal(actions.filter(a=>a[0]==='create').length,0);
    assert.equal(actions.filter(a=>a[0]==='start').length,1);
  });
  await scenario('all existing root tabs busy opens one new tab',[
    {id:1,empty:false},{id:2,empty:false}],{},({actions,outcome,tabs})=>{
    assert.equal(outcome.tabId,101);
    assert.equal(actions.filter(a=>a[0]==='create').length,1);
    assert.equal(actions.filter(a=>a[0]==='start').length,1);
    assert.equal(tabs[0].empty,false);
  });
  await scenario('new tab clears a restored draft automatically before Start',[
    {id:1,empty:false}],{freshEmpty:false},({actions,outcome})=>{
    assert.equal(outcome.tabId,101);
    assert.equal(actions.filter(a=>a[0]==='create').length,1);
    assert.equal(actions.filter(a=>a[0]==='clear').length,1);
    assert.equal(actions.filter(a=>a[0]==='start').length,1);
    assert.equal(actions.filter(a=>a[0]==='notice').length,0);
  });
  await scenario('failed clear still stops before Start',[
    {id:1,empty:false}],{freshEmpty:false,clearFails:true},({actions,outcome})=>{
    assert.match(String(outcome.message),/AI_WEB_WAIT_REVIEW/);
    assert.equal(actions.filter(a=>a[0]==='clear').length,1);
    assert.equal(actions.filter(a=>a[0]==='start').length,0);
  });
  await scenario('draft restored after first clear is cleared once more',[
    {id:1,empty:false}],{freshEmpty:false,restoreAfterFirstClear:true},({actions,outcome})=>{
    assert.equal(outcome.tabId,101);
    assert.equal(actions.filter(a=>a[0]==='clear').length,2);
    assert.equal(actions.filter(a=>a[0]==='start').length,1);
  });
  await scenario('attachment in new tab is never cleared or submitted',[
    {id:1,empty:false}],{freshEmpty:false,freshReason:'attachment_present'},({actions,outcome})=>{
    assert.match(String(outcome.message),/AI_WEB_WAIT_REVIEW/);
    assert.equal(actions.filter(a=>a[0]==='clear').length,0);
    assert.equal(actions.filter(a=>a[0]==='start').length,0);
  });
  await scenario('previously owned tab is never adopted even when momentarily empty',[
    {id:1,empty:true}],{rememberedIds:[1]},({actions,outcome})=>{
    assert.equal(outcome.tabId,101);
    assert.equal(actions.filter(a=>a[0]==='create').length,1);
  });
  await scenario('new ChatGPT tab waits for a delayed composer without opening again',[
    {id:1,empty:false}],{freshReadyAfter:2},({actions,outcome})=>{
    assert.equal(outcome.tabId,101);
    assert.equal(actions.filter(a=>a[0]==='create').length,1);
    assert.equal(actions.filter(a=>a[0]==='start').length,1);
  });
  await scenario('adopted tab changes, so a new owned tab starts instead',[
    {id:1,empty:true}],{changeAfterFirst:true},({actions,outcome})=>{
    assert.equal(outcome.tabId,101);
    assert.equal(actions.filter(a=>a[0]==='create').length,1);
    assert.equal(actions.filter(a=>a[0]==='start').length,1);
    assert.equal(actions.filter(a=>a[0]==='clear').length,0);
  });
  await scenario('adopted document replacement uses a new owned tab',[
    {id:1,empty:true}],{replaceDocument:true},({actions,outcome})=>{
    assert.equal(outcome.tabId,101);
    assert.equal(actions.filter(a=>a[0]==='create').length,1);
    assert.equal(actions.filter(a=>a[0]==='start').length,1);
  });
  await scenario('uninspectable tab is skipped',[
    {id:1,empty:true,probeError:true}],{},({actions,outcome})=>{
    assert.equal(outcome.tabId,101);
    assert.equal(actions.filter(a=>a[0]==='start').length,1);
  });
  await scenario('existing Gemini root remains reusable',[
    {id:1,url:'https://gemini.google.com/app',empty:false}],{provider:'gemini'},({actions,outcome})=>{
    assert.equal(outcome.tabId,1);
    assert.equal(actions.filter(a=>a[0]==='create').length,0);
  });
  await scenario('loading Gemini root still waits for existing tab',[
    {id:1,url:'https://gemini.google.com/app',status:'loading'}],{provider:'gemini'},({actions,outcome})=>{
    assert.equal(outcome.tabId,1);
    assert.equal(actions.filter(a=>a[0]==='create').length,0);
  });
  {
    const operations=[];
    const form={querySelector:()=>null};
    const editor={isConnected:true,isContentEditable:true,innerText:'old restored draft',
      getClientRects:()=>[{}],closest:()=>form,focus:()=>operations.push('focus')};
    const document={
      querySelectorAll:selector=>selector.startsWith('#prompt-textarea')?[editor]:[],
      querySelector:()=>null,
      createRange:()=>({selectNodeContents:()=>operations.push('range')}),
      execCommand:command=>{operations.push(command);editor.innerText='';return true;}
    };
    const selection={removeAllRanges:()=>{},addRange:()=>{}};
    const context=vm.createContext({document,location:{hostname:'chatgpt.com',pathname:'/'},
      getSelection:()=>selection,String});
    vm.runInContext(helpers,context);
    assert.equal(context.clearOwnedChatGPTBootstrapDraft().cleared,true);
    assert.deepEqual(operations,['focus','range','delete']);
    editor.innerText='new draft';
    form.querySelector=()=>({});
    assert.equal(context.clearOwnedChatGPTBootstrapDraft().reason,'attachment_present');
    assert.equal(editor.innerText,'new draft');
    passed++;
    process.stdout.write('PASS real draft clearer removes only plain composer text and guards attachments\n');
  }
  {
    const events=[];
    const context=vm.createContext({Set,String,
      reportWebActionProgress:async row=>events.push(['progress',row]),
      reportExtensionTrace:async row=>events.push(['trace',row])});
    vm.runInContext(part('async function reportAICommandFailure(','async function reportFlowCommandFailure('),context);
    const failure=Object.assign(Error('review'),{code:'AI_WEB_WAIT_REVIEW',tabId:101,bootstrapReason:'draft_present'});
    await context.reportAICommandFailure({action:'open_story_chatgpt',job_id:'STORY-BOOTSTRAP',run_id:'RUN-ONE'},failure);
    assert.equal(events[0][0],'progress');
    assert.equal(events[1][0],'trace');
    assert.equal(events[1][1].tabId,101);
    assert.equal(events[1][1].detail.reason,'draft_present');
    passed++;
    process.stdout.write('PASS review reports safe reason and tab ID without draft text\n');
  }
  process.stdout.write(`${passed} story bootstrap cases passed\n`);
})().catch(error=>{console.error(error);process.exitCode=1;});
