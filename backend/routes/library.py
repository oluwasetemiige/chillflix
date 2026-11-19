from flask import Blueprint, g, request

from services.catalog import TABLES, img
from utils import validation as v
from utils.db import db
from utils.responses import ApiError, ok
from utils.security import login_required
from utils.times import iso

bp = Blueprint("library", __name__)


def _title_row(media_type, media_id):
    return db.one(f"SELECT id, title, year, rating, poster_path, backdrop_path FROM {TABLES[media_type]} WHERE id = ?", [media_id])


def _card(media_type, t):
    return {"id": t["id"], "media_type": media_type, "title": t["title"], "year": t["year"],
            "rating": round(float(t["rating"] or 0), 1), "poster": img(t["poster_path"], "w342"),
            "backdrop": img(t["backdrop_path"], "w780")}


# ------------------------------------------------------------------ watchlist
@bp.get("/watchlist")
@login_required
def list_watchlist():
    rows = db.query("SELECT * FROM watchlist WHERE user_id = ? ORDER BY created_at DESC, id DESC", [g.user["id"]])
    items = []
    for r in rows:
        t = _title_row(r["media_type"], r["media_id"])
        if t:
            items.append({"watchlist_id": r["id"], "added_at": r["created_at"], **_card(r["media_type"], t)})
    return ok({"items": items, "total": len(items)})


@bp.post("/watchlist")
@login_required
def add_watchlist():
    data = v.json_body()
    media_type = v.media_type(data.get("media_type"))
    media_id = v.integer(data.get("media_id"), None, 1, None, "media_id")
    if media_id is None or not _title_row(media_type, media_id):
        raise ApiError("Title not found.", 404, "not_found")
    db.execute("INSERT INTO watchlist (user_id, media_type, media_id) VALUES (?,?,?) ON CONFLICT DO NOTHING",
               [g.user["id"], media_type, media_id])
    row = db.one("SELECT id FROM watchlist WHERE user_id = ? AND media_type = ? AND media_id = ?",
                 [g.user["id"], media_type, media_id])
    return ok({"watchlist_id": row["id"]}, 201)


@bp.delete("/watchlist/<int:item_id>")
@login_required
def remove_watchlist(item_id):
    removed = db.execute("DELETE FROM watchlist WHERE id = ? AND user_id = ?", [item_id, g.user["id"]])
    if not removed:
        raise ApiError("That item is not in your watchlist.", 404, "not_found")
    return ok({"removed": item_id})


# ------------------------------------------------------------------ history
@bp.get("/history")
@login_required
def list_history():
    only_continue = request.args.get("continue") == "1"
    limit = v.integer(request.args.get("limit"), 40, 1, 100, "limit")
    rows = db.query("SELECT * FROM watch_history WHERE user_id = ? ORDER BY updated_at DESC, id DESC", [g.user["id"]])
    items, seen = [], set()
    for r in rows:
        key = (r["media_type"], r["media_id"])
        if only_continue:
            if key in seen:
                continue
            seen.add(key)
            progress = (r["position_seconds"] / r["duration_seconds"]) if r["duration_seconds"] else 0
            if r["completed"] or progress < 0.02 or progress > 0.95:
                continue
        t = _title_row(r["media_type"], r["media_id"])
        if not t:
            continue
        item = {"history_id": r["id"], "episode_id": r["episode_id"], "position": r["position_seconds"],
                "duration": r["duration_seconds"], "completed": bool(r["completed"]), "updated_at": r["updated_at"],
                **_card(r["media_type"], t)}
        if r["episode_id"]:
            ep = db.one("SELECT e.episode_number, s.season_number FROM episodes e JOIN seasons s ON s.id = e.season_id "
                        "WHERE e.id = ?", [r["episode_id"]])
            if ep:
                item["episode_label"] = f"S{ep['season_number']} E{ep['episode_number']}"
        items.append(item)
        if len(items) >= limit:
            break
    return ok({"items": items, "total": len(items)})


@bp.post("/history")
@login_required
def save_history():
    data = v.json_body()
    media_type = v.media_type(data.get("media_type"))
    media_id = v.integer(data.get("media_id"), None, 1, None, "media_id")
    episode_id = v.integer(data.get("episode_id"), 0, 0, None, "episode_id")
    position = v.integer(data.get("position"), 0, 0, 60 * 60 * 24, "position")
    duration = v.integer(data.get("duration"), 0, 0, 60 * 60 * 24, "duration")
    if media_id is None or not _title_row(media_type, media_id):
        raise ApiError("Title not found.", 404, "not_found")
    completed = bool(duration) and position >= duration * 0.95
    db.execute(
        "INSERT INTO watch_history (user_id, media_type, media_id, episode_id, position_seconds, duration_seconds, completed, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (user_id, media_type, media_id, episode_id) DO UPDATE SET "
        "position_seconds = excluded.position_seconds, duration_seconds = excluded.duration_seconds, "
        "completed = excluded.completed, updated_at = excluded.updated_at",
        [g.user["id"], media_type, media_id, episode_id, position, duration, completed, iso()])
    return ok({"saved": True, "completed": completed})


@bp.get("/history/position")
@login_required
def history_position():
    media_type = v.media_type(request.args.get("media_type"))
    media_id = v.integer(request.args.get("media_id"), None, 1, None, "media_id")
    episode_id = v.integer(request.args.get("episode_id"), 0, 0, None, "episode_id")
    row = db.one("SELECT position_seconds, duration_seconds, completed FROM watch_history WHERE user_id = ? "
                 "AND media_type = ? AND media_id = ? AND episode_id = ?", [g.user["id"], media_type, media_id, episode_id])
    return ok({"position": row["position_seconds"] if row and not row["completed"] else 0,
               "duration": row["duration_seconds"] if row else 0})


@bp.delete("/history/<int:history_id>")
@login_required
def delete_history(history_id):
    removed = db.execute("DELETE FROM watch_history WHERE id = ? AND user_id = ?", [history_id, g.user["id"]])
    if not removed:
        raise ApiError("History entry not found.", 404, "not_found")
    return ok({"removed": history_id})
