"""总开关和限额：关了就不接；每个会话、每个访客每天的次数；用量到上限时提醒店主一次。"""

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from customer_agent import service
from customer_agent.db import Base, ChatMessage, Conversation, IndexVersion, KnowledgeBase, UsageDaily


class Shop:
    def __init__(self):
        self.notices = []

    def notify(self, notice):
        self.notices.append(notice)


@pytest.fixture
def world():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        kb = KnowledgeBase(name="t")
        session.add(kb)
        session.flush()
        index = IndexVersion(kb_id=kb.id, name="v1", chunker="heading", chunk_size=400, overlap=40, embed_model="fake")
        session.add(index)
        session.flush()
        yield session, kb, index


def chat(session, kb, index, visitor="v", turns=0):
    conversation = Conversation(id=uuid.uuid4().hex, kb_id=kb.id, index_id=index.id, visitor_id=visitor)
    session.add(conversation)
    session.flush()
    session.add_all([ChatMessage(conversation_id=conversation.id, role="user", text="hi") for _ in range(turns)])
    session.commit()
    return conversation


def test_defaults_let_a_new_chat_through(world):
    session, kb, index = world
    service.check(session, chat(session, kb, index), Shop(), "hi")
    assert service.open_now(session)


def test_the_switch_stops_everything(world):
    session, kb, index = world
    service.current(session).enabled = False
    with pytest.raises(service.Refused) as refused:
        service.check(session, chat(session, kb, index), Shop(), "hi")
    assert refused.value.status == 503 and not service.open_now(session)


def test_turn_limits(world):
    session, kb, index = world
    service.current(session).per_conversation = 3
    with pytest.raises(service.Refused):
        service.check(session, chat(session, kb, index, turns=3), Shop(), "hi")
    service.current(session).per_visitor_day = 4
    chat(session, kb, index, visitor="w", turns=2)
    with pytest.raises(service.Refused) as refused:
        service.check(session, chat(session, kb, index, visitor="w", turns=2), Shop(), "hi")
    assert refused.value.status == 429
    service.check(session, chat(session, kb, index, visitor="other", turns=2), Shop(), "hi")


def test_the_daily_cap_pauses_and_tells_the_owner_once(world):
    session, kb, index = world
    service.current(session).daily_token_limit = 1000
    session.add(UsageDaily(kb_id=kb.id, day=date.today(), calls=3, input_tokens=900, output_tokens=200, cached_tokens=0))
    session.commit()
    shop = Shop()
    for _ in range(2):
        with pytest.raises(service.Refused):
            service.check(session, chat(session, kb, index), shop, "hi")
    assert [n.kind for n in shop.notices] == ["daily_limit"]
    assert not service.open_now(session)


def test_long_messages_are_refused(world):
    session, kb, index = world
    service.current(session).max_message_chars = 10
    service.check(session, chat(session, kb, index), Shop(), "一" * 10)
    with pytest.raises(service.Refused) as refused:
        service.check(session, chat(session, kb, index), Shop(), "一" * 11)
    assert refused.value.status == 422 and "10" in refused.value.message
