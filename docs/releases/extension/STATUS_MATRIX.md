# SmartFlow Extension — Evidence Matrix

อัปเดต: 5 กันยายน 2026

ตารางนี้แยก “ทำงานจริง”, “มีเพียงเทสต์”, และ “เคยพังจริง” เพื่อไม่ให้เลือก Source จากเลขรุ่นอย่างเดียว

| รุ่น | ระดับหลักฐาน | สถานะ/การใช้งาน |
|---|---|---|
| `0.7.5` | งานจริง Flow 3/3 | พฤติกรรมยุคเก่า ใช้อ้างอิงเท่านั้น |
| `0.15.70` | Drama one-click Final จริง | ใช้อ้างอิง Story/Drama checkpoint ไม่ใช้ยืนยัน Flow upload รุ่นใหม่ |
| `0.15.72` | Product Flow หลาย Job 3/3 | Behavioral reference; ไม่มี Git snapshot ตรงรุ่น |
| `0.15.112` / `afcb918` | Product 3/3 + Final และย้อน Source ได้ | Reproducible Golden ของ physical Flow |
| `0.15.118` | Real one-shot 8 วินาที | ยืนยัน media/video URL เฉพาะหนึ่งช็อต |
| `0.15.121–0.15.122` | Drama Gemini Final และ Story 15 ฉาก | อ้างอิง Gemini/Story checkpoint |
| `0.15.162` | Resume Product จน Final จริง | อ้างอิง exact-shot ownership/crop |
| `0.15.179` | Regression จริง | ห้ามใช้เป็นฐาน: closure แข่งและ upload ซ้ำ |
| `0.15.182–0.15.189` | แก้รายจุด/ส่วนใหญ่ targeted tests | รับเฉพาะ invariant ที่มี test ห้าม restore ทั้งไฟล์ |
| `0.15.196` | Regression จริง | ห้ามใช้เป็นฐาน: empty picker + file drop + project loop |
| `0.15.197–0.15.200` | Golden transaction + security architecture | รับกฎ upload/lease/owner/passive observer; ต้องไม่เปลี่ยน physical flow |
| `0.15.201` | Release gate FAIL | ห้ามใช้เป็นฐาน: JavaScript declaration ซ้ำ |
| `0.15.202–0.15.213` | แก้ exact result/recovery เป็นช่วง | ใช้เฉพาะกฎที่มีหลักฐาน/Regression test |
| `0.15.214` | งาน `JOB-20260903-941B28` จบ 3/3 | ทำงานจริง แต่ยังมี false attachment review และรอ download นาน |
| `0.15.215` | Patch CDN download | เก็บ downloader `flow-content.google`; E2E เกิดก่อนแพ็ก |
| `0.15.216` | งาน `JOB-20260903-DACA78` จบ 3/3 + Final | Modern proven Extension baseline ที่ดีที่สุด; ไม่มี Desktop commit คู่รุ่น |
| `0.15.218` | ถอนรุ่น | ห้ามใช้เป็นฐาน: บังคับ Gemini preview ใหม่จนแนบวน |
| `0.15.219–0.15.224` | Fix ตามเหตุจริง + tests | เก็บ AI attach/send, JSON repair, overlay และ output-slot reassignment |
| `0.15.225` | Regression งาน `JOB-20260904-8E178B` | ห้ามใช้เป็นฐาน: review/upload/project ซ้ำจำนวนมาก |
| `0.15.226` | Targeted fix | ปิด Flow changelog popup แบบ scoped |
| `0.15.227` | 442 tests + isolated harness + package parity | Runtime Candidate; ยังไม่เป็น Golden จนผ่าน Real 3-shot smoke |
| `0.15.228` | 471 tests + isolated harness + parity 36/36 + fast handoff/strict ownership | Runtime Candidate; สืบทอด 0.15.227 และยังรอ Real 3-shot smoke |
| `0.15.229` | ChatGPT composer attachment proof + current Thai upload UI | Runtime Candidate; ห้ามส่ง Prompt เมื่อรูปอ้างอิงยังไม่แสดงจริง |
| `0.15.230` | Google Flow upload 100% continues in-place without refresh | Runtime Candidate; เลือก asset ต่อทันทีและห้ามอัปโหลดซ้ำ |
| `0.15.231` | Live Composer recheck after Settings + direct Agent failure detection | Runtime Candidate; ลดการรอผิดพลาด 75–90 วินาที |
| `0.15.232` | Passive wait for uploaded Flow gallery tile before one-shot animate action | Runtime Candidate; 0.15.231 ผ่าน E2E 3/3 แล้วและรุ่นนี้แก้ false attachment review ที่พบระหว่างงาน |
| `0.15.233` | Close proven upload menu once + physical hit-test before gallery action | Runtime Candidate; งาน `JOB-20260904-8B6BF7` เปิด still-image editor เพราะเมนูอัปโหลดบัง จึงเพิ่ม guard และหยุดโดยไม่อัปโหลดซ้ำ |
| `0.15.234` | Exact uploaded-card `ทำให้เคลื่อนไหว` path + real composer thumbnail proof + program trace | Runtime Candidate; งาน `JOB-20260904-F9AB53` พิสูจน์ manual path แล้วและพบ root cause `องค์ประกอบ cancel` ทำให้ 0.15.233 เปิด picker เกินจำเป็น |
| `0.15.235` | Fresh semantic click point + reuse open animate menu + exact filename/reference + passive safe-stop | Runtime Candidate; แก้จากหลักฐานงาน `JOB-20260904-6547D7`, รอ rerun Job เดิมให้ครบ 3 ช็อตและ Final |
| `0.15.236` | Stable animate target + post-hover hit-test + click postcondition + desktop persistent safe-stop | Runtime Candidate; ช็อต 1 ของ `JOB-20260904-6547D7` ผ่าน แต่ช็อต 2 พิสูจน์ว่า Flow ไม่รับคลิกและ Desktop รอผิด 30 นาที รอ rerun งานเดิม |
| `0.15.237` | Gemini text-only Product prompt + refusal-aware retry + editor-state-safe Prompt insertion | Runtime Candidate; แก้จาก `JOB-20260904-8C4A1B` โดยคง Google Flow transaction เดิมจาก `0.15.236` |
| `0.15.238` | Gemini single-line exact Composer writer + one CDP fallback + pre-click exact guard | Runtime Candidate; live input/JSON response passed on `JOB-20260904-84A00F`, pending full SmartFlow rerun |
| `0.15.239` | Gemini refusal stability gate + canonical turn count + post-CDP target recheck + acceptance trace | Runtime Candidate; recovery JSON passed on `JOB-20260904-CD2A8C`, pending installed Extension rerun |
| `0.15.240` | Current-card policy fingerprint + queue-safe monitor + structured terminal evidence + Story same-image local fallback | Runtime Candidate; automated gates passed, pending installed real Story resume smoke |
| `0.15.241` | First structured current-card policy terminal → immediate same-canonical-image local motion for Product/Story/Drama + truthful hybrid provenance | Runtime Candidate; automated gate 513/513, bridge/snapshot harness และ source/folder/ZIP parity 36/36 ผ่าน รอ installed policy-hybrid smoke ก่อน promotion |
| `0.15.242` | Fail-closed Policy checkpoint + same-image Local Motion + continue next source/scene | Runtime Candidate; ปิด stale package/real-clip overwrite, resume ไม่แตะ Flow, target counts/cleanup ถูกต้อง และ automated gate 518/518 ผ่าน รอ installed policy-hybrid smoke ก่อน promotion |

## เกณฑ์เลื่อน Candidate เป็น Golden

- งานจริงเส้นทางปกติครบทุก Flow slot และอย่างน้อยหนึ่งงาน policy-hybrid ที่มี ordered segment ครบทุก Product source หรือ Story/Drama scene
- ต่อ Flow shot มีหนึ่ง project, upload, submit และ approve เท่านั้น; slot ที่ได้ structured current-card `FLOW_POLICY_BLOCKED` + no-charge + Retry ต้องสร้าง local motion จากรูป canonical เดิมทันที โดยไม่มี safe-prompt retry, reupload, reassign หรือ Alternate Take
- Queue/busy/transient/stale card ต้องรอหรือกู้ Run เดิมและห้ามกระตุ้น fallback; ไม่มี Prompt/รูปซ้ำ ไม่มีรับ result card เก่า และ SHA ของคลิปจริงคนละ slot ไม่ซ้ำ
- ดาวน์โหลด Flow file และสร้าง local-motion file ตาม provenance จริงครบ โปรแกรมเดิน source/scene ถัดไปเอง และ Library/Final แสดง source type พร้อมจำนวน Flow/local/ทั้งหมดตรงกับ manifest
- เก็บ Job ID, log และ media probe เป็นหลักฐานในพิมพ์เขียว

หากยังไม่ผ่านครบ ให้แก้เฉพาะ state transition ที่มีหลักฐานและออกรุ่น Candidate ใหม่ ห้ามเปลี่ยน Attach, Submit, Monitor และ Download พร้อมกัน
