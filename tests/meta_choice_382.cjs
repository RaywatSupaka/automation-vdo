const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/src/platforms/meta-ai/video.js'),'utf8');
const cases=JSON.parse(fs.readFileSync(path.join(__dirname,'meta_choice_cases_382.json'),'utf8'));
const expected=JSON.parse(fs.readFileSync(0,'utf8'));
let now=100000;
class Clock extends Date {static now(){return now;}}
const s={Date:Clock,URL};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../browser_extension/single_answer.js'),'utf8'),s);
vm.runInNewContext(source.replaceAll('export ','')+'\nthis.Adapter=MetaVideoAdapter;this.inspect=inspectMetaDOM;this.offer=metaChoiceOffer;this.safe=metaSafeOffer;this.followup=metaFollowupOffer;',s);
const clone=x=>JSON.parse(JSON.stringify(x));
const normalize=x=>x.replace(/\s+/g,' ').trim();
const offer=clone(s.offer(cases[0].answer));
const saferAnswer='วิดีโอจากภาพนี้ยังสร้างไม่ได้ในตอนนี้ค่ะ ภาพต้นฉบับมีการจัดองค์ประกอบที่ทำให้ระบบไม่สามารถทำเป็นวิดีโอเคลื่อนไหวพร้อมเสียงพูดได้ ฉันช่วยทำเวอร์ชันที่ปลอดภัยขึ้นให้ได้ทันที โดยปรับการแต่งกายให้มิดชิดขึ้นและจัดเฟรมให้เห็นห้องมากขึ้น อยากให้ลองทำเวอร์ชันนั้นให้เลยไหม?';
const safe=clone(s.safe(saferAnswer));
const historicalOffers=JSON.parse(fs.readFileSync(path.join(__dirname,'meta_historical_offer_cases.json'),'utf8'));
assert.equal(safe.kind,'safe_revision');assert.equal(s.followup(saferAnswer).prompt,safe.prompt);
assert.equal(s.safe('วิดีโอนี้ละเมิดนโยบายความปลอดภัย'),null);
let checks=0;
for(let i=0;i<cases.length;i++){assert.deepEqual(clone(s.offer(cases[i].answer)),expected[i],cases[i].name);checks++;}
const originalPrompt='Create the market scene video with the attached image.';
const url='https://www.meta.ai/prompt/owned';
const state={composerFound:true,composerText:'',composer:{tag:'editor',x:20,y:20},imageCount:0,uploadDialog:false,
  documentReady:true,documentId:'document-fixture',observedURL:url,sendTarget:'send-node',
  matchedOriginal:true,matchedUser:true,matchedChoice:false,userCount:1,conversation:url,stop:false,busy:false,
  answerBusy:false,answerText:offer.proposal_text,answerComplete:true,answerTruncated:false,videoCount:0,videoReady:false,
  proposalText:offer.proposal_text,proposalVideoCount:0,proposalBusy:false,send:{tag:'send',x:30,y:30}};
function fixture(changes={}, selectedOffer=offer){
  let receipt={job_id:'STORY-CHOICE',index:8,request_id:'owned',context_id:'ctx',stage:'generating',conversation_url:url};
  let dom={...state,answerText:selectedOffer.proposal_text,proposalText:selectedOffer.proposal_text,...changes},lost='',cancel=false,changeAfterClaim=false;
  const records={},events=[],physical=[],closed=[],owners={};
  const api=async(route,body)=>{
    if(cancel)throw Object.assign(new Error('cancelled'),{metaBridge:true,metaPaused:true});
    if(!body)return {package:{prompt:originalPrompt,image_name:'scene.png',...clone(receipt)}};
    events.push(clone(body));let authorized;
    if(body.stage==='choice_prepare')receipt.choice ||= {...selectedOffer,stage:'prepared'};
    else if(body.stage==='choice_send_intent'){
      authorized=receipt.choice.stage==='prepared';
      if(authorized)receipt.choice={...receipt.choice,stage:'send_intent',send_at:now/1000};
      if(changeAfterClaim)dom={...dom,stop:true};
    } else if(body.stage==='choice_submitted') receipt.choice={...receipt.choice,stage:'accepted'};
    else if(body.stage==='retry_prepared')throw new Error('must not reupload a choice offer');
    else receipt={...receipt,...body};
    if(lost===body.stage){lost='';throw Object.assign(new Error('lost ack'),{metaBridge:true});}
    return {receipt:{...clone(receipt),...(authorized===undefined?{}:{choice_send_authorized:authorized})}};
  };
  const chrome={runtime:{id:'fixture'},storage:{local:{get:async()=>clone(records),set:async value=>Object.assign(records,clone(value))},
    session:{get:async()=>clone(owners),set:async value=>Object.assign(owners,clone(value))}},
    tabs:{get:async()=>({url,status:'complete'}),create:async()=>{throw new Error('must not open a new tab');},remove:async id=>closed.push(id)},
    downloads:{download:async()=>{physical.push('download');return 9;},search:async()=>[{id:9,state:'complete',exists:true,filename:'C:/fixture/video.mp4'}]}};
  function adapter(){const a=new s.Adapter({api,chromeAPI:chrome});a.inspect=async()=>({...dom,
    composerWireText:dom.composerText?s.SmartFlowSingleAnswer.wrap(dom.composerText):''});
    a.click=async(id,p)=>physical.push(p.tag);a.debug=async(id,operation)=>operation(async(method,params)=>{
      if(method==='Input.dispatchMouseEvent'){if(params.type==='mouseReleased'&&params.x>=0)physical.push('send');return;}
      assert.equal(method,'Input.insertText','must not upload an image');assert.equal(params.text,s.SmartFlowSingleAnswer.wrap(selectedOffer.prompt));physical.push('type-choice');
    });return a;}
  const a=adapter(),row={prompt:originalPrompt,image_name:'scene.png',image_path:'C:/fixture/scene.png',...clone(receipt),tabId:11};
  return {a,row,adapter,events,physical,closed,receipt:()=>clone(receipt),set:value=>{dom=value;},
    lost:stage=>{lost=stage;},cancel:()=>{cancel=true;},changeAfterClaim:()=>{changeAfterClaim=true;},
    init:async()=>{await a.save(row);await a.own(row);},
    prepare:async()=>{await a.save(row);await a.own(row);await a.step(row);now+=6000;await a.step(row);}};
}
(async()=>{
  const browser=await chromium.launch({headless:true,
    ...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  try{
    const page=await browser.newPage();await page.route('**/*',r=>r.abort());
    await page.setContent('<div id="root" role="article" aria-label="ข้อความของคุณ"><p></p><img alt="scene.png"></div><div id="proposal" role="article" aria-label="การตอบกลับของ Meta AI"><p></p><button aria-label="ถูกใจการตอบกลับนี้"></button><button aria-label="คัดลอกการตอบกลับ"></button></div>');
    await page.evaluate(({prompt,proposal})=>{
      document.querySelector('#root p').textContent=prompt;document.querySelector('#proposal p').textContent=proposal;
      Object.defineProperties(document.querySelector('img'),{complete:{value:true},naturalWidth:{value:720}});
    },{prompt:originalPrompt,proposal:offer.proposal_text});
    const scan=choice=>page.evaluate(({fn,prompt,choice})=>new Function('return ('+fn+')')()(prompt,'scene.png',choice),
      {fn:s.inspect.toString(),prompt:originalPrompt,choice});
    assert.equal((await scan(null)).matchedUser,true);checks++;
    let snap=await scan({...offer,stage:'prepared'});
    assert.equal(snap.matchedOriginal,true);assert.equal(snap.matchedChoice,false);
    assert.equal(snap.answerText,'');assert.equal(snap.proposalText,offer.proposal_text);checks++;
    await page.evaluate(prompt=>{
      const user=document.createElement('div');user.id='choice';user.setAttribute('role','article');user.setAttribute('aria-label','ข้อความของคุณ');user.textContent=prompt;document.body.append(user);
      const reply=document.createElement('div');reply.id='result';reply.setAttribute('role','article');reply.setAttribute('aria-label','การตอบกลับของ Meta AI');reply.innerHTML='<video src="https://media.invalid/new.mp4"></video>';document.body.append(reply);
      Object.defineProperties(reply.querySelector('video'),{readyState:{value:4},videoWidth:{value:720},duration:{value:10}});
    },offer.prompt);
    snap=await scan({...offer,stage:'accepted'});
    assert.equal(snap.matchedChoice,true);assert.equal(snap.matchedUser,true);assert.equal(snap.videoReady,true);checks++;
    assert.equal((await scan(null)).videoReady,false,'legacy controller must not accept arbitrary second user');checks++;
    await page.evaluate(()=>{document.querySelector('#result').remove();});
    snap=await scan({...offer,stage:'accepted'});assert.equal(snap.answerText,'');assert.equal(snap.videoReady,false);checks++;
    await page.evaluate(()=>{document.querySelector('#proposal').insertAdjacentHTML('beforeend','<video src="https://media.invalid/old.mp4"></video>');});
    snap=await scan({...offer,stage:'accepted'});assert.equal(snap.matchedChoice,false);assert.equal(snap.videoReady,false);checks++;
    await page.evaluate(()=>{document.querySelector('video').remove();document.querySelector('#choice').textContent='unrelated user text';});
    assert.equal((await scan({...offer,stage:'accepted'})).matchedChoice,false);checks++;
    await page.evaluate(prompt=>{document.querySelector('#choice').textContent=prompt;document.body.append(document.querySelector('#choice').cloneNode(true));},offer.prompt);
    assert.equal((await scan({...offer,stage:'accepted'})).matchedChoice,false);checks++;
    await page.setContent('<div id="root" role="article" aria-label="ข้อความของคุณ"><p></p><img alt="scene.png"></div><div id="proposal" role="article" aria-label="การตอบกลับของ Meta AI"><p></p><button aria-label="ถูกใจการตอบกลับนี้"></button><button aria-label="คัดลอกการตอบกลับ"></button></div>');
    await page.evaluate(({prompt,proposal})=>{
      document.querySelector('#root p').textContent=prompt;document.querySelector('#proposal p').textContent=proposal;
      Object.defineProperties(document.querySelector('img'),{complete:{value:true},naturalWidth:{value:720}});
    },{prompt:originalPrompt,proposal:saferAnswer});
    snap=await scan(null);assert.equal(snap.matchedUser,true);assert.equal(snap.answerComplete,true);
    assert.equal(snap.videoCount,0);assert.equal(s.safe(snap.answerText).kind,'safe_revision');checks++;
    await page.evaluate(prompt=>{
      const user=document.createElement('div');user.setAttribute('role','article');user.setAttribute('aria-label','ข้อความของคุณ');user.textContent=prompt;document.body.append(user);
      const reply=document.createElement('div');reply.setAttribute('role','article');reply.setAttribute('aria-label','การตอบกลับของ Meta AI');reply.innerHTML='<video src="https://media.invalid/safer.mp4"></video>';document.body.append(reply);
      Object.defineProperties(reply.querySelector('video'),{readyState:{value:4},videoWidth:{value:720},duration:{value:10}});
    },safe.prompt);
    snap=await scan({...safe,stage:'accepted'});assert.equal(snap.matchedChoice,true);assert.equal(snap.videoReady,true);checks++;
  }finally{await browser.close();}

  const c=fixture();await c.prepare();assert.equal(c.receipt().choice.stage,'prepared');assert.deepEqual(c.physical,[]);
  await c.a.step(c.row);assert.deepEqual(c.physical,['editor','type-choice']);
  c.set({...state,composerText:normalize(offer.prompt)});await c.a.step(c.row);
  assert.equal(c.receipt().choice.stage,'send_intent');assert.equal(c.physical.filter(x=>x==='send').length,1);
  await c.a.step(c.row);assert.equal(c.physical.filter(x=>x==='send').length,1);
  const accepted={...state,composerText:'',matchedChoice:true,userCount:2,answerText:'',answerComplete:false,stop:true};
  c.set(accepted);await c.a.step(c.row);assert.equal(c.receipt().choice.stage,'accepted');
  await c.a.step(c.row);assert.equal(c.physical.filter(x=>x==='download').length,0);
  const restarted=c.adapter();let row=(await restarted.records()).owned;
  c.set({...accepted,stop:false,videoReady:true,videoCount:1,videoSrc:'https://media.invalid/choice.mp4'});
  await restarted.step(row);assert.equal(c.receipt().stage,'downloading');
  await restarted.step(row);assert.equal(c.receipt().stage,'stored');await restarted.step(row);
  assert.deepEqual(c.closed,[11]);assert.equal(c.physical.filter(x=>x==='send').length,1);checks++;
  const safer=fixture({},safe);await safer.prepare();assert.equal(safer.receipt().choice.kind,'safe_revision');
  await safer.a.step(safer.row);assert.deepEqual(safer.physical,['editor','type-choice']);
  safer.set({...state,proposalText:safe.proposal_text,composerText:normalize(safe.prompt)});
  await safer.a.step(safer.row);assert.equal(safer.receipt().choice.stage,'send_intent');
  await safer.a.step(safer.row);assert.equal(safer.physical.filter(x=>x==='send').length,1);
  safer.set({...state,proposalText:safe.proposal_text,matchedChoice:true,userCount:2,composerText:'',stop:false,answerText:'',answerComplete:false});
  await safer.a.step(safer.row);assert.equal(safer.receipt().choice.stage,'accepted');
  safer.set({...state,proposalText:safe.proposal_text,matchedChoice:true,userCount:2,composerText:'',stop:false,videoReady:true,videoCount:1,videoSrc:'https://media.invalid/safer.mp4'});
  await safer.a.step(safer.row);assert.equal(safer.receipt().stage,'downloading');
  await safer.a.step(safer.row);assert.equal(safer.receipt().stage,'stored');
  assert.equal(safer.physical.filter(x=>x==='send').length,1);checks++;

  // Retained M5/M6 provider replies must enter the same durable one-followup
  // path. No original-image upload, native preference vote or fresh tab.
  for(const entry of historicalOffers){
    const selected=clone(s.followup(entry.answer));
    assert.equal(selected.kind,'safe_revision');
    if(entry.family==='M6'){assert.equal(selected.selection,'first_clothing_only');assert.equal(selected.number,1);}
    const f=fixture({},selected);await f.prepare();assert.equal(f.receipt().choice.stage,'prepared');
    await f.a.step(f.row);assert.deepEqual(f.physical,['editor','type-choice']);
    const selectedState={...state,proposalText:selected.proposal_text,answerText:selected.proposal_text,
      composerText:normalize(selected.prompt)};
    f.set(selectedState);await f.a.step(f.row);await f.a.step(f.row);
    assert.equal(f.physical.filter(x=>x==='send').length,1);
    f.set({...selectedState,composerText:'',matchedChoice:true,userCount:2,answerText:'Here is a video description.',
      answerComplete:true});await f.a.step(f.row);await f.a.step(f.row);
    assert.equal(f.receipt().stage,'generating');assert(!f.physical.includes('download'));
    f.set({...selectedState,composerText:'',matchedChoice:true,userCount:2,videoReady:true,videoCount:1,
      videoSrc:'https://media.invalid/historical.mp4'});
    await f.a.step(f.row);await f.a.step(f.row);assert.equal(f.receipt().stage,'stored');
    assert.equal(f.physical.filter(x=>x==='download').length,1);checks++;

    const unknown=fixture({},selected);await unknown.prepare();
    unknown.set(selectedState);unknown.lost('choice_send_intent');
    await assert.rejects(()=>unknown.a.step(unknown.row),/lost ack/);
    const restored=unknown.adapter(),saved=(await restored.records()).owned;
    await restored.step(saved);assert.deepEqual(unknown.physical,[]);checks++;

    const pair=fixture({comparison:true},selected);await pair.prepare();
    assert(!pair.receipt().choice);assert.deepEqual(pair.physical,[]);
    assert.equal(pair.receipt().stage,'needs_attention','unscoped comparison must not wait forever or combine offers');checks++;
  }

  for(const changes of [{stop:true},{busy:true},{answerBusy:true},{videoCount:1},{answerComplete:false},{answerTruncated:true},{matchedUser:false}]){
    const f=fixture(changes);await f.prepare();assert.equal(f.receipt().choice,undefined);assert.deepEqual(f.physical,[]);checks++;
  }
  for(const changes of [{stop:true},{busy:true},{proposalBusy:true},{proposalVideoCount:1},{proposalText:'changed'},
    {composerFound:false},{imageCount:1},{uploadDialog:true},{matchedOriginal:false}]){
    const f=fixture();await f.prepare();f.set({...state,composerText:normalize(offer.prompt),...changes});await f.a.step(f.row);
    assert.deepEqual(f.physical,[]);assert.equal(f.receipt().choice.stage,'prepared');checks++;
  }
  const foreign=fixture();await foreign.prepare();foreign.set({...state,composerText:'user draft'});
  await foreign.a.step(foreign.row);assert.equal(foreign.receipt().stage,'needs_attention');assert.deepEqual(foreign.physical,[]);checks++;
  // Crash after durable send claim: observe original chat, never click again.
  const lost=fixture();await lost.prepare();lost.set({...state,composerText:normalize(offer.prompt)});lost.lost('choice_send_intent');
  await assert.rejects(()=>lost.a.step(lost.row),/lost ack/);
  const recovered=lost.adapter();row=(await recovered.records()).owned;await recovered.step(row);
  assert.deepEqual(lost.physical,[]);lost.set({...accepted,stop:false});await recovered.step(row);
  assert.equal(lost.receipt().choice.stage,'accepted');assert.deepEqual(lost.physical,[]);checks++;
  const prepLost=fixture();await prepLost.init();await prepLost.a.step(prepLost.row);now+=6000;prepLost.lost('choice_prepare');
  await assert.rejects(()=>prepLost.a.step(prepLost.row),/lost ack/);await prepLost.a.step(prepLost.row);
  assert.equal(prepLost.events.filter(x=>x.stage==='choice_prepare').length,1);
  assert.deepEqual(prepLost.physical,['editor','type-choice']);checks++;
  const blocked=fixture();await blocked.prepare();blocked.set({...state,composerText:normalize(offer.prompt)});blocked.changeAfterClaim();
  await blocked.a.step(blocked.row);assert.deepEqual(blocked.physical,[]);assert.equal(blocked.receipt().choice.stage,'send_intent');checks++;
  const cancel=fixture();await cancel.prepare();cancel.cancel();await cancel.a.tick();assert.deepEqual(cancel.physical,[]);checks++;
  console.log(`Meta choice382: ${checks} actual-source DOM/controller cases passed; no live generation`);
})().catch(e=>{console.error(e);process.exitCode=1;});
