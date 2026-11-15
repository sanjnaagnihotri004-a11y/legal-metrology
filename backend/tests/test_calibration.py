import io
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app
from app.services.calibration import detect_card, lines_outside, resolve_scale
from app.services.pipeline import analyze

SAMPLE = Path(__file__).resolve().parent.parent / "app" / "mock_data" / "sample.jpg"
RATIO = 85.60 / 53.98


def canvas(w=1200, h=900):
    return Image.new("RGB", (w, h), (110, 130, 150))


def draw_card(img, cx, cy, long_px, angle_deg=0.0, ratio=RATIO):
    short_px = long_px / ratio
    a = math.radians(angle_deg)
    points = []
    for dx, dy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
        x, y = dx * long_px / 2, dy * short_px / 2
        points.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    ImageDraw.Draw(img).polygon(points, fill=(235, 235, 235), outline=(30, 30, 30))
    return img


# ---------- finding the card ----------

def test_card_is_found_and_gives_the_scale():
    card = detect_card(draw_card(canvas(), 600, 450, 400), [])
    assert card is not None
    assert card["mm_per_px"] == pytest.approx(85.6 / 400, rel=0.05)


def test_tilted_card_is_found():
    card = detect_card(draw_card(canvas(), 600, 450, 400, angle_deg=20), [])
    assert card is not None
    assert card["mm_per_px"] == pytest.approx(85.6 / 400, rel=0.06)


def test_plain_image_has_no_card():
    assert detect_card(canvas(), []) is None


def test_square_is_not_a_card():
    assert detect_card(draw_card(canvas(), 600, 450, 300, ratio=1.0), []) is None


def test_wide_rectangle_is_not_a_card():
    assert detect_card(draw_card(canvas(), 600, 450, 500, ratio=3.0), []) is None


def test_a_panel_full_of_text_is_not_a_card():
    img = draw_card(canvas(), 600, 450, 400)
    lines = [{"text": "t", "bbox": [500 + i * 5, 400 + i * 10, 560 + i * 5, 420 + i * 10], "confidence": 0.9}
             for i in range(6)]
    assert detect_card(img, lines) is None


def test_lines_on_the_card_are_dropped():
    lines = [{"text": "VISA", "bbox": [500, 400, 560, 420], "confidence": 0.9},
             {"text": "Net Wt. 100 g", "bbox": [100, 100, 300, 140], "confidence": 0.9}]
    kept = lines_outside(lines, [400, 324, 800, 576])
    assert [l["text"] for l in kept] == ["Net Wt. 100 g"]


# ---------- where the scale comes from ----------

def test_typed_width_wins():
    s = resolve_scale(canvas(1600, 1200), [], 120.0)
    assert s["source"] == "manual" and s["reference_bbox"] is None
    assert s["mm_per_px"] == pytest.approx(0.075)


def test_no_reference_means_no_scale():
    assert resolve_scale(canvas(), [], None) == {"mm_per_px": None, "source": "none", "reference_bbox": None}


def test_card_is_used_when_no_width_is_typed():
    s = resolve_scale(draw_card(canvas(), 600, 450, 400), [], None)
    assert s["source"] == "card" and s["reference_bbox"] is not None


# ---------- the whole pipeline with real OCR (a few seconds each) ----------

def test_pipeline_without_any_scale_skips_the_font_check():
    out = analyze(SAMPLE.read_bytes(), None)
    st = {r["rule_id"]: r["status"] for r in out["rule_results"]}
    assert out["scale_source"] == "none" and out["label_width_mm"] is None
    assert st["LM-R6"] == "not_checked"
    assert "scale" in out["font_info"]["note"].lower()
    assert st["LM-R3"] == "fail"            # the other rules still work


def test_pipeline_finds_the_card_by_itself():
    big = Image.new("RGB", (2300, 1200), (110, 130, 150))
    big.paste(Image.open(SAMPLE).convert("RGB"), (0, 0))
    draw_card(big, 1980, 300, 600)           # a "card" 600 px long, beside the label
    buf = io.BytesIO()
    big.save(buf, format="JPEG", quality=92)

    out = analyze(buf.getvalue(), None)
    st = {r["rule_id"]: r["status"] for r in out["rule_results"]}
    assert out["scale_source"] == "card"
    assert out["label_width_mm"] == pytest.approx(2300 * 85.6 / 600, rel=0.06)
    assert st["LM-R6"] == "pass"


# ---------- the API with the optional width (OCR replaced by the fast stand-in) ----------

client = TestClient(app)


def _headers():
    token = client.post("/auth/login", json={"email": "inspector@lm.test",
                                              "password": "Inspector@123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(buf, format="PNG")
    return buf.getvalue()


def _post(data):
    base = {"product_name": "Auto Scale", "brand": "TestCo", "category": "food"}
    return client.post("/scans", headers=_headers(),
                       files={"image": ("a.png", _png(), "image/png")}, data={**base, **data})


@pytest.mark.usefixtures("fake_ocr")
def test_scan_without_a_width_is_accepted():
    r = _post({})
    assert r.status_code == 201
    body = r.json()
    assert body["label_width_mm"] is None and body["scale_source"] == "none"
    assert client.get(f"/scans/{body['id']}", headers=_headers()).json()["scale_source"] == "none"
    assert client.get(f"/scans/{body['id']}/report?format=pdf", headers=_headers()).content.startswith(b"%PDF")


@pytest.mark.usefixtures("fake_ocr")
def test_blank_width_counts_as_no_width():
    assert _post({"label_width_mm": ""}).status_code == 201


@pytest.mark.usefixtures("fake_ocr")
def test_typed_width_is_still_stored():
    body = _post({"label_width_mm": "120"}).json()
    assert body["label_width_mm"] == 120.0 and body["scale_source"] == "manual"


@pytest.mark.usefixtures("fake_ocr")
def test_bad_width_is_still_rejected():
    r = _post({"label_width_mm": "0"})
    assert r.status_code == 422 and "label_width_mm" in r.json()["error"]["fields"]