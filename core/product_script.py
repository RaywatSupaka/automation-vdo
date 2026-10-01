"""Opt-in, immutable product storytelling choices; absent means legacy."""


def product_script_options(value=None, *, product=None):
    if value is None:
        return None
    if not isinstance(value, dict) or type(value.get('version')) is not int:
        raise ValueError('รูปแบบบทสินค้าไม่ถูกต้อง')
    if product is False:
        raise ValueError('แนวบทรีวิวใช้กับคลิปสินค้า Shopee ใหม่เท่านั้น')
    if value['version'] == 1 and value.get('style') in ('standard', 'story_first_review'):
        return {'version': 1, 'style': value['style']}
    if value['version'] == 2 and value.get('style') == 'short_film_ad':
        genre = value.get('genre', 'auto')
        cta = value.get('ending_cta', True)
        if genre not in ('auto', 'warm', 'comedy', 'twist') or type(cta) is not bool:
            raise ValueError('แนวหนังสั้นหรือคำชวนดูตะกร้าไม่ถูกต้อง')
        return {'version': 2, 'style': 'short_film_ad', 'genre': genre, 'ending_cta': cta}
    if value['version'] == 3:
        from core.creative_brief import PRODUCT_STYLES
        if set(value) == {'version', 'style'} and value.get('style') in {'auto', *(row[0] for row in PRODUCT_STYLES)}:
            return {'version': 3, 'style': value['style']}
    raise ValueError('รูปแบบบทสินค้าไม่ใช่เวอร์ชันที่รองรับ')


def story_first_review(job):
    options = job.get('product_script_options') or {}
    return (job.get('product_short') is True and isinstance(options, dict)
            and type(options.get('version')) is int and options['version'] == 1
            and options.get('style') == 'story_first_review')


def short_film_ad(job):
    options = job.get('product_script_options') or {}
    return (job.get('product_short') is True and isinstance(options, dict)
            and type(options.get('version')) is int and options['version'] == 2
            and options.get('style') == 'short_film_ad')


def authored_product_script(job):
    """These styles own their ending; never append legacy engagement copy."""
    return story_first_review(job) or short_film_ad(job) or creative_product_script(job)


def creative_product_script(job):
    return job.get('product_short') is True and (job.get('product_script_options') or {}).get('version') == 3


def creative_product_instruction(job):
    if not creative_product_script(job):
        return ''
    from core.creative_brief import instruction
    from core.media_audio import audio_mode
    from core.product_pointing import enabled as pointing_review
    if pointing_review(job):
        delivery = {
            'flow_original': 'NATIVE AUDIO: One reviewer holding the camera speaks the exact saved Thai lines from behind the camera. No visible speaker, face or lip-sync; no second narrator or extra dialogue.',
            'none': 'SILENT VIDEO: Use pointing gestures and visible details only. Keep saved script fields for compatibility; do not generate speech.',
        }.get(audio_mode(job), 'VOICEOVER: Use only the selected voice track as the camera-holder review. No competing generated speech, visible speaker or lip-sync.')
        return ('PRODUCT CREATIVE SCRIPT v3: Write ONE coherent first-person product review using supplied facts and visible details only. '
                'Do not invent incidents, specifications, purchases, personal testimonials, health claims, prices or test results. '
                'Use exactly the saved scene count, each scene adding a supported detail or demonstration. '
                'Align narration_script, scene_narrations and dialogue turns word for word. '
                'Preserve approved lines and facts during repair. No mandatory sales/engagement CTA; '
                'a user-requested closing invitation appears at most once in the final scene. '
                + delivery + '\n' + instruction(job))
    delivery = {
        'flow_original': 'NATIVE AUDIO: Use the saved visible reviewer/cast to speak concise exact Thai lines. Do not introduce a separate narrator or extra speakers for this preset.',
        'none': 'SILENT VIDEO: Convey the narrative through visible actions. Preserve saved script fields for compatibility, but do not request generated speech.',
    }.get(audio_mode(job), 'VOICEOVER: Use the selected voice track. No competing generated speech or promise of lip sync.')
    return ('PRODUCT CREATIVE SCRIPT v3: Write ONE coherent fictional scenario using supplied product facts only. '
            'Never invent specifications, health claims, prices, discounts, testimonials, purchases or test results. '
            'Keep exact product appearance and selected cast/outfit. Never add a second person just for a preset. '
            'Use exactly the saved scene count; align narration_script, scene_narrations and dialogue turns word for word. '
            'Each scene adds an event or useful detail. No mandatory sales/engagement CTA and no program-added CTA. '
            'Keep any user-requested closing invitation at most once, only after the conclusion in the final scene. '
            'Preserve approved lines and facts during missing-scene or JSON repair. ' + delivery + '\n' + instruction(job))


def film_instruction(job):
    if not short_film_ad(job):
        return ''
    options = product_script_options(job['product_script_options'])
    from core.media_audio import audio_mode
    delivery = ('NATIVE AUDIO: Characters speak to each other or react to the event, NOT to camera as reviewers. '
                'Keep one visible speaking character per scene; listener may be off-screen. '
                'Only the final CTA may address the viewer. Preserve exact Thai dialogue and natural lip sync. '
                if audio_mode(job) == 'flow_original' else
                'VOICEOVER: A short-film storyteller uses the selected API voice, not a salesperson. '
                'No competing speech in the video; do not promise lip sync. ')
    if audio_mode(job) == 'none':
        delivery = 'SILENT VIDEO: Tell the story through visible actions; do not require generated speech. Keep text fields for the saved script only. '
    ending = ('After the payoff, finish the final spoken text with ONE short basket invitation, also copied verbatim to ending_cta_text. '
              'Do not claim the shopping link is already attached. ' if options['ending_cta'] else
              'No sales/engagement CTA anywhere. ending_cta_text must be an empty string. ')
    return ('PRODUCT SHORT FILM AD v2: Create ONE complete fictional short film, not a review, testimonial or spec list. '
            'Open with an intriguing event, mystery, goal or misunderstanding unrelated to selling; '
            'the first scene must NOT show or name the product, price, benefits or basket. '
            'Use 1–2 consistent adult characters and the selected cast identity; develop the SAME event. '
            'Causally bridge the event to a later natural product appearance: a prop, gift or useful object, '
            'not a magical cure. Show the product only in scenes whose product_visible is true; '
            'attached product references preserve appearance WHEN revealed, not a requirement to include them in every image. '
            'Resolve the opening question/event before any CTA. Do not invent purchase history, endorsements, '
            'test results, health claims, prices, discounts or unsupported features. facts_used must quote only supplied product data. '
            f'Genre: {options["genre"]}. Use exactly scene_count, never increase it. For 3 scenes combine setup with hook, '
            'bridge with product, payoff with optional CTA. With more scenes develop the same story without padding. '
            'Return product_film_plan={version:1, premise:string, product_connection:string, resolution:string, '
            'ending_cta_text:string, scenes:[{roles:[hook|setup|bridge|product|payoff|cta], action:string, '
            'product_visible:boolean, speaker:string, listener:string, spoken_text:string, facts_used:[string]}]}. '
            'scenes must have exactly scene_count entries; hook first, payoff last, bridge and product after opening. '
            'Every scene needs visible action, speaker/listener and exact spoken_text matching scene_narrations[i]. '
            'Keep action/direction OUT of spoken text. narration_script equals those lines joined in order. '
            'scene_dialogue_turns uses that same named speaker and text; preserve visual_bible/cast/location continuity. '
            'Keep lines short enough for saved clip duration, including the final CTA; no captions burned into images. '
            'During JSON or scene repair preserve approved lines, scene roles, reveal timing and product facts; '
            'never rewrite neighboring saved scenes. ' + ending + delivery)


def script_instruction(job):
    if creative_product_script(job):
        return creative_product_instruction(job)
    return film_instruction(job) if short_film_ad(job) else review_instruction(job)


def validate_creative_plan(job, result):
    if not creative_product_script(job):
        return
    import re
    lines = result.get('scene_narrations')
    count = int(job.get('scene_count') or 0)
    if not isinstance(lines, list) or len(lines) != count or any(not isinstance(line, str) or not line.strip() for line in lines):
        raise ValueError('PRODUCT_CREATIVE_REVIEW • บทพูดต้องครบจำนวนฉาก')
    compact = lambda text: re.sub(r'\s+', '', text)
    narration = result.get('narration_script')
    if not isinstance(narration, str) or compact(narration) != compact(' '.join(lines)):
        raise ValueError('PRODUCT_CREATIVE_REVIEW • บทเต็มต้องตรงกับบทพูดรายฉาก')
    cta = re.compile(r'(?:กด|ฝาก|ช่วย)\s*(?:หัวใจ|ไล[กค]์|ติดตาม|คอมเมนต์|แชร์)|(?:จิ้ม|กด|ดู)\s*(?:สินค้า(?:ที่)?)?\s*ตะกร้า|subscribe', re.I)
    if any(cta.search(line) for line in lines[:-1]) or len(cta.findall(lines[-1])) > 1:
        raise ValueError('PRODUCT_CREATIVE_REVIEW • คำชวนมีส่วนร่วมต้องไม่ซ้ำและอยู่เฉพาะท้ายเรื่อง')


def validate_film_plan(job, result):
    """Structural pre-image gate, not a claim that a plot/fact is semantically true."""
    if not short_film_ad(job):
        return result
    import re
    def fail(message):
        raise ValueError('PRODUCT_FILM_PLAN • ' + message)
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    def compact(value):
        return re.sub(r'\s+', '', value)
    plan = result.get('product_film_plan')
    if not isinstance(plan, dict) or type(plan.get('version')) is not int or plan['version'] != 1:
        fail('ต้องมีแผนหนังสั้นเวอร์ชัน 1 ก่อนสร้างภาพ')
    if any(not text(plan.get(k)) for k in ('premise', 'product_connection', 'resolution')):
        fail('ต้องมีเรื่องเปิด เหตุเชื่อมสินค้า และบทสรุป')
    scenes, lines = plan.get('scenes'), result.get('scene_narrations')
    count = int(job.get('scene_count') or 0)
    if (not isinstance(scenes, list) or len(scenes) != count or count < 3
            or not isinstance(lines, list) or len(lines) != count):
        fail('แผนและบทพูดต้องครบจำนวนฉากที่เลือก')
    allowed = {'hook', 'setup', 'bridge', 'product', 'payoff', 'cta'}
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            fail('ข้อมูลฉากต้องเป็น object')
        roles = scene.get('roles')
        if (not isinstance(roles, list) or not roles or any(not isinstance(r, str) or r not in allowed for r in roles)
                or type(scene.get('product_visible')) is not bool
                or any(not text(scene.get(k)) for k in ('action', 'speaker', 'listener', 'spoken_text'))
                or not isinstance(scene.get('facts_used'), list) or any(not text(f) for f in scene['facts_used'])):
            fail(f'ข้อมูลฉาก {i+1} ยังไม่ครบ')
        if not text(lines[i]) or scene['spoken_text'].strip() != lines[i].strip():
            fail(f'บทพูดฉาก {i+1} ไม่ตรงกับแผน')
        if 'cta' in roles and i != count - 1:
            fail('คำชวนดูตะกร้าต้องอยู่เฉพาะฉากสุดท้าย')
    if 'hook' not in scenes[0]['roles'] or scenes[0]['product_visible'] or scenes[0]['facts_used']:
        fail('ฉากเปิดต้องเล่าเรื่องก่อน ยังไม่โชว์หรือขายสินค้า')
    if ('payoff' not in scenes[-1]['roles'] or not any('bridge' in s['roles'] for s in scenes[1:])
            or not any('product' in s['roles'] and s['product_visible'] for s in scenes[1:])):
        fail('ขาดฉากเชื่อมสินค้า การเผยสินค้า หรือบทสรุป')
    if not text(result.get('narration_script')) or compact(result['narration_script']) != compact(' '.join(lines)):
        fail('บทเต็มต้องตรงกับบทพูดเรียงทุกฉาก')
    cta = plan.get('ending_cta_text')
    enabled = product_script_options(job['product_script_options'])['ending_cta']
    if enabled:
        if not text(cta) or 'cta' not in scenes[-1]['roles'] or not lines[-1].strip().endswith(cta.strip()):
            fail('ต้องปิดเรื่องแล้วชวนดูตะกร้าเฉพาะท้ายบท')
        if compact(' '.join(lines)).count(compact(cta)) != 1:
            fail('คำชวนดูตะกร้าต้องมีครั้งเดียว')
    elif cta != '' or any('cta' in s['roles'] for s in scenes):
        fail('งานนี้ปิดคำชวนดูตะกร้าไว้')
    if any(re.search(r'ตะกร้า|กด(?:ซื้อ|หัวใจ|ไลก์|ติดตาม)|สั่งซื้อ|add to cart', line, re.I) for line in (lines[:-1] if enabled else lines)):
        fail('พบคำชวนขายหรือมีส่วนร่วมก่อนจบเรื่อง')
    return result


def film_scene(job, index):
    if not short_film_ad(job):
        return None
    scenes = (job.get('product_film_plan') or {}).get('scenes') or []
    if not 0 < index <= len(scenes):
        raise ValueError('PRODUCT_FILM_PLAN • ไม่พบแผนฉากที่บันทึกไว้')
    return scenes[index - 1]


def review_instruction(job):
    if not story_first_review(job):
        return ''
    from core.media_audio import product_native_delivery
    delivery = (
        'NATIVE AUDIO: The same visible adult reviewer speaks these exact Thai lines on camera, '
        'with natural expression, small gestures and synchronized mouth movement. No separate narrator. '
        if product_native_delivery(job) else
        'VOICEOVER: Write first-person Thai storytelling for the selected voice track. '
        'Do not add competing spoken audio or promise lip sync in the generated video. '
    )
    return ('PRODUCT STORY-FIRST REVIEW v1: Open with one intriguing everyday situation or intention, '
            'then naturally connect the product to that SAME story. The first spoken line is a hook, '
            'not a long product name, price, spec list or formulaic sales introduction. '
            'Use one consistent fictional reviewer persona and first-person pronoun throughout. '
            'Write short conversational Thai with believable reactions, not a third-person announcer '
            'or a character reading advertising copy. Invent the situation, NOT personal purchase/use '
            'history, test results, testimonials, endorsements, specifications, prices or health benefits. '
            'Mention only one or two relevant supported product facts; never invent missing facts. '
            'Keep the saved product appearance and selected person identity. Product visibility may be '
            'subtle in the opening and need not dominate every scene. '
            'Finish the event naturally: no mandatory purchase pitch, like/comment/follow request or '
            'program-added CTA. A genuinely relevant closing question is optional. '
            'Use exactly the requested scene count and fit each short line to its scene duration. '
            'For three scenes: situation → natural product use → conclusion. For more scenes, develop '
            'the same event without padding, repetitive hooks or repeated product names. '
            'Keep scene_narrations, scene_dialogue_turns and narration_script aligned word for word; '
            'image and motion plans illustrate the same event, not a new advertisement. '
            'When repairing JSON or completing missing scenes, preserve approved dialogue and product '
            'facts, apply this style only to missing content, and never rewrite saved scenes. ' + delivery)
