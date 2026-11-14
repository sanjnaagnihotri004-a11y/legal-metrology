
import io
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from PIL import Image

# A throw-away database and storage folder, so tests never touch your real data.
# This must happen BEFORE the app is imported.
_TMP = Path(tempfile.mkdtemp(prefix="lm_tests_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(_TMP / "storage")

from app.errors import AppError                 # noqa: E402
from app.services import annotate, pipeline     # noqa: E402
from app.services import engine as rule_engine  # noqa: E402
from scripts.seed import seed                   # noqa: E402

seed()    # creates the tables, the 6 rules and the two dev users in the test database


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)


def _fake_fields():
    def f(value, bbox, conf=0.95):
        return {"found": True, "value": value, "confidence": conf, "bbox": bbox}

    net = f("Net Wt. 200 g", [115, 299, 346, 346])
    net.update(quantity=200.0, unit="g", font_height_mm=2.0, min_font_height_mm=1.0)
    return {
        "manufacturer_name_address": f("Mfd. by CrunchCo Foods, Indore 452001", [96, 902, 647, 938]),
        "net_quantity": net,
        "mrp": f("MRP Rs. 50.00", [116, 402, 356, 441]),        # no tax wording -> LM-R3 fails
        "mfg_date": {"found": False, "value": None, "confidence": None, "bbox": None},   # LM-R4 fails
        "consumer_care": f("Call 1800-123-456", [97, 1005, 345, 1034]),
    }


@pytest.fixture
def fake_ocr(monkeypatch):
    """Replaces the slow OCR step with a fixed reading, but still uses the REAL rule engine,
    annotation, database and files. Any image narrower than 20 px simulates 'no readable text'."""

    def fake_analyze(image_bytes, label_width_mm):
        pic = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if pic.size[0] < 20:
            raise AppError(422, "OCR_NO_TEXT",
                           "No readable text found. Retake the photo: flat, well lit and in focus.")
        fields = _fake_fields()
        results = rule_engine.evaluate(fields)
        status, score, violations = rule_engine.summarize(results, 0.9)
        return {
            "status": status, "score": score, "violations_count": violations,
            "extracted_fields": fields, "rule_results": results,
            "ocr_text": "CrunchCo Masala Peanuts Net Wt. 200 g MRP Rs. 50.00",
            "ocr_confidence": 0.9,
            "image_width_px": pic.size[0], "image_height_px": pic.size[1],
            "image": pic, "annotated_image": annotate.annotate(pic, results),
            "font_info": {"mm_per_px": None, "pdp_area_cm2": None, "note": None},
        }

    monkeypatch.setattr(pipeline, "analyze", fake_analyze)