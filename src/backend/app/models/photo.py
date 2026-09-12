"""Photo archive ORM: one original file, assignments point at itinerary items."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PhotoAsset(Base):
    __tablename__ = "photo_assets"
    __table_args__ = (
        UniqueConstraint("trip_id", "file_hash", name="uq_photo_assets_trip_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    file_path: Mapped[str] = mapped_column(Text(), nullable=False)
    preview_path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float(), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float(), nullable=True)
    exif_json: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    height: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    assignments: Mapped[list["PhotoAssignment"]] = relationship(
        back_populates="photo", cascade="all, delete-orphan"
    )


class PhotoAssignment(Base):
    __tablename__ = "photo_assignments"
    __table_args__ = (
        Index(
            "uq_photo_assignments_primary",
            "photo_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    photo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("photo_assets.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("itinerary_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="time")
    confidence: Mapped[float] = mapped_column(Float(), nullable=False, default=0)
    evidence_json: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean(), default=False)
    is_primary: Mapped[bool] = mapped_column(Boolean(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    photo: Mapped[PhotoAsset] = relationship(back_populates="assignments")


class PhotoJob(Base):
    __tablename__ = "photo_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress: Mapped[int] = mapped_column(Integer(), default=0)
    payload: Mapped[dict] = mapped_column(JSONB(), nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    stages: Mapped[list] = mapped_column(JSONB(), nullable=False, default=list, server_default=text("'[]'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )
