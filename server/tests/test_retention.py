"""到期清理：老会话连同消息一起删；评测用到的检索过程留下。"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from customer_agent import retention
from customer_agent.db import Base, ChatMessage, Conversation, EvalResult, EvalRun, IndexVersion, KnowledgeBase, RetrievalTrace


def test_old_records_go_and_eval_traces_stay():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    now = datetime(2026, 11, 24)
    old, recent = now - timedelta(days=91), now - timedelta(days=5)
    with Session(engine) as session:
        kb = KnowledgeBase(name="t")
        session.add(kb)
        session.flush()
        index = IndexVersion(kb_id=kb.id, name="v1", chunker="heading", chunk_size=400, overlap=40, embed_model="fake")
        session.add(index)
        session.flush()
        for created in (old, recent):
            cid = uuid.uuid4().hex
            session.add(Conversation(id=cid, kb_id=kb.id, index_id=index.id, visitor_id="v", created_at=created))
            session.flush()
            session.add(ChatMessage(conversation_id=cid, role="user", text="hi"))
        traces = [RetrievalTrace(index_id=index.id, query=q, config={}, stages=[], took_ms=1, created_at=at) for q, at in (("老的", old), ("评测的", old), ("新的", recent))]
        session.add_all(traces)
        run = EvalRun(index_id=index.id, question_set="t", config={}, scores={}, status="done", total=1)
        session.add(run)
        session.flush()
        session.add(EvalResult(run_id=run.id, question_id="q1", trace_id=traces[1].id))
        session.commit()

        cleaned = retention.clean(session, now=now)

        assert (cleaned.conversations, cleaned.traces) == (1, 1)
        assert len(session.scalars(select(ChatMessage)).all()) == 1
        assert sorted(session.scalars(select(RetrievalTrace.query)).all()) == ["新的", "评测的"]
