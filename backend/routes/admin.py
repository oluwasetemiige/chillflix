import json
import re

from flask import Blueprint, g, request

from config import Config
from routes.health import database_health, tmdb_health
from services import catalog as cat
from services import sync as syncer
from services.membership import grant
from services.providers import provider_health
from services.providers.base import clean_source
from services.tmdb import TMDBError, tmdb
from utils import validation as v
from utils.cache import cache
from utils.db import db
from utils.responses import ApiError, ok
from utils.security import admin_required
from utils.times import iso

bp = Blueprint("admin", __name__, url_prefix="/admin")
SLUG_RE = re.compile(r"^[a-z0-9-]{2,40}$")


# ------------------------------------------------------------------ overview
@bp.get("/stats")
@admin_required
def stats():
    now = iso()
    premium = db.one("SELECT COUNT(DISTINCT user_id) AS c FROM subscriptions WHERE status = 'active' "
                     "AND starts_at <= ? AND ends_at > ?", [now, now])["c"]
    revenue = db.query("SELECT currency, SUM(amount) AS total, COUNT(*) AS payments FROM payments "
                       "WHERE status = 'success' GROUP BY currency")
    recent = db.query("SELECT id, username, email, role, created_at FROM profiles ORDER BY created_at DESC, id DESC LIMIT 8")
    return ok({
        "totals": {
            "users": db.one("SELECT COUNT(*) AS c FROM profiles")["c"],
            "movies": db.one("SELECT COUNT(*) AS c FROM movies")["c"],
            "series": db.one("SELECT COUNT(*) AS c FROM series")["c"],
            "premium_subscribers": premium,
            "playable_titles": db.one("SELECT COUNT(DISTINCT media_type || ':' || media_id) AS c FROM provider_sources "
                                      "WHERE is_active = ?", [True])["c"],
        },
        "revenue": [{"currency": r["currency"], "total_major": (r["total"] or 0) / 100, "payments": r["payments"]} for r in revenue],
        "recent_users": recent,
        "health": {"database": database_health(), "tmdb": tmdb_health(), "providers": provider_health()},
        "sync": syncer.history(5),
    })


# ------------------------------------------------------------------ synchronisation
@bp.get("/sync")
@admin_required
def sync_status():
    logs = syncer.history(20)
    return ok({"running": any(l["status"] == "running" for l in logs), "tmdb_configured": tmdb.configured,
               "auto_sync_hours": Config.AUTO_SYNC_HOURS, "logs": logs})


@bp.post("/sync")
@admin_required
def sync_trigger():
    if not tmdb.configured:
        raise ApiError("Add TMDB_API_KEY to the backend environment first.", 400, "tmdb_not_configured")
    body = request.get_json(silent=True) or {}
    log_id = syncer.start_sync("manual", g.user["id"], force=bool(body.get("force")))
    return ok({"log_id": log_id, "message": "Synchronization started."}, 202)


# ------------------------------------------------------------------ catalogue
def _titles_table(media_type):
    return cat.table_for(v.media_type(media_type))


@bp.get("/titles")
@admin_required
def list_titles():
    media_type = request.args.get("type", "movie")
    table = _titles_table(media_type)
    q = (request.args.get("q") or "").strip().lower().replace("%", "")
    page = v.integer(request.args.get("page"), 1, 1, 1000, "page")
    where, params = ("WHERE LOWER(title) LIKE ?", [f"%{q}%"]) if q else ("", [])
    total = db.one(f"SELECT COUNT(*) AS c FROM {table} {where}", params)["c"]
    rows = db.query(f"SELECT id, tmdb_id, title, year, rating, source, poster_path, updated_at FROM {table} {where} "
                    f"ORDER BY id DESC LIMIT 25 OFFSET ?", params + [(page - 1) * 25])
    for r in rows:
        r["poster"] = cat.img(r.pop("poster_path"), "w185")
        r["has_sources"] = cat.has_sources(media_type, r["id"])
    return ok({"items": rows, "page": page, "pages": max(1, -(-total // 25)), "total": total})


def _editable_fields(data, partial):
    """Validate admin-supplied metadata and map it to column values."""
    out = {}
    if not partial or "title" in data:
        out["title"] = v.text(data, "title", "Title", max_len=200)
    if "overview" in data:
        out["overview"] = v.text(data, "overview", "Overview", max_len=4000, required=False) or ""
    if "release_date" in data:
        rd = v.text(data, "release_date", "Release date", max_len=10, required=False)
        if rd and not re.match(r"^\d{4}-\d{2}-\d{2}$", rd):
            raise ApiError("Release date must look like 2024-05-31.", 422, "validation_error", {"release_date": "invalid"})
        out["release_date"] = rd
        out["year"] = int(rd[:4]) if rd else out.get("year")
    if "year" in data and "release_date" not in data:
        out["year"] = v.integer(data["year"], None, 1900, 2100, "year")
    if "rating" in data:
        try:
            out["rating"] = max(0.0, min(10.0, float(data["rating"] or 0)))
        except (TypeError, ValueError):
            raise ApiError("Rating must be a number from 0 to 10.", 422, "validation_error", {"rating": "invalid"})
    for key in ("genres", "countries"):
        if key in data:
            items = data[key]
            if isinstance(items, str):
                items = [i.strip() for i in items.split(",") if i.strip()]
            if not isinstance(items, list) or len(items) > 20:
                raise ApiError(f"{key.title()} must be a short list.", 422, "validation_error", {key: "invalid"})
            out[key] = cat.jdump([str(i)[:40] for i in items])
    if "original_language" in data:
        out["original_language"] = v.text(data, "original_language", "Language", max_len=5, required=False)
    for field, column in (("poster_url", "poster_path"), ("backdrop_url", "backdrop_path")):
        if field in data:
            url = v.text(data, field, field, max_len=1000, required=False)
            if url and not url.startswith("https://"):
                raise ApiError("Image links must start with https://", 422, "validation_error", {field: "invalid"})
            out[column] = url
    for key in ("runtime", "episode_runtime"):
        if key in data:
            out[key] = v.integer(data[key], None, 0, 1000, key)
    if "trailer_key" in data:
        out["trailer_key"] = v.text(data, "trailer_key", "Trailer key", max_len=20, required=False)
    return out


@bp.post("/titles")
@admin_required
def add_title():
    data = v.json_body()
    media_type = v.media_type(data.get("media_type"))
    table = cat.table_for(media_type)
    row = _editable_fields(data, partial=False)
    allowed = {"runtime"} if media_type == "movie" else {"episode_runtime"}
    row = {k: val for k, val in row.items() if k not in {"runtime", "episode_runtime"} or k in allowed}
    row["source"] = "manual"
    cols = list(row)
    new_id = db.insert(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({','.join('?' for _ in cols)})", list(row.values()))
    cache.clear("home")
    return ok({"id": new_id}, 201)


@bp.post("/titles/import")
@admin_required
def import_from_tmdb():
    data = v.json_body()
    media_type = v.media_type(data.get("media_type"))
    tmdb_id = v.integer(data.get("tmdb_id"), None, 1, None, "tmdb_id")
    if tmdb_id is None:
        raise ApiError("tmdb_id is required.", 422, "validation_error", {"tmdb_id": "required"})
    if not tmdb.configured:
        raise ApiError("Add TMDB_API_KEY to the backend environment first.", 400, "tmdb_not_configured")
    try:
        local_id, outcome = syncer.import_title("movie" if media_type == "movie" else "tv", tmdb_id)
    except TMDBError as exc:
        raise ApiError(f"TMDB: {exc}", 502, "tmdb_error")
    cache.clear("home")
    return ok({"id": local_id, "outcome": outcome}, 201)


@bp.put("/titles/<media_type>/<int:title_id>")
@admin_required
def edit_title(media_type, title_id):
    table = _titles_table(media_type)
    data = v.json_body()
    row = _editable_fields(data, partial=True)
    if media_type == "movie":
        row.pop("episode_runtime", None)
    else:
        row.pop("runtime", None)
    if not row:
        raise ApiError("Nothing to update.", 400, "bad_request")
    row["updated_at"] = iso()
    changed = db.execute(f"UPDATE {table} SET {', '.join(k + ' = ?' for k in row)} WHERE id = ?", list(row.values()) + [title_id])
    if not changed:
        raise ApiError("Title not found.", 404, "not_found")
    cache.clear("home")
    return ok({"updated": title_id})


@bp.delete("/titles/<media_type>/<int:title_id>")
@admin_required
def delete_title(media_type, title_id):
    table = _titles_table(media_type)
    with db.tx() as t:
        if not t.execute(f"DELETE FROM {table} WHERE id = ?", [title_id]):
            raise ApiError("Title not found.", 404, "not_found")
        for dependent in ("provider_sources", "watchlist", "watch_history"):  # no FK across the two tables
            t.execute(f"DELETE FROM {dependent} WHERE media_type = ? AND media_id = ?", [media_type, title_id])
    cache.clear("home")
    return ok({"deleted": title_id})


# ------------------------------------------------------------------ playback sources

@bp.post("/titles/quick-publish")
@admin_required
def quick_publish():
    data = v.json_body()

    if v.media_type(data.get("media_type", "movie")) != "movie":
        raise ApiError("Quick Publish currently supports movies.", 422, "validation_error")

    tmdb_id = v.integer(data.get("tmdb_id"), None, 1, None, "tmdb_id")
    if tmdb_id is None:
        raise ApiError("TMDB ID is required.", 422, "validation_error")

    if not tmdb.configured:
        raise ApiError("TMDB_API_KEY is not configured.", 400, "tmdb_not_configured")

    try:
        movie_id, outcome = syncer.import_title("movie", tmdb_id)
    except TMDBError as exc:
        raise ApiError(f"TMDB: {exc}", 502, "tmdb_error")

    # Try the configured, authorised MovieBox provider.
    from services.playback import discover_from_providers
    provider_sources = discover_from_providers("movie", movie_id)

    # An admin can also supply an authorised direct stream.
    manual_added = 0
    raw_source = data.get("source")

    if raw_source:
        src = clean_source(raw_source)
        if not src:
            raise ApiError("Provide a valid HTTPS MP4 or HLS source.", 422, "validation_error")

        manual_added = db.execute(
            "INSERT INTO provider_sources "
            "(provider, media_type, media_id, episode_id, source_url, source_type, "
            "quality, language, subtitles, premium_only, is_active, last_checked_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            [
                "manual", "movie", movie_id, 0, src["url"], src["type"],
                src["quality"], src["language"], json.dumps(src["subtitles"]),
                bool(raw_source.get("premium_only")), True, iso()
            ]
        )

    cache.clear("home")
    cache.clear("nosrc")

    return ok({
        "id": movie_id,
        "outcome": outcome,
        "provider_sources": provider_sources,
        "manual_source_added": bool(manual_added),
        "playable": bool(provider_sources or manual_added)
    })

@bp.get("/titles/<media_type>/<int:title_id>/sources")
@admin_required
def list_sources(media_type, title_id):
    _titles_table(media_type)
    rows = db.query("SELECT * FROM provider_sources WHERE media_type = ? AND media_id = ? ORDER BY id", [media_type, title_id])
    return ok({"items": [{"id": r["id"], "provider": r["provider"], "episode_id": r["episode_id"], "url": r["source_url"],
                          "type": r["source_type"], "quality": r["quality"], "language": r["language"],
                          "premium_only": bool(r["premium_only"])} for r in rows]})


@bp.post("/titles/<media_type>/<int:title_id>/sources")
@admin_required
def add_source(media_type, title_id):
    """Only add links you are licensed to stream. CHILLFLIX never generates links."""
    table = _titles_table(media_type)
    data = v.json_body()
    if not db.one(f"SELECT id FROM {table} WHERE id = ?", [title_id]):
        raise ApiError("Title not found.", 404, "not_found")
    src = clean_source({"url": data.get("url"), "type": data.get("type"), "quality": data.get("quality"),
                        "language": data.get("language"), "subtitles": data.get("subtitles")})
    if not src:
        raise ApiError("Use an https:// link and type hls or mp4.", 422, "validation_error", {"url": "invalid"})
    episode_id = v.integer(data.get("episode_id"), 0, 0, None, "episode_id") if media_type == "series" else 0
    if media_type == "series" and not episode_id:
        raise ApiError("Choose the episode this link belongs to.", 422, "validation_error", {"episode_id": "required"})
    if episode_id and not db.one("SELECT id FROM episodes WHERE id = ? AND series_id = ?", [episode_id, title_id]):
        raise ApiError("Episode not found for this series.", 404, "not_found")
    new_id = db.insert(
        "INSERT INTO provider_sources (provider, media_type, media_id, episode_id, source_url, source_type, quality, language, "
        "subtitles, premium_only, is_active, last_checked_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ["manual", media_type, title_id, episode_id, src["url"], src["type"], src["quality"], src["language"],
         json.dumps(src["subtitles"]), bool(data.get("premium_only")), True, iso()])
    cache.clear("nosrc")
    return ok({"id": new_id}, 201)


@bp.delete("/sources/<int:source_id>")
@admin_required
def delete_source(source_id):
    if not db.execute("DELETE FROM provider_sources WHERE id = ?", [source_id]):
        raise ApiError("Source not found.", 404, "not_found")
    return ok({"deleted": source_id})


# ------------------------------------------------------------------ categories
def _category_values(data):
    slug = v.text(data, "slug", "Slug", max_len=40).lower()
    if not SLUG_RE.match(slug):
        raise ApiError("Slug can only use lowercase letters, numbers and dashes.", 422, "validation_error", {"slug": "invalid"})
    return [slug, v.text(data, "name", "Name", max_len=60),
            v.choice(data.get("media_type", "all"), ("movie", "series", "all"), "media_type"),
            v.text(data, "country", "Country", max_len=40, required=False),
            v.text(data, "language", "Language", max_len=20, required=False),
            v.text(data, "genre", "Genre", max_len=120, required=False),
            v.text(data, "exclude_genre", "Exclude genre", max_len=120, required=False),
            v.choice(data.get("sort", "popularity"), ("popularity", "rating", "recent", "trending"), "sort"),
            v.integer(data.get("position"), 99, 0, 999, "position"), bool(data.get("show_on_home", True))]


@bp.get("/categories")
@admin_required
def admin_categories():
    return ok({"items": cat.list_categories()})


@bp.post("/categories")
@admin_required
def add_category():
    values = _category_values(v.json_body())
    if db.one("SELECT 1 AS x FROM categories WHERE slug = ?", [values[0]]):
        raise ApiError("That slug already exists.", 409, "slug_taken", {"slug": "taken"})
    new_id = db.insert("INSERT INTO categories (slug, name, media_type, country, language, genre, exclude_genre, sort, position, "
                       "show_on_home) VALUES (?,?,?,?,?,?,?,?,?,?)", values)
    cache.clear("home")
    return ok({"id": new_id}, 201)


@bp.put("/categories/<int:category_id>")
@admin_required
def edit_category(category_id):
    values = _category_values(v.json_body())
    clash = db.one("SELECT id FROM categories WHERE slug = ? AND id <> ?", [values[0], category_id])
    if clash:
        raise ApiError("That slug already exists.", 409, "slug_taken", {"slug": "taken"})
    changed = db.execute("UPDATE categories SET slug = ?, name = ?, media_type = ?, country = ?, language = ?, genre = ?, "
                         "exclude_genre = ?, sort = ?, position = ?, show_on_home = ? WHERE id = ?", values + [category_id])
    if not changed:
        raise ApiError("Category not found.", 404, "not_found")
    cache.clear("home")
    return ok({"updated": category_id})


@bp.delete("/categories/<int:category_id>")
@admin_required
def delete_category(category_id):
    if not db.execute("DELETE FROM categories WHERE id = ?", [category_id]):
        raise ApiError("Category not found.", 404, "not_found")
    cache.clear("home")
    return ok({"deleted": category_id})


# ------------------------------------------------------------------ users
@bp.get("/users")
@admin_required
def list_users():
    q = (request.args.get("q") or "").strip().lower().replace("%", "")
    page = v.integer(request.args.get("page"), 1, 1, 1000, "page")
    where, params = ("WHERE LOWER(username) LIKE ? OR LOWER(email) LIKE ?", [f"%{q}%", f"%{q}%"]) if q else ("", [])
    total = db.one(f"SELECT COUNT(*) AS c FROM profiles {where}", params)["c"]
    rows = db.query(f"SELECT id, username, email, role, is_active, created_at, last_login_at FROM profiles {where} "
                    f"ORDER BY id DESC LIMIT 25 OFFSET ?", params + [(page - 1) * 25])
    now = iso()
    for r in rows:
        r["is_active"] = bool(r["is_active"])
        r["premium"] = bool(db.one("SELECT 1 AS x FROM subscriptions WHERE user_id = ? AND status = 'active' AND starts_at <= ? "
                                   "AND ends_at > ?", [r["id"], now, now]))
    return ok({"items": rows, "page": page, "pages": max(1, -(-total // 25)), "total": total})


@bp.put("/users/<int:user_id>")
@admin_required
def update_user(user_id):
    data = v.json_body()
    if user_id == g.user["id"] and ("role" in data or "is_active" in data):
        raise ApiError("You can't change your own role or status.", 400, "bad_request")
    sets, params = [], []
    if "role" in data:
        sets.append("role = ?")
        params.append(v.choice(data["role"], ("user", "admin"), "role"))
    if "is_active" in data:
        sets.append("is_active = ?")
        params.append(bool(data["is_active"]))
        if not data["is_active"]:
            sets.append("token_version = token_version + 1")  # sign them out immediately
    if not sets:
        raise ApiError("Nothing to update.", 400, "bad_request")
    if not db.execute(f"UPDATE profiles SET {', '.join(sets)} WHERE id = ?", params + [user_id]):
        raise ApiError("User not found.", 404, "not_found")
    return ok({"updated": user_id})


# ------------------------------------------------------------------ subscriptions
@bp.get("/subscriptions")
@admin_required
def list_subscriptions():
    rows = db.query("SELECT s.id, s.user_id, p.username, p.email, s.plan, s.status, s.starts_at, s.ends_at, s.payment_id "
                    "FROM subscriptions s JOIN profiles p ON p.id = s.user_id ORDER BY s.id DESC LIMIT 100")
    return ok({"items": rows})


@bp.post("/subscriptions")
@admin_required
def grant_subscription():
    data = v.json_body()
    user_id = v.integer(data.get("user_id"), None, 1, None, "user_id")
    plan_id = v.choice(data.get("plan"), tuple(Config.plans()), "plan")
    days = v.integer(data.get("days"), Config.plans()[plan_id]["days"], 1, 3650, "days")
    if user_id is None or not db.one("SELECT id FROM profiles WHERE id = ?", [user_id]):
        raise ApiError("User not found.", 404, "not_found")
    return ok({"id": grant(user_id, plan_id, days)}, 201)


@bp.post("/subscriptions/<int:sub_id>/cancel")
@admin_required
def cancel_subscription(sub_id):
    if not db.execute("UPDATE subscriptions SET status = 'cancelled' WHERE id = ?", [sub_id]):
        raise ApiError("Subscription not found.", 404, "not_found")
    return ok({"cancelled": sub_id})
