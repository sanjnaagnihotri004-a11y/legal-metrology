
import io

from PIL import Image, ImageDraw, ImageFont

COLORS = {"pass": (30, 160, 60), "fail": (210, 40, 40), "not_checked": (240, 150, 0)}
RANK = {"pass": 0, "not_checked": 1, "fail": 2}


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _fit(draw, text: str, font, max_width: float) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "...", font=font) > max_width:
        text = text[:-1]
    return text + "..."


def annotate(image: Image.Image, results: list[dict]) -> bytes:
    """Draws a box per rule (green pass, red fail, orange needs-review).
    Problems with nothing to point at (a missing declaration) go in a banner above the photo."""
    pic = image.convert("RGB")
    width, height = pic.size
    size = max(14, width // 45)
    pad = size // 2
    font = _font(size)
    line_width = max(2, width // 300)

    notes = [f"{r['rule_id']}: {r['message']}"
             for r in results if r["status"] != "pass" and not r.get("bbox")]
    banner_h = pad + (len(notes) + 1) * (size + pad) if notes else 0

    canvas = Image.new("RGB", (width, height + banner_h), (255, 255, 255))
    canvas.paste(pic, (0, banner_h))
    d = ImageDraw.Draw(canvas)

    if notes:
        d.rectangle([0, 0, width, banner_h], fill=(120, 20, 20))
        y = pad
        d.text((pad, y), "NOT FOUND / NEEDS ATTENTION:", fill="white", font=font)
        for note in notes:
            y += size + pad
            d.text((pad, y), _fit(d, note, font, width - 2 * pad), fill="white", font=font)

    groups: dict[tuple, dict] = {}      # rules sharing one box are drawn once
    for r in results:
        box = r.get("bbox")
        if not box:
            continue
        g = groups.setdefault(tuple(box), {"ids": [], "status": "pass"})
        g["ids"].append(r["rule_id"])
        if RANK[r["status"]] > RANK[g["status"]]:
            g["status"] = r["status"]

    for (x1, y1, x2, y2), g in groups.items():
        color = COLORS[g["status"]]
        top, bottom = y1 + banner_h, y2 + banner_h
        d.rectangle([x1, top, x2, bottom], outline=color, width=line_width)
        label = ", ".join(g["ids"])
        text_w = d.textlength(label, font=font)
        label_y = top - size - 4
        if label_y < banner_h:
            label_y = bottom + 2
        d.rectangle([x1, label_y, x1 + text_w + 8, label_y + size + 4], fill=color)
        d.text((x1 + 4, label_y + 1), label, fill="white", font=font)

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=88)
    return buf.getvalue()