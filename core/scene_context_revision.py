"""Validated, non-destructive story variants for a failed Flow scene."""
import copy
import hashlib
import json
import re
from core.atomic_json import AtomicJsonFile


class DuplicateSceneRevision(ValueError):
    """A valid proposal repeats an old event; ask for a new proposal, not media."""


def normalized(value):
    return re.sub(r'\s+', '', str(value or '')).casefold()


def validate_revision(candidate, context, previous):
    if not isinstance(candidate, dict) or candidate.get('needs_review') is not False:
        raise ValueError('AI ยังไม่ยืนยันเนื้อเรื่องใหม่')
    # Proposal concerns a NEW image. A changed event may intentionally not
    # match the old composition; the later motion gate validates the new image.
    if (type(candidate.get('reference_compatible')) is not bool
            or type(candidate.get('material_change')) is not bool
            or (context.get('creative_revision_version') != 1
                and candidate['reference_compatible'] is False and candidate['material_change'] is not True)):
        raise ValueError('ข้อมูลเนื้อเรื่องใหม่ไม่ครบ')
    clean = {}
    for key, minimum, maximum in [('prompt', 40, 2500), ('scene_narration', 10, 2000), ('context_summary', 10, 1000)]:
        text = candidate.get(key)
        if not isinstance(text, str) or not minimum <= len(text.strip()) <= maximum:
            raise ValueError('เนื้อเรื่องใหม่ขาด ' + key)
        clean[key] = text.strip()
    if context.get('creative_revision_version') == 1 and context.get('actor_dialogue'):
        turns = candidate.get('scene_dialogue_turns')
        if not isinstance(turns, list) or len(turns) > 3 or any(not isinstance(turn, dict) for turn in turns):
            raise ValueError('ฉากใหม่ต้องมี scene_dialogue_turns 0–3 ช่วงสำหรับนักแสดง หรือ [] ถ้าเงียบ')
        clean.update(dialogue_revision_version=1, scene_dialogue_turns=copy.deepcopy(turns))
    old = [context.get('story_beat', '')] + [row.get('scene_narration', '') for row in previous]
    if normalized(clean['scene_narration']) in {normalized(item) for item in old}:
        raise DuplicateSceneRevision('AI เสนอเนื้อเรื่องเดิมที่เคยใช้แล้ว')
    if normalized(clean['context_summary']) in {normalized(row.get('context_summary')) for row in previous}:
        raise DuplicateSceneRevision('AI เสนอบริบทเดิมที่เคยใช้แล้ว')
    clean['revision_hash'] = hashlib.sha256(normalized(clean['scene_narration']).encode()).hexdigest()
    if clean.get('dialogue_revision_version') == 1:
        clean['revision_hash'] = hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return clean


def revised_story(job, rows):
    """Build render-only text without overwriting original analysis/media.

    Legacy dialogue edits require an exact contiguous old-scene match. New
    actor revisions carry explicit scene-indexed turns and revalidate the plan;
    never guess which character's words to remove from an unindexed script.
    """
    result = copy.deepcopy(job)
    beats = list(result.get('scene_narrations') or [])
    turns = list(result.get('dialogue_turns') or [])
    changed = []
    revised_dialogue = False
    for key, row in sorted(rows.items(), key=lambda item: int(item[0])):
        revision = row.get('revision')
        if row.get('phase') != 'ready' or not revision:
            continue
        index = int(key) - 1
        if not 0 <= index < len(beats):
            raise ValueError('ฉากเปลี่ยนบทไม่ตรงงาน')
        old, new = beats[index], revision['scene_narration']
        if result.get('actor_dialogue'):
            if revision.get('dialogue_revision_version') == 1:
                groups = result.get('scene_dialogue_turns')
                if not isinstance(groups, list) or len(groups) != len(beats):
                    raise ValueError('บทนักแสดงเดิมไม่ครบ ไม่เดาการจับคู่ฉาก')
                groups[index] = copy.deepcopy(revision['scene_dialogue_turns'])
                revised_dialogue = True
            # Legacy revisions remain visual-only. New explicitly authorized
            # revisions replace just this scene's dialogue, never the old job.
            beats[index] = new
            changed.append(revision['revision_hash'])
            continue
        if turns and old != new:
            matches = []
            for start in range(len(turns)):
                joined = ''
                for end in range(start, len(turns)):
                    joined += normalized(turns[end].get('text'))
                    if joined == normalized(old):
                        matches.append((start, end + 1))
                    if len(joined) >= len(normalized(old)):
                        break
            if len(matches) != 1:
                raise ValueError('ยังจับคู่บทพูดฉากเดิมไม่ได้ ไม่ใช้เสียงเก่ากับเรื่องใหม่')
            start, end = matches[0]
            turns[start:end] = [{'speaker': 'ผู้บรรยาย', 'text': new, 'emotion': 'normal', 'pause_after': .4}]
        beats[index] = new
        groups = result.get('scene_dialogue_turns')
        if isinstance(groups,list) and len(groups)==len(beats):
            groups[index] = [{'speaker':'ผู้บรรยาย','text':new,'emotion':'normal','pause_after':.4}]
        changed.append(revision['revision_hash'])
    if changed:
        result.update(scene_narrations=beats, narration_script=result.get('narration_script', '') if result.get('actor_dialogue') else '\n'.join(beats), dialogue_turns=turns,
                      flow_story_revision=':'.join(changed))
    if revised_dialogue:
        from core.story_performance import validate_plan
        result = validate_plan(job, result)
    if changed:
        from core.speech_delivery import freeze_plan
        from core.product_editorial import rebind_revision
        rebind_revision(job, result, ':'.join(changed))
        freeze_plan(result)
    return result


def render_story(folder, job):
    rows = AtomicJsonFile(folder / 'prompts' / 'flow_replacement.json').read({}).get('scenes', {})
    return revised_story(job, rows)
