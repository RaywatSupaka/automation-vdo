const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 9338;
const APP_URL = process.argv[2] || "http://127.0.0.1:8765/desktop/#longvideo";
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

  await waitFor(cdp, "Boolean(ui.state?.ok)", "desktop state");
  const checks=[];
  for (const width of [1440,1024,768]) {
    await cdp.send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
    await cdp.eval("showPage('longvideo')");
    const layout=await cdp.eval(`(()=>{const p=document.querySelector('[data-view="longvideo"]');return {visible:getComputedStyle(p).display!=='none',overflow:document.documentElement.scrollWidth>innerWidth+2,buttons:[...p.querySelectorAll('button')].map(x=>x.textContent),count:document.querySelectorAll('#sidebar [data-page="longvideo"]').length}})()`);
    if(!layout.visible || layout.overflow || layout.count!==1) throw Error(JSON.stringify(layout));
    checks.push({width,...layout});
  }
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
  await delay(200);
  const shot = await cdp.send('Page.captureScreenshot',{format:'png'});
  const report = path.join(__dirname,'../docs/reports/long-video-270');
  fs.mkdirSync(report,{recursive:true});
  fs.writeFileSync(path.join(report,'long-video-ui.png'),Buffer.from(shot.data,'base64'));
  // Spy replaces the transport; no jobs, queue entries or paid requests are created.
  await cdp.eval("globalThis.smokeCalls=[]; postAction=async(action,payload)=>{smokeCalls.push({action,payload});return {ok:true,job_id:'OFFLINE-SMOKE'}}; poll=async()=>{}; document.querySelector('#long-topic').value='Offline long video'; document.querySelector('#long-duration').value='300'; document.querySelector('#long-scenes').value='40';");
  await physicalClick(cdp,'#create-longvideo');
  await cdp.eval("submitLongVideo(true)");
  const calls=await cdp.eval('smokeCalls');
  if(calls.length!==2 || calls[0].action!=='create_story' || calls[1].action!=='enqueue_long_video' || calls[0].payload.long_video.scene_count!=='40')throw Error(JSON.stringify(calls));
  console.log(JSON.stringify({ok:true,layout:checks,actions:calls.map(x=>x.action),paidRequests:0}));
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
