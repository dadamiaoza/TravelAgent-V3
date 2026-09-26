"""Retry generation is device-scoped and only starts from a failed trip."""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.trip import GenerationJob, Trip
from app.services.demo_auth import DEMO_USER_ID


def _client() -> TestClient:
    return TestClient(app)


def _delete(trip_ids: list[str]) -> None:
    if not trip_ids:
        return
    with SessionLocal() as db:
        db.query(Trip).filter(Trip.id.in_(trip_ids)).delete(synchronize_session=False)
        db.commit()


def _mark_failed(trip_id: str, *, payload: dict | None = None, clear_dates: bool = False) -> str:
    with SessionLocal() as db:
        trip = db.get(Trip, trip_id)
        assert trip is not None
        trip.status = "generation_failed"
        if clear_dates:
            trip.start_date = None
            trip.end_date = None
        job = (
            db.query(GenerationJob)
            .filter(GenerationJob.trip_id == trip.id)
            .order_by(GenerationJob.created_at.desc())
            .first()
        )
        assert job is not None
        job.status = "failed"
        job.message = "模型暂时没有返回行程"
        if payload is not None:
            job.payload = payload
        db.commit()
        return str(job.id)


def test_retry_failed_trip_starts_a_new_generating_job():
    device = _client()
    created = device.post(
        "/api/v1/trips",
        json={
            "destination": "火锅",
            "city": "成都",
            "start_date": "2033-10-01",
            "end_date": "2033-10-05",
            "people_count": 2,
        },
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    payload = {"selected_entities": [{"poi_name": "宽窄巷子", "day_index": 1, "seq": 1}]}
    try:
        payload["fill_draft"] = {
            "city": "成都",
            "days": [{"day_index": 1, "items": [{"seq": 1, "poi_name": "宽窄巷子"}]}],
        }
        old_job_id = _mark_failed(trip_id, payload=payload)

        retried = device.post(f"/api/v1/trips/{trip_id}/retry")
        assert retried.status_code == 200, retried.text
        body = retried.json()
        assert body["status"] == "generating"
        assert body["job_id"]
        assert body["job_id"] != old_job_id
        assert body["days"] == []

        progress = device.get(f"/api/v1/trips/{trip_id}/progress")
        assert progress.status_code == 200
        assert progress.json()["job_id"] == body["job_id"]
        assert progress.json()["status"] == "pending"

        job = device.get(f"/api/v1/jobs/{body['job_id']}")
        assert job.status_code == 200
        assert job.json()["status"] == "pending"
        assert job.json()["trip_id"] == trip_id

        with SessionLocal() as db:
            stored = db.get(GenerationJob, body["job_id"])
            assert stored is not None
            assert stored.payload["selected_entities"][0]["poi_name"] == "宽窄巷子"
            assert stored.payload["fill_draft"]["days"][0]["items"][0]["poi_name"] == "宽窄巷子"

        again = device.post(f"/api/v1/trips/{trip_id}/retry")
        assert again.status_code == 409
        assert "只有生成失败" in again.json()["detail"]
    finally:
        _delete([trip_id])


def test_retry_rejects_non_failed_and_other_devices():
    owner = _client()
    other = _client()
    created = owner.post(
        "/api/v1/trips",
        json={
            "destination": "还在生成",
            "start_date": "2033-11-01",
            "end_date": "2033-11-02",
        },
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    draft = owner.post("/api/v1/trips", json={"destination": "日期未定"})
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["id"]
    try:
        assert owner.post(f"/api/v1/trips/{trip_id}/retry").status_code == 409
        assert owner.post(
            f"/api/v1/trips/{trip_id}/retry",
            json={"discard_fill_draft": True},
        ).status_code == 409
        assert other.post(f"/api/v1/trips/{trip_id}/retry").status_code == 404
        assert other.post(
            f"/api/v1/trips/{trip_id}/retry",
            json={"discard_fill_draft": True},
        ).status_code == 404

        _mark_failed(trip_id)
        assert other.post(f"/api/v1/trips/{trip_id}/retry").status_code == 404
        assert other.post(
            f"/api/v1/trips/{trip_id}/retry",
            json={"discard_fill_draft": True},
        ).status_code == 404

        with SessionLocal() as db:
            row = db.get(Trip, trip_id)
            assert row is not None
            row.status = "generated"
            db.commit()
        generated = owner.post(f"/api/v1/trips/{trip_id}/retry")
        assert generated.status_code == 409
        assert owner.post(
            f"/api/v1/trips/{trip_id}/retry",
            json={"discard_fill_draft": True},
        ).status_code == 409

        assert owner.post(f"/api/v1/trips/{draft_id}/retry").status_code == 409
        assert other.post(f"/api/v1/trips/{uuid4()}/retry").status_code == 404
    finally:
        _delete([trip_id, draft_id])


def test_retry_follows_demo_claim_rules():
    owner = _client()
    other = _client()
    created = owner.post(
        "/api/v1/trips",
        json={
            "destination": "演示认领后重试",
            "city": "成都",
            "start_date": "2034-04-01",
            "end_date": "2034-04-03",
        },
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    try:
        assert owner.post("/api/v1/auth/demo/login").status_code == 200
        with SessionLocal() as db:
            row = db.get(Trip, trip_id)
            assert row is not None
            assert row.user_id == DEMO_USER_ID
        _mark_failed(trip_id)

        retried = owner.post(f"/api/v1/trips/{trip_id}/retry")
        assert retried.status_code == 200, retried.text
        assert retried.json()["status"] == "generating"

        _mark_failed(trip_id)
        assert other.post("/api/v1/auth/demo/login").status_code == 200
        assert other.post(f"/api/v1/trips/{trip_id}/retry").status_code == 404
        assert other.post(
            f"/api/v1/trips/{trip_id}/retry",
            json={"discard_fill_draft": True},
        ).status_code == 404

        assert owner.post("/api/v1/auth/logout").status_code == 204
        logged_out = owner.post(f"/api/v1/trips/{trip_id}/retry")
        assert logged_out.status_code == 404
        assert owner.post(
            f"/api/v1/trips/{trip_id}/retry",
            json={"discard_fill_draft": True},
        ).status_code == 404
        opened = owner.get(f"/api/v1/trips/{trip_id}")
        assert opened.status_code == 404
    finally:
        _delete([trip_id])


def test_discard_fill_draft_drops_only_the_draft_on_the_next_job():
    device = _client()
    created = device.post(
        "/api/v1/trips",
        json={
            "destination": "丢掉草稿",
            "city": "杭州",
            "start_date": "2034-05-01",
            "end_date": "2034-05-02",
            "people_count": 2,
        },
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    draft = {
        "city": "杭州",
        "days": [{"day_index": 1, "items": [{"seq": 1, "poi_name": "西湖"}]}],
    }
    try:
        _mark_failed(
            trip_id,
            payload={
                "selected_entities": [{"poi_name": "灵隐寺", "day_index": 1, "seq": 1}],
                "fill_draft": draft,
            },
        )
        before = device.get(f"/api/v1/trips/{trip_id}/progress")
        assert before.status_code == 200
        assert before.json()["has_fill_draft"] is True

        retried = device.post(
            f"/api/v1/trips/{trip_id}/retry",
            json={"discard_fill_draft": True},
        )
        assert retried.status_code == 200, retried.text
        assert retried.json()["status"] == "generating"
        with SessionLocal() as db:
            stored = db.get(GenerationJob, retried.json()["job_id"])
            assert stored is not None
            assert "fill_draft" not in (stored.payload or {})
            assert stored.payload["selected_entities"][0]["poi_name"] == "灵隐寺"
        after = device.get(f"/api/v1/trips/{trip_id}/progress")
        assert after.json()["has_fill_draft"] is False
        assert after.json()["job_id"] == retried.json()["job_id"]
    finally:
        _delete([trip_id])


def test_empty_and_false_retry_body_still_copy_fill_draft():
    device = _client()
    ids: list[str] = []
    try:
        for body in ({}, {"discard_fill_draft": False}):
            created = device.post(
                "/api/v1/trips",
                json={
                    "destination": "沿用草稿",
                    "city": "杭州",
                    "start_date": "2034-06-01",
                    "end_date": "2034-06-02",
                },
            )
            assert created.status_code == 201, created.text
            trip_id = created.json()["id"]
            ids.append(trip_id)
            _mark_failed(
                trip_id,
                payload={
                    "selected_entities": [{"poi_name": "西湖", "day_index": 1, "seq": 1}],
                    "fill_draft": {"city": "杭州", "days": []},
                },
            )
            retried = device.post(f"/api/v1/trips/{trip_id}/retry", json=body)
            assert retried.status_code == 200, retried.text
            with SessionLocal() as db:
                stored = db.get(GenerationJob, retried.json()["job_id"])
                assert stored is not None
                assert stored.payload["fill_draft"]["city"] == "杭州"
                assert stored.payload["selected_entities"][0]["poi_name"] == "西湖"
            assert device.get(f"/api/v1/trips/{trip_id}/progress").json()["has_fill_draft"] is True
    finally:
        _delete(ids)


def test_retry_requires_dates_when_failed():
    device = _client()
    created = device.post(
        "/api/v1/trips",
        json={
            "destination": "缺日期",
            "start_date": "2033-12-01",
            "end_date": "2033-12-02",
        },
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    try:
        _mark_failed(trip_id, clear_dates=True)
        response = device.post(f"/api/v1/trips/{trip_id}/retry")
        assert response.status_code == 422
        assert "日期" in response.json()["detail"]
        discarded = device.post(
            f"/api/v1/trips/{trip_id}/retry",
            json={"discard_fill_draft": True},
        )
        assert discarded.status_code == 422
        opened = device.get(f"/api/v1/trips/{trip_id}")
        assert opened.json()["status"] == "generation_failed"
    finally:
        _delete([trip_id])
