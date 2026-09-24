"""Library list payload: city, people, place count, dates, no cover URL."""
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.trip import ItineraryDay, ItineraryItem, Trip
from app.services.device_access import DEVICE_COOKIE


def test_list_brief_includes_card_fields_and_hides_cover():
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
        assert match["cover_url"] is None
    finally:
        with SessionLocal() as db:
            db.query(Trip).filter(Trip.id == trip_id).delete(synchronize_session=False)
            db.commit()
