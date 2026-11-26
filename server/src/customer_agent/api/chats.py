"""后台的会话记录：按条件列会话、看一个会话的每一步、客服直接回复和交还给 AI（docs/07）、AI 起草（docs/08）、标答错、把答错的题导出成评测题。"""

import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from customer_agent import runtime
from customer_agent.api.conversations import ImageOut, image_file, images_by_message
from customer_agent.api.deps import db
from customer_agent.chat import copilot, staff, tools
from customer_agent.db import ChatMessage, Conversation, Handoff, Image, IndexVersion, ToolCallLog

router = APIRouter(prefix="/api/chats")

LIST_LIMIT = 200


class ChatRow(BaseModel):
    id: str
    visitor_id: str
    channel: str
    created_at: datetime
    first: str  # 买家的第一句话
    turns: int
    status: str  # open / handoff / staff
    down: bool  # 有回答被点了没用
    wrong: bool  # 有回答被标了答错


class ChatCounts(BaseModel):
    conversations: int
    messages: int  # 买家发的消息
    handoffs: int
    down: int
    wrong: int


class ChatList(BaseModel):
    counts: ChatCounts
    rows: list[ChatRow]


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _has(condition) -> object:
    return select(ChatMessage.id).where(ChatMessage.conversation_id == Conversation.id, condition).exists()


@router.get("")
def list_chats(
    days: int = Query(7, ge=1, le=90),
    show: Literal["all", "handoff", "down", "wrong"] = "all",
    q: str = Query("", max_length=100),
    session: DbSession = Depends(db),
) -> ChatList:
    since = _since(days)
    query = select(Conversation).where(Conversation.created_at >= since)
    if show == "handoff":
        query = query.where(Conversation.status.in_(("handoff", "staff")))
    elif show == "down":
        query = query.where(_has(ChatMessage.feedback == 0))
    elif show == "wrong":
        query = query.where(_has(ChatMessage.wrong_reason.is_not(None)))
    if q.strip():
        word = q.strip()
        ticket = select(Handoff.id).where(Handoff.conversation_id == Conversation.id, Handoff.ticket_no == word).exists()
        query = query.where(or_(_has((ChatMessage.role == "user") & ChatMessage.text.contains(word, autoescape=True)), ticket))
    conversations = session.scalars(query.order_by(Conversation.created_at.desc()).limit(LIST_LIMIT)).all()

    messages = session.scalars(select(ChatMessage).where(ChatMessage.conversation_id.in_([c.id for c in conversations])).order_by(ChatMessage.id)).all()
    by_chat: dict[str, list[ChatMessage]] = {}
    for message in messages:
        by_chat.setdefault(message.conversation_id, []).append(message)
    rows = []
    for conversation in conversations:
        own = by_chat.get(conversation.id, [])
        said = [m for m in own if m.role == "user"]
        rows.append(ChatRow(
            id=conversation.id,
            visitor_id=conversation.visitor_id,
            channel=conversation.channel,
            created_at=conversation.created_at,
            first=said[0].text if said else "",
            turns=len(said),
            status=conversation.status,
            down=any(m.feedback == 0 for m in own),
            wrong=any(m.wrong_reason is not None for m in own),
        ))

    def count(statement) -> int:
        return session.scalar(statement) or 0

    in_range = ChatMessage.created_at >= since
    counts = ChatCounts(
        conversations=count(select(func.count()).select_from(Conversation).where(Conversation.created_at >= since)),
        messages=count(select(func.count()).select_from(ChatMessage).where(in_range, ChatMessage.role == "user")),
        handoffs=count(select(func.count()).select_from(Handoff).where(Handoff.created_at >= since)),
        down=count(select(func.count()).select_from(ChatMessage).where(in_range, ChatMessage.feedback == 0)),
        wrong=count(select(func.count()).select_from(ChatMessage).where(in_range, ChatMessage.wrong_reason.is_not(None))),
    )
    return ChatList(counts=counts, rows=rows)


class StepOut(BaseModel):
    name: str
    arguments: dict
    result: str
    ms: int


class ChatMessageOut(BaseModel):
    id: int
    role: str
    text: str
    sources: list[dict]
    feedback: int | None
    wrong_reason: str | None
    tokens: int  # 输入加输出
    seconds: float | None  # 从买家发出到回答存好；只有回答有
    created_at: datetime
    steps: list[StepOut]
    image: ImageOut | None  # 买家发的图


class HandoffRecord(BaseModel):
    id: int
    conversation_id: str
    visitor_id: str
    kind: str  # ticket 工单；record 记录（有邮箱按邮箱回，没邮箱是会员，看他的订单）
    ticket_no: str | None
    email: str | None
    summary: str
    status: str
    created_at: datetime


class ChatDetail(BaseModel):
    id: str
    visitor_id: str
    channel: str
    status: str  # open / handoff / staff
    visitor_seen_at: datetime | None  # 买家的聊天窗最近一次来拉消息，看买家还在不在
    created_at: datetime
    tokens: int
    messages: list[ChatMessageOut]
    handoffs: list[HandoffRecord]


def handoff_out(row: Handoff, visitor_id: str) -> HandoffRecord:
    return HandoffRecord(
        id=row.id, conversation_id=row.conversation_id, visitor_id=visitor_id, kind=row.kind, ticket_no=row.ticket_no,
        email=row.email, summary=row.summary, status=row.status, created_at=row.created_at,
    )


def _conversation(session: DbSession, conversation_id: str) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(404, "没有这个会话")
    staff.expire(session, conversation)
    return conversation


@router.get("/{conversation_id}")
def read_chat(conversation_id: str, session: DbSession = Depends(db)) -> ChatDetail:
    conversation = _conversation(session, conversation_id)
    messages = session.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation.id).order_by(ChatMessage.id)).all()
    calls = session.scalars(select(ToolCallLog).where(ToolCallLog.message_id.in_([m.id for m in messages])).order_by(ToolCallLog.id)).all()
    steps: dict[int, list[StepOut]] = {}
    for call in calls:
        steps.setdefault(call.message_id, []).append(StepOut(name=call.name, arguments=call.arguments, result=call.result, ms=call.ms))
    pictures = images_by_message(session, conversation.id)
    out, asked_at = [], None
    for m in messages:
        seconds = None
        if m.role == "user":
            asked_at = m.created_at
        elif m.role == "assistant" and asked_at is not None:
            seconds = round((m.created_at - asked_at).total_seconds(), 1)
        out.append(ChatMessageOut(
            id=m.id, role=m.role, text=m.text, sources=m.sources, feedback=m.feedback, wrong_reason=m.wrong_reason,
            tokens=m.input_tokens + m.output_tokens, seconds=seconds, created_at=m.created_at, steps=steps.get(m.id, []), image=pictures.get(m.id),
        ))
    handoffs = session.scalars(select(Handoff).where(Handoff.conversation_id == conversation.id).order_by(Handoff.id)).all()
    return ChatDetail(
        id=conversation.id, visitor_id=conversation.visitor_id, channel=conversation.channel, status=conversation.status,
        visitor_seen_at=conversation.visitor_seen_at, created_at=conversation.created_at, tokens=sum(m.tokens for m in out), messages=out,
        handoffs=[handoff_out(h, conversation.visitor_id) for h in handoffs],
    )


@router.get("/images/{image_id}", response_model=None)
def read_image(image_id: int, session: DbSession = Depends(db)):
    """后台看买家发的图。"""
    image = session.get(Image, image_id)
    if image is None:
        raise HTTPException(404, "没有这张图片")
    return image_file(image)


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/{conversation_id}/reply", status_code=204)
def reply(conversation_id: str, body: ReplyIn, session: DbSession = Depends(db)) -> None:
    """客服直接回复买家。第一句发出后会话由客服接手，AI 不再回答。"""
    staff.reply(session, _conversation(session, conversation_id), body.text.strip())


@router.post("/{conversation_id}/release", status_code=204)
def release(conversation_id: str, session: DbSession = Depends(db)) -> None:
    """交还给 AI。"""
    conversation = _conversation(session, conversation_id)
    if conversation.status != "staff":
        raise HTTPException(409, "这个会话现在不是客服在接")
    staff.release(session, conversation, staff.HANDED_BACK)


class DraftSource(BaseModel):
    title: str
    document: str


class DraftOut(BaseModel):
    text: str
    sources: list[DraftSource]  # 起草时用到的资料
    orders_at: datetime | None  # 订单信息是什么时候查的，提醒客服到店铺核对
    open_points: list[str]  # 草稿里【待确认】的内容


@router.post("/{conversation_id}/draft")
def draft(conversation_id: str, session: DbSession = Depends(db)) -> DraftOut:
    """AI 起草一条回复，客服改完再发。不存库；算进当天用量，到了上限也能用。"""
    conversation = _conversation(session, conversation_id)
    index = session.get(IndexVersion, conversation.index_id)
    try:
        llm = runtime.chat_model()
    except runtime.MissingKey as error:
        raise HTTPException(503, str(error)) from error
    result = copilot.draft(session, conversation, index, runtime.retriever_for(index, tools.RECIPE), llm)
    return DraftOut(text=result.text, sources=[DraftSource(**s) for s in result.sources], orders_at=result.orders_at, open_points=result.open_points)


class WrongIn(BaseModel):
    reason: str | None = Field(None, max_length=500)  # 空表示取消标记


@router.put("/{conversation_id}/messages/{message_id}/wrong", status_code=204)
def mark_wrong(conversation_id: str, message_id: int, body: WrongIn, session: DbSession = Depends(db)) -> None:
    message = session.get(ChatMessage, message_id)
    if message is None or message.role != "assistant" or message.conversation_id != conversation_id:
        raise HTTPException(404, "没有这条回答")
    message.wrong_reason = None if body.reason is None else body.reason.strip()
    session.commit()


@router.get("/export/wrong.jsonl", response_class=Response)
def export_wrong(days: int = Query(90, ge=1, le=90), session: DbSession = Depends(db)) -> Response:
    """标了答错的回答，连同买家问的那句，按评测题的格式导出（evals/<知识库>/questions.jsonl）。标准答案和该命中的资料要人补上。"""
    wrong = session.scalars(
        select(ChatMessage).where(ChatMessage.wrong_reason.is_not(None), ChatMessage.created_at >= _since(days)).order_by(ChatMessage.id)
    ).all()
    lines = []
    for message in wrong:
        asked = session.scalars(
            select(ChatMessage.text).where(ChatMessage.conversation_id == message.conversation_id, ChatMessage.role == "user", ChatMessage.id < message.id).order_by(ChatMessage.id.desc())
        ).first()
        lines.append(json.dumps({
            "id": f"chat-{message.id}",
            "q": asked or "",
            "kind": "kb",
            "expect_docs": [],
            "answer": "",
            "behavior": "answer",
            "note": f"线上答错：{message.wrong_reason or '没写原因'}。当时的回答：{message.text[:300]}",
        }, ensure_ascii=False))
    return Response("\n".join(lines) + ("\n" if lines else ""), media_type="application/x-ndjson", headers={"Content-Disposition": 'attachment; filename="wrong-answers.jsonl"'})
