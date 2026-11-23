import sys
from pathlib import Path

from PIL import Image, ImageOps

from app.services.ocr import _reading

path = Path(sys.argv[1])
pic = ImageOps.exif_transpose(Image.open(path)).convert("RGB")

for angle in (0, 90, 270, 180):
    turned = pic.rotate(angle, expand=True) if angle else pic
    r = _reading(turned, angle)
    print(f"\n=== turned {angle:>3} degrees | {len(r['lines'])} lines | quality {r['quality']:.0f} "
          f"| vertical text: {r['vertical']} | declarations found: {r['found']}")
    for line in r["lines"][:6]:
        print(f"     {line['confidence']:.2f}  {line['text']}")