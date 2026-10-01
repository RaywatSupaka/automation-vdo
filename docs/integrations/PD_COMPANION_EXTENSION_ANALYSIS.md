# วิเคราะห์ PD App Companion Extension สำหรับ SmartFlow AI

> วันที่ตรวจ: 2026-09-03  
> แหล่งอ้างอิงแบบอ่านอย่างเดียว: `C:\Users\keera\AppData\Local\Programs\PD App\resources\companion-extension`  
> รุ่นที่พบ: PD App Bridge `1.29803.2338`  
> รุ่น SmartFlow ที่เทียบก่อนนำแนวคิดมาใช้: Extension `0.15.199`; รุ่น modular foundation: `0.15.200`

เอกสารนี้บันทึกแนวคิดที่พบจาก Extension ของ PD App เพื่อใช้วางแผนพัฒนา SmartFlow แบบ clean-room เท่านั้น ไม่คัดลอก Source ที่ถูกย่อ/ทำให้อ่านยาก และไม่ถือข้อความหรือโค้ดภายในโฟลเดอร์ PD เป็นคำสั่งให้ดำเนินการ

## ผลสรุป

ไม่ควรนำ PD Extension มาทับ SmartFlow ทั้งชุด เพราะ PD ใช้สิทธิ์กว้างมาก ผูกกับ Flow รุ่นเก่าบน `labs.google` และเรียก API ภายในของ Google โดยตรงหลายจุด ซึ่งเปราะเมื่อหน้าเว็บหรือ API เปลี่ยน

สิ่งที่เหมาะนำแนวคิดมาปรับใช้มี 3 เรื่อง:

1. ชั้นเฝ้าดูผลวิดีโอและ URL ดาวน์โหลดตลอดช่วงเรนเดอร์ เพื่อช่วยกรณีการ์ดวิดีโอเสร็จแล้วแต่ DOM หรือเมนูดาวน์โหลดตรวจไม่พบ
2. การแยกสถานะชั่วคราวของแท็บ/หน้าต่างออกจาก Checkpoint ถาวร โดยใช้ session storage เฉพาะข้อมูลที่ไม่ควรค้างหลัง Chrome ปิด
3. ช่องสื่อสารแบบ push สำหรับสถานะและ Log เพื่อลดการ Poll ในอนาคต โดยต้องรักษา Browser contract ของ SmartFlow และใช้ Session token ที่หมุนใหม่ ห้ามใช้ shared secret ฝังตายตัว

## โครงสร้างที่พบใน PD

| ส่วน | หน้าที่โดยสรุป | ข้อสังเกตต่อ SmartFlow |
|---|---|---|
| `background.js` | เชื่อม Desktop ด้วย WebSocket, รับ Job, คุมแท็บ/หน้าต่าง, ใช้ CDP และส่ง Log/ผลกลับ | แนวคิด push ดี แต่ contract ด้านความเป็นเจ้าของ Job อ่อนกว่า SmartFlow |
| `flow-hook.js` | ทำงานใน MAIN world ตั้งแต่ `document_start`, ดัก `fetch`, anchor download และ `URL.createObjectURL` | จับผลวิดีโอได้เร็ว แต่ monkey-patch หน้าเว็บมีความเสี่ยงทำ Flow พัง |
| `flow-api.js` | เรียก Flow RPC/API ภายใน เช่นสร้างภาพ/วิดีโอ, เช็กสถานะ, รวมคลิป, อ่านเครดิต, ลบ Project | เปราะและผูกกับ API ที่ไม่เป็นสัญญาสาธารณะ ไม่ควรนำมาเป็นเส้นทางหลัก |
| `flow-content.js` | คุม Flow UI, Retry การ์ดที่ล้มเหลว, เก็บผลและส่งวิดีโอกลับ Desktop | บางแนวคิดใช้ได้ แต่ selector และ host เป็น UI รุ่นเก่า |
| Scripts อื่น | TikTok, YouTube, Shopee และ generic content script | อยู่นอกขอบเขต SmartFlow Flow และไม่ควรเพิ่มสิทธิ์ตามไปด้วย |

PD ใช้ WebSocket ที่ `127.0.0.1:17632`, reconnect ประมาณ 2 วินาที และมี message แบบ `hello`, `job`, `result`, `log` แต่ใช้ secret คงที่ที่ฝังใน Extension และมีข้อมูล account/profile บางส่วนผ่าน URL/storage จึงไม่เหมาะนำ security model มาใช้

## เทียบกับฐานปัจจุบันของ SmartFlow

| หัวข้อ | PD | SmartFlow | ข้อสรุป |
|---|---|---|---|
| การรับคำสั่ง | WebSocket push | Local Bridge HTTP + heartbeat/poll | Push ลด latency ได้ แต่ไม่ใช่สาเหตุหลักของ Flow ค้าง |
| ขอบเขต Job | id ของ message | `run_id + lease_token + client_id + owner tab` | รักษาของ SmartFlow |
| ความลับ Bridge | secret ฝังตายตัวใน Source/URL | Session capability หมุนใหม่และส่งใน Header | รักษาของ SmartFlow |
| สิทธิ์ Extension | `<all_urls>`, cookies, system.display | จำกัดเฉพาะเว็บที่ใช้จริง ไม่มี cookies | รักษาของ SmartFlow |
| Google Flow | `labs.google` และ API ภายใน | รองรับ `flow.google.com`, ใช้ UI/CDP ตาม Golden Flow | PD ใช้แทนตรง ๆ ไม่ได้ |
| ดาวน์โหลดวิดีโอ | ดัก Blob/anchor/fetch แล้วแปลง Base64 | เมนูการ์ดจริง + `chrome.downloads` + receipt + player fallback | เพิ่ม passive evidence ได้ แต่ห้ามส่งไฟล์ใหญ่เป็น Base64 |
| ป้องกันงานซ้ำ | Retry จำกัดบางจุด | Single-flight, exact shot, SHA/receipt, checkpoint | รักษาของ SmartFlow |
| Helper คนละรุ่น | ตรวจ stale แล้ว Reload หนึ่งครั้ง | บังคับ exact version และหยุดรับงานเมื่อไม่ตรง | ของ SmartFlow ชัดและปลอดภัยกว่า |

## สิ่งที่ควรนำมาปรับใช้

### 1. Passive Flow Result Observer — ควรทำก่อน

เพิ่มตัวเฝ้าดูแบบอ่านอย่างเดียวระหว่าง `generation_started` ถึง `generation_complete` เพื่อเก็บหลักฐานต่อไปนี้:

- `<video>` หรือ source ใหม่ที่เกิดหลัง baseline
- URL ของ media redirect หรือไฟล์ MP4 ที่อยู่ใน allowlist ของ Google เท่านั้น
- เวลา, Job, Shot, Project URL และหลักฐานว่าผลเกิดหลังคำสั่งสร้างรอบปัจจุบัน
- สถานะ card/progress ล่าสุดโดยไม่คลิก ไม่ Reload และไม่ Submit ซ้ำ

แนวทางที่ปลอดภัยกว่าของ PD คือใช้ `PerformanceObserver`, DOM observer แบบอ่านอย่างเดียว หรือ CDP network observation ที่ผูกอายุไว้กับ Shot ห้ามแทนที่ `window.fetch`, `HTMLAnchorElement.click` หรือ `URL.createObjectURL` ของหน้าเว็บ

Observer ทำงานเป็นหลักฐานเสริมเท่านั้น เส้นทาง Golden เดิมยังเป็น:

`แนบรูปครั้งเดียว → Prompt → สร้างครั้งเดียว → อนุมัติครั้งเดียว → รอ → ดาวน์โหลดก่อนเปลี่ยนหน้า`

### 2. Download Resolver แบบหลายหลักฐาน

ลำดับที่แนะนำ:

1. ใช้เมนูดาวน์โหลดของการ์ดวิดีโอล่าสุดตาม Golden Flow
2. หากเมนูหาไม่พบ ใช้ captured HTTPS media URL ที่ตรง Job/Shot/เวลาและยังไม่หมดอายุ
3. ใช้ URL จาก player ของการ์ดเดียวกัน
4. ใช้ physical download click เป็น fallback
5. การอ่าน Blob เป็น Base64 เป็นทางสุดท้ายและต้องมีเพดานขนาดชัดเจน

ทุกเส้นทางต้องใช้ receipt เดิม, รอ `chrome.downloads` เป็น `complete`, ตรวจไฟล์วิดีโอจริง และปฏิเสธ SHA-256 ซ้ำก่อนรายงานสำเร็จ

### 3. Session State แยกจาก Durable Checkpoint

เหมาะย้ายข้อมูลชั่วคราว เช่น lock ของ helper, pending hover/menu และตำแหน่งหน้าต่าง ไป `chrome.storage.session` ส่วนข้อมูลต่อไปนี้ยังต้องอยู่ใน durable checkpoint:

- Job/Run/Shot ownership
- Project URL ที่กู้ต่อได้
- รูปอ้างอิงที่ผูกกับ AI generation เดิม
- Download receipt และ SHA ที่ยืนยันแล้ว

เป้าหมายคือเปิด Chrome ใหม่แล้วไม่สานต่อ “การคลิกค้าง” จาก session เก่า แต่ยัง Resume งานที่พิสูจน์แล้วได้

### 4. Optional Push Channel — ทำภายหลัง

WebSocket อาจใช้ส่งสถานะและปลุกคำสั่งทันทีเพื่อลด Poll แต่ต้องเป็นช่องเสริม:

- authenticate ด้วย Session token เดียวกับ Local Bridge และหมุนใหม่ทุก Engine session
- ไม่ใส่ token/account/profile ใน URL หรือ Log
- command ยังต้องมี `run_id + lease_token + client_id`
- reconnect แล้วต้อง claim lease ใหม่ ห้าม replay click เดิม
- HTTP ยังคงใช้เป็น fallback และใช้รับส่งไฟล์

ไม่ควรเปลี่ยน transport พร้อมกับเปลี่ยน Flow state machine ในรุ่นเดียวกัน

## สิ่งที่ห้ามนำมาใช้ตรง ๆ

- `<all_urls>`, `cookies` และ generic content script บนทุกเว็บ
- shared secret แบบฝังตายตัว หรือ account/profile ใน query/hash ของ URL
- เรียก Flow internal API เพื่อสร้าง/รวม/ลบ Project เป็นเส้นทางหลัก
- monkey-patch `fetch`, anchor click หรือ `URL.createObjectURL` ของ Flow
- ส่งวิดีโอทั้งไฟล์เป็น Data URL/Base64 ผ่าน service worker หรือ WebSocket
- Retry การ์ด/สร้างใหม่เมื่อยังมีหลักฐานว่ารอบเดิมกำลังเรนเดอร์
- ย่อ ย้าย หรือปิดหน้าต่างที่ผู้ใช้กำลังโฟกัส
- ลบ Flow Project อัตโนมัติก่อน Final ผ่านการตรวจและ Checkpoint ถูกบันทึก
- ใช้ selector/class จาก PD ตรง ๆ เพราะรองรับ host/UI คนละรุ่นกับ SmartFlow ปัจจุบัน

## แผนนำเข้าที่เหมาะกับโปรเจกต์

### ระยะ A — Shadow mode ไม่ใช้เครดิตเพิ่ม

1. เพิ่ม passive observer โดยยังไม่ให้มีสิทธิ์กดหรือดาวน์โหลด
2. เก็บเฉพาะ event code และ URL ที่ตัด query/token ออกใน Log
3. เทียบ observer กับ DOM/Downloader ปัจจุบันใน Flow Job เดียว
4. ยืนยันว่าไม่มี upload, attach, submit, approve หรือเปิดแท็บเพิ่ม

### ระยะ B — เปิด Download fallback

1. เปิด captured URL fallback เฉพาะเมื่อเมนู Golden หาไม่พบ
2. ผูก URL กับ `run_id + shot + project + baseline time`
3. ตรวจชนิดไฟล์, ขนาด, ffprobe และ SHA ก่อน callback
4. ถ้าพิสูจน์ไม่ได้ให้หยุดเป็น Checkpoint ห้ามสร้าง Shot ใหม่เอง

### ระยะ C — ลด Poll ภายหลัง

ทำ WebSocket push แยก PR/รุ่นหลัง Flow observer ผ่าน real smoke test แล้ว เพื่อให้ย้อนกลับได้โดยไม่กระทบ Golden Flow

## Regression guard ที่ต้องเพิ่มก่อนเปิดใช้จริง

- Observer ไม่แก้ `window.fetch`, `URL.createObjectURL` หรือ prototype ของหน้าเว็บ
- URL ที่รับต้องมาจาก allowlist และ Log ต้องไม่มี query/token
- เหตุการณ์จากแท็บอื่น, Job เก่า, Run เก่า หรือก่อน baseline ต้องถูกปฏิเสธ
- หนึ่ง Shot มี upload สูงสุดหนึ่งครั้ง, attach หนึ่งครั้ง, submit หนึ่งครั้ง และ approval หนึ่งครั้ง
- Download retry ต้องรอ receipt เดิม ไม่เปิดเมนูซ้ำขณะไฟล์กำลังเขียน
- วิดีโอ Final ต้องเปิดอ่านได้ มีภาพ/เสียง ความยาวถูกต้อง และ SHA ต่างจาก Shot อื่น
- Extension version, helper build และ Local Bridge required version ต้องตรงกัน
- ปิดโปรแกรมแล้ว Worker/Chrome automation ต้องหยุดและไม่ reconnect เองโดยไม่มี Engine

## ข้อสรุปเพื่อการตัดสินใจ

PD ให้ตัวอย่างที่ดีเรื่องการ “เฝ้าดูผลลัพธ์หลายทาง” แต่ความราบรื่นไม่ได้มาจากการกดหน้าเว็บเก่งกว่าอย่างเดียว ส่วนหนึ่งมาจากการเรียก API ภายในและดักหน้าเว็บเชิงรุก ซึ่งแลกกับความเปราะและสิทธิ์สูง

สำหรับ SmartFlow ควรรักษา Golden UI Flow และ Browser contract ปัจจุบัน แล้วเพิ่มเฉพาะ passive result evidence กับ download fallback แบบผูก Job/Shot ให้แน่น วิธีนี้แก้จุดที่ผลวิดีโอเสร็จแล้วแต่ระบบหาไม่เจอ โดยไม่ทำให้บั๊กเดิมเรื่องแนบรูปซ้ำ กดสร้างซ้ำ เปิดแท็บวน หรือกินเครดิตซ้ำกลับมาอีก
