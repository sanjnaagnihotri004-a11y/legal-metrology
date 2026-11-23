import io
from pathlib import Path

import pytest
from PIL import Image

from app.services.pipeline import analyze

SAMPLE = Path(__file__).resolve().parent.parent / "app" / "mock_data" / "sample.jpg"


def turned(angle):
    buf = io.BytesIO()
    Image.open(SAMPLE).convert("RGB").rotate(angle, expand=True).save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def declarations(out):
    """Verdicts for the five declaration rules (LM-R6 depends on the scale, so it is left out)."""
    return {r["rule_id"]: r["status"] for r in out["rule_results"] if r["rule_id"] != "LM-R6"}


@pytest.mark.parametrize("angle", [90, 270])
def test_sideways_photo_gives_the_same_verdicts_as_upright(angle):
    upright = analyze(SAMPLE.read_bytes(), 120.0)
    out = analyze(turned(angle), 120.0)
    assert declarations(out) == declarations(upright), f"rotation chosen: {out['rotation']}"
    assert out["rotation"] in (90, 270)
    assert out["image_width_px"] > out["image_height_px"]         # stored upright (landscape)
    assert out["extracted_fields"]["net_quantity"]["font_height_mm"] is not None


@pytest.mark.parametrize("angle", [90, 270])
def test_sideways_photo_ends_up_the_right_way_up(angle):
    # Turning the photo by `angle` is undone by turning it a further (360 - angle) degrees.
    # Telling the two sideways directions apart is a heuristic, so this test shows how well it works.
    out = analyze(turned(angle), 120.0)
    assert out["rotation"] == 360 - angle, f"chose {out['rotation']}, expected {360 - angle}"


def test_upright_photo_is_left_alone():
    out = analyze(SAMPLE.read_bytes(), 120.0)
    assert out["rotation"] == 0