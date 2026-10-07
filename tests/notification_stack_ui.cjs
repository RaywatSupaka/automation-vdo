const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    const errors=[];
    page.on('pageerror', error=>errors.push(error.message));
    await page.route('**/*', route=>route.abort());
    const html=fs.readFileSync('web_ui/index.html','utf8');
    await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
    for(const match of html.matchAll(/<link[^>]*href="\/desktop\/([^?" ]+)\.css[^" ]*"/g))
      await page.addStyleTag({content:fs.readFileSync(`web_ui/${match[1]}.css`,'utf8')});
    await page.evaluate(()=>{
      window.pywebview={api:{}};
      window.setTimeout=()=>0;window.setInterval=()=>0;
    });
    await page.addScriptTag({content:fs.readFileSync('web_ui/updates.js','utf8')});
    await page.evaluate(()=>{
      dispatchEvent(new Event('pywebviewready'));
      document.querySelector('#toast span').textContent='คิวสร้างคลิป • สำเร็จ 14/19 คลิป';
      document.querySelector('#progress-minimized').textContent='● 28% • ภาพ 3 • ครั้ง 1 • reference_image • รูปตั้งต้น 1 • Prompt 3220 ตัวอักษร • บันทึกคำสั่งและช่องพิมพ์จริงก่อนส่ง • เปิดรายละเอียด';
    });
    let checks=0;
    for(const [width,height] of [[1920,1080],[1180,720],[700,600],[390,844],[320,480]]) {
      await page.setViewportSize({width,height});
      for(let mask=0;mask<8;mask++) {
        const rects=await page.evaluate(mask=>{
          document.querySelector('#toast').classList.toggle('show',Boolean(mask&1));
          document.querySelector('#progress-minimized').classList.toggle('hidden',!(mask&2));
          document.querySelector('#sp-run-pill').hidden=!(mask&4);
          return [...document.querySelector('#notification-stack').children].filter(n=>n.getClientRects().length)
            .map(n=>({id:n.id||n.className,...n.getBoundingClientRect().toJSON()}));
        },mask);
        assert.equal(rects.length,1+Boolean(mask&1)+Boolean(mask&2)+Boolean(mask&4));
        for(let i=0;i<rects.length;i++) {
          const r=rects[i];
          assert(r.left>=0 && r.right<=width && r.top>=0 && r.bottom<=height,`${width}: ${r.id} offscreen`);
          if(i)assert(rects[i-1].bottom+8<=r.top,`${width}: overlapping notices`);
        }
        checks++;
      }
    }
    assert.deepEqual(errors,[]);
    await page.setViewportSize({width:1180,height:720});
    await page.evaluate(()=>{document.querySelector('#sp-run-pill').hidden=true;});
    fs.mkdirSync('build/notification-stack',{recursive:true});
    await page.screenshot({path:'build/notification-stack/desktop.png'});
    console.log(`${checks} notification layouts passed; update control and notices stay within viewport`);
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
