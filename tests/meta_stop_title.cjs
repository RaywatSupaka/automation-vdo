// Actual-source regression: synthetic offline browser; no user profile/provider/API.
// Verifies completed-video collection and preserves genuine Stop/owner guards.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=process.cwd();
const source=fs.readFileSync(path.join(root,'browser_extension/src/platforms/meta-ai/video.js'),'utf8');
function load(code){const scope={Date,URL};vm.runInNewContext(code.replaceAll('export ','')+'\nthis.Adapter=MetaVideoAdapter;this.inspect=inspectMetaDOM;',scope);return scope;}
const scope=load(source),clone=value=>JSON.parse(JSON.stringify(value));
const prompt='A saved scene about stop-motion and a character saying หยุด, with the full exact original instruction.';
const url='https://www.meta.ai/prompt/synthetic-owned';
let checks=0;
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1000,height:800}});
  await page.route('**/*',route=>route.abort());
  const setup=async({label='',attrs={},hidden=false,partial=false,duplicate=false,imageAlt='scene_02.png',wrapper=false,composer=false}={})=>{
   await page.setContent('<main><nav id="navigation"></nav><form id="composer"><div role="textbox" contenteditable="true" data-lexical-editor="true" style="width:400px;height:60px"></div></form><div id="user" role="article" aria-label="ข้อความของคุณ"></div><div id="answer" role="article" aria-label="การตอบกลับของ Meta AI"><p>วิดีโอฉาก 02 เสร็จแล้ว</p><video></video><button aria-label="คัดลอกการตอบกลับ">Copy</button><button aria-label="ถูกใจการตอบกลับนี้">Like</button><button>ดูวิดีโอ</button><button>ดาวน์โหลด</button></div><div role="progressbar" style="display:none"></div></main>');
   await page.evaluate(({prompt,label,attrs,hidden,partial,duplicate,imageAlt,wrapper,composer})=>{
    const user=document.querySelector('#user');user.textContent=partial?prompt.slice(0,35):prompt;
    const image=document.createElement('img');image.alt=imageAlt;user.append(image);
    Object.defineProperties(image,{complete:{value:true},naturalWidth:{value:720},naturalHeight:{value:1280}});
    if(partial){const expand=document.createElement('button');expand.textContent='ขยาย';user.append(expand);}
    if(duplicate){const another=document.createElement('div');another.setAttribute('role','article');another.setAttribute('aria-label','ข้อความของคุณ');another.textContent='Another request';user.after(another);}
    const button=document.createElement('button');button.textContent=label;for(const [key,value] of Object.entries(attrs))button.setAttribute(key,value);
    if(hidden)button.style.display='none';document.querySelector(composer?'#composer':wrapper?'#answer':'#navigation').append(button);
    const video=document.querySelector('video');video.src='https://media.invalid/owned.mp4';
    Object.defineProperties(video,{readyState:{value:4},videoWidth:{value:720},videoHeight:{value:1280},duration:{value:10}});
   },{prompt,label,attrs,hidden,partial,duplicate,imageAlt,wrapper,composer});
  };
  const scan=scope=>page.evaluate(({fn,prompt})=>new Function('return ('+fn+')')()(prompt,'scene_02.png'),{fn:scope.inspect.toString(),prompt});
  await setup({label:'ยายบุญจักรหยุด'});
  let fixed=await scan(scope);
  assert.equal(fixed.matchedUser,true);checks++;
  assert.equal(fixed.stop,false);assert.equal(fixed.videoReady,true);assert.equal(fixed.pageBusy,false);checks+=3;
  const stops=[{label:'หยุด',composer:true},{label:'หยุดสร้างคำตอบ',composer:true},{label:'หยุดการตอบกลับ',composer:true},
    {label:'Stop',composer:true},{label:'Stop generating',composer:true},{label:'Stop generating response',composer:true},
    {label:'Send',attrs:{'aria-label':'Stop generating'}},{label:'',attrs:{title:'หยุดสร้างวิดีโอ'}},
    {label:'',attrs:{'data-testid':'stop-response-button'}}];
  for(const control of stops){await setup(control);const state=await scan(scope);assert.equal(state.stop,true,JSON.stringify(control));assert.equal(state.videoReady,false);checks+=2;}
  const nonStops=[{label:'ยายบุญจักรหยุด'},{label:'Stop-motion story'},{label:'Never stop dreaming'},
    {label:'หยุด'},{label:'Stop'},{label:'Stop generating'},
    {label:'หยุดหรือทำต่อ'},{label:'Restart or Stop'},{label:'ดาวน์โหลด'},
    {label:'Pause',attrs:{'aria-label':'หยุดชั่วคราว'}},{label:'',attrs:{title:'Story about หยุด'}},
    {label:'',attrs:{'data-testid':'story-stop-title'}},{label:'',attrs:{'data-testid':'submit'}},
    {label:'Prompt copy: stop talking then wave',wrapper:true},{label:'Stop',hidden:true}];
  for(const control of nonStops){await setup(control);const state=await scan(scope);assert.equal(state.stop,false,JSON.stringify(control));assert.equal(state.videoReady,true);assert.equal(state.send,null);checks+=3;}
  for(const block of [{partial:true},{duplicate:true},{imageAlt:'other-scene.png'}]){
   await setup({label:'ยายบุญจักรหยุด',...block});for(const candidate of [scope]){
    const state=await scan(candidate);assert.equal(state.matchedUser,false);assert.equal(state.videoReady,false);checks+=2;
   }
  }
  async function collect(scope,dom){
   let receipt={job_id:'STORY-FIXTURE',index:2,request_id:'owned',context_id:'ctx',stage:'generating',conversation_url:url};
   const local={},events=[],downloads=[];
   const api=async(_,body)=>{if(!body)return{package:clone(receipt)};events.push(body.stage);receipt={...receipt,...body};return{receipt:clone(receipt)};};
   const chrome={storage:{local:{get:async()=>clone(local),set:async value=>Object.assign(local,clone(value))}},
    tabs:{get:async()=>({url,status:'complete'})},downloads:{download:async request=>{downloads.push(request);return 7;}}};
   const adapter=new scope.Adapter({api,chromeAPI:chrome});adapter.owns=async()=>true;
   adapter.inspect=async()=>({...dom,conversation:url});const row={...receipt,tabId:1};await adapter.step(row);
   return{stage:receipt.stage,events,downloads};
  }
  await setup({label:'ยายบุญจักรหยุด'});fixed=await scan(scope);
  let result=await collect(scope,fixed);assert.equal(result.stage,'downloading');assert.deepEqual(result.events,['download_intent','downloading']);assert.equal(result.downloads.length,1);checks+=3;
  await setup({label:'Stop generating',composer:true});result=await collect(scope,await scan(scope));assert.equal(result.stage,'generating');assert.equal(result.downloads.length,0);checks+=2;
  assert.equal(fs.readFileSync(path.join(root,'browser_extension/src/platforms/meta-ai/video.js'),'utf8'),source,'active source must stay unchanged');checks++;
  console.log(JSON.stringify({pass:true,checks,canonicalModified:false,observedTitleProtected:true,syntheticOfflineOnly:true}));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
