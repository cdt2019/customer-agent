"""按技术方案 §5.2 的接口调接入方。模拟店铺和以后的真实接入方都照这组接口实现。"""

from dataclasses import asdict
from datetime import date

import httpx

from customer_agent.connectors.base import Article, Notice, OrderSummary, Product, ShopInfo


class HttpShop:
    def __init__(self, base_url: str, api_key: str, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(base_url=base_url, headers={"X-Api-Key": api_key}, timeout=15, transport=transport, trust_env=False)

    def _get(self, path: str, visitor: str | None = None, **params) -> list | dict:
        headers = {"X-Visitor-Token": visitor} if visitor else {}
        response = self._client.get(path, params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    def info(self) -> ShopInfo:
        data = self._get("/shop-api/settings")
        return ShopInfo(name=data["name"], contacts=data["contacts"], reply_hours=data["reply_hours"], online=data["online"], away_message=data["away_message"])

    def articles(self) -> list[Article]:
        return [Article(**{field: item[field] for field in Article.__dataclass_fields__}) for item in self._get("/shop-api/articles")]

    def products(self, query: str) -> list[Product]:
        return [Product(**item) for item in self._get("/shop-api/products", q=query)]

    def orders(self, visitor: str | None) -> list[OrderSummary]:
        if not visitor:
            return []
        rows = [{field: row.get(field) for field in OrderSummary.__dataclass_fields__} for row in self._get("/shop-api/orders", visitor)]
        return [OrderSummary(**{**row, "warranty_until": row["warranty_until"] and date.fromisoformat(row["warranty_until"])}) for row in rows]

    def create_ticket(self, visitor: str | None, order_no: str, summary: str) -> str:
        response = self._client.post(f"/shop-api/orders/{order_no}/tickets", json={"summary": summary}, headers={"X-Visitor-Token": visitor or ""})
        if response.status_code == 403:
            raise PermissionError(order_no)
        response.raise_for_status()
        return response.json()["ticket_no"]

    def notify(self, notice: Notice) -> None:
        self._client.post("/shop-api/notifications", json=asdict(notice)).raise_for_status()
