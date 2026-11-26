"""店铺数据：商品、订单、帮助文章从 data/ 读；工单和给店主的通知只记在内存里。"""

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import cache

from demo_shop import settings

IDENTITIES = ("guest", "member-a", "member-b")
SUMMARY_FIELDS = ("order_no", "product", "status", "paid", "delivered", "warranty_until", "open_ticket")
_tickets: list[dict] = []
_notices: list[dict] = []


@cache
def _data() -> dict:
    return json.loads((settings.DATA_DIR / "shop.json").read_text(encoding="utf-8"))


def info() -> dict:
    return _data()["info"]


def _local(now: datetime | None = None) -> datetime:
    """店铺所在时区的现在。"""
    return (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=info()["hours"]["utc_offset"])))


def online(now: datetime | None = None) -> bool:
    """现在是不是客服在线时间。"""
    hours = info()["hours"]
    return hours["open"] <= _local(now).strftime("%H:%M") < hours["close"]


def widget() -> dict:
    return _data()["widget"]


def products(query: str = "") -> list[dict]:
    items = _data()["products"]
    words = query.lower().split()
    matched = [item for item in items if any(word in item["name"].lower() for word in words)]
    return matched or items  # 没对上名字时给全部，由模型自己判断


def orders(who: str, now: datetime | None = None) -> list[dict]:
    """这个身份的订单，含卡密，只给店铺自己的订单页用。
    样例数据只写「几天前交付」，质保到期日按今天和商品的质保天数现算，样例不会随时间过期。"""
    warranty_days = {p["name"]: p["warranty_days"] for p in _data()["products"]}
    today = _local(now).date()
    rows = []
    for order in _data()["orders"].get(who, []):
        row = {key: value for key, value in order.items() if key != "delivered_days_ago"}
        ago = order["delivered_days_ago"]
        row["warranty_until"] = None if ago is None else (today - timedelta(days=ago - warranty_days[order["product"]])).isoformat()
        rows.append(row)
    for row in rows:
        mine = [t["ticket_no"] for t in _tickets if t["order_no"] == row["order_no"]]
        row["open_ticket"] = mine[-1] if mine else row["open_ticket"]
    return rows


def order_summaries(who: str) -> list[dict]:
    """给客服服务看的订单摘要：没有卡密、邮箱和付款账号。"""
    return [{field: order[field] for field in SUMMARY_FIELDS} for order in orders(who)]


def create_ticket(who: str, order_no: str, summary: str) -> str | None:
    if order_no not in {order["order_no"] for order in orders(who)}:
        return None
    ticket = f"T{uuid.uuid4().hex[:8].upper()}"
    _tickets.append({"ticket_no": ticket, "order_no": order_no, "summary": summary})
    return ticket


def add_notice(notice: dict) -> None:
    _notices.append(notice)


def notices() -> list[dict]:
    return list(_notices)


_FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)


@cache
def articles() -> list[dict]:
    """全部帮助文章，各语言都有。编号是「目录/文件名」，不带语言；客服服务按编号同步，出处也按它链回帮助页。"""
    root = settings.DATA_DIR / "posts"
    found = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        front = _FRONT.match(text)
        meta = dict(line.split(": ", 1) for line in front[1].splitlines() if ": " in line) if front else {}
        stem, _, lang = path.relative_to(root).as_posix().removesuffix(".md").rpartition(".")
        found.append({
            "id": stem,
            "lang": lang,
            "title": meta.get("title", stem),
            "kind": meta.get("kind", path.parent.name),
            "category": meta.get("category", ""),
            "markdown": text[front.end():].strip() if front else text,
        })
    return found


def help_articles() -> list[dict]:
    """帮助页用的中文文章。"""
    return [{"id": a["id"], "title": a["title"], "category": a["category"], "body": a["markdown"]} for a in articles() if a["lang"] == "zh"]
