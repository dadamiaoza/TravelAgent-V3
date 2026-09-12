"""Local disk storage for original / preview / thumbnail. One original per photo id."""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from uuid import UUID

from PIL import Image

from app.core.config import settings

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
REJECTED_CONTENT_TYPES = {"image/heic", "image/heif", "image/heic-sequence"}
MAX_BYTES = 12 * 1024 * 1024
MAX_FILES = 50
PREVIEW_MAX = 1600
THUMB_MAX = 240


def upload_reject_detail(content_type: str, filename: str) -> tuple[int, str] | None:
    """Return (status, message) if the file is not accepted."""
    ctype = (content_type or "").lower()
    lower = filename.lower()
    if ctype in REJECTED_CONTENT_TYPES or lower.endswith((".heic", ".heif")):
        return 415, "暂不支持 HEIC，请先转为 JPEG"
    if ctype and ctype not in ALLOWED_CONTENT_TYPES and not lower.endswith(
        (".jpg", ".jpeg", ".png", ".webp")
    ):
        return 415, "仅支持 JPEG / PNG / WebP"
    return None


def upload_root() -> Path:
    root = Path(settings.photo_upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def suffix_for(content_type: str, filename: str) -> str:
    if content_type in ALLOWED_CONTENT_TYPES:
        return ALLOWED_CONTENT_TYPES[content_type]
    lower = filename.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if lower.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def photo_dir(trip_id: UUID, photo_id: UUID) -> Path:
    path = upload_root() / str(trip_id) / str(photo_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_original(trip_id: UUID, photo_id: UUID, data: bytes, suffix: str) -> str:
    dest = photo_dir(trip_id, photo_id) / f"original{suffix}"
    dest.write_bytes(data)
    return str(dest.relative_to(upload_root())).replace("\\", "/")


def _resize_save(data: bytes, dest: Path, max_edge: int, quality: int) -> None:
    with Image.open(BytesIO(data)) as image:
        image = image.convert("RGB")
        image.thumbnail((max_edge, max_edge))
        dest.parent.mkdir(parents=True, exist_ok=True)
        image.save(dest, format="WEBP", quality=quality)


def save_derivatives(trip_id: UUID, photo_id: UUID, data: bytes) -> tuple[str, str]:
    folder = photo_dir(trip_id, photo_id)
    preview = folder / "preview.webp"
    thumb = folder / "thumbnail.webp"
    _resize_save(data, preview, PREVIEW_MAX, 82)
    _resize_save(data, thumb, THUMB_MAX, 70)
    root = upload_root()
    return (
        str(preview.relative_to(root)).replace("\\", "/"),
        str(thumb.relative_to(root)).replace("\\", "/"),
    )


def resolve_stored(relative: str) -> Path:
    candidate = (upload_root() / relative).resolve()
    root = upload_root().resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("invalid photo path")
    return candidate


def delete_photo_dir(trip_id: UUID, photo_id: UUID) -> None:
    folder = upload_root() / str(trip_id) / str(photo_id)
    if not folder.exists():
        return
    for child in folder.glob("*"):
        child.unlink(missing_ok=True)
    folder.rmdir()
