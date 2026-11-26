"""时间：库里一律存带时区的时间，代码里用 UTC；「今天」按业务时区（settings.TIMEZONE）算，每天的限额和统计从那里的零点开始。"""

from datetime import UTC, date, datetime, time

from customer_agent import settings


def today() -> date:
    return datetime.now(settings.TIMEZONE).date()


def day_start(day: date) -> datetime:
    """业务时区里这一天零点，换成 UTC。"""
    return datetime.combine(day, time.min, settings.TIMEZONE).astimezone(UTC)
