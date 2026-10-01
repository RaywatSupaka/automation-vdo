const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const context={};vm.createContext(context);vm.runInContext(source.slice(source.indexOf('  function coverPromptForRequest('),source.indexOf('  async function collectCoverImage(')),context);
const legacy={title:'ชื่อคลิป',headline:'ข้อความกำหนดเอง',aspect_ratio:'9:16',single_image_only:true};
const before=context.coverPromptForRequest(legacy);assert(!before.includes(legacy.headline));
assert(context.coverPromptForRequest({...legacy,cover_prompt_version:2}).includes(legacy.headline));
assert.equal(context.coverPromptForRequest({...legacy,headline:'',cover_prompt_version:2}),context.coverPromptForRequest({...legacy,headline:''}));
(async()=>{const browser=await chromium.launch({headless:true});let checks=3;
 try{const page=await browser.newPage();let network=0;await page.route('**/*',r=>{network++;return r.abort();});
  await page.setContent('<body></body>');
  await page.addScriptTag({content:`const calls=[];window.setTimeout=fn=>{queueMicrotask(fn);return 0;};
   const libraryItem=()=>null,postAction=async(action,payload)=>{calls.push({action,payload});
    if(action==='get_cover_editor')return {editor:{item_id:'story:STORY-TEST',revision:'r',aspect_ratio:'9:16',images:[],settings:{headline:'',emphasis:'',theme:'bold',position:'top',alternatives:[]}}};
    if(action.startsWith('ai_cover'))return {request:{request_id:'fixture',phase:'needs_review'}};
    return {};};`});
  await page.addScriptTag({content:fs.readFileSync('web_ui/clip_cover.js','utf8')});await page.evaluate(()=>openClipCover('story:STORY-TEST'));
  for(const text of ['ก'.repeat(40),'ก'.repeat(41),'ก'.repeat(60),'😀'.repeat(40),'😀'.repeat(41),'กำ'.repeat(20),'']){
   const result=await page.evaluate(async text=>{
    const input=document.querySelector('[data-cover-headline]');input.value=text;input.dispatchEvent(new Event('input'));
    calls.length=0;await document.querySelector('[data-cover-ai]').onclick();
    return{calls:structuredClone(calls),status:document.querySelector('.cover-editor-status').textContent,count:document.querySelector('[data-cover-count]').textContent};
   },text);
   const count=Array.from(text).length,submitted=result.calls.find(c=>c.action==='ai_cover_regenerate');
   assert.equal(!!submitted,count<=40,`${count}: ${JSON.stringify(result)}`);
   if(submitted)assert.equal(submitted.payload.settings.headline,text);else assert.match(result.status,/AI.*40/);
   assert(result.count.includes(String(count)));checks++;
  }
  const local=await page.evaluate(async()=>{document.querySelector('[data-cover-headline]').value='😀'.repeat(60);calls.length=0;
   await document.querySelector('[data-cover-save]').onclick();return structuredClone(calls);});
  assert.equal(local[0].action,'save_library_cover');assert.equal(Array.from(local[0].payload.settings.headline).length,60);checks++;
  assert.equal(network,0);console.log(JSON.stringify({ok:true,checks,providerActions:0}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
