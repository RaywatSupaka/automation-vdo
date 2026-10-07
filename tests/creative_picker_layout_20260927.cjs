// Real index, complete stylesheet cascade and shared native picker controllers.
// Synthetic catalog/transport only; never opens the app, a profile or a provider.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),read=file=>fs.readFileSync(path.join(root,'web_ui',file),'utf8');
const catalog=JSON.parse(process.env.SMARTFLOW_CREATIVE_CATALOG),probe=process.argv.includes('--probe');
const viewports=[[390,844],[600,707],[707,600],[980,707],[1440,900],[1440,600],[707,420],[390,568]];
let checks=0;
function same(actual,expected,message){assert.deepEqual(actual,expected,message);checks++;}
function requireTrue(value,message){assert(value,message);checks++;}
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[],network=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',route=>{network.push(route.request().url());return route.abort();});
    const html=read('index.html'),styles=[...html.matchAll(/<link\b[^>]*rel="stylesheet"[^>]*href="([^"?]+)[^"]*"[^>]*>/gi)].map(match=>path.basename(match[1]));
    await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
    for(const file of styles)await page.addStyleTag({content:read(file)});
    await page.addScriptTag({content:`
      const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
      const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const ui={state:{},activePage:'products',aiModelDrafts:{},dramaImages:{},dramaFootage:[]},pageMeta={},calls=[];
      const toast=()=>{},poll=async()=>{},renderSystem=()=>{},showPage=name=>{ui.activePage=name;$$('[data-view]').forEach(node=>node.classList.toggle('active',node.dataset.view===name));};
      let postAction=async(action,payload={})=>{calls.push({action,payload:JSON.parse(JSON.stringify(payload))});return {ok:true,assets:[]};};
      window.fetch=async()=>{throw Error('Picker attempted an unexpected fetch');};
      window.pickerChanges=[];
    `});
    const app=read('app.js'),start=app.indexOf('const fallbackAiModelOptions =');
    await page.addScriptTag({content:app.slice(start,app.indexOf('function bindAiModelSelect(',start))});
    await page.addScriptTag({content:read('creative_controls.js')});
    // Observe the actual onChange path, including radio adapters, without replacing it.
    await page.evaluate(()=>{
      const mount=window.mountCreativePicker;
      window.mountCreativePicker=options=>mount({...options,onChange:value=>{
        pickerChanges.push({id:options.id,value});return options.onChange?.(value);
      }});
    });
    for(const file of ['status_vocabulary.js','creation_queue.js','media_audio.js','product_story.js','storytelling.js','creator_ux.js'])await page.addScriptTag({content:read(file)});
    await page.evaluate(catalog=>{renderCreativeCatalog(catalog);showPage('products');},catalog);
    same(errors,[],'All real controllers initialize');
    const defaultSummary=await page.locator('[data-view=story] .creator-review p').textContent();
    requireTrue(!defaultSummary.includes('โครงเรื่อง:')&&!defaultSummary.includes('เปลี่ยน'),'Legacy Story default is suppressed and picker action text never leaks into its summary');
    const dialog=page.locator('.creative-dialog[open]'),back=()=>dialog.getByRole('button',{name:'กลับ',exact:true});
    async function geometry(){
      return dialog.evaluate(node=>{
        const card=node.querySelector('.modal-card'),list=node.querySelector('.creative-options');
        const rect=n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
        return {viewport:{width:innerWidth,height:innerHeight},dialog:rect(node),card:rect(card),
          dialogOverflow:node.scrollWidth-node.clientWidth,cardOverflow:card.scrollWidth-card.clientWidth,listOverflow:list.scrollWidth-list.clientWidth,
          search:rect(node.querySelector('input[type=search]')),back:rect([...node.querySelectorAll('button')].find(n=>n.textContent==='กลับ'))};
      });
    }
    function fits(g,label){
      requireTrue(g.card.x>=8&&g.card.right<=g.viewport.width-8,label+' card fits horizontally: '+JSON.stringify(g));
      requireTrue(g.card.y>=8&&g.card.bottom<=g.viewport.height-8,label+' card fits vertically: '+JSON.stringify(g));
      requireTrue(Math.abs(g.card.x+g.card.width/2-g.viewport.width/2)<=3,label+' card is horizontally centered: '+JSON.stringify(g));
      requireTrue(Math.abs(g.card.y+g.card.height/2-g.viewport.height/2)<=3,label+' card is vertically centered: '+JSON.stringify(g));
      requireTrue(g.dialogOverflow<=1&&g.cardOverflow<=1&&g.listOverflow<=1,label+' no horizontal scroll: '+JSON.stringify(g));
      requireTrue(g.search.y>=g.card.y&&g.search.bottom<=g.card.bottom&&g.back.y>=g.card.y&&g.back.bottom<=g.card.bottom,label+' search and back remain in the card');
    }
    async function changes(){return page.evaluate(()=>pickerChanges.length);}
    async function focused(id){
      try{await page.waitForFunction(id=>document.activeElement===document.getElementById(id),id,{timeout:3000});}
      catch(error){throw Error('Focus did not return to '+id+': '+JSON.stringify(await page.evaluate(()=>({active:document.activeElement?.outerHTML,open:[...document.querySelectorAll('dialog[open]')].map(node=>node.id),search:document.querySelector('.creative-dialog[open] input[type=search]')?.value}))));}
      checks++;
    }
    if(!probe){
      // The catalog can arrive after the user has already opened and searched.
      await page.evaluate(()=>renderCreativeCatalog({version:1,product:[],story:[]}));
      await page.locator('#ps-creative-style').click();
      same(await dialog.locator('[data-creative-value]').count(),0);
      requireTrue((await dialog.locator('.creative-options').textContent()).includes('กำลังโหลดรายการแนวบท'),'Empty catalog shows loading state');
      await dialog.locator('input[type=search]').fill('ก่อนออก');
      let before=await changes();await page.evaluate(catalog=>renderCreativeCatalog(catalog),catalog);
      same(await dialog.locator('input[type=search]').inputValue(),'ก่อนออก','Late catalog preserves the typed query');
      same(await dialog.locator('[data-creative-value]').count(),1);
      same(await dialog.locator('[data-creative-value]').getAttribute('data-creative-value'),'before_leaving');
      same(await changes(),before,'Catalog arrival is not a user selection');
      await dialog.locator('.creative-close').click();await focused('ps-creative-style');same(await changes(),before,'Close X does not change selection');
      // Identical state polls must not replace the option being inspected.
      await page.setViewportSize({width:390,height:568});await page.locator('#ps-creative-style').click();
      await dialog.locator('input[type=search]').fill('สินค้า');
      await dialog.locator('[data-creative-value]').last().focus();
      const inspected=await dialog.evaluate(node=>{
        window.fixtureFocusedOption=document.activeElement;
        return {search:node.querySelector('input[type=search]').value,scroll:node.querySelector('.creative-options').scrollTop,focused:document.activeElement.dataset.creativeValue};
      });
      requireTrue(inspected.scroll>0,'Filtered list is scrolled before the unchanged state poll');before=await changes();
      await page.evaluate(catalog=>{renderCreativeCatalog(catalog);renderCreativeCatalog(JSON.parse(JSON.stringify(catalog)));},catalog);
      same(await dialog.evaluate(node=>({search:node.querySelector('input[type=search]').value,scroll:node.querySelector('.creative-options').scrollTop,focused:document.activeElement.dataset.creativeValue})),inspected,'Identical catalog retains search, scroll and focus');
      same(await page.evaluate(()=>document.activeElement===window.fixtureFocusedOption),true,'Focused option DOM identity survives the poll');
      same(await changes(),before);await page.keyboard.press('Escape');await focused('ps-creative-style');
      // Saved settings can hydrate the native radio without dispatching change.
      // An identical catalog poll must still refresh its closed trigger label.
      const hydratedChoice=catalog.product.find(item=>item.value==='story_first_review');
      before=await changes();
      await page.evaluate(catalog=>{
        document.querySelector('[name=ps-script-style][value=story_first_review]').checked=true;
        renderCreativeCatalog(catalog);
      },catalog);
      same(await dialog.count(),0,'Hydration does not open the picker');
      same(await page.locator('[name=ps-script-style]:checked').inputValue(),hydratedChoice.value);
      same(await page.locator('#ps-creative-style .creative-current-label').textContent(),hydratedChoice.label,'Identical catalog refreshes a programmatically hydrated closed picker');
      same(await changes(),before,'Hydration refresh does not invoke selection callback');
    }
    const evidence=[];
    for(const [width,height] of viewports){
      await page.setViewportSize({width,height});await page.locator('#ps-creative-style').click();
      const g=await geometry();evidence.push(g);
      if(probe){
        if(width===1440&&height===900){
          const folder=path.join(root,'build','creative-picker-layout-20260927');fs.mkdirSync(folder,{recursive:true});
          await page.screenshot({path:path.join(folder,'before-1440x900.png')});
        }
        await page.keyboard.press('Escape');continue;
      }
      fits(g,`${width}x${height}`);
      same(await dialog.locator('[data-creative-value]').evaluateAll(nodes=>nodes.map(node=>node.dataset.creativeValue)),catalog.product.map(item=>item.value),'All catalog choices, including AI auto and pointing review, are mounted');
      same(await dialog.locator('[data-creative-value] > small').evaluateAll(nodes=>nodes.map(node=>node.textContent)),catalog.product.map(item=>item.description),'Every choice includes the supplied short description');
      await page.keyboard.press('Escape');await focused('ps-creative-style');
      // Every choice must be reachable by normal scrolling and commit exactly once.
      for(const item of catalog.product){
        await page.locator('#ps-creative-style').click();
        const option=dialog.locator(`[data-creative-value="${item.value}"]`);await option.scrollIntoViewIfNeeded();
        const visible=await option.evaluate(node=>{const r=node.getBoundingClientRect(),card=node.closest('.modal-card').getBoundingClientRect();return r.x>=card.x&&r.right<=card.right+1&&r.y>=card.y&&r.bottom<=card.bottom+1&&r.y>=0&&r.bottom<=innerHeight;});
        requireTrue(visible,`${item.value} is accessible at ${width}x${height}`);
        const count=await changes();await option.click();
        same(await changes(),count+1,'One choice invokes its actual callback once');
        same(await page.locator('[name=ps-script-style]:checked').inputValue(),item.value);
        same(await dialog.count(),0);await focused('ps-creative-style');
      }
      await page.locator('#ps-creative-style').click();
      const search=dialog.locator('input[type=search]');same(await search.evaluate(node=>document.activeElement===node),true,'Opening puts focus in search');
      await search.fill('ก่อนออก');same(await dialog.locator('[data-creative-value]').count(),1);
      same(await dialog.locator('[data-creative-value]').getAttribute('data-creative-value'),'before_leaving');
      await search.fill('ไม่มีแนวบทที่ชื่อแบบนี้-98765');same(await dialog.locator('[data-creative-value]').count(),0);
      requireTrue((await dialog.locator('.creative-options').textContent()).includes('ไม่พบแนวที่ตรงกับคำค้น'),'No-result feedback is shown');
      await search.fill('AI');same(await dialog.locator('[data-creative-value=auto]').count(),1,'AI auto remains searchable');
      await search.fill('');same(await dialog.locator('[data-creative-value]').count(),catalog.product.length,'Clearing search restores every option');
      const before=await page.evaluate(()=>({changes:pickerChanges.length,value:document.querySelector('[name=ps-script-style]:checked').value}));
      await back().click();await focused('ps-creative-style');
      same(await page.evaluate(()=>({changes:pickerChanges.length,value:document.querySelector('[name=ps-script-style]:checked').value})),before,'Back neither selects nor changes anything');
      await page.locator('#ps-creative-style').click();await search.fill('เปลี่ยนคำค้นเท่านั้น');
      await search.evaluate(node=>node.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',isComposing:true,bubbles:true,cancelable:true})));
      same(await dialog.count(),1,'Escape during IME composition leaves the picker open');
      same(await search.inputValue(),'เปลี่ยนคำค้นเท่านั้น');same(await changes(),before.changes);
      await page.keyboard.press('Escape');await focused('ps-creative-style');
      same(await page.evaluate(()=>({changes:pickerChanges.length,value:document.querySelector('[name=ps-script-style]:checked').value})),before,'Escape preserves selection');
      if(process.env.SMARTFLOW_PICKER_SCREENSHOTS==='1'&&[[390,844],[707,420],[1440,900]].some(size=>size[0]===width&&size[1]===height)){
        await page.locator('#ps-creative-style').click();
        const folder=path.join(root,'build','creative-picker-layout-20260927');fs.mkdirSync(folder,{recursive:true});
        await page.screenshot({path:path.join(folder,`after-${width}x${height}.png`)});await page.keyboard.press('Escape');
      }
    }
    if(probe){console.log(JSON.stringify({probe:true,styles:styles.length,geometry:evidence,errors,networkRequests:network.length}));return;}
    // The same component remains usable above the queue's already-open dialog.
    for(const [width,height] of [[390,844],[707,420],[1440,900]]){
      await page.setViewportSize({width,height});await page.evaluate(()=>showPage('creation'));
      await page.locator('#queue-add-products').click();
      await page.locator('#creation-product-settings > summary').click();
      await page.locator('#creation-product-style').click();fits(await geometry(),'Queue '+width+'x'+height);
      same(await dialog.locator('[data-creative-value]').count(),catalog.product.length);
      let count=await changes();await dialog.locator('[data-creative-value=auto]').click();same(await changes(),count+1);await focused('creation-product-style');
      same(await page.locator('[name=creation-product-script]:checked').inputValue(),'auto');
      await page.locator('#creation-product-style').click();await page.keyboard.press('Escape');await focused('creation-product-style');
      same(await page.locator('#creation-editor').evaluate(node=>node.open),true,'Closing nested picker keeps the queue editor open');
      await page.locator('#creation-editor-close').click();
      await page.evaluate(()=>showPage('story'));
      await page.locator('[data-storytelling=story] .storytelling-advanced').evaluate(node=>node.open=true);
      await page.locator('#story-structure').click();fits(await geometry(),'Story '+width+'x'+height);
      same(await dialog.locator('[data-creative-value]').count(),12);
      count=await changes();await dialog.locator('[data-creative-value=countdown]').click();same(await changes(),count+1);await focused('story-structure');
      requireTrue((await page.locator('#story-structure').textContent()).includes('ภารกิจก่อนหมดเวลา'),'Story retains its shared-picker selection');
      const review=await page.locator('[data-view=story] .creator-review p').textContent();
      requireTrue(review.includes('โครงเรื่อง: ภารกิจก่อนหมดเวลา')&&!review.includes('เปลี่ยน'),'Story review contains only the selected structure label');
      await page.locator('#story-structure').click();await back().click();await focused('story-structure');same(await changes(),count+1);
    }
    same(errors,[]);same(network,[]);
    same(await page.evaluate(()=>calls.filter(call=>!['product_cast_state'].includes(call.action))),[],'Picker interaction never submits creation or other actions');
    console.log(JSON.stringify({ok:true,checks,styles:styles.length,viewports,productChoices:catalog.product.length,storyChoices:12,networkRequests:0,providerRequests:0}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
