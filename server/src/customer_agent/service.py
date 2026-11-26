"""客服服务的总开关和限额。存在数据库里，后台可改；对话接口每收一条消息先过这里。"""

import logging

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from customer_agent import clock
from customer_agent.connectors.base import Notice, Shop
from customer_agent.db import ChatMessage, Conversation, ServiceSettings, UsageDaily

log = logging.getLogger(__name__)


class Refused(Exception):
    """这条消息不接。status 是给接入方的 HTTP 状态码。"""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def current(session: Session) -> ServiceSettings:
    """只有一行。第一次用时按默认值建出来；几个请求同时来建时只有一个建成，其余跳过。"""
    row = session.get(ServiceSettings, 1)
    if row is None:
        insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
        session.execute(insert(ServiceSettings).values(id=1).on_conflict_do_nothing(index_elements=["id"]))
        session.commit()
        row = session.get(ServiceSettings, 1)
    return row


def used_today(session: Session) -> int:
    """今天全店用了多少 token（输入加输出）。"""
    total = session.scalar(select(func.sum(UsageDaily.input_tokens + UsageDaily.output_tokens)).where(UsageDaily.day == clock.today()))
    return int(total or 0)


def open_now(session: Session) -> bool:
    """聊天窗现在能不能用：总开关开着，且今天的用量没到上限。"""
    row = current(session)
    return row.enabled and used_today(session) < row.daily_token_limit


def check(session: Session, conversation: Conversation, shop: Shop, text: str) -> None:
    """不接时抛 Refused。用量刚到上限的那天提醒店主一次。"""
    row = current(session)
    if not row.enabled:
        raise Refused(503, "AI 助手已暂停，可以联系人工客服")
    if len(text) > row.max_message_chars:
        raise Refused(422, f"一条消息最多 {row.max_message_chars} 字")
    used = used_today(session)
    if used >= row.daily_token_limit:
        if row.cap_notified_on != clock.today():
            try:
                shop.notify(Notice("daily_limit", f"今天的 AI 用量到上限了（{used} / {row.daily_token_limit} token），聊天窗已暂停，明天自动恢复；要提前恢复，到后台调高上限。"))
            except Exception:
                log.exception("用量到上限的提醒没发出去")
            row.cap_notified_on = clock.today()
            session.commit()
        raise Refused(503, "AI 助手今天暂时不可用，可以联系人工客服")
    turns = session.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.conversation_id == conversation.id, ChatMessage.role == "user"))
    if turns >= row.per_conversation:
        raise Refused(429, "这个对话聊得太长了，可以开一个新对话")
    since = clock.day_start(clock.today())
    visitor_turns = session.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .join(Conversation)
        .where(Conversation.visitor_id == conversation.visitor_id, Conversation.kb_id == conversation.kb_id, ChatMessage.role == "user", ChatMessage.created_at >= since)
    )
    if visitor_turns >= row.per_visitor_day:
        raise Refused(429, "今天的提问次数用完了，可以联系人工客服")
