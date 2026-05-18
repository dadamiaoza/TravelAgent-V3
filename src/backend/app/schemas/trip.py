"""Pydantic schemas for trip API requests and responses."""
from datetime import date, time, datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ── Request schemas ──

class TripCreate(BaseModel):
    destination: str = Field(..., min_length=1, max_length=128, examples=["北京"])
    start_date: date = Field(..., examples=["2026-06-01"])
    end_date: date = Field(..., examples=["2026-06-03"])
    people_count: int = Field(default=1, ge=1, le=20)
    budget_min: int | None = None
    budget_max: int | None = None


class TripGenerate(BaseModel):
    """Trigger itinerary generation for a trip."""
    pass  # No extra fields needed for MVP — reads trip constraints from DB later


# ── Source (travelogue) parsing schemas ──

class SourceParseRequest(BaseModel):
    text: str = Field(..., min_length=1, examples=["第一天去了西湖，下午雷峰塔；第二天灵隐寺..."])


class SourceEntityOut(BaseModel):
    poi_name: str
    day_index: int
    seq: int
    lat: float | None = None
    lng: float | None = None


class SourceParseOut(BaseModel):
    entities: list[SourceEntityOut]


# ── Fact check schemas ──

class FactCheckItem(BaseModel):
    poi_name: str
    date: date


class FactCheckRequest(BaseModel):
    items: list[FactCheckItem] = Field(..., min_length=1)


class FactCheckResult(BaseModel):
    poi_name: str
    date: date
    weather: str | None = None
    opening_hours: str | None = None
    risk: str | None = None  # "low" | "medium" | "high"


class FactCheckOut(BaseModel):
    results: list[FactCheckResult]


# ── Response schemas ──

class ItineraryItemOut(BaseModel):
    id: UUID
    seq: int
    poi_name: str
    start_time: time | None = None
    end_time: time | None = None
    lat: float | None = None
    lng: float | None = None
    transport_mode: str | None = None
    travel_minutes: int | None = None
    cost_estimate: int | None = None
    is_locked: bool

    model_config = {"from_attributes": True}


class ItineraryDayOut(BaseModel):
    id: UUID
    day_index: int
    date: date
    items: list[ItineraryItemOut] = []

    model_config = {"from_attributes": True}


class TripOut(BaseModel):
    id: UUID
    destination: str
    start_date: date
    end_date: date
    people_count: int
    budget_min: int | None = None
    budget_max: int | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    days: list[ItineraryDayOut] = []

    model_config = {"from_attributes": True}


class TripBrief(BaseModel):
    """Minimal trip info for list views."""
    id: UUID
    destination: str
    start_date: date
    end_date: date
    status: str

    model_config = {"from_attributes": True}
