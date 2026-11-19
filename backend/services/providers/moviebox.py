"""MovieBox provider adapter.

IMPORTANT: MovieBox does not publish a stable public API, and CHILLFLIX does not
scrape it. This adapter only talks to an endpoint YOU are authorised to use (for
example a licensed partner gateway). Set MOVIEBOX_API_BASE (and MOVIEBOX_API_KEY
if needed). With nothing set the adapter reports "not_configured" and the site
keeps working on TMDB metadata alone.

Expected contract of the authorised endpoint:

  GET {BASE}/health
      -> HTTP 200

  GET {BASE}/sources?tmdb_id=<id>&type=movie|tv[&season=<n>&episode=<n>]
      -> {"sources": [{
            "url": "https://.../master.m3u8",
            "type": "hls" | "mp4",
            "quality": "1080p",
            "language": "ko",
            "subtitles": [{"lang": "en", "label": "English", "url": "https://.../en.vtt"}]
         }]}
"""
import time

import requests

from config import Config
from services.providers.base import Provider, clean_source


class MovieBoxProvider(Provider):
    name = "moviebox"

    def configured(self):
        return bool(Config.MOVIEBOX_API_BASE)

    def _headers(self):
        headers = {"Accept": "application/json"}
        if Config.MOVIEBOX_API_KEY:
            headers["Authorization"] = f"Bearer {Config.MOVIEBOX_API_KEY}"
        return headers

    def health(self):
        if not self.configured():
            return {"status": "not_configured", "detail": "MOVIEBOX_API_BASE is not set.", "latency_ms": None}
        started = time.time()
        try:
            resp = requests.get(f"{Config.MOVIEBOX_API_BASE}/health", headers=self._headers(), timeout=8)
            latency = int((time.time() - started) * 1000)
            if resp.status_code == 200:
                return {"status": "ok", "detail": "Reachable.", "latency_ms": latency}
            return {"status": "down", "detail": f"HTTP {resp.status_code}", "latency_ms": latency}
        except requests.RequestException as exc:
            return {"status": "down", "detail": exc.__class__.__name__, "latency_ms": None}

    def find_sources(self, ctx):
        if not self.configured():
            return []
        params = {"tmdb_id": ctx["tmdb_id"], "type": ctx["media_type"]}
        if ctx.get("season") is not None:
            params["season"] = ctx["season"]
        if ctx.get("episode") is not None:
            params["episode"] = ctx["episode"]
        try:
            resp = requests.get(f"{Config.MOVIEBOX_API_BASE}/sources", params=params,
                                headers=self._headers(), timeout=12)
            if resp.status_code != 200:
                return []
            payload = resp.json()
        except (requests.RequestException, ValueError):
            return []
        cleaned = [clean_source(item) for item in (payload.get("sources") or [])]
        return [s for s in cleaned if s]
