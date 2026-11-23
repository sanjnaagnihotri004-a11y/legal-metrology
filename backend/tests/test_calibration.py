import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services.calibration import resolve_scale
from app.services.pipeline import analyze

SAMPLE = Path(__file__).resolve().parent.parent / "app" / "mock_data" / "sample.jpg"


def test_typed_width_gives_the_scale():
    s = resolve_scale(Image.new("RGB", (1600, 1200)), [], 120.0)
    assert s["source"] == "manual" and s["reference_bbox"] is None
    assert s["mm_per_px"] == pytest.approx(0.075)


def test_no_width_means_no_scale():
    s = resolve_scale(Image.new("RGB", (800, 600)), [], None)
    assert s == {"mm_per_px": None, "source": "none", "reference_bbox": None}


# ---------- the whole pipeline with real OCR (a few seconds each) ----------

def test_pipeline_without_width_skips_only_the_font_check():
    out = analyze(SAMPLE.read_bytes(), None)
    st = {r["rule_id"]: r["status"] for r in out["rule_results"]}
    assert out["scale_source"] == "none" and out["label_width_mm"] is None
    assert st["LM-R6"] == "not_checked"
    assert "width" in out["font_info"]["note"].lower()
    assert st["LM-R3"] == "fail"            # the other rules still work


def test_pipeline_with_width_measures_the_numerals():
    out = analyze(SAMPLE.read_bytes(), 120.0)
    assert out["scale_source"] == "manual"
    assert out["label_width_mm"] == pytest.approx(120.0, abs=0.2)
    assert out["extracted_fields"]["net_quantity"]["font_height_mm"] is not None


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
    base = {"product_name": "Width Test", "brand": "TestCo", "category": "food"}
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
def test_typed_width_is_stored():
    body = _post({"label_width_mm": "120"}).json()
    assert body["label_width_mm"] == 120.0 and body["scale_source"] == "manual"


@pytest.mark.usefixtures("fake_ocr")
def test_bad_width_is_rejected():
    r = _post({"label_width_mm": "0"})
    assert r.status_code == 422 and "label_width_mm" in r.json()["error"]["fields"]