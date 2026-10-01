# SmartFlow AI Extension 0.15.236

- แก้เหตุการณ์จริงใน `JOB-20260904-6547D7`: ช็อต 1 สำเร็จ แต่ช็อต 2 ค้างก่อนเริ่มเรนเดอร์เพราะ Google Flow ไม่รับคลิก `ทำให้เคลื่อนไหว`
- รอ semantic target ของเมนูให้นิ่งสามครั้งก่อนทำธุรกรรมคลิก
- หลังเลื่อนเมาส์ไปยังเมนู รอ Material layout beat แล้ว resolve และ hit-test ปุ่มจริงซ้ำอีกครั้ง
- ส่ง `mousePressed`/`mouseReleased` เพียงครั้งเดียว ไม่มี fallback คลิกซ้ำ
- รายงานว่าคลิกสำเร็จต่อเมื่อรูปเข้า Composer หรือเมนูปิดจริง หากหน้าไม่เปลี่ยนให้ `FLOW_ANIMATE_CLICK_NOT_ACCEPTED` แล้ว safe-stop
- แก้ Desktop ให้รู้จักสถานะถาวร `attachment_waiting_manual` และแจ้งข้อผิดพลาดทันที ห้ามแสดงเหมือนกำลังเรนเดอร์ต่ออีก 30 นาที
- Safe-stop ใช้ข้อความมาตรฐานที่บล็อก outer retry จึงไม่เปิดโปรเจกต์หรืออัปโหลดรูปเดิมซ้ำ
- ผ่าน Unit/Regression tests 481 รายการ, JavaScript syntax 26/26 และ Isolated Extension Bridge Harness

สถานะ: Candidate รอทดสอบงานจริงต่อจาก Checkpoint ช็อต 2 ของ `JOB-20260904-6547D7`
