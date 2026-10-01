# SmartFlow AI Extension 0.15.234

- ใช้เส้นทาง Google Flow ที่พิสูจน์กับหน้าเว็บจริง: การ์ดรูป → เมนู → `ทำให้เคลื่อนไหว` → thumbnail ใน Prompt
- แก้ตัวตรวจ thumbnail ที่เคยอ่าน `aria-label=องค์ประกอบ` รวมกับไอคอน `cancel` แล้วตัดสินผิดว่าไม่มีรูป
- รองรับรูป Composer จาก `flow-content.google/image/`
- ตัด fallback ที่เปิดเมนู `+`, เลือกโปรเจกต์ และเลือกรูปเดิมซ้ำทั้งหมดจากธุรกรรมแนบรูป
- ตรวจ semantic target ซ้ำ ณ วินาทีกด `ทำให้เคลื่อนไหว` เพื่อไม่ให้พิกัดจากหน้าจอที่เปลี่ยนไปคลิกคำสั่งอื่น
- `attachment_needs_review` แบบ single-flight safe stop หยุดทันที ไม่วน inspect สิบนาที
- เพิ่ม Extension trace ใน Log โปรแกรมและไฟล์ `logs/extension_trace.jsonl` ต่อ Job โดยไม่รบกวนสถานะหลัก

หลักฐานจริง: `JOB-20260904-F9AB53` ช็อต 1 ผ่าน upload/submit/render/download และการทดสอบช็อต 2 ด้วยเส้นทางข้างต้นแนบรูป ใส่ Prompt อนุมัติ และสร้างวิดีโอสำเร็จ
