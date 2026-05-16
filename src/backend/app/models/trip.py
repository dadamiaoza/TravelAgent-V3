"""SQLAlchemy ORM models for trips, days, and items."""
import uuid
from datetime import date, time, datetime
from sqlalchemy import String, Integer, Float, Boolean, Date, Time, DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination: Mapped[str] = mapped_column(String(128))
    start_date: Mapped[date] = mapped_column(Date())
    end_date: Mapped[date] = mapped_column(Date())
    people_count: Mapped[int] = mapped_column(Integer(), default=1)
    budget_min: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    budget_max: Mapped[int | None] = mapped_column(Integer(), nullable=True)
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
    cost_estimate: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean(), default=False)

    day: Mapped["ItineraryDay"] = relationship(back_populates="items")
