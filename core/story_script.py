import re


def clean_dialogue_turn_text(turn, character_names=None):
    """Remove production-only speaker labels from one spoken dialogue turn."""
    turn = turn if isinstance(turn, dict) else {}
    text = str(turn.get("text") or "").strip()
    speaker = str(turn.get("speaker") or "").strip()
    labels = {"ผู้บรรยาย", speaker}
    labels.update(str(name or "").strip() for name in (character_names or []))
    for label in sorted((value for value in labels if value), key=len, reverse=True):
        text = re.sub(
            rf"^\s*{re.escape(label)}\s*(?:[:：]|[-–—])\s*",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
    return text


def spoken_script_for_job(job, include_pauses=False):
    """Return exactly what Voice AI should speak, never production speaker labels."""
    job = job if isinstance(job, dict) else {}
    if str(job.get("job_type") or "") == "drama_episode":
        character_names = [
            str(character.get("name") or "").strip()
            for character in (job.get("character_bible") or [])
            if isinstance(character, dict) and str(character.get("name") or "").strip()
        ]
        parts = []
        for turn in job.get("dialogue_turns") or []:
            text = clean_dialogue_turn_text(turn, character_names)
            if not text:
                continue
            if include_pauses:
                try:
                    pause_after = max(0.2, min(2.0, float(turn.get("pause_after") or 0.35)))
                except (TypeError, ValueError):
                    pause_after = 0.35
                parts.append(f"{text} [pause:{pause_after:.1f}]")
            else:
                parts.append(text)
        if parts:
            return " ".join(parts).strip()
    return str(job.get("narration_script") or "").strip()


__all__ = ["clean_dialogue_turn_text", "spoken_script_for_job"]
