"""Trip CRUD integration tests — DB + API via TestClient."""
from app.models.trip import Trip
from app.services.itinerary import generate_itinerary


def test_create_trip_db(db):
    """Direct DB: create a trip with itinerary."""
    trip = Trip(
        destination="杭州",
        start_date="2026-06-01",
        end_date="2026-06-02",
        people_count=1,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    assert trip.id is not None
    assert trip.status == "draft"

    trip = generate_itinerary(db, trip)
    assert trip.status == "generated"
    assert len(trip.days) == 2


def test_create_trip_api(client):
    """POST /trips via TestClient."""
    r = client.post("/api/v1/trips", json={
        "destination": "北京",
        "start_date": "2026-07-01",
        "end_date": "2026-07-02",
        "people_count": 2,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert "id" in data
    assert data["destination"] == "北京"
    assert len(data["days"]) == 2


def test_get_trip(client):
    """POST → GET /trips/{id} round-trip."""
    r = client.post("/api/v1/trips", json={
        "destination": "上海",
        "start_date": "2026-08-01",
        "end_date": "2026-08-03",
    })
    trip_id = r.json()["id"]

    r2 = client.get(f"/api/v1/trips/{trip_id}")
    assert r2.status_code == 200
    assert r2.json()["destination"] == "上海"
    assert len(r2.json()["days"]) == 3


def test_list_trips(client):
    """GET /trips returns list."""
    r = client.get("/api/v1/trips")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_read_trip(db):
    """Direct DB: query back a trip with its days and items."""
    trip = Trip(
        destination="杭州",
        start_date="2026-09-01",
        end_date="2026-09-02",
        people_count=3,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    trip = generate_itinerary(db, trip)

    found = db.query(Trip).filter(Trip.id == trip.id).first()
    assert found is not None
    assert found.destination == "杭州"
    assert len(found.days) == 2
    for day in found.days:
        assert len(day.items) > 0
