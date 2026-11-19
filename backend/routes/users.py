import json
import re

from flask import Blueprint, g

from routes.auth import public_user
from services.catalog import jload
from services.membership import get_membership
from utils import validation as v
from utils.db import db
from utils.ratelimit import limit
from utils.responses import ApiError, ok
from utils.security import hash_password, login_required, verify_password
from utils.times import iso

bp = Blueprint("users", __name__, url_prefix="/users")

THEMES = ("violet", "rose", "azure", "emerald")
FREE_THEMES = ("violet",)
QUALITIES = ("auto", "480p", "720p", "1080p")
AVATAR_RE = re.compile(r"^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$")


def preferences_of(user_id):
    row = db.one("SELECT * FROM user_preferences WHERE user_id = ?", [user_id])
    if not row:
        db.execute("INSERT INTO user_preferences (user_id) VALUES (?)", [user_id])
        row = db.one("SELECT * FROM user_preferences WHERE user_id = ?", [user_id])
    return {"favorite_genres": jload(row["favorite_genres"], []), "autoplay_next": bool(row["autoplay_next"]),
            "subtitle_language": row["subtitle_language"], "default_quality": row["default_quality"],
            "accent_theme": row["accent_theme"]}


@bp.get("/profile")
@login_required
def profile():
    uid = g.user["id"]
    counts = {
        "watchlist": db.one("SELECT COUNT(*) AS c FROM watchlist WHERE user_id = ?", [uid])["c"],
        "history": db.one("SELECT COUNT(*) AS c FROM watch_history WHERE user_id = ?", [uid])["c"],
    }
    return ok({"user": public_user(g.user), "preferences": preferences_of(uid), "counts": counts})


@bp.put("/profile")
@login_required
def update_profile():
    data = v.json_body()
    uid = g.user["id"]
    sets, params = [], []
    if "username" in data:
        name = v.username(data)
        taken = db.one("SELECT id FROM profiles WHERE LOWER(username) = ? AND id <> ?", [name.lower(), uid])
        if taken:
            raise ApiError("That username is taken.", 409, "username_taken", {"username": "taken"})
        sets.append("username = ?")
        params.append(name)
    if "avatar" in data:
        avatar = data["avatar"]
        if avatar in (None, ""):
            sets.append("avatar_url = ?")
            params.append(None)
        else:
            if not isinstance(avatar, str) or not AVATAR_RE.match(avatar) or len(avatar) > 400_000:
                raise ApiError("Use a JPEG, PNG or WebP image under 300 KB.", 422, "validation_error", {"avatar": "invalid"})
            sets.append("avatar_url = ?")
            params.append(avatar)
    if not sets:
        raise ApiError("Nothing to update.", 400, "bad_request")
    db.execute(f"UPDATE profiles SET {', '.join(sets)} WHERE id = ?", params + [uid])
    return ok({"user": public_user(db.one("SELECT * FROM profiles WHERE id = ?", [uid]))})


@bp.put("/preferences")
@login_required
def update_preferences():
    data = v.json_body()
    uid = g.user["id"]
    premium = get_membership(uid)["is_premium"]
    current = preferences_of(uid)
    if "favorite_genres" in data:
        genres = data["favorite_genres"]
        if not isinstance(genres, list) or len(genres) > 20 or not all(isinstance(x, str) and 0 < len(x) <= 40 for x in genres):
            raise ApiError("Pick up to 20 genres.", 422, "validation_error", {"favorite_genres": "invalid"})
        current["favorite_genres"] = list(dict.fromkeys(genres))
    if "autoplay_next" in data:
        current["autoplay_next"] = bool(data["autoplay_next"])
    if "subtitle_language" in data:
        lang = str(data["subtitle_language"]).strip().lower()
        if not re.match(r"^[a-z]{2,3}(-[a-z]{2,4})?$|^off$", lang):
            raise ApiError("Invalid subtitle language.", 422, "validation_error", {"subtitle_language": "invalid"})
        current["subtitle_language"] = lang
    if "default_quality" in data:
        quality = v.choice(data["default_quality"], QUALITIES, "default_quality")
        if quality == "1080p" and not premium:
            raise ApiError("1080p playback is a Premium feature.", 403, "premium_required")
        current["default_quality"] = quality
    if "accent_theme" in data:
        theme = v.choice(data["accent_theme"], THEMES, "accent_theme")
        if theme not in FREE_THEMES and not premium:
            raise ApiError("Colour themes are a Premium feature.", 403, "premium_required")
        current["accent_theme"] = theme
    db.execute(
        "UPDATE user_preferences SET favorite_genres = ?, autoplay_next = ?, subtitle_language = ?, default_quality = ?, "
        "accent_theme = ?, updated_at = ? WHERE user_id = ?",
        [json.dumps(current["favorite_genres"]), current["autoplay_next"], current["subtitle_language"],
         current["default_quality"], current["accent_theme"], iso(), uid])
    return ok({"preferences": current})


@bp.post("/password")
@login_required
@limit(6, 600, "change-password")
def change_password():
    data = v.json_body()
    if not verify_password(str(data.get("current_password") or ""), g.user["password_hash"]):
        raise ApiError("Your current password is wrong.", 403, "invalid_credentials", {"current_password": "wrong"})
    new = v.password(data, "new_password")
    db.execute("UPDATE profiles SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
               [hash_password(new), g.user["id"]])
    return ok({"message": "Password changed. Please sign in again."})
