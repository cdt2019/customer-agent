"""到期清理：聊天记录（含买家发的图片）和检索过程留 90 天（产品需求 §5.9）。评测用到的检索过程不删，那不是买家的数据。"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from customer_agent.chat import images
from customer_agent.db import Conversation, EvalResult, Image, RetrievalTrace

KEEP_DAYS = 90


@dataclass(frozen=True)
class Cleaned:
    conversations: int
    traces: int


def clean(session: Session, days: int = KEEP_DAYS, now: datetime | None = None) -> Cleaned:
    """删掉早于 days 天的会话（消息、工具调用、转人工、图片一起删）和检索过程。图片文件在库里删掉之后再删。"""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    old = select(Conversation.id).where(Conversation.created_at < cutoff)
    files = list(session.scalars(select(Image.stored_name).where(Image.conversation_id.in_(old))))
    conversations = session.execute(delete(Conversation).where(Conversation.created_at < cutoff)).rowcount
    used_by_evals = select(EvalResult.trace_id).where(EvalResult.trace_id.is_not(None))
    traces = session.execute(delete(RetrievalTrace).where(RetrievalTrace.created_at < cutoff, RetrievalTrace.id.not_in(used_by_evals))).rowcount
    session.commit()
    images.remove_files(files)
    return Cleaned(conversations, traces)
