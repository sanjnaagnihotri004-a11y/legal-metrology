
import pytest

from app.services.extraction import INCL_TAX_RE, PIN_RE, STANDARD_UNITS, extract_fields


def L(text, y=100, conf=0.95):
    return {"text": text, "bbox": [100, y, 600, y + 40], "confidence": conf}


def lines_of(*texts):
    return [L(t, y=100 + i * 60) for i, t in enumerate(texts)]


def test_compliant_label():
    f = extract_fields(lines_of(
        "CrunchCo", "Masala Peanuts", "Net Wt. 200 g",
        "MRP Rs. 50.00 (Incl. of all taxes)", "Pkd 10/2026",
        "Mfd. by CrunchCo Foods, Indore 452001", "Customer Care: 1800-123-456",
    ))
    assert all(f[k]["found"] for k in f)
    nq = f["net_quantity"]
    assert (nq["quantity"], nq["unit"]) == (200.0, "g")
    assert INCL_TAX_RE.search(f["mrp"]["value"])
    assert PIN_RE.search(f["manufacturer_name_address"]["value"])
    assert f["mfg_date"]["value"] == "Pkd 10/2026"
    assert f["mrp"]["bbox"] == [100, 280, 600, 320]


def test_empty_input():
    f = extract_fields([])
    assert set(f) == {"manufacturer_name_address", "net_quantity", "mrp", "mfg_date", "consumer_care"}
    assert not any(f[k]["found"] for k in f)
    assert set(f["net_quantity"]) == {"found", "value", "confidence", "bbox", "quantity", "unit",
                                      "font_height_mm", "min_font_height_mm"}


# ---------- MRP ----------

def test_mrp_missing():
    assert not extract_fields(lines_of("Net Wt. 200 g"))["mrp"]["found"]


def test_mrp_without_tax_text():
    mrp = extract_fields(lines_of("MRP Rs. 50.00"))["mrp"]
    assert mrp["found"]
    assert INCL_TAX_RE.search(mrp["value"]) is None


def test_mrp_tax_on_next_line():
    mrp = extract_fields(lines_of("MRP Rs. 50.00", "(Inclusive of all taxes)"))["mrp"]
    assert mrp["found"]
    assert INCL_TAX_RE.search(mrp["value"])


def test_mrp_amount_on_next_line():
    mrp = extract_fields(lines_of("M.R.P.", "Rs. 50.00/-"))["mrp"]
    assert mrp["found"]
    assert "50.00" in mrp["value"]


@pytest.mark.parametrize("text", [
    "Inclusive of all taxes", "Incl. of all taxes", "(Incl. all taxes)",
    "Inc. of all taxes", "Inclusive of GST",
])
def test_incl_tax_variants(text):
    assert INCL_TAX_RE.search(text)


# ---------- manufacture date ----------

@pytest.mark.parametrize("text", [
    "Pkd 10/2026", "MFG: OCT-2026", "Mfd. 10/10/2026",
    "Date of Manufacture: Oct 2026", "Packed on 12 Oct 2026",
])
def test_date_formats(text):
    d = extract_fields(lines_of(text))["mfg_date"]
    assert d["found"]
    assert d["value"] == text


def test_manufacturer_line_is_not_a_date():
    assert not extract_fields(lines_of("Mfd. by CrunchCo Foods, Indore 452001"))["mfg_date"]["found"]


def test_expiry_text_is_not_a_date():
    f = extract_fields(lines_of("Best before 6 months from manufacture", "Exp 12/2027"))
    assert not f["mfg_date"]["found"]


# ---------- net quantity ----------

@pytest.mark.parametrize("text,quantity,unit", [
    ("Net Wt. 200 g", 200.0, "g"),
    ("NET QUANTITY: 1.5 L", 1.5, "l"),
    ("Net Wt.200g", 200.0, "g"),
    ("Net Weight 1,000 GRAMS", 1000.0, "g"),
])
def test_net_quantity_formats(text, quantity, unit):
    nq = extract_fields(lines_of(text))["net_quantity"]
    assert nq["found"]
    assert nq["quantity"] == quantity
    assert nq["unit"] == unit


def test_net_quantity_non_metric_unit():
    nq = extract_fields(lines_of("Net Wt. 8 oz"))["net_quantity"]
    assert nq["found"]
    assert nq["unit"] == "oz"
    assert nq["unit"] not in STANDARD_UNITS


def test_net_quantity_split_across_lines():
    nq = extract_fields(lines_of("Net Wt.", "200 g"))["net_quantity"]
    assert nq["found"]
    assert (nq["quantity"], nq["unit"]) == (200.0, "g")


def test_net_quantity_needs_the_net_keyword():
    assert not extract_fields(lines_of("200 g"))["net_quantity"]["found"]


# ---------- manufacturer and address ----------

def test_address_collects_lines_until_pin():
    a = extract_fields(lines_of(
        "Manufactured by: CrunchCo Foods Pvt Ltd", "Plot 5, Industrial Area, Indore",
        "Madhya Pradesh 452001", "MRP Rs. 50.00",
    ))["manufacturer_name_address"]
    assert a["found"]
    assert "452001" in a["value"]
    assert a["bbox"] == [100, 100, 600, 260]


def test_address_without_pin():
    a = extract_fields(lines_of("Mfd. by CrunchCo Foods", "MRP Rs. 50.00"))["manufacturer_name_address"]
    assert a["found"]
    assert PIN_RE.search(a["value"]) is None


# ---------- consumer care ----------

def test_care_phone_with_keyword():
    c = extract_fields(lines_of("Customer Care: 1800-123-456"))["consumer_care"]
    assert c["found"]
    assert "1800" in c["value"]
    assert c["confidence"] == 0.95


def test_care_mobile_number():
    c = extract_fields(lines_of("For complaints call 98765 43210"))["consumer_care"]
    assert c["found"]
    assert c["confidence"] == 0.95


def test_care_email_only_has_lower_confidence():
    c = extract_fields(lines_of("care@crunchco.com"))["consumer_care"]
    assert c["found"]
    assert c["confidence"] < 0.95


def test_care_keyword_without_contact():
    assert not extract_fields(lines_of("Customer Care"))["consumer_care"]["found"]

# ---------- real label (lines copied from an actual photo's OCR output) ----------

REAL_LABEL = lines_of(
    "2.89/g",
    "AA*289/-,",
    "#05/26 B049",
    "@04/28",
    "FACE WASH. MADE IN INDIA. MKTD. BY: HINDUSTAN UNILEVER",
    "(HUL), UNILEVER HOUSE, B. D. SAWANT MARG, CHAKALA,",
    "ANDHERI (E), MUMBAI 400 099, MAHARASHTRA. © HUL 2025.",
    "FOR MFG. UNIT NAME AND ADDRESS, READ THE FIRST CHARACTER(S) OF THE",
    "CODE FOLLOWING 0 IN CODING AREA, AND THEN REFER HERE:",
    "(AX) ALPLA INDIA PRIVATE LIMITED, SURVEY NO. 255/26, BEHIND",
    "SURVEY NO. 284/2, NEAR NAROLI CHECK",
    "RP (INCL OF LL TAXES), USP",
    "INGD, B.NO. & @USE BEFORE",
    "LEVERCARE-QUERY / FEEDBACK",
    "TOLL FREE: 1800-10-22-221",
    "P0B0X 14760, MUMBAI 400 099",
    "LEVER.CARE@UNILEVER.COM",
    "Net Wt.:",
    "100 g",
)


def test_real_photo_mrp_footnote_style():
    mrp = extract_fields(REAL_LABEL)["mrp"]
    assert mrp["found"]
    assert "289/-" in mrp["value"]
    assert INCL_TAX_RE.search(mrp["value"])
    assert mrp["bbox"] == [100, 160, 600, 200]   # the box marks the price line


def test_real_photo_dates_marked_with_symbols():
    d = extract_fields(REAL_LABEL)["mfg_date"]
    assert d["found"]
    assert "05/26" in d["value"]                 # the earlier date, not 04/28 and not 1800-10-22
    assert d["confidence"] < 0.8                 # a heuristic result is flagged as less certain


def test_real_photo_consumer_care():
    c = extract_fields(REAL_LABEL)["consumer_care"]
    assert c["found"]
    assert "1800-10-22-221" in c["value"]
    assert c["confidence"] == 0.95


def test_real_photo_net_quantity():
    nq = extract_fields(REAL_LABEL)["net_quantity"]
    assert (nq["quantity"], nq["unit"]) == (100.0, "g")


def test_unit_price_is_not_taken_as_mrp():
    assert not extract_fields(lines_of("\u20b9 2.89/g"))["mrp"]["found"]


def test_two_dates_without_footnote_are_not_guessed():
    f = extract_fields(lines_of("05/26", "04/28"))
    assert not f["mfg_date"]["found"]


def test_incl_tax_with_ocr_slip():
    assert INCL_TAX_RE.search("RP (INCL OF LL TAXES), USP")


@pytest.mark.parametrize("text", [
    "TOLL FREE: 1800-10-22-221", "Toll free 1800 123 4567", "Call 1800-123-456",
])
def test_toll_free_variants(text):
    assert extract_fields(lines_of(text))["consumer_care"]["found"] 