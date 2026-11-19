"""Base class for playback providers.

A provider answers one question: "do you have an AUTHORISED stream for this
title?". To connect another provider, copy moviebox.py, change the two methods,
and register it in providers/__init__.py. Nothing else in the app changes.
"""
import re

SOURCE_TYPES = ("hls", "mp4")


class Provider:
    name = "provider"

    def configured(self):
        raise NotImplementedError

    def health(self):
        """Return {"status": "ok"|"down"|"not_configured", "detail": str, "latency_ms": int|None}."""
        raise NotImplementedError

    def find_sources(self, ctx):
        """ctx = {"tmdb_id", "media_type": "movie"|"tv", "title", "season", "episode"}.
        Return a list of dicts: url, type, quality, language, subtitles."""
        raise NotImplementedError


def clean_source(raw):
    """Accept only well-formed https sources. Anything else is ignored, never guessed."""
    if not isinstance(raw, dict):
        return None
    url = str(raw.get("url") or "").strip()
    kind = str(raw.get("type") or "").lower()
    if not url.lower().startswith("https://") or kind not in SOURCE_TYPES or len(url) > 2000:
        return None
    subtitles = []
    for sub in raw.get("subtitles") or []:
        if isinstance(sub, dict) and str(sub.get("url", "")).lower().startswith("https://"):
            subtitles.append({
                "lang": re.sub(r"[^A-Za-z-]", "", str(sub.get("lang", "")))[:8] or "und",
                "label": str(sub.get("label") or sub.get("lang") or "Subtitles")[:40],
                "url": str(sub["url"])[:2000],
            })
    return {
        "url": url,
        "type": kind,
        "quality": str(raw.get("quality") or "auto")[:16],
        "language": str(raw.get("language") or "original")[:16],
        "subtitles": subtitles,
    }
