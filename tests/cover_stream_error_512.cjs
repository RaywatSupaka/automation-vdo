const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const part=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)+a.length));
const production=part('  function visible(', '  const dismissedDiscoveryCards')+
  part('  function chatGPTConversationFrames(', '  async function revealChatGPTAnswer(')+
  part('  function motionRequestIsLatestUser(', '  function geminiTextRequestHash(')+
  part('  function analysisResponseStopButton(', '  function analysisStopLabel(')+
  part('  function confirmedStoryImageServiceError(', '  function storyImageNoResultReady(')+
  part('  function generatedImageElements(', '  function generatedImageUrls(')+
  part('  function coverResultScope(', '  function coverDraftSnapshot(')+
  part('  function coverPromptForRequest(', '  async function runAICover(');

(async()=>{
  const browser=await chromium.launch({headless:true});let checks=0;
  try{
    for(const variant of ['owned','collect_owner_changed_after_claim','foreign_prompt','newer_user','duplicate_retry','quota','busy','missing_button']){
      const page=await browser.newPage();
      await page.setContent('<main></main><form><div id="prompt-textarea" contenteditable="true"></div></form>');
      await page.addScriptTag({content:`
        const IS_GEMINI=false,Node=window.Node;
        let now=1000;Date.now=()=>now;const sleep=async ms=>{now+=ms;};
        const assertNotCancelled=()=>{},events=[];
        const composer=()=>document.querySelector('#prompt-textarea'),composerText=()=>'';
        const coverEvent=async event=>{
          events.push(structuredClone(event));
          if(event.retry_count===1 && window.testVariant==='collect_owner_changed_after_claim')
            document.querySelector('.whitespace-pre-wrap').textContent='Different owner';
          return {...request,...event};
        };
        ${production}
        const request={request_id:'a'.repeat(32),title:'Fixture',source_images:['data:image/jpeg;base64,AA=='],
          collect_only:true,send_state:'accepted',retry_count:0,
          reference_proof:{status:'verified',expected:1,loaded:1,method:'filename',reason:'ready'}};
        coverConversationURL=()=> 'https://chatgpt.com/c/fixture';
        const prompt=coverPromptForRequest(request);
        const main=document.querySelector('main');
        const user=document.createElement('section');user.dataset.chatgptSearchUnitKey='owned:0:user';
        user.dataset.chatgptSearchMessageIds='owned-id';
        user.innerHTML='<div data-user-message-bubble="true"><div class="whitespace-pre-wrap"></div></div>';
        user.querySelector('.whitespace-pre-wrap').textContent=prompt;main.append(user);
        const error=document.createElement('div');error.setAttribute('role','alert');
        error.innerHTML='<span>เกิดข้อผิดพลาดในสตรีมของข้อความ</span><button type="button">ลองใหม่</button>';
        main.append(error);error.querySelector('button').addEventListener('click',()=>window.retryClicks++);
        window.retryClicks=0;
      `});
      await page.evaluate(variant=>{
        window.testVariant=variant;
        if(variant==='foreign_prompt')document.querySelector('.whitespace-pre-wrap').textContent='Another request';
        if(variant==='newer_user'){
          const extra=document.querySelector('[data-chatgpt-search-unit-key]').cloneNode(true);
          extra.dataset.chatgptSearchUnitKey='new:0:user';extra.dataset.chatgptSearchMessageIds='new-id';
          extra.querySelector('.whitespace-pre-wrap').textContent='Newer request';document.querySelector('main').append(extra);
        }
        if(variant==='duplicate_retry')document.querySelector('[role=alert]').after(document.querySelector('[role=alert]').cloneNode(true));
        if(variant==='quota')document.querySelector('[role=alert] span').textContent='คุณถึงขีดจำกัดการสร้างภาพแล้ว';
        if(variant==='busy')document.querySelector('main').insertAdjacentHTML('beforeend','<button data-testid="stop-button">หยุด</button>');
        if(variant==='missing_button')document.querySelector('[role=alert] button').remove();
      },variant);
      const result=await page.evaluate(async()=>{
        const found=coverNativeStreamErrorSnapshot(request,prompt);
        if(!found)return {found:false,clicks:retryClicks};
        let error='';try{await collectCoverImage(request,0);}catch(caught){error=caught.message;}
        return {found:true,error,clicks:retryClicks,stages:events.map(e=>e.collector_state?.stage).filter(Boolean),
          retryBudget:events.filter(e=>e.retry_count===1).length,
          proofOwned:coverRecoveryOwnsReferences(request),claim:request.native_retry_claim};
      });
      assert.equal(result.found,['owned','collect_owner_changed_after_claim'].includes(variant),variant+': '+JSON.stringify(result));
      if(variant==='owned'){
        assert.match(result.error,/สตรีมของปกเดิม/);
        assert.equal(result.clicks,1);
        assert.equal(result.retryBudget,1);
        assert.equal(result.proofOwned,true);
        assert.equal(result.claim?.reason,'native_stream_error');
      }
      if(variant==='collect_owner_changed_after_claim'){
        assert.match(result.error,/คำตอบเปลี่ยนก่อนกดลองอีกครั้ง/);
        assert.equal(result.clicks,0);
        assert.equal(result.retryBudget,1);
      }
      checks++;await page.close();
    }
    for(const variant of ['native_retry','owner_changed_after_claim']){
      const page=await browser.newPage();
      page.on('pageerror',error=>console.error('fixture page error:',error.message));
      await page.setContent('<main></main><form><div id="prompt-textarea" contenteditable="true"></div></form>');
      await page.addScriptTag({content:`
        const IS_GEMINI=false,Node=window.Node;
        let now=1000;Date.now=()=>now;const sleep=async ms=>{now+=ms;};
        const assertNotCancelled=()=>{};window.events=[];window.providerSends=0;window.retryClicks=0;
        const composer=()=>document.querySelector('#prompt-textarea'),composerText=()=>'';
        const waitForResponseIdle=async()=>{},prepareCoverImageTool=async()=>{},waitForComposer=async()=>composer();
        const setChatGPTImageTool=async()=>{};
        const attachSourceImages=async()=>{},setComposerText=async()=>composer();
        const waitForStableSendDraft=async()=>({button:null,editor:composer()});
        const coverEvent=async event=>{
          window.events.push(structuredClone(event));
          if(event.retry_count===1 && window.testVariant==='owner_changed_after_claim')
            document.querySelector('.whitespace-pre-wrap').textContent='Different owner';
          return {...request,...event};
        };
        ${production}
        const request={request_id:'a'.repeat(32),title:'Fixture',source_images:['data:image/jpeg;base64,AA=='],retry_count:0};
        coverConversationURL=()=> 'https://chatgpt.com/c/fixture';
        const sendCoverAndVerify=async()=>{
          window.providerSends++;
          const user=document.createElement('section');user.dataset.chatgptSearchUnitKey='owned:0:user';
          user.dataset.chatgptSearchMessageIds='owned-id';
          user.innerHTML='<div data-user-message-bubble="true"><div class="whitespace-pre-wrap"></div></div>';
          user.querySelector('.whitespace-pre-wrap').textContent=coverPromptForRequest(request);
          document.querySelector('main').append(user);
          const error=document.createElement('div');error.setAttribute('role','alert');
          error.innerHTML='<span>เกิดข้อผิดพลาดในสตรีมของข้อความ</span><button type="button">ลองใหม่</button>';
          error.querySelector('button').addEventListener('click',()=>window.retryClicks++);
          document.querySelector('main').append(error);
        };
      `});
      await page.evaluate(value=>{window.testVariant=value;},variant);
      const result=await page.evaluate(async()=>{
        let error='';try{await collectCoverImage(request,0);}catch(caught){error=caught.message;}
        return {error,providerSends:window.providerSends,retryClicks:window.retryClicks,retryBudget:window.events.filter(e=>e.retry_count===1).length,
          retryStage:window.events.find(e=>e.collector_state?.stage==='stream_error_retry')?.collector_state.stage};
      });
      assert.match(result.error,variant==='native_retry'?/สตรีมของปกเดิม/:/คำตอบเปลี่ยนก่อนกดลองอีกครั้ง/);
      assert.equal(result.providerSends,1);
      assert.equal(result.retryClicks,variant==='native_retry'?1:0);
      assert.equal(result.retryBudget,1);
      assert.equal(result.retryStage,'stream_error_retry');
      checks++;await page.close();
    }
    for(const variant of ['claimed_result','wrong_claim_owner']){
      const page=await browser.newPage();
      await page.setContent('<main></main><form><div id="prompt-textarea" contenteditable="true"></div></form>');
      await page.addScriptTag({content:`
        const IS_GEMINI=false,Node=window.Node;
        let now=1000;Date.now=()=>now;const sleep=async ms=>{now+=ms;};
        const assertNotCancelled=()=>{},events=[];
        const composer=()=>document.querySelector('#prompt-textarea'),composerText=()=>'';
        const coverEvent=async event=>{events.push(structuredClone(event));return {...request,...event};};
        ${production}
        const request={request_id:'a'.repeat(32),title:'Fixture',source_images:['data:image/jpeg;base64,AA=='],
          collect_only:true,send_state:'accepted',retry_count:1,
          reference_proof:{status:'verified',expected:1,loaded:1,method:'filename',reason:'ready'},
          native_retry_claim:{version:1,request_id:'a'.repeat(32),conversation_url:'https://chatgpt.com/c/fixture',
            user_id:'owned-id',reason:'native_stream_error'}};
        coverConversationURL=()=> 'https://chatgpt.com/c/fixture';
        const user=document.createElement('section');user.dataset.chatgptSearchUnitKey='owned:0:user';
        user.dataset.chatgptSearchMessageIds='owned-id';
        user.innerHTML='<div data-user-message-bubble="true"><div class="whitespace-pre-wrap"></div></div>';
        user.querySelector('.whitespace-pre-wrap').textContent=coverPromptForRequest(request);
        document.querySelector('main').append(user);
        const heading=document.createElement('h4');heading.dataset.conversationRole='assistant';
        document.querySelector('main').append(heading);
        const answer=document.createElement('section');answer.dataset.chatgptSearchUnitKey='owned:1:assistant';
        answer.dataset.chatgptSearchMessageIds='answer-id';answer.dataset.turn='assistant';
        answer.innerHTML='<div data-testid="generated-image-gallery"><button data-testid="generated-image-preview"><img data-asset="recovered" alt="รูปภาพที่สร้าง 1" width="941" height="1672" src="blob:https://chatgpt.com/11111111-1111-1111-1111-111111111111"></button></div>';
        document.querySelector('main').append(answer);
        Object.defineProperties(answer.querySelector('img'),{complete:{value:true},naturalWidth:{value:941},naturalHeight:{value:1672}});
      `});
      if(variant==='wrong_claim_owner')await page.evaluate(()=>{request.native_retry_claim.user_id='foreign-id';});
      const result=await page.evaluate(async()=>{
        try{const image=await collectCoverImage(request,0);return {ok:true,asset:image.dataset.asset};}
        catch(error){return {ok:false,message:error.message};}
      });
      assert.equal(result.ok,variant==='claimed_result',variant+': '+JSON.stringify(result));
      if(result.ok)assert.equal(result.asset,'recovered');
      checks++;await page.close();
    }
    console.log(JSON.stringify({ok:true,checks,providerSendsPerFreshRequest:1,maxNativeRetries:1}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
