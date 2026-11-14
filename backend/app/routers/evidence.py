
import itertools
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.config import settings
from app.deps import get_current_user
from app.errors import AppError
from app.mock_data import store
from app.models import User
from app.schemas.scan import EvidenceOut

router = APIRouter(tags=["evidence"])

FILES: dict[int, dict] = {}  # in-memory, cleared on restart
_ids = itertools.count(1)

# First bytes of a real JPEG, PNG and PDF file
SIGNATURES = {b"\xff\xd8": "image/jpeg", b"\x89PNG": "image/png", b"%PDF": "application/pdf"}


def _sniff(data: bytes) -> str | None:
    for signature, content_type in SIGNATURES.items():
        if data.startswith(signature):
            return content_type
    return None


@router.post("/scans/{scan_id}/evidence", response_model=EvidenceOut, status_code=201)
def add_evidence(
    scan_id: int,
    file: UploadFile = File(...),
    note: str | None = Form(None, max_length=300),
    user: User = Depends(get_current_user),
):
    entry = store.get_entry(scan_id, user)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AppError(413, "FILE_TOO_LARGE", f"File must be under {settings.max_upload_mb} MB")

    content_type = _sniff(data)
    if content_type is None:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", "Only JPG, PNG and PDF files are accepted")

    evidence_id = next(_ids)
    evidence = {
        "id": evidence_id,
        "scan_id": scan_id,
        "file_url": f"/evidence/{evidence_id}/file",
        "note": (note or "").strip() or None,
        "uploaded_by": user.name,
        "created_at": datetime.now(timezone.utc),
    }
    FILES[evidence_id] = {"scan_id": scan_id, "data": data, "content_type": content_type}
    entry["scan"]["evidence"].append(evidence)
    return evidence


@router.get("/evidence/{evidence_id}/file")
def get_evidence_file(evidence_id: int, user: User = Depends(get_current_user)):
    item = FILES.get(evidence_id)
    if item is None:
        raise AppError(404, "NOT_FOUND", "Evidence not found")
    store.get_entry(item["scan_id"], user)  # 404 if this user may not see the scan
    return Response(content=item["data"], media_type=item["content_type"])