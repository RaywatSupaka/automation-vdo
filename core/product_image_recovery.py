"""One durable Product image budget shared by desktop and extension.

The ledger is intentionally independent of transport retries. An unresolved
reservation remains unresolved after restart; it is never permission to resend.
"""
import hashlib
import json
import re
import uuid
from pathlib import Path
from core.atomic_json import AtomicJsonFile
from PIL import Image


def _digest(path):
    with Image.open(path) as image:
        image.verify()
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pixels(image):
    rgba = image.convert('RGBA')
    return hashlib.sha256(f'{rgba.width}x{rgba.height}:'.encode() + rgba.tobytes()).hexdigest()


class ProductImageRecovery:
    def __init__(self, manager, job_id):
        if not re.fullmatch(r"JOB-[A-Za-z0-9-]+", str(job_id)):
            raise ValueError("Product Job ID ไม่ถูกต้อง")
        self.manager, self.job_id = manager, str(job_id)
        self.folder = (Path(manager.root) / self.job_id).resolve()
        self.store = AtomicJsonFile(self.folder / "prompts" / "image_recovery.json")

    def state(self):
        return self.store.read(default={})

    def _job(self):
        job = self.manager.get_job(self.job_id)
        if job.get("automation_status") == "cancelled" or job.get("status") == "cancelled":
            raise ValueError("ยกเลิกงานแล้ว • ไม่อนุญาตสร้างภาพต่อ")
        return job

    def _file(self, index):
        return self.folder / "generated" / f"selling_image_{index:02d}.png"

    def start(self, analysis):
        job = self._job()
        prompts = analysis.get("image_prompts") if isinstance(analysis, dict) else None
        if not isinstance(prompts, list) or len(prompts) != 3 or not all(isinstance(p, str) and p.strip() for p in prompts):
            raise ValueError("ต้องมีแผนภาพสินค้า 3 ภาพ")
        for field in ('flow_shot_prompts', 'spoken_script_segments'):
            values = analysis.get(field)
            if values is None:
                continue
            if not isinstance(values, list) or len(values) != len(prompts):
                raise ValueError(f'{field} ต้องจับคู่กับภาพครบ 3 ฉาก')
            for index, value in enumerate(values, 1):
                if isinstance(value, dict) and 'scene_index' in value and (
                        type(value['scene_index']) is not int or value['scene_index'] != index):
                    raise ValueError(f'{field} scene_index ไม่ตรงภาพฉาก {index}')
        if len(json.dumps(analysis)) > 250000:
            raise ValueError("ผลวิเคราะห์ใหญ่เกินไป")
        sources = job.get("ai_reference_images", job.get("source_images") or [])
        fingerprints = []
        for relative in sources:
            path = (self.folder / relative).resolve()
            if self.folder not in path.parents:
                raise ValueError("ภาพอ้างอิงอยู่นอกงาน")
            fingerprints.append([relative, _digest(path)])
        if not fingerprints:
            raise ValueError("SOURCE_IMAGES_NEED_REVIEW • ไม่มีภาพสินค้าที่เหมาะสมให้ใช้อ้างอิง")
        revision = hashlib.sha256(json.dumps([prompts, fingerprints], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        def update(state):
            if state:
                if state.get("revision") != revision:
                    raise ValueError("AI_IMAGE_REVISION_CHANGED • ชุดภาพหรือแผนเปลี่ยน ต้องตรวจงานเดิมก่อน ไม่เริ่มงบใหม่")
                return state
            slots = {}
            for index in range(1, 4):
                path = self._file(index)
                slot = {"attempts": 0, "status": "missing", "donor_index": 0}
                # Upgrade existing durable checkpoints, never arbitrary images
                # scraped from the conversation (which have no reliable slot).
                relative = str(path.relative_to(self.folder)).replace("\\", "/")
                existing = list(job.get("partial_generated_images") or []) + list(job.get("generated_images") or [])
                if relative in [str(p).replace("\\", "/") for p in existing] and path.is_file():
                    slot.update(status="succeeded", attempts=1, sha256=_digest(path), origin="existing_checkpoint")
                    with Image.open(path) as image:
                        slot['pixel_sha256'] = _pixels(image)
                slots[str(index)] = slot
            clean_analysis = {key: value for key, value in analysis.items()
                              if key in {"cover", "job_id", "caption_short", "hashtags", "image_prompts", "video_prompt",
                                         "flow_gui_design", "flow_shot_prompts", "spoken_script", "spoken_script_short",
                                         "spoken_script_segments", "pronunciation_notes", "warnings", "editing_overlay_plan"}}
            return {"schema_version": 1, "job_id": self.job_id, "revision": revision,
                    "analysis": clean_analysis, "sources": fingerprints, "slots": slots}
        return self.store.update(update, default={})

    def reserve(self, revision, index, run_id, request_id, donor_index=0):
        self._job()
        if not run_id or not request_id or len(str(run_id)) > 100 or len(str(request_id)) > 100:
            raise ValueError("ไม่พบรหัสรอบส่งภาพ")
        index, donor_index = int(index), int(donor_index)
        reply = {}
        def update(state):
            if state.get("revision") != revision or str(index) not in state.get("slots", {}):
                raise ValueError("AI_IMAGE_REVISION_CHANGED • ไม่ตรงชุดภาพปัจจุบัน")
            if any(s.get("status") not in {"missing", "failed", "succeeded"} for s in state["slots"].values()):
                raise ValueError("AI_IMAGE_RECOVERY_STOP • มีรอบภาพค้างหรือถูกหยุด ต้องตรวจสอบก่อน")
            slot = state["slots"][str(index)]
            if slot.get("status") not in {"missing", "failed"} or slot.get("attempts", 0) >= 2:
                raise ValueError("AI_IMAGE_RECOVERY_STOP • ภาพนี้มีผลค้าง/จบแล้ว หรือใช้สิทธิ์กู้ครบ ห้ามส่งซ้ำ")
            if slot["attempts"]:
                donor = state["slots"].get(str(donor_index), {})
                if donor_index == index or donor.get("status") != "succeeded" or donor.get("donor_index"):
                    raise ValueError("AI_IMAGE_RECOVERY_STOP • ไม่มีภาพสำเร็จรอบแรกที่ใช้กู้ได้")
                if _digest(self._file(donor_index)) != donor.get("sha256"):
                    raise ValueError("AI_IMAGE_RECOVERY_STOP • ภาพอ้างอิงเปลี่ยนหรือเสียหาย")
            elif donor_index:
                raise ValueError("ห้ามใช้ donor ในรอบแรก")
            # Persist before browser dispatch. A lost HTTP response cannot
            # obtain the same permission again using the same request id.
            slot.update(attempts=slot["attempts"] + 1, status="reserved", run_id=str(run_id),
                        request_id=str(request_id), token=uuid.uuid4().hex, donor_index=donor_index)
            reply.update(token=slot["token"], attempt=slot["attempts"], donor_index=donor_index)
            return state
        self.store.update(update)
        return reply

    def finish(self, revision, index, run_id, token, outcome, image=None, reason=""):
        self._job()
        index = int(index)
        allowed = {"failed", "policy_blocked", "uncertain", "download_pending", "succeeded", "blocked"}
        if outcome not in allowed:
            raise ValueError("สถานะภาพไม่ถูกต้อง")
        def update(state):
            slot = state.get("slots", {}).get(str(index), {})
            if state.get("revision") != revision or slot.get("token") != token or slot.get("run_id") != run_id:
                raise ValueError("AI_IMAGE_RECOVERY_STOP • ผลภาพไม่ตรงเจ้าของรอบ")
            if slot.get("status") == outcome and outcome != "succeeded":
                return state
            if slot.get("status") == "succeeded":
                return state  # Duplicate completion never overwrites a file.
            if slot.get("status") != "reserved":
                raise ValueError("AI_IMAGE_RECOVERY_STOP • รอบภาพจบแล้ว")
            if outcome == "succeeded":
                import base64
                import io
                payload = base64.b64decode(str(image or "").split(",")[-1], validate=True)
                if len(payload) > 20 * 1024 * 1024:
                    raise ValueError("ภาพเกิน 20 MB")
                with Image.open(io.BytesIO(payload)) as decoded:
                    decoded.load()
                    width, height = decoded.size
                    pixel_sha = _pixels(decoded)
                    sha = hashlib.sha256(payload).hexdigest()
                    previous_pixels = [row.get('pixel_sha256') for row in slot.get('candidate_images', [])]
                    slot.setdefault('candidate_images', []).append({'sha256': sha, 'pixel_sha256': pixel_sha,
                        'request_id': slot.get('request_id'), 'attempt': slot.get('attempts'), 'width': width, 'height': height})
                    if width < 256 or height < 400 or not .45 <= width / height <= .72:
                        slot.update(status="failed", reason="invalid_image_dimensions")
                        return state
                if slot.get('prompt_repair', {}).get('contract_version', 1) >= 2:
                    source_pixels = []
                    for relative, digest in state['sources']:
                        path = (self.folder / relative).resolve()
                        if self.folder not in path.parents or _digest(path) != digest:
                            raise ValueError('AI_IMAGE_REVISION_CHANGED • ภาพอ้างอิงเปลี่ยน')
                        with Image.open(path) as source:
                            source_pixels.append(_pixels(source))
                    if pixel_sha in previous_pixels + source_pixels:
                        slot.update(status='failed', reason='redesign_reused_image')
                        return state
                if any(other.get("sha256") == sha or other.get("pixel_sha256") == pixel_sha
                       for key, other in state["slots"].items() if key != str(index)):
                    slot.update(status="failed", reason="duplicate_image")
                    return state
                self.manager.save_partial_image(self.job_id, index, image)
                slot.update(sha256=sha, pixel_sha256=pixel_sha, origin="recovered_from_reference" if slot["donor_index"] else "generated")
            slot["status"] = outcome
            if outcome != "succeeded":
                slot["reason"] = str(reason or outcome)[:1500]
            return state
        return self.store.update(update)

    def prompt_repair(self, operation, revision, index, run_id, request_id="", candidate=None, contract_version=1):
        """Distinct, durable approval for a new compliant composition, not a retry bypass.

        Service failures may obtain successive proposals. A content refusal may
        obtain ONE genuinely different compliant proposal per slot; another
        refusal requires human review. Unknown sends never enter this path.
        """
        self._job()
        if not isinstance(run_id, str) or not run_id or len(run_id) > 100:
            raise ValueError("ไม่พบรหัสรอบงาน")
        index = str(int(index))
        reply = {}
        def update(state):
            slot = state.get("slots", {}).get(index, {})
            if state.get("revision") != revision or not slot:
                raise ValueError("AI_IMAGE_REVISION_CHANGED • ชุดภาพเปลี่ยน")
            if slot.get("status") not in {"failed", "policy_blocked"}:
                raise ValueError("AI_IMAGE_RECOVERY_STOP • ต้องยืนยันว่ารอบก่อนล้มเหลวก่อน")
            if any(s.get("status") not in {"missing", "failed", "policy_blocked", "succeeded"}
                   for s in state["slots"].values()):
                raise ValueError("AI_IMAGE_RECOVERY_STOP • มีผลภาพค้าง ไม่ส่งทับ")
            for relative, digest in state["sources"]:
                path = (self.folder / relative).resolve()
                if self.folder not in path.parents or _digest(path) != digest:
                    raise ValueError("AI_IMAGE_REVISION_CHANGED • ภาพอ้างอิงเปลี่ยน")
            repair = slot.get("prompt_repair")
            if operation == "prepare_repair":
                if repair and repair.get("failure_token") == slot.get("token"):
                    reply.update(repair=repair)
                    return state  # Lost ACK/restart adopts the exact helper, never a new tab.
                if repair and repair.get("phase") != "submitted":
                    raise ValueError("AI_IMAGE_RECOVERY_STOP • ต้องตรวจคำตอบช่วยแก้เดิม")
                if slot["status"] == "policy_blocked" and slot.get("policy_redesign_used"):
                    raise ValueError("AI_IMAGE_POLICY_REVIEW • ภาพทางเลือกยังถูกปฏิเสธ ต้องตรวจเนื้อหา ไม่วนหลบข้อกำหนด")
                if repair:
                    slot.setdefault("prompt_repair_history", []).append(repair)
                repair = {"request_id": uuid.uuid4().hex, "failure_token": slot.get("token"),
                          "contract_version": 2 if contract_version == 2 else 1,
                          "phase": "prepared", "round": len(slot.get("prompt_repair_history", [])) + 1,
                          "reason": slot.get("reason", slot["status"]), "failure_status": slot["status"],
                          "original_prompt": state["analysis"]["image_prompts"][int(index)-1],
                          "previous_prompt": slot.get("effective_prompt", state["analysis"]["image_prompts"][int(index)-1]),
                          "prepared_run_id": run_id}
                slot["prompt_repair"] = repair
                if slot["status"] == "policy_blocked":
                    slot["policy_redesign_used"] = True
                reply.update(repair=repair)
                return state
            if not repair or repair.get("request_id") != request_id or repair.get("failure_token") != slot.get("token"):
                raise ValueError("AI_IMAGE_RECOVERY_STOP • คำตอบช่วยแก้ไม่ตรงภาพรอบที่ล้มเหลว")
            if operation == "claim_repair_helper":
                if repair["phase"] != "prepared":
                    raise ValueError("AI_IMAGE_RECOVERY_STOP • แท็บช่วยงานถูกจองแล้ว อ่านผลเดิมก่อน")
                repair["phase"] = "helper_claimed"
                reply.update(repair=repair)
            elif operation == "approve_repair":
                fields = ['prompt', 'needs_review', 'reference_compatible', 'material_change', 'change_summary']
                if repair.get('contract_version', 1) >= 2:
                    fields += ['visual_concept', 'visual_changes', 'substantive_redesign', 'product_facts_preserved']
                clean_candidate = {k: candidate.get(k) for k in fields} if isinstance(candidate, dict) else {}
                if repair["phase"] == "approved" and repair.get("candidate") == clean_candidate:
                    reply.update(repair=repair)
                    return state
                if repair["phase"] != "helper_claimed":
                    raise ValueError("AI_IMAGE_RECOVERY_STOP • คำตอบช่วยแก้จบแล้ว")
                valid = (isinstance(candidate, dict)
                         and candidate.get("needs_review") is False
                         and candidate.get("reference_compatible") is True
                         and candidate.get("material_change") is False
                         and isinstance(candidate.get("prompt"), str)
                         and 20 <= len(candidate["prompt"].strip()) <= 20000
                         and isinstance(candidate.get("change_summary"), str)
                         and bool(candidate["change_summary"].strip()))
                if valid:
                    normalized = lambda text: " ".join(text.split()).casefold()
                    previous = [repair["original_prompt"], repair["previous_prompt"]]
                    previous += [r.get("candidate", {}).get("prompt", "") for r in slot.get("prompt_repair_history", [])]
                    valid = normalized(candidate["prompt"]) not in [normalized(p) for p in previous]
                    if re.search(r"ignore (?:all |the )?(?:previous|policy|safety)|bypass|evade|หลบ(?:เลี่ยง)?(?:นโยบาย|ตัวกรอง)|ข้าม(?:นโยบาย|ข้อกำหนด)", candidate["prompt"], re.I):
                        valid = False
                    if repair.get('contract_version', 1) >= 2:
                        concept = candidate.get('visual_concept')
                        changes = candidate.get('visual_changes')
                        valid = (valid and candidate.get('substantive_redesign') is True
                                 and candidate.get('product_facts_preserved') is True
                                 and isinstance(concept, str) and 20 <= len(concept.strip()) <= 2000
                                 and isinstance(changes, list) and 2 <= len(changes) <= 6
                                 and all(isinstance(c, str) and 10 <= len(c.strip()) <= 500 for c in changes)
                                 and len(set(normalized(c) for c in changes)) == len(changes))
                        if valid:
                            prior = [r.get('candidate', {}).get('visual_concept', '') for r in slot.get('prompt_repair_history', [])]
                            valid = normalized(concept) not in [normalized(c) for c in prior]
                repair["phase"] = "approved" if valid else "needs_review"
                # Only these typed fields are consumed; no helper tool instructions.
                repair["candidate"] = clean_candidate
                reply.update(repair=repair)
            elif operation == "reserve_repaired":
                if repair["phase"] != "approved":
                    raise ValueError("AI_IMAGE_RECOVERY_STOP • AI ยังไม่ได้เสนอภาพทางเลือกที่พร้อมใช้งาน")
                slot.setdefault("attempt_history", []).append({k: slot.get(k) for k in (
                    "attempts", "status", "run_id", "request_id", "token", "donor_index", "reason", "effective_prompt")})
                slot.update(attempts=slot["attempts"] + 1, status="reserved", run_id=run_id,
                            request_id=request_id, token=uuid.uuid4().hex, donor_index=0,
                            effective_prompt=repair["candidate"]["prompt"].strip())
                repair.update(phase="submitted", submitted_run_id=run_id)
                reply.update(token=slot["token"], attempt=slot["attempts"], prompt=slot["effective_prompt"])
            else:
                raise ValueError("คำสั่งช่วยแก้ภาพไม่ถูกต้อง")
            return state
        self.store.update(update)
        return reply

    def validate_result(self, result):
        """A final callback cannot replace a reserved/failed or approved slot."""
        self._job()
        state = self.state()
        if not state:
            return {}  # Legacy jobs retain their existing result contract.
        import base64
        images = result.get("generated_images") or []
        effective_prompts = [state["slots"][str(i)].get("effective_prompt", state["analysis"]["image_prompts"][i-1]) for i in range(1, 4)]
        if len(images) != 3 or result.get("image_prompts") != effective_prompts:
            raise ValueError("AI_IMAGE_RECOVERY_STOP • ผลภาพไม่ตรงแผนที่บันทึกไว้")
        origins = {}
        for index, image in enumerate(images, 1):
            slot = state["slots"][str(index)]
            if slot.get("status") != "succeeded" or not isinstance(image, str):
                raise ValueError("AI_IMAGE_RECOVERY_STOP • ยังมีช่องภาพไม่สำเร็จ ห้ามส่งต่อ Flow")
            sha = hashlib.sha256(base64.b64decode(image.split(',')[-1], validate=True)).hexdigest()
            if sha != slot.get("sha256") or _digest(self._file(index)) != sha:
                raise ValueError("AI_IMAGE_RECOVERY_STOP • ไฟล์ภาพไม่ตรง Checkpoint")
            origins[str(index)] = {"origin": slot["origin"], "donor_index": slot.get("donor_index", 0),
                                   "path": f"generated/selling_image_{index:02d}.png", "sha256": sha}
            if slot.get("effective_prompt"):
                origins[str(index)]["prompt_repair_request_id"] = slot["prompt_repair"]["request_id"]
        return {"image_slot_origins": origins, "image_recovery_revision": state["revision"],
                "ai_generated_image_count": 3, "reused_image_count": 0,
                "recovered_image_count": sum(bool(s.get('donor_index') or s.get('effective_prompt')) for s in state['slots'].values())}

    def request(self, body):
        operation = body.get("operation")
        if operation == "start":
            return {"state": self.start(body.get("analysis"))}
        if operation == "state":
            return {"state": self.state()}
        fields = {key: body.get(key) for key in ("revision", "index", "run_id")}
        if operation in {"prepare_repair", "claim_repair_helper", "approve_repair", "reserve_repaired"}:
            return self.prompt_repair(operation, **fields, request_id=body.get("request_id", ""), candidate=body.get("candidate"), contract_version=body.get('contract_version', 1))
        if operation == "reserve":
            return self.reserve(**fields, request_id=body.get("request_id"), donor_index=body.get("donor_index", 0))
        if operation == "finish":
            return {"state": self.finish(**fields, token=body.get("token"), outcome=body.get("outcome"), image=body.get("image"), reason=body.get("reason", ""))}
        raise ValueError("คำสั่งกู้ภาพไม่ถูกต้อง")

    def approve_existing_source(self, relative, expected_revision):
        """Explicit desktop-only consent, never callable by an AI web message."""
        job = self._job()
        if job.get("automation_status") == "running" or job.get("flow_clips") or job.get("flow_local_motion_clips") or job.get("video_path"):
            raise ValueError("หยุดงานก่อนเลือกภาพสำรอง และห้ามแทนงานที่มีวิดีโอแล้ว")
        with self.store.locked():
            state = self.store.read_unlocked(default={})
            if not state or state.get("revision") != expected_revision:
                raise ValueError("ชุดภาพเปลี่ยน กรุณาเปิดตรวจภาพอีกครั้ง")
            if any(s.get('status') in {'reserved', 'uncertain', 'download_pending'} for s in state['slots'].values()):
                raise ValueError("ยังไม่ทราบผลภาพรอบก่อน ห้ามแทนที่ขณะอาจกำลังสร้าง/ดาวน์โหลด")
            if not any(s.get('status') in {'missing', 'failed', 'policy_blocked', 'blocked'} for s in state['slots'].values()):
                raise ValueError("ไม่มีช่องที่ต้องเลือกภาพสำรอง หรือยืนยันไว้แล้ว")
            valid = [p for p, sha in state['sources']]
            valid += [str(self._file(int(i)).relative_to(self.folder)).replace('\\', '/')
                      for i, slot in state['slots'].items() if slot.get('status') == 'succeeded']
            relative = str(relative).replace('\\', '/')
            if relative not in [p.replace('\\', '/') for p in valid]:
                raise ValueError("ภาพสำรองต้องเป็นภาพที่ตรวจผ่านของงานนี้")
            source = (self.folder / relative).resolve()
            if self.folder not in source.parents:
                raise ValueError("ภาพอยู่นอกงาน")
            source_hash = _digest(source)
            original_hashes = {str(p).replace('\\', '/'): sha for p, sha in state['sources']}
            for i, slot in state['slots'].items():
                if slot.get('status') == 'succeeded':
                    original_hashes[str(self._file(int(i)).relative_to(self.folder)).replace('\\', '/')] = slot['sha256']
            if original_hashes.get(relative) != source_hash:
                raise ValueError("ไฟล์สำรองเปลี่ยนจากภาพที่ตรวจไว้ กรุณาตรวจใหม่")
            import base64
            result = dict(state['analysis'], job_id=self.job_id)
            result['image_prompts'] = [state['slots'][str(i)].get('effective_prompt', state['analysis']['image_prompts'][i-1]) for i in range(1, 4)]
            result['generated_images'] = [
                'data:image/png;base64,' + base64.b64encode(self._file(i).read_bytes()).decode()
                if state['slots'][str(i)]['status'] == 'succeeded' else None for i in range(1, 4)]
            result['provider'] = f"{job.get('image_ai_provider', 'chatgpt')}_web_extension"
            saved = self.manager.apply_ai_result(result)
            paths, origins, fallbacks = [], {}, {}
            for i in range(1, 4):
                slot = state['slots'][str(i)]
                success = slot['status'] == 'succeeded'
                path = str(self._file(i).relative_to(self.folder)).replace('\\', '/') if success else relative
                paths.append(path)
                origins[str(i)] = {'origin': slot.get('origin', 'generated') if success else 'reused_existing', 'path': path}
                if not success:
                    fallbacks[str(i)] = {'failure_code': 'USER_APPROVED_IMAGE_REUSE', 'user_approved': True,
                        'revision': state['revision'], 'source_image_index': i, 'source_image': path,
                        'source_sha256': source_hash, 'status': 'pending', 'reason': slot['status']}
                    slot.update(status='fallback', origin='reused_existing')
            saved.update(composition_images=paths, image_slot_origins=origins,
                         image_reuse_fallbacks=fallbacks, image_recovery_revision=state['revision'],
                         flow_target_clip_count=3, flow_required_clip_count=3,
                         flow_source_image_map={str(i): i for i in range(1, 4)},
                         flow_source_variant_map={str(i): 1 for i in range(1, 4)},
                         ai_generated_image_count=len(saved.get('generated_images') or []),
                         reused_image_count=len(fallbacks), automation_status='idle')
            self.manager._save_manifest_file(self.folder / 'job.json', saved)
            self.store.write_unlocked(state)
            return saved
