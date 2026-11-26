"""模型能调的四个工具。访客身份由代码带着，不在工具参数里，模型改不了。"""

import json
from dataclasses import asdict, dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from customer_agent import clock
from customer_agent.chat import handoff
from customer_agent.chat.guard import redact
from customer_agent.connectors.base import Shop
from customer_agent.db import Conversation, Handoff, IndexVersion
from customer_agent.rag.retrieval import Recipe, Retriever

RECIPE = Recipe(dense=True, keyword=True)  # 默认配方，见 docs/05 §12.5


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required}}}


SCHEMAS = [
    _tool("search_knowledge", "查店铺的帮助资料：商品说明、付款、到货、兑换、质保、退款规则。", {"query": {"type": "string", "description": "要查的内容，一次一件事"}}, ["query"]),
    _tool("lookup_product", "查商品的实时价格、库存和交付方式。", {"query": {"type": "string", "description": "商品名关键词，比如 plus"}}, ["query"]),
    _tool("my_orders", "查当前这位买家自己的订单状态。不需要参数。", {}, []),
    _tool(
        "transfer_to_human",
        "转人工。需要人决定的事、或买家要找人时调用。",
        {
            "summary": {"type": "string", "description": "给客服看的摘要：买家想解决什么、试过什么、相关状态"},
            "order_no": {"type": "string", "description": "相关订单号，没有就不传"},
            "email": {"type": "string", "description": "买家留的邮箱，没有订单时需要"},
        },
        ["summary"],
    ),
]


@dataclass
class ToolContext:
    session: Session
    conversation: Conversation
    index: IndexVersion
    retriever: Retriever
    shop: Shop
    visitor: str | None
    sources: list[dict] = field(default_factory=list)  # 这一轮查到的资料，编号全程递增
    handoff: Handoff | None = None


def search_knowledge(ctx: ToolContext, query: str = "", **_) -> tuple[dict, int | None]:
    found, trace = ctx.retriever.retrieve(ctx.session, ctx.index, query, RECIPE)
    results = []
    for item in found[: RECIPE.limit]:
        known = next((s for s in ctx.sources if s["chunk_id"] == item.chunk.id), None)
        if known is None:
            known = {"n": len(ctx.sources) + 1, "chunk_id": item.chunk.id, "document": item.document.source_id, "title": item.document.title}
            ctx.sources.append(known)
        results.append({"编号": known["n"], "内容": item.text})
    return {"资料": results}, trace.id


def lookup_product(ctx: ToolContext, query: str = "", **_) -> tuple[dict, None]:
    return {"商品": [asdict(item) for item in ctx.shop.products(query)]}, None


def my_orders(ctx: ToolContext, **_) -> tuple[dict, None]:
    orders = ctx.shop.orders(ctx.visitor)
    if not orders:
        return {"结果": "这里查不到这位买家的订单（没在网店登录，或者是从 Telegram 这类渠道来的）。可以引导到网店的「查订单」页用下单邮箱查找，不要在聊天里收订单号和邮箱。"}, None
    today = clock.today()
    rows = [{**asdict(order), "warranty_until": warranty(order.warranty_until, today)} for order in orders]
    return {"订单": rows, "说明": "warranty_until 已按今天算好，照着说，不要自己算日期；质保期只说时间，这次问题算不算在保由客服认定。"}, None


def warranty(until: date | None, today: date) -> str:
    if until is None:
        return "没有质保期（还没交付）"
    left = (until - today).days
    if left < 0:
        return f"已过期，{until} 到期"
    return f"今天到期（{until}）" if left == 0 else f"还剩 {left} 天，{until} 到期"


def transfer_to_human(ctx: ToolContext, summary: str = "", order_no: str = "", email: str = "", **_) -> tuple[dict, None]:
    if ctx.conversation.status == "handoff":
        return {"结果": "这件事已经转过人工了，告诉买家等客服回复即可。"}, None
    ctx.handoff = handoff.transfer(ctx.session, ctx.conversation, ctx.shop, ctx.visitor, summary, order_no, email)
    if ctx.handoff is None:
        return {"结果": "还不能转：这位买家没有可关联的订单。请向买家要一个邮箱，拿到后再调用。同时可以给出店铺联系方式。"}, None
    info = ctx.shop.info()
    hours = info.reply_hours
    if ctx.handoff.ticket_no:
        result = f"已转人工，工单号 {ctx.handoff.ticket_no}，客服一般 {hours} 小时内回复，进度在订单页看。"
    elif ctx.handoff.email:
        result = f"已转人工，这次没有工单号，不要提工单号。客服一般 {hours} 小时内回复到 {ctx.handoff.email}。"
    else:
        result = f"已转人工，这次没有工单号，不要提工单号。客服一般 {hours} 小时内在这个对话里回复。"
    if not info.online:
        result += f"现在不在客服时间：{info.away_message}"
    return {"结果": result, "回答要求": "告诉买家这个结果（不在客服时间的话也要说），再用一两句讲查到的相关规则，不下结论。"}, None


HANDLERS = {"search_knowledge": search_knowledge, "lookup_product": lookup_product, "my_orders": my_orders, "transfer_to_human": transfer_to_human}


def run_tool(ctx: ToolContext, name: str, arguments: str) -> tuple[str, dict, int | None]:
    """执行一次工具调用，返回 (给模型看的结果, 记录用的参数, 检索记录编号)。出错也告诉模型，不让对话断掉。"""
    try:
        args = json.loads(arguments or "{}")
        result, trace_id = HANDLERS[name](ctx, **args)
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        return json.dumps({"错误": f"工具调用不对：{error}"}, ensure_ascii=False), {}, None
    logged = {key: redact(value) if isinstance(value, str) else value for key, value in args.items()}
    return json.dumps(result, ensure_ascii=False), logged, trace_id
