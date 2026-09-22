"""路线优化工具 — 地理编码 + 路径计时 + 有条件的最近邻降级。

默认信任 fill 给出的顺序（LLM / 候选），只在顺序无效、同日跨城、
明显绕路或高德大面积失败时才退回最近邻。日程耗时优先采用高德；
高德失败时按攻略路段 → LLM 估计 → Haversine 采纳，不把三种来源取平均。

高德 Direction 只请求最终顺序的相邻路段（约 N-1 次/天）。排序和 +50% 基线
只用 Haversine，不再构建 N×(N-1) 高德矩阵。5 个点的全量矩阵曾是 20 次请求。
见 docs/retrospectives/development-notes.md §23、§28。知识地图 §11 里的有向
旅行时间矩阵是当时的做法，不能再用来决定顺序或计算降级基线。
"""
import json
import logging
import math

import requests

from app.agents.tools.geo import geocode_poi, _result_matches_city
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.cache_store import get_cache, set_cache
from app.services.geo_convert import haversine_m

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


# 同城一日点之间不应跳到外省同名路；跨城请写 POI 自己的 city
_CROSS_CITY_JUMP_M = 250_000

# fill 总耗时相对最近邻基线 ≥ +50%，且绝对多出 ≥ 30 分钟，才降级重排
_NN_RELATIVE_LIMIT = 1.5
_NN_ABSOLUTE_EXCESS_MIN = 30

# 高德路段未核验达到一半（含）时，认为大面积不可达
_AMAP_UNVERIFIED_LEG_RATIO = 0.5

# 估计值与采用值同时满足绝对差和相对差才提示，避免短途噪声
_DISCREPANCY_ABS_MIN = 15
_DISCREPANCY_REL = 0.40


def _geocode_with_fallback(
    name: str,
    preferred_city: str,
    nearby: tuple[float, float] | None = None,
    route_type: str = "city",
) -> dict:
    """POI 地理编码回退链：周边搜索 → 指定城市 → mock。

    指定了城市时绝不做全国搜索。高德 city 参数默认只是偏好，
    黄兴路步行街 会命中上海黄兴路，必须 citylimit + 城市校验。
    """
    nearby_ctx = nearby if route_type == "scenic" else None

    def _accept(result: dict | None) -> dict | None:
        if result is None:
            return None
        if not _result_matches_city(result, preferred_city):
            return None
        if (
            nearby
            and route_type == "city"
            and haversine_m(nearby[0], nearby[1], result["lat"], result["lng"])
            > _CROSS_CITY_JUMP_M
        ):
            return None
        return result

    if nearby_ctx:
        accepted = _accept(
            geocode_poi(name, city=preferred_city, mock_fallback=False, nearby=nearby_ctx)
        )
        if accepted is not None:
            return accepted

    if preferred_city:
        accepted = _accept(
            geocode_poi(name, city=preferred_city, mock_fallback=False, nearby=nearby_ctx)
        )
        if accepted is not None:
            return accepted
        return geocode_poi(name, city=preferred_city)

    accepted = _accept(geocode_poi(name, city="", mock_fallback=False))
    if accepted is not None:
        return accepted
    return geocode_poi(name, city=preferred_city)

def optimize_itinerary(
    itinerary_json: str,
    reorder: bool | None = None,
    respect_fill_order: bool = True,
) -> str:
    """地理编码并填充路段时间。默认保留 fill 顺序，必要时降级最近邻。

    流程：
    1. 地理编码所有 POI → 填 lat/lng
    2. respect_fill_order=True（默认）时按当前顺序计时，不做最近邻重排
    3. 顺序无效、同日跨城跳跃、总耗时明显差于最近邻，或高德路段大面积失败时，
       整日降级为最近邻，并标记 order_source=nearest_neighbor
    4. reorder=False 时锁定调用方顺序（不因绕路降级）
    5. respect_fill_order=False 或 reorder=True 时直接最近邻
    6. 日程分钟优先高德；失败则攻略路段 → LLM 估计 → Haversine
    7. 相邻日首尾过远只写 day_boundary_warning，不把景点挪到另一天

    Args:
        itinerary_json: JSON 字符串，结构为
            {"days": [{"day_index": 1, "theme": "...", "items": [
                {"seq": 1, "poi_name": "...", "duration_h": 0.0, "travel_minutes_from_prev": 0}
            ]}]}
        reorder: False 锁定顺序；True 强制最近邻；省略时由 respect_fill_order 决定。
        respect_fill_order: 生产路径默认 True。False 表示显式重排（如 reoptimize）。

    Returns:
        JSON 字符串。每个 item 含 lat/lng、采用的 travel_minutes_from_prev，
        以及 travel_amap_minutes / travel_estimate_* / travel_discrepancy。
        每天有 order_source=fill|nearest_neighbor。
    """
    itinerary = json.loads(itinerary_json)
    # 行程级城市作为全局兜底；单个 POI 可用自己的 city 覆盖
    fallback_city = itinerary.get("city", "")
    amap_available = bool(settings.amap_api_key)
    policy = _resolve_order_policy(reorder, respect_fill_order)

    for day in itinerary.get("days", []):
        items = day.get("items", [])
        if not items:
            continue

        route_type = _infer_route_type_from_items(day)
        day["route_type"] = route_type

        invalid_order = False
        if policy == "respect":
            invalid_order = _normalize_fill_order(items) == "invalid"

        if any(not str(item.get("poi_name") or "").strip() for item in items):
            day["order_source"] = "nearest_neighbor"
            day["order_degrade_reason"] = "invalid_order"
            continue

        # 第一步：地理编码所有 POI（优先使用 POI 级城市，并带上上一节点作为周边参考）
        prev_center: tuple[float, float] | None = None
        for item in items:
            item_city = item.get("city") or fallback_city
            result = _geocode_with_fallback(
                item["poi_name"], item_city, nearby=prev_center, route_type=route_type
            )
            item["lat"] = result["lat"]
            item["lng"] = result["lng"]
            item["city"] = result.get("city", "")
            item["amap_poi_id"] = result.get("amap_poi_id")
            item["poi_address"] = result.get("poi_address")
            item["poi_type"] = result.get("poi_type")
            prev_center = (item["lat"], item["lng"])

        order_source, degrade_reason = _apply_order_and_timing(
            items,
            route_type=route_type,
            policy=policy,
            amap_available=amap_available,
            invalid_order=invalid_order,
        )
        day["order_source"] = order_source
        if degrade_reason:
            day["order_degrade_reason"] = degrade_reason
        else:
            day.pop("order_degrade_reason", None)

        for i, item in enumerate(items):
            item["seq"] = i + 1

        for item in items:
            item.pop("city", None)
            item.pop("_amap_minutes", None)
            item.pop("_est_minutes", None)
            item.pop("_est_source", None)

    _annotate_cross_day_boundaries(itinerary.get("days") or [])
    return json.dumps(itinerary, ensure_ascii=False)


def _resolve_order_policy(reorder: bool | None, respect_fill_order: bool) -> str:
    """lock = 永不重排；nn = 直接最近邻；respect = 保留 fill，除非 sanity 失败。"""
    if reorder is False:
        return "lock"
    if reorder is True or not respect_fill_order:
        return "nn"
    return "respect"


def _positive_minutes(raw) -> int | None:
    if raw is None or raw is False or raw == "":
        return None
    try:
        minutes = int(float(raw))
    except (TypeError, ValueError):
        return None
    if minutes <= 0:
        return None
    return minutes


def _normalize_fill_order(items: list[dict]) -> str | None:
    """唯一 seq 时按 seq 排成 fill 顺序。重复且不一致的 seq 视为无效顺序。"""
    if not all(isinstance(item, dict) for item in items):
        return "invalid"
    parsed: list[int | None] = []
    for item in items:
        if item.get("seq") is None:
            return None
        try:
            parsed.append(int(item["seq"]))
        except (TypeError, ValueError):
            return "invalid"
    seqs = [seq for seq in parsed if seq is not None]
    if len(set(seqs)) == len(seqs):
        order = sorted(range(len(items)), key=lambda index: seqs[index])
        if order != list(range(len(items))):
            ranked = [items[index] for index in order]
            items.clear()
            items.extend(ranked)
        return None
    if len(set(seqs)) == 1:
        return None
    return "invalid"


def _read_fill_estimate(item: dict) -> tuple[int | None, str | None]:
    """读取 fill 留下的路段估计。没有 source 的正数分钟视为 LLM 估计。"""
    source = item.get("travel_estimate_source")
    raw = item.get("travel_estimate_minutes")
    if raw is None:
        raw = item.get("travel_minutes_from_prev")
    minutes = _positive_minutes(raw)
    if minutes is None:
        return None, None
    if source in {"guide", "llm"}:
        return minutes, source
    return minutes, "llm"


def _stash_fill_estimates(items: list[dict]) -> None:
    for index, item in enumerate(items):
        item.pop("_est_minutes", None)
        item.pop("_est_source", None)
        if index == 0:
            continue
        minutes, source = _read_fill_estimate(item)
        if minutes is None:
            continue
        item["_est_minutes"] = minutes
        item["_est_source"] = source


def _has_cross_city_jump(items: list[dict]) -> bool:
    for prev, curr in zip(items, items[1:]):
        if prev.get("lat") is None or curr.get("lat") is None:
            continue
        dist_m = _haversine_distance(prev["lat"], prev["lng"], curr["lat"], curr["lng"])
        if dist_m > _CROSS_CITY_JUMP_M:
            return True
    return False


def _path_minutes(matrix: dict, order: list[int]) -> int:
    total = 0
    for origin, dest in zip(order, order[1:]):
        total += _matrix_minutes(matrix, (origin, dest))
    return total


def _fill_much_worse_than_nn(items: list[dict]) -> bool:
    """用 Haversine 估计比较 fill 顺序和最近邻。这里不调用高德。"""
    count = len(items)
    if count <= 2:
        return False
    if any(item.get("lat") is None or item.get("lng") is None for item in items):
        return False
    matrix = _build_haversine_matrix(items)
    fill_total = _path_minutes(matrix, list(range(count)))
    nn_total = _path_minutes(matrix, _nearest_neighbor_order(count, matrix))
    if nn_total <= 0:
        return False
    excess = fill_total - nn_total
    return fill_total >= nn_total * _NN_RELATIVE_LIMIT and excess >= _NN_ABSOLUTE_EXCESS_MIN


def _reorder_nn(items: list[dict]) -> None:
    if len(items) <= 2:
        return
    if any(item.get("lat") is None or item.get("lng") is None for item in items):
        return
    _reorder_by_nearest_neighbor(items, _build_haversine_matrix(items))


def _time_current_order(items: list[dict], route_type: str, amap_available: bool) -> None:
    """按当前顺序只请求相邻段。调用前必须已经决定好顺序。"""
    for item in items:
        item.pop("_amap_minutes", None)
    matrix = None
    if amap_available and len(items) > 1:
        try:
            matrix = _build_sequence_travel_matrix(items, route_type=route_type)
        except Exception:
            logger.warning("相邻路段矩阵构建异常，降级到坐标估算", exc_info=True)
            matrix = None
    if matrix is not None:
        _fill_travel_times_from_matrix(
            items, matrix, list(range(len(items))), route_type=route_type
        )
    else:
        _fill_travel_times_fallback(items, route_type=route_type)


def _amap_widespread_failure(items: list[dict], amap_available: bool) -> bool:
    if not amap_available:
        return False
    legs = items[1:]
    if not legs:
        return False
    unverified = sum(1 for item in legs if _positive_minutes(item.get("_amap_minutes")) is None)
    return unverified / len(legs) >= _AMAP_UNVERIFIED_LEG_RATIO


def _discrepancy_message(estimate: int | None, adopted: int) -> str | None:
    if estimate is None or adopted <= 0:
        return None
    diff = abs(estimate - adopted)
    if diff >= _DISCREPANCY_ABS_MIN and diff / adopted >= _DISCREPANCY_REL:
        return f"路段估计 {estimate} 分钟，日程采用 {adopted} 分钟"
    return None


def _commit_adopted_times(items: list[dict]) -> None:
    """高德成功用高德；否则 guide → llm → 已写入的 Haversine。不取平均。"""
    for index, item in enumerate(items):
        estimate = item.pop("_est_minutes", None)
        source = item.pop("_est_source", None)
        amap_minutes = _positive_minutes(item.pop("_amap_minutes", None))
        if index == 0:
            item["travel_minutes_from_prev"] = 0
            item["travel_minutes"] = 0
            item["travel_amap_minutes"] = None
            item["travel_estimate_minutes"] = None
            item["travel_estimate_source"] = None
            item["travel_discrepancy"] = None
            continue

        if amap_minutes is not None:
            adopted = amap_minutes
        elif source == "guide" and estimate is not None:
            adopted = estimate
        elif source == "llm" and estimate is not None:
            adopted = estimate
        else:
            adopted = _positive_minutes(item.get("travel_minutes_from_prev")) or 0

        item["travel_amap_minutes"] = amap_minutes
        item["travel_estimate_minutes"] = estimate
        item["travel_estimate_source"] = source if estimate is not None else None
        item["travel_minutes_from_prev"] = adopted
        item["travel_minutes"] = adopted
        message = _discrepancy_message(estimate, adopted)
        item["travel_discrepancy"] = message
        if message:
            advice = (item.get("travel_advice") or "").strip()
            if message not in advice:
                item["travel_advice"] = f"{advice} {message}".strip()


def _apply_order_and_timing(
    items: list[dict],
    *,
    route_type: str,
    policy: str,
    amap_available: bool,
    invalid_order: bool,
) -> tuple[str, str | None]:
    _stash_fill_estimates(items)
    order_source = "fill"
    reason: str | None = None

    if policy == "nn":
        _reorder_nn(items)
        order_source = "nearest_neighbor"
        reason = "explicit_reorder"
    elif policy == "respect":
        if invalid_order:
            _reorder_nn(items)
            order_source = "nearest_neighbor"
            reason = "invalid_order"
        elif _has_cross_city_jump(items):
            _reorder_nn(items)
            order_source = "nearest_neighbor"
            reason = "cross_city_jump"
        elif _fill_much_worse_than_nn(items):
            _reorder_nn(items)
            order_source = "nearest_neighbor"
            reason = "travel_time"

    _time_current_order(items, route_type, amap_available)
    if policy == "respect" and order_source == "fill" and _amap_widespread_failure(items, amap_available):
        logger.info("高德路段大面积未核验，降级最近邻")
        _reorder_nn(items)
        _time_current_order(items, route_type, amap_available)
        order_source = "nearest_neighbor"
        reason = "amap_unverified"

    if reason:
        logger.info("当日顺序来源=%s，原因=%s", order_source, reason)
    _commit_adopted_times(items)
    return order_source, reason


def _annotate_cross_day_boundaries(days: list) -> None:
    """相邻日终点和次日起点过远时只告警，不自动换天。"""
    usable: list[tuple[dict, list[dict]]] = []
    for day in days:
        if not isinstance(day, dict):
            continue
        located = [
            item
            for item in day.get("items") or []
            if isinstance(item, dict) and item.get("lat") is not None and item.get("lng") is not None
        ]
        usable.append((day, located))
    ordered = sorted(usable, key=lambda pair: int(pair[0].get("day_index") or 0))
    for (prev_day, prev_items), (next_day, next_items) in zip(ordered, ordered[1:]):
        if not prev_items or not next_items:
            continue
        end = prev_items[-1]
        start = next_items[0]
        dist_m = _haversine_distance(end["lat"], end["lng"], start["lat"], start["lng"])
        if dist_m <= _CROSS_CITY_JUMP_M:
            continue
        km = max(1, round(dist_m / 1000))
        warning = (
            f"第{prev_day.get('day_index')}天终点「{end.get('poi_name')}」与"
            f"第{next_day.get('day_index')}天起点「{start.get('poi_name')}」相距约 {km} 公里，"
            "跨天衔接偏远。本次不会自动把景点改到另一天。"
        )
        next_day["day_boundary_warning"] = warning
        advice = (start.get("travel_advice") or "").strip()
        if warning not in advice:
            start["travel_advice"] = f"{advice} {warning}".strip()


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


def _is_scenic_poi(item: dict) -> bool:
    """判断单个 POI 是否属于景区/山岳类，用于按路段而不是按天选择模式。"""
    text = f"{item.get('poi_name', '')} {item.get('poi_type', '')}"
    return any(
        token in text
        for token in ("景区", "风景名胜", "索道", "缆车", "登山步道", "游步道", "国家级景点", "山")
    )


def _infer_leg_route_type(from_item: dict, to_item: dict, day_route_type: str) -> str:
    """按路段推断 route_type。

    - 两端都在景区内 → 景区内部路段，用步行/驾车/索道。
    - 一端在景区、另一端不在 → 进出景区的接驳/转移路段，按城市模式处理。
    - 两端都不在景区 → 沿用当天默认。
    """
    from_scenic = _is_scenic_poi(from_item)
    to_scenic = _is_scenic_poi(to_item)
    if from_scenic and to_scenic:
        return "scenic"
    if from_scenic != to_scenic:
        return "city"
    return day_route_type if day_route_type == "scenic" else "city"


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

_DIRECTION_CACHE: dict[tuple, dict] = {}


def _amap_direction_direct(
    origin_lng: float, origin_lat: float,
    dest_lng: float, dest_lat: float,
    mode: str, city: str = "",
) -> dict | None:
    """Cached Amap direction lookup (memory + Postgres)."""
    cache_key = (mode, origin_lng, origin_lat, dest_lng, dest_lat, city)
    if cache_key in _DIRECTION_CACHE:
        return _DIRECTION_CACHE[cache_key]

    db_cache_key = f"{mode}|{origin_lng}|{origin_lat}|{dest_lng}|{dest_lat}|{city}"
    db = SessionLocal()
    try:
        persisted = get_cache(db, "direction", db_cache_key)
        if persisted is not None:
            _DIRECTION_CACHE[cache_key] = persisted
            return persisted
    except Exception:
        pass
    finally:
        db.close()

    result = _amap_direction_direct_uncached(
        origin_lng, origin_lat, dest_lng, dest_lat, mode=mode, city=city
    )
    if result is not None:
        _DIRECTION_CACHE[cache_key] = result
        db = SessionLocal()
        try:
            set_cache(db, "direction", db_cache_key, result)
        except Exception:
            pass
        finally:
            db.close()
    return result


def _amap_direction_direct_uncached(
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

def _build_haversine_matrix(items: list[dict]) -> dict:
    """仅用坐标距离估算时间的矩阵，用于快速贪心排序，不调高德。"""
    n = len(items)
    matrix = {}
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            dist = _haversine_distance(
                items[i]["lat"], items[i]["lng"],
                items[j]["lat"], items[j]["lng"],
            )
            matrix[(i, j)] = _estimate_travel_minutes_from_distance(dist)
    return matrix


def _build_sequence_travel_matrix(
    items: list[dict], route_type: str = "city"
) -> dict | None:
    """只为当前顺序的相邻路段请求高德，约 N-1 次。

    不构建全量 N×(N-1) Direction 矩阵。全量矩阵会按 5 个点 20 次请求烧掉配额和时间，
    见 docs/retrospectives/development-notes.md §23、§28。
    """
    n = len(items)
    if n <= 1:
        return {}

    matrix = {}
    for i in range(1, n):
        dist = _haversine_distance(
            items[i - 1]["lat"], items[i - 1]["lng"],
            items[i]["lat"], items[i]["lng"],
        )
        leg_route_type = _infer_leg_route_type(items[i - 1], items[i], route_type)
        mode = _select_mode(dist, route_type=leg_route_type)
        city = items[i].get("city", "")
        route_info = _amap_direction_direct(
            items[i - 1]["lng"], items[i - 1]["lat"],
            items[i]["lng"], items[i]["lat"],
            mode=mode, city=city,
        )
        if route_info is None:
            logger.warning(
                "Direction API 失败(相邻): %s → %s，跳过该段，保留其他真实路段",
                items[i - 1]["poi_name"], items[i]["poi_name"],
            )
            continue
        matrix[(i - 1, i)] = route_info
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


def _nearest_neighbor_order(count: int, matrix: dict) -> list[int]:
    """贪心最近邻。index 0 固定为起点，只重排其余点。"""
    if count <= 2:
        return list(range(count))

    ordered = [0]
    remaining = set(range(1, count))
    current = 0
    while remaining:
        nearest = min(remaining, key=lambda j: _matrix_minutes(matrix, (current, j)))
        ordered.append(nearest)
        remaining.discard(nearest)
        current = nearest
    return ordered


def _reorder_by_nearest_neighbor(items: list[dict], matrix: dict) -> list[int]:
    """贪心最近邻重排 POI。

    items[0] 固定为起点（Agent 选择），只重排 items[1:]。

    Returns:
        index_map: new_pos → original_index 的映射列表
    """
    ordered = _nearest_neighbor_order(len(items), matrix)
    reordered = [items[i] for i in ordered]
    items.clear()
    items.extend(reordered)
    return ordered


# ── 交通时间填充 ──

def _fill_travel_times_from_matrix(
    items: list[dict], matrix: dict, index_map: list[int], route_type: str = "city"
):
    """用真实矩阵数据回填交通时间；缺失路段回退为估算。

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
        route_info = matrix.get((orig_from, orig_to))

        if route_info is None:
            # 该段没有真实路线，按当前模式估算并保留示意
            prev = items[i - 1]
            curr = items[i]
            dist_m = _haversine_distance(prev["lat"], prev["lng"], curr["lat"], curr["lng"])
            scenic_leg = _infer_leg_route_type(prev, curr, route_type) == "scenic"
            if scenic_leg:
                explicit = curr.get("transport_mode") or curr.get("suggested_transport")
                api_mode = _select_mode(dist_m, route_type="scenic")
                mode = _infer_scenic_transport(
                    prev.get("poi_name", ""), curr.get("poi_name", ""), api_mode, explicit
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
            continue

        if isinstance(route_info, dict):
            items[i]["travel_minutes_from_prev"] = route_info.get("minutes", 0)
            items[i]["_amap_minutes"] = route_info.get("minutes")
            api_mode = route_info.get("mode") or "walking"
            api_path = route_info.get("path") or None

            if _infer_leg_route_type(items[i - 1], items[i], route_type) == "scenic":
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
            items[i]["_amap_minutes"] = route_info
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

        if _infer_leg_route_type(prev, curr, route_type) == "scenic":
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
