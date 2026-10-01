"""Resolve prepared Product settings from durable desktop data, not live forms."""
import copy

from core.creation_queue import clean_settings


def prepared_product_runtime(products, payload):
    context = payload.get('creative_context') or {}
    if context.get('kind') != 'product_story' or not context.get('source_product_id'):
        return None
    source = products.get_job(str(context['source_product_id']))
    saved_context = source.get('story_creative_context') or {}
    if (not source.get('story_source_only') or not context.get('snapshot_id')
            or saved_context.get('snapshot_id') != context.get('snapshot_id')):
        raise ValueError('ค่าตัวเลือกสินค้าไม่ตรงกับข้อมูลอ้างอิงที่บันทึกไว้')
    prepared = source.get('story_prepare_options') or {}
    saved = prepared.get('product_runtime_snapshot')
    if isinstance(saved, dict):
        required_dicts = ('audio_choices', 'audio', 'render', 'finish_config', 'flow_settings',
                          'ai_cover_options', 'intro_options', 'green_options', 'presenter')
        if (any(not isinstance(saved.get(key), dict) for key in required_dicts)
                or any(not isinstance(saved.get(key), str) for key in ('voice_reference_id', 'voice_reference_file'))
                or saved['audio_choices'].get('mode') not in {'api', 'none', 'flow_original'}):
            raise ValueError('ค่าประกอบคลิปสินค้าที่บันทึกไว้ไม่ครบ • ไม่ใช้ค่าปัจจุบันแทนค่าของงานเดิม')
        result = clean_settings(copy.deepcopy(saved))
    else:
        # Legacy captures cannot use whatever happens to be selected now. Keep
        # explicit saved choices and disable absent optional features.
        if not isinstance(prepared.get('audio_choices'), dict):
            raise ValueError('งานเตรียมสินค้าเก่าไม่มีค่าการพากย์ที่บันทึกไว้ • กรุณาเลือกค่าก่อนสร้างงานใหม่')
        result = clean_settings(prepared)
        for key in ('ai_cover_options', 'intro_options', 'green_options', 'presenter'):
            result.setdefault(key, {'enabled': False})
        for key in ('flow_settings', 'render', 'finish_config', 'audio'):
            result.setdefault(key, {})
        result.setdefault('voice_reference_id', '')
        result.setdefault('voice_reference_file', '')
        result.setdefault('subtitle_enabled', bool(prepared.get('subtitle', prepared['audio_choices'].get('subtitle', False))))
    result['creative_context'] = copy.deepcopy(context)
    # Complete deterministic compatibility defaults, not falsey dictionaries
    # that downstream workers would replace with today's live widgets.
    result['render'] = { 'width':720, 'height':1280, 'fps':30, 'crf':18,
        'backend_version':1, 'encoder':'auto', 'green_filter_threads':4,
        'motion_strength':1.0, 'transition_sec':0.22, **(result.get('render') or {}) }
    result['voice'] = {'language':'th', 'engine':'auto', 'emotion_id':'normal',
        'speed':1.0, 'silence_sec':0.3, 'output_format':'mp3', **(result.get('voice') or {})}
    return clean_settings(result)
