"""Provider registry. Add new authorised providers to PROVIDERS."""
from services.providers.moviebox import MovieBoxProvider
from utils.cache import cache

PROVIDERS = [MovieBoxProvider()]


def provider_health(force=False):
    """Health of every provider (cached for a minute so pages stay fast)."""
    if force:
        cache.clear("provider-health")

    def check():
        out = []
        for p in PROVIDERS:
            info = p.health()
            info["name"] = p.name
            out.append(info)
        return out

    return cache.remember("provider-health", 60, check)
