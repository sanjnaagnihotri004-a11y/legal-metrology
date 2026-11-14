
"""Turns OCR text lines into the 5 declarations of the API contract.

A "line" is a dict: {"text": str, "bbox": [x1, y1, x2, y2], "confidence": float}
"""
import re
from statistics import mean

MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?"
    r"|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)

# ---------- patterns ----------

PIN_RE = re.compile(r"\b[1-9]\d{5}\b")

# "Mfd. by", "Manufactured & Marketed by", "Packed by", "Manufacturer:" ...
MAKER_RE = re.compile(
    r"\b(?:manufactured|mfd|mfg|packed|pkd|marketed|mktd|imported|distributed|produced)\b\.?"
    r"(?:\s*(?:&|and)\s*\w+)?\s*(?:by|at)\b"
    r"|\b(?:manufacturer|packer|importer|marketer)\b",
    re.IGNORECASE,
)

# Lines that belong to some other field (used to stop reading an address)
OTHER_FIELD_RE = re.compile(
    r"\bm\.?\s?r\.?\s?p\b|\bnet\s*(?:wt|weight|qty|quantity|content)"
    r"|\b(?:mfd|mfg|pkd)\b|customer\s*care|consumer\s*care|best\s*before"
    r"|\bexp(?:iry|iration)?\b",
    re.IGNORECASE,
)

UNIT = (
    r"(?:kgs?|kilograms?|grams?|gms?|g|mg|ml|millilit(?:re|er)s?|lit(?:re|er)s?|ltrs?|l|cl|cm|mm|m"
    r"|pcs?|pieces?|nos|units?|number)"
)
NONSTANDARD = r"(?:fl\.?\s*oz|oz|ounces?|lbs?|pounds?|gallons?|pints?|quarts?)"

UNIT_MAP = {
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "mg": "mg",
    "ml": "ml", "millilitre": "ml", "millilitres": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "ltr": "l", "ltrs": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "cl": "cl", "cm": "cm", "mm": "mm", "m": "m",
    "pc": "nos", "pcs": "nos", "piece": "nos", "pieces": "nos",
    "nos": "nos", "unit": "nos", "units": "nos", "number": "nos",
}
STANDARD_UNITS = set(UNIT_MAP.values())

NET_RE = re.compile(
    r"\bnet\s*(?:wt|weight|qty|quantity|contents?|vol|volume|measure)?\s*\.?\s*"
    r"(?:\(?e\)?\s*)?[:\-=]?\s*(\d+(?:[.,]\d+)?)\s*(" + UNIT + "|" + NONSTANDARD + r")\b",
    re.IGNORECASE,
)

MRP_RE = re.compile(
    r"\b(?:m\.?\s?r\.?\s?p\.?|maximum\s+retail\s+price)\D{0,20}?(\d[\d,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
# "Inclusive of all taxes", "Incl. of all taxes", "Inc. all taxes", "Inclusive of GST",
# and common OCR slips such as "INCL OF LL TAXES"
INCL_TAX_RE = re.compile(
    r"\binc(?:l\w*)?\.?\s*(?:of\s*)?(?:a?l{1,2}\s*)?(?:taxes|tax|gst)", re.IGNORECASE
)
TAX_HINT_RE = re.compile(r"tax|incl|gst", re.IGNORECASE)

# A price printed without the word MRP next to it:  "289/-"   or   "₹ 289"
# (a unit price such as "₹ 2.89/g" is deliberately NOT accepted)
PRICE_SLASH_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})?\s*/\s*-")
PRICE_CURRENCY_RE = re.compile(
    r"(?:\u20b9|\brs\.?|\binr)\s*\d[\d,]*(?:\.\d{1,2})?(?![\d.,])(?!\s*/\s*(?:g|gm|kg|ml|l|100|unit)\b)",
    re.IGNORECASE,
)

DATE_KEY_RE = re.compile(
    r"\b(?:mfd|mfg|pkd|manufactured|manufacturing|manufacture|packed|packing|packaged|imported|import)\b",
    re.IGNORECASE,
)
AFTER_BY_RE = re.compile(r"^\W*(?:(?:&|and)\s*\w+\s*)?(?:by|at)\b", re.IGNORECASE)
EXPIRY_RE = re.compile(r"\bexp|best\s*before|use\s*(?:by|before)", re.IGNORECASE)
DATE_RE = re.compile(
    r"\b\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*(?:\d{4}|\d{2})\b"   # 10/10/2026
    r"|\b\d{1,2}\s*[/\-.]\s*(?:\d{4}|\d{2})\b"                    # 10/2026, 10/26
    r"|\b" + MONTH + r"\b[\s.,'/\-]*(?:\d{4}|\d{2})\b"              # Oct 2026, OCT-26
    r"|\b\d{1,2}[\s\-/.]*" + MONTH + r"\b[\s.,'/\-]*(?:\d{4}|\d{2})\b",  # 12 Oct 2026
    re.IGNORECASE,
)
# Month/year only, e.g. "05/26" or "04/2028" (used when dates are marked with symbols)
SHORT_DATE_RE = re.compile(r"(?<!\d)(0?[1-9]|1[0-2])\s*[/\-.]\s*(\d{4}|\d{2})(?!\d)")
# Footnote wording such as "#MFD., B. NO. & @USE BEFORE"
DATE_NOTE_RE = re.compile(r"use\s*before|best\s*before|\bb\.?\s*no\b|batch", re.IGNORECASE)

CARE_KEY_RE = re.compile(
    r"customer\s*care|consumer\s*care|customer\s*(?:support|service)"
    r"|consumer\s*(?:complaint|grievance)|complaints?|toll[\s\-]*free|help\s*line"
    r"|feedback|contact\s*us|call\s*us|\bcall\b|write\s*to|quer(?:y|ies)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(
    r"\b1800(?:[\s\-]?\d){6,9}\b"                                    # toll free, any grouping
    r"|(?<!\w)(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}\b"             # mobile
    r"|\b0\d{2,4}[\s\-]?\d{6,8}\b"                                    # landline
)


# ---------- helpers ----------

def _missing() -> dict:
    return {"found": False, "value": None, "confidence": None, "bbox": None}


def _make(lines: list[dict], indices: list[int]) -> dict:
    chosen = [lines[i] for i in indices]
    boxes = [l["bbox"] for l in chosen]
    return {
        "found": True,
        "value": " ".join(l["text"].strip() for l in chosen),
        "confidence": round(mean(l["confidence"] for l in chosen), 2),
        "bbox": [min(b[0] for b in boxes), min(b[1] for b in boxes),
                 max(b[2] for b in boxes), max(b[3] for b in boxes)],
    }


def _windows(lines: list[dict]):
    """Each single line first, then each pair of neighbouring lines (OCR often splits one phrase)."""
    for i in range(len(lines)):
        yield [i], lines[i]["text"]
    for i in range(len(lines) - 1):
        yield [i, i + 1], lines[i]["text"] + " " + lines[i + 1]["text"]


def _to_number(text: str) -> float:
    if re.fullmatch(r"\d{1,3}(,\d{3})+", text):
        text = text.replace(",", "")          # 1,000 -> 1000
    else:
        text = text.replace(",", ".")         # 1,5 -> 1.5
    return float(text)


# ---------- the five finders ----------

def _find_address(lines: list[dict]) -> dict:
    candidates = []
    for i, line in enumerate(lines):
        if not MAKER_RE.search(line["text"]):
            continue
        indices, text = [i], line["text"]
        while not PIN_RE.search(text) and len(indices) < 4 and indices[-1] + 1 < len(lines):
            nxt = lines[indices[-1] + 1]
            if OTHER_FIELD_RE.search(nxt["text"]) or MAKER_RE.search(nxt["text"]):
                break
            indices.append(indices[-1] + 1)
            text += " " + nxt["text"]
        candidates.append((indices, text))

    for indices, text in candidates:          # prefer a block that contains a PIN code
        if PIN_RE.search(text):
            return _make(lines, indices)
    if candidates:
        return _make(lines, candidates[0][0])
    return _missing()


def _net_missing() -> dict:
    field = _missing()
    field.update(quantity=None, unit=None, font_height_mm=None, min_font_height_mm=None)
    return field


def _find_net_quantity(lines: list[dict]) -> dict:
    for indices, text in _windows(lines):
        m = NET_RE.search(text)
        if m:
            raw_unit = m.group(2).lower().replace(" ", "").replace(".", "")
            field = _make(lines, indices)
            field.update(
                quantity=_to_number(m.group(1)),
                unit=UNIT_MAP.get(raw_unit, raw_unit),   # non-metric units stay as written, e.g. "oz"
                font_height_mm=None,                      # filled in by the font-size step
                min_font_height_mm=None,
            )
            return field
    return _net_missing()


def _find_price_line(lines: list[dict]) -> int | None:
    for pattern in (PRICE_SLASH_RE, PRICE_CURRENCY_RE):   # "289/-" is the stronger signal
        for i, line in enumerate(lines):
            if pattern.search(line["text"]):
                return i
    return None


def _find_mrp(lines: list[dict]) -> dict:
    # 1) The normal case: the word MRP followed by an amount
    for indices, text in _windows(lines):
        if MRP_RE.search(text):
            used = list(indices)
            if not INCL_TAX_RE.search(text):
                last = indices[-1]
                for k in (last + 1, last + 2):    # "(Inclusive of all taxes)" is often on the next line
                    if k < len(lines) and TAX_HINT_RE.search(lines[k]["text"]):
                        used.append(k)
                        break
            return _make(lines, used)

    # 2) Price printed alone (often in a coding band), with "*MRP (incl. of all taxes)" as a footnote
    price_i = _find_price_line(lines)
    if price_i is None:
        return _missing()
    field = _make(lines, [price_i])               # the box marks the price itself
    for j, line in enumerate(lines):
        if j != price_i and INCL_TAX_RE.search(line["text"]):
            field["value"] += " " + line["text"].strip()
            field["confidence"] = round((field["confidence"] + line["confidence"]) / 2, 2)
            break
    field["confidence"] = round(field["confidence"] * 0.8, 2)   # less certain: no "MRP" beside the price
    return field


def _find_mfg_date(lines: list[dict]) -> dict:
    # 1) The normal case: a keyword such as Mfd / Pkd followed by a date
    for indices, text in _windows(lines):
        for key in DATE_KEY_RE.finditer(text):
            rest = text[key.end():]
            if AFTER_BY_RE.match(rest):           # "Mfd. by <company>" is an address, not a date
                continue
            d = DATE_RE.search(rest[:60])
            if d and not EXPIRY_RE.search(rest[:d.start()]):   # skip dates that belong to "Exp"
                return _make(lines, indices)

    # 2) Symbol-marked dates ("#05/26 ... @04/28") explained by a footnote.
    #    Only used when there are at least two different dates, and the earlier one is taken.
    if any(DATE_NOTE_RE.search(l["text"]) for l in lines):
        dates = []
        for i, line in enumerate(lines):
            text = line["text"]
            if PHONE_RE.search(text) or EMAIL_RE.search(text) or re.search(r"toll", text, re.IGNORECASE):
                continue                          # "1800-10-22" must not be read as a date
            m = SHORT_DATE_RE.search(text)
            if m:
                month, year = int(m.group(1)), int(m.group(2))
                if year < 100:
                    year += 2000
                if 2015 <= year <= 2045:
                    dates.append(((year, month), i))
        if len({d for d, _ in dates}) >= 2:
            _, i = min(dates)
            field = _make(lines, [i])
            field["confidence"] = round(field["confidence"] * 0.7, 2)
            return field
    return _missing()


def _find_consumer_care(lines: list[dict]) -> dict:
    strong, weak = None, None
    for indices, text in _windows(lines):
        if not (EMAIL_RE.search(text) or PHONE_RE.search(text)):
            continue
        if CARE_KEY_RE.search(text):
            strong = indices
            break
        if weak is None:
            weak = indices

    if strong:
        return _make(lines, strong)
    if weak:                                       # a phone or email with no "customer care" wording
        field = _make(lines, weak)
        field["confidence"] = round(field["confidence"] * 0.7, 2)
        return field
    return _missing()


def extract_fields(lines: list[dict]) -> dict:
    return {
        "manufacturer_name_address": _find_address(lines),
        "net_quantity": _find_net_quantity(lines),
        "mrp": _find_mrp(lines),
        "mfg_date": _find_mfg_date(lines),
        "consumer_care": _find_consumer_care(lines),
    }