const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1024,height:800}});await page.route('**/*',r=>r.abort());
  const root=path.join(__dirname,'../web_ui');
  const html=fs.readFileSync(path.join(root,'index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
  await page.setContent(html);
  for(const match of html.matchAll(/href="\/desktop\/([^"?]+\.css)(?:\?[^" ]*)?"/g))
    await page.addStyleTag({content:fs.readFileSync(path.join(root,match[1]),'utf8')});
  await page.evaluate(()=>document.querySelectorAll('.page').forEach(n=>n.classList.remove('active')));
  await page.addScriptTag({content:`const pageMeta={},ui={activePage:'intro'};let calls=[];
    const file='assets/intro/'+('a'.repeat(64))+'.mp4';
    const state={settings:{enabled:false,file:''},assets:[{file,name:'ตัวอย่างอินโทร.mp4',duration:2}]};
    function showPage(p){ui.activePage=p;}window.smartflowCreationFormKey=(a,p)=>({create_story:'story',enqueue_story_batch:'story-batch',create_drama_series:'drama',enqueue_long_video:'long',creation_enqueue:'story'}[a]||'');
    let postAction=async(action,payload)=>{calls.push({action,payload});if(action==='intro_status')return{ok:true,...state};
      if(action==='intro_choose_file')throw Error('Must not open a backend/Tk picker');
      if(action==='intro_save'){state.settings=payload.settings;return{ok:true,...state};}return{ok:true};};`});
  await page.addScriptTag({content:`let uploadCalls=[],failUpload=false;
    window.fetch=async(url,opts)=>{uploadCalls.push({url,name:opts.body.name,size:opts.body.size,headers:opts.headers});
      if(failUpload)throw Error('fixture network failure');
      return{ok:true,json:async()=>({ok:true,...state,asset:state.assets[0]})};};`});
  await page.addScriptTag({content:fs.readFileSync(path.join(__dirname,'../web_ui/video_intro.js'),'utf8')});
  assert((await page.locator('[data-view=intro]').innerText()).includes('สุ่มจุดแทรกช่วงต้น'));
  assert(!(await page.locator('[data-view=intro]').innerText()).includes('ตรงวินาทีที่ 3'));
  const chooserPromise=page.waitForEvent('filechooser');
  await page.locator('#intro-import').click();
  const chooser=await chooserPromise;
  await chooser.setFiles({name:'อินโทร.mp4',mimeType:'video/mp4',buffer:Buffer.from('video fixture')});
  await page.waitForFunction(()=>document.querySelector('#intro-status').textContent.includes('นำเข้าแล้ว'));
  assert.equal(await page.evaluate(()=>calls.some(c=>c.action==='intro_choose_file')),false);
  assert.equal(await page.evaluate(()=>uploadCalls[0].url),'/api/desktop/intro-upload');
  assert.equal(await page.evaluate(()=>decodeURIComponent(uploadCalls[0].headers['X-File-Name'])),'อินโทร.mp4');
  await page.locator('#intro-upload').dispatchEvent('cancel');
  assert.equal(await page.locator('#intro-import').isEnabled(),true);
  await page.locator('#intro-upload').setInputFiles({name:'bad.png',mimeType:'image/png',buffer:Buffer.from('bad')});
  assert.equal(await page.evaluate(()=>uploadCalls.length),1,'invalid extension must not upload');
  await page.evaluate(()=>failUpload=true);
  await page.locator('#intro-upload').setInputFiles({name:'retry.mp4',mimeType:'video/mp4',buffer:Buffer.from('video')});
  await page.waitForFunction(()=>document.querySelector('#intro-status').textContent.includes('นำเข้าไม่สำเร็จ'));
  assert.doesNotMatch(await page.locator('#intro-status').textContent(),/fixture network failure/);
  assert.equal(await page.locator('#intro-import').isEnabled(),true);
  assert.equal(await page.locator('#intro-save').isEnabled(),true);
  await page.evaluate(()=>failUpload=false);
  await page.locator('#intro-upload').setInputFiles({name:'retry.mp4',mimeType:'video/mp4',buffer:Buffer.from('video')});
  await page.waitForFunction(()=>document.querySelector('#intro-status').textContent.includes('นำเข้าแล้ว'));
  assert.equal(await page.locator('.intro-options input').first().isChecked(),false);
  await page.locator('#intro-story-default').check();await page.locator('#intro-drama-default').check();await page.locator('#intro-save').click();
  await page.waitForFunction(()=>document.querySelector('#intro-status').textContent.includes('บันทึกแล้ว'));
  for(const name of ['story','story-batch','drama','long']){
    const enabled=await page.evaluate(key=>{
      const anchor=document.querySelector(key==='long'?'#long-mode':'#'+key+'-video-mode');
      return (anchor.closest('label')||anchor).nextElementSibling.querySelector('input').checked;
    },name);
    assert.equal(enabled,name!=='long');
  }
  const results=await page.evaluate(async()=>{
    for(const action of ['create_story','enqueue_story_batch','create_drama_series','enqueue_long_video','creation_enqueue'])
      await postAction(action,{render_options:{},mode:'story'});
    await postAction('create_story',{job_id:'OLD-JOB'});
    return calls.filter(c=>['create_story','enqueue_story_batch','create_drama_series','enqueue_long_video','creation_enqueue'].includes(c.action));
  });
  for(const row of results.slice(0,5)){assert.equal(row.payload.intro_options.enabled,row.action!=='enqueue_long_video');assert.equal(row.payload.intro_options.file,'assets/intro/'+('a'.repeat(64))+'.mp4');assert.deepEqual(row.payload.render_options.intro_options,row.payload.intro_options);}
  assert.equal(results.at(-1).payload.intro_options,undefined,'resume must retain job settings');
  for(const [story,drama] of [[true,false],[false,true],[false,false],[true,true]]){
    await page.locator('#intro-story-default').setChecked(story);
    await page.locator('#intro-drama-default').setChecked(drama);
    await page.locator('#intro-save').click();
    await page.waitForFunction(([s,d])=>state.settings.targets.story===s&&state.settings.targets.drama===d,[story,drama]);
    const actual=await page.evaluate(async()=>{
      const rows=[];for(const a of ['create_story','enqueue_story_batch','create_drama_series','creation_enqueue']){
        await postAction(a,{mode:'story'});rows.push(calls.at(-1).payload.intro_options.enabled);
      }return rows;
    });
    assert.deepEqual(actual,[story,story,drama,story]);
  }
  await page.evaluate(()=>{document.querySelector('[data-view=intro]').classList.remove('active');document.querySelector('[data-view=story]').classList.add('active');});
  await page.locator('[data-view=story] .intro-options input').uncheck();
  const off=await page.evaluate(async()=>{await postAction('create_story',{});return calls.at(-1).payload;});
  assert.equal(off.intro_options.enabled,false);
  await page.evaluate(()=>{document.querySelector('[data-view=story]').classList.remove('active');document.querySelector('[data-view=intro]').classList.add('active');window.scrollTo(0,0);});
  for(const width of [1024,600]){
    await page.setViewportSize({width,height:800});
    await page.evaluate(()=>{document.querySelectorAll('.content,.main-area').forEach(n=>n.scrollTop=0);window.scrollTo(0,0);});
    assert.equal(await page.locator('#intro-save').isVisible(),true);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'No horizontal overflow');
    if(process.argv.includes('--screenshot')){
      const folder=path.join(__dirname,'../docs/reports/video-intro');fs.mkdirSync(folder,{recursive:true});
      await page.locator('[data-view=intro]').screenshot({path:path.join(folder,`intro-${width}.png`),animations:'disabled'});
    }
  }
  console.log('Intro UI import/save/defaults/per-job override/5 dispatch routes/resume guards passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
