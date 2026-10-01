const fs=require('fs'),assert=require('assert/strict');
const {chromium}=require('playwright');
const read=p=>fs.readFileSync('browser_extension/'+p,'utf8');
const part=(source,a,b)=>{const i=source.indexOf(a),j=source.indexOf(b,i+a.length);assert(i>=0&&j>i);return source.slice(i,j);};
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();await page.setContent('<textarea id="editor"></textarea><main></main>');
  await page.addScriptTag({content:read('single_answer.js')});
  const content=read('chatgpt.js'),flow=read('flow.js');
  await page.addScriptTag({content:`let IS_GEMINI=false; const AI_NAME='Fixture AI',composer=()=>document.querySelector('#editor'),sleep=async()=>{},report=async()=>{};
    ${part(content,'function chatGPTConversationFrames(','function assistantTurns(')}
    ${part(content,'function composerText(','function explicitAnalysisRefusal(')}
    ${part(content,'async function setComposerText(','async function sourceFile(')}
    ${part(content,'function storyUserBody(','function chatGPTStoryRequest(')}
    ${part(content,'function motionRequestIsLatestUser(','function geminiTextRequestHash(')}
    const userTurns=()=>[...document.querySelectorAll('[data-message-author-role="user"]')];
    ${part(flow,'function flowPromptMatches(','function findPromptEditor(')}
    let pkg={video_prompt:'One smooth camera move. Dialogue: สวัสดี. Keep original audio.'};
    const findPromptEditor=composer;
    ${part(flow,'async function fillPrompt(','function findNewProjectButton(')}
    window.check=async()=>{
      const rule=SmartFlowSingleAnswer,prompt='Return JSON with all 14 scenes. Dialogue stays unchanged.';
      for(const provider of [false,true]){
        IS_GEMINI=provider;await setComposerText(composer(),prompt);
        if(composerText()!==prompt||!rule.has(composer().value))throw Error('wire/canonical mismatch');
        if(rule.wrap(composer().value)!==composer().value)throw Error('duplicate instruction');
      }
      composer().outerHTML='<div id="editor" contenteditable="true" style="width:600px;min-height:80px"></div>';
      for(const provider of [false,true]){
        IS_GEMINI=provider;await setComposerText(composer(),prompt);
        if(composerText()!==prompt||!rule.has(composer().innerText))throw Error('rich editor wire/canonical mismatch');
      }
      composer().outerHTML='<textarea id="editor"></textarea>';
      document.querySelector('main').innerHTML='<section><div data-message-author-role="user"><div class="whitespace-pre-wrap"></div></div></section>';
      const body=document.querySelector('.whitespace-pre-wrap');body.textContent=rule.wrap(prompt);
      if(storyUserBody(body.closest('section'))!==prompt||!motionRequestIsLatestUser(prompt))throw Error('owned response changed');
      body.textContent += ' unexpected change';
      if(storyUserBody(body.closest('section'))===prompt)throw Error('tampered body accepted');
      if(!await fillPrompt()||!rule.has(composer().value))throw Error('Flow wire missing');
      if(!flowPromptMatches(composer().value,pkg.video_prompt)||!flowPromptMatches(pkg.video_prompt,pkg.video_prompt))throw Error('Flow legacy/wire mismatch');
      if(flowPromptMatches(composer().value+' unexpected',pkg.video_prompt))throw Error('Flow changed draft accepted');
      if(rule.wrap('')!=='')throw Error('empty prompt populated');
      return true;
    };`});
  assert.equal(await page.evaluate(()=>window.check()),true);
  const manifest=JSON.parse(read('manifest.json'));
  for(const entry of manifest.content_scripts.filter(e=>e.js.some(f=>['chatgpt.js','flow.js'].includes(f))))
    assert.equal(entry.js[0],'single_answer.js');
  const bg=read('background.js');
  for(const match of bg.matchAll(/files:\s*\[([^\]]*(?:chatgpt|flow)\.js[^\]]*)\]/g)) assert(match[1].includes('single_answer.js'));
  assert(read('src/background/service-worker.js').includes('import "../../single_answer.js"'));
  console.log('Single-answer transport, exact ownership, and all injection paths passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
