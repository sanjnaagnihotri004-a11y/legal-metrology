"""Scan a whole folder of label photos through the real pipeline.

Usage (from the backend folder):
    python -m scripts.bulk_scan "D:\\path\\to\\photos" --spread-days 10
    python -m scripts.bulk_scan "D:\\path\\to\\photos" --mm-per-px 0.06

The folder must contain labels.csv with these columns:
    filename, product_name, brand, category        (barcode and label_width_mm are optional)

How the scale (millimetres per pixel) is found, per photo:
  1. label_width_mm in the CSV row, if you filled it in
  2. otherwise --mm-per-px, if you gave it (a fixed camera setup)
  3. otherwise the pipeline looks for a bank/ID card in the photo
"""
import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import get_args

from PIL import Image, ImageOps

from app.db import SessionLocal
from app.errors import AppError
from app.models import Scan, User
from app.schemas.common import Category
from app.services import scan_service

CATEGORIES = set(get_args(Category))


def main():
    parser = argparse.ArgumentParser(description="Scan a folder of label photos.")
    parser.add_argument("folder")
    parser.add_argument("--user", default="inspector@lm.test", help="who the scans belong to")
    parser.add_argument("--spread-days", type=int, default=0,
                        help="spread the scan dates over the last N days (makes dashboard charts richer)")
    parser.add_argument("--mm-per-px", type=float, default=None,
                        help="camera calibration, used when label_width_mm is blank")
    args = parser.parse_args()

    folder = Path(args.folder)
    sheet = folder / "labels.csv"
    if not sheet.exists():
        raise SystemExit(f"labels.csv not found in {folder}")

    db = SessionLocal()
    user = db.query(User).filter(User.email == args.user).first()
    if user is None:
        raise SystemExit(f"User {args.user} not found. Run: python -m scripts.seed")

    done = failed = 0
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = row["filename"].strip()
            path = folder / name
            problem = None
            if not path.exists():
                problem = "file not found"
            elif row["category"].strip() not in CATEGORIES:
                problem = f"category must be one of {sorted(CATEGORIES)}"
            if problem:
                print(f"SKIPPED  {name:<32} {problem}")
                failed += 1
                continue

            width_text = (row.get("label_width_mm") or "").strip()
            try:
                if width_text:
                    width_mm = float(width_text)
                elif args.mm_per_px:
                    with Image.open(path) as im:
                        width_mm = ImageOps.exif_transpose(im).size[0] * args.mm_per_px
                else:
                    width_mm = None          # the pipeline looks for a bank card in the photo
            except Exception as e:
                print(f"SKIPPED  {name:<32} {e}")
                failed += 1
                continue

            try:
                result = scan_service.create_scan(
                    db, user,
                    image_bytes=path.read_bytes(),
                    product_name=row["product_name"].strip(),
                    brand=row["brand"].strip(),
                    category=row["category"].strip(),
                    label_width_mm=width_mm,
                    barcode=(row.get("barcode") or "").strip() or None,
                    notes=None,
                )
            except AppError as e:
                print(f"FAILED   {name:<32} {e.code}: {e.message}")
                failed += 1
                continue

            if args.spread_days:
                when = datetime.now(timezone.utc) - timedelta(
                    days=random.randint(0, args.spread_days), hours=random.randint(0, 12))
                scan = db.get(Scan, result["id"])
                scan.created_at = when.replace(tzinfo=None)    # the database stores UTC without a zone
                db.commit()

            print(f"{name:<32} {result['status']:<14} score {result['score']:>5}   "
                  f"violations {result['violations_count']}   scale {result['scale_source']}")
            done += 1

    db.close()
    print(f"\nDone: {done} scanned, {failed} skipped or failed.")


if __name__ == "__main__":
    main()