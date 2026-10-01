"""One-scene test uses the full Shorts pipeline and user choices."""
import copy

def smoke_payload(payload):
    topic=str(payload.get('topic') or '').strip()
    if not topic:
        raise ValueError('กรุณาใส่หัวข้อทดสอบ')
    allowed=('topic','story_text','provider','ai_web_model','flow_settings','visual_style',
             'visual_style_custom','main_image','fictional_ai_characters_confirmed',
             'ai_cover_options','presenter','audio_choices','subtitle','queue_only')
    result={key:copy.deepcopy(payload[key]) for key in allowed if key in payload}
    result.update(topic=topic,scene_count=1,video_generation_mode='google_flow')
    return result
