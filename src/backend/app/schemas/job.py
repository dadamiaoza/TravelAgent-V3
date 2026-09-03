"""Pydantic schemas for generation job API responses."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class GenerationJobOut(BaseModel):
    id: UUID
    trip_id: UUID
    status: str
    progress: int
    message: str | None = None
    error_code: str | None = None
    attempts: int
    max_attempts: int
    status_version: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    next_run_at: datetime | None = None

    model_config = {"from_attributes": True}
