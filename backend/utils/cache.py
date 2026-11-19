"""A tiny in-memory cache with expiry (used for TMDB responses and home rows)."""
import threading
import time


class TTLCache:
    def __init__(self, max_items=2000):
        self._data = {}
        self._lock = threading.Lock()
        self._max = max_items

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
            if not hit:
                return None
            expires, value = hit
            if expires < time.time():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key, value, ttl):
        with self._lock:
            if len(self._data) >= self._max:
                now = time.time()
                for k in [k for k, (exp, _) in self._data.items() if exp < now]:
                    self._data.pop(k, None)
                if len(self._data) >= self._max:
                    self._data.clear()
            self._data[key] = (time.time() + ttl, value)

    def remember(self, key, ttl, producer):
        value = self.get(key)
        if value is None:
            value = producer()
            self.set(key, value, ttl)
        return value

    def clear(self, prefix=None):
        with self._lock:
            if prefix is None:
                self._data.clear()
            else:
                for k in [k for k in self._data if str(k).startswith(prefix)]:
                    self._data.pop(k, None)


cache = TTLCache()
