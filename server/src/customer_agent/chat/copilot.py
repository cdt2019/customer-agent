"""工单副驾驶（docs/08）：客服回复时，按这段对话、转人工摘要、对话里查过的订单和相关资料起草一份回复，客服改完再发。

草稿不存库，也不发给买家。要店铺拍板的地方写成【待确认：……】，由客服决定。
"""

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from customer_agent.chat.agent import record_usage
from customer_agent.chat.tools import RECIPE
from customer_agent.db import ChatMessage, Conversation, Handoff, IndexVersion, ToolCallLog
from customer_agent.llm import ChatModel
from customer_agent.rag.retrieval import Retrieved, Retriever

HISTORY_MESSAGES = 20
OPEN_POINT = re.compile(r"【待确认：([^】]+)】")
SPEAKER = {"user": "买家", "assistant": "AI 助手", "staff": "客服"}

PROMPT = """你在帮网店的人工客服起草一条回复。客服会看过、改过再发，你写的不会直接发给买家。

怎么写：
- 用客服的口吻，称「我们」，可以说「我来处理」「我核实一下」。简短、直接、有礼貌。
- 规则照下面的资料说，资料里没有的不要编。
- 要店铺拍板的事（退不退款、补不补发、算不算在保、封号怎么处理、付错的钱怎么办）不要替客服下结论，写成【待确认：要确认什么】，紧接着用一句话列出相关规则，方便客服决定。
- 资料里有计算方法（比如按剩余天数退款）就把方法写清楚，订单里有的数能代入就代入。
- 订单信息里已经有的（订单号、商品、状态）直接用，不要再问买家；只提订单号和状态，状态可能已经变了，不要说得太死。
- 不复述卡密、密码、验证码；买家发过也不要提。
- 买家用什么语言就用什么语言写。
- 只输出要发给买家的这一条回复，不要加解释、标题或引号。"""


@dataclass(frozen=True)
class Draft:
    text: str
    sources: list[dict]  # 起草时用到的资料：{"title", "document"}
    orders_at: datetime | None  # 订单信息是什么时候查的；对话里没查过订单时为空
    open_points: list[str]  # 草稿里【待确认】的内容


def _orders(session: Session, conversation: Conversation) -> tuple[str, datetime | None]:
    """对话里最近一次查订单的结果。后台没有访客令牌，不能重新查，只能用买家当时看到的。"""
    row = session.execute(
        select(ToolCallLog.result, ChatMessage.created_at)
        .join(ChatMessage, ToolCallLog.message_id == ChatMessage.id)
        .where(ChatMessage.conversation_id == conversation.id, ToolCallLog.name == "my_orders")
        .order_by(ToolCallLog.id.desc())
    ).first()
    return (row[0], row[1]) if row else ("", None)


def _knowledge(session: Session, index: IndexVersion, retriever: Retriever, queries: list[str]) -> list[Retrieved]:
    """每个问题各检索一次，按名次合并去重，取前 RECIPE.limit 块。"""
    found: dict[int, Retrieved] = {}
    for query in queries:
        hits, _ = retriever.retrieve(session, index, query, RECIPE)
        for hit in hits[: RECIPE.limit]:
            found.setdefault(hit.chunk.id, hit)
    return list(found.values())[: RECIPE.limit]


def draft(session: Session, conversation: Conversation, index: IndexVersion, retriever: Retriever, llm: ChatModel) -> Draft:
    past = session.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation.id, ChatMessage.role.in_(SPEAKER)).order_by(ChatMessage.id.desc()).limit(HISTORY_MESSAGES)
    ).all()[::-1]
    handoff = session.scalars(select(Handoff).where(Handoff.conversation_id == conversation.id).order_by(Handoff.id.desc())).first()
    orders, orders_at = _orders(session, conversation)
    asked = next((m.text for m in reversed(past) if m.role == "user"), "")
    knowledge = _knowledge(session, index, retriever, [q for q in (asked, handoff.summary if handoff else "") if q.strip()])

    parts = ["对话：\n" + "\n".join(f"{SPEAKER[m.role]}：{m.text}" for m in past)]
    if handoff:
        where = f"工单 {handoff.ticket_no}" if handoff.ticket_no else f"买家留的邮箱 {handoff.email}" if handoff.email else "没有工单和邮箱"
        parts.append(f"转人工的摘要（{where}）：{handoff.summary}")
    if orders:
        parts.append(f"订单（{orders_at:%Y-%m-%d %H:%M} 查的）：{orders}")
    parts.append("资料：\n" + "\n\n".join(f"[{n}] {hit.text}" for n, hit in enumerate(knowledge, 1)))
    reply = llm.complete(PROMPT, "\n\n".join(parts))
    record_usage(session, conversation.kb_id, reply.input_tokens, reply.output_tokens, 0)
    session.commit()

    text = reply.text.strip()
    sources = list({hit.document.source_id: {"title": hit.document.title, "document": hit.document.source_id} for hit in knowledge}.values())
    return Draft(text=text, sources=sources, orders_at=orders_at, open_points=OPEN_POINT.findall(text))
