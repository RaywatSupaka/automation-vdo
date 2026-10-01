"""Presentation contract for text analysis, never image/video generation.

Markdown paragraphs can consume JSON escapes before a browser reader sees them.
Persist this rule in the canonical request, not in an untracked Send suffix.
"""

ANALYSIS_JSON_FORMAT = (
    '[SmartFlow analysis JSON v1] Return exactly one JSON object inside one '
    '```json code block, with no prose outside it. The code block is only a '
    'transport wrapper; preserve every required field and scene. Use valid JSON '
    'string escaping, including embedded quotation marks in product names and '
    'dialogue. Do not change names or content merely to avoid quotes. Do not '
    'create images or videos in this text-analysis response.'
)


def analysis_json_prompt(prompt):
    """Apply only while building a new request; never rewrite an owned send."""
    prompt = str(prompt).rstrip()
    if prompt.endswith(ANALYSIS_JSON_FORMAT):
        return prompt
    return prompt + '\n\n' + ANALYSIS_JSON_FORMAT
