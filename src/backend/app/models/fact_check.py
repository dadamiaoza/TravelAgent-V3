"""FactCheck 持久化模型 — 保存每次时效风险校验结果，便于追溯查询。"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FactCheckRecord(Base):
    __tablename__ = "fact_checks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # 可选关联：记录来自哪个行程/哪个节点；没传时为 NULL，不影响落库
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )
    itinerary_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("itinerary_items.id", ondelete="SET NULL"), nullable=True
    )

    poi_name: Mapped[str] = mapped_column(String(256))
    check_date: Mapped[date] = mapped_column(Date())
    risk: Mapped[str] = mapped_column(String(16))
    risk_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source: Mapped[str | None] = mapped_column(Text(), nullable=True)
    weather: Mapped[str | None] = mapped_column(Text(), nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(Text(), nullable=True)
    needs_manual_confirmation: Mapped[bool] = mapped_column(Boolean(), default=True)
    advice: Mapped[str | None] = mapped_column(Text(), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
