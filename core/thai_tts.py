import re
import unicodedata


_DIGIT_WORDS = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
_PLACE_WORDS = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน"]
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_PAUSE_PATTERN = re.compile(r"\[pause:(0\.[2-9]|[12](?:\.\d+)?|3(?:\.0+)?)\]", re.I)
_VOICE_TAG_PATTERN = re.compile(
    r"\[(?:pause:(?:0\.[2-9]|[12](?:\.\d+)?|3(?:\.0+)?)|"
    r"laughter|sigh|surprise-ah|question-ah|dissatisfaction-hnn)\]",
    re.I,
)


def _under_million(number):
    if number == 0:
        return ""
    digits = str(number)
    parts = []
    length = len(digits)
    for index, raw_digit in enumerate(digits):
        digit = int(raw_digit)
        place = length - index - 1
        if digit == 0:
            continue
        if place == 1 and digit == 1:
            parts.append("สิบ")
        elif place == 1 and digit == 2:
            parts.append("ยี่สิบ")
        elif place == 0 and digit == 1 and length > 1:
            parts.append("เอ็ด")
        else:
            parts.append(_DIGIT_WORDS[digit] + _PLACE_WORDS[place])
    return "".join(parts)


def thai_number_words(value):
    """Convert an integer or decimal string into speech-friendly Thai words."""
    raw = str(value if value is not None else "").translate(_THAI_DIGITS).replace(",", "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return str(value)
    whole, dot, decimal = raw.partition(".")
    number = int(whole)
    if number == 0:
        result = "ศูนย์"
    else:
        groups = []
        while number:
            groups.append(number % 1_000_000)
            number //= 1_000_000
        spoken_groups = []
        for group_index in range(len(groups) - 1, -1, -1):
            group = groups[group_index]
            if group:
                spoken_groups.append(_under_million(group))
            if group_index:
                spoken_groups.append("ล้าน")
        result = "".join(spoken_groups)
    if dot and decimal:
        result += "จุด" + "".join(_DIGIT_WORDS[int(digit)] for digit in decimal)
    return result


_SPEECH_REPLACEMENTS = (
    # Common names/titles used by Story Shorts.  Keep these deterministic so a
    # completed image job is not blocked at the voice stage merely because the
    # story title contains an English proper name.
    (r"\bDoctor\b", "ด็อกเตอร์"),
    (r"\bDoom\b", "ดูม"),
    (r"\bSupreme\b", "ซูพรีม"),
    (r"\bHunter\s*[x×]\s*Hunter\b", "ฮันเตอร์ ฮันเตอร์"),
    (r"\bHunter\b", "ฮันเตอร์"),
    (r"\bGoogle\s+Flow\b", "กูเกิล โฟลว์"),
    (r"\bAction\s+Camera\b", "กล้องแอ็กชัน"),
    (r"\bFull\s*HD\b", "ฟูลเอชดี"),
    (r"\bGoPro\b", "โกโปร"),
    (r"\bShopee\b", "ช้อปปี้"),
    (r"\bBluetooth\b", "บลูทูธ"),
    (r"\bWi[\s-]*Fi\b", "ไวไฟ"),
    (r"\bUSB[\s-]*C\b", "ยูเอสบี ซี"),
    (r"\bAUX\b", "อ็อกซ์"),
    (r"\bUSB\b", "ยูเอสบี"),
    (r"\bLED\b", "แอลอีดี"),
    (r"\bTF\b", "ทีเอฟ"),
    (r"\bHDMI\b", "เอชดีเอ็มไอ"),
    (r"\bRGB\b", "อาร์จีบี"),
    (r"\bLCD\b", "แอลซีดี"),
    (r"\bNFC\b", "เอ็นเอฟซี"),
    (r"\bOLED\b", "โอแอลอีดี"),
    (r"\bGPS\b", "จีพีเอส"),
    (r"\bMAX\b", "แม็กซ์"),
    (r"\bAI\b", "เอไอ"),
    # Drama episode labels are commonly appended to titles by the series
    # manager.  They can also appear in the generated narration, so make the
    # label speech-ready instead of rejecting an otherwise valid Thai script.
    (r"\bEP\b", "อีพี"),
    (r"\bVoice\b", "วอยซ์"),
    (r"\b4K\b", "โฟร์เค"),
)


def _apply_pronunciation_notes(text, pronunciation_notes):
    """Apply safe AI-provided readings before the built-in vocabulary map."""
    if not isinstance(pronunciation_notes, dict):
        return text
    result = text
    entries = sorted(pronunciation_notes.items(), key=lambda item: len(str(item[0])), reverse=True)
    for raw_key, raw_value in entries:
        key = str(raw_key or "").strip()
        spoken = re.sub(r"[-–—]+", " ", str(raw_value or "").strip())
        spoken = re.sub(r"\s+", " ", spoken)
        if not key or len(key) > 80 or not re.search(r"[A-Za-z0-9]", key):
            continue
        if not spoken or len(spoken) > 160 or re.search(r"[A-Za-z0-9]", spoken):
            continue
        pattern = rf"(?<![A-Za-z0-9]){re.escape(key)}(?![A-Za-z0-9])"
        result = re.sub(pattern, spoken, result, flags=re.I)
    return result


def prepare_thai_tts_script(text, pronunciation_notes=None):
    """Return a TTS-friendly script plus issues requiring review.

    Supported pause tags are preserved. URLs, emoji, hashtags and difficult symbols
    are removed or spoken out. Known product/technology words are transliterated.
    Other English words remain intact for the selected voice engine to read;
    a missing Thai pronunciation entry is not a reason to stop narration.
    """
    # NFC preserves Thai SARA AM (ำ) as one character, which gives Thai TTS
    # engines a more natural input than the compatibility-decomposed form (ํา).
    source = unicodedata.normalize("NFC", str(text or "")).strip()
    if not source:
        return "", ["ยังไม่มีบทพูด"]

    pauses = []

    def protect_pause(match):
        pauses.append(match.group(0).lower())
        return f" พอสแท็ก{len(pauses) - 1} "

    script = _VOICE_TAG_PATTERN.sub(protect_pause, source)
    script = re.sub(r"https?://\S+|www\.\S+", " ลิงก์สินค้า ", script, flags=re.I)
    script = _apply_pronunciation_notes(script, pronunciation_notes)

    for pattern, replacement in _SPEECH_REPLACEMENTS:
        script = re.sub(pattern, replacement, script, flags=re.I)

    script = re.sub(
        r"([0-9๐-๙]+)\s*:\s*([0-9๐-๙]+)",
        lambda match: f"{thai_number_words(match.group(1))} ต่อ {thai_number_words(match.group(2))}",
        script,
    )

    script = re.sub(
        r"฿\s*([0-9๐-๙][0-9๐-๙,]*(?:\.[0-9๐-๙]+)?)",
        lambda match: thai_number_words(match.group(1)) + "บาท",
        script,
    )
    script = re.sub(
        r"([0-9๐-๙][0-9๐-๙,]*(?:\.[0-9๐-๙]+)?)\s*%",
        lambda match: thai_number_words(match.group(1)) + "เปอร์เซ็นต์",
        script,
    )
    script = re.sub(
        r"([0-9๐-๙][0-9๐-๙,]*(?:\.[0-9๐-๙]+)?)",
        lambda match: thai_number_words(match.group(1)),
        script,
    )

    script = script.replace("&", " และ ").replace("+", " พลัส ")
    script = script.replace("/", " ต่อ ").replace("#", "")
    script = re.sub(r"[|*_`~<>^=]", " ", script)
    script = "".join(" " if unicodedata.category(char) in {"So", "Cs"} else char for char in script)
    script = re.sub(r"\s+", " ", script).strip(" ,;:-")

    for index, pause in enumerate(pauses):
        script = script.replace(f"พอสแท็ก{thai_number_words(index)}", pause)

    unsupported_tags = [
        tag for tag in re.findall(r"\[[^\]]+\]", script)
        if not _VOICE_TAG_PATTERN.fullmatch(tag)
    ]
    issues = []
    if unsupported_tags:
        issues.append("พบแท็กที่ Voice AI อาจไม่รองรับ: " + ", ".join(sorted(set(unsupported_tags))))
    check_text = _VOICE_TAG_PATTERN.sub("", script)
    if re.search(r"\d", check_text):
        issues.append("ยังพบตัวเลขอารบิกในบทพูด")
    return script, issues
