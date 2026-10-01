"""Typed, versioned requested options. Never infer observed phone state."""
DEFAULT_OPTIONS = {'schema': 1, 'allow_reuse': False, 'ai_label': True}


def validate_options(value):
    if (not isinstance(value, dict) or set(value) not in (set(DEFAULT_OPTIONS), set(DEFAULT_OPTIONS)|{'allow_missing_controls'})
            or type(value.get('schema')) is not int or value['schema'] != 1
            or any(type(value.get(k)) is not bool for k in ('allow_reuse', 'ai_label'))
            or 'allow_missing_controls' in value and type(value['allow_missing_controls']) is not bool):
        raise ValueError('ตัวเลือกโพสต์ไม่ถูกต้องหรือเป็นรุ่นที่ยังไม่รองรับ กรุณาโหลดคิวใหม่')
    return dict(value)


def requested_options(row):
    # Legacy unsent drafts use explicit safe defaults, never current global defaults.
    if 'post_options' not in row and not row.get('publish_intent'):
        return dict(DEFAULT_OPTIONS)
    return validate_options(row.get('post_options'))


def option_summary(options):
    options = validate_options(options)
    return ('ใช้ซ้ำ: ' + ('เปิด' if options['allow_reuse'] else 'ปิด') + ' • ป้าย AI: ' + ('เปิด' if options['ai_label'] else 'ปิด')
            + (' • สวิตช์ที่ไม่มี: ข้ามและโพสต์ต่อ' if options.get('allow_missing_controls') else ''))


def proof_matches_options(proof, options):
    """Keep old receipts valid; never fabricate an AI OFF/ON value for absence."""
    options = validate_options(options)
    if not isinstance(proof, dict):
        return False
    if proof.get('method') != 'shared_layout_v3':
        return (proof.get('method') in (None,'shared_screen_v2')
                and proof.get('options') == options and not options.get('allow_missing_controls'))
    observed = proof.get('options') or {}
    capabilities = proof.get('capabilities') or {}
    controls = proof.get('control_values') or {}
    layout = capabilities.get('layout')
    reuse = capabilities.get('reuse_controls')
    if (not isinstance(reuse,list) or len(set(reuse)) != len(reuse)
            or layout not in {'combined_reuse','split_duet_stitch','no_reuse_controls'}
            or layout == 'combined_reuse' and reuse != ['allow_reuse_toggle']
            or layout == 'split_duet_stitch' and (not reuse or any(c not in {'allow_duet_toggle','allow_stitch_toggle'} for c in reuse))
            or layout == 'no_reuse_controls' and reuse != []):
        return False
    if (proof.get('requested_options') != options or proof.get('sharing_off') is not True
            or observed.get('schema') != 1
            or (observed.get('allow_reuse') is not options['allow_reuse'] if reuse else
                'allow_reuse' not in observed or observed['allow_reuse'] is not None or options.get('allow_missing_controls') is not True)
            or any(controls.get(c) is not options['allow_reuse'] for c in reuse)
            or any(controls.get(c) is not False for c in ('iv_whatsapp','iv_facebook'))):
        return False
    if layout == 'split_duet_stitch' and len(reuse) != 2 and options.get('allow_missing_controls') is not True:
        return False
    available_ai = capabilities.get('ai_label_available')
    if type(available_ai) is not bool or set(controls) != set(reuse+['iv_whatsapp','iv_facebook']+(['ai_generated_toggle'] if available_ai else [])):
        return False
    if capabilities.get('ai_label_available') is True:
        return observed.get('ai_label') is options['ai_label'] and controls.get('ai_generated_toggle') is options['ai_label']
    return (capabilities.get('ai_label_available') is False and options.get('allow_missing_controls') is True
            and 'ai_label' in observed and observed['ai_label'] is None
            and 'ai_generated_toggle' not in controls and 'ai_label' in proof.get('unavailable_options',[]))
