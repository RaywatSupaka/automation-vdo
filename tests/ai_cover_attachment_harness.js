// Exercise the actual cover sourceFile + attachment path in isolated Chromium.
// Synthetic provider markup, not an installed-provider generation claim.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync(process.argv[3]||path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const section=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
const code=section('  async function sourceFile(', '  function aiWebFailureDiagnostic(');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage();
  let uploadedJPEG='';
  await page.route('**/*',r=>r.request().url().startsWith('https://chatgpt.com/backend-api/estuary/content?fixture=')
    ? r.fulfill({contentType:'image/jpeg',body:Buffer.from(uploadedJPEG.split(',')[1],'base64')}) : r.abort());
  const packet=process.argv[2]?JSON.parse(fs.readFileSync(process.argv[2],'utf8')):null;
  const cases=[
   {name:'chatgpt actual indexed filenames'},
   {name:'chatgpt hidden filenames',hidden:true},
   {name:'chatgpt input cleared but exact filenames',clear:true},
   {name:'chatgpt hidden progress',hiddenProgress:true},
   {name:'gemini actual indexed filenames',gemini:true},
   {name:'gemini hidden filenames',gemini:true,hidden:true},
   {name:'one saved source',count:1},
   {name:'only one of two loaded',missing:true,fail:true},
   {name:'second image still decoding',broken:true,fail:true},
   {name:'foreign file selection',foreign:true,fail:true},
   {name:'unknown cleared input with hidden names',clear:true,hidden:true,fail:true},
   {name:'visible progress',busy:true,fail:true},
   {name:'upload failure',failed:true,fail:true},
   {name:'user changed draft during upload',draft:true,fail:true},
   {name:'cancel during upload',cancel:true,fail:true},
   {name:'stale composer preview',stale:true,fail:true},
   {name:'extra image',extra:true,fail:true},
   {name:'preview keeps changing',unstable:true,fail:true},
   {name:'gemini missing second image',gemini:true,missing:true,fail:true},
   {name:'gemini second image still decoding',gemini:true,broken:true,fail:true},
   {name:'detached upload input',detached:true,fail:true},
   {name:'gemini detached input with named decoded references',gemini:true,detached:true},
   {name:'gemini remounted shell with named decoded references',gemini:true,remount:true},
   {name:'gemini remounted shell with unknown references',gemini:true,remount:true,hidden:true,fail:true},
   {name:'gemini detached input missing second reference',gemini:true,detached:true,missing:true,fail:true},
   {name:'gemini remounted shell user draft changed',gemini:true,remount:true,draft:true,fail:true},
   {name:'live339 semantic file groups, empty alt and HTTPS thumbnails',fileGroup:true,clear:true},
   {name:'file group with one source',fileGroup:true,clear:true,count:1},
   {name:'file group missing second source',fileGroup:true,clear:true,missing:true,fail:true},
   {name:'file group second source broken',fileGroup:true,clear:true,broken:true,fail:true},
   {name:'file group extra source',fileGroup:true,clear:true,extra:true,fail:true},
   {name:'stale file group must never reupload',fileGroup:true,stale:true,fail:true},
   {name:'filename tile fallback without role group',labelledTile:true,clear:true},
   {name:'unlabelled unrelated composer image',unlabelled:true,clear:true,fail:true},
   {name:'upload takes longer than 30 seconds',slow:true},
   {name:'stuck upload is bounded',busy:true,fail:true},
   {name:'reference removed during progress ACK cannot pass stale proof',reportMutation:true,fail:true},
  ];
  for(const options of cases){
   await page.setContent(`<style>img{width:60px;height:60px}button,[role=progressbar]{width:30px;height:30px}</style>
    <article><img alt="uploaded old image"></article><form class="text-input-field">
    <div id="refs"></div><div contenteditable="true" id="editor"></div>
    <button type="button" aria-label="เพิ่มไฟล์และอื่นๆ">+</button><input id="upload-files" type="file" multiple data-photo-upload-enabled="true">
    <span id="status"></span></form>`);
   uploadedJPEG=packet?.source_images?.[0] || await page.evaluate(()=>{const c=document.createElement('canvas');c.width=c.height=32;return c.toDataURL('image/jpeg');});
   const result=await page.evaluate(async({code,options,packet})=>{
    let now=0,cancelled=false,assignments=0,uploadStarted=0,mutated=false;const Date={now:()=>now};
    const IS_GEMINI=!!options.gemini,AI_NAME=IS_GEMINI?'Gemini Web':'ChatGPT Web';
    const composer=()=>document.querySelector('#editor'),composerText=()=>composer().textContent;
    const userTurns=()=>[],lastUserTurnSignature=()=>'';
    const visible=n=>!!n&&n.getBoundingClientRect().width>8&&getComputedStyle(n).display!=='none';
    const report=async stage=>{if(options.reportMutation&&!mutated&&stage==='cover_reference_wait'&&now-uploadStarted>=10000){
      refs.lastElementChild?.remove();mutated=true;}};
    const assertNotCancelled=()=>{if(cancelled)throw Error('cancelled');};
    const sleep=async ms=>{now+=ms;await new Promise(r=>setTimeout(r,1));
      if(options.slow&&now>35000)document.querySelector('[role="progressbar"]')?.remove();
      if(options.reportMutation&&assignments){await finished;
        if(now-uploadStarted>=9000)document.querySelector('[role="progressbar"]')?.remove();}
      if(options.unstable){const img=document.querySelector('#refs img');if(img)img.replaceWith(img.cloneNode(true));}};
    const canvas=document.createElement('canvas');canvas.width=canvas.height=32;
    const jpeg=canvas.toDataURL('image/jpeg');
    const source_images=(packet?.source_images || [jpeg,jpeg]).slice(0,options.count||2);
    const activeCoverRequest={...(packet||{}),request_id:'attachment-fixture',source_images,source_data:source_images[0]};
    const chrome={runtime:{sendMessage:()=>{throw Error('unexpected bridge URL fetch');}}};
    const input=document.querySelector('input'),refs=document.querySelector('#refs');
    const add=async(file,i)=>{
     const wrap=document.createElement('div');wrap.dataset.testid='attachment-preview';
     const img=document.createElement('img');img.alt=IS_GEMINI?'attachment':(options.hidden?'uploaded reference':file.name);
     img.src=URL.createObjectURL(file);wrap.append(img);
     const remove=document.createElement('button');remove.type='button';remove.setAttribute('aria-label','remove file');wrap.append(remove);
     if(!options.hidden)wrap.title=file.name;
     if(options.fileGroup||options.labelledTile||options.unlabelled){
       delete wrap.dataset.testid;wrap.removeAttribute('title');img.alt='';
       img.src=`https://chatgpt.com/backend-api/estuary/content?fixture=${i}`;
       const open=document.createElement('button');open.type='button';open.setAttribute('aria-haspopup','dialog');
       open.setAttribute('aria-label','เปิดรูปภาพ: ภาพที่อัปโหลดโดยผู้ใช้');open.append(img);wrap.prepend(open);
       remove.setAttribute('aria-label',`ลบไฟล์ ${i+1}: ${file.name}`);
       if(options.fileGroup){wrap.setAttribute('role','group');wrap.setAttribute('aria-label',file.name);}
       if(options.labelledTile)wrap.title=file.name;
       if(options.unlabelled)remove.setAttribute('aria-label','unrelated control');
     }
     if(options.broken&&i===1)img.src='data:image/jpeg;base64,WA==';
     refs.append(wrap);await img.decode().catch(()=>{});
    };
    if(options.stale)await add(new File([new Uint8Array([1])],'old.jpg'),0);
    let finished=Promise.resolve();
    input.addEventListener('change',()=>{
     assignments++;uploadStarted=now;const files=Array.from(input.files);
     if(options.reportMutation){const p=document.createElement('div');p.setAttribute('role','progressbar');refs.append(p);}
     finished=(async()=>{
      for(let i=0;i<files.length;i++)if(!(options.missing&&i===1))await add(files[i],i);
      if(options.extra)await add(files[0],2);
      if(options.clear)input.value='';
      if(options.foreign){const t=new DataTransfer();t.items.add(new File(['x'],'unrelated.jpg'));input.files=t.files;}
      if(options.busy||options.hiddenProgress||options.slow){const p=document.createElement('div');p.setAttribute('role','progressbar');
        if(options.hiddenProgress)p.style.display='none';refs.append(p);}
      if(options.failed)document.querySelector('#status').textContent='Upload failed';
      if(options.draft)composer().textContent='user draft';
      if(options.cancel)cancelled=true;
      if(options.detached)input.remove();
      if(options.remount){const shell=document.querySelector('form');shell.replaceWith(shell.cloneNode(true));}
     })();
    });
    const api=eval(code+';({attachSourceImages})');
    let error='';try{await api.attachSourceImages(source_images,0,'smartflow-cover-attachment-fixture.jpg');}catch(e){error=e.message;}
    await finished;
    return {error,assignments,now,mutated};
   },{code,options,packet});
   if(options.reportMutation)assert(result.mutated,options.name+' must reach the scheduled mutation');
   if(options.fail)assert(result.error,options.name+' must block');
   else assert.equal(result.error,'',options.name);
   assert.equal(result.assignments,options.stale?0:1,options.name+' never reattaches');
   assert(result.now<=121000,options.name+' bounded passive wait');
  }
  console.log(JSON.stringify({ok:true,cases:cases.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
