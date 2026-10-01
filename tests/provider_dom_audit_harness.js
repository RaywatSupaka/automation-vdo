// Live-observed ChatGPT composer controls, sanitized and offline. No account,
// provider request, paid generation or user Chrome profile is touched.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const section=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage();
  await page.route('**/*',route=>route.abort());
  await page.setContent(`<style>button,img,[role=progressbar]{width:30px;height:30px} [contenteditable]{min-height:50px}</style>
    <section><p role="alert">Upload failed in an old answer</p><img alt="uploaded old image"></section>
    <form data-type="unified-composer">
      <div data-testid="attachment-preview"><img alt="uploaded reference"><button aria-label="remove file">Remove</button></div>
      <div id="prompt-textarea" class="ProseMirror" role="textbox" contenteditable="true">A person says uploading and upload failed in this story.</div>
      <button type="button" data-testid="composer-plus-btn" aria-label="เพิ่มไฟล์และอื่นๆ">+</button>
      <button type="button" data-testid="send-button" aria-label="ส่งคำสั่ง">Send</button>
      <div role="progressbar" style="display:none"></div><span id="upload-status"></span>
      <input type="file" id="upload-files" data-photo-upload-enabled="true" multiple>
      <input type="file" id="upload-photos" data-testid="upload-photos-input" accept="image/*" multiple>
      <input type="file" id="upload-media" data-testid="upload-media-input" accept="image/*,video/*" multiple>
      <input type="file" id="upload-camera" accept="image/*" capture="environment">
      <input type="file" id="upload-media-files" accept="image/*,video/*" multiple>
    </form>`);
  const result=await page.evaluate(code=>{
    const IS_GEMINI=false;
    const visible=n=>!!n&&n.getBoundingClientRect().width>0&&getComputedStyle(n).display!=='none';
    const api=eval('"use strict";'+code+';({composer,sendButton,chatGPTComposerAttachmentState,preferredSourceFileInput})');
    const check=(condition,message)=>{if(!condition)throw Error(message);};
    let cases=0,state=api.chatGPTComposerAttachmentState();
    check(state.count===1,'One reference, not historical or nested controls');
    check(!state.busy&&!state.failed,'Prompt prose and old reply must not be upload status');cases++;
    check(api.composer().id==='prompt-textarea','Real composer');
    check(api.sendButton().getAttribute('aria-label')==='ส่งคำสั่ง','Real Thai Send parent');cases++;
    check(api.preferredSourceFileInput().id==='upload-files','Observed photo-enabled input');
    document.querySelector('#upload-files').remove();
    check(api.preferredSourceFileInput().id==='upload-photos','Image-specific fallback, not camera');cases++;
    const progress=document.querySelector('[role=progressbar]');progress.style.display='block';
    check(api.chatGPTComposerAttachmentState().busy,'Visible upload progress blocks');
    progress.style.display='none';check(!api.chatGPTComposerAttachmentState().busy,'Hidden progress does not block');cases++;
    document.querySelector('#upload-status').textContent='Upload failed';
    check(api.chatGPTComposerAttachmentState().failed,'Actual upload failure blocks');cases++;
    document.querySelector('#upload-status').textContent='';
    document.querySelector('[data-testid=attachment-preview]').remove();
    state=api.chatGPTComposerAttachmentState();check(state.count===0&&!state.busy&&!state.failed,'Removed current image, old history untouched');cases++;
    return {ok:true,cases};
  },section('  function composer(', '  function loginRequired(')
    +section('  function chatGPTComposerAttachmentState(', '  function sourceAttachmentPreviews(')
    +section('  function preferredSourceFileInput(', '  async function waitForChatGPTSourceAttachmentProof(')
    +section('  function isStopGenerationButton(', '  function stopButton(')
    +section('  function resolveChatGPTComposerSendTarget(', '  function sendButton(')
    +section('  function sendButton(', '  async function waitForStableSendDraft('));
  assert.deepEqual(result,{ok:true,cases:6});console.log(JSON.stringify(result));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
