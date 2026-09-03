"""Focused unit tests for generation job lifecycle transitions."""

import pytest

from app.models.trip import GenerationJob
from app.services.generation_jobs import (
    GenerationJobStatus,
    InvalidGenerationJobTransitionError,
    transition_job,
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
