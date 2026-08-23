"""Tests for route_optimizer Agent — Step 5 + Step 7.6 route optimization."""
import json
import re
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from app.agents.route_optimizer import create_route_optimizer
from app.agents.tools.route_optimizer import (optimize_itinerary,
    _geocode_with_fallback, _haversine_distance, _reorder_by_nearest_neighbor,
    _fill_travel_times_from_matrix, _fill_travel_times_fallback,
    _select_mode, _estimate_travel_minutes_from_distance)


# ── 纯 Tool 测试（不经过 Agent，直接测 Tool 函数）──

def test_optimize_itinerary_tool():
    """Tool function: geocode POIs and fill lat/lng, preserve order."""
    input_json = json.dumps({
        "days": [{
            "day_index": 1,
            "theme": "测试",
            "items": [
                {"seq": 1, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 0},
                {"seq": 2, "poi_name": "雷峰塔", "duration_h": 1.5, "travel_minutes_from_prev": 20},
            ]
        }]
    }, ensure_ascii=False)

    result_str = optimize_itinerary(input_json)
    result = json.loads(result_str)

    items = result["days"][0]["items"]
    assert len(items) == 2

    # 坐标应被填充
    for item in items:
        assert "lat" in item, f"Missing lat in {item}"
        assert "lng" in item, f"Missing lng in {item}"
        assert isinstance(item["lat"], (int, float))
        assert isinstance(item["lng"], (int, float))

    # 顺序应保持不变
    assert items[0]["poi_name"] == "西湖"
    assert items[1]["poi_name"] == "雷峰塔"

    # 坐标应为合理的中国范围（不再断言具体值，因为真实 API 结果取决于城市参数）
    for item in items:
        assert 18.0 <= item["lat"] <= 54.0, f"lat out of China range: {item['lat']}"
        assert 73.0 <= item["lng"] <= 136.0, f"lng out of China range: {item['lng']}"


def test_optimize_itinerary_tool_unknown_poi():
    """Tool function: unknown POI gets hash-based fallback coordinates."""
    input_json = json.dumps({
        "days": [{
            "day_index": 1,
            "theme": "测试",
            "items": [
                {"seq": 1, "poi_name": "一个不存在的地方名称XYZ", "duration_h": 1, "travel_minutes_from_prev": 0},
            ]
        }]
    }, ensure_ascii=False)

    result_str = optimize_itinerary(input_json)
    result = json.loads(result_str)

    item = result["days"][0]["items"][0]
    # 即使是未知 POI，也应该有坐标（fallback）
    assert isinstance(item["lat"], (int, float))
    assert isinstance(item["lng"], (int, float))


def test_optimize_itinerary_passes_city_to_geocode():
    """服务层传入 city 后，地理编码必须带上该城市，避免同名 POI 匹配到外地。"""
    with patch("app.agents.tools.route_optimizer.geocode_poi") as mock_geocode:
        mock_geocode.return_value = {"lat": 27.0, "lng": 113.0, "city": "萍乡"}

        input_json = json.dumps({
            "city": "萍乡",
            "days": [{
                "day_index": 1,
                "theme": "测试",
                "items": [
                    {"seq": 1, "poi_name": "玉湖湿地公园", "duration_h": 2, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "杨岐山", "duration_h": 1, "travel_minutes_from_prev": 10},
                ],
            }],
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        assert result["days"][0]["items"][0]["lat"] == 27.0
        mock_geocode.assert_any_call("玉湖湿地公园", city="萍乡", mock_fallback=False)



def test_geocode_with_fallback_prefers_item_city():
    """有指定城市时，优先用该城市做严格地理编码。"""
    with patch("app.agents.tools.route_optimizer.geocode_poi") as mock_geocode:
        mock_geocode.return_value = {"lat": 27.0, "lng": 113.0, "city": "萍乡"}
        result = _geocode_with_fallback("玉湖湿地公园", "萍乡")
        assert result["lat"] == 27.0
        mock_geocode.assert_called_once_with("玉湖湿地公园", city="萍乡", mock_fallback=False)


def test_geocode_with_fallback_falls_back_to_no_city():
    """指定城市搜不到时，放开城市限制，兼容跨城景点。"""
    with patch("app.agents.tools.route_optimizer.geocode_poi") as mock_geocode:
        mock_geocode.side_effect = [
            None,
            {"lat": 30.0, "lng": 120.0, "city": "嘉兴"},
        ]
        result = _geocode_with_fallback("乌镇", "杭州")
        assert result["lat"] == 30.0
        assert mock_geocode.call_count == 2
        assert mock_geocode.call_args_list[0].kwargs == {
            "city": "杭州",
            "mock_fallback": False,
        }
        assert mock_geocode.call_args_list[1].kwargs == {
            "city": "",
            "mock_fallback": False,
        }


def test_geocode_with_fallback_uses_mock_as_last_resort():
    """所有真实搜索都失败时，才使用 mock 兜底坐标。"""
    with patch("app.agents.tools.route_optimizer.geocode_poi") as mock_geocode:
        mock_geocode.side_effect = [
            None,
            None,
            {"lat": 31.0, "lng": 121.0, "city": ""},
        ]
        result = _geocode_with_fallback("一个不存在的跨城POI", "杭州")
        assert result["lat"] == 31.0
        assert mock_geocode.call_count == 3
        assert mock_geocode.call_args_list[2].kwargs == {"city": "杭州"}


# ── Agent 测试（完整 Agent + Tool 管道）──

@pytest.fixture
def agent():
    return create_route_optimizer()


def test_route_optimizer_agent(agent):
    """Agent: receives itinerary JSON, calls tool, returns JSON with coords."""
    itinerary_json = json.dumps({
        "days": [{
            "day_index": 1,
            "theme": "杭州一日",
            "items": [
                {"seq": 1, "poi_name": "灵隐寺", "duration_h": 2, "travel_minutes_from_prev": 0},
                {"seq": 2, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 30},
            ]
        }]
    }, ensure_ascii=False)

    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"请调用 optimize_itinerary 处理：\n{itinerary_json}"}]}
    )

    final = _get_final_json(result["messages"])
    parsed = json.loads(final)

    items = parsed["days"][0]["items"]
    assert len(items) == 2
    assert items[0]["poi_name"] == "灵隐寺"
    assert "lat" in items[0]
    assert "lng" in items[0]


# ══════════════════════════════════════════════════
# Step 7.6 新增测试：真实路径排序 + 降级
# ══════════════════════════════════════════════════

# ── 辅助函数：构造模拟旅行时间矩阵 ──

def _make_fake_matrix(side_effect_fn):
    """用 mock 替换 _amap_direction_direct，通过 _build_travel_time_matrix 生成矩阵。

    需要同时 mock settings.amap_api_key 让代码进入 API 路径。
    """
    def decorator(func):
        return patch("app.agents.tools.route_optimizer.settings")(
            patch("app.agents.tools.route_optimizer._amap_direction_direct")(func)
        )
    return decorator


# ── 单元测试：辅助函数 ──

def test_haversine_distance_same_point():
    """同一位置距离为 0。"""
    d = _haversine_distance(30.0, 120.0, 30.0, 120.0)
    assert d == 0.0


def test_haversine_distance_beijing_shanghai():
    """北京→上海约 1068 km。"""
    d = _haversine_distance(39.9042, 116.4074, 31.2304, 121.4737)
    # 实际约 1068 km
    assert 1_000_000 < d < 1_200_000


def test_select_mode_walking():
    """距离 < 1500m 应选步行。"""
    assert _select_mode(500) == "walking"
    assert _select_mode(1499) == "walking"


def test_select_mode_transit():
    """距离 ≥ 1500m 应选公交。"""
    assert _select_mode(1500) == "transit"
    assert _select_mode(5000) == "transit"


def test_estimate_travel_minutes_walking():
    """步行 1.4 km（< 阈值 1500m）→ 约 17 分钟（5km/h）。"""
    m = _estimate_travel_minutes_from_distance(1400)
    # 1400m / (5000m/3600s) = 1008s ≈ 17 min
    assert 15 <= m <= 20


def test_estimate_travel_minutes_transit():
    """公交 5 km → 约 15 分钟（20km/h）。"""
    m = _estimate_travel_minutes_from_distance(5000)
    assert 12 <= m <= 20


# ── 降级路径测试（无 API Key）──

def test_fallback_preserves_order():
    """无 API Key 时保持 Agent 原始顺序。"""
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        input_json = json.dumps({
            "days": [{
                "day_index": 1, "theme": "测试",
                "items": [
                    {"seq": 1, "poi_name": "灵隐寺", "duration_h": 2, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 0},
                    {"seq": 3, "poi_name": "雷峰塔", "duration_h": 1.5, "travel_minutes_from_prev": 0},
                ]
            }]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        items = result["days"][0]["items"]

        assert [it["poi_name"] for it in items] == ["灵隐寺", "西湖", "雷峰塔"]


def test_fallback_fills_travel_times():
    """无 API Key 时使用 Haversine 估算填充。"""
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        input_json = json.dumps({
            "days": [{
                "day_index": 1, "theme": "测试",
                "items": [
                    {"seq": 1, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "雷峰塔", "duration_h": 1.5, "travel_minutes_from_prev": 0},
                ]
            }]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        items = result["days"][0]["items"]

        # 第一个 POI travel=0
        assert items[0]["travel_minutes_from_prev"] == 0
        # 第二个 POI 应有估算值（西湖→雷峰塔约 1-2km）
        assert items[1]["travel_minutes_from_prev"] > 0


def test_fallback_single_poi_noop():
    """单 POI 日：无 API 调用，travel=0，seq=1。"""
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings:
        mock_settings.amap_api_key = ""
        input_json = json.dumps({
            "days": [{
                "day_index": 1, "theme": "测试",
                "items": [
                    {"seq": 1, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 0},
                ]
            }]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        items = result["days"][0]["items"]

        assert len(items) == 1
        assert items[0]["seq"] == 1
        assert items[0]["travel_minutes_from_prev"] == 0


# ── 真实 API 路径测试（Mock _amap_direction_direct）──

def test_reorder_with_mock_matrix():
    """Mock matrix → 贪心最近邻正确重排。

    场景：3 POI — 灵隐寺(0), 西湖(1), 雷峰塔(2)
    灵隐寺→西湖=10min, 灵隐寺→雷峰塔=50min, 西湖→雷峰塔=20min
    预期：灵隐寺 → 西湖(10min) → 雷峰塔(20min)，顺序不变
    """
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings, \
         patch("app.agents.tools.route_optimizer._amap_direction_direct") as mock_direct:
        mock_settings.amap_api_key = "fake-key"

        def fake_direction(lng1, lat1, lng2, lat2, mode, city=""):
            # 用近似坐标识别 POI 对
            key = (round(lat1, 2), round(lng1, 2), round(lat2, 2), round(lng2, 2))
            # 灵隐寺(30.24,120.10) → 西湖(30.24,120.14): 10min
            # 灵隐寺(30.24,120.10) → 雷峰塔(30.23,120.15): 50min
            # 西湖(30.24,120.14) → 雷峰塔(30.23,120.15): 20min
            if key[0] == round(30.2427, 2) and key[2] == round(30.2374, 2):
                return 10
            if key[0] == round(30.2427, 2) and key[2] == round(30.2336, 2):
                return 50
            if key[0] == round(30.2374, 2) and key[2] == round(30.2336, 2):
                return 20
            return 15

        mock_direct.side_effect = fake_direction

        input_json = json.dumps({
            "days": [{
                "day_index": 1, "theme": "杭州",
                "items": [
                    {"seq": 1, "poi_name": "灵隐寺", "duration_h": 2, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 0},
                    {"seq": 3, "poi_name": "雷峰塔", "duration_h": 1.5, "travel_minutes_from_prev": 0},
                ]
            }]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        items = result["days"][0]["items"]

        assert items[0]["poi_name"] == "灵隐寺"  # 第一个 POI 不变
        assert items[1]["poi_name"] == "西湖"    # 10min < 50min → 西湖 在 雷峰塔 之前
        assert items[2]["poi_name"] == "雷峰塔"


def test_first_poi_preserved_in_reorder():
    """无论矩阵值如何，第一个 POI 始终固定在 seq=1。"""
    # 直接在内存中测试 _reorder_by_nearest_neighbor
    items = [
        {"seq": 1, "poi_name": "A", "lat": 30.0, "lng": 120.0},
        {"seq": 2, "poi_name": "B", "lat": 30.1, "lng": 120.0},
        {"seq": 3, "poi_name": "C", "lat": 30.2, "lng": 120.0},
    ]
    # 矩阵：A 离 C 更近(5)，A→B 很远(100)
    matrix = {
        (0, 1): 100, (0, 2): 5,
        (1, 0): 100, (1, 2): 10,
        (2, 0): 5, (2, 1): 10,
    }

    index_map = _reorder_by_nearest_neighbor(items, matrix)
    assert items[0]["poi_name"] == "A"        # 第一个固定
    assert items[1]["poi_name"] == "C"        # A→C (5) < A→B (100)
    assert index_map[0] == 0                   # 原始索引 0 → 新位置 0


def test_seq_renumbered_after_reorder():
    """重排后 seq 从 1 开始连续编号。"""
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings, \
         patch("app.agents.tools.route_optimizer._amap_direction_direct") as mock_direct:
        mock_settings.amap_api_key = "fake-key"
        mock_direct.return_value = 15  # 所有路段 15min

        input_json = json.dumps({
            "days": [{
                "day_index": 1, "theme": "测试",
                "items": [
                    {"seq": 99, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0},
                    {"seq": 99, "poi_name": "雷峰塔", "duration_h": 1, "travel_minutes_from_prev": 0},
                    {"seq": 99, "poi_name": "灵隐寺", "duration_h": 2, "travel_minutes_from_prev": 0},
                ]
            }]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        items = result["days"][0]["items"]

        assert [it["seq"] for it in items] == [1, 2, 3]


def test_travel_times_from_matrix():
    """验证矩阵数据正确回填到 travel_minutes_from_prev。"""
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings, \
         patch("app.agents.tools.route_optimizer._amap_direction_direct") as mock_direct:
        mock_settings.amap_api_key = "fake-key"
        mock_direct.return_value = 15

        input_json = json.dumps({
            "days": [{
                "day_index": 1, "theme": "测试",
                "items": [
                    {"seq": 1, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "雷峰塔", "duration_h": 1, "travel_minutes_from_prev": 0},
                ]
            }]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        items = result["days"][0]["items"]

        assert items[0]["travel_minutes_from_prev"] == 0
        assert items[1]["travel_minutes_from_prev"] == 15  # mock 返回值


def test_multi_day_isolation():
    """多日行程：每日独立优化，互不干扰。"""
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings, \
         patch("app.agents.tools.route_optimizer._amap_direction_direct") as mock_direct:
        mock_settings.amap_api_key = "fake-key"
        mock_direct.return_value = 15

        input_json = json.dumps({
            "days": [
                {"day_index": 1, "theme": "第一天", "items": [
                    {"seq": 1, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "雷峰塔", "duration_h": 1, "travel_minutes_from_prev": 0},
                ]},
                {"day_index": 2, "theme": "第二天", "items": [
                    {"seq": 1, "poi_name": "灵隐寺", "duration_h": 2, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "故宫", "duration_h": 3, "travel_minutes_from_prev": 0},
                ]},
            ]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))

        assert len(result["days"]) == 2
        # 第一天
        assert result["days"][0]["items"][0]["poi_name"] == "西湖"
        assert len(result["days"][0]["items"]) == 2
        # 第二天
        assert result["days"][1]["items"][0]["poi_name"] == "灵隐寺"
        assert len(result["days"][1]["items"]) == 2


def test_api_failure_triggers_fallback():
    """_amap_direction_direct 返回 None → 降级到 fallback。"""
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings, \
         patch("app.agents.tools.route_optimizer._amap_direction_direct") as mock_direct:
        mock_settings.amap_api_key = "fake-key"
        mock_direct.return_value = None  # 模拟 API 全部失败

        input_json = json.dumps({
            "days": [{
                "day_index": 1, "theme": "测试",
                "items": [
                    {"seq": 1, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "雷峰塔", "duration_h": 1.5, "travel_minutes_from_prev": 0},
                    {"seq": 3, "poi_name": "灵隐寺", "duration_h": 2, "travel_minutes_from_prev": 0},
                ]
            }]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        items = result["days"][0]["items"]

        # 应保持原始顺序
        assert [it["poi_name"] for it in items] == ["西湖", "雷峰塔", "灵隐寺"]
        # travel 应全部有估算值
        for item in items:
            assert "travel_minutes_from_prev" in item
            assert isinstance(item["travel_minutes_from_prev"], int)


def test_two_poi_no_reorder_but_time_filled():
    """2 POI 日：不重排（n≤2），但用真实 API 数据填充时间。"""
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings, \
         patch("app.agents.tools.route_optimizer._amap_direction_direct") as mock_direct:
        mock_settings.amap_api_key = "fake-key"
        mock_direct.return_value = 15  # 固定 15min

        input_json = json.dumps({
            "days": [{
                "day_index": 1, "theme": "测试",
                "items": [
                    {"seq": 1, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "雷峰塔", "duration_h": 1.5, "travel_minutes_from_prev": 0},
                ]
            }]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        items = result["days"][0]["items"]

        # 顺序不变（n≤2）
        assert items[0]["poi_name"] == "西湖"
        assert items[1]["poi_name"] == "雷峰塔"
        # 时间从 matrix 填充
        assert items[0]["travel_minutes_from_prev"] == 0
        assert items[1]["travel_minutes_from_prev"] == 15


def test_city_field_removed_from_output():
    """内部 city 字段不应出现在最终输出中。"""
    with patch("app.agents.tools.route_optimizer.settings") as mock_settings, \
         patch("app.agents.tools.route_optimizer._amap_direction_direct") as mock_direct:
        mock_settings.amap_api_key = "fake-key"
        mock_direct.return_value = 15

        input_json = json.dumps({
            "days": [{
                "day_index": 1, "theme": "测试",
                "items": [
                    {"seq": 1, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0},
                ]
            }]
        }, ensure_ascii=False)

        result = json.loads(optimize_itinerary(input_json))
        item = result["days"][0]["items"][0]

        assert "city" not in item


def _get_final_json(messages: list) -> str:
    """Extract JSON from the final AIMessage (no tool_calls)."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = getattr(msg, "content", "")
            if not content:
                continue
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
            for start_ch, end_ch in [("{", "}"), ("[", "]")]:
                start = content.find(start_ch)
                end = content.rfind(end_ch)
                if start != -1 and end > start:
                    return content[start:end + 1]
            return content
    return ""
