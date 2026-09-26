"""Verify-exit / persist-input draft boundary.

Aligned with the fields ``persist_itinerary`` actually reads. A string
``day_index`` becomes ``TypeError`` inside ``timedelta``; a non-int
``travel_minutes_from_prev`` becomes ``TypeError`` inside ``time()``.
Those must fail here, with a stage message, instead of ``INTERNAL_ERROR``.

Coordinates follow the fill rule: both missing is allowed (columns are
nullable and route may not have filled them). A one-sided or non-finite
pair is not. This gate does not look at route degradation fields.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from app.schemas.draft_boundary import (
    DraftBoundaryError,
    gate_draft,
    require_coordinate_pair,
    require_optional_bool,
    require_optional_duration,
    require_optional_list,
    require_optional_nonnegative_int,
    require_optional_str,
    validate_draft,
)

PERSIST_DRAFT_ERROR_MESSAGE = "行程草稿字段不合法，无法保存"
PERSIST_DRAFT_ERROR_PROGRESS = 96


class PersistDraftValidationError(DraftBoundaryError):
    """Raised when a draft must not be written by persist_itinerary."""

    safe_message = PERSIST_DRAFT_ERROR_MESSAGE


class PersistDraftItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    seq: StrictInt = Field(..., ge=1)
    poi_name: StrictStr = Field(..., min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _persist_item_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            require_coordinate_pair(data)
            require_optional_duration(data)
            require_optional_nonnegative_int(data, "travel_minutes_from_prev", allow_null=False)
            require_optional_str(data, "transport_mode")
            require_optional_str(data, "travel_advice")
            require_optional_str(data, "amap_poi_id")
            require_optional_str(data, "poi_address")
            require_optional_str(data, "poi_type")
            require_optional_bool(data, "route_verified")
            require_optional_list(data, "route_polyline")
        return data


class PersistDraftDay(BaseModel):
    model_config = ConfigDict(extra="allow")

    day_index: StrictInt = Field(..., ge=1)
    items: list[PersistDraftItem] = Field(..., min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _persist_day_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            require_optional_str(data, "route_type")
        return data

    @model_validator(mode="after")
    def _unique_seq(self) -> PersistDraftDay:
        seqs = [item.seq for item in self.items]
        if len(seqs) != len(set(seqs)):
            raise ValueError("同一天的 seq 不能重复")
        return self


class PersistDraft(BaseModel):
    """Itinerary JSON that verify must hand to persist."""

    model_config = ConfigDict(extra="allow")

    days: list[PersistDraftDay] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _unique_day_index(self) -> PersistDraft:
        indexes = [day.day_index for day in self.days]
        if len(indexes) != len(set(indexes)):
            raise ValueError("day_index 不能重复")
        return self


def validate_persist_draft(draft: dict) -> dict:
    """Return the same draft when it is safe to persist. Does not reshape it."""
    return validate_draft(draft, PersistDraft, PersistDraftValidationError)


def gate_persist_draft(
    draft: dict,
    on_stage: Callable[[str, int, str], object] | None = None,
) -> dict:
    """Validate the draft immediately before persist_itinerary."""
    return gate_draft(
        draft,
        PersistDraft,
        PersistDraftValidationError,
        progress=PERSIST_DRAFT_ERROR_PROGRESS,
        on_stage=on_stage,
    )
