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

# 6-digit PIN code, often printed with a space ("400 099")
PIN_RE = re.compile(r"\b[1-9]\d{2}\s?\d{3}\b")

# "Mfd. by", "Manufactured & Marketed by", "Packed by", "Made in India by", "Manufacturer:" ...
MAKER_RE = re.compile(
    r"\b(?:manufactured|mfd|mfg|packed|pkd|marketed|mktd|imported|distributed|produced)\b\.?"
    r"(?:\s*(?:&|and)\s*\w+)?\s*(?:by|at)\b"
    r"|\bmade\s+(?:in\s+[a-z]+\s+)?by\b"
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

# "Net Wt. 200 g", "Net Vol. when packed 100ml", "NET QUANTITY: 1.5 L"
NET_RE = re.compile(
    r"\bnet\s*(?:wt|weight|qty|quantity|contents?|vol|volume|measure)?\s*\.?\s*"
    r"(?:\(?e\)?\s*)?(?:when\s*packed|at\s*the\s*time\s*of\s*packing)?\s*[:\-=]?\s*"
    r"(\d+(?:[.,]\d+)?)\s*(" + UNIT + "|" + NONSTANDARD + r")\b",
    re.IGNORECASE,
)

MRP_RE = re.compile(
    r"\b(?:m\.?\s?r\.?\s?p\.?|maximum\s+retail\s+price)\D{0,20}?(\d[\d,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
# "Inclusive of all taxes", "Incl. of all taxes", "Inc. all taxes", "Inclusive of GST",
# and common OCR slips such as "INCL OF LL TAXES"
class _TaxWording:
    """Behaves like a compiled regex (it has .search) but ignores spaces, dots and brackets, so OCR
    slips such as 'Inclu sive of all taxes' or 'Inclusve of all taxes' still match."""
    _pattern = re.compile(r"inc[a-z]{0,10}(?:of)?a?l{0,2}(?:taxes|tax|gst)")

    def search(self, text):
        return self._pattern.search(re.sub(r"[^a-z]", "", (text or "").lower()))


INCL_TAX_RE = _TaxWording()
TAX_HINT_RE = re.compile(r"tax|incl|gst", re.IGNORECASE)

# A price printed without the word MRP next to it:  "289/-"   or   "₹ 289"
# (a unit price such as "₹ 2.89/g" is deliberately NOT accepted)
PRICE_SLASH_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})?\s*/\s*-")
PRICE_CURRENCY_RE = re.compile(
    r"(?:\u20b9|\brs\.?|\binr)\s*\d[\d,]*(?:\.\d{1,2})?(?![\d.,])(?!\s*/\s*(?:g|gm|kg|ml|l|100|unit)\b)",
    re.IGNORECASE,
)
# A bare two-decimal amount such as "110.00" (OCR often loses the rupee symbol).
# Only used when the label also has an "MRP (incl. of all taxes)" footnote.
PRICE_DECIMAL_RE = re.compile(
    r"(?<![\d.,/])\d{1,5}\.\d{2}(?![\d.,])(?!\s*/\s*(?:g|gm|kg|ml|l|100|unit)\b)",
    re.IGNORECASE,
)
MRP_WORD_RE = re.compile(r"\bm\.?\s?r\.?\s?p\b", re.IGNORECASE)

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


def _windows(lines: list[dict], max_lines: int = 2):
    """Single lines first, then runs of 2 (or 3) neighbouring lines: OCR often splits one phrase."""
    for size in range(1, max_lines + 1):
        for i in range(len(lines) - size + 1):
            indices = list(range(i, i + size))
            yield indices, " ".join(lines[j]["text"] for j in indices)


def _to_number(text: str) -> float:
    if re.fullmatch(r"\d{1,3}(,\d{3})+", text):
        text = text.replace(",", "")          # 1,000 -> 1000
    else:
        text = text.replace(",", ".")         # 1,5 -> 1.5
    return float(text)

# ---------- table layouts: a heading with its value printed underneath ----------
# Shop stickers and coding bands often look like:
#     MRP (incl. of all taxes)     MFG. DATE      EXPIRY DATE
#     70.00                        SEPT.2026      AUG.2027

MRP_HEAD_RE = re.compile(r"\bm\.?\s?r\.?\s?p\b|maximum\s+retail\s+price", re.IGNORECASE)
_NAMED_DATE = re.compile(r"\b" + MONTH + r"\b[\s.,'/\-]*(\d{4}|\d{2})\b", re.IGNORECASE)
_NUM_DATE = re.compile(r"(?<![\d.])(?:[0-3]?\d\s*[/\-.]\s*)?(0?[1-9]|1[0-2])\s*[/\-.]\s*(\d{4}|\d{2})(?!\d)")
_AMOUNT = re.compile(r"(?<![\d.,/])(\d[\d,]*\.\d{2}|\d[\d,]*\s*/\s*-)(?!\d)")
MAX_HEADING_LENGTH = 28


def _valid_year(text: str) -> bool:
    year = int(text)
    if year < 100:
        year += 2000
    return 2015 <= year <= 2045


def _date_matches(text: str) -> list:
    """Month/year dates with a real month and a believable year ('70.00' is not a date)."""
    found = [m for m in _NAMED_DATE.finditer(text) if _valid_year(m.group(1))]
    found += [m for m in _NUM_DATE.finditer(text) if _valid_year(m.group(2))]
    return sorted(found, key=lambda m: m.start())


def _amount_matches(text: str) -> list:
    """Prices such as 70.00 or 289/-, but not unit prices such as 0.70/g (or 0.70/9 when OCR misreads the g)."""
    found = []
    for m in _AMOUNT.finditer(text):
        if re.match(r"\s*/\s*(?!-)[a-z0-9]", text[m.end():m.end() + 4], re.IGNORECASE):
            continue
        found.append(m)
    return found


def _pick_by_x(line: dict, matches: list, target_x: float):
    """When OCR merged a whole row into one line, choose the match that sits closest to the heading."""
    x1, _, x2, _ = line["bbox"]
    length = max(len(line["text"]), 1)
    return min(matches, key=lambda m: abs(x1 + ((m.start() + m.end()) / 2 / length) * (x2 - x1) - target_x))


def _below_in_column(lines: list[dict], key_index: int, max_gap_heights: int = 8) -> list:
    """Lines printed underneath lines[key_index], in the same column, nearest first."""
    kx1, ky1, kx2, ky2 = lines[key_index]["bbox"]
    key_h = max(ky2 - ky1, 1)
    below = []
    for j, line in enumerate(lines):
        if j == key_index:
            continue
        x1, y1, x2, y2 = line["bbox"]
        if (y1 + y2) / 2 <= (ky1 + ky2) / 2 + 0.5 * key_h:
            continue                                   # not clearly underneath
        if y1 - ky2 > max_gap_heights * key_h:
            continue                                   # too far down to belong to this heading
        if min(x2, kx2) - max(x1, kx1) < 0.25 * min(x2 - x1, kx2 - kx1):
            continue                                   # a different column
        below.append((y1 - ky2, j))
    return sorted(below)


def _find_mrp_by_column(lines: list[dict]):
    for i, key in enumerate(lines):
        if len(key["text"]) > MAX_HEADING_LENGTH or not MRP_HEAD_RE.search(key["text"]):
            continue
        heading_x = (key["bbox"][0] + key["bbox"][2]) / 2
        for _, j in _below_in_column(lines, i):
            matches = _amount_matches(lines[j]["text"])
            if matches:
                pick = _pick_by_x(lines[j], matches, heading_x)
                field = _make(lines, [i, j])
                field["value"] = f"{key['text'].strip()} {pick.group(0)}"
                return field, {i, j}
    return None


def _find_date_by_column(lines: list[dict]):
    for i, key in enumerate(lines):
        text = key["text"]
        if len(text) > MAX_HEADING_LENGTH:
            continue
        m = DATE_KEY_RE.search(text)
        if not m or AFTER_BY_RE.match(text[m.end():]):       # "Mfd. by <company>" is an address
            continue
        heading_x = (key["bbox"][0] + key["bbox"][2]) / 2
        for _, j in _below_in_column(lines, i):
            matches = _date_matches(lines[j]["text"])
            if matches:
                pick = _pick_by_x(lines[j], matches, heading_x)
                field = _make(lines, [i, j])
                field["value"] = f"{text.strip()} {pick.group(0)}"
                return field
    return None

# ---------- the five finders ----------

def _find_address(lines: list[dict]) -> dict:
    candidates = []
    for i, line in enumerate(lines):
        if not MAKER_RE.search(line["text"]):
            continue
        indices, text = [i], line["text"]
        while not PIN_RE.search(text) and len(indices) < 5 and indices[-1] + 1 < len(lines):
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
    for indices, text in _windows(lines, 3):      # "NET VOL." / "WHEN PACKED" / "100ml" can be 3 lines
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
    # The rupee symbol is often lost by OCR. If the label has an "MRP (incl. of all taxes)" footnote,
    # a bare two-decimal amount (e.g. "110.00#08/26" in a coding band) is the price.
    if any(MRP_WORD_RE.search(l["text"]) and INCL_TAX_RE.search(l["text"]) for l in lines):
        for i, line in enumerate(lines):
            if PRICE_DECIMAL_RE.search(line["text"]):
                return i
    return None


def _attach_tax_wording(lines: list[dict], field: dict, used: set) -> None:
    """If the MRP text lacks 'inclusive of all taxes', look for that wording anywhere on the label
    (on one line, or split over two neighbouring lines) and add the nearest match."""
    if INCL_TAX_RE.search(field["value"]):
        return
    candidates = [
        indices for indices, text in _windows(lines)
        if not used.intersection(indices) and INCL_TAX_RE.search(text)
    ]
    if not candidates:
        return

    mx = (field["bbox"][0] + field["bbox"][2]) / 2
    my = (field["bbox"][1] + field["bbox"][3]) / 2

    def distance(indices):
        boxes = [lines[j]["bbox"] for j in indices]
        cx = (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2
        cy = (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2
        return abs(cx - mx) + abs(cy - my)

    chosen = min(candidates, key=distance)
    field["value"] += " " + " ".join(lines[j]["text"].strip() for j in chosen)
    field["confidence"] = round(
        (field["confidence"] + mean(lines[j]["confidence"] for j in chosen)) / 2, 2)


def _find_mrp(lines: list[dict]) -> dict:
    # 1) The normal case: the word MRP followed by an amount
    for indices, text in _windows(lines):
        if MRP_RE.search(text):
            field = _make(lines, indices)
            _attach_tax_wording(lines, field, set(indices))
            return field

    # 1b) Table layout: an "MRP" heading with the amount underneath
    column = _find_mrp_by_column(lines)
    if column:
        field, used = column
        _attach_tax_wording(lines, field, used)
        return field

    # 2) Price printed alone (often in a coding band), with "*MRP (incl. of all taxes)" as a footnote
    price_i = _find_price_line(lines)
    if price_i is None:
        return _missing()
    field = _make(lines, [price_i])               # the box marks the price itself
    _attach_tax_wording(lines, field, {price_i})
    field["confidence"] = round(field["confidence"] * 0.8, 2)   # less certain: no "MRP" beside the price
    return field

def _find_mfg_date(lines: list[dict]) -> dict:
    # 1) The normal case: a keyword such as Mfd / Pkd followed by a date
    for indices, text in _windows(lines):
        for key in DATE_KEY_RE.finditer(text):
            rest = text[key.end():]
            if AFTER_BY_RE.match(rest):           # "Mfd. by <company>" is an address, not a date
                continue
            dates = _date_matches(rest[:60])     # month and year are validated: "70.00" is not a date
            if dates and not EXPIRY_RE.search(rest[:dates[0].start()]):   # skip dates that belong to "Exp"
                return _make(lines, indices)

    # 1b) Table layout: an "MFG. DATE" heading with the date underneath
    column = _find_date_by_column(lines)
    if column:
        return column

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


# ---------- used by manual corrections ----------

QTY_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(" + UNIT + "|" + NONSTANDARD + r")\b", re.IGNORECASE)


def parse_quantity(text: str):
    """'Net Wt. 200 g' or just '200 g' -> (200.0, 'g'). Returns None if no quantity is found."""
    m = QTY_RE.search(text)
    if not m:
        return None
    raw_unit = m.group(2).lower().replace(" ", "").replace(".", "")
    return _to_number(m.group(1)), UNIT_MAP.get(raw_unit, raw_unit)