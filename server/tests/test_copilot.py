"""工单副驾驶（docs/08）：材料拼对了、找得出【待确认】、草稿不存库、用量记账。模型和检索用替身。"""

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from customer_agent.chat import copilot
from customer_agent.db import Base, ChatMessage, Chunk, Conversation, Document, Handoff, IndexVersion, KnowledgeBase, RetrievalTrace, ToolCallLog, UsageDaily
from customer_agent.llm import Reply
from customer_agent.rag.retrieval import Retrieved


class Model:
    def __init__(self, text):
        self.text, self.seen = text, []

    def complete(self, system, user):
        self.seen.append(user)
        return Reply(self.text, 300, 50)


class Retriever:
    def __init__(self):
        self.queries = []

    def retrieve(self, session, index, query, recipe):
        self.queries.append(query)
        doc = session.scalars(select(Document)).first()
        chunk = session.scalars(select(Chunk)).first()
        return [Retrieved(chunk, doc, 0.9)], RetrievalTrace(index_id=index.id, query=query, config={}, stages=[], took_ms=1)


@pytest.fixture
def world():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        kb = KnowledgeBase(name="t")
        session.add(kb)
        session.flush()
        index = IndexVersion(kb_id=kb.id, name="v1", chunker="heading", chunk_size=400, overlap=40, embed_model="fake")
        doc = Document(kb_id=kb.id, source_id="faq/refund", lang="zh", title="退款规则", kind="faq", markdown="未使用的卡密可以退。", content_hash="h")
        session.add_all([index, doc])
        session.flush()
        session.add(Chunk(index_id=index.id, document_id=doc.id, doc_hash="h", seq=0, heading_path=["退款"], text="未使用的卡密可以退。"))
        conversation = Conversation(id="c1", kb_id=kb.id, index_id=index.id, visitor_id="v", status="handoff")
        session.add(conversation)
        asked = ChatMessage(conversation_id="c1", role="user", text="EX1001 的卡密用不了，我要退款")
        answer = ChatMessage(conversation_id="c1", role="assistant", text="已转人工")
        session.add_all([asked, answer])
        session.flush()
        session.add(ToolCallLog(message_id=answer.id, name="my_orders", arguments={}, result='{"订单": [{"order_no": "EX1001", "status": "已交付"}]}', ms=1))
        session.add(Handoff(conversation_id="c1", kind="ticket", ticket_no="T1", summary="卡密无效要退款"))
        session.commit()
        yield session, conversation, index


def test_draft_uses_the_conversation_orders_and_knowledge(world):
    session, conversation, index = world
    model, retriever = Model("您好，我来核实。【待确认：是否退款】未使用的卡密可以退。"), Retriever()
    result = copilot.draft(session, conversation, index, retriever, model)

    prompt = model.seen[0]
    assert "买家：EX1001 的卡密用不了" in prompt and "工单 T1" in prompt and "EX1001" in prompt and "[1] " in prompt
    assert retriever.queries == ["EX1001 的卡密用不了，我要退款", "卡密无效要退款"]
    assert result.open_points == ["是否退款"] and result.sources == [{"title": "退款规则", "document": "faq/refund"}]
    assert result.orders_at is not None
    # 草稿不存库，用量记账
    assert session.scalar(select(func.count()).select_from(ChatMessage)) == 2
    assert session.get(UsageDaily, (conversation.kb_id, date.today())).input_tokens == 300


def test_no_orders_checked_means_no_order_time(world):
    session, conversation, index = world
    session.query(ToolCallLog).delete()
    session.commit()
    result = copilot.draft(session, conversation, index, Retriever(), Model("您好"))
    assert result.orders_at is None and result.open_points == []
