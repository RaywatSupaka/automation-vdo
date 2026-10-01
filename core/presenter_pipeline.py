"""One owned Presenter run. Browser gestures remain in the SmartFlow Extension."""
import time
from pathlib import Path
from core.cancellable_process import check_cancelled
from core.presenter import PresenterRenderer


class PresenterPipeline:
    def __init__(self, manager, bridge, notify, download, cancel_event):
        self.manager, self.bridge, self.notify = manager, bridge, notify
        self.download, self.cancel = download, cancel_event

    def _queue_flow(self, action, ident, shot, run_id):
        check_cancelled(self.cancel)
        # UI progress is disposable; the Extension's project/submit receipts
        # are not. Clear only this shot's old display state before dispatch.
        self.bridge.clear_flow_progress(ident, shot)
        return self.bridge.queue_extension_command(action, ident, shot, run_id=run_id)

    def wait(self, ident, scope, run_id, predicate, timeout=1800, shot=0, command=None):
        started = time.monotonic()
        deadline = started + timeout; previous = None; offline_since = None; approval_sent = False
        command_id = str(command.get("id") or "") if isinstance(command, dict) else ""
        inspect_id = command_id if isinstance(command, dict) and command.get("action") == "inspect_flow" else ""
        inspection_seen = not inspect_id
        acknowledged_at = None
        unknown_since = None
        while time.monotonic() < deadline:
            check_cancelled(self.cancel)
            state = self.bridge.extension_status()
            clients = [c for c in state.get("clients", []) if c.get("version") == self.bridge.REQUIRED_EXTENSION_VERSION]
            matching = next((c for c in clients if c.get(f"{scope}_job_id") == ident
                             and c.get(f"{scope}_run_id") == run_id
                             and (scope != "flow" or int(c.get("flow_shot_index") or 0) == shot)), None)
            if not clients:
                offline_since = offline_since or time.monotonic()
                if time.monotonic() - offline_since > 60:
                    raise RuntimeError("Extension หลุด • เก็บจุดค้าง ไม่ส่งสร้างซ้ำ")
            else:
                offline_since = None
            command_ready = not command_id
            if command_id:
                receipt = self.bridge.extension_command_status(command_id)
                status = str((receipt or {}).get("status") or "")
                if status in {"failed", "cancelled"}:
                    raise RuntimeError(str(receipt.get("error") or "คำสั่งตรวจ/ทำต่อ Flow ไม่สำเร็จ")
                                       + " • เก็บโปรเจกต์เดิม ไม่ส่งสร้างซ้ำ")
                command_ready = status == "completed"
                if command_ready and acknowledged_at is None:
                    acknowledged_at = time.monotonic()
                if not command_ready and time.monotonic() - started >= 120:
                    raise RuntimeError("ยังไม่ยืนยันว่าคำสั่ง Flow ทำงานแล้ว • เก็บโปรเจกต์เดิม ไม่ส่งคำสั่งซ้ำ")
            if matching and command_ready and not inspection_seen:
                inspection_seen = str(matching.get("flow_inspection_command_id") or "") == inspect_id
            if inspect_id and acknowledged_at is not None and not inspection_seen and time.monotonic() - acknowledged_at >= 60:
                raise RuntimeError("คำสั่งตรวจ Flow ทำงานแล้วแต่ยังไม่มีผลตรวจของรอบนี้ • เก็บโปรเจกต์เดิม ไม่ส่งสร้างซ้ำ")
            if not command_ready or not inspection_seen:
                if self.cancel.wait(1): check_cancelled(self.cancel)
                continue
            if matching:
                step = str(matching.get(f"{scope}_step") or "")
                message = str(matching.get(f"{scope}_message") or step)
                if (step, message) != previous:
                    self.notify(step, message); previous = (step, message)
                if predicate(matching):
                    return matching
                if scope == "flow" and step == "awaiting_credit_approval" and not approval_sent:
                    approval_sent = True
                    self.notify("approving", "อนุมัติการสร้างคลิปนี้หนึ่งครั้ง • ไม่ส่งพรอมต์ซ้ำ")
                    self.bridge.queue_extension_command("approve_flow_credit", ident, shot, run_id=run_id)
                if step in {"error", "cancelled", "generation_failed", "attachment_failed", "credit_exhausted",
                            "checkpoint_missing", "checkpoint_mismatch", "wrong_output_type", "project_open_failed",
                            "attachment_terminal", "submission_blocked", "image_upload_missing"}:
                    reason = str(matching.get("flow_failure_reason") or "").strip() if scope == "flow" else ""
                    failure = RuntimeError((f"สาเหตุ: {reason}" if reason else message) + " • เก็บจุดค้าง ไม่สร้างหรือแนบซ้ำ")
                    if scope == "flow" and matching.get("flow_failure_code") == "FLOW_POLICY_BLOCKED":
                        failure.flow_failure_client = dict(matching)
                    raise failure
                if scope == "flow" and step == "generation_status_unknown":
                    unknown_since = unknown_since or time.monotonic()
                    if time.monotonic() - unknown_since >= 90:
                        raise RuntimeError("Flow ยังไม่ยืนยันการสร้างหรือผลลัพธ์ของโปรเจกต์เดิม • หยุดตรวจโดยไม่ส่งซ้ำ")
                else:
                    unknown_since = None
                if step == "user_action_required":
                    deadline += 1
            if self.cancel.wait(1): check_cancelled(self.cancel)
        raise TimeoutError("รอผลตัวละครนานเกินกำหนด • เก็บสถานะเดิม ไม่ส่งซ้ำ")

    def run(self, ident, run_id):
        job = self.manager.get(ident)
        if not job.get("image"):
            if job["intents"].get("image"):
                raise RuntimeError("ส่งภาพตัวละครแล้วแต่ยังไม่บันทึก • ตรวจเว็บก่อน ห้ามเริ่มสร้างซ้ำ")
            self.notify("image", "ส่งภาพตัวละครเข้า AI Web หนึ่งครั้ง")
            self.bridge.queue_extension_command("open_chatgpt", ident, provider_hint=job["image_ai_provider"], run_id=run_id)
            self.wait(ident, "ai", run_id, lambda c: bool(self.manager.get(ident).get("image")), timeout=1200)
        job = self.manager.get(ident)
        if job["status"] == "image_review":
            self.notify("image_review", "ภาพหลักพร้อม • ตรวจภาพและยืนยันก่อนทำคลิป"); return
        for index in range(1, 4):
            check_cancelled(self.cancel); job = self.manager.get(ident)
            if str(index) in job["clips"]:
                if not (self.manager.folder(ident) / job["clips"][str(index)]["path"]).is_file():
                    raise RuntimeError("ไฟล์คลิปที่บันทึกไว้หาย ไม่ส่งสร้างซ้ำ")
                continue
            key = f"flow_{index}"
            flow_run = str(job["intents"].get(key) or run_id)
            if key not in job["intents"]:
                intents = {**job["intents"], key: flow_run}
                self.manager.update(ident, intents=intents, stage=key)
                command = self._queue_flow("open_flow", ident, index, flow_run)
            else:
                # Rebind the same run/project only. Missing remote state stops;
                # a restart is never permission to generate another paid take.
                command = self._queue_flow("inspect_flow", ident, index, flow_run)
            self.notify(key, f"กำลังทำคลิปผู้บรรยาย {index}/3")
            result = self.wait(ident, "flow", flow_run,
                lambda c: c.get("flow_step") == "generation_complete"
                or (isinstance(command, dict) and command.get("action") == "inspect_flow"
                    and c.get("flow_step") == "checkpoint_preparing"), shot=index, command=command)
            if isinstance(result, dict) and result.get("flow_step") == "checkpoint_preparing":
                # Only the owned inspection can prove a durable pre-submit
                # checkpoint. Image/prompt flags or missing receipts alone
                # are never permission to make another paid request.
                if str(result.get("flow_inspection_command_id") or "") != str(command.get("id") or ""):
                    raise RuntimeError("ผลตรวจ Flow ไม่ตรงคำสั่งรอบนี้ • ไม่ส่งสร้างซ้ำ")
                self.notify(key, f"ตรวจพบจุดเตรียมเดิมที่ยังไม่ส่ง • ทำคลิปผู้บรรยาย {index}/3 ต่อในโปรเจกต์เดิม")
                resumed = self._queue_flow("resume_flow_workspace", ident, index, flow_run)
                self.wait(ident, "flow", flow_run, lambda c: c.get("flow_step") == "generation_complete",
                          shot=index, command=resumed)
            started = time.time()
            self.notify("downloading", f"กำลังดาวน์โหลดคลิปผู้บรรยาย {index}/3 • รอไฟล์จริงก่อนทำต่อ")
            self.bridge.queue_extension_command("download_flow_result", ident, index, run_id=flow_run)
            path = self.download(ident, index, cancel_event=self.cancel, started_at=started, total_shots=3)
            check_cancelled(self.cancel)
            saved = self.manager.save_clip(ident, index, path, run_id)
            self.notify("downloaded", f"บันทึกคลิปผู้บรรยาย {index}/3 แล้ว")
            if saved["status"] == "clip_review":
                self.notify("clip_review", saved["error"]); return
        job = self.manager.get(ident)
        clips = [self.manager.folder(ident) / job["clips"][str(i)]["path"] for i in range(1, 4)]
        self.notify("joining", "รวมคลิปผู้บรรยาย • ตัดเสียง Flow ออก ไม่เรียก API เสียง")
        PresenterRenderer(self.manager.ffmpeg_path).join(clips, self.manager.folder(ident) / "exports/presenter_green_screen.mp4", self.cancel, job["screen"])
        check_cancelled(self.cancel)
        self.manager.update(ident, status="ready", stage="ready", error="", lip_sync=False)
        self.notify("ready", "ตัวละครพร้อม 3 คลิป • ใช้ซ้ำได้ ไม่ซิงก์ปากกับเสียง")
