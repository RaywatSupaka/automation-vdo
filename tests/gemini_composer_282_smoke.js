const fs=require('fs'),assert=require('assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage();
  await page.setContent('<div class="old-reply"><img alt="uploaded" width="80" height="80"></div><div class="text-input-field"><div class="preview"><img alt="attachment" width="80" height="80"></div><div><div><div><rich-textarea><div class="ql-editor"></div></rich-textarea></div></div></div></div>');
  const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
  const from=source.indexOf('    const referenceShell =',source.indexOf('async function attachSourceImages'));
  const code=source.slice(from,source.indexOf('    if (strictReference',from));
  const result=await page.evaluate(code=>{
   const composer=()=>document.querySelector('.ql-editor'),IS_GEMINI=true;
   const visible=n=>!!n.getBoundingClientRect().width;
   const sourceAttachmentPreviews=()=>Array.from(document.querySelectorAll('img'));
   return eval(code+';({count:localPreviews().length,alt:localPreviews()[0]?.alt,oldScope:composer().parentElement.parentElement.querySelectorAll("img").length})');
  },code);
  assert.deepEqual(result,{count:1,alt:'attachment',oldScope:0});
  console.log('Actual selector integration passed: finds composer attachment, excludes old reply');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
