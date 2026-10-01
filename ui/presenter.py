"""Presenter UI adapter. Workers never touch Tk widgets."""
import threading
import uuid
import time
from pathlib import Path
from core.cancellable_process import OperationCancelled
from core.presenter import presenter_settings, PresenterRenderer
from core.presenter_pipeline import PresenterPipeline
from core.job_file_guard import guarded_thread


class PresenterMixin:
    def _presenter_busy(self):
        worker = getattr(self, "_presenter_worker", None)
        return bool(worker and worker.is_alive())

    def _presenter_selection(self, value):
        if isinstance(value, dict) and value.get("enabled") and value.get("use_saved"):
            value = self.presenters.defaults()
            if not value.get("enabled"):
                raise ValueError("บันทึกการตั้งค่าผู้บรรยายก่อนเริ่มงาน")
        selection = presenter_settings(value)
        if selection["enabled"]:
            self.presenters.assets(selection)
        return selection

    def _presenter_status(self):
        """Small immutable UI snapshot; polling never submits a provider action."""
        progress = dict(getattr(self, "_presenter_progress", {}) or {})
        ident = progress.get("id")
        if not ident:
            return {"active": False}
        try:
            job = self.presenters.get(ident)
        except (OSError, ValueError):
            return {"active": False}
        active = self._presenter_busy()
        progress.update(active=active, job_id=ident, name=job["name"], status=job["status"],
                        clips=len(job["clips"]), image_ready=bool(job.get("image")),
                        elapsed=max(0, int((time.time() if active else progress.get("updated_at", time.time())) - progress.get("started_at", time.time()))))
        return progress

    def _presenter_action(self, action, payload):
        if action == "presenter_library_state":
            if payload.get("confirmed") is not True:
                raise ValueError("กรุณายืนยันการจัดการตัวละคร")
            if self._presenter_busy():
                raise ValueError("รอการสร้างตัวละครเสร็จก่อนจัดการคลัง")
            return {"ok": True, "job": self.presenters.set_library_state(
                str(payload.get("id") or ""), str(payload.get("state") or ""))}
        if action == "presenter_save_settings":
            return {"ok": True, "settings": self.presenters.save_defaults(payload.get("settings"))}
        if action == "presenter_focus":
            job = self.presenters.get(str(payload.get("id") or ""))
            progress = getattr(self, "_presenter_progress", {})
            if progress.get("id") != job["id"]:
                raise ValueError("สถานะหน้าต่างไม่ตรงกับงานปัจจุบัน")
            service = str(progress.get("service") or "ai")
            if service == "flow":
                missing = next((i for i in range(1, 4) if str(i) not in job["clips"]), 3)
                self.bridge.queue_extension_command("focus_flow_web", job["id"], missing,
                    run_id=job["intents"].get(f"flow_{missing}", job["run_id"]))
            else:
                self.bridge.queue_extension_command("focus_ai_web", job["id"],
                    provider_hint=job["image_ai_provider"], run_id=job["run_id"])
            self._activate_or_launch_chrome("https://flow.google.com/" if service == "flow" else self._ai_web_url(job["image_ai_provider"]))
            return {"ok": True}
        if action == "presenter_state":
            jobs = self.presenters.list_jobs()
            for job in jobs:
                if job["status"] == "running" and not self._presenter_busy():
                    job.update(status="interrupted", error="งานหยุดก่อนจบ • กดทำต่อเพื่อตรวจ Checkpoint เดิม ไม่ส่งซ้ำ")
            return {"ok": True, "jobs": jobs, "active": self._presenter_busy(),
                    "progress": self._presenter_status(), "defaults": self.presenters.defaults_state(), "ui_version": 2}
        if action == "presenter_cancel":
            if self._presenter_busy():
                self._presenter_cancel.set()
                self._presenter_progress = {**self._presenter_progress, "stage": "cancelling", "message": "กำลังหยุดงาน • เก็บคลิปที่เสร็จแล้ว"}
                ident = self._presenter_progress.get("id", "")
                if ident:
                    job = self.presenters.get(ident)
                    self.presenters.update(ident, status="cancelled", error="ผู้ใช้ยกเลิก • เก็บคลิปที่เสร็จแล้ว")
                    self.bridge.cancel_presenter_pending_commands(ident)
                    self.bridge.queue_extension_command("cancel_story_chatgpt", ident, run_id=job["run_id"])
                    stop_commands = []
                    for index in range(1, 4):
                        if f"flow_{index}" in job["intents"] and str(index) not in job["clips"]:
                            command = self.bridge.queue_extension_command("stop_flow_generation", ident, index,
                                run_id=job["intents"][f"flow_{index}"], preserve_checkpoint=True)
                            stop_commands.append(command["id"])
                    if stop_commands:
                        self.presenters.update(ident, pending_stop_commands=stop_commands, stop_receipt_recovery_count=0)
            return {"ok": True}
        if action == "presenter_open_folder":
            self._open_folder(self.presenters.folder(str(payload.get("id") or "")))
            return {"ok": True}
        owned = {str(payload.get("id") or "")} if action in {"presenter_run", "presenter_approve"} else set()
        reason = self._creation_idle_reason(ignore_remote_jobs=owned)
        if reason:
            raise ValueError("มีงานกำลังใช้ระบบอัตโนมัติ • " + reason)
        if action == "presenter_create":
            from core.flow_settings import snapshot_flow
            selected_flow = snapshot_flow(payload, getattr(self, "cfg", {}).get("flow_defaults"))
            reference = self._resolve_desktop_reference_image(payload.get("reference"))
            job = self.presenters.create(payload.get("name", ""), payload.get("description", ""),
                payload.get("provider", "chatgpt"), payload.get("style", "realistic"), payload.get("screen", "green"),
                reference, payload.get("consent") is True, payload.get("review") is True)
            job = self.presenters.update(job["id"], flow_settings=selected_flow)
            return {"ok": True, "job": job}
        if action in {"presenter_run", "presenter_approve"}:
            ident = str(payload.get("id") or ""); job = self.presenters.get(ident)
            if job.get("library_state") == "trash":
                raise ValueError("กู้คืนตัวละครจากถังขยะก่อนทำต่อ")
            if job["status"] == "ready": return {"ok": True, "job": job}
            stop_receipts = [self.bridge.extension_command_status(command_id)
                             for command_id in job.get("pending_stop_commands", [])]
            if any(not receipt for receipt in stop_receipts):
                # Bridge commands are in-memory. A backend restart can lose
                # the ACK while the preserved, local-only pause completed.
                # Re-issue that idempotent pause once, never a Generate/Stop
                # provider gesture; persist its budget before dispatch.
                if int(job.get("stop_receipt_recovery_count") or 0) >= 1:
                    raise ValueError("ยังไม่พบใบยืนยันหยุด Flow หลังตรวจซ้ำหนึ่งครั้ง • ต้องตรวจโปรเจกต์เดิม ไม่เริ่มหรือส่งสร้างซ้ำ")
                targets = [(index, job["intents"][f"flow_{index}"]) for index in range(1, 4)
                           if f"flow_{index}" in job["intents"] and str(index) not in job["clips"]]
                if not targets:
                    raise ValueError("ไม่พบรอบ Flow เดิมสำหรับยืนยันหยุด • ต้องตรวจ Checkpoint ก่อนทำต่อ")
                self.presenters.update(ident, stop_receipt_recovery_count=1)
                replacement_ids = []
                for index, flow_run in targets:
                    command = self.bridge.queue_extension_command("stop_flow_generation", ident, index,
                        run_id=flow_run, preserve_checkpoint=True)
                    replacement_ids.append(command["id"])
                    self.presenters.update(ident, pending_stop_commands=replacement_ids)
                raise ValueError("เปิดโปรแกรมใหม่แล้ว • กำลังยืนยันพัก Flow รอบเดิมอีกหนึ่งครั้งโดยไม่กดหยุดเว็บหรือสร้างซ้ำ • รอแล้วกดทำต่อ")
            for receipt in stop_receipts:
                if receipt.get("status") != "completed":
                    raise ValueError("คำสั่งหยุด Flow รอบก่อนยังไม่ยืนยัน • รอให้หยุดเรียบร้อยก่อนกดทำต่อ ไม่ส่งสร้างซ้ำ")
            if job.get("pending_stop_commands"):
                self.presenters.update(ident, pending_stop_commands=[])
            if job["status"] in {"image_review", "clip_review"}:
                if action != "presenter_approve" or payload.get("confirmed") is not True:
                    raise ValueError("ตรวจภาพ/คลิปและกดยืนยันก่อนทำต่อ")
            if not job["image"] and job["intents"].get("image"):
                raise ValueError("ภาพนี้ส่งแล้วแต่ยังไม่บันทึก • ต้องตรวจเว็บ ไม่ส่งซ้ำโดยอัตโนมัติ")
            extension, compatible = self._compatible_extension()
            if extension.get("connected") and not compatible:
                raise ValueError(f"กรุณาเปิด Chrome และโหลด SmartFlow Extension {self.bridge.REQUIRED_EXTENSION_VERSION}")
            if not compatible:
                self._activate_or_launch_chrome(self._ai_web_url(job["image_ai_provider"]))
            run_id = "RUN-" + uuid.uuid4().hex[:12].upper()
            self.presenters.update(ident, run_id=run_id, status="running", error="")
            self._presenter_cancel = threading.Event()
            notice_cancel_event = self._presenter_cancel
            started = time.time()
            def notify(stage, message):
                old = getattr(self, "_presenter_progress", {})
                service = "flow" if stage.startswith("flow_") else old.get("service", "ai")
                if stage == "image": service = "ai"
                self._presenter_progress = {"id": ident, "run_id": run_id, "stage": stage,
                    "message": message, "service": service, "started_at": started, "updated_at": time.time()}
                self.events.put(("presenter_trace", f"{ident} • {stage} • {message}"))
                self.bridge._record_extension_trace({"job_id": ident, "run_id": run_id,
                    "service": "presenter", "action": stage, "message": message})
            def work():
                try:
                    if not compatible:
                        notify("connecting", "เปิด Chrome แล้ว • รอ Extension รุ่นที่ตรงกัน ไม่เปิดซ้ำ")
                        for _ in range(60):
                            if self._presenter_cancel.wait(1):
                                raise OperationCancelled("ยกเลิกระหว่างรอ Chrome")
                            if self._compatible_extension()[1]: break
                        else:
                            raise RuntimeError(f"ยังไม่พบ Extension {self.bridge.REQUIRED_EXTENSION_VERSION} • เก็บงานไว้ ยังไม่ส่งสร้าง")
                    PresenterPipeline(self.presenters, self.bridge, notify, self._wait_download, self._presenter_cancel).run(ident, run_id)
                except OperationCancelled:
                    self.presenters.update(ident, status="cancelled", error="ผู้ใช้ยกเลิก • เก็บ Checkpoint")
                    notify("cancelled", "ยกเลิกแล้ว • เก็บไฟล์ที่เสร็จไว้")
                except Exception as exc:
                    self.presenters.update(ident, status="error", error=str(exc))
                    notify("error", str(exc))
                    failure_client = getattr(exc, "flow_failure_client", None)
                    if failure_client:
                        self._queue_flow_failure_notice(ident, failure_client.get("flow_shot_index"),
                            failure_client, notice_cancel_event, presenter_run_id=run_id)
            self._presenter_progress = {"id": ident, "run_id": run_id, "stage": "starting", "message": "เริ่มงานตัวละคร", "started_at": started, "updated_at": started}
            self._presenter_worker = guarded_thread(self, '', work, references=job, daemon=True, name="SmartFlowPresenter")
            return {"ok": True, "id": ident}
        raise ValueError("ไม่พบคำสั่งตัวละคร")

    def _presenter_media(self, item_id):
        _, ident, kind = item_id.split(":", 2)
        job = self.presenters.get(ident); folder = self.presenters.folder(ident).resolve()
        relative = job.get("image") if kind == "image" else (job["clips"].get(kind) or {}).get("path")
        if kind == "export": relative = "exports/presenter_green_screen.mp4"
        path = (folder / str(relative or "")).resolve()
        if folder not in path.parents or not path.is_file(): raise ValueError("ไม่พบไฟล์ตัวละคร")
        return str(path)
