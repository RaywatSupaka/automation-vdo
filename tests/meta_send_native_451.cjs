// Isolated native DOM + production inspector/controller + actual CDP input.
// All content is local synthetic markup. No user browser/profile/provider I/O.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright');const source=fs.readFileSync('browser_extension/src/platforms/meta-ai/video.js','utf8');
const s={Date,URL};vm.runInNewContext(source.replaceAll('export ','')+'\nthis.Adapter=MetaVideoAdapter;this.inspect=inspectMetaDOM;',s);
vm.runInNewContext(fs.readFileSync('browser_extension/single_answer.js','utf8'),s);
const clone=x=>JSON.parse(JSON.stringify(x));
(async()=>{const browser=await chromium.launch({headless:true});let cases=0;
 try{for(const boundary of ['ack','press'])for(const mutation of ['none','draft','stop','move','cover','replace','image']){
  const page=await browser.newPage();let network=0;await page.route('**/*',route=>{network++;return route.abort();});
  await page.setContent('<style>#editor{position:absolute;left:20px;top:20px;width:400px;height:120px}button{position:absolute;left:460px;top:80px;width:90px;height:50px}</style><div role="textbox" contenteditable="true" data-lexical-editor="true" id="editor">owned prompt<img alt="scene.png"></div><button aria-label="Send" id="send">Send</button>');
  await page.evaluate(instruction=>document.querySelector('#editor').append(document.createTextNode('\n\n'+instruction)),s.SmartFlowSingleAnswer.instruction);
  await page.evaluate(()=>{window.sends=0;window.stops=0;const image=document.querySelector('img');image.dataset.source='original';
   Object.defineProperties(image,{complete:{value:true},naturalWidth:{value:512},naturalHeight:{value:512},currentSrc:{get(){return 'blob:'+this.dataset.source;}}});
   document.addEventListener('click',event=>{if(event.target.closest('#send')){if(event.target.textContent==='Stop')window.stops++;else window.sends++;}});});
  const change=async()=>page.evaluate(mutation=>{
   const button=document.querySelector('#send'),editor=document.querySelector('#editor');
   if(mutation==='draft')editor.firstChild.textContent='manual draft';
   if(mutation==='stop'){button.textContent='Stop';button.setAttribute('title','Stop generating');}
   if(mutation==='move')button.style.left='650px';
   if(mutation==='replace')button.replaceWith(button.cloneNode(true));
   if(mutation==='image')editor.querySelector('img').dataset.source='different';
   if(mutation==='cover'){const cover=document.createElement('div');cover.style='position:absolute;left:450px;top:70px;width:120px;height:80px;background:red;z-index:10';document.body.append(cover);}
  },mutation);
  let receipt={job_id:'STORY-FIXTURE',index:1,request_id:'r',context_id:'c',stage:'ready_to_send',prompt:'owned prompt',image_name:'scene.png'};
  const store={},physical=[],session=await page.context().newCDPSession(page);
  const chrome={storage:{local:{get:async()=>clone(store),set:async value=>Object.assign(store,clone(value))}},
   scripting:{executeScript:async({func,args})=>{
    const result=await page.evaluate(({fn,args})=>new Function('return ('+fn+')')()(...args),{fn:func.toString(),args});
    return[{documentId:'isolated-document',result:{...result,observedURL:'https://www.meta.ai/'}}];
   }},
   tabs:{get:async()=>({url:'https://www.meta.ai/',status:'complete'})},debugger:{attach:async()=>{},detach:async()=>{},sendCommand:async(_,method,params)=>{
    physical.push(clone(params));const result=await session.send(method,params);if(boundary==='press'&&params.type==='mousePressed')await change();return result;}}};
  const api=async(_,body)=>{if(!body)return{package:clone(receipt)};receipt={...receipt,...body};
   if(boundary==='ack'&&body.stage==='send_intent')await change();return{receipt:clone(receipt)};};
  const adapter=new s.Adapter({api,chromeAPI:chrome});adapter.owns=async()=>true;
  const row={...receipt,tabId:1};await adapter.step(row);await adapter.step(row);
  const clicks=await page.evaluate(()=>({sends:window.sends,stops:window.stops}));
  assert.equal(clicks.sends,mutation==='none'?1:0,boundary+'/'+mutation);assert.equal(clicks.stops,0);
  assert.equal(physical.filter(p=>p.type==='mousePressed').length,mutation==='none'||boundary==='press'?1:0);
  if(boundary==='press'&&mutation!=='none')assert(physical.at(-1).x<0&&physical.at(-1).y<0);
  assert.equal(network,0);cases++;await session.detach();await page.close();
 }
 console.log(JSON.stringify({ok:true,cases,nativeDom:true,nativeInput:true,providerNetworkRequests:0}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
