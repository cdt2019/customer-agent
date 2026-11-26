"""Telegram 渠道（docs/10）：Telegram 用假接口，模型和检索用替身。"""

import io
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from PIL import Image as Pil
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from customer_agent import runtime, settings
from customer_agent.channels import telegram_bot
from customer_agent.channels.telegram import Telegram
from customer_agent.chat import staff
from customer_agent.connectors.base import ShopInfo
from customer_agent.db import Base, ChatMessage, Chunk, Conversation, Document, Image, IndexVersion, KnowledgeBase, RetrievalTrace, ServiceSettings
from customer_agent.llm import Finished, Reply, ToolRequest
from customer_agent.rag.retrieval import Retrieved


class FakeTelegram:
    """假的 Telegram 接口：排着队的新消息，记下发出去的。"""

    def __init__(self):
        self.queue, self.sent, self.actions = [], [], []

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content) if request.content else {}
        if request.url.path.startswith("/file/"):
            out = io.BytesIO()
            Pil.new("RGB", (40, 30), "red").save(out, format="JPEG")
            return httpx.Response(200, content=out.getvalue())
        result = {
            "getMe": lambda: {"username": "shop_bot"},
            "getUpdates": lambda: [u for u in self.queue if u["update_id"] >= body["offset"]],
            "sendMessage": lambda: self.sent.append(body) or {},
            "sendChatAction": lambda: self.actions.append(body) or True,
            "getFile": lambda: {"file_path": "photos/a.jpg", "file_size": 1000},
        }[method]()
        return httpx.Response(200, json={"ok": True, "result": result})


class Model:
    """先查资料，再按资料回答。"""

    def stream(self, messages, tools, tool_choice=None):
        if messages[-1]["role"] != "tool":
            yield Finished("", [ToolRequest("c1", "search_knowledge", '{"query": "到货"}')], 100, 10, 0)
            return
        yield "**付款后一分钟**内发货[1]。"
        yield Finished("**付款后一分钟**内发货[1]。", [], 100, 10, 0)

    def complete(self, system, user):
        return Reply("否", 5, 1)


class Retriever:
    def retrieve(self, session, index, query, recipe):
        doc = session.scalars(select(Document)).first()
        chunk = session.scalars(select(Chunk)).first()
        trace = RetrievalTrace(index_id=index.id, query=query, config={}, stages=[], took_ms=1)
        session.add(trace)
        session.flush()
        return [Retrieved(chunk, doc, 0.9)], trace


class Shop:
    def info(self):
        return ShopInfo("示例商店", "Telegram：@support", 12, True, "")

    def orders(self, visitor):
        return []


def private(update_id: int, text: str = "", user: int = 42, **extra) -> dict:
    message = {"chat": {"id": user, "type": "private"}, "from": {"id": user, "language_code": "zh-hans"}, **extra}
    if text:
        message["text"] = text
    return {"update_id": update_id, "message": message}


@pytest.fixture
def world(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    fake = FakeTelegram()
    bot = Telegram("123:abc", transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(telegram_bot, "DbSession", Session)
    monkeypatch.setattr(runtime, "telegram", lambda: bot)
    monkeypatch.setattr(runtime, "shop", Shop)
    monkeypatch.setattr(runtime, "chat_model", Model)
    monkeypatch.setattr(runtime, "retriever_for", lambda index, recipe: Retriever())
    monkeypatch.setattr(settings, "IMAGES_DIR", tmp_path)
    with Session() as session:
        kb = KnowledgeBase(name="t")
        session.add(kb)
        session.flush()
        index = IndexVersion(kb_id=kb.id, name="v1", chunker="heading", chunk_size=400, overlap=40, embed_model="fake")
        doc = Document(kb_id=kb.id, source_id="faq/when", lang="zh", title="多久到货", kind="faq", markdown="付款后一分钟内发货。", content_hash="h")
        session.add_all([index, doc, ServiceSettings(id=1, suggestions={"zh": ["多久到货？"]})])
        session.flush()
        session.add(Chunk(index_id=index.id, document_id=doc.id, doc_hash="h", seq=0, heading_path=["到货"], text="付款后一分钟内发货。"))
        session.commit()
        monkeypatch.setattr(settings, "TELEGRAM_INDEX_ID", index.id)
    return fake, bot, Session


def test_a_question_gets_one_plain_answer_with_sources(world):
    fake, bot, Session = world
    fake.queue = [private(1, "多久到货")]
    telegram_bot.run_once(bot)
    assert fake.sent[-1]["chat_id"] == 42 and fake.sent[-1]["text"] == "付款后一分钟内发货[1]。\n\n出处：[1] 多久到货"
    assert fake.actions and fake.actions[0]["action"] == "typing"
    with Session() as session:
        conversation = session.scalars(select(Conversation)).one()
        assert (conversation.channel, conversation.visitor_id) == ("telegram", "tg:42")
        assert session.get(ServiceSettings, 1).telegram_offset == 2


def test_each_update_is_handled_once(world):
    fake, bot, Session = world
    fake.queue = [private(1, "多久到货")]
    telegram_bot.run_once(bot)
    telegram_bot.run_once(bot)  # 位置已经往后挪，同一条不会再回
    assert len(fake.sent) == 1


def test_start_shows_the_suggestions_and_groups_are_ignored(world):
    fake, bot, _ = world
    group = {"update_id": 2, "message": {"chat": {"id": -5, "type": "group"}, "from": {"id": 7}, "text": "多久到货"}}
    fake.queue = [private(1, "/start"), group]
    telegram_bot.run_once(bot)
    assert len(fake.sent) == 1 and "示例商店" in fake.sent[0]["text"] and fake.sent[0]["reply_markup"]["keyboard"] == [[{"text": "多久到货？"}]]


def test_new_start_and_a_long_silence_start_a_new_conversation(world):
    fake, bot, Session = world
    fake.queue = [private(1, "多久到货"), private(2, "/new"), private(3, "多久到货"), private(4, "/start"), private(5, "多久到货")]
    telegram_bot.run_once(bot)
    with Session() as session:
        assert len(session.scalars(select(Conversation)).all()) == 3
        old = session.scalars(select(ChatMessage)).all()
        for message in old:
            message.created_at = datetime.now(UTC) - timedelta(days=2)
        session.commit()
    fake.queue.append(private(6, "多久到货"))
    telegram_bot.run_once(bot)
    with Session() as session:
        assert len(session.scalars(select(Conversation)).all()) == 4


def test_staff_replies_are_pushed_to_telegram(world):
    fake, bot, Session = world
    fake.queue = [private(1, "多久到货")]
    telegram_bot.run_once(bot)
    with Session() as session:
        conversation = session.scalars(select(Conversation)).one()
        staff.reply(session, conversation, "您好，我来处理")
        staff.release(session, conversation, staff.HANDED_BACK)
    assert [m["text"] for m in fake.sent[-2:]] == ["您好，我来处理", staff.HANDED_BACK]
    # 客服在接时买家的话不调模型、不回
    with Session() as session:
        staff.reply(session, session.scalars(select(Conversation)).one(), "在吗")
    sent = len(fake.sent)
    fake.queue.append(private(2, "在的"))
    telegram_bot.run_once(bot)
    assert len(fake.sent) == sent


def test_paused_service_replies_with_contacts(world):
    fake, bot, Session = world
    with Session() as session:
        session.get(ServiceSettings, 1).enabled = False
        session.commit()
    fake.queue = [private(1, "多久到货")]
    telegram_bot.run_once(bot)
    assert "Telegram：@support" in fake.sent[-1]["text"]


def test_photos_are_cleaned_and_attached(world):
    fake, bot, Session = world
    fake.queue = [private(1, photo=[{"file_id": "small"}, {"file_id": "big"}])]
    telegram_bot.run_once(bot)
    with Session() as session:
        image = session.scalars(select(Image)).one()
        assert (image.width, image.height) == (40, 30)
        assert session.get(ChatMessage, image.message_id).text == "[图片]"


def test_sources_from_the_same_article_are_listed_once():
    sources = [{"n": 1, "title": "兑换礼品卡"}, {"n": 3, "title": "地区"}, {"n": 4, "title": "兑换礼品卡"}]
    assert telegram_bot.plain("**看这里**", sources, "出处") == "看这里\n\n出处：[1][4] 兑换礼品卡；[3] 地区"
