from PIL import Image

from app.services import pipeline
from app.services.extraction import INCL_TAX_RE


def line(text, conf=0.9):
    return {"text": text, "bbox": [0, 0, 10, 10], "confidence": conf}


def fields_with(value, found=True):
    return {"mrp": {"found": found, "value": value if found else None,
                    "confidence": 0.9 if found else None, "bbox": [10, 10, 200, 50] if found else None}}


def run(fields):
    pipeline.add_tax_wording_from_second_look(Image.new("RGB", (300, 300)), fields)


def test_second_look_adds_the_missing_wording(monkeypatch):
    monkeypatch.setattr(pipeline, "read_region", lambda *a, **k: [line("Inclusive of all taxes")])
    f = fields_with("M.R.P. 155.00")
    run(f)
    assert INCL_TAX_RE.search(f["mrp"]["value"])


def test_second_look_handles_wording_split_over_two_lines(monkeypatch):
    monkeypatch.setattr(pipeline, "read_region", lambda *a, **k: [line("Inclusive of"), line("all taxes")])
    f = fields_with("M.R.P. 155.00")
    run(f)
    assert INCL_TAX_RE.search(f["mrp"]["value"])


def test_second_look_is_skipped_when_the_wording_is_already_there(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "read_region", lambda *a, **k: calls.append(1) or [])
    run(fields_with("M.R.P. 155.00 Inclusive of all taxes"))
    assert calls == []


def test_second_look_is_skipped_when_there_is_no_mrp(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "read_region", lambda *a, **k: calls.append(1) or [])
    run(fields_with("", found=False))
    assert calls == []


def test_second_look_gives_up_quietly(monkeypatch):
    monkeypatch.setattr(pipeline, "read_region", lambda *a, **k: [line("KESHRI DAILY NEEDS")])
    f = fields_with("M.R.P. 155.00")
    run(f)
    assert INCL_TAX_RE.search(f["mrp"]["value"]) is None