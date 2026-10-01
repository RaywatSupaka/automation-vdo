// Isolated Chromium; no requests reach Gemini and no provider Send occurs.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync(process.argv[2]||path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const section=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage();
  await page.route('**/*',r=>r.fulfill({contentType:'text/html',body:'<div class="text-input-field"></div>'}));
  await page.goto('https://gemini.google.com/app');
  const result=await page.evaluate(async code=>{
   let tick=0,live;
   const Date={now:()=>tick},sleep=async ms=>{tick+=ms;};
   const assertNotCancelled=()=>{},geminiTextSendReview=m=>Error(m);
   const geminiTextSendState=()=>live;
   const api=eval(code+';({geminiTextAttachmentIdentity,waitGeminiTextPreSend,geminiTextSendChanges})');
   const shell=document.querySelector('.text-input-field');
   const make=async(color,width=32)=>{
    const c=document.createElement('canvas');c.width=width;c.height=32;
    c.getContext('2d').fillStyle=color;c.getContext('2d').fillRect(0,0,c.width,c.height);
    const blob=await new Promise(resolve=>c.toBlob(resolve));
    const i=document.createElement('img');i.alt='attachment';i.src=URL.createObjectURL(blob);await i.decode();return i;
   };
   for(const color of ['red','green','blue'])shell.append(await make(color));
   const state=()=>({job:'J',run:'R',url:location.href,prompt:'same draft',ready:true,busy:false,stopped:false,expanded:false,
    sourceSignature:JSON.stringify([...shell.querySelectorAll('img')].map(api.geminiTextAttachmentIdentity)),
    sourceTransportSignature:JSON.stringify([...shell.querySelectorAll('img')].map(i=>i.src))});
   const initial=state();let cases=0;
   const check=(ok,label)=>{if(!ok)throw Error(label);cases++;};
   const old=Array.from(shell.children);
   for(let i=0;i<3;i++)old[i].replaceWith(await make(['red','green','blue'][i]));
   live=state();
   check(initial.sourceTransportSignature!==live.sourceTransportSignature,'different blob URLs required');
   check(initial.sourceSignature===live.sourceSignature,'same decoded images must retain identity');
   await api.waitGeminiTextPreSend(initial,'same draft');cases++;
   check(api.geminiTextSendChanges(initial,live).length===0,'post-claim watch accepts identical decoded image');
   const loaded=state();
   await api.waitGeminiTextPreSend({...loaded,busy:true,sourceSignature:'pending decode'},'same draft');cases++;
   shell.children[1].replaceWith(await make('yellow'));
   live=state();
   check(api.geminiTextSendChanges(initial,live).includes('sourceSignature'),'actual replacement must block');
   try {await api.waitGeminiTextPreSend(initial,'same draft');throw Error('accepted wrong image');}
   catch(e){check(e.notDispatched===true,'replacement rejected before dispatch');}
   shell.children[1].replaceWith(await make('green'));
   shell.append(shell.firstElementChild);live=state();
   check(api.geminiTextSendChanges(initial,live).includes('sourceSignature'),'reordered references must block');
   shell.firstElementChild.remove();live=state();
   check(api.geminiTextSendChanges(initial,live).includes('sourceSignature'),'removed reference must block');
   const unreadable={src:'blob:https://gemini.google.com/unreadable',complete:true,naturalWidth:32,naturalHeight:32};
   check(api.geminiTextAttachmentIdentity(unreadable)==='url:'+unreadable.src,'unreadable image keeps strict URL');
   check(initial.sourceSignature.length<250,'no raw pixels persisted in signature');
   const large=await make('red',800),canvas=document.createElement('canvas');
   canvas.width=800;canvas.height=32;canvas.getContext('2d').drawImage(large,0,0);
   canvas.getContext('2d').clearRect(799,31,1,1);
   const changed=document.createElement('img');changed.src=URL.createObjectURL(await new Promise(r=>canvas.toBlob(r)));await changed.decode();
   check(api.geminiTextAttachmentIdentity(large)!==api.geminiTextAttachmentIdentity(changed),'last pixel change must be detected, not downsampled');
   return {ok:true,cases};
  },section('  function geminiTextAttachmentIdentity(', '  function geminiTextSendState(')+section('  function geminiTextSendChanges(', '  function geminiSendWatch(')+section('  async function waitGeminiTextPreSend(', '  async function sendGeminiTextAndVerify('));
  assert.deepEqual(result,{ok:true,cases:12});console.log(JSON.stringify(result));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
