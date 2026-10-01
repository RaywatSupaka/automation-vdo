# SmartFlow reusable tools

`BUILD_SMARTFLOW_INSTALLER.bat` ที่รากโปรเจกต์เรียก `build_installer_one_click.py` เพื่อสร้าง Setup รุ่นทดสอบถัดไปโดยตรวจคู่เวอร์ชัน Extension, ของที่ต้องแพ็ก, เทสต์ตัวติดตั้ง และ hash ก่อน ไม่ติดตั้งหรือเผยแพร่เอง ดู `docs/CUSTOMER_INSTALLER.md` สำหรับข้อจำกัดและ `--check-only`.

ไฟล์ในรายการนี้เป็นเครื่องมือที่ใช้ซ้ำได้และอนุญาตให้เรียกจากโปรเจกต์ปัจจุบัน:

- `benchmark_green_render.py` — local-only old/new green comparison, temporary media, max10s sample; no user-job/bridge/provider writes. See docs/reports/meta-single-green-v2.md.

- `apply_ai_package.py`
- `audit_ui_pages.py` (Legacy Tk audit เท่านั้น ห้ามใช้แทนการตรวจ Hybrid ปัจจุบัน)
- `build_safe_image_video.py`
- `finalize_product_job.py`
- `finalize_story_job.py`
- `hybrid_ui_click_smoke.js` (ใช้หลังเปิดโปรแกรมผ่าน EXE; คลิกปุ่มคลังวิดีโอโดยไม่ลบไฟล์ หรือเพิ่ม `--studio-audit` หลัง URL เพื่อตรวจ 13 หน้า/3 ขนาดและ preview latency; ปิดเบราว์เซอร์ทดสอบเองเมื่อจบ)
- `project_integrity_audit.py`
- `repair_video_compatibility.py`
- `run_extension_harness_isolated.py`
- `run_product_smoke.py`
- `run_subtitle_font_e2e.py`
- `run_voice_job.py`
- `validate_media_features.py`

สคริปต์ `add_*`, `fix_*`, `patch_*`, `reconcile_*` และสคริปต์ลงวันที่ 20260903 เป็น migration/repair แบบใช้ครั้งเดียว ถูกเก็บไว้ใน `archives/migration-scripts/2026-09-03/` เพื่อเป็นหลักฐาน ห้ามรันกับ Source ปัจจุบันโดยตรง

ไฟล์ scrcpy เป็น Runtime tool สำหรับ Android ไม่ใช่ Source และไม่ควรถูกเปิดอ่านเพื่อวิเคราะห์โปรเจกต์

หลังทดสอบ UI ตรวจว่าไม่มี Product/Story/Drama active แล้วปิด **หน้าต่าง SmartFlow จริง** อย่างปกติและตรวจ backend หยุดด้วย การส่ง `shutdown` ไป backend อย่างเดียวขณะหน้าต่างยังเปิดจะทำให้ watchdog เปิด engine กลับ เพราะถือว่า engine หลุด ไม่ใช่การปิดโปรแกรม
