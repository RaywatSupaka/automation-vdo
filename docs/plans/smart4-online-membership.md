# SmartFlow AI — แผนระบบสมาชิก, Token และอัปเดตผ่านเซิร์ฟเวอร์

แผนเดิม: 2026-09-16 • รวมและทบทวน: 2026-09-20

**เพิ่มข้อกำหนดอัปเดตโดยไม่ล็อกอินซ้ำ (2026-09-20):** ตัวตนสมาชิก/เครื่อง/Chrome profile ต้องคงเดิมข้ามเวอร์ชัน เลขเวอร์ชันใช้ตรวจความเข้ากันได้และแสดงผลเท่านั้น ไม่ใช้สร้างผู้ใช้ใหม่ การคืนสิทธิ์ใช้ renewal credential ใน Windows ไม่เก็บ API Token ดิบหรือคัดลอกข้อมูล Chrome หลังอัปเดต หน้ารอคืนสิทธิ์ต้องไม่บังคับกรอก Token อีกครั้ง คงเงื่อนไขหมดอายุ/เพิกถอน/เตะ/เปลี่ยนเครื่องหรือโปรไฟล์ ผู้ใช้อนุมัติเตรียมย้ายจากโฟลเดอร์รุ่นไป `browser_extension` ถาวรครั้งเดียว; ยังไม่ย้ายจริง และ P3 ต้องอัปเดตไฟล์ในตำแหน่งเดิม/รักษา Extension ID กับ receipt ก่อน Reload ไม่ Load unpacked เป็นคนละตัวทุกเวอร์ชัน ดู [แผนย้าย](../reports/extension-login-persistence-386/MIGRATION.md)

**สถานะ 2026-09-20: P1 หลังบ้านขึ้นเซิร์ฟเวอร์แล้วตามรายงาน deploy ในโปรเจกต์เซิร์ฟเวอร์; P2 หน้า Login desktop/Extension และตัวตรวจสิทธิ์เชื่อมตาม API จริงแล้ว ทดสอบแยกโดยยังไม่ใช้ Token ลูกค้าจริง ไม่ restart/reload งานผู้ใช้ และยังไม่ผ่าน installed/frozen E2E; P3 updater/P4 installer ยังไม่เสร็จ** ดู [รายงาน client384](../reports/membership-384/README.md)

ชื่อผลิตภัณฑ์ที่ผู้ใช้ยืนยันคือ **SmartFlow AI** ไม่ใช่ Smart4 ส่วนชื่อไฟล์ `smart4-online-membership.md` คงไว้เพื่อให้ลิงก์เดิมเปิดได้ ไม่ใช่ชื่อแบรนด์ใหม่ ทุกหน้า/API/ข้อความใหม่ต้องใช้ SmartFlow AI และคง `app_id=smartflow` เดิม

**ข้อยืนยันล่าสุด 2026-09-20:** รวม Login/Token, สมาชิกออนไลน์/บล็อก/เตะ, อัปเดต และตัวติดตั้งในแผนเดียวกัน โดย desktop และ Extension ตรวจสิทธิ์กับเซิร์ฟเวอร์ที่เจ้าของเปิดอยู่ ไม่ใช่แค่ตรวจ Token ในเครื่อง หน้าอัปเดตหลังบ้านมีเพียง **แพตช์โปรแกรม ZIP + Extension ZIP**; `release.json` อยู่ภายในแพตช์ และตัวติดตั้ง EXE อยู่ส่วนลูกค้าใหม่แยกต่างหาก ข้อนี้แทนข้อเสนอเก่าให้เลือกไฟล์รวมหนึ่งไฟล์หรือให้เลือก release.json/EXE แยกในหน้าออกแพตช์ ไม่ใช่การอนุมัติ deploy หรือคำยืนยันว่าพัฒนาแล้ว

## 1. เป้าหมายที่ผู้ใช้กำหนด

- แอดมินออก Token ให้ลูกค้าใช้เข้า SmartFlow AI และ Extension ของ SmartFlow AI
- หลังบ้านแสดงสมาชิก/เครื่องที่ออนไลน์ แอดมินบล็อกหรือเตะออกได้
- เมื่อมีรุ่นใหม่ เจ้าของโปรแกรมขอให้จัดทำไฟล์แพตช์ แล้วนำไฟล์นั้นไปอัปโหลดเข้าเซิร์ฟเวอร์เอง
- หน้าออกอัปเดตมีสองช่องเท่านั้น: แพตช์โปรแกรม ZIP และ Extension ZIP (ช่องหลังไม่บังคับเมื่อใช้รุ่นเดิมที่ตรวจแล้ว) ไม่มีช่องให้แอดมินเลือก `release.json` หรือ EXE ในขั้นตอนนี้
- เมื่อเผยแพร่แล้ว โปรแกรมลูกค้าตรวจพบและแจ้งป๊อปอัป ผู้ใช้กด **อัปเดต** แล้วโปรแกรมดาวน์โหลด ตรวจสอบ ติดตั้ง และเปิดใหม่ให้เอง ไม่ต้องแตก ZIP หรือคัดลอกไฟล์โปรแกรม
- รักษางานเดิม การตั้งค่า คิว รูป เสียง วิดีโอ Token และใบรับผลจาก Extension ไม่สั่งสร้างหรือโพสต์ซ้ำหลังอัปเดต
- ทำต่อจากระบบอัปเดตที่มีแล้ว ไม่สร้างระบบคู่ขนาน ไม่แตะงานของ VoiceClone/Subtitle และไม่เปลี่ยนวิธีสร้างคลิปจากการทำระบบสมาชิก

ลำดับหลัก: **จัดทำแพตช์ → เจ้าของอัปโหลด → ตรวจครบและเผยแพร่ → ลูกค้าเห็นป๊อปอัป → กดอัปเดต → ติดตั้งเมื่อปลอดภัย → เปิดใหม่และตรวจรุ่นจริง**

## 2. สิ่งที่ตรวจพบในโค้ดปัจจุบัน

สำรวจเดิมวันที่ 2026-09-19 และปรับสถานะสมาชิกวันที่ 2026-09-20; การพบโค้ดไม่ใช่หลักฐานว่าเผยแพร่ให้ลูกค้าหรือผ่านการติดตั้งบนเครื่องอื่นแล้ว

| ส่วน | มีแล้ว | ยังต้องทำ/ยืนยัน |
|---|---|---|
| สมาชิก SmartFlow | P1 server/admin deployed; P2 Login และตัวตรวจสิทธิ์ desktop/Extension384 ใช้ API เดียวกัน มีการทดสอบแยก | ยังต้องทดสอบ installed/frozen EXE, Extension จริง, admin kick และเครื่องลูกค้าสะอาด |
| หลังบ้านอัปเดต | หน้า `/admin3s/smartflow-updates`, ร่างรุ่น, อัปโหลดเป็นชิ้น, ตรวจไฟล์, กดเผยแพร่ | ปรับเป็นสองช่องแพตช์ ZIP/Extension ZIP, อ่าน signed metadata จากแพตช์ และแยก EXE ไปส่วนลูกค้าใหม่ |
| ข้อมูลรุ่น | `/api/smartflow-updates/latest/{channel}`, ไฟล์ตาม SHA-256, signed release | client ปัจจุบันระบุ beta ตายตัว; ต้องเลือก stable/beta ตามสิทธิ์และการตั้งค่าที่เชื่อถือได้ |
| แจ้งอัปเดต | `web_ui/updates.js` ตรวจหลังเปิดประมาณ 7 วินาทีและมีป๊อปอัปเมื่อว่าง | ยังไม่มีวงรอบตรวจรุ่นใหม่ขณะเปิดค้าง; ปัจจุบันดาวน์โหลดกับติดตั้งแยกปุ่ม |
| ตัวติดตั้งแพตช์ | `desktop/update_api.py`, `core/app_updates.py`, `tools/customer_updater.py` ตรวจลายเซ็น/ขนาด/hash, สำรองรายไฟล์, เปิดใหม่ตรวจสุขภาพ, rollback เมื่อเปิดไม่สำเร็จ | เพิ่มธุรกรรมทนเครื่องดับ/ไฟล์ล็อก, การกู้สถานะ, safe-idle ครอบคลุมทุกงาน และการตรวจคู่ Extension |
| สร้างแพตช์ | `tools/sign_customer_release.py` สร้าง cumulative code ZIP + signed `release.json` | ตอนนี้รวมไฟล์โปรแกรมทั้งชุดและคาดหวัง Extension ZIP/installer EXE; ยังไม่ใช่ตัวสร้างแพตช์ส่วนต่างเล็ก ๆ แบบเลือกได้ทุกกรณี |
| Extension | ดาวน์โหลด ZIP แยก และตรวจรุ่นที่เชื่อมต่อ | ปัจจุบันยังมีขั้นตอนผู้ใช้เปลี่ยนไฟล์/Reload; ห้ามอ้างว่าพออัปโหลดเซิร์ฟเวอร์แล้ว Chrome จะเปลี่ยนให้เอง |

`CURRENT_RELEASE.json` แยก source runtime `0.15.382` ออกจาก customer distribution `0.3.0-beta.8` ซึ่งจับคู่ Extension `0.15.276` และบันทึก `online_published=false` อย่าเอาเลข Extension มาแทนเลขเวอร์ชันโปรแกรม หรือถือว่าชุดพัฒนาล่าสุดอยู่ในตัวติดตั้งลูกค้าแล้ว ต้องตรวจ metadata ใหม่ทุกครั้งก่อนบิลด์

เซิร์ฟเวอร์ที่ตรวจ: `C:/Users/keera/AppData/Local/SmartSubAI/VoiceCloneOnline`; มี frontend/backend ทำงานอยู่ แต่รอบนี้ไม่ได้ตรวจการเผยแพร่ของทุก channel ผ่านบัญชีลูกค้า ไม่ได้เปิด/อ่าน secrets และไม่ได้ปรับบริการ

## 3. ออกแบบ Token และการเข้าใช้งาน

### 3.1 สมาชิกหนึ่งราย สิทธิ์เดียว แยกขอบเขตสอง client

- แยก `member`, `entitlement`, `activation_token`, `device`, `session` และ `audit_event` ของ SmartFlow ไม่ใช้ Token เพจ Facebook, SmartSub API หรือ local bridge เป็น license
- แอดมินออก activation Token สอง scope คือ `desktop` และ `extension` ภายใต้ entitlement เดียวกัน แสดงตัวเต็มครั้งเดียว; หลังบ้านเก็บ digest สำหรับ Token ที่สุ่มอย่างแข็งแรง ไม่เก็บค่าตัวเต็มใน log
- แลก activation เป็น device credential และ session อายุสั้น แยกสิทธิ์ตาม client และผูกสมาชิก/เครื่องเดียวกัน ไม่ส่ง activation Token ไปทุก heartbeat
- ค่าเริ่มต้นเสนอ: 1 เครื่อง + 1 Chrome profile; แอดมินกำหนดจำนวนเครื่อง วันหมดอายุ และ feature/channel ได้ โดยมี transaction กัน activation สองเครื่องพร้อมกันเกินสิทธิ์
- Desktop เก็บ credential ใน Windows Credential Manager/กลไกป้องกันของ Windows; Extension ให้ background เป็นผู้ถือ credential อายุสั้นและจำกัดขอบเขต ไม่เผยให้ content scripts, provider DOM, URL หรือ telemetry
- คงการตรวจ local bridge token ที่มีอยู่เพื่อป้องกันช่องทางในเครื่อง เป็นคนละชั้นกับสิทธิ์สมาชิก ไม่เปลี่ยนตัวหนึ่งให้แทนอีกตัว
- UX: หน้าเข้า SmartFlow AI มีช่อง Token, ปุ่มเปิดใช้งาน, สถานะตรวจสอบ/หมดอายุ/ถูกบล็อก และวิธีติดต่อแอดมิน; การจับคู่ Extension ใช้ flow ง่าย ๆ แต่ต้องตรวจสิทธิ์จริงทั้งสองฝั่ง
- แผน API ชื่อใหม่ใช้ namespace SmartFlow เฉพาะ เช่น `/api/smartflow-membership/*` สำหรับ activate/renew/heartbeat/logout และ admin operations; เป็นชื่อเสนอ ยังไม่มี route เหล่านี้ที่ยืนยันว่าทำแล้ว

### 3.2 ออนไลน์ บล็อก เตะออก

- ค่าเสนอ: heartbeat ทุก 30 วินาทีพร้อม jitter; last_seen ภายใน 90 วินาทีเป็นออนไลน์, 90–180 วินาทีเป็นขาดการติดต่อ, เกิน 180 วินาทีเป็นออฟไลน์ ไม่ตีความ heartbeat หายว่าโดนบล็อก
- แสดง desktop และ Extension แยกกัน พร้อมเครื่อง รุ่นโปรแกรม รุ่น Extension เวลาพบล่าสุด สถานะ license และ update; ไม่แสดง Token เต็ม
- **เตะออก**: ผู้ใช้ยืนยัน 2026-09-20 ว่าใช้ Token เดิมเข้าสู่ระบบได้ตามปกติ **1 Token ต่อ 1 เครื่อง**; revoke session และ renewal credential แต่ไม่เพิกถอน activation Token และไม่ล้าง binding ต้องกลับกรอก Token เองที่เครื่องเดิม ไม่ activate กลับเอง การย้ายเครื่องใช้ปุ่มปลดผูกเครื่องของแอดมินแยกต่างหาก เตะ desktop ให้เตะ Extension ที่จับคู่ด้วย; เตะ Extension อย่างเดียวไม่เตะ desktop
- **บล็อก**: ปิด entitlement ไม่ให้ activate/renew หรือเริ่มงานใหม่ได้จนแอดมินปลด; reset device, revoke Token และ rotate Token เป็นคนละ action มี confirmation/audit
- เสนอ lease 5 นาทีสำหรับขาดการติดต่อ; ขณะออนไลน์ตรวจคำสั่ง revoke ใน heartbeat จึงควรเห็นผลรอบถัดไป ไม่อ้างว่าเตะได้ทันทีเมื่อเครื่องลูกค้าออฟไลน์
- ตรวจสิทธิ์ก่อน create/queue/resume/เปลี่ยนฉาก/ส่งคำสั่ง browser ใหม่; ฝั่งเซิร์ฟเวอร์ตรวจด้วย ไม่ใช่ซ่อนปุ่ม UI อย่างเดียว
- ถ้าหมดสิทธิ์หรือ server ล่มเกิน lease ให้หยุดรับงาน/ส่งคำสั่งใหม่ที่จุดปลอดภัย คงข้อมูลและเก็บผลของคำขอที่ส่งไปแล้วได้เท่าที่ปลอดภัย ห้ามรีเซ็ต receipt หรือวนส่งใหม่
- งานที่ส่งไป provider แล้วไม่สามารถรับประกันว่ายกเลิกจากเซิร์ฟเวอร์เราได้; การเตะไม่ควรฆ่า renderer ทันทีจนไฟล์เสีย

## 4. รูปแบบไฟล์แพตช์ที่ส่งให้เจ้าของโปรแกรม

เป้าหมาย UX ที่ยืนยันล่าสุด: เจ้าของได้รับ **แพตช์โปรแกรมหนึ่ง ZIP และ Extension อีกหนึ่ง ZIP เมื่อมีรุ่นใหม่** ไม่ต้องแก้ JSON, คำนวณ hash หรืออัปโหลดตัวติดตั้งเต็มในหน้าออกอัปเดต

รูปแบบส่งมอบและช่องอัปโหลด:

1. **แพตช์โปรแกรม ZIP** — `SmartFlow-Patch-<version>.zip` เป็นไฟล์ห่อสำหรับแอดมิน มี `release.json` ที่ลงลายเซ็นแล้ว, `payload.zip` ซึ่งบรรจุเฉพาะไฟล์โปรแกรมที่อนุญาต และ `README-อัปเดต.txt` ไม่รวมข้อมูลผู้ใช้
2. **Extension ZIP** — `SmartFlow-Extension-<version>.zip` แยกจากแพตช์ อัปโหลดเมื่อเปลี่ยน Extension; ถ้าไม่เปลี่ยน แสดง “ใช้ Extension รุ่นเดิม” พร้อมรุ่นที่ signed metadata กำหนด ไม่ให้แอดมินเดาคู่รุ่นเอง

`release.json` ระบุ app_id, release_id, version, channel, platform, notes, supported_from, minimum updater, รูปแบบแพ็ก และคู่ Extension พร้อม hash/ขนาดของ payload และ Extension ที่ต้องใช้ ไม่มีช่องอัปโหลด JSON แยกในหน้าเว็บ

hash ของแพตช์ใน signed metadata ต้องอ้าง **payload ภายใน** ไม่อ้าง ZIP ห่อที่มี manifest ตัวเองจนเกิดวงจร hash เซิร์ฟเวอร์ตรวจลายเซ็นและไฟล์ใน staging แล้วนำ signed manifest/payload เข้าระบบเผยแพร่เดิมที่ใช้ไฟล์ immutable ตาม hash; กำหนด package schema/adapter ให้ client รุ่นเก่าอ่านได้หรือมีเส้นทางอัปเดตขั้นกลาง ห้ามเปลี่ยนรูปแบบไฟล์ของ endpoint เดิมเงียบ ๆ

เมื่อไม่อัปโหลด Extension ใหม่ ต้องพบ artifact เดิมที่เชื่อถือได้ตามรุ่น/identity/hash/ขนาดที่ manifest ลงลายเซ็นไว้และคู่รุ่นที่ผ่านทดสอบ หากไม่มีหรือไม่ตรงให้หยุดก่อนเผยแพร่ ไม่หยิบไฟล์ชื่อคล้ายกันหรือ latest มาแทนเอง กรณีใช้ Chrome Web Store ให้ตรวจ store identity/รุ่นตามช่องทางที่เลือก ไม่ตีความ ZIP บนเซิร์ฟเวอร์ว่า Chrome อัปเดตแล้ว

**ตัวติดตั้งเต็ม EXE** ยังคงต้องสร้างและทดสอบสำหรับลูกค้าใหม่ แต่จัดการในส่วน “ตัวติดตั้งสำหรับลูกค้าใหม่” แยกจากหน้าแพตช์ ไม่บังคับสร้าง/อัปโหลด EXE ใหม่ทุกครั้งที่ออกแพตช์

เริ่มจาก cumulative code patch ที่ตรวจง่ายและรองรับรุ่นต้นทางชัดเจนก่อน อย่ารับประกันว่าแพตช์จะเล็ก เพราะระบบเดิมแพ็ก binary/runtime ด้วย; incremental patch ทำภายหลังได้เมื่อมี baseline และ base-file hashes ที่แน่นอน

ใช้เครื่องมือ signing เดิมต่อยอด; private signing key อยู่เฉพาะฝั่งผู้เผยแพร่ ไม่ใส่ใน bundle/โปรแกรม/Extension/เซิร์ฟเวอร์สาธารณะ ลูกค้าและเว็บใช้ public key ตรวจสอบเท่านั้น เก็บขั้นตอนสำรอง/หมุนกุญแจโดยไม่อ่านกุญแจมาใส่รายงาน

manifest ต้องรองรับ dependency/prerequisite และ minimum updater version ถ้ารุ่นเดิมเก่าเกินไปให้มีเส้นทางอัปเดตขั้นกลางหรือตัวติดตั้งเต็มที่รักษาข้อมูล ไม่ทดลองทับแบบเดา

ต้องมีรายการไฟล์และข้อกำหนดลบไฟล์โค้ดเก่าที่ชัดเจน หากจำเป็นต้องลบ: จำกัดเฉพาะ code-owned allowlist และสำรองคืนได้ ห้ามใช้การล้างโฟลเดอร์ราก/โฟลเดอร์ข้อมูลเป็นวิธีอัปเดต

## 5. หลังบ้านอัปโหลดและเผยแพร่

ใช้หน้า **ระบบ → อัปเดต SmartFlow AI** และ API เดิมเป็นฐาน สมาชิกมีสองหน้าหลัก: **สมาชิกและ API Token** (เจ้าของสิทธิ์ วันหมดอายุ จำนวนเครื่อง ต่ออายุ/บล็อก) และ **ผู้ใช้ออนไลน์ SmartFlow AI** (แยก desktop/Extension พร้อมวันหมดอายุ last_seen และปุ่มเตะ/บล็อก) ประวัติการใช้งาน/อัปเดตเป็นส่วนตรวจสอบเพิ่มเติม ใช้ admin authentication เดิม ไม่ใช้ Token สมาชิกแทนสิทธิ์แอดมิน

1. แสดงสองช่อง **แพตช์โปรแกรม ZIP** และ **Extension ZIP** เท่านั้น เมื่อเลือกแพตช์ระบบอ่าน metadata แล้วแสดงรุ่นปัจจุบัน → รุ่นใหม่, stable/beta, ขนาด, สิ่งที่เปลี่ยน และ Extension ใหม่หรือรุ่นเดิมที่ต้องใช้ ไม่ให้เลือก release.json/EXE เพิ่ม
2. อัปโหลดเป็นร่างแบบ resumable พร้อมเปอร์เซ็นต์; ไม่เผยแพร่เพียงเพราะอัปโหลดเริ่มแล้ว
3. ตรวจ signature, product/channel/platform, supported_from, ทุกไฟล์/ขนาด/hash และความตรงกันของข้อมูลที่ฝังใน EXE/Extension manifest
4. การอ่าน ZIP ห่อ, payload และ Extension ต้องปฏิเสธ path traversal, absolute path, symlink/reparse escape, ชื่อซ้ำแบบไม่แยกตัวพิมพ์, ZIP bomb และไฟล์นอก allowlist; ใช้ staging แยกและจำกัดขนาดทั้งแบบบีบอัด/แตกไฟล์รวมทุกชั้นก่อนเผยแพร่ ไม่ติดตั้งหรือ execute ไฟล์ระหว่างตรวจ
5. แสดง **ตรวจครบและเผยแพร่** เมื่อ signed metadata, payload และ Extension ที่อัปโหลดหรืออ้างรุ่นเดิมตรวจครบ; แพตช์รุ่นใหม่ไม่บังคับ asset installer และไม่ประกาศไฟล์ EXE ที่ไม่มีจริง ต้องปรับ signer/validator/router/client ที่คาดหวัง EXE ให้ตรงกัน ไม่ใช่แค่ซ่อนช่องในหน้าเว็บ
6. เมื่อแอดมินกดเผยแพร่ ให้สลับ published pointer แบบ atomic โดยใช้ไฟล์ immutable ตาม hash เดิม เก็บเวอร์ชันและผู้เผยแพร่ใน audit ห้ามแก้ไฟล์ภายใต้ release_id เดิมเงียบ ๆ
7. มีประวัติ รุ่นที่กำลังเผยแพร่ และถอนการเสนอรุ่นที่มีปัญหา; การเอารุ่นเก่ากลับเป็น latest ไม่ได้ทำให้เครื่องที่อัปเดตแล้ว downgrade เอง ต้องใช้ local rollback หรือเผยแพร่รุ่นแก้ที่เลขสูงกว่า
8. ทดสอบกรณีอัปโหลดหลุด/อัปโหลดซ้ำ/กดเผยแพร่ซ้ำ/แอดมินสองคนก่อนเปิดให้ลูกค้าใช้
9. ถ้ายังไม่ล็อกอินหรือ session แอดมินหมดอายุ ให้มีปุ่มเข้าสู่ระบบ/กลับหน้าภาพรวมและข้อความชัดเจน แยกจาก “ไฟล์แพตช์ไม่ถูกต้อง”; ไม่แก้ปัญหาด้วยการข้ามสิทธิ์แอดมิน

MVP ใช้ปุ่มอัปโหลดและเผยแพร่แยกกันเพื่อยืนยันผลก่อนถึงลูกค้า; ผู้ใช้ไม่ต้องวางไฟล์ server ด้วยตนเองหรือแก้ `latest` JSON หลังบ้านจัดการให้

## 6. การตรวจรุ่นและป๊อปอัปของโปรแกรมลูกค้า

- ตรวจหลังเปิด/ล็อกอิน และตรวจซ้ำเป็นระยะขณะโปรแกรมเปิดอยู่ ค่าเสนอทุก 15 นาที + jitter; เมื่อเน็ตกลับมาให้ตรวจอีกครั้งโดยมี cooldown
- ใช้ ETag/conditional requests และ backoff เมื่อ server ไม่พร้อม ไม่ผูกการอ่าน manifest ทุกครั้งกับ heartbeat สมาชิก 30 วินาที
- นี่เป็น polling: เผยแพร่แล้วเห็นในการตรวจรอบถัดไป ไม่รับประกันว่าทุกเครื่องเห็นทันที; เมื่อกด “ตรวจอัปเดต” ให้ตรวจทันที
- เลือก stable เป็นช่องทางลูกค้าปกติ; beta ต้องได้รับสิทธิ์และเลือกเข้าร่วมชัดเจน ไม่สลับช่องทางให้ลูกค้าอัตโนมัติ
- การแจ้งป๊อปอัปใช้ release_id deduplicate และบันทึก “ไว้ภายหลัง” แบบมีอายุข้ามการเปิดโปรแกรม ไม่แสดงซ้ำทุก heartbeat
- ป๊อปอัปแสดง “มี SmartFlow AI รุ่นใหม่”, รุ่นเดิม/ใหม่, สิ่งที่แก้, ขนาดดาวน์โหลด, เวลา/เงื่อนไขต้องปิดเปิดใหม่ และสถานะคู่ Extension
- ปุ่มหลัก **อัปเดตและเปิดใหม่**, ปุ่มรอง **ไว้ภายหลัง**, ลิงก์ **ดูรายละเอียด**; เมื่อกดหลักครั้งเดียวให้ดาวน์โหลด → ตรวจ → ติดตั้งต่อเอง ไม่บังคับกลับมากดติดตั้งรอบสองใน desktop flow ปกติ
- หากกำลังสร้างคลิป/เสียง/ปก/render/โพสต์ Facebook หรือ Shopee หรือมีคำขอ provider ค้าง: ใช้แจ้งเตือนที่ไม่บังงาน และเสนอตัวเลือก **ดาวน์โหลดและอัปเดตหลังงานปัจจุบันเสร็จ** ต้องได้รับการเลือกก่อน
- เมื่อเลือกหลังงานเสร็จ ให้ตั้ง queue handoff barrier กันเริ่มรายการถัดไป; รอทั้งผลที่บันทึกจริงและ ACK ที่เกี่ยวข้อง ไม่ดูเปอร์เซ็นต์ 100% อย่างเดียว
- ถ้างานค้าง/ผลยังไม่ชัดเจน ให้แสดง “รอตรวจงานเดิมก่อนอัปเดต” ไม่ force stop หรือยกเลิกงานเพื่ออัปเดต; ผู้ใช้เลือกจัดการงานเองได้
- แยกสถานะ checking / available / downloading / verifying / waiting_for_idle / installing / restarting / waiting_for_extension / complete / rolled_back / failed โดยไม่เอาไปปน error ของงานคลิป
- การบังคับรุ่นขั้นต่ำเสนอให้ใช้เฉพาะ release ที่ประกาศชัดและผ่านอนุมัติ: บล็อกเริ่มงานใหม่เมื่อจำเป็น แต่ยังเปิดข้อมูล/ส่งออก/อัปเดตได้ ไม่บังคับฆ่างานค้าง

## 7. ติดตั้งอัตโนมัติอย่างปลอดภัย

1. ดาวน์โหลดไป `.partial` นอกโฟลเดอร์โปรแกรม แยกตาม release/hash ตรวจไฟล์ครบก่อนย้ายเป็นพร้อมติดตั้ง; เพิ่ม resume เฉพาะ byte range ที่ตรวจสอบได้ ถ้า server ไม่รองรับให้เริ่มดาวน์โหลดใหม่โดยไม่แตะไฟล์ติดตั้งเดิม
2. ตรวจลายเซ็น/hash/version/platform/supported_from/minimum updater และพื้นที่ staging+backup ให้ครบก่อนปิดโปรแกรม
3. ขอ update lease/lock เดียวทั้ง desktop/engine กันสองหน้าต่างหรือสอง updater ทำพร้อมกัน ตรวจ safe-idle จาก state ล่าสุดภายใต้ lock ไม่ใช้ค่าที่ UI อ่านไว้เมื่อหลายวินาทีก่อน
4. ตรวจทุกงาน: Product/Shorts/Drama/Presenter, rendering/audio/cover, creation queue, Facebook upload/schedule, Shopee mobile posting/unknown public Post และ pending/unknown Extension commands; อย่าเท่ากับ service worker idle ของ Chrome
5. บันทึกคิว/receipt/checkpoint แล้วพักเฉพาะการ dispatch งานใหม่ ปิดเฉพาะ process โปรแกรมที่ updater เป็นเจ้าของ ห้ามปิด Chrome ทั้งหมดหรือ service เซิร์ฟเวอร์
6. external updater ที่ลงลายเซ็น/ตรวจความแท้ได้ทำ staging + durable journal + backup แล้วเปลี่ยนเฉพาะ code files ที่อนุญาต; ถ้า engine ไม่ยอมปิดให้หยุดติดตั้งโดยไฟล์เดิมยังอยู่
7. รองรับไฟล์ล็อก, disk full, antivirus, access denied, เครื่องดับระหว่างเปลี่ยนไฟล์, และ updater crash: boot ครั้งถัดไปต้องอ่าน journal แล้วกู้/rollback ไม่ใช้ไดเรกทอรีที่มีไฟล์ครึ่งรุ่น
8. ถ้าเตรียมอัปเดตไม่สำเร็จ ต้องปลด update lock/pending state อย่างควบคุมได้ ไม่ปล่อย UI ติดข้อความ “กำลังอัปเดต” ถาวร และไม่ resume คิวโดยไม่ได้ยินยอม
9. เปิดผ่าน `SmartFlow AI.exe` แล้วตรวจ version/engine/UI readiness/migration/license schema และรุ่น Extension จริง; ถ้าใหม่เปิดไม่สำเร็จ ให้ย้อน code พร้อม schema ที่เกี่ยวข้องอย่างสอดคล้องแล้วแจ้งผู้ใช้
10. หลังสำเร็จคงสถานะคิวพักไว้ ให้ผู้ใช้ทำต่อจาก checkpoint; ไม่สั่งงานหรือโพสต์ Facebook ใหม่เองจากการเปิดหลังอัปเดต

สถานะติดตั้งโปรแกรมเสร็จ กับ “พร้อมทำ automation” ต้องแยกกัน หากโปรแกรมเปิดแล้วแต่ Extension ยังไม่เข้าคู่ให้บอกชัด ไม่ rollback วนเพราะ Chrome ยังไม่ส่ง heartbeat

การอัปเดต license ที่มี schema ใหม่ต้องมี migration idempotent และแผน rollback; rollback code ไม่สามารถยกเลิกสถานะบล็อกฝั่ง server หรือฟื้น session ที่ถูก revoke ได้

## 8. การอัปเดต Extension และข้อจำกัด Chrome

Desktop patch จากเซิร์ฟเวอร์เรา กับการอัปเดต Chrome Extension เป็นคนละช่องทาง อย่าสัญญาว่า desktop updater จะติดตั้ง Extension ใหม่เงียบ ๆ บน Windows ทุกเครื่อง

แนวทางเสนอ:

- **ลูกค้าทั่วไป:** ใช้ Chrome Web Store สำหรับแจกและอัปเดต Extension; desktop patch ยังอยู่บน catfufu ตามแผนผู้ใช้ แต่ release ต้องรอ Extension รุ่นที่เข้าคู่เผยแพร่จริง หรือมี compatibility window ที่ทดสอบแล้ว
- **แบบ unpacked ที่ใช้อยู่สำหรับพัฒนา/ทดสอบ:** helper ช่วยเตรียมไฟล์ในตำแหน่งถาวรและแนะนำ Reload เมื่อไม่มีงาน ไม่ถอนติดตั้ง ไม่เปลี่ยน ID/profile ไม่ล้าง receipts; แสดงว่ามีขั้นตอน Chrome ที่ผู้ใช้ต้องทำ ไม่เรียกว่าทั้งระบบอัตโนมัติครบแล้ว
- **เครื่ององค์กรที่จัดการจริง:** ประเมิน enterprise policy/self-host แยกได้เมื่อได้รับอนุญาต ไม่ใส่นโยบายองค์กรหลอกหรือปิดความปลอดภัยให้เครื่องลูกค้าทั่วไป

Chrome อาจอัปเดตช้าตาม lifecycle ของตน และ content script ที่ยังทำงานไม่ได้แปลว่า Chrome มอง Extension ว่ายุ่งเสมอ จึงต้องมี durable checkpoints, compatibility handshake และตรวจ build ของ helper ในแท็บก่อน dispatch ใหม่; ห้าม reload แท็บที่มี unknown Send เพื่อบังคับรุ่น

กำหนดคู่ release ที่ทดสอบจริง พร้อม protocol/schema compatibility; ในช่วง MVP ใช้ exact pair จนพิสูจน์ช่วงที่รองรับได้ ไม่ยอมรับทุกเวอร์ชันด้วยการเปรียบเทียบเลขอย่างเดียว

รอ heartbeat จาก background และ helper รุ่นที่ถูกต้องก่อนขึ้น “พร้อมใช้งาน”; การดาวน์โหลด ZIP เสร็จไม่ใช่หลักฐานว่าติดตั้ง/Reload แล้ว

เอกสารทางการที่ตรวจ 2026-09-19: [การแจก Extension](https://developer.chrome.com/docs/extensions/how-to/distribute) และ [วงจรอัปเดต Extension](https://developer.chrome.com/docs/extensions/develop/concepts/extensions-update-lifecycle) ต้องตรวจนโยบายล่าสุดซ้ำก่อนเลือกช่องทางส่งมอบจริง

## 9. ผูกสิทธิ์สมาชิกกับการอัปเดตโดยไม่ล็อกตาย

- entitlement ระบุ stable/beta, feature และ update policy; server เป็นผู้ตัดสิน ไม่รับ claim จาก client ว่ามีสิทธิ์เอง
- activation Token ไม่ถูกส่งใน URL ของแพตช์ ใช้ scoped session หากจำกัดการดาวน์โหลด; signed manifest/hash ยังคงต้องตรวจแม้ยืนยันสมาชิกแล้ว
- เสนอให้หน้าล็อกอิน/บัญชีหมดอายุ/ถูกเตะยังเปิด “อัปเดตโปรแกรม” ได้ และให้อ่านข้อมูลรุ่น public ได้เหมือนเส้นทางเดิม เพื่อไม่เกิดวงจรต้องล็อกอินด้วยรุ่นใหม่ก่อนจึงดาวน์โหลดรุ่นใหม่ได้
- ถ้าต้องจำกัดไฟล์ให้สมาชิกเท่านั้น ให้ออกสิทธิ์เฉพาะ update recovery ที่ไม่อนุญาตสร้างงาน; นโยบายนี้ต้องล็อกก่อน implementation ไม่ถือว่าการอัปเดตต่ออายุสมาชิกให้โดยอัตโนมัติ
- แสดง admin ว่ารุ่นใดถูกเสนอ/ดาวน์โหลด/ติดตั้ง/เปิดสำเร็จ/rollback ด้วย event_id กันบันทึกซ้ำ และเก็บ last_seen พร้อมเวลา; เครื่องที่ไม่รายงานต้องเป็น unknown ไม่เดาว่าอัปเดตสำเร็จ
- telemetry ส่งเฉพาะรหัสอุปกรณ์แบบจำกัด, version, phase และ error code ที่ลบข้อมูลอ่อนไหว ไม่ส่ง prompt, media, ชื่อไฟล์ส่วนตัว หรือ Token

## 10. การรักษาข้อมูลและป้องกันการส่องโค้ด

- ห้ามแพ็กหรือเขียนทับ config/credentials, Windows Credential Store, workspace/jobs/queues/receipts, รูป/เสียง/วิดีโอ/ปก, เพลง/intro/green screen/คลังนายแบบที่ผู้ใช้อัปโหลด, Chrome profiles/storage/cookies และข้อมูล Facebook Planner
- แยก app-owned resources จาก user data; รุ่นเก่าที่วางข้อมูลปนอยู่ต้องมี migration สำรองก่อนและตรวจการย้ายจริง ไม่ลบทิ้งเพื่อให้ update ผ่าน
- ไม่เพิ่ม prerequisite ที่พึ่งเฉพาะเครื่องพัฒนา; ปฏิบัติตาม [ข้อกำหนดเครื่องใหม่](clean-machine-installer.md) รวม runtime/libraries/เครื่องมือสื่อที่จำเป็นและมีสิทธิ์แจก หรือมีขั้นตอนติดตั้งทางการที่พิสูจน์แล้ว
- compiled desktop, signed releases และสิทธิ์ที่ตรวจ server ช่วยลดการแก้/แจกต่อ แต่ไม่ป้องกัน reverse engineering ได้ 100%; Extension ตรวจดูโค้ดได้ และห้ามโหลด remote executable JS เพื่อเลี่ยงข้อกำหนด MV3
- ไม่แจก publisher key/server secrets; ไม่รวม Chrome profile/cookies/Token/สื่อของผู้พัฒนา; HTTPS, rate limit, audit และสิทธิ์ admin ที่แยกการออก Token/เผยแพร่รุ่น
- สำรองตาม release/journal และจำกัดการเก็บเมื่อมีจุดคืนที่ยืนยันแล้ว ไม่ลบ backup รุ่นเดิมก่อนตรวจ health/compatibility เสร็จ

## 11. ลำดับลงมือทำในอนาคต

รายละเอียดงานย่อยและเกณฑ์ผ่านแต่ละช่วง: [แผนลงมือทำและส่งมอบ EXE](smartflow-customer-release-roadmap.md)

1. **P0 โครงสร้าง/บิ้วทดสอบภายใน:** ล็อก app/data layout, dependency inventory, identity/version/schema, supported_from, Token scopes, ช่องทาง Extension และ key trust; ทดสอบ frozen build ตั้งแต่ต้นโดยยังไม่แจก
2. **P1 สมาชิกฝั่ง server:** schema/migration แบบแยกผลิตภัณฑ์, activate/renew/revoke/heartbeat, admin members/sessions/audit และ tests ในฐานข้อมูลแยก
3. **P2 สมาชิก client:** desktop gate + secure credential + Extension pairing + lease/recovery โดยไม่เปลี่ยน provider automation ที่ใช้งานได้; ทำ frozen build smoke ด้วย
4. **P3 อัปเดตครบวงจร:** ต่อจาก signer/router/page เดิม ปรับเป็นแพตช์ ZIP + Extension ZIP, embedded signed metadata, ใช้ Extension เดิมแบบ exact verified reference, popup กดครั้งเดียว, after-current-job barrier, download/lock/journal/restart/rollback และ compatibility ของ Extension
5. **P4 ตัวติดตั้งรวมระบบรุ่น A:** รวม Login/updater/dependencies ใน EXE Setup ทดสอบเครื่องสะอาด/การย้ายข้อมูล โดยไม่แจกชุดที่ไม่มี updater ให้ลูกค้าก่อน
6. **P5 พิสูจน์ A→B:** เจ้าของอัปโหลดและเผยแพร่แพตช์ B ใน test/beta channel; A ต้องเห็น popup กดแล้วอัปเดตได้จริง ข้อมูลเดิมครบ และ failure rollback ผ่านบนเครื่องอื่น
7. **P6 ทยอยส่งมอบ:** beta สมาชิกกลุ่มเล็ก → stable หลังผ่านเกณฑ์; บันทึกผลจริงและจุด rollback ของโค้ด/ข้อมูล/เซิร์ฟเวอร์แยกกัน

ลำดับสรุปคือ **โครงสร้าง → Login/Token → อัปเดต → ตัวติดตั้งจริง → ทดสอบแพตช์ → เผยแพร่** โดยบิ้วทดสอบภายในระหว่างพัฒนา ไม่รอพิสูจน์การแพ็ก EXE จนถึงขั้นสุดท้าย

การเริ่มพัฒนา บิลด์ installer/patch จริง ลง Extension หรือ deploy ต้องมีคำสั่งถัดไป เอกสารนี้ไม่อนุญาตให้เปลี่ยนงานหรือเผยแพร่เองโดยอัตโนมัติ

## 12. เกณฑ์ยืนยันว่าพร้อมใช้งาน

### สมาชิก

- Token ผิด/หมดอายุ/ถูก revoke, activate พร้อมกันเกิน seats, ต่างสมาชิกจับคู่กัน, เปลี่ยนเครื่อง/profile, renew แข่งกับ block, replay/session เก่า
- เตะ/บล็อกขณะ idle/กำลังสร้าง/รับผล/ประกอบ/โพสต์: ไม่มีงานใหม่หลังสิทธิ์หมด ไม่เสียไฟล์ ไม่โพสต์ซ้ำ และบอก latency/offline status ตามจริง
- server outage/เน็ตหลุด/เวลาเครื่องผิด/เปิดใหม่: lease และ checkpoint ทำงาน ไม่เปิดสิทธิ์ไม่จำกัด

### อัปเดต

- หน้าออกแพตช์มีสองช่องเท่านั้น ไม่มีช่อง JSON/EXE; patch-only + exact Extension เดิม และ patch + Extension ใหม่ต้องเผยแพร่ได้เมื่อครบ ส่วน first release/รุ่นไม่ตรง/hash ไม่ตรง/asset เดิมหายต้องปฏิเสธก่อน publish
- ตรวจ signed metadata ภายในและ payload แยกจาก ZIP ห่อ ไม่มี circular hash; patch หาย metadata, metadata ถูกแก้, duplicate entry และ nested ZIP เกินขนาดต้องถูกปฏิเสธ รุ่น client/updater เดิมที่รองรับต้องอ่านผลจาก server adapter ได้จริง
- อัปโหลดร่างไม่ครบต้องไม่มีป๊อปอัปลูกค้า; publish ครบแล้วให้เครื่องที่เปิดค้างตรวจพบได้โดยไม่ต้องเปิดโปรแกรมใหม่
- ก่อนกดยินยอมไม่ติดตั้ง; กดครั้งเดียวแล้วดำเนินการต่อครบเมื่อ idle; dismiss/snooze ไม่เด้งซ้ำตลอด
- รุ่นเท่าเดิม/ต่ำกว่า, ผิด product/platform/channel, signature/hash ไม่ตรง, ZIP path traversal/duplicates/bomb, insufficient disk, locked files ต้องปฏิเสธก่อนทำลายรุ่นเดิม
- โหลดหลุด, กดซ้ำ, เปิดสองหน้าต่าง, เครื่องดับ/ถูกปิดทุกช่วงของ journal, เปิดรุ่นใหม่ไม่ขึ้น: กู้คืนได้ มีข้อความชัดเจนและไม่ค้าง update lock
- อัปเดตจากทุก `supported_from` ที่ประกาศจริง และเครื่องใหม่ไม่มี Python/dev libraries; ตัวเต็ม fallback ต้องรักษาข้อมูล
- คลิปสินค้า/Shorts/Drama/ปก/เสียง/render/Facebook Planner/Shopee posting/คิว/unknown Send ค้างอยู่: update ต้องรอหรือ defer ไม่สั่งซ้ำ/ปิดแท็บเดา
- desktop/Extension คนละรุ่น, store ยังไม่ส่งรุ่น, helper เก่าในแท็บ: บอก `waiting_for_extension`/compatibility ให้ถูก ไม่แสดงพร้อมและไม่ reload งานค้าง
- สำรองเปรียบเทียบข้อมูลสำคัญก่อน/หลัง: งาน คิว ตัวเลือกสื่อ ผลงาน ประวัติโพสต์ Token และ receipts ต้องอยู่ครบ โดยไม่พิมพ์ secrets ในหลักฐาน
- withdraw/rollback server กับ local rollback แยกกัน; หลัง rollback license block ที่ server ยังมีผล และไม่ลด version หนีข้อกำหนดโดยเงียบ

### หลักฐานการทบทวนเดิม 2026-09-19

- อ่าน source ของ updater/UI/packager และ backend/admin update routes จริง รวมทั้งแผนสมาชิกเดิม
- compact status พบ Story กำลังทำงาน จึงไม่เปิด/ปิด/restart/reload โปรแกรมหรือ Extension และไม่ทำ installed update test
- ทดสอบ `tests.test_app_updates` ด้วย project `.build-env/Scripts/python.exe`: **5 tests ผ่าน** (version/signature/path/patch+rollback/data preservation/duplicate archive ตาม test cases)
- การลองด้วย Python ทั่วไปครั้งแรก import ไม่ได้เพราะ environment นั้นไม่มี `cryptography`; เปลี่ยนใช้ build environment ที่มีอยู่แล้ว ไม่ติดตั้ง dependency ใหม่ และไม่ใช้ผลนั้นสรุปว่าโปรแกรมลูกค้าพัง
- ไม่ได้ทดสอบ publish จริง/ลูกค้าสองเครื่อง/Token integration/one-click UX ใหม่ จึงยังเรียกว่า end-to-end พร้อมใช้ไม่ได้ ไม่มีการสร้างคลิปหรือใช้เครดิตจากงานนี้

### การรวมแผน 2026-09-20

- ผู้ใช้ยืนยันให้รวม UX สองไฟล์จากภาพหลังบ้านเข้าแผนทั้งหมด; แก้แผนหลัก, roadmap, ข้อกำหนด installer และดัชนีเอกสารให้ตรงกัน ไม่เรียกการแก้เอกสารว่าอัปเกรด runtime แล้ว
- ภาพที่ผู้ใช้ส่งแสดงสี่ช่อง release.json/patch/Extension/EXE พร้อมข้อความให้เข้าสู่ระบบแอดมิน การลดเหลือสองช่องต้องเปลี่ยนแพ็กเกจและ validation ตามข้อ 4–5; ข้อความล็อกอินเป็นคนละปัญหา ไม่ใช่หลักฐานว่าไฟล์เสีย
- ตรวจสถานะแบบอ่านอย่างเดียวพบ engine41656/Extension required0.15.383 และ Story active; ไม่ restart/reload/แก้ runtime, ไม่แตะเซิร์ฟเวอร์หรือฐานข้อมูล, ไม่สร้างแพตช์/Token จริง และไม่รันทดสอบโพสต์/สร้างคลิปเพิ่ม ผล tests เดิมข้างบนไม่ใช่ผลทดสอบฟังก์ชันสองไฟล์ใหม่นี้

## 13. แผนที่ไฟล์สำหรับงานถัดไป

Desktop repository: `C:/Users/keera/Desktop/Shopee_Android_AutoPost`

- `core/app_updates.py`: trusted manifest/version/hash/URL; เพิ่ม typed metadata/channel/compatibility ตามสัญญา
- `desktop/update_api.py`, `web_ui/updates.js`: update coordinator/UX/progress/native actions
- `tools/customer_updater.py`: transaction/journal/rollback/boot verification
- `tools/sign_customer_release.py`, `tools/build_customer.py`: สร้างแพตช์ห่อ metadata+payload และ Extension ZIP แยก, installer อยู่ช่องทางลูกค้าใหม่, package schema/signing/clean-machine dependencies
- `ui/main_window.py` เฉพาะ `prepare_app_update` และ idle/queue hooks, `core/local_bridge.py`: update barrier/pairing; ตรวจ Facebook/Shopee workers และ cover ด้วย
- `browser_extension/background.js` และ storage/bridge modules: scoped activation/pairing/version/checkpoint; ไม่แก้ provider Send โดยไม่มีเหตุ
- `tests/test_app_updates.py` และ tests ใหม่: offline recovery, UI, member/update integration, installed VM matrix

Server repository: `C:/Users/keera/AppData/Local/SmartSubAI/VoiceCloneOnline`

- `backend/routers/smartflow_updates.py`: ต่อยอดระบบรุ่นเดิม ไม่สร้าง latest endpoint ซ้ำ
- `frontend/app/admin3s/smartflow-updates/page.tsx`: หน้าอัปโหลด/เผยแพร่เดิม
- `backend/routers/auth.py`: ใช้ admin auth/online patterns; `smartsub_online.py` เป็น reference เท่านั้น ไม่ยืม Token หรือฐานสิทธิ์คนละผลิตภัณฑ์
- เพิ่ม module/schema/routes/pages สมาชิก SmartFlow แบบแยกตามข้อ 3 และ migration/audit/test ของตัวเอง
- เมื่อ deploy ภายหลัง: อ่าน host guardian, สำรอง schema/data, build frontend ใน staging, restart เฉพาะบริการที่แก้ และตรวจหน้า/API/assets/rollback โดยไม่กระทบระบบอื่น
