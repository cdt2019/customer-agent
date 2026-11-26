"""渠道：买家从哪来，回复怎么送到。网页聊天窗自己来拉，不用推；Telegram 要推（docs/10）。

人工接管的代码只调 push，不认识具体的渠道。
"""

import logging

from customer_agent import runtime
from customer_agent.db import Conversation

log = logging.getLogger(__name__)
TELEGRAM = "telegram"
VISITOR_PREFIX = "tg:"  # Telegram 来的访客编号是 tg:<Telegram 用户编号>，私聊里也就是聊天编号


def push(conversation: Conversation, text: str) -> None:
    """把客服的话、交还说明送到买家那边。送不到只记日志，后台照样存着。"""
    bot = runtime.telegram()
    if conversation.channel != TELEGRAM or bot is None:
        return
    try:
        bot.send(int(conversation.visitor_id.removeprefix(VISITOR_PREFIX)), text)
    except Exception:
        log.exception("没推到 Telegram：%s", conversation.id)
