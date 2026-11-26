"""模拟店铺的测试：令牌、店铺接口的权限、对话转发的归属。客服服务用假的代替。"""

import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from demo_shop import relay, tokens
from demo_shop.app import app

SHOP = {"X-Api-Key": "shop-key"}


def token_for(who: str, minutes: int = 10) -> str:
    return tokens.sign("test-secret", who, "b1", minutes)


def test_token_round_trip_and_tampering():
    token = token_for("member-a")
    assert tokens.read("test-secret", token) == "member-a"
    assert tokens.read("other-secret", token) is None
    body, mac = token.split(".")
    assert tokens.read("test-secret", body[:-2] + "xx." + mac) is None


def test_expired_token_is_rejected(monkeypatch):
    token = token_for("member-a")
    monkeypatch.setattr(time, "time", lambda: 10**10)
    assert tokens.read("test-secret", token) is None


def test_shop_api_needs_the_key():
    client = TestClient(app)
    assert client.get("/shop-api/settings").status_code == 401
    assert client.get("/shop-api/settings", headers=SHOP).json()["reply_hours"] == 12


def test_orders_are_scoped_and_carry_no_secrets():
    client = TestClient(app)
    mine = client.get("/shop-api/orders", headers=SHOP | {"X-Visitor-Token": token_for("member-a")}).json()
    assert {o["order_no"] for o in mine} == {"EX1001", "EX1002", "EX1003"}
    assert "card_secret" not in json.dumps(mine) and "@" not in json.dumps(mine)
    assert client.get("/shop-api/orders", headers=SHOP).json() == []
    assert client.get("/shop-api/orders", headers=SHOP | {"X-Visitor-Token": "forged.token"}).json() == []


def test_cannot_open_a_ticket_on_someone_elses_order():
    client = TestClient(app)
    as_b = SHOP | {"X-Visitor-Token": token_for("member-b")}
    assert client.post("/shop-api/orders/EX1001/tickets", json={"summary": "退款"}, headers=as_b).status_code == 403
    ticket = client.post("/shop-api/orders/EX2001/tickets", json={"summary": "催一下"}, headers=as_b).json()["ticket_no"]
    assert client.get("/shop-api/orders", headers=as_b).json()[0]["open_ticket"] == ticket


def test_the_order_page_shows_the_card_only_to_its_owner():
    client = TestClient(app)
    client.post("/api/shop/identity", json={"who": "member-a"})
    assert "TEST-CARD" in client.get("/api/shop/orders").text
    client.post("/api/shop/identity", json={"who": "member-b"})
    assert "TEST-CARD" not in client.get("/api/shop/orders").text


def test_help_article_ids_match_the_knowledge_base():
    articles = TestClient(app).get("/api/shop/help").json()
    assert any(a["id"] == "faq/when-delivered" for a in articles)


class FakeAgent:
    """记下转发过来的请求，按台词回话。"""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.next_id = 0
        self.enabled = True

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["X-Api-Key"] == "agent-key"
        if request.url.path == "/v1/conversations":
            self.next_id += 1
            return httpx.Response(201, json={"id": f"c{self.next_id}", "status": "open"})
        if request.url.path == "/v1/status":
            return httpx.Response(200, json={"enabled": self.enabled, "max_message_chars": 500, "suggestions": {"zh": ["多久到货？"]}})
        if request.url.path.endswith("/images"):
            return httpx.Response(200, content=b'event: done\ndata: {"message_id": 2}\n\n', headers={"content-type": "text/event-stream"})
        if "/images/" in request.url.path:
            return httpx.Response(200, content=b"JPEGDATA", headers={"content-type": "image/jpeg", "content-security-policy": "sandbox"})
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, content=b'event: done\ndata: {"message_id": 1}\n\n', headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"ok": True})


@pytest.fixture
def agent(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(relay, "_agent", lambda: httpx.AsyncClient(base_url="http://agent.test", headers={"X-Api-Key": "agent-key"}, transport=httpx.MockTransport(fake.handler)))
    return fake


def browser(who: str = "guest") -> TestClient:
    client = TestClient(app)
    client.get("/api/chat/config")
    client.post("/api/shop/identity", json={"who": who})
    return client


def test_relay_signs_a_token_for_the_current_identity(agent):
    client = browser("member-a")
    cid = client.post("/api/chat/conversations").json()["id"]
    reply = client.post(f"/api/chat/conversations/{cid}/messages", json={"text": "我的订单"})
    assert "event: done" in reply.text
    sent = json.loads(agent.requests[-1].content)
    assert tokens.read("test-secret", sent["visitor_token"]) == "member-a"
    created = next(r for r in agent.requests if r.url.path == "/v1/conversations")
    assert json.loads(created.content)["index_id"] == 7


def test_relay_forwards_pictures_with_the_token(agent):
    """发图片：文件和访客令牌一起转给客服服务；看图只能看自己会话里的。"""
    client = browser("member-a")
    cid = client.post("/api/chat/conversations").json()["id"]
    assert "event: done" in client.post(f"/api/chat/conversations/{cid}/images", files={"file": ("a.jpg", b"JPEGDATA", "image/jpeg")}).text
    upload = agent.requests[-1]
    assert b"JPEGDATA" in upload.content and b"visitor_token" in upload.content
    seen = client.get(f"/api/chat/conversations/{cid}/images/1")
    assert seen.content == b"JPEGDATA" and seen.headers["content-security-policy"] == "sandbox"
    assert browser("member-a").get(f"/api/chat/conversations/{cid}/images/1").status_code == 404


def test_another_browser_cannot_use_my_conversation(agent):
    cid = browser("member-a").post("/api/chat/conversations").json()["id"]
    stranger = browser("member-a")
    assert stranger.get(f"/api/chat/conversations/{cid}").status_code == 404
    assert stranger.post(f"/api/chat/conversations/{cid}/messages", json={"text": "hi"}).status_code == 404


def test_switching_identity_drops_the_old_conversation(agent):
    client = browser("member-a")
    cid = client.post("/api/chat/conversations").json()["id"]
    client.post("/api/shop/identity", json={"who": "member-b"})
    assert client.get(f"/api/chat/conversations/{cid}").status_code == 404


def test_agent_down_gives_a_clear_error(monkeypatch):
    def down(request):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(relay, "_agent", lambda: httpx.AsyncClient(base_url="http://agent.test", transport=httpx.MockTransport(down)))
    reply = browser().post("/api/chat/conversations")
    assert reply.status_code == 503
    assert TestClient(app).get("/api/chat/config").json()["enabled"] is False


def test_config_follows_the_service_switch(agent):
    config = TestClient(app).get("/api/chat/config").json()
    assert config["enabled"] is True and config["max_message_chars"] == 500 and config["suggestions"] == {"zh": ["多久到货？"]}
    agent.enabled = False
    assert TestClient(app).get("/api/chat/config").json()["enabled"] is False


def test_online_follows_the_shop_hours():
    from datetime import datetime, timezone

    from demo_shop import store

    assert store.online(datetime(2026, 11, 24, 2, 0, tzinfo=timezone.utc))  # 北京时间 10:00
    assert not store.online(datetime(2026, 11, 24, 16, 0, tzinfo=timezone.utc))  # 北京时间 0:00
    settings = TestClient(app).get("/shop-api/settings", headers=SHOP).json()
    assert isinstance(settings["online"], bool) and settings["away_message"]


def test_warranty_dates_follow_today():
    """样例订单写的是几天前交付，质保到期日按店铺所在地的今天现算。"""
    from datetime import datetime, timezone

    from demo_shop import store

    now = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)  # 北京时间 11 月 25 日
    until = {o["order_no"]: o["warranty_until"] for o in store.orders("member-a", now)}
    assert until == {"EX1001": "2026-12-21", "EX1002": None, "EX1003": "2026-10-27"}
    assert "delivered_days_ago" not in store.orders("member-a", now)[0]


def test_notices_are_kept_for_the_owner():
    client = TestClient(app)
    notice = {"kind": "handoff", "summary": "售前咨询", "conversation_id": "c1", "email": "a@example.com"}
    assert client.post("/shop-api/notifications", json=notice).status_code == 401
    assert client.post("/shop-api/notifications", json=notice, headers=SHOP).status_code == 204
    assert notice in client.get("/shop-api/notifications", headers=SHOP).json()


def test_pages_and_widget_are_revalidated():
    """聊天窗和页面更新后，买家下次打开就是新的：带 no-cache 和 ETag，没变时回 304。"""
    client = TestClient(app)
    first = client.get("/web/app.js")
    assert first.headers["cache-control"] == "no-cache" and first.headers["etag"]
    assert client.get("/web/app.js", headers={"If-None-Match": first.headers["etag"]}).status_code == 304
    assert client.get("/").headers["cache-control"] == "no-cache"


def test_shop_api_lists_all_help_articles():
    """客服服务从这里同步知识库：各语言都有，同一篇的编号相同，正文不带开头的说明块。"""
    client = TestClient(app)
    assert client.get("/shop-api/articles").status_code == 401
    articles = client.get("/shop-api/articles", headers=SHOP).json()
    assert {a["lang"] for a in articles} >= {"zh"} and all(set(a) == {"id", "lang", "title", "kind", "markdown"} for a in articles)
    assert not any(a["markdown"].startswith("---") for a in articles)
    assert {a["id"] for a in articles if a["lang"] == "zh"} == {a["id"] for a in client.get("/api/shop/help").json()}
