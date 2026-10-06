// Real Background dispatch + real content owner/reader. Chrome/clock/DOM only
// are fixtures. No live bridge, generation or user-owned tab is modified.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {setup,REQUEST,OWNER_ID}=require('./gemini_text_request_332_harness');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const begin=source.indexOf('async function startAIWebJob('),end=source.indexOf('async function cancelChatGPTJob(',begin);
async function routing(provider,kind='closed',stage='motion'){
  const url=provider==='gemini'?'https://gemini.google.com/app/aaaaaaaaaaaa0332':'https://chatgpt.com/c/fixture-345';
  const root=provider==='gemini'?'https://gemini.google.com/app':'https://chatgpt.com/';
  const job={id:'STORY-345',image_ai_provider:provider};
  const pkg={job,ai_resume:{required:true,provider,conversation_url:kind==='missing'?'':url,stage,request:REQUEST}};
  const opened=[],messages=[],removed=[],storage={};let current={id:9,url:kind==='root'?root:url};
  const c=vm.createContext({console,setTimeout,BRIDGE:'http://fixture.invalid',
    AI_WEB:{[provider]:{url:root,matches:[root.replace(/\/$/,'')+'*'],name:provider}},
    normalizeAIProvider:x=>x,bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,package:pkg})}),
    openAIWebTab:()=>{throw Error('Provider ROOT fallback is forbidden for pending requests');},
    rememberAutomationTabs:async()=>{},focusOpenedBrowserTab:async()=>{},waitForTabComplete:async()=>{},
    isWebLoginUrl:()=>false,isGoogleVerificationUrl:()=>false,
    chrome:{storage:{local:{get:async()=>({[`smartpostAIWebTab:${provider}:${job.id}`]:9}),set:async x=>Object.assign(storage,x),remove:async()=>{}}},
      tabs:{query:async()=>[],get:async id=>{if(kind==='closed'&&id===9)throw Error('closed');return current;},
        create:async options=>{opened.push(options.url);return current={id:10,url:kind==='redirect'?root:options.url};},
        update:async()=>current,remove:async id=>removed.push(id),
        sendMessage:async(id,message)=>{messages.push({id,message,url:current.url});return {ok:true};}},
      scripting:{executeScript:async()=>[]}}});
  c.revealChatGPTAnswer=async()=>false; // Separate DOM fixture covers reveal.
  vm.runInContext(source.slice(begin,end),c);
  if(['missing','fresh','redirect'].includes(kind)){
    // Redirect must first need a new tab, then end at a wrong root.
    if(kind==='redirect')c.chrome.tabs.get=async id=>{if(id===9)throw Error('closed');return current;};
    await assert.rejects(c.startAIWebJob(job.id,true,provider,kind==='fresh','RUN-345'),/AI_WEB_RESUME_REVIEW/);
    assert.equal(messages.length,0);assert.equal(removed.length,0);return;
  }
  await c.startAIWebJob(job.id,true,provider,false,'RUN-345');
  assert.equal(opened.length,kind==='existing'?0:1);
  assert.equal(messages.length,1);assert.equal(messages[0].url,url);
  assert.equal(messages[0].message.package.ai_resume.conversation_url,url);
  assert.equal(messages[0].message.package.reuse_analysis,true);
  assert.equal(removed.length,0);
  return messages[0].message.package;
}
async function tests(){let cases=0;
  for(const provider of ['gemini','chatgpt'])for(const kind of ['closed','root','existing','missing','fresh','redirect']){await routing(provider,kind);cases++;}
  let f=setup({historyCount:0}),c=f.frontend;
  c.location.href='https://gemini.google.com/app';
  f.accept(REQUEST,'{"job_id":"STORY-345","scene_prompts":["one"]}');
  let owner=c.geminiTextRequestSnapshot(REQUEST).owner;
  c.location.href='https://gemini.google.com/app/aaaaaaaaaaaa0332';
  let snapshot=c.geminiTextRequestSnapshot(REQUEST,owner);
  assert.equal(snapshot.reason,'first_conversation_bound');owner=snapshot.owner;cases++;
  f.remove(OWNER_ID);f.mount('eeeeeeeeeeee0345',REQUEST,'{"job_id":"STORY-345","scene_prompts":["one"]}',12);
  snapshot=c.geminiTextRequestSnapshot(REQUEST,owner);
  assert.equal(snapshot.reason,'request_remounted');assert.equal(snapshot.owner.request_container_id,'eeeeeeeeeeee0345');cases++;
  f.setDraft('User edited draft');assert.equal(c.geminiTextRequestSnapshot(REQUEST,owner).owner,null);f.setDraft('');cases++;
  c.location.href='https://gemini.google.com/app/bbbbbbbbbbbb0345';assert.equal(c.geminiTextRequestSnapshot(REQUEST,owner).reason,'conversation_changed');cases++;
  c.location.href=owner.conversation_url;f.mount('dddddddddddd0345',REQUEST,'second',13);
  assert.equal(c.geminiTextRequestSnapshot(REQUEST,owner).owner,null);cases++;
  // Compose the real Background routing output with the real passive reader.
  // Closed old tab -> exact new conversation -> original owned answer -> result.
  const pkg=await routing('gemini','closed','analysis');
  f=setup({historyCount:0});c=f.frontend;c.activeJobId=pkg.job.id;
  f.accept(REQUEST,JSON.stringify({job_id:pkg.job.id,scene_prompts:['one']}));
  c.extractJson=node=>JSON.parse(node.innerText);
  c.validateAnalysis=result=>{assert.equal(result.job_id,pkg.job.id);assert.equal(result.scene_prompts.length,1);return result;};
  const result=await c.readPendingAnalysis(pkg,'scene_prompts',1);
  assert.equal(result.job_id,pkg.job.id);assert.equal(f.presses(),0);assert.equal(f.attachments(),0);cases++;
  pkg.ai_resume.request='Unknown old prompt';
  await assert.rejects(c.readPendingAnalysis(pkg,'scene_prompts',1),/AI_WEB_RESUME_REVIEW/);
  assert.equal(f.presses(),0);cases++;
  console.log(JSON.stringify({ok:true,cases}));
}
module.exports={routing};
if(require.main===module)tests().catch(error=>{console.error(error);process.exitCode=1;});
