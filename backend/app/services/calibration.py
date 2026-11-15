import cv2
import numpy as np
from PIL import Image

# ISO/IEC 7810 ID-1: bank cards, ID cards, driving licences
CARD_LONG_MM = 85.60
CARD_SHORT_MM = 53.98
CARD_RATIO = CARD_LONG_MM / CARD_SHORT_MM          # about 1.586

RATIO_TOLERANCE = 0.12        # a tilted card looks a little distorted
MIN_RECTANGULARITY = 0.85     # how well the outline fills its rectangle
MIN_AREA_FRACTION = 0.005     # the card must cover 0.5% to 35% of the photo
MAX_AREA_FRACTION = 0.35
MAX_TEXT_LINES_INSIDE = 3     # a label panel is full of text; a card has very little
PLAUSIBLE_WIDTH_MM = (30.0, 2000.0)   # the whole photo must cover a believable real-world width


def _center_inside(line: dict, box: list[int]) -> bool:
    cx = (line["bbox"][0] + line["bbox"][2]) / 2
    cy = (line["bbox"][1] + line["bbox"][3]) / 2
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


def lines_outside(lines: list[dict], box: list[int]) -> list[dict]:
    """Drops text lines that sit on the card (bank name, card number) so they never reach the extractors."""
    return [l for l in lines if not _center_inside(l, box)]


def detect_card(image: Image.Image, lines: list[dict]) -> dict | None:
    """Looks for a card-shaped rectangle. Returns {'mm_per_px', 'bbox', 'confidence'} or None."""
    gray = np.array(image.convert("L"))
    height, width = gray.shape
    shrink = min(1.0, 1000.0 / max(height, width))         # work on a smaller copy for speed
    small = cv2.resize(gray, (int(width * shrink), int(height * shrink))) if shrink < 1.0 else gray

    edges = cv2.Canny(cv2.GaussianBlur(small, (5, 5), 0), 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    total = small.shape[0] * small.shape[1]
    best, best_score = None, 0.0
    for contour in contours:
        area = cv2.contourArea(contour)
        if not (MIN_AREA_FRACTION * total <= area <= MAX_AREA_FRACTION * total):
            continue
        rect = cv2.minAreaRect(contour)
        side_a, side_b = rect[1]
        long_side, short_side = max(side_a, side_b), min(side_a, side_b)
        if short_side < 5:
            continue

        error = abs(long_side / short_side - CARD_RATIO) / CARD_RATIO
        if error > RATIO_TOLERANCE:
            continue
        rectangularity = min(1.0, area / (side_a * side_b))
        if rectangularity < MIN_RECTANGULARITY:
            continue

        corners = cv2.boxPoints(rect) / shrink              # back to full-size pixel coordinates
        box = [int(corners[:, 0].min()), int(corners[:, 1].min()),
               int(corners[:, 0].max()), int(corners[:, 1].max())]
        if sum(1 for l in lines if _center_inside(l, box)) > MAX_TEXT_LINES_INSIDE:
            continue

        # average the two estimates (long side and short side) to soften perspective error
        scale = (CARD_LONG_MM / (long_side / shrink) + CARD_SHORT_MM / (short_side / shrink)) / 2
        if not (PLAUSIBLE_WIDTH_MM[0] <= scale * width <= PLAUSIBLE_WIDTH_MM[1]):
            continue

        score = rectangularity * (1 - 0.5 * error / RATIO_TOLERANCE)
        if score > best_score:
            best_score = score
            best = {"mm_per_px": scale, "bbox": box, "confidence": round(score, 2)}
    return best


def resolve_scale(image: Image.Image, lines: list[dict], label_width_mm: float | None) -> dict:
    """Where does the millimetres-per-pixel figure come from?
    1) a width typed by the inspector, 2) a card found in the photo, 3) nowhere (font check is skipped)."""
    if label_width_mm:
        return {"mm_per_px": label_width_mm / image.size[0], "source": "manual", "reference_bbox": None}
    card = detect_card(image, lines)
    if card:
        return {"mm_per_px": card["mm_per_px"], "source": "card", "reference_bbox": card["bbox"]}
    return {"mm_per_px": None, "source": "none", "reference_bbox": None}