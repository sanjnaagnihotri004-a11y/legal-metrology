import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.errors import AppError
from app.models import Evidence, User
from app.schemas.scan import EvidenceOut
from app.services import scan_service, storage

router = APIRouter(tags=["evidence"])

# First bytes of a real JPEG, PNG and PDF file (the browser's claimed type is not trusted)
SIGNATURES = {b"\xff\xd8": "jpg", b"\x89PNG": "png", b"%PDF": "pdf"}


def _sniff(data: bytes) -> str | None:
    for signature, ext in SIGNATURES.items():
        if data.startswith(signature):
            return ext
    return None


@router.post("/scans/{scan_id}/evidence", response_model=EvidenceOut, status_code=201)
def add_evidence(
    scan_id: int,
    file: UploadFile = File(...),
    note: str | None = Form(None, max_length=300),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scan = scan_service.get_visible(db, scan_id, user)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AppError(413, "FILE_TOO_LARGE", f"File must be under {settings.max_upload_mb} MB")
    ext = _sniff(data)
    if ext is None:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", "Only JPG, PNG and PDF files are accepted")

    path = storage.save("evidence", f"{uuid.uuid4().hex}.{ext}", data)
    evidence = Evidence(scan_id=scan.id, file_path=path,
                        note=(note or "").strip() or None, uploaded_by=user.id)
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return scan_service.evidence_dict(db, evidence)


@router.get("/evidence/{evidence_id}/file")
def get_evidence_file(evidence_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    evidence = db.get(Evidence, evidence_id)
    if evidence is None:
        raise AppError(404, "NOT_FOUND", "Evidence not found")
    scan_service.get_visible(db, evidence.scan_id, user)   # 404 if this user may not see the scan
    try:
        data = storage.read(evidence.file_path)
    except FileNotFoundError:
        raise AppError(404, "NOT_FOUND", "Evidence file not found")
    return Response(content=data, media_type=storage.content_type(evidence.file_path))