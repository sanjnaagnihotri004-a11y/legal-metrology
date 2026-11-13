
import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)

FORM = {"product_name": "Test Biscuits", "brand": "TestCo", "category": "food", "label_width_mm": "120"}


def login(email, password):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin():
    return login("admin@lm.test", "Admin@123")


def inspector():
    return login("inspector@lm.test", "Inspector@123")


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(buf, format="PNG")
    return buf.getvalue()


def create_scan(headers, form=None, content=None, content_type="image/png"):
    data = png_bytes() if content is None else content
    return client.post("/scans", headers=headers,
                       files={"image": ("label.png", data, content_type)},
                       data=form or FORM)


def test_scans_require_login():
    r = client.get("/scans")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_create_scan_success():
    r = create_scan(admin())
    assert r.status_code == 201
    body = r.json()
    assert [x["rule_id"] for x in body["rule_results"]] == [f"LM-R{i}" for i in range(1, 7)]
    assert set(body["extracted_fields"]) == {
        "manufacturer_name_address", "net_quantity", "mrp", "mfg_date", "consumer_care"}
    assert body["product"]["name"] == "Test Biscuits"
    assert body["image_width_px"] == 200
    assert body["status"] in ("compliant", "non_compliant", "needs_review")
    assert body["created_at"].endswith("Z")


def test_create_scan_rejects_pdf():
    r = create_scan(admin(), content_type="application/pdf")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_file_too_large():
    r = create_scan(admin(), content=b"0" * (10 * 1024 * 1024 + 1))
    assert r.status_code == 413, r.text
    assert r.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_create_scan_bad_width():
    r = create_scan(admin(), form={**FORM, "label_width_mm": "0"})
    assert r.status_code == 422
    assert "label_width_mm" in r.json()["error"]["fields"]


def test_create_scan_missing_product_name():
    form = {k: v for k, v in FORM.items() if k != "product_name"}
    r = create_scan(admin(), form=form)
    assert r.status_code == 422
    assert "product_name" in r.json()["error"]["fields"]


def test_error_ocr_trigger():
    r = create_scan(admin(), form={**FORM, "product_name": "error_ocr"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "OCR_NO_TEXT"


def test_list_shape_and_pagination():
    r = client.get("/scans?page=1&page_size=5", headers=admin())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert len(body["items"]) <= 5
    assert body["total"] >= 12
    assert body["page"] == 1


def test_list_filter_by_status():
    r = client.get("/scans?status=non_compliant&page_size=100", headers=admin())
    items = r.json()["items"]
    assert items and all(i["status"] == "non_compliant" for i in items)


def test_page_size_limit():
    r = client.get("/scans?page_size=500", headers=admin())
    assert r.status_code == 422


def test_inspector_cannot_open_admin_scan():
    scan_id = create_scan(admin()).json()["id"]
    r = client.get(f"/scans/{scan_id}", headers=inspector())
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert client.get(f"/scans/{scan_id}", headers=admin()).status_code == 200


def test_get_unknown_scan():
    r = client.get("/scans/99999", headers=admin())
    assert r.status_code == 404


def test_images_load_with_token_only():
    scan_id = create_scan(inspector()).json()["id"]
    for path in ("image", "annotated-image"):
        r = client.get(f"/scans/{scan_id}/{path}", headers=inspector())
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")
        assert client.get(f"/scans/{scan_id}/{path}").status_code == 401


def test_recheck_updates_rules():
    scan_id = create_scan(inspector()).json()["id"]
    r = client.post(f"/scans/{scan_id}/recheck", headers=inspector(), json={
        "corrections": {"mrp": "MRP Rs. 50.00 (Incl. of all taxes)", "mfg_date": "Pkd 10/2026"}})
    assert r.status_code == 200
    body = r.json()
    assert body["corrected"] is True
    statuses = {x["rule_id"]: x["status"] for x in body["rule_results"]}
    assert statuses["LM-R3"] == "pass"
    assert statuses["LM-R4"] == "pass"


def test_recheck_unknown_field():
    scan_id = create_scan(inspector()).json()["id"]
    r = client.post(f"/scans/{scan_id}/recheck", headers=inspector(),
                    json={"corrections": {"colour": "red"}})
    assert r.status_code == 422
    assert "colour" in r.json()["error"]["fields"]