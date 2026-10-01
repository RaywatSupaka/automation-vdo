// Native offline DOM fixtures for the actual MAIN-world prepress resolver.
// Every document is fulfilled locally; this never loads a user's browser/profile.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.SMARTFLOW_TEST_PLAYWRIGHT_PACKAGE || 'playwright');

const source = fs.readFileSync(path.join(__dirname, '..', 'browser_extension', 'background.js'), 'utf8');
const marker = 'const resolveAiSendPrepressPoint = (';
const start = source.indexOf(marker);
const end = source.indexOf('const readInitialSendPoint =', start + marker.length);
assert(start >= 0 && end > start, 'Production prepress resolver extraction markers exist');
const production = source.slice(start, end) + '\nwindow.__fixtureResolve = resolveAiSendPrepressPoint;';
const FIXTURE_URL = 'https://chatgpt.com/c/smartflow-offline-send-fixture';
const DRAFT = 'Synthetic offline draft only.\nReturn one small JSON object.';
const VIEWPORT = {width:400, height:850};
const HTML = `<!doctype html><meta charset="utf-8"><title>Offline Send fixture</title>
<style>
  * { box-sizing:border-box; }
  html { scroll-behavior:auto; }
  body { margin:0; min-height:1900px; }
  #prompt-textarea { position:fixed; left:20px; bottom:20px; width:260px; height:80px; }
  #send { position:fixed; left:312px; bottom:28px; width:64px; height:48px;
    border:0; padding:0; background:#ddd; }
  #send svg { position:absolute; left:20px; top:12px; width:24px; height:24px; }
  #cover { position:fixed; z-index:99; background:#333; }
</style><textarea id="prompt-textarea"></textarea>
<button id="send" type="button" aria-label="ส่ง"><svg viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" fill="black"/></svg></button>`;

let checks = 0;
function equal(actual, expected, label) { checks++; assert.equal(actual, expected, label); }
function truth(value, label) { checks++; assert(value, label); }
const resolve = (page, {initial=false, focusTarget=false, key='', allowFallback=true, draft=DRAFT}={}) =>
  page.evaluate(({draft,initial,focusTarget,key,allowFallback}) =>
    window.__fixtureResolve(draft, initial, focusTarget, key, allowFallback),
  {draft,initial,focusTarget,key,allowFallback});

async function setup(page, options={}) {
  await page.setViewportSize(VIEWPORT);
  await page.goto(FIXTURE_URL);
  await page.addScriptTag({content:production});
  await page.evaluate(({draft,options}) => {
    document.querySelector('#prompt-textarea').value = options.draftMismatch ? 'Different synthetic draft' : draft;
    const button = document.querySelector('#send');
    button.querySelector('svg').style.pointerEvents = options.svgChild ? 'auto' : 'none';
    if (options.offscreen) {
      button.style.position = options.fixed ? 'fixed' : 'absolute';
      button.style.top = '1200px'; button.style.bottom = 'auto';
    }
    if (options.disabled) button.disabled = true;
    if (options.ariaDisabled) button.setAttribute('aria-disabled', 'true');
    if (options.stop) {
      button.setAttribute('aria-label', 'หยุด');
      // Existing ChatGPT submit IDs are reused for Stop; labels must win.
      button.setAttribute('data-testid', 'composer-submit-button');
    }
    if (options.overlay) {
      const rect = button.getBoundingClientRect();
      const cover = document.createElement('div'); cover.id = 'cover';
      Object.assign(cover.style, options.overlay === 'partial'
        ? {left:`${rect.left + 20}px`, top:`${rect.top + 15}px`, width:'24px', height:'18px'}
        : {left:`${rect.left - 2}px`, top:`${rect.top - 2}px`, width:`${rect.width + 4}px`, height:`${rect.height + 4}px`});
      document.body.append(cover);
    }
    window.__fixtureScrollCalls = [];
    const wrap = (owner, method) => {
      const original = owner[method];
      owner[method] = function(...args) {
        window.__fixtureScrollCalls.push({method, target:this.id || 'window'});
        return original.apply(this,args);
      };
    };
    wrap(Element.prototype,'scrollIntoView');
    wrap(Element.prototype,'scrollTo'); wrap(Element.prototype,'scrollBy');
    wrap(window,'scrollTo'); wrap(window,'scrollBy');
    window.__fixtureClicks = [];
    document.addEventListener('click', event => window.__fixtureClicks.push({
      trusted:event.isTrusted, onTarget:button === event.target || button.contains(event.target)
    }), true);
  },{draft:DRAFT,options});
}

async function snapshot(page) {
  return page.evaluate(() => {
    const gesture = window.__smartflowAiSendGestureV3;
    const preparation = window.__smartflowAiSendPreparationV1;
    const rect = document.querySelector('#send').getBoundingClientRect();
    return {scrollCalls:window.__fixtureScrollCalls, clicks:window.__fixtureClicks,
      rect:[rect.left,rect.top,rect.width,rect.height], prompt:document.querySelector('#prompt-textarea').value,
      preparation:preparation ? {scrollAttempted:preparation.scrollAttempted,
        buttonMatches:preparation.button === document.querySelector('#send'),
        editorMatches:preparation.editor === document.querySelector('#prompt-textarea')} : null,
      gesture:gesture ? {armed:gesture.armed, scrollAttempted:gesture.scrollAttempted,
        capture:!!(gesture.button && gesture.lastFrame && window.__smartflowAiSendGestureCaptureV3),
        trustedClickSeen:gesture.trustedClickSeen,
        releaseOnSendTarget:gesture.releaseOnSendTarget, events:gesture.events,
        targetChanged:gesture.targetChanged} : null};
  });
}

async function pointHitsTarget(page, point, label) {
  truth(point.ok, label + ' resolves: ' + JSON.stringify(point));
  truth(Number.isFinite(point.x) && Number.isFinite(point.y), label + ' has finite coordinates');
  truth(typeof point.key === 'string' && point.key.length > 0, label + ' has stable arm key');
  equal(point.label, 'ส่ง', label + ' keeps exact Thai label without test ID');
  truth(Number.isInteger(point.point_index) && point.point_index >= 0, label + ' records point index');
  truth(await page.evaluate(({x,y}) => {
    const button=document.querySelector('#send'), hit=document.elementFromPoint(x,y);
    return !!hit && (hit === button || button.contains(hit));
  },point), label + ' native hit test is the button or its child');
  equal((await snapshot(page)).prompt, DRAFT, label + ' never edits the draft');
}

async function rejectedWithoutScroll(page, options, allowFallback=true) {
  await setup(page, options);
  const point = await resolve(page,{initial:true,focusTarget:true,allowFallback});
  equal(point.ok,false,'Blocked control rejects: '+JSON.stringify(point));
  truth(typeof point.error === 'string' && point.error.length > 0,'Blocked control explains rejection');
  const proof = await snapshot(page);
  equal(proof.scrollCalls.length,0,'Invalid/fully visible/Gemini control cannot scroll');
  equal(proof.clicks.length,0,'Blocked control cannot click');
}

const cases = [
  ['center', async page => {
    await setup(page);
    const point = await resolve(page,{initial:true,focusTarget:true});
    await pointHitsTarget(page,point,'Unobstructed center');
    equal(point.point_strategy,'center','Normal button retains center strategy');
    equal(point.point_index,0,'Center remains point zero');
    const proof = await snapshot(page);
    equal(proof.scrollCalls.length,0,'Visible center needs no scroll');
    truth(proof.gesture && proof.gesture.capture,'Initial resolution records capture');
    equal(proof.gesture.scrollAttempted,false,'Initial center records unspent scroll');
    const armed = await resolve(page,{key:point.key});
    equal(armed.ok,true,'Unchanged center arms once');
    equal((await snapshot(page)).gesture.armed,true,'Arm key arms gesture');
    await page.mouse.click(armed.x,armed.y);
    const after = await snapshot(page);
    equal(after.clicks.length,1,'Native center has one fixture click');
    equal(after.gesture.trustedClickSeen,true,'Trusted center click is captured');
    equal(after.gesture.releaseOnSendTarget,true,'Trusted center release is on Send');
    truth(after.gesture.events.every(event => event.trusted && event.on_target),'Capture reports native target events');
    await page.evaluate(() => {window.__fixtureGesture = window.__smartflowAiSendGestureV3;});
    const again = await resolve(page);
    equal(again.ok,true,'Read after trusted click retains geometry');
    truth(await page.evaluate(() => window.__fixtureGesture === window.__smartflowAiSendGestureV3),
      'Read reuses gesture object');
    equal((await snapshot(page)).gesture.trustedClickSeen,true,'Read retains trusted click evidence');
    equal((await snapshot(page)).gesture.releaseOnSendTarget,true,'Read retains release evidence');
  }],
  ['svg_child', async page => {
    await setup(page,{svgChild:true});
    const point = await resolve(page,{initial:true,focusTarget:true});
    await pointHitsTarget(page,point,'SVG child center');
    equal(point.point_strategy,'center','SVG child hit remains center');
    equal(await page.evaluate(({x,y}) => document.elementFromPoint(x,y).tagName.toLowerCase(),point),'rect',
      'Native center actually targets SVG child');
    const armed = await resolve(page,{key:point.key});
    equal(armed.ok,true,'SVG child arms');
    await page.mouse.click(armed.x,armed.y);
    const proof = await snapshot(page);
    equal(proof.clicks.length,1,'SVG case makes one native fixture click');
    equal(proof.gesture.trustedClickSeen,true,'SVG child preserves trusted target recognition');
    equal(proof.gesture.releaseOnSendTarget,true,'SVG child release belongs to Send');
  }],
  ['partial_center_overlay', async page => {
    await setup(page,{overlay:'partial'});
    equal(await page.evaluate(() => {
      const r=document.querySelector('#send').getBoundingClientRect();
      return document.elementFromPoint(r.left+r.width/2,r.top+r.height/2).id;
    }),'cover','Fixture blocks actual center');
    const point = await resolve(page,{initial:true,focusTarget:true});
    await pointHitsTarget(page,point,'Partial center overlay');
    equal(point.point_strategy,'interior_point','Partial cover uses bounded interior point');
    truth(point.point_index > 0,'Partial cover uses a non-center index');
    equal((await snapshot(page)).scrollCalls.length,0,'Partial visible overlay does not scroll');
    const armed = await resolve(page,{key:point.key});
    equal(armed.ok,true,'Stable interior point arms');
    equal(armed.key,point.key,'Interior sample has stable arm key');
  }],
  ['fully_covered', page => rejectedWithoutScroll(page,{overlay:'full'})],
  ['offscreen_scroll_once', async page => {
    await setup(page,{offscreen:true});
    truth((await snapshot(page)).rect[1] > VIEWPORT.height,'Fixture starts below viewport');
    const point = await resolve(page,{initial:true,focusTarget:true});
    await pointHitsTarget(page,point,'Offscreen button');
    equal(point.point_strategy,'viewport_scroll','Offscreen button records viewport scroll');
    let proof = await snapshot(page);
    equal(proof.scrollCalls.length,1,'Offscreen button scrolls exactly once');
    equal(proof.gesture.scrollAttempted,true,'Gesture records spent scroll attempt');
    for (let i=0;i<3;i++) {
      const repeated = await resolve(page);
      equal(repeated.ok,true,'Visible recheck after scroll remains valid');
    }
    proof = await snapshot(page);
    equal(proof.scrollCalls.length,1,'Visible rereads cannot repeat scroll');
    equal(proof.clicks.length,0,'Scroll preparation does not click');
  }],
  ['fixed_offscreen_no_geometry_change', async page => {
    await setup(page,{offscreen:true,fixed:true});
    const before = (await snapshot(page)).rect;
    const point = await resolve(page,{initial:true,focusTarget:true});
    equal(point.ok,false,'Fixed offscreen target rejects after no movement');
    let proof = await snapshot(page);
    equal(JSON.stringify(proof.rect),JSON.stringify(before),'Native scroll cannot move fixed target');
    equal(proof.scrollCalls.length,1,'Fixed target uses at most one initial attempt');
    equal(proof.gesture,null,'Unsafe point never invents a gesture capture');
    truth(proof.preparation,'Failed initial scroll retains its preparation evidence');
    equal(proof.preparation.scrollAttempted,true,'Failed fixed scroll remains spent');
    truth(proof.preparation.buttonMatches && proof.preparation.editorMatches,
      'Failed scroll claim belongs to the exact button and editor');
    for (let i=0;i<3;i++) {
      const repeated = await resolve(page,{initial:true,focusTarget:true});
      equal(repeated.ok,false,'Repeated fixed-target initialization stays rejected');
      equal(repeated.reason,'target_blocked','Repeated initialization retains blocked-point reason');
    }
    proof = await snapshot(page);
    equal(proof.scrollCalls.length,1,'Fixed target rejection cannot repeat scroll');
    equal(proof.gesture,null,'Repeated unsafe point never creates gesture');
    equal(proof.clicks.length,0,'Fixed target never clicks');
  }],
  ['fully_visible_overlay_no_scroll', async page => {
    await setup(page);
    const first = await resolve(page,{initial:true,focusTarget:true});
    equal(first.ok,true,'Visible button starts valid');
    await page.evaluate(() => {
      const r=document.querySelector('#send').getBoundingClientRect();
      const cover=document.createElement('div');cover.id='cover';
      Object.assign(cover.style,{left:`${r.left-2}px`,top:`${r.top-2}px`,width:`${r.width+4}px`,height:`${r.height+4}px`});
      document.body.append(cover);
    });
    equal((await resolve(page)).ok,false,'Late visible full overlay rejects');
    equal((await snapshot(page)).scrollCalls.length,0,'Late overlay does not spend viewport recovery');
  }],
  ['disabled_no_recovery', page => rejectedWithoutScroll(page,{offscreen:true,disabled:true})],
  ['aria_disabled_no_recovery', page => rejectedWithoutScroll(page,{offscreen:true,ariaDisabled:true})],
  ['stop_no_recovery', page => rejectedWithoutScroll(page,{offscreen:true,stop:true})],
  ['draft_mismatch_no_recovery', async page => {
    await rejectedWithoutScroll(page,{offscreen:true,draftMismatch:true});
    equal((await resolve(page,{initial:true,focusTarget:true})).reason,'draft_mismatch','Draft mismatch stays typed');
    equal((await snapshot(page)).scrollCalls.length,0,'Repeated mismatched draft cannot scroll');
  }],
  ['arm_after_viewport_change', async page => {
    await setup(page);
    const point = await resolve(page,{initial:true,focusTarget:true});
    equal(point.ok,true,'Initial arm capture succeeds');
    const before = (await snapshot(page)).rect;
    await page.setViewportSize({width:420,height:VIEWPORT.height});
    equal(JSON.stringify((await snapshot(page)).rect),JSON.stringify(before),
      'Viewport changed without moving fixed button, isolating viewport capture');
    const armed = await resolve(page,{key:point.key});
    equal(armed.ok,false,'Changed viewport rejects previously captured arm key');
    equal((await snapshot(page)).gesture.armed,false,'Changed viewport cannot arm');
    equal((await snapshot(page)).scrollCalls.length,0,'Arm rejection cannot recover position');
  }],
  ['gemini_center_overlay_unchanged', page => rejectedWithoutScroll(page,{overlay:'partial'},false)],
  ['gemini_offscreen_unchanged', page => rejectedWithoutScroll(page,{offscreen:true},false)],
];

(async () => {
  const requested = process.argv.find(arg => arg.startsWith('--case='))?.slice(7);
  const requestedNames = requested ? requested.split(',') : null;
  const selected = requestedNames ? cases.filter(([name]) => requestedNames.includes(name)) : cases;
  assert(selected.length > 0 && (!requestedNames || selected.length === requestedNames.length),'Requested fixtures exist');
  const browser = await chromium.launch({headless:true,
    ...(process.env.SMARTFLOW_TEST_CHROMIUM ? {executablePath:process.env.SMARTFLOW_TEST_CHROMIUM} : {})});
  let scenarios = 0, fulfilledDocuments = 0, blockedRequests = 0;
  try {
    const context = await browser.newContext({viewport:VIEWPORT,serviceWorkers:'block'});
    await context.route('**/*', route => {
      if (route.request().isNavigationRequest() && route.request().url() === FIXTURE_URL) {
        fulfilledDocuments++;
        return route.fulfill({contentType:'text/html; charset=utf-8',body:HTML});
      }
      blockedRequests++;
      return route.abort();
    });
    const page = await context.newPage();
    for (const [name, run] of selected) {
      try { await run(page); }
      catch (error) { error.message = name + ': ' + error.message; throw error; }
      scenarios++;
    }
    equal(blockedRequests,0,'Fixture contains no unhandled resource requests');
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify({ok:true,nativeDom:true,scenarios,checks,
    fulfilledDocuments,blockedRequests,providerNetworkRequests:0,providerActions:0,ownedBrowserClosed:true}));
})().catch(error => {console.error(error);process.exitCode=1;});
