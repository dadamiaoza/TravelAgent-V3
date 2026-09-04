"""Source (travelogue) parsing API — Agent-powered guide parsing + multi-source merge."""
import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from app.core.config import settings
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
    InferredTripOut,
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


@router.post("/{source_id}/infer-trip", response_model=InferredTripOut)
def infer_trip_from_source(source_id: UUID, db: Session = Depends(get_db)):
    """从攻略内容中自动推断目的地和天数，用于创建新行程。"""
    doc = db.query(SourceDocument).filter(SourceDocument.id == source_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Source not found")

    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
    prompt = (
        "你是旅行规划助手。请根据以下攻略内容推断行程基本信息。\n"
        "只输出 JSON，不要其他文字，格式："
        '{"destination": "展示名称", "city": "干净城市名", "day_count": 天数整数}\n\n'
        f"攻略标题：{doc.title}\n"
        f"攻略内容：\n{doc.content}\n"
    )
    response = model.invoke(prompt)
    content = response.content.strip()
    content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
    fence = re.search(r"```json\s*(.*?)```", content, flags=re.DOTALL)
    if fence:
        content = fence.group(1)
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end <= start:
        raise HTTPException(status_code=500, detail="Failed to infer trip from source")
    data = json.loads(content[start:end + 1])
    return InferredTripOut(
        destination=str(data.get("destination", "未知目的地")),
          city=str(data.get("city") or "").strip() or None,
        day_count=max(1, int(data.get("day_count", 1))),
    )


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
