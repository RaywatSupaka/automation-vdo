# MASTER PROMPT — SmartFlow AI Browser Bridge

คุณเป็น Senior Browser Extension Architect และ Senior JavaScript/TypeScript Engineer

ฉันต้องการพัฒนา Chrome Extension ชื่อ **SmartFlow AI Browser Bridge**

เว็บไซต์เป้าหมาย:

- `https://affiliate.shopee.co.th/*`
- `https://shopee.co.th/*`
- `https://chatgpt.com/*`
- `https://gemini.google.com/*`
- `https://flow.google.com/*`
- Legacy redirect เฉพาะ `https://labs.google/fx/*` และ `https://labs.google/flow/*`
- Local Bridge เฉพาะ `http://127.0.0.1:8765/*`

เป้าหมายหลัก:

เชื่อม SmartFlow AI Desktop App กับ Chrome ที่ผู้ใช้ Login อยู่แล้ว เพื่ออ่านสินค้า Shopee, สร้างบทและภาพผ่าน ChatGPT/Gemini Web, นำภาพพร้อม Prompt เข้า Google Flow เพื่อสร้างวิดีโอจริง, เฝ้าสถานะ, ดาวน์โหลดผลกลับเข้า Job เดิม และกู้ต่อจาก Checkpoint โดยไม่อัปโหลดซ้ำ กดสร้างซ้ำ เปิดแท็บวน หรือใช้เครดิตซ้ำ

คำสั่งที่ต้องรองรับ:

- Shopee: `capture_shopee_product`
- AI Web: `open_chatgpt`, `open_story_chatgpt`, `cancel_story_chatgpt`, `resume_chatgpt`, `restart_chatgpt_images`, `inspect_chatgpt`, `focus_ai_web`
- Google Flow: `focus_flow_web`, `debug_flow_dom`, `open_flow`, `inspect_flow`, `resume_flow_workspace`, `approve_flow_credit`, `stop_flow_generation`, `open_flow_result`, `download_flow_result`, `inspect_flow_result_dom`
- Core: `close_automation_browser`

Architecture:

```text
SmartFlow AI Desktop App
→ Local Bridge 127.0.0.1:8765
→ Chrome Extension Background Service Worker
→ Job Router
→ Shopee / AI Web / Google Flow Platform Adapter
→ Content Script
→ Optional validated MAIN-world observer
→ Target Website
```

ห้ามสร้าง Source เป็น JavaScript ไฟล์ใหญ่ไฟล์เดียว ให้ย้ายแบบ incremental โดยรักษา `background.js`, `chatgpt.js` และ `flow.js` เป็น Legacy runtime adapter ชั่วคราวจนแต่ละส่วนมี regression test และ real smoke test ยืนยันก่อนย้าย

## 1. TECHNOLOGY

- Chrome Extension Manifest V3
- Background เป็น module Service Worker
- Source ใหม่ใช้ ES Modules
- ใช้ JavaScript โดยไม่เพิ่ม framework/build dependency ที่ไม่จำเป็น
- Load Unpacked ได้จาก `browser_extension/`
- Content script ที่ Chrome ไม่โหลดเป็น module ให้ใช้ bootstrap ขนาดเล็กและ message contract เดียว

## 2. PROJECT STRUCTURE

```text
browser_extension/
  src/
    background/
      service-worker.js
      bootstrap.js
      job-router.js
      tab-manager.js
      window-manager.js
    core/
      bridge-transport.js
      message-schema.js
      storage.js
      logger.js
      retry.js
      errors.js
      constants.js
      media-transfer.js
    platforms/
      platform-adapter.js
      shopee/adapter.js
      ai-web/adapter.js
      google-flow/
        adapter.js
        selectors.js
        injected-result-observer.js
        result-observer-content.js
    ui/
      overlay.js
  background.js
  content.js
  chatgpt.js
  flow.js
  manifest.json
```

ทุก module ต้องมีหน้าที่ชัดเจนและต้องถูก import/เรียกใช้จริง

## 3. LOCAL APP BRIDGE

Runtime ปัจจุบันใช้ authenticated HTTP Local Bridge และต้องคง backward compatibility รองรับ WebSocket localhost เป็น transport เสริมเมื่อ Desktop เปิด endpoint ที่ authenticated แล้วเท่านั้น

Job ต้องมีอย่างน้อย `id`, `action`, `client_id`, `run_id`, `lease_token`, `job_id`, `shot_index` และข้อมูลเฉพาะ action ส่วนผลต้องเป็น structured result พร้อม error code

WebSocket ต้องมี exponential backoff, heartbeat, request ID, duplicate result receipt, timeout และ pairing token/nonce ที่เปลี่ยนได้ ห้ามใส่ secret/token ใน URL และห้ามส่ง cookie, access token, Authorization header หรือ credential จาก browser ไป Desktop

## 4. JOB ROUTER

ใช้ `Map` registry กลาง ห้ามเพิ่ม action ที่รัน arbitrary JavaScript ทุกคำสั่งต้องผ่าน schema, allowlist, timeout และ structured error ก่อน execute

รองรับ progress/cancel เมื่อ action ทำได้ และ duplicate request ID ต้องคืน receipt เดิมโดยไม่ทำ physical action ซ้ำ

## 5. PLATFORM ADAPTER

ใช้ interface `detect()`, `status()`, `prepare()`, `execute(action,payload)`, `cleanup()` แยก Shopee, AI Web และ Google Flow Background core ห้ามเพิ่ม DOM selector เฉพาะเว็บไซต์ใหม่

ช่วง incremental migration ให้ adapter เรียก Legacy delegate เดิมได้ แต่ห้ามเปลี่ยน physical action และ state transition ของ Google Flow พร้อมกับการย้ายไฟล์

## 6. CONTENT SCRIPT

แต่ละแพลตฟอร์มมี message dispatcher กลาง ใช้ structured result และ validate message ทุกครั้ง ห้ามกระจาย listener ที่ทำงานเดียวกันหลายตัวในหน้าเดียว

## 7. MAIN WORLD INJECTION

ใช้เมื่อจำเป็นจริงและสื่อสารผ่าน `window.postMessage` ที่มี namespace, channel, requestId, type และ payload ตรวจ `event.source === window`, namespace, type, requestId, schema, URL และ timeout พร้อม cleanup listener

Google Flow observer เป็น read-only เท่านั้น ห้าม monkey-patch `fetch`, `URL.createObjectURL`, anchor click หรือ prototype และห้ามคลิก/Reload/Submit

## 8. AUTHENTICATION

ใช้ session ที่ผู้ใช้ Login อยู่แล้ว ห้าม bypass Login/CAPTCHA, ดึง password, export cookie/token หรือส่ง credential ไป Desktop หาก Logout ให้คืน `AUTH_REQUIRED` แล้วพัก Job/timeout จนผู้ใช้ Login เอง

## 9. DOM AUTOMATION

Selector ใหม่ต้องอยู่ใน adapter/selectors ของแพลตฟอร์ม มี bounded timeout และ fallback ที่มีหลักฐาน ห้าม infinite loop และห้ามเดา private endpoint

Google Flow ต้องรักษา Golden transaction:

```text
แนบรูปครั้งเดียว → รอ media พร้อม → เลือกรูปเข้า Composer
→ ใส่ Prompt แบบ trusted → ตรวจรูป+Prompt → กดสร้างครั้งเดียว
→ อนุมัติครั้งเดียว → รอ → ดาวน์โหลดก่อนเปลี่ยนหน้า
```

## 10. MEDIA TRANSFER

ไฟล์ใหญ่ห้ามส่ง Base64 ก้อนเดียว ใช้ transferId, sequence, totalChunks, TTL, max size, checksum และ cleanup เมื่อ chunk ไม่ครบต้องยกเลิกด้วย `TRANSFER_INCOMPLETE`

สำหรับวิดีโอ Flow ให้ `chrome.downloads` เขียนไฟล์โดยตรงเป็นหลัก ใช้ chunk transport เฉพาะกรณีที่ไม่มีเส้นทางดาวน์โหลดไฟล์จริง

## 11. STATUS SYSTEM

Adapter ต้องรายงาน `connected`, `loggedIn`, `ready`, `url`, `account` โดยไม่ใช้ cookie/token เป็นหลักฐานเดียว ตรวจจาก UI ที่ authenticated หรือ endpoint ที่รองรับเมื่อเหมาะสม และห้ามส่งข้อมูลบัญชีที่ละเอียดเกินจำเป็น

## 12. PROGRESS EVENTS

ส่ง stage เช่น `preparing`, `uploading`, `processing`, `waiting`, `downloading`, `completed` พร้อม Job/Run/Shot และข้อความที่ผู้ใช้อ่านเข้าใจ Progress จากแท็บหรือ Run เก่าต้องถูกปฏิเสธ

## 13. RETRY

Retry utility กลางรองรับ maxAttempts, initialDelay, exponentialBackoff, 408, 429, 5xx และ AbortSignal แยก DOM retry จาก HTTP retry ไม่ Retry auth error, current generation หรือ physical action ที่ไม่มี receipt

ทุก Retry ของ Flow ทำเฉพาะ Shot ที่ขาดและไม่เกินเพดานเดิม ห้ามย้อนภาพ/เสียง/คลิปที่สำเร็จแล้ว

## 14. WINDOW/TAB MANAGEMENT

ใช้ TabManager/WindowManager กลางสำหรับค้นหา เปิด รอ Focus เมื่อผู้ใช้ต้องทำเอง Reuse และปิด worker tab ห้าม Reload เพียงเพราะ content script คนละรุ่น ห้ามปิด/ย้ายหน้าต่างที่ผู้ใช้กำลังโฟกัส และหนึ่ง Job+Shot ต้องมี owner tab เดียว

## 15. EXTENSION VERSION CHECK

Manifest, Local Bridge required version, helper version และ build ID ต้องตรง ถ้า stale ให้หยุดรับคำสั่งและแจ้งอัปเดต ห้าม `chrome.runtime.reload()` หรือ Reload Flow เป็นวงรอบ Helper เก่าบน SPA ให้แทนที่ shell แบบ single-flight โดยไม่สร้าง Project ใหม่

## 16. PERMISSIONS

ใช้ least privilege ห้าม `<all_urls>`, cookies และ system.display สิทธิ์ `debugger` คงไว้เฉพาะ trusted file/text/mouse actions ที่ Golden Flow ต้องใช้ และต้อง validate tab/domain ก่อนทุกครั้ง

## 17. LOGGING

Logger ต้องมี debug/info/warn/error/progress พร้อม platform, jobId, action, stage และ event code ห้าม Log password, cookie, authorization, access/session/lease token หรือ query string ของ signed media URL

## 18. ERROR MODEL

ใช้ error code กลาง: `AUTH_REQUIRED`, `TAB_NOT_FOUND`, `PAGE_NOT_READY`, `ELEMENT_NOT_FOUND`, `UPLOAD_FAILED`, `API_ERROR`, `RATE_LIMITED`, `TIMEOUT`, `CANCELLED`, `UNSUPPORTED_ACTION`, `CONTENT_SCRIPT_STALE`, `BRIDGE_DISCONNECTED`, `INVALID_MESSAGE`, `DUPLICATE_JOB`, `SECURITY_REJECTED`, `TRANSFER_INCOMPLETE`

Desktop ต้องตัดสินใจจาก code ได้โดยไม่ parse ข้อความภาษาไทย

## 19. UI OVERLAY

Overlay กลางรองรับ loading/progress/error/hide ใช้ Shadow DOM และห้ามบัง Composer ปุ่มอนุมัติ หรือการ์ดผลลัพธ์ Google Flow Helper overlay ต้องถูกตัดออกจาก result/progress detector เสมอ

## 20. SECURITY

Validate message, URL, tabId, platform/domain และ payload ทุกครั้ง ไม่มี action `eval`, `executeRawScript`, `runJavascript` Token ของ Local Bridge อยู่ใน memory/header เท่านั้นและหมุนใหม่ทุก Engine session

## 21. DEVELOPMENT RULE

- สร้าง Source ใช้งานจริง ไม่ใช้ pseudo-code สำหรับ core
- Module ใหม่ต้องมี import/wiring และ regression test
- ห้ามเดา selector/API หากข้อมูลหน้าเว็บไม่พอ
- อ่าน `CODEX_START_HERE.md`, `EXTENSION_BLUEPRINT.md` และ `PROGRAM_BLUEPRINT.md` หัวข้อ 12.4 ก่อนแก้ Flow
- เปลี่ยนทีละชั้นและรักษา Golden rollback `0.15.112 / afcb918`
- ห้ามเรียกรุ่นใหม่ว่า Golden จนมีงานจริง 3 Shot และ Final ผ่าน QA

## 22. TESTING

ต้องมี router, schema, retry, chunk transfer, adapter, permission/security และ passive observer tests พร้อม manual checklist:

- Load Unpacked และ version ตรง Local Bridge
- Bridge connect/disconnect/reconnect
- Target tab discovery และ Login gate
- Command/progress/error/cancel
- Reload Extension/target tab โดยไม่สร้างงานซ้ำ
- Flow upload/attach/submit/approve อย่างละหนึ่ง physical action
- Download receipt และ SHA ไม่ซ้ำ
- ปิดโปรแกรมแล้ว browser worker หยุด

รัน syntax, targeted tests, full suite และ real smoke test แบบผู้ใช้กดจากโปรแกรมเท่านั้นก่อนประกาศพร้อมใช้จริง

## 23. OUTPUT ORDER

1. วิเคราะห์ requirements และ architecture
2. สร้าง file tree
3. กำหนด protocol/schema
4. ปรับ manifest
5. สร้าง Core + Bridge + JobRouter
6. สร้าง Platform Adapter
7. สร้าง Content/Main-world observer เมื่อจำเป็น
8. สร้าง Status/Error/Retry/Progress
9. สร้าง tests
10. ตรวจ security/permissions
11. ส่ง Source ที่เชื่อมต่อจริง พร้อมรายงานสิ่งที่ยังเป็น Legacy adapter อย่างตรงไปตรงมา

หลังแต่ละ Phase ต้องตรวจว่าเชื่อมกับ Phase ก่อนหน้าและไม่เปลี่ยน Golden Flow physical action โดยไม่มีหลักฐานใหม่ เป้าหมายคือ Extension ที่เพิ่มแพลตฟอร์มภายหลังได้โดยไม่แก้ Core และ Resume งานเดิมได้โดยไม่เสียเครดิตซ้ำ
