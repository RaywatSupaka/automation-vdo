# SmartFlow AI Extension 0.15.240

สถานะ: Candidate — ผ่านการตรวจอัตโนมัติแล้ว แต่ยังต้อง Reload Extension และเปิดโปรแกรมใหม่เพื่อทดสอบกับ Chrome ที่ล็อกอินจริง

## สาเหตุที่แก้

งาน Story `STORY-20260904-030BF6` มีคลิป Flow จริงของฉาก 1–3 แล้ว แต่ฉาก 4 แสดงการ์ดปฏิเสธบุคคลที่มีชื่อเสียงและยืนยันว่าไม่หักเครดิต ในหน้าเดียวกันยังมีข้อความ Agent ว่าอยู่ในคิว รุ่นก่อนอ่านสถานะทั้งหน้ารวมกัน จึงมีโอกาสรอคิวเก่าหรืออ่านการ์ดเก่าเป็นผลของรอบใหม่ผิดพลาด

## พฤติกรรมใหม่

- Extension อ่านเฉพาะ Error card ที่มองเห็น และบังคับให้ข้อความ Policy, ข้อความไม่หักเครดิต และปุ่ม Retry อยู่ในการ์ดเดียวกัน
- เทียบ fingerprint และจำนวนการ์ดกับ baseline ก่อนส่ง เพื่อแยกการ์ดเก่าออกจากผลของรอบปัจจุบัน
- หากรอบปัจจุบันมีหลักฐานคิวหรือกำลังสร้าง จะรอต่อในโปรเจกต์เดิม ไม่ Reload, Upload, Submit หรือ Approve ซ้ำ
- เมื่อเป็น terminal policy จริง Extension ส่ง `failure_code`, `policy_failure_category` และ `failure_card_fingerprint` ผ่าน Local Bridge ให้โปรแกรมตัดสินใจจากข้อมูลแบบมีโครงสร้าง
- Story/ละคร: ครั้งแรกใช้รูป canonical เดิมและลอง Prompt แบบขยับเฉพาะกล้อง แสง และสภาพแวดล้อม โดยไม่ระบุหรือเปลี่ยนบุคคลในภาพ
- Story/ละคร: หาก Run ใหม่ถูกปฏิเสธอีกครั้ง โปรแกรมทำ local motion จากรูปฉากเดิม บันทึก Checkpoint แล้วเดินฉากถัดไปทันที
- Final แบบผสมระบุ `google_flow_story_hybrid_fallback` และแยกจำนวนคลิป Flow จริงกับฉาก fallback อย่างตรงไปตรงมา
- Product ไม่เปลี่ยนกฎ: ยังต้องได้คลิป Flow จริงครบ 3 คลิป โดยย้าย output slot ไปยังรูปถัดไปเมื่อรูปหนึ่งถูก Policy ปฏิเสธ

## การตรวจสอบ

- JavaScript syntax และ Flow snapshot harness: ผ่าน โดยยืนยันทั้ง queue หลังการ์ดเก่า, busy หลังการ์ดเก่า และ terminal policy ปัจจุบัน
- Python regression suite: ผ่าน `503/503`
- Source/package parity: ผ่าน `36/36` ไฟล์ และ ZIP มี `manifest.json` อยู่ที่ root
- SHA-256 ของ ZIP: `2949E6745789FDD8617D15C242451AA4438F24F15338828E8D7F9C68FAC9307F`
- Installed Chrome smoke: รอผู้ใช้ Reload Extension `0.15.240` และเปิดโปรแกรมใหม่

## การติดตั้ง

ปิด SmartFlow AI เดิมก่อน จากนั้นเปิด `chrome://extensions`, ลบหรือ Reload รุ่นเก่า แล้วกด Load unpacked จากโฟลเดอร์ `deliverables/SmartFlow_AI_Extension_0.15.240` ก่อนเปิดโปรแกรมใหม่ เพื่อให้ Desktop bridge และ Extension ใช้สัญญารุ่นเดียวกัน
