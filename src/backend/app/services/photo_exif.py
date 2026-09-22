"""Read GPS and DateTimeOriginal from EXIF only. Never use filesystem mtime."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

import piexif
from PIL import Image

from app.services.photo_match import PhotoMeta


def _ratio_to_float(value) -> float:
    if isinstance(value, tuple) and len(value) == 2 and value[1]:
        return value[0] / value[1]
    return float(value)


def _dms_to_deg(dms, ref: bytes | str) -> float:
    deg = _ratio_to_float(dms[0])
    minutes = _ratio_to_float(dms[1])
    seconds = _ratio_to_float(dms[2])
    sign_raw = ref.decode() if isinstance(ref, bytes) else ref
    sign = -1 if sign_raw in {"S", "W"} else 1
    return sign * (deg + minutes / 60.0 + seconds / 3600.0)


def read_photo_meta(data: bytes) -> PhotoMeta:
    """Parse EXIF. Missing GPS/time stays None — do not backfill created_at."""
    latitude = None
    longitude = None
    captured_at = None
    try:
        exif = piexif.load(data)
    except Exception:
        return PhotoMeta(latitude=None, longitude=None, captured_at=None)

    gps = exif.get("GPS") or {}
    try:
        if piexif.GPSIFD.GPSLatitude in gps and piexif.GPSIFD.GPSLongitude in gps:
            latitude = _dms_to_deg(
                gps[piexif.GPSIFD.GPSLatitude],
                gps.get(piexif.GPSIFD.GPSLatitudeRef, b"N"),
            )
            longitude = _dms_to_deg(
                gps[piexif.GPSIFD.GPSLongitude],
                gps.get(piexif.GPSIFD.GPSLongitudeRef, b"E"),
            )
    except Exception:
        latitude = None
        longitude = None

    zeroth = exif.get("Exif") or {}
    raw = zeroth.get(piexif.ExifIFD.DateTimeOriginal) or (exif.get("0th") or {}).get(
        piexif.ImageIFD.DateTime
    )
    if raw:
        try:
            text = raw.decode() if isinstance(raw, bytes) else str(raw)
            captured_at = datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
        except Exception:
            captured_at = None

    return PhotoMeta(latitude=latitude, longitude=longitude, captured_at=captured_at)


def image_size(data: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(BytesIO(data)) as image:
            return image.size
    except Exception:
        return None, None
