"""Source (travelogue) parsing API — Agent-powered guide parsing + multi-source merge."""
import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage
from sqlalchemy.orm import Session

from app.agents.guide_parser import create_guide_parser
from app.db.session import get_db
from app.models.source import SourceDocument, SourceEntity
from app.schemas.trip import (
    SourceCreateRequest,
    SourceDocumentDetailOut,
    SourceDocumentOut,
    SourceParseRequest,
    SourceParseOut,
    SourceEntityOut,
    MergeRequest,
    MergeOut,
    MergedEntityOut,
)
from app.services.merge import merge_candidates

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=SourceDocumentOut, status_code=201)
def create_source(body: SourceCreateRequest, db: Session = Depends(get_db)):
    """保存一篇攻略原文，持久化后供后续解析。"""
    doc = SourceDocument(
        title=body.title or body.text[:30],
        url=body.url,
        content=body.text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("", response_model=list[SourceDocumentOut])
def list_sources(db: Session = Depends(get_db)):
    """列出所有已保存的攻略来源。"""
    return db.query(SourceDocument).order_by(SourceDocument.created_at.desc()).all()


@router.get("/{source_id}", response_model=SourceDocumentDetailOut)
def get_source(source_id: UUID, db: Session = Depends(get_db)):
    """获取攻略详情及已解析实体。"""
    doc = db.query(SourceDocument).filter(SourceDocument.id == source_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Source not found")
    return doc


@router.post("/{source_id}/parse", response_model=SourceDocumentDetailOut)
def parse_source_persist(source_id: UUID, db: Session = Depends(get_db)):
    """对已保存的攻略执行 Agent 解析，并将候选实体持久化。"""
    doc = db.query(SourceDocument).filter(SourceDocument.id == source_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Source not found")

    # 重复解析时先清空旧实体，避免堆积
    db.query(SourceEntity).filter(SourceEntity.source_id == doc.id).delete()
    db.flush()

    agent = create_guide_parser()
    result = agent.invoke({"messages": [{"role": "user", "content": doc.content}]})
    raw = _extract_json(result["messages"])

    for item in raw:
        db.add(SourceEntity(
            source_id=doc.id,
            poi_name=item["poi_name"],
            day_index=item.get("day_index", 1),
            seq=item.get("seq", 0),
            lat=item.get("lat"),
            lng=item.get("lng"),
            suggested_duration_h=item.get("suggested_duration_h"),
            best_time=item.get("best_time"),
            cost_estimate=item.get("cost_estimate"),
        ))

    db.commit()
    db.refresh(doc)
    return doc


@router.post("/parse", response_model=SourceParseOut)
def parse_source(body: SourceParseRequest):
    """无状态解析：直接返回候选列表，不落库（保留兼容）。"""
    agent = create_guide_parser()

    result = agent.invoke({"messages": [{"role": "user", "content": body.text}]})

    raw = _extract_json(result["messages"])
    entities = []
    for item in raw:
        entities.append(SourceEntityOut(
            poi_name=item["poi_name"],
            day_index=item.get("day_index", 1),
            seq=item.get("seq", 0),
            lat=item.get("lat"),
            lng=item.get("lng"),
            suggested_duration_h=item.get("suggested_duration_h"),
            best_time=item.get("best_time"),
            cost_estimate=item.get("cost_estimate"),
        ))

    return SourceParseOut(entities=entities)


@router.post("/merge", response_model=MergeOut)
def merge_sources(body: MergeRequest):
    """Merge candidate lists from multiple parsed sources via LLM semantic dedup."""
    sources = [
        (src.label, [e.model_dump(exclude_none=True) for e in src.entities])
        for src in body.sources
    ]
    merged = merge_candidates(sources)
    entities = [MergedEntityOut(**item) for item in merged]
    return MergeOut(entities=entities)


def _extract_json(messages: list) -> list:
    """Extract JSON array from agent messages."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = getattr(msg, "content", "")
            if not content:
                continue
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end > start:
                return json.loads(content[start:end + 1])
    raise HTTPException(status_code=500, detail="Agent did not return valid JSON")
