// Actual Background recovery function with offline tab and Bridge doubles.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const start=source.indexOf('async function storyBootstrapDraftFingerprint(');
const end=source.indexOf('async function showStoryBootstrapReview(',start);
assert(start>=0&&end>start);
const code=source.slice(start,end);

async function fixture({changed=false,missing=false,attachment=false}={}){
  const tabs=[{id:11,url:'https://chatgpt.com/'},{id:12,url:'https://chatgpt.com/'},
    {id:13,url:'https://chatgpt.com/'},{id:14,url:'https://chatgpt.com/c/owned'}];
  const state=new Map([[11,'draft_present'],[12,attachment?'attachment_present':'draft_present'],
    [13,'draft_present'],[14,'conversation_present']]);
  const clears=[],traces=[];let reads=0;
  const c=vm.createContext({URL,Promise,Number,String,Error,setTimeout:resolve=>resolve(),
    chrome:{tabs:{query:async()=>tabs},scripting:{executeScript:async({target})=>{
      const tabId=target.tabId;
      return [{documentId:`document-${tabId}`,result:state.get(tabId)==='draft_present'
        ?{length:tabId===13?5:10,digest:tabId===13?'other':'same'}:null}];
    }}},
    inspectChatGPTRootDocument:async tabId=>({documentId:`document-${tabId}`,
      reason:missing&&tabId===11?'ready':state.get(tabId),empty:state.get(tabId)==='ready'}),
    clearOwnedChatGPTRootDraft:async(tabId,doc)=>{
      clears.push(tabId);assert.equal(doc,`document-${tabId}`);state.set(tabId,'ready');
      return {cleared:true};
    },
    waitForCleanChatGPTRoot:async(tabId,doc)=>({empty:state.get(tabId)==='ready',documentId:doc}),
    reportExtensionTrace:async row=>traces.push(row)
  });
  vm.runInContext(code,c);
  if(changed){
    const original=c.storyBootstrapDraftFingerprint;
    c.storyBootstrapDraftFingerprint=async(...args)=>{
      const result=await original(...args);
      if(args[0]===12&&++reads===2)return {length:10,digest:'changed'};
      return result;
    };
  }
  const command={job_id:'STORY-20261007-A22FCE',run_id:'RUN-33252111A265',target_tab_id:11};
  return {run:()=>c.clearAuthorizedStoryBootstrapDraft(command),clears,traces};
}

(async()=>{
  const normal=await fixture();const result=await normal.run();
  assert.equal(result.cleared,true);assert.equal(result.tab_count,2);
  assert.deepEqual(normal.clears,[11,12]);
  assert.equal(normal.traces[0].detail.verified,true);
  assert.equal(normal.traces[0].detail.tab_count,2);
  const missing=await fixture({missing:true});
  await assert.rejects(missing.run(),/แท็บต้นทาง/);assert.deepEqual(missing.clears,[]);
  const attachment=await fixture({attachment:true});
  assert.equal((await attachment.run()).tab_count,1);assert.deepEqual(attachment.clears,[11]);
  const changed=await fixture({changed:true});
  await assert.rejects(changed.run(),/ร่างหรือเอกสารเปลี่ยน/);
  assert.deepEqual(changed.clears,[11]);
  console.log(JSON.stringify({ok:true,cases:4}));
})().catch(error=>{console.error(error);process.exitCode=1;});
