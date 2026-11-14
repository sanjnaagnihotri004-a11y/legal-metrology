
import sys

from rapidocr import RapidOCR

path = sys.argv[1] if len(sys.argv) > 1 else "app/mock_data/sample.jpg"
print("Reading:", path)

engine = RapidOCR()
result = engine(path)

print("Result type:", type(result).__name__)
print("Attributes:", [a for a in dir(result) if not a.startswith("_")])

texts = getattr(result, "txts", None)
if not texts:
    print("No text found")
else:
    boxes = result.boxes
    scores = result.scores
    for box, text, score in zip(boxes, texts, scores):
        xs = [int(p[0]) for p in box]
        ys = [int(p[1]) for p in box]
        print(f"{score:.2f}  x {min(xs)}-{max(xs)}  y {min(ys)}-{max(ys)}  {text}")