from datetime import date, datetime, timedelta, timezone


SINGAPORE_TZ = timezone(timedelta(hours=8), name="SGT")


def singapore_now():
    return datetime.now(SINGAPORE_TZ)


def singapore_today():
    return singapore_now().date()


def to_singapore(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=SINGAPORE_TZ)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("Empty timestamp")
        value = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(SINGAPORE_TZ)
