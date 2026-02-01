from datetime import datetime, timezone, timedelta

UTC_PLUS_1 = timezone(timedelta(hours=1))

def as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

def as_utc_plus1(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(UTC_PLUS_1)

def isoformat_utc_plus1(dt: datetime, *, timespec: str = "seconds") -> str:
    return as_utc_plus1(dt).isoformat(timespec=timespec)
