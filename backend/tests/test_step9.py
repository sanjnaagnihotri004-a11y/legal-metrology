
import csv
import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)


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


def new_scan(headers):
    r = client.post(
        "/scans", headers=headers,
        files={"image": ("label.png", png_bytes(), "image/png")},
        data={"product_name": "Test", "brand": "TestCo", "category": "food", "label_width_mm": "100"},
    )
    assert r.status_code == 201
    return r.json()["id"]


# ---------- evidence ----------

def test_add_evidence_and_fetch_it():
    h = inspector()
    scan_id = new_scan(h)
    data = png_bytes()
    r = client.post(f"/scans/{scan_id}/evidence", headers=h,
                    files={"file": ("close.png", data, "image/png")}, data={"note": "Close-up of MRP"})
    assert r.status_code == 201
    ev = r.json()
    assert ev["file_url"] == f"/evidence/{ev['id']}/file"
    assert ev["uploaded_by"] == "Asha Verma"
    assert ev["note"] == "Close-up of MRP"

    scan = client.get(f"/scans/{scan_id}", headers=h).json()
    assert [e["id"] for e in scan["evidence"]] == [ev["id"]]

    f = client.get(ev["file_url"], headers=h)
    assert f.status_code == 200
    assert f.content == data


def test_evidence_rejects_text_file():
    h = inspector()
    r = client.post(f"/scans/{new_scan(h)}/evidence", headers=h,
                    files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_evidence_note_too_long():
    h = inspector()
    r = client.post(f"/scans/{new_scan(h)}/evidence", headers=h,
                    files={"file": ("a.png", png_bytes(), "image/png")}, data={"note": "x" * 301})
    assert r.status_code == 422
    assert "note" in r.json()["error"]["fields"]


def test_inspector_cannot_add_evidence_to_admin_scan():
    scan_id = new_scan(admin())
    r = client.post(f"/scans/{scan_id}/evidence", headers=inspector(),
                    files={"file": ("a.png", png_bytes(), "image/png")})
    assert r.status_code == 404


def test_evidence_file_needs_login():
    h = inspector()
    scan_id = new_scan(h)
    ev = client.post(f"/scans/{scan_id}/evidence", headers=h,
                     files={"file": ("a.png", png_bytes(), "image/png")}).json()
    assert client.get(ev["file_url"]).status_code == 401


# ---------- stats ----------

def test_stats_shape():
    r = client.get("/stats", headers=admin())
    assert r.status_code == 200
    body = r.json()
    for key in ("total_scans", "compliant", "non_compliant", "needs_review", "compliance_rate",
                "scans_today", "top_violated_rules", "violations_over_time", "scans_over_time",
                "by_category", "recent_scans"):
        assert key in body
    assert isinstance(body["top_violated_rules"], list)
    assert len(body["recent_scans"]) <= 10


def test_stats_numbers_add_up():
    body = client.get("/stats", headers=admin()).json()
    assert body["compliant"] + body["non_compliant"] + body["needs_review"] == body["total_scans"]
    assert body["compliance_rate"] == round(body["compliant"] / body["total_scans"] * 100, 1)


def test_inspector_stats_smaller_than_admin():
    a = client.get("/stats", headers=admin()).json()["total_scans"]
    i = client.get("/stats", headers=inspector()).json()["total_scans"]
    assert i < a


def test_stats_empty_range_returns_empty_lists():
    body = client.get("/stats?date_from=2999-01-01", headers=admin()).json()
    assert body["total_scans"] == 0
    assert body["compliance_rate"] == 0.0
    assert body["top_violated_rules"] == []
    assert body["by_category"] == []
    assert body["recent_scans"] == []


# ---------- reports ----------

def test_pdf_report():
    r = client.get("/scans/1/report?format=pdf", headers=admin())
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="LM_Report_1.pdf"' in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_docx_report():
    r = client.get("/scans/1/report?format=docx", headers=admin())
    assert r.status_code == 200
    assert r.content.startswith(b"PK")  # a .docx is a zip file
    assert "LM_Report_1.docx" in r.headers["content-disposition"]


def test_csv_report():
    r = client.get("/scans/1/report?format=csv", headers=admin())
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert len(rows) == 7  # header + 6 rules
    assert rows[0][8] == "rule_id"


def test_report_bad_format():
    r = client.get("/scans/1/report?format=exe", headers=admin())
    assert r.status_code == 422
    assert "format" in r.json()["error"]["fields"]


def test_report_other_users_scan_is_404():
    r = client.get("/scans/4/report?format=pdf", headers=inspector())  # scan 4 belongs to the admin
    assert r.status_code == 404


def test_report_needs_login():
    assert client.get("/scans/1/report?format=pdf").status_code == 401


# ---------- rules ----------

def test_rules_list():
    r = client.get("/rules", headers=inspector())
    assert r.status_code == 200
    assert [x["rule_id"] for x in r.json()] == [f"LM-R{i}" for i in range(1, 7)]


# ---------- users ----------

def new_email():
    return f"test-{uuid.uuid4().hex[:8]}@lm.test"


def create_user(email, password="Passw0rd!", role="inspector"):
    return client.post("/users", headers=admin(),
                       json={"name": "Test User", "email": email, "password": password, "role": role})


def test_inspector_cannot_list_users():
    r = client.get("/users", headers=inspector())
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_admin_lists_users():
    r = client.get("/users", headers=admin())
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert "admin@lm.test" in emails and "inspector@lm.test" in emails
    assert all("password_hash" not in u for u in r.json())


def test_create_user_then_login():
    email = new_email()
    r = create_user(email)
    assert r.status_code == 201
    assert r.json()["role"] == "inspector"
    login_r = client.post("/auth/login", json={"email": email, "password": "Passw0rd!"})
    assert login_r.status_code == 200


def test_duplicate_email_rejected():
    r = create_user("ADMIN@lm.test")
    assert r.status_code == 422
    assert "email" in r.json()["error"]["fields"]


def test_short_password_rejected():
    r = create_user(new_email(), password="short")
    assert r.status_code == 422
    assert "password" in r.json()["error"]["fields"]


def test_disabled_user_cannot_login():
    email = new_email()
    user_id = create_user(email).json()["id"]
    r = client.patch(f"/users/{user_id}", headers=admin(), json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    login_r = client.post("/auth/login", json={"email": email, "password": "Passw0rd!"})
    assert login_r.status_code == 401
    assert login_r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_admin_cannot_disable_self():
    admin_id = client.post("/auth/login", json={"email": "admin@lm.test", "password": "Admin@123"}).json()["user"]["id"]
    r = client.patch(f"/users/{admin_id}", headers=admin(), json={"is_active": False})
    assert r.status_code == 422
    assert "is_active" in r.json()["error"]["fields"]

def test_report_with_photo_and_pdf_evidence():
    h = inspector()
    scan_id = new_scan(h)
    client.post(f"/scans/{scan_id}/evidence", headers=h,
                files={"file": ("photo.png", png_bytes(), "image/png")}, data={"note": "photo"})
    client.post(f"/scans/{scan_id}/evidence", headers=h,
                files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")}, data={"note": "pdf"})
    pdf = client.get(f"/scans/{scan_id}/report?format=pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    docx = client.get(f"/scans/{scan_id}/report?format=docx", headers=h)
    assert docx.status_code == 200 and docx.content.startswith(b"PK")