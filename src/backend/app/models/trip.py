"""SQLAlchemy ORM models for trips, days, and items."""
import uuid
from datetime import date, time, datetime
from sqlalchemy import String, Integer, Float, Boolean, Date, Time, DateTime, ForeignKey, Text, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination: Mapped[str] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)

    start_date: Mapped[date] = mapped_column(Date())
    end_date: Mapped[date] = mapped_column(Date())
    people_count: Mapped[int] = mapped_column(Integer(), default=1)
    budget_min: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    budget_max: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    user_prompt: Mapped[str | None] = mapped_column(Text(), nullable=True)
    must_visit: Mapped[list | None] = mapped_column(JSONB(), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    days: Mapped[list["ItineraryDay"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="ItineraryDay.day_index"
    )


class ItineraryDay(Base):
    __tablename__ = "itinerary_days"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    day_index: Mapped[int] = mapped_column(Integer())
    date: Mapped[date] = mapped_column(Date())
    # 当天路线类型：city=城市常规路线，scenic=景区内部（步道/索道/接驳车）
    route_type: Mapped[str] = mapped_column(String(16), default="city", server_default="city")

    trip: Mapped["Trip"] = relationship(back_populates="days")
    items: Mapped[list["ItineraryItem"]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="ItineraryItem.seq"
    )


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    day_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("itinerary_days.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer())
    poi_name: Mapped[str] = mapped_column(String(256))
    start_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float(), nullable=True)
    lng: Mapped[float | None] = mapped_column(Float(), nullable=True)
    transport_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    travel_minutes: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    # 从上一个节点到当前节点的真实道路坐标，格式 [[lng,lat], ...]
    route_polyline: Mapped[list | None] = mapped_column(JSONB(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    amap_poi_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    poi_address: Mapped[str | None] = mapped_column(Text(), nullable=True)
    poi_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    cost_estimate: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    # 该段路线是否来自高德真实路径；景区索道/接驳车等属于建议，不标记为已核实
    route_verified: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    # 无法核实的景区交通建议文案（如“以景区现场指引/官方班次为准”）
    travel_advice: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean(), default=False)

    @property
    def is_scenic(self) -> bool:
        """判断该节点是否位于景区/山岳类地点。"""
        text = f"{self.poi_name or ''} {self.poi_type or ''}"
        return any(
            token in text
            for token in ("景区", "风景名胜", "索道", "缆车", "登山步道", "游步道", "国家级景点", "山")
        )

    day: Mapped["ItineraryDay"] = relationship(back_populates="items")


class AmapCache(Base):
    __tablename__ = "amap_cache"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cache_type: Mapped[str] = mapped_column(String(32), index=True)
    cache_key: Mapped[str] = mapped_column(Text())
    payload: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        Index(
            "uq_generation_jobs_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_generation_jobs_active_trip",
            "trip_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running', 'retry_wait')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress: Mapped[int] = mapped_column(Integer(), default=0)
    attempts: Mapped[int] = mapped_column(Integer(), default=0)
    max_attempts: Mapped[int] = mapped_column(Integer(), default=3, server_default=text("3"))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_token: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_version: Mapped[int] = mapped_column(Integer(), default=0, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
