"""Catalogue queries and JSON shaping (movies + series share one code path)."""
import json
from datetime import date

from config import Config
from services.tmdb import TMDBError, tmdb
from utils.db import db
from utils.responses import ApiError
from utils.times import iso

TABLES = {"movie": "movies", "series": "series"}

COMMON_COLS = (
    "id, tmdb_id, title, original_title, overview, year, release_date, rating, vote_count, "
    "popularity, poster_path, backdrop_path, genres, countries, original_language, trending_rank"
)

ORDERS = {
    "popularity": "popularity DESC, id DESC",
    "rating": "rating DESC, vote_count DESC, id DESC",
    "recent": "release_date DESC, popularity DESC",
    "trending": "CASE WHEN trending_rank IS NULL THEN 1 ELSE 0 END, trending_rank, popularity DESC",
    "title": "LOWER(title) ASC",
}

GENRE_CHOICES = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Drama", "Family", "Fantasy",
    "Historical", "Horror", "Mystery", "Romance", "Science Fiction", "Thriller", "War",
]


# ---------------------------------------------------------------- helpers
def img(path, size="w500"):
    if not path:
        return None
    if str(path).startswith("http"):
        return path
    return f"{Config.TMDB_IMAGE_BASE}{size}{path}"


def jload(value, default):
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def jdump(value):
    return json.dumps(value, ensure_ascii=False)


def table_for(media_type):
    if media_type not in TABLES:
        raise ApiError("Unknown media type.", 400, "bad_request")
    return TABLES[media_type]


def _csv(value):
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


def to_card(r, hero=False):
    card = {
        "id": r["id"],
        "media_type": r["media_type"],
        "title": r["title"],
        "year": r.get("year"),
        "rating": round(float(r.get("rating") or 0), 1),
        "poster": img(r.get("poster_path"), "w342"),
    }
    if hero:
        card.update({
            "overview": r.get("overview") or "",
            "genres": jload(r.get("genres"), [])[:3],
            "backdrop": img(r.get("backdrop_path"), "w1280"),
            "backdrop_small": img(r.get("backdrop_path"), "w780"),
        })
    return card


# ---------------------------------------------------------------- listing
def _where(f):
    where, params = [], []
    codes = [c.upper() for c in _csv(f.get("country"))]
    if codes:
        where.append("(" + " OR ".join("countries LIKE ?" for _ in codes) + ")")
        params += [f'%"{c.replace(chr(34), "")}"%' for c in codes]
    langs = [l.lower() for l in _csv(f.get("language"))]
    if langs:
        where.append("original_language IN (" + ",".join("?" for _ in langs) + ")")
        params += langs
    for key in ("genre", "extra_genre"):
        names = [n.replace('"', "").replace("%", "") for n in _csv(f.get(key))]
        if names:
            where.append("(" + " OR ".join("genres LIKE ?" for _ in names) + ")")
            params += [f'%"{n}"%' for n in names]
    excl = [n.replace('"', "").replace("%", "") for n in _csv(f.get("exclude_genre"))]
    if excl:
        where.append("(" + " AND ".join("genres NOT LIKE ?" for _ in excl) + ")")
        params += [f'%"{n}"%' for n in excl]
    if f.get("year"):
        where.append("year = ?")
        params.append(int(f["year"]))
    if f.get("q"):
        like = "%" + str(f["q"]).lower().replace("%", "").replace("_", "") + "%"
        where.append("(LOWER(title) LIKE ? OR LOWER(COALESCE(original_title, '')) LIKE ?)")
        params += [like, like]
    if f.get("released"):
        where.append("release_date IS NOT NULL AND release_date <= ?")
        params.append(date.today().isoformat())
    if f.get("min_votes"):
        where.append("vote_count >= ?")
        params.append(int(f["min_votes"]))
    if f.get("trending"):
        where.append("trending_rank IS NOT NULL")
    if f.get("has_backdrop"):
        where.append("backdrop_path IS NOT NULL AND overview IS NOT NULL AND overview <> ''")
    return (" AND ".join(where) or "1=1"), params


def list_titles(media_type="all", filters=None, sort="popularity", page=1, limit=24):
    """Returns {"items": [...rows], "total": n}. media_type: movie | series | all."""
    filters = dict(filters or {})
    sort = sort if sort in ORDERS else "popularity"
    if sort == "recent":
        filters["released"] = True
    if sort == "rating":
        filters.setdefault("min_votes", 50)
    if sort == "trending":
        filters["trending"] = True
    types = ["movie", "series"] if media_type == "all" else [media_type]
    where, wparams = _where(filters)
    branches, params = [], []
    for mt in types:
        branches.append(f"SELECT '{mt}' AS media_type, {COMMON_COLS} FROM {table_for(mt)} WHERE {where}")
        params += wparams
    inner = " UNION ALL ".join(branches)
    total = db.one(f"SELECT COUNT(*) AS c FROM ({inner}) t", params)["c"]
    rows = db.query(
        f"SELECT * FROM ({inner}) t ORDER BY {ORDERS[sort]} LIMIT ? OFFSET ?",
        params + [limit, (page - 1) * limit],
    )
    return {"rows": rows, "total": total}


def paged(media_type, filters, sort, page, limit, hero=False):
    result = list_titles(media_type, filters, sort, page, limit)
    pages = max(1, -(-result["total"] // limit))
    return {
        "items": [to_card(r, hero=hero) for r in result["rows"]],
        "page": page, "pages": pages, "total": result["total"],
    }


# ---------------------------------------------------------------- categories
def category_query(cat):
    filters = {
        "country": cat.get("country"), "language": cat.get("language"),
        "genre": cat.get("genre"), "exclude_genre": cat.get("exclude_genre"),
    }
    return cat["media_type"], filters, cat["sort"]


def get_category(slug):
    return db.one("SELECT * FROM categories WHERE slug = ?", [slug])


def list_categories(only_home=False):
    sql = "SELECT * FROM categories" + (" WHERE show_on_home = ?" if only_home else "") + " ORDER BY position, id"
    rows = db.query(sql, [True] if only_home else [])
    for r in rows:
        r["show_on_home"] = bool(r["show_on_home"])
    return rows


def home_rows(per_row=18):
    rows = []
    for cat in list_categories(only_home=True):
        mt, filters, sort = category_query(cat)
        result = list_titles(mt, filters, sort, 1, per_row)
        if result["rows"]:
            rows.append({
                "slug": cat["slug"], "title": cat["name"], "ranked": cat["sort"] == "trending",
                "items": [to_card(r) for r in result["rows"]],
            })
    return rows


def hero_items(limit=6):
    result = list_titles("all", {"has_backdrop": True, "trending": True}, "trending", 1, limit)
    if len(result["rows"]) < 3:
        result = list_titles("all", {"has_backdrop": True}, "popularity", 1, limit)
    return [to_card(r, hero=True) for r in result["rows"]]


def seed_categories():
    if db.one("SELECT COUNT(*) AS c FROM categories")["c"]:
        return
    #        slug, name, media, country, language, genre, exclude, sort
    defaults = [
        ("trending", "Trending Now", "all", None, None, None, None, "trending"),
        ("k-drama", "Popular K-Dramas", "series", "KR", None, "Drama", None, "popularity"),
        ("c-drama", "Popular C-Dramas", "series", "CN,TW,HK", None, "Drama", None, "popularity"),
        ("japanese-movies", "Japanese Movies", "movie", None, "ja", None, "Animation", "popularity"),
        ("anime", "Japanese Anime", "all", None, "ja", "Animation", None, "popularity"),
        ("recent", "Recently Released", "all", None, None, None, None, "recent"),
        ("top-rated-movies", "Top Rated Asian Movies", "movie", None, None, None, None, "rating"),
        ("romance", "Romance", "all", None, None, "Romance", None, "popularity"),
        ("action-adventure", "Action & Adventure", "all", None, None, "Action,Adventure,Action & Adventure", None, "popularity"),
        ("thriller", "Thriller", "all", None, None, "Thriller", None, "popularity"),
        ("historical", "Historical Dramas", "all", None, None, "Historical", None, "popularity"),
    ]
    for pos, row in enumerate(defaults, start=1):
        db.execute(
            "INSERT INTO categories (slug, name, media_type, country, language, genre, exclude_genre, sort, position, show_on_home) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)", list(row) + [pos, True],
        )


def genre_options():
    """Genre names that exist in the catalogue, plus the standard list for preferences."""
    names = set(GENRE_CHOICES)
    for table in TABLES.values():
        for r in db.query(f"SELECT genres FROM {table}"):
            names.update(jload(r["genres"], []))
    return sorted(names)


# ---------------------------------------------------------------- details
def _similar(media_type, row):
    table = table_for(media_type)
    ids = jload(row.get("similar_tmdb_ids"), [])[:20]
    items = []
    if ids:
        marks = ",".join("?" for _ in ids)
        items = db.query(
            f"SELECT '{media_type}' AS media_type, {COMMON_COLS} FROM {table} "
            f"WHERE tmdb_id IN ({marks}) AND id <> ? ORDER BY popularity DESC LIMIT 14", ids + [row["id"]])
    if len(items) < 6:
        genres = jload(row.get("genres"), [])
        if genres:
            more = list_titles(media_type, {"genre": genres[0]}, "popularity", 1, 14)["rows"]
            seen = {i["id"] for i in items} | {row["id"]}
            items += [m for m in more if m["id"] not in seen][: 14 - len(items)]
    return [to_card(i) for i in items]


def has_sources(media_type, media_id):
    return bool(db.one(
        "SELECT 1 AS x FROM provider_sources WHERE media_type = ? AND media_id = ? AND is_active = ? LIMIT 1",
        [media_type, media_id, True]))


def get_title(media_type, media_id, user=None):
    table = table_for(media_type)
    row = db.one(f"SELECT * FROM {table} WHERE id = ?", [media_id])
    if not row:
        raise ApiError("Title not found.", 404, "not_found")
    trailer_key = row.get("trailer_key")
    data = {
        "id": row["id"], "media_type": media_type, "tmdb_id": row.get("tmdb_id"),
        "title": row["title"], "original_title": row.get("original_title"),
        "overview": row.get("overview") or "",
        "year": row.get("year"), "release_date": row.get("release_date"),
        "rating": round(float(row.get("rating") or 0), 1), "vote_count": row.get("vote_count") or 0,
        "poster": img(row.get("poster_path"), "w500"),
        "backdrop": img(row.get("backdrop_path"), "w1280"),
        "genres": jload(row.get("genres"), []),
        "countries": jload(row.get("countries"), []),
        "language": row.get("original_language"),
        "cast": [
            {"name": c.get("name"), "character": c.get("character"), "photo": img(c.get("profile_path"), "w185")}
            for c in jload(row.get("cast_members"), [])
        ],
        "directors": jload(row.get("directors"), []),
        "trailer": ({"key": trailer_key, "embed_url": f"https://www.youtube-nocookie.com/embed/{trailer_key}"}
                    if trailer_key else None),
        "similar": _similar(media_type, row),
        "playable": has_sources(media_type, media_id),
        "watchlist_id": None, "progress": None,
    }
    if media_type == "movie":
        data["runtime"] = row.get("runtime")
    else:
        data.update({
            "episode_runtime": row.get("episode_runtime"), "status": row.get("status"),
            "number_of_seasons": row.get("number_of_seasons"), "number_of_episodes": row.get("number_of_episodes"),
        })
        seasons = db.query(
            "SELECT season_number, name, episode_count, air_date, poster_path FROM seasons WHERE series_id = ? "
            "ORDER BY CASE WHEN season_number = 0 THEN 1 ELSE 0 END, season_number", [media_id])
        data["seasons"] = [{
            "season_number": s["season_number"], "name": s["name"] or f"Season {s['season_number']}",
            "episode_count": s["episode_count"], "air_date": s["air_date"], "poster": img(s["poster_path"], "w185"),
        } for s in seasons]
    if user:
        w = db.one("SELECT id FROM watchlist WHERE user_id = ? AND media_type = ? AND media_id = ?",
                   [user["id"], media_type, media_id])
        data["watchlist_id"] = w["id"] if w else None
        h = db.one(
            "SELECT episode_id, position_seconds, duration_seconds, completed FROM watch_history "
            "WHERE user_id = ? AND media_type = ? AND media_id = ? ORDER BY updated_at DESC LIMIT 1",
            [user["id"], media_type, media_id])
        if h:
            data["progress"] = {
                "episode_id": h["episode_id"], "position": h["position_seconds"],
                "duration": h["duration_seconds"], "completed": bool(h["completed"]),
            }
    return data


def season_episodes(series_id, season_number):
    series = db.one("SELECT id, tmdb_id FROM series WHERE id = ?", [series_id])
    if not series:
        raise ApiError("Series not found.", 404, "not_found")
    season = db.one("SELECT * FROM seasons WHERE series_id = ? AND season_number = ?", [series_id, season_number])
    if not season:
        raise ApiError("Season not found.", 404, "not_found")
    episodes = db.query("SELECT * FROM episodes WHERE season_id = ? ORDER BY episode_number", [season["id"]])
    if not episodes and series["tmdb_id"] and tmdb.configured:
        try:
            payload = tmdb.season(series["tmdb_id"], season_number)
            with db.tx() as t:
                for ep in payload.get("episodes") or []:
                    t.execute(
                        "INSERT INTO episodes (season_id, series_id, episode_number, name, overview, air_date, runtime, still_path) "
                        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (season_id, episode_number) DO UPDATE SET "
                        "name = excluded.name, overview = excluded.overview, air_date = excluded.air_date, "
                        "runtime = excluded.runtime, still_path = excluded.still_path",
                        [season["id"], series_id, ep.get("episode_number"), ep.get("name"), ep.get("overview"),
                         ep.get("air_date") or None, ep.get("runtime"), ep.get("still_path")])
            episodes = db.query("SELECT * FROM episodes WHERE season_id = ? ORDER BY episode_number", [season["id"]])
        except TMDBError:
            pass  # show whatever we have; the page handles an empty list
    playable_ids = set()
    if episodes:
        marks = ",".join("?" for _ in episodes)
        playable_ids = {r["episode_id"] for r in db.query(
            f"SELECT DISTINCT episode_id FROM provider_sources WHERE media_type = 'series' AND media_id = ? "
            f"AND is_active = ? AND episode_id IN ({marks})", [series_id, True] + [e["id"] for e in episodes])}
    return {
        "season_number": season_number, "name": season["name"] or f"Season {season_number}",
        "episodes": [{
            "id": e["id"], "episode_number": e["episode_number"], "name": e["name"] or f"Episode {e['episode_number']}",
            "overview": e["overview"] or "", "air_date": e["air_date"], "runtime": e["runtime"],
            "still": img(e["still_path"], "w300"), "playable": e["id"] in playable_ids,
        } for e in episodes],
    }


# ---------------------------------------------------------------- recommendations
def recommendations(user, premium):
    prefs = db.one("SELECT favorite_genres FROM user_preferences WHERE user_id = ?", [user["id"]]) or {}
    favorites = jload(prefs.get("favorite_genres"), [])
    weights = {g: 3 for g in favorites}
    seen = set()
    if premium:  # premium tier also learns from what you watch and save
        rows = db.query("SELECT media_type, media_id FROM watch_history WHERE user_id = ? "
                        "UNION SELECT media_type, media_id FROM watchlist WHERE user_id = ?", [user["id"], user["id"]])
        for r in rows:
            seen.add((r["media_type"], r["media_id"]))
            title = db.one(f"SELECT genres FROM {TABLES[r['media_type']]} WHERE id = ?", [r["media_id"]])
            for g in jload(title["genres"], []) if title else []:
                weights[g] = weights.get(g, 0) + 1
    else:
        for r in db.query("SELECT media_type, media_id FROM watchlist WHERE user_id = ?", [user["id"]]):
            seen.add((r["media_type"], r["media_id"]))
    top = [g for g, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:4]]
    size = 24 if premium else 12
    if top:
        pool = list_titles("all", {"genre": ",".join(top)}, "popularity", 1, 80)["rows"]
        scored = []
        for r in pool:
            if (r["media_type"], r["id"]) in seen:
                continue
            score = sum(weights.get(g, 0) for g in jload(r["genres"], [])) + float(r["rating"] or 0) / 10
            scored.append((score, r))
        scored.sort(key=lambda s: -s[0])
        rows = [r for _, r in scored[:size]]
        reason = "Because you like " + ", ".join(top[:3]) + "."
    else:
        rows = list_titles("all", {}, "rating", 1, size)["rows"]
        reason = "Top rated right now. Pick favourite genres in your profile to personalise this."
    return {"items": [to_card(r) for r in rows], "reason": reason, "personalized": bool(top),
            "tier": "premium" if premium else "free"}
