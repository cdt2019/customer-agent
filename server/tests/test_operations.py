"""后台运营的接口：会话记录、转人工、用量和花费、聊天窗设置。"""

import json
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from customer_agent import runtime
from customer_agent.api import chats, conversations, deps, handoffs, usage, widget
from customer_agent.db import Base, ChatMessage, Conversation, Handoff, IndexVersion, KnowledgeBase, ServiceSettings, ToolCallLog, UsageDaily


class Shop:
    def __init__(self):
        self.notices, self.fails = [], False

    def notify(self, notice):
        if self.fails:
            raise ConnectionError("down")
        self.notices.append(notice)


@pytest.fixture
def world(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    for module in (chats, handoffs, usage, widget):
        app.include_router(module.router)

    def db():
        with Session() as session:
            yield session

    app.dependency_overrides[deps.db] = db
    shop = Shop()
    monkeypatch.setattr(runtime, "shop", lambda: shop)
    with Session() as session:
        kb = KnowledgeBase(name="t")
        session.add(kb)
        session.flush()
        index = IndexVersion(kb_id=kb.id, name="v1", chunker="heading", chunk_size=400, overlap=40, embed_model="fake")
        session.add(index)
        session.commit()
        yield TestClient(app), session, kb, index, shop


def talk(session, kb, index, said, visitor="v", status="open"):
    now = datetime.now()
    conversation = Conversation(id=f"c{said[:3]}{visitor}", kb_id=kb.id, index_id=index.id, visitor_id=visitor, status=status, created_at=now)
    session.add(conversation)
    session.flush()
    asked = ChatMessage(conversation_id=conversation.id, role="user", text=said, created_at=now)
    answer = ChatMessage(conversation_id=conversation.id, role="assistant", text="回答", input_tokens=100, output_tokens=20, created_at=now + timedelta(seconds=3.5))
    session.add_all([asked, answer])
    session.flush()
    session.add(ToolCallLog(message_id=answer.id, name="search_knowledge", arguments={"query": said}, result="块", ms=40))
    session.commit()
    return conversation, answer


def test_chat_list_filters_and_detail(world):
    client, session, kb, index, _ = world
    talk(session, kb, index, "礼品卡怎么兑换")
    handed, _ = talk(session, kb, index, "兑换码已被使用", status="handoff")
    session.add(Handoff(conversation_id=handed.id, kind="ticket", ticket_no="T42", summary="s"))
    _, disliked = talk(session, kb, index, "能开发票吗")
    disliked.feedback = 0
    session.commit()

    listed = client.get("/api/chats").json()
    assert listed["counts"] == {"conversations": 3, "messages": 3, "handoffs": 1, "down": 1, "wrong": 0}
    assert [r["first"] for r in client.get("/api/chats", params={"show": "handoff"}).json()["rows"]] == ["兑换码已被使用"]
    assert [r["first"] for r in client.get("/api/chats", params={"show": "down"}).json()["rows"]] == ["能开发票吗"]
    assert [r["first"] for r in client.get("/api/chats", params={"q": "T42"}).json()["rows"]] == ["兑换码已被使用"]
    assert [r["first"] for r in client.get("/api/chats", params={"q": "发票"}).json()["rows"]] == ["能开发票吗"]

    detail = client.get(f"/api/chats/{handed.id}").json()
    answer = detail["messages"][1]
    assert answer["seconds"] == 3.5 and answer["tokens"] == 120 and answer["steps"][0]["name"] == "search_knowledge"
    assert detail["handoffs"][0]["ticket_no"] == "T42"


def test_mark_wrong_then_export(world):
    client, session, kb, index, _ = world
    conversation, answer = talk(session, kb, index, "工单多久处理")
    url = f"/api/chats/{conversation.id}/messages/{answer.id}/wrong"
    assert client.put(url, json={"reason": "答成了到账时间"}).status_code == 204
    assert client.get("/api/chats", params={"show": "wrong"}).json()["counts"]["wrong"] == 1

    exported = client.get("/api/chats/export/wrong.jsonl").text.strip().splitlines()
    question = json.loads(exported[0])
    assert question["q"] == "工单多久处理" and "答成了到账时间" in question["note"] and question["id"] == f"chat-{answer.id}"

    client.put(url, json={"reason": None})
    assert client.get("/api/chats/export/wrong.jsonl").text == ""
    assert client.put(f"/api/chats/other/messages/{answer.id}/wrong", json={"reason": "x"}).status_code == 404


def test_handoff_states(world):
    client, session, kb, index, shop = world
    conversation, _ = talk(session, kb, index, "可以开发票吗")
    row = Handoff(conversation_id=conversation.id, kind="record", email="a@b.c", summary="买家要发票", status="unnotified")
    session.add(row)
    session.commit()

    listed = client.get("/api/handoffs", params={"status": "unnotified"}).json()
    assert listed["counts"] == {"open": 0, "unnotified": 1, "done": 0, "replies": 0} and listed["rows"][0]["visitor_id"] == "v"

    shop.fails = True
    assert client.post(f"/api/handoffs/{row.id}/notify").status_code == 502
    shop.fails = False
    assert client.post(f"/api/handoffs/{row.id}/notify").status_code == 204
    assert shop.notices[0].email == "a@b.c"
    assert client.get("/api/handoffs/counts").json() == {"open": 1, "unnotified": 0, "done": 0, "replies": 0}
    assert client.post(f"/api/handoffs/{row.id}/notify").status_code == 409
    assert client.post(f"/api/handoffs/{row.id}/done").status_code == 204
    assert client.get("/api/handoffs").json()["counts"] == {"open": 0, "unnotified": 0, "done": 1, "replies": 0}


def test_usage_fills_days_and_prices(world):
    client, session, kb, index, _ = world
    session.add(ServiceSettings(id=1, price_input=2, price_cached_input=0.2, price_output=8))
    session.add(UsageDaily(kb_id=kb.id, day=date.today(), calls=2, input_tokens=1_000_000, cached_tokens=500_000, output_tokens=100_000))
    session.commit()

    out = client.get("/api/usage", params={"days": 3}).json()
    assert [d["input_tokens"] for d in out["days"]] == [0, 0, 1_000_000]
    assert out["days"][-1]["cost"] == pytest.approx(0.5 * 2 + 0.5 * 0.2 + 0.1 * 8)
    assert out["used_today"] == 1_100_000 and out["priced"]
    assert out["cost_month"] == pytest.approx(1.9)


def test_shop_name_for_the_admin_frame(monkeypatch):
    from customer_agent.api import shop as shop_api
    from customer_agent.connectors.base import ShopInfo

    app = FastAPI()
    app.include_router(shop_api.router)
    client = TestClient(app)

    class Up:
        def info(self):
            return ShopInfo(name="示例商店", contacts="", reply_hours=12, online=True, away_message="")

    class Down:
        def info(self):
            raise ConnectionError("down")

    monkeypatch.setattr(runtime, "shop", Up)
    assert client.get("/api/shop").json() == {"name": "示例商店", "online": True}
    monkeypatch.setattr(runtime, "shop", Down)
    assert client.get("/api/shop").json() == {"name": None, "online": None}


def test_widget_suggestions_are_edited_in_the_admin_and_reach_the_widget(world):
    """常见问题在后台改，接入方从 /v1/status 拿给聊天窗；空的语言不存，太长、太多的不收。"""
    client, session, *_ = world
    assert client.get("/api/widget-settings").json() == {"suggestions": {}}
    saved = client.put("/api/widget-settings", json={"suggestions": {"zh": [" 多久到货？ ", "怎么付款"], "en": []}})
    assert saved.json() == {"suggestions": {"zh": ["多久到货？", "怎么付款"]}}
    assert conversations.status(session).suggestions == {"zh": ["多久到货？", "怎么付款"]}
    assert client.put("/api/widget-settings", json={"suggestions": {"zh": ["问"] * 7}}).status_code == 422
    assert client.put("/api/widget-settings", json={"suggestions": {"zh": ["长" * 61]}}).status_code == 422
    assert client.put("/api/widget-settings", json={"suggestions": {"中文": ["问"]}}).status_code == 422


def test_system_info_never_shows_the_service_key(monkeypatch):
    from customer_agent import settings
    from customer_agent.api import system

    app = FastAPI()
    app.include_router(system.router)
    monkeypatch.setattr(settings, "SERVICE_API_KEY", "secret-key")
    out = TestClient(app).get("/api/system").json()
    assert out["service_key_set"] is True and "secret-key" not in json.dumps(out)
    assert out["llm_model"] == settings.LLM_MODEL
