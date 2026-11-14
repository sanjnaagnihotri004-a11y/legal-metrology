from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.errors import AppError
from app.models import User
from app.schemas.common import ReportFormat
from app.services import reports, scan_service, storage

router = APIRouter(tags=["reports"])

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv; charset=utf-8",
}


@router.get("/scans/{scan_id}/report")
def download_report(
    scan_id: int,
    fmt: ReportFormat = Query(..., alias="format"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scan = scan_service.get_visible(db, scan_id, user)
    data = scan_service.scan_to_dict(db, scan)

    if fmt == "csv":
        content = reports.build_csv(data)
    else:
        try:
            image = storage.read(scan.image_path)
            annotated = storage.read(scan.annotated_path)
        except (FileNotFoundError, TypeError):
            raise AppError(404, "NOT_FOUND", "Scan images not found")
        evidence_files = {}
        for e in scan.evidence:
            try:
                evidence_files[e.id] = {"data": storage.read(e.file_path),
                                        "content_type": storage.content_type(e.file_path)}
            except FileNotFoundError:
                continue
        builder = reports.build_pdf if fmt == "pdf" else reports.build_docx
        content = builder(data, image, annotated, evidence_files)

    return Response(
        content=content,
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="LM_Report_{scan_id}.{fmt}"'},
    )