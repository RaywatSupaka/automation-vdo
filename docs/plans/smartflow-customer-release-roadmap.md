# SmartFlow AI — แผนลงมือทำ Login, อัปเดต และตัวติดตั้ง EXE

วันที่: 2026-09-19 • รวมข้อยืนยันล่าสุด: 2026-09-20 • สถานะ: **P1 ขึ้นเซิร์ฟเวอร์แล้ว; P2 หน้า Login/สิทธิ์ desktop และ Extension พัฒนาแล้ว อยู่ขั้นตรวจ source/fixture ยังไม่ผ่าน installed/frozen E2E; P3–P6 ยังไม่เสร็จ** ดู [รายงาน client384](../reports/membership-384/README.md); P0 inventory/contract ตรวจแล้ว แต่ frozen clean-machine smoke ยังไม่ผ่านเกณฑ์ส่งลูกค้า รายงาน deploy อยู่ในโปรเจกต์เซิร์ฟเวอร์ `docs/reports/smartflow-admin-live-20260920.md`

ใช้ร่วมกับ [แผนสมาชิกและอัปเดตฉบับหลัก](smart4-online-membership.md) และ [ข้อกำหนดติดตั้งเครื่องใหม่](clean-machine-installer.md) เอกสารนี้จัดลำดับงานและเกณฑ์ส่งต่อ ไม่แทนที่รายละเอียดด้านความปลอดภัยในแผนหลัก

## ข้อสรุป

**วางโครงสร้างติดตั้ง → Login/Token → ระบบอัปเดต → บิ้วตัวติดตั้งรวมระบบ → ทดสอบเครื่องอื่นและแพตช์ A→B → แจกจริง**

บิ้ว EXE ภายในได้ตั้งแต่ช่วงต้นและทดสอบซ้ำทุกช่วง แต่ต้องไม่เรียกตัวทดลองนั้นว่าเป็นตัวติดตั้งพร้อมแจก ลูกค้ารุ่นแรกต้องได้รับทั้ง license gate และ updater ที่ใช้งานจริงแล้ว

ข้อยืนยัน 2026-09-20 รวมอยู่ใน P0/P1/P2/P3/P4/P5/P6 ด้านล่าง: ใช้เซิร์ฟเวอร์ที่เจ้าของเปิดอยู่ตรวจสิทธิ์ SmartFlow, สองหน้าหลักสำหรับ Token/ผู้ใช้ออนไลน์พร้อมหมดอายุ/บล็อก/เตะ และหน้าออกอัปเดต **สองช่องแพตช์ ZIP + Extension ZIP** เท่านั้น Metadata อยู่ในแพตช์ ส่วน EXE แยกสำหรับลูกค้าใหม่ แทนข้อเสนอเก่าให้เลือก bundle เดียวหรือแยก JSON/EXE ในหน้าออกแพตช์

## หลักฐานที่ใช้จัดลำดับ

- `tools/build_customer.py` มี PyInstaller สำหรับ app/updater, bundle UI/ไลบรารีบางส่วน/FFmpeg/FFprobe และ Extension อยู่แล้ว; `launcher/customer.iss` เป็นฐานตัวติดตั้ง
- `core/customer_runtime.py` แยกข้อมูลผู้ใช้ใน `%LOCALAPPDATA%/SmartFlowAI/data` สำหรับ frozen build อยู่แล้ว ต้องต่อยอดและตรวจครบ ไม่ย้ายข้อมูลใหม่โดยไม่มี migration
- มี backend/admin update routes และ signed patch pipeline อยู่แล้ว แต่ยังต้องทำ periodic notification/one-click UX และทดสอบแบบติดตั้งจริง
- metadata ปัจจุบันแยก runtime Extension `0.15.382` จากชุดติดตั้ง `0.3.0-beta.8` ที่จับคู่ `0.15.276`; ชุดเดิมระบุยังไม่ publish และการทดสอบเครื่องที่สองยังค้าง เป็น snapshot ไม่ใช่เลขรุ่นที่จะใช้ส่งมอบครั้งหน้า
- ตอนสำรวจครั้งแรก membership/Token ยังอยู่ในแผน; ปัจจุบัน P1 server ขึ้นแล้ว และ P2 client384 พัฒนา/ทดสอบแยกแล้ว แต่ยังต้องผ่าน installed/frozen Login และ admin-kick ก่อนส่งมอบลูกค้า
- ขณะสำรวจพบ Story กำลังทำงาน จึงไม่ได้ restart/reload/build/deploy หรือทดสอบ installer กับเครื่องที่กำลังใช้งาน

## ลำดับงานและเงื่อนไขผ่าน

| ช่วง | งาน | ผลส่งมอบ/เงื่อนไขผ่านก่อนขยับต่อ |
|---|---|---|
| P0 | โครงสร้างติดตั้ง ข้อมูล และรุ่น | มี dependency inventory, schema/compatibility contract, isolated build smoke และทางเลือกการแจก Extension |
| P1 | Token และหลังบ้าน | ออก/หมดอายุ/บล็อก/เตะ/จำกัดเครื่องได้จริงในระบบทดสอบ มี audit และ migration rollback |
| P2 | Login โปรแกรม + สิทธิ์ Extension | ยังไม่ activate เริ่มงานไม่ได้; activate แล้วใช้ได้; restart/outage/revoke ไม่ทำงานหรือส่งคำสั่งซ้ำ |
| P3 | อัปเดตครบวงจรฝั่ง server/client | แพตช์ ZIP + Extension ใหม่/รุ่นเดิมที่ตรวจแล้ว → draft → publish → popup → ยินยอม → safe install → restart/rollback ผ่านในระบบทดสอบ |
| P4 | ตัวติดตั้ง EXE รวมระบบ รุ่น A | ติดตั้งบน Windows สะอาดและใช้งานครบ ไม่พึ่ง Python/พาธ/บัญชีเครื่องผู้พัฒนา |
| P5 | แพตช์รุ่น B ทดสอบ A→B จริง | เครื่องที่ลง A เห็น popup อัปเดตเป็น B ได้ ข้อมูลเดิมครบ คู่ Extension ถูกต้อง และ failure rollback ผ่าน |
| P6 | ปล่อย beta แล้ว stable | ผ่านข้อบกพร่องที่บล็อกการแจก มีชุดส่งมอบ/คู่มือ/หลักฐาน และเจ้าของอนุมัติการเผยแพร่ |

### P0 — ล็อกโครงสร้างก่อนเขียนระบบเพิ่ม

1. บันทึก baseline ของ source ปัจจุบันและ known-good tests โดยไม่ reset cumulative worktree หรือยกชุดติดตั้งเก่าทับโค้ดล่าสุด
2. กำหนด app identity, installer identity, customer version, Extension ID/version, bridge protocol และรูปแบบ schema ให้แยกกัน พร้อมกติกาขยับรุ่น
3. ยืนยันตำแหน่ง app code, user data, secure credentials, downloads/staging/backups และ log; รักษา path เดิมที่ใช้ได้ ถ้าจะเปลี่ยนต้องออกแบบ migration พร้อมกู้คืน
4. ตรวจ dependency จากทุกฟังก์ชันที่ส่งมอบ: UI/WebView, Python runtime/DLL, media tools, Thai fonts/text, crypto, audio/subtitle, Facebook upload และ Android tools ถ้ายังอยู่ในขอบเขตผลิตภัณฑ์
5. กำหนดรองรับ Windows/architecture/สิทธิ์ติดตั้ง/พื้นที่และ prerequisite โดยอ้างอิงเครื่องที่ทดสอบจริง ไม่โฆษณาว่ารองรับทุกเครื่อง
6. ล็อกช่องทาง Extension ก่อนสัญญาลูกค้าว่าอัปเดตอัตโนมัติ: unpacked สำหรับทดสอบแบบมีผู้ช่วยติดตั้ง กับ store/ช่องทางทางการสำหรับการแจกจริงตามแผนหลัก
7. สร้าง internal build smoke ในโฟลเดอร์และข้อมูลทดสอบแยก ตรวจว่าเปิด frozen app และ updater ได้ ใช้ public key ที่ถูกต้อง และไม่มี secrets/jobs ของผู้พัฒนาหลุดเข้าแพ็ก
8. ล็อก package schema: ไฟล์แพตช์ที่แอดมินเลือกมี signed release.json + payload.zip + คู่มือ; signed hash อ้าง payload ไม่ hash ตัวห่อแบบวนกลับ เซิร์ฟเวอร์ adapter ตรวจแล้วเผยแพร่ manifest/payload ผ่านเส้นทางเดิมที่ client รองรับ แยก Extension ZIP และไม่บังคับ EXE ใน patch manifest

ผ่านเมื่อ: บันทึกสิ่งที่รวม/ขาด/ต้องให้ผู้ใช้ติดตั้งเองครบ และรู้ว่าจะอัปเดตอะไรได้โดยไม่เขียนทับข้อมูลผู้ใช้ ไม่จำเป็นต้องรอให้ UX ทั้งหมดสวยก่อนจบช่วงนี้

### P1 — หลังบ้านสมาชิกและ Token

- เพิ่ม schema/namespace SmartFlow แยกจากบริการอื่น ใช้ admin auth เดิมเฉพาะสิทธิ์ผู้ดูแล
- หน้า “สมาชิกและ API Token”: ออก Token แบบ desktop/Extension ภายใต้สมาชิกเดียว ดูเจ้าของสิทธิ์/วันหมดอายุ ต่ออายุ ตั้งจำนวนเครื่อง และเปิด-ปิดสิทธิ์
- หน้า “ผู้ใช้ออนไลน์ SmartFlow AI”: desktop และ Extension แยกกัน แสดง last_seen/รุ่น/สถานะ/วันหมดอายุ พร้อมปุ่มเตะ/บล็อก ไม่เปิดเผย Token เต็ม
- ปุ่มเตะเครื่อง/ทุกเครื่อง บล็อก ปลดบล็อก reset device และ rotate Token แยกกัน พร้อมยืนยันและ audit
- API ต้องกันการ activate พร้อมกันเกินจำนวนเครื่อง, replay, pairing ข้ามสมาชิก และ session เก่าหลัง revoke
- เริ่มบนฐานข้อมูลทดสอบและ migration ที่ย้อนกลับได้ การ deploy ขึ้นระบบจริงเป็นงานแยกหลังผ่าน tests และได้รับคำสั่ง

ผ่านเมื่อ: ทดสอบครบ Token ถูก/ผิด/หมดอายุ/บล็อก/เตะ/ปลดบล็อก และ online/offline ไม่สับสนกับสถานะสิทธิ์

### P2 — Login ในโปรแกรมและ Extension

- หน้าแรกเปิดใช้ด้วย Token, จำเครื่องผ่าน secure credential, แสดงข้อผิดพลาดที่ทำต่อได้; ไม่ให้การซ่อน UI เป็นการป้องกันเพียงอย่างเดียว
- ถูกเตะต้องกลับหน้ากรอก Token ไม่ใช้ credential ต่ออายุ/activate กลับอัตโนมัติ ผู้ใช้ยืนยันแล้ว: กรอก Token เดิมเข้าเครื่องเดิมได้เมื่อสิทธิ์ยังใช้ได้, 1 Token ต่อ 1 เครื่อง; ย้ายเครื่องต้อง admin reset binding แยกจากบล็อก/เพิกถอน
- Engine ตรวจสิทธิ์ที่จุดเริ่มงาน/ทำต่อ/dispatch และ Extension ตรวจ scoped session/pairing ก่อนรับคำสั่งใหม่
- นโยบาย P1: 1 Token ต่อ 1 เครื่อง, Extension เพิ่ม binding 1 profile ภายใต้ desktop สมาชิกเดียวกัน; heartbeat 30 วินาที, lease 5 นาที (P2 ต้อง enforce ใน client และเก็บผลที่รับไปแล้ว)
- เมื่อมีงานส่งออกไปแล้วและโดนเตะ/ขาดการติดต่อ ให้หยุดงานใหม่ เก็บ checkpoint/ผลที่กลับมาโดยไม่สั่งสร้างซ้ำ; ไม่อ้างว่าสั่งยกเลิก provider ภายนอกได้ทุกกรณี
- เปิดหน้าอัปเดตและทางช่วยเหลือได้แม้ session หมดอายุ เพื่อไม่เกิด deadlock “ต้อง login รุ่นใหม่ก่อนจึงโหลดรุ่นใหม่ได้”
- ทดสอบ frozen EXE ด้วย ไม่ทดสอบเฉพาะ source Python เพื่อจับปัญหา credential path/network/packaging ตั้งแต่ต้น

ผ่านเมื่อ: activation→เปิดใหม่→จับคู่ Extension→ตรวจสิทธิ์ก่อน dispatch ทำงานครบ และไม่มีอาการกระทบ ChatGPT/Gemini/Flow/Meta ที่ไม่ได้อยู่ในขอบเขตการแก้

### P3 — อัปเดตโปรแกรมผ่านเซิร์ฟเวอร์

- ต่อจาก signer/router/admin page เดิม ให้หน้าอัปเดตมีเพียงสองช่อง **แพตช์โปรแกรม ZIP** และ **Extension ZIP**; อ่าน release.json จากแพตช์เอง ไม่มีช่อง JSON/EXE และไม่ให้กรอก hash เอง
- ถ้าไม่เปลี่ยน Extension ให้แสดงรุ่นเดิมที่ signed metadata ระบุและตรวจ artifact/identity/hash/ขนาดครบ; ถ้าไม่พบหรือรุ่นใหม่ไม่ตรงให้หยุดก่อนเผยแพร่ ไม่เลือก latest แทนเอง
- ปรับ packager, signed metadata, backend validators, asset schema และ client compatibility ให้ตรงกัน ไม่ใช่ซ่อนช่องอย่างเดียว; ส่วน EXE อยู่หน้าตัวติดตั้งลูกค้าใหม่แยกต่างหาก
- คงสองขั้น “อัปโหลดและตรวจสอบ” → “เผยแพร่” พร้อมสถานะ/เหตุผลครบ ถ้ายังไม่ล็อกอินแอดมินให้มีทางเข้าสู่ระบบ ไม่ลดการตรวจสิทธิ์เพื่อให้อัปโหลดผ่าน
- Client ตรวจเปิดโปรแกรม/เป็นระยะ/เมื่อเน็ตกลับ แสดง popup ต่อ release แบบไม่รบกวนงานซ้ำ ๆ
- กด “อัปเดตและเปิดใหม่” ครั้งเดียว หรือเลือกหลังจบงานปัจจุบัน; การรอหลังจบงานต้องกัน queue เริ่มรายการถัดไป
- ดาวน์โหลดและตรวจ signature/hash/version/base compatibility ก่อนปิด app; updater มี lock/journal/staging/backup/restart health และ rollback
- งาน Product/Shorts/Drama/ปก/เสียง/render/Facebook upload/Shopee mobile posting/unknown sends ต้องถูกรวมใน busy gate ไม่ใช้แค่เปอร์เซ็นต์หรือสถานะหน้าจอ
- แยก “ติดตั้ง desktop เสร็จ” จาก “Extension พร้อม” และไม่บังคับ reload Chrome/แท็บที่กำลังมีงาน
- สถานะสมาชิก/สิทธิ์ที่ server ไม่ถูกย้อนคืนด้วยการ rollback ไฟล์โปรแกรม

ผ่านเมื่อ: UI สองช่อง, patch-only อ้าง Extension เดิม, patch+Extension ใหม่, ไม่บังคับ EXE, signed inner payload/no circular hash, missing/tampered metadata, missing/wrong Extension, network loss, duplicate clicks, busy job, update failure และ restart reconciliation ผ่านในระบบทดสอบ พร้อม staged server release ที่กู้กลับได้

### P4 — บิ้วตัวติดตั้งรวมระบบ รุ่น A

- ใช้ release manifest ล็อก source/build inputs และ Extension คู่เดียวกัน ตรวจผลก่อนใช้เลขรุ่นใหม่ ไม่หยิบ runtime candidate ทั้งหมดมาเรียก stable โดยอัตโนมัติ
- สร้าง `SmartFlow AI.exe`, updater และ `SmartFlow-AI-Setup-<version>.exe` ที่มี dependency ครบตาม P0
- ตัวติดตั้งเต็มเผยแพร่ในส่วนลูกค้าใหม่แยกจากหน้าออกแพตช์ ไม่บังคับบิ้ว/อัปโหลด EXE ทุกครั้งที่แก้โปรแกรมเล็กน้อย แต่ยังต้องรักษาคู่รุ่นและการตรวจความแท้
- ทำ wizard ติดตั้ง/shortcut/first run/login/Extension connection/prerequisite diagnostics ที่อ่านง่าย ไม่ต้องให้ลูกค้าพิมพ์คำสั่งหรือติดตั้ง Python เอง
- ถ้า Chrome ต้องให้ผู้ใช้อนุญาต ให้มีขั้นตอนใน wizard ชัดเจน ไม่ข้าม consent หรือคัดลอก profile ของผู้พัฒนา
- แยก patch signing ออกจาก Windows executable signing: ตรวจความแท้ของแพตช์ด้วยกุญแจที่เชื่อถือได้; ประเมิน certificate สำหรับ EXE/installer และทดสอบ Windows warnings ไม่รับประกันว่าแค่มี hash จะไม่มีคำเตือน
- ทดสอบติดตั้งใหม่, เปิดซ้ำ, repair/reinstall และ uninstall ที่ไม่ลบงานโดยเงียบ

ผ่านเมื่อ: เครื่องสะอาดที่ไม่มี environment พัฒนาติดตั้ง เปิด Login เชื่อม Extension และทำ workflow ที่ประกาศรองรับได้จริง

### P5 — ทดสอบรุ่น A → B ก่อนแจก

1. ติดตั้ง A บนเครื่องทดสอบที่สอง/VM ล็อกอินบัญชีทดสอบ และสร้างชุดข้อมูล/คิว/checkpoint ทดสอบที่ตรวจเปรียบเทียบได้
2. บิ้ว B ที่มีการเปลี่ยนแปลงระบุชัด ทำแพตช์ signed ให้รองรับ A ไม่ใช้ไฟล์เดียวกันเปลี่ยนแค่ชื่อหลอกทดสอบ
3. อัปโหลดร่างผ่านสองช่องตาม P3 โดยไม่อัปโหลด JSON/EXE แยก ทดสอบทั้งใช้ Extension เดิมและเปลี่ยน Extension ตรวจว่า A ยังไม่เห็นอัปเดตก่อน publish; publish ใน test/beta channel แล้ว A ที่เปิดค้างต้องตรวจพบเอง
4. ผู้ใช้กดปุ่มหลักครั้งเดียว ติดตั้ง เปิดใหม่ ตรวจ version B, Token, data และคู่ Extension โดยไม่คัดลอก ZIP เอง
5. ทำซ้ำกรณีกำลังทำงาน/กดเลื่อน/เน็ตหลุด/พื้นที่ไม่พอ/ไฟล์เสีย/ไฟล์ล็อก/ปิดเครื่องระหว่างธุรกรรมและเปิด B ไม่สำเร็จ เพื่อพิสูจน์ rollback
6. ตรวจคิวเก็บครบและพักตามสัญญา ไม่สร้างภาพ/คลิป/เสียง/โพสต์ซ้ำ; เปรียบเทียบ hashes/count ของข้อมูลทดสอบโดยไม่เปิดเผย credentials
7. ทดสอบทุก base version ที่ประกาศ `supported_from`; ถ้าตรวจไม่ครบให้ลดรายการรองรับ ไม่เดาว่า patch เดียวข้ามได้ทุกรุ่น

ผ่านเมื่อ: มีรายงานเครื่อง/รุ่น/ขั้นตอน/ผล/ข้อจำกัดจริง ไม่ใช้ผล mock 5 tests ของ updater เดิมแทนผลนี้ และไม่คิดว่าสร้าง EXE สำเร็จเท่ากับอัปเดตลูกค้าสำเร็จ

### P6 — ส่งมอบและเผยแพร่

- ส่งมอบแพตช์ ZIP ที่มี signed metadata/คู่มือในตัว และ Extension ZIP แยกเมื่อเปลี่ยนรุ่น; installer เต็มสำหรับลูกค้าใหม่อยู่ส่วนแยก คู่มือ admin ต้องแสดงสองช่องตรงกับหน้าจอจริง ไม่สั่งให้เลือก JSON/EXE เพิ่มก่อนออกแพตช์
- ทดสอบ beta กลุ่มเล็กก่อน stable แยก channel ชัดเจน ผู้ใช้ทั่วไปไม่ถูกย้ายเข้า beta เอง
- เจ้าของเป็นผู้อนุมัติ/อัปโหลด/กดเผยแพร่ตาม workflow ที่กำหนด การจัดทำไฟล์ไม่ได้หมายถึงอนุญาตโพสต์หรือ deploy อัตโนมัติ
- หน้า admin รายงานรุ่นที่เครื่องส่งกลับมาจริง ไม่สรุปว่าทุกคนอัปเดตแล้วเพียงเพราะกด publish

## สิ่งที่ล็อกก่อนเริ่ม P1/P2

ใช้เป็นข้อเสนอเริ่มต้น ไม่ขัดกับแผนหลัก และไม่ถือเป็นการกำหนดเงื่อนไขขายแทนเจ้าของ:

- default 1 เครื่อง/1 Chrome profile; วันหมดอายุให้แอดมินเลือกตอนออกสิทธิ์ ไม่กำหนดราคา/แพ็กเกจขึ้นเอง
- Token desktop/Extension แยกขอบเขตแต่สมาชิกเดียวกัน; ถ้าจะลดให้ผู้ใช้กรอกครั้งเดียว ต้องออกแบบ pairing consent และ credential exchange ไม่ย้าย Token desktop ทั้งตัวเข้า Extension
- ผู้ใช้ยืนยันแล้วว่า “เตะ” ไม่ใช่ “เพิกถอน”: ใช้ Token เดิมที่มีสิทธิ์กับเครื่องเดิมได้ตามปกติ แต่ต้องกรอกเอง, 1 Token ต่อ 1 เครื่อง
- เปิดให้อัปเดตซอฟต์แวร์ได้เมื่อสมาชิกหมดอายุ โดยไม่คืนสิทธิ์สร้างงาน; ถ้าจะจำกัดสิทธิ์ดาวน์โหลดต้องออกแบบ recovery route ให้ชัด
- เริ่มรองรับชุด Windows ที่พิสูจน์แล้ว และบันทึกเครื่องที่ยังไม่ทดสอบ; ไม่ผูกกับพาธผู้ใช้ `keera`
- ช่องทาง Extension และ Windows signing certificate เป็นจุดตัดสินใจก่อนส่งมอบสู่ลูกค้าทั่วไป ถ้าไม่ได้ข้อสรุปให้คง internal/beta ไม่อ้างว่าพร้อม public distribution

## ขอบเขตที่ไม่ทำในรอบแผน

- ไม่แก้ logic สร้างคลิป/โพสต์ Facebook, ไม่บิลด์ installer/แพตช์, ไม่เปลี่ยนเวอร์ชัน, ไม่โหลด Extension ใหม่ และไม่หยุดงานที่กำลังรัน
- ไม่ deploy/restart server ไม่เปลี่ยนฐานข้อมูล ไม่ออก Token จริง ไม่จัดการกุญแจ/ใบรับรอง และไม่ใช้เครดิตสร้างคลิป
- ไม่มีเวลาส่งมอบที่ยืนยันจนกว่าจะจบ P0 และรู้ข้อจำกัด clean-machine/Extension distribution; ให้รายงานความคืบหน้าตามเกณฑ์ผ่าน ไม่รับประกันปราศจากบั๊ก

**งานแรกเมื่อได้รับคำสั่งลงมือ: P0 ตรวจและล็อกโครงสร้าง จากนั้น P1 ระบบ Token หลังบ้าน แล้ว P2 Login/client โดยมี internal build smoke ควบคู่**

## แผนฟังก์ชันอื่นที่ยังเก็บไว้

[โมชั่นกราฟิกและนายแบบ/นางแบบใน Story Shorts](shorts-motion-graphics-cast.md) ยังคงเป็นแผนพักไว้ ไม่ถูกลบหรือถือว่าทำเสร็จจากการรวมแผน Login/อัปเดตครั้งนี้ ให้เจ้าของเลือกลำดับทำฟังก์ชันนั้นแยกจาก P0–P6 เพื่อไม่เปลี่ยน provider automation ที่ใช้งานอยู่โดยปริยาย
