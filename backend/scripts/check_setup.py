"""Checks which Step 14 / 14b / 15 edits are in place.
Run from the backend folder:  python -m scripts.check_setup
"""
import sqlite3
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def exists(path):
    return (BACKEND / path).exists()


def has(path, *texts):
    f = BACKEND / path
    if not f.exists():
        return False
    content = f.read_text(encoding="utf-8", errors="ignore")
    return all(t in content for t in texts)


def db_has_scale_column():
    db = BACKEND / "lm.db"
    if not db.exists():
        return False
    conn = sqlite3.connect(db)
    try:
        return "scale_source" in [row[1] for row in conn.execute("PRAGMA table_info(scans)")]
    finally:
        conn.close()


CHECKS = [
    # Step 14
    ("ocr.py has the lock", "Step 14, Part C, edit 2 (or paste the full ocr.py)",
     has("app/services/ocr.py", "_lock", '"image": pic')),
    ("extraction.py has parse_quantity", "Step 14, Part C, edit 3",
     has("app/services/extraction.py", "def parse_quantity")),
    ("engine.py check_r2 is the new version", "Step 14, Part C, edit 4",
     has("app/services/engine.py", "could not be read")),
    ("storage.py and scan_service.py exist", "Step 14, Parts D and E",
     exists("app/services/storage.py") and exists("app/services/scan_service.py")),
    ("conftest.py and test_api.py exist", "Step 14, Part G",
     exists("tests/conftest.py") and exists("tests/test_api.py")),
    ("old mock tests deleted", "Step 14, Part B (delete tests/test_scans.py and tests/test_step9.py)",
     not exists("tests/test_scans.py") and not exists("tests/test_step9.py")),
    ("old mock store deleted", "Step 15, Part B (delete app/mock_data/store.py)",
     not exists("app/mock_data/store.py")),
    # Step 14b
    ("calibration.py", "Step 14b, Part B", has("app/services/calibration.py", "def detect_card")),
    ("fontsize.py takes a scale", "Step 14b, Part C", has("app/services/fontsize.py", "scale: float | None")),
    ("pipeline.py uses the calibration", "Step 14b, Part D", has("app/services/pipeline.py", "calibration.resolve_scale")),
    ("annotate.py draws the card box", "Step 14b, Part E (both edits)",
     has("app/services/annotate.py", "reference_box", "SCALE: card")),
    ("models/scan.py has scale_source", "Step 14b, Part F, edit 1", has("app/models/scan.py", "scale_source")),
    ("schemas/scan.py has scale_source", "Step 14b, Part F, edit 2", has("app/schemas/scan.py", "scale_source: str | None")),
    ("scan_service.py: width is optional", "Step 14b, Part F, edit 3 (first change)",
     has("app/services/scan_service.py", "label_width_mm: float | None")),
    ("scan_service.py: saves the found width", "Step 14b, Part F, edit 3 (second change)",
     has("app/services/scan_service.py", 'analysis["label_width_mm"]', "scale_source=analysis")),
    ("scan_service.py: returns scale_source", "Step 14b, Part F, edit 3 (third change)",
     has("app/services/scan_service.py", '"scale_source": scan.scale_source')),
    ("routers/scans.py: width is optional", "Step 14b, Part F, edit 4",
     has("app/routers/scans.py", "label_width_mm: float | None = Form(None")),
    ("reports.py shows the scale source", "Step 14b, Part F, edit 5", has("app/services/reports.py", "Scale source")),
    ("bulk_scan.py is the new version", "paste the full bulk_scan.py I gave", has("scripts/bulk_scan.py", "width_mm = None")),
    ("probe_pipeline.py prints scale source", "Step 14b, Part G", has("scripts/probe_pipeline.py", "Scale source")),
    ("conftest.py has scale_source", "Step 14b, Part I, edit 1", has("tests/conftest.py", '"scale_source"')),
    ("test_calibration.py exists", "Step 14b, Part I, edit 2", exists("tests/test_calibration.py")),
    ("database has the scale_source column", "Step 14b, Part H (do this LAST, after every code edit)",
     db_has_scale_column()),
]

missing = [c for c in CHECKS if not c[2]]
for label, where, ok in CHECKS:
    print(f"{'OK     ' if ok else 'MISSING'}  {label}" + ("" if ok else f"   ->  {where}"))
print(f"\n{len(CHECKS) - len(missing)} of {len(CHECKS)} in place.")