from datetime import date, datetime, timezone, timedelta

ROME_STANDARD = timezone(timedelta(hours=1), name="CET")
ROME_DAYLIGHT = timezone(timedelta(hours=2), name="CEST")


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _last_sunday(year: int, month: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() + 1) % 7)


def _rome_dst_bounds_utc(year: int) -> tuple[datetime, datetime]:
    dst_start = datetime.combine(
        _last_sunday(year, 3),
        datetime.min.time(),
        tzinfo=timezone.utc,
    ) + timedelta(hours=1)
    dst_end = datetime.combine(
        _last_sunday(year, 10),
        datetime.min.time(),
        tzinfo=timezone.utc,
    ) + timedelta(hours=1)
    return dst_start, dst_end


def as_rome(dt: datetime | None) -> datetime | None:
    utc_value = as_utc(dt)
    if utc_value is None:
        return None

    dst_start, dst_end = _rome_dst_bounds_utc(utc_value.year)
    display_tz = ROME_DAYLIGHT if dst_start <= utc_value < dst_end else ROME_STANDARD
    return utc_value.astimezone(display_tz)


def isoformat_rome(dt: datetime, *, timespec: str = "seconds") -> str:
    return as_rome(dt).isoformat(timespec=timespec)
