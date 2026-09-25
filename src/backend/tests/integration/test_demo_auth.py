"""Demo login session, device claim, isolation, and logout."""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.trip import Trip
from app.services.demo_auth import DEMO_USER_ID, SESSION_COOKIE
from app.services.device_access import DEVICE_COOKIE


def _client() -> TestClient:
    return TestClient(app)


def _delete(trip_ids: list[str]) -> None:
    if not trip_ids:
        return
    with SessionLocal() as db:
        db.query(Trip).filter(Trip.id.in_(trip_ids)).delete(synchronize_session=False)
        db.commit()


def test_demo_login_issues_session_without_email():
    device = _client()
    device.get("/api/v1/trips")
    logged_in = device.post("/api/v1/auth/demo/login")
    assert logged_in.status_code == 200, logged_in.text
    body = logged_in.json()
    assert body["demo_auth"] is True
    assert body["user"]["id"] == DEMO_USER_ID
    assert body["user"]["display_name"] == "演示用户"
    assert "email" not in body["user"]
    cookie = logged_in.headers["set-cookie"]
    assert SESSION_COOKIE in cookie
    assert "httponly" in cookie.lower()

    me = device.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["id"] == DEMO_USER_ID


def test_claim_moves_device_trips_to_user_and_lists_them():
    device = _client()
    created = device.post("/api/v1/trips", json={"destination": "演示认领"})
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    try:
        logged_in = device.post("/api/v1/auth/demo/login")
        assert logged_in.status_code == 200, logged_in.text

        with SessionLocal() as db:
            row = db.get(Trip, trip_id)
            assert row is not None
            assert row.user_id == DEMO_USER_ID
            assert row.device_id

        listed = {item["id"] for item in device.get("/api/v1/trips").json()}
        assert trip_id in listed
        assert device.get(f"/api/v1/trips/{trip_id}").status_code == 200

        again = device.post("/api/v1/auth/demo/login")
        assert again.status_code == 200
        with SessionLocal() as db:
            row = db.get(Trip, trip_id)
            assert row is not None
            assert row.user_id == DEMO_USER_ID
    finally:
        _delete([trip_id])


def test_other_devices_stay_isolated_after_claim():
    device_a = _client()
    created = device_a.post(
        "/api/v1/trips",
        json={"destination": "演示隔离", "start_date": "2033-01-01", "end_date": "2033-01-02"},
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    device_b = _client()
    try:
        assert device_a.post("/api/v1/auth/demo/login").status_code == 200
        assert device_b.get(f"/api/v1/trips/{trip_id}").status_code == 404
        listed_b = {item["id"] for item in device_b.get("/api/v1/trips").json()}
        assert trip_id not in listed_b

        assert device_b.post("/api/v1/auth/demo/login").status_code == 200
        assert device_b.get(f"/api/v1/trips/{trip_id}").status_code == 404
        listed_b = {item["id"] for item in device_b.get("/api/v1/trips").json()}
        assert trip_id not in listed_b
        with SessionLocal() as db:
            row = db.get(Trip, trip_id)
            assert row is not None
            assert row.device_id != device_b.cookies.get(DEVICE_COOKIE)
    finally:
        _delete([trip_id])


def test_logout_clears_session_and_device_cookie_remains():
    device = _client()
    created = device.post("/api/v1/trips", json={"destination": "演示退出"})
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    try:
        assert device.post("/api/v1/auth/demo/login").status_code == 200
        device_cookie = device.cookies.get(DEVICE_COOKIE)
        assert device_cookie

        logged_out = device.post("/api/v1/auth/logout")
        assert logged_out.status_code == 204
        assert device.cookies.get(SESSION_COOKIE) is None
        assert device.cookies.get(DEVICE_COOKIE) == device_cookie

        me = device.get("/api/v1/auth/me")
        assert me.json()["user"] is None
        assert device.get(f"/api/v1/trips/{trip_id}").status_code == 404
        listed = {item["id"] for item in device.get("/api/v1/trips").json()}
        assert trip_id not in listed

        fresh = device.post("/api/v1/trips", json={"destination": "退出后新建"})
        assert fresh.status_code == 201, fresh.text
        fresh_id = fresh.json()["id"]
        listed = {item["id"] for item in device.get("/api/v1/trips").json()}
        assert fresh_id in listed
        assert trip_id not in listed

        assert device.post("/api/v1/auth/demo/login").status_code == 200
        listed = {item["id"] for item in device.get("/api/v1/trips").json()}
        assert trip_id in listed
        assert fresh_id in listed
    finally:
        _delete([trip_id])
        with SessionLocal() as db:
            db.query(Trip).filter(Trip.destination == "退出后新建").delete(synchronize_session=False)
            db.commit()


def test_demo_login_hidden_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "demo_auth", False)
    device = _client()
    denied = device.post("/api/v1/auth/demo/login")
    assert denied.status_code == 404
    me = device.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["demo_auth"] is False
    assert me.json()["user"] is None


def test_orphan_user_row_is_not_claimed():
    other_id = uuid4()
    with SessionLocal() as db:
        db.add(
            Trip(
                id=other_id,
                destination="别人的行程",
                user_id="someone-else",
                device_id=str(uuid4()),
                status="draft",
            )
        )
        db.commit()
    device = _client()
    try:
        assert device.post("/api/v1/auth/demo/login").status_code == 200
        with SessionLocal() as db:
            row = db.get(Trip, other_id)
            assert row is not None
            assert row.user_id == "someone-else"
        assert device.get(f"/api/v1/trips/{other_id}").status_code == 404
    finally:
        _delete([str(other_id)])
