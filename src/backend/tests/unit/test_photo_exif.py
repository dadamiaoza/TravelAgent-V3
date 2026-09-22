from datetime import datetime
from io import BytesIO
from pathlib import Path

import piexif
from PIL import Image

from app.services.photo_exif import read_photo_meta


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _jpeg_bytes(*, exif: bytes | None = None) -> bytes:
    image = Image.new("RGB", (32, 24), color=(20, 80, 40))
    buffer = BytesIO()
    if exif:
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_jpeg_without_exif_does_not_invent_captured_at(tmp_path: Path) -> None:
    data = _jpeg_bytes()
    path = tmp_path / "mmexport1712345678901.jpg"
    path.write_bytes(data)
    path.touch()
    meta = read_photo_meta(data)
    assert meta.captured_at is None
    assert meta.latitude is None
    assert meta.longitude is None


def test_datetime_original_and_gps_are_read_from_exif() -> None:
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: ((27, 1), (26, 1), (5460, 100)),
        piexif.GPSIFD.GPSLongitudeRef: "E",
        piexif.GPSIFD.GPSLongitude: ((114, 1), (10, 1), (3540, 100)),
    }
    exif_ifd = {piexif.ExifIFD.DateTimeOriginal: "2024:07:31 09:05:42"}
    data = _jpeg_bytes(exif=piexif.dump({"0th": {}, "Exif": exif_ifd, "GPS": gps_ifd}))
    meta = read_photo_meta(data)
    assert meta.captured_at == datetime(2024, 7, 31, 9, 5, 42)
    assert meta.latitude is not None and abs(meta.latitude - 27.4485) < 0.0002
    assert meta.longitude is not None and abs(meta.longitude - 114.1765) < 0.0002


def test_real_wugongshan_photo_has_exif_time_or_gps() -> None:
    sample = _repo_root() / ".ad" / "武功山-测试照片" / "IMG_20240731_090542.jpg"
    assert sample.exists()
    meta = read_photo_meta(sample.read_bytes())
    assert meta.captured_at is not None or meta.latitude is not None
