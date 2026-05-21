"""Multi-source merge & dedup via LLM semantic judgment.

Takes parsed candidate lists from multiple guide sources, asks the LLM to
identify which POIs are the same across sources, and returns a deduplicated
list with mention_count and source_names.
"""
import json
import re

from langchain_openai import ChatOpenAI

from app.core.config import settings


def merge_candidates(sources: list[tuple[str, list[dict]]]) -> list[dict]:
    """Merge candidate lists from multiple sources using LLM semantic dedup.

    Args:
        sources: List of (label, entities) tuples, e.g.
            [("攻略A", [{"poi_name": "西湖", ...}, ...]),
             ("攻略B", [{"poi_name": "杭州西湖", ...}, ...])]

    Returns:
        Merged list with added fields: mention_count (int), source_names (list[str]).
    """
    if len(sources) <= 1:
        result = []
        for label, entities in sources:
            for e in entities:
                item = dict(e)
                item["mention_count"] = 1
                item["source_names"] = [label]
                result.append(item)
        return result

    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    prompt = _build_merge_prompt(sources)
    response = model.invoke(prompt)
    return _parse_merge_response(response.content)


def _build_merge_prompt(sources: list[tuple[str, list[dict]]]) -> str:
    blocks = []
    for label, entities in sources:
        safe = [{k: v for k, v in e.items() if k not in ("mention_count", "source_names")}
                for e in entities]
        blocks.append(f"### {label}\n```json\n{json.dumps(safe, ensure_ascii=False, indent=2)}\n```")

    joined = "\n\n".join(blocks)
    return (
        "You are merging POI candidate lists from multiple travel guides.\n"
        "Each source below is a parsed list from one guide article.\n"
        "Identify which POIs refer to the SAME real-world attraction and merge them.\n\n"
        "Rules:\n"
        "- Same POI with identical or similar names → merge (e.g. \"西湖\" and \"杭州西湖\")\n"
        "- Obvious typos → merge (e.g. \"雷锋塔\" and \"雷峰塔\")\n"
        "- Same name but clearly different cities → do NOT merge (e.g. Beijing Drum Tower vs Nanjing Drum Tower)\n"
        "- For merged items, pick the most complete poi_name as the canonical name\n"
        "- For fields like lat/lng/suggested_duration_h/best_time/cost_estimate: keep the first non-null value\n"
        "- day_index and seq from individual sources are discarded (not meaningful after merge)\n\n"
        f"{joined}\n\n"
        "Output a single JSON array (no other text). Each item must have:\n"
        "- All original fields from the input (poi_name, lat, lng, suggested_duration_h, best_time, cost_estimate)\n"
        "- plus \"mention_count\" (int): how many sources mention this POI\n"
        "- plus \"source_names\" (list[str]): which sources it came from\n\n"
        "Sort by mention_count descending (most mentioned first)."
    )


def _parse_merge_response(content: str) -> list[dict]:
    content = content.strip()
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end > start:
        return json.loads(content[start:end + 1])

    match = re.search(r"\[.*]", content, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError(f"LLM merge did not return valid JSON array: {content[:300]}")
