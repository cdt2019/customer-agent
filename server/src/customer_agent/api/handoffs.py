"""后台的转人工列表：待处理、没通知到、已处理。没通知到的可以重新通知，处理完的标掉。"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from customer_agent import runtime
from customer_agent.api.chats import HandoffRecord, handoff_out
from customer_agent.api.deps import db
from customer_agent.connectors.base import Notice
from customer_agent.db import ChatMessage, Conversation, Handoff

router = APIRouter(prefix="/api/handoffs")

LIST_LIMIT = 200


class HandoffList(BaseModel):
    counts: dict[str, int]  # 每个状态各有几条
    rows: list[HandoffRecord]


@router.get("/counts")
def counts(session: DbSession = Depends(db)) -> dict[str, int]:
    """每个状态各有几条，加上 replies：客服接手中、买家说了话还没回的会话。左侧菜单的「转人工」后面显示待处理、没通知到和 replies 的条数。"""
    found = dict(session.execute(select(Handoff.status, func.count()).group_by(Handoff.status)).all())
    last = select(ChatMessage.role).where(ChatMessage.conversation_id == Conversation.id, ChatMessage.role.in_(("user", "staff"))).order_by(ChatMessage.id.desc()).limit(1).scalar_subquery()
    replies = session.scalar(select(func.count()).select_from(Conversation).where(Conversation.status == "staff", last == "user")) or 0
    return {name: found.get(name, 0) for name in ("open", "unnotified", "done")} | {"replies": replies}


@router.get("")
def list_handoffs(status: Literal["open", "unnotified", "done"] = "open", session: DbSession = Depends(db)) -> HandoffList:
    rows = session.execute(
        select(Handoff, Conversation.visitor_id).join(Conversation).where(Handoff.status == status).order_by(Handoff.id.desc()).limit(LIST_LIMIT)
    ).all()
    return HandoffList(counts=counts(session), rows=[handoff_out(h, visitor) for h, visitor in rows])


def _get(session: DbSession, handoff_id: int) -> Handoff:
    row = session.get(Handoff, handoff_id)
    if row is None:
        raise HTTPException(404, "没有这条转人工")
    return row


@router.post("/{handoff_id}/done", status_code=204)
def mark_done(handoff_id: int, session: DbSession = Depends(db)) -> None:
    _get(session, handoff_id).status = "done"
    session.commit()


@router.post("/{handoff_id}/notify", status_code=204)
def notify_again(handoff_id: int, session: DbSession = Depends(db)) -> None:
    """再通知一次店铺。成功后回到待处理。"""
    row = _get(session, handoff_id)
    if row.status != "unnotified":
        raise HTTPException(409, "这条已经通知过了")
    try:
        runtime.shop().notify(Notice("handoff", row.summary, row.conversation_id, row.email))
    except Exception as error:
        raise HTTPException(502, "还是没通知到店铺，稍后再试") from error
    row.status = "open"
    session.commit()
