"""攻略来源与解析实体持久化模型。"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # 预留用户字段；当前单用户演示模式为 NULL，后续接入认证后启用
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    content: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    entities: Mapped[list["SourceEntity"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        order_by="SourceEntity.day_index, SourceEntity.seq",
    )


class SourceEntity(Base):
    """攻略解析出的候选 POI 实体。"""

    __tablename__ = "source_entities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE")
    )
    poi_name: Mapped[str] = mapped_column(String(256))
    day_index: Mapped[int] = mapped_column(Integer(), default=1)
    seq: Mapped[int] = mapped_column(Integer(), default=0)
    lat: Mapped[float | None] = mapped_column(Float(), nullable=True)
    lng: Mapped[float | None] = mapped_column(Float(), nullable=True)
    suggested_duration_h: Mapped[float | None] = mapped_column(Float(), nullable=True)
    best_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cost_estimate: Mapped[str | None] = mapped_column(String(256), nullable=True)
    visit_tips: Mapped[str | None] = mapped_column(Text(), nullable=True)

    source: Mapped["SourceDocument"] = relationship(back_populates="entities")
