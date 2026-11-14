from fastapi import APIRouter, Depends, Query, Response

from app.deps import get_current_user
from app.mock_data import store
from app.models import User
from app.routers.evidence import FILES
from app.schemas.common import ReportFormat
from app.services import reports

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
    user: User = Depends(get_current_user),
):
    entry = store.get_entry(scan_id, user)
    scan = entry["scan"]
    image = entry["image"] or store.SAMPLE_IMAGE.read_bytes()
    annotated = store.SAMPLE_ANNOTATED.read_bytes()
    evidence_files = {e["id"]: FILES[e["id"]] for e in scan["evidence"] if e["id"] in FILES}

    if fmt == "pdf":
        content = reports.build_pdf(scan, image, annotated, evidence_files)
    elif fmt == "docx":
        content = reports.build_docx(scan, image, annotated, evidence_files)
    else:
        content = reports.build_csv(scan)

    return Response(
        content=content,
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="LM_Report_{scan_id}.{fmt}"'},
    )