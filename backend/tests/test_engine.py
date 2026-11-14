
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.annotate import annotate
from app.services.engine import evaluate, load_rules, summarize
from app.services.fontsize import (
    estimate_pdp_area_cm2, measure_numeral_height_px, min_height_mm, mm_per_px,
)
from app.services.pipeline import analyze


def fld(value="x", found=True, conf=0.95, bbox=(10, 10, 100, 40)):
    return {"found": found, "value": value if found else None,
            "confidence": conf if found else None, "bbox": list(bbox) if found else None}


def net(qty=200.0, unit="g", height=2.4, minimum=1.0, found=True):
    f = fld("Net Wt. 200 g", found)
    f.update(quantity=qty if found else None, unit=unit if found else None,
             font_height_mm=height, min_font_height_mm=minimum)
    return f


def good():
    return {
        "manufacturer_name_address": fld("Mfd. by CrunchCo Foods, Indore 452001"),
        "net_quantity": net(),
        "mrp": fld("MRP Rs. 50.00 (Incl. of all taxes)"),
        "mfg_date": fld("Pkd 10/2026"),
        "consumer_care": fld("Customer Care: 1800-123-456"),
    }


def status_of(results, rule_id):
    return next(r["status"] for r in results if r["rule_id"] == rule_id)


def message_of(results, rule_id):
    return next(r["message"] for r in results if r["rule_id"] == rule_id)


# ---------- rule engine ----------

def test_everything_passes():
    results = evaluate(good())
    assert [r["rule_id"] for r in results] == [f"LM-R{i}" for i in range(1, 7)]
    assert all(r["status"] == "pass" for r in results)
    assert summarize(results) == ("compliant", 100.0, 0)


def test_missing_mrp():
    f = good()
    f["mrp"] = fld(found=False)
    r = evaluate(f)
    assert status_of(r, "LM-R3") == "fail"
    assert "not found" in message_of(r, "LM-R3")


def test_mrp_without_tax_wording():
    f = good()
    f["mrp"] = fld("MRP Rs. 50.00")
    r = evaluate(f)
    assert status_of(r, "LM-R3") == "fail"
    assert "inclusive" in message_of(r, "LM-R3").lower()


def test_address_without_pin():
    f = good()
    f["manufacturer_name_address"] = fld("Mfd. by CrunchCo Foods, Indore")
    r = evaluate(f)
    assert status_of(r, "LM-R1") == "fail"
    assert "PIN" in message_of(r, "LM-R1")


def test_pin_written_with_a_space_is_accepted():
    f = good()
    f["manufacturer_name_address"] = fld("MKTD. BY HUL, ANDHERI (E), MUMBAI 400 099")
    assert status_of(evaluate(f), "LM-R1") == "pass"


def test_address_missing():
    f = good()
    f["manufacturer_name_address"] = fld(found=False)
    assert status_of(evaluate(f), "LM-R1") == "fail"


def test_non_metric_unit_fails():
    f = good()
    f["net_quantity"] = net(qty=8.0, unit="oz")
    assert status_of(evaluate(f), "LM-R2") == "fail"


def test_missing_date_and_care():
    f = good()
    f["mfg_date"] = fld(found=False)
    f["consumer_care"] = fld(found=False)
    r = evaluate(f)
    assert status_of(r, "LM-R4") == "fail"
    assert status_of(r, "LM-R5") == "fail"


def test_font_ok():
    f = good()
    f["net_quantity"] = net(height=1.2, minimum=1.0)
    assert status_of(evaluate(f), "LM-R6") == "pass"


def test_font_below_minimum():
    f = good()
    f["net_quantity"] = net(height=0.8, minimum=1.0)
    assert status_of(evaluate(f), "LM-R6") == "fail"


def test_font_borderline_needs_review():
    f = good()
    f["net_quantity"] = net(height=1.05, minimum=1.0)
    r = evaluate(f)
    assert status_of(r, "LM-R6") == "not_checked"
    assert summarize(r)[0] == "needs_review"


def test_font_not_measured():
    f = good()
    f["net_quantity"] = net(height=None, minimum=None)
    r = evaluate(f, ctx={"note": "Numeral height could not be measured in this photo"})
    assert status_of(r, "LM-R6") == "not_checked"
    assert "could not be measured" in message_of(r, "LM-R6")


def test_net_quantity_missing():
    f = good()
    f["net_quantity"] = net(found=False)
    r = evaluate(f)
    assert status_of(r, "LM-R2") == "fail"
    assert status_of(r, "LM-R6") == "not_checked"


def test_score_matches_the_contract_example():
    f = good()
    f["mrp"] = fld("MRP Rs. 50.00")          # LM-R3 fails (critical, 3)
    f["mfg_date"] = fld(found=False)         # LM-R4 fails (major, 2)
    assert summarize(evaluate(f)) == ("non_compliant", 66.7, 2)


def test_low_ocr_confidence_needs_review():
    assert summarize(evaluate(good()), ocr_confidence=0.4)[0] == "needs_review"


def test_a_failure_beats_needs_review():
    f = good()
    f["mrp"] = fld(found=False)
    assert summarize(evaluate(f), ocr_confidence=0.4)[0] == "non_compliant"


def test_disabled_rule_is_not_checked():
    rules = load_rules()
    rules[2]["active"] = False
    r = evaluate(good(), rules=rules)
    assert status_of(r, "LM-R3") == "not_checked"
    assert "disabled" in message_of(r, "LM-R3")


def test_bbox_comes_from_the_field():
    f = good()
    f["mfg_date"] = fld(found=False)
    r = evaluate(f)
    assert next(x for x in r if x["rule_id"] == "LM-R3")["bbox"] == [10, 10, 100, 40]
    assert next(x for x in r if x["rule_id"] == "LM-R4")["bbox"] is None


# ---------- font table and measuring ----------

@pytest.mark.parametrize("area,expected", [
    (10, 1.0), (50, 1.0), (50.1, 1.5), (100, 1.5), (150, 2.5),
    (500, 2.5), (501, 4.0), (2500, 4.0), (2501, 6.0), (99999, 6.0),
])
def test_min_height_by_area(area, expected):
    assert min_height_mm(area) == expected


def test_calibration():
    assert mm_per_px(120, 1600) == 0.075


def test_pdp_area_estimate():
    lines = [{"text": "a", "bbox": [0, 0, 100, 50], "confidence": 1.0},
             {"text": "b", "bbox": [0, 150, 100, 200], "confidence": 1.0}]
    # box is 100 x 200 px at 0.5 mm/px = 50 mm x 100 mm = 50 cm2
    assert estimate_pdp_area_cm2(lines, 0.5) == pytest.approx(50.0)


@pytest.mark.parametrize("background,text", [("white", "black"), ("black", "white")])
def test_measure_numeral_height(background, text):
    try:
        font = ImageFont.load_default(size=40)
    except TypeError:
        font = ImageFont.load_default()
    pic = Image.new("RGB", (300, 120), background)
    d = ImageDraw.Draw(pic)
    d.text((20, 20), "100", fill=text, font=font)
    left, top, right, bottom = d.textbbox((20, 20), "100", font=font)
    measured = measure_numeral_height_px(pic, [0, 0, 300, 120])
    assert measured is not None
    assert abs(measured - (bottom - top)) <= 3


# ---------- annotated image ----------

def test_annotate_with_boxes_only():
    pic = Image.new("RGB", (400, 300), "white")
    results = [{"rule_id": "LM-R1", "status": "pass", "message": "ok", "bbox": [10, 10, 100, 40]}]
    data = annotate(pic, results)
    assert data.startswith(b"\xff\xd8")
    assert Image.open(io.BytesIO(data)).size == (400, 300)


def test_annotate_adds_banner_for_missing_declarations():
    pic = Image.new("RGB", (400, 300), "white")
    results = [{"rule_id": "LM-R4", "status": "fail", "message": "date not found", "bbox": None}]
    out = Image.open(io.BytesIO(annotate(pic, results)))
    assert out.size[0] == 400
    assert out.size[1] > 300


# ---------- the whole pipeline on the sample label (runs real OCR, takes a few seconds) ----------

def test_pipeline_on_sample_label():
    sample = Path(__file__).resolve().parent.parent / "app" / "mock_data" / "sample.jpg"
    out = analyze(sample.read_bytes(), 120.0)
    st = {r["rule_id"]: r["status"] for r in out["rule_results"]}
    assert st["LM-R1"] == "pass"
    assert st["LM-R2"] == "pass"
    assert st["LM-R3"] == "fail"       # the sample has no "inclusive of all taxes"
    assert st["LM-R4"] == "fail"       # and no date
    assert st["LM-R5"] == "pass"
    assert out["status"] == "non_compliant"
    assert out["extracted_fields"]["net_quantity"]["font_height_mm"] is not None
    assert out["annotated_image"].startswith(b"\xff\xd8")