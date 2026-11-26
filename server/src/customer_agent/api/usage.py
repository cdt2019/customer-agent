"""后台的用量和花费：最近几天每天用了多少 token，按后台填的单价估算花费。"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from customer_agent import clock, service
from customer_agent.api.deps import db
from customer_agent.db import ChatMessage, ServiceSettings, UsageDaily

router = APIRouter()


class DayUsage(BaseModel):
    day: date
    input_tokens: int  # 含命中缓存的部分
    cached_tokens: int
    output_tokens: int
    cost: float  # 估算，元


class UsageOut(BaseModel):
    days: list[DayUsage]  # 从早到晚，没用量的日子也列出来
    used_today: int
    limit: int
    open_now: bool
    turns_today: int  # 今天回答了几条
    cost_month: float
    priced: bool  # 单价填了没有；没填时花费都是 0


def cost(row: ServiceSettings, input_tokens: int, cached: int, output: int) -> float:
    """按单价（每百万 token）估算，不分高峰和空闲时段。"""
    return ((input_tokens - cached) * row.price_input + cached * row.price_cached_input + output * row.price_output) / 1_000_000


def _sums(session: DbSession, start: date, end: date) -> dict[date, tuple[int, int, int]]:
    rows = session.execute(
        select(UsageDaily.day, func.sum(UsageDaily.input_tokens), func.sum(UsageDaily.cached_tokens), func.sum(UsageDaily.output_tokens))
        .where(UsageDaily.day >= start, UsageDaily.day <= end)
        .group_by(UsageDaily.day)
    ).all()
    return {day: (int(i or 0), int(c or 0), int(o or 0)) for day, i, c, o in rows}


@router.get("/api/usage")
def read_usage(days: int = Query(14, ge=1, le=90), session: DbSession = Depends(db)) -> UsageOut:
    settings = service.current(session)
    today = clock.today()
    start = today - timedelta(days=days - 1)
    sums = _sums(session, min(start, today.replace(day=1)), today)
    listed = []
    for n in range(days):
        day = start + timedelta(days=n)
        i, c, o = sums.get(day, (0, 0, 0))
        listed.append(DayUsage(day=day, input_tokens=i, cached_tokens=c, output_tokens=o, cost=round(cost(settings, i, c, o), 4)))
    month = [value for day, value in sums.items() if day >= today.replace(day=1)]
    turns = session.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.role == "assistant", ChatMessage.created_at >= clock.day_start(today))
    )
    return UsageOut(
        days=listed,
        used_today=service.used_today(session),
        limit=settings.daily_token_limit,
        open_now=service.open_now(session),
        turns_today=turns or 0,
        cost_month=round(sum(cost(settings, *value) for value in month), 4),
        priced=any((settings.price_input, settings.price_cached_input, settings.price_output)),
    )
