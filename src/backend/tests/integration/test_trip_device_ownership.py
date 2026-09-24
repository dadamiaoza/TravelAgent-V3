"""Device ownership, undated drafts, and openable generation statuses."""
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.trip import Trip


def _client() -> TestClient:
    return TestClient(app)


def _delete(trip_ids: list[str]) -> None:
    if not trip_ids:
        return
    with SessionLocal() as db:
        db.query(Trip).filter(Trip.id.in_(trip_ids)).delete(synchronize_session=False)
        db.commit()


def test_two_devices_cannot_see_each_other():
    device_a = _client()
    device_b = _client()
    created = device_a.post(
        "/api/v1/trips",
        json={
            "destination": "设备隔离",
            "start_date": "2032-04-01",
            "end_date": "2032-04-02",
        },
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    try:
        assert "ta_device" in created.headers["set-cookie"]
        assert created.json()["status"] == "generating"

        own = device_a.get(f"/api/v1/trips/{trip_id}")
        assert own.status_code == 200
        assert own.json()["days"] == []

        other = device_b.get(f"/api/v1/trips/{trip_id}")
        assert other.status_code == 404

        listed_a = {row["id"] for row in device_a.get("/api/v1/trips").json()}
        listed_b = {row["id"] for row in device_b.get("/api/v1/trips").json()}
        assert trip_id in listed_a
        assert trip_id not in listed_b

        patched = device_a.patch(f"/api/v1/trips/{trip_id}", json={"destination": "设备隔离-改"})
        assert patched.status_code == 200
        assert patched.json()["destination"] == "设备隔离-改"
        assert device_b.patch(f"/api/v1/trips/{trip_id}", json={"destination": "越权"}).status_code == 404
    finally:
        _delete([trip_id])


def test_orphan_anonymous_rows_are_hidden():
    orphan_id = uuid4()
    with SessionLocal() as db:
        db.add(
            Trip(
                id=orphan_id,
                destination="旧匿名",
                user_id=None,
                device_id=None,
                start_date=date(2032, 5, 1),
                end_date=date(2032, 5, 2),
                status="draft",
            )
        )
        db.commit()
    device = _client()
    try:
        listed = {row["id"] for row in device.get("/api/v1/trips").json()}
        assert str(orphan_id) not in listed
        assert device.get(f"/api/v1/trips/{orphan_id}").status_code == 404
        assert device.patch(
            f"/api/v1/trips/{orphan_id}",
            json={"destination": "认领"},
        ).status_code == 404
    finally:
        _delete([str(orphan_id)])


def test_undated_draft_can_be_stored_and_reopened():
    device = _client()
    created = device.post("/api/v1/trips", json={"destination": "日期未定"})
    assert created.status_code == 201, created.text
    body = created.json()
    trip_id = body["id"]
    try:
        assert body["status"] == "draft"
        assert body["start_date"] is None
        assert body["end_date"] is None
        assert body["job_id"] is None
        assert body["days"] == []

        again = device.get(f"/api/v1/trips/{trip_id}")
        assert again.status_code == 200
        assert again.json()["status"] == "draft"

        listed = device.get("/api/v1/trips").json()
        match = next(row for row in listed if row["id"] == trip_id)
        assert match["start_date"] is None
        assert match["status"] == "draft"

        partial = device.post(
            "/api/v1/trips",
            json={"destination": "只填开始", "start_date": "2032-06-01"},
        )
        assert partial.status_code == 422
    finally:
        _delete([trip_id])


def test_generating_and_failed_trips_open_without_days():
    device = _client()
    created = device.post(
        "/api/v1/trips",
        json={
            "destination": "生成中",
            "start_date": "2032-07-01",
            "end_date": "2032-07-02",
        },
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    other = _client()
    try:
        opened = device.get(f"/api/v1/trips/{trip_id}")
        assert opened.status_code == 200
        assert opened.json()["status"] == "generating"
        assert opened.json()["days"] == []
        assert other.get(f"/api/v1/trips/{trip_id}").status_code == 404

        with SessionLocal() as db:
            row = db.get(Trip, trip_id)
            assert row is not None
            row.status = "generation_failed"
            db.commit()

        failed = device.get(f"/api/v1/trips/{trip_id}")
        assert failed.status_code == 200
        assert failed.json()["status"] == "generation_failed"
        assert failed.json()["days"] == []
        assert other.get(f"/api/v1/trips/{trip_id}").status_code == 404
    finally:
        _delete([trip_id])
