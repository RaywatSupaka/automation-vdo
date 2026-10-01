const fs=require('fs'),assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage();
 await page.route('**/*',r=>r.request().isNavigationRequest()?r.fulfill({contentType:'text/html',body:fs.readFileSync('web_ui/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'')}):r.abort());
 await page.goto('https://fixture.invalid/');
 await page.addScriptTag({content:fs.readFileSync('web_ui/music_library.js','utf8')});
 await page.addStyleTag({content:fs.readFileSync('web_ui/styles.css','utf8')+'\n'+fs.readFileSync('web_ui/music_library.css','utf8')});
 await page.evaluate(()=>{document.querySelector('[data-view="audio"]').classList.add('active');document.querySelector('#audio-background-enabled').checked=true;SmartFlowMusic.render({background_files:['สุ่มจากคลัง','a.mp3','b.mp3','c.mp3','d.mp3','e.mp3'],background_selection:['a.mp3','b.mp3','c.mp3','d.mp3','e.mp3'],background_track_count:5});});
 assert.equal(await page.locator('.music-track').count(),5);
 assert.equal(await page.locator('#audio-background-file').isVisible(),false);
 assert.equal(await page.evaluate(()=>SmartFlowMusic.payload().background_track_count),5);
 await page.evaluate(()=>document.querySelector('[data-music-count="4"]').click());
 assert.equal(await page.evaluate(()=>SmartFlowMusic.payload().background_track_count),4);
 await page.evaluate(()=>{document.querySelector('[data-music-name="e.mp3"]').click();SmartFlowMusic.render({background_files:['สุ่มจากคลัง','a.mp3','b.mp3','c.mp3','d.mp3','e.mp3'],background_selection:['e.mp3'],background_track_count:1});});
 assert.deepEqual(await page.evaluate(()=>SmartFlowMusic.payload().background_selection),['a.mp3','b.mp3','c.mp3','d.mp3']);
 await page.evaluate(()=>document.querySelector('[data-music-none]').click());
 assert(await page.evaluate(()=>{try{SmartFlowMusic.payload();return false;}catch{return true;}}));
 await page.evaluate(()=>{document.querySelector('[data-music-all]').click();document.querySelector('#music-count').value='4';});
 assert.equal(await page.evaluate(()=>SmartFlowMusic.payload().background_selection.length),5);
 // Only one player exists; previews never trigger rendering or AI requests.
 assert.equal(await page.locator('.music-library audio').count(),1);
 await page.evaluate(()=>{window.playRequests=[];HTMLMediaElement.prototype.play=function(){playRequests.push(this.src);return Promise.resolve();};document.querySelector('[data-music-play="a.mp3"]').click();});
 assert((await page.evaluate(()=>playRequests[0])).endsWith('/api/desktop/music-preview?file=a.mp3'));
 if(process.env.SMARTFLOW_TEST_SCREENSHOT){
   await page.evaluate(()=>{document.querySelectorAll('[data-view]').forEach(e=>{e.style.display=e.dataset.view==='audio'?'block':'none';});});
   fs.mkdirSync('workspace/test-artifacts',{recursive:true});
   await page.locator('.music-library').screenshot({path:'workspace/test-artifacts/music-library-368.png'});
 }
 console.log('music library DOM passed: selection/count/poll preservation/preview');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
