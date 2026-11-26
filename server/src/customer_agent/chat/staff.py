"""人工接管（docs/07）：客服在后台发了话，会话变成 staff，AI 不再回答，买家的话只存下来给客服看。

客服点「交还给 AI」，或者 STAFF_IDLE 内没再说话，会话回到 open。
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from customer_agent import channels
from customer_agent.chat import guard
from customer_agent.chat.agent import Event
from customer_agent.db import ChatMessage, Conversation

STAFF_IDLE = timedelta(minutes=30)
RELEASED = "客服暂时离开了，有问题可以继续问 AI 助手。"
HANDED_BACK = "客服这边先处理到这里，有问题可以继续问 AI 助手。"


def reply(session: Session, conversation: Conversation, text: str) -> ChatMessage:
    """客服发一句。客服的话不打码：客服是自己人（docs/07 待定 3）。"""
    message = ChatMessage(conversation_id=conversation.id, role="staff", text=text)
    conversation.status, conversation.staff_at = "staff", datetime.now(UTC)
    session.add(message)
    session.commit()
    channels.push(conversation, text)
    return message


def release(session: Session, conversation: Conversation, note: str | None = None) -> None:
    """交还给 AI。note 是给买家看的一句说明，存成 system 消息。"""
    conversation.status, conversation.staff_at = "open", None
    if note:
        session.add(ChatMessage(conversation_id=conversation.id, role="system", text=note))
    session.commit()
    if note:
        channels.push(conversation, note)


def expire(session: Session, conversation: Conversation, now: datetime | None = None) -> None:
    """客服太久没说话就自动交还。不另开定时任务：读会话、发消息时顺手查一下。"""
    if conversation.status != "staff" or conversation.staff_at is None:
        return
    spoke = conversation.staff_at.replace(tzinfo=conversation.staff_at.tzinfo or UTC)  # 测试用的 SQLite 读回来不带时区，库里存的都是 UTC
    if (now or datetime.now(UTC)) - spoke > STAFF_IDLE:
        release(session, conversation, RELEASED)


def buyer_says(session: Session, conversation: Conversation, text: str) -> Iterator[Event]:
    """客服接手时买家发的话：打码后存下来，不调模型。"""
    said = guard.redact(text)
    message = ChatMessage(conversation_id=conversation.id, role="user", text=said)
    session.add(message)
    session.commit()
    yield Event("user", {"text": said, "message_id": message.id})
    yield Event("done", {"message_id": message.id, "staff": True, "sources": [], "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0})


def seen(session: Session, conversation: Conversation) -> None:
    """买家的聊天窗来拉过消息：记下最近一次在看的时间，后台显示买家还在不在。"""
    conversation.visitor_seen_at = datetime.now(UTC)
    session.commit()
