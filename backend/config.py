"""CHILLFLIX backend settings.

Every setting is read from environment variables (or from backend/.env while
developing). Copy .env.example to .env and fill it in. Nothing secret lives in
this file.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


def _list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")
    DEBUG = APP_ENV == "development"
    VERSION = "1.0.0"

    # --- security ---------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    TOKEN_TTL_HOURS = _int("TOKEN_TTL_HOURS", 24 * 14)
    TRUST_PROXY = _bool("TRUST_PROXY", False)  # true when behind Render/Railway/etc.
    ADMIN_EMAILS = [e.lower() for e in _list("ADMIN_EMAILS")]
    CORS_ORIGINS = _list(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,"
        "http://127.0.0.1:5500,http://localhost:8000,http://127.0.0.1:8000",
    )
    FRONTEND_URL = (os.getenv("FRONTEND_URL") or "http://localhost:8000").rstrip("/")

    # --- database ---------------------------------------------------------
    # postgresql://...  (Supabase / PostgreSQL)   or   sqlite:///path (local dev)
    DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'chillflix.db'}"

    # --- TMDB -------------------------------------------------------------
    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()  # v3 key OR v4 read token
    TMDB_BASE = "https://api.themoviedb.org/3"
    TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"
    SYNC_PAGES = _int("SYNC_PAGES", 2)                 # pages per discovery job (20 titles each)
    SYNC_MAX_TITLES = _int("SYNC_MAX_TITLES", 400)     # safety cap per run
    SYNC_REFRESH_HOURS = _int("SYNC_REFRESH_HOURS", 24)
    AUTO_SYNC_HOURS = _int("AUTO_SYNC_HOURS", 0)       # 0 = off; e.g. 12 = every 12 hours

    # --- playback provider (MovieBox adapter) ---------------------------------
    MOVIEBOX_API_BASE = os.getenv("MOVIEBOX_API_BASE", "").strip().rstrip("/")
    MOVIEBOX_API_KEY = os.getenv("MOVIEBOX_API_KEY", "").strip()

    # --- payments (Paystack) --------------------------------------------------
    PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "NGN").upper()
    PLAN_MONTHLY_PRICE = _int("PLAN_MONTHLY_PRICE", 2500)   # major units (e.g. naira)
    PLAN_YEARLY_PRICE = _int("PLAN_YEARLY_PRICE", 25000)

    # --- email (password recovery) ----------------------------------------
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USER = os.getenv("SMTP_USER", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    MAIL_FROM = os.getenv("MAIL_FROM", "CHILLFLIX <no-reply@chillflix.local>")

    @classmethod
    def plans(cls):
        """Premium plans. Prices come from the environment, not from code."""
        return {
            "monthly": {
                "id": "monthly", "name": "Premium Monthly", "days": 30,
                "price": cls.PLAN_MONTHLY_PRICE, "currency": cls.PAYMENT_CURRENCY,
            },
            "yearly": {
                "id": "yearly", "name": "Premium Yearly", "days": 365,
                "price": cls.PLAN_YEARLY_PRICE, "currency": cls.PAYMENT_CURRENCY,
            },
        }

    @classmethod
    def validate(cls):
        if not cls.SECRET_KEY:
            if cls.APP_ENV == "production":
                raise RuntimeError("SECRET_KEY must be set when APP_ENV=production")
            cls.SECRET_KEY = "dev-only-secret-change-me"
