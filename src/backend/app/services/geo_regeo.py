"""Amap reverse geocode. Returns a place name or None. Never invents coordinates."""
from __future__ import annotations

import logging
from collections.abc import Callable

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.cache_store import get_cache, set_cache

logger = logging.getLogger(__name__)

AMAP_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
FetchFn = Callable[[str, dict], dict]


def _default_fetch(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=8)
    response.raise_for_status()
    return response.json()


def _name_from_regeo(payload: dict) -> str | None:
    regeo = payload.get("regeocode") or {}
    pois = regeo.get("pois") or []
    if isinstance(pois, list):
        for poi in pois:
            name = (poi or {}).get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    formatted = regeo.get("formatted_address")
    if isinstance(formatted, str) and formatted.strip():
        return formatted.strip()
    component = regeo.get("addressComponent") or {}
    neighborhood = component.get("neighborhood") or {}
    name = neighborhood.get("name") if isinstance(neighborhood, dict) else None
    if isinstance(name, list):
        name = name[0] if name else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def reverse_geocode_amap(
    lng: float,
    lat: float,
    db: Session | None = None,
    *,
    fetch: FetchFn | None = None,
) -> str | None:
    """GCJ-02 lng/lat → display name. None if key missing or API fails."""
    if not settings.amap_api_key and fetch is None:
        return None
    cache_key = f"{round(lng, 5)},{round(lat, 5)}"
    if db is not None:
        cached = get_cache(db, "regeo", cache_key)
        if cached and cached.get("place_name"):
            return str(cached["place_name"])
    params = {
        "key": settings.amap_api_key,
        "location": f"{lng},{lat}",
        "extensions": "all",
        "radius": 300,
    }
    try:
        payload = (fetch or _default_fetch)(AMAP_REGEO_URL, params)
    except Exception as exc:
        logger.warning("reverse geocode failed: %s", exc)
        return None
    if str(payload.get("status")) != "1":
        return None
    name = _name_from_regeo(payload)
    if name and db is not None:
        set_cache(db, "regeo", cache_key, {"place_name": name})
    return name
