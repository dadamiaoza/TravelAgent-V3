"""Reliable DB-backed generation job worker."""
import logging
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterator
from uuid import UUID

import httpx
import requests
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.trip import Trip, GenerationJob
from app.schemas.draft_boundary import DraftBoundaryError
from app.schemas.fill_draft import FillDraftValidationError, gate_fill_draft
from app.schemas.persist_draft import gate_persist_draft
from app.schemas.route_draft import gate_route_draft
from app.services.generation_jobs import (
    FILL_DRAFT_PAYLOAD_KEY,
    ClaimedGenerationJob,
    append_job_stage,
    claim_next_job,
    clear_job_fill_draft,
    finalize_job_success,
    mark_job_failed,
    recover_stale_jobs,
    renew_heartbeat,
    save_job_fill_draft,
    schedule_job_retry,
)
from app.agents.itinerary_gen import clear_itinerary_gen_thread
from app.services.itinerary import fill_itinerary_draft, route_itinerary_draft
from app.services.fact_verify import apply_verify_to_draft, verify_itinerary_draft
from app.services.route_degradation import collect_route_degradation_messages

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30.0
HEARTBEAT_JOIN_TIMEOUT_SECONDS = 1.0
ROUTE_STAGE_MESSAGE = "正在补路线..."
RESUME_ROUTE_MESSAGE = "沿用已生成的草稿，正在补路线..."
ROUTE_WARNING_PROGRESS = 75
VERIFY_WARNING_PROGRESS = 95
VERIFY_FAILED_MESSAGE = "时效核对未完成，行程已按路线生成"


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
    selected_entities: tuple[dict, ...]
    thread_id: str
    fill_draft: dict | None = None


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
    if isinstance(exc, DraftBoundaryError):
        return ErrorDisposition(True, "MALFORMED_MODEL_OUTPUT", exc.safe_message)
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
        job = db.get(GenerationJob, claim.id)
        payload = (job.payload if job is not None else None) or {}
        entities = payload.get("selected_entities") or []
        raw_draft = payload.get(FILL_DRAFT_PAYLOAD_KEY)
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
            selected_entities=tuple(entities),
            thread_id=f"trip-{trip.id}",
            fill_draft=raw_draft if isinstance(raw_draft, dict) else None,
        )


def _default_generate(
    generation_input: GenerationInput,
    on_stage: Callable[[str, int, str], bool | None] | None = None,
    *,
    claim: ClaimedGenerationJob | None = None,
) -> dict | None:
    """Fill, or resume from a stored fill draft, then route and verify.

    Returns None when this attempt no longer owns the job and must stop
    without finalizing.
    """
    resumed = generation_input.fill_draft is not None
    if resumed:
        try:
            filled = gate_fill_draft(deepcopy(generation_input.fill_draft), on_stage)
        except FillDraftValidationError:
            if claim is not None:
                clear_job_fill_draft(claim)
            raise
        logger.info(
            "resuming generation for trip %s from persisted fill draft",
            generation_input.trip_id,
        )
    else:
        # Selected entities never call itinerary_gen. A reusable fill_draft
        # already returned above. Clear only when this attempt will LLM-fill,
        # so a prior trip-{id} history cannot shape the next invoke.
        if not generation_input.selected_entities:
            clear_itinerary_gen_thread(generation_input.thread_id)
            logger.info(
                "cleared itinerary_gen checkpoints for %s before llm fill",
                generation_input.thread_id,
            )
        filled = fill_itinerary_draft(
            destination=generation_input.destination,
            city=generation_input.city,
            start_date=generation_input.start_date,
            end_date=generation_input.end_date,
            people_count=generation_input.people_count,
            budget_min=generation_input.budget_min,
            budget_max=generation_input.budget_max,
            user_prompt=generation_input.user_prompt,
            must_visit=list(generation_input.must_visit) or None,
            selected_entities=list(generation_input.selected_entities) or None,
            thread_id=generation_input.thread_id,
        )
        gate_fill_draft(filled, on_stage)
        if claim is not None and not save_job_fill_draft(claim, filled):
            return None
    if on_stage is not None:
        message = RESUME_ROUTE_MESSAGE if resumed else ROUTE_STAGE_MESSAGE
        if on_stage("route", 70, message) is False:
            return None
    routed = route_itinerary_draft(filled)
    gate_route_draft(routed, on_stage)
    recorded: list[str] = []
    for message in collect_route_degradation_messages(routed):
        if not _record_warning(on_stage, ROUTE_WARNING_PROGRESS, message, recorded):
            return None
    if not _emit_stage(on_stage, "verify", 90, "正在核对开放时间/天气..."):
        return None
    try:
        outcome = verify_itinerary_draft(
            routed,
            city=generation_input.city or generation_input.destination,
            start_date=generation_input.start_date,
        )
        apply_verify_to_draft(routed, outcome)
        if outcome.warnings:
            if not _record_warning(on_stage, VERIFY_WARNING_PROGRESS, outcome.summary[:500], recorded):
                return None
    except Exception:
        logger.exception("generation verify failed for trip %s", generation_input.trip_id)
        if not _record_warning(on_stage, VERIFY_WARNING_PROGRESS, VERIFY_FAILED_MESSAGE, recorded):
            return None
    return routed


def _emit_stage(
    on_stage: Callable[[str, int, str], bool | None] | None,
    key: str,
    progress: int,
    message: str,
) -> bool:
    """Return False only when the owner rejected the stage write."""
    if on_stage is None:
        return True
    return on_stage(key, progress, message) is not False


def _record_warning(
    on_stage: Callable[[str, int, str], bool | None] | None,
    progress: int,
    message: str,
    recorded: list[str],
) -> bool:
    text = " ".join(str(message).split()).strip()[:500]
    if not text or text in recorded:
        return True
    if not _emit_stage(on_stage, "warning", progress, text):
        return False
    recorded.append(text)
    return True


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
        using_default = regenerate is _default_generate
        resuming = using_default and generation_input.fill_draft is not None
        if not resuming:
            fill_message = (
                "正在按勾选排行程..."
                if generation_input.selected_entities
                else "正在规划景点..."
            )
            if not report("fill", 30, fill_message):
                return

        with _heartbeat_during(claim):
            if using_default:
                draft = _default_generate(
                    generation_input,
                    on_stage=report,
                    claim=claim,
                )
                if draft is None:
                    return
            else:
                draft = regenerate(generation_input)

        gate_persist_draft(draft, report)
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