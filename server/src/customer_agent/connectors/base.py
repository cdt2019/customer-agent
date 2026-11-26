"""接入方要提供什么。对话只认这个接口，不知道背后是哪家店。

visitor 是接入方签发的访客令牌，这里原样带回去，能看哪些订单由接入方判断。
返回的结构里没有卡密、完整邮箱和付款账号这些字段，想说也说不出来。
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class Product:
    name: str
    price: str
    in_stock: bool
    delivery: str


@dataclass(frozen=True)
class OrderSummary:
    order_no: str
    product: str
    status: str
    paid: bool
    delivered: bool
    warranty_until: date | None  # 质保到期那天；没交付的没有
    open_ticket: str | None


@dataclass(frozen=True)
class Article:
    id: str  # 接入方的编号，同一篇文章的各语言版本编号相同
    lang: str
    title: str
    kind: str  # 分类，比如 faq、guide
    markdown: str


@dataclass(frozen=True)
class Notice:
    """要店主知道的事。kind：handoff 没挂在订单上的转人工；daily_limit 今天的用量到上限了。"""

    kind: str
    summary: str
    conversation_id: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class ShopInfo:
    name: str
    contacts: str
    reply_hours: int
    online: bool  # 现在是不是客服在线时间，由接入方按自己的营业时间算
    away_message: str  # 不在线时给买家看的说明


class Shop(Protocol):
    def info(self) -> ShopInfo: ...

    def articles(self) -> list[Article]: ...

    def products(self, query: str) -> list[Product]: ...

    def orders(self, visitor: str | None) -> list[OrderSummary]: ...

    def create_ticket(self, visitor: str | None, order_no: str, summary: str) -> str:
        """给这位访客能打开的订单建工单，返回工单号；打不开时抛 PermissionError。"""
        ...

    def notify(self, notice: Notice) -> None:
        """请接入方提醒店主，用它自己的方式（后台通知、邮件、即时消息）。"""
        ...
