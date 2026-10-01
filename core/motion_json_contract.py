"""Serialization guidance shared by motion planning and its bounded repair."""
import json


def motion_json_contract(context):
    example = {
        'job_id': context['job_id'], 'index': context['index'],
        'context_id': context['context_id'],
        'prompt': 'One continuous camera move. Spoken line: "ตัวอย่างบทพูด". All spoken dialogue must be in Thai only.',
        'needs_review': True, 'reference_compatible': False,
        'material_change': False, 'review_reason': 'Example only; evaluate the actual reference and request.',
    }
    return (
        'JSON SERIALIZATION: Return one parseable JSON object, not a JSON-encoded string. '
        'Inside a JSON string, escape every literal double quote as backslash-double-quote '
        '(\\") and every literal backslash as two backslashes. Do not put unescaped dialogue '
        'quotation marks inside prompt. Prefer Spoken line: followed by the exact supplied Thai '
        'words without surrounding quotation marks. Preserve the words and all content decisions. '
        'Use real booleans, not strings. Check that the whole response parses as JSON before sending. '
        'The following is a syntax example with this request\'s identifiers, NOT scene content or '
        'approval defaults; replace prompt and review flags according to the actual evidence:\n'
        + json.dumps(example, ensure_ascii=False)
    )
