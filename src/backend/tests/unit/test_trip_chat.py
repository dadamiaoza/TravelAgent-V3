"""Trip Assistant tools: propose without writing; apply only in auto mode."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from app.schemas.trip import TripChatRequest
from app.services.trip_chat import (
    WRITE_MODE_AUTO,
    WRITE_MODE_PROPOSE,
    TripChatSession,
    build_tools,
    chat_thread_id,
    run_trip_chat,
)

LEIFENG = UUID("11111111-1111-1111-1111-111111111111")
WEST_LAKE = UUID("22222222-2222-2222-2222-222222222222")


def _context() -> dict:
    return {
        "destination": "杭州",
        "city": "杭州",
        "start_date": "2026-06-01",
        "days": [
            {
                "day_index": 1,
                "date": "2026-06-01",
                "route_type": "city",
                "items": [
                    {
                        "id": str(WEST_LAKE),
                        "seq": 1,
                        "poi_name": "西湖",
                        "start_time": "09:00:00",
                        "end_time": "11:00:00",
                        "travel_minutes": 0,
                    },
                    {
                        "id": str(LEIFENG),
                        "seq": 2,
                        "poi_name": "雷峰塔",
                        "start_time": "11:30:00",
                        "end_time": "13:00:00",
                        "travel_minutes": 20,
                    },
                ],
            },
            {
                "day_index": 2,
                "date": "2026-06-02",
                "route_type": "city",
                "items": [
                    {
                        "id": "33333333-3333-3333-3333-333333333333",
                        "seq": 1,
                        "poi_name": "灵隐寺",
                        "start_time": "09:00:00",
                        "end_time": "12:00:00",
                        "travel_minutes": 0,
                    },
                ],
            },
        ],
    }


def _session(write_mode: str = WRITE_MODE_PROPOSE, db=None) -> TripChatSession:
    return TripChatSession(
        trip_id=uuid4(),
        context=_context(),
        write_mode=write_mode,
        db=db,
    )


def _tools(session: TripChatSession) -> dict:
    return {fn.__name__: fn for fn in build_tools(session)}


def test_propose_mode_does_not_expose_apply_delta() -> None:
    names = set(_tools(_session(WRITE_MODE_PROPOSE)))
    assert names == {"propose_delta", "check_facts", "parse_guide"}


def test_auto_mode_exposes_apply_delta() -> None:
    names = set(_tools(_session(WRITE_MODE_AUTO)))
    assert names == {"propose_delta", "check_facts", "parse_guide", "apply_delta"}


def test_propose_delete_by_name_records_delta_without_writing() -> None:
    session = _session()
    with patch("app.services.trip_chat.trip_editor.apply_delta") as apply_fn:
        result = _tools(session)["propose_delta"]("delete", poi_name="雷峰塔")

    apply_fn.assert_not_called()
    assert "雷峰塔" in result
    assert len(session.suggestions) == 1
    delta = session.suggestions[0]
    assert delta.action == "delete"
    assert delta.target is not None
    assert delta.target.item_id == LEIFENG
    assert delta.target.day_index == 1
    assert delta.payload is not None
    assert delta.payload.poi_name == "雷峰塔"
    assert session.applied == []


def test_apply_delta_refused_if_called_in_propose_mode() -> None:
    session = _session(WRITE_MODE_PROPOSE, db=MagicMock())
    # Direct call through the helper keeps the policy even if a tool slips in.
    from app.services.trip_chat import apply_itinerary_delta

    result = apply_itinerary_delta(session, action="delete", poi_name="雷峰塔")

    assert "只提议" in result
    assert session.applied == []


def test_apply_delta_writes_in_auto_mode() -> None:
    db = MagicMock()
    session = _session(WRITE_MODE_AUTO, db=db)
    with patch("app.services.trip_chat.trip_editor.apply_delta") as apply_fn:
        apply_fn.return_value = MagicMock()
        result = _tools(session)["apply_delta"]("delete", poi_name="雷峰塔")

    apply_fn.assert_called_once()
    assert session.applied
    assert session.applied[0].target.item_id == LEIFENG
    assert "已写入" in result or "已删除" in result or "雷峰塔" in result


def test_check_facts_returns_weather_and_hours() -> None:
    session = _session()
    with (
        patch("app.services.trip_chat.get_weather", return_value="杭州 2026-06-01：小雨"),
        patch("app.services.trip_chat.get_opening_hours", return_value="08:00-17:00"),
        patch(
            "app.services.trip_chat.evaluate_closure_rule",
            return_value={"matched": False, "risk": "low", "reason": "", "source": ""},
        ),
    ):
        result = _tools(session)["check_facts"](poi_name="雷峰塔", day_index=1)

    assert "小雨" in result
    assert "08:00-17:00" in result
    assert "雷峰塔" in result


def test_chat_thread_id_is_not_generation_prefix() -> None:
    trip_id = uuid4()
    thread = chat_thread_id(trip_id)
    assert thread.startswith("trip-chat-")
    assert f"trip-{trip_id}" != thread


def test_run_trip_chat_collects_tool_suggestions() -> None:
    item = SimpleNamespace(
        id=LEIFENG,
        seq=2,
        poi_name="雷峰塔",
        start_time=None,
        end_time=None,
        travel_minutes=0,
    )
    day = SimpleNamespace(
        day_index=1,
        date=date(2026, 6, 1),
        route_type="city",
        items=[item],
    )
    trip = SimpleNamespace(
        id=uuid4(),
        destination="杭州",
        city="杭州",
        start_date=date(2026, 6, 1),
        days=[day],
    )

    def fake_invoke(*, tools, **_kwargs) -> str:
        by_name = {fn.__name__: fn for fn in tools}
        by_name["propose_delta"]("delete", poi_name="雷峰塔")
        return "建议删除雷峰塔，确认后从行程里拿掉。"

    out = run_trip_chat(
        trip=trip,
        body=TripChatRequest(message="删掉雷峰塔"),
        thread_id="trip-chat-test",
        db=None,
        invoker=fake_invoke,
    )

    assert out.thread_id == "trip-chat-test"
    assert "雷峰塔" in out.reply
    assert len(out.suggestions) == 1
    assert out.suggestions[0].action == "delete"
    assert out.applied == []


def test_run_trip_chat_passes_plain_user_message() -> None:
    captured: dict = {}
    item = SimpleNamespace(
        id=LEIFENG,
        seq=1,
        poi_name="雷峰塔",
        start_time=None,
        end_time=None,
        travel_minutes=0,
        is_locked=False,
    )
    trip = SimpleNamespace(
        id=uuid4(),
        destination="杭州",
        city="杭州",
        start_date=date(2026, 6, 1),
        days=[
            SimpleNamespace(day_index=1, date=date(2026, 6, 1), route_type="city", items=[item]),
        ],
    )

    def fake_invoke(*, message: str, context: dict, **_kwargs) -> str:
        captured["message"] = message
        captured["context"] = context
        return "好的"

    run_trip_chat(
        trip=trip,
        body=TripChatRequest(message="删掉雷峰塔"),
        thread_id="trip-chat-test",
        db=None,
        invoker=fake_invoke,
    )

    assert captured["message"] == "删掉雷峰塔"
    assert "days" in captured["context"]
    assert '"poi_name"' not in captured["message"]


def test_propose_move_sets_destination_day() -> None:
    session = _session()
    result = _tools(session)["propose_delta"]("move", poi_name="雷峰塔", day_index=2)
    delta = session.suggestions[0]
    assert delta.action == "move"
    assert delta.target is not None
    assert delta.target.day_index == 2
    assert delta.target.item_id == LEIFENG
    assert delta.preview_before
    assert "第1天" in (delta.preview_before or "")
    assert "第2天" in (delta.preview_after or "")
    assert "雷峰塔" in result


def test_propose_replace_uses_new_name() -> None:
    session = _session()
    _tools(session)["propose_delta"](
        "replace",
        poi_name="雷峰塔",
        new_poi_name="河坊街",
    )
    delta = session.suggestions[0]
    assert delta.action == "replace"
    assert delta.payload is not None
    assert delta.payload.poi_name == "河坊街"
    assert "河坊街" in (delta.preview_after or "")


def test_propose_update_sets_visit_tips() -> None:
    session = _session()
    _tools(session)["propose_delta"](
        "update",
        poi_name="雷峰塔",
        visit_tips="傍晚登塔看西湖。",
    )
    delta = session.suggestions[0]
    assert delta.action == "update"
    assert delta.payload is not None
    assert delta.payload.visit_tips == "傍晚登塔看西湖。"


def test_parse_guide_adds_new_pois_and_skips_existing() -> None:
    session = _session()
    entities = [
        {"poi_name": "西湖", "day_index": 1, "seq": 1},
        {"poi_name": "断桥", "day_index": 1, "seq": 2, "visit_tips": "清晨人少。", "cost_estimate": "免费"},
    ]
    with patch("app.services.guide_extract.extract_guide_entities", return_value=entities):
        result = _tools(session)["parse_guide"]("第一天西湖和断桥")
    names = [d.payload.poi_name for d in session.suggestions if d.payload]
    assert "断桥" in names
    assert "西湖" not in names
    assert "1 个" in result
    added = next(d for d in session.suggestions if d.payload and d.payload.poi_name == "断桥")
    assert added.payload is not None
    assert added.payload.visit_tips == "清晨人少。"
    assert added.payload.cost_note == "免费"


def test_check_facts_still_returns_weather_when_poi_missing() -> None:
    session = _session()
    with (
        patch("app.services.trip_chat.get_weather", return_value="杭州 2026-06-01：小雨"),
        patch("app.services.trip_chat.get_opening_hours", return_value="09:00-17:00"),
        patch(
            "app.services.trip_chat.evaluate_closure_rule",
            return_value={"matched": False, "risk": "low", "reason": "", "source": ""},
        ),
    ):
        result = _tools(session)["check_facts"](poi_name="不存在的馆", day_index=1)
    assert "小雨" in result
    assert "找不到" in result


def test_progress_callback_fires_for_tools() -> None:
    seen: list[tuple[str, str]] = []
    session = _session()
    session.progress = lambda tool, message: seen.append((tool, message))
    with (
        patch("app.services.trip_chat.get_weather", return_value="晴"),
        patch("app.services.trip_chat.get_opening_hours", return_value="09:00-17:00"),
        patch(
            "app.services.trip_chat.evaluate_closure_rule",
            return_value={"matched": False, "risk": "low"},
        ),
    ):
        _tools(session)["check_facts"](day_index=1)
    assert seen
    assert seen[0][0] == "check_facts"
