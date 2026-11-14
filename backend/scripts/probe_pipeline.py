
import sys
from pathlib import Path

from app.services.pipeline import analyze

path = Path(sys.argv[1] if len(sys.argv) > 1 else "app/mock_data/sample.jpg")
label_width_mm = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0

result = analyze(path.read_bytes(), label_width_mm)

print(f"\nStatus: {result['status']}   Score: {result['score']}   Violations: {result['violations_count']}")
print("Font info:", result["font_info"])
nq = result["extracted_fields"]["net_quantity"]
print("Net quantity:", nq["value"], "| height mm:", nq["font_height_mm"], "| minimum mm:", nq["min_font_height_mm"])
print("\n--- Rules ---")
for r in result["rule_results"]:
    print(f"{r['rule_id']}  {r['status']:<11} {r['message']}")

Path("storage").mkdir(exist_ok=True)
out = Path("storage/annotated_probe.jpg")
out.write_bytes(result["annotated_image"])
print("\nAnnotated image saved to", out.resolve())