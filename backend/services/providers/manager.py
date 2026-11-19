"""Finds playable sources for a title: stored sources first, then the configured providers."""
import json
from services.providers.moviebox import MovieBoxProvider
from utils import cache
from utils.db import new_id, now

PROVIDERS = [MovieBoxProvider()]  # add more authorized providers here


def health_all(use_cache=True):
    key = ("provider-health",)
    if use_cache and cache.get(key):
        return cache.get(key)
    result = [p.health() for p in PROVIDERS]
    cache.set(key, result, 60)
    return result


def _row_to_source(row):
    return {"id": row["id"], "provider": row["provider"], "url": row["url"], "kind": row["kind"],
            "quality": row["quality"] or "", "language": row["language"] or "",
            "subtitles": json.loads(row["subtitles"] or "[]"), "min_plan": row["min_plan"]}


def stored_sources(conn, title_type, title_id, season=0, episode=0):
    rows = conn.all(
        "SELECT * FROM provider_sources WHERE title_type=? AND title_id=? AND season_number=? "
        "AND episode_number=? AND is_active=1 ORDER BY created_at", (title_type, title_id, season, episode))
    return [_row_to_source(r) for r in rows]


def find_sources(conn, title_type, title_id, tmdb_id, season=0, episode=0):
    found = stored_sources(conn, title_type, title_id, season, episode)
    if found:
        return found
    miss_key = ("no-source", title_type, title_id, season, episode)
    if cache.get(miss_key):
        return []
    for provider in PROVIDERS:
        if not provider.is_configured():
            continue
        for src in provider.get_sources("movie" if title_type == "movie" else "tv", tmdb_id, season, episode):
            conn.run(
                "INSERT INTO provider_sources (id, provider, title_type, title_id, season_number, episode_number, url, "
                "kind, quality, language, subtitles, min_plan, is_active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
                (new_id(), provider.name, title_type, title_id, season, episode, src["url"], src["kind"],
                 src["quality"], src["language"], json.dumps(src["subtitles"]), "free", now()))
    found = stored_sources(conn, title_type, title_id, season, episode)
    if not found:
        cache.set(miss_key, True, 300)  # don't hammer the provider for titles it doesn't have
    return found
