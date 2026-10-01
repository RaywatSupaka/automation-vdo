// DOM structure read from Gemini A9F010: five old uploads, one current
// alt=attachment outside rich-textarea, and the arrow_upward Send button.
const assert=require('node:assert/strict'), fs=require('node:fs');
const {chromium}=require('playwright');
const source=fs.readFileSync(require('node:path').join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const html=`<main>
  ${Array.from({length:5},(_,i)=>`<user-query>old question ${i}<img class="preview-image" alt="ตัวอย่างรูปภาพที่อัปโหลด" src="https://example.invalid/old-${i}"></user-query><model-response><message-content>old answer ${i}</message-content></model-response>`).join('')}
  <model-response id="latest"><message-content>{"index":5,"prompt":"saved"}</message-content><button id="toolbar">Copy</button></model-response>
  <div class="text-input-field"><img alt="attachment" src="https://example.invalid/current">
    <div class="textarea-wrapper"><rich-textarea><div class="ql-editor" contenteditable="true">Scene 6 prompt mentions uploading as ordinary text.</div></rich-textarea></div>
    <button aria-label="ส่งข้อความ"><mat-icon data-mat-icon-name="arrow_upward" fonticon="arrow_upward"></mat-icon></button>
  </div></main>`;
(async()=>{
const browser=await chromium.launch({headless:true});
try {
const page=await browser.newPage();
await page.route('**/*',route=>route.abort());
await page.setContent(html);
const result=await page.evaluate(({code,buttonCode})=>{
const d=document, current=d.querySelector('img[alt="attachment"]');
Object.defineProperties(current,{complete:{value:true,configurable:true},naturalWidth:{value:572,configurable:true}});
const IS_GEMINI=true,activeJobId='STORY-X',activeRunId='RUN-X';
const composer=()=>d.querySelector('.ql-editor'),composerText=n=>n.textContent;
const sendButton=eval('"use strict";'+buttonCode+';sendButton'),stopButtonVisible=()=>false;
const userTurns=()=>[...d.querySelectorAll('user-query')],lastUserTurnSignature=()=>userTurns().at(-1)?.textContent||'old';
const assistantTurns=()=>[...d.querySelectorAll('model-response')];
const generatedImageElements=scope=>[...scope.querySelectorAll('img')];
const sourceAttachmentPreviews=()=>[...d.querySelectorAll('img[alt*="อัปโหลด"]')];
const visible=n=>!!n&&!n.hidden;
const c=eval(code+';({geminiImageSendState,geminiTextSendState,geminiComposerAttachmentState,geminiImageSendUnchanged,geminiTextSendChanges})');
const assert=Object.assign(value=>{if(!value)throw Error('Expected truthy');},{equal:(actual,expected)=>{if(actual!==expected)throw Error(`Expected ${expected}, got ${actual}`);}});
let cases=0;
const old=c.geminiImageSendState(), before=c.geminiTextSendState();
assert.equal(JSON.parse(old.sourceSignature).length,1);
assert.equal(JSON.parse(before.sourceSignature).length,1);
assert.equal(c.geminiComposerAttachmentState().count,1);
assert.equal(before.busy,false);cases++;
assert.equal(sendButton().querySelector('mat-icon').getAttribute('fonticon'),'arrow_upward');
d.querySelector('img.preview-image').src='https://example.invalid/lazy-loaded-history';
d.querySelector('#toolbar').textContent='Copied!';
assert.equal(c.geminiImageSendUnchanged(old,c.geminiImageSendState()),false);
assert.equal(c.geminiImageSendUnchanged(before,c.geminiTextSendState()),true);cases++;
current.src='https://example.invalid/changed-current';
assert(c.geminiTextSendChanges(before,c.geminiTextSendState()).includes('sourceSignature'));cases++;
Object.defineProperty(current,'naturalWidth',{value:0,configurable:true});
assert(c.geminiTextSendChanges(before,c.geminiTextSendState()).includes('upload_busy'));cases++;
Object.defineProperty(current,'naturalWidth',{value:572,configurable:true});
const status=d.createElement('span');status.setAttribute('role','status');status.textContent='Uploading';
d.querySelector('.text-input-field').append(status);
assert.equal(c.geminiComposerAttachmentState().busy,true);
status.textContent='Upload failed';assert.equal(c.geminiTextSendState().ready,false);cases++;
status.remove();current.remove();assert.equal(c.geminiComposerAttachmentState().count,0);
assert(c.geminiTextSendChanges(before,c.geminiTextSendState()).includes('sourceSignature'));cases++;
return {ok:true,cases};
},{code:source.slice(source.indexOf('  function geminiImageSendState('),source.indexOf('  async function geminiTextSendKey(')),
   buttonCode:source.slice(source.indexOf('  function isStopGenerationButton('),source.indexOf('  function stopButton('))
     +source.slice(source.indexOf('  function sendButton('),source.indexOf('  async function waitForStableSendDraft('))});
assert.deepEqual(result,{ok:true,cases:6});
console.log(JSON.stringify(result));
} finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
