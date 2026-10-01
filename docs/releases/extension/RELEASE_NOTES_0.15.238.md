# SmartFlow AI Extension 0.15.238

แก้บั๊ก Gemini Web รับ Prompt หลายบรรทัดเพียงบรรทัดแรกจากงานจริง `JOB-20260904-84A00F`

- แปลงเฉพาะ whitespace จริงของ Prompt เป็น single line ก่อนเขียนเข้า Gemini
- ตรวจข้อความครบแบบ exact จาก live Composer สองครั้งติดกัน
- หากวิธีหลักไม่ผ่าน ใช้ trusted CDP text input ได้เพียงหนึ่งครั้งและไม่แนบรูปใหม่
- คืน Composer ตัวล่าสุดให้ขั้นตอนส่ง ป้องกันการอ้าง editor ที่ถูก Gemini rerender
- ตรวจ Prompt แบบ exact อีกครั้งใน Background ก่อน trusted click; หากขาดหรือเปลี่ยนจะไม่คลิก
- ใช้รูปอ้างอิงที่มีอยู่ใน Composer ต่อได้แม้ยังไม่มี user turn ป้องกันการอัปโหลดซ้ำ
- เพิ่ม Log เฉพาะ method, expected/actual length, editor replacement และจำนวน attempt โดยไม่บันทึกเนื้อ Prompt

หลักฐาน live: multiline เหลือ 113 ตัวอักษร; normalized single-line ผ่าน 2,069/2,069 และ Gemini ตอบ JSON สมบูรณ์
