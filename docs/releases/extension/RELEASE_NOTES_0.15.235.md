# SmartFlow AI Extension 0.15.235

- แก้ `FLOW_ANIMATE_TARGET_CHANGED_BEFORE_CLICK` โดยค้นหาปุ่ม `ทำให้เคลื่อนไหว` ใหม่ ณ จังหวะ physical click หลัง Material menu ขยับ
- ถ้าเมนูรูปเดิมยังเปิดอยู่ ให้ใช้คำสั่งในเมนูนั้นต่อทันที ไม่ย้อนกลับไปค้นปุ่มสามจุดที่ overlay บัง
- เลือกเฉพาะการ์ดรูปที่ชื่อไฟล์ตรงกับ reference ของ Job/ช็อต ห้ามเดาการ์ดล่าสุด
- เปิดหรือ resume Job/ช็อตเดิมโดยใช้ไฟล์ reference เดิม ไม่ดาวน์โหลดสำเนาใหม่จนชื่อไฟล์เปลี่ยน
- เมื่อธุรกรรมแนบรูปหยุดแบบ at-most-once ให้ helper เฝ้าดู Composer แบบอ่านอย่างเดียว ห้ามอัปโหลด เลือกรูป หรือแนบซ้ำ
- ป้องกัน Product runtime recovery จากการปลุก safe-stop แล้ววนอัปโหลด/แนบรูปอีกครั้ง
- เพิ่ม Regression tests ครอบคลุม fresh target, open-menu reuse, exact card, reference reuse และ passive safe-stop

หลักฐานต้นเหตุ: `JOB-20260904-6547D7` อัปโหลดสำเร็จหนึ่งครั้ง แต่เมนูขยับก่อนคลิกจนไม่เคยส่งสร้างและไม่เสียเครดิต รุ่นนี้ต้องผ่าน rerun งานเดิมครบ 3 ช็อตก่อนเลื่อนสถานะจาก Candidate
