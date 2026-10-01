// Read the existing EXE-backed desktop; all API writes and state are mocked.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try {
    const page=await browser.newPage({viewport:{width:1366,height:768}});
    const health=await (await page.request.get('http://127.0.0.1:8765/health')).json();
    assert.equal(health.desktop_ui,'hybrid');
    const state=await (await page.request.get('http://127.0.0.1:8765/api/desktop/state')).json();
    const series={id:'SERIES-ui-fixture',title:'ทดสอบปุ่มทำต่อ',status:'queued',episode_count:2,characters:[],
      episodes:[{episode_no:1,status:'completed',story_job_id:'STORY-fixture-done'},
        {episode_no:2,status:'queued',story_job_id:''}]};
    state.drama_series={items:[series]}; state.story_progress={active:false};
    state.story_queue={paused:true,items:[{mode:'drama',status:'queued',series_id:series.id,episode_no:2}]};
    const posts=[], errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/**',async route=>{
      if(route.request().method()!=='GET') {
        posts.push(route.request().postDataJSON());
        return route.fulfill({json:{ok:true}});
      }
      if(route.request().url().includes('/api/desktop/state')) return route.fulfill({json:state});
      return route.continue();
    });
    await page.goto('http://127.0.0.1:8765/desktop/#drama');
    await page.locator('.navigation [data-page="drama"]').click();
    const card=page.locator('#drama-series-list [data-start-drama-series]');
    await card.waitFor(); assert.match(await card.innerText(),/เริ่ม EP 2/);
    await page.locator('[data-open-series="SERIES-ui-fixture"]').click();
    const button=page.locator('#drama-project-modal [data-start-drama-series]');
    assert.equal(await button.count(),1); assert(await button.isVisible());
    await button.click();
    assert(posts.some(p=>p.action==='creation_start_series'&&p.series_id==='SERIES-ui-fixture'
      || p.action==='creation_start_series'&&p.payload?.series_id==='SERIES-ui-fixture'));
    assert(!posts.some(p=>['story_queue_resume','creation_start'].includes(p.action)));
    for(const width of [1000,760]) {
      await page.setViewportSize({width,height:768});
      await page.locator('[data-open-series="SERIES-ui-fixture"]').click();
      assert(await button.isVisible());
      await page.evaluate(()=>document.querySelector('#drama-project-modal').close());
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: actual desktop HTML, card/modal start button, scoped payload, 3 widths; all writes intercepted; headless browser closed');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
