import re
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

RULES_FILE = Path(__file__).resolve().parent.parent.parent / "rules" / "rules.yaml"


def _load_table() -> list[dict]:
    data = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))
    rows = data["font_height_table"]
    return sorted(rows, key=lambda r: float("inf") if r["max_area_cm2"] is None else r["max_area_cm2"])


FONT_TABLE = _load_table()


def min_height_mm(area_cm2: float) -> float:
    """Minimum numeral height (normal printing) for a principal display panel of this area."""
    for row in FONT_TABLE:
        if row["max_area_cm2"] is None or area_cm2 <= row["max_area_cm2"]:
            return float(row["normal_mm"])
    return float(FONT_TABLE[-1]["normal_mm"])


def mm_per_px(label_width_mm: float, image_width_px: int) -> float:
    """Calibration: the photo's full width covers label_width_mm in real life."""
    return label_width_mm / image_width_px


def estimate_pdp_area_cm2(lines: list[dict], scale: float) -> float:
    """Estimate the panel area from the extent of all detected text."""
    x1 = min(l["bbox"][0] for l in lines)
    y1 = min(l["bbox"][1] for l in lines)
    x2 = max(l["bbox"][2] for l in lines)
    y2 = max(l["bbox"][3] for l in lines)
    return ((x2 - x1) * scale) * ((y2 - y1) * scale) / 100.0   # mm x mm -> cm2


def measure_numeral_height_px(image: Image.Image, bbox: list[int]) -> float | None:
    """Height in pixels of the tall glyphs (digits, capitals) inside a text line's box."""
    margin = 3
    width, height = image.size
    x1, y1, x2, y2 = bbox
    crop = image.crop((max(0, x1 - margin), max(0, y1 - margin),
                       min(width, x2 + margin), min(height, y2 + margin))).convert("L")
    gray = np.array(crop)
    if gray.shape[0] < 8 or gray.shape[1] < 8:
        return None

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if (binary == 255).mean() > 0.5:           # make the text the minority colour (white on black)
        binary = cv2.bitwise_not(binary)

    count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    heights = []
    for i in range(1, count):
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 6 or h >= gray.shape[0] - 1:   # skip specks and background that spans the whole crop
            continue
        heights.append(h)
    if not heights:
        return None
    tallest = max(heights)
    tall = [h for h in heights if h >= 0.6 * tallest]   # ignore small letters, dots and noise
    return float(np.median(tall))


def _numeral_line(net: dict, lines: list[dict]) -> dict | None:
    """The OCR line that holds the quantity digits (e.g. '100 g', not 'Net Wt.:')."""
    x1, y1, x2, y2 = net["bbox"]
    inside = [
        l for l in lines
        if l["bbox"][0] >= x1 - 2 and l["bbox"][1] >= y1 - 2
        and l["bbox"][2] <= x2 + 2 and l["bbox"][3] <= y2 + 2
        and re.search(r"\d", l["text"])
    ]
    if not inside:
        return None
    wanted = f"{net['quantity']:g}".replace(".", "")
    for line in inside:
        if wanted in re.sub(r"\D", "", line["text"]):
            return line
    return inside[0]


def apply_font_check(fields: dict, lines: list[dict], image: Image.Image, label_width_mm: float) -> dict:
    """Fills font_height_mm and min_font_height_mm in fields['net_quantity'] (in place)."""
    info = {"mm_per_px": None, "pdp_area_cm2": None, "note": None}
    net = fields["net_quantity"]
    if not net["found"]:
        info["note"] = "Net quantity not found, so numeral height could not be checked"
        return info

    scale = mm_per_px(label_width_mm, image.size[0])
    area = estimate_pdp_area_cm2(lines, scale)
    info["mm_per_px"] = round(scale, 5)
    info["pdp_area_cm2"] = round(area, 1)

    line = _numeral_line(net, lines)
    height_px = measure_numeral_height_px(image, line["bbox"]) if line else None
    if height_px is None:
        info["note"] = "Numeral height could not be measured in this photo"
        return info

    net["font_height_mm"] = round(height_px * scale, 2)
    net["min_font_height_mm"] = min_height_mm(area)
    return info