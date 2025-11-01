import datetime
from typing import Optional


def is_updated_today(
    last_update: Optional[datetime.datetime],
    now_time: Optional[datetime.datetime] = None,
    tz: datetime.tzinfo = datetime.timezone.utc,
) -> bool:
    """
    True, если last_update приходится на тот же календарный день, что и now_time,
    с учётом указанного часового пояса tz.
    """
    if last_update is None:
        return False

    # Текущее время
    if now_time is None:
        now_time = datetime.datetime.now(tz)

    # Нормализуем обе даты к одному часовому поясу
    if last_update.tzinfo is None:
        last_update = last_update.replace(tzinfo=tz)
    else:
        last_update = last_update.astimezone(tz)

    if now_time.tzinfo is None:
        now_time = now_time.replace(tzinfo=tz)
    else:
        now_time = now_time.astimezone(tz)

    return last_update.date() == now_time.date()


