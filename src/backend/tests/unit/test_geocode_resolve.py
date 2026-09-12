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


def test_huangxing_road_prefers_full_pedestrian_street_name() -> None:
    pois = [
        {"name": "黄兴路", "cityname": "上海市", "location": "121.528,31.281"},
        {"name": "黄兴南路步行街", "cityname": "长沙市", "location": "112.976,28.192"},
    ]
    chosen = geo._resolve_candidate("黄兴路步行街", pois)
    assert chosen is not None
    assert chosen["cityname"] == "长沙市"


def test_filter_pois_by_city_drops_other_province() -> None:
    pois = [
        {"name": "黄兴路", "cityname": "上海市", "adname": "杨浦区"},
        {"name": "黄兴南路步行街", "cityname": "长沙市", "adname": "芙蓉区"},
    ]
    matched = geo._filter_pois_by_city(pois, "长沙")
    assert [row["cityname"] for row in matched] == ["长沙市"]


def test_result_matches_city_accepts_municipality_suffix() -> None:
    assert geo._result_matches_city({"city": "长沙市"}, "长沙")
    assert not geo._result_matches_city({"city": "上海市"}, "长沙")
