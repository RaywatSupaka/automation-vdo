// Real index.html and real stylesheets in an isolated browser. No server, queue, provider or saved data.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const html = read('web_ui/index.html');
const app = read('web_ui/app.js');
const shots = path.join(root, 'build', 'ui-foundation');

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1360, height: 860}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/desktop/media') {
        return route.fulfill({contentType: 'image/png', body: fs.readFileSync(path.join(root, 'assets', 'smartflow_logo.png'))});
      }
      return route.abort();
    });
    await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '').replace(/<link\b[^>]*>/gi, ''), {waitUntil: 'domcontentloaded'});
    for (const match of html.matchAll(/<link[^>]*href="\/desktop\/([^?" ]+)\.css[^" ]*"/g)) {
      await page.addStyleTag({content: read(`web_ui/${match[1]}.css`)});
    }
    await page.addScriptTag({content: read('web_ui/status_vocabulary.js')});
    // Run the real showPage() against the real DOM, with only its collaborators stubbed.
    const pageMeta = app.match(/const pageMeta = \{[\s\S]*?\r?\n\};/)[0];
    const showPage = app.match(/function showPage\([^)]*\) \{[\s\S]*?\r?\n\}\r?\n/)[0];
    const toggleHandler = app.match(/\$\$\('\.nav-group'\)\.forEach\(group => group\.addEventListener\('toggle'[^\r\n]*/)[0];
    await page.addScriptTag({content: `
      const ui = {state: null, activePage: 'dashboard'};
      const $ = (s, r = document) => r.querySelector(s);
      const $$ = (s, r = document) => [...r.querySelectorAll(s)];
      function setNewJobMenu() {} function setSidebarOpen() {} function poll() {}
      ${pageMeta}
      ${showPage}
      window.showPage = showPage;
      ${toggleHandler}`});
    let checks = 0;
    const ok = (condition, message) => { assert(condition, message); checks++; };

    // ---- Navigation: grouped, nothing lost, fits the default window --------------------------------------------------
    const routes = await page.locator('.navigation .nav-item').evaluateAll(nodes => nodes.map(n => n.dataset.page));
    ok(routes.length === 22 && new Set(routes).size === 22, 'all 22 pages are in the sidebar exactly once');
    ok(await page.locator('.nav-group').count() === 3, 'three collapsible groups');
    ok(await page.locator('.nav-group[open]').count() === 0, 'groups start closed');
    const closed = await page.evaluate(() => {
      const nav = document.querySelector('.navigation');
      const rows = [...document.querySelectorAll('.navigation > .nav-item:not(.hidden), .navigation > .nav-group > summary')]
        .filter(n => n.getClientRects().length);
      return {rows: rows.length, fits: nav.scrollHeight <= nav.clientHeight + 1, lowest: Math.max(...rows.map(n => n.getBoundingClientRect().bottom))};
    });
    ok(closed.rows === 10, `ten visible sidebar rows with groups closed, got ${closed.rows}`);
    ok(closed.fits && closed.lowest <= 860, 'closed sidebar needs no scrolling at 1360x860');

    await page.evaluate(() => showPage('voice'));
    ok(await page.locator('.nav-group[data-nav-group="settings"]').evaluate(n => n.open), 'the group holding the active page opens');
    ok(await page.locator('.nav-group[open]').count() === 1, 'other groups stay closed');
    ok(await page.locator('.nav-item[data-page="voice"]').getAttribute('aria-current') === 'page', 'active page is announced');
    ok(await page.locator('.navigation .nav-item.active').count() === 1, 'exactly one active item');
    await page.evaluate(() => showPage('queue'));
    ok(await page.locator('.nav-group[data-nav-group="publish"]').evaluate(n => n.open), 'publish group opens for its page');
    ok(await page.locator('.nav-item[data-page="voice"]').getAttribute('aria-current') === null, 'previous page is no longer current');
    await page.evaluate(() => showPage('dashboard'));
    ok(await page.locator('.nav-item[data-page="dashboard"]').evaluate(n => n.classList.contains('active')), 'dashboard can be reached again');

    // The active page's item must be visible, not hidden below the fold of the scrolling menu.
    await page.evaluate(() => showPage('logs'));
    ok(await page.evaluate(() => { const nav = document.querySelector('.navigation').getBoundingClientRect(), item = document.querySelector('.nav-item[data-page="logs"]').getBoundingClientRect(); return item.top >= nav.top - 1 && item.bottom <= nav.bottom + 1; }), 'the active item is scrolled into view');
    await page.evaluate(() => { document.querySelectorAll('.nav-group').forEach(g => { g.open = false; }); document.querySelector('.navigation').scrollTop = 0; });

    // Opening a group by hand scrolls its items into view too.
    await page.locator('.nav-group[data-nav-group="settings"] > summary').click();
    await page.waitForFunction(() => {
      const nav = document.querySelector('.navigation').getBoundingClientRect();
      const last = document.querySelector('.nav-item[data-page="logs"]').getBoundingClientRect();
      return last.bottom <= nav.bottom + 1 && last.top >= nav.top - 1;
    }, null, {timeout: 3000});
    checks++;
    await page.locator('.nav-group[data-nav-group="settings"] > summary').click();

    // Keyboard: a group header is a real focusable control that toggles with Enter.
    const castSummary = page.locator('.nav-group[data-nav-group="cast"] > summary');
    await castSummary.focus();
    await page.keyboard.press('Enter');
    ok(await page.locator('.nav-group[data-nav-group="cast"]').evaluate(n => n.open), 'Enter opens a group');
    await page.keyboard.press('Enter');
    ok(!(await page.locator('.nav-group[data-nav-group="cast"]').evaluate(n => n.open)), 'Enter closes it again');
    ok(await castSummary.evaluate(n => getComputedStyle(n).outlineStyle !== 'none'), 'focused group header shows a focus ring');

    // ---- Text: nothing below 11px; touch targets at least 44px high ------------------------------------------------------
    await page.evaluate(() => document.querySelectorAll('.nav-group').forEach(g => { g.open = true; }));
    const smallest = await page.evaluate(() => {
      let min = {size: 999, text: ''};
      for (const el of document.querySelectorAll('.sidebar *')) {
        if (!el.getClientRects().length) continue;
        const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
        if (!own) continue;
        const size = parseFloat(getComputedStyle(el).fontSize);
        if (size < min.size) min = {size, text: el.textContent.trim().slice(0, 30)};
      }
      return min;
    });
    ok(smallest.size >= 11, `sidebar text must be at least 11px, found ${smallest.size}px on "${smallest.text}"`);
    const rowHeights = await page.locator('.sidebar .nav-item:visible, .sidebar .nav-group > summary').evaluateAll(nodes => nodes.map(n => n.getBoundingClientRect().height));
    ok(Math.min(...rowHeights) >= 44, `sidebar rows are at least 44px tall, shortest ${Math.min(...rowHeights)}`);

    // ---- Colour: one palette, readable status pills, solid primary buttons -----------------------------------------------
    const contrast = (fg, bg) => {
      const lum = c => { const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); return .2126 * r + .7152 * g + .0722 * b; };
      const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
      return (a + .05) / (b + .05);
    };
    const tokens = await page.evaluate(() => { const s = getComputedStyle(document.documentElement); return ['--cyan', '--sf-cyan', '--surface', '--sf-surface', '--text', '--sf-copy'].map(k => s.getPropertyValue(k).trim().toLowerCase()); });
    ok(tokens[0] === tokens[1] && tokens[2] === tokens[3] && tokens[4] === tokens[5], 'both token families resolve to one palette');

    const pills = await page.evaluate(() => {
      const host = document.createElement('div');
      host.style.cssText = 'position:fixed;left:0;top:0;padding:12px;background:#0B0F17;display:flex;gap:8px;flex-wrap:wrap;width:900px;z-index:99999';
      host.id = 'pill-host';
      host.innerHTML = ['queued', 'running', 'action_required', 'failed', 'paused', 'completed', 'ready', 'cancelled', 'missing']
        .map(code => SmartFlowStatus.pill(code, {extraClass: 'status-pill'})).join('');
      document.body.append(host);
      return [...host.children].map(n => { const s = getComputedStyle(n); return {text: n.textContent, fg: s.color, bg: s.backgroundColor, size: parseFloat(s.fontSize)}; });
    });
    for (const pill of pills) {
      const bg = pill.bg === 'rgba(0, 0, 0, 0)' ? 'rgb(11, 15, 23)' : pill.bg;
      ok(contrast(pill.fg, bg) >= 4.5, `${pill.text}: contrast ${contrast(pill.fg, bg).toFixed(2)} (${pill.fg} on ${bg})`);
      ok(pill.size >= 12, `${pill.text}: pill text is ${pill.size}px`);
    }
    ok(new Set(pills.map(p => p.bg)).size >= 6, 'the six states are visually distinct');

    const primary = await page.evaluate(() => {
      const b = document.createElement('button'); b.className = 'button primary'; b.textContent = 'เริ่มสร้างเลย'; document.body.append(b);
      const s = getComputedStyle(b); const out = {fg: s.color, bg: s.backgroundColor, image: s.backgroundImage, height: b.getBoundingClientRect().height}; b.remove(); return out;
    });
    ok(primary.image === 'none', 'primary button is a solid colour, not a gradient');
    ok(contrast(primary.fg, primary.bg) >= 4.5, `primary button contrast ${contrast(primary.fg, primary.bg).toFixed(2)}`);
    ok(primary.height >= 40, `primary button height ${primary.height}`);

    ok(errors.length === 0, `no page errors: ${errors.join('; ')}`);
    fs.mkdirSync(shots, {recursive: true});
    await page.locator('#pill-host').screenshot({path: path.join(shots, 'status-pills.png')});
    await page.evaluate(() => { document.querySelector('#pill-host').remove(); document.activeElement?.blur(); });
    await page.evaluate(() => document.querySelectorAll('.nav-group').forEach(g => { g.open = false; }));
    await page.screenshot({path: path.join(shots, 'sidebar-closed.png'), clip: {x: 0, y: 0, width: 360, height: 860}});
    await page.evaluate(() => { showPage('voice'); });
    await page.screenshot({path: path.join(shots, 'sidebar-open.png'), clip: {x: 0, y: 0, width: 360, height: 860}});
    console.log(`UI foundation: ${checks} checks passed; screenshots in build/ui-foundation`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
