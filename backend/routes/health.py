import time

from flask import Blueprint

from config import Config
from services.providers import provider_health
from services.tmdb import TMDBError, tmdb
from utils.cache import cache
from utils.db import db
from utils.responses import ok

bp = Blueprint("health", __name__)


def database_health():
    started = time.time()
    try:
        db.ping()
        return {"status": "ok", "engine": "postgresql" if db.is_postgres else "sqlite",
                "latency_ms": int((time.time() - started) * 1000)}
    except Exception as exc:
        return {"status": "down", "engine": "postgresql" if db.is_postgres else "sqlite", "detail": exc.__class__.__name__}


def tmdb_health():
    if not tmdb.configured:
        return {"status": "not_configured", "detail": "TMDB_API_KEY is not set."}

    def check():
        try:
            return {"status": "ok", "latency_ms": tmdb.check()}
        except TMDBError as exc:
            return {"status": "down", "detail": str(exc)}

    return cache.remember("tmdb-health", 300, check)


@bp.get("/health")
def health():
    database, tmdb_info, providers = database_health(), tmdb_health(), provider_health()
    healthy = database["status"] == "ok"
    degraded = tmdb_info["status"] == "down" or any(p["status"] == "down" for p in providers)
    return ok({
        "status": "ok" if healthy and not degraded else ("degraded" if healthy else "down"),
        "version": Config.VERSION, "environment": Config.APP_ENV,
        "database": database, "tmdb": tmdb_info, "providers": providers,
    }, 200 if healthy else 503)
