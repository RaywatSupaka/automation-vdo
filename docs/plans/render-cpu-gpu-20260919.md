# SmartFlow AI — วิเคราะห์ CPU/GPU ตอนประกอบคลิปและแผนปรับปรุง

วันที่ 2026-09-19 — **วิเคราะห์และวางแผนเท่านั้น ยังไม่เปลี่ยนโค้ดหรือการตั้งค่างาน**

อัปเดตหลังผู้ใช้อนุมัติลงมือทำ: เพิ่ม local render backend v1 ใน source แล้ว ดูผลทดสอบและขอบเขตที่ยังไม่รับรองใน [รายงานการนำแผนไปใช้](../reports/render-backend-20260919.md) ข้อมูลด้านล่างคงไว้เป็นหลักฐานการวิเคราะห์ก่อนแก้ ไม่ใช่สถานะปัจจุบันของ source และยังไม่ใช่การรับรอง installed E2E หรือไฟล์ติดตั้งรุ่นใหม่

## หลักฐานจากเครื่องและงานล่าสุด

- งาน `STORY-20260919-411C24`: สร้างสำเร็จ 10 ฉาก / 80 วินาที / Google Flow / เสียงต้นฉบับ / เพลงพื้นหลัง เปิดโลโก้ ไม่เปิด Subtitle, intro, presenter หรือ green screen
- โปรแกรมที่เปิดจริง: engine PID 28424, required Extension 0.15.383; ช่วงแรกที่ตรวจ Story ยัง active ต่อมาตรวจพบ complete/100% และคิวพักอยู่ ไม่ได้หยุดหรือเริ่มงานแทนผู้ใช้
- CPU: AMD Ryzen 5 7600, 6 cores / 12 logical processors; GPU: NVIDIA RTX 5070 Ti และ AMD integrated graphics
- ภาพรวม NVIDIA ขณะเก็บตัวอย่าง: GPU 9%, encoder 0%, decoder 0%; ไม่พบ FFmpeg กำลังทำงาน ช่วงวัด CPU ของโปรแกรมซ้ำ 5 วินาทีเป็น **หลังงานจบ** ได้ประมาณ 0.08% ของ 12 logical processors จึงใช้ตัวเลขนี้สรุปประสิทธิภาพระหว่างเรนเดอร์ไม่ได้
- FFmpeg ที่ resolve ตามโปรแกรมอยู่ที่ `C:/Users/keera/AppData/Local/SmartSubAI/VoiceCloneOnline/ffmpeg/bin/ffmpeg.exe` ตามค่าประจำงานด้วย มี h264_nvenc/h264_amf/h264_qsv ใน build
- ทดสอบวินิจฉัย NVENC ด้วยภาพสังเคราะห์ 720x1280 / 30 เฟรมไปยัง null output ผ่าน exit 0 ยืนยันว่าชุด FFmpeg/driver/GPU นี้เปิด encoder ได้ ไม่ใช่ benchmark งานประกอบจริง และไม่ได้สร้างไฟล์หรือใช้เครดิต AI
- FFprobe ของ Final: H.264 High, yuv420p, 720x1280, **60 fps**, AAC, 80.000 วินาที; encoder tag เป็น `Lavc62.28.101 libx264` จึงยืนยันว่าไฟล์นี้เข้ารหัสภาพด้วย software encoder
- ตรวจไฟล์ดาวน์โหลดต้นทางทั้ง 10 ไฟล์: ทุกไฟล์ 720x1280 / **24 fps** / 8 วินาที ค่าประจำงานตั้ง 60 fps/high จริง ไม่ใช่หลักฐานว่าโปรแกรมเปลี่ยนค่าผู้ใช้เอง

## ลำดับเวลาที่แยกการเรนเดอร์ออกจากการรอเว็บ

| เวลาไทย | หลักฐาน |
|---|---|
| 05:59:08 | Extension ยืนยันดาวน์โหลดวิดีโอฉาก 10 และส่งต่อขั้นตอนรายฉาก |
| 05:59:11 | โปรแกรมรับบทและภาพครบ / STORY_AI_RESULT success |
| 05:59:52 | ไฟล์ `videos/story_short_complete.mp4` เขียนเสร็จ และสร้างคำขอ AI cover |
| 06:01:22 | AI cover ได้รับ/บันทึกแล้ว; ledger คำขอปกใช้เวลา 90.83 วินาที |
| 06:01:25 | งาน complete, final_validation passed และโปรแกรมทำ cleanup ของตัวเอง |

ช่วงประมาณ 41 วินาทีจากรับผลครบถึงบันทึกวิดีโอเป็นกรอบเวลาการประกอบ/ตกแต่งท้ายงาน ไม่ใช่เวลา encoder ที่วัดแยกทุกขั้น และไม่รวมการเตรียมคลิปแต่ละฉากก่อนหน้านั้น ช่วงอีกประมาณ 91 วินาทีคือวงจรทำปกบน AI Web ไม่ใช่การเข้ารหัสวิดีโอในเครื่อง CPU/GPU ต่ำในช่วงนี้จึงไม่ใช่หลักฐานว่าตัวประกอบค้าง

ไม่พบหลักฐานว่าการค้างหรืออุปกรณ์เสียเป็นสาเหตุของงานนี้ แต่ยังไม่มีการเก็บ utilization ระหว่างการประกอบจริงทุกช่วง จึงไม่สรุปว่า CPU เคยใช้กี่เปอร์เซ็นต์ขณะเรนเดอร์

## สาเหตุในโค้ดที่ยืนยันได้

1. **ยังไม่มีนโยบายเลือก hardware encoder กลาง**: `core/flow_native_audio.py:compose_native`, `video_composer.py:compose`, `story_video.py`, `video_logo.py:render`, `subtitle_renderer.py`, `video_intro.py`, `presenter.py`, `green_screen.py` กำหนด `libx264` โดยตรงหลายเส้นทาง ไม่พบ h264_nvenc/AMF/QSV/hwaccel ใน core/ui ที่เรียกใช้จริง การมี GPU ไม่ทำให้คำสั่งเหล่านี้สลับไปใช้เอง
2. **เข้ารหัสหลายรอบ**: `scene_voice.py:render_scene_asset` normalize รายฉาก → `_compose_story_media` รวมฉากผ่าน compose_native และ encode อีกครั้ง → `finish_story_media` ใส่โลโก้ด้วย encode อีกรอบ ปัจจุบันยังไม่มีเส้นทางรวมแบบคัดลอก stream สำหรับ segment ที่เหมือนกันครบทุกเงื่อนไข
3. **เพิ่มจำนวนเฟรมตามค่าที่บันทึก**: ต้นทาง 24 fps ไป Final 60 fps ทำให้วิดีโอ 80 วินาทีมี 4,800 เฟรม แทน 1,920 เฟรม เป็นจำนวนเฟรม 2.5 เท่า ไม่ใช่คำรับรองว่าเวลาเพิ่มหรือลด 2.5 เท่า และไม่ได้สร้างรายละเอียดการเคลื่อนไหวใหม่ด้วยตัวมันเอง ห้ามลดค่า 60 fps ของผู้ใช้โดยเงียบ ๆ
4. **การวัดสถานะยังไม่ครอบคลุม**: ตัวประกอบหลัก/โลโก้/ซับรอ `run_cancellable` จบ โดยไม่ได้ส่ง frame/fps/speed/device ระหว่างทำงานเหมือน green_progress ทำให้แยกงานคำนวณกับช่วงรอภายนอกได้ยาก
5. **กรีนสกรีนมีข้อจำกัดแยกต่างหาก**: กำหนด `-filter_complex_threads 1` ในขั้นเตรียมและ overlay และใช้ libx264 เช่นกัน; ค่า 1 จำกัดงาน filter graph ไม่ได้แปลว่า decoder/encoder ทุกตัวใช้ CPU thread เดียว งานล่าสุดปิดฟังก์ชันนี้ จึงห้ามระบุว่ากรีนเป็นต้นเหตุรอบนี้
6. **ส่วนที่ทำถูกอยู่แล้วต้องรักษาไว้**: AudioMixer ใช้ `-c:v copy` เวลาเพิ่มเพลง, green v2 ลด fps/size ก่อน key และมี cache, checkpoint รายฉากป้องกันสร้าง AI/เสียงซ้ำ, Final ผ่าน validation และเก็บต้นฉบับก่อน publish

## แผนดำเนินการตามลำดับ

### P0 — สถานะและข้อมูลวัดผลก่อนปรับความเร็ว

- แยก `กำลังประกอบในเครื่อง`, `ใส่โลโก้/ซับ`, `มิกซ์เสียง`, `ตรวจไฟล์`, `วิดีโอพร้อม—กำลังสร้างปกบนเว็บ` ไม่ใช้คำว่าประกอบคลิปครอบช่วงรอปก
- แสดง encoder จริง, FFmpeg PID, เฟรมปัจจุบัน/ทั้งหมด, render fps, speed, elapsed และเหตุผลที่ fallback
- ขยาย progress reader ให้เส้นทางประกอบ/โลโก้/ซับใช้ร่วมกัน; ระบาย stdout/stderr ต่อเนื่อง รักษาปุ่มยกเลิก จำกัด log และ throttle UI ไม่ให้เป็นตัวถ่วงเอง
- บันทึก stage timings/read-only render diagnostics ต่อ job โดยไม่เก็บ token หรือ prompt; งานรอเว็บไม่ถูก watchdog ตีว่า FFmpeg ค้าง
- เฟรมไม่เพิ่มหรือ CPU ต่ำอย่างเดียวไม่ใช่เหตุให้ kill/restart; ตรวจ process, file/progress activity, I/O และขั้นตอนก่อนวินิจฉัย

### P1 — เลือก CPU/GPU อย่างถูกต้อง

- เพิ่ม `core/render_backend.py` (เสนอใหม่) เป็นจุดเดียวสำหรับ encoder/capability/quality policy: Auto / GPU preferred / CPU
- Auto ตรวจ FFmpeg ที่ใช้จริงและทดลอง encoder สั้น ๆ; cache ตาม executable/build/driver ไม่ตรวจใหม่ทุกเฟรมหรือทุกรอบย่อย
- เครื่องนี้เลือก NVIDIA `h264_nvenc` เมื่อผ่าน probe; รองรับ AMF/QSV ภายหลังด้วยการทดสอบจริงของอุปกรณ์ ไม่ถือว่ามีชื่อ encoder แปลว่าใช้ได้
- เริ่มจาก **CPU ทำ filters + GPU encode** เพื่อคงผลภาพเดิม ก่อนพิจารณาย้าย decode/scale/overlay ไป GPU ทีละส่วน การเปลี่ยน encoder อย่างเดียวไม่ย้าย chromakey/subtitle/filter ทั้งหมดไป GPU
- แยก quality options ของ x264 กับ NVENC ห้ามนำ `-crf` ไปแทนค่า NVENC โดยตรง; รักษา H.264 High/yuv420p/AAC และตรวจภาพ/เสียง/เวลา/ขนาดไฟล์
- GPU ใช้ไม่ได้ให้ fallback CPU เฉพาะขั้นตอน local ที่ล้มเหลวแบบมีขอบเขต เก็บสาเหตุและ candidate แยก ไม่เรียก AI/สร้างคลิป/ทำเสียงใหม่ ไม่ overwrite Final ที่ดีอยู่
- ส่งค่า renderer ผ่าน settings → queue snapshot → scene/whole composition; งานเก่าคงค่าที่บันทึกไว้ เว้นแต่ผู้ใช้ขอประกอบใหม่

### P2 — ลดงานซ้ำก่อนเพิ่มภาระฮาร์ดแวร์

- ตรวจ codec/profile/pixel format/ขนาด/fps/time base/audio layout/sample rate/codec parameters/timestamp continuity ก่อนใช้ concat แบบ copy; หากไม่เหมือนกันหรือมี trim/transition/filter ให้ใช้ normalize ที่จำเป็นเท่านั้น
- รักษา checkpoint รายฉากและ voice-fit; ห้ามตัดขั้นเตรียมเสียง/ปรับระยะของงาน API voice เพื่อแลกความเร็ว
- รวม filter ที่เข้ากันได้ใน encode ครั้งเดียว เช่น normalize/concat + logo โดยรักษาลำดับ subtitle, intro และ green ชั้นบนสุด; แยกเป็นขั้นเมื่อจำเป็น
- เพิ่มตัวเลือก fps `ตามต้นฉบับ` สำหรับงานใหม่; ค่า 24/30/60 ที่เลือกเองยังต้องเคารพ และคิวเก่าห้ามถูกเปลี่ยนย้อนหลัง
- ส่วนเพิ่มเพลงคง `-c:v copy` ที่ทำอยู่แล้ว ไม่เปลี่ยนให้ re-encode

### P3 — ปรับกรีนสกรีนแยกจากบั๊กปัจจุบัน

- ใช้ benchmark เปรียบเทียบ filter threads 1/2/4/auto และ software/hardware final encoding แทนการเพิ่ม threads สูงสุดโดยไม่วัด
- รักษา single-pass/cached-cycle v2, alpha/transparency, ขอบสี, fit/opacity, ลำดับ 1–3 effects และทิ้งเสียงเอฟเฟกต์ตามเดิม
- GPU key/overlay เป็นขั้นถัดไปหลังตรวจ filter capability และผลภาพ ไม่ย้ายทั้ง pipeline ในครั้งเดียวหรือปิด cache ที่ผ่านการตรวจแล้ว

### P4 — การทดสอบก่อนส่งให้ใช้จริง

- ใช้คลิปเดิมอ่านอย่างเดียวและพื้นที่ชั่วคราว ไม่แตะ Final/ledger ของงานนี้ ไม่เสียเครดิตสร้างภาพ/วิดีโอใหม่
- วัดเวลาจริงแยก normalize, concat, logo, subtitle, audio, intro, green และ publish; เปรียบเทียบ CPU กับ NVENC ที่คุณภาพใกล้เคียง ไม่ตั้งเป้า CPU/GPU 100% เป็นเกณฑ์ผ่าน
- ครอบคลุม Shopee/Shorts/Drama, เสียงต้นฉบับ/API, โหมดตัวละครไม่มีซับ, 24/30/60 fps, มี/ไม่มี green, cold/cache hit และหลายความยาว
- ตรวจ duration, frame count, AV sync, เสียงไม่หาย, สี/ซับไทย/ขอบ alpha, คุณภาพและ playback; จำลองไม่มี GPU/driver เปลี่ยน/encoder เปิดไม่ได้/ยกเลิก/พื้นที่ดิสก์หมด/เปิดงานเดิมต่อ
- ตรวจ installed EXE แบบแยกงานทดสอบก่อนรับรอง E2E ไม่เท่ากับ unit test หรือการตรวจ NVENC 30 เฟรม
- ทบทวนการ bundle FFmpeg ให้ SmartFlow เป็นอิสระก่อนทำ installer สำหรับเครื่องอื่น ปัจจุบันใช้ไฟล์จากการติดตั้ง VoiceCloneOnline; ไม่ใช่สาเหตุ GPU ใช้ไม่ได้ในเครื่องนี้ แต่เป็นความเสี่ยง portability ที่ต้องแก้ตามแผน installer

## ขอบเขต Extension

การเข้ารหัส Final อยู่ในโปรแกรม ไม่อยู่ใน Extension จึง **ไม่แก้ Send/DOM/provider recovery** เพื่อแก้ประสิทธิภาพนี้ ตรวจความเข้ากันได้ของสถานะรอปก/ผลวิดีโอ และเพิ่มข้อมูล progress เฉพาะเมื่อ protocol จำเป็นจริง ห้ามเปลี่ยนรุ่น Extension เพียงเพราะคาดว่าจะต้องแก้

## เอกสารอ้างอิง

- NVIDIA: [Using FFmpeg with NVIDIA GPU Hardware Acceleration](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ffmpeg-with-nvidia-gpu/index.html) — แยก software decode/filter และ hardware encode ได้; การเร่งทั้ง pipeline ต้องตั้งแต่ละส่วนโดยตรง
- FFmpeg: [filter_complex_threads](https://ffmpeg.org/ffmpeg.html#Advanced-options) — เป็นจำนวน threads ของ complex filter graph ไม่ใช่เพดานการใช้ CPU ทั้งโปรแกรม
- หลักฐานในเครื่อง: job/render_plan, `prompts/scene_pipeline.json`, `logs/extension_trace.jsonl`, `workspace/ai_cover_requests.json`, `logs/2026-09-19.log`, ffprobe ทั้ง 10 คลิปและ Final

การตรวจครั้งนี้ไม่มีการติดตั้ง/รีโหลด/เปลี่ยน config/หยุดงาน/แก้ source โปรแกรมหรือ Extension; มีเพียงอ่านข้อมูลและ diagnostic NVENC ไป null output ซึ่งจบแล้ว
