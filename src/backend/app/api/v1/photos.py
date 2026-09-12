"""Photo archive HTTP API. Nested under trips; no LLM."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.photo import PhotoAsset, PhotoAssignment, PhotoJob
from app.models.trip import ItineraryDay, ItineraryItem, Trip
from app.schemas.photo import (
    AssignmentPatch,
    BatchAssignRequest,
    PhotoAssetOut,
    PhotoAssignmentOut,
    PhotoCandidateOut,
    PhotoJobOut,
    PhotoMapSummaryItemOut,
    PhotoUploadItemOut,
    PhotoUploadOut,
)
from app.services.photo_storage import (
    MAX_BYTES,
    MAX_FILES,
    delete_photo_dir,
    resolve_stored,
    save_original,
    sha256_hex,
    suffix_for,
    upload_reject_detail,
)


def _item_on_trip(db: Session, trip_id: UUID, item_id: UUID) -> ItineraryItem:
    item = (
        db.query(ItineraryItem)
        .join(ItineraryDay)
        .filter(ItineraryItem.id == item_id, ItineraryDay.trip_id == trip_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="行程节点不存在")
    return item


router = APIRouter(prefix="/trips", tags=["photos"])


def _get_trip(db: Session, trip_id: UUID) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


def _file_url(trip_id: UUID, photo_id: UUID, variant: str) -> str:
    return f"/api/v1/trips/{trip_id}/photos/{photo_id}/file?variant={variant}"


def _primary(photo: PhotoAsset) -> PhotoAssignment | None:
    for row in photo.assignments:
        if row.is_primary:
            return row
    return photo.assignments[0] if photo.assignments else None


def _to_out(photo: PhotoAsset) -> PhotoAssetOut:
    assignment = _primary(photo)
    candidates: list[PhotoCandidateOut] = []
    evidence = (assignment.evidence_json if assignment else None) or {}
    for row in evidence.get("candidates") or []:
        try:
            candidates.append(
                PhotoCandidateOut(
                    item_id=UUID(str(row["item_id"])),
                    poi_name=row.get("poi_name"),
                    score=row.get("score"),
                )
            )
        except Exception:
            continue
    assignment_out = None
    if assignment:
        assignment_out = PhotoAssignmentOut(
            item_id=assignment.item_id,
            assignment_type=assignment.assignment_type,
            confidence=assignment.confidence,
            is_confirmed=assignment.is_confirmed,
            evidence=assignment.evidence_json,
        )
    return PhotoAssetOut(
        id=photo.id,
        trip_id=photo.trip_id,
        original_filename=photo.original_filename,
        captured_at=photo.captured_at,
        latitude=photo.latitude,
        longitude=photo.longitude,
        width=photo.width,
        height=photo.height,
        status=photo.status,
        error=photo.error,
        thumbnail_url=_file_url(photo.trip_id, photo.id, "thumbnail") if photo.thumbnail_path else None,
        preview_url=_file_url(photo.trip_id, photo.id, "preview") if photo.preview_path else None,
        assignment=assignment_out,
        candidates=candidates,
        created_at=photo.created_at,
    )


def _form_files(form) -> list[UploadFile]:
    collected: list[UploadFile] = []
    for key in ("files", "file", "files[]"):
        for part in form.getlist(key):
            if isinstance(part, UploadFile) and part not in collected:
                collected.append(part)
    return collected


def _form_item_id(form, fallback: UUID | None) -> UUID | None:
    if fallback is not None:
        return fallback
    raw = form.get("item_id")
    if raw is None or isinstance(raw, UploadFile):
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return UUID(text)
    except ValueError:
        raise HTTPException(status_code=400, detail="item_id 不是有效的节点 ID") from None


@router.post("/{trip_id}/photos", response_model=PhotoUploadOut, status_code=202)
async def upload_photos(
    trip_id: UUID,
    request: Request,
    item_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    _get_trip(db, trip_id)
    form = await request.form(max_part_size=MAX_BYTES)
    files = _form_files(form)
    item_id = _form_item_id(form, item_id)
    if not files:
        raise HTTPException(status_code=400, detail="请选择照片")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=413, detail=f"一次最多上传 {MAX_FILES} 张")
    if item_id is not None:
        _item_on_trip(db, trip_id, item_id)

    created: list[PhotoUploadItemOut] = []
    photo_ids: list[str] = []
    for upload in files:
        content_type = (upload.content_type or "").lower()
        filename = upload.filename or "photo.jpg"
        rejected = upload_reject_detail(content_type, filename)
        if rejected is not None:
            status, detail = rejected
            raise HTTPException(status_code=status, detail=detail)
        data = await upload.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="单张照片不能超过 12MB")
        digest = sha256_hex(data)
        existing = (
            db.query(PhotoAsset)
            .filter(PhotoAsset.trip_id == trip_id, PhotoAsset.file_hash == digest)
            .one_or_none()
        )
        if existing is not None:
            created.append(
                PhotoUploadItemOut(
                    id=existing.id,
                    original_filename=existing.original_filename,
                    duplicate=True,
                )
            )
            if str(existing.id) not in photo_ids:
                photo_ids.append(str(existing.id))
            continue
        photo_id = uuid4()
        suffix = suffix_for(content_type, filename)
        relative = save_original(trip_id, photo_id, data, suffix)
        asset = PhotoAsset(
            id=photo_id,
            trip_id=trip_id,
            file_path=relative,
            original_filename=filename,
            file_hash=digest,
            status="pending",
        )
        db.add(asset)
        created.append(
            PhotoUploadItemOut(id=photo_id, original_filename=filename, duplicate=False)
        )
        photo_ids.append(str(photo_id))

    job = PhotoJob(
        trip_id=trip_id,
        status="pending",
        progress=0,
        payload={"photo_ids": photo_ids, "target_item_id": str(item_id) if item_id else None},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return PhotoUploadOut(job_id=job.id, photos=created)


@router.get("/{trip_id}/photo-jobs/{job_id}", response_model=PhotoJobOut)
def get_photo_job(trip_id: UUID, job_id: UUID, db: Session = Depends(get_db)):
    _get_trip(db, trip_id)
    job = db.get(PhotoJob, job_id)
    if job is None or job.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.get("/{trip_id}/photos", response_model=list[PhotoAssetOut])
def list_photos(
    trip_id: UUID,
    item_id: UUID | None = None,
    review: str | None = None,
    db: Session = Depends(get_db),
):
    _get_trip(db, trip_id)
    photos = (
        db.query(PhotoAsset)
        .options(joinedload(PhotoAsset.assignments))
        .filter(PhotoAsset.trip_id == trip_id)
        .order_by(PhotoAsset.created_at.desc())
        .all()
    )
    results = [_to_out(photo) for photo in photos]
    if item_id is not None:
        results = [
            row
            for row in results
            if row.assignment and row.assignment.item_id == item_id
        ]
    if review == "pending":
        results = [
            row
            for row in results
            if row.assignment is None
            or (
                not row.assignment.is_confirmed
                and (
                    row.assignment.item_id is None
                    or (row.assignment.confidence or 0) < 0.85
                )
            )
        ]
    return results


@router.get("/{trip_id}/photos/map-summary", response_model=list[PhotoMapSummaryItemOut])
def map_summary(trip_id: UUID, db: Session = Depends(get_db)):
    _get_trip(db, trip_id)
    photos = (
        db.query(PhotoAsset)
        .options(joinedload(PhotoAsset.assignments))
        .filter(PhotoAsset.trip_id == trip_id)
        .all()
    )
    grouped: dict[UUID, list[PhotoAsset]] = {}
    for photo in photos:
        assignment = _primary(photo)
        if assignment is None or assignment.item_id is None:
            continue
        grouped.setdefault(assignment.item_id, []).append(photo)
    out: list[PhotoMapSummaryItemOut] = []
    for item_id, group in grouped.items():
        thumb = next((p for p in group if p.thumbnail_path), group[0])
        out.append(
            PhotoMapSummaryItemOut(
                item_id=item_id,
                count=len(group),
                thumbnail_photo_id=thumb.id,
            )
        )
    return out


@router.get("/{trip_id}/photos/{photo_id}/file")
def get_photo_file(
    trip_id: UUID,
    photo_id: UUID,
    variant: str = "preview",
    db: Session = Depends(get_db),
):
    _get_trip(db, trip_id)
    photo = db.get(PhotoAsset, photo_id)
    if photo is None or photo.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="照片不存在")
    relative = {
        "original": photo.file_path,
        "preview": photo.preview_path or photo.file_path,
        "thumbnail": photo.thumbnail_path or photo.preview_path or photo.file_path,
    }.get(variant)
    if not relative:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = resolve_stored(relative)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    media = {
        ".webp": "image/webp",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(path.suffix.lower(), "image/jpeg")
    return FileResponse(path, media_type=media)


@router.patch("/{trip_id}/photos/{photo_id}/assignment", response_model=PhotoAssetOut)
def patch_assignment(
    trip_id: UUID,
    photo_id: UUID,
    body: AssignmentPatch,
    db: Session = Depends(get_db),
):
    _get_trip(db, trip_id)
    photo = db.get(PhotoAsset, photo_id)
    if photo is None or photo.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="照片不存在")
    assignment = _primary(photo)
    if assignment is None:
        assignment = PhotoAssignment(
            photo_id=photo.id,
            assignment_type="manual",
            confidence=1.0,
            is_primary=True,
        )
        db.add(assignment)
        db.flush()
    if body.action == "unassign":
        assignment.item_id = None
        assignment.is_confirmed = False
        assignment.assignment_type = "manual"
        assignment.confidence = 0
    elif body.action in {"confirm", "reassign"}:
        item_id = body.item_id if body.action == "reassign" else body.item_id or assignment.item_id
        if item_id is None:
            raise HTTPException(status_code=400, detail="请选择地点")
        _item_on_trip(db, trip_id, item_id)
        assignment.item_id = item_id
        assignment.assignment_type = "manual"
        assignment.confidence = 1.0
        assignment.is_confirmed = True
    else:
        raise HTTPException(status_code=400, detail="未知操作")
    db.commit()
    photo = (
        db.query(PhotoAsset)
        .options(joinedload(PhotoAsset.assignments))
        .filter(PhotoAsset.id == photo_id)
        .one()
    )
    return _to_out(photo)


@router.post("/{trip_id}/photos/batch-assign", response_model=list[PhotoAssetOut])
def batch_assign(
    trip_id: UUID,
    body: BatchAssignRequest,
    db: Session = Depends(get_db),
):
    _get_trip(db, trip_id)
    _item_on_trip(db, trip_id, body.item_id)
    assigned_ids: list[UUID] = []
    for photo_id in body.photo_ids:
        photo = db.get(PhotoAsset, photo_id)
        if photo is None or photo.trip_id != trip_id:
            continue
        assignment = _primary(photo)
        if assignment is None:
            assignment = PhotoAssignment(photo_id=photo.id, is_primary=True)
            db.add(assignment)
        assignment.item_id = body.item_id
        assignment.assignment_type = "manual"
        assignment.confidence = 1.0
        assignment.is_confirmed = True
        assigned_ids.append(photo.id)
    db.commit()
    if not assigned_ids:
        return []
    photos = (
        db.query(PhotoAsset)
        .options(joinedload(PhotoAsset.assignments))
        .filter(PhotoAsset.id.in_(assigned_ids))
        .all()
    )
    by_id = {photo.id: photo for photo in photos}
    return [_to_out(by_id[photo_id]) for photo_id in assigned_ids if photo_id in by_id]


@router.delete("/{trip_id}/photos/{photo_id}", status_code=204)
def delete_photo(trip_id: UUID, photo_id: UUID, db: Session = Depends(get_db)):
    _get_trip(db, trip_id)
    photo = db.get(PhotoAsset, photo_id)
    if photo is None or photo.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="照片不存在")
    delete_photo_dir(trip_id, photo_id)
    db.delete(photo)
    db.commit()
    return None
