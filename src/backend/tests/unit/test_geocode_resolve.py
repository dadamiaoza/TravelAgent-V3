"""Geocoding on the generation hot path must not call MiniMax."""

from app.agents.tools import geo


def test_resolve_candidate_uses_name_match_for_weak_queries() -> None:
    pois = [
        {
            "name": "西湖景区游客中心",
            "address": "杭州市",
            "type": "风景名胜",
            "location": "120.1,30.2",
        },
        {
            "name": "西湖大道地铁站",
            "address": "杭州市",
            "type": "交通设施",
            "location": "120.2,30.3",
        },
    ]

    chosen = geo._resolve_candidate("西", pois)

    assert chosen is not None
    assert chosen["name"] in {"西湖景区游客中心", "西湖大道地铁站"}
