// Real browser DOM regression for ChatGPT's inline Create image label.
// Local fixture only: no provider page, send gesture, or user job.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const start = source.indexOf('  function composerText(');
const end = source.indexOf('  function explicitAnalysisRefusal(', start);
assert(start >= 0 && end > start);
const reader = source.slice(start, end);

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    const read = async markup => {
      await page.setContent(`<form><div id="prompt-textarea" contenteditable="true">${markup}</div></form>`);
      return page.evaluate(code => new Function('IS_GEMINI', `${code}\nreturn composerText(document.querySelector('#prompt-textarea'));`)(false), reader);
    };
    const inspect = async markup => {
      await page.setContent(`<form><div id="prompt-textarea" contenteditable="true">${markup}</div></form>`);
      await page.addScriptTag({path:'browser_extension/single_answer.js'});
      return page.evaluate(code => new Function('IS_GEMINI', `${code}\nconst editor=document.querySelector('#prompt-textarea');return {draft:composerText(editor),formatReady:SmartFlowSingleAnswer.has(composerText(editor,true))};`)(false), reader);
    };
    assert.equal(await read('<span contenteditable="false">สร้างรูปภาพ</span>'), '', 'inline tool alone is not a draft');
    assert.equal(await read('<span contenteditable="false">Create image</span>'), '', 'English inline tool');
    assert.equal(await read('<p><span contenteditable="false">สร้างรูปภาพ</span>first</p><p>second</p>'),
      'first second', 'paragraph boundaries stay separated');
    assert.equal(await read('<span contenteditable="false">สร้างรูปภาพ</span>สร้างรูปภาพ'),
      'สร้างรูปภาพ', 'editable words matching the tool remain a draft');
    assert.equal(await read('สร้างรูปภาพ'), 'สร้างรูปภาพ', 'unmarked user draft is protected');
    assert.equal(await read('<span contenteditable="false">other tool</span>'), 'other tool',
      'unrecognized noneditable content is not discarded');
    const suffix='[SmartFlow response format v1] Return exactly one final answer for this request. Do not offer alternative responses, numbered choices, or ask me to choose. Choose one suitable solution yourself. Keep the requested schema, all required scenes/items, facts, dialogue and audio settings unchanged. If JSON is requested, return one complete JSON value only. If an image or video is requested, create exactly one actual media result, not a description of a result. Report genuine failure or unavailability truthfully.';
    assert.deepEqual(await inspect(`<p>owned prompt</p><p>${suffix}</p><span contenteditable="false">สร้างรูปภาพ</span>`),
      {draft:'owned prompt',formatReady:true}, 'inline tool after suffix does not hide the transport rule');
    assert.deepEqual(await inspect(`<span contenteditable="false">Create image</span><p>owned prompt</p><p>${suffix}</p>`),
      {draft:'owned prompt',formatReady:true}, 'remounted tool before the draft leaves the suffix readable');
    assert.deepEqual(await inspect('<p>owned prompt</p><span contenteditable="false">สร้างรูปภาพ</span>'),
      {draft:'owned prompt',formatReady:false}, 'missing suffix still blocks Send');
    console.log(JSON.stringify({ok:true,cases:9,providerSubmissions:0}));
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error);process.exitCode=1;});
