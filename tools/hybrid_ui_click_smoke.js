const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 9337;
const APP_URL = process.argv[2] || "http://127.0.0.1:8765/desktop/#library";
const STUDIO_AUDIT = process.argv.includes("--studio-audit");
const QUEUE_AUDIT = process.argv.includes("--queue-audit");
const profile = path.join(os.tmpdir(), `smartflow-ui-smoke-${process.pid}`);
let browser;
let cdp;

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function waitJson(url, attempts = 80) {
  for (let index = 0; index < attempts; index += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return response.json();
    } catch (_) {}
    await delay(100);
  }
  throw new Error(`DevTools endpoint unavailable: ${url}`);
}

class Cdp {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
  }

  async open() {
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", event => {
      const message = JSON.parse(String(event.data));
      if (!message.id || !this.pending.has(message.id)) return;
      const { resolve, reject } = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result || {});
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text || "Evaluation failed");
    return result.result?.value;
  }

  close() {
    this.socket.close();
  }
}

async function waitFor(cdp, expression, label) {
  for (let index = 0; index < 100; index += 1) {
    if (await cdp.eval(expression)) return;
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function physicalClick(cdp, selector) {
  await cdp.eval(`document.querySelector(${JSON.stringify(selector)})?.scrollIntoView({block:'center', inline:'center'})`);
  await delay(100);
  const point = await cdp.eval(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const hit = document.elementFromPoint(x, y);
    return {
      x, y,
      disabled: Boolean(element.disabled),
      target: hit ? hit.outerHTML.slice(0, 240) : "",
      intended: hit === element || element.contains(hit),
    };
  })()`);
  if (!point) throw new Error(`Missing click target: ${selector}`);
  if (point.disabled || !point.intended) {
    throw new Error(`Blocked click target ${selector}: ${JSON.stringify(point)}`);
  }
  await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x: point.x, y: point.y, button: "left", clickCount: 1 });
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: point.x, y: point.y, button: "left", clickCount: 1 });
  await delay(180);
  return point;
}

async function main() {
  if (!fs.existsSync(EDGE)) throw new Error("Microsoft Edge was not found");
  fs.mkdirSync(profile, { recursive: true });
  browser = spawn(EDGE, [
    "--headless=new",
    `--remote-debugging-port=${PORT}`,
    "--remote-allow-origins=*",
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--disable-gpu",
    "about:blank",
  ], { stdio: "ignore", windowsHide: true });

  await waitJson(`http://127.0.0.1:${PORT}/json/version`);
  const target = await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(APP_URL)}`, { method: "PUT" }).then(response => response.json());
  cdp = new Cdp(target.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send("Runtime.enable");
  await waitFor(cdp, "document.readyState === 'complete' && document.querySelector('#library-grid')", "SmartFlow shell");
  if (QUEUE_AUDIT) {
    await waitFor(cdp, "Boolean(ui.state?.creation_queue && window.renderCreationQueue)", "creation queue runtime");
    await creationQueueAudit(cdp);
    return;
  }
  if (STUDIO_AUDIT) {
    await waitFor(cdp, "ui.state?.story_visual_styles?.length === 8", "new studio runtime");
    await studioAudit(cdp);
    return;
  }
  await waitFor(cdp, "document.querySelectorAll('[data-library-id]').length > 0", "library cards");

  const cardHit = await physicalClick(cdp, "#library-grid [data-library-id]");
  await waitFor(cdp, "document.querySelector('#detail-modal')?.open === true", "detail modal");
  await cdp.eval("window.__smartflowSmokeCalls=[]; window.__smartflowSmokeCopies=[]; window.__smartflowSmokeClicks=[]; window.__smartflowSmokeErrors=[]; window.addEventListener('error',event=>window.__smartflowSmokeErrors.push(event.message||String(event.error||''))); window.addEventListener('unhandledrejection',event=>window.__smartflowSmokeErrors.push(String(event.reason?.stack||event.reason||''))); document.addEventListener('click',event=>window.__smartflowSmokeClicks.push({delegated:event.smartflowDelegated===true,button:event.target?.closest?.('button')?.outerHTML?.slice(0,180)||event.target?.outerHTML?.slice(0,180)||''}),true); postAction=async(action,payload={})=>{window.__smartflowSmokeCalls.push({action,payload});return {ok:true}}; copyText=value=>window.__smartflowSmokeCopies.push(String(value||''));");

  const copyHit = await physicalClick(cdp, "[data-copy-key='post_text']");
  const coverHit = await physicalClick(cdp, "[data-detail-cover]");
  const folderHit = await physicalClick(cdp, "[data-detail-folder]");
  const playHit = await physicalClick(cdp, "[data-detail-play]");
  const deleteHit = await physicalClick(cdp, "[data-detail-delete-video]");
  await delay(250);
  const deleteState = await cdp.eval(`({confirmOpen:document.querySelector('#confirm-modal')?.open === true, confirmAction:ui.confirmAction, calls:window.__smartflowSmokeCalls, clicks:window.__smartflowSmokeClicks, errors:window.__smartflowSmokeErrors})`);
  if (!deleteState.confirmOpen) throw new Error(`Delete confirmation did not open: ${JSON.stringify(deleteState)}`);
  await physicalClick(cdp, "[data-close-modal='confirm-modal']");
  const deleteProjectHit = await physicalClick(cdp, "[data-detail-delete-project]");
  await waitFor(cdp, "document.querySelector('#confirm-modal')?.open === true", "project delete confirmation");
  await physicalClick(cdp, "[data-close-modal='confirm-modal']");
  const closeHit = await physicalClick(cdp, "[data-close-modal='detail-modal']");

  const outcome = await cdp.eval(`({
    modalClosed: document.querySelector('#detail-modal')?.open === false,
    calls: window.__smartflowSmokeCalls,
    copies: window.__smartflowSmokeCopies,
    errors: window.__smartflowSmokeErrors,
    folderButtons: document.querySelectorAll('[data-detail-folder]').length,
    playButtons: document.querySelectorAll('[data-detail-play]').length,
  })`);
  const actions = outcome.calls.map(call => call.action);
  for (const expected of ["open_library_cover", "open_library_folder", "open_library_video"]) {
    if (!actions.includes(expected)) throw new Error(`Missing action ${expected}: ${JSON.stringify(outcome)}`);
  }
  if (!outcome.modalClosed || !outcome.copies.length || outcome.errors.length) {
    throw new Error(`Detail controls failed: ${JSON.stringify(outcome)}`);
  }
  console.log(JSON.stringify({ ok: true, cardHit, copyHit, coverHit, folderHit, playHit, deleteHit, deleteProjectHit, closeHit, outcome }, null, 2));
}

async function studioAudit(cdp) {
  const directory = path.resolve(__dirname, "../docs/reports/studio-20260905-phase2");
  fs.mkdirSync(directory, { recursive: true });
  await cdp.eval(`window.__studioErrors=[]; window.addEventListener('error', e=>window.__studioErrors.push(e.message)); window.addEventListener('unhandledrejection', e=>window.__studioErrors.push(String(e.reason)));`);
  const pages = await cdp.eval("Object.keys(pageMeta)");
  const layouts = [];
  for (const width of [1440, 1024, 768]) {
    await cdp.send("Emulation.setDeviceMetricsOverride", {width, height:950, deviceScaleFactor:1, mobile:false});
    for (const page of pages) {
      await cdp.eval(`showPage(${JSON.stringify(page)})`);
      await delay(90);
      layouts.push(await cdp.eval(`({page:ui.activePage,width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth+2,visible:!!document.querySelector('.page.active'),heading:document.querySelector('.page.active h1')?.textContent||''})`));
      if (width === 1440 && ['story','subtitle','dashboard'].includes(page)) {
        const capture = await cdp.send("Page.captureScreenshot", {format:"png"});
        fs.writeFileSync(path.join(directory, `${page}.png`), Buffer.from(capture.data,"base64"));
      }
    }
  }
  await cdp.send("Emulation.setDeviceMetricsOverride", {width:1440,height:950,deviceScaleFactor:1,mobile:false});
  await cdp.eval("showPage('subtitle')");
  await waitFor(cdp, "!ui.polling && !ui.pendingFullPoll", "navigation state settled");
  await cdp.eval(`window.__originalPreviewPayload=subtitlePayload(); window.__studioRequests=[]; const originalFetch=window.fetch; window.fetch=async (...args)=>{const url=String(args[0]); if(url.includes('/api/desktop/')) window.__studioRequests.push({url,at:performance.now()}); return originalFetch(...args);};`);
  const initial = await cdp.eval("Number(document.querySelector('#subtitle-preview-video').dataset.token||0)");
  await cdp.eval(`window.__previewStart=performance.now(); document.querySelector('#subtitle-text-color').value='#eee'+(Date.now()%4096).toString(16).padStart(3,'0'); const slider=document.querySelector('#subtitle-font-size'); const last=Number(slider.value)===59?58:59; for(let i=0;i<30;i++){slider.value=i===29?last:30+i; slider.dispatchEvent(new Event('input',{bubbles:true}));}`);
  try {
    await waitFor(cdp, `Number(document.querySelector('#subtitle-preview-video').dataset.token||0)>${initial} && document.querySelector('#subtitle-preview-video').readyState>=2 && document.querySelector('#subtitle-preview-state').hidden`, "latest preview ready");
  } catch (error) {
    console.log(await cdp.eval(`({requests:window.__studioRequests,errors:window.__studioErrors,initial:${initial},video:document.querySelector('#subtitle-preview-video').outerHTML,state:document.querySelector('#subtitle-preview-state').outerHTML,mediaError:document.querySelector('#subtitle-preview-video').error?.message,ready:document.querySelector('#subtitle-preview-video').readyState})`));
    throw error;
  }
  const preview = await cdp.eval(`({elapsed_ms:Math.round(performance.now()-window.__previewStart),requests:window.__studioRequests,readyState:document.querySelector('#subtitle-preview-video').readyState})`);
  const backendPreview = await fetch('http://127.0.0.1:8765/api/desktop/state?mode=subtitle_preview').then(r=>r.json());
  preview.render_ms = backendPreview.subtitle_preview.preview_render_ms;
  if (!preview.render_ms) throw new Error('Expected a newly rendered preview, not a warm cache result');
  const staleResult = await cdp.eval(`(()=>{const current=${JSON.stringify(backendPreview.subtitle_preview)}; const node=document.querySelector('#subtitle-preview-video'); const src=node.src; renderSubtitlePreview({...current,preview_ready_token:0,preview_video_url:'/stale.mp4',preview_busy:true}); return node.src===src;})()`);
  if (!staleResult) throw new Error('An old state replaced the latest preview');
  const posts = preview.requests.filter(item=>item.url==='/api/desktop/action');
  const fullReads = preview.requests.filter(item=>item.url==='/api/desktop/state');
  if (posts.length !== 1 || fullReads.length) throw new Error(`Preview request regression: ${JSON.stringify(preview)}`);
  const beforeMode = posts.length;
  await physicalClick(cdp, '[data-subtitle-preview-mode="frame"]');
  await physicalClick(cdp, '[data-subtitle-preview-mode="detail"]');
  const afterMode = await cdp.eval("window.__studioRequests.filter(item=>item.url==='/api/desktop/action').length");
  if (beforeMode !== afterMode) throw new Error("Preview mode unexpectedly renders again");
  await cdp.eval(`(async()=>{const restored=await postAction('subtitle_preview_style',window.__originalPreviewPayload); await waitSubtitlePreview(++ui.subtitlePreviewSequence,restored.preview_token);})()`);
  await cdp.eval("showPage('story')");
  await waitFor(cdp,"document.querySelector('#story-review-job')?.value",'Story review job');
  await physicalClick(cdp,'[data-open-studio="story"]');
  await waitFor(cdp,"document.querySelectorAll('#studio-review-modal .studio-scene').length > 0",'Storyboard scenes');
  await waitFor(cdp,"[...document.querySelectorAll('#studio-review-modal img')].filter(n=>n.getBoundingClientRect().top<innerHeight).every(n=>n.complete&&n.naturalWidth>0)",'Visible storyboard images decoded');
  const review = await cdp.eval(`({scenes:document.querySelectorAll('#studio-review-modal .studio-scene').length, stages:document.querySelectorAll('.studio-checkpoints li').length, modal:document.querySelector('#studio-review-modal').open, noOverflow:document.querySelector('.studio-review-card').scrollWidth<=document.querySelector('.studio-review-card').clientWidth+2})`);
  const shot = await cdp.send('Page.captureScreenshot',{format:'png'});
  fs.writeFileSync(path.join(directory,'storyboard.png'),Buffer.from(shot.data,'base64'));
  await physicalClick(cdp,'[data-preview-notes]');
  await waitFor(cdp,"document.querySelector('#studio-voice-result').textContent.length > 0",'Pronunciation preview');
  review.widths=[];
  for(const width of [1024,768]){
    await cdp.send('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:false});
    await delay(100);
    review.widths.push(await cdp.eval(`(()=>{const card=document.querySelector('.studio-review-card');const r=card.getBoundingClientRect();return {width:${width},noOverflow:card.scrollWidth<=card.clientWidth+2,inside:r.left>=0&&r.right<=innerWidth+2};})()`));
  }
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:950,deviceScaleFactor:1,mobile:false});
  await cdp.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  review.reducedMotion=await cdp.eval("getComputedStyle(document.querySelector('.studio-review-launcher')).animationName==='none'");
  await cdp.send('Emulation.setEmulatedMedia',{features:[]});
  await physicalClick(cdp,'[data-close-modal="studio-review-modal"]');
  review.closed = await cdp.eval("!document.querySelector('#studio-review-modal').open");
  review.focusRestored = await cdp.eval("document.activeElement?.dataset.openStudio === 'story'");
  await cdp.eval("showPage('logs')");
  const filters = await cdp.eval(`(()=>{const input=document.querySelector('#studio-log-query');input.value='SHOT-2';document.querySelector('#studio-log-service').value='flow';document.querySelector('#studio-log-errors').checked=true;renderLogs({system:{},logs:['Flow SHOT-2 error failed','Flow SHOT-1 ready','Voice SHOT-2 error']});const result=document.querySelector('#log-console').textContent==='Flow SHOT-2 error failed';input.value='';document.querySelector('#studio-log-service').value='all';document.querySelector('#studio-log-errors').checked=false;renderLogs(ui.state);return result;})()`);
  const lightweightLogs = await fetch('http://127.0.0.1:8765/api/desktop/state?mode=logs').then(r=>r.json());
  const checks = await cdp.eval(`({errors:window.__studioErrors,duplicateIds:[...document.querySelectorAll('[id]')].map(n=>n.id).filter((id,i,all)=>all.indexOf(id)!==i),styles:['story','story-batch','drama'].map(prefix=>({prefix,count:document.querySelector('#'+prefix+'-visual-style').options.length}))})`);
  checks.logFilters=filters;checks.logsLightweight=lightweightLogs.partial===true&&!lightweightLogs.library;
  const outcome = {ok:!layouts.some(item=>item.overflow) && !checks.errors.length && !checks.duplicateIds.length && filters && checks.logsLightweight && review.closed && review.focusRestored && review.noOverflow && review.reducedMotion && review.widths.every(x=>x.noOverflow&&x.inside),layouts,preview,review,checks};
  fs.writeFileSync(path.join(directory,'audit.json'),JSON.stringify(outcome,null,2));
  console.log(JSON.stringify(outcome,null,2));
  if (!outcome.ok) throw new Error("Studio layout/console audit failed; see audit.json");
}

async function creationQueueAudit(cdp) {
  const directory = path.join(__dirname,'..','docs','reports','creation-queue-20260905');
  fs.mkdirSync(directory,{recursive:true});
  const prefix = `queue-smoke-${Date.now()}`;
  const baseline = await cdp.eval('ui.state.creation_queue');
  if (baseline.active_count || !baseline.paused) throw new Error('User queue is active; smoke will not touch it');
  const beforeIds = baseline.items.map(row=>row.queue_id);
  const results = {mode:'paused UI CRUD + synthetic progress; no AI jobs', checks:{}, layouts:[]};
  await cdp.eval(`window.__queueErrors=[];window.addEventListener('error',e=>__queueErrors.push(e.message));window.__queueOriginalPost=postAction;window.__queueActions=[];postAction=async function(action,payload){if(!['creation_enqueue','creation_edit','creation_move','creation_remove','enqueue_story_batch'].includes(action))throw new Error('Blocked live action during queue smoke: '+action);__queueActions.push(action);return __queueOriginalPost(action,payload);};showPage('creation');`);
  try {
    await physicalClick(cdp,'#queue-add-products');
    results.checks.openModal = await cdp.eval("document.querySelector('#creation-editor').open && getComputedStyle(document.querySelector('#creation-recapture-wrap')).display==='none'");
    await cdp.eval(`document.querySelector('#creation-values').value=${JSON.stringify([1,2,3].map(n=>`https://s.shopee.co.th/${prefix}-${n}`).join('\n'))}`);
    await physicalClick(cdp,'#creation-editor-submit');
    await waitFor(cdp,`ui.state.creation_queue.items.filter(r=>(r.link||'').includes(${JSON.stringify(prefix)})).length===3`,'3 queued products');
    results.checks.batch = await cdp.eval(`ui.state.creation_queue.paused && ui.state.creation_queue.items.filter(r=>(r.link||'').includes(${JSON.stringify(prefix)})).every(r=>!r.job_id && r.status==='queued')`);
    await cdp.eval(`window.__queueTestIds=ui.state.creation_queue.items.filter(r=>(r.link||'').includes(${JSON.stringify(prefix)})).map(r=>r.queue_id)`);
    await physicalClick(cdp,'[data-cq="move"][data-id="'+await cdp.eval('__queueTestIds[2]')+'"][data-direction="-1"]');
    await waitFor(cdp,`ui.state.creation_queue.items.filter(r=>(r.link||'').includes(${JSON.stringify(prefix)}))[1].queue_id===__queueTestIds[2]`,'reordered queue persisted');
    results.checks.reorder = await cdp.eval(`ui.state.creation_queue.items.filter(r=>(r.link||'').includes(${JSON.stringify(prefix)}))[1].queue_id===__queueTestIds[2]`);
    await physicalClick(cdp,'[data-cq="edit"][data-id="'+await cdp.eval('__queueTestIds[0]')+'"]');
    await cdp.eval(`document.querySelector('#creation-values').value=${JSON.stringify(`https://s.shopee.co.th/${prefix}-edited`)}`);
    await physicalClick(cdp,'#creation-editor-submit');
    await waitFor(cdp,"!document.querySelector('#creation-editor').open || Boolean(document.querySelector('#creation-editor-error').textContent)",'edit response');
    const editError = await cdp.eval("document.querySelector('#creation-editor-error').textContent");
    if(editError)throw new Error('Queue edit failed: '+editError);
    await waitFor(cdp,"ui.state.creation_queue.items.find(r=>r.queue_id===__queueTestIds[0]).link.endsWith('-edited')",'edited queue state');
    results.checks.edit = await cdp.eval(`ui.state.creation_queue.items.find(r=>r.queue_id===__queueTestIds[0]).link.endsWith('-edited')`);
    await physicalClick(cdp,'#queue-add-stories');
    await cdp.eval(`document.querySelector('#story-batch-topics').value=${JSON.stringify(`${prefix} เรื่องทดสอบหนึ่ง\n${prefix} เรื่องทดสอบสอง`)};updateStoryBatchDialog()`);
    await physicalClick(cdp,'#story-batch-submit');
    await waitFor(cdp,`ui.state.creation_queue.items.filter(r=>(r.topic||'').includes(${JSON.stringify(prefix)})).length===5`,'mixed queue');
    results.checks.mixed = await cdp.eval(`ui.state.creation_queue.counts.running===0 && ui.state.creation_queue.items.slice(-2).every(r=>r.mode==='story'&&!r.job_id)`);
    const types = ['product','story','all'];
    results.checks.filter = true;
    for(const type of types){
      const okay=await cdp.eval(`document.querySelector('#creation-filter').value=${JSON.stringify(type)};document.querySelector('#creation-filter').dispatchEvent(new Event('change'));document.querySelectorAll('#creation-list .cq-row').length===ui.state.creation_queue.items.filter(r=>${JSON.stringify(type)}==='all'||(r.mode||'story')===${JSON.stringify(type)}).length`);
      results.checks.filter &&= okay;
    }
    await cdp.eval("document.querySelector('#creation-filter').value='product';document.querySelector('#creation-filter').dispatchEvent(new Event('change'));showPage('creation')");
    for(const width of [1440,1024,768,390]){
      await cdp.send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
      await delay(400);
      const layout=await cdp.eval(`({overflow:document.documentElement.scrollWidth>innerWidth+2,duplicateIds:[...document.querySelectorAll('[id]')].map(n=>n.id).filter((id,i,a)=>a.indexOf(id)!==i)})`);
      results.layouts.push({width,...layout});
      const screenshot=await cdp.send('Page.captureScreenshot',{format:'png'});
      fs.writeFileSync(path.join(directory,`queue-${width}.png`),Buffer.from(screenshot.data,'base64'));
    }
    results.checks.stableButtons = await cdp.eval(`(()=>{const old=document.querySelector('#creation-list button');window.renderCreationQueue({...ui.state,product_progress:{percent:62,message:'fixture progress'}});return old===document.querySelector('#creation-list button')})()`);
    results.pageLayouts = [];
    for(const width of [1440,1024,768]){
      await cdp.send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
      for(const page of await cdp.eval('Object.keys(pageMeta)')){
        await cdp.eval(`showPage(${JSON.stringify(page)})`); await delay(180);
        const overflow=await cdp.eval('document.documentElement.scrollWidth>innerWidth+2');
        results.pageLayouts.push({page,width,overflow});
      }
    }
    results.checks.allPages = results.pageLayouts.length===42 && !results.pageLayouts.some(x=>x.overflow);
    results.checks.noJobs = await cdp.eval(`!ui.state.product_progress.active && !ui.state.story_progress.active && ui.state.creation_queue.items.filter(r=>(r.topic||'').includes(${JSON.stringify(prefix)})).every(r=>!r.job_id)`);
    results.errors = await cdp.eval('__queueErrors');
  } finally {
    // Remove only rows created by this audit, never user Jobs/assets/history.
    const current = await cdp.eval('ui.state.creation_queue');
    const created = current.items.filter(row=>!beforeIds.includes(row.queue_id) && String(row.topic||'').includes(prefix));
    for(const row of created) await cdp.eval(`__queueOriginalPost('creation_remove',{queue_id:${JSON.stringify(row.queue_id)}})`);
    await cdp.eval('(async()=>{postAction=__queueOriginalPost;await poll();})()');
    results.checks.cleanup = await cdp.eval(`ui.state.creation_queue.items.length===${baseline.items.length} && ui.state.creation_queue.counts.running===0`);
    results.actions = await cdp.eval('__queueActions');
    results.ok=Object.values(results.checks).every(Boolean)&&!results.layouts.some(x=>x.overflow||x.duplicateIds.length)&&!(results.errors||[]).length;
    fs.writeFileSync(path.join(directory,'queue-audit.json'),JSON.stringify(results,null,2));
    console.log(JSON.stringify(results,null,2));
  }
  if(!results.ok)throw new Error('Creation queue UI audit failed');
}

main().catch(error => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
}).finally(async () => {
  if (cdp) {
    try {
      await Promise.race([cdp.send("Browser.close"), delay(2000)]);
    } catch (_) {}
    cdp.close();
  }
  await delay(500);
  if (browser?.pid) {
    spawnSync("taskkill", ["/PID", String(browser.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
  }
  const tempRoot = path.resolve(os.tmpdir());
  const resolvedProfile = path.resolve(profile);
  if (resolvedProfile.startsWith(`${tempRoot}${path.sep}smartflow-ui-smoke-`)) {
    try {
      fs.rmSync(resolvedProfile, { recursive: true, force: true, maxRetries: 5, retryDelay: 150 });
    } catch (_) {}
  }
  process.exit(process.exitCode || 0);
});
