import io
from statistics import mean

import numpy as np
from PIL import Image, ImageOps
from rapidocr import RapidOCR

from app.errors import AppError

_engine = None


def _get_engine():
    """Load the OCR engine once, on first use (loading takes a few seconds)."""
    global _engine
    if _engine is None:
        _engine = RapidOCR()
    return _engine


def read_label(image_bytes: bytes) -> dict:
    """Run OCR on an image. Returns lines (text, bbox, confidence) sorted top to bottom."""
    try:
        pic = Image.open(io.BytesIO(image_bytes))
        pic = ImageOps.exif_transpose(pic).convert("RGB")  # fixes sideways phone photos
    except Exception:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", "File is not a valid image")

    width, height = pic.size
    bgr = np.array(pic)[:, :, ::-1].copy()  # RapidOCR expects BGR colour order

    result = _get_engine()(bgr)
    texts = getattr(result, "txts", None)

    lines = []
    if texts:
        for box, text, score in zip(result.boxes, texts, result.scores):
            if not text.strip():
                continue
            xs = [int(p[0]) for p in box]
            ys = [int(p[1]) for p in box]
            lines.append({
                "text": text.strip(),
                "bbox": [min(xs), min(ys), max(xs), max(ys)],  # [x1, y1, x2, y2]
                "confidence": round(float(score), 2),
            })

    if not lines:
        raise AppError(422, "OCR_NO_TEXT",
                       "No readable text found. Retake the photo: flat, well lit and in focus.")

    lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))  # top to bottom, then left to right
    return {
        "lines": lines,
        "text": "\n".join(l["text"] for l in lines),
        "confidence": round(mean(l["confidence"] for l in lines), 2),
        "width": width,
        "height": height,
        "image": pic,
    }