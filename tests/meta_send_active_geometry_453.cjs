// Exact production inspector/controller against a local button with Meta's
// observed active scale animation. No user profile or provider network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/src/platforms/meta-ai/video.js','utf8');
const scope={Date,URL};vm.runInNewContext(source.replaceAll('export ','')+'\nthis.Adapter=MetaVideoAdapter;',scope);
vm.runInNewContext(fs.readFileSync('browser_extension/single_answer.js','utf8'),scope);
const clone=value=>JSON.parse(JSON.stringify(value));
(async()=>{
 const browser=await chromium.launch({headless:true});const findings=[];
 try {
  const cases=[...['none','transform','scale'].map(animation=>({animation,mutation:'none',choice:false})),
   {animation:'scale',mutation:'none',choice:true},
   ...['cover','stop','replace','image'].map(mutation=>({animation:'scale',mutation,choice:false}))];
  for(const {animation,mutation,choice} of cases) {
   const page=await browser.newPage({viewport:{width:1600,height:900}});let network=0;
   await page.route('**/*',route=>{network++;return route.abort();});
   await page.setContent(`<style>
    #editor{position:absolute;left:700px;top:500px;width:680px;height:100px}
    #send{position:absolute;left:1426px;top:567px;width:32px;height:32px;padding:0;border:0;transition-property:transform,translate,scale,rotate;transition-duration:150ms;transition-timing-function:cubic-bezier(.4,0,.2,1)}
    #send:active{${animation==='transform'?'transform:scale(.98)':animation==='scale'?'scale:.98':''}}
   </style>${choice?'<div role="article" aria-label="ข้อความของคุณ">owned prompt<img alt="scene_04.png"></div><div role="article" aria-label="การตอบกลับของ Meta AI">owned proposal</div>':''}<div role="textbox" contenteditable="true" data-lexical-editor="true" id="editor">${choice?'owned choice':'owned prompt<img alt="scene_04.png">'}</div><button aria-label="ส่ง" data-testid="composer-send-button" id="send">ส่ง</button>`);
   await page.evaluate(instruction=>document.querySelector('#editor').append(document.createTextNode('\n\n'+instruction)),scope.SmartFlowSingleAnswer.instruction);
   await page.evaluate(()=>{
    window.sends=0;window.stops=0;
    document.addEventListener('click',event=>{const button=event.target.closest('#send');if(button){if(button.textContent==='Stop')window.stops++;else window.sends++;}});
    const img=document.querySelector('img');img.dataset.source='owned';
    Object.defineProperties(img,{complete:{value:true},naturalWidth:{value:512},naturalHeight:{value:512},currentSrc:{get(){return 'blob:'+this.dataset.source;}}});
   });
   let receipt={job_id:'STORY-FIXTURE',index:4,request_id:'r',context_id:'c',stage:choice?'generating':'ready_to_send',prompt:'owned prompt',image_name:'scene_04.png'};
   if(choice)receipt.choice={stage:'prepared',prompt:'owned choice',proposal_text:'owned proposal'};
   const store={},physical=[],samples=[],session=await page.context().newCDPSession(page);
   const chrome={storage:{local:{get:async()=>clone(store),set:async value=>Object.assign(store,clone(value))}},
    tabs:{get:async()=>({url:'https://www.meta.ai/',status:'complete'})},
    scripting:{executeScript:async({func,args})=>{
     const state=await page.evaluate(({fn,args})=>new Function('return ('+fn+')')()(...args),{fn:func.toString(),args});
     state.observedURL='https://www.meta.ai/';samples.push({point:state.send,target:state.sendTarget,origin:args[3],originMatches:state.sendOriginMatches});return [{documentId:'native-document',result:state}];
    }},
    debugger:{attach:async()=>{},detach:async()=>{},sendCommand:async(_,method,params)=>{
     physical.push(clone(params));const result=await session.send(method,params);
     // Freeze one real native transition frame, making floating-point geometry
     // reproducible without relying on machine speed or a provider response.
     if(params.type==='mousePressed')await page.evaluate(mutation=>{
      const button=document.querySelector('#send');
      for(const transition of button.getAnimations()){
       transition.pause();transition.currentTime=30;
      }
      if(mutation==='cover'){const cover=document.createElement('div');cover.style='position:absolute;left:1420px;top:560px;width:50px;height:50px;z-index:99;background:red';document.body.append(cover);}
      if(mutation==='stop'){button.textContent='Stop';button.setAttribute('title','Stop generating');}
      if(mutation==='replace')button.replaceWith(button.cloneNode(true));
      if(mutation==='image')document.querySelector('#editor img').dataset.source='different';
     },mutation);
     return result;
    }}};
   const api=async(_,body)=>{
    if(!body)return {package:clone(receipt)};receipt={...receipt,...body};
    if(body.stage==='choice_send_intent'){receipt.stage='generating';receipt.choice={...receipt.choice,stage:'send_intent',send_at:Date.now()/1000};}
    return {receipt:{...clone(receipt),choice_send_authorized:true}};
   };
   const adapter=new scope.Adapter({api,chromeAPI:chrome});adapter.owns=async()=>true;
   const row={...receipt,tabId:1};await adapter.step(row);
   findings.push({animation,mutation,choice,...await page.evaluate(()=>({clicks:window.sends,stops:window.stops})),stage:row.stage,samples,physical,sendDiagnostic:row.sendDiagnostic||'',network});
   await session.detach();await page.close();
  }
  console.log(JSON.stringify({findings},null,2));
  for(const row of findings){
   assert.equal(row.network,0);assert.equal(row.stops,0);
   assert.equal(row.clicks,row.mutation==='none'?1:0,`${row.animation}/${row.mutation}/${row.choice}: full click only on unchanged owned Send`);
  }
  for(const row of findings){
   if(row.mutation!=='none'){
    assert.equal(row.stage,'send_intent');assert.equal(row.sendDiagnostic,'gesture_outcome_unknown');
    assert.equal(row.physical.filter(event=>event.type==='mousePressed').length,1);
    assert.equal(row.physical.filter(event=>event.type==='mouseReleased').length,1);
    assert(row.physical.at(-1).x<0&&row.physical.at(-1).y<0,'changed target must release outside page');
    continue;
   }
   assert.deepEqual(row.physical.map(event=>({type:event.type,x:event.x,y:event.y})),[
    {type:'mousePressed',x:1442,y:583},{type:'mouseReleased',x:1442,y:583}
   ]);
   assert(row.samples.slice(1).every(sample=>sample.origin?.x===1442&&sample.origin?.y===583&&sample.originMatches===true),
    'every guard read must prove the original gesture point still hits the same Send button');
  }
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
