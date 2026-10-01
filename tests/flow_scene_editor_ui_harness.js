const fs=require('fs'),assert=require('assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const source=fs.readFileSync('web_ui/studio.js','utf8');
 const markup=source.slice(source.indexOf('  function storyScenePromptMarkup'),source.indexOf('  function imageScenePromptMarkup'));
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  await page.route('**/*',route=>route.abort());
  await page.setContent('<main></main>');
  await page.addScriptTag({content:`const escapeHtml=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');function imageScenePromptMarkup(){return '';} ${markup} document.querySelector('main').innerHTML=storyScenePromptMarkup({index:2,flow_editable:true,flow_prompt:'Camera moves closer.',flow_model:'Veo 3.1 - Quality'});`});
  await page.locator('summary').click();
  assert.equal(await page.locator('option').count(),6);
  assert.equal(await page.locator('select').inputValue(),'Veo 3.1 - Quality');
  await page.locator('textarea').fill('Slow pan, 9:16.');
  await page.locator('select').selectOption('Veo 3.1 - Lite [Lower Priority]');
  assert.equal(await page.locator('textarea').inputValue(),'Slow pan, 9:16.');
  assert.equal(await page.locator('[data-save-flow]').getAttribute('data-save-flow'),'2');
  console.log(JSON.stringify({ok:true,models:5,scope:'actual markup, offline only'}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
