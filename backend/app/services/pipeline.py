from statistics import mean

from app.services import annotate, calibration, engine, fontsize
from app.services.extraction import extract_fields
from app.services.ocr import read_label


def analyze(image_bytes: bytes, label_width_mm: float | None = None) -> dict:
    """The whole scan: OCR, scale, extraction, font check, rules, score, annotated image."""
    ocr = read_label(image_bytes)
    image = ocr["image"]
    scale = calibration.resolve_scale(image, ocr["lines"], label_width_mm)

    lines = ocr["lines"]
    if scale["reference_bbox"]:       # ignore anything printed on the card itself
        lines = calibration.lines_outside(lines, scale["reference_bbox"]) or lines

    fields = extract_fields(lines)
    try:
        font_info = fontsize.apply_font_check(fields, lines, image, scale["mm_per_px"])
    except Exception:       # a measuring problem must never lose the whole scan
        font_info = {"mm_per_px": None, "pdp_area_cm2": None,
                     "note": "Numeral height could not be measured"}
    font_info["scale_source"] = scale["source"]

    results = engine.evaluate(fields, ctx=font_info)
    confidence = round(mean(l["confidence"] for l in lines), 2)
    status, score, violations = engine.summarize(results, confidence)

    mm_per_px = scale["mm_per_px"]
    return {
        "status": status,
        "score": score,
        "violations_count": violations,
        "extracted_fields": fields,
        "rule_results": results,
        "ocr_text": "\n".join(l["text"] for l in lines),
        "ocr_confidence": confidence,
        "image_width_px": ocr["width"],
        "image_height_px": ocr["height"],
        "image": image,
        "annotated_image": annotate.annotate(image, results, scale["reference_bbox"]),
        "font_info": font_info,
        "label_width_mm": round(mm_per_px * ocr["width"], 1) if mm_per_px else None,
        "scale_source": scale["source"],
    }