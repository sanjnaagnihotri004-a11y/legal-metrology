
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import AppError, register_error_handlers


def make_client():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise AppError(403, "FORBIDDEN", "You do not have access")

    @app.get("/crash")
    def crash():
        raise RuntimeError("bug")

    @app.get("/need-number")
    def need_number(n: int):
        return {"n": n}

    return TestClient(app, raise_server_exceptions=False)


client = make_client()


def test_app_error_shape():
    r = client.get("/boom")
    assert r.status_code == 403
    assert r.json() == {"error": {"code": "FORBIDDEN", "message": "You do not have access"}}


def test_validation_error_has_fields():
    r = client.get("/need-number?n=abc")
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert "n" in body["fields"]


def test_unknown_url_is_not_found():
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_crash_returns_internal_error():
    r = client.get("/crash")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"