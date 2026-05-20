"""Attraction search and travel estimation tools — Step 4 of agent learning path.

Travel time: Amap Direction API (when AMAP_API_KEY is configured)
Fallback: hash-based mock estimation (when no key or API fails)
"""
import logging
import math

import requests

from app.agents.tools.geo import geocode_poi
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Amap Direction API URLs ──

AMAP_WALKING_URL = "https://restapi.amap.com/v3/direction/walking"
AMAP_DRIVING_URL = "https://restapi.amap.com/v3/direction/driving"
AMAP_TRANSIT_URL = "https://restapi.amap.com/v3/direction/transit/integrated"
AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"

_MOCK_ATTRACTIONS: dict[str, list[dict]] = {
    "杭州": [
        {"name": "西湖", "category": "自然风光", "duration_h": 3, "rating": 4.9},
        {"name": "雷峰塔", "category": "历史古迹", "duration_h": 1.5, "rating": 4.6},
        {"name": "灵隐寺", "category": "寺庙", "duration_h": 2, "rating": 4.7},
        {"name": "龙井村", "category": "自然风光", "duration_h": 2.5, "rating": 4.5},
        {"name": "九溪烟树", "category": "自然风光", "duration_h": 2, "rating": 4.6},
        {"name": "苏堤", "category": "自然风光", "duration_h": 1.5, "rating": 4.8},
        {"name": "河坊街", "category": "美食购物", "duration_h": 2, "rating": 4.3},
        {"name": "宋城", "category": "主题公园", "duration_h": 4, "rating": 4.4},
        {"name": "西溪湿地", "category": "自然风光", "duration_h": 3, "rating": 4.5},
        {"name": "钱塘江大桥", "category": "城市地标", "duration_h": 1, "rating": 4.2},
    ],
    "北京": [
        {"name": "故宫", "category": "历史古迹", "duration_h": 4, "rating": 4.9},
        {"name": "天安门", "category": "城市地标", "duration_h": 1, "rating": 4.8},
        {"name": "天坛", "category": "历史古迹", "duration_h": 2, "rating": 4.7},
        {"name": "颐和园", "category": "自然风光", "duration_h": 3, "rating": 4.8},
        {"name": "长城", "category": "历史古迹", "duration_h": 5, "rating": 4.9},
        {"name": "鸟巢", "category": "现代建筑", "duration_h": 1.5, "rating": 4.3},
        {"name": "南锣鼓巷", "category": "美食购物", "duration_h": 2, "rating": 4.4},
        {"name": "798艺术区", "category": "文化艺术", "duration_h": 3, "rating": 4.5},
        {"name": "鼓楼", "category": "历史古迹", "duration_h": 1, "rating": 4.3},
        {"name": "簋街", "category": "美食购物", "duration_h": 2, "rating": 4.4},
    ],
    "上海": [
        {"name": "外滩", "category": "城市地标", "duration_h": 2, "rating": 4.8},
        {"name": "东方明珠", "category": "现代建筑", "duration_h": 2, "rating": 4.5},
        {"name": "南京路", "category": "美食购物", "duration_h": 2.5, "rating": 4.3},
        {"name": "豫园", "category": "历史古迹", "duration_h": 2, "rating": 4.4},
        {"name": "迪士尼", "category": "主题公园", "duration_h": 8, "rating": 4.7},
        {"name": "田子坊", "category": "美食购物", "duration_h": 2, "rating": 4.2},
        {"name": "上海博物馆", "category": "文化艺术", "duration_h": 2.5, "rating": 4.4},
        {"name": "新天地", "category": "美食购物", "duration_h": 1.5, "rating": 4.1},
        {"name": "朱家角", "category": "自然风光", "duration_h": 4, "rating": 4.3},
        {"name": "上海科技馆", "category": "现代建筑", "duration_h": 3, "rating": 4.2},
    ],
}

_TRAVEL_TIMES: dict[str, dict[str, int]] = {
    "西湖": {"雷峰塔": 20, "灵隐寺": 30, "龙井村": 35},
    "天安门": {"故宫": 10, "天坛": 25, "南锣鼓巷": 20},
    "外滩": {"南京路": 15, "豫园": 20, "东方明珠": 10},
}


def search_attractions(destination: str, preference: str = "") -> str:
    """搜索目的地城市的景点。

    优先使用高德 POI 搜索 API。如果 API 不可用（无 Key、网络错误、空结果），
    自动降级到本地 mock 数据。

    Args:
        destination: 城市名，如 "杭州"、"北京"
        preference: 可选偏好分类，如 "自然风光"、"历史古迹"

    Returns:
        格式化字符串，每行列出一个景点（名称、分类、建议时长、评分）。
    """
    if settings.amap_api_key:
        try:
            result = _search_attractions_amap(destination, preference)
            if result:
                return result
        except Exception:
            logger.warning("高德 POI 搜索失败，降级到 mock", exc_info=True)

    return _search_attractions_mock(destination, preference)


# ── 高德 POI 搜索 API ──

def _search_attractions_amap(destination: str, preference: str) -> str | None:
    """调用高德 POI 关键字搜索。返回格式化字符串，失败返回 None。"""
    # A 方案：preference 直接作为 keywords（效果不好时升级为 types 映射）
    keywords = preference or "景点"

    params = {
        "key": settings.amap_api_key,
        "keywords": keywords,
        "city": destination,
        "offset": 20,
        "extensions": "all",
    }

    resp = requests.get(AMAP_PLACE_TEXT_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "1" or int(data.get("count", 0)) == 0:
        return None

    pois = data.get("pois", [])
    if not pois:
        return None

    lines = [f"{destination} 景点列表（偏好：{preference or '全部'}）："]
    for i, p in enumerate(pois, 1):
        name = p.get("name", "未知")
        # type 格式："风景名胜;旅游景点;国家级景点" → 取第一段
        raw_type = p.get("type", "")
        category = raw_type.split(";")[0] if raw_type else "其他"
        rating = p.get("rating", "")
        rating_str = f"评分{rating}" if rating else "暂无评分"
        lines.append(f"  {i}. {name} | {category} | 建议2h | {rating_str}")

    return "\n".join(lines)


# ── Mock 降级兜底 ──

def _search_attractions_mock(destination: str, preference: str) -> str:
    """本地 mock 数据兜底。"""
    if destination not in _MOCK_ATTRACTIONS:
        return f"未找到 {destination} 的景点数据。支持的城市：{', '.join(_MOCK_ATTRACTIONS.keys())}"

    pois = _MOCK_ATTRACTIONS[destination]
    if preference:
        pois = [p for p in pois if preference in p["category"]]
        if not pois:
            return f"{destination} 没有分类为「{preference}」的景点"

    lines = [f"{destination} 景点列表（偏好：{preference or '全部'}）："]
    for i, p in enumerate(pois, 1):
        lines.append(f"  {i}. {p['name']} | {p['category']} | 建议{p['duration_h']}h | 评分{p['rating']}")
    return "\n".join(lines)


def get_travel_time(from_poi: str, to_poi: str, mode: str = "walking", city: str = "") -> int:
    """估算两个 POI 之间的交通时间（分钟）。

    优先使用高德路径规划 API。如果 API 不可用（无 Key、网络错误、空结果），
    自动降级到 hash 估算。

    Args:
        from_poi: 起点 POI 名称，如 "灵隐寺"
        to_poi: 终点 POI 名称，如 "西湖"
        mode: 交通方式 — "walking"（步行）、"taxi"（打车）、"transit"（公交）
        city: 可选城市名，用于更精确的地理编码，如 "北京"

    Returns:
        预计交通时间（分钟）
    """
    if settings.amap_api_key:
        try:
            result = _travel_time_amap(from_poi, to_poi, mode, city)
            if result is not None:
                return result
        except Exception:
            logger.warning("高德路径规划失败，降级到 mock", exc_info=True)

    return _travel_time_mock(from_poi, to_poi, mode)


# ── 高德路径规划 API ──

# 交通方式 → 高德 API 端点映射
_MODE_TO_AMAP_URL = {
    "walking": AMAP_WALKING_URL,
    "taxi": AMAP_DRIVING_URL,      # 打车走机动车道，等同于驾车
    "transit": AMAP_TRANSIT_URL,
}


def _travel_time_amap(from_poi: str, to_poi: str, mode: str, city: str) -> int | None:
    """调用高德路径规划 API。返回分钟数，失败返回 None。"""
    # 第一步：地理编码两个 POI
    origin = geocode_poi(from_poi, city)
    dest = geocode_poi(to_poi, city)

    # 高德坐标格式：lng,lat
    origin_str = f"{origin['lng']},{origin['lat']}"
    dest_str = f"{dest['lng']},{dest['lat']}"

    # 第二步：选择对应的高德 API 端点
    url = _MODE_TO_AMAP_URL.get(mode) or AMAP_WALKING_URL

    params = {
        "key": settings.amap_api_key,
        "origin": origin_str,
        "destination": dest_str,
    }
    # 公交 API 必须传 city 参数
    if mode == "transit":
        params["city"] = city or "北京"

    # 第三步：调用高德路径规划 API
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "1":
        return None

    # 第四步：提取耗时（秒 → 分钟，向上取整）
    duration_sec = _extract_duration(data, mode)
    if duration_sec is None:
        return None
    try:
        duration_sec = int(duration_sec)
    except (ValueError, TypeError):
        return None
    if duration_sec <= 0:
        return None

    return math.ceil(duration_sec / 60)


def _extract_duration(data: dict, mode: str) -> int | None:
    """从高德路径规划响应中提取耗时（秒）。"""
    route = data.get("route", {})

    if mode in ("walking", "taxi"):
        # 步行/驾车：route.paths[0].duration
        paths = route.get("paths")
        if paths and len(paths) > 0:
            return paths[0].get("duration")
    elif mode == "transit":
        # 公交：route.transits[0].duration
        transits = route.get("transits")
        if transits and len(transits) > 0:
            return transits[0].get("duration")

    return None


# ── Mock 降级兜底 ──

def _travel_time_mock(from_poi: str, to_poi: str, mode: str) -> int:
    """Hash 估算 + 已知 POI 配对查表。"""
    import hashlib

    # 先查已知配对
    base = _TRAVEL_TIMES.get(from_poi, {}).get(to_poi)
    if base is None:
        base = _TRAVEL_TIMES.get(to_poi, {}).get(from_poi)
    # 未知配对用 hash 估算
    if base is None:
        h = int(hashlib.md5(f"{from_poi}:{to_poi}".encode()).hexdigest()[:8], 16)
        base = 10 + (h % 40)

    # 按交通方式调整
    factors = {"walking": 1.0, "transit": 0.6, "taxi": 0.4}
    return max(5, int(base * factors.get(mode, 1.0)))
