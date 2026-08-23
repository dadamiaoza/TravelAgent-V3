"""景区开放时间查询工具。

优先使用高德 POI 搜索 API（extensions=all，提取 biz_ext 深度信息）。
API 不可用时降级到 mock 兜底。
"""
import logging

import requests

from app.agents.tools.geo import geocode_poi
from app.core.config import settings
from app.services.closure_rules import evaluate_closure_rule

logger = logging.getLogger(__name__)

AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"


def get_opening_hours(name: str, date: str) -> str:
    """查询景点的开放时间、门票和预约信息。

    优先使用高德 POI 搜索 API 的 biz_ext 深度信息。
    API 不可用时降级到 mock。

    Args:
        name: 景点中文名称，如 "故宫博物院"
        date: 日期 YYYY-MM-DD，如 "2026-06-01"

    Returns:
        开放时间、门票价格、预约状态等信息。
    """
    if settings.amap_api_key:
        try:
            result = _opening_hours_amap(name, date)
            if result:
                return _append_rule_hint(result, name, date)
        except Exception:
            logger.warning("高德 POI 详情查询失败，降级到 mock", exc_info=True)

    return _append_rule_hint(_opening_hours_mock(name, date), name, date)


def _append_rule_hint(base: str, name: str, date: str) -> str:
    """把 A-1 规则引擎的结果拼到开放时间结果后面。

    产品原则：只做风险提示，不承诺 100% 准确；建议出行前再确认。
    """
    rule = evaluate_closure_rule(name, date)

    if rule["matched"]:
        reason = rule.get("reason") or "命中时效规则"
        source = rule.get("source") or "内部规则"
        if rule.get("closed"):
            hint = f"时效提示：{reason}；来源：{source}；建议出行前再确认"
        elif rule.get("effect") == "adjusted":
            hint = f"时效提示：{reason}；来源：{source}；建议出行前再确认"
        else:
            # 节假日开放覆盖也提示一下，让用户知道已识别到特殊安排
            hint = f"时效提示：{reason}；来源：{source}；建议出行前再确认"
    else:
        hint = "时效提示：未命中固定闭馆规则；建议出行前以官方公告为准"

    return f"{base}；{hint}"



# ── 高德 POI 搜索 → biz_ext 深度信息 ──

def _opening_hours_amap(name: str, date: str) -> str | None:
    """通过高德 POI 搜索获取景点的开放时间和门票信息。返回格式化字符串，失败返回 None。"""
    # 第一步：地理编码获取城市，提高搜索精度
    geo = geocode_poi(name)
    city = _extract_city_from_geocode(geo)

    # 第二步：POI 关键字搜索 + 深度信息
    params = {
        "key": settings.amap_api_key,
        "keywords": name,
        "extensions": "all",
        "offset": 3,
    }
    if city:
        params["city"] = city

    resp = requests.get(AMAP_PLACE_TEXT_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "1":
        return None

    pois = data.get("pois", [])
    if not pois:
        return None

    # 第三步：取名称最匹配的 POI
    poi = _best_match_poi(name, pois)
    if poi is None:
        return None
    poi_name = poi.get("name", name)
    biz_ext = poi.get("biz_ext", {}) or {}

    # 第四步：提取关键信息
    opentime = biz_ext.get("opentime2", "")
    rating = biz_ext.get("rating", "")
    cost = biz_ext.get("cost", "")

    # 第五步：格式化输出
    return _format_opening_hours(poi_name, date, opentime, rating, cost)


def _best_match_poi(query_name: str, pois: list) -> dict | None:
    """从搜索结果中找与查询名称最匹配的 POI。匹配太差返回 None。"""
    if not pois:
        return None

    # 按名称相似度排序：完全匹配 > 包含关系 > 编辑距离
    best = pois[0]
    best_score = _name_match_score(query_name, best.get("name", ""))

    for p in pois[1:]:
        score = _name_match_score(query_name, p.get("name", ""))
        if score > best_score:
            best = p
            best_score = score

    # 阈值：至少要有包含关系（双向子串匹配），单字重叠不算
    if best_score < 2:
        return None

    return best


def _name_match_score(query: str, result: str) -> int:
    """简单名称匹配打分。2=包含关系，1=单字重叠，0=不匹配。"""
    # 去括号和空格后比较
    import re
    q_clean = re.sub(r"[（）()\s]", "", query)
    r_clean = re.sub(r"[（）()\s]", "", result)

    if q_clean == r_clean:
        return 2
    if q_clean in r_clean or r_clean in q_clean:
        return 2
    # 至少有一个字重叠
    if any(ch in r_clean for ch in q_clean):
        return 1
    return 0


def _extract_city_from_geocode(geo: dict) -> str:
    """从 geocode 返回中提取城市名（高德 API 可能返回 city 字段）。"""
    return geo.get("city", "")


def _format_opening_hours(name: str, date: str, opentime: str, rating: str, cost: str) -> str:
    parts = [f"{name}"]

    if opentime:
        parts.append(f"开放时间：{opentime}")
    else:
        parts.append("开放时间：暂无数据")

    if rating:
        parts.append(f"评分：{rating}")

    if cost:
        parts.append(f"门票：{cost}")

    parts.append(f"查询日期：{date}")

    return "；".join(parts)


# ── Mock 降级兜底 ──

def _opening_hours_mock(name: str, date: str) -> str:
    """Mock 兜底：返回通用开放时间。"""
    return f"{name}：{date} 开放时间 08:30-17:00（16:00 停止入园），门票 60 元，当日可预约"
