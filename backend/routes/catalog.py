from flask import Blueprint, g, request

from services import catalog as cat
from services.membership import is_premium
from services.playback import resolve
from utils import validation as v
from utils.cache import cache
from utils.db import db
from utils.responses import ApiError, ok
from utils.security import login_required, optional_auth

bp = Blueprint("catalog", __name__)

SORTS = ("popularity", "rating", "recent", "trending", "title")


def _listing(media_type):
    """Shared by /catalog, /movies and /series."""
    args = request.args
    page = v.integer(args.get("page"), 1, 1, 500, "page")
    limit = v.integer(args.get("limit"), 24, 1, 60, "limit")
    sort = args.get("sort") or "popularity"
    v.choice(sort, SORTS, "sort")
    filters = {"extra_genre": args.get("genre"), "country": args.get("country"), "language": args.get("language"),
               "year": v.integer(args.get("year"), None, 1900, 2100, "year"), "q": (args.get("q") or "").strip()[:80]}
    if args.get("category"):
        category = cat.get_category(args["category"])
        if not category:
            raise ApiError("Unknown category.", 404, "not_found")
        media_type, base, cat_sort = cat.category_query(category)
        for key in ("country", "language", "year", "q"):
            if filters.get(key) and not base.get(key):
                base[key] = filters[key]
        base["extra_genre"] = filters["extra_genre"]  # the page's genre picker narrows the category
        filters = base
        if not args.get("sort"):
            sort = cat_sort
    elif filters["extra_genre"]:
        filters["genre"], filters["extra_genre"] = filters["extra_genre"], None
    return ok(cat.paged(media_type, filters, sort, page, limit))


@bp.get("/catalog")
def catalog_all():
    media_type = request.args.get("type", "all")
    v.choice(media_type, ("all", "movie", "series"), "type")
    return _listing(media_type)


@bp.get("/movies")
def movies():
    return _listing("movie")


@bp.get("/series")
def series():
    return _listing("series")


@bp.get("/movies/trending")
def trending():
    result = cat.paged("movie", {}, "trending", 1, v.integer(request.args.get("limit"), 20, 1, 50, "limit"))
    if not result["items"]:  # nothing ranked yet: fall back to popularity
        result = cat.paged("movie", {}, "popularity", 1, 20)
    return ok(result)


@bp.get("/movies/popular")
def popular():
    return ok(cat.paged("movie", {}, "popularity", v.integer(request.args.get("page"), 1, 1, 500, "page"),
                        v.integer(request.args.get("limit"), 20, 1, 50, "limit")))


@bp.get("/movies/search")
def search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        raise ApiError("Type at least 2 characters to search.", 422, "validation_error", {"q": "length"})
    media_type = request.args.get("type", "all")
    v.choice(media_type, ("all", "movie", "series"), "type")
    return ok(cat.paged(media_type, {"q": q[:80]}, "popularity", v.integer(request.args.get("page"), 1, 1, 100, "page"), 30))


@bp.get("/movies/<int:movie_id>")
@optional_auth
def movie_detail(movie_id):
    return ok(cat.get_title("movie", movie_id, g.user))


@bp.get("/series/<int:series_id>")
@optional_auth
def series_detail(series_id):
    return ok(cat.get_title("series", series_id, g.user))


@bp.get("/series/<int:series_id>/seasons/<int:season_number>")
def season(series_id, season_number):
    return ok(cat.season_episodes(series_id, season_number))


@bp.get("/categories")
def categories():
    rows = cat.list_categories()
    return ok({"items": [{"slug": r["slug"], "name": r["name"], "media_type": r["media_type"]} for r in rows]})


@bp.get("/genres")
def genres():
    return ok({"items": cache.remember("genres", 300, cat.genre_options)})


@bp.get("/home")
def home():
    def build():
        return {"hero": cat.hero_items(6), "rows": cat.home_rows(18)}
    return ok(cache.remember("home:v1", 60, build))


@bp.get("/recommendations")
@login_required
def recommendations():
    return ok(cat.recommendations(g.user, is_premium(g.user["id"])))


@bp.get("/watch/<media_type>/<int:media_id>")
@optional_auth
def watch(media_type, media_id):
    v.media_type(media_type)
    episode_id = v.integer(request.args.get("episode"), 0, 0, None, "episode")
    premium = bool(g.user) and is_premium(g.user["id"])
    info = cat.get_title(media_type, media_id, None)
    payload = {"title": {k: info[k] for k in ("id", "media_type", "title", "year", "poster", "backdrop")},
               "episode": None, "episodes": [], "next_episode": None, "previous_episode": None}
    if media_type == "series":
        if not episode_id:
            first = db.one("SELECT e.id FROM episodes e JOIN seasons s ON s.id = e.season_id WHERE e.series_id = ? "
                           "AND s.season_number > 0 ORDER BY s.season_number, e.episode_number LIMIT 1", [media_id])
            episode_id = first["id"] if first else 0
        ep = db.one("SELECT e.id, e.name, e.episode_number, e.season_id, s.season_number FROM episodes e "
                    "JOIN seasons s ON s.id = e.season_id WHERE e.id = ? AND e.series_id = ?", [episode_id, media_id]) if episode_id else None
        if ep:
            payload["episode"] = {"id": ep["id"], "name": ep["name"], "episode_number": ep["episode_number"],
                                  "season_number": ep["season_number"]}
            ordered = db.query("SELECT e.id, e.name, e.episode_number, s.season_number FROM episodes e "
                               "JOIN seasons s ON s.id = e.season_id WHERE e.series_id = ? AND s.season_number > 0 "
                               "ORDER BY s.season_number, e.episode_number", [media_id])
            ids = [o["id"] for o in ordered]
            pos = ids.index(ep["id"])
            if pos + 1 < len(ordered):
                payload["next_episode"] = ordered[pos + 1]
            if pos > 0:
                payload["previous_episode"] = ordered[pos - 1]
            payload["episodes"] = [o for o in ordered if o["season_number"] == ep["season_number"]]
    sources = resolve(media_type, media_id, episode_id if media_type == "series" else 0, premium)
    payload.update(sources)
    payload["available"] = bool(sources["sources"])
    payload["is_premium"] = premium
    return ok(payload)
