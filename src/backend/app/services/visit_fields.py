"""Copy visit-advice fields between entities, drafts, and itinerary items."""
from __future__ import annotations


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_duration(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    if duration <= 0:
        return None
    return duration


def cost_note_from(source: dict) -> str | None:
    note = _clean_text(source.get("cost_note"))
    if note:
        return note
    raw = source.get("cost_estimate")
    if isinstance(raw, str):
        return _clean_text(raw)
    return None


def copy_visit_fields(source: dict) -> dict:
    """Structured visit fields for a draft item. Omits empties except explicit None skips."""
    duration = _clean_duration(source.get("suggested_duration_h"))
    if duration is None:
        duration = _clean_duration(source.get("duration_h"))
    fields = {
        "suggested_duration_h": duration,
        "best_time": _clean_text(source.get("best_time")),
        "cost_note": cost_note_from(source),
        "visit_tips": _clean_text(source.get("visit_tips") or source.get("tips")),
        "opening_hours": _clean_text(source.get("opening_hours")),
        "fact_warning": _clean_text(source.get("fact_warning")),
    }
    return {key: value for key, value in fields.items() if value is not None}
