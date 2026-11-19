"""TMDB client: metadata, images, cast, trailers and similar titles.

Accepts either a v3 API key (32 characters) or a v4 "API Read Access Token"
(starts with eyJ) in TMDB_API_KEY. Responses are cached in memory.
"""
import time

import requests

from config import Config
from utils.cache import cache


class TMDBError(Exception):
    pass


class TMDBClient:
    CACHE_SECONDS = 60 * 30

    @property
    def configured(self):
        return bool(Config.TMDB_API_KEY)

    def _request(self, path, params=None, ttl=None):
        if not self.configured:
            raise TMDBError("TMDB_API_KEY is not set.")
        params = dict(params or {})
        headers = {"Accept": "application/json"}
        key = Config.TMDB_API_KEY
        if key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {key}"
        else:
            params["api_key"] = key

        cache_key = f"tmdb:{path}:{sorted((k, str(v)) for k, v in params.items() if k != 'api_key')}"
        ttl = self.CACHE_SECONDS if ttl is None else ttl
        if ttl:
            hit = cache.get(cache_key)
            if hit is not None:
                return hit

        last_error = None
        for attempt in range(3):
            try:
                resp = requests.get(f"{Config.TMDB_BASE}{path}", params=params, headers=headers, timeout=15)
            except requests.RequestException as exc:
                last_error = f"network error: {exc.__class__.__name__}"
                time.sleep(0.6 * (attempt + 1))
                continue
            if resp.status_code == 429:
                time.sleep(min(int(resp.headers.get("Retry-After", "2")), 10))
                last_error = "rate limited by TMDB"
                continue
            if resp.status_code == 401:
                raise TMDBError("TMDB rejected the API key (401).")
            if resp.status_code == 404:
                raise TMDBError("Not found on TMDB (404).")
            if resp.status_code >= 500:
                last_error = f"TMDB server error {resp.status_code}"
                time.sleep(0.6 * (attempt + 1))
                continue
            try:
                data = resp.json()
            except ValueError:
                raise TMDBError("TMDB returned an unreadable response.")
            if ttl:
                cache.set(cache_key, data, ttl)
            return data
        raise TMDBError(last_error or "TMDB request failed.")

    # -- endpoints ---------------------------------------------------------------
    def check(self):
        """Health check used by /api/health and the admin dashboard."""
        started = time.time()
        self._request("/configuration", ttl=0)
        return int((time.time() - started) * 1000)

    def discover(self, media_type, page=1, **params):
        path = "/discover/movie" if media_type == "movie" else "/discover/tv"
        params.update({"page": page, "include_adult": "false"})
        return self._request(path, params)

    def details(self, media_type, tmdb_id):
        path = f"/movie/{tmdb_id}" if media_type == "movie" else f"/tv/{tmdb_id}"
        return self._request(path, {
            "append_to_response": "credits,videos,similar",
            "include_video_language": "en,null,ko,ja,zh",
        })

    def season(self, tv_tmdb_id, season_number):
        return self._request(f"/tv/{tv_tmdb_id}/season/{season_number}")

    def keyword_id(self, name):
        data = self._request("/search/keyword", {"query": name}, ttl=60 * 60 * 24)
        for item in data.get("results") or []:
            if item.get("name", "").lower() == name.lower():  # exact matches only, never a guess
                return item["id"]
        return None


tmdb = TMDBClient()
