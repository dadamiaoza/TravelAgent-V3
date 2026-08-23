"""路线优化工具 — 地理编码 + 路径规划 + POI 重排序。

Step 7.6 升级：从"只填坐标"升级为"真实路径排序"。
- 高德 Direction API 构建旅行时间矩阵（按距离自动选 walking/transit）
- 贪心最近邻重排序（每日第一个 POI 固定）
- 回填真实 travel_minutes_from_prev
- API 不可用时降级到 Haversine 距离估算
"""
import json
import logging
import math

import requests

from app.agents.tools.geo import geocode_poi
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── 高德 Direction API 端点 ──

_AMAP_WALKING_URL = "https://restapi.amap.com/v3/direction/walking"
_AMAP_TRANSIT_URL = "https://restapi.amap.com/v3/direction/transit/integrated"

# 步行/公交分界阈值（米）：< 1500m 步行，≥ 1500m 公交
_WALK_DISTANCE_THRESHOLD = 1500


# ── 公共接口 ──


def _geocode_with_fallback(name: str, preferred_city: str) -> dict:
    """POI 地理编码回退链：优先指定城市 → 无城市搜索 → mock 兜底。"""
    # 1. 先按 POI 自己的城市/行程城市搜索，消除同名歧义
    if preferred_city:
        result = geocode_poi(name, city=preferred_city, mock_fallback=False)
        if result is not None:
            return result

    # 2. 找不到时放开城市限制，兼容跨城景点
    result = geocode_poi(name, city="", mock_fallback=False)
    if result is not None:
        return result

    # 3. 仍找不到才使用 mock 兜底，保证行程始终有可展示坐标
    return geocode_poi(name, city=preferred_city)


def optimize_itinerary(itinerary_json: str) -> str:
    """对行程中的 POI 进行地理编码、路径优化排序和交通时间填充。

    流程：
    1. 地理编码所有 POI → 填 lat/lng/city
    2. 尝试构建真实旅行时间矩阵（高德 Direction API）
       - 每对 POI 按 Haversine 距离自动选 walking 或 transit
       - 任一 API 调用失败 → 该日整体降级
    3. 贪心最近邻重排序（每日第一个 POI 固定为起点）
    4. 回填 travel_minutes_from_prev（真实或估算值）
    5. 更新 seq 序号、移除内部 city 字段

    Args:
        itinerary_json: JSON 字符串，结构为
            {"days": [{"day_index": 1, "theme": "...", "items": [
                {"seq": 1, "poi_name": "...", "duration_h": 0.0, "travel_minutes_from_prev": 0}
            ]}]}

    Returns:
        JSON 字符串，每个 item 新增 lat/lng，travel_minutes_from_prev 已更新，
        seq 已按优化后的顺序重新编号。
    """
    itinerary = json.loads(itinerary_json)
    # 行程级城市作为全局兜底；单个 POI 可用自己的 city 覆盖
    fallback_city = itinerary.get("city", "")
    amap_available = bool(settings.amap_api_key)

    for day in itinerary.get("days", []):
        items = day.get("items", [])
        if not items:
            continue

        # 第一步：地理编码所有 POI（优先使用 POI 级城市）
        for item in items:
            item_city = item.get("city") or fallback_city
            result = _geocode_with_fallback(item["poi_name"], item_city)
            item["lat"] = result["lat"]
            item["lng"] = result["lng"]
            item["city"] = result.get("city", "")

        # 第二步：尝试构建真实旅行时间矩阵
        matrix = None
        if amap_available:
            try:
                matrix = _build_travel_time_matrix(items)
            except Exception:
                logger.warning("构建旅行时间矩阵异常，降级到坐标估算", exc_info=True)

        # 第三步：排序 + 填充交通时间
        if matrix is not None:
            index_map = _reorder_by_nearest_neighbor(items, matrix)
            _fill_travel_times_from_matrix(items, matrix, index_map)
        else:
            _fill_travel_times_fallback(items)

        # 第四步：更新 seq 序号
        for i, item in enumerate(items):
            item["seq"] = i + 1

        # 第五步：移除内部字段，不暴露给下游
        for item in items:
            item.pop("city", None)

    return json.dumps(itinerary, ensure_ascii=False)


# ── 交通方式选择 ──

def _select_mode(distance_m: float) -> str:
    """根据距离选择交通方式。"""
    return "walking" if distance_m < _WALK_DISTANCE_THRESHOLD else "transit"


# ── Haversine 球面距离 ──

def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点间的球面距离（米）。"""
    R = 6371000  # 地球半径（米）

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ── 高德 Direction API（坐标直调） ──

def _amap_direction_direct(
    origin_lng: float, origin_lat: float,
    dest_lng: float, dest_lat: float,
    mode: str, city: str = "",
) -> int | None:
    """用坐标直调高德 Direction API，返回旅行分钟数。

    不做 geocode——调用方自行提供坐标。失败返回 None。
    """
    if not settings.amap_api_key:
        return None

    # transit 必须传 city
    if mode == "transit" and not city:
        return None

    url = _AMAP_WALKING_URL if mode == "walking" else _AMAP_TRANSIT_URL
    params = {
        "key": settings.amap_api_key,
        "origin": f"{origin_lng},{origin_lat}",
        "destination": f"{dest_lng},{dest_lat}",
    }
    if mode == "transit":
        params["city"] = city

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.warning("高德 Direction API 请求失败", exc_info=True)
        return None

    if data.get("status") != "1":
        return None

    duration_sec = _extract_duration_direct(data, mode)
    if duration_sec is None:
        return None

    try:
        duration_sec = int(duration_sec)
    except (ValueError, TypeError):
        return None

    if duration_sec <= 0:
        return None

    return math.ceil(duration_sec / 60)


def _extract_duration_direct(data: dict, mode: str) -> int | None:
    """从高德 Direction API 响应中提取 duration（秒）。"""
    route = data.get("route", {})

    if mode == "walking":
        paths = route.get("paths")
        if paths and len(paths) > 0:
            return paths[0].get("duration")
    elif mode == "transit":
        transits = route.get("transits")
        if transits and len(transits) > 0:
            return transits[0].get("duration")

    return None


# ── 旅行时间矩阵 ──

def _build_travel_time_matrix(items: list[dict]) -> dict | None:
    """构建 N×(N-1) 有向旅行时间矩阵。

    对每对 (i→j, i≠j)，先算 Haversine 距离决定交通方式，
    再调高德 Direction API 获取真实旅行时间。

    key 为 (from_index, to_index) 原始索引。

    任一 API 调用失败 → 返回 None（触发降级）。
    """
    n = len(items)
    if n <= 1:
        return {}

    matrix = {}

    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            dist = _haversine_distance(
                items[i]["lat"], items[i]["lng"],
                items[j]["lat"], items[j]["lng"],
            )
            mode = _select_mode(dist)
            city = items[j].get("city", "")

            minutes = _amap_direction_direct(
                items[i]["lng"], items[i]["lat"],
                items[j]["lng"], items[j]["lat"],
                mode=mode, city=city,
            )

            if minutes is None:
                logger.warning(
                    "Direction API 失败: %s → %s，该日降级到估算",
                    items[i]["poi_name"], items[j]["poi_name"],
                )
                return None

            matrix[(i, j)] = minutes

    return matrix


# ── 贪心最近邻排序 ──

def _reorder_by_nearest_neighbor(items: list[dict], matrix: dict) -> list[int]:
    """贪心最近邻重排 POI。

    items[0] 固定为起点（Agent 选择），只重排 items[1:]。

    Returns:
        index_map: new_pos → original_index 的映射列表
    """
    n = len(items)
    if n <= 2:
        return list(range(n))

    ordered = [0]          # 第一个 POI 固定
    remaining = set(range(1, n))
    current = 0

    while remaining:
        nearest = min(remaining, key=lambda j: matrix.get((current, j), 10 ** 9))
        ordered.append(nearest)
        remaining.discard(nearest)
        current = nearest

    # 原地重建列表
    reordered = [items[i] for i in ordered]
    items.clear()
    items.extend(reordered)

    return ordered


# ── 交通时间填充 ──

def _fill_travel_times_from_matrix(items: list[dict], matrix: dict, index_map: list[int]):
    """用真实矩阵数据回填 travel_minutes_from_prev。"""
    items[0]["travel_minutes_from_prev"] = 0

    for i in range(1, len(items)):
        orig_from = index_map[i - 1]  # 前一个 POI 的原始索引
        orig_to = index_map[i]        # 当前 POI 的原始索引
        items[i]["travel_minutes_from_prev"] = matrix.get((orig_from, orig_to), 0)


# ── 降级路径 ──

def _estimate_travel_minutes_from_distance(distance_m: float) -> int:
    """根据距离估算旅行时间（分钟）。"""
    mode = _select_mode(distance_m)
    speed_ms = (5 * 1000 / 3600) if mode == "walking" else (20 * 1000 / 3600)
    minutes = distance_m / 60 / speed_ms  # 等价于 distance_m / speed_ms / 60
    return max(1, math.ceil(minutes))


def _fill_travel_times_fallback(items: list[dict]):
    """降级路径：保持原始顺序 + Haversine 距离估算填充。"""
    items[0]["travel_minutes_from_prev"] = 0

    for i in range(1, len(items)):
        prev = items[i - 1]
        curr = items[i]
        dist_m = _haversine_distance(
            prev["lat"], prev["lng"],
            curr["lat"], curr["lng"],
        )
        items[i]["travel_minutes_from_prev"] = _estimate_travel_minutes_from_distance(dist_m)
