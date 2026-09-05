from app.services.visit_fields import copy_visit_fields


def test_copy_visit_fields_maps_cost_estimate_string() -> None:
    fields = copy_visit_fields(
        {
            "suggested_duration_h": 2,
            "best_time": "morning",
            "cost_estimate": "门票60元",
            "visit_tips": "早上去排队短。",
        }
    )
    assert fields["cost_note"] == "门票60元"
    assert fields["suggested_duration_h"] == 2
    assert fields["best_time"] == "morning"
    assert fields["visit_tips"] == "早上去排队短。"


def test_copy_visit_fields_prefers_tips_key_from_planner() -> None:
    fields = copy_visit_fields({"duration_h": 3, "tips": "沿湖骑行一圈。"})
    assert fields["suggested_duration_h"] == 3
    assert fields["visit_tips"] == "沿湖骑行一圈。"


def test_copy_visit_fields_keeps_long_opening_hours() -> None:
    blob = "拙政园开放时间：" + "06:45-17:30；" * 20 + "建议出行前以官方公告为准"
    fields = copy_visit_fields({"opening_hours": blob})
    assert fields["opening_hours"] == blob
    assert len(fields["opening_hours"]) > 128


def test_copy_visit_fields_skips_empty() -> None:
    assert copy_visit_fields({"poi_name": "西湖", "duration_h": 0}) == {}
