from flask import Blueprint, g

from config import Config
from services import mailer
from services.membership import get_membership
from utils import validation as v
from utils.db import db
from utils.ratelimit import limit
from utils.responses import ApiError, ok
from utils.security import (hash_password, hash_token, login_required, make_token, new_reset_token, verify_password)
from utils.times import iso, in_days, parse, utcnow

bp = Blueprint("auth", __name__, url_prefix="/auth")


def public_user(u):
    m = get_membership(u["id"])
    return {"id": u["id"], "username": u["username"], "email": u["email"], "avatar_url": u["avatar_url"],
            "role": u["role"], "created_at": u["created_at"], "subscription": m}


@bp.post("/register")
@limit(8, 600, "auth-register")
def register():
    data = v.json_body()
    name, mail, pw = v.username(data), v.email(data), v.password(data)
    if db.one("SELECT 1 AS x FROM profiles WHERE LOWER(email) = ?", [mail]):
        raise ApiError("An account with this email already exists.", 409, "email_taken", {"email": "taken"})
    if db.one("SELECT 1 AS x FROM profiles WHERE LOWER(username) = ?", [name.lower()]):
        raise ApiError("That username is taken.", 409, "username_taken", {"username": "taken"})
    role = "admin" if mail in Config.ADMIN_EMAILS else "user"
    with db.tx() as t:
        uid = t.insert("INSERT INTO profiles (username, email, password_hash, role) VALUES (?,?,?,?)",
                       [name, mail, hash_password(pw), role])
        t.execute("INSERT INTO user_preferences (user_id) VALUES (?)", [uid])
    user = db.one("SELECT * FROM profiles WHERE id = ?", [uid])
    return ok({"token": make_token(user), "user": public_user(user)}, 201)


@bp.post("/login")
@limit(10, 300, "auth-login")
def login():
    data = v.json_body()
    ident = v.text(data, "identifier", "Email or username", max_len=254).lower()
    pw = data.get("password")
    user = db.one("SELECT * FROM profiles WHERE LOWER(email) = ? OR LOWER(username) = ?", [ident, ident])
    if not user or not isinstance(pw, str) or not verify_password(pw, user["password_hash"]):
        raise ApiError("Wrong email/username or password.", 401, "invalid_credentials")
    if not user["is_active"]:
        raise ApiError("This account has been disabled.", 403, "account_disabled")
    db.execute("UPDATE profiles SET last_login_at = ? WHERE id = ?", [iso(), user["id"]])
    return ok({"token": make_token(user), "user": public_user(user)})


@bp.post("/logout")
@login_required
def logout():
    """Bumping token_version invalidates every token issued before now."""
    db.execute("UPDATE profiles SET token_version = token_version + 1 WHERE id = ?", [g.user["id"]])
    return ok({"message": "Signed out."})


@bp.post("/forgot")
@limit(5, 900, "auth-forgot")
def forgot():
    data = v.json_body()
    mail = v.email(data)
    user = db.one("SELECT * FROM profiles WHERE LOWER(email) = ? AND is_active = ?", [mail, True])
    payload = {"message": "If that email has an account, a reset link is on its way."}
    if user:
        token, token_hash = new_reset_token()
        db.execute("INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?,?,?)",
                   [user["id"], token_hash, in_days(1 / 24)])
        link = f"{Config.FRONTEND_URL}/reset-password.html?token={token}"
        sent = mailer.send(mail, "Reset your CHILLFLIX password",
                           f"Hi {user['username']},\n\nUse this link within 1 hour to choose a new password:\n{link}\n\n"
                           "If you didn't ask for this, you can ignore this email.")
        if not sent and Config.DEBUG:  # development only: no SMTP configured, show the link
            payload["dev_reset_url"] = link
            payload["message"] = "Email isn't configured, so here is your reset link (development mode only)."
    return ok(payload)


@bp.post("/reset")
@limit(10, 900, "auth-reset")
def reset():
    data = v.json_body()
    token = v.text(data, "token", "Reset token", max_len=200)
    pw = v.password(data, "password")
    row = db.one("SELECT * FROM password_resets WHERE token_hash = ?", [hash_token(token)])
    if not row or row["used_at"] or parse(row["expires_at"]) < utcnow():
        raise ApiError("This reset link is invalid or has expired. Request a new one.", 400, "invalid_reset_token")
    with db.tx() as t:
        t.execute("UPDATE profiles SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
                  [hash_password(pw), row["user_id"]])
        t.execute("UPDATE password_resets SET used_at = ? WHERE id = ?", [iso(), row["id"]])
    return ok({"message": "Password updated. You can sign in now."})
