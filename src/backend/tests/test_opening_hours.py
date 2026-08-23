"""get_opening_hours 日期感知改造测试 — A-2。"""
from unittest.mock import patch

from app.agents.tools.opening_hours import get_opening_hours


def _mock_amap_base(name: str, date: str) -> str:
    return f"{name}；开放时间：09:00-17:00；查询日期：{date}"


def test_opening_hours_includes_monday_closure_hint():
    """周一博物馆应命中规则，并返回“建议出行前再确认”。"""
    with patch("app.agents.tools.opening_hours.settings") as mock_settings:
        mock_settings.amap_api_key = "fake-key"
        with patch(
            "app.agents.tools.opening_hours._opening_hours_amap",
            return_value=_mock_amap_base("萍乡博物馆", "2026-08-24"),
        ):
            result = get_opening_hours("萍乡博物馆", "2026-08-24")

    assert "时效提示" in result
    assert "周一闭馆" in result
    assert "建议出行前再确认" in result


def test_opening_hours_no_rule_hit_on_tuesday():
    """周二不命中周闭馆规则，返回“未命中固定闭馆规则”。"""
    with patch("app.agents.tools.opening_hours.settings") as mock_settings:
        mock_settings.amap_api_key = "fake-key"
        with patch(
            "app.agents.tools.opening_hours._opening_hours_amap",
            return_value=_mock_amap_base("萍乡博物馆", "2026-08-25"),
        ):
            result = get_opening_hours("萍乡博物馆", "2026-08-25")

    assert "未命中固定闭馆规则" in result
    assert "建议出行前以官方公告为准" in result


def test_opening_hours_holiday_adjusted_hint():
    """景区在节假日命中调整规则，也应输出时效提示。"""
    with patch("app.agents.tools.opening_hours.settings") as mock_settings:
        mock_settings.amap_api_key = "fake-key"
        with patch(
            "app.agents.tools.opening_hours._opening_hours_amap",
            return_value=_mock_amap_base("萍乡某景区", "2026-10-05"),
        ):
            result = get_opening_hours("萍乡某景区", "2026-10-05")

    assert "时效提示" in result
    assert "建议出行前再确认" in result
