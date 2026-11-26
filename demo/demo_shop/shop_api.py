"""给客服服务调的店铺接口（技术方案 §5.2）。鉴权：服务密钥；和某位访客有关的，再带访客令牌。"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from demo_shop import settings, store, tokens


def require_key(x_api_key: str = Header(default="")) -> None:
    if not settings.SHOP_API_KEY or not hmac.compare_digest(x_api_key, settings.SHOP_API_KEY):
        raise HTTPException(401, "店铺接口密钥不对")


router = APIRouter(prefix="/shop-api", dependencies=[Depends(require_key)])


def visitor(x_visitor_token: str = Header(default="")) -> str:
    """没带令牌或令牌失效都按游客算：游客没有能看的订单。"""
    return (x_visitor_token and tokens.read(settings.TOKEN_SECRET, x_visitor_token)) or "guest"


@router.get("/articles")
def shop_articles() -> list[dict]:
    """帮助文章，客服服务拿来同步知识库。"""
    return [{key: a[key] for key in ("id", "lang", "title", "kind", "markdown")} for a in store.articles()]


@router.get("/settings")
def shop_settings() -> dict:
    info = store.info()
    return {"name": info["name"], "contacts": info["contacts"], "reply_hours": info["reply_hours"], "online": store.online(), "away_message": info["away_message"]}


@router.get("/products")
def products(q: str = "") -> list[dict]:
    return [{key: item[key] for key in ("name", "price", "in_stock", "delivery")} for item in store.products(q)]


@router.get("/orders")
def orders(who: str = Depends(visitor)) -> list[dict]:
    return store.order_summaries(who)


class TicketIn(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)


class NoticeIn(BaseModel):
    kind: str = Field(max_length=30)  # handoff 转人工；daily_limit 今天的 AI 用量到上限了
    summary: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(None, max_length=64)
    email: str | None = Field(None, max_length=200)


@router.post("/notifications", status_code=204)
def notify(body: NoticeIn) -> None:
    """客服服务请店主知道的事。真店铺在这里提醒店主，比如后台通知、发邮件。"""
    store.add_notice(body.model_dump())


@router.get("/notifications")
def notices() -> list[dict]:
    return store.notices()


@router.post("/orders/{order_no}/tickets", status_code=201)
def create_ticket(order_no: str, body: TicketIn, who: str = Depends(visitor)) -> dict:
    ticket = store.create_ticket(who, order_no, body.summary)
    if ticket is None:
        raise HTTPException(403, "这位访客打不开这张订单")
    return {"ticket_no": ticket}
