"""「今天」按业务时区算：限额和统计从那里的零点开始，跟服务器和数据库在哪个时区无关。"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from customer_agent import clock, settings


def test_a_business_day_starts_at_local_midnight(monkeypatch):
    monkeypatch.setattr(settings, "TIMEZONE", ZoneInfo("Asia/Shanghai"))
    assert clock.day_start(date(2026, 11, 25)) == datetime(2026, 11, 24, 16, 0, tzinfo=UTC)
    monkeypatch.setattr(settings, "TIMEZONE", ZoneInfo("Europe/Berlin"))
    assert clock.day_start(date(2026, 11, 25)) == datetime(2026, 11, 24, 23, 0, tzinfo=UTC)


def test_today_follows_the_business_time_zone(monkeypatch):
    monkeypatch.setattr(settings, "TIMEZONE", ZoneInfo("Pacific/Kiritimati"))  # UTC+14，比 UTC 早一天的时候最多
    ahead = clock.today()
    monkeypatch.setattr(settings, "TIMEZONE", ZoneInfo("Pacific/Honolulu"))  # UTC-10，正好差 24 小时，任何时刻都差一天
    assert (ahead - clock.today()).days == 1
