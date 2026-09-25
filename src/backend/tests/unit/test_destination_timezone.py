from app.services.destination_timezone import effective_timezone, timezone_for_place


def test_known_cities_map_to_iana_zones():
    assert timezone_for_place("杭州") == "Asia/Shanghai"
    assert timezone_for_place("大阪") == "Asia/Tokyo"
    assert timezone_for_place("檀香山市") == "Pacific/Honolulu"
    assert timezone_for_place(None, "京都") == "Asia/Tokyo"
    assert timezone_for_place("无名镇") is None


def test_stored_timezone_wins_over_city():
    assert effective_timezone("Pacific/Honolulu", "杭州") == "Pacific/Honolulu"
    assert effective_timezone("Not/AZone", "杭州") == "Asia/Shanghai"
    assert effective_timezone(None, "美食", "大阪") == "Asia/Tokyo"
    assert effective_timezone(None, None, "草稿") is None
