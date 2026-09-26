"""Library list payload: city, timezone, people, place count, one cover URL."""
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.photo import PhotoAsset
from app.models.trip import ItineraryDay, ItineraryItem, Trip
from app.services.device_access import DEVICE_COOKIE


def test_list_brief_includes_card_fields_and_one_cover():
    client = TestClient(app)
    listed = client.get("/api/v1/trips")
    assert listed.status_code == 200
    device_id = client.cookies.get(DEVICE_COOKIE)
    assert device_id

    trip_id = uuid4()
    day_id = uuid4()
    with SessionLocal() as db:
        db.add(
            Trip(
                id=trip_id,
                destination="周末",
                city="杭州",
                device_id=device_id,
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 3),
                people_count=2,
                status="generated",
            )
        )
        db.flush()
        db.add(ItineraryDay(id=day_id, trip_id=trip_id, day_index=1, date=date(2026, 5, 1)))
        db.flush()
        db.add(ItineraryItem(day_id=day_id, seq=1, poi_name="西湖"))
        db.add(ItineraryItem(day_id=day_id, seq=2, poi_name="灵隐寺"))
        db.commit()

    try:
        body = client.get("/api/v1/trips").json()
        match = next(row for row in body if row["id"] == str(trip_id))
        assert match["city"] == "杭州"
        assert match["destination"] == "周末"
        assert match["people_count"] == 2
        assert match["place_count"] == 2
        assert match["start_date"] == "2026-05-01"
        assert match["end_date"] == "2026-05-03"
        assert match["status"] == "generated"
        assert match["created_at"]
        assert match["timezone"] == "Asia/Shanghai"
        assert match["cover_url"] is None
        assert match["degradations"] == []
    finally:
        with SessionLocal() as db:
            db.query(Trip).filter(Trip.id == trip_id).delete(synchronize_session=False)
            db.commit()


def test_list_cover_uses_explicit_photo_else_earliest_upload():
    owner = TestClient(app)
    owner.get("/api/v1/trips")
    device_id = owner.cookies.get(DEVICE_COOKIE)
    other = TestClient(app)
    other.get("/api/v1/trips")

    trip_id = uuid4()
    early_id = uuid4()
    late_id = uuid4()
    base = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add(
            Trip(
                id=trip_id,
                destination="周末",
                city="杭州",
                device_id=device_id,
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 3),
                status="generated",
            )
        )
        db.flush()
        db.add(
            PhotoAsset(
                id=late_id,
                trip_id=trip_id,
                file_path=f"{trip_id}/{late_id}/original.jpg",
                thumbnail_path=f"{trip_id}/{late_id}/thumbnail.webp",
                original_filename="late.jpg",
                file_hash="b" * 64,
                created_at=base + timedelta(hours=2),
            )
        )
        db.add(
            PhotoAsset(
                id=early_id,
                trip_id=trip_id,
                file_path=f"{trip_id}/{early_id}/original.jpg",
                preview_path=f"{trip_id}/{early_id}/preview.webp",
                original_filename="early.jpg",
                file_hash="a" * 64,
                created_at=base,
            )
        )
        db.commit()

    try:
        earliest = owner.get("/api/v1/trips").json()
        match = next(row for row in earliest if row["id"] == str(trip_id))
        assert match["cover_url"] == (
            f"/api/v1/trips/{trip_id}/photos/{early_id}/file?variant=preview"
        )
        assert all(row["id"] != str(trip_id) for row in other.get("/api/v1/trips").json())

        with SessionLocal() as db:
            trip = db.get(Trip, trip_id)
            trip.cover_photo_id = late_id
            db.commit()

        explicit = owner.get("/api/v1/trips").json()
        match = next(row for row in explicit if row["id"] == str(trip_id))
        assert match["cover_url"] == (
            f"/api/v1/trips/{trip_id}/photos/{late_id}/file?variant=thumbnail"
        )
    finally:
        with SessionLocal() as db:
            db.query(Trip).filter(Trip.id == trip_id).delete(synchronize_session=False)
            db.commit()
