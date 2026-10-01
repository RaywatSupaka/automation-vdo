const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const {chromium}=require('playwright');
const sandbox={URL,Date,TextEncoder,crypto:require('crypto').webcrypto};
vm.runInNewContext(fs.readFileSync('browser_extension/single_answer.js','utf8'),sandbox);
vm.runInNewContext(fs.readFileSync('browser_extension/src/platforms/meta-ai/video.js','utf8').replaceAll('export ','')+
  '\nthis.inspect=inspectMetaDOM;this.Adapter=MetaVideoAdapter;this.select=typeof metaComparisonOffer===\"function\"?metaComparisonOffer:null;',sandbox);
const offer='Option 1: A calm close shot. Option 2: A gentle camera move for the video. Would you like me to generate it?';
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
 try{
  const page=await browser.newPage();
  const prompt='Create one video of the dog waiting at the crossing.';
  const card=value=>`<div role="article" aria-label="Meta AI response"><p>${value}</p><button>Copy response</button><button>Like response</button><button>I prefer this response</button></div>`;
  const setup=async(left=offer,right=offer.replace('gentle camera','slow tracking'))=>{
   await page.setContent(`<div role="article" aria-label="your message"><p>${prompt}</p><img alt="scene.png"></div>${card(left)}${card(right)}`);
   await page.evaluate(()=>Object.defineProperties(document.querySelector('img'),{complete:{value:true},naturalWidth:{value:720}}));
  };
  const scan=choice=>page.evaluate(({fn,prompt,choice})=>new Function('return ('+fn+')')()(prompt,'scene.png',choice),{fn:sandbox.inspect.toString(),prompt,choice});
  await setup();let state=await scan();
  assert.equal(state.answerComplete,true,'two completed offers must not remain an unfinished answer');
  const selected=sandbox.select(state.answerBranches);
  assert.equal(selected.proposal_branch,0);assert.equal(selected.proposal_text,offer);
  assert(!selected.prompt.includes('slow tracking'),'never mix text from the other response');
  state=await scan(selected);assert.equal(state.proposalMatches,true);
  await page.evaluate(()=>document.querySelectorAll('[aria-label="Meta AI response"] p')[1].textContent='changed sibling');
  assert.equal((await scan(selected)).proposalMatches,false,'all persisted branch evidence must remain exact');
  await setup();await page.evaluate(()=>document.body.insertAdjacentHTML('beforeend','<button aria-label="Stop generating">Stop</button>'));
  assert.equal((await scan()).stop,true);
  await setup('Dog video (file unavailable)','Another failed result');
  await page.evaluate(()=>document.querySelectorAll('[aria-label="Meta AI response"]').forEach((root,index)=>{
   const video=document.createElement('video');video.src='https://example.invalid/'+index+'.mp4';root.append(video);
   Object.defineProperties(video,{readyState:{value:index?4:0},videoWidth:{value:index?720:0},duration:{value:index?8:NaN}});
  }));
  state=await scan();assert.equal(state.videoReady,true,'one failed alternative must not block the playable result');
  assert(state.videoSrc.endsWith('/1.mp4'));assert.equal(state.videoCandidates.length,2);
  await page.evaluate(()=>document.querySelectorAll('[aria-label="Meta AI response"]')[0].insertAdjacentHTML('beforeend','<div role="progressbar">Generating</div>'));
  assert.equal((await scan()).videoReady,false,'active sibling keeps the same request waiting');
  await page.evaluate(()=>document.querySelector('[aria-label="your message"] p').textContent='foreign');
  assert.equal((await scan()).videoReady,false);
  // Actual lexical DOM draft upgrade appends once without replacing its image.
  await page.route('https://www.meta.ai/**',route=>route.fulfill({contentType:'text/html',body:'<div role="textbox" contenteditable="true" data-lexical-editor="true" style="width:600px;height:200px"></div>'}));
  await page.goto('https://www.meta.ai/');
  await page.evaluate(prompt=>{
   const editor=document.querySelector('[role="textbox"]');editor.append(document.createTextNode(prompt));
   const img=document.createElement('img');img.alt='scene.png';img.src='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';editor.append(img);
   Object.defineProperties(img,{complete:{value:true},naturalWidth:{value:720},naturalHeight:{value:1280}});window.reference=img;
  },prompt);
  const row={job_id:'fixture',index:1,request_id:'draft',context_id:'context',stage:'ready_to_send',prompt,image_name:'scene.png',tabId:1};
  let owner=true,changedBeforeEdit=false,edits=0;
  const adapter=new sandbox.Adapter({api:async()=>({package:{...row}}),chromeAPI:{scripting:{executeScript:async({func,args,target})=>{
   if(target.documentIds){edits++;if(changedBeforeEdit)await page.evaluate(()=>document.querySelector('[role="textbox"]').prepend(document.createTextNode('manual ')));}
   return[{documentId:'doc',result:await page.evaluate(({fn,args})=>new Function('return ('+fn+')')()(...args),{fn:func.toString(),args})}];
  }}}});adapter.owns=async()=>owner;adapter.save=async()=>{};
  let draft=await adapter.inspect(row);
  assert.equal(await adapter.prepareWireDraft(row,draft),false);
  assert.equal(await page.evaluate(()=>document.querySelector('img')===window.reference),true);
  draft=await adapter.inspect(row);assert(sandbox.SmartFlowSingleAnswer.has(draft.composerWireText));
  assert.equal(await adapter.prepareWireDraft(row,draft),true);assert.equal(edits,1);
  const resetDraft=async()=>page.evaluate(prompt=>{const e=document.querySelector('[role="textbox"]'),img=e.querySelector('img');e.replaceChildren(document.createTextNode(prompt),img);},prompt);
  await resetDraft();owner=false;assert.equal(await adapter.prepareWireDraft(row,await adapter.inspect(row)),false);assert.equal(edits,1);
  owner=true;row.stage='send_intent';assert.equal(await adapter.prepareWireDraft(row,await adapter.inspect(row)),false);assert.equal(edits,1);
  row.stage='ready_to_send';changedBeforeEdit=true;await adapter.prepareWireDraft(row,await adapter.inspect(row));
  assert((await adapter.inspect(row)).composerText.startsWith('manual '));assert.equal(edits,2);
  assert.equal(await adapter.prepareWireDraft(row,await adapter.inspect(row)),false);assert.equal(edits,2);
  const missing={};
  vm.runInNewContext(fs.readFileSync('browser_extension/src/platforms/meta-ai/video.js','utf8').replaceAll('export ','')+'\nthis.Adapter=MetaVideoAdapter;',missing);
  await assert.rejects(()=>new missing.Adapter({api:async()=>{throw Error('must not reach bridge');}}).prepareWireDraft(row,draft),/AI_RESPONSE_FORMAT_NOT_READY/);
  assert.equal(edits,2);
  console.log('Meta multiple result DOM guards passed');
 }finally{await browser.close();}
 // Real controller persists its first selected playable asset across ACK loss
 // and does not switch when the DOM later orders another ready alternative first.
 const url='https://www.meta.ai/prompt/owned',chosen='https://media.invalid/chosen.mp4';
 let receipt={job_id:'fixture',index:1,request_id:'video',context_id:'context',stage:'generating',prompt:'owned',image_name:'scene.png',conversation_url:url};
 let dom={matchedUser:true,conversation:url,stop:false,busy:false,answerBusy:false,pageBusy:false,videoReady:true,videoCount:2,
  videoSrc:chosen,videoCandidates:[{src:'https://media.invalid/failed.mp4',ready:false},{src:chosen,ready:true}]};
 let lose=true,changedOnIntent=false;const downloads=[],events=[];
 const clone=value=>JSON.parse(JSON.stringify(value));
 const api=async(route,body)=>{
  if(!body)return{package:clone(receipt)};events.push(body.stage);
  if(body.stage==='video_select'){
   receipt.video_selection={asset_sha256:body.video_evidence.asset_sha256};
   if(lose){lose=false;throw Error('lost selection ACK');}
  }else{receipt.stage=body.stage;if(changedOnIntent&&body.stage==='download_intent')dom.stop=true;}
  return{receipt:clone(receipt)};
 };
 const make=()=>{
  const adapter=new sandbox.Adapter({api,chromeAPI:{tabs:{get:async()=>({url,status:'complete'})},downloads:{download:async data=>{downloads.push(data.url);return 9;}}}});
  adapter.owns=async()=>true;adapter.save=async()=>{};adapter.inspect=async()=>clone(dom);return adapter;
 };
 const row={...receipt,tabId:1};await assert.rejects(()=>make().step(row),/lost selection ACK/);
 dom.videoSrc='https://media.invalid/other.mp4';dom.videoCandidates.unshift({src:dom.videoSrc,ready:true});
 await make().step(row);assert.deepEqual(downloads,[chosen]);assert.equal(events.filter(x=>x==='video_select').length,1);
 receipt={...receipt,stage:'generating',request_id:'changed'};row.request_id='changed';row.stage='generating';changedOnIntent=true;
 await make().step(row);assert.equal(receipt.stage,'needs_attention');assert.deepEqual(downloads,[chosen]);
 console.log('Meta selected-video receipt/controller guards passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
