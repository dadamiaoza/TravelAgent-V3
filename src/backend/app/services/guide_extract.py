"""Parse travelogue text into POI entities. Service, not an Agent."""
from __future__ import annotations

import json
import re

from langchain_openai import ChatOpenAI

from app.core.config import settings

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

PARSE_GUIDE_PROMPT = (
    "你是攻略解析器。只从用户给出的攻略文本抽取景点，不要搜索网页。\n"
    "只输出 JSON 数组，不要其他文字：\n"
    '[{"poi_name":"...","day_index":1,"seq":1,"lat":null,"lng":null,'
    '"suggested_duration_h":null,"best_time":null,"cost_estimate":null,"visit_tips":null}]\n'
    "规则：day_index 从 1 起；同一天按出现顺序编 seq；文中没分天则全部 day_index=1；"
    "同名景点只保留第一次。时长、时段、花费、visit_tips 仅当原文有依据才填，否则 null；"
    "visit_tips 最多一句中文，不要编造开馆时间和门票。"
)


def extract_guide_entities(text: str) -> list[dict]:
    """Return parsed POI dicts from pasted guide text."""
    raw = (text or "").strip()
    if not raw:
        return []
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
    response = model.invoke(f"{PARSE_GUIDE_PROMPT}\n\n攻略文本：\n{raw}")
    content = getattr(response, "content", "") or ""
    if isinstance(content, list):
        content = "".join(
            block if isinstance(block, str) else str(getattr(block, "text", "") or block.get("text", ""))
            for block in content
        )
    content = _THINK_RE.sub("", str(content)).strip()
    fence = re.search(r"```json\s*(.*?)```", content, flags=re.DOTALL)
    if fence:
        content = fence.group(1)
    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    entities: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("poi_name") or "").strip()
        if not name:
            continue
        duration = item.get("suggested_duration_h")
        try:
            duration_h = float(duration) if duration not in (None, "") else None
        except (TypeError, ValueError):
            duration_h = None
        entities.append(
            {
                "poi_name": name,
                "day_index": int(item.get("day_index") or 1),
                "seq": int(item.get("seq") or 0),
                "lat": item.get("lat"),
                "lng": item.get("lng"),
                "suggested_duration_h": duration_h,
                "best_time": str(item.get("best_time") or "").strip() or None,
                "cost_estimate": str(item.get("cost_estimate") or "").strip() or None,
                "visit_tips": str(item.get("visit_tips") or "").strip() or None,
            }
        )
    return entities
