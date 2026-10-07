// Pure logic: the shared status vocabulary. No browser, no provider, no saved data.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync(path.join(__dirname, '..', 'web_ui', 'status_vocabulary.js'), 'utf8');
const context = {};
context.window = context;
vm.createContext(context);
vm.runInContext(source, context);
const S = context.SmartFlowStatus;
let checks = 0;
const eq = (actual, expected, message) => { assert.equal(actual, expected, message); checks++; };

// The six states a customer sees.
assert.deepEqual(Object.keys(S.STATES), ['queued', 'running', 'waiting', 'failed', 'paused', 'done']); checks++;
assert.deepEqual(Object.values(S.STATES).map(s => s.label), ['รอคิว', 'กำลังสร้าง', 'รอคุณ', 'สะดุด', 'หยุดไว้', 'เสร็จแล้ว']); checks++;
assert(Object.isFrozen(S), 'vocabulary object is frozen'); checks++;

// Backend codes land on the right state.
for (const [code, label, tone] of [
  ['queued', 'รอคิว', 'queued'], ['pending', 'รอคิว', 'queued'],
  ['running', 'กำลังสร้าง', 'running'],
  ['action_required', 'รอคุณ', 'waiting'], ['needs_attention', 'รอคุณ', 'waiting'], ['image_review', 'รอคุณ', 'waiting'],
  ['failed', 'สะดุด', 'failed'], ['error', 'สะดุด', 'failed'],
  ['paused', 'หยุดไว้', 'paused'],
  ['completed', 'เสร็จแล้ว', 'done'], ['success', 'เสร็จแล้ว', 'done'],
  // Narrower meanings keep their own label.
  ['ready', 'พร้อม', 'done'], ['posted', 'โพสต์แล้ว', 'done'], ['request_ready', 'พร้อมส่ง AI', 'queued'],
  ['cancelled', 'ยกเลิกแล้ว', 'paused'], ['canceled', 'ยกเลิกแล้ว', 'paused'],
  ['login_required', 'รอคุณ · ต้องเข้าสู่ระบบ', 'waiting'], ['credit_exhausted', 'รอคุณ · เครดิตหมด', 'waiting'],
  ['missing', 'ยังไม่มี', 'none'], ['deleted', 'ลบแล้ว', 'none'],
]) {
  eq(S.label(code), label, `${code} label`);
  eq(S.tone(code), tone, `${code} tone`);
}
// Case and whitespace do not matter; unknown values pass through unchanged.
eq(S.label('  FAILED '), 'สะดุด', 'trimmed and case-folded');
eq(S.label('something_new'), 'something_new', 'unknown passes through');
eq(S.tone('something_new'), 'none', 'unknown has no tone');
eq(S.label(''), '—', 'empty'); eq(S.label(null), '—', 'null'); eq(S.label(undefined), '—', 'undefined');

// "ทำต่อได้" is promised only where the page really offers resume.
eq(S.label('failed'), 'สะดุด', 'plain failure never promises resume');
eq(S.label('failed', {resumable: true}), 'สะดุด · ทำต่อได้', 'resumable failure');
eq(S.RESUMABLE_FAILED, 'สะดุด · ทำต่อได้', 'exported resumable label');
eq(S.label('completed', {resumable: true}), 'เสร็จแล้ว', 'resumable only affects failures');

// Pill markup escapes everything it prints.
const evil = S.pill('<img src=x onerror=alert(1)>', {extraClass: '"><script>'});
assert(!/<img|<script/.test(evil), `unescaped markup: ${evil}`); checks++;
assert(/data-tone="none"/.test(evil)); checks++;
assert.match(S.pill('running'), /^<span class="sf-status " data-tone="running">กำลังสร้าง<\/span>$/); checks++;
assert.match(S.pill('running', {extraClass: 'cq-status running'}), /class="sf-status cq-status running"/); checks++;
assert.match(S.pill('failed', {label: 'ข้อความเอง'}), />ข้อความเอง</); checks++;

// Pause reasons: known keys explain themselves; unknown or empty stay silent.
for (const reason of ['startup_review', 'awaiting_user_start', 'job_needs_attention', 'ai_cover_needs_attention', 'preflight',
  'start_failed', 'dispatch_error', 'extension_update', 'app_update', 'user', 'user_cancel', 'user_cancel_all',
  'state_cleared', 'missing_final']) {
  assert(S.pauseReason(reason).length > 8, `${reason} has customer text`); checks++;
}
assert(S.pauseReason('drama_failure:SERIES-1:2').includes('ละครสั้น'), 'drama failure prefix'); checks++;
eq(S.pauseReason(''), '', 'empty reason'); eq(S.pauseReason(undefined), '', 'undefined reason'); eq(S.pauseReason('totally_new'), '', 'unknown reason');
// Customer text never leaks internal codes or tooling names.
for (const reason of ['startup_review', 'job_needs_attention', 'extension_update', 'missing_final']) {
  assert(!/[a-z]_[a-z]|Codex|Checkpoint|Job\b/.test(S.pauseReason(reason)), `${reason} text is jargon-free`); checks++;
}

console.log(`status vocabulary: ${checks} checks passed`);
