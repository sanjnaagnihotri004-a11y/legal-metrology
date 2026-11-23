from statistics import mean

from app.services import annotate, calibration, engine, fontsize
from app.services.extraction import INCL_TAX_RE, extract_fields
from app.services.ocr import read_label, read_region


def add_tax_wording_from_second_look(image, fields) -> None:
    """If an MRP was found without 'inclusive of all taxes', zoom in around it and read that area again."""
    mrp = fields["mrp"]
    if not mrp["found"] or INCL_TAX_RE.search(mrp["value"]):
        return
    for angle in (0, 90, 270):
        extra = read_region(image, mrp["bbox"], angle)
        for size in (1, 2):                      # the wording may be split over two lines
            for i in range(len(extra) - size + 1):
                chunk = extra[i:i + size]
                text = " ".join(l["text"] for l in chunk)
                if INCL_TAX_RE.search(text):
                    mrp["value"] += " " + text
                    mrp["confidence"] = round(
                        (mrp["confidence"] + mean(l["confidence"] for l in chunk)) / 2, 2)
                    return


def analyze(image_bytes: bytes, label_width_mm: float | None = None) -> dict:
    """The whole scan: OCR, scale, extraction, font check, rules, score, annotated image."""
    ocr = read_label(image_bytes)
    image = ocr["image"]                  # upright copy: everything below works on this
    lines = ocr["lines"]

    # The typed width describes the photo as taken. Turning the picture upright does not change
    # the size of a pixel, so the scale uses the ORIGINAL photo width.
    scale = calibration.resolve_scale(image, lines, label_width_mm, width_px=ocr["original_width"])

    fields = extract_fields(lines)
    try:
        add_tax_wording_from_second_look(image, fields)
    except Exception:       # a failed second look must never lose the whole scan
        pass

    try:
        font_info = fontsize.apply_font_check(fields, lines, image, scale["mm_per_px"])
    except Exception:       # a measuring problem must never lose the whole scan
        font_info = {"mm_per_px": None, "pdp_area_cm2": None,
                     "note": "Numeral height could not be measured"}
    font_info["scale_source"] = scale["source"]

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
        "image": image,
        "annotated_image": annotate.annotate(image, results),
        "font_info": font_info,
        "label_width_mm": round(label_width_mm, 1) if label_width_mm else None,
        "scale_source": scale["source"],
        "rotation": ocr["rotation"],
    }