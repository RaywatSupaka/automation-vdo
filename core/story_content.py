"""Structural Story identity checks; no image judging, mutation or regeneration."""
import copy
import json
import re
import unicodedata


STORY_CONTENT_VERSION = 1
STORY_VISUAL_DEPICTION_INSTRUCTION = (
    "NON-GRAPHIC VISUAL DEPICTION: Preserve the requested cast, names, ages, identities, "
    "visual style, setting and established story facts. For a violent story event, depict "
    "the tension immediately before it or a non-graphic aftermath without showing strikes, "
    "blood, wounds or visible injury. Keep the event in the narration where appropriate; "
    "do not rewrite the plot or substitute characters. This is visual framing guidance, "
    "not a guarantee that the image provider will accept the request."
)
_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:['’-][A-Za-z0-9]+)*")
_GENERIC_TITLE_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "with", "from",
    "what", "if", "when", "then", "once", "one", "two", "three", "this", "that", "it",
    "story", "short", "shorts", "scene", "chapter", "episode", "ep", "part", "original",
    "cinematic", "anime", "comic", "watercolor", "realistic", "photorealistic", "3d", "2d",
}


def _normalized_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = re.sub(r"[-_‐‑‒–—−]", " ", value)
    return " ".join(value.split())


def contains_story_name(text, name):
    """Match supplied names/aliases, including Thai spacing, without translating."""
    text, name = _normalized_name(text), _normalized_name(name)
    if not name:
        return False
    if re.search(r"[ก-๙]", name) and not re.search(r"[a-z0-9]", name):
        return name.replace(" ", "") in text.replace(" ", "")
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", text))


def _story_bilingual_display_parts(name):
    """Read two explicit Thai/Latin spellings, not translations or descriptions."""
    if not isinstance(name, str) or len(name) > 200:
        return []
    value = unicodedata.normalize("NFKC", name).strip()
    if len(value) > 200:
        return []
    match = re.fullmatch(r"([^()]+)\s*\(([^()]+)\)", value)
    if not match:
        return []
    parts = [part.strip() for part in match.groups()]
    thai = r"[\u0e01-\u0e3a\u0e40-\u0e4e]+(?: +[\u0e01-\u0e3a\u0e40-\u0e4e]+)*"
    latin = r"[A-Z][A-Za-z]*(?:['’-][A-Za-z]+)*(?: +[A-Z][A-Za-z]*(?:['’-][A-Za-z]+)*){0,5}"
    if not ((re.fullmatch(thai, parts[0]) and re.fullmatch(latin, parts[1]))
            or (re.fullmatch(latin, parts[0]) and re.fullmatch(thai, parts[1]))):
        return []
    return parts


def _story_unambiguous_display_aliases(entities):
    """Derived lookup only: existing registry and explicit aliases stay untouched."""
    def collision_key(value):
        normalized = _normalized_name(value)
        if re.search(r"[\u0e01-\u0e4e]", normalized) and not re.search(r"[a-z0-9]", normalized):
            return normalized.replace(" ", "")
        return normalized

    candidates = {entity["id"]: _story_bilingual_display_parts(entity["name"]) for entity in entities}
    owners = {}
    for entity in entities:
        for value in [entity["name"], *entity["aliases"], *candidates[entity["id"]]]:
            owners.setdefault(collision_key(value), set()).add(entity["id"])
    return {entity["id"]: [value for value in candidates[entity["id"]]
                           if owners[collision_key(value)] == {entity["id"]}]
            for entity in entities}


def requested_story_names(job):
    """Hard anchors only from explicit character/world fields, never guessed prose."""
    names = []

    def add(value):
        value = str(value or "").strip()
        if value and len(value) <= 200 and _normalized_name(value) not in {_normalized_name(row) for row in names}:
            names.append(value)

    for character in job.get("character_bible") or []:
        if isinstance(character, dict):
            add(character.get("name"))
    for value in (job.get("topic"), job.get("story_input")):
        source = str(value or "")
        for match in re.finditer(
            r"^\s*(?:ตัวละคร(?:ชื่อ)?|จักรวาล|แฟรนไชส์|characters?|universe|franchise)\s*[:：]\s*([^\n]{1,200})$",
            source, re.I | re.M,
        ):
            for name in re.split(r"[,;]", match.group(1)):
                add(name.strip().strip('"“”\''))
    return names[:64]


def story_source_aliases(job):
    """Aliases explicitly present in source metadata; never generated substitutes."""
    result = {}
    for character in job.get("character_bible") or []:
        if not isinstance(character, dict) or not isinstance(character.get("name"), str):
            continue
        aliases = character.get("aliases")
        if isinstance(aliases, list):
            result[character["name"].strip()] = [alias.strip() for alias in aliases
                                                 if isinstance(alias, str) and alias.strip() and len(alias) <= 200][:16]
    notes = job.get("user_pronunciation_notes") if isinstance(job.get("user_pronunciation_notes"), dict) else {}
    for name, alias in notes.items():
        if isinstance(name, str) and isinstance(alias, str) and name in requested_story_names(job):
            result.setdefault(name, []).append(alias)
    return result


def _inferred_story_names(job):
    """Weak review hints only: capitalization cannot establish a required cast."""
    names = []
    for value in (job.get("topic"), job.get("story_input")):
        source = str(value or "")
        group = []
        previous_end = -1
        for token in _LATIN_TOKEN.finditer(source):
            word = token.group()
            named = word[0].isupper() and word.casefold() not in _GENERIC_TITLE_WORDS
            adjacent = previous_end >= 0 and bool(re.fullmatch(r"[ \t-]+", source[previous_end:token.start()]))
            if not named or not adjacent:
                if group:
                    names.append(" ".join(group))
                group = []
            if named:
                group.append(word)
            previous_end = token.end()
        if group:
            names.append(" ".join(group))
    return names[:64]


def story_content_instruction(job):
    anchors = requested_story_names(job)
    return (
        "STORY CONTENT CONTRACT v1 — แยกเนื้อเรื่องออกจากรูปแบบภาพ: "
        "คงตัวละคร ชื่อ จักรวาล เหตุการณ์ และความสัมพันธ์ตามเรื่องที่ผู้ใช้ให้มา "
        "การเลือกอนิเมะ/3D/คอมิกเปลี่ยนเฉพาะวิธีวาด ไม่อนุญาตให้แทนตัวละครด้วยคนทั่วไปหรือตัวละครใหม่ "
        "รักษา visual_identity ของตัวละคร; ไม่อ้างอิงใบหน้าของนักแสดงโดยอัตโนมัติ เว้นแต่ผู้ใช้ขอไว้ชัดเจน.\n"
        "ส่ง story_entities เป็น array ของ {id,name,aliases,visual_identity}; id ไม่ซ้ำ, name คือชื่อเดิม, "
        "aliases เป็น array ของชื่อเรียก/คำอ่านไทยที่ใช้จริง, visual_identity เป็นข้อความหรือ object อธิบายภาพจำเดิม. "
        "ชื่อใน registry และ scene_prompts คงตัวตนเดิม; pronunciation_notes ใช้เฉพาะคำอ่านเสียง/ซับ ไม่ใช่การเปลี่ยนชื่อตัวละครในภาพ.\n"
        f"ส่ง scene_entities เป็น array จำนวน {int(job.get('scene_count') or 0)} รายการตรงกับ scene_prompts/scene_narrations; "
        "แต่ละรายการเป็น array ของ id ที่มีอยู่จริงใน story_entities และอยู่ในฉากนั้น "
        "ทุก id ต้องมี name หรือ alias ปรากฏใน scene_prompt เดียวกัน "
        "ถ้าใช้คำบรรยายรูปลักษณ์แทนชื่อ ให้ใส่ canonical name ของ id นั้นในวงเล็บกำกับวลีเดิม ไม่ใช้เพียงคำอธิบายแทนชื่อ "
        "scene_entities ระบุเฉพาะตัวตนที่มองเห็นในภาพ; บทเล่าสามารถพูดถึงตัวละครนอกจอได้โดยไม่ต้องใส่ในภาพ "
        "ฉากวิวที่ไม่มีตัวละครใช้ [] ได้ และเรื่องที่ไม่มีชื่อเฉพาะใช้ story_entities=[] ได้.\n"
        "ชื่อที่ผู้ใช้ระบุใน Character Bible/ช่องชื่อชัดเจน ต้องเป็น canonical name ใน registry และคงไว้ใน scene_prompts หรือ visual_bible: "
        + json.dumps(anchors, ensure_ascii=False)
        + "\nสำหรับชื่อที่ระบุชัดนี้ ห้ามซ่อนชื่อเดิมไว้แค่ aliases แล้วเปลี่ยน canonical name เป็นตัวละครทั่วไป; "
        "ภาพใช้ canonical name, alias ที่ผู้ใช้ให้มา หรือคำอ่านไทยใน pronunciation_notes ของ canonical name นั้นได้."
        + "\nการตรวจอัตโนมัติตรวจโครงสร้างและชื่อที่ตรงกันเท่านั้น ไม่ได้ยืนยันความถูกต้องเชิงความหมายหรือรายละเอียดภาพทั้งหมด."
    )


class StoryContentError(ValueError):
    code = "STORY_CONTENT_MISMATCH"

    def __init__(self, issues):
        self.issues = issues
        super().__init__(self.code + ": " + "; ".join(row["message"] for row in issues[:8]))


def _story_canonical_id_binding_phrase(prompt, entity_id, entities, scene_ids):
    """Verify exact declared ID evidence; never infer identity from a description."""
    if (not isinstance(prompt, str) or not isinstance(entity_id, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+", entity_id)
            or len(entity_id) > 80 or not isinstance(scene_ids, list) or entity_id not in scene_ids
            or prompt.count(entity_id) != 1):
        return None
    position = prompt.index(entity_id)
    def token_character(character):
        return bool(character and (character in "_-" or unicodedata.category(character)[0] in "LMN"))
    if (token_character(prompt[position - 1] if position else "")
            or token_character(prompt[position + len(entity_id):position + len(entity_id) + 1])):
        return None
    entity = next((row for row in entities if row["id"] == entity_id), None)
    if not entity or sum(_normalized_name(row["id"]) == _normalized_name(entity_id) for row in entities) != 1:
        return None
    for token in re.findall(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+", prompt):
        if token not in scene_ids or not any(row["id"] == token for row in entities):
            return None
    prefix = re.split(r"[.!?;\n]", prompt[:position])[-1]
    suffix = re.split(r"[.!?;\n]", prompt[position + len(entity_id):])[0]
    clause = prefix + entity_id + suffix
    display_aliases = _story_unambiguous_display_aliases(entities)
    for other in entities:
        if other["id"] == entity_id:
            continue
        if any(contains_story_name(entity_id, name)
               or _normalized_name(name) == _normalized_name(entity["name"])
               or contains_story_name(clause, name)
               for name in [other["name"], *other.get("aliases", []), *display_aliases[other["id"]]]):
            return None
    if (re.search(r"(?:\b(?:no|not|without|exclud(?:e[sd]?|ing)|avoid|omit|remove|replace|instead|rather|negative)\b|ไม่|ห้าม|ไร้|ปราศจาก|ยกเว้น|แทน)[^,.!?;\n]{0,100}$", prefix, re.I)
            or re.search(r"^[\s,:(]*(?:(?:is|are|was|were|should|must|will|would|can|could|does)\s+){0,3}(?:not\b|absent\b|excluded\b|omitted\b|removed\b|missing\b|replaced\b|ไม่|ห้าม|ถูกแทน)", suffix, re.I)):
        return None
    return entity_id


def validate_story_name_repair(result, entities, scenes, anchors=()):
    """Verify local name insertions before persisting their audit trail."""
    value = result.get("story_content_name_repair")
    if value is None:
        return {}
    def fail():
        raise StoryContentError([{"code": "INVALID_NAME_REPAIR", "message": "หลักฐานการเติมชื่อในแผนไม่ตรงกับคำบรรยายฉาก"}])
    if (not isinstance(value, dict) or set(value) != {"version", "changes"}
            or type(value.get("version")) is not int or value["version"] != 1
            or not isinstance(value.get("changes"), list) or not 1 <= len(value["changes"]) <= 12):
        fail()
    if len(json.dumps(value, ensure_ascii=False)) > 200000:
        fail()
    registry = {entity["id"]: entity for entity in entities}
    display_aliases = _story_unambiguous_display_aliases(entities)
    seen, latest = set(), {}
    prompts = result.get("scene_prompts", [])
    for change in value["changes"]:
        keys = {"scene_index", "entity_id", "name", "phrase", "before", "after"}
        canonical = isinstance(change, dict) and change.get("method") == "canonical_entity_id"
        if not isinstance(change, dict) or set(change) != (keys | {"method"} if canonical else keys):
            fail()
        index, entity_id = change["scene_index"], change["entity_id"]
        if (type(index) is not int or not 1 <= index <= len(scenes) or not isinstance(entity_id, str)
                or entity_id not in registry or entity_id not in scenes[index - 1] or (index, entity_id) in seen):
            fail()
        name, phrase, before, after = (change[key] for key in ("name", "phrase", "before", "after"))
        if (not all(isinstance(item, str) for item in (name, phrase, before, after))
                or name != registry[entity_id]["name"] or not (1 if canonical else 12) <= len(phrase.strip()) <= 1000
                or before.count(phrase) != 1 or len(before) > 40000 or len(after) > 40202
                or after != before.replace(phrase, phrase + " (" + name + ")", 1)
                or (index in latest and latest[index] != before)):
            fail()
        if canonical and (phrase != entity_id
                or any(_normalized_name(name) == _normalized_name(anchor) for anchor in anchors)
                or _story_canonical_id_binding_phrase(before, entity_id, entities, scenes[index - 1]) != phrase):
            fail()
        if any(contains_story_name(phrase, alias)
               for other in entities if other["id"] != entity_id
               for alias in [other["name"], *other["aliases"], *display_aliases[other["id"]]]):
            fail()
        latest[index] = after
        seen.add((index, entity_id))
    if any(prompts[index - 1] != after for index, after in latest.items()):
        fail()
    return {"story_content_name_repair": copy.deepcopy(value)}


def validate_story_content(job, result):
    """Return independent registry/mapping copies or fail before media writes."""
    contract = job.get("story_content_contract")
    required = isinstance(contract, dict) and type(contract.get("version")) is int and contract["version"] == 1
    supplied = "story_entities" in result or "scene_entities" in result
    if not required and not supplied:
        return {}
    issues = []

    def issue(code, message, scene=None):
        row = {"code": code, "message": message}
        if scene is not None:
            row["scene"] = scene
        issues.append(row)

    raw_entities = result.get("story_entities")
    raw_scenes = result.get("scene_entities")
    count = int(job.get("scene_count") or 0)
    if not isinstance(raw_entities, list) or len(raw_entities) > 64:
        issue("INVALID_STORY_ENTITIES", "story_entities ต้องเป็น array ไม่เกิน 64 รายการ")
    if not isinstance(raw_scenes, list) or len(raw_scenes) != count:
        issue("INVALID_SCENE_ENTITIES", f"scene_entities ต้องมี {count} รายการตรงกับฉาก")
    if issues:
        raise StoryContentError(issues)
    entities, by_id = [], {}
    for index, raw in enumerate(raw_entities, 1):
        if not isinstance(raw, dict):
            issue("INVALID_ENTITY", f"ตัวตนลำดับ {index} ต้องเป็น object")
            continue
        entity_id, name = raw.get("id"), raw.get("name")
        aliases = raw.get("aliases", [])
        identity = raw.get("visual_identity", "")
        if (not isinstance(entity_id, str) or not entity_id.strip() or len(entity_id) > 80
                or not isinstance(name, str) or not name.strip() or len(name) > 200):
            issue("INVALID_ENTITY", f"ตัวตนลำดับ {index} ต้องมี id และ name ที่ไม่ว่าง")
            continue
        entity_id, name = entity_id.strip(), name.strip()
        if entity_id in by_id:
            issue("DUPLICATE_ENTITY_ID", f"id ตัวตนซ้ำ: {entity_id}")
            continue
        if (not isinstance(aliases, list) or len(aliases) > 16
                or any(not isinstance(alias, str) or not alias.strip() or len(alias) > 200 for alias in aliases)):
            issue("INVALID_ENTITY_ALIASES", f"aliases ของ {name} ต้องเป็นชื่อไม่ว่างไม่เกิน 16 รายการ")
            continue
        try:
            identity_json = json.dumps(identity, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            identity_json = ""
        if (not isinstance(identity, (str, dict)) or not identity_json or len(identity_json) > 4000
                or (required and not (identity.strip() if isinstance(identity, str) else identity))):
            issue("INVALID_VISUAL_IDENTITY", f"visual_identity ของ {name} ต้องอธิบายภาพจำเดิมไม่เกิน 4000 ตัวอักษร")
            continue
        entity = {"id": entity_id, "name": name, "aliases": [alias.strip() for alias in aliases],
                  "visual_identity": copy.deepcopy(identity)}
        entities.append(entity)
        by_id[entity_id] = entity
    prompts = result.get("scene_prompts") if isinstance(result.get("scene_prompts"), list) else []
    anchors = requested_story_names(job)
    source_aliases = story_source_aliases(job)
    notes = result.get("pronunciation_notes") if isinstance(result.get("pronunciation_notes"), dict) else {}
    display_aliases = _story_unambiguous_display_aliases(entities)

    def image_aliases(entity):
        name = entity["name"]
        if not any(_normalized_name(name) == _normalized_name(anchor) for anchor in anchors):
            return [name, *entity["aliases"], *display_aliases[entity["id"]]]
        approved = [alias for key, aliases in source_aliases.items() if _normalized_name(key) == _normalized_name(name) for alias in aliases]
        for key, reading in notes.items():
            if (_normalized_name(key) == _normalized_name(name) and isinstance(reading, str)
                    and re.search(r"[ก-๙]", reading) and not re.search(r"[A-Za-z]", reading)):
                approved.append(reading)
        return [name, *approved]
    if len(prompts) != count:
        issue("INVALID_SCENE_PROMPTS", f"scene_prompts ต้องมี {count} รายการตรงกับฉาก")
    scenes = []
    for index, raw in enumerate(raw_scenes, 1):
        if (not isinstance(raw, list) or len(raw) > 64
                or any(not isinstance(value, str) or not value.strip() or len(value) > 80 for value in raw)):
            issue("INVALID_SCENE_ENTITY_IDS", "รายการตัวตนของฉากต้องเป็น array ของ id", index)
            scenes.append([])
            continue
        ids = [value.strip() for value in raw]
        if len(set(ids)) != len(ids):
            issue("DUPLICATE_SCENE_ENTITY", "ฉากอ้างอิง id ซ้ำ", index)
        prompt = str(prompts[index - 1] or "") if index <= len(prompts) else ""
        for entity_id in ids:
            entity = by_id.get(entity_id)
            if not entity:
                issue("UNKNOWN_SCENE_ENTITY", f"ไม่พบ id {entity_id} ใน story_entities", index)
            elif not any(contains_story_name(prompt, alias) for alias in image_aliases(entity)):
                issue("ENTITY_MISSING_FROM_PROMPT", f"ภาพฉากนี้ไม่ได้อ้างชื่อหรือ alias ของ {entity['name']}", index)
        scenes.append(ids)
    visual_text = "\n".join(str(row) for row in prompts) + "\n" + json.dumps(result.get("visual_bible") or {}, ensure_ascii=False)
    for name in anchors:
        matching = [entity for entity in entities if _normalized_name(name) == _normalized_name(entity["name"])]
        if not matching:
            issue("REQUESTED_NAME_MISSING", f"ชื่อจากข้อมูลผู้ใช้ยังไม่อยู่ใน story_entities: {name}")
        elif not any(contains_story_name(visual_text, alias) for entity in matching for alias in image_aliases(entity)):
            issue("REQUESTED_NAME_GENERICIZED", f"ข้อมูลภาพไม่ได้คงชื่อหรือ alias จากเรื่อง: {name}")
    if issues:
        raise StoryContentError(issues)
    return {"story_entities": entities, "scene_entities": scenes,
            **validate_story_name_repair(result, entities, scenes, anchors)}


def story_content_review(job):
    """Build an on-demand report from a job dict; never save or invalidate it."""
    contract = job.get("story_content_contract")
    current = isinstance(contract, dict) and type(contract.get("version")) is int and contract["version"] == STORY_CONTENT_VERSION
    result = {"status": "pending", "issues": [], "entities": [], "scene_entities": [],
              "verification": "structural_only"}
    if not job.get("scene_prompts") and not job.get("story_entities"):
        if not current:
            result["status"] = "legacy"
        return result
    if not current and "story_entities" not in job and "scene_entities" not in job:
        result["status"] = "legacy"
        names = requested_story_names(job)
        inferred = _inferred_story_names(job)
        notes = job.get("pronunciation_notes") if isinstance(job.get("pronunciation_notes"), dict) else {}
        source_text = str(job.get("topic") or "") + "\n" + str(job.get("story_input") or "")
        names += [name for name in notes if any(contains_story_name(candidate, name) for candidate in inferred)
                  and contains_story_name(source_text, name)]
        for index, prompt in enumerate(job.get("scene_prompts") or [], 1):
            text = str(prompt or "")
            substitution = re.search(
                r"original\s+(?:character|hero)|generic\s+(?:character|hero)|ไม่มีหน้ากาก|"
                r"ห้าม[^\n]{0,80}(?:แฟรนไชส์|ชื่อตัวละคร)|ตัวละครต้นฉบับ", text, re.I,
            )
            if names and substitution and not any(contains_story_name(text, name) for name in names):
                result["issues"].append({"code": "LEGACY_POSSIBLE_SUBSTITUTION", "scene": index,
                                         "message": "คำสั่งภาพเดิมมีข้อความออกแบบตัวละครทั่วไป แต่ไม่พบชื่อจากเรื่อง ควรตรวจฉากนี้"})
        if result["issues"]:
            result["status"] = "needs_review"
        return result
    try:
        clean = validate_story_content(job, job)
        result.update(status="ready" if current else "legacy", entities=clean.get("story_entities", []),
                      scene_entities=clean.get("scene_entities", []))
    except StoryContentError as exc:
        result.update(status="needs_review", issues=copy.deepcopy(exc.issues))
    return result
