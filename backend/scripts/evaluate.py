"""Compares the app's verdicts with YOUR verdicts, photo by photo, and prints precision and recall.

Step 1 (once):  python -m scripts.evaluate "D:\\label_photos" --template
                creates ground_truth.csv. Fill it in by LOOKING AT EACH PHOTO, not at the app's output.
Step 2:         python -m scripts.evaluate "D:\\label_photos"

Rules judged: LM-R1 to LM-R5 (they do not depend on the photo scale).
A violation (fail) is the "positive" class.
"""
import argparse
import csv
from pathlib import Path

from app.errors import AppError
from app.services.pipeline import analyze

RULE_IDS = ["LM-R1", "LM-R2", "LM-R3", "LM-R4", "LM-R5"]
COLUMNS = ["R1", "R2", "R3", "R4", "R5"]
IMAGE_TYPES = {".jpg", ".jpeg", ".png"}


def pct(numerator, denominator):
    return f"{numerator / denominator * 100:.0f}%" if denominator else "n/a"


def make_template(folder: Path) -> None:
    sheet = folder / "ground_truth.csv"
    if sheet.exists():
        raise SystemExit(f"{sheet} already exists. Delete or rename it first.")
    names = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in IMAGE_TYPES)
    with sheet.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["filename"] + COLUMNS)
        for name in names:
            writer.writerow([name] + [""] * len(COLUMNS))
    print(f"Created {sheet} with {len(names)} photos. Fill R1 to R5 with pass or fail for each photo.")


def evaluate(folder: Path) -> None:
    sheet = folder / "ground_truth.csv"
    if not sheet.exists():
        raise SystemExit(f"{sheet} not found. Create it first with --template.")

    records, unreadable, skipped = [], [], []
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("filename") or "").strip()
            truth = {rid: (row.get(col) or "").strip().lower() for rid, col in zip(RULE_IDS, COLUMNS)}
            path = folder / name
            if not path.exists():
                skipped.append((name, "file not found"))
                continue
            if any(v not in ("pass", "fail") for v in truth.values()):
                skipped.append((name, "R1 to R5 must each be pass or fail"))
                continue
            try:
                out = analyze(path.read_bytes(), None)       # R1 to R5 do not need the photo scale
            except AppError as e:
                unreadable.append((name, e.code))
                continue
            by_rule = {r["rule_id"]: r for r in out["rule_results"]}
            for rid in RULE_IDS:
                records.append({"filename": name, "rule": rid, "expected": truth[rid],
                                "app": by_rule[rid]["status"], "message": by_rule[rid]["message"]})
            print(f"scanned {name}")

    if not records:
        raise SystemExit("Nothing to evaluate. Fill in ground_truth.csv first.")

    print("\n=== DISAGREEMENTS (you versus the app) ===")
    mismatches = 0
    for r in records:
        app_fail = r["app"] == "fail"
        truly_fail = r["expected"] == "fail"
        if app_fail != truly_fail:
            mismatches += 1
            kind = "FALSE ALARM" if app_fail else "MISSED    "
            print(f"{kind} {r['filename']:<28} {r['rule']}  you: {r['expected']:<4} app: {r['app']:<11} {r['message']}")
    if not mismatches:
        print("none")

    print("\n=== RESULTS PER RULE (a violation = positive) ===")
    print(f"{'rule':<7}{'photos':>7}{'correct':>9}{'accuracy':>10}{'precision':>11}{'recall':>8}")
    total_correct = 0
    for rid in RULE_IDS:
        rows = [r for r in records if r["rule"] == rid]
        tp = sum(1 for r in rows if r["expected"] == "fail" and r["app"] == "fail")
        fp = sum(1 for r in rows if r["expected"] == "pass" and r["app"] == "fail")
        fn = sum(1 for r in rows if r["expected"] == "fail" and r["app"] != "fail")
        tn = len(rows) - tp - fp - fn
        total_correct += tp + tn
        print(f"{rid:<7}{len(rows):>7}{tp + tn:>9}{pct(tp + tn, len(rows)):>10}"
              f"{pct(tp, tp + fp):>11}{pct(tp, tp + fn):>8}")
    print(f"{'ALL':<7}{len(records):>7}{total_correct:>9}{pct(total_correct, len(records)):>10}")
    print("\nprecision = of the violations the app reported, how many were real")
    print("recall    = of the real violations, how many the app found")

    if unreadable:
        print("\nUnreadable photos (not counted above):", ", ".join(f"{n} ({c})" for n, c in unreadable))
    if skipped:
        print("Skipped rows:", "; ".join(f"{n}: {why}" for n, why in skipped))

    out_file = folder / "evaluation_results.csv"
    with out_file.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "rule", "expected", "app", "message"])
        writer.writeheader()
        writer.writerows(records)
    print(f"\nFull results saved to {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare the app's verdicts with yours.")
    parser.add_argument("folder")
    parser.add_argument("--template", action="store_true", help="create an empty ground_truth.csv")
    args = parser.parse_args()
    folder = Path(args.folder)
    make_template(folder) if args.template else evaluate(folder)