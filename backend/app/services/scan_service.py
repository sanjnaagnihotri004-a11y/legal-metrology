
import copy
import io

from PIL import Image
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.errors import AppError
from app.models import Product, Scan, User, Violation
from app.services import annotate, engine, pipeline, storage
from app.services.extraction import parse_quantity

CORRECTABLE = ("manufacturer_name_address", "net_quantity", "mrp", "mfg_date", "consumer_care")


# ---------- reading ----------

def get_visible(db: Session, scan_id: int, user: User) -> Scan:
    """Admins see every scan; inspectors only their own. Others get 404 on purpose."""
    scan = db.get(Scan, scan_id)
    if scan is None or (user.role != "admin" and scan.user_id != user.id):
        raise AppError(404, "NOT_FOUND", "Scan not found")
    return scan


def visible_rows(db: Session, user: User) -> list[Scan]:
    query = db.query(Scan).options(joinedload(Scan.product), joinedload(Scan.user))
    if user.role != "admin":
        query = query.filter(Scan.user_id == user.id)
    return query.order_by(Scan.created_at.desc(), Scan.id.desc()).all()


def summary(scan: Scan) -> dict:
    return {
        "id": scan.id,
        "product_name": scan.product.name,
        "brand": scan.product.brand,
        "category": scan.product.category,
        "status": scan.status,
        "score": scan.score,
        "violations_count": scan.violations_count,
        "inspector_name": scan.user.name,
        "created_at": scan.created_at,
    }


def evidence_dict(db: Session, evidence) -> dict:
    uploader = db.get(User, evidence.uploaded_by)
    return {
        "id": evidence.id,
        "scan_id": evidence.scan_id,
        "file_url": f"/evidence/{evidence.id}/file",
        "note": evidence.note,
        "uploaded_by": uploader.name if uploader else "Unknown",
        "created_at": evidence.created_at,
    }


def scan_to_dict(db: Session, scan: Scan) -> dict:
    """Builds the full Scan object of the API contract (frontend doc, Section 5.5)."""
    p = scan.product
    return {
        "id": scan.id,
        "product": {"id": p.id, "name": p.name, "brand": p.brand, "barcode": p.barcode, "category": p.category},
        "inspector": {"id": scan.user.id, "name": scan.user.name},
        "created_at": scan.created_at,
        "status": scan.status,
        "score": scan.score,
        "corrected": scan.corrected,
        "notes": scan.notes,
        "label_width_mm": scan.label_width_mm,
        "image_width_px": scan.image_width_px,
        "image_height_px": scan.image_height_px,
        "image_url": f"/scans/{scan.id}/image",
        "annotated_image_url": f"/scans/{scan.id}/annotated-image",
        "ocr_text": scan.ocr_text,
        "ocr_confidence": scan.ocr_confidence,
        "extracted_fields": scan.extracted_json,
        "rule_results": scan.rule_results_json,
        "violations_count": scan.violations_count,
        "evidence": [evidence_dict(db, e) for e in scan.evidence],
    }


# ---------- writing ----------

def _find_or_create_product(db: Session, name, brand, category, barcode) -> Product:
    """The same product scanned again reuses its row, which builds its inspection history."""
    query = db.query(Product).filter(
        func.lower(Product.name) == name.lower(),
        func.lower(Product.brand) == brand.lower(),
    )
    query = query.filter(Product.barcode == barcode) if barcode else query.filter(Product.barcode.is_(None))
    product = query.first()
    if product:
        product.category = category
        return product
    product = Product(name=name, brand=brand, category=category, barcode=barcode)
    db.add(product)
    return product


def _replace_violations(scan: Scan, results: list[dict]) -> None:
    scan.violations.clear()
    for r in results:
        if r["status"] == "fail":
            scan.violations.append(Violation(
                rule_id=r["rule_id"], severity=r["severity"], message=r["message"], bbox_json=r["bbox"],
            ))


def _jpeg(pic: Image.Image) -> bytes:
    buf = io.BytesIO()
    pic.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def create_scan(db: Session, user: User, *, image_bytes: bytes, product_name: str, brand: str,
                category: str, label_width_mm: float, barcode: str | None, notes: str | None) -> dict:
    analysis = pipeline.analyze(image_bytes, label_width_mm)   # may raise OCR_NO_TEXT
    try:
        product = _find_or_create_product(db, product_name, brand, category, barcode)
        scan = Scan(
            product=product,
            user_id=user.id,
            status=analysis["status"],
            score=analysis["score"],
            corrected=False,
            notes=notes,
            label_width_mm=label_width_mm,
            image_width_px=analysis["image_width_px"],
            image_height_px=analysis["image_height_px"],
            ocr_text=analysis["ocr_text"],
            ocr_confidence=analysis["ocr_confidence"],
            extracted_json=analysis["extracted_fields"],
            rule_results_json=analysis["rule_results"],
            violations_count=analysis["violations_count"],
        )
        db.add(scan)
        db.flush()                                   # gives the scan its id
        scan.image_path = storage.save("originals", f"{scan.id}.jpg", _jpeg(analysis["image"]))
        scan.annotated_path = storage.save("annotated", f"{scan.id}.jpg", analysis["annotated_image"])
        _replace_violations(scan, analysis["rule_results"])
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(scan)
    return scan_to_dict(db, scan)


def recheck(db: Session, scan: Scan, corrections: dict[str, str]) -> dict:
    """Applies an inspector's corrections and re-runs the rules. OCR is not run again."""
    fields = copy.deepcopy(scan.extracted_json)
    for key, raw in corrections.items():
        value = raw.strip()
        field = fields[key]
        if value:
            field.update(found=True, value=value, confidence=1.0)    # a human typed it
            if key == "net_quantity":
                parsed = parse_quantity(value)
                field["quantity"], field["unit"] = parsed if parsed else (None, None)
        else:
            field.update(found=False, value=None, confidence=None, bbox=None)
            if key == "net_quantity":
                field.update(quantity=None, unit=None, font_height_mm=None, min_font_height_mm=None)

    results = engine.evaluate(fields)
    status, score, violations = engine.summarize(results, 1.0)   # 1.0: a human has reviewed this scan

    scan.extracted_json = fields          # assigned as a new object, so the database notices the change
    scan.rule_results_json = results
    scan.status, scan.score, scan.violations_count = status, score, violations
    scan.corrected = True
    _replace_violations(scan, results)

    original = Image.open(io.BytesIO(storage.read(scan.image_path)))
    storage.save("annotated", f"{scan.id}.jpg", annotate.annotate(original, results))
    db.commit()
    db.refresh(scan)
    return scan_to_dict(db, scan)