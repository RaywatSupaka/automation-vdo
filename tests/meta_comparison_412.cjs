const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/src/platforms/meta-ai/video.js','utf8');
const sandbox={URL,Date};
vm.runInNewContext(source.replaceAll('export ','')+'\nthis.inspect=inspectMetaDOM;this.failure=metaReplyFailure;this.Adapter=MetaVideoAdapter;',sandbox);
(async()=>{
 const browser=await chromium.launch({headless:true,
  ...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
 try {
  const page=await browser.newPage();
  const prompt='Create one video of the dog waiting at the crossing.';
  const card=n=>`<div role="article" aria-label="Meta AI response"><h3>คำตอบที่ ${n}</h3><p>Dog waiting (file unavailable)</p><p>This video was created using a legacy model.</p><button>ฉันชอบการตอบกลับนี้มากกว่า</button></div>`;
  await page.setContent(`<div role="article" aria-label="your message"><p>${prompt}</p><img alt="scene.png"></div><h2>คุณชอบการตอบกลับแบบใด</h2>${card(1)}${card(2)}`);
  await page.evaluate(()=>Object.defineProperties(document.querySelector('img'),{complete:{value:true},naturalWidth:{value:720}}));
  const scan=()=>page.evaluate(({fn,prompt})=>new Function('return ('+fn+')')()(prompt,'scene.png'),{fn:sandbox.inspect.toString(),prompt});
  let state=await scan();
  assert.equal(state.matchedUser,true);
  assert.equal(state.answerComplete,true,'two completed response cards must not wait forever');
  assert.equal(state.comparison,true);
  assert.equal(sandbox.failure(state.answerText),'completed_no_video');
  assert.equal(state.videoCount,0);
  await page.evaluate(()=>document.querySelector('[aria-label="Meta AI response"]').insertAdjacentHTML('beforeend','<video></video>'));
  state=await scan();assert.equal(state.videoCount,1);assert.equal(state.videoReady,false);
  await page.evaluate(()=>document.querySelector('video').remove());
  await page.evaluate(()=>document.querySelector('[aria-label="Meta AI response"]').insertAdjacentHTML('beforeend','<div role="progressbar">Generating</div>'));
  assert.equal((await scan()).answerBusy,true);
  await page.evaluate(()=>document.querySelector('[role="progressbar"]').remove());
  await page.evaluate(()=>document.querySelectorAll('[aria-label="Meta AI response"] p')[2].textContent='Generating now');
  assert.equal((await scan()).answerComplete,false,'one unavailable candidate is not proof both failed');
  await page.evaluate(()=>document.querySelectorAll('[aria-label="Meta AI response"] p')[2].textContent='video (file unavailable)');
  await page.evaluate(()=>document.querySelectorAll('[aria-label="Meta AI response"]').forEach((node,index)=>{
    const video=document.createElement('video');video.src='https://example.invalid/'+index+'.mp4';node.append(video);
    Object.defineProperties(video,{readyState:{value:4},videoWidth:{value:720},duration:{value:8}});
  }));
  state=await scan();assert.equal(state.videoReady,true);assert.equal(state.videoCount,2);
  assert(state.videoSrc.endsWith('/0.mp4'),'choose one actual result without voting');
  await page.evaluate(()=>document.querySelector('[aria-label="your message"] p').textContent='Different request');
  state=await scan();assert.equal(state.matchedUser,false);assert.equal(state.answerComplete,false);
  // Execute the real Meta writer and inspector with the shared transport rule.
  vm.runInNewContext(fs.readFileSync('browser_extension/single_answer.js','utf8'),sandbox);
  await page.setContent('<div contenteditable="true" role="textbox" data-lexical-editor="true" style="width:600px;height:300px"></div>');
  const row={job_id:'fixture',index:1,request_id:'r',context_id:'c',stage:'prepared',prompt,image_name:'scene.png',tabId:1};
  let inserts=0;
  const adapter=new sandbox.Adapter({api:async()=>({package:row}),chromeAPI:{
    tabs:{get:async()=>({url:'https://www.meta.ai/',status:'complete'})},
    scripting:{executeScript:async({func,args})=>[{result:await page.evaluate(({fn,args})=>new Function('return ('+fn+')')()(...args),{fn:func.toString(),args})}]}
  }});
  adapter.owns=async()=>true;adapter.save=async()=>{};adapter.click=async()=>{};
  adapter.debug=async(_id,fn)=>fn(async(method,params)=>{
    assert.equal(method,'Input.insertText');inserts++;
    assert(sandbox.SmartFlowSingleAnswer.has(params.text));
    await page.evaluate(value=>document.querySelector('[role="textbox"]').textContent=value,params.text);
  });
  adapter.event=async(r,stage)=>{r.stage=stage;};
  await adapter.step(row);await adapter.step(row);
  assert.equal(inserts,1);assert.equal(row.stage,'uploading');
  console.log('Meta comparison regression passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
