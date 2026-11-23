
"""Checks which edits are in place (state after the table-layout step).
Run from the backend folder:  python -m scripts.check_setup
"""
import sqlite3
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def exists(path):
    return (BACKEND / path).exists()


def text(path):
    f = BACKEND / path
    return f.read_text(encoding="utf-8", errors="ignore") if f.exists() else ""


def has(path, *needles):
    t = text(path)
    return bool(t) and all(n in t for n in needles)


def lacks(path, *needles):
    t = text(path)
    return bool(t) and not any(n in t for n in needles)


def db_ok():
    db = BACKEND / "lm.db"
    if not db.exists():
        return False
    conn = sqlite3.connect(db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(scans)")]
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return "scale_source" in cols and users >= 2
    except sqlite3.Error:
        return False
    finally:
        conn.close()


CHECKS = [
    ("settings file .env exists", "create backend\\.env (see Step 4 of the early setup)", exists(".env")),
    ("virtual environment exists", "py -3.11 -m venv venv", exists("venv")),
    ("database has scale_source column and 2 users",
     "stop the server, then: Remove-Item lm.db ; python -m scripts.seed", db_ok()),
    # services
    ("storage.py and scan_service.py", "Step 14, Parts D and E",
     exists("app/services/storage.py") and exists("app/services/scan_service.py")),
    ("engine.py: new check_r2", "Step 14, Part C, edit 4", has("app/services/engine.py", "could not be read")),
    ("fontsize.py takes a scale", "fix 'Replace apply_font_check' (scale: float | None)",
     has("app/services/fontsize.py", "scale: float | None", "Label width was not provided")),
    ("calibration.py is the typed-width version", "paste the small calibration.py from the 'no card' message",
     has("app/services/calibration.py", "width_px") and lacks("app/services/calibration.py", "detect_card", "pytest")),
    ("annotate.py accepts reference_box", "Step 14b, Part E", has("app/services/annotate.py", "reference_box")),
    ("reports.py shows the scale source", "Step 14b, Part F, edit 5", has("app/services/reports.py", "Scale source")),
    # OCR and rotation
    ("ocr.py: lock", "paste the full ocr.py from the 'sideways photos' message", has("app/services/ocr.py", "_lock")),
    ("ocr.py: sideways detection", "paste the full ocr.py from the 'sideways photos' message",
     has("app/services/ocr.py", "_is_vertical", "original_width")),
    ("ocr.py: read_region (second look)", "the second-look message, Step 1", has("app/services/ocr.py", "def read_region")),
    ("pipeline.py: rotation and second look", "the second-look message, Step 2",
     has("app/services/pipeline.py", "add_tax_wording_from_second_look", 'width_px=ocr["original_width"]')),
    # extraction
    ("extraction.py: parse_quantity", "Step 14, Part C, edit 3", has("app/services/extraction.py", "def parse_quantity")),
    ("extraction.py: 'made in India by', 'when packed', bare price",
     "the long extraction.py from the Joy bottle message",
     has("app/services/extraction.py", "made\\s+", "when\\s*packed", "PRICE_DECIMAL_RE")),
    ("extraction.py: tax wording anywhere", "the 'incl. of all taxes' message, Edits 1 and 2",
     has("app/services/extraction.py", "class _TaxWording", "def _attach_tax_wording")),
    ("extraction.py: table layouts", "the coding-band message, Edits A, B and C",
     has("app/services/extraction.py", "def _find_mrp_by_column", "def _find_date_by_column", "1b) Table layout")),
    # API
    ("models/scan.py: scale_source", "Step 14b, Part F, edit 1", has("app/models/scan.py", "scale_source")),
    ("schemas/scan.py: scale_source", "Step 14b, Part F, edit 2", has("app/schemas/scan.py", "scale_source: str | None")),
    ("scan_service.py: optional width", "Step 14b, Part F, edit 3",
     has("app/services/scan_service.py", "label_width_mm: float | None", 'analysis["label_width_mm"]',
         '"scale_source": scan.scale_source')),
    ("routers/scans.py: optional width", "Step 14b, Part F, edit 4",
     has("app/routers/scans.py", "label_width_mm: float | None = Form(None")),
    # tests
    ("old mock tests and store deleted", "Remove-Item tests\\test_scans.py, tests\\test_step9.py, app\\mock_data\\store.py",
     not exists("tests/test_scans.py") and not exists("tests/test_step9.py") and not exists("app/mock_data/store.py")),
    ("conftest.py has scale_source", "Step 14b, Part I, edit 1", has("tests/conftest.py", '"scale_source"')),
    ("tests: api, engine, calibration", "Steps 14 and 14b and the 'no card' message",
     exists("tests/test_api.py") and exists("tests/test_engine.py")
     and has("tests/test_calibration.py", "test_typed_width_gives_the_scale")),
    ("tests: rotation", "the sideways-photo message, File 2",
     has("tests/test_rotation.py", "test_sideways_photo_gives_the_same_verdicts_as_upright")),
    ("tests: second look", "the second-look message, Step 3", exists("tests/test_second_look.py")),
    ("tests: table layouts", "the coding-band message, 'Add tests'",
     has("tests/test_extraction.py", "test_coding_band_mrp_and_date_are_found")),
    # scripts
    ("bulk_scan.py is the new version", "paste the full bulk_scan.py", has("scripts/bulk_scan.py", "width_mm = None")),
    ("probe scripts", "the sideways-photo message, Files 4 and 5",
     has("scripts/probe_pipeline.py", "rotation") and exists("scripts/probe_rotation.py")
     and has("scripts/probe_extract.py", "turned")),
    ("leftover probe_card.py removed", "Remove-Item scripts\\probe_card.py", not exists("scripts/probe_card.py")),
]

missing = [c for c in CHECKS if not c[2]]
for label, where, ok in CHECKS:
    print(f"{'OK     ' if ok else 'MISSING'}  {label}" + ("" if ok else f"   ->  {where}"))
print(f"\n{len(CHECKS) - len(missing)} of {len(CHECKS)} in place.")