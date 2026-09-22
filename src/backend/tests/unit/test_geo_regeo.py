from app.services.geo_regeo import reverse_geocode_amap


def test_reverse_geocode_prefers_poi_name() -> None:
    payload = {
        "status": "1",
        "regeocode": {
            "formatted_address": "湖南省长沙市芙蓉区黄兴路",
            "pois": [{"name": "黄兴路步行街"}],
        },
    }
    name = reverse_geocode_amap(112.976, 28.188, fetch=lambda _url, _params: payload)
    assert name == "黄兴路步行街"


def test_reverse_geocode_falls_back_to_formatted_address() -> None:
    payload = {
        "status": "1",
        "regeocode": {"formatted_address": "湖南省长沙市芙蓉区", "pois": []},
    }
    name = reverse_geocode_amap(112.976, 28.188, fetch=lambda _url, _params: payload)
    assert name == "湖南省长沙市芙蓉区"


def test_reverse_geocode_returns_none_on_failure() -> None:
    def boom(_url: str, _params: dict) -> dict:
        raise TimeoutError("amap down")

    assert reverse_geocode_amap(112.976, 28.188, fetch=boom) is None
