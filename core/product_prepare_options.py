"""The single durable settings contract for Shopee capture and later handoff."""
import copy


def product_option_snapshot(value):
    """Validate saved UI provenance without treating it as a live form selector."""
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or value.get('form') not in {'product', 'product-batch'}
            or set(value) != {'version', 'form'}):
        raise ValueError('ข้อมูลตัวเลือกสินค้าที่บันทึกไว้ไม่ถูกต้อง')
    return {'version': 1, 'form': value['form']}


def freeze_product_options(options):
    source = options if isinstance(options, dict) else {}
    wardrobe = str(source.get('outfit_mode') or 'auto')
    if wardrobe not in {'auto', 'saved', 'product'}:
        raise ValueError('รูปแบบชุดนายแบบ / นางแบบไม่ถูกต้อง')
    result = {
        'provider': str(source.get('provider') or 'chatgpt').lower()[:20],
        'ai_web_model': str(source.get('ai_web_model') or '').lower()[:40],
        'video_generation_mode': str(source.get('video_generation_mode') or 'google_flow').lower()[:30],
        'scene_count': max(3, min(15, int(source.get('scene_count') or 3))),
        'product_script_options': copy.deepcopy(source.get('product_script_options') or {}),
        'story_text': str(source.get('story_text') or '')[:10000],
        'cast_id': str(source.get('cast_id') or '')[:100],
        'outfit_mode': wardrobe,
        'handoff_mode': 'queue' if source.get('handoff_mode') == 'queue' else 'immediate',
    }
    if not isinstance(result['product_script_options'], dict):
        result['product_script_options'] = {}
    if 'speech_delivery_version' in source:
        from core.speech_delivery import version
        result['speech_delivery_version'] = version(source['speech_delivery_version'])
    if 'product_editorial_version' in source:
        from core.product_editorial import version
        result['product_editorial_version'] = version(source['product_editorial_version'])
    for key in ('audio_choices', 'flow_settings', 'storytelling_options', 'generated_music_options', 'intro_options',
                'green_options', 'ai_cover_options', 'render', 'finish_config', 'presenter'):
        if isinstance(source.get(key), dict):
            result[key] = copy.deepcopy(source[key])
    if 'product_option_snapshot' in source:
        result['product_option_snapshot'] = product_option_snapshot(source['product_option_snapshot'])
        required = ('audio_choices', 'flow_settings', 'intro_options', 'green_options', 'ai_cover_options', 'presenter')
        if any(not isinstance(source.get(key), dict) for key in required):
            raise ValueError('ตัวเลือกสินค้าก่อนอ่าน Shopee ไม่ครบ • ยังไม่ได้เริ่มงาน')
    if 'product_runtime_snapshot' in source:
        if not isinstance(source['product_runtime_snapshot'], dict):
            raise ValueError('ค่าประกอบคลิปสินค้าที่บันทึกไว้ไม่ถูกต้อง')
        from core.creation_queue import clean_settings
        result['product_runtime_snapshot'] = clean_settings(source['product_runtime_snapshot'])
    for key in ('actor_dialogue', 'fictional_ai_characters_confirmed', 'subtitle_enabled', 'subtitle'):
        if key in source:
            result[key] = bool(source[key])
    for key in ('visual_style', 'visual_style_custom'):
        if key in source:
            result[key] = str(source[key] or '')[:500]
    return result
