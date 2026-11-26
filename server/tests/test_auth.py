"""后台登录：签名、过期、改密码失效，以及没登录的请求被挡住。"""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from customer_agent import settings
from customer_agent.api import auth


def app_with_a_page(monkeypatch, password="right"):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", password)
    monkeypatch.setattr(settings, "ADMIN_USER", "admin")
    monkeypatch.setattr(settings, "ADMIN_COOKIE_SECURE", False)  # 测试客户端走 http
    monkeypatch.setattr(auth.time, "sleep", lambda _: None)
    auth._failures.clear()
    app = FastAPI()
    app.include_router(auth.router)

    @app.get("/api/secret", dependencies=[Depends(auth.require_admin)])
    def secret():
        return {"ok": True}

    return TestClient(app)


def test_login_then_use_the_admin_api(monkeypatch):
    client = app_with_a_page(monkeypatch)
    assert client.get("/api/secret").status_code == 401
    assert client.post("/api/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"username": "admin", "password": "right"}).status_code == 200
    assert client.get("/api/secret").json() == {"ok": True}
    assert client.get("/api/me").json() == {"username": "admin"}
    client.post("/api/logout")
    assert client.get("/api/secret").status_code == 401


def test_no_password_means_no_admin(monkeypatch):
    client = app_with_a_page(monkeypatch, password="")
    assert client.post("/api/login", json={"username": "admin", "password": ""}).status_code == 503
    assert client.get("/api/secret").status_code == 503


def test_tokens_expire_and_die_with_the_password(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "one")
    token = auth.issue("admin", now=1000)
    assert auth.verify(token, now=1001) == "admin"
    assert auth.verify(token, now=1000 + auth.SESSION_DAYS * 86400 + 1) is None
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "two")
    assert auth.verify(token, now=1001) is None


def test_a_forged_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "one")
    body, mac = auth.issue("admin").split(".")
    assert auth.verify(f"{body}.{mac[:-2]}xx") is None


def test_too_many_wrong_passwords_pause_login(monkeypatch):
    client = app_with_a_page(monkeypatch)
    for _ in range(auth.MAX_FAILURES):
        assert client.post("/api/login", json={"username": "admin", "password": "guess"}).status_code == 401
    assert client.post("/api/login", json={"username": "admin", "password": "right"}).status_code == 429
    later = auth.time.time() + auth.LOCK_SECONDS + 1
    monkeypatch.setattr(auth.time, "time", lambda: later)
    assert client.post("/api/login", json={"username": "admin", "password": "right"}).status_code == 200


def test_the_service_does_not_publish_its_api_list():
    from customer_agent.api import app

    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert "/api/chats" in app.openapi()["paths"]  # 本地导出照常
