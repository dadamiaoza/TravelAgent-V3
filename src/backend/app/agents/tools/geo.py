"""Geocoding tool — converts POI names to lat/lng coordinates.

Primary: Amap Place Search API when a city is provided (better for POIs inside scenic areas)
Fallback: Amap Geocoding API, then mock POI database.
"""
import logging
from typing import Dict

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Mock fallback database ──
_MOCK_POI: Dict[str, Dict[str, float]] = {
    "西湖": {"lat": 30.2374, "lng": 120.1407},
    "雷峰塔": {"lat": 30.2336, "lng": 120.1485},
    "灵隐寺": {"lat": 30.2427, "lng": 120.1015},
    "故宫": {"lat": 39.9163, "lng": 116.3972},
    "天安门": {"lat": 39.9087, "lng": 116.3975},
    "长城": {"lat": 40.3597, "lng": 116.0174},
    "颐和园": {"lat": 39.9996, "lng": 116.2755},
    "天坛": {"lat": 39.8827, "lng": 116.4066},
    "外滩": {"lat": 31.2400, "lng": 121.4904},
    "东方明珠": {"lat": 31.2397, "lng": 121.4998},
    "南京路": {"lat": 31.2343, "lng": 121.4718},
    "豫园": {"lat": 31.2272, "lng": 121.4875},
    "迪士尼": {"lat": 31.1433, "lng": 121.6613},
    "大雁塔": {"lat": 34.2180, "lng": 108.9593},
    "兵马俑": {"lat": 34.3853, "lng": 109.2732},
    "鼓楼": {"lat": 39.9419, "lng": 116.3892},
    "南锣鼓巷": {"lat": 39.9374, "lng": 116.4034},
    "798": {"lat": 39.9842, "lng": 116.4952},
    "鸟巢": {"lat": 39.9919, "lng": 116.3906},
    "水立方": {"lat": 39.9917, "lng": 116.3842},
}


def geocode_poi(
    name: str,
    city: str = "",
    mock_fallback: bool = True,
) -> dict | None:
    """Convert a POI name to geographic coordinates.

    With a city context, prefer Amap Place Search because it returns precise
    sub-POI locations inside scenic areas (e.g. 武功山金顶, 吊马桩).
    """
    if settings.amap_api_key:
        # 1. 带城市时先用 POI 搜索，避免把景区子景点匹配到外地同名地点
        if city:
            try:
                result = _geocode_amap_poi(name, city)
                if result:
                    return result
            except Exception:
                logger.warning("高德 POI 搜索失败，尝试地理编码", exc_info=True)

        # 2. 再尝试传统 geocode
        try:
            result = _geocode_amap(name, city)
            if result:
                return result
        except Exception:
            logger.warning("高德地理编码失败，降级到 mock", exc_info=True)

    if mock_fallback:
        return _geocode_mock(name)
    return None


# ── Amap API ──

AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"


def _geocode_amap_poi(name: str, city: str = "") -> dict | None:
    """使用高德 POI 搜索获取更精确的景点坐标。"""
    import re
    # 去掉括号说明，例如“金顶(赏日落)”用“金顶”搜索
    search_name = re.sub(r"[（(][^）)]*[）)]", "", name).strip() or name
    params = {
        "key": settings.amap_api_key,
        "keywords": search_name,
        "offset": 20,
        "extensions": "all",
    }
    if city:
        params["city"] = city

    resp = requests.get(AMAP_PLACE_TEXT_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "1" or int(data.get("count", 0)) == 0:
        return None

    pois = data.get("pois") or []
    if not pois:
        return None

    best = _best_match_poi(search_name, pois)
    if best is None:
        return None

    location = best.get("location", "")
    if not location:
        return None
    lng_str, lat_str = location.split(",")
    return {
        "name": best.get("name", name),
        "lat": float(lat_str),
        "lng": float(lng_str),
        "city": best.get("cityname") or best.get("adname", ""),
    }


def _geocode_amap(name: str, city: str = "") -> dict | None:
    """Call Amap Geocoding API. Returns None if no result found."""
    params = {
        "key": settings.amap_api_key,
        "address": name,
    }
    if city:
        params["city"] = city

    resp = requests.get(AMAP_GEOCODE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "1" or int(data.get("count", 0)) == 0:
        return None

    geocode = data["geocodes"][0]
    location = geocode["location"]
    lng_str, lat_str = location.split(",")
    return {
        "name": name,
        "lat": float(lat_str),
        "lng": float(lng_str),
        "city": geocode.get("city", ""),
    }


def _best_match_poi(query_name: str, pois: list) -> dict | None:
    """从 POI 搜索结果中按名称相似度选择最佳匹配。

    会去掉查询中的括号说明（如“金顶(赏日落)” → “金顶”），
    因为这些括号内容通常是用户补充的场景描述，不是 POI 正式名称。
    """
    import re

    base_query = re.sub(r"[（(][^）)]*[）)]", "", query_name).strip()
    if not base_query:
        base_query = query_name

    if not pois:
        return None
    best = pois[0]
    best_score = _name_match_score(base_query, best.get("name", ""))
    for p in pois[1:]:
        score = _name_match_score(base_query, p.get("name", ""))
        if score > best_score:
            best = p
            best_score = score
    # 带城市上下文的 POI 搜索已经过滤到目标城市，允许较低匹配阈值
    return best if best_score >= 1 else None


def _name_match_score(query: str, result: str) -> int:
    """简单名称匹配打分：2=完全/包含，1=单字重叠，0=不匹配。"""
    import re

    q_clean = re.sub(r"[（）()\s]", "", query)
    r_clean = re.sub(r"[（）()\s]", "", result)
    if q_clean == r_clean:
        return 2
    if q_clean in r_clean or r_clean in q_clean:
        return 2
    if any(ch in r_clean for ch in q_clean):
        return 1
    return 0


# ── Mock fallback ──

def _geocode_mock(name: str) -> dict:
    """Mock geocode using hardcoded database with hash-based fallback."""
    if name in _MOCK_POI:
        return {
            "name": name,
            "lat": _MOCK_POI[name]["lat"],
            "lng": _MOCK_POI[name]["lng"],
            "city": "",
        }

    import hashlib
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    lat = 30.0 + (h % 10000) / 10000.0 * 10.0
    lng = 116.0 + ((h >> 16) % 10000) / 10000.0 * 10.0
    return {"name": name, "lat": round(lat, 4), "lng": round(lng, 4), "city": ""}
