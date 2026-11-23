import csv
import sys
from pathlib import Path

folder = Path(sys.argv[1])
images = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
sheet = folder / "labels.csv"
if sheet.exists():
    raise SystemExit("labels.csv already exists in that folder. Delete or rename it first.")

with sheet.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["filename", "product_name", "brand", "category", "label_width_mm"])
    for name in images:
        writer.writerow([name, "", "", "", ""])
print(f"Created {sheet} with {len(images)} photos. Now open it and fill in the columns.")