from datetime import date, datetime, time
from uuid import uuid4

from app.services.geo_convert import haversine_m, wgs84_to_gcj02
from app.services.photo_match import ItineraryNode, PhotoMeta, match_photo


def test_wgs84_to_gcj02_shifts_hundreds_of_meters_in_china() -> None:
    wgs_lat, wgs_lng = 39.9042, 116.4074
    gcj_lat, gcj_lng = wgs84_to_gcj02(wgs_lat, wgs_lng)
    offset = haversine_m(wgs_lat, wgs_lng, gcj_lat, gcj_lng)
    assert 200 <= offset <= 700
    assert (gcj_lat, gcj_lng) != (wgs_lat, wgs_lng)


def test_wgs84_to_gcj02_is_identity_outside_china() -> None:
    lat, lng = 40.7128, -74.0060
    assert wgs84_to_gcj02(lat, lng) == (lat, lng)


def test_close_daytime_gps_auto_assigns() -> None:
    item_id = uuid4()
    wgs_lat, wgs_lng = 27.4485, 114.1765
    gcj_lat, gcj_lng = wgs84_to_gcj02(wgs_lat, wgs_lng)
    node = ItineraryNode(
        item_id=item_id,
        poi_name="金顶",
        day_date=date(2024, 7, 31),
        start_time=time(9, 0),
        end_time=time(11, 0),
        lat=gcj_lat,
        lng=gcj_lng,
    )
    result = match_photo(
        PhotoMeta(
            latitude=wgs_lat,
            longitude=wgs_lng,
            captured_at=datetime(2024, 7, 31, 9, 30),
        ),
        [node],
    )
    assert result.photo_class == "A"
    assert result.auto_assign is True
    assert result.item_id == item_id
    assert result.confidence >= 0.85


def test_close_gps_at_2am_is_not_auto() -> None:
    item_id = uuid4()
    wgs_lat, wgs_lng = 27.4485, 114.1765
    gcj_lat, gcj_lng = wgs84_to_gcj02(wgs_lat, wgs_lng)
    node = ItineraryNode(
        item_id=item_id,
        poi_name="金顶",
        day_date=date(2024, 7, 31),
        start_time=time(9, 0),
        end_time=time(17, 0),
        lat=gcj_lat,
        lng=gcj_lng,
    )
    result = match_photo(
        PhotoMeta(
            latitude=27.4485,
            longitude=114.1765,
            captured_at=datetime(2024, 7, 31, 2, 0),
        ),
        [node],
    )
    assert result.photo_class == "A"
    assert result.auto_assign is False
    assert result.confidence < 0.85


def test_time_only_photo_never_auto_assigns() -> None:
    node = ItineraryNode(
        item_id=uuid4(),
        poi_name="金顶",
        day_date=date(2024, 7, 31),
        start_time=time(9, 0),
        end_time=time(11, 0),
        lat=27.45,
        lng=114.18,
    )
    result = match_photo(
        PhotoMeta(
            latitude=None,
            longitude=None,
            captured_at=datetime(2024, 7, 31, 9, 30),
        ),
        [node],
    )
    assert result.photo_class == "B"
    assert result.auto_assign is False
    assert result.item_id is None
    assert result.candidates


def test_gps_only_photo_uses_gps_score() -> None:
    item_id = uuid4()
    wgs_lat, wgs_lng = 27.4485, 114.1765
    gcj_lat, gcj_lng = wgs84_to_gcj02(wgs_lat, wgs_lng)
    node = ItineraryNode(
        item_id=item_id,
        poi_name="金顶",
        day_date=date(2024, 7, 31),
        start_time=time(9, 0),
        end_time=time(11, 0),
        lat=gcj_lat,
        lng=gcj_lng,
    )
    result = match_photo(
        PhotoMeta(latitude=wgs_lat, longitude=wgs_lng, captured_at=None),
        [node],
    )
    assert result.photo_class == "A"
    assert result.auto_assign is True
    assert result.item_id == item_id
    assert result.confidence >= 0.85


def test_wechat_photo_has_no_captured_at_and_never_auto() -> None:
    node = ItineraryNode(
        item_id=uuid4(),
        poi_name="金顶",
        day_date=date(2024, 7, 31),
        start_time=time(9, 0),
        end_time=time(11, 0),
        lat=27.45,
        lng=114.18,
    )
    result = match_photo(
        PhotoMeta(latitude=None, longitude=None, captured_at=None),
        [node],
    )
    assert result.photo_class == "C"
    assert result.auto_assign is False
    assert result.item_id is None
    assert result.confidence == 0
    assert result.assignment_type != "batch_neighbor"
