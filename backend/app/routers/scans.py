
import io
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from PIL import Image

from app.config import settings
from app.deps import get_current_user
from app.errors import AppError
from app.mock_data import store
from app.models import User
from app.schemas.common import Category, ScanStatus
from app.schemas.scan import RecheckRequest, Scan, ScanListResponse

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("", response_model=Scan, status_code=201)
def create_scan(
    image: UploadFile = File(...),
    product_name: str = Form(..., min_length=1, max_length=120),
    brand: str = Form(..., min_length=1, max_length=80),
    category: Category = Form(...),
    label_width_mm: float = Form(..., gt=0, le=1000),
    barcode: str | None = Form(None),
    notes: str | None = Form(None, max_length=500),
    user: User = Depends(get_current_user),
):
    barcode = (barcode or "").strip() or None
    if barcode and not (barcode.isdigit() and 8 <= len(barcode) <= 14):
        raise AppError(422, "VALIDATION_ERROR", "Some inputs are invalid",
                       {"barcode": "must be 8 to 14 digits"})

    if image.content_type not in ("image/jpeg", "image/png"):
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", "Only JPG and PNG images are accepted")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = image.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AppError(413, "FILE_TOO_LARGE", f"Image must be under {settings.max_upload_mb} MB")

    try:
        pic = Image.open(io.BytesIO(data))
        width, height = pic.size
        fmt = pic.format
    except Exception:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", "File is not a valid image")
    if fmt not in ("JPEG", "PNG"):
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", "Only JPG and PNG images are accepted")

    # Test trigger for the frontend developer
    if product_name.strip().lower() == "error_ocr":
        raise AppError(422, "OCR_NO_TEXT",
                       "No readable text found. Retake the photo: flat, well lit and in focus.")

    return store.add_scan(
        product_name=product_name.strip(), brand=brand.strip(), category=category,
        user_id=user.id, user_name=user.name, scenario=next(store.ROTATION),
        label_width_mm=label_width_mm, barcode=barcode, notes=notes,
        image=data, image_type="image/jpeg" if fmt == "JPEG" else "image/png",
        width=width, height=height,
    )


@router.get("", response_model=ScanListResponse)
def list_scans(
    q: str | None = None,
    status: ScanStatus | None = None,
    brand: str | None = None,
    category: Category | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    rule_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    matches = []
    for scan in store.visible_scans(user):
        p = scan["product"]
        if q and q.lower() not in f'{p["name"]} {p["brand"]} {p["barcode"] or ""}'.lower():
            continue
        if status and scan["status"] != status:
            continue
        if brand and brand.lower() not in p["brand"].lower():
            continue
        if category and p["category"] != category:
            continue
        day = scan["created_at"].date()
        if date_from and day < date_from:
            continue
        if date_to and day > date_to:
            continue
        if rule_id and not any(r["rule_id"] == rule_id and r["status"] == "fail"
                               for r in scan["rule_results"]):
            continue
        matches.append(scan)

    start = (page - 1) * page_size
    return {
        "items": [store.summary(s) for s in matches[start:start + page_size]],
        "total": len(matches),
        "page": page,
        "page_size": page_size,
    }


@router.get("/{scan_id}", response_model=Scan)
def get_scan(scan_id: int, user: User = Depends(get_current_user)):
    return store.get_entry(scan_id, user)["scan"]


@router.get("/{scan_id}/image")
def get_image(scan_id: int, user: User = Depends(get_current_user)):
    entry = store.get_entry(scan_id, user)
    if entry["image"]:
        return Response(content=entry["image"], media_type=entry["image_type"])
    return Response(content=store.SAMPLE_IMAGE.read_bytes(), media_type="image/jpeg")


@router.get("/{scan_id}/annotated-image")
def get_annotated_image(scan_id: int, user: User = Depends(get_current_user)):
    store.get_entry(scan_id, user)
    return Response(content=store.SAMPLE_ANNOTATED.read_bytes(), media_type="image/jpeg")


@router.post("/{scan_id}/recheck", response_model=Scan)
def recheck(scan_id: int, body: RecheckRequest, user: User = Depends(get_current_user)):
    entry = store.get_entry(scan_id, user)
    if not body.corrections:
        raise AppError(422, "VALIDATION_ERROR", "No corrections provided",
                       {"corrections": "must contain at least one field"})
    bad = [key for key in body.corrections if key not in store.FIELD_TO_RULE]
    if bad:
        raise AppError(422, "VALIDATION_ERROR", "Unknown field in corrections",
                       {key: "not a correctable field" for key in bad})
    store.apply_corrections(entry["scan"], body.corrections)
    return entry["scan"]