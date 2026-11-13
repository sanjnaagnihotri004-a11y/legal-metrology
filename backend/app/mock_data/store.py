
import itertools
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from app.errors import AppError

HERE = Path(__file__).resolve().parent
SAMPLE_IMAGE = HERE / "sample.jpg"
SAMPLE_ANNOTATED = HERE / "sample_annotated.jpg"
RULES_FILE = HERE.parent.parent / "rules" / "rules.yaml"

# The rule list comes from the same YAML file the database was seeded from
RULES = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))["rules"]
WEIGHTS = {"critical": 3, "major": 2, "minor": 1}

FIELD_TO_RULE = {
    "manufacturer_name_address": "LM-R1",
    "net_quantity": "LM-R2",
    "mrp": "LM-R3",
    "mfg_date": "LM-R4",
    "consumer_care": "LM-R5",
}
RULE_TO_FIELD = {rule: field for field, rule in FIELD_TO_RULE.items()}
RULE_TO_FIELD["LM-R6"] = "net_quantity"

# In-memory storage (cleared whenever the server restarts)
ENTRIES: dict[int, dict] = {}
_scan_ids = itertools.count(1)
ROTATION = itertools.cycle(["non_compliant", "compliant", "needs_review"])


# ---------- pretend extraction ----------

def _fields(scenario: str) -> dict:
    fields = {
        "manufacturer_name_address": {"found": True, "value": "Mfd. by CrunchCo Foods, Indore 452001",
                                      "confidence": 0.91, "bbox": [100, 900, 700, 980]},
        "net_quantity": {"found": True, "value": "Net Wt. 200 g", "confidence": 0.95,
                         "bbox": [120, 300, 400, 340], "quantity": 200.0, "unit": "g",
                         "font_height_mm": 2.4, "min_font_height_mm": 2.0},
        "mrp": {"found": True, "value": "MRP Rs. 50.00 (Incl. of all taxes)", "confidence": 0.90,
                "bbox": [120, 400, 380, 440]},
        "mfg_date": {"found": True, "value": "Pkd 10/2026", "confidence": 0.86,
                     "bbox": [120, 500, 380, 540]},
        "consumer_care": {"found": True, "value": "Call 1800-123-456", "confidence": 0.88,
                          "bbox": [100, 1000, 500, 1040]},
    }
    missing = {"found": False, "value": None, "confidence": None, "bbox": None}
    if scenario == "non_compliant":
        fields["mrp"]["value"] = "MRP Rs. 50.00"
        fields["mfg_date"] = dict(missing)
    elif scenario == "no_care":
        fields["consumer_care"] = dict(missing)
    elif scenario == "small_font":
        fields["net_quantity"]["font_height_mm"] = 1.2
    elif scenario == "needs_review":
        fields["net_quantity"]["font_height_mm"] = None
        fields["net_quantity"]["min_font_height_mm"] = None
    return fields


# ---------- pretend rule engine (the real one comes in a later step) ----------

def _check(rule_id: str, f: dict) -> tuple[str, str]:
    nq = f["net_quantity"]
    if rule_id == "LM-R1":
        ok = f["manufacturer_name_address"]["found"]
        return ("pass", "Name and address declared") if ok else \
               ("fail", "Manufacturer / packer name and address not found")
    if rule_id == "LM-R2":
        return ("pass", "Net quantity declared") if nq["found"] else ("fail", "Net quantity not found")
    if rule_id == "LM-R3":
        mrp = f["mrp"]
        if not mrp["found"]:
            return "fail", "MRP not found"
        if "incl" not in (mrp["value"] or "").lower():
            return "fail", "MRP found but 'inclusive of all taxes' is missing"
        return "pass", "MRP declared inclusive of all taxes"
    if rule_id == "LM-R4":
        ok = f["mfg_date"]["found"]
        return ("pass", "Month and year declared") if ok else \
               ("fail", "Month and year of manufacture/packing not found")
    if rule_id == "LM-R5":
        ok = f["consumer_care"]["found"]
        return ("pass", "Consumer care details declared") if ok else \
               ("fail", "Consumer care details not found")
    if rule_id == "LM-R6":
        height, minimum = nq["font_height_mm"], nq["min_font_height_mm"]
        if not nq["found"] or height is None or minimum is None:
            return "not_checked", "Font height could not be measured"
        if height >= minimum:
            return "pass", f"Font height {height} mm meets the {minimum} mm minimum"
        return "fail", f"Font height {height} mm is below the {minimum} mm minimum"
    return "not_checked", "Rule not implemented"


def evaluate(fields: dict) -> list[dict]:
    results = []
    for rule in RULES:
        status, message = _check(rule["rule_id"], fields)
        results.append({
            "rule_id": rule["rule_id"],
            "clause": rule["clause"],
            "title": rule["title"],
            "description": rule["description"],
            "severity": rule["severity"],
            "status": status,
            "message": message,
            "bbox": fields[RULE_TO_FIELD[rule["rule_id"]]]["bbox"] if status != "pass" else
                    fields[RULE_TO_FIELD[rule["rule_id"]]]["bbox"],
        })
    return results


def summarize(results: list[dict]) -> tuple[str, float, int]:
    total = sum(WEIGHTS[r["severity"]] for r in results)
    passed = sum(WEIGHTS[r["severity"]] for r in results if r["status"] == "pass")
    score = round(passed / total * 100, 1) if total else 0.0
    fails = sum(1 for r in results if r["status"] == "fail")
    if fails:
        status = "non_compliant"
    elif any(r["status"] == "not_checked" for r in results):
        status = "needs_review"
    else:
        status = "compliant"
    return status, score, fails


def _refresh(scan: dict) -> None:
    results = evaluate(scan["extracted_fields"])
    status, score, violations = summarize(results)
    scan["rule_results"] = results
    scan["status"] = status
    scan["score"] = score
    scan["violations_count"] = violations


# ---------- building and storing scans ----------

def add_scan(product_name, brand, category, user_id, user_name, scenario,
             created_at=None, label_width_mm=120.0, barcode=None, notes=None,
             image=None, image_type="image/jpeg", width=1600, height=1200) -> dict:
    scan_id = next(_scan_ids)
    fields = _fields(scenario)
    ocr_text = " ".join(f["value"] for f in fields.values() if f["value"])
    scan = {
        "id": scan_id,
        "product": {"id": scan_id, "name": product_name, "brand": brand,
                    "barcode": barcode, "category": category},
        "inspector": {"id": user_id, "name": user_name},
        "created_at": created_at or datetime.now(timezone.utc),
        "corrected": False,
        "notes": notes,
        "label_width_mm": label_width_mm,
        "image_width_px": width,
        "image_height_px": height,
        "image_url": f"/scans/{scan_id}/image",
        "annotated_image_url": f"/scans/{scan_id}/annotated-image",
        "ocr_text": ocr_text,
        "ocr_confidence": 0.87,
        "extracted_fields": fields,
        "evidence": [],
    }
    _refresh(scan)
    ENTRIES[scan_id] = {"user_id": user_id, "scan": scan, "image": image, "image_type": image_type}
    return scan


def get_entry(scan_id: int, user) -> dict:
    """Admins see every scan; inspectors only their own. Others get 404 on purpose."""
    entry = ENTRIES.get(scan_id)
    if entry is None or (user.role != "admin" and entry["user_id"] != user.id):
        raise AppError(404, "NOT_FOUND", "Scan not found")
    return entry


def visible_scans(user) -> list[dict]:
    scans = [e["scan"] for e in ENTRIES.values() if user.role == "admin" or e["user_id"] == user.id]
    return sorted(scans, key=lambda s: s["created_at"], reverse=True)


def summary(scan: dict) -> dict:
    return {
        "id": scan["id"],
        "product_name": scan["product"]["name"],
        "brand": scan["product"]["brand"],
        "category": scan["product"]["category"],
        "status": scan["status"],
        "score": scan["score"],
        "violations_count": scan["violations_count"],
        "inspector_name": scan["inspector"]["name"],
        "created_at": scan["created_at"],
    }


_QTY = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l|litres|litre)\b", re.I)


def apply_corrections(scan: dict, corrections: dict) -> None:
    for key, raw in corrections.items():
        value = raw.strip()
        field = scan["extracted_fields"][key]
        if value:
            field["found"] = True
            field["value"] = value
            field["confidence"] = 1.0
            if key == "net_quantity":
                match = _QTY.search(value)
                if match:
                    field["quantity"] = float(match.group(1))
                    field["unit"] = match.group(2).lower()
        else:
            field.update({"found": False, "value": None, "confidence": None, "bbox": None})
    _refresh(scan)
    scan["corrected"] = True


# ---------- 12 pre-made scans so the repository and dashboard are never empty ----------

_SEED = [
    ("Masala Peanuts", "CrunchCo", "food", 2, "Asha Verma", 9, "non_compliant"),
    ("Refined Sunflower Oil 1L", "GoldDrop", "edible_oil", 2, "Asha Verma", 8, "compliant"),
    ("Detergent Powder 1kg", "SparkWash", "detergent_household", 2, "Asha Verma", 7, "small_font"),
    ("Face Cream 50g", "GlowSkin", "cosmetics", 1, "Admin User", 6, "non_compliant"),
    ("Orange Juice 200ml", "FreshPour", "beverages", 2, "Asha Verma", 5, "no_care"),
    ("Herbal Shampoo 180ml", "LeafCare", "personal_care", 2, "Asha Verma", 4, "compliant"),
    ("Salted Chips 90g", "CrunchCo", "food", 1, "Admin User", 3, "needs_review"),
    ("Mustard Oil 500ml", "GoldDrop", "edible_oil", 2, "Asha Verma", 3, "non_compliant"),
    ("Dish Wash Gel 500ml", "SparkWash", "detergent_household", 2, "Asha Verma", 2, "compliant"),
    ("Soft Drink 750ml", "FreshPour", "beverages", 2, "Asha Verma", 1, "small_font"),
    ("Biscuits 250g", "CrunchCo", "food", 2, "Asha Verma", 0, "non_compliant"),
    ("Body Lotion 100ml", "GlowSkin", "cosmetics", 1, "Admin User", 0, "compliant"),
]


def _seed() -> None:
    now = datetime.now(timezone.utc)
    for i, (name, brand, category, uid, uname, days_ago, scenario) in enumerate(_SEED):
        add_scan(name, brand, category, uid, uname, scenario,
                 created_at=now - timedelta(days=days_ago, hours=i + 1))


_seed()