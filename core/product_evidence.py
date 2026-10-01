"""Frozen product evidence, not a claim that seller copy was independently verified."""
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def compact(value):
    return re.sub(r'\s+', '', str(value or '')).casefold()


_DIMENSION = re.compile(r'(\d+(?:\.\d+)?)\s*(?:x|×|\*|คูณ)\s*(\d+(?:\.\d+)?)\s*(นิ้ว|inches?|inch|ซม\.?|cm|เมตร|meters?|m)', re.I)


def dimensions(text):
    # Only explicit paired dimensions with one shared unit; no inferred variant.
    rows = []
    for match in _DIMENSION.finditer(str(text or '')):
        unit = match[3].lower()
        factor = 2.54 if unit in ('นิ้ว', 'inch', 'inches') else 100 if unit in ('เมตร', 'm', 'meter', 'meters') else 1
        rows.append(tuple(sorted(round(float(match[i]) * factor, 3) for i in (1, 2))))
    return rows


def snapshot(job):
    product = job.get('product_story') or {}
    records = []
    for key in ('name', 'description', 'price'):
        text = str(product.get(key) or '').strip()[:3000]
        if text:
            records.append({'id': 'listing_' + key, 'text': text, 'source': 'saved_listing',
                            'status': 'seller_claim' if key != 'price' else 'listed_price'})
    images = [{'id': 'reference_' + str(i + 1), 'file': str(file),
               'kind': (product.get('reference_roles') or [])[i]
               if i < len(product.get('reference_roles') or []) else 'unknown'}
              for i, file in enumerate(job.get('source_images') or [])]
    dims = [d for row in records for d in dimensions(row['text'])]
    conflicts = ['dimensions'] if len(set(dims)) > 1 else []
    return {'version': 1, 'records': records, 'images': images,
            'selected_variant': product.get('selected_variant') or None,
            'missing': [key for key in ('name', 'description', 'price') if not product.get(key)],
            'conflicts': conflicts, 'provenance': 'saved_product_snapshot_not_independent_verification'}


def allowed_numbers(evidence):
    return {match for row in evidence['records'] for match in re.findall(r'\d+(?:\.\d+)?', row['text'])}


def quantities(text):
    units = {'นิ้ว': (2.54, 'cm'), 'inch': (2.54, 'cm'), 'inches': (2.54, 'cm'),
             'เมตร': (100, 'cm'), 'm': (100, 'cm'), 'meter': (100, 'cm'), 'meters': (100, 'cm'),
             'ซม': (1, 'cm'), 'cm': (1, 'cm'), 'บาท': (1, 'THB'), 'baht': (1, 'THB'),
             'กิโลกรัม': (1000, 'g'), 'kg': (1000, 'g'), 'กรัม': (1, 'g'), 'g': (1, 'g')}
    result = []
    for match in re.finditer(r'(\d+(?:\.\d+)?)\s*(' + '|'.join(sorted(units, key=len, reverse=True)) + r')(?![a-z])', str(text), re.I):
        factor, unit = units[match[2].lower()]
        result.append((round(float(match[1]) * factor, 3), unit))
    for pair in dimensions(text):
        result.extend((value, 'cm') for value in pair)
    return result


def unsupported_quantity(evidence, text):
    supported = {q for row in evidence['records'] for q in quantities(row['text'])}
    pairs = {d for row in evidence['records'] for d in dimensions(row['text'])}
    return bool(set(quantities(text)) - supported or set(dimensions(text)) - pairs)


def numeric_conflict(evidence, observations):
    # AI observations can veto a claim, NEVER certify it. No OCR or external call.
    dims = [d for row in evidence['records'] for d in dimensions(row['text'])]
    image_ids = {row['id'] for row in evidence['images']}
    for row in observations if isinstance(observations, list) else []:
        if isinstance(row, dict) and row.get('reference_id') in image_ids:
            dims.extend(dimensions(row.get('text')))
    return bool(evidence['conflicts'] or len(set(dims)) > 1)
