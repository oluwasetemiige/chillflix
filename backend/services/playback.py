"""Finds playable sources for a title/episode. Never invents a link."""
import json

from services.catalog import jload
from services.providers import PROVIDERS
from utils.cache import cache
from utils.db import db
from utils.times import iso


def _serialize(r):
    return {
        "id": r["id"], "url": r["source_url"], "type": r["source_type"], "quality": r["quality"],
        "language": r["language"], "subtitles": jload(r["subtitles"], []), "premium_only": bool(r["premium_only"]),
        "provider": r["provider"],
    }


def _stored(media_type, media_id, episode_id):
    return db.query(
        "SELECT * FROM provider_sources WHERE media_type = ? AND media_id = ? AND episode_id = ? AND is_active = ? "
        "ORDER BY id", [media_type, media_id, episode_id, True])


def discover_from_providers(media_type, media_id, episode_id=0):
    """Ask every configured provider and store what they authorise. Returns how many were saved."""
    table = "movies" if media_type == "movie" else "series"
    title = db.one(f"SELECT id, tmdb_id, title FROM {table} WHERE id = ?", [media_id])
    if not title or not title["tmdb_id"]:
        return 0
    ctx = {"tmdb_id": title["tmdb_id"], "media_type": "movie" if media_type == "movie" else "tv",
           "title": title["title"], "season": None, "episode": None}
    if media_type == "series" and episode_id:
        ep = db.one("SELECT e.episode_number, s.season_number FROM episodes e JOIN seasons s ON s.id = e.season_id "
                    "WHERE e.id = ? AND e.series_id = ?", [episode_id, media_id])
        if not ep:
            return 0
        ctx["season"], ctx["episode"] = ep["season_number"], ep["episode_number"]
    elif media_type == "series":
        return 0  # a series is played episode by episode
    saved = 0
    for provider in PROVIDERS:
        if not provider.configured():
            continue
        for src in provider.find_sources(ctx):
            saved += db.execute(
                "INSERT INTO provider_sources (provider, media_type, media_id, episode_id, source_url, source_type, "
                "quality, language, subtitles, premium_only, is_active, last_checked_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT DO NOTHING",
                [provider.name, media_type, media_id, episode_id, src["url"], src["type"], src["quality"],
                 src["language"], json.dumps(src["subtitles"]), src["quality"] in ("1080p", "2160p", "4k"), True, iso()])
    return saved


def resolve(media_type, media_id, episode_id=0, premium=False):
    rows = _stored(media_type, media_id, episode_id)
    if not rows:
        key = f"nosrc:{media_type}:{media_id}:{episode_id}"
        if cache.get(key) is None:
            if discover_from_providers(media_type, media_id, episode_id):
                rows = _stored(media_type, media_id, episode_id)
            else:
                cache.set(key, True, 600)  # don't hammer providers for titles they don't have
    sources = [_serialize(r) for r in rows]
    visible = [s for s in sources if premium or not s["premium_only"]]
    return {"sources": visible, "locked_count": len(sources) - len(visible)}
