"""后台外框用：现在接的是哪家店。名字从接入方的店铺接口取（技术方案 §5.2），连不上时为空。"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from customer_agent import runtime

router = APIRouter()
log = logging.getLogger(__name__)


class ShopOut(BaseModel):
    name: str | None  # 连不上接入方时为空
    online: bool | None


@router.get("/api/shop")
def read_shop() -> ShopOut:
    try:
        info = runtime.shop().info()
    except Exception:
        log.exception("读不到接入方的店铺信息")
        return ShopOut(name=None, online=None)
    return ShopOut(name=info.name, online=info.online)
