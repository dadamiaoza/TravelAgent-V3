"""Score photos against itinerary nodes. No LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from uuid import UUID

from app.services.geo_convert import haversine_m, wgs84_to_gcj02

GPS_WEIGHT = 0.50
TIME_WEIGHT = 0.30
ITINERARY_WEIGHT = 0.20
GPS_ZERO_DISTANCE_M = 2000.0
TIME_PENALTY_PER_HOUR = 0.15
AUTO_THRESHOLD = 0.85
PENDING_THRESHOLD = 0.60


@dataclass(frozen=True)
class ItineraryNode:
    item_id: UUID
    poi_name: str
    day_date: date
    start_time: time | None
    end_time: time | None
    lat: float | None  # GCJ-02
    lng: float | None


@dataclass(frozen=True)
class PhotoMeta:
    latitude: float | None  # WGS-84 EXIF
    longitude: float | None
    captured_at: datetime | None  # naive camera local time


@dataclass(frozen=True)
class CandidateScore:
    item_id: UUID
    poi_name: str
    score: float
    gps_score: float
    time_score: float
    itinerary_score: float
    distance_m: float | None


@dataclass
class MatchResult:
    photo_class: str  # A | B | C
    auto_assign: bool
    item_id: UUID | None
    confidence: float
    assignment_type: str  # gps | time | batch_neighbor
    candidates: list[CandidateScore] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


def classify_photo(photo: PhotoMeta) -> str:
    has_gps = photo.latitude is not None and photo.longitude is not None
    has_time = photo.captured_at is not None
    if has_gps:
        return "A"
    if has_time:
        return "B"
    return "C"


def gps_score(distance_m: float) -> float:
    if distance_m <= 0:
        return 1.0
    if distance_m >= GPS_ZERO_DISTANCE_M:
        return 0.0
    return 1.0 - distance_m / GPS_ZERO_DISTANCE_M


def time_score(captured_at: datetime | None, node: ItineraryNode) -> float:
    if captured_at is None:
        return 0.0
    start = datetime.combine(node.day_date, node.start_time or time(9, 0))
    end = datetime.combine(node.day_date, node.end_time or time(18, 0))
    if start <= captured_at <= end:
        return 1.0
    if captured_at < start:
        delta_h = (start - captured_at).total_seconds() / 3600.0
    else:
        delta_h = (captured_at - end).total_seconds() / 3600.0
    return max(0.0, 1.0 - TIME_PENALTY_PER_HOUR * delta_h)


def itinerary_score(captured_at: datetime | None, node: ItineraryNode) -> float:
    if captured_at is None:
        return 0.0
    return 1.0 if captured_at.date() == node.day_date else 0.0


def _combined(gps: float, time_s: float, itin: float, photo_class: str) -> float:
    if photo_class == "A" and time_s == 0.0 and itin == 0.0:
        return gps
    return GPS_WEIGHT * gps + TIME_WEIGHT * time_s + ITINERARY_WEIGHT * itin


def match_photo(photo: PhotoMeta, nodes: list[ItineraryNode]) -> MatchResult:
    photo_class = classify_photo(photo)
    candidates: list[CandidateScore] = []
    gcj_lat = gcj_lng = None
    if photo.latitude is not None and photo.longitude is not None:
        gcj_lat, gcj_lng = wgs84_to_gcj02(photo.latitude, photo.longitude)

    for node in nodes:
        distance_m: float | None = None
        g_score = 0.0
        if gcj_lat is not None and gcj_lng is not None and node.lat is not None and node.lng is not None:
            distance_m = haversine_m(gcj_lat, gcj_lng, node.lat, node.lng)
            g_score = gps_score(distance_m)
        t_score = time_score(photo.captured_at, node)
        i_score = itinerary_score(photo.captured_at, node)
        score = _combined(g_score, t_score, i_score, photo_class)
        candidates.append(
            CandidateScore(
                item_id=node.item_id,
                poi_name=node.poi_name,
                score=score,
                gps_score=g_score,
                time_score=t_score,
                itinerary_score=i_score,
                distance_m=distance_m,
            )
        )

    candidates.sort(key=lambda item: item.score, reverse=True)
    best = candidates[0] if candidates else None
    confidence = best.score if best else 0.0
    auto = False
    item_id = None
    assignment_type = "time"
    if photo_class == "A" and best is not None:
        assignment_type = "gps"
        if best.score >= AUTO_THRESHOLD:
            auto = True
            item_id = best.item_id
        elif best.score >= PENDING_THRESHOLD:
            item_id = best.item_id
    elif photo_class == "B":
        auto = False
        item_id = None
        assignment_type = "time"
    else:
        auto = False
        item_id = None
        assignment_type = "time"

    evidence = {
        "photo_class": photo_class,
        "candidates": [
            {
                "item_id": str(row.item_id),
                "poi_name": row.poi_name,
                "score": round(row.score, 4),
                "gps_score": round(row.gps_score, 4),
                "time_score": round(row.time_score, 4),
                "itinerary_score": round(row.itinerary_score, 4),
                "distance_m": None if row.distance_m is None else round(row.distance_m, 1),
            }
            for row in candidates[:8]
        ],
    }
    if best and best.distance_m is not None:
        evidence["distance_m"] = round(best.distance_m, 1)

    return MatchResult(
        photo_class=photo_class,
        auto_assign=auto,
        item_id=item_id,
        confidence=round(confidence, 4),
        assignment_type=assignment_type,
        candidates=candidates,
        evidence=evidence,
    )
