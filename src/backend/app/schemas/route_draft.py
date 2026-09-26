"""Route-exit / verify-input draft boundary.

``optimize_itinerary`` keeps fill's ``day_index`` and ``duration_h``, rewrites
``seq`` to ``1..n``, and writes integer leg minutes. It also adds optional
``order_source`` (``fill`` or ``nearest_neighbor``), ``order_degrade_reason``,
and ``day_boundary_warning``. Those degradation fields are warnings upstream;
this gate only rejects illegal types, not a nearest-neighbor day or a
cross-day distance warning.

Verify reads ``day_index`` and ``poi_name`` and tolerates coercion. The types
rejected here are the ones that would later raise in ``persist_itinerary``,
plus route-added fields whose types are not the ones ``optimize_itinerary``
writes (a string ``travel_amap_minutes``, a non-string ``order_source``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import Field, model_validator

from app.schemas.draft_boundary import (
    DraftBoundaryError,
    gate_draft,
    require_optional_nonnegative_int,
    require_optional_str,
    validate_draft,
)
from app.schemas.persist_draft import PersistDraft, PersistDraftDay, PersistDraftItem

ROUTE_DRAFT_ERROR_MESSAGE = "路线草稿的站点或路段时间无效，无法继续核对"
ROUTE_DRAFT_ERROR_PROGRESS = 80


class RouteDraftValidationError(DraftBoundaryError):
    """Raised when route output must not continue into verify."""

    safe_message = ROUTE_DRAFT_ERROR_MESSAGE


class RouteDraftItem(PersistDraftItem):
    @model_validator(mode="before")
    @classmethod
    def _route_item_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            require_optional_nonnegative_int(data, "travel_minutes", allow_null=False)
            require_optional_nonnegative_int(data, "travel_amap_minutes", allow_null=True)
            require_optional_nonnegative_int(data, "travel_estimate_minutes", allow_null=True)
            require_optional_str(data, "travel_estimate_source")
            require_optional_str(data, "travel_discrepancy")
        return data


class RouteDraftDay(PersistDraftDay):
    items: list[RouteDraftItem] = Field(..., min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _route_day_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            require_optional_str(data, "order_source")
            require_optional_str(data, "order_degrade_reason")
            require_optional_str(data, "day_boundary_warning")
        return data


class RouteDraft(PersistDraft):
    """Itinerary JSON that route must hand to verify."""

    days: list[RouteDraftDay] = Field(..., min_length=1)


def validate_route_draft(draft: dict) -> dict:
    """Return the same draft when it is safe to verify. Does not reshape it."""
    return validate_draft(draft, RouteDraft, RouteDraftValidationError)


def gate_route_draft(
    draft: dict,
    on_stage: Callable[[str, int, str], object] | None = None,
) -> dict:
    """Validate route output before verify."""
    return gate_draft(
        draft,
        RouteDraft,
        RouteDraftValidationError,
        progress=ROUTE_DRAFT_ERROR_PROGRESS,
        on_stage=on_stage,
    )
