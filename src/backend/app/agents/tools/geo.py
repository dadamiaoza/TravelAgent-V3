"""Geocoding tool — converts POI names to lat/lng coordinates.

Primary: Amap Geocoding API (when AMAP_API_KEY is configured)
Fallback: mock POI database (when no key or API fails)
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


def geocode_poi(name: str, city: str = "") -> dict:
    """Convert a POI name to geographic coordinates.

    Tries Amap Geocoding API first. Falls back to mock database if the API
    is unavailable (no key configured, network error, or empty result).

    Args:
        name: POI name in Chinese, e.g. "西湖", "故宫"
        city: Optional city name for more precise results, e.g. "北京"

    Returns:
        Dict with keys: name (str), lat (float), lng (float).
    """
    if settings.amap_api_key:
        try:
            result = _geocode_amap(name, city)
            if result:
                return result
        except Exception:
            logger.warning("高德地理编码失败，降级到 mock", exc_info=True)

    return _geocode_mock(name)


# ── Amap API ──

AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"


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

    # Amap returns "lng,lat" — split and convert
    location = data["geocodes"][0]["location"]
    lng_str, lat_str = location.split(",")
    return {"name": name, "lat": float(lat_str), "lng": float(lng_str)}


# ── Mock fallback ──

def _geocode_mock(name: str) -> dict:
    """Mock geocode using hardcoded database with hash-based fallback."""
    if name in _MOCK_POI:
        return {"name": name, "lat": _MOCK_POI[name]["lat"], "lng": _MOCK_POI[name]["lng"]}

    import hashlib
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    lat = 30.0 + (h % 10000) / 10000.0 * 10.0
    lng = 116.0 + ((h >> 16) % 10000) / 10000.0 * 10.0
    return {"name": name, "lat": round(lat, 4), "lng": round(lng, 4)}
