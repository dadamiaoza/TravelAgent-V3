"""闭馆规则引擎测试 — A-1 原型验证。"""
from app.services.closure_rules import (
    evaluate_closure_rule,
    is_closed_by_rule,
    load_closure_rules,
)


def test_load_example_rules():
    """示例 JSON 配置可以被正常加载。"""
    rules = load_closure_rules()
    assert len(rules) >= 3
    assert any(rule["id"] == "museum-monday-closed" for rule in rules)


def test_museum_monday_closed():
    """博物馆周一闭馆：应命中且判定为闭馆。"""
    result = evaluate_closure_rule("萍乡博物馆", "2026-08-24")  # 周一
    assert result["matched"] is True
    assert result["closed"] is True
    assert result["rule_id"] == "museum-monday-closed"
    assert result["risk"] == "high"


def test_museum_not_closed_on_tuesday():
    """博物馆周二正常：不应命中周闭馆规则。"""
    result = evaluate_closure_rule("萍乡博物馆", "2026-08-25")  # 周二
    assert result["matched"] is False
    assert result["closed"] is False


def test_museum_holiday_override_weekly_closure():
    """国庆假期覆盖周一闭馆：应命中但判定为不闭馆。"""
    result = evaluate_closure_rule("萍乡博物馆", "2026-10-05")  # 假期中的周一
    assert result["matched"] is True
    assert result["closed"] is False
    assert result["rule_id"] == "museum-national-holiday-open"
    assert result["risk"] == "low"


def test_scenic_holiday_adjusted():
    """景区节假日命中调整规则：未闭馆但风险为 medium。"""
    result = evaluate_closure_rule("萍乡某景区", "2026-10-05")
    assert result["matched"] is True
    assert result["closed"] is False
    assert result["effect"] == "adjusted"
    assert result["risk"] == "medium"


def test_is_closed_by_rule_helper():
    """便捷函数：周一博物馆返回 True，周二返回 False。"""
    assert is_closed_by_rule("萍乡博物馆", "2026-08-24") is True
    assert is_closed_by_rule("萍乡博物馆", "2026-08-25") is False
