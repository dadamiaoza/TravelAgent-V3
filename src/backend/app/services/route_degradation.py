"""Route degradations as user-facing warning copy.

`order_source`, `order_degrade_reason`, and `day_boundary_warning` live on
the routed draft and are not itinerary columns. The generation worker copies
them onto `GenerationJob` stages with `key=warning` — the same channel verify
already uses — so detail and the library can read them after success.
"""
from __future__ import annotations

_DEGRADE_REASON_COPY = {
    "invalid_order": "顺序无效",
    "cross_city_jump": "同日跨城过远",
    "travel_time": "路时明显绕路",
    "amap_unverified": "路段未能核验",
    "explicit_reorder": "指定重排",
}
_MESSAGE_LIMIT = 500


def warning_stage_messages(stages: list | None) -> list[str]:
    """Warning-stage copy in record order, skipping blanks and duplicates."""
    messages: list[str] = []
    for stage in stages or []:
        if not isinstance(stage, dict) or stage.get("key") != "warning":
            continue
        text = str(stage.get("message") or "").strip()
        if text and text not in messages:
            messages.append(text)
    return messages


def collect_route_degradation_messages(draft: dict) -> list[str]:
    """Nearest-neighbor reorder, then cross-day boundary warnings.

    Fill-ordered days are omitted. Cross-day text is the draft's
    `day_boundary_warning`; this does not move stops between days.
    """
    days = [day for day in (draft.get("days") or []) if isinstance(day, dict)]
    grouped: dict[str, list[tuple[int, object]]] = {}
    boundaries: list[tuple[int, str]] = []
    for day in days:
        sort_key = _day_sort_key(day.get("day_index"))
        if day.get("order_source") == "nearest_neighbor":
            reason = str(day.get("order_degrade_reason") or "").strip() or "unspecified"
            grouped.setdefault(reason, []).append((sort_key, day.get("day_index")))
        warning = str(day.get("day_boundary_warning") or "").strip()
        if warning:
            boundaries.append((sort_key, warning))

    messages: list[str] = []
    for reason in sorted(grouped, key=lambda item: min(pair[0] for pair in grouped[item])):
        labels = [label for _, label in sorted(grouped[reason], key=lambda pair: pair[0])]
        messages.append(_nn_message(labels, reason))
    for _, warning in sorted(boundaries, key=lambda pair: pair[0]):
        text = warning[:_MESSAGE_LIMIT]
        if text not in messages:
            messages.append(text)
    return messages


def _day_sort_key(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 10**9


def _day_phrase(labels: list[object]) -> str:
    parts: list[str] = []
    for label in labels:
        text = "" if label is None else str(label).strip()
        parts.append(f"第{text}天" if text else "某天")
    return "、".join(parts)


def _nn_message(labels: list[object], reason: str) -> str:
    days = _day_phrase(labels)
    why = _DEGRADE_REASON_COPY.get(reason)
    if why:
        text = f"{days}已按最近邻重排（{why}）"
    else:
        text = f"{days}已按最近邻重排"
    return text[:_MESSAGE_LIMIT]
