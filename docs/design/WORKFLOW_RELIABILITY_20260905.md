# SmartFlow — แผนเสถียรภาพโปรแกรมและ Extension

วันที่: 2026-09-05 • รุ่นเป้าหมาย: 0.15.244 Candidate

## ขอบเขตและปัญหาที่พิสูจน์ได้

รอบนี้แก้การส่งงาน/สถานะ/ผลลัพธ์ระหว่างโปรแกรมกับ Extension ไม่รื้อขั้นตอนคลิก Google Flow ที่ใช้งานได้แล้ว และไม่เปลี่ยน provider, Prompt, รูป หรือไฟล์งานเดิม

| ปัญหาจาก Source ที่จำลองได้ | แนวแก้ | จุดทดสอบ |
|---|---|---|
| คำสั่งยาวกัก heartbeat จนโปรแกรมคิดว่า Extension หลุด | แยก heartbeat ออกจากคิว action แต่ action ยังทีละคำสั่ง | คำสั่งค้าง + heartbeat รอบใหม่ยังส่งได้ |
| ตอบรับคำสั่งถูกปฏิเสธ แต่ Extension มองว่าสำเร็จ | ตรวจ HTTP/body และเก็บผล action ไว้ส่ง ACK ซ้ำอย่างเดียว | ACK ล้ม/lease เปลี่ยนต้องไม่กดสร้างใหม่ |
| ดาวน์โหลดไฟล์อื่นระหว่างรอ Flow ถูกเปลี่ยนชื่อเป็น MP4 | จับคู่ download ID/แหล่งไฟล์/ชนิดสื่อ/รอบงาน | PDF หรือรูปที่ไม่เกี่ยวต้องไม่ถูกแก้ชื่อ |
| ดาวน์โหลดเสร็จแล้ว แต่แท็บปิดทำให้กู้ receipt ไม่ได้ | ตรวจไฟล์/receipt ของ Job+Shot+Run ก่อนหาแท็บ | มีไฟล์ถูกต้องกู้ได้; ไฟล์หาย/คนละรอบต้องไม่รับ |
| ยกเลิกงาน A ลบ monitor งาน B | ล้างสถานะเฉพาะเจ้าของงานและช็อต | งานอื่นต้องคงอยู่ |
| ผล AI มาช้าหลังยกเลิก เปิด Flow ขึ้นมาอีก | ปฏิเสธ callback ที่ไม่ควรรับก่อนแก้ checkpoint | cancelled ห้าม apply/open; duplicate ห้ามล้างคลิป |
| Resume เลือกฉากที่มี policy fallback แล้ว | หา canonical slot ที่ยังขาดจริงและเชื่อเฉพาะ client ปัจจุบัน | local-motion slot ต้องไม่กลับไป Flow |
| Worker อ่านสถานะจาก Extension รุ่นเก่า | กรอง exact required version จาก fresh bridge snapshot | old/new client ของ Job เดียวกันไม่ปะปน |
| callback ยกเลิก Story รอบเก่าไปหยุดรอบใหม่ | ผูก callback กับ Job + cancellation event เดิม | resume Job เดิม/เปลี่ยน EP ไม่โดน callback เก่า |

## สัญญาการทำงาน

```text
EXE / โปรแกรม
  → บันทึก Job + provider + canonical images + Run
  → Bridge แจกคำสั่งพร้อมเจ้าของ/lease
  → SmartFlow Extension ทำ action ครั้งเดียว
  → ตรวจ postcondition + เก็บ execution receipt
  → ส่ง ACK (ส่ง ACK ซ้ำได้ แต่ห้ามทำ action ซ้ำเพื่อส่ง ACK)
  → เมื่อคลิปเสร็จ: ดาวน์โหลดไฟล์ของช็อต/Run นั้น
  → โปรแกรมตรวจและบันทึกไฟล์ + checkpoint
  → ไปช็อตที่ขาดถัดไป
  → รวมเสียง/ซับ/วิดีโอ → Final พร้อมจริง
```

Heartbeat เป็นสายแยกสำหรับบอกว่า Extension ยังเชื่อมต่อ ไม่ใช่หลักฐานว่าช็อตสำเร็จ ดาวน์โหลดเสร็จไม่เท่ากับโปรแกรมรับเข้า checkpoint แล้ว และส่งรูปครบไม่ใช่ Final พร้อม

### สิ่งที่คงเดิม

- อัปโหลดรูปครั้งเดียว → รอการ์ดในหน้าเดิม → เมนู “ทำให้เคลื่อนไหว” → พิสูจน์รูปในช่อง Prompt → ส่งครั้งเดียว → อนุมัติครั้งเดียว → รอ → ดาวน์โหลดผลใหม่ที่ตรงช็อต
- ห้าม reload หลังอัปโหลดรูป 100%, เปิดดูรูปแทนแนบ, สลับ provider หรืออัปโหลด/ส่งซ้ำเพราะ ACK ขาด
- เฉพาะ structured current-card policy + ไม่หักเครดิต + Retry ที่ผ่านหลักฐานเดิม จึงใช้รูป canonical เดิมทำ local motion แล้วไปฉากถัดไป คิวแน่นไม่ใช่ policy
- Final ต้องแยกจำนวน Flow จริงกับ local motion และคง H.264/yuv420p/AAC
- โปรแกรมเปิดผ่าน SmartFlow AI.exe เท่านั้น เทสต์ GUI เสร็จต้องปิดหน้าต่างและหลังบ้านของเทสต์ โดยไม่หยุดงานผู้ใช้ที่กำลังทำอยู่

## Log ที่ใช้วินิจฉัย

ยึด trace เดิมในโปรแกรมและ extension_trace.jsonl โดยแยก command received, action started/completed, ACK pending/recovered, download matched/completed, import/checkpoint และ next-shot ให้ชัด ใช้ Job/Shot/Run/command เป็นตัวผูก ไม่ใช้ข้อความทั้งหน้ามาตัดสินสถานะ ห้ามบันทึก token, cookies หรือ signed media URL เต็ม

## ลำดับตรวจรับ

1. จำลองบั๊กจาก Source จริงแบบไม่เปิดเบราว์เซอร์และไม่แตะงานผู้ใช้
2. เทสต์ regression ที่เกี่ยวข้อง แล้ว full unittest suite
3. รัน isolated Extension ↔ Bridge integration กับข้อมูลชั่วคราว
4. ตรวจ manifest/service worker/JS และเลขรุ่นโปรแกรมตรงกัน
5. เปิด EXE ตรวจหน้า/สถานะ แล้วปิดเทสต์และตรวจหลังบ้าน
6. แพ็กโฟลเดอร์+ZIP ใหม่ ตรวจทุกไฟล์ตรงกับ Source ด้วย SHA-256
7. ติดตั้ง Extension ใหม่และรันงานจริงเพื่อรับรอง E2E; ห้ามยก automated tests เป็นหลักฐานว่า Google Flow จริงจบแล้ว

## ขั้นต่อไปที่ยังไม่เหมารวมว่าทำเสร็จ

- เก็บสถานะราย Job+Shot+Run แยกจาก slot เดียวใน client เพื่อให้ progress เก่าทับ progress ใหม่ไม่ได้แม้อยู่รุ่นเดียวกัน
- dashboard เวลาแต่ละขั้นจาก measured traces; เปรียบเทียบ shot 1/2/3 และแยกเวลารอ Google ออกจากเวลาของ Extension
- ทดสอบ restart/crash ระหว่าง external click กับบันทึก receipt: มีช่องว่างที่ไม่สามารถรับรอง exactly-once ได้ ต้องตรวจ postcondition/หยุดตรวจ แทนส่งซ้ำ
- installed Chrome E2E ของ Product 3 ช็อต, Story หลายฉาก, cancel/resume และ policy-hybrid ก่อนเลื่อน Candidate เป็น proven baseline

ผลที่ทำจริงและจำนวนเทสต์ให้ดู `CURRENT_RELEASE.json` และ `docs/reports/workflow-20260905/VALIDATION.md` ไม่ใช้เลขเวอร์ชันเป็นหลักฐานว่าเสถียรขึ้นกี่เปอร์เซ็นต์
