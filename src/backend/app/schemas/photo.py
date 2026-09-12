from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PhotoUploadItemOut(BaseModel):
    id: UUID
    original_filename: str
    duplicate: bool = False


class PhotoUploadOut(BaseModel):
    job_id: UUID
    photos: list[PhotoUploadItemOut]


class PhotoJobOut(BaseModel):
    id: UUID
    trip_id: UUID
    status: str
    progress: int
    error: str | None = None

    model_config = {"from_attributes": True}


class PhotoCandidateOut(BaseModel):
    item_id: UUID
    poi_name: str | None = None
    score: float | None = None


class PhotoAssignmentOut(BaseModel):
    item_id: UUID | None = None
    assignment_type: str
    confidence: float
    is_confirmed: bool
    evidence: dict | None = None


class PhotoAssetOut(BaseModel):
    id: UUID
    trip_id: UUID
    original_filename: str
    captured_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    width: int | None = None
    height: int | None = None
    status: str
    error: str | None = None
    thumbnail_url: str | None = None
    preview_url: str | None = None
    assignment: PhotoAssignmentOut | None = None
    candidates: list[PhotoCandidateOut] = Field(default_factory=list)
    created_at: datetime | None = None


class PhotoMapSummaryItemOut(BaseModel):
    item_id: UUID
    count: int
    thumbnail_photo_id: UUID | None = None


class AssignmentPatch(BaseModel):
    action: str  # confirm | reassign | unassign
    item_id: UUID | None = None


class BatchAssignRequest(BaseModel):
    photo_ids: list[UUID]
    item_id: UUID
