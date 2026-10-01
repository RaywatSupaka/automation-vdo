"""Exact observed controls, idempotent setting and fresh pre-publication proof."""
import time

from core.shopee_posting.device import ReviewRequired, ShopeeDevice
from core.shopee_posting.options import validate_options, option_summary, proof_matches_options
from core.shopee_posting.settings_layout import detect_layout, SettingsNotReady

P = 'com.shopee.th.dfpluginshopee16:id/'
CONTROLS = {
    'allow_reuse': ('allow_reuse_toggle', 'tv_allow_reuse', 'อนุญาตให้นำเนื้อหาไปใช้ซ้ำหรือเผยแพร่ต่อ'),
    'ai_label': ('ai_generated_toggle', 'tv_ai_generated_title', 'ครีเอเตอร์เพิ่มป้ายกำกับ AI ไปยังเนื้อหานี้'),
}


def ensure_toggle(device, control, desired):
    resource = P + control
    if device.visual_green(resource) is desired:
        return
    # One tap at most, even if its ACK is lost. Only passive reads may follow.
    try:
        device.tap(**{'resource-id': resource})
    except (OSError, ReviewRequired):
        pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        device.verify(); device.foreground()
        try:
            if device.visual_green(resource) is desired:
                return
        except ReviewRequired:
            pass
        time.sleep(.25)
    raise ReviewRequired('กดสวิตช์แล้วแต่ยืนยันค่าไม่ได้: ' + control + ' • ไม่กดซ้ำและยังไม่โพสต์')


SHARES = ('iv_whatsapp', 'iv_facebook')
RESOURCES = tuple(P + value[0] for value in CONTROLS.values()) + tuple(P + c for c in SHARES)


def read_options(device, validate=None, previous=None):
    capabilities = None
    def resolve(nodes):
        nonlocal capabilities
        capabilities = detect_layout(nodes)
        return capabilities['resources']
    # Only incomplete known pages retry; never retry a mutation, ambiguous
    # control, changed final proof, wrong device or unknown Send.
    for attempt in range(3):
        try:
            observation = device.observe_controls(resolve, validate=validate, previous=previous)
            break
        except SettingsNotReady:
            if previous is not None or attempt == 2:
                raise
            device.verify()
            time.sleep(.25)
    values = {r.rsplit('/',1)[-1]:value for r,value in observation['values'].items()}
    reuse = [values[r] for r in capabilities['reuse_controls']]
    observed = {'schema':1, 'allow_reuse':reuse[0] if reuse and all(v is reuse[0] for v in reuse) else None,
                'ai_label':values.get('ai_generated_toggle')}
    proof = dict(options=observed, checked_at=observation['checked_at'],
                 sharing_off=all(observation['values'][P+c] is False for c in SHARES),
                 method='shared_layout_v3', capabilities={k:v for k,v in capabilities.items() if k!='resources'},
                 control_values=values, unavailable_options=([] if capabilities['ai_label_available'] else ['ai_label'])
                 + (['allow_reuse'] if not reuse else []))
    return proof, observation


def require_supported(proof, options):
    if not proof['capabilities']['ai_label_available'] and not options.get('allow_missing_controls'):
        raise ReviewRequired('SHOPEE_AI_LABEL_UNAVAILABLE • หน้านี้ไม่มีปุ่มป้าย AI • เปิดตัวเลือกข้ามสวิตช์ที่ไม่มี หากต้องการโพสต์ต่อ • ยังไม่ได้โพสต์')
    if (proof['capabilities']['layout']=='no_reuse_controls' or
            proof['capabilities']['layout']=='split_duet_stitch' and len(proof['capabilities']['reuse_controls'])!=2) and not options.get('allow_missing_controls'):
        raise ReviewRequired('SHOPEE_REUSE_UNAVAILABLE • หน้านี้มีสวิตช์ใช้ซ้ำไม่ครบ • ยังไม่ได้โพสต์')


def observe_options(device, options, validate=None, previous=None):
    options = validate_options(options)
    proof, observation = read_options(device, validate, previous)
    require_supported(proof, options)
    proof['requested_options'] = dict(options)
    if not proof['sharing_off']:
        raise ReviewRequired('ยังไม่ยืนยันว่าปิดแชร์ต่อแอปอื่น • ยังไม่โพสต์')
    if not proof_matches_options(proof, options):
        raise ReviewRequired('ตัวเลือกบนมือถือไม่ตรง: ' + option_summary(options) + ' • ยังไม่โพสต์')
    return proof, observation


def verify_options(device, options):
    return observe_options(device, options)[0]


def apply_options(device, options):
    options = validate_options(options)
    proof, observation = read_options(device)
    require_supported(proof, options)
    desired = {control:options['allow_reuse'] for control in proof['capabilities']['reuse_controls']}
    if proof['capabilities']['ai_label_available']:
        desired['ai_generated_toggle'] = options['ai_label']
    desired.update({c: False for c in SHARES})
    changed = False
    for control, value in desired.items():
        if observation['values'][P+control] is not value:
            # Fresh single-control read before mutation; never act on old bounds.
            ensure_toggle(device, control, value)
            changed = True
    if changed:
        return verify_options(device, options)
    proof['requested_options'] = dict(options)
    if not proof_matches_options(proof, options):
        raise ReviewRequired('ยังยืนยันตัวเลือกครบตามที่เลือกไม่ได้ • ยังไม่โพสต์')
    return proof
