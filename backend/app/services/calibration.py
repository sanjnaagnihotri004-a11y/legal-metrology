from PIL import Image


def lines_outside(lines: list[dict], box: list[int]) -> list[dict]:
    """Drops text lines whose centre lies inside a box (kept for the pipeline; unused without a reference)."""
    def inside(line):
        cx = (line["bbox"][0] + line["bbox"][2]) / 2
        cy = (line["bbox"][1] + line["bbox"][3]) / 2
        return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]
    return [l for l in lines if not inside(l)]


def resolve_scale(image: Image.Image, lines: list[dict], label_width_mm: float | None,
                  width_px: int | None = None) -> dict:
    """The scale comes from the width the inspector types: the real width in mm of the area
    covered by the whole photo AS IT WAS TAKEN. width_px is that photo's pixel width; it differs
    from the image's own width when the photo was turned upright for reading.
    Without a typed width there is no scale, and the font check is skipped."""
    if label_width_mm:
        return {"mm_per_px": label_width_mm / (width_px or image.size[0]),
                "source": "manual", "reference_bbox": None}
    return {"mm_per_px": None, "source": "none", "reference_bbox": None}