"""Conservative, scene-scoped check of speech actually heard in provider clips.

The subtitle transcript is the evidence.  A repeated short word is not enough
to reject a clip: require a substantial, non-overlapping phrase that appears
once in the saved script but at least twice inside the same scene's audio.
"""
import hashlib
import unicodedata

SPEECH_DELIVERY_CORRECTION = ('\nSPEECH DELIVERY CORRECTION: Speak the saved line exactly once in one continuous take. '
                              'Do not restart, echo, loop, or repeat any words or clause. '
                              'Keep the same image, scene action, product, and intended meaning.')


def retry_prompt(prompt):
    prompt = str(prompt or '')
    return prompt if SPEECH_DELIVERY_CORRECTION in prompt else prompt + SPEECH_DELIVERY_CORRECTION


def _normal(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return ''.join(char for char in value if char.isalnum() or unicodedata.category(char).startswith('M'))


def _nonoverlapping(text, phrase):
    count, offset = 0, 0
    while phrase:
        found = text.find(phrase, offset)
        if found < 0:
            break
        count += 1
        offset = found + len(phrase)
    return count


def _scene_texts(segments, durations):
    boundaries, end = [], 0.0
    for duration in durations:
        end += float(duration)
        boundaries.append(end)
    grouped = [[] for _ in durations]
    for cue in segments or []:
        try:
            midpoint = (float(cue['start']) + float(cue['end'])) / 2
        except (KeyError, TypeError, ValueError):
            continue
        if midpoint < 0:
            continue
        for index, boundary in enumerate(boundaries):
            if midpoint < boundary + (0.15 if index == len(boundaries) - 1 else 0):
                grouped[index].append(str(cue.get('text') or ''))
                break
    return [_normal(''.join(items)) for items in grouped]


def _duplicate(actual, expected, minimum=16):
    """Return only a long repeat of an expected once-only phrase."""
    if len(actual) < minimum * 2 or len(expected) < minimum:
        return ''
    # Searching longest first yields useful evidence and avoids reporting a
    # tiny substring of a much clearer repeated clause.
    for size in range(min(36, len(expected), len(actual) // 2), minimum - 1, -1):
        seen = set()
        for offset in range(len(expected) - size + 1):
            phrase = expected[offset:offset + size]
            if phrase in seen or _nonoverlapping(expected, phrase) != 1:
                continue
            seen.add(phrase)
            if _nonoverlapping(actual, phrase) >= 2:
                return phrase
    return ''


def audit_native_scene_speech(transcript, narrations, durations, composed_duration=None):
    """Return a durable, serializable result; never infer success from silence.

    `durations` must describe the actual composed scene segments, not the
    planned durations. Ambiguous timing is skipped rather than guessed.
    """
    if len(narrations) != len(durations) or not narrations:
        return {'status': 'unverified', 'reason': 'scene_boundaries_missing', 'findings': []}
    try:
        lengths = [float(value) for value in durations]
    except (TypeError, ValueError):
        return {'status': 'unverified', 'reason': 'scene_boundaries_invalid', 'findings': []}
    if any(length <= 0 for length in lengths):
        return {'status': 'unverified', 'reason': 'scene_boundaries_invalid', 'findings': []}
    if composed_duration is not None and abs(sum(lengths) - float(composed_duration)) > max(.4, len(lengths) * .15):
        return {'status': 'unverified', 'reason': 'scene_boundaries_mismatch', 'findings': []}
    actual_scenes = _scene_texts(transcript.get('segments') or [], lengths)
    findings = []
    for index, (expected_raw, actual) in enumerate(zip(narrations, actual_scenes), 1):
        expected = _normal(expected_raw)
        repeated = _duplicate(actual, expected)
        if repeated:
            findings.append({
                'scene': index,
                'phrase': repeated,
                'actual_count': _nonoverlapping(actual, repeated),
                'expected_count': 1,
                'expected_sha256': hashlib.sha256(expected.encode()).hexdigest(),
            })
    return {'version': 1, 'status': 'repeat_confirmed' if findings else 'no_clear_repeat',
            'findings': findings, 'source_sha256': str(transcript.get('source_sha256') or '')}


class RepeatedNativeSpeechError(ValueError):
    def __init__(self, audit):
        self.audit = audit
        scenes = ', '.join(str(row['scene']) for row in audit['findings'])
        super().__init__(f'FLOW_SPEECH_REPEAT • ฉาก {scenes} พูดประโยคซ้ำจากบทที่บันทึก • เก็บคลิปเดิมไว้ตรวจ')
