import requests, streamlit as st
from utils.config import BACKEND_URL, REQUEST_TIMEOUT_SECONDS, USE_MOCK

class ApiError(Exception):
    def __init__(self, status=0, code="ERROR", message="Something went wrong", fields=None):
        self.status, self.code, self.message, self.fields = status, code, message, fields or {}
        super().__init__(message)

def _mock_scan(scan_id=42, status="non_compliant"):
    statuses = ["pass", "pass", "fail", "pass", "pass", "fail"] if status == "non_compliant" else ["pass"]*6
    rules = []
    titles = ["Manufacturer / packer / importer details", "Net quantity declaration",
              "MRP declaration", "Manufacture / packing date", "Consumer care details",
              "Net quantity font height"]
    for i, (title, result) in enumerate(zip(titles, statuses), 1):
        rules.append({"rule_id": f"LM-R{i}", "clause": f"Rule 6(1)({chr(96+i)})",
                      "title": title, "description": title, "severity": "critical" if i <= 3 else "major",
                      "status": result, "message": "Requirement satisfied." if result == "pass" else "Declaration needs verification."})
    return {"id": scan_id, "product": {"id": 7, "name": "Masala Peanuts", "brand": "CrunchCo",
            "barcode": None, "category": "food"}, "inspector": {"id": 2, "name": "Asha Verma"},
            "created_at": "2026-11-10T09:15:30Z", "status": status,
            "score": 66.7 if status == "non_compliant" else 100, "corrected": False,
            "notes": "", "label_width_mm": 120, "image_width_px": 1600, "image_height_px": 1200,
            "image_url": None, "annotated_image_url": None,
            "ocr_text": "CrunchCo Masala Peanuts Net Wt. 200 g MRP Rs. 50.00",
            "ocr_confidence": 0.87,
            "extracted_fields": {
                "manufacturer_name_address": {"found": True, "value": "CrunchCo Foods, Indore 452001", "confidence": .91},
                "net_quantity": {"found": True, "value": "Net Wt. 200 g", "confidence": .95, "quantity": 200, "unit": "g", "font_height_mm": 1.2, "min_font_height_mm": 2.0},
                "mrp": {"found": True, "value": "MRP Rs. 50.00", "confidence": .90},
                "mfg_date": {"found": False, "value": None, "confidence": None},
                "consumer_care": {"found": True, "value": "Call 1800-123-456", "confidence": .88}},
            "rule_results": rules, "violations_count": sum(x["status"] == "fail" for x in rules), "evidence": []}

def _request(method, path, *, json=None, data=None, files=None, params=None, auth=True):
    if USE_MOCK:
        return _mock_response(method, path, json=json)
    headers = {}
    token = st.session_state.get("token")
    if auth and token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.request(method, BACKEND_URL + path, headers=headers, json=json,
                                    data=data, files=files, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApiError(message=f"Cannot connect to backend: {exc}")
    if response.status_code == 401 and auth:
        for key in ("token", "user"):
            st.session_state[key] = None
        st.session_state.notice = "Session expired. Please log in again."
        st.rerun()
    if not response.ok:
        try:
            body = response.json()
            err = body.get("error", body)
            message = err.get("message") or str(body.get("detail", "Request failed"))
            fields = err.get("fields", {})
            code = err.get("code", "ERROR")
        except Exception:
            message, fields, code = "Request failed. Please try again.", {}, "ERROR"
        raise ApiError(response.status_code, code, message, fields)
    if response.status_code == 204 or not response.content:
        return {}
    if "application/json" in response.headers.get("content-type", ""):
        return response.json()
    return response        # images, PDF, Word and CSV: the caller reads .content

def _mock_response(method, path, json=None):
    if path == "/health": return {"status": "ok"}
    if path == "/auth/login":
        return {"access_token": "mock-token", "token_type": "bearer", "expires_in": 3600,
                "user": {"id": 2, "name": "Asha Verma", "email": (json or {}).get("email", "inspector@lm.test"),
                         "role": "admin" if (json or {}).get("email") == "admin@lm.test" else "inspector"}}
    if path == "/auth/me": return st.session_state.get("user") or {"id": 2, "name": "Asha Verma", "email": "inspector@lm.test", "role": "inspector"}
    if path == "/stats":
        return {"total_scans": 57, "compliant": 20, "non_compliant": 31, "needs_review": 6,
                "compliance_rate": 35.1, "scans_today": 4,
                "top_violated_rules": [{"rule_id":"LM-R4","title":"Manufacture/packing date","count":18},{"rule_id":"LM-R3","title":"MRP declaration","count":14}],
                "violations_over_time":[{"date":"2026-11-09","count":5},{"date":"2026-11-10","count":8}],
                "scans_over_time":[], "by_category":[{"category":"food","total":25,"compliant":9,"non_compliant":16}],
                "recent_scans": _mock_response("GET", "/scans")["items"][:5]}
    if path == "/scans" and method == "GET":
        return {"items":[{"id":42,"product_name":"Masala Peanuts","brand":"CrunchCo","category":"food","status":"non_compliant","score":66.7,"violations_count":2,"inspector_name":"Asha Verma","created_at":"2026-11-10T09:15:30Z"},
                         {"id":41,"product_name":"Herbal Shampoo","brand":"NatureCare","category":"personal_care","status":"compliant","score":100,"violations_count":0,"inspector_name":"Asha Verma","created_at":"2026-11-09T08:00:00Z"}], "total":2,"page":1,"page_size":20}
    if path.startswith("/scans/") and path.endswith("/report"): return b"Demo report (mock mode)"
    if path.startswith("/scans/") and path.endswith("/recheck"): return _mock_scan(int(path.split("/")[2]), "compliant")
    if path.startswith("/scans/"): return _mock_scan(int(path.split("/")[2]))
    if path == "/scans" and method == "POST": return _mock_scan(43, "needs_review")
    if path == "/rules":
        return [{"rule_id":f"LM-R{i}","clause":"Provided by backend","title":t,"description":t,"severity":"critical" if i<=3 else "major","active":True}
                for i,t in enumerate(["Manufacturer/packer/importer name and address","Net quantity with valid unit","MRP inclusive of all taxes","Month and year of manufacture/packing/import","Consumer care phone and/or email","Net quantity font height"],1)]
    if path == "/users": return [{"id":1,"name":"Admin User","email":"admin@lm.test","role":"admin","is_active":True,"created_at":"2026-10-01T08:00:00Z"},{"id":2,"name":"Asha Verma","email":"inspector@lm.test","role":"inspector","is_active":True,"created_at":"2026-10-02T08:00:00Z"}]
    if path.startswith("/users/"): return {}
    if path == "/users" and method == "POST": return {"id":3, **(json or {}), "is_active":True}
    return {}

def health(): return _request("GET", "/health", auth=False)
def login(email, password): return _request("POST", "/auth/login", json={"email":email,"password":password}, auth=False)
def me(): return _request("GET", "/auth/me")
def create_scan(fields, image):
    return _request("POST", "/scans", data=fields, files={"image":(image.name,image.getvalue(),image.type)})
def list_scans(params=None): return _request("GET", "/scans", params=params or {})
def get_scan(scan_id): return _request("GET", f"/scans/{scan_id}")
def recheck_scan(scan_id, corrections): return _request("POST", f"/scans/{scan_id}/recheck", json={"corrections":corrections})
def get_image_bytes(path):
    if USE_MOCK: return None
    return _request("GET", path).content
def add_evidence(scan_id, file, note):
    return _request("POST", f"/scans/{scan_id}/evidence", data={"note":note}, files={"file":(file.name,file.getvalue(),file.type)})
def get_evidence_bytes(path): return get_image_bytes(path)
def download_report(scan_id, fmt):
    if USE_MOCK: return f"Mock {fmt.upper()} report for scan {scan_id}".encode()
    return _request("GET", f"/scans/{scan_id}/report", params={"format":fmt}).content
def get_stats(params=None): return _request("GET", "/stats", params=params or {})
def get_rules(): return _request("GET", "/rules")
def list_users(): return _request("GET", "/users")
def create_user(payload): return _request("POST", "/users", json=payload)
def update_user(user_id, payload): return _request("PATCH", f"/users/{user_id}", json=payload)
