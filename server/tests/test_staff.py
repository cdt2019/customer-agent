"""人工接管（docs/07）：客服回复后 AI 不再答，买家拉得到客服的话，交还或太久没说话后 AI 接着答。"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from customer_agent import runtime, settings
from customer_agent.api import chats, conversations, deps, handoffs
from customer_agent.chat import staff
from customer_agent.db import Base, ChatMessage, Conversation, IndexVersion, KnowledgeBase

KEY = {"X-Api-Key": "k"}


@pytest.fixture
def world(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    for module in (chats, conversations, handoffs):
        app.include_router(module.router)

    def db():
        with Session() as session:
            yield session

    app.dependency_overrides[deps.db] = db
    monkeypatch.setattr(settings, "SERVICE_API_KEY", "k")

    def no_model():
        raise AssertionError("客服接手时不该调模型")

    monkeypatch.setattr(runtime, "chat_model", no_model)
    with Session() as session:
        kb = KnowledgeBase(name="t")
        session.add(kb)
        session.flush()
        index = IndexVersion(kb_id=kb.id, name="v1", chunker="heading", chunk_size=400, overlap=40, embed_model="fake")
        session.add(index)
        session.flush()
        conversation = Conversation(id="c1", kb_id=kb.id, index_id=index.id, visitor_id="v", status="handoff")
        session.add_all([conversation, ChatMessage(conversation_id="c1", role="user", text="我要退款"), ChatMessage(conversation_id="c1", role="assistant", text="已转人工")])
        session.commit()
    return TestClient(app), Session


def events(response) -> list[dict]:
    return [{"type": block.split("\n")[0][7:], "data": json.loads(block.split("\n")[1][6:])} for block in response.text.strip().split("\n\n")]


def test_staff_reply_takes_over_and_the_buyer_pulls_it(world):
    client, Session = world
    last = client.get("/v1/conversations/c1", headers=KEY).json()["messages"][-1]["id"]
    assert client.post("/api/chats/c1/reply", json={"text": "您好，我来处理"}).status_code == 204

    pulled = client.get("/v1/conversations/c1", params={"after": last}, headers=KEY).json()
    assert pulled["status"] == "staff" and [(m["role"], m["text"]) for m in pulled["messages"]] == [("staff", "您好，我来处理")]
    with Session() as session:
        assert session.get(Conversation, "c1").visitor_seen_at is not None

    # 客服接手时买家的话只存下来，不调模型
    said = events(client.post("/v1/conversations/c1/messages", json={"text": "订单 EX1001"}, headers=KEY))
    assert [e["type"] for e in said] == ["user", "done"] and said[-1]["data"]["staff"] is True
    assert client.get("/api/handoffs/counts").json()["replies"] == 1
    client.post("/api/chats/c1/reply", json={"text": "收到"})
    assert client.get("/api/handoffs/counts").json()["replies"] == 0
    assert client.get("/api/chats", params={"show": "handoff"}).json()["rows"][0]["status"] == "staff"


def test_release_hands_back_to_ai(world):
    client, Session = world
    assert client.post("/api/chats/c1/release").status_code == 409
    client.post("/api/chats/c1/reply", json={"text": "您好"})
    assert client.post("/api/chats/c1/release").status_code == 204
    assert client.get("/api/chats/c1").json()["status"] == "open"


def test_staff_idle_too_long_hands_back_with_a_note(world):
    _, Session = world
    with Session() as session:
        conversation = session.get(Conversation, "c1")
        staff.reply(session, conversation, "您好")
        staff.expire(session, conversation, datetime.now(UTC) + timedelta(minutes=10))
        assert conversation.status == "staff"
        staff.expire(session, conversation, datetime.now(UTC) + staff.STAFF_IDLE + timedelta(minutes=1))
        assert conversation.status == "open"
        note = session.scalars(select(ChatMessage).where(ChatMessage.role == "system")).one()
        assert note.text == staff.RELEASED
