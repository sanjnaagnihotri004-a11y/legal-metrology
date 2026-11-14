from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SAMPLE = Path(__file__).resolve().parent.parent / "app" / "mock_data" / "sample.jpg"


def test_real_scan_from_upload_to_report():
    token = client.post("/auth/login", json={"email": "inspector@lm.test",
                                              "password": "Inspector@123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    r = client.post("/scans", headers=h,
                    files={"image": ("sample.jpg", SAMPLE.read_bytes(), "image/jpeg")},
                    data={"product_name": "Masala Peanuts", "brand": "CrunchCo",
                          "category": "food", "label_width_mm": "120"})
    assert r.status_code == 201, r.text
    scan = r.json()
    st = {x["rule_id"]: x["status"] for x in scan["rule_results"]}
    assert st["LM-R1"] == "pass" and st["LM-R3"] == "fail" and st["LM-R4"] == "fail"
    assert scan["extracted_fields"]["net_quantity"]["font_height_mm"] is not None

    fixed = client.post(f"/scans/{scan['id']}/recheck", headers=h, json={"corrections": {
        "mrp": "MRP Rs. 50.00 (Incl. of all taxes)", "mfg_date": "Pkd 10/2026"}})
    assert fixed.status_code == 200
    body = fixed.json()
    st = {x["rule_id"]: x["status"] for x in body["rule_results"]}
    assert st["LM-R3"] == "pass" and st["LM-R4"] == "pass"
    assert body["corrected"] is True and body["status"] in ("compliant", "needs_review")

    assert client.get(f"/scans/{scan['id']}/report?format=pdf", headers=h).content.startswith(b"%PDF")