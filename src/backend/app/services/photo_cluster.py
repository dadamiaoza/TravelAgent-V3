"""Cluster unmatched GPS photos into suggested visit stops. No LLM."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.services.geo_convert import haversine_m, wgs84_to_gcj02
from app.services.photo_match import ItineraryNode

CLUSTER_RADIUS_M = 500.0
LINK_ITEM_RADIUS_M = 500.0


@dataclass(frozen=True)
class GpsPoint:
    photo_id: UUID
    latitude: float  # WGS-84 EXIF
    longitude: float
    captured_at: datetime | None


@dataclass
class PhotoCluster:
    lat: float  # GCJ-02 centroid
    lng: float
    photo_ids: list[UUID]
    time_start: datetime | None
    time_end: datetime | None
    nearest_item_id: UUID | None
    nearest_item_name: str | None
    nearest_distance_m: float | None


def _centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    lat = sum(point[0] for point in points) / len(points)
    lng = sum(point[1] for point in points) / len(points)
    return lat, lng


def _link_nearest_node(lat: float, lng: float, nodes: list[ItineraryNode]) -> tuple[UUID | None, str | None, float | None]:
    best_id = None
    best_name = None
    best_distance: float | None = None
    for node in nodes:
        if node.lat is None or node.lng is None:
            continue
        distance = haversine_m(lat, lng, node.lat, node.lng)
        if distance > LINK_ITEM_RADIUS_M:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_id = node.item_id
            best_name = node.poi_name
    return best_id, best_name, None if best_distance is None else round(best_distance, 1)


def cluster_unmatched_photos(
    points: list[GpsPoint],
    nodes: list[ItineraryNode],
    *,
    cluster_radius_m: float = CLUSTER_RADIUS_M,
) -> list[PhotoCluster]:
    """Greedy spatial clusters. Does not modify itinerary nodes."""
    prepared: list[tuple[GpsPoint, float, float]] = []
    for point in points:
        gcj_lat, gcj_lng = wgs84_to_gcj02(point.latitude, point.longitude)
        prepared.append((point, gcj_lat, gcj_lng))
    prepared.sort(key=lambda row: (row[0].captured_at is None, row[0].captured_at or datetime.min))

    groups: list[list[tuple[GpsPoint, float, float]]] = []
    for row in prepared:
        _, lat, lng = row
        assigned = False
        for group in groups:
            center_lat, center_lng = _centroid([(item[1], item[2]) for item in group])
            if haversine_m(lat, lng, center_lat, center_lng) <= cluster_radius_m:
                group.append(row)
                assigned = True
                break
        if not assigned:
            groups.append([row])

    clusters: list[PhotoCluster] = []
    for group in groups:
        center_lat, center_lng = _centroid([(item[1], item[2]) for item in group])
        times = [item[0].captured_at for item in group if item[0].captured_at is not None]
        linked_id, linked_name, linked_distance = _link_nearest_node(center_lat, center_lng, nodes)
        clusters.append(
            PhotoCluster(
                lat=round(center_lat, 6),
                lng=round(center_lng, 6),
                photo_ids=[item[0].photo_id for item in group],
                time_start=min(times) if times else None,
                time_end=max(times) if times else None,
                nearest_item_id=linked_id,
                nearest_item_name=linked_name,
                nearest_distance_m=linked_distance,
            )
        )
    return clusters
