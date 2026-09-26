"""Shared checks for generation draft boundaries.

Gates validate the caller's dict and return it unchanged. They do not
coerce strings into integers or fill in missing coordinates.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pydantic import BaseModel, ValidationError


class DraftBoundaryError(ValueError):
    """Illegal draft at a generation stage boundary. Retryable malformed output."""

    safe_message = "行程草稿字段不合法，无法继续生成"

    def __init__(self, detail: str) -> None:
        super().__init__(detail[:500])


def finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def require_coordinate_pair(data: dict) -> None:
    """Both coordinates missing is allowed. A present side must be a finite pair."""
    lat_present = "lat" in data and data.get("lat") is not None
    lng_present = "lng" in data and data.get("lng") is not None
    if not lat_present and not lng_present:
        return
    lat = finite_number(data.get("lat"))
    lng = finite_number(data.get("lng"))
    if (
        lat is None
        or lng is None
        or not -90.0 <= lat <= 90.0
        or not -180.0 <= lng <= 180.0
    ):
        raise ValueError("景点坐标必须是有限经纬度")


def require_optional_duration(data: dict) -> None:
    """duration_h is hours at the stop. Missing uses persist's 1.5 default.

    None, strings, and bools are rejected. persist does ``int(duration_h * 60)``;
    None and non-numeric values raise, and a numeric string repeats instead of
    converting. Floats such as 1.5 are what route leaves untouched.
    """
    if "duration_h" not in data:
        return
    value = data["duration_h"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("duration_h 必须是有限非负数字")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("duration_h 必须是有限非负数字")


def require_optional_nonnegative_int(data: dict, key: str, *, allow_null: bool) -> None:
    """Reject types that break ``time()`` or that route never writes.

    Missing keys are allowed: persist treats a missing travel leg as 0.
    Explicit null is allowed only when the producer writes null (Amap
    minutes on the first stop). Floats are rejected even when they are
    whole numbers, because ``time()`` requires an int.
    """
    if key not in data:
        return
    value = data[key]
    if value is None:
        if allow_null:
            return
        raise ValueError(f"{key} 不能为 null")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} 必须是非负整数")


def require_optional_str(data: dict, key: str) -> None:
    if key not in data:
        return
    value = data[key]
    if value is None or isinstance(value, str):
        return
    raise ValueError(f"{key} 必须是字符串")


def require_optional_bool(data: dict, key: str) -> None:
    if key not in data:
        return
    value = data[key]
    if value is None or isinstance(value, bool):
        return
    raise ValueError(f"{key} 必须是布尔值")


def require_optional_list(data: dict, key: str) -> None:
    if key not in data:
        return
    value = data[key]
    if value is None or isinstance(value, list):
        return
    raise ValueError(f"{key} 必须是数组")


def summarize_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors()[:6]:
        loc = ".".join(str(item) for item in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('type')}")
    return "; ".join(parts) or "invalid draft"


def validate_draft(draft: object, model: type[BaseModel], error_cls: type[DraftBoundaryError]) -> dict:
    if not isinstance(draft, dict):
        raise error_cls("draft is not an object")
    try:
        model.model_validate(draft)
    except ValidationError as exc:
        raise error_cls(summarize_validation_error(exc)) from exc
    return draft


def gate_draft(
    draft: dict,
    model: type[BaseModel],
    error_cls: type[DraftBoundaryError],
    *,
    progress: int,
    on_stage: Callable[[str, int, str], object] | None = None,
) -> dict:
    try:
        return validate_draft(draft, model, error_cls)
    except DraftBoundaryError as exc:
        if on_stage is not None:
            on_stage("error", progress, exc.safe_message)
        raise
