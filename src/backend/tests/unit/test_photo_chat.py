"""Trip Assistant photo tools: propose without writing; never guess GPS."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from app.schemas.trip import ItineraryDelta, ItineraryDeltaPayload
from app.services.photo_chat import PHOTO_ACTIONS, apply_photo_delta, propose_photo_change
from app.services.trip_chat import WRITE_MODE_AUTO, WRITE_MODE_PROPOSE, TripChatSession, build_tools

WANGJIANG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
YUELU = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PHOTO_A = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _session(write_mode: str = WRITE_MODE_PROPOSE, db=None) -> TripChatSession:
    return TripChatSession(
        trip_id=uuid4(),
        context={
            "destination": "长沙",
            "days": [
                {
                    "day_index": 1,
                    "items": [
                        {"id": str(YUELU), "seq": 1, "poi_name": "岳麓山"},
                    ],
                }
            ],
            "visit_stops": [
                {
                    "id": str(WANGJIANG),
                    "place_name": "长沙望江公园",
                    "status": "confirmed",
                    "photo_count": 2,
                    "photo_ids": [str(PHOTO_A)],
                }
            ],
            "photos": [
                {
                    "id": str(PHOTO_A),
                    "filename": "IMG_20240802_150304.jpg",
                    "captured_at": "2024-08-02",
                    "place": "长沙望江公园",
                    "item_id": None,
                    "visit_stop_id": str(WANGJIANG),
                }
            ],
        },
        write_mode=write_mode,
        db=db,
    )


def _tools(session: TripChatSession) -> dict:
    return {fn.__name__: fn for fn in build_tools(session)}


def test_propose_mode_exposes_photo_tool_not_apply() -> None:
    names = set(_tools(_session(WRITE_MODE_PROPOSE)))
    assert "propose_photo_change" in names
    assert "apply_photo_change" not in names
    assert "apply_delta" not in names


def test_auto_mode_exposes_apply_photo_change() -> None:
    names = set(_tools(_session(WRITE_MODE_AUTO)))
    assert "propose_photo_change" in names
    assert "apply_photo_change" in names


def test_propose_dismiss_stop_by_name_does_not_write() -> None:
    session = _session()
    with patch("app.services.photo_chat.dismiss_visit_stop") as dismiss:
        result = propose_photo_change(session, action="dismiss_visit_stop", place_name="望江公园")

    dismiss.assert_not_called()
    assert "望江公园" in result
    assert len(session.suggestions) == 1
    delta = session.suggestions[0]
    assert delta.action == "dismiss_visit_stop"
    assert delta.payload is not None
    assert delta.payload.visit_stop_id == WANGJIANG
    assert session.applied == []


def test_propose_dismiss_unknown_stop_does_not_invent() -> None:
    session = _session()
    result = propose_photo_change(session, action="dismiss", place_name="外滩")
    assert session.suggestions == []
    assert "找不到" in result or "没有" in result


def test_propose_reassign_by_place_name_attaches_stop() -> None:
    session = _session()
    result = propose_photo_change(
        session,
        action="reassign_photo",
        place_name="望江公园",
        poi_name="岳麓山",
    )
    delta = session.suggestions[0]
    assert delta.action == "attach_visit_stop"
    assert delta.payload is not None
    assert delta.payload.visit_stop_id == WANGJIANG
    assert delta.target is not None
    assert delta.target.item_id == YUELU
    assert "岳麓山" in result
    assert "IMG_" not in (delta.preview_before or "")


def test_propose_reassign_unassigned_by_plain_words() -> None:
    session = _session()
    loose_id = uuid4()
    session.context["photos"].append(
        {
            "id": str(loose_id),
            "filename": "mmexport123.jpg",
            "captured_at": "2024-08-02",
            "place": None,
            "item_id": None,
            "visit_stop_id": None,
        }
    )
    propose_photo_change(session, action="reassign_photo", place_name="未归类", poi_name="岳麓山")
    delta = session.suggestions[0]
    assert delta.action == "reassign_photo"
    assert delta.payload is not None
    assert loose_id in (delta.payload.photo_ids or [])
    assert "未归类" in (delta.preview_before or "")
    assert "mmexport" not in (delta.preview_before or "")


def test_propose_reassign_uses_opened_photo() -> None:
    session = _session()
    session.context["current_photo_id"] = str(PHOTO_A)
    propose_photo_change(session, action="reassign_photo", poi_name="岳麓山")
    delta = session.suggestions[0]
    assert delta.action == "reassign_photo"
    assert delta.payload is not None
    assert PHOTO_A in (delta.payload.photo_ids or [])


def test_propose_reassign_asks_for_place_not_filename() -> None:
    session = _session()
    result = propose_photo_change(session, action="reassign_photo", poi_name="岳麓山")
    assert session.suggestions == []
    assert "文件名" not in result
    assert "地点" in result or "点开" in result


def test_propose_reassign_photo_by_filename_still_works() -> None:
    session = _session()
    result = propose_photo_change(
        session,
        action="reassign_photo",
        filename="IMG_20240802_150304.jpg",
        poi_name="岳麓山",
    )
    delta = session.suggestions[0]
    assert delta.action == "reassign_photo"
    assert delta.payload is not None
    assert PHOTO_A in (delta.payload.photo_ids or [])
    assert delta.target is not None
    assert delta.target.item_id == YUELU
    assert "岳麓山" in result


def test_propose_refuses_to_guess_location() -> None:
    session = _session()
    result = propose_photo_change(session, action="reassign_photo", filename="IMG_20240802_150304.jpg")
    assert session.suggestions == []
    assert "地点" in result or "计划" in result


def test_apply_photo_change_refused_in_propose_mode() -> None:
    from app.services.trip_chat import apply_photo_change

    session = _session(WRITE_MODE_PROPOSE, db=MagicMock())
    result = apply_photo_change(session, action="dismiss_visit_stop", place_name="望江公园")
    assert "只提议" in result
    assert session.applied == []


def test_apply_photo_delta_dismisses_stop() -> None:
    db = MagicMock()
    stop = SimpleNamespace(id=WANGJIANG, trip_id=uuid4(), status="confirmed", assignments=[])
    db.get.return_value = stop
    delta = ItineraryDelta(
        action="dismiss_visit_stop",
        payload=ItineraryDeltaPayload(visit_stop_id=WANGJIANG, poi_name="长沙望江公园"),
    )
    with patch("app.services.photo_chat.dismiss_visit_stop") as dismiss:
        apply_photo_delta(db, stop.trip_id, delta)
    dismiss.assert_called_once_with(db, stop)


def test_photo_actions_are_not_itinerary_edits() -> None:
    assert "delete" not in PHOTO_ACTIONS
    assert "add" not in PHOTO_ACTIONS
