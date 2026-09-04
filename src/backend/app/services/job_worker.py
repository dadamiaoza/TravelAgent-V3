"""Reliable DB-backed generation job worker."""
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterator
from uuid import UUID

import httpx
import requests
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.trip import Trip
from app.services.generation_jobs import (
    ClaimedGenerationJob,
    append_job_stage,
    claim_next_job,
    finalize_job_success,
    mark_job_failed,
    recover_stale_jobs,
    renew_heartbeat,
    schedule_job_retry,
)
from app.services.trip_editor import generate_draft

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30.0
HEARTBEAT_JOIN_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True)
class GenerationInput:
    """Immutable snapshot of trip fields needed to generate an itinerary draft."""

    trip_id: UUID
    destination: str
    city: str
    start_date: date
    end_date: date
    people_count: int
    budget_min: int | None
    budget_max: int | None
    user_prompt: str | None
    must_visit: tuple[str, ...]
    thread_id: str


Regenerate = Callable[[GenerationInput], dict]


@dataclass(frozen=True)
class ErrorDisposition:
    retryable: bool
    code: str
    safe_message: str


class MissingTripError(Exception):
    """Raised when a claimed job references a trip that no longer exists."""


def classify_generation_error(exc: Exception) -> ErrorDisposition:
    """Classify execution failures without exposing internal details to users."""
    if isinstance(exc, MissingTripError):
        return ErrorDisposition(False, "TRIP_NOT_FOUND", "关联的行程不存在")
    if isinstance(exc, ValidationError):
        return ErrorDisposition(False, "INVALID_INPUT", "行程生成失败，请检查输入后重试")
    if isinstance(exc, ValueError):
        return ErrorDisposition(
            True,
            "MALFORMED_MODEL_OUTPUT",
            "AI 返回内容格式异常，正在准备重试",
        )
    if isinstance(
        exc,
        (
            TimeoutError,
            ConnectionError,
            httpx.TransportError,
            requests.RequestException,
            OperationalError,
        ),
    ):
        return ErrorDisposition(
            True,
            "TRANSIENT_DEPENDENCY_ERROR",
            "生成服务暂时不可用，正在准备重试",
        )
    return ErrorDisposition(False, "INTERNAL_ERROR", "行程生成失败，请检查输入后重试")


@contextmanager
def _heartbeat_during(
    claim: ClaimedGenerationJob,
    interval: float = HEARTBEAT_INTERVAL_SECONDS,
    join_timeout: float = HEARTBEAT_JOIN_TIMEOUT_SECONDS,
) -> Iterator[None]:
    stop = threading.Event()

    def heartbeat_loop() -> None:
        while not stop.wait(interval):
            try:
                if not renew_heartbeat(claim.id, claim.run_token):
                    return
            except Exception:
                logger.exception("generation job heartbeat failed for %s", claim.id)

    thread = threading.Thread(
        target=heartbeat_loop,
        name=f"generation-heartbeat-{claim.id}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=join_timeout)
        if thread.is_alive():
            logger.warning(
                "heartbeat thread did not stop within %.1f seconds for job %s",
                join_timeout,
                claim.id,
            )


def _load_generation_input(claim: ClaimedGenerationJob) -> GenerationInput:
    with SessionLocal() as db:
        trip = db.get(Trip, claim.trip_id)
        if trip is None:
            raise MissingTripError(f"Trip {claim.trip_id} not found")
        return GenerationInput(
            trip_id=trip.id,
            destination=trip.destination,
            city=trip.city or "",
            start_date=trip.start_date,
            end_date=trip.end_date,
            people_count=trip.people_count,
            budget_min=trip.budget_min,
            budget_max=trip.budget_max,
            user_prompt=trip.user_prompt,
            must_visit=tuple(trip.must_visit or ()),
            thread_id=f"trip-{trip.id}",
        )


def _default_generate(
    generation_input: GenerationInput,
    on_stage: Callable[[str, int, str], bool | None] | None = None,
) -> dict:
    return generate_draft(
        destination=generation_input.destination,
        city=generation_input.city,
        start_date=generation_input.start_date,
        end_date=generation_input.end_date,
        people_count=generation_input.people_count,
        budget_min=generation_input.budget_min,
        budget_max=generation_input.budget_max,
        user_prompt=generation_input.user_prompt,
        must_visit=list(generation_input.must_visit) or None,
        thread_id=generation_input.thread_id,
        on_stage=on_stage,
    )


def _stage_reporter(claim: ClaimedGenerationJob):
    def report(key: str, progress: int, message: str) -> bool:
        return append_job_stage(
            claim.id,
            claim.run_token,
            key=key,
            progress=progress,
            message=message,
        )

    return report


def _execute_claim(claim: ClaimedGenerationJob, regenerate: Regenerate) -> None:
    try:
        generation_input = _load_generation_input(claim)
        report = _stage_reporter(claim)
        if not report("plan", 30, "正在规划景点..."):
            return

        with _heartbeat_during(claim):
            if regenerate is _default_generate:
                draft = _default_generate(generation_input, on_stage=report)
            else:
                draft = regenerate(generation_input)

        if not finalize_job_success(claim, draft):
            logger.warning("stale generation owner could not complete job %s", claim.id)
    except Exception as exc:
        disposition = classify_generation_error(exc)
        detail = f"{type(exc).__name__}: {exc}"
        if disposition.retryable and claim.attempts < claim.max_attempts:
            updated = schedule_job_retry(
                claim,
                error_code=disposition.code,
                error=detail,
                message=disposition.safe_message,
            )
        else:
            terminal_message = (
                "行程生成失败，请稍后重试"
                if disposition.retryable
                else disposition.safe_message
            )
            updated = mark_job_failed(
                claim,
                error_code=disposition.code,
                error=detail,
                message=terminal_message,
            )
        if not updated:
            logger.warning("stale generation owner could not update job %s", claim.id)


def process_pending_jobs(
    max_jobs: int = 1,
    *,
    regenerate: Regenerate | None = None,
) -> int:
    """Recover stale work, then claim and handle up to ``max_jobs`` attempts."""
    regenerate = regenerate or _default_generate
    recover_stale_jobs()
    handled = 0

    for _ in range(max_jobs):
        claim = claim_next_job()
        if claim is None:
            break
        _execute_claim(claim, regenerate)
        handled += 1

    return handled


def job_worker_loop(interval: float = 2.0):
    while True:
        try:
            count = process_pending_jobs()
            if count:
                logger.info("processed %d generation jobs", count)
        except Exception:
            logger.exception("job worker iteration failed")
        time.sleep(interval)


def start_worker_thread():
    try:
        recover_stale_jobs()
    except Exception:
        logger.exception("generation job startup recovery failed")
    thread = threading.Thread(target=job_worker_loop, daemon=True)
    thread.start()
    return thread