"""One library cover per trip.

Selection order:
1. ``trips.cover_photo_id`` when that photo still belongs to the trip.
2. Otherwise the earliest uploaded photo (``created_at``, then ``id``).

The URL is the owning device's photo file route (thumbnail, else preview,
else original). Another device never receives the trip, and the file route
checks ``device_id`` again.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.photo import PhotoAsset
from app.models.trip import Trip


def cover_file_url(trip_id: UUID, photo: PhotoAsset) -> str:
    if photo.thumbnail_path:
        variant = "thumbnail"
    elif photo.preview_path:
        variant = "preview"
    else:
        variant = "original"
    return f"/api/v1/trips/{trip_id}/photos/{photo.id}/file?variant={variant}"


def covers_for_trips(db: Session, trips: list[Trip]) -> dict[UUID, str | None]:
    trip_ids = [trip.id for trip in trips]
    if not trip_ids:
        return {}
    photos = (
        db.query(PhotoAsset)
        .filter(PhotoAsset.trip_id.in_(trip_ids))
        .order_by(PhotoAsset.created_at.asc(), PhotoAsset.id.asc())
        .all()
    )
    by_trip: dict[UUID, list[PhotoAsset]] = {}
    by_id: dict[UUID, PhotoAsset] = {}
    for photo in photos:
        by_trip.setdefault(photo.trip_id, []).append(photo)
        by_id[photo.id] = photo

    chosen: dict[UUID, str | None] = {}
    for trip in trips:
        photo = None
        explicit = by_id.get(trip.cover_photo_id) if trip.cover_photo_id else None
        if explicit is not None and explicit.trip_id == trip.id:
            photo = explicit
        else:
            rows = by_trip.get(trip.id) or []
            photo = rows[0] if rows else None
        chosen[trip.id] = cover_file_url(trip.id, photo) if photo else None
    return chosen
