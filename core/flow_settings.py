"""Small immutable Flow request contract; absent fields preserve the web setting.

Capabilities are observations of the open account/menu, never a model catalogue
or a price promise. Every requested value is verified again immediately before Send.
"""
import copy

FIELDS = ("model", "video_type", "resolution", "duration")


def flow_settings(value=None):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("ตั้งค่า Google Flow ไม่ถูกต้อง")
    if set(value) - {*FIELDS, "display", "outputs", "schema_version"}:
        raise ValueError("มีตัวเลือก Google Flow ที่ไม่รองรับ")
    if value.get("display", "unchanged") not in {"unchanged", "compact"}:
        raise ValueError("โหมดหน้าจอ Flow ไม่ถูกต้อง")
    if type(value.get("outputs", 1)) is not int or value.get("outputs", 1) != 1:
        raise ValueError("Google Flow สร้างครั้งละ 1 คลิปเท่านั้น")
    # Display is now a program invariant, not a per-job option.
    result = {'display': 'compact'}
    for key in FIELDS:
        text = value.get(key, "")
        if not isinstance(text, str) or len(text) > 120 or any(ord(c) < 32 for c in text):
            raise ValueError("ค่า Google Flow ไม่ถูกต้อง: " + key)
        if text.strip():
            result[key] = text.strip()
    if result.get("video_type") not in {None, "Frames", "Ingredients"}:
        raise ValueError("ชนิดวิดีโอ Flow ไม่ถูกต้อง")
    return result


def flow_capabilities(value):
    """Whitelist only UI labels, never return arbitrary page text or URLs."""
    if not isinstance(value, dict):
        return {}
    result = {"available": value.get("available") is True, "scope": "visible_menu_only"}
    if type(value.get('model_menu_open')) is bool:
        result['model_menu_open'] = value['model_menu_open']
    for key in FIELDS:
        entries = value.get(key, [])
        result[key] = [s.strip() for s in entries if isinstance(s, str) and 0 < len(s.strip()) <= 120
                       and not any(ord(c) < 32 for c in s)][:30] if isinstance(entries, list) else []
    selected = value.get("selected")
    result["selected"] = flow_settings({k: v for k, v in selected.items() if k in FIELDS}) if isinstance(selected, dict) else {}
    result["credit_notice"] = str(value.get("credit_notice") or "")[:180]
    context = value.get('context') or {}
    result['context'] = {k: str(context.get(k) or '')[:120] for k in ('model','video_type','aspect_ratio','layout')} if isinstance(context,dict) else {}
    states = value.get('states') or {}
    result['states'] = {k:v for k,v in states.items() if k in FIELDS and v in {'selectable','fixed_from_summary','unknown','disabled'}} if isinstance(states,dict) else {}
    return result


def snapshot_flow(payload, defaults=None):
    return copy.deepcopy(flow_settings(payload.get("flow_settings", defaults)))
