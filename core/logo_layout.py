"""Versioned local logo placement. Missing layouts always mean legacy anchors."""
import copy
import math


PROFILE_SIZES = {'portrait': (720, 1280), 'landscape': (1920, 1080)}


def normalize_logo_layout(value):
    if value is None:
        return None
    if not isinstance(value, dict) or type(value.get('version')) is not int or value.get('version') != 1:
        raise ValueError('รูปแบบตำแหน่งโลโก้ไม่รองรับ')
    result = {'version': 1}
    for name in PROFILE_SIZES:
        profile = value.get(name)
        if not isinstance(profile, dict):
            raise ValueError('ตำแหน่งโลโก้ต้องมีทั้งแนวตั้งและแนวนอน')
        row = {}
        for key, low, high in (('x', 0, 1), ('y', 0, 1), ('size_percent', 3, 60)):
            number = profile.get(key)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not low <= number <= high:
                raise ValueError('ค่าตำแหน่งหรือขนาดโลโก้ไม่ถูกต้อง')
            row[key] = float(number)
        result[name] = row
    return result


def logo_profile(width, height):
    return 'landscape' if width > height else 'portrait'


def pixel_round(value):
    """Positive half-up rounding, shared with the browser's Math.round."""
    return int(math.floor(value + 0.5))


def logo_geometry(layout, width, height, logo_width, logo_height):
    layout = normalize_logo_layout(layout)
    if not layout or min(width, height, logo_width, logo_height) <= 0:
        raise ValueError('ขนาดภาพหรือตำแหน่งโลโก้ไม่ถูกต้อง')
    row = layout[logo_profile(width, height)]
    desired = max(8, pixel_round(width * row['size_percent'] / 100))
    scale = min(desired / logo_width, width / logo_width, height / logo_height)
    w = max(1, min(width, pixel_round(logo_width * scale)))
    h = max(1, min(height, pixel_round(logo_height * scale)))
    x = max(0, min(width - w, pixel_round(row['x'] * width - w / 2)))
    y = max(0, min(height - h, pixel_round(row['y'] * height - h / 2)))
    return {'x': x, 'y': y, 'width': w, 'height': h}


def frozen_logo_config(config, *snapshots):
    """Only an explicit saved layout may activate free placement for a job."""
    result = dict(config)
    result.pop('logo_layout', None)
    for saved in snapshots:
        if isinstance(saved, dict) and 'logo_layout' in saved:
            result['logo_layout'] = normalize_logo_layout(copy.deepcopy(saved['logo_layout']))
    return result


def logo_render_options(config):
    options = {'opacity': float(config.get('logo_opacity', .65)),
               'size_percent': float(config.get('logo_size_percent', 16)),
               'position': str(config.get('logo_position', 'top_right')),
               'margin': int(config.get('logo_margin', 28))}
    layout = normalize_logo_layout(config.get('logo_layout'))
    if layout is not None:
        options['layout'] = layout
    return options
