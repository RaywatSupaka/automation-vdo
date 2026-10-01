const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const selector=source.slice(source.indexOf('function resolveFlowStartFrameTarget'),source.indexOf('// Loading/progress is not an attachment failure.'));
const waitSource=source.slice(source.indexOf('async function waitForFlowStartFrameAsset'),source.indexOf('// Runs in the page after tab activation'));
const start=source.indexOf('      const attachVisibleMedia = async () => {');
const branch=source.slice(start,source.indexOf('// Correct Flow order',start))+'return "legacy"; };';
const thumbnail='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=';
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
 const page=await browser.newPage({viewport:{width:400,height:802}});
 const html=`<style>button,[role=option]{display:block;width:160px;height:40px}[hidden]{display:none!important}</style>
 <div class="base-prompt-box"><button class="empty-chip">เริ่ม</button><button class="empty-chip">สิ้นสุด</button></div>
 <div role="dialog" hidden><div role="listbox"><div role="option" tabindex="0" aria-label="selling_image_01 (75).png">selling_image_01 (75).png<img class="asset-thumbnail-image" src="${thumbnail}"></div></div></div>
 <script>document.querySelector('button').onclick=()=>document.querySelector('[role=dialog]').hidden=false;
 document.querySelector('[role=option]').onclick=()=>{window.attached=true;document.querySelector('[role=dialog]').hidden=true;};</script>`;
 async function reset(){await page.setContent(html);await page.waitForFunction(()=>document.querySelector('img').naturalWidth>0);}
 async function target(kind,filename=''){return page.evaluate(`(${selector})(${JSON.stringify(kind)},${JSON.stringify(filename)})`);}
 await reset();assert(await target('start'));assert.equal(await target('asset','selling_image_01 (75).png'),null);
 let now=100000,clicks=[],current=true,onWait=async()=>{};const context={attachJobId:'JOB',attachShotIndex:1,referenceFilename:'selling_image_01 (75).png',Date:{now:()=>now},
 referenceStore:{smartpostFlowReferenceFile:{jobId:'JOB',shotIndex:1}},setTimeout:f=>f(),method:'',
 attachmentStillCurrent:async()=>current,
 CLIENT_ID:'fixture',attachRunId:'RUN',tabId:1,sender:{tab:{url:'https://flow.google.com/project/fixture'}},forwardObservedProgress:async()=>{},
 findPoint:async(kind,c={})=>{now+=300;await onWait();return target(kind==='start_frame'?'start':kind==='start_frame_state'?'state':'asset',c.filename);},
 physicalClick:async p=>{clicks.push(p.kind);await page.mouse.click(p.x,p.y);},
 waitForPromptMediaProof:async()=>page.evaluate(()=>Boolean(window.attached)),traceAttach:async()=>{}};
 vm.createContext(context);vm.runInContext(waitSource+branch,context);
 assert.equal(await vm.runInContext('attachVisibleMedia()',context),true);assert.deepEqual(clicks,['start','asset']);
 await reset();await page.getByRole('button',{name:'เริ่ม',exact:true}).click();
 assert.equal(await target('start'),null);assert.equal(await target('asset','wrong.png'),null);
 assert(await target('asset','selling_image_01 (75).png'));
 await page.evaluate(()=>{const el=document.querySelector('[role=option]');el.parentNode.append(el.cloneNode(true));});
 assert.equal(await target('asset','selling_image_01 (75).png'),null,'ambiguous filename rejected');
 await reset();clicks=[];context.referenceStore.smartpostFlowReferenceFile.jobId='OTHER';
 assert.equal(await vm.runInContext('attachVisibleMedia()',context),false);assert.equal(clicks.length,0);
 context.referenceStore.smartpostFlowReferenceFile.jobId='JOB';context.referenceFilename='missing.png';
 assert.equal(await vm.runInContext('attachVisibleMedia()',context),false);assert.deepEqual(clicks,['start'],'no repeat/gallery/upload after missing match');
 context.referenceFilename='selling_image_01 (75).png';
 // Actual mobile markup: filename is a nested span, not aria-label. Full-screen
 // dialog can extend a fraction of a pixel beyond the viewport while animating.
 await reset();await page.evaluate(thumbnail=>{
   const dialog=document.querySelector('[role=dialog]');dialog.style='position:fixed;left:0;top:0;width:400.5px;height:802.5px';
   const option=document.querySelector('[role=option]');option.removeAttribute('aria-label');
   option.innerHTML=`<flow-add-menu-asset-item><img class="asset-thumbnail-image" src="${thumbnail}"><span class="asset-title">selling_image_01 (75).png</span><span>image</span></flow-add-menu-asset-item>`;
   option.hidden=true;dialog.insertAdjacentHTML('beforeend','<div role="progressbar" style="width:30px;height:30px">กำลังโหลด…</div>');
 },thumbnail);
 clicks=[];const begun=now;onWait=async()=>{if(now-begun>12000)await page.evaluate(()=>{
   document.querySelector('[role=option]').hidden=false;document.querySelector('[role=progressbar]')?.remove();
 });};
 assert.equal(await vm.runInContext('attachVisibleMedia()',context),true,'slow virtualized picker exceeds old eight-second deadline');
 assert.deepEqual(clicks,['start','asset']);onWait=async()=>{};
 // A mounted filename/button is NOT a loaded image. Hold the actual thumbnail
 // network request; old371 incorrectly returns a clickable target here.
 await reset();await page.getByRole('button',{name:'เริ่ม',exact:true}).click();
 let thumbnailRoute;
 await page.route('https://fixture.invalid/slow.png',route=>{thumbnailRoute=route;});
 await page.evaluate(()=>{document.querySelector('img').src='https://fixture.invalid/slow.png';});
 await page.waitForFunction(()=>!document.querySelector('img').complete);
 assert.equal(await target('asset','selling_image_01 (75).png'),null,'never click while thumbnail is loading');
 assert.equal((await target('state','selling_image_01 (75).png')).loading,true,'image loading is activity even without a spinner');
 clicks=[];const imageBegan=now;let imageReleased=false;
 onWait=async()=>{if(now-imageBegan>20000 && !imageReleased && thumbnailRoute){
   imageReleased=true;await thumbnailRoute.fulfill({contentType:'image/png',body:Buffer.from(thumbnail.split(',')[1],'base64')});
   await page.waitForFunction(()=>document.querySelector('img').complete && document.querySelector('img').naturalWidth>0);
 }};
 assert.equal(await vm.runInContext('attachVisibleMedia()',context),true);
 assert.deepEqual(clicks,['asset'],'exactly one asset click, only after image load');onWait=async()=>{};
 // Broken image, absent thumbnail, disabled option and pending upload all veto.
 await reset();await page.getByRole('button',{name:'เริ่ม',exact:true}).click();
 await page.evaluate(()=>{document.querySelector('img').src='data:image/png;base64,broken';});
 await page.waitForFunction(()=>document.querySelector('img').complete);
 assert.equal(await target('asset','selling_image_01 (75).png'),null,'broken image must not be selected');
 assert.equal((await target('state','selling_image_01 (75).png')).image_state,'failed');
 await page.evaluate(()=>document.querySelector('img').remove());
 assert.equal(await target('asset','selling_image_01 (75).png'),null,'title without thumbnail is not ready');
 await reset();await page.getByRole('button',{name:'เริ่ม',exact:true}).click();
 await page.evaluate(()=>document.querySelector('[role=option]').setAttribute('aria-busy','true'));
 assert.equal(await target('asset','selling_image_01 (75).png'),null,'decoded thumbnail still uploading');
 await page.evaluate(()=>document.querySelector('[role=option]').removeAttribute('aria-busy'));
 assert(await target('asset','selling_image_01 (75).png'));
 await page.evaluate(()=>document.querySelector('[role=option]').setAttribute('aria-disabled','true'));
 assert.equal(await target('asset','selling_image_01 (75).png'),null);
 await reset();await page.getByRole('button',{name:'เริ่ม',exact:true}).click();
 await page.evaluate(()=>{
   window.loaderAnimation=document.querySelector('img').animate([{opacity:.1},{opacity:.9}],{duration:1000,iterations:Infinity});
 });
 assert.equal(await target('asset','selling_image_01 (75).png'),null,'wait while thumbnail is animated');
 assert.equal((await target('state','selling_image_01 (75).png')).animation_active,true);
 await page.evaluate(()=>window.loaderAnimation.cancel());
 assert(await target('asset','selling_image_01 (75).png'));
 await reset();await page.getByRole('button',{name:'เริ่ม',exact:true}).click();clicks=[];
 assert.equal(await vm.runInContext('attachVisibleMedia()',context),true,'reuse open picker without another Start');assert.deepEqual(clicks,['asset']);
 await reset();clicks=[];current=false;
 assert.equal(await vm.runInContext('attachVisibleMedia()',context),false);assert.deepEqual(clicks,[]);current=true;
 // Busy must survive any six-minute total deadline, but cancellation stops it.
 let reads=0;context.inspection=async()=>({loading:true,reason:'picker_loading',dialog_count:1,option_labels:[]});
 context.clockWait=async ms=>{now+=ms;reads++;};context.still=async()=>reads<1500;
 const cancelled=await vm.runInContext('waitForFlowStartFrameAsset({inspect:inspection,isCurrent:still,wait:clockWait,onProgress:async()=>{}})',context);
 assert.equal(cancelled.reason,'attachment_owner_changed');assert(reads*300>360000);
 reads=0;context.inspection=async()=>({loading:true,animation_active:true,activity:'animation',reason:'picker_loading'});
 const animated=await vm.runInContext('waitForFlowStartFrameAsset({inspect:inspection,isCurrent:still,wait:clockWait,onProgress:async()=>{}})',context);
 assert.equal(animated.reason,'attachment_owner_changed');assert(reads*300>360000,'animated loading has no total six-minute timeout');
 reads=0;context.inspection=async()=>({loading:true,animation_active:false,activity:'unchanged',image_state:'loading',reason:'picker_loading'});
 const stalled=await vm.runInContext('waitForFlowStartFrameAsset({inspect:inspection,isCurrent:still,wait:clockWait,onProgress:async()=>{}})',context);
 assert.equal(stalled.stalled,true);assert(stalled.idle_ms>=45000);
 // Just-before-press block from physicalClick must re-read the source and
 // readiness; it returns to lookup without dispatching a mouse event.
 const pressStart=source.indexOf("          if (point?.guard === 'start_frame')");
 const pressEnd=source.indexOf('          await chrome.debugger.sendCommand(debuggee, "Input.dispatchMouseEvent"',pressStart);
 const pressGuard=source.slice(pressStart,pressEnd);
 const press={point:{guard:'start_frame',kind:'asset',filename:'f.png',image_source:'old'},
   attachmentStillCurrent:async()=>true,findPoint:async()=>null};
 vm.createContext(press);
 const pressFn=`(async()=>{let clickPoint=point;${pressGuard}return true;})()`;
 assert.equal(await vm.runInContext(pressFn,press),false,'loading again before click');
 press.findPoint=async()=>({image_source:'new'});assert.equal(await vm.runInContext(pressFn,press),false,'virtual row source changed');
 press.findPoint=async()=>({image_source:'old'});assert.equal(await vm.runInContext(pressFn,press),true);
 // A wrong filename and a duplicate exact name never produce an asset click.
 await reset();await page.getByRole('button',{name:'เริ่ม',exact:true}).click();
 await page.evaluate(()=>{const el=document.querySelector('[role=option]');el.parentNode.append(el.cloneNode(true));});clicks=[];
 assert.equal(await vm.runInContext('attachVisibleMedia()',context),false);assert.deepEqual(clicks,[]);
 // Execute the actual per-sample owner guard, including authorized fresh repair
 // receipts from a different project. Preserve normal/unknown-send protection.
 const guardSource=source.slice(source.indexOf('      const attachmentStillCurrent = async () => {'),source.indexOf('      const attachVisibleMedia = async () => {'));
 const receiptStore='receipts',repairKey='repair',scope={jobId:'JOB',shotIndex:1,runId:'RUN'};
 const store={smartpostAutoFlow:{...scope},smartpostFlowReferenceFile:{...scope,filename:'image.png'}};
 const guardContext={URL,attachJobId:'JOB',attachShotIndex:1,attachRunId:'RUN',tabId:1,sender:{tab:{url:'https://flow.google.com/project/p1'}},
 FLOW_SUBMISSION_RECEIPTS_KEY:receiptStore,flowRepairKey:()=>repairKey,flowProjectId:url=>String(url||'').match(/project\/([^/?#]+)/)?.[1]||'',
 flowProgressOwnership:async()=>({active:true,ownerTabId:1,activeRunId:'RUN'}),
 referenceStore:{smartpostFlowReferenceFile:{filename:'image.png'}},
 chrome:{storage:{local:{get:async()=>store}},tabs:{get:async()=>({url:'https://flow.google.com/project/p1'})}}};
 vm.createContext(guardContext);vm.runInContext(guardSource,guardContext);
 const check=()=>vm.runInContext('attachmentStillCurrent()',guardContext);
 assert.equal(await check(),true);
 store[receiptStore]={'JOB:1:RUN':{...scope}};assert.equal(await check(),false);
 store.smartpostAutoFlow.repairRequestId='R1';store.smartpostFlowReferenceFile.repair_request_id='R1';
 store[repairKey]={fresh_project:true,request_id:'R1',job_id:'JOB',index:1,run_id:'RUN',owner_tab:1,project_path:'/project/p1',phase:'preparing'};
 assert.equal(await check(),true,'owned fresh repair can retain prior failed receipt');
 store[receiptStore]['JOB:1:RUN:repair:R1']={...scope};assert.equal(await check(),false,'never reattach after current repair Send');
 delete store[receiptStore]['JOB:1:RUN:repair:R1'];store[repairKey].phase='submitted';assert.equal(await check(),false);
 store[repairKey].phase='preparing';store.smartpostFlowPausedTabs={1:true};assert.equal(await check(),false);
 delete store.smartpostFlowPausedTabs;store.smartpostFlowReferenceFile.filename='other.png';assert.equal(await check(),false);
 console.log('ok');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
