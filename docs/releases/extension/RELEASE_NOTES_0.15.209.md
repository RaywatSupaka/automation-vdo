# SmartFlow AI Extension 0.15.209

วันที่: 2026-09-03

## แก้ไข Responsive Google Flow

- รองรับ Media picker ที่เปลี่ยนรูปแบบตามขนาดหน้าต่าง Chrome
- Overlay/Listbox ต้องครอบแถวชื่อไฟล์ที่อัปโหลดจริงจึงจะถูกเลือก
- ไม่ใช้ `overlays.at(-1)` แบบไม่ตรวจสอบ ซึ่งอาจชี้ไปยังเมนูอื่น
- ใช้พิกัดจากองค์ประกอบจริงหลัง Flow จัดหน้า ไม่ใช้พิกัดตายตัว
- คงกฎแนบรูปครั้งเดียว อัปโหลดครั้งเดียว และกดสร้างครั้งเดียว

## Version contract

- Extension/Local Bridge: 0.15.209
- Flow helper build: `flow-0.15.209-20260903.1`
