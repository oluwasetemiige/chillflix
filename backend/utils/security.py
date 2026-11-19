"""Passwords, tokens and route guards."""
import hashlib
import secrets
from datetime import timedelta
from functools import wraps

import jwt
from flask import g, request
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from utils.db import db
from utils.responses import ApiError
from utils.times import utcnow


def hash_password(password):
    return generate_password_hash(password, method="pbkdf2:sha256:600000")


def verify_password(password, password_hash):
    return check_password_hash(password_hash, password)


def make_token(user):
    payload = {
        "sub": str(user["id"]),
        "tv": user["token_version"],
        "exp": utcnow() + timedelta(hours=Config.TOKEN_TTL_HOURS),
        "iat": utcnow(),
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def new_reset_token():
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _user_from_request():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(header[7:], Config.SECRET_KEY, algorithms=["HS256"])
        user = db.one("SELECT * FROM profiles WHERE id = ?", [int(payload["sub"])])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise ApiError("Your session has expired. Please sign in again.", 401, "invalid_token")
    if not user or not user["is_active"] or user["token_version"] != payload.get("tv"):
        raise ApiError("Your session has expired. Please sign in again.", 401, "invalid_token")
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _user_from_request()
        if not user:
            raise ApiError("Please sign in to continue.", 401, "auth_required")
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


def optional_auth(fn):
    """Runs with g.user set when a valid token is sent, otherwise g.user = None."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            g.user = _user_from_request()
        except ApiError:
            g.user = None
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user["role"] != "admin":
            raise ApiError("Administrator access required.", 403, "forbidden")
        return fn(*args, **kwargs)
    return wrapper
