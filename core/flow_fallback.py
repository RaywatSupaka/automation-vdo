"""Structured terminal reasons that permit same-image local motion."""

FLOW_POLICY_BLOCKED = "FLOW_POLICY_BLOCKED"
FLOW_ATTACHMENT_UNCONFIRMED = "FLOW_ATTACHMENT_UNCONFIRMED"
FLOW_LOCAL_FALLBACK_CODES = frozenset({FLOW_POLICY_BLOCKED, FLOW_ATTACHMENT_UNCONFIRMED})


def validated_attachment_failure_evidence(evidence, flow_run_id, fingerprint):
    """Require a latched, pre-submit attachment attempt after its passive grace.

    Page text and error strings are never evidence. The Extension/Bridge owns
    live observation; managers retain only its bounded structured proof.
    """
    proof = dict(evidence) if isinstance(evidence, dict) else {}
    run_id = str(flow_run_id or "").strip()
    fingerprint = str(fingerprint or "").strip()
    required_true = (
        "submission_absent", "generation_absent", "result_absent",
        "confirmation_absent", "terminal_latched",
    )
    numeric_keys = ("attempt_started_at", "grace_started_at", "grace_elapsed_ms")
    valid_numbers = all(
        isinstance(proof.get(key), (int, float)) and not isinstance(proof.get(key), bool)
        and 0 < proof[key] < float("inf") for key in numeric_keys
    )
    if not (
        run_id and fingerprint
        and type(proof.get("schema_version")) is int and proof["schema_version"] == 1
        and proof.get("phase") == "before_submit"
        and proof.get("run_id") == run_id
        and str(proof.get("attempt_key") or "").strip()
        and str(proof.get("project_id") or "").strip()
        and type(proof.get("attachment_attempt_count")) is int and proof["attachment_attempt_count"] == 1
        and valid_numbers
        and proof.get("grace_elapsed_ms", 0) >= 30000
        and proof.get("grace_started_at", 0) >= proof.get("attempt_started_at", 0)
        and all(proof.get(key) is True for key in required_true)
    ):
        raise ValueError("ไม่พบหลักฐานยืนยันว่าแนบภาพ Flow ไม่สำเร็จก่อนส่งงานและครบเวลารอ")
    return {
        "schema_version": 1, "phase": "before_submit",
        "attempt_key": str(proof["attempt_key"])[:240],
        "project_id": str(proof["project_id"])[:160], "run_id": run_id[:160],
        "attachment_attempt_count": 1,
        **{key: proof[key] for key in numeric_keys},
        **{key: True for key in required_true},
        **({"selection_recovery_available": True} if proof.get("selection_recovery_available") is True else {}),
    }
