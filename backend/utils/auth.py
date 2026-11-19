"""Password hashing, JWT tokens and route protection."""
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, request
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from utils.db import db
from utils.responses import ApiError


def hash_password(plain):
    return generate_password_hash(plain)  # salted scrypt/pbkdf2 hash


def verify_password(plain, hashed):
    return check_password_hash(hashed, plain)


def create_token(user):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "tv": user["token_version"],  # bumping token_version on the user logs out every device
        "iat": now,
        "exp": now + timedelta(hours=Config.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def _user_from_request():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(header[7:], Config.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    user = db().one("SELECT * FROM profiles WHERE id = ?", (payload.get("sub"),))
    if not user or not user["is_active"] or user["token_version"] != payload.get("tv"):
        return None
    return user


def optional_auth(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        g.user = _user_from_request()
        return fn(*args, **kwargs)
    return inner


def login_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        g.user = _user_from_request()
        if not g.user:
            raise ApiError("Please log in to continue.", 401, "unauthorized")
        return fn(*args, **kwargs)
    return inner


def admin_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        g.user = _user_from_request()
        if not g.user:
            raise ApiError("Please log in to continue.", 401, "unauthorized")
        if g.user["role"] != "admin":
            raise ApiError("Administrator access is required.", 403, "forbidden")
        return fn(*args, **kwargs)
    return inner
