"""Desktop Flow defaults/discovery actions, independent of creation scheduling."""
from core.flow_settings import flow_settings


def flow_settings_action(app, action, payload):
    if action == "flow_settings_get":
        return {"ok": True, "settings": flow_settings(app.cfg.get("flow_defaults"))}
    if action == "flow_settings_save":
        settings = flow_settings(payload.get("settings"))
        from core.config import _config_store
        _config_store().update(lambda current: {**current, "flow_defaults": settings})
        app.cfg["flow_defaults"] = settings
        return {"ok": True, "settings": settings}
    if action == "flow_settings_read":
        reason = app._creation_idle_reason()
        if reason:
            # Expected safety block, not an internal server failure. Return
            # the actionable reason without enqueuing a browser command.
            return {"ok": False, "blocked": True, "error": reason, "command_id": None}
        command = app.bridge.queue_extension_command("read_flow_settings")
        return {"ok": True, "command_id": command["id"]}
    if action == "flow_settings_result":
        command = app.bridge.extension_command_status(payload.get("command_id"))
        if not command or command.get("action") != "read_flow_settings":
            raise ValueError("ไม่พบคำขออ่านค่าตั้ง Flow")
        return {"ok": True, "status": command["status"], "error": command.get("error", ""),
                "capabilities": command.get("flow_capabilities"), "checked_at": command.get("completed_at")}
    raise ValueError("คำสั่งตั้งค่า Flow ไม่ถูกต้อง")
