"""转人工：模型调工具和买家点按钮都走这里。有订单建工单；没订单的记下来并通知接入方提醒店主；都没有就转不成。"""

import logging
import re

from sqlalchemy.orm import Session

from customer_agent.chat import images
from customer_agent.chat.guard import redact
from customer_agent.connectors.base import Notice, Shop
from customer_agent.db import Conversation, Handoff

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
log = logging.getLogger(__name__)


def transfer(session: Session, conversation: Conversation, shop: Shop, visitor: str | None, summary: str, order_no: str = "", email: str = "") -> Handoff | None:
    """转成了返回转人工记录；没有能关联的订单、也没有邮箱时返回空。调用前先看会话是不是已经转过。"""
    summary = redact(summary)[:2000]
    pictures = images.count(session, conversation.id)
    if pictures:  # 图片模型看不到，提醒客服到会话里看（docs/09）
        summary += f"\n（买家发了 {pictures} 张图片，在客服后台的会话记录里看）"
    email = email.strip()
    owned = {order.order_no for order in shop.orders(visitor)}
    if not order_no and len(owned) == 1:
        order_no = next(iter(owned))
    if order_no in owned:
        handoff = Handoff(conversation_id=conversation.id, kind="ticket", ticket_no=shop.create_ticket(visitor, order_no, summary), summary=summary)
    elif EMAIL.match(email):
        handoff = Handoff(conversation_id=conversation.id, kind="record", email=email, summary=summary)
    elif owned:  # 有身份但说不清是哪一单：客服能看到这位买家的订单，不用再要邮箱
        handoff = Handoff(conversation_id=conversation.id, kind="record", summary=summary)
    else:
        return None
    session.add(handoff)
    conversation.status = "handoff"
    if handoff.kind == "record":
        try:
            shop.notify(Notice("handoff", summary, conversation.id, handoff.email))
        except Exception:
            log.exception("转人工没通知到接入方：%s", conversation.id)
            handoff.status = "unnotified"  # 记录还在，后台能看到这条没通知到
    return handoff
