"""Simple in-memory rate limiter (per IP). Good for a single server process.

For several server processes use a shared store (Redis) or your host's limiter.
"""
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import request

from config import Config
from utils.responses import ApiError

_hits = defaultdict(deque)
_lock = threading.Lock()


def client_ip():
    if Config.TRUST_PROXY:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def check(scope, limit, window):
    key = (scope, client_ip())
    now = time.time()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, int(window - (now - q[0])))
            raise ApiError(f"Too many requests. Try again in {retry}s.", 429, "rate_limited", {"retry_after": retry})
        q.append(now)
        if len(_hits) > 20000:  # keep memory bounded
            for k in [k for k, v in _hits.items() if not v or v[-1] <= now - window]:
                _hits.pop(k, None)


def limit(limit_count, window_seconds, scope=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            check(scope or fn.__name__, limit_count, window_seconds)
            return fn(*args, **kwargs)
        return wrapper
    return decorator
