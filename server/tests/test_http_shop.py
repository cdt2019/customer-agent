"""按接口调店铺：请求带对密钥和令牌，403 变成没权限。店铺用 httpx 的假传输代替。"""

import json

import httpx
import pytest

from customer_agent.connectors.base import Notice
from customer_agent.connectors.http_shop import HttpShop


def handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["X-Api-Key"] == "k"
    token = request.headers.get("X-Visitor-Token")
    if request.url.path == "/shop-api/settings":
        return httpx.Response(200, json={"name": "店", "contacts": "tg", "reply_hours": 12, "online": False, "away_message": "下班了", "extra": 1})
    if request.url.path == "/shop-api/articles":
        return httpx.Response(200, json=[{"id": "faq/pay", "lang": "zh", "title": "怎么付款", "kind": "faq", "markdown": "# 怎么付款\n支付宝", "category": "x"}])
    if request.url.path == "/shop-api/products":
        return httpx.Response(200, json=[{"name": "Plus", "price": "¥1", "in_stock": True, "delivery": "自动发货"}])
    if request.url.path == "/shop-api/orders":
        rows = [{"order_no": "A1", "product": "Plus", "status": "已交付", "paid": True, "delivered": True, "warranty_until": "2026-12-21", "open_ticket": None}]
        return httpx.Response(200, json=rows if token == "member" else [])
    if request.url.path.endswith("/tickets"):
        if token != "member":
            return httpx.Response(403, json={"detail": "no"})
        assert json.loads(request.content)["summary"] == "退款"
        return httpx.Response(201, json={"ticket_no": "T1"})
    if request.url.path == "/shop-api/notifications":
        assert json.loads(request.content) == {"kind": "handoff", "summary": "售前", "conversation_id": "c1", "email": None}
        return httpx.Response(204)
    return httpx.Response(404)


@pytest.fixture
def shop():
    return HttpShop("http://shop.test", "k", transport=httpx.MockTransport(handler))


def test_reads_settings_and_products(shop):
    assert shop.info().reply_hours == 12 and not shop.info().online
    assert shop.products("plus")[0].in_stock


def test_orders_need_a_visitor(shop):
    assert shop.orders(None) == []
    assert shop.orders("member")[0].order_no == "A1"
    assert shop.orders("member")[0].warranty_until.day == 21
    assert shop.orders("stranger") == []


def test_ticket_permission(shop):
    assert shop.create_ticket("member", "A1", "退款") == "T1"
    with pytest.raises(PermissionError):
        shop.create_ticket("stranger", "A1", "退款")


def test_notifies_a_handoff(shop):
    shop.notify(Notice("handoff", "售前", "c1"))


def test_reads_help_articles_and_turns_them_into_documents(shop, monkeypatch):
    """知识库来源写 shop 时，按接入方的帮助文章同步；多出来的字段不管。"""
    from customer_agent import kb_sources, runtime

    assert shop.articles()[0].title == "怎么付款"
    monkeypatch.setattr(runtime, "shop", lambda: shop)
    docs = list(kb_sources.documents(kb_sources.SHOP))
    assert [(d.source_id, d.lang, d.kind) for d in docs] == [("faq/pay", "zh", "faq")] and docs[0].markdown.startswith("# 怎么付款")
    assert kb_sources.available(kb_sources.SHOP) and not kb_sources.available(None) and not kb_sources.available("/no/such/folder")
