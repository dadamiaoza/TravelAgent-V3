"""Destination IANA timezone for library day partitions.

Stored ``trips.timezone`` wins when it is a valid IANA name. Otherwise the
city, then the destination label, is looked up in ``CITY_TIMEZONES``.

Unknown places stay unset. Callers then fall back to the viewer's local
calendar day and should say so. Keep this map in sync with
``src/frontend/src/lib/destinationTimezones.ts``.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Normalized place label → IANA. Suffixes such as 市 are stripped first.
CITY_TIMEZONES: dict[str, str] = {
    # Mainland China (Asia/Shanghai), with Xinjiang called out.
    "北京": "Asia/Shanghai",
    "上海": "Asia/Shanghai",
    "杭州": "Asia/Shanghai",
    "成都": "Asia/Shanghai",
    "厦门": "Asia/Shanghai",
    "广州": "Asia/Shanghai",
    "深圳": "Asia/Shanghai",
    "西安": "Asia/Shanghai",
    "重庆": "Asia/Shanghai",
    "南京": "Asia/Shanghai",
    "苏州": "Asia/Shanghai",
    "武汉": "Asia/Shanghai",
    "长沙": "Asia/Shanghai",
    "青岛": "Asia/Shanghai",
    "大连": "Asia/Shanghai",
    "三亚": "Asia/Shanghai",
    "昆明": "Asia/Shanghai",
    "桂林": "Asia/Shanghai",
    "丽江": "Asia/Shanghai",
    "拉萨": "Asia/Shanghai",
    "哈尔滨": "Asia/Shanghai",
    "天津": "Asia/Shanghai",
    "宁波": "Asia/Shanghai",
    "福州": "Asia/Shanghai",
    "珠海": "Asia/Shanghai",
    "乌鲁木齐": "Asia/Urumqi",
    "喀什": "Asia/Urumqi",
    "香港": "Asia/Hong_Kong",
    "澳门": "Asia/Macau",
    "台北": "Asia/Taipei",
    # Japan
    "东京": "Asia/Tokyo",
    "東京": "Asia/Tokyo",
    "大阪": "Asia/Tokyo",
    "京都": "Asia/Tokyo",
    "北海道": "Asia/Tokyo",
    "札幌": "Asia/Tokyo",
    "冲绳": "Asia/Tokyo",
    "沖縄": "Asia/Tokyo",
    "奈良": "Asia/Tokyo",
    "福冈": "Asia/Tokyo",
    "福岡": "Asia/Tokyo",
    "名古屋": "Asia/Tokyo",
    "横滨": "Asia/Tokyo",
    "神户": "Asia/Tokyo",
    "tokyo": "Asia/Tokyo",
    "osaka": "Asia/Tokyo",
    "kyoto": "Asia/Tokyo",
    # Elsewhere used by the library demo and common trips.
    "首尔": "Asia/Seoul",
    "首爾": "Asia/Seoul",
    "釜山": "Asia/Seoul",
    "新加坡": "Asia/Singapore",
    "曼谷": "Asia/Bangkok",
    "清迈": "Asia/Bangkok",
    "普吉": "Asia/Bangkok",
    "巴厘岛": "Asia/Makassar",
    "悉尼": "Australia/Sydney",
    "巴黎": "Europe/Paris",
    "伦敦": "Europe/London",
    "罗马": "Europe/Rome",
    "巴塞罗那": "Europe/Madrid",
    "迪拜": "Asia/Dubai",
    "纽约": "America/New_York",
    "洛杉矶": "America/Los_Angeles",
    "檀香山": "Pacific/Honolulu",
    "雷克雅未克": "Atlantic/Reykjavik",
    "冰岛": "Atlantic/Reykjavik",
}


def _normalize_place(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text.endswith("市") and len(text) > 1:
        text = text[:-1]
    return text


def is_valid_iana(name: str | None) -> bool:
    if not name or not name.strip():
        return False
    try:
        ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def timezone_for_place(city: str | None, destination: str | None = None) -> str | None:
    """Return an IANA name for a known city or destination label."""
    for raw in (city, destination):
        zone = CITY_TIMEZONES.get(_normalize_place(raw))
        if zone:
            return zone
    return None


def effective_timezone(
    stored: str | None,
    city: str | None = None,
    destination: str | None = None,
) -> str | None:
    """Prefer a valid stored IANA name, else derive from city / destination."""
    if is_valid_iana(stored):
        return stored.strip()
    return timezone_for_place(city, destination)
