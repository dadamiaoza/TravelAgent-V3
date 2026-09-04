"""Source parse route must persist entities, not infer a trip."""
from app.api.v1.sources import router


def test_parse_and_infer_are_distinct_handlers() -> None:
    named = {
        route.path: route.endpoint.__name__
        for route in router.routes
        if hasattr(route, "endpoint")
    }
    assert named["/sources/{source_id}/parse"] == "parse_source_persist"
    assert named["/sources/{source_id}/infer-trip"] == "infer_trip_from_source"
