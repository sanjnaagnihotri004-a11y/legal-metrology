import csv
import io
from datetime import timedelta, timezone
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Inches
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

IST = timezone(timedelta(hours=5, minutes=30))
DISCLAIMER = "Automated screening result. Findings must be verified by an authorised officer."
STATUS_LABEL = {"compliant": "Compliant", "non_compliant": "Non-compliant", "needs_review": "Needs review"}
RULE_LABEL = {"pass": "PASS", "fail": "FAIL", "not_checked": "NOT CHECKED"}
FIELD_LABEL = {
    "manufacturer_name_address": "Manufacturer / packer / importer",
    "net_quantity": "Net quantity",
    "mrp": "MRP",
    "mfg_date": "Month/year of manufacture or packing",
    "consumer_care": "Consumer care details",
}


def _when(dt) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def _info_rows(scan):
    p = scan["product"]
    return [
        ("Scan ID", scan["id"]),
        ("Product", p["name"]),
        ("Brand", p["brand"]),
        ("Category", p["category"]),
        ("Barcode", p["barcode"] or "-"),
        ("Inspector", scan["inspector"]["name"]),
        ("Scanned at", _when(scan["created_at"])),
        ("Label width (mm)", scan["label_width_mm"]),
        ("Corrected manually", "Yes" if scan["corrected"] else "No"),
        ("Notes", scan["notes"] or "-"),
    ]


def _field_rows(scan):
    rows = []
    for key, label in FIELD_LABEL.items():
        f = scan["extracted_fields"][key]
        value = f["value"] if f["found"] else "Not found"
        conf = f"{round(f['confidence'] * 100)}%" if f["confidence"] is not None else "-"
        rows.append((label, value, conf))
    nq = scan["extracted_fields"]["net_quantity"]
    if nq.get("font_height_mm") is not None:
        text = f"{nq['font_height_mm']} mm"
        if nq.get("min_font_height_mm") is not None:
            text += f" (minimum {nq['min_font_height_mm']} mm)"
        rows.append(("Net quantity font height", text, "-"))
    return rows


def _rule_rows(scan):
    return [
        (r["rule_id"], r["title"], r["clause"], r["severity"], RULE_LABEL[r["status"]], r["message"])
        for r in scan["rule_results"]
    ]


# ---------------- PDF ----------------

def _img(data: bytes, width_mm: float, max_height_mm: float = 120) -> Image:
    with PILImage.open(io.BytesIO(data)) as im:
        w, h = im.size
    width = width_mm * mm
    height = width * h / w
    max_height = max_height_mm * mm
    if height > max_height:
        height = max_height
        width = height * w / h
    return Image(io.BytesIO(data), width=width, height=height)


def build_pdf(scan: dict, image: bytes, annotated: bytes, evidence_files: dict | None = None) -> bytes:
    evidence_files = evidence_files or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm, title=f"Compliance Report {scan['id']}",
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8.5, leading=10.5)

    def p(text, style=small):
        return Paragraph(escape(str(text)), style)

    def table(rows, widths, header=None, fail_rows=()):
        data = []
        if header:
            data.append([p(h, styles["BodyText"]) for h in header])
        data += [[p(c) for c in row] for row in rows]
        t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")))
        offset = 1 if header else 0
        for i in fail_rows:
            style.append(("BACKGROUND", (0, i + offset), (-1, i + offset), colors.HexColor("#fde2e2")))
        t.setStyle(TableStyle(style))
        return t

    rules = _rule_rows(scan)
    fails = [i for i, r in enumerate(rules) if r[4] == "FAIL"]

    story = [
        p("Legal Metrology Compliance Report", styles["Title"]),
        p(f"Overall status: {STATUS_LABEL[scan['status']]}   |   Score: {scan['score']}%   |   "
          f"Violations: {scan['violations_count']}", styles["BodyText"]),
        Spacer(1, 4 * mm),
        p("Product and inspection details", styles["Heading2"]),
        table(_info_rows(scan), [50, 130]),
        Spacer(1, 4 * mm),
        p("Rule-by-rule result", styles["Heading2"]),
        table(rules, [16, 40, 26, 18, 20, 60],
              header=["Rule", "Check", "Clause", "Severity", "Result", "Message"], fail_rows=fails),
        Spacer(1, 4 * mm),
        p("Extracted declarations", styles["Heading2"]),
        table(_field_rows(scan), [55, 95, 30], header=["Field", "Value", "Confidence"]),
        Spacer(1, 4 * mm),
        p("Images", styles["Heading2"]),
        Table([[_img(image, 85), _img(annotated, 85)],
               [p("Original image"), p("Annotated image")]], colWidths=[90 * mm, 90 * mm]),
        Spacer(1, 4 * mm),
        p("Evidence", styles["Heading2"]),
    ]

    if scan["evidence"]:
        for e in scan["evidence"]:
            story.append(p(f"#{e['id']}: {e['note'] or 'No note'} "
                           f"(by {e['uploaded_by']}, {_when(e['created_at'])})"))
            attached = evidence_files.get(e["id"])
            if attached and attached["content_type"].startswith("image/"):
                story.append(Spacer(1, 2 * mm))
                story.append(_img(attached["data"], 80))
            elif attached:
                story.append(p("(PDF attachment, not shown in this report)"))
            story.append(Spacer(1, 3 * mm))
    else:
        story.append(p("No extra evidence attached."))
    doc.build(story)
    return buf.getvalue()


# ---------------- DOCX ----------------

def _docx_table(doc, header, rows):
    cols = len(header) if header else len(rows[0])
    t = doc.add_table(rows=0, cols=cols)
    t.style = "Table Grid"
    if header:
        cells = t.add_row().cells
        for cell, text in zip(cells, header):
            cell.text = text
            for run in cell.paragraphs[0].runs:
                run.bold = True
    for row in rows:
        for cell, text in zip(t.add_row().cells, row):
            cell.text = str(text)


def build_docx(scan: dict, image: bytes, annotated: bytes, evidence_files: dict | None = None) -> bytes:
    evidence_files = evidence_files or {}
    doc = Document()
    doc.add_heading("Legal Metrology Compliance Report", level=0)
    doc.add_paragraph(f"Overall status: {STATUS_LABEL[scan['status']]}   |   Score: {scan['score']}%   |   "
                      f"Violations: {scan['violations_count']}")
    doc.add_heading("Product and inspection details", level=1)
    _docx_table(doc, None, _info_rows(scan))
    doc.add_heading("Rule-by-rule result", level=1)
    _docx_table(doc, ["Rule", "Check", "Clause", "Severity", "Result", "Message"], _rule_rows(scan))
    doc.add_heading("Extracted declarations", level=1)
    _docx_table(doc, ["Field", "Value", "Confidence"], _field_rows(scan))
    doc.add_heading("Images", level=1)
    doc.add_paragraph("Original image")
    doc.add_picture(io.BytesIO(image), width=Inches(3.5))
    doc.add_paragraph("Annotated image")
    doc.add_picture(io.BytesIO(annotated), width=Inches(3.5))
    doc.add_heading("Evidence", level=1)
    if scan["evidence"]:
        for e in scan["evidence"]:
            doc.add_paragraph(
                f"#{e['id']}: {e['note'] or 'No note'} (by {e['uploaded_by']}, {_when(e['created_at'])})",
                style="List Bullet",
            )
            attached = evidence_files.get(e["id"])
            if attached and attached["content_type"].startswith("image/"):
                doc.add_picture(io.BytesIO(attached["data"]), width=Inches(3))
            elif attached:
                doc.add_paragraph("(PDF attachment, not shown in this report)")
    else:
        doc.add_paragraph("No extra evidence attached.")
    doc.add_paragraph(DISCLAIMER)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------- CSV ----------------

def build_csv(scan: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["scan_id", "product_name", "brand", "category", "inspector", "scanned_at",
                "overall_status", "score", "rule_id", "clause", "rule_title", "severity",
                "rule_result", "message"])
    for r in scan["rule_results"]:
        w.writerow([scan["id"], scan["product"]["name"], scan["product"]["brand"],
                    scan["product"]["category"], scan["inspector"]["name"], _when(scan["created_at"]),
                    scan["status"], scan["score"], r["rule_id"], r["clause"], r["title"],
                    r["severity"], r["status"], r["message"]])
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel shows symbols correctly