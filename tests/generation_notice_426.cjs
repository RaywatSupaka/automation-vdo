const fs=require('fs'),assert=require('assert/strict'),{chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage();await page.route('**/*',r=>r.abort());
 await page.setContent('<button id="start">สร้าง</button>');
 await page.evaluate(()=>{window.calls=[];window.postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true};};});
 await page.addScriptTag({content:fs.readFileSync('web_ui/generation_notice.js','utf8')});
 await page.evaluate(()=>{window.pending=postAction('create_product',{link:'fixture'});});
 assert.equal(await page.isVisible('#generation-notice'),true);
 assert.equal(await page.evaluate(()=>calls.length),0);
 await page.click('[data-notice-start]');await page.evaluate(()=>pending);
 assert.equal(await page.evaluate(()=>calls.length),1);
 await page.evaluate(()=>{window.pending=postAction('creation_start',{}).catch(e=>e.message);});
 await page.click('[data-notice-cancel]');await page.evaluate(()=>pending);
 assert.equal(await page.evaluate(()=>calls.length),1);
 await page.evaluate(()=>postAction('product_cast_state',{}));
 assert.equal(await page.isVisible('#generation-notice'),false);
 console.log('Generation reminder: creation, queue, cancel, read-only actions passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
