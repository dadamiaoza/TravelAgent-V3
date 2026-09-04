"""Focused unit tests for generation job lifecycle transitions."""

import pytest

from app.models.trip import GenerationJob
from app.services.generation_jobs import (
    DEADLINE_EXPIRED,
    PERMANENT_ERROR,
    RETRY_EXHAUSTED,
    GenerationJobStatus,
    InvalidGenerationJobTransitionError,
    transition_job,
    validate_job_transition,
)


ALLOWED_TRANSITIONS = {
    ("pending", "running"),
    ("retry_wait", "running"),
    ("running", "retry_wait"),
    ("running", "succeeded"),
    ("running", "failed"),
}


class RecordingSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.refreshed = []

    def commit(self) -> None:
        self.commit_calls += 1

    def refresh(self, value: object) -> None:
        self.refreshed.append(value)


def test_generation_job_statuses_are_exact() -> None:
    assert {status.value for status in GenerationJobStatus} == {
        "pending",
        "running",
        "retry_wait",
        "succeeded",
        "failed",
    }


@pytest.mark.parametrize(("current_status", "new_status"), sorted(ALLOWED_TRANSITIONS))
def test_allowed_transition_commits(
    current_status: str,
    new_status: str,
) -> None:
    db = RecordingSession()
    job = GenerationJob(status=current_status, status_version=4)

    result = transition_job(db, job, new_status)

    assert result is job
    assert job.status == new_status
    assert job.status_version == 5
    assert db.commit_calls == 1
    assert db.refreshed == [job]


ALL_STATUSES = {"pending", "running", "retry_wait", "succeeded", "failed"}
REJECTED_TRANSITIONS = sorted(
    (current, target)
    for current in ALL_STATUSES
    for target in ALL_STATUSES
    if (current, target) not in ALLOWED_TRANSITIONS
)


@pytest.mark.parametrize(("current_status", "new_status"), REJECTED_TRANSITIONS)
def test_rejected_transition_does_not_commit(
    current_status: str,
    new_status: str,
) -> None:
    db = RecordingSession()
    job = GenerationJob(status=current_status, status_version=2)

    with pytest.raises(
        InvalidGenerationJobTransitionError,
        match=f"{current_status} -> {new_status}",
    ):
        transition_job(db, job, new_status)

    assert job.status == current_status
    assert job.status_version == 2
    assert db.commit_calls == 0
    assert db.refreshed == []


@pytest.mark.parametrize("reason", [RETRY_EXHAUSTED, PERMANENT_ERROR])
def test_pending_to_failed_commits_when_retries_exhausted(reason: str) -> None:
    db = RecordingSession()
    job = GenerationJob(status="pending", status_version=2)

    result = transition_job(db, job, "failed", reason=reason)

    assert result is job
    assert job.status == "failed"
    assert job.status_version == 3
    assert db.commit_calls == 1


@pytest.mark.parametrize("reason", [RETRY_EXHAUSTED, DEADLINE_EXPIRED])
def test_retry_wait_to_failed_commits_when_expired_or_exhausted(reason: str) -> None:
    db = RecordingSession()
    job = GenerationJob(status="retry_wait", status_version=2)

    result = transition_job(db, job, "failed", reason=reason)

    assert result is job
    assert job.status == "failed"
    assert job.status_version == 3
    assert db.commit_calls == 1


@pytest.mark.parametrize(
    ("current_status", "reason"),
    [
        ("pending", None),
        ("pending", "TRANSIENT"),
        ("retry_wait", None),
        ("retry_wait", "TRANSIENT"),
    ],
)
def test_active_to_failed_rejected_without_terminal_reason(
    current_status: str,
    reason: str | None,
) -> None:
    db = RecordingSession()
    job = GenerationJob(status=current_status, status_version=2)

    with pytest.raises(
        InvalidGenerationJobTransitionError,
        match=f"{current_status} -> failed",
    ):
        transition_job(db, job, "failed", reason=reason)

    assert job.status == current_status
    assert job.status_version == 2
    assert db.commit_calls == 0


def test_validate_and_transition_job_reject_the_same_illegal_edge() -> None:
    db = RecordingSession()
    job = GenerationJob(status="succeeded", status_version=1)

    with pytest.raises(InvalidGenerationJobTransitionError, match="succeeded -> pending"):
        validate_job_transition("succeeded", "pending")
    with pytest.raises(InvalidGenerationJobTransitionError, match="succeeded -> pending"):
        transition_job(db, job, "pending")

    assert job.status == "succeeded"
    assert db.commit_calls == 0
