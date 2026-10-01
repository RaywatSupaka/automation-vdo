"""Opt-in first-person product review; no migration or provider actions."""
import json


VISUAL_INSTRUCTION = (
    'POINTING REVIEW v1: First-person handheld-camera product review (camera-holder POV), '
    'not an object narrating and not a third-person shot of a camera operator. '
    'Keep the referenced product as the main subject with its exact shape, color, branding and visible details. '
    'Show only one anatomically natural hand/forearm entering from the frame edge; its index finger points '
    'to one real visible detail relevant to this scene, without covering the product or its important label. '
    'The reviewer stays behind the camera: no visible face, full-body presenter or lip-sync. '
    'Keep the same hand/forearm and relevant sleeve appearance across scenes; do not add extra hands, '
    'fingers, jewelry, arrows or pointer graphics. Do not copy unrelated objects from framing examples. '
    'Use gentle handheld motion, short pointing gestures and natural rests; vary the detail and distance '
    'according to each saved scene, not the same frozen pointing pose throughout. '
    'Demonstrate only supported uses; never invent product facts, test results, prices or testimonials. '
    'Preserve the saved scene count, aspect ratio, speech and audio mode. These are visual directions, '
    'not words to speak. Keep this POV in image, motion and recovery requests.'
)


def enabled(job):
    options = job.get('product_script_options') or {}
    return (job.get('product_short') is True and isinstance(options, dict)
            and type(options.get('version')) is int and options['version'] == 3
            and options.get('style') == 'pointing_review')


def visual_instruction(job):
    return VISUAL_INSTRUCTION if enabled(job) else ''


def apply_visual(job, prompt):
    text = visual_instruction(job)
    return prompt + '\n' + text if text and text not in prompt else prompt


def native_audio(job, index, prompt=''):
    """One saved voice behind the camera; never turn the hand into a speaker."""
    lines = job.get('scene_narrations') or job.get('spoken_script_segments') or []
    line = lines[index - 1] if 0 < index <= len(lines) else ''
    if isinstance(line, dict):
        line = line.get('text') or line.get('script') or ''
    if not str(line).strip():
        return ('\nPOINTING REVIEW AUDIO: No speech is saved for this scene. '
                'Do not invent speech, vocals or a visible speaking presenter.')
    text = ('\nPOINTING REVIEW AUDIO: One reviewer holding the camera speaks the exact saved Thai line once '
            'from behind the camera. No visible face, synchronized mouth movement, second speaker or extra words. '
            'Do not read visual directions or add burned-in subtitles. Spoken line: '
            + json.dumps(str(line), ensure_ascii=False))
    return '' if text in prompt else text
