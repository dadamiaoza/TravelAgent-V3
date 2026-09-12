from datetime import date, datetime, time
from uuid import uuid4

from app.services.geo_convert import wgs84_to_gcj02
from app.services.photo_cluster import GpsPoint, cluster_unmatched_photos
from app.services.photo_match import ItineraryNode


def _node(lat: float, lng: float, name: str = "计划点") -> ItineraryNode:
    return ItineraryNode(
        item_id=uuid4(),
        poi_name=name,
        day_date=date(2024, 7, 31),
        start_time=time(9, 0),
        end_time=time(11, 0),
        lat=lat,
        lng=lng,
    )


def test_nearby_gps_photos_form_one_cluster() -> None:
    wgs_lat, wgs_lng = 28.188, 112.976
    points = [
        GpsPoint(photo_id=uuid4(), latitude=wgs_lat, longitude=wgs_lng, captured_at=datetime(2024, 8, 2, 15, 0)),
        GpsPoint(
            photo_id=uuid4(),
            latitude=wgs_lat + 0.0008,
            longitude=wgs_lng,
            captured_at=datetime(2024, 8, 2, 15, 10),
        ),
    ]
    clusters = cluster_unmatched_photos(points, [])
    assert len(clusters) == 1
    assert len(clusters[0].photo_ids) == 2
    assert clusters[0].nearest_item_id is None


def test_far_apart_gps_photos_form_two_clusters() -> None:
    points = [
        GpsPoint(photo_id=uuid4(), latitude=28.188, longitude=112.976, captured_at=datetime(2024, 8, 2, 15, 0)),
        GpsPoint(photo_id=uuid4(), latitude=27.45, longitude=114.18, captured_at=datetime(2024, 8, 2, 18, 0)),
    ]
    clusters = cluster_unmatched_photos(points, [])
    assert len(clusters) == 2
    assert {len(cluster.photo_ids) for cluster in clusters} == {1}


def test_cluster_near_planned_node_gets_linked_item() -> None:
    wgs_lat, wgs_lng = 28.188, 112.976
    gcj_lat, gcj_lng = wgs84_to_gcj02(wgs_lat, wgs_lng)
    node = _node(gcj_lat, gcj_lng, "黄兴路步行街")
    points = [
        GpsPoint(photo_id=uuid4(), latitude=wgs_lat, longitude=wgs_lng, captured_at=datetime(2024, 8, 2, 15, 0)),
        GpsPoint(
            photo_id=uuid4(),
            latitude=wgs_lat + 0.0004,
            longitude=wgs_lng,
            captured_at=datetime(2024, 8, 2, 15, 5),
        ),
    ]
    clusters = cluster_unmatched_photos(points, [node])
    assert len(clusters) == 1
    assert clusters[0].nearest_item_id == node.item_id
    assert clusters[0].nearest_item_name == "黄兴路步行街"
    assert clusters[0].nearest_distance_m is not None
    assert clusters[0].nearest_distance_m < 500


def test_cluster_far_from_plan_is_not_linked() -> None:
    node = _node(27.45, 114.18, "金顶")
    points = [
        GpsPoint(photo_id=uuid4(), latitude=28.188, longitude=112.976, captured_at=datetime(2024, 8, 2, 15, 0)),
    ]
    clusters = cluster_unmatched_photos(points, [node])
    assert len(clusters) == 1
    assert clusters[0].nearest_item_id is None
    assert clusters[0].nearest_distance_m is None or clusters[0].nearest_distance_m > 500


def test_clustering_does_not_mutate_nodes() -> None:
    node = _node(27.45, 114.18)
    original_id = node.item_id
    points = [
        GpsPoint(photo_id=uuid4(), latitude=28.188, longitude=112.976, captured_at=None),
    ]
    cluster_unmatched_photos(points, [node])
    assert node.item_id == original_id
    assert node.poi_name == "计划点"
