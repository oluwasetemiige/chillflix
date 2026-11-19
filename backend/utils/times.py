"""Timestamps are stored as UTC ISO strings so SQLite and PostgreSQL behave the same."""
from datetime import datetime, timedelta, timezone

FMT = "%Y-%m-%dT%H:%M:%S+00:00"


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or utcnow()).strftime(FMT)


def in_days(days):
    return iso(utcnow() + timedelta(days=days))


def parse(value):
    """Accepts a datetime (PostgreSQL) or an ISO string (SQLite) -> aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00").replace(" ", "T")
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
