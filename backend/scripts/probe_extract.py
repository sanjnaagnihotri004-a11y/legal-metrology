import json
import sys
from pathlib import Path

from app.services.extraction import extract_fields
from app.services.ocr import read_label

path = Path(sys.argv[1] if len(sys.argv) > 1 else "app/mock_data/sample.jpg")
ocr = read_label(path.read_bytes())

print(f"\nImage {ocr['width']}x{ocr['height']} (turned {ocr['rotation']} degrees to read it), "
      f"{len(ocr['lines'])} text lines, average confidence {ocr['confidence']}")
print("\n--- OCR lines ---")
for line in ocr["lines"]:
    print(f"{line['confidence']:.2f}  {line['bbox']}  {line['text']}")

print("\n--- Extracted fields ---")
print(json.dumps(extract_fields(ocr["lines"]), indent=2, ensure_ascii=False))