"""Pydantic schemas for trip API requests and responses."""
from datetime import date, time, datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ── Request schemas ──

class TripCreate(BaseModel):
    destination: str = Field(..., min_length=1, max_length=128, examples=["北京"])
    city: str | None = Field(default=None, max_length=128)

    start_date: date = Field(..., examples=["2026-06-01"])
    end_date: date = Field(..., examples=["2026-06-03"])
    people_count: int = Field(default=1, ge=1, le=20)
    budget_min: int | None = None
    budget_max: int | None = None
    # 用户优化后的提示词，会传给 itinerary_gen 作为补充需求
    user_prompt: str | None = None
    # 用户明确指定的必去地点
    must_visit: list[str] | None = None


class TripGenerate(BaseModel):
    """Trigger itinerary generation for a trip."""
    pass  # No extra fields needed for MVP — reads trip constraints from DB later



class TripUpdate(BaseModel):
    """编辑行程标题（destination）。"""
    destination: str | None = Field(default=None, max_length=128)


class TripSuggestRequest(BaseModel):
    """用户自由输入的自然语言行程需求。"""
    text: str = Field(..., min_length=1)


class TripSuggestOut(BaseModel):
    """提示词优化结果：结构化参数 + 优化后的提示词。"""
    destination: str | None = None
    city: str | None = None

    must_visit: list[str] = []
    start_date: date | None = None
    end_date: date | None = None
    people_count: int = 1
    optimized_prompt: str = ""



class ItineraryItemUpdate(BaseModel):
    """用户编辑单个行程节点时允许修改的字段。"""
    poi_name: str | None = Field(default=None, max_length=256)
    start_time: time | None = None
    end_time: time | None = None
    notes: str | None = None


class ItineraryDayCreate(BaseModel):
    """新增一个 Day，默认追加到最后。"""
    day_index: int | None = None


class ItineraryItemCreate(BaseModel):
    """新增单个行程节点。"""
    day_id: UUID
    poi_name: str = Field(..., min_length=1, max_length=256)
    start_time: time | None = None
    end_time: time | None = None
    notes: str | None = None
    lat: float | None = None
    lng: float | None = None


class TripDaySync(BaseModel):
    """某一天内所有节点的新顺序。"""
    day_id: UUID
    item_ids: list[UUID]


class TripItemSync(BaseModel):
    """单个节点的轻量字段同步。"""
    item_id: UUID
    poi_name: str | None = None


class TripSyncRequest(BaseModel):
    """轻量最终一致性同步请求：只传排序和名称。"""
    days: list[TripDaySync] = []
    items: list[TripItemSync] = []


class ItineraryDayReorder(BaseModel):
    """同一天内的节点排序：item_ids 即新顺序。"""
    item_ids: list[UUID] = Field(..., min_length=1)


# ── Source (travelogue) parsing schemas ──

class SourceParseRequest(BaseModel):
    text: str = Field(..., min_length=1, examples=["第一天去了西湖，下午雷峰塔；第二天灵隐寺..."])


class SourceEntityOut(BaseModel):
    id: UUID | None = None
    poi_name: str
    day_index: int
    seq: int
    lat: float | None = None
    lng: float | None = None
    suggested_duration_h: float | None = None
    best_time: str | None = None
    cost_estimate: str | None = None

    model_config = {"from_attributes": True}


class SourceParseOut(BaseModel):
    entities: list[SourceEntityOut]



class SourceCreateRequest(BaseModel):
    """保存一篇攻略原文，后续再触发解析。"""
    title: str = Field(default="", max_length=256)
    url: str | None = None
    text: str = Field(..., min_length=1)


class SourceDocumentOut(BaseModel):
    id: UUID
    title: str
    url: str | None = None
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceDocumentDetailOut(SourceDocumentOut):
    entities: list[SourceEntityOut] = []

    model_config = {"from_attributes": True}


# ── Merge schemas ──

class MergeSourceIn(BaseModel):
    label: str = Field(..., min_length=1, examples=["攻略A"])
    entities: list[SourceEntityOut]




class EntityImportRequest(BaseModel):
    """将选中的攻略候选 POI 导入到指定行程。"""
    entity_ids: list[UUID] = Field(..., min_length=1)


class InferredTripOut(BaseModel):
    """从攻略内容中推断出的新行程基本信息。"""
    destination: str
    city: str | None = None

    day_count: int = Field(..., ge=1, le=30)


class MergeRequest(BaseModel):
    sources: list[MergeSourceIn] = Field(..., min_length=1)


class MergedEntityOut(BaseModel):
    poi_name: str
    lat: float | None = None
    lng: float | None = None
    suggested_duration_h: float | None = None
    best_time: str | None = None
    cost_estimate: str | None = None
    mention_count: int
    source_names: list[str]


class MergeOut(BaseModel):
    entities: list[MergedEntityOut]


# ── Fact check schemas ──

class FactCheckItem(BaseModel):
    poi_name: str
    date: date
    itinerary_item_id: UUID | None = None


class FactCheckRequest(BaseModel):
    items: list[FactCheckItem] = Field(..., min_length=1)
    trip_id: UUID | None = None


class FactCheckResult(BaseModel):
    poi_name: str
    date: date
    weather: str | None = None
    opening_hours: str | None = None
    risk: str | None = None  # "low" | "medium" | "high"
    risk_type: str | None = None  # weekly_closure / holiday_adjustment / weather_risk / none
    reason: str | None = None
    source: str | None = None
    needs_manual_confirmation: bool = True
    advice: str | None = None
    checked_at: datetime | None = None


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
    route_polyline: list[list[float]] | None = None
    notes: str | None = None
    amap_poi_id: str | None = None
    poi_address: str | None = None
    poi_type: str | None = None
    cost_estimate: int | None = None
    route_verified: bool | None = None
    travel_advice: str | None = None
    is_scenic: bool = False
    is_locked: bool

    model_config = {"from_attributes": True}


class ItineraryDayOut(BaseModel):
    id: UUID
    day_index: int
    date: date
    route_type: str = "city"
    items: list[ItineraryItemOut] = []

    model_config = {"from_attributes": True}


class TripOut(BaseModel):
    id: UUID
    destination: str
    city: str | None = None

    start_date: date
    end_date: date
    people_count: int
    budget_min: int | None = None
    budget_max: int | None = None
    user_prompt: str | None = None
    must_visit: list[str] | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    days: list[ItineraryDayOut] = []
    job_id: UUID | None = None

    model_config = {"from_attributes": True}


class TripBrief(BaseModel):
    """Minimal trip info for list views."""
    id: UUID
    destination: str
    start_date: date
    end_date: date
    status: str

    model_config = {"from_attributes": True}


# ── Chat schemas ──

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["帮我规划北京3日游，偏好历史文化"])
    thread_id: str | None = None  # 可选，指定后可以延续之前的对话


class ChatOut(BaseModel):
    reply: str
    thread_id: str


# ── Trip chat / AI delta schemas (Phase C1) ──

class TripChatContext(BaseModel):
    day_index: int | None = None
    item_id: UUID | None = None


class TripChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str | None = None
    context: TripChatContext | None = None


class ItineraryDeltaTarget(BaseModel):
    day_index: int | None = None
    item_id: UUID | None = None
    seq: int | None = None


class ItineraryDeltaPayload(BaseModel):
    poi_name: str | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration_h: float | None = None
    notes: str | None = None
    lat: float | None = None
    lng: float | None = None
    item_ids: list[UUID] | None = None


class ItineraryDelta(BaseModel):
    suggestion_id: UUID | None = None
    action: str = Field(..., examples=["add", "update", "delete", "move", "reorder"])
    target: ItineraryDeltaTarget | None = None
    payload: ItineraryDeltaPayload | None = None


class TripChatOut(BaseModel):
    reply: str
    thread_id: str
    suggestions: list[ItineraryDelta] = []


class DeltaApplyRequest(BaseModel):
    delta: ItineraryDelta
