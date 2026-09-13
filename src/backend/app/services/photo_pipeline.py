"""Process one photo: EXIF → derivatives → match. No LLM."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.photo import PhotoAsset, PhotoAssignment, VisitStop
from app.models.trip import ItineraryDay, Trip
from app.services.geo_regeo import reverse_geocode_amap
from app.services.photo_cluster import GpsPoint, cluster_unmatched_photos
from app.services.photo_exif import image_size, read_photo_meta
from app.services.photo_match import ItineraryNode, match_photo
from app.services.photo_neighbor import apply_batch_neighbors
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
    visit_stop_id: UUID | None = None,
) -> None:
    existing = (
        db.query(PhotoAssignment)
        .filter(PhotoAssignment.photo_id == photo.id, PhotoAssignment.is_primary.is_(True))
        .one_or_none()
    )
    if existing:
        existing.item_id = item_id
        existing.visit_stop_id = visit_stop_id
        existing.assignment_type = assignment_type
        existing.confidence = confidence
        existing.evidence_json = evidence
        existing.is_confirmed = is_confirmed
        return
    db.add(
        PhotoAssignment(
            photo_id=photo.id,
            item_id=item_id,
            visit_stop_id=visit_stop_id,
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


def _assignment_already_placed(assignment: PhotoAssignment | None) -> bool:
    if assignment is None:
        return False
    if assignment.item_id is not None:
        return True
    if assignment.visit_stop_id is not None:
        return True
    return False


def suggest_visit_stops(db: Session, trip_id: UUID, nodes: list[ItineraryNode]) -> list[VisitStop]:
    photos = (
        db.query(PhotoAsset)
        .options(joinedload(PhotoAsset.assignments))
        .filter(
            PhotoAsset.trip_id == trip_id,
            PhotoAsset.latitude.isnot(None),
            PhotoAsset.longitude.isnot(None),
            PhotoAsset.status == "completed",
        )
        .all()
    )
    unmatched: list[GpsPoint] = []
    photo_by_id = {photo.id: photo for photo in photos}
    for photo in photos:
        assignment = next((row for row in photo.assignments if row.is_primary), None)
        if _assignment_already_placed(assignment):
            continue
        unmatched.append(
            GpsPoint(
                photo_id=photo.id,
                latitude=photo.latitude,
                longitude=photo.longitude,
                captured_at=photo.captured_at,
            )
        )
    if not unmatched:
        return []
    created: list[VisitStop] = []
    for cluster in cluster_unmatched_photos(unmatched, nodes):
        place_name = reverse_geocode_amap(cluster.lng, cluster.lat, db=db) or "未命名停留"
        stop = VisitStop(
            trip_id=trip_id,
            lat=cluster.lat,
            lng=cluster.lng,
            place_name=place_name,
            linked_item_id=cluster.nearest_item_id,
            status="suggested",
            time_start=cluster.time_start,
            time_end=cluster.time_end,
            evidence_json={
                "photo_count": len(cluster.photo_ids),
                "nearest_item_name": cluster.nearest_item_name,
                "nearest_distance_m": cluster.nearest_distance_m,
                "rule": "gps_cluster",
            },
        )
        db.add(stop)
        db.flush()
        for photo_id in cluster.photo_ids:
            photo = photo_by_id.get(photo_id)
            if photo is None:
                continue
            _replace_primary_assignment(
                db,
                photo,
                item_id=None,
                visit_stop_id=stop.id,
                assignment_type="cluster",
                confidence=0.5,
                evidence={
                    "photo_class": "A",
                    "rule": "gps_cluster",
                    "visit_stop_id": str(stop.id),
                    "place_name": place_name,
                },
                is_confirmed=False,
            )
        created.append(stop)
    return created


def confirm_visit_stop(db: Session, stop: VisitStop, place_name: str | None = None) -> None:
    if place_name:
        stop.place_name = place_name.strip() or stop.place_name
    stop.status = "confirmed"
    for assignment in stop.assignments:
        assignment.is_confirmed = True
        assignment.visit_stop_id = stop.id
        assignment.item_id = None


def dismiss_visit_stop(db: Session, stop: VisitStop) -> None:
    stop.status = "dismissed"
    for assignment in stop.assignments:
        assignment.visit_stop_id = None
        assignment.is_confirmed = False


def attach_visit_stop_to_item(db: Session, stop: VisitStop, item_id: UUID) -> None:
    stop.status = "dismissed"
    stop.linked_item_id = item_id
    for assignment in stop.assignments:
        assignment.item_id = item_id
        assignment.visit_stop_id = None
        assignment.assignment_type = "manual"
        assignment.confidence = 1.0
        assignment.is_confirmed = True



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
    suggest_visit_stops(db, job.trip_id, nodes)
    apply_batch_neighbors(db, job)
    job.status = "succeeded"
    job.progress = 100
    db.commit()
