// Meta is a separate, durable video adapter. Never invoke the Flow helper here.
const KEY = 'smartflowMetaVideoRequestsV1';
const OWNERS = 'smartflowMetaTabOwnersV1';
const HOME = 'https://www.meta.ai/';
const normal = value => String(value || '').replace(/\s+/g, ' ').trim();

export function metaScenePlanMatches(row, current, allowLegacyActive = false) {
  const left=row?.scene_video_plan, right=current?.scene_video_plan;
  if (!left && !right) return !row?.scene_video_plan_required && !current?.scene_video_plan_required
    || Boolean(allowLegacyActive && current?.scene_video_plan_legacy_active
      && ['send_intent','submitted','generating','download_intent','downloading','stored','needs_attention'].includes(row?.stage));
  const fields=['version','scene_index','plan_revision','selection_id','attempt_id','provider','settings_sha256'];
  return Boolean(left && right && left.version===1 && left.provider==='meta_ai'
    && left.scene_index===Number(row.index) && Number.isInteger(left.plan_revision) && left.plan_revision>=0
    && ['selection_id','attempt_id','settings_sha256'].every(key=>typeof left[key]==='string' && left[key])
    && fields.every(key=>left[key]===right[key]));
}

// Only the observed infrastructure sentence is exempt from the broad safety
// keyword gate. Any additional policy/quota statement still takes precedence.
export function metaSafetyServiceOutage(text) {
  return /^the video (?:couldn't|could not) be generated right now\s*[—–:-]\s*the safety check service is temporarily unavailable[.!](?:\s|$)/.test(normal(text).replace(/’/g, "'").toLowerCase());
}

export function metaReplyFailure(text) {
  const value = normal(text).replace(/’/g, "'").toLowerCase();
  const outage = metaSafetyServiceOutage(value);
  const policyText = outage ? value.replace(/^the video (?:couldn't|could not) be generated right now\s*[—–:-]\s*the safety check service is temporarily unavailable[.!]/, '') : value;
  if (/polic|safety|guideline|not allowed|prohibited|copyright|นโยบาย|ความปลอดภัย|ละเมิด|ไม่อนุญาต/.test(policyText)) return 'policy';
  if (/rate.?limit|quota|limit reached|reached.{0,30}limit|too many|ขีดจำกัด|โควตา/.test(value)) return 'quota';
  if (/\b(?:log|sign)[ -]?in\b|\bauthenticate\b|เข้าสู่ระบบ/.test(value)) return 'authentication_required';
  if (outage) return 'transient_service_error';
  if (/^ขออภัย ดูเหมือนว่าทางฝั่งของฉันจะเกิดปัญหาบางอย่าง โปรดลองอีกครั้ง[.!?。]?$/.test(value)) return 'technical_redesign';
  if (/\b(?:server|network) error\b|\bservice (?:is )?(?:temporarily )?unavailable\b|ข้อผิดพลาด(?:ของ|จาก)?(?:เซิร์ฟเวอร์|เครือข่าย)/.test(value) &&
      /(?:could not|couldn't|cannot|can't|unable to|failed to|wasn't able to|was not able to)\s+(?:be\s+)?(?:create|generate|make)(?:d)?\b|without producing (?:a video|video|media)|ไม่ได้สร้าง(?:วิดีโอ|คลิป)|สร้าง(?:วิดีโอ|คลิป)ไม่สำเร็จ/.test(value)) return 'transient_service_error';
  if (/วิดีโอ.{0,50}(?:สร้าง|ทำ).{0,12}ไม่ได้|ภาพต้นฉบับ.{0,100}ไม่สามารถ.{0,45}(?:วิดีโอ|เคลื่อนไหว)|(?:image|starting frame).{0,80}(?:cannot|can.t|unable).{0,40}(?:video|animate)/.test(value)) return 'image_not_viable';
  if (/\bfile unavailable\b|\bvideo (?:file )?(?:is )?unavailable\b|ไฟล์(?:วิดีโอ)?ไม่พร้อมใช้งาน|(?:couldn't|could not|can't|cannot|unable to|failed to|wasn't able to|was not able to)\s+(?:create|generate|make)\b|ไม่สามารถ(?:สร้าง|ทำตาม)|สร้าง(?:วิดีโอ|คลิป)ไม่สำเร็จ/.test(value)) return 'completed_no_video';
  return '';
}

export function metaChoiceOffer(answer, aspectRatio = '9:16') {
  const value = normal(answer);
  if (value.length > 12000 || ['policy', 'quota', 'authentication_required'].includes(metaReplyFailure(value))) return null;
  const markers = [...value.matchAll(/(?:\boption|(?:ตัวเลือก|ทางเลือก)(?:ที่)?|ข้อ)\s*([1-9])\s*[-:–—.)]/gi)];
  if (markers.length !== 2 || markers[0][1] !== '1' || markers[1][1] !== '2' || !/video|วิดีโอ|คลิป/i.test(value)) return null;
  const tail = value.slice(markers[1].index + markers[1][0].length);
  const ask = /(?:want me to|would you like me to|shall i)\s+(?:generate|create|make)|which (?:option|version)|(?:ต้องการ|อยาก)(?:ให้)?(?:ฉัน|ผม)?.{0,35}(?:สร้าง|เลือก)|เลือก(?:ข้อ|ตัวเลือก|ทางเลือก).{0,20}(?:ไหน|ใด)/i.exec(tail);
  if (!ask) return null;
  const first = value.slice(markers[0].index + markers[0][0].length, markers[1].index).trim();
  const selected = tail.slice(0, ask.index).trim();
  if (!first || selected.length < 5 || selected.length > 4000) return null;
  const orientation = aspectRatio === '16:9' ? 'landscape 16:9' : 'vertical 9:16';
  return {number: 2, text: selected, proposal_text: value,
    prompt: `I choose option 2: ${selected}\nCreate that actual playable ${orientation} video now, using the image already attached in this conversation. Keep the characters and audio/dialogue instructions from my original request. No text, captions or watermark.`};
}

export function metaSafeOffer(answer, aspectRatio = '9:16') {
  const value = normal(answer);
  if (!value || value.length > 12000 || !['image_not_viable', 'completed_no_video'].includes(metaReplyFailure(value))) return null;
  const orientation = aspectRatio === '16:9' ? 'landscape 16:9' : 'vertical 9:16';
  // M6 is a prose choice, not a native preference vote or a blanket yes.
  // Accept only the observed first clothing adjustment; ambiguous choices keep
  // the existing no-video recovery instead of silently changing story/style.
  if (/อยากให้ลองทำเป็นเวอร์ชันไหน/.test(value)) {
    const clothingChoice = /เช่น\s+ปรับชุดให้มิดชิดขึ้นเป็นเสื้อยืดกับกางเกงขายาว\s+หรือทำเป็นสไตล์แอนิเมชัน\/ภาพวาด\s+แบบไม่มีการเน้นสรีระ\s+อยากให้ลองทำเป็นเวอร์ชันไหนดี(?:คะ|ครับ)?\??$/.test(value);
    if (!clothingChoice || !/ฉันช่วยทำเวอร์ชันที่ปลอดภัยขึ้นให้ได้\s+โดยยังคงไอเดียเดิมไว้ทั้งหมด/.test(value) ||
        /เปลี่ยน(?:ตัวละคร|บุคคล|สินค้า|บท|เสียง|สไตล์)|แทนที่(?:สินค้า|ตัวละคร)|เพิ่ม(?:บทพูด|เพลง)|(?:ตัวเลือก|ทางเลือก|\boption)\s*[1-9]/i.test(value)) return null;
    const prompt = 'Yes. Use only the first adjustment you offered: a modest T-shirt and long trousers. ' +
      'Keep the original characters, product identity and visibility, setting, action, visual style, ' +
      'exact dialogue and audio settings unchanged. Do not choose the alternative animation/drawing style. ' +
      'If changing the clothing would replace or hide the product, or require changing those other details, ' +
      'report that conflict truthfully instead of inventing a different scene. ' +
      `Generate exactly one actual playable ${orientation} video, not a still image or text description. ` +
      'Do not offer alternatives or ask me to choose or confirm again. No added text or watermark.';
    return {kind:'safe_revision',selection:'first_clothing_only',number:1,
      text:'Meta-proposed modest clothing only',proposal_text:value,prompt};
  }
  if (!/ปลอดภัยขึ้น|แต่งกายให้มิดชิด|safer (?:version|scene)|compliant (?:version|scene)|different take|more covered outfit|wider framing/i.test(value) ||
      !/ฉันช่วยทำ|ช่วยทำเวอร์ชัน|ฉันสามารถสร้างวิดีโอใหม่ให้ได้ด้วยภาพเริ่มต้นที่ฉันสร้างขึ้นเอง|i can (?:help with|make|create|generate)/i.test(value) ||
      !/อยากให้.{0,100}(?:ทำ|สร้าง).{0,30}ไหม\??|อยากให้ฉันลองทำเวอร์ชันที่ปรับเฟรมให้ปลอดภัยขึ้นแต่ยังคงฮุคนี้ไว้เลยไหม(?:คะ|ครับ)?\??|(?:would you like|want me to|let me know if you.d like me to).{0,100}(?:make|create|generate|try)/i.test(value)) return null;
  const prompt = 'Yes, please make the safer version you just offered. Choose compliant clothing, framing, '
    + `and a revised starting visual if needed. Generate exactly one actual playable ${orientation} video, `
    + 'not a still image or a text description. Preserve the harmless hook, scene action, product identity '
    + 'where possible, and the original Thai spoken line and audio settings. Do not ask me to choose or confirm '
    + 'again. If video generation is unavailable, report that truthfully.';
  return {kind: 'safe_revision', number: 0, text: 'Meta-proposed safer version', proposal_text: value, prompt};
}

export function metaFollowupOffer(answer, aspectRatio = '9:16') {
  return metaChoiceOffer(answer, aspectRatio) || metaSafeOffer(answer, aspectRatio);
}

export function metaComparisonOffer(branches, aspectRatio = '9:16') {
  if (!Array.isArray(branches) || branches.length !== 2 || branches.some(branch =>
    !branch || typeof branch.text !== 'string' || !branch.text || branch.text.length > 12000 ||
    branch.complete !== true || branch.truncated !== false || branch.busy !== false || branch.video_count !== 0)) return null;
  for (let index = 0; index < branches.length; index++) {
    const offer = metaFollowupOffer(branches[index].text, aspectRatio);
    if (!offer) continue;
    return {...offer, proposal_branch:index, proposal_branches:branches.map(branch => normal(branch.text)),
      prompt:`Use response ${index + 1} only, with this selected proposal; disregard the other response.\n${offer.prompt}`};
  }
  return null;
}

function metaWirePrompt(prompt) {
  const helper = globalThis.SmartFlowSingleAnswer;
  if (!helper || typeof helper.wrap !== 'function' || typeof helper.has !== 'function')
    throw new Error('AI_RESPONSE_FORMAT_NOT_READY');
  const wire = helper.wrap(prompt);
  if (!helper.has(wire)) throw new Error('AI_RESPONSE_FORMAT_NOT_READY');
  return wire;
}

async function metaVideoAssetDigest(value) {
  const bytes = new TextEncoder().encode(value);
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
    .map(byte => byte.toString(16).padStart(2,'0')).join('');
}

// This function is serialised into the owned tab. Do not depend on module globals.
export function inspectMetaDOM(prompt, imageName, choice = null, sendOrigin = null) {
  const visible = node => !!node && !!(node.getBoundingClientRect().width && node.getBoundingClientRect().height);
  const text = value => String(value || '').replace(/\s+/g, ' ').trim();
  const point = node => {
    if (!visible(node) || node.disabled || node.getAttribute('aria-disabled') === 'true') return null;
    const rect = node.getBoundingClientRect();
    const x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
    const hit = document.elementFromPoint(x, y);
    return hit && (node === hit || node.contains(hit)) ? {x, y} : null;
  };
  const labelled = (root, names) => [...root.querySelectorAll('button,[role="button"]')]
    .find(node => names.includes(text(node.getAttribute('aria-label') || node.textContent)) && visible(node));
  const answerBodyText = root => {
    const parts = [], walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const parent = node.parentElement;
      if (!parent || parent.closest('button,[role="button"],[hidden],[aria-hidden="true"],script,style')) continue;
      let hidden = false;
      for (let element = parent; element; element = element.parentElement) {
        const style = getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden') { hidden = true; break; }
        if (element === root) break;
      }
      if (!hidden) parts.push(node.nodeValue || '');
    }
    return text(parts.join(' '));
  };
  const responseBusy = root => root.matches('[aria-busy="true"],[role="progressbar"]') ||
    !![...root.querySelectorAll('[aria-busy="true"],[role="progressbar"]')].find(visible);
  const unavailable = root => /\bfile unavailable\b|\bvideo (?:file )?(?:is )?unavailable\b|ไฟล์(?:วิดีโอ)?ไม่พร้อมใช้งาน/i.test(root.innerText || '');
  const responseComplete = root => !!labelled(root, ['คัดลอกการตอบกลับ', 'Copy response', 'Copy']) &&
    !!labelled(root, ['ถูกใจการตอบกลับนี้', 'ไม่ถูกใจการตอบกลับนี้', 'Like response', 'Dislike response', 'Good response', 'Bad response']);
  const preferenceButtonsFor = root => [...root.querySelectorAll('button,[role="button"]')]
    .filter(node => visible(node) && /^(?:ฉันชอบการตอบกลับนี้มากกว่า|I prefer this response)$/i.test(text(node.textContent)));
  const separatedBranches = replies => {
    const roots = replies.filter(node => !replies.some(other => other !== node && other.contains(node)));
    if (roots.length !== 2 || roots.some(root => preferenceButtonsFor(root).length !== 1)) return [];
    return roots.map(root => {
      const value = answerBodyText(root);
      return {text:value.slice(0,12000), complete:responseComplete(root) || unavailable(root),
        truncated:value.length > 12000, busy:responseBusy(root), video_count:root.querySelectorAll('video').length};
    });
  };
  const editors = [...document.querySelectorAll('[role="textbox"][contenteditable="true"][data-lexical-editor="true"]')].filter(visible);
  const editor = editors.length === 1 ? editors[0] : null;
  const images = editor ? [...editor.querySelectorAll('img')] : [];
  const imageReady = images.length === 1 && images[0].complete && images[0].naturalWidth > 32 && images[0].naturalHeight > 32;
  let busy = !![...(editor?.parentElement || document).querySelectorAll('[aria-busy="true"],[role="progressbar"]')].find(visible);
  const articles = [...document.querySelectorAll('[role="article"]')];
  const users = articles.filter(node => /ข้อความของคุณ|your message/i.test(node.getAttribute('aria-label') || ''));
  const matched = users.filter(node => text(node.innerText).includes(text(prompt)) &&
    [...node.querySelectorAll('img')].some(img => img.complete && img.naturalWidth > 32 && (img.alt === imageName || !img.alt)));
  const original = matched.length === 1 && (users.length === 1 || (choice && users.length === 2)) ? matched[0] : null;
  const repliesAfter = user => {
    if (!user) return [];
    const start = articles.indexOf(user) + 1;
    const next = articles.findIndex((n, i) => i >= start && users.includes(n));
    return articles.slice(start, next < 0 ? undefined : next)
      .filter(node => /การตอบกลับของ Meta AI|Meta AI.*response/i.test(node.getAttribute('aria-label') || ''));
  };
  const proposals = repliesAfter(original);
  const proposal = proposals.length === 1 ? proposals[0] : null;
  const proposalBranches = separatedBranches(proposals);
  const branchChoice = Array.isArray(choice?.proposal_branches);
  const proposalMatches = branchChoice ? proposalBranches.length === 2 &&
    Number.isInteger(choice.proposal_branch) && choice.proposal_branch >= 0 && choice.proposal_branch < 2 &&
    proposalBranches.every((branch,index) => branch.text === choice.proposal_branches[index] &&
      branch.complete && !branch.truncated && !branch.busy && branch.video_count === 0) &&
    proposalBranches[choice.proposal_branch].text === choice.proposal_text :
    !!proposal && (!choice || text(proposal.innerText) === choice.proposal_text) && proposal.querySelectorAll('video').length === 0;
  const followups = original && choice ? users.filter(node => node !== original &&
    articles.indexOf(node) > articles.indexOf(original) && text(node.innerText).includes(text(choice.prompt))) : [];
  const matchedChoice = followups.length === 1 && users.length === 2 && proposalMatches;
  const user = choice ? (matchedChoice ? followups[0] : null) : original;
  const after = repliesAfter(user);
  const answer = after.length === 1 ? after[0] : null;
  // Native preference experiments are provider UI, not an Option 1/2 prompt.
  // Read only replies to this exact user; never vote or choose a follow-up chip.
  const roots = after.filter(node => !after.some(other => other !== node && other.contains(node)));
  const preferenceButtons = roots.flatMap(preferenceButtonsFor);
  const comparison = !!user && roots.length >= 1 && roots.length <= 2 && preferenceButtons.length === 2;
  const scope = comparison ? roots : answer ? [answer] : [];
  const videos = [...new Set(scope.flatMap(root => [...root.querySelectorAll('video')]))];
  const isStop = node => {
    // Exact action labels only: a conversation title can contain "หยุด"/"stop".
    const actionLabel = value => /^(?:stop(?: generating(?: response)?| generation| response| responding)?|หยุด(?:(?:การ)?(?:สร้าง(?:คำตอบ|วิดีโอ)?|ตอบ(?:กลับ)?))?)$/i.test(text(value));
    if (['aria-label','title'].some(key=>actionLabel(node?.getAttribute?.(key)||'')) ||
        /^(?:stop|stop[-_](?:button|generating|generation|response|responding)|stop[-_](?:generating|generation|response)[-_]button)$/i.test(text(node?.getAttribute?.('data-testid')||''))) return true;
    const composerScope = editor?.closest('form,[role="form"]') || editor?.parentElement;
    return !!composerScope && composerScope.contains(node) && actionLabel(node?.textContent||'');
  };
  const stop = [...document.querySelectorAll('button,[role="button"]')].some(node=>visible(node)&&isStop(node));
  const answerBusy = scope.some(responseBusy);
  const answerBranches = comparison ? separatedBranches(after) : [];
  const answerText = text(scope.map(answerBodyText).join('\n'));
  const allUnavailable = roots.length === 2 ? roots.every(unavailable) :
    (answerText.match(/\bfile unavailable\b|\bvideo (?:file )?(?:is )?unavailable\b|ไฟล์(?:วิดีโอ)?ไม่พร้อมใช้งาน/gi) || []).length === 2;
  const answerComplete = comparison ? (allUnavailable || videos.length > 0 ||
    answerBranches.length === 2 && answerBranches.every(branch => branch.complete)) : !!answer && responseComplete(answer);
  const playable = node => node.readyState >= 2 && node.videoWidth > 0 && Number.isFinite(node.duration) && node.duration > 0;
  const video = videos.find(node => playable(node) && /^https:\/\//.test(node.currentSrc || node.src || '')) ||
    (videos.length === 1 ? videos[0] : null);
  const dialogs = [...document.querySelectorAll('[role="dialog"]')].filter(visible);
  const uploadDialog = dialogs.find(node => /เพิ่มสื่อและไฟล์|Add media and files/i.test(node.innerText || node.getAttribute('aria-label') || ''));
  // Meta portals the dialog, but keeps TWO hidden file inputs in desktop/mobile
  // composers. The input belongs to the visible editor, not to the dialog DOM.
  let composerRoot = editor?.parentElement;
  while (composerRoot && !composerRoot.querySelector('input[type="file"]')) composerRoot = composerRoot.parentElement;
  if (composerRoot) busy = busy || !![...composerRoot.querySelectorAll('[aria-busy="true"],[role="progressbar"]')].find(visible);
  const files = uploadDialog && composerRoot ? [...composerRoot.querySelectorAll('input[type="file"]')]
    .filter(node => !node.disabled && visible(node.parentElement) && /image\//.test(node.accept)) : [];
  // Mark a unique composer-owned input, never the first file input on the page.
  document.querySelectorAll('[data-smartflow-meta-file]').forEach(node => node.removeAttribute('data-smartflow-meta-file'));
  if (files.length === 1) files[0].setAttribute('data-smartflow-meta-file', 'current');
  const sendButton = labelled(document, ['ส่ง', 'Send']);
  // A pressed Meta button animates its CSS scale. Its computed center can
  // drift by a fraction of a pixel while the original mouse point is still
  // on the very same button. Check that point, not floating-point equality.
  const originHit = sendOrigin && Number.isFinite(sendOrigin.x) && Number.isFinite(sendOrigin.y)
    ? document.elementFromPoint(sendOrigin.x, sendOrigin.y) : null;
  const sendOriginMatches = sendOrigin ? !!sendButton && !!originHit &&
    (originHit === sendButton || sendButton.contains(originHit)) : null;
  // Retain DOM node identity across inspections, not only reused coordinates.
  const targets = document.__smartflowMetaSendTargets ||
    (document.__smartflowMetaSendTargets = {nodes:new WeakMap(), next:0});
  if (sendButton && !targets.nodes.has(sendButton)) targets.nodes.set(sendButton, String(++targets.next));
  return {
    // A filled, tall editor can be readable while its center is clipped or
    // covered. Presence/text validation must not depend on a mouse target.
    composerFound: !!editor, composerCount: editors.length,
    composer: point(editor), composerText: text(editor?.innerText), imageCount: images.length,
    imageReady, imageName: images[0]?.alt || '', imageSource: images[0]?.currentSrc || images[0]?.src || '', busy,
    attach: point(labelled(document, ['เพิ่มไฟล์แนบ', 'Add attachment'])),
    send: isStop(sendButton) ? null : point(sendButton), sendTarget: sendButton ? targets.nodes.get(sendButton) : '', sendOriginMatches, uploadDialog: !!uploadDialog, fileInput: files.length === 1,
    matchedUser: !!user, matchedOriginal: !!original, matchedChoice, userCount: users.length, stop,
    proposalText: branchChoice && proposalMatches ? choice.proposal_text : text(proposal?.innerText).slice(0, 12000),
    proposalMatches,
    proposalVideoCount: proposals.reduce((sum,node) => sum + node.querySelectorAll('video').length,0),
    proposalBusy: proposals.some(responseBusy),
    answerText: answerText.slice(0, 12000), answerTruncated: answerText.length > 12000,
    answerComplete, answerBusy, comparison, answerBranches, videoCount: videos.length,
    videoCandidates: videos.map(node => ({src:node.currentSrc || node.src || '', ready:playable(node)})),
    videoReady: !!video && !stop && !answerBusy && playable(video),
    videoSrc: video?.currentSrc || video?.src || '',
    conversation: /^\/prompt\/[\w-]+\/?$/.test(location.pathname) ? location.origin + location.pathname.replace(/\/$/, '') : '',
    observedURL: location.origin + location.pathname,
    documentReady: document.readyState === 'complete',
    pageVideoCount: document.querySelectorAll('video').length,
    pageMessageCount: articles.length,
    pageBusy: !![...document.querySelectorAll('[aria-busy="true"],[role="progressbar"]')].find(visible),
    pageDialog: !![...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].find(visible),
    login: !!labelled(document, ['เข้าสู่ระบบ', 'Log in', 'Log In']),
  };
}

export class MetaVideoAdapter {
  constructor({api, redesign, chromeAPI = globalThis.chrome}) {
    this.api = api;
    this.redesign = redesign;
    this.chrome = chromeAPI;
    this.running = false;
    this.opening = new Map();
    this.routeObservations = new Map();
    // A worker restart must observe a fresh stable pair; persisted samples are
    // diagnostics, not permission to retry after just one new DOM read.
    this.failureObservations = new Map();
  }
  async records() { return (await this.chrome.storage.local.get(KEY))[KEY] || {}; }
  async owns(row) {
    const owners = (await this.chrome.storage.session.get(OWNERS))[OWNERS] || {};
    return owners[row.tabId] === row.request_id;
  }
  async own(row) {
    const owners = (await this.chrome.storage.session.get(OWNERS))[OWNERS] || {};
    owners[row.tabId] = row.request_id;
    await this.chrome.storage.session.set({[OWNERS]: owners});
  }
  async save(row) {
    const records = await this.records();
    records[row.request_id] = row;
    await this.chrome.storage.local.set({[KEY]: records});
  }
  async assertSceneOwner(row, allowLegacyActive = false) {
    if (!row.scene_video_plan && !row.scene_video_plan_required) return;
    const {package: current}=await this.api(`/api/meta-video/package?job_id=${encodeURIComponent(row.job_id)}&index=${row.index}`);
    if (!metaScenePlanMatches(row,current,allowLegacyActive) || current.request_id!==row.request_id || current.context_id!==row.context_id
        || row.paused || row.closed) throw Error('META_SCENE_PLAN_STALE');
  }
  async event(row, stage, extra = {}) {
    const response = await this.api('/api/meta-video/event', {job_id: row.job_id, index: row.index,
      request_id: row.request_id, context_id: row.context_id, stage,
      conversation_url: row.conversation_url || '',
      ...(row.send_diagnostic ? {send_diagnostic:row.send_diagnostic} : {}), ...extra,
      ...(row.scene_video_plan ? {scene_video_plan:row.scene_video_plan,video_provider:'meta_ai'} : {})});
    if ((row.scene_video_plan || response.receipt?.scene_video_plan)
        && !metaScenePlanMatches(row,response.receipt)) throw Error('META_SCENE_PLAN_ACK_CHANGED');
    if (row.stage !== stage) delete row.waitReason;
    const {choice_send_authorized, ...saved} = response.receipt;
    Object.assign(row, saved);
    await this.save(row);
    return response.receipt;
  }
  async wait(row, reason, message) {
    // Keep the durable stage and show the actual blocker in the desktop. Emit
    // once per changed reason, not every polling tick or as a new request.
    if (row.waitReason === reason) return;
    await this.event(row, row.stage, {message});
    row.waitReason = reason;
    await this.save(row);
  }
  async adoptRetry(row, receipt) {
    const redesigned=receipt.redesign_previous_request_id===row.request_id;
    if (!redesigned && (receipt.retry_previous_request_id !== row.request_id || receipt.context_id !== row.context_id)) return;
    // Retire the old worker AFTER persisting/opening the successor. A crash can
    // replay this handoff without a new send. Keep the old conversation intact.
    await this.open({job_id: row.job_id, shot_index: row.index});
    if(redesigned&&receipt.redesign_completed_id){
      const key=`smartflowMetaRedesign:${receipt.redesign_completed_id}`;
      const helper=(await this.chrome.storage.local.get(key))[key];
      if(helper?.request_id===row.request_id){
        delete helper.image;helper.phase='committed';await this.chrome.storage.local.set({[key]:helper});
      }
    }
    row.closed = true; row.superseded_by = receipt.request_id;
    this.failureObservations.delete(row.request_id);
    this.routeObservations.delete(row.request_id);
    await this.save(row);
  }
  async retryCompleted(row, state, observation, redesign = false) {
    const {receipt} = await this.api('/api/meta-video/event', {job_id: row.job_id, index: row.index,
      request_id: row.request_id, context_id: row.context_id, stage: redesign ? 'redesign_prepare' : 'retry_prepared',
      conversation_url: row.conversation_url, retry_evidence: {
        composer_empty: !state.composerText && !state.imageCount && !state.uploadDialog,
        matched_request: state.matchedUser === true, answer_complete: state.answerComplete === true,
        answer_truncated: state.answerTruncated, stop: state.stop,
        busy: !!(state.busy || state.answerBusy || state.pageBusy), video_count: state.videoCount,
        answer_text: state.answerText, samples: observation.samples, stable_ms: Date.now() - observation.since,
        choice_prompt: row.choice?.prompt || '',
      }, ...(row.scene_video_plan ? {scene_video_plan:row.scene_video_plan} : {})});
    if (receipt.request_id !== row.request_id) await this.adoptRetry(row, receipt);
    else { delete row.waitReason; Object.assign(row, receipt); await this.save(row); }
  }
  async open(command) {
    const key = `${command.job_id}:${command.shot_index}`;
    if (this.opening.has(key)) return this.opening.get(key);
    const pending = this.openFreshContext(command);
    this.opening.set(key, pending);
    try { return await pending; }
    finally { if (this.opening.get(key) === pending) this.opening.delete(key); }
  }
  async freshStart(row, evidence, routeEvidence = null) {
    // Explicit user policy: abandon this interrupted browser attempt, not its
    // saved scene assets. The desktop atomically archives and fences the owner.
    const {receipt} = await this.api('/api/meta-video/event', {
      job_id:row.job_id, index:row.index, request_id:row.request_id, context_id:row.context_id,
      stage:'fresh_start', fresh_start_evidence:evidence,
      ...(row.scene_video_plan ? {scene_video_plan:row.scene_video_plan} : {}),
      ...(routeEvidence ? {route_evidence:routeEvidence} : {}),
    });
    const waiting = receipt?.stage === 'prepared' &&
      Date.now() < Number(receipt.fresh_start_not_before || 0) * 1000;
    if (!receipt || receipt.context_id !== row.context_id ||
        (receipt.request_id === row.request_id ? receipt.stage !== 'stored' && !waiting :
          receipt.retry_previous_request_id !== row.request_id)) {
      throw new Error('Meta fresh-start acknowledgement does not identify the successor');
    }
    if (receipt.request_id !== row.request_id && receipt.retry_previous_request_id === row.request_id) {
      row.closed = true; row.superseded_by = receipt.request_id;
      this.failureObservations.delete(row.request_id);
      this.routeObservations.delete(row.request_id);
      await this.save(row);
    }
    return receipt;
  }
  async openFreshContext(command) {
    const {package: pkg} = await this.api(`/api/meta-video/package?job_id=${encodeURIComponent(command.job_id)}&index=${command.shot_index}`);
    const old = (await this.records())[pkg.request_id];
    if (old && old.context_id !== pkg.context_id) throw new Error('Meta context changed');
    const row = {...pkg, ...old, stage: pkg.stage, conversation_url: pkg.conversation_url || old?.conversation_url || ''};
    if (!metaScenePlanMatches(row,pkg,true)) throw new Error('META_SCENE_PLAN_STALE');
    row.paused = false;
    if (row.stage === 'stored' || row.stage === 'needs_attention') return;
    if (row.stage==='redesigning') { await this.save(row);await this.redesign(row);return; }
    if (Date.now() < Number(pkg.fresh_start_not_before || 0) * 1000) { await this.save(row); return; }
    const owned = !!row.tabId && await this.owns(row);
    let tab = row.tabId ? await this.chrome.tabs.get(row.tabId).catch(() => null) : null;
    if (tab && (!owned || !/^https:\/\/www\.meta\.ai\//.test(tab.url || ''))) {
      await this.freshStart(row, {reason:owned ? 'tab_left_meta' : 'tab_not_owned',
        tab_id:row.tabId, tab_missing:false, session_owned:owned});
      return this.openFreshContext(command);
    }
    if (!tab) {
      // Never navigate an archived /prompt/ URL. Preparation flags and Send
      // intent belong to that old tab and must not leak into a clean page.
      if (row.stage !== 'prepared' || row.openIntent || row.tabId || row.conversation_url) {
        await this.freshStart(row, {reason:'tab_missing', tab_id:row.tabId ?? -1,
          tab_missing:true, session_owned:owned});
        return this.openFreshContext(command);
      }
      row.openIntent = true;
      await this.save(row);
      tab = await this.chrome.tabs.create({url:HOME, active:true});
      row.tabId = tab.id;
      await this.own(row);
    }
    await this.save(row);
  }
  async debug(tabId, operation) {
    const target = {tabId};
    await this.chrome.debugger.attach(target, '1.3');
    try { return await operation((method, params = {}) => this.chrome.debugger.sendCommand(target, method, params)); }
    finally { await this.chrome.debugger.detach(target).catch(() => {}); }
  }
  async click(tabId, point) {
    if (!point) return;
    await this.debug(tabId, async call => {
      await call('Input.dispatchMouseEvent', {type: 'mousePressed', ...point, button: 'left', clickCount: 1});
      await call('Input.dispatchMouseEvent', {type: 'mouseReleased', ...point, button: 'left', clickCount: 1});
    });
  }
  async sendGuarded(row, baseline, choice = false) {
    // The intent has already been acknowledged. Any interruption from here
    // remains observational recovery; it must never restore ready_to_send.
    const requestId=row.request_id, contextId=row.context_id, tabId=row.tabId;
    const expectedWire = normal(metaWirePrompt(choice ? row.choice.prompt : row.prompt));
    let reason='validation_failed';
    const valid = state => {
      if (!state || !baseline.documentId || state.documentId !== baseline.documentId
          || state.observedURL !== baseline.observedURL || state.documentReady !== true) {reason='document_changed';return false;}
      if (state.stop || state.busy || state.pageBusy || state.uploadDialog || state.login) {reason='busy';return false;}
      if (!state.composerFound || state.composerText !== normal(choice ? row.choice.prompt : row.prompt)) {reason='draft_changed';return false;}
      if (normal(state.composerWireText) !== expectedWire) {reason='draft_changed';return false;}
      if (!state.send || !state.sendTarget || state.sendTarget !== baseline.sendTarget) {reason='target_changed';return false;}
      const originalPointStillHits = state.sendOriginMatches === true ||
        (state.sendOriginMatches == null && state.send.x === baseline.send?.x && state.send.y === baseline.send?.y);
      if (!originalPointStillHits) {reason='target_moved';return false;}
      const sourceMatches = (choice ? state.matchedOriginal && state.userCount === 1 && state.imageCount === 0
        && state.proposalText === row.choice.proposal_text && (!row.choice.proposal_branches || state.proposalMatches === true)
        && !state.proposalBusy && state.proposalVideoCount === 0
        : state.userCount === 0 && state.imageCount === 1 && state.imageReady
          && state.imageName === row.image_name && state.imageSource === baseline.imageSource);
      if (!sourceMatches) reason='source_changed';
      return sourceMatches;
    };
    const check = async () => {
      const {package: current} = await this.api(`/api/meta-video/package?job_id=${encodeURIComponent(row.job_id)}&index=${row.index}`);
      if (current.request_id !== requestId || current.context_id !== contextId
          || !metaScenePlanMatches(row,current)
          || current.prompt !== row.prompt || current.image_name !== row.image_name
          || (choice ? current.choice?.stage !== 'send_intent' : current.stage !== 'send_intent')
          || choice && (current.choice.prompt !== row.choice.prompt || current.choice.proposal_text !== row.choice.proposal_text
            || JSON.stringify(current.choice.proposal_branches) !== JSON.stringify(row.choice.proposal_branches)
            || current.choice.proposal_branch !== row.choice.proposal_branch)
          || row.paused || row.closed || !await this.owns(row)) {reason='owner_changed';return false;}
      const tab=await this.chrome.tabs.get(tabId).catch(()=>null);
      if (!tab || tab.status !== 'complete' || tab.url?.split(/[?#]/)[0] !== baseline.observedURL) {reason='tab_changed';return false;}
      return valid(await this.inspect(row, baseline.send));
    };
    let pressed=false, pressAcknowledged=false, releaseAttempted=false, released=false, changed=false;
    try {
      await this.debug(tabId, async call => {
        if (!await check()) {changed=true;return;}
        // Treat a lost press acknowledgement as a possibly pressed pointer.
        pressed=true;
        try {
          await call('Input.dispatchMouseEvent', {type:'mousePressed', ...baseline.send, button:'left', clickCount:1});
          pressAcknowledged=true;
          if (!await check()) {changed=true;return;}
          releaseAttempted=true;
          await call('Input.dispatchMouseEvent', {type:'mouseReleased', ...baseline.send, button:'left', clickCount:1});
          released=true;
        } finally {
          if (!released) {
            // A negative viewport location cannot hit a newly mounted Stop or
            // another control. Do not move/retry the original gesture.
            await call('Input.dispatchMouseEvent', {type:'mouseReleased',x:-1,y:-1,button:'left',buttons:0,clickCount:0}).catch(()=>{});
          }
        }
      });
    } catch (_) { changed=true;reason='dispatch_error'; }
    row.send_diagnostic={phase:releaseAttempted?'released':pressed?'pressed':'before_press',
      outcome:released?'gesture_released':!pressed?'blocked_before_press':pressAcknowledged&&!releaseAttempted?'release_cancelled':'dispatch_unknown',
      press_dispatched:pressed,release_dispatched:releaseAttempted,...(changed?{reason}:{})};
    await this.save(row);
    if (changed) {
      row.sendDiagnostic=pressed?'gesture_outcome_unknown':'page_changed_before_press';
      await this.save(row);
      await this.wait(row,row.sendDiagnostic,pressed
        ? 'หน้า Meta เปลี่ยนระหว่างกดส่ง • เก็บใบรับและตรวจผลเดิม ไม่ส่งซ้ำ'
        : 'หน้า Meta เปลี่ยนก่อนกดส่ง • ยังไม่กดส่ง เก็บใบรับเพื่อตรวจคำขอเดิม').catch(()=>{});
    }
  }
  async inspect(row, sendOrigin = null) {
    const [value] = await this.chrome.scripting.executeScript({target: {tabId: row.tabId},
      func: inspectMetaDOM, args: [row.prompt, row.image_name, row.choice || null, sendOrigin]});
    const state = value?.result;
    if (state) state.documentId = value.documentId || '';
    if (state) {
      state.composerWireText = state.composerText;
      if (globalThis.SmartFlowSingleAnswer) state.composerText = normal(globalThis.SmartFlowSingleAnswer.canonical(state.composerText));
    }
    return state;
  }
  async prepareWireDraft(row, state, choice = false) {
    const prompt = choice ? row.choice.prompt : row.prompt, wire = metaWirePrompt(prompt);
    if (normal(state.composerWireText) === normal(wire)) return true;
    // An accepted/uncertain Send is never rewritten to retrofit the format rule.
    const prepared = current => choice ? current.stage === 'generating' && current.choice?.stage === 'prepared' &&
      current.choice.prompt === prompt && current.choice.proposal_text === row.choice.proposal_text &&
      JSON.stringify(current.choice.proposal_branches) === JSON.stringify(row.choice.proposal_branches) :
      ['prepared','uploading','ready_to_send'].includes(current.stage);
    const valid = value => value && value.documentId === state.documentId && value.documentReady === true &&
      value.observedURL === state.observedURL && value.composerFound &&
      normal(value.composerWireText) === normal(prompt) && !value.stop && !value.busy && !value.pageBusy &&
      !value.answerBusy && !value.uploadDialog && !value.login &&
      value.imageCount === state.imageCount && value.imageSource === state.imageSource && value.imageName === state.imageName &&
      (choice ? value.userCount === 1 && value.matchedOriginal && value.proposalText === row.choice.proposal_text &&
        (!row.choice.proposal_branches || value.proposalMatches === true) && !value.proposalBusy && value.proposalVideoCount === 0 : value.userCount === 0);
    if (!state.documentId || !prepared(row) || !valid(state)) return false;
    const {package: current} = await this.api(`/api/meta-video/package?job_id=${encodeURIComponent(row.job_id)}&index=${row.index}`);
    if (current.request_id !== row.request_id || current.context_id !== row.context_id || current.prompt !== row.prompt ||
        !metaScenePlanMatches(row,current) ||
        !prepared(current) || row.paused || row.closed || !await this.owns(row)) return false;
    const fresh = await this.inspect(row);
    if (!valid(fresh)) return false;
    const suffix = wire.slice(String(prompt).trimEnd().length);
    // Append at the end of the exact owned draft, preserving attached image DOM.
    // The synchronous check+edit rejects a user edit between the awaited checks.
    await this.chrome.scripting.executeScript({target:{tabId:row.tabId, documentIds:[state.documentId]},
      func:(expected,addition,imageCount,imageSource) => {
        const normal = value => String(value || '').replace(/\s+/g,' ').trim();
        const editors = [...document.querySelectorAll('[role="textbox"][contenteditable="true"][data-lexical-editor="true"]')]
          .filter(node => node.getBoundingClientRect().width && node.getBoundingClientRect().height);
        const editor = editors.length === 1 ? editors[0] : null, images = [...(editor?.querySelectorAll('img') || [])];
        if (!editor || normal(editor.innerText) !== expected || images.length !== imageCount ||
            (images[0]?.currentSrc || images[0]?.src || '') !== imageSource) return false;
        editor.focus();
        const range = document.createRange(); range.selectNodeContents(editor); range.collapse(false);
        const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
        return document.execCommand('insertText', false, addition);
      },args:[normal(prompt),suffix,state.imageCount,state.imageSource || '']});
    await this.save(row);
    return false; // Next tick revalidates owner, attachments and the full wire text.
  }
  async recoverRoute(row, state) {
    const proof = {observed_url:state.observedURL, document_id:state.documentId,
      ready:state.documentReady, login:state.login, composer_count:state.composerCount,
      composer_empty:state.composerFound === true && !state.composerText,
      user_count:state.userCount, image_count:state.imageCount, video_count:state.pageVideoCount, message_count:state.pageMessageCount,
      busy:!!(state.busy || state.answerBusy || state.pageBusy), stop:state.stop,
      answer_empty:!state.answerText && !state.matchedUser, dialog:!!(state.uploadDialog || state.pageDialog)};
    const emptyHome = proof.observed_url === 'https://www.meta.ai/' && proof.document_id &&
      proof.ready === true && proof.login === false && proof.composer_count === 1 &&
      proof.composer_empty && proof.user_count === 0 && proof.image_count === 0 &&
      proof.video_count === 0 && proof.message_count === 0 && !proof.busy && proof.stop === false && proof.answer_empty && !proof.dialog;
    if (!emptyHome) {
      this.routeObservations.delete(row.request_id);
      await this.wait(row, 'route_loading', `ฉาก ${row.index}: รอหน้า Meta พร้อมเพื่อตรวจผลเดิม • ยังไม่ส่งซ้ำ`);
      return;
    }
    let seen = this.routeObservations.get(row.request_id);
    if (!seen || seen.document !== state.documentId) {
      seen = {document:state.documentId, at:Date.now(), samples:0};
      this.routeObservations.set(row.request_id, seen);
    }
    seen.samples++;
    if (seen.samples < 2 || Date.now()-seen.at < 5000) return;
    const latest = await this.chrome.tabs.get(row.tabId).catch(() => null);
    if (!latest || latest.status !== 'complete' || latest.url?.split(/[?#]/)[0] !== HOME || !await this.owns(row)) return;
    // A lost route starts at clean Home under a new receipt. Do not reopen the
    // previous /prompt/ URL only to discover the same redirect again.
    await this.freshStart(row, {reason:'route_home', tab_id:row.tabId,
      tab_missing:false, session_owned:true}, {...proof, samples:seen.samples, stable_ms:Date.now()-seen.at});
    await this.open({job_id:row.job_id, shot_index:row.index});
  }
  async stepChoice(row, state) {
    const choice = row.choice;
    if (choice.stage === 'send_intent') {
      if (state.matchedOriginal && state.matchedChoice && state.userCount === 2
          && state.composerFound && !state.composerText && state.imageCount === 0 && !state.uploadDialog) {
        await this.event(row, 'choice_submitted', {choice_prompt: choice.prompt, matched_choice: true, user_count: 2});
      } else if ((!state.matchedChoice && state.userCount > 1) || Date.now() - choice.send_at * 1000 > 90000) {
        await this.event(row, 'needs_attention', {message: 'ยังยืนยันคำตอบเลือก Meta ไม่ได้ • เก็บแชตเดิม ไม่ส่งซ้ำ'});
      }
      return;
    }
    const unchanged = s => s.matchedOriginal && s.userCount === 1 &&
      s.proposalText === choice.proposal_text && (!choice.proposal_branches || s.proposalMatches === true)
      && !s.proposalBusy && s.proposalVideoCount === 0 &&
      !s.stop && !s.busy && s.composerFound && s.imageCount === 0 && !s.uploadDialog;
    if (!unchanged(state)) {
      await this.wait(row, 'choice_wait', 'รอยืนยันข้อเสนอและช่องข้อความ Meta เดิมก่อนตอบเลือก • ไม่แนบรูปซ้ำ'); return;
    }
    if (!state.composerText && !row.choiceTextIntent) {
      if (!state.composer) { await this.wait(row, 'choice_composer_blocked', 'รอช่องตอบเลือก Meta ที่คลิกได้'); return; }
      const wire = metaWirePrompt(choice.prompt);
      row.choiceTextIntent = true; await this.save(row);
      await this.click(row.tabId, state.composer);
      await this.debug(row.tabId, call => call('Input.insertText', {text: wire})); return;
    }
    if (state.composerText !== normal(choice.prompt)) {
      await this.event(row, 'needs_attention', {message: 'ข้อความตอบเลือก Meta เปลี่ยนหรือหาย • เก็บแชตเดิม ไม่ส่งทับ'}); return;
    }
    if (!state.send) { await this.wait(row, 'choice_send_disabled', 'รอปุ่มส่งคำตอบเลือก Meta พร้อม'); return; }
    if (!await this.prepareWireDraft(row, state, true)) return;
    const receipt = await this.event(row, 'choice_send_intent', {choice_prompt: choice.prompt});
    if (receipt.choice_send_authorized !== true) return;
    await this.sendGuarded(row, state, true);
  }
  async tick() {
    if (this.running) return;
    this.running = true;
    try {
      for (const row of Object.values(await this.records())) {
        if (row.stage === 'needs_attention' || row.closed || row.paused) continue;
        try { await this.step(row); }
        catch (error) {
          // Network/engine interruptions keep the receipt intact. No repeat Send.
          row.diagnostic = error.metaBridge ? 'desktop_context_unavailable' : 'meta_step_interrupted';
          row.paused = error.metaPaused === true;
          await this.save(row);
          if (!error.metaBridge || error.metaPaused) {
            await this.event(row, 'needs_attention', {message: `ทำขั้นตอน Meta (${row.stage}) ไม่สำเร็จ • ตรวจแท็บเดิมก่อนกดทำต่อ`}).catch(() => {});
          }
        }
      }
    } finally { this.running = false; }
  }
  async step(row) {
    if (this.opening.has(`${row.job_id}:${row.index}`)) return;
    // The desktop validates cancellation, scene context and current provider every tick.
    const {package: current} = await this.api(`/api/meta-video/package?job_id=${encodeURIComponent(row.job_id)}&index=${row.index}`);
    if (!metaScenePlanMatches(row,current,true)) {
      row.paused=true; row.error='META_SCENE_PLAN_STALE'; await this.save(row); return;
    }
    if (current.redesign_previous_request_id===row.request_id) { await this.adoptRetry(row,current); return; }
    if (current.context_id !== row.context_id) return;
    if (current.request_id !== row.request_id) { await this.adoptRetry(row, current); return; }
    row.stage = current.stage;
    if (row.stage === 'needs_attention') return;
    if (Date.now() < Number(current.fresh_start_not_before || 0) * 1000) return;
    if (current.route_recovery) row.route_recovery = current.route_recovery;
    else delete row.route_recovery;
    if (current.aspect_ratio === '16:9') row.aspect_ratio = current.aspect_ratio;
    // Cooldown belongs to the desktop receipt and survives worker restarts.
    // Continue inspecting the old answer: a late real video or busy state wins.
    if (current.recovery) row.recovery = current.recovery;
    else delete row.recovery;
    if (row.stage==='redesigning') {
      if (!this.redesign) throw Error('Meta image recovery is unavailable');
      await this.redesign(current);return;
    }
    if (current.choice) row.choice = current.choice;
    if (current.video_selection) row.video_selection = current.video_selection;
    if (Number.isInteger(current.download_id)) row.download_id = current.download_id;
    // A completed local download does not need a surviving browser tab.
    if (row.stage === 'downloading') { await this.collectDownload(row); return; }
    if (row.stage === 'download_intent') { await this.reconcileDownload(row); return; }
    // Session ownership disappears on Chrome restart, unlike tab IDs on disk.
    // Never trust a recycled tab ID belonging to the user or another workflow.
    const owned = !!row.tabId && await this.owns(row);
    const tab = row.tabId ? await this.chrome.tabs.get(row.tabId).catch(() => null) : null;
    if (row.stage === 'stored') {
      if (owned && tab?.url && tab.url.split('?')[0] === row.conversation_url) await this.chrome.tabs.remove(row.tabId);
      this.failureObservations.delete(row.request_id);
      row.closed = true; await this.save(row); return;
    }
    if (!tab || !owned || !/^https:\/\/www\.meta\.ai\//.test(tab.url || '')) {
      if (!tab && row.stage === 'prepared' && !row.openIntent && !row.tabId && !row.conversation_url) {
        await this.open({job_id:row.job_id, shot_index:row.index}); return;
      }
      await this.freshStart(row, {reason:!tab ? 'tab_missing' : !owned ? 'tab_not_owned' : 'tab_left_meta',
        tab_id:row.tabId ?? -1, tab_missing:!tab, session_owned:owned});
      await this.open({job_id:row.job_id, shot_index:row.index}); return;
    }
    if (tab.status !== 'complete') { this.routeObservations.delete(row.request_id); return; }
    const state = await this.inspect(row);
    if (!state) { this.routeObservations.delete(row.request_id); return; }
    if (state.login) { await this.event(row, 'needs_attention', {message: 'กรุณาเข้าสู่ระบบ Meta AI ใน Chrome ก่อน', page_diagnostic:{observed_url:state.observedURL}}); return; }
    if (row.conversation_url && state.conversation !== row.conversation_url.replace(/\/$/, '')) {
      if (state.conversation) {
        await this.event(row, 'needs_attention', {message:`ฉาก ${row.index}: แท็บ Meta ถูกย้ายไปบทสนทนาอื่น • ไม่ส่งทับ`, page_diagnostic:{observed_url:state.observedURL}}); return;
      }
      await this.recoverRoute(row, state); return;
    }
    this.routeObservations.delete(row.request_id);
    if (row.route_recovery) {
      await this.event(row, 'route_restored', {route_check_id:row.route_recovery.check_id});
      delete row.route_recovery; delete row.routeNavigation;
    }
    if (row.stage === 'generating' && row.choice && row.choice.stage !== 'accepted') {
      await this.stepChoice(row, state); return;
    }
    if (['prepared', 'uploading', 'ready_to_send'].includes(row.stage)) {
      if (state.userCount) { await this.event(row, 'needs_attention', {message: 'มีข้อความเดิมในหน้าเตรียม Meta • ไม่ส่งทับ'}); return; }
      if (row.stage === 'prepared') {
        if (!state.composerFound) {
          await this.wait(row, 'composer_unavailable', 'รอช่องข้อความ Meta ที่ระบุได้ช่องเดียว • ยังไม่แนบภาพหรือกดส่ง'); return;
        }
        if (state.busy || state.stop) {
          await this.wait(row, 'composer_busy', 'Meta ยังแสดงสถานะกำลังทำงาน • เก็บพรอมต์เดิมไว้'); return;
        }
        if (!state.composerText && !row.textIntent) {
          if (!state.composer) {
            await this.wait(row, 'composer_obstructed', 'ช่องข้อความ Meta ยังคลิกไม่ได้หรือถูกบัง • ยังไม่ได้วางพรอมต์'); return;
          }
          const wire = metaWirePrompt(row.prompt);
          row.textIntent = true; await this.save(row);
          await this.assertSceneOwner(row);
          await this.click(row.tabId, state.composer);
          await this.assertSceneOwner(row);
          await this.debug(row.tabId, call => call('Input.insertText', {text: wire})); return;
        }
        if (state.composerText !== normal(row.prompt)) {
          await this.event(row, 'needs_attention', {message: 'ข้อความใน Meta ไม่ตรงงาน • ไม่ล้างรูปหรือข้อความเดิม'}); return;
        }
        if (!await this.prepareWireDraft(row, state)) return;
        await this.event(row, 'uploading', {message: 'แนบภาพฉากเดิมให้ Meta'}); return;
      }
      if (state.composerText !== normal(row.prompt)) return;
      if (row.stage === 'uploading') {
        if (state.imageCount === 1 && state.imageReady && !state.busy && state.imageName === row.image_name && !state.uploadDialog) {
          await this.event(row, 'ready_to_send', {message: 'ภาพโหลดครบและพรอมต์ตรงฉาก'}); return;
        }
        if (state.imageCount > 0 || state.busy) return;
        if (state.uploadDialog && !state.fileInput) {
          await this.event(row, 'needs_attention', {message: 'หน้าต่างอัปโหลด Meta ไม่ตรงช่องแชต • เก็บข้อความเดิมไว้'}); return;
        }
        if (state.fileInput && !row.uploadIntent) {
          row.uploadIntent = true; await this.save(row);
          await this.debug(row.tabId, async call => {
            const {root} = await call('DOM.getDocument');
            const {nodeId} = await call('DOM.querySelector', {nodeId: root.nodeId, selector: '[data-smartflow-meta-file="current"]'});
            if (!nodeId) throw new Error('Meta upload dialog not ready');
            await this.assertSceneOwner(row);
            await call('DOM.setFileInputFiles', {nodeId, files: [row.image_path]});
          }); return;
        }
        if (!state.uploadDialog && !row.uploadIntent) { await this.assertSceneOwner(row); await this.click(row.tabId, state.attach); }
        return;
      }
      if (state.send && state.imageCount === 1 && state.imageReady && !state.busy && !state.stop
          && !state.uploadDialog && state.imageName === row.image_name) {
        if (!await this.prepareWireDraft(row, state)) return;
        row.sendAt = Date.now();
        await this.event(row, 'send_intent', {message: 'เตรียมกดส่ง Meta • ยังไม่ยืนยันการรับงาน'});
        await this.sendGuarded(row, state);
      }
      return;
    }
    if (row.stage === 'send_intent') {
      if (state.matchedUser && state.conversation && state.composerFound
          && !state.composerText && state.imageCount === 0 && !state.uploadDialog) {
        row.conversation_url = state.conversation;
        await this.event(row, 'submitted', {message: 'Meta รับข้อความและรูปของฉากนี้แล้ว'});
      } else if (Date.now() - (row.sendAt || current.updated_at * 1000) > 90000) {
        const detail=row.send_diagnostic?.outcome;
        const message=detail==='blocked_before_press'?'Meta เปลี่ยนก่อนกดส่ง • ยังไม่ได้คลิกส่ง เก็บรูปและพรอมต์เดิม':
          detail==='release_cancelled'?'Meta เปลี่ยนระหว่างกด • ยกเลิกการปล่อยคลิกและเก็บหลักฐานเดิม':
          detail==='gesture_released'?'คลิกส่ง Meta ครบแล้ว แต่ยังไม่พบการรับคำขอ • เก็บแท็บเดิม ไม่ส่งซ้ำ':
          'ยังยืนยันการกดส่ง Meta ไม่ได้ • เก็บแท็บเดิม ไม่ส่งซ้ำ';
        await this.event(row, 'needs_attention', {message});
      }
      return;
    }
    if (row.stage === 'submitted') {
      if (state.matchedUser) await this.event(row, 'generating', {message: 'Meta รับคำขอแล้ว • รอผลวิดีโอในบทสนทนาเดิม'});
      return;
    }
    if (row.stage === 'generating') {
      if (!state.matchedUser) {
        this.failureObservations.delete(row.request_id);
        if (row.failureObservation) { delete row.failureObservation; await this.save(row); }
        return;
      }
      if (state.stop || state.busy || state.answerBusy || state.pageBusy) {
        this.failureObservations.delete(row.request_id);
        if (row.failureObservation) { delete row.failureObservation; await this.save(row); }
        return;
      }
      if (!state.videoReady) {
        const reason = metaReplyFailure(state.answerText);
        const offer = state.comparison ? metaComparisonOffer(state.answerBranches, row.aspect_ratio || '9:16') :
          metaFollowupOffer(state.answerText, row.aspect_ratio || '9:16');
        const completed = state.answerComplete && state.answerTruncated === false &&
          !state.stop && !state.busy && !state.answerBusy && state.videoCount === 0;
        if (!completed) {
          this.failureObservations.delete(row.request_id);
          if (row.failureObservation) { delete row.failureObservation; await this.save(row); }
          return;
        }
        let observation = this.failureObservations.get(row.request_id);
        const signature = JSON.stringify([state.answerText, state.answerBranches || []]);
        if (!observation || observation.signature !== signature) observation = {text: state.answerText, signature, since: Date.now(), samples: 0};
        this.failureObservations.set(row.request_id, observation);
        observation.samples += 1; row.failureObservation = observation; await this.save(row);
        // Debounce a completed reply, not a time limit on real generation.
        if (observation.samples < 2 || Date.now() - observation.since < 5000) return;
        if (state.comparison && !offer && metaFollowupOffer(state.answerText, row.aspect_ratio || '9:16')) {
          await this.event(row, 'needs_attention', {message:'Meta ตอบหลายแนวทางแล้ว แต่ยังแยกข้อเสนอที่รองรับไม่ได้ • เก็บคำตอบเดิม ไม่ตอบตกลงรวม'});
          return;
        }
        if (!reason && !offer) {
          if (state.comparison) {
            await this.event(row, 'needs_attention', {message:'Meta ตอบหลายแนวทางแล้ว แต่ยังแยกข้อเสนอที่รองรับไม่ได้ • เก็บคำตอบเดิม ไม่ตอบตกลงรวม'});
            return;
          }
          await this.wait(row, 'unrecognized_completed_no_video',
            'Meta ตอบจบแล้วแต่ยังไม่พบวิดีโอหรือข้อผิดพลาดที่ยืนยันได้ • กำลังตรวจผลเดิม ไม่กดส่งซ้ำ');
          return;
        }
        if (reason === 'transient_service_error' && !offer) {
          if (state.composerText || state.imageCount || state.uploadDialog) {
            await this.wait(row, 'meta_draft_preserved',
              'Meta แจ้งบริการขัดข้อง แต่มีข้อความหรือรูปในช่องพิมพ์ • เก็บไว้ก่อน ไม่ส่งซ้ำ');
            return;
          }
          const recovery = row.recovery;
          if (recovery?.protocol === 1 && recovery.category === reason && recovery.state === 'cooldown' &&
              Date.now() < Number(recovery.next_retry_at) * 1000) return;
          await this.retryCompleted(row, state, observation); return;
        }
        if (offer) {
          if (row.choice) {
            await this.retryCompleted(row,state,observation,true); return;
          }
          await this.event(row, 'choice_prepare', {choice_evidence: {
            matched_request: true, answer_complete: true, answer_truncated: false, stop: false, busy: false,
            comparison: !!state.comparison,
            ...(state.comparison ? {comparison_branches:state.answerBranches, selected_branch:offer.proposal_branch} : {}),
            video_count: 0, answer_text: offer.proposal_text, samples: observation.samples, stable_ms: Date.now() - observation.since,
          }});
        }
        else if (reason === 'technical_redesign' && (state.composerText || state.imageCount || state.uploadDialog)) {
          await this.wait(row, 'meta_draft_preserved',
            'Meta ตอบผิดพลาดแล้ว แต่ช่องพิมพ์มีข้อความหรือรูปค้าง • เก็บฉากเดิมไว้ ไม่เริ่มคำขอใหม่');
          return;
        }
        else if (reason === 'technical_redesign' || reason === 'image_not_viable' ||
            (reason === 'completed_no_video' && (row.choice || Number(row.retry_count||0)>=2)))
          await this.retryCompleted(row,state,observation,true);
        else if (reason === 'completed_no_video') await this.retryCompleted(row, state, observation);
        else await this.event(row, 'needs_attention', {message: reason === 'quota'
          ? 'Meta แจ้งขีดจำกัดการใช้งาน • เก็บรูปและพรอมต์ ไม่ส่งซ้ำ'
          : reason === 'authentication_required'
            ? 'Meta ต้องเข้าสู่ระบบ • เก็บรูปและพรอมต์ ไม่ส่งซ้ำ'
          : reason === 'image_not_viable'
            ? 'Meta สร้างวิดีโอจากภาพนี้ไม่ได้และไม่ได้เสนอเวอร์ชันใหม่ • เก็บคำตอบให้ตรวจ'
            : 'Meta แจ้งข้อจำกัดเนื้อหา • เก็บคำตอบเดิมให้ตรวจ ไม่ส่งซ้ำ'});
        return;
      }
      if (!/^https:\/\//.test(state.videoSrc)) {
        await this.event(row, 'needs_attention', {message: 'Meta ตอบวิดีโอแล้ว แต่ยังไม่มีแหล่งดาวน์โหลดที่ตรวจได้'}); return;
      }
      if (state.videoCount > 1 || row.video_selection) {
        if (!row.video_selection) {
          await this.event(row, 'video_select', {video_evidence:{matched_request:true, ready:true, stop:false,
            busy:false, asset_sha256:await metaVideoAssetDigest(state.videoSrc)}});
          return; // Re-read the owned, idle page after the durable selection ACK.
        }
        const selected = [];
        for (const candidate of state.videoCandidates || []) {
          if (candidate.ready && /^https:\/\//.test(candidate.src) &&
              await metaVideoAssetDigest(candidate.src) === row.video_selection.asset_sha256) selected.push(candidate.src);
        }
        if (!selected.length) {
          await this.wait(row, 'selected_video_unavailable', 'รอวิดีโอ Meta ที่เลือกไว้พร้อม • ไม่เปลี่ยนไปดาวน์โหลดอีกตัวเลือก');
          return;
        }
        state.videoSrc = selected[0];
      }
      row.downloadName = `SmartFlow/Meta/${row.job_id}/scene-${row.index}-${row.request_id}.mp4`;
      await this.event(row, 'download_intent', {message: 'พบวิดีโอของฉากนี้ กำลังดาวน์โหลด',
        ...(row.video_selection ? {asset_sha256:row.video_selection.asset_sha256} : {})});
      if (row.video_selection) {
        const fresh = await this.inspect(row);
        const ready = fresh?.matchedUser && fresh.conversation === row.conversation_url &&
          !fresh.stop && !fresh.busy && !fresh.answerBusy && !fresh.pageBusy &&
          fresh.videoCandidates?.some(candidate => candidate.ready && candidate.src === state.videoSrc);
        if (!ready || row.paused || row.closed || !await this.owns(row)) {
          await this.event(row, 'needs_attention', {message:'ผล Meta เปลี่ยนหลังเตรียมดาวน์โหลด • เก็บตัวเลือกและใบรับเดิม'});
          return;
        }
      }
      // Only this exact, request-scoped video URL is used. Never persist signed URLs.
      await this.assertSceneOwner(row, true);
      row.download_id = await this.chrome.downloads.download({url: state.videoSrc,
        filename: row.downloadName, saveAs: false, conflictAction: 'uniquify'});
      await this.save(row);
      await this.event(row, 'downloading', {download_id: row.download_id, message: 'รอไฟล์ Meta ดาวน์โหลดครบ'});
      return;
    }
  }
  async reconcileDownload(row) {
      if (!Number.isInteger(row.download_id)) {
        const candidates = await this.chrome.downloads.search({filenameRegex: `${row.request_id}\\.mp4$`});
        const name = row.downloadName || `SmartFlow/Meta/${row.job_id}/scene-${row.index}-${row.request_id}.mp4`;
        const owned = candidates.filter(item => item.byExtensionId === this.chrome.runtime.id &&
          typeof item.filename === 'string' && item.filename.replace(/\\/g, '/').endsWith(name));
        if (owned.length === 1) row.download_id = owned[0].id;
      }
      if (Number.isInteger(row.download_id)) await this.event(row, 'downloading', {download_id: row.download_id});
      else await this.event(row, 'needs_attention', {message: 'ตรวจดาวน์โหลด Meta เดิมก่อน • ไม่กดดาวน์โหลดซ้ำ'});
  }
  async collectDownload(row) {
      const [item] = await this.chrome.downloads.search({id: row.download_id});
      if (!item || item.state === 'interrupted') {
        await this.event(row, 'needs_attention', {message: 'ดาวน์โหลด Meta หยุด • เก็บแท็บและใบรับงานเดิม'}); return;
      }
      if (item.state !== 'complete' || !item.filename || !item.exists) return;
      await this.event(row, 'stored', {filename: item.filename, download_id: item.id, message: 'ตรวจไฟล์และบันทึกวิดีโอ Meta เข้าฉากแล้ว'});
  }
}
