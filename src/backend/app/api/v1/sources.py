"""Source (travelogue) parsing API — Agent-powered guide parsing + multi-source merge."""
import json
import re

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage

from app.agents.guide_parser import create_guide_parser
from app.schemas.trip import (
    SourceParseRequest, SourceParseOut, SourceEntityOut,
    MergeRequest, MergeOut, MergedEntityOut,
)
from app.services.merge import merge_candidates

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("/parse", response_model=SourceParseOut)
def parse_source(body: SourceParseRequest):
    """Parse raw travelogue text into a structured candidate list."""
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
