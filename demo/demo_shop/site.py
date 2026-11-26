"""模拟店铺网页用的接口：商品、我的订单、帮助、切换身份。"""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from demo_shop import identity, store

router = APIRouter(prefix="/api/shop")


@router.get("/me")
def me(request: Request, response: Response) -> dict:
    identity.ensure_browser(request, response)
    info = store.info()
    return {"who": identity.current(request)[0], "name": info["name"], "brand": info["brand"]}


class IdentityIn(BaseModel):
    who: str


@router.post("/identity")
def switch(body: IdentityIn, request: Request, response: Response) -> dict:
    if body.who not in store.IDENTITIES:
        raise HTTPException(400, "没有这个身份")
    identity.ensure_browser(request, response)
    response.set_cookie("who", body.who, max_age=90 * 86400, httponly=True, samesite="lax")
    return {"who": body.who}


@router.get("/products")
def products() -> list[dict]:
    return store.products()


@router.get("/orders")
def orders(request: Request) -> list[dict]:
    """店铺自己的订单页：本人能看到卡密，这是卡密唯一出现的地方。"""
    return [{key: value for key, value in order.items() if key != "email"} for order in store.orders(identity.current(request)[0])]


@router.get("/help")
def help_articles() -> list[dict]:
    return store.help_articles()
