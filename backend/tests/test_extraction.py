
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

# ---------- tax wording found anywhere on the label ----------

def test_tax_wording_on_a_distant_line_is_found():
    mrp = extract_fields(lines_of(
        "MUMFALLI 1KG", "M.R.P. 155.00", "RATE", "KESHRI DAILY NEEDS", "Inclusive of all taxes"))["mrp"]
    assert mrp["found"]
    assert INCL_TAX_RE.search(mrp["value"])


def test_tax_wording_split_over_two_lines():
    mrp = extract_fields(lines_of("M.R.P. 155.00", "RATE", "Inclusive of", "all taxes"))["mrp"]
    assert INCL_TAX_RE.search(mrp["value"])


def test_no_tax_wording_anywhere_still_fails():
    mrp = extract_fields(lines_of("M.R.P. 155.00", "RATE", "KESHRI DAILY NEEDS"))["mrp"]
    assert mrp["found"]
    assert INCL_TAX_RE.search(mrp["value"]) is None


@pytest.mark.parametrize("text", [
    "Inclusve of all taxes", "Inclu sive of all taxes", "INCLUSIVE OF ALL TAXES", "incl.ofalltaxes",
])
def test_ocr_slips_in_tax_wording(text):
    assert INCL_TAX_RE.search(text)

# ---------- table layouts: heading on top, value underneath (a coding band) ----------

def box_line(text, x1, y1, x2, y2, conf=0.95):
    return {"text": text, "bbox": [x1, y1, x2, y2], "confidence": conf}


def reading_order(lines):
    return sorted(lines, key=lambda l: (l["bbox"][1], l["bbox"][0]))


BAND_HEADINGS = [
    box_line("MRP \u20b9:", 60, 62, 190, 100),
    box_line("MFG.", 345, 72, 435, 105),
    box_line("LOT", 515, 72, 585, 105),
    box_line("UNIT SALE", 640, 72, 825, 108),
    box_line("EXPIRY", 885, 72, 1015, 108),
    box_line("(INCL. OF ALL TAXES)", 58, 105, 282, 135),
    box_line("DATE", 340, 112, 435, 145),
    box_line("NO.", 518, 112, 585, 145),
    box_line("PRICE \u20b9", 660, 112, 800, 150),
    box_line("DATE", 905, 112, 1000, 150),
]
BAND_VALUES_SPLIT = [
    box_line("70.00", 60, 222, 238, 262),
    box_line("SEPT.2026", 280, 228, 450, 262),
    box_line("0926016A", 505, 228, 655, 262),
    box_line("0.70/9", 708, 228, 818, 262),
    box_line("AUG.2027", 870, 228, 1015, 262),
]
BAND_VALUES_MERGED = [box_line("70.00 SEPT.2026 0926016A 0.70/9 AUG.2027", 60, 225, 1015, 265)]


@pytest.mark.parametrize("values", [BAND_VALUES_SPLIT, BAND_VALUES_MERGED])
def test_coding_band_mrp_and_date_are_found(values):
    f = extract_fields(reading_order(BAND_HEADINGS + values))
    assert f["mrp"]["found"]
    assert "70.00" in f["mrp"]["value"]
    assert "0.70" not in f["mrp"]["value"].replace("70.00", "")     # the unit price is not the MRP
    assert INCL_TAX_RE.search(f["mrp"]["value"])
    assert f["mfg_date"]["found"]
    assert "SEPT.2026" in f["mfg_date"]["value"]
    assert "AUG" not in f["mfg_date"]["value"]                      # the expiry column is not used


def test_expiry_column_alone_is_not_a_manufacture_date():
    f = extract_fields(reading_order([
        box_line("EXPIRY", 885, 72, 1015, 108),
        box_line("DATE", 905, 112, 1000, 150),
        box_line("AUG.2027", 870, 228, 1015, 262),
    ]))
    assert not f["mfg_date"]["found"]


def test_unit_price_under_an_mrp_heading_is_not_the_mrp():
    f = extract_fields(reading_order([
        box_line("MRP \u20b9:", 60, 62, 190, 100),
        box_line("NOTHING HERE", 600, 100, 900, 130),     # keeps the heading and the price apart
        box_line("0.70/9", 60, 228, 180, 262),
    ]))
    assert not f["mrp"]["found"]


def test_an_amount_is_not_a_date():
    f = extract_fields(reading_order([
        box_line("MFG.", 345, 72, 435, 105),
        box_line("70.00", 340, 228, 440, 262),
    ]))
    assert not f["mfg_date"]["found"]

def test_amount_on_the_same_line_as_a_date_keyword_is_not_a_date():
    assert not extract_fields(lines_of("Mfd. Rs. 70.00"))["mfg_date"]["found"]