"""Isolate generation-job integration tests on the shared local database."""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import or_

from app.db.session import SessionLocal
from app.models.trip import GenerationJob, Trip


_TEST_DESTINATION_PREFIXES = ("test-", "atomic-", "job-api-", "rollback-")
_TEST_START_DATES = (date(2030, 1, 1), date(2031, 3, 1))
_ACTIVE_STATUSES = ("pending", "running", "retry_wait")


@pytest.fixture(autouse=True)
def quarantine_leftover_test_generation_jobs() -> None:
    """Fail leftover test-owned active jobs so claim/recovery counts stay local."""
    with SessionLocal() as db:
        jobs = (
            db.query(GenerationJob)
            .join(Trip, GenerationJob.trip_id == Trip.id)
            .filter(
                GenerationJob.status.in_(_ACTIVE_STATUSES),
                or_(
                    *[
                        Trip.destination.like(f"{prefix}%")
                        for prefix in _TEST_DESTINATION_PREFIXES
                    ],
                    Trip.start_date.in_(_TEST_START_DATES),
                ),
            )
            .all()
        )
        if not jobs:
            return
        now = datetime.now(timezone.utc)
        for job in jobs:
            job.status = "failed"
            job.progress = 100
            job.message = "test isolation"
            job.error_code = "TEST_ISOLATION"
            job.next_run_at = None
            job.run_token = None
            job.heartbeat_at = None
            job.finished_at = now
        db.commit()
