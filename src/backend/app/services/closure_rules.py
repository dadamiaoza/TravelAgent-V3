"""闭馆规则引擎 — 第 1 层：确定性规则。

原则：系统输出“风险提示 + 来源 + 建议出行前再确认”，
不追求 100% 准确，也不做绝对保证。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

_RULES_PATH = Path(__file__).with_name("closure_rules.json")


def _coerce_date(value: str | date) -> date:
    """把字符串日期统一成 date 对象。"""
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _matches_poi(rule: dict[str, Any], poi_name: str) -> bool:
    """原型阶段只支持 contains 包含匹配。"""
    pattern = rule.get("poi_pattern", "")
    match_mode = rule.get("match_mode", "contains")
    if match_mode == "contains":
        return pattern in poi_name
    return False


def _in_date_range(rule: dict[str, Any], target: date) -> bool:
    start = _coerce_date(rule["date_range"][0])
    end = _coerce_date(rule["date_range"][1])
    return start <= target <= end


def _rule_applies(rule: dict[str, Any], poi_name: str, target: date) -> bool:
    """判断某条规则是否作用于当前 POI + 日期。"""
    if not _matches_poi(rule, poi_name):
        return False

    rule_type = rule.get("rule_type")
    if rule_type == "weekly_closure":
        return target.weekday() in rule.get("closed_weekdays", [])
    if rule_type in ("holiday_override", "holiday_closure"):
        return _in_date_range(rule, target)
    return False


def load_closure_rules(path: Path | None = None) -> list[dict[str, Any]]:
    """加载 JSON 规则配置，返回规则列表。"""
    rules_path = path or _RULES_PATH
    with rules_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rules", [])


def evaluate_closure_rule(
    poi_name: str,
    target_date: str | date,
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """判断 POI 在指定日期是否命中闭馆/节假日规则。

    返回结构同时包含“命中规则”和“是否闭馆”，方便上层统一汇总。
    """
    target = _coerce_date(target_date)
    rule_list = rules if rules is not None else load_closure_rules()

    applicable = [
        rule for rule in rule_list
        if _rule_applies(rule, poi_name, target)
    ]

    if not applicable:
        return {
            "matched": False,
            "closed": False,
            "risk": "low",
            "reason": "未命中闭馆规则",
            "rule_id": None,
            "rule_type": None,
            "source": "",
            "effect": None,
        }

    # priority 越大越优先；节假日覆盖规则优先于周闭馆规则
    applicable.sort(key=lambda rule: rule.get("priority", 0), reverse=True)
    top = applicable[0]
    effect = top.get("effect", "closed")

    if effect == "open":
        risk = "low"
        reason = top.get("notes", "节假日正常开放")
        closed = False
    elif effect == "adjusted":
        risk = "medium"
        reason = top.get("notes", "节假日可能调整开放时间")
        closed = False
    else:
        risk = "high"
        reason = top.get("notes", "闭馆/闭园")
        closed = True

    return {
        "matched": True,
        "closed": closed,
        "risk": risk,
        "reason": reason,
        "rule_id": top.get("id"),
        "rule_type": top.get("rule_type"),
        "source": top.get("source", ""),
        "effect": effect,
    }


def is_closed_by_rule(
    poi_name: str,
    target_date: str | date,
    rules: list[dict[str, Any]] | None = None,
) -> bool:
    """便捷判断：是否命中明确闭馆规则。"""
    result = evaluate_closure_rule(poi_name, target_date, rules)
    return bool(result.get("matched") and result.get("closed"))
