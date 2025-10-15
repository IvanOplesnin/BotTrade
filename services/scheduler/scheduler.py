import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


TZ_DEFAULT = ZoneInfo("Europe/Moscow")

def parse_hhmm(s: str) -> time:
    # принимает "HH:MM" или "HH:MM:SS"
    parts = [int(x) for x in s.strip().split(":")]
    if len(parts) == 2:
        h, m = parts
        return time(h, m)
    elif len(parts) == 3:
        h, m, sec = parts
        return time(h, m, sec)
    raise ValueError(f"Invalid time format: {s!r}")

def parse_duration(s: str) -> timedelta:
    # принимает "5m", "15min", "1h", "300s", "00:05:00"
    s = s.strip().lower()
    if ":" in s:
        # "HH:MM:SS" или "MM:SS"
        parts = [int(x) for x in s.split(":")]
        if len(parts) == 3:
            h, m, sec = parts
            return timedelta(hours=h, minutes=m, seconds=sec)
        elif len(parts) == 2:
            m, sec = parts
            return timedelta(minutes=m, seconds=sec)
        else:
            raise ValueError(f"Invalid duration: {s!r}")
    if s.endswith("ms"):
        return timedelta(milliseconds=int(s[:-2]))
    if s.endswith("s"):
        return timedelta(seconds=int(s[:-1]))
    if s.endswith("m") or s.endswith("min"):
        num = s[:-1] if s.endswith("m") else s[:-3]
        return timedelta(minutes=int(num))
    if s.endswith("h"):
        return timedelta(hours=int(s[:-1]))
    # по умолчанию — секунды
    return timedelta(seconds=int(s))