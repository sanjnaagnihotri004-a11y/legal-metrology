
from pathlib import Path

import yaml

from app.services.extraction import INCL_TAX_RE, PIN_RE, STANDARD_UNITS

RULES_FILE = Path(__file__).resolve().parent.parent.parent / "rules" / "rules.yaml"

WEIGHTS = {"critical": 3, "major": 2, "minor": 1}
LOW_CONFIDENCE = 0.6     # below this average OCR confidence, a "clean" result needs a human look
BORDERLINE = 0.10        # numeral height within 10% of the limit is too close to call from a photo

# Which extracted field each rule looks at (its box is used on the annotated image)
RULE_FIELD = {
    "LM-R1": "manufacturer_name_address",
    "LM-R2": "net_quantity",
    "LM-R3": "mrp",
    "LM-R4": "mfg_date",
    "LM-R5": "consumer_care",
    "LM-R6": "net_quantity",
}


def load_rules() -> list[dict]:
    return yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))["rules"]


# ---------- one small function per rule: returns (status, message) ----------

def check_r1(f, ctx):
    a = f["manufacturer_name_address"]
    if not a["found"]:
        return "fail", "Manufacturer / packer / importer name and address not found"
    if not PIN_RE.search(a["value"]):
        return "fail", "Address found but no 6-digit PIN code detected"
    return "pass", "Name and address declared with PIN code"


def check_r2(f, ctx):
    n = f["net_quantity"]
    if not n["found"]:
        return "fail", "Net quantity not found"
    if n["unit"] not in STANDARD_UNITS:
        return "fail", f"Unit '{n['unit']}' is not a standard metric unit"
    if not n["quantity"] or n["quantity"] <= 0:
        return "fail", "Net quantity value is missing or zero"
    return "pass", f"Net quantity declared: {n['quantity']:g} {n['unit']}"


def check_r3(f, ctx):
    m = f["mrp"]
    if not m["found"]:
        return "fail", "MRP not found"
    if not INCL_TAX_RE.search(m["value"]):
        return "fail", "MRP found but 'inclusive of all taxes' wording not found"
    return "pass", "MRP declared inclusive of all taxes"


def check_r4(f, ctx):
    if f["mfg_date"]["found"]:
        return "pass", "Month and year declared"
    return "fail", "Month and year of manufacture/packing/import not found"


def check_r5(f, ctx):
    if f["consumer_care"]["found"]:
        return "pass", "Consumer care details declared"
    return "fail", "Consumer care details (phone or email) not found"


def check_r6(f, ctx):
    n = f["net_quantity"]
    if not n["found"]:
        return "not_checked", "Net quantity not found, so numeral height could not be checked"
    height, minimum = n["font_height_mm"], n["min_font_height_mm"]
    if height is None or minimum is None:
        return "not_checked", (ctx or {}).get("note") or "Numeral height could not be measured"
    ratio = height / minimum
    if ratio >= 1 + BORDERLINE:
        return "pass", f"Numeral height about {height} mm (minimum {minimum} mm)"
    if ratio <= 1 - BORDERLINE:
        return "fail", f"Numeral height about {height} mm is below the {minimum} mm minimum"
    return "not_checked", (f"Numeral height about {height} mm is very close to the {minimum} mm "
                           f"minimum; verify manually")


CHECKS = {
    "LM-R1": check_r1, "LM-R2": check_r2, "LM-R3": check_r3,
    "LM-R4": check_r4, "LM-R5": check_r5, "LM-R6": check_r6,
}


def evaluate(fields: dict, rules: list[dict] | None = None, ctx: dict | None = None) -> list[dict]:
    """Always returns one result per rule, in rule order (the API contract promises 6)."""
    results = []
    for rule in rules if rules is not None else load_rules():
        rule_id = rule["rule_id"]
        if not rule.get("active", True):
            status, message = "not_checked", "Rule disabled by an administrator"
        elif rule_id in CHECKS:
            status, message = CHECKS[rule_id](fields, ctx)
        else:
            status, message = "not_checked", "Rule not implemented"
        field = fields.get(RULE_FIELD.get(rule_id, ""), {})
        results.append({
            "rule_id": rule_id,
            "clause": rule["clause"],
            "title": rule["title"],
            "description": rule["description"],
            "severity": rule["severity"],
            "status": status,
            "message": message,
            "bbox": field.get("bbox"),
        })
    return results


def summarize(results: list[dict], ocr_confidence: float = 1.0) -> tuple[str, float, int]:
    """Returns (status, score, violations_count) exactly as the API contract defines them."""
    total = sum(WEIGHTS[r["severity"]] for r in results)
    passed = sum(WEIGHTS[r["severity"]] for r in results if r["status"] == "pass")
    score = round(passed / total * 100, 1) if total else 0.0
    fails = sum(1 for r in results if r["status"] == "fail")
    if fails:
        status = "non_compliant"
    elif any(r["status"] == "not_checked" for r in results) or ocr_confidence < LOW_CONFIDENCE:
        status = "needs_review"
    else:
        status = "compliant"
    return status, score, fails