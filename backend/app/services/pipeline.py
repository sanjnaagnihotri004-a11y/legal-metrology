
from app.services import annotate, engine, fontsize
from app.services.extraction import extract_fields
from app.services.ocr import read_label


def analyze(image_bytes: bytes, label_width_mm: float) -> dict:
    """The whole scan: OCR, extraction, font check, rules, score, annotated image."""
    ocr = read_label(image_bytes)
    fields = extract_fields(ocr["lines"])

    try:
        font_info = fontsize.apply_font_check(fields, ocr["lines"], ocr["image"], label_width_mm)
    except Exception:       # a measuring problem must never lose the whole scan
        font_info = {"mm_per_px": None, "pdp_area_cm2": None,
                     "note": "Numeral height could not be measured"}

    results = engine.evaluate(fields, ctx=font_info)
    status, score, violations = engine.summarize(results, ocr["confidence"])
    return {
        "status": status,
        "score": score,
        "violations_count": violations,
        "extracted_fields": fields,
        "rule_results": results,
        "ocr_text": ocr["text"],
        "ocr_confidence": ocr["confidence"],
        "image_width_px": ocr["width"],
        "image_height_px": ocr["height"],
        "annotated_image": annotate.annotate(ocr["image"], results),
        "font_info": font_info,
    }