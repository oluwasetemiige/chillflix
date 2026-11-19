"""Automatic catalogue synchronisation (TMDB -> database).

What a run does
  1. Discovers Asian titles with TMDB "discover" jobs (K-Drama, C-Drama, J-Drama,
     anime, Korean/Japanese/Chinese/Thai/Hindi movies, top rated, recent, and
     keyword jobs for Historical / Romance / Thriller dramas).
  2. Fetches full details (cast, trailer, similar) and inserts or updates rows.
  3. Detects duplicates (same TMDB id, or same title + year + language).
  4. Refreshes trending ranks.
  5. Asks configured playback providers for AUTHORISED sources of new movies.
  6. Writes a row to synchronization_logs.

Run it from the admin dashboard, `python manage.py sync`, or set AUTO_SYNC_HOURS.
"""
import json
import logging
import re
import threading
import time
from datetime import date, timedelta

from config import Config
from services.catalog import jdump, jload, TABLES
from services.providers import PROVIDERS, provider_health
from services.tmdb import TMDBError, tmdb
from utils.cache import cache
from utils.db import db
from utils.responses import ApiError
from utils.times import iso, parse, utcnow

log = logging.getLogger("chillflix.sync")
_run_lock = threading.Lock()

ASIAN_LANGS = ["ko", "ja", "zh", "cn", "th", "hi"]
TOP_RATED_LANGS = ["ko", "ja", "zh", "th", "hi"]
TV_COUNTRIES = ["KR", "CN", "TW", "HK", "JP", "TH"]
# TMDB TV has no Romance/Thriller/History genres, so those rows come from keywords.
KEYWORD_TAGS = {
    "Historical": ["historical drama", "period drama", "historical fiction", "historical"],
    "Romance": ["romance"],
    "Thriller": ["thriller"],
}
TAG_NAMES = set(KEYWORD_TAGS) | {"Historical"}
MAX_PROVIDER_LOOKUPS = 60


def build_jobs():
    today = date.today()
    recent_from = (today - timedelta(days=150)).isoformat()
    pages = max(1, Config.SYNC_PAGES)
    jobs = []

    def add(media, params, trend=False, tag=None, n=None):
        jobs.append({"media": media, "params": params, "trend": trend, "tag": tag, "pages": n or pages})

    for lang in ASIAN_LANGS:
        add("movie", {"with_original_language": lang, "sort_by": "popularity.desc"})
        add("movie", {"with_original_language": lang, "sort_by": "popularity.desc",
                      "primary_release_date.gte": recent_from, "primary_release_date.lte": today.isoformat()},
            trend=True, n=1)
    for lang in TOP_RATED_LANGS:
        add("movie", {"with_original_language": lang, "sort_by": "vote_average.desc", "vote_count.gte": 300})
    add("movie", {"with_original_language": "ja", "with_genres": "16", "sort_by": "popularity.desc"})  # anime films

    for cc in TV_COUNTRIES:
        extra = {"without_genres": "16"} if cc == "JP" else {}
        add("tv", {"with_origin_country": cc, "sort_by": "popularity.desc", **extra})
        add("tv", {"with_origin_country": cc, "sort_by": "popularity.desc", "air_date.gte": recent_from,
                   "air_date.lte": today.isoformat(), **extra}, trend=True, n=1)
    add("tv", {"with_original_language": "ja", "with_genres": "16", "sort_by": "popularity.desc"})  # anime series
    add("tv", {"with_original_language": "ja", "with_genres": "16", "sort_by": "popularity.desc",
               "air_date.gte": recent_from, "air_date.lte": today.isoformat()}, trend=True, n=1)

    for tag, names in KEYWORD_TAGS.items():
        ids = [k for k in (_safe_keyword(n) for n in names) if k]
        if not ids:
            continue
        for cc in ("KR", "CN", "JP", "TW", "TH"):
            add("tv", {"with_origin_country": cc, "with_keywords": "|".join(str(i) for i in ids),
                       "sort_by": "popularity.desc"}, tag=tag, n=1)
    return jobs


def _safe_keyword(name):
    try:
        return tmdb.keyword_id(name)
    except TMDBError:
        return None


# ------------------------------------------------------------------ helpers
def _norm(title):
    return re.sub(r"\W+", "", (title or "").lower())


def _pick_trailer(videos):
    clips = [v for v in (videos or {}).get("results", []) if v.get("site") == "YouTube" and v.get("key")]
    for kind in ("Trailer", "Teaser"):
        picks = [v for v in clips if v.get("type") == kind]
        picks.sort(key=lambda v: not v.get("official"))
        if picks:
            return picks[0]["key"]
    return None


def _row_from_tmdb(media, d, tags, existing_genres):
    credits = d.get("credits") or {}
    if media == "movie":
        title, original = d.get("title"), d.get("original_title")
        release = d.get("release_date") or None
        countries = [c["iso_3166_1"] for c in d.get("production_countries", [])] or d.get("origin_country") or []
        directors = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"][:3]
    else:
        title, original = d.get("name"), d.get("original_name")
        release = d.get("first_air_date") or None
        countries = d.get("origin_country") or [c["iso_3166_1"] for c in d.get("production_countries", [])]
        directors = [c["name"] for c in d.get("created_by", [])][:3]
    genres = [g["name"] for g in d.get("genres", [])]
    if "History" in genres:
        genres.append("Historical")
    kept = [g for g in existing_genres if g in TAG_NAMES]
    genres = list(dict.fromkeys(genres + sorted(tags) + kept))
    row = {
        "title": title or original or "Untitled", "original_title": original, "overview": d.get("overview") or "",
        "release_date": release, "year": int(release[:4]) if release else None,
        "rating": d.get("vote_average") or 0, "vote_count": d.get("vote_count") or 0,
        "popularity": d.get("popularity") or 0,
        "poster_path": d.get("poster_path"), "backdrop_path": d.get("backdrop_path"),
        "genres": jdump(genres), "countries": jdump(countries), "original_language": d.get("original_language"),
        "cast_members": jdump([{"name": c["name"], "character": c.get("character"), "profile_path": c.get("profile_path")}
                               for c in credits.get("cast", [])[:15]]),
        "directors": jdump(directors), "trailer_key": _pick_trailer(d.get("videos")),
        "similar_tmdb_ids": jdump([s["id"] for s in (d.get("similar") or {}).get("results", [])[:20]]),
        "source": "tmdb", "last_synced_at": iso(), "updated_at": iso(),
    }
    if media == "movie":
        row["runtime"] = d.get("runtime")
    else:
        runtimes = d.get("episode_run_time") or []
        row.update({"episode_runtime": runtimes[0] if runtimes else None,
                    "number_of_seasons": d.get("number_of_seasons") or 0,
                    "number_of_episodes": d.get("number_of_episodes") or 0, "status": d.get("status")})
    return row


def _write(table, row, tmdb_id, row_id=None):
    if row_id:
        sets = ", ".join(f"{k} = ?" for k in row)
        params = list(row.values()) + ([tmdb_id] if tmdb_id else []) + [row_id]
        db.execute(f"UPDATE {table} SET {sets}{', tmdb_id = ?' if tmdb_id else ''} WHERE id = ?", params)
        return row_id
    cols = ["tmdb_id"] + list(row)
    marks = ",".join("?" for _ in cols)
    return db.insert(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks})", [tmdb_id] + list(row.values()))


def _save_seasons(series_id, d):
    for s in d.get("seasons") or []:
        db.execute(
            "INSERT INTO seasons (series_id, tmdb_id, season_number, name, overview, air_date, episode_count, poster_path) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (series_id, season_number) DO UPDATE SET tmdb_id = excluded.tmdb_id, "
            "name = excluded.name, overview = excluded.overview, air_date = excluded.air_date, "
            "episode_count = excluded.episode_count, poster_path = excluded.poster_path",
            [series_id, s.get("id"), s.get("season_number"), s.get("name"), s.get("overview"),
             s.get("air_date") or None, s.get("episode_count") or 0, s.get("poster_path")])


def _is_fresh(ts):
    return bool(ts) and parse(ts) > utcnow() - timedelta(hours=Config.SYNC_REFRESH_HOURS)


def import_title(media, tmdb_id, tags=()):
    """Fetch one title from TMDB and insert/update it. Returns (local_id, outcome)."""
    media_type = "movie" if media == "movie" else "series"
    table = TABLES[media_type]
    existing = db.one(f"SELECT id, genres FROM {table} WHERE tmdb_id = ?", [tmdb_id])
    details = tmdb.details(media, tmdb_id)
    row = _row_from_tmdb(media, details, set(tags), jload(existing["genres"], []) if existing else [])
    if existing:
        local_id = _write(table, row, None, existing["id"])
        outcome = "updated"
    else:
        outcome = "added"
        local_id = None
        if row["year"]:  # duplicate detection: same title + year + language, different/unknown TMDB id
            for cand in db.query(f"SELECT id, title, tmdb_id, original_language FROM {table} WHERE year = ?", [row["year"]]):
                same_lang = not cand["original_language"] or cand["original_language"] == row["original_language"]
                if same_lang and _norm(cand["title"]) == _norm(row["title"]):
                    if cand["tmdb_id"] is None:  # a hand-added entry: adopt it, don't duplicate it
                        local_id = _write(table, row, tmdb_id, cand["id"])
                        outcome = "merged"
                    else:
                        return cand["id"], "duplicate"
                    break
        if local_id is None:
            local_id = _write(table, row, tmdb_id)
    if media_type == "series":
        _save_seasons(local_id, details)
    return local_id, outcome


# ------------------------------------------------------------------ the run
def _run(log_id, force):
    stats = {"added": 0, "updated": 0, "dups": 0, "errors": 0, "unchanged": 0, "sources": 0}
    messages, status = [], "success"
    try:
        if not tmdb.configured:
            raise RuntimeError("TMDB_API_KEY is not set, so there is nothing to synchronise from.")
        health = provider_health(force=True)
        found = {}
        jobs = build_jobs()
        for job in jobs:
            for page in range(1, job["pages"] + 1):
                try:
                    data = tmdb.discover(job["media"], page, **job["params"])
                except TMDBError as exc:
                    stats["errors"] += 1
                    messages.append(f"discover {job['media']} p{page}: {exc}")
                    break
                for item in data.get("results") or []:
                    entry = found.setdefault((job["media"], item["id"]), {"tags": set(), "trend": False, "item": item})
                    if job["tag"]:
                        entry["tags"].add(job["tag"])
                    entry["trend"] = entry["trend"] or job["trend"]
                if page >= (data.get("total_pages") or 1):
                    break
        order = sorted(found.items(), key=lambda kv: (not kv[1]["trend"], -(kv[1]["item"].get("popularity") or 0)))
        touched = []
        for (media, tmdb_id), entry in order[: Config.SYNC_MAX_TITLES]:
            media_type = "movie" if media == "movie" else "series"
            table = TABLES[media_type]
            existing = db.one(f"SELECT id, last_synced_at FROM {table} WHERE tmdb_id = ?", [tmdb_id])
            try:
                if existing and not force and _is_fresh(existing["last_synced_at"]) and not entry["tags"]:
                    it = entry["item"]
                    db.execute(f"UPDATE {table} SET popularity = ?, rating = ?, vote_count = ? WHERE id = ?",
                               [it.get("popularity") or 0, it.get("vote_average") or 0, it.get("vote_count") or 0, existing["id"]])
                    stats["unchanged"] += 1
                    continue
                local_id, outcome = import_title(media, tmdb_id, entry["tags"])
            except (TMDBError, ValueError, KeyError) as exc:
                stats["errors"] += 1
                if len(messages) < 25:
                    messages.append(f"{media} {tmdb_id}: {exc}")
                continue
            if outcome == "duplicate":
                stats["dups"] += 1
            elif outcome == "added":
                stats["added"] += 1
            else:
                stats["updated"] += 1
            if media_type == "movie" and outcome in ("added", "merged"):
                touched.append(local_id)

        # trending = most popular titles with recent releases / airing episodes
        trending = sorted([(k, v) for k, v in found.items() if v["trend"]],
                          key=lambda kv: -(kv[1]["item"].get("popularity") or 0))[:30]
        if trending:
            for table in TABLES.values():
                db.execute(f"UPDATE {table} SET trending_rank = NULL")
            for rank, ((media, tmdb_id), _) in enumerate(trending, start=1):
                db.execute(f"UPDATE {TABLES['movie' if media == 'movie' else 'series']} SET trending_rank = ? WHERE tmdb_id = ?",
                           [rank, tmdb_id])

        if any(p["status"] == "ok" for p in health):
            from services.playback import discover_from_providers
            for movie_id in touched[:MAX_PROVIDER_LOOKUPS]:
                stats["sources"] += discover_from_providers("movie", movie_id)

        if stats["errors"]:
            status = "partial" if (stats["added"] + stats["updated"] + stats["unchanged"]) else "failed"
        details = {"unchanged": stats["unchanged"], "sources_saved": stats["sources"], "jobs": len(jobs),
                   "titles_found": len(found), "providers": provider_health(), "messages": messages}
    except Exception as exc:  # the log must always get closed
        log.exception("sync failed")
        status = "failed"
        stats["errors"] += 1
        details = {"messages": [str(exc)]}
    finally:
        cache.clear("home")
        db.execute(
            "UPDATE synchronization_logs SET status = ?, finished_at = ?, titles_added = ?, titles_updated = ?, "
            "duplicates_skipped = ?, errors = ?, details = ? WHERE id = ?",
            [status, iso(), stats["added"], stats["updated"], stats["dups"], stats["errors"], json.dumps(details), log_id])
        _run_lock.release()


def start_sync(trigger="manual", user_id=None, force=False, background=True):
    if not _run_lock.acquire(blocking=False):
        raise ApiError("A synchronization is already running.", 409, "sync_running")
    try:
        cutoff = iso(utcnow() - timedelta(hours=2))
        db.execute("UPDATE synchronization_logs SET status = 'failed', finished_at = ?, details = ? "
                   "WHERE status = 'running' AND started_at < ?", [iso(), json.dumps({"messages": ["Interrupted."]}), cutoff])
        if db.one("SELECT id FROM synchronization_logs WHERE status = 'running'"):
            raise ApiError("A synchronization is already running.", 409, "sync_running")
        log_id = db.insert("INSERT INTO synchronization_logs (trigger_type, status, started_at, triggered_by) VALUES (?,?,?,?)",
                           [trigger, "running", iso(), user_id])
    except Exception:
        _run_lock.release()
        raise
    if background:
        threading.Thread(target=_run, args=(log_id, force), daemon=True, name="chillflix-sync").start()
    else:
        _run(log_id, force)
    return log_id


def history(limit=15):
    rows = db.query("SELECT * FROM synchronization_logs ORDER BY started_at DESC, id DESC LIMIT ?", [limit])
    for r in rows:
        r["details"] = jload(r["details"], {})
    return rows


def start_scheduler():
    """Optional background loop: sync every AUTO_SYNC_HOURS hours (use ONE server worker)."""
    if Config.AUTO_SYNC_HOURS <= 0 or not tmdb.configured:
        return

    def loop():
        time.sleep(20)
        while True:
            try:
                last = db.one("SELECT MAX(started_at) AS s FROM synchronization_logs")["s"]
                if last is None or parse(last) < utcnow() - timedelta(hours=Config.AUTO_SYNC_HOURS):
                    start_sync("scheduled", background=False)
            except ApiError:
                pass
            except Exception:
                log.exception("scheduler error")
            time.sleep(600)

    threading.Thread(target=loop, daemon=True, name="chillflix-scheduler").start()
