"""Same-job neighbor copy for type-C photos. No LLM, no captured_at."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.photo import PhotoAsset, PhotoAssignment, PhotoJob, VisitStop
from app.models.trip import ItineraryItem

NEIGHBOR_SANDWICH_SCORE = 0.55
NEIGHBOR_ONESIDE_SCORE = 0.50


@dataclass(frozen=True)
class NeighborSlot:
    photo_id: UUID
    has_gps: bool
    captured_at: datetime | None
    item_id: UUID | None
    visit_stop_id: UUID | None


@dataclass(frozen=True)
class NeighborHint:
    photo_id: UUID
    item_id: UUID | None
    visit_stop_id: UUID | None
    confidence: float
    bound: str  # sandwich | left | right
    neighbor_photo_ids: tuple[UUID, ...]


def _is_type_c(slot: NeighborSlot) -> bool:
    return (
        not slot.has_gps
        and slot.captured_at is None
        and slot.item_id is None
        and slot.visit_stop_id is None
    )


def _anchor_target(slot: NeighborSlot) -> tuple[UUID | None, UUID | None] | None:
    if not slot.has_gps:
        return None
    if slot.item_id is None and slot.visit_stop_id is None:
        return None
    return (slot.item_id, slot.visit_stop_id)


def _copied_ids(anchor: NeighborSlot) -> tuple[UUID | None, UUID | None]:
    if anchor.item_id is not None:
        return anchor.item_id, None
    return None, anchor.visit_stop_id


def infer_batch_neighbors(slots: list[NeighborSlot]) -> list[NeighborHint]:
    anchors = [(index, slot) for index, slot in enumerate(slots) if _anchor_target(slot) is not None]
    if not anchors:
        return []

    hints: list[NeighborHint] = []

    def emit(start: int, end: int, bound: str, neighbors: tuple[NeighborSlot, ...], score: float) -> None:
        item_id, visit_stop_id = _copied_ids(neighbors[0])
        neighbor_photo_ids = tuple(row.photo_id for row in neighbors)
        confidence = min(score, NEIGHBOR_SANDWICH_SCORE)
        for slot in slots[start:end]:
            if not _is_type_c(slot):
                continue
            hints.append(
                NeighborHint(
                    photo_id=slot.photo_id,
                    item_id=item_id,
                    visit_stop_id=visit_stop_id,
                    confidence=confidence,
                    bound=bound,
                    neighbor_photo_ids=neighbor_photo_ids,
                )
            )

    first_index, first_slot = anchors[0]
    if first_index > 0:
        emit(0, first_index, "right", (first_slot,), NEIGHBOR_ONESIDE_SCORE)

    for (left_index, left_slot), (right_index, right_slot) in zip(anchors, anchors[1:]):
        if right_index - left_index <= 1:
            continue
        if _anchor_target(left_slot) != _anchor_target(right_slot):
            continue
        emit(left_index + 1, right_index, "sandwich", (left_slot, right_slot), NEIGHBOR_SANDWICH_SCORE)

    last_index, last_slot = anchors[-1]
    if last_index < len(slots) - 1:
        emit(last_index + 1, len(slots), "left", (last_slot,), NEIGHBOR_ONESIDE_SCORE)

    return hints


def apply_batch_neighbors(db: Session, job: PhotoJob) -> None:
    from app.services.photo_pipeline import _assignment_already_placed, _replace_primary_assignment

    photo_ids = [UUID(str(value)) for value in (job.payload or {}).get("photo_ids") or []]
    if not photo_ids:
        return
    photos = (
        db.query(PhotoAsset)
        .options(joinedload(PhotoAsset.assignments).joinedload(PhotoAssignment.visit_stop))
        .filter(PhotoAsset.id.in_(photo_ids))
        .all()
    )
    by_id = {photo.id: photo for photo in photos}
    slots: list[NeighborSlot] = []
    ordered: list[PhotoAsset] = []
    for photo_id in photo_ids:
        photo = by_id.get(photo_id)
        if photo is None:
            continue
        assignment = next((row for row in photo.assignments if row.is_primary), None)
        slots.append(
            NeighborSlot(
                photo_id=photo.id,
                has_gps=photo.latitude is not None and photo.longitude is not None,
                captured_at=photo.captured_at,
                item_id=assignment.item_id if assignment else None,
                visit_stop_id=assignment.visit_stop_id if assignment else None,
            )
        )
        ordered.append(photo)

    hints = infer_batch_neighbors(slots)
    if not hints:
        return
    photo_by_id = {photo.id: photo for photo in ordered}
    for hint in hints:
        photo = photo_by_id.get(hint.photo_id)
        if photo is None or photo.status != "completed":
            continue
        assignment = next((row for row in photo.assignments if row.is_primary), None)
        if _assignment_already_placed(assignment):
            continue
        poi_name = _hint_place_name(db, hint)
        _replace_primary_assignment(
            db,
            photo,
            item_id=hint.item_id,
            visit_stop_id=hint.visit_stop_id,
            assignment_type="batch_neighbor",
            confidence=hint.confidence,
            evidence={
                "photo_class": "C",
                "rule": "batch_neighbor",
                "bound": hint.bound,
                "confidence_cap": NEIGHBOR_SANDWICH_SCORE,
                "neighbor_photo_ids": [str(value) for value in hint.neighbor_photo_ids],
                "target_kind": "item" if hint.item_id is not None else "visit_stop",
                "poi_name": poi_name,
            },
            is_confirmed=False,
        )


def _hint_place_name(db: Session, hint: NeighborHint) -> str:
    if hint.item_id is not None:
        item = db.get(ItineraryItem, hint.item_id)
        return item.poi_name if item else ""
    if hint.visit_stop_id is not None:
        stop = db.get(VisitStop, hint.visit_stop_id)
        return stop.place_name if stop else ""
    return ""
