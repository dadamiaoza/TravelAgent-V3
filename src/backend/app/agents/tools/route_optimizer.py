"""路线优化工具 — 地理编码 + 路径规划 + POI 重排序。

Step 7.6 升级：从"只填坐标"升级为"真实路径排序"。
- 高德 Direction API 构建旅行时间矩阵
  - 城市模式：按距离自动选 walking/transit
  - 景区模式：只使用 walking/driving，不虚构索道/接驳车路线
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
_AMAP_DRIVING_URL = "https://restapi.amap.com/v3/direction/driving"

# 步行/公交分界阈值（米）：< 1500m 步行，≥ 1500m 公交（城市模式）
_WALK_DISTANCE_THRESHOLD = 1500

# 景区模式内部：只使用步行/驾车连接可定位 POI；索道、接驳车等没有高德路线 API
_SCENIC_DRIVING_DISTANCE_THRESHOLD = 3000

# 景区内部无法核实的交通方式及其建议
_SCENIC_UNVERIFIED_MODES = {"hiking", "shuttle", "cable_car"}


# ── 公共接口 ──


def _geocode_with_fallback(
    name: str,
    preferred_city: str,
    nearby: tuple[float, float] | None = None,
) -> dict:
    """POI 地理编码回退链：周边搜索 → 指定城市 → 无城市 → mock。"""
    # 1. 有上一节点坐标时，优先周边搜索，解决景区内同名地点错配
    if nearby:
        result = geocode_poi(name, city=preferred_city, mock_fallback=False, nearby=nearby)
        if result is not None:
            return result

    # 2. 再按 POI 自己的城市/行程城市搜索，消除同名歧义
    if preferred_city:
        result = geocode_poi(name, city=preferred_city, mock_fallback=False, nearby=nearby)
        if result is not None:
            return result

    # 3. 找不到时放开城市限制，兼容跨城景点
    result = geocode_poi(name, city="", mock_fallback=False)
    if result is not None:
        return result

    # 4. 仍找不到才使用 mock 兜底，保证行程始终有可展示坐标
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

        route_type = _infer_route_type_from_items(day)
        day["route_type"] = route_type

        # 第一步：地理编码所有 POI（优先使用 POI 级城市，并带上上一节点作为周边参考）
        prev_center: tuple[float, float] | None = None
        for item in items:
            item_city = item.get("city") or fallback_city
            result = _geocode_with_fallback(item["poi_name"], item_city, nearby=prev_center)
            item["lat"] = result["lat"]
            item["lng"] = result["lng"]
            item["city"] = result.get("city", "")
            item["amap_poi_id"] = result.get("amap_poi_id")
            item["poi_address"] = result.get("poi_address")
            item["poi_type"] = result.get("poi_type")
            prev_center = (item["lat"], item["lng"])

        # 第二步：尝试构建真实旅行时间矩阵
        matrix = None
        if amap_available:
            try:
                matrix = _build_travel_time_matrix(items, route_type=route_type)
            except Exception:
                logger.warning("构建旅行时间矩阵异常，降级到坐标估算", exc_info=True)

        # 第三步：排序 + 填充交通时间
        if matrix is not None:
            index_map = _reorder_by_nearest_neighbor(items, matrix)
            _fill_travel_times_from_matrix(items, matrix, index_map, route_type=route_type)
        else:
            _fill_travel_times_fallback(items, route_type=route_type)

        # 第四步：更新 seq 序号
        for i, item in enumerate(items):
            item["seq"] = i + 1

        # 第五步：移除内部字段，不暴露给下游
        for item in items:
            item.pop("city", None)

    return json.dumps(itinerary, ensure_ascii=False)


# ── 交通方式选择 ──

def _select_mode(distance_m: float, route_type: str = "city") -> str:
    """根据距离选择交通方式。

    城市模式：短距离步行，长距离公交。
    景区模式：不使用公交/地铁，只使用步行或驾车连接可定位 POI；
    索道/接驳车等不作为高德路线能力调用，由业务层另行标注。
    """
    if route_type == "scenic":
        return "walking" if distance_m < _SCENIC_DRIVING_DISTANCE_THRESHOLD else "driving"
    return "walking" if distance_m < _WALK_DISTANCE_THRESHOLD else "transit"


def _normalize_route_type(value: str | None) -> str:
    """把路线类型收敛为 city/scenic。"""
    return "scenic" if (value or "").lower() == "scenic" else "city"


def _infer_route_type_from_items(day: dict) -> str:
    """没有显式 route_type 时，根据 POI 名称里的景区内部交通线索推断。"""
    if day.get("route_type"):
        return _normalize_route_type(day["route_type"])
    names = " ".join(str(item.get("poi_name", "")) for item in day.get("items", []))
    scenic_hints = ("索道", "缆车", "接驳", "观光车", "登山步道", "游步道", "景区")
    if any(hint in names for hint in scenic_hints):
        return "scenic"
    return "city"


def _infer_scenic_transport(prev_name: str, curr_name: str, api_mode: str, explicit: str | None = None) -> str:
    """推断景区内一段交通的业务层标注。

    优先级：
    1. 用户/LLM 显式给出的交通方式
    2. 根据前后节点名称中的索道/接驳车线索
    3. 步行/驾车（高德可核实）
    """
    if explicit in {"walking", "hiking", "shuttle", "cable_car", "driving"}:
        return explicit

    prev_cable = any(token in prev_name for token in ("索道", "缆车", "观光缆车"))
    curr_cable = any(token in curr_name for token in ("索道", "缆车", "观光缆车"))
    prev_shuttle = any(token in prev_name for token in ("接驳", "摆渡", "观光车", "景区公交"))
    curr_shuttle = any(token in curr_name for token in ("接驳", "摆渡", "观光车", "景区公交"))

    # 从索道站/接驳站出发前往下一站，才标记为索道/接驳车；
    # 前往车站本身应步行/驾车到站，不能虚构为索道/接驳车路线。
    if prev_cable and not curr_cable:
        return "cable_car"
    if prev_shuttle and not curr_shuttle:
        return "shuttle"

    names = f"{prev_name} {curr_name}"
    if any(token in names for token in ("徒步", "登山步道", "游步道", "栈道")):
        return "hiking"
    return api_mode or "walking"


def _scenic_travel_advice(mode: str, verified: bool = False) -> str | None:
    """无法核实的景区交通方式返回给游客的建议。"""
    if verified:
        return None
    if mode == "cable_car":
        return "索道路段为参考建议：具体运行时间、票价和班次以景区当日现场公示为准。"
    if mode == "shuttle":
        return "景区接驳车为参考建议：具体停靠站、发车间隔和运营时间以景区官方班次为准。"
    if mode == "hiking":
        return "登山步道为参考建议：实际路线、开放情况和安全提示以景区现场指引为准。"
    return "该段为参考路线：具体步行/乘车路线和开放情况以景区现场指引为准。"


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
) -> dict | None:
    """用坐标直调高德 Direction API，返回分钟数、交通方式和道路坐标。

    返回结构：{"minutes": int, "mode": str, "path": [[lng, lat], ...]}
    失败返回 None。
    """
    if not settings.amap_api_key:
        return None

    # transit 必须传 city
    if mode == "transit" and not city:
        return None

    if mode == "walking":
        url = _AMAP_WALKING_URL
    elif mode == "driving":
        url = _AMAP_DRIVING_URL
    else:
        url = _AMAP_TRANSIT_URL
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

    return {
        "minutes": math.ceil(duration_sec / 60),
        "mode": mode,
        "path": _extract_route_path_direct(data, mode),
    }


def _extract_duration_direct(data: dict, mode: str) -> int | None:
    """从高德 Direction API 响应中提取 duration（秒）。"""
    route = data.get("route", {})

    if mode in ("walking", "driving"):
        paths = route.get("paths")
        if paths and len(paths) > 0:
            return paths[0].get("duration")
    elif mode == "transit":
        transits = route.get("transits")
        if transits and len(transits) > 0:
            return transits[0].get("duration")

    return None


def _append_polyline_points(coords: list[list[float]], polyline: str | None) -> None:
    """把高德返回的 "lng,lat;lng,lat" 字符串追加到坐标列表。"""
    if not polyline:
        return
    for point in polyline.split(";"):
        if not point:
            continue
        try:
            lng_str, lat_str = point.split(",")
            coords.append([float(lng_str), float(lat_str)])
        except (ValueError, TypeError):
            continue


def _extract_route_path_direct(data: dict, mode: str) -> list[list[float]]:
    """从高德 Direction API 响应中尽力提取真实道路坐标。"""
    route = data.get("route", {})
    coords: list[list[float]] = []

    if mode in ("walking", "driving"):
        paths = route.get("paths") or []
        if paths:
            for step in (paths[0].get("steps") or []):
                _append_polyline_points(coords, step.get("polyline"))
        return coords

    if mode == "transit":
        transits = route.get("transits") or []
        if not transits:
            return coords
        for segment in (transits[0].get("segments") or []):
            # 步行段
            walking = segment.get("walking") or {}
            for step in (walking.get("steps") or []):
                _append_polyline_points(coords, step.get("polyline"))
            # 公交段
            bus = segment.get("bus") or {}
            for line in (bus.get("buslines") or []):
                _append_polyline_points(coords, line.get("polyline"))
        return coords

    return coords


# ── 旅行时间矩阵 ──

def _build_travel_time_matrix(items: list[dict], route_type: str = "city") -> dict | None:
    """构建 N×(N-1) 有向旅行时间矩阵。

    对每对 (i→j, i≠j)，先算 Haversine 距离决定交通方式，
    再调高德 Direction API 获取真实旅行时间。
    景区模式不会调用公交/地铁，只使用步行或驾车。

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
            mode = _select_mode(dist, route_type=route_type)
            city = items[j].get("city", "")

            route_info = _amap_direction_direct(
                items[i]["lng"], items[i]["lat"],
                items[j]["lng"], items[j]["lat"],
                mode=mode, city=city,
            )

            if route_info is None:
                logger.warning(
                    "Direction API 失败: %s → %s，该日降级到估算",
                    items[i]["poi_name"], items[j]["poi_name"],
                )
                return None

            # 兼容旧的 int 返回（测试 mock），真实返回是 {minutes,mode,path}
            matrix[(i, j)] = route_info

    return matrix


# ── 贪心最近邻排序 ──

def _matrix_minutes(matrix: dict, key: tuple[int, int]) -> int:
    """从矩阵中取分钟数，兼容 int 和 {minutes, mode, path} 两种形态。"""
    value = matrix.get(key)
    if isinstance(value, dict):
        return int(value.get("minutes", 10 ** 9))
    if value is None:
        return 10 ** 9
    return int(value)


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
        nearest = min(remaining, key=lambda j: _matrix_minutes(matrix, (current, j)))
        ordered.append(nearest)
        remaining.discard(nearest)
        current = nearest

    # 原地重建列表
    reordered = [items[i] for i in ordered]
    items.clear()
    items.extend(reordered)

    return ordered


# ── 交通时间填充 ──

def _fill_travel_times_from_matrix(
    items: list[dict], matrix: dict, index_map: list[int], route_type: str = "city"
):
    """用真实矩阵数据回填 travel_minutes、transport_mode 和 route_polyline。

    城市模式：直接采用高德返回的 mode 和真实道路。
    景区模式：只保留可核实的步行/驾车道路；索道/接驳车等作为业务层标注，
    不虚构高德路线，并给出“以现场/官方班次为准”的建议。
    """
    items[0]["travel_minutes_from_prev"] = 0
    items[0]["transport_mode"] = None
    items[0]["route_polyline"] = None
    items[0]["route_verified"] = False
    items[0]["travel_advice"] = None

    for i in range(1, len(items)):
        orig_from = index_map[i - 1]  # 前一个 POI 的原始索引
        orig_to = index_map[i]        # 当前 POI 的原始索引
        route_info = matrix.get((orig_from, orig_to), 0)

        # 兼容旧测试：直接传 int 时只填时间
        if isinstance(route_info, dict):
            items[i]["travel_minutes_from_prev"] = route_info.get("minutes", 0)
            api_mode = route_info.get("mode") or "walking"
            api_path = route_info.get("path") or None

            if route_type == "scenic":
                prev = items[i - 1]
                curr = items[i]
                explicit = curr.get("transport_mode") or curr.get("suggested_transport")
                mode = _infer_scenic_transport(
                    prev.get("poi_name", ""), curr.get("poi_name", ""), api_mode, explicit
                )
                items[i]["transport_mode"] = mode
                items[i]["route_verified"] = mode not in _SCENIC_UNVERIFIED_MODES and bool(api_path)
                items[i]["travel_advice"] = _scenic_travel_advice(mode, verified=items[i]["route_verified"])
                # 索道/接驳车/登山步道没有高德路线，不画成真实道路
                items[i]["route_polyline"] = None if mode in _SCENIC_UNVERIFIED_MODES else api_path
            else:
                items[i]["transport_mode"] = api_mode
                items[i]["route_polyline"] = api_path
                items[i]["route_verified"] = bool(api_path)
                items[i]["travel_advice"] = None
        else:
            items[i]["travel_minutes_from_prev"] = route_info
            items[i]["transport_mode"] = None
            items[i]["route_polyline"] = None
            items[i]["route_verified"] = False
            items[i]["travel_advice"] = None


# ── 降级路径 ──

def _estimate_travel_minutes_from_distance(distance_m: float, route_type: str = "city") -> int:
    """根据距离估算旅行时间（分钟）。"""
    mode = _select_mode(distance_m, route_type=route_type)
    if mode == "walking":
        speed_ms = 5 * 1000 / 3600
    elif mode == "driving":
        speed_ms = 30 * 1000 / 3600
    else:
        speed_ms = 20 * 1000 / 3600
    minutes = distance_m / 60 / speed_ms  # 等价于 distance_m / speed_ms / 60
    return max(1, math.ceil(minutes))


def _fill_travel_times_fallback(items: list[dict], route_type: str = "city"):
    """降级路径：保持原始顺序 + Haversine 距离估算填充，不提供真实路线。"""
    items[0]["travel_minutes_from_prev"] = 0
    items[0]["transport_mode"] = None
    items[0]["route_polyline"] = None
    items[0]["route_verified"] = False
    items[0]["travel_advice"] = None

    for i in range(1, len(items)):
        prev = items[i - 1]
        curr = items[i]
        dist_m = _haversine_distance(
            prev["lat"], prev["lng"],
            curr["lat"], curr["lng"],
        )

        if route_type == "scenic":
            # 景区内按业务层标注交通方式；高德不可核实，只给建议
            explicit = curr.get("transport_mode") or curr.get("suggested_transport")
            mode = _infer_scenic_transport(
                prev.get("poi_name", ""), curr.get("poi_name", ""),
                _select_mode(dist_m, route_type="scenic"), explicit,
            )
            items[i]["travel_minutes_from_prev"] = _estimate_travel_minutes_from_distance(
                dist_m, route_type="scenic"
            )
            items[i]["transport_mode"] = mode
            items[i]["route_polyline"] = None
            items[i]["route_verified"] = False
            items[i]["travel_advice"] = _scenic_travel_advice(mode, verified=False)
        else:
            items[i]["travel_minutes_from_prev"] = _estimate_travel_minutes_from_distance(
                dist_m, route_type="city"
            )
            items[i]["transport_mode"] = _select_mode(dist_m, route_type="city")
            items[i]["route_polyline"] = None
            items[i]["route_verified"] = False
            items[i]["travel_advice"] = None
