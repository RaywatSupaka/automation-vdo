# SmartFlow AI Extension 0.15.215

รุ่นแก้การค้างหลัง Google Flow ดาวน์โหลดวิดีโอสำเร็จ โดยอ้างอิงงานจริง `JOB-20260903-941B28`

## แก้ไข

- รองรับเหตุการณ์ดาวน์โหลดวิดีโอที่มาจาก CDN `flow-content.google`
- ไม่รอ timeout 90 วินาทีเมื่อ Chrome เริ่มดาวน์โหลดไฟล์จริงแล้ว
- คงการตรวจไฟล์ตาม Job/SHOT และชนิด MP4/WebM ก่อนส่งผลกลับโปรแกรม
- ไม่เปลี่ยนลอจิกแนบรูป, กดสร้าง, อนุมัติ หรือการติดตามผล จึงไม่เพิ่มความเสี่ยงส่ง Prompt ซ้ำ

## ผลจากงานจริงก่อนแก้

- AI Web สร้างรูปครบ 3 รูป
- Google Flow สร้างและดาวน์โหลดครบ 3 ช็อตโดยไม่ส่งซ้ำ
- Final ยาว 30.0 วินาที พร้อมเสียงพากย์ Subtitle เพลง เสียงเน้น และโลโก้
- โปรแกรมตรวจ Final ผ่านและล้างไฟล์ขั้นกลาง 6 ไฟล์ คืนพื้นที่ 51.3 MB

## Regression

- เพิ่ม test ยืนยันว่า native download watcher รับ `flow-content.google`
- รุ่น Extension, helper และ Local Bridge ต้องตรงกันที่ `0.15.215`
- Focused regression: 2/2 ผ่าน
- Unit tests: 418/418 ผ่าน
- JavaScript/Python syntax: ผ่าน
- Package parity: Source และแพ็กตรงกัน 36/36 ไฟล์
- ZIP SHA-256: `9F6A54A50720C4E6FE9C2AEC4B6D445A56508D1426E62B9B020687FF171755A6`
