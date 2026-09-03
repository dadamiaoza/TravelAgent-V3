"""Reliable DB-backed generation job worker."""
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

import httpx
import requests
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.trip import Trip
from app.services.generation_jobs import (
    ClaimedGenerationJob,
    claim_next_job,
    mark_job_failed,
    mark_job_succeeded,
    recover_stale_jobs,
    renew_heartbeat,
    schedule_job_retry,
    update_job_progress,
)
from app.services.trip_editor import regenerate_trip

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30.0
HEARTBEAT_JOIN_TIMEOUT_SECONDS = 1.0
Regenerate = Callable[[Session, Trip], object]


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


def _execute_claim(claim: ClaimedGenerationJob, regenerate: Regenerate) -> None:
    try:
        with SessionLocal() as execution_db:
            trip = execution_db.get(Trip, claim.trip_id)
            if trip is None:
                raise MissingTripError(f"Trip {claim.trip_id} not found")

            if not update_job_progress(
                claim.id,
                claim.run_token,
                progress=30,
                message="AI 正在生成行程...",
            ):
                return

            with _heartbeat_during(claim):
                regenerate(execution_db, trip)

        if not mark_job_succeeded(claim.id, claim.run_token):
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
    regenerate = regenerate or regenerate_trip
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