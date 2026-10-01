const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const front=fs.readFileSync('browser_extension/chatgpt.js','utf8'),back=fs.readFileSync('browser_extension/background.js','utf8');
const url='https://lh3.googleusercontent.com/owned-image',dataUrl='data:image/png;base64,'+'A'.repeat(600);
const pick=(src,start,end)=>src.slice(src.indexOf(start),src.indexOf(end,src.indexOf(start)));
(async()=>{
 let calls=[];
 const c=vm.createContext({IS_GEMINI:true,PROVIDER_KEY:'gemini',AI_NAME:'Gemini',activeJobId:'STORY-X',activeRunId:'R',assertNotCancelled:()=>{},
 chrome:{runtime:{sendMessage:async m=>{calls.push(m);return m.type==='GET_CHATGPT_GENERATED_IMAGE'?{ok:false,error:'HTTP 403'}:{ok:true,dataUrl};}}}});
 vm.runInContext(pick(front,'  function imageDownloadFailure(','  async function generateOneImage('),c);
 assert.equal(await c.imageDataFromUrl(url),dataUrl);assert.equal(calls.length,2);assert.equal(calls[1].run_id,'R');
 c.IS_GEMINI=false;calls=[];await assert.rejects(c.imageDataFromUrl(url),/403/);assert.equal(calls.length,1);
 c.IS_GEMINI=true;calls=[];await assert.rejects(c.imageDataFromUrl('https://unrelated.example/image'),/403/);assert.equal(calls.length,1);
 c.assertNotCancelled=()=>{throw new Error('cancelled');};calls=[];await assert.rejects(c.imageDataFromUrl(url),/cancelled/);assert.equal(calls.length,1);
 const image={src:url,complete:true,naturalWidth:1024,naturalHeight:1536};let fetches=0;
 const page=vm.createContext({document:{querySelectorAll:()=>[image],createElement:()=>({getContext:()=>({drawImage:()=>{}}),toDataURL:()=>dataUrl})},fetch:async()=>{fetches++;throw Error('should not fetch');}});
 vm.runInContext(pick(back,'async function readRenderedGeminiImage(','const storyRepairLocks'),page);
 assert.equal((await page.readRenderedGeminiImage(url)).method,'loaded_image');assert.equal(fetches,0);
 await assert.rejects(page.readRenderedGeminiImage(url+'other'),/Exact/);
 image.complete=false;await assert.rejects(page.readRenderedGeminiImage(url),/Exact/);image.complete=true;
 page.document.createElement=()=>({getContext:()=>({drawImage:()=>{throw Error('tainted');}})});
 Object.assign(page,{AbortController,setTimeout,clearTimeout,FileReader:class {readAsDataURL(){this.result=dataUrl;this.onload();}},fetch:async()=>({ok:true,blob:async()=>({type:'image/png',size:600})})});
 assert.equal((await page.readRenderedGeminiImage(url)).method,'page_fetch');
 page.fetch=async()=>({ok:true,blob:async()=>({type:'text/html',size:600})});await assert.rejects(page.readRenderedGeminiImage(url),/valid image/);
 assert(!c.imageDownloadFailure(Error('failed https://example.com/?token=secret')).includes('secret'));
 console.log(JSON.stringify({ok:true,cases:10}));
})().catch(e=>{console.error(e);process.exitCode=1;});
