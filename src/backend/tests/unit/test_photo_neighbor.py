from datetime import datetime
from uuid import uuid4

from app.services.photo_neighbor import (
    NEIGHBOR_ONESIDE_SCORE,
    NEIGHBOR_SANDWICH_SCORE,
    NeighborSlot,
    infer_batch_neighbors,
)


def _c(photo_id=None) -> NeighborSlot:
    return NeighborSlot(
        photo_id=photo_id or uuid4(),
        has_gps=False,
        captured_at=None,
        item_id=None,
        visit_stop_id=None,
    )


def _anchor(*, item_id=None, visit_stop_id=None, photo_id=None) -> NeighborSlot:
    return NeighborSlot(
        photo_id=photo_id or uuid4(),
        has_gps=True,
        captured_at=datetime(2024, 7, 31, 9, 0),
        item_id=item_id,
        visit_stop_id=visit_stop_id,
    )


def test_sandwich_same_item_copies_both_c_photos() -> None:
    jinding = uuid4()
    left = _anchor(item_id=jinding)
    right = _anchor(item_id=jinding)
    c1, c2 = _c(), _c()
    hints = infer_batch_neighbors([left, c1, c2, right])
    assert {hint.photo_id for hint in hints} == {c1.photo_id, c2.photo_id}
    for hint in hints:
        assert hint.item_id == jinding
        assert hint.visit_stop_id is None
        assert hint.confidence == NEIGHBOR_SANDWICH_SCORE
        assert hint.bound == "sandwich"
        assert hint.neighbor_photo_ids == (left.photo_id, right.photo_id)


def test_different_bounds_do_not_copy() -> None:
    c1 = _c()
    hints = infer_batch_neighbors(
        [
            _anchor(item_id=uuid4()),
            c1,
            _anchor(item_id=uuid4()),
        ]
    )
    assert hints == []


def test_trailing_oneside_copies_from_left_anchor() -> None:
    jinding = uuid4()
    left = _anchor(item_id=jinding)
    c1, c2 = _c(), _c()
    hints = infer_batch_neighbors([left, c1, c2])
    assert [hint.photo_id for hint in hints] == [c1.photo_id, c2.photo_id]
    for hint in hints:
        assert hint.item_id == jinding
        assert hint.confidence == NEIGHBOR_ONESIDE_SCORE
        assert hint.bound == "left"
        assert hint.neighbor_photo_ids == (left.photo_id,)


def test_all_type_c_batch_is_noop() -> None:
    assert infer_batch_neighbors([_c(), _c(), _c()]) == []


def test_sandwich_copies_visit_stop_not_item() -> None:
    stop_id = uuid4()
    left = _anchor(visit_stop_id=stop_id)
    right = _anchor(visit_stop_id=stop_id)
    c1 = _c()
    hints = infer_batch_neighbors([left, c1, right])
    assert len(hints) == 1
    assert hints[0].visit_stop_id == stop_id
    assert hints[0].item_id is None
    assert hints[0].bound == "sandwich"


def test_manual_type_c_is_not_hinted() -> None:
    jinding = uuid4()
    manual = NeighborSlot(
        photo_id=uuid4(),
        has_gps=False,
        captured_at=None,
        item_id=jinding,
        visit_stop_id=None,
    )
    hints = infer_batch_neighbors(
        [
            _anchor(item_id=jinding),
            manual,
            _anchor(item_id=jinding),
        ]
    )
    assert hints == []


def test_neighbor_scores_never_reach_auto_or_pending_band() -> None:
    jinding = uuid4()
    hints = infer_batch_neighbors(
        [
            _anchor(item_id=jinding),
            _c(),
            _c(),
            _anchor(item_id=jinding),
            _c(),
        ]
    )
    assert hints
    assert all(hint.confidence <= 0.55 for hint in hints)
    assert all(hint.confidence < 0.60 for hint in hints)
    assert all(hint.confidence < 0.85 for hint in hints)


def test_item_and_visit_stop_are_different_targets() -> None:
    c1 = _c()
    hints = infer_batch_neighbors(
        [
            _anchor(item_id=uuid4()),
            c1,
            _anchor(visit_stop_id=uuid4()),
        ]
    )
    assert hints == []


def test_leading_oneside_copies_from_right_anchor() -> None:
    jinding = uuid4()
    right = _anchor(item_id=jinding)
    c1 = _c()
    hints = infer_batch_neighbors([c1, right])
    assert len(hints) == 1
    assert hints[0].photo_id == c1.photo_id
    assert hints[0].item_id == jinding
    assert hints[0].bound == "right"
    assert hints[0].confidence == NEIGHBOR_ONESIDE_SCORE


def test_type_b_is_not_hinted() -> None:
    jinding = uuid4()
    type_b = NeighborSlot(
        photo_id=uuid4(),
        has_gps=False,
        captured_at=datetime(2024, 7, 31, 10, 0),
        item_id=None,
        visit_stop_id=None,
    )
    hints = infer_batch_neighbors(
        [
            _anchor(item_id=jinding),
            type_b,
            _anchor(item_id=jinding),
        ]
    )
    assert hints == []
