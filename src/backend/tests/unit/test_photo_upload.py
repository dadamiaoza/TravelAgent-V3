from uuid import uuid4

from fastapi import HTTPException

from app.api.v1.photos import _form_item_id
from app.services.photo_storage import sha256_hex, upload_reject_detail


def test_heic_is_rejected() -> None:
    assert upload_reject_detail("image/heic", "IMG_0001.HEIC") == (
        415,
        "暂不支持 HEIC，请先转为 JPEG",
    )
    assert upload_reject_detail("image/jpeg", "photo.heif")[0] == 415


def test_jpeg_png_webp_are_accepted() -> None:
    assert upload_reject_detail("image/jpeg", "a.jpg") is None
    assert upload_reject_detail("image/png", "a.png") is None
    assert upload_reject_detail("image/webp", "a.webp") is None
    assert upload_reject_detail("", "a.jpeg") is None


def test_same_bytes_share_hash() -> None:
    assert sha256_hex(b"abc") == sha256_hex(b"abc")
    assert sha256_hex(b"abc") != sha256_hex(b"abd")


def test_empty_form_item_id_is_omitted() -> None:
    assert _form_item_id({"item_id": ""}, None) is None
    assert _form_item_id({"item_id": "  "}, None) is None


def test_invalid_form_item_id_is_400() -> None:
    try:
        _form_item_id({"item_id": "not-a-uuid"}, None)
    except HTTPException as exc:
        assert exc.status_code == 400
        return
    raise AssertionError("expected HTTPException")


def test_form_item_id_prefers_query_fallback() -> None:
    item_id = uuid4()
    assert _form_item_id({"item_id": ""}, item_id) == item_id
