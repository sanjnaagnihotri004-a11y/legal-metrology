import io
import re
import threading
from statistics import mean

import numpy as np
from PIL import Image, ImageOps
from rapidocr import RapidOCR

from app.errors import AppError
from app.services.extraction import extract_fields

_engine = None
_lock = threading.Lock()

# Below this much trustworthy text, the photo may be sideways, upside down or too blurry to read.
GOOD_ENOUGH = 60


def _get_engine():
    """Load the OCR engine once, on first use (loading takes a few seconds)."""
    global _engine
    if _engine is None:
        _engine = RapidOCR()
    return _engine


def _read_lines(pic: Image.Image) -> list[dict]:
    bgr = np.array(pic)[:, :, ::-1].copy()  # RapidOCR expects BGR colour order
    with _lock:   # the OCR engine is not safe to share between simultaneous requests
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
    return lines


def _quality(lines: list[dict]) -> float:
    """How much trustworthy text was read: characters weighted by confidence squared."""
    return sum(len(re.sub(r"\W", "", l["text"])) * l["confidence"] ** 2
               for l in lines if l["confidence"] >= 0.5)


def _is_vertical(lines: list[dict]) -> bool:
    """True when most of the substantial text lines are taller than they are wide (a sideways photo)."""
    solid = [l for l in lines if l["confidence"] >= 0.5 and len(re.sub(r"\W", "", l["text"])) >= 4]
    if len(solid) < 2:
        return False
    tall = sum(1 for l in solid
               if (l["bbox"][3] - l["bbox"][1]) > 1.5 * (l["bbox"][2] - l["bbox"][0]))
    return tall >= 0.6 * len(solid)


def _reading(pic: Image.Image, angle: int) -> dict:
    lines = _read_lines(pic)
    lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))     # top to bottom, then left to right
    found = sum(1 for f in extract_fields(lines).values() if f["found"])
    return {"angle": angle, "pic": pic, "lines": lines, "found": found,
            "quality": _quality(lines), "vertical": _is_vertical(lines)}


def _better(new: dict, old: dict) -> bool:
    """Is this orientation clearly better than the best one found so far?"""
    if old["vertical"] and not new["vertical"]:
        # text that now reads horizontally wins, unless it reads clearly worse
        return new["found"] >= old["found"] and new["quality"] >= 0.7 * old["quality"]
    if new["found"] != old["found"]:
        return new["found"] > old["found"]               # more declarations found
    if old["angle"] == 0:
        return new["quality"] > old["quality"] * 1.3 + 5  # don't turn a fine photo for a small gain
    return new["quality"] > old["quality"]               # between two turned copies any gain counts


def _best_reading(pic: Image.Image) -> dict:
    best = _reading(pic, 0)
    if not (best["vertical"] or best["quality"] < GOOD_ENOUGH or best["found"] <= 1):
        return best                                       # a normal photo: one reading is enough
    angles = (90, 270) if best["vertical"] else (90, 270, 180)   # degrees counter-clockwise
    for angle in angles:
        candidate = _reading(pic.rotate(angle, expand=True), angle)
        if _better(candidate, best):
            best = candidate
    return best


def read_label(image_bytes: bytes) -> dict:
    """Run OCR on an image. Returns lines (text, bbox, confidence) sorted top to bottom.
    A sideways photo is turned upright first; 'image' is the upright copy and 'rotation' says how far."""
    try:
        pic = Image.open(io.BytesIO(image_bytes))
        pic = ImageOps.exif_transpose(pic).convert("RGB")  # fixes sideways phone photos
    except Exception:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", "File is not a valid image")

    original_width = pic.size[0]
    best = _best_reading(pic)
    lines = best["lines"]
    if not lines:
        raise AppError(422, "OCR_NO_TEXT",
                       "No readable text found. Retake the photo: flat, well lit and in focus.")

    return {
        "lines": lines,
        "text": "\n".join(l["text"] for l in lines),
        "confidence": round(mean(l["confidence"] for l in lines), 2),
        "width": best["pic"].size[0],
        "height": best["pic"].size[1],
        "original_width": original_width,
        "rotation": best["angle"],
        "image": best["pic"],
    }



def read_region(pic: Image.Image, bbox: list[int], angle: int = 0, zoom: float = 2.5) -> list[dict]:
    """Second look: cut out the area around a box, enlarge it, boost the contrast and read it again.
    Small or faint print is often missed on the first pass over a whole photo."""
    x1, y1, x2, y2 = bbox
    pad_y = max(int((y2 - y1) * 3), 40)
    pad_x = max(int((x2 - x1) * 0.5), 40)
    area = (max(0, x1 - pad_x), max(0, y1 - pad_y),
            min(pic.size[0], x2 + pad_x), min(pic.size[1], y2 + pad_y))
    crop = pic.crop(area)
    crop = crop.resize((max(1, int(crop.size[0] * zoom)), max(1, int(crop.size[1] * zoom))), Image.LANCZOS)
    crop = ImageOps.autocontrast(crop, cutoff=1)
    if angle:
        crop = crop.rotate(angle, expand=True)
    return _read_lines(crop)