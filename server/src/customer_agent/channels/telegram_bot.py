"""把 Telegram 的私聊接到对话上（docs/10）：收消息 → 和网页一样走对话流程 → 整段回过去。

买家只有 Telegram 账号，接入方不认识他，查不了订单（docs/10 §6，绑定以后再说），转人工按留邮箱走。
一个 Telegram 账号一个进行中的对话；超过 FRESH_AFTER 没说话，或者发 /new，就开新的。
"""

import asyncio
import logging
import re
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from customer_agent import channels, runtime, service, settings
from customer_agent.channels.telegram import Telegram
from customer_agent.chat import agent, images, staff, tools
from customer_agent.db import ChatMessage, Conversation, IndexVersion
from customer_agent.db import Session as DbSession

log = logging.getLogger(__name__)
FRESH_AFTER = timedelta(hours=24)
TYPING_EVERY = 4  # 秒；Telegram 的「正在输入」过 5 秒自己消失
RETRY_AFTER = 5  # 秒；连不上 Telegram 时等一会儿再拉
username: str | None = None  # 连上以后记下机器人的名字，后台「接入方」页显示

TEXTS = {
    "zh": {
        "welcome": "你好，我是{name} AI 助手。可以问商品、付款、到货和售后，需要人工时发 /human。\n查自己的订单请到网店的「查订单」页。",
        "new": "已经开了一个新对话。",
        "human": "我要转人工",
        "only": "现在只能收文字和图片。",
        "busy": "没回答成功，可以再发一次。",
        "images": "一个对话最多发 {n} 张图片，可以发 /new 开新对话，或者用文字描述。",
        "sources": "出处",
    },
    "en": {
        "welcome": "Hi, I'm the {name} AI assistant. Ask about products, payment, delivery or after-sales. Send /human any time to reach a person.\nTo look up your orders, use the order lookup page on our website.",
        "new": "Started a new chat.",
        "human": "I'd like to talk to a human",
        "only": "I can only take text and images for now.",
        "busy": "That didn't go through. Please send it again.",
        "images": "This chat can take at most {n} images. Send /new to start a new chat, or describe the problem in words.",
        "sources": "Sources",
    },
}


def language(message: dict) -> str:
    return "zh" if (message.get("from", {}).get("language_code") or "").startswith("zh") else "en"


def plain(answer: str, sources: list[dict], label: str) -> str:
    """Telegram 按纯文本发：去掉 Markdown 的加粗，出处在末尾列标题。同一篇文章的几段合成一条：[1][4] 标题。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", answer).strip()
    by_title: dict[str, list[int]] = {}
    for source in sources:
        by_title.setdefault(source["title"], []).append(source["n"])
    if by_title:
        text += f"\n\n{label}：" + "；".join("".join(f"[{n}]" for n in numbers) + f" {title}" for title, numbers in by_title.items())
    return text


def conversation_for(session: Session, user_id: int, fresh: bool = False) -> Conversation:
    """这个 Telegram 账号进行中的对话；没有、太久没说话或要新的就开一个。"""
    visitor = f"{channels.VISITOR_PREFIX}{user_id}"
    latest = session.scalars(
        select(Conversation).where(Conversation.channel == channels.TELEGRAM, Conversation.visitor_id == visitor).order_by(Conversation.created_at.desc())
    ).first()
    if latest and not fresh:
        spoke = session.scalar(select(ChatMessage.created_at).where(ChatMessage.conversation_id == latest.id).order_by(ChatMessage.id.desc()).limit(1)) or latest.created_at
        if datetime.now(UTC) - spoke.replace(tzinfo=spoke.tzinfo or UTC) < FRESH_AFTER:  # 测试用的 SQLite 读回来不带时区
            return latest
    index = session.get(IndexVersion, settings.TELEGRAM_INDEX_ID)
    conversation = Conversation(id=uuid.uuid4().hex, kb_id=index.kb_id, index_id=index.id, channel=channels.TELEGRAM, visitor_id=visitor)
    session.add(conversation)
    session.commit()
    return conversation


def handle(session: Session, bot: Telegram, update: dict) -> None:
    """处理一条 Telegram 消息。只理私聊。"""
    message = update.get("message")
    if not message or message.get("chat", {}).get("type") != "private":
        return
    chat_id, lang = message["chat"]["id"], language(message)
    words = TEXTS[lang]
    text = (message.get("text") or "").strip()
    if text == "/start":  # 点「开始」就是想从头聊：开新对话
        conversation_for(session, message["from"]["id"], fresh=True)
        name = runtime.shop().info().name
        bot.send(chat_id, words["welcome"].format(name=name), service.current(session).suggestions.get(lang) or None)
        return
    if text == "/new":
        conversation_for(session, message["from"]["id"], fresh=True)
        bot.send(chat_id, words["new"])
        return
    if text == "/human":
        text = words["human"]

    conversation = conversation_for(session, message["from"]["id"])
    staff.expire(session, conversation)
    cleaned = None
    if message.get("photo"):
        if images.count(session, conversation.id) >= images.PER_CONVERSATION:
            bot.send(chat_id, words["images"].format(n=images.PER_CONVERSATION))
            return
        try:
            cleaned = images.clean(bot.download(message["photo"][-1]["file_id"], images.MAX_BYTES) or b"")
        except images.Rejected as error:
            bot.send(chat_id, str(error))
            return
        text = images.TEXT
    if not text:
        bot.send(chat_id, words["only"])
        return

    if conversation.status == "staff":
        events = staff.buyer_says(session, conversation, text)
    else:
        try:
            service.check(session, conversation, runtime.shop(), text)
        except service.Refused as refused:
            bot.send(chat_id, f"{refused.message}。{runtime.shop().info().contacts}")
            return
        index = session.get(IndexVersion, conversation.index_id)
        events = agent.respond(session, conversation, index, runtime.retriever_for(index, tools.RECIPE), runtime.shop(), runtime.chat_model(), None, text)

    answer, sources, typed = "", [], 0.0
    for event in events:
        if time.monotonic() - typed > TYPING_EVERY:
            bot.typing(chat_id)
            typed = time.monotonic()
        if event.type == "user" and cleaned:
            images.attach(session, conversation.id, event.data["message_id"], cleaned)
        elif event.type == "text":
            answer += event.data["text"]
        elif event.type == "clear":
            answer = ""
        elif event.type == "done":
            sources = event.data.get("sources", [])
    if answer:
        bot.send(chat_id, plain(answer, sources, words["sources"]))


def run_once(bot: Telegram) -> None:
    """拉一批新消息，一条条处理；每处理完一条记下位置，重启后不重复回。"""
    with DbSession() as session:
        offset = service.current(session).telegram_offset
    for update in bot.updates(offset):  # 长轮询，没新消息时会等一会儿，这时不占着库
        with DbSession() as session:
            try:
                handle(session, bot, update)
            except Exception:
                session.rollback()
                log.exception("Telegram 消息处理失败：%s", update.get("update_id"))
                chat = update.get("message", {}).get("chat", {})
                if chat.get("type") == "private":
                    bot.send(chat["id"], TEXTS[language(update["message"])]["busy"])
            service.current(session).telegram_offset = update["update_id"] + 1
            session.commit()


async def run_forever(bot: Telegram) -> None:
    """服务启动时起的后台任务。Telegram 连不上时等一会儿再拉，不影响别的。"""
    global username
    while True:
        try:
            if username is None:
                username = (await asyncio.to_thread(bot.me))["username"]
            await asyncio.to_thread(run_once, bot)
        except Exception:
            log.exception("Telegram 拉消息失败，%s 秒后再试", RETRY_AFTER)
            await asyncio.sleep(RETRY_AFTER)
