
"""Builds the example Scan from the frontend doc (Section 5.5) and prints it."""
from app.schemas.scan import Scan

example = {
    "id": 42,
    "product": {"id": 7, "name": "Masala Peanuts", "brand": "CrunchCo", "barcode": None, "category": "food"},
    "inspector": {"id": 2, "name": "Asha Verma"},
    "created_at": "2026-11-10T09:15:30Z",
    "status": "non_compliant",
    "score": 66.7,
    "corrected": False,
    "notes": None,
    "label_width_mm": 120.0,
    "image_width_px": 1600,
    "image_height_px": 1200,
    "image_url": "/scans/42/image",
    "annotated_image_url": "/scans/42/annotated-image",
    "ocr_text": "CrunchCo Masala Peanuts Net Wt. 200 g",
    "ocr_confidence": 0.87,
    "extracted_fields": {
        "manufacturer_name_address": {"found": True, "value": "Mfd. by CrunchCo Foods, Indore 452001", "confidence": 0.91, "bbox": [100, 900, 700, 980]},
        "net_quantity": {"found": True, "value": "Net Wt. 200 g", "confidence": 0.95, "bbox": [120, 300, 400, 340],
                         "quantity": 200.0, "unit": "g", "font_height_mm": 1.2, "min_font_height_mm": 2.0},
        "mrp": {"found": True, "value": "MRP Rs. 50.00", "confidence": 0.9, "bbox": [120, 400, 380, 440]},
        "mfg_date": {"found": False, "value": None, "confidence": None, "bbox": None},
        "consumer_care": {"found": True, "value": "Call 1800-123-456", "confidence": 0.88, "bbox": [100, 1000, 500, 1040]},
    },
    "rule_results": [
        {"rule_id": "LM-R3", "clause": "Rule 6(1)(e)", "title": "MRP declaration",
         "description": "MRP must be declared inclusive of all taxes", "severity": "critical",
         "status": "fail", "message": "MRP found but inclusive of all taxes is missing",
         "bbox": [120, 400, 380, 440]},
    ],
    "violations_count": 2,
    "evidence": [
        {"id": 1, "scan_id": 42, "file_url": "/evidence/1/file", "note": "Close-up of MRP",
         "uploaded_by": "Asha Verma", "created_at": "2026-11-10T09:20:00Z"},
    ],
}

scan = Scan.model_validate(example)
print(scan.model_dump_json(indent=2))