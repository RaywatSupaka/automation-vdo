// Isolated actual-source UI checks. No desktop bridge, provider tabs or POSTs.
const fs=require('node:fs');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');

(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const app=fs.readFileSync('web_ui/app.js','utf8');
    const banner=await browser.newPage();
    await banner.setContent('<section id="workspace-issues" hidden><strong id="workspace-issues-summary"></strong><div id="workspace-issue-list"></div></section>');
    await banner.addScriptTag({content:`const $=s=>document.querySelector(s);const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const calls=[];const postAction=async(a,p)=>{calls.push({a,p})};const toast=()=>{};`});
    const displayStart=app.indexOf('function renderWorkspaceIssues('),displayEnd=app.indexOf('\nfunction videoSourcePresentation(',displayStart);
    assert(displayStart>=0&&displayEnd>displayStart);
    await banner.addScriptTag({content:app.slice(displayStart,displayEnd)});
    await banner.evaluate(()=>renderWorkspaceIssues({count:1,items:[{kind:'story',label:'เรื่องเล่า',id:'STORY-BROKEN',reason:'อ่านไฟล์ไม่ได้'}]}));
    assert.equal(await banner.locator('#workspace-issues').isVisible(),true);
    assert.match(await banner.locator('#workspace-issues').innerText(),/STORY-BROKEN/);
    await banner.locator('#workspace-issue-list button').click();
    assert.deepEqual(await banner.evaluate(()=>calls[0]),{a:'open_workspace_issue_folder',p:{kind:'story',id:'STORY-BROKEN'}});
    await banner.evaluate(()=>renderWorkspaceIssues({count:0,items:[]}));
    assert.equal(await banner.locator('#workspace-issues').isVisible(),false);

    const review=await browser.newPage();
    await review.setContent('<form id="creation-form"><select id="creation-product-video-provider"><option value="flow">Google Flow</option><option value="meta_ai">Meta AI</option></select><select id="creation-product-provider"><option>ChatGPT Web</option></select><select id="creation-product-scenes"><option value="3">3 ฉาก</option></select><div class="cq-buttons"><button id="creation-editor-submit">เพิ่มคิว</button></div></form>');
    await review.addScriptTag({content:`window.mediaAudioChoice=()=>({mode:'none',subtitle:false,music:false,sfx:false});`});
    await review.addScriptTag({content:fs.readFileSync('web_ui/creator_ux.js','utf8')});
    assert.match(await review.locator('.creator-review').innerText(),/Google Flow/);
    await review.evaluate(()=>{const s=document.querySelector('#creation-product-video-provider');s.value='meta_ai';s.dispatchEvent(new Event('change',{bubbles:true}));});
    assert.match(await review.locator('.creator-review').innerText(),/Meta AI/);

    const queue=await browser.newPage();
    await queue.setContent('<button id="queue-add-stories">เพิ่มจากคิว</button><button id="open-story-batch">เพิ่มจากเรื่องเดี่ยว</button><input id="story-topic" value="เรื่องเดี่ยว"><textarea id="story-text"></textarea><select id="story-provider"><option value="chatgpt">ChatGPT</option></select><select id="story-video-mode"><option value="image_motion">Local</option></select><select id="story-visual-style"><option value="auto">Auto</option></select><input id="story-visual-style-custom"><select id="story-scenes"><option value="10">10</option></select><dialog id="story-batch-modal"><textarea id="story-batch-topics">ร่างในคิว</textarea><textarea id="story-batch-direction"></textarea><select id="story-batch-provider"><option value="gemini">Gemini</option><option value="chatgpt">ChatGPT</option></select><select id="story-batch-video-mode"><option value="meta_ai">Meta</option><option value="image_motion">Local</option></select><select id="story-batch-visual-style"><option value="auto">Auto</option></select><input id="story-batch-visual-style-custom"><select id="story-batch-scenes"><option value="8">8</option><option value="10">10</option></select><input id="story-batch-image-path"><span id="story-batch-image-name"></span></dialog>');
    await queue.addScriptTag({content:`const $=s=>document.querySelector(s);const ui={storyBatchDirty:false,storyBatchImage:'',storyImage:''};let audioCopies=0;window.preparePresenterQueue=()=>{};window.prepareStoryAudioBatch=()=>{audioCopies++};const updateStoryBatchDialog=()=>{};const fillAiModelSelect=()=>{};const selectedAiModel=()=>'';`});
    const queueSource=fs.readFileSync('web_ui/creation_queue.js','utf8');
    const queueStart=queueSource.indexOf("$('#queue-add-stories').addEventListener"),queueEnd=queueSource.indexOf("\n  $('#creation-editor-close')",queueStart);
    assert(queueStart>=0&&queueEnd>queueStart);
    await queue.addScriptTag({content:app.slice(app.indexOf("for (const type of ['input','change']) $('#story-batch-modal')"),app.indexOf("$('#story-batch-topics').addEventListener",app.indexOf("for (const type of ['input','change']) $('#story-batch-modal')")))});
    await queue.addScriptTag({content:queueSource.slice(queueStart,queueEnd)});
    await queue.locator('#queue-add-stories').click();
    assert.equal(await queue.locator('#story-batch-topics').inputValue(),'ร่างในคิว');
    assert.equal(await queue.locator('#story-batch-provider').inputValue(),'gemini');
    assert.equal(await queue.locator('#story-batch-video-mode').inputValue(),'meta_ai');
    assert.equal(await queue.evaluate(()=>audioCopies),0);
    console.log('PASS workspace warning, actual provider summary, queue Story draft preservation');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
