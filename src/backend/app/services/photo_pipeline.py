"""Process one photo: EXIF → derivatives → match. No LLM."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.photo import PhotoAsset, PhotoAssignment
from app.models.trip import ItineraryDay, ItineraryItem, Trip
from app.services.photo_exif import image_size, read_photo_meta
from app.services.photo_match import ItineraryNode, match_photo
from app.services.photo_storage import resolve_stored, save_derivatives


def load_trip_nodes(db: Session, trip_id: UUID) -> list[ItineraryNode]:
    days = (
        db.query(ItineraryDay)
        .filter(ItineraryDay.trip_id == trip_id)
        .order_by(ItineraryDay.day_index)
        .all()
    )
    nodes: list[ItineraryNode] = []
    for day in days:
        items = sorted(day.items, key=lambda item: item.seq)
        for item in items:
            nodes.append(
                ItineraryNode(
                    item_id=item.id,
                    poi_name=item.poi_name,
                    day_date=day.date,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    lat=item.lat,
                    lng=item.lng,
                )
            )
    return nodes


def _replace_primary_assignment(
    db: Session,
    photo: PhotoAsset,
    *,
    item_id: UUID | None,
    assignment_type: str,
    confidence: float,
    evidence: dict,
    is_confirmed: bool,
) -> None:
    existing = (
        db.query(PhotoAssignment)
        .filter(PhotoAssignment.photo_id == photo.id, PhotoAssignment.is_primary.is_(True))
        .one_or_none()
    )
    if existing:
        existing.item_id = item_id
        existing.assignment_type = assignment_type
        existing.confidence = confidence
        existing.evidence_json = evidence
        existing.is_confirmed = is_confirmed
        return
    db.add(
        PhotoAssignment(
            photo_id=photo.id,
            item_id=item_id,
            assignment_type=assignment_type,
            confidence=confidence,
            evidence_json=evidence,
            is_confirmed=is_confirmed,
            is_primary=True,
        )
    )


def process_photo_asset(
    db: Session,
    photo: PhotoAsset,
    nodes: list[ItineraryNode],
    target_item_id: UUID | None = None,
) -> None:
    photo.status = "processing"
    db.flush()
    data = resolve_stored(photo.file_path).read_bytes()
    meta = read_photo_meta(data)
    photo.latitude = meta.latitude
    photo.longitude = meta.longitude
    photo.captured_at = meta.captured_at
    photo.exif_json = {
        "has_gps": meta.latitude is not None and meta.longitude is not None,
        "has_datetime_original": meta.captured_at is not None,
    }
    width, height = image_size(data)
    photo.width = width
    photo.height = height
    try:
        preview, thumb = save_derivatives(photo.trip_id, photo.id, data)
        photo.preview_path = preview
        photo.thumbnail_path = thumb
    except Exception as exc:
        photo.error = f"thumbnail failed: {exc}"

    if target_item_id is not None:
        _replace_primary_assignment(
            db,
            photo,
            item_id=target_item_id,
            assignment_type="manual",
            confidence=1.0,
            evidence={"photo_class": "manual", "reason": "upload_to_item"},
            is_confirmed=True,
        )
        photo.status = "completed"
        photo.error = None
        return

    result = match_photo(meta, nodes)
    _replace_primary_assignment(
        db,
        photo,
        item_id=result.item_id,
        assignment_type=result.assignment_type,
        confidence=result.confidence,
        evidence=result.evidence,
        is_confirmed=False,
    )
    photo.status = "completed"
    photo.error = None


def process_photo_job(db: Session, job_id: UUID) -> None:
    from app.models.photo import PhotoJob

    job = db.get(PhotoJob, job_id)
    if job is None:
        return
    job.status = "running"
    payload = job.payload or {}
    photo_ids = [UUID(str(value)) for value in payload.get("photo_ids") or []]
    target_raw = payload.get("target_item_id")
    target_item_id = UUID(str(target_raw)) if target_raw else None
    trip = db.get(Trip, job.trip_id)
    if trip is None:
        job.status = "failed"
        job.error = "行程不存在"
        job.progress = 100
        return
    nodes = load_trip_nodes(db, job.trip_id)
    total = max(len(photo_ids), 1)
    for index, photo_id in enumerate(photo_ids, start=1):
        photo = db.get(PhotoAsset, photo_id)
        if photo is None or photo.trip_id != job.trip_id:
            continue
        try:
            process_photo_asset(db, photo, nodes, target_item_id=target_item_id)
        except Exception as exc:
            photo.status = "failed"
            photo.error = str(exc)[:500]
        job.progress = int(index / total * 100)
        db.commit()
    job.status = "succeeded"
    job.progress = 100
    db.commit()
