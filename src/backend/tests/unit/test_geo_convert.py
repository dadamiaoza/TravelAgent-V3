from app.services.geo_convert import haversine_m, wgs84_to_gcj02


def test_wgs84_to_gcj02_shifts_hundreds_of_meters_in_china() -> None:
    wgs_lat, wgs_lng = 39.9042, 116.4074
    gcj_lat, gcj_lng = wgs84_to_gcj02(wgs_lat, wgs_lng)
    offset = haversine_m(wgs_lat, wgs_lng, gcj_lat, gcj_lng)
    assert 200 <= offset <= 700
    assert (gcj_lat, gcj_lng) != (wgs_lat, wgs_lng)


def test_wgs84_to_gcj02_is_identity_outside_china() -> None:
    lat, lng = 40.7128, -74.0060
    assert wgs84_to_gcj02(lat, lng) == (lat, lng)
