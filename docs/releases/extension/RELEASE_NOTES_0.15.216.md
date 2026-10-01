# SmartFlow AI Extension 0.15.216

รุ่นแก้ false error ขณะส่ง Prompt ไป ChatGPT Web จากหลักฐานงานจริง `JOB-20260903-DACA78`

## สาเหตุ

- หลัง ChatGPT รับ Prompt หน้าเว็บเปลี่ยน Composer เป็น DOM ชุดใหม่
- Extension รุ่นก่อนยังอ่าน editor ตัวเก่าที่หลุดจากหน้า จึงไม่เห็นว่าช่องพิมพ์ถูกล้าง
- การยืนยันเดิมรอเพียงประมาณ 6 วินาทีและมี fallback ส่งซ้ำหลายวิธี

## แก้ไข

- ใช้ trusted browser click เพียงหนึ่งครั้งสำหรับทั้ง ChatGPT และ Gemini
- อ่าน Composer ปัจจุบันใหม่ในทุกครั้งที่ตรวจหลักฐาน
- ตรวจเพิ่มจาก user turn, assistant turn และปุ่มหยุดที่เกิดขึ้นใหม่
- รอหลักฐานสูงสุด 30 วินาที โดยไม่ใช้ `requestSubmit`, synthetic Enter หรือ click ซ้ำ
- คง hotfix ดาวน์โหลด `flow-content.google` จากรุ่น 0.15.215

## ความปลอดภัย

- ถ้ายังไม่มีหลักฐานภายใน 30 วินาที ระบบหยุดที่ Checkpoint พร้อมข้อความชัดเจน
- ห้ามส่ง Prompt ซ้ำอัตโนมัติเมื่อสถานะยังไม่แน่นอน

## ผลตรวจรุ่นส่งมอบ

- Regression เฉพาะการส่ง AI Web และดาวน์โหลด Flow: ผ่าน
- Unit tests: 418/418 ผ่าน
- JavaScript/Python syntax: ผ่าน
- Package parity: Source และแพ็กตรงกัน 36/36 ไฟล์
- ZIP SHA-256: `238FB9D673F512B09A5DB5A7855478FFBF4B728BCF18EC2BEBD1D378DA52A0AD`
