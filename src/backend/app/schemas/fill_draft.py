"""Fill-exit draft boundary.

Route may geocode a visit that omits both coordinates. A coordinate is
"present" when the key is set to something other than null. If either lat
or lng is present, both must be finite numbers inside the geographic range.
Null/missing on both sides is allowed.

Sequencing is strict: day_index and seq are JSON integers (no string
coercion), seq is positive and unique within a day, and day_index values
are positive and unique.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError, model_validator

from app.schemas.draft_boundary import DraftBoundaryError, require_coordinate_pair

FILL_DRAFT_ERROR_MESSAGE = "行程草稿的坐标或顺序无效，无法继续排路线"
_ERROR_STAGE_PROGRESS = 40


class FillDraftValidationError(DraftBoundaryError):
    """Raised when a fill draft must not continue into route."""

    safe_message = FILL_DRAFT_ERROR_MESSAGE


class FillDraftItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    seq: StrictInt = Field(..., ge=1)
    poi_name: StrictStr = Field(..., min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _require_coordinate_pair(cls, data: Any) -> Any:
        if isinstance(data, dict):
            require_coordinate_pair(data)
        return data


class FillDraftDay(BaseModel):
    model_config = ConfigDict(extra="allow")

    day_index: StrictInt = Field(..., ge=1)
    items: list[FillDraftItem] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _unique_seq(self) -> FillDraftDay:
        seqs = [item.seq for item in self.items]
        if len(seqs) != len(set(seqs)):
            raise ValueError("同一天的 seq 不能重复")
        return self


class FillDraft(BaseModel):
    """Itinerary JSON that fill must hand to route."""

    model_config = ConfigDict(extra="allow")

    days: list[FillDraftDay] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _unique_day_index(self) -> FillDraft:
        indexes = [day.day_index for day in self.days]
        if len(indexes) != len(set(indexes)):
            raise ValueError("day_index 不能重复")
        return self


def _summarize(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors()[:6]:
        loc = ".".join(str(item) for item in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('type')}")
    return "; ".join(parts) or "invalid fill draft"


def validate_fill_draft(draft: dict) -> dict:
    """Return the same draft when it is safe to route. Does not reshape it."""
    if not isinstance(draft, dict):
        raise FillDraftValidationError("fill draft is not an object")
    try:
        FillDraft.model_validate(draft)
    except ValidationError as exc:
        raise FillDraftValidationError(_summarize(exc)) from exc
    return draft


def gate_fill_draft(
    draft: dict,
    on_stage: Callable[[str, int, str], object] | None = None,
) -> dict:
    """Validate fill output and record an error stage before route."""
    try:
        return validate_fill_draft(draft)
    except FillDraftValidationError as exc:
        if on_stage is not None:
            on_stage("error", _ERROR_STAGE_PROGRESS, exc.safe_message)
        raise
