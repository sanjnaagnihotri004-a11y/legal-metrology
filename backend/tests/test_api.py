
import csv
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

pytestmark = pytest.mark.usefixtures("fake_ocr")
client = TestClient(app)

FORM = {"product_name": "Test Biscuits", "brand": "TestCo", "category": "food", "label_width_mm": "120"}
RULE_IDS = [f"LM-R{i}" for i in range(1, 7)]


def login(email, password):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin():
    return login("admin@lm.test", "Admin@123")


def inspector():
    return login("inspector@lm.test", "Inspector@123")


def png_bytes(width=200, height=100):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="PNG")
    return buf.getvalue()


def create_scan(headers, form=None, content=None, content_type="image/png"):
    data = png_bytes() if content is None else content
    return client.post("/scans", headers=headers,
                       files={"image": ("label.png", data, content_type)}, data=form or FORM)


def new_scan_id(headers, **form):
    r = create_scan(headers, form={**FORM, **form})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------- creating and reading scans ----------

def test_scans_need_login():
    r = client.get("/scans")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_create_scan_returns_the_full_contract_object():
    r = create_scan(admin())
    assert r.status_code == 201
    b = r.json()
    assert [x["rule_id"] for x in b["rule_results"]] == RULE_IDS
    assert set(b["extracted_fields"]) == {
        "manufacturer_name_address", "net_quantity", "mrp", "mfg_date", "consumer_care"}
    assert (b["status"], b["score"], b["violations_count"]) == ("non_compliant", 66.7, 2)
    assert b["image_width_px"] == 200 and b["created_at"].endswith("Z")
    assert b["inspector"]["name"] == "Admin User"
    assert b["image_url"] == f"/scans/{b['id']}/image"


def test_scan_is_saved_and_can_be_read_back():
    h = inspector()
    created = create_scan(h).json()
    again = client.get(f"/scans/{created['id']}", headers=h)
    assert again.status_code == 200
    assert again.json() == created


def test_same_product_reuses_its_row():
    h = inspector()
    name = f"Repeat-{uuid.uuid4().hex[:6]}"
    a = create_scan(h, form={**FORM, "product_name": name}).json()
    b = create_scan(h, form={**FORM, "product_name": name.upper()}).json()
    assert a["product"]["id"] == b["product"]["id"]
    assert a["id"] != b["id"]


def test_images_need_a_token_and_annotated_has_a_banner():
    h = inspector()
    sid = new_scan_id(h)
    original = client.get(f"/scans/{sid}/image", headers=h)
    annotated = client.get(f"/scans/{sid}/annotated-image", headers=h)
    assert original.status_code == 200 and original.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(original.content)).size == (200, 100)
    assert Image.open(io.BytesIO(annotated.content)).size[1] > 100     # banner for the missing date
    assert client.get(f"/scans/{sid}/image").status_code == 401


def test_rejects_non_image_file():
    r = create_scan(admin(), content_type="application/pdf")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_file_too_large():
    r = create_scan(admin(), content=b"0" * (10 * 1024 * 1024 + 1))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_no_readable_text():
    r = create_scan(admin(), content=png_bytes(10, 10))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "OCR_NO_TEXT"


def test_bad_width_and_missing_name():
    r = create_scan(admin(), form={**FORM, "label_width_mm": "0"})
    assert r.status_code == 422 and "label_width_mm" in r.json()["error"]["fields"]
    r = create_scan(admin(), form={k: v for k, v in FORM.items() if k != "product_name"})
    assert r.status_code == 422 and "product_name" in r.json()["error"]["fields"]


def test_bad_barcode():
    r = create_scan(admin(), form={**FORM, "barcode": "12ab"})
    assert r.status_code == 422 and "barcode" in r.json()["error"]["fields"]


# ---------- list, filters, visibility ----------

def test_list_filters_and_pagination():
    h = admin()
    brand = f"Brand{uuid.uuid4().hex[:6]}"
    for i in range(3):
        new_scan_id(h, brand=brand, product_name=f"Item {i}")
    body = client.get(f"/scans?brand={brand}&page=1&page_size=2", headers=h).json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 3 and len(body["items"]) == 2
    assert len(client.get(f"/scans?brand={brand}&page=2&page_size=2", headers=h).json()["items"]) == 1
    assert client.get(f"/scans?brand={brand}&status=compliant", headers=h).json()["total"] == 0
    assert client.get(f"/scans?brand={brand}&rule_id=LM-R3", headers=h).json()["total"] == 3
    assert client.get(f"/scans?brand={brand}&q=item%201", headers=h).json()["total"] == 1
    assert client.get("/scans?page_size=500", headers=h).status_code == 422


def test_inspector_cannot_open_admin_scan():
    sid = new_scan_id(admin())
    r = client.get(f"/scans/{sid}", headers=inspector())
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert client.get(f"/scans/{sid}", headers=admin()).status_code == 200
    assert client.get("/scans/999999", headers=admin()).status_code == 404


# ---------- manual correction ----------

def test_recheck_fixes_the_failed_rules():
    h = inspector()
    sid = new_scan_id(h)
    r = client.post(f"/scans/{sid}/recheck", headers=h, json={"corrections": {
        "mrp": "MRP Rs. 50.00 (Incl. of all taxes)", "mfg_date": "Pkd 10/2026"}})
    assert r.status_code == 200
    b = r.json()
    assert b["corrected"] is True
    assert (b["status"], b["score"], b["violations_count"]) == ("compliant", 100.0, 0)
    assert client.get(f"/scans/{sid}", headers=h).json()["corrected"] is True


def test_recheck_clearing_a_field_makes_it_fail():
    h = inspector()
    sid = new_scan_id(h)
    b = client.post(f"/scans/{sid}/recheck", headers=h, json={"corrections": {"consumer_care": ""}}).json()
    statuses = {x["rule_id"]: x["status"] for x in b["rule_results"]}
    assert statuses["LM-R5"] == "fail"


def test_recheck_rereads_a_typed_quantity():
    h = inspector()
    sid = new_scan_id(h)
    b = client.post(f"/scans/{sid}/recheck", headers=h, json={"corrections": {"net_quantity": "8 oz"}}).json()
    assert {x["rule_id"]: x["status"] for x in b["rule_results"]}["LM-R2"] == "fail"
    assert b["extracted_fields"]["net_quantity"]["unit"] == "oz"


def test_recheck_validation():
    h = inspector()
    sid = new_scan_id(h)
    r = client.post(f"/scans/{sid}/recheck", headers=h, json={"corrections": {"colour": "red"}})
    assert r.status_code == 422 and "colour" in r.json()["error"]["fields"]
    assert client.post(f"/scans/{sid}/recheck", headers=h, json={"corrections": {}}).status_code == 422


# ---------- evidence ----------

def test_evidence_roundtrip():
    h = inspector()
    sid = new_scan_id(h)
    data = png_bytes()
    r = client.post(f"/scans/{sid}/evidence", headers=h,
                    files={"file": ("close.png", data, "image/png")}, data={"note": "Close-up of MRP"})
    assert r.status_code == 201
    ev = r.json()
    assert ev["file_url"] == f"/evidence/{ev['id']}/file"
    assert ev["uploaded_by"] == "Asha Verma" and ev["note"] == "Close-up of MRP"
    assert [e["id"] for e in client.get(f"/scans/{sid}", headers=h).json()["evidence"]] == [ev["id"]]
    assert client.get(ev["file_url"], headers=h).content == data
    assert client.get(ev["file_url"]).status_code == 401


def test_evidence_validation_and_ownership():
    h = inspector()
    sid = new_scan_id(h)
    r = client.post(f"/scans/{sid}/evidence", headers=h, files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    r = client.post(f"/scans/{sid}/evidence", headers=h,
                    files={"file": ("a.png", png_bytes(), "image/png")}, data={"note": "x" * 301})
    assert r.status_code == 422 and "note" in r.json()["error"]["fields"]
    other = new_scan_id(admin())
    r = client.post(f"/scans/{other}/evidence", headers=h, files={"file": ("a.png", png_bytes(), "image/png")})
    assert r.status_code == 404


# ---------- reports ----------

def test_all_three_report_formats():
    h = inspector()
    sid = new_scan_id(h)
    pdf = client.get(f"/scans/{sid}/report?format=pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert f'filename="LM_Report_{sid}.pdf"' in pdf.headers["content-disposition"]
    docx = client.get(f"/scans/{sid}/report?format=docx", headers=h)
    assert docx.status_code == 200 and docx.content.startswith(b"PK")
    csv_r = client.get(f"/scans/{sid}/report?format=csv", headers=h)
    rows = list(csv.reader(io.StringIO(csv_r.content.decode("utf-8-sig"))))
    assert len(rows) == 7 and rows[0][8] == "rule_id"


def test_report_with_photo_and_pdf_evidence():
    h = inspector()
    sid = new_scan_id(h)
    client.post(f"/scans/{sid}/evidence", headers=h,
                files={"file": ("p.png", png_bytes(), "image/png")}, data={"note": "photo"})
    client.post(f"/scans/{sid}/evidence", headers=h,
                files={"file": ("d.pdf", b"%PDF-1.4 fake", "application/pdf")}, data={"note": "pdf"})
    assert client.get(f"/scans/{sid}/report?format=pdf", headers=h).content.startswith(b"%PDF")
    assert client.get(f"/scans/{sid}/report?format=docx", headers=h).content.startswith(b"PK")


def test_report_errors():
    sid = new_scan_id(admin())
    assert client.get(f"/scans/{sid}/report?format=exe", headers=admin()).status_code == 422
    assert client.get(f"/scans/{sid}/report?format=pdf", headers=inspector()).status_code == 404
    assert client.get(f"/scans/{sid}/report?format=pdf").status_code == 401


# ---------- stats and rules ----------

def test_stats_add_up_and_respect_scope():
    new_scan_id(inspector())
    new_scan_id(admin())
    a = client.get("/stats", headers=admin()).json()
    i = client.get("/stats", headers=inspector()).json()
    assert a["compliant"] + a["non_compliant"] + a["needs_review"] == a["total_scans"]
    assert a["compliance_rate"] == round(a["compliant"] / a["total_scans"] * 100, 1)
    assert a["total_scans"] > i["total_scans"] >= 1
    assert a["top_violated_rules"][0]["rule_id"] in ("LM-R3", "LM-R4")
    assert a["scans_today"] >= 2 and len(a["recent_scans"]) <= 10


def test_stats_empty_range():
    body = client.get("/stats?date_from=2999-01-01", headers=admin()).json()
    assert body["total_scans"] == 0 and body["compliance_rate"] == 0.0
    assert body["top_violated_rules"] == [] and body["recent_scans"] == []


def test_rules_list():
    r = client.get("/rules", headers=inspector())
    assert r.status_code == 200
    assert [x["rule_id"] for x in r.json()] == RULE_IDS


# ---------- users ----------

def new_email():
    return f"test-{uuid.uuid4().hex[:8]}@lm.test"


def create_user(email, password="Passw0rd!", role="inspector"):
    return client.post("/users", headers=admin(),
                       json={"name": "Test User", "email": email, "password": password, "role": role})


def test_inspector_cannot_list_users():
    r = client.get("/users", headers=inspector())
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


def test_admin_lists_users_without_password_hash():
    r = client.get("/users", headers=admin())
    assert r.status_code == 200
    assert all("password_hash" not in u for u in r.json())


def test_create_user_then_login():
    email = new_email()
    assert create_user(email).status_code == 201
    assert client.post("/auth/login", json={"email": email, "password": "Passw0rd!"}).status_code == 200


def test_user_validation():
    assert "email" in create_user("ADMIN@lm.test").json()["error"]["fields"]
    assert "password" in create_user(new_email(), password="short").json()["error"]["fields"]


def test_disabled_user_cannot_login_and_admin_cannot_disable_self():
    email = new_email()
    uid = create_user(email).json()["id"]
    assert client.patch(f"/users/{uid}", headers=admin(), json={"is_active": False}).status_code == 200
    r = client.post("/auth/login", json={"email": email, "password": "Passw0rd!"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    admin_id = client.post("/auth/login", json={"email": "admin@lm.test", "password": "Admin@123"}).json()["user"]["id"]
    r = client.patch(f"/users/{admin_id}", headers=admin(), json={"is_active": False})
    assert r.status_code == 422 and "is_active" in r.json()["error"]["fields"]