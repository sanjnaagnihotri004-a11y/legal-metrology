
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "app" / "mock_data"
W, H = 1600, 1200


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def make_label(annotated):
    img = Image.new("RGB", (W, H), (250, 244, 225))
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, W - 40, H - 40], outline=(120, 80, 30), width=8)
    d.text((120, 100), "CrunchCo", fill=(150, 40, 20), font=font(100))
    d.text((120, 210), "Masala Peanuts", fill=(30, 30, 30), font=font(60))
    d.text((120, 300), "Net Wt. 200 g", fill=(0, 0, 0), font=font(36))
    d.text((120, 400), "MRP Rs. 50.00", fill=(0, 0, 0), font=font(36))
    d.text((100, 900), "Mfd. by CrunchCo Foods, Indore 452001", fill=(0, 0, 0), font=font(30))
    d.text((100, 1000), "Call 1800-123-456", fill=(0, 0, 0), font=font(30))

    if annotated:
        green, red = (30, 160, 60), (210, 40, 40)
        for box in ([120, 300, 400, 340], [100, 900, 700, 980], [100, 1000, 500, 1040]):
            d.rectangle(box, outline=green, width=5)
        d.rectangle([120, 400, 380, 440], outline=red, width=6)
        d.text((400, 405), "LM-R3: not inclusive of all taxes", fill=red, font=font(30))
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make_label(False).save(OUT / "sample.jpg", quality=85)
    make_label(True).save(OUT / "sample_annotated.jpg", quality=85)
    print("Created sample.jpg and sample_annotated.jpg in", OUT)