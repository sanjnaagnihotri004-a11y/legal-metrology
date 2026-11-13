
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def do_login(email="admin@lm.test", password="Admin@123"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_login_success():
    r = do_login()
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["user"]["role"] == "admin"
    assert "password_hash" not in body["user"]


def test_inspector_login():
    r = do_login("inspector@lm.test", "Inspector@123")
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "inspector"


def test_wrong_password():
    r = do_login(password="wrong-password")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_unknown_email():
    r = do_login(email="nobody@lm.test")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_missing_password():
    r = client.post("/auth/login", json={"email": "admin@lm.test"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_me_without_token():
    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_with_token():
    token = do_login().json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "admin@lm.test"


def test_garbage_token():
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_expired_token():
    expired = jwt.encode(
        {"sub": "1", "role": "admin", "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "TOKEN_EXPIRED"