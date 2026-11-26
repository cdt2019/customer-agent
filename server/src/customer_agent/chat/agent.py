"""对话循环：模型决定调哪个工具，最后给出回答。一边做一边吐事件，接口把它们流给前端。"""

import json
import re
import time
from collections import Counter
from collections.abc import Generator, Iterator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from customer_agent import clock
from customer_agent.chat import guard
from customer_agent.chat.prompts import NEEDS_HUMAN, SECRET_SENT, system_prompt
from customer_agent.chat.tools import SCHEMAS, ToolContext, run_tool
from customer_agent.connectors.base import Shop
from customer_agent.db import ChatMessage, Conversation, IndexVersion, ToolCallLog, UsageDaily
from customer_agent.llm import ChatModel, Finished
from customer_agent.rag.retrieval import Retriever

HISTORY_MESSAGES = 12
CITATION = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class Event:
    type: str  # user（买家的话，已打码，带存库后的编号）/ status（在调哪个工具）/ text / clear（撤掉已流出的文字）/ handoff / done
    data: dict


def record_usage(session: Session, kb_id: int, input_tokens: int, output_tokens: int, cached: int) -> None:
    insert = (pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert)(UsageDaily)
    statement = insert.values(kb_id=kb_id, day=clock.today(), calls=1, input_tokens=input_tokens, output_tokens=output_tokens, cached_tokens=cached)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["kb_id", "day"],
            set_={
                "calls": UsageDaily.calls + 1,
                "input_tokens": UsageDaily.input_tokens + input_tokens,
                "output_tokens": UsageDaily.output_tokens + output_tokens,
                "cached_tokens": UsageDaily.cached_tokens + cached,
            },
        )
    )


def _speak(session: Session, kb_id: int, llm: ChatModel, messages: list[dict], tools: list[dict] | None, spent: Counter, tool_choice: dict | None = None) -> Generator[Event, None, Finished]:
    """调一次模型，文字边出边流，用量记账。"""
    finished = None
    for piece in llm.stream(messages, tools, tool_choice):
        if isinstance(piece, Finished):
            finished = piece
        else:
            yield Event("text", {"text": piece})
    spent.update(input_tokens=finished.input_tokens, output_tokens=finished.output_tokens, cached_tokens=finished.cached_tokens)
    record_usage(session, kb_id, finished.input_tokens, finished.output_tokens, finished.cached_tokens)
    session.commit()
    return finished


def _needs_human(session: Session, kb_id: int, llm: ChatModel, said: str, spent: Counter) -> bool:
    reply = llm.complete(NEEDS_HUMAN, said)
    spent.update(input_tokens=reply.input_tokens, output_tokens=reply.output_tokens)
    record_usage(session, kb_id, reply.input_tokens, reply.output_tokens, 0)
    session.commit()
    return reply.text.strip().startswith("是")


def respond(
    session: Session, conversation: Conversation, index: IndexVersion, retriever: Retriever, shop: Shop, llm: ChatModel, visitor: str | None, text: str
) -> Iterator[Event]:
    """处理买家的一条消息。买家的话先打码，再发给模型和存库。"""
    said = guard.redact(text)
    past = session.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation.id, ChatMessage.role.in_(("user", "assistant", "staff"))).order_by(ChatMessage.id.desc()).limit(HISTORY_MESSAGES)
    ).all()
    asked = ChatMessage(conversation_id=conversation.id, role="user", text=said)
    session.add(asked)
    session.commit()
    yield Event("user", {"text": said, "message_id": asked.id})

    messages = [{"role": "system", "content": system_prompt(shop.info())}]
    # 客服说过的话也让模型知道，交还给 AI 之后才接得上
    messages += [{"role": "assistant", "content": f"（人工客服）{m.text}"} if m.role == "staff" else {"role": m.role, "content": m.text} for m in reversed(past)]
    secret_sent = said != text
    if secret_sent:
        messages.append({"role": "system", "content": SECRET_SENT})
    messages.append({"role": "user", "content": said})
    ctx = ToolContext(session, conversation, index, retriever, shop, visitor)
    logs: list[ToolCallLog] = []
    answer, spent = "", Counter()

    for round_ in range(guard.MAX_TOOL_ROUNDS + 1):
        # 工具次数用完后不再给工具，逼模型用已有的内容回答
        must_search = {"type": "function", "function": {"name": "search_knowledge"}} if secret_sent and round_ == 0 else None
        finished = yield from _speak(session, conversation.kb_id, llm, messages, SCHEMAS if round_ < guard.MAX_TOOL_ROUNDS else None, spent, must_search)
        if not finished.tool_requests:
            answer = finished.text
            break
        if finished.text:  # 调工具前的铺垫话不算回答，让前端撤掉
            yield Event("clear", {})
        messages.append({
            "role": "assistant",
            "content": finished.text,
            "tool_calls": [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}} for c in finished.tool_requests],
        })
        for call in finished.tool_requests:
            yield Event("status", {"tool": call.name})
            started = time.perf_counter()
            result, logged, trace_id = run_tool(ctx, call.name, call.arguments)
            logs.append(ToolCallLog(name=call.name, arguments=logged, result=guard.redact(result)[:4000], trace_id=trace_id, ms=round((time.perf_counter() - started) * 1000)))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    # 嘴上说转了却没调工具、该转的事还在反问、连着两次没答上（或上一条被点了没用又没答上）：代码替它转，再按真实结果重新回答
    previous = next((m for m in past if m.role == "assistant"), None)
    stuck = guard.unanswered(answer) and previous is not None and (guard.unanswered(previous.text) or previous.feedback == 0)
    if conversation.status != "handoff" and (stuck or guard.claims_handoff(answer) or (guard.offers_handoff(answer) and _needs_human(session, conversation.kb_id, llm, said, spent))):
        yield Event("clear", {})
        yield Event("status", {"tool": "transfer_to_human"})
        arguments = json.dumps({"summary": f"买家：{said}"}, ensure_ascii=False)
        result, logged, _ = run_tool(ctx, "transfer_to_human", arguments)
        logs.append(ToolCallLog(name="transfer_to_human", arguments={**logged, "补转": True}, result=guard.redact(result)[:4000], trace_id=None, ms=0))
        messages.append({"role": "assistant", "content": "", "tool_calls": [{"id": "guard-transfer", "type": "function", "function": {"name": "transfer_to_human", "arguments": arguments}}]})
        messages.append({"role": "tool", "tool_call_id": "guard-transfer", "content": result})
        answer = (yield from _speak(session, conversation.kb_id, llm, messages, None, spent)).text

    # 这一轮没查到的编号（比如照着历史里的回答抄来的）指向空处：去掉，并让前端换成去掉后的文字
    known = {s["n"] for s in ctx.sources}
    checked = CITATION.sub(lambda m: m[0] if int(m[1]) in known else "", answer)
    if checked != answer:
        answer = re.sub(r"[ \t]+(?=[，。；：、！？,.;:!?\n]|$)", "", checked)
        yield Event("clear", {})
        yield Event("text", {"text": answer})
    cited = {int(n) for n in CITATION.findall(answer)}
    sources = [{"n": s["n"], "title": s["title"], "document": s["document"]} for s in ctx.sources if s["n"] in cited]
    message = ChatMessage(conversation_id=conversation.id, role="assistant", text=answer, sources=sources, **spent)
    session.add(message)
    session.flush()
    for log in logs:
        log.message_id = message.id
        session.add(log)
    session.commit()
    if ctx.handoff:
        info = shop.info()
        yield Event("handoff", {"kind": ctx.handoff.kind, "ticket_no": ctx.handoff.ticket_no, "email": ctx.handoff.email, "reply_hours": info.reply_hours, "away_message": None if info.online else info.away_message})
    yield Event("done", {"message_id": message.id, "sources": sources, "input_tokens": spent["input_tokens"], "output_tokens": spent["output_tokens"], "cached_tokens": spent["cached_tokens"]})
