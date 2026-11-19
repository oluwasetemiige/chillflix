"""End-to-end API tests. Run:  cd backend && python -m unittest tests.test_api -v

TMDB and Paystack are replaced by FAKE FIXTURES here so the tests run offline.
The fixture titles ("Test Movie 1101" ...) exist only inside the test database,
never in the real application.
"""
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["TMDB_API_KEY"] = "test-key"
os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_fixture"
os.environ["MOVIEBOX_API_BASE"] = "https://provider.example"
os.environ["ADMIN_EMAILS"] = "boss@example.com"
os.environ["SECRET_KEY"] = "test-secret"

import app as app_module  # noqa: E402
from services import sync as syncer  # noqa: E402
from services.tmdb import tmdb  # noqa: E402
from utils.db import db  # noqa: E402

LANG_MOVIES = {"ko": 1100, "ja": 1200, "zh": 1300, "cn": 1400, "th": 1500, "hi": 1600}
TV_BASE = {"KR": 2100, "CN": 2200, "TW": 2300, "HK": 2400, "JP": 2500, "TH": 2600}
ANIME_MOVIES, ANIME_TV = [1291, 1292], [2701, 2702]


def fake_tmdb(path, params=None, ttl=None):
    params = params or {}
    if path == "/configuration":
        return {}
    if path == "/search/keyword":
        return {"results": [{"id": 77, "name": params["query"]}]}
    if path == "/discover/movie":
        if params.get("with_genres") == "16":
            ids = ANIME_MOVIES
        else:
            base = LANG_MOVIES[params["with_original_language"]]
            ids = [base + 1, base + 2, base + 3]
        return {"page": 1, "total_pages": 1, "results": [{"id": i, "popularity": 100 - (i % 50), "vote_average": 7, "vote_count": 500} for i in ids]}
    if path == "/discover/tv":
        if params.get("with_genres") == "16":
            ids = ANIME_TV
        else:
            base = TV_BASE[params["with_origin_country"]]
            ids = [base + 1, base + 2] if "with_keywords" not in params else [base + 1]
        return {"page": 1, "total_pages": 1, "results": [{"id": i, "popularity": 90 - (i % 40), "vote_average": 8, "vote_count": 900} for i in ids]}
    parts = path.strip("/").split("/")
    if parts[0] == "movie":
        i = int(parts[1])
        lang = next((l for l, b in LANG_MOVIES.items() if b < i <= b + 3), "ja")
        genres = [{"id": 16, "name": "Animation"}] if i in ANIME_MOVIES else (
            [{"id": 18, "name": "Drama"}, {"id": 10749, "name": "Romance"}] if i % 10 == 1 else
            [{"id": 28, "name": "Action"}] if i % 10 == 2 else [{"id": 53, "name": "Thriller"}, {"id": 36, "name": "History"}])
        return {"id": i, "title": f"Test Movie {i}", "original_title": f"Test Movie {i}", "overview": "Fixture overview.",
                "release_date": "2025-03-10", "vote_average": 7.5, "vote_count": 500, "popularity": 50, "poster_path": f"/p{i}.jpg",
                "backdrop_path": f"/b{i}.jpg", "runtime": 110, "genres": genres, "production_countries": [{"iso_3166_1": "KR"}],
                "original_language": "ja" if i in ANIME_MOVIES else lang,
                "credits": {"cast": [{"name": "Actor One", "character": "Lead", "profile_path": "/a.jpg"}],
                            "crew": [{"job": "Director", "name": "Director One"}]},
                "videos": {"results": [{"site": "YouTube", "type": "Trailer", "key": f"yt{i}", "official": True}]},
                "similar": {"results": [{"id": i + 1}]}}
    if parts[0] == "tv" and len(parts) == 2:
        i = int(parts[1])
        cc = next((c for c, b in TV_BASE.items() if b < i <= b + 2), "JP")
        anime = i in ANIME_TV
        genres = [{"id": 16, "name": "Animation"}] if anime else [{"id": 18, "name": "Drama"}]
        return {"id": i, "name": f"Test Series {i}", "original_name": f"Test Series {i}", "overview": "Fixture series overview.",
                "first_air_date": "2025-01-05", "vote_average": 8.1, "vote_count": 900, "popularity": 80, "poster_path": f"/p{i}.jpg",
                "backdrop_path": f"/b{i}.jpg", "episode_run_time": [60], "number_of_seasons": 2, "number_of_episodes": 4,
                "status": "Returning Series", "genres": genres, "origin_country": ["JP" if anime else cc],
                "original_language": "ja" if anime else {"KR": "ko", "CN": "zh", "TW": "zh", "HK": "cn", "JP": "ja", "TH": "th"}[cc],
                "created_by": [{"name": "Creator One"}],
                "seasons": [{"id": i * 10 + 1, "season_number": 1, "name": "Season 1", "episode_count": 2, "air_date": "2025-01-05"},
                            {"id": i * 10 + 2, "season_number": 2, "name": "Season 2", "episode_count": 2, "air_date": "2025-06-05"}],
                "credits": {"cast": [{"name": "Actor Two", "character": "Hero", "profile_path": None}]},
                "videos": {"results": []}, "similar": {"results": []}}
    if parts[0] == "tv" and parts[2] == "season":
        n = int(parts[3])
        return {"episodes": [{"episode_number": e, "name": f"Ep {e}", "overview": "x", "air_date": "2025-01-05", "runtime": 60, "still_path": None} for e in (1, 2)]}
    raise AssertionError(f"unexpected TMDB path {path}")


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = mock.patch.object(tmdb, "_request", side_effect=fake_tmdb)
        cls.patch.start()
        app_module.prepare_database()
        cls.client = app_module.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()

    def call(self, method, url, token=None, **kw):
        headers = kw.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return getattr(self.client, method)(url, headers=headers, **kw)

    def register(self, name, email, password="Passw0rd!x"):
        from utils import ratelimit
        ratelimit._hits.clear()  # tests register many users from one fake IP
        r = self.call("post", "/api/auth/register", json={"username": name, "email": email, "password": password})
        return r


class FullFlow(Base):
    def test_01_sync_populates_catalogue(self):
        syncer.start_sync("cli", background=False)
        log = syncer.history(1)[0]
        self.assertEqual(log["status"], "success", log)
        self.assertGreater(log["titles_added"], 20)
        movies = db.one("SELECT COUNT(*) AS c FROM movies")["c"]
        series = db.one("SELECT COUNT(*) AS c FROM series")["c"]
        self.assertGreater(movies, 10)
        self.assertGreater(series, 10)
        # second run: nothing re-fetched, no duplicates created
        syncer.start_sync("cli", background=False)
        again = syncer.history(1)[0]
        self.assertEqual(again["titles_added"], 0)
        self.assertEqual(db.one("SELECT COUNT(*) AS c FROM movies")["c"], movies)
        # keyword-tagged titles got their tags
        hist = db.one("SELECT genres FROM series WHERE tmdb_id = 2101")
        self.assertIn("Historical", hist["genres"])
        self.assertIn("Romance", hist["genres"])

    def test_02_health_and_home(self):
        r = self.call("get", "/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["data"]["database"]["status"], "ok")
        home = self.call("get", "/api/home").json["data"]
        self.assertTrue(home["hero"])
        slugs = [row["slug"] for row in home["rows"]]
        for expected in ("trending", "k-drama", "c-drama", "anime", "historical", "romance", "thriller"):
            self.assertIn(expected, slugs)
        card = home["rows"][0]["items"][0]
        self.assertTrue({"id", "media_type", "title", "year", "rating", "poster"} <= set(card))
        self.assertTrue(card["poster"].startswith("https://image.tmdb.org/t/p/"))

    def test_03_listing_filters_search_details(self):
        r = self.call("get", "/api/movies?limit=5&sort=rating").json["data"]
        self.assertEqual(len(r["items"]), 5)
        kdrama = self.call("get", "/api/catalog?category=k-drama").json["data"]
        self.assertTrue(kdrama["items"])
        self.assertTrue(all(i["media_type"] == "series" for i in kdrama["items"]))
        narrowed = self.call("get", "/api/catalog?category=k-drama&genre=Romance").json["data"]
        self.assertLessEqual(narrowed["total"], kdrama["total"])
        s = self.call("get", "/api/movies/search?q=test movie 1101").json["data"]
        self.assertEqual([i["title"] for i in s["items"]], ["Test Movie 1101"])
        self.assertEqual(self.call("get", "/api/movies/search?q=a").status_code, 422)
        mid = db.one("SELECT id FROM movies WHERE tmdb_id = 1101")["id"]
        d = self.call("get", f"/api/movies/{mid}").json["data"]
        self.assertEqual(d["directors"], ["Director One"])
        self.assertEqual(d["trailer"]["key"], "yt1101")
        self.assertEqual(d["cast"][0]["name"], "Actor One")
        self.assertFalse(d["playable"])
        sid = db.one("SELECT id FROM series WHERE tmdb_id = 2101")["id"]
        sd = self.call("get", f"/api/series/{sid}").json["data"]
        self.assertEqual(len(sd["seasons"]), 2)
        eps = self.call("get", f"/api/series/{sid}/seasons/1").json["data"]["episodes"]
        self.assertEqual(len(eps), 2)
        self.assertEqual(self.call("get", "/api/movies/999999").status_code, 404)
        self.assertEqual(self.call("get", "/api/catalog?sort=bogus").status_code, 422)

    def test_04_auth_watchlist_history_profile(self):
        r = self.register("setemi", "setemi@example.com")
        self.assertEqual(r.status_code, 201, r.json)
        token = r.json["data"]["token"]
        self.assertEqual(self.register("setemi", "other@example.com").status_code, 409)
        self.assertEqual(self.register("weak", "weak@example.com", "12345678").status_code, 422)
        bad = self.call("post", "/api/auth/login", json={"identifier": "setemi", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)
        good = self.call("post", "/api/auth/login", json={"identifier": "SETEMI@example.com", "password": "Passw0rd!x"})
        self.assertEqual(good.status_code, 200)
        self.assertEqual(self.call("get", "/api/users/profile").status_code, 401)
        prof = self.call("get", "/api/users/profile", token).json["data"]
        self.assertEqual(prof["user"]["username"], "setemi")
        self.assertEqual(prof["user"]["subscription"]["tier"], "free")
        self.assertNotIn("password_hash", json.dumps(prof))

        mid = db.one("SELECT id FROM movies WHERE tmdb_id = 1101")["id"]
        add = self.call("post", "/api/watchlist", token, json={"media_type": "movie", "media_id": mid})
        self.assertEqual(add.status_code, 201)
        wid = add.json["data"]["watchlist_id"]
        again = self.call("post", "/api/watchlist", token, json={"media_type": "movie", "media_id": mid})
        self.assertEqual(again.json["data"]["watchlist_id"], wid)  # no duplicate rows
        self.assertEqual(self.call("get", "/api/watchlist", token).json["data"]["total"], 1)
        self.assertEqual(self.call("get", f"/api/movies/{mid}", token).json["data"]["watchlist_id"], wid)
        self.assertEqual(self.call("post", "/api/watchlist", token, json={"media_type": "movie", "media_id": 99999}).status_code, 404)
        self.assertEqual(self.call("delete", f"/api/watchlist/{wid}", token).status_code, 200)
        self.assertEqual(self.call("delete", f"/api/watchlist/{wid}", token).status_code, 404)

        save = self.call("post", "/api/history", token, json={"media_type": "movie", "media_id": mid, "position": 600, "duration": 6000})
        self.assertEqual(save.status_code, 200)
        cont = self.call("get", "/api/history?continue=1", token).json["data"]["items"]
        self.assertEqual(cont[0]["position"], 600)
        pos = self.call("get", f"/api/history/position?media_type=movie&media_id={mid}", token).json["data"]
        self.assertEqual(pos["position"], 600)
        self.call("post", "/api/history", token, json={"media_type": "movie", "media_id": mid, "position": 5900, "duration": 6000})
        self.assertEqual(self.call("get", "/api/history?continue=1", token).json["data"]["items"], [])  # finished

        # preferences + premium gating
        self.assertEqual(self.call("put", "/api/users/preferences", token, json={"favorite_genres": ["Romance", "Drama"]}).status_code, 200)
        self.assertEqual(self.call("put", "/api/users/preferences", token, json={"accent_theme": "rose"}).status_code, 403)
        self.assertEqual(self.call("put", "/api/users/preferences", token, json={"default_quality": "1080p"}).status_code, 403)
        rec = self.call("get", "/api/recommendations", token).json["data"]
        self.assertTrue(rec["personalized"])
        self.assertEqual(rec["tier"], "free")
        avatar = "data:image/png;base64,iVBORw0KGgo="
        self.assertEqual(self.call("put", "/api/users/profile", token, json={"avatar": avatar}).status_code, 200)
        self.assertEqual(self.call("put", "/api/users/profile", token, json={"avatar": "http://evil"}).status_code, 422)

        # logout invalidates the token everywhere
        self.assertEqual(self.call("post", "/api/auth/logout", token).status_code, 200)
        self.assertEqual(self.call("get", "/api/users/profile", token).status_code, 401)

    def test_05_password_reset(self):
        self.register("resetme", "reset@example.com")
        r = self.call("post", "/api/auth/forgot", json={"email": "reset@example.com"})
        link = r.json["data"]["dev_reset_url"]
        token = link.split("token=")[1]
        self.assertEqual(self.call("post", "/api/auth/reset", json={"token": "nope", "password": "Newpass123"}).status_code, 400)
        self.assertEqual(self.call("post", "/api/auth/reset", json={"token": token, "password": "Newpass123"}).status_code, 200)
        self.assertEqual(self.call("post", "/api/auth/reset", json={"token": token, "password": "Another123"}).status_code, 400)  # single use
        ok = self.call("post", "/api/auth/login", json={"identifier": "resetme", "password": "Newpass123"})
        self.assertEqual(ok.status_code, 200)
        # unknown emails get the same answer (no account enumeration)
        self.assertEqual(self.call("post", "/api/auth/forgot", json={"email": "nobody@example.com"}).status_code, 200)

    def test_06_premium_payment_flow(self):
        token = self.register("payer", "payer@example.com").json["data"]["token"]
        plans = self.call("get", "/api/premium/plans").json["data"]
        self.assertEqual({p["id"] for p in plans["plans"]}, {"monthly", "yearly"})
        with mock.patch("services.paystack.initialize", return_value={"authorization_url": "https://paystack.test/pay"}) as init:
            r = self.call("post", "/api/premium/checkout", token, json={"plan": "monthly"})
        self.assertEqual(r.status_code, 200, r.json)
        ref = r.json["data"]["reference"]
        self.assertEqual(init.call_args[0][1], 2500 * 100)
        # not paid yet -> stays free
        with mock.patch("services.paystack.verify", return_value={"status": "abandoned", "amount": 250000, "currency": "NGN", "channel": None}):
            v1 = self.call("get", f"/api/premium/verify?reference={ref}", token).json["data"]
        self.assertEqual(v1["membership"]["tier"], "free")
        # wrong amount -> rejected
        with mock.patch("services.paystack.verify", return_value={"status": "success", "amount": 100, "currency": "NGN", "channel": "card"}):
            v2 = self.call("get", f"/api/premium/verify?reference={ref}", token).json["data"]
        self.assertEqual(v2["membership"]["tier"], "free")
        # fresh payment, verified OK -> premium, and replaying doesn't stack
        with mock.patch("services.paystack.initialize", return_value={"authorization_url": "https://paystack.test/pay"}):
            ref = self.call("post", "/api/premium/checkout", token, json={"plan": "monthly"}).json["data"]["reference"]
        good = {"status": "success", "amount": 250000, "currency": "NGN", "channel": "card"}
        with mock.patch("services.paystack.verify", return_value=good):
            first = self.call("get", f"/api/premium/verify?reference={ref}", token).json["data"]
            self.call("get", f"/api/premium/verify?reference={ref}", token)
        self.assertEqual(first["membership"]["tier"], "premium")
        self.assertEqual(db.one("SELECT COUNT(*) AS c FROM subscriptions WHERE status = 'active' AND user_id = (SELECT id FROM profiles WHERE username = 'payer')")["c"], 1)
        # webhook: bad signature refused, good one accepted
        body = json.dumps({"event": "charge.success", "data": {"reference": ref}}).encode()
        self.assertEqual(self.call("post", "/api/premium/webhook", data=body, headers={"x-paystack-signature": "bad"}).status_code, 401)
        sig = hmac.new(b"sk_test_fixture", body, hashlib.sha512).hexdigest()
        self.assertEqual(self.call("post", "/api/premium/webhook", data=body, headers={"x-paystack-signature": sig, "Content-Type": "application/json"}).status_code, 200)
        # premium unlocks themes and 1080p preference
        self.assertEqual(self.call("put", "/api/users/preferences", token, json={"accent_theme": "rose", "default_quality": "1080p"}).status_code, 200)
        hist = self.call("get", "/api/premium/payments", token).json["data"]["items"]
        self.assertEqual([p["status"] for p in hist].count("success"), 1)
        # someone else's reference cannot be verified
        other = self.register("snoop", "snoop@example.com").json["data"]["token"]
        self.assertEqual(self.call("get", f"/api/premium/verify?reference={ref}", other).status_code, 404)

    def test_07_provider_and_playback(self):
        mid = db.one("SELECT id FROM movies WHERE tmdb_id = 1102")["id"]
        sid = db.one("SELECT id FROM series WHERE tmdb_id = 2102")["id"]
        self.call("get", f"/api/series/{sid}/seasons/1")
        ep = db.one("SELECT id FROM episodes WHERE series_id = ? ORDER BY id", [sid])["id"]

        # No provider answer -> honest "unavailable"
        class Resp:
            status_code = 200
            def __init__(self, payload): self._p = payload
            def json(self): return self._p

        with mock.patch("services.providers.moviebox.requests.get", return_value=Resp({"sources": []})):
            w = self.call("get", f"/api/watch/movie/{mid}").json["data"]
        self.assertFalse(w["available"])

        # Provider returns an authorised source (+ one malformed one that must be ignored)
        payload = {"sources": [
            {"url": "https://cdn.example/m.m3u8", "type": "hls", "quality": "720p", "language": "ko",
             "subtitles": [{"lang": "en", "label": "English", "url": "https://cdn.example/en.vtt"}]},
            {"url": "http://insecure.example/x.mp4", "type": "mp4"},
            {"url": "https://cdn.example/hd.m3u8", "type": "hls", "quality": "1080p"}]}
        from utils.cache import cache
        cache.clear("nosrc")
        with mock.patch("services.providers.moviebox.requests.get", return_value=Resp(payload)):
            w = self.call("get", f"/api/watch/movie/{mid}").json["data"]
        self.assertTrue(w["available"])
        self.assertEqual(len(w["sources"]), 1)        # 1080p hidden from free users
        self.assertEqual(w["locked_count"], 1)
        self.assertEqual(w["sources"][0]["subtitles"][0]["lang"], "en")
        self.assertTrue(self.call("get", f"/api/movies/{mid}").json["data"]["playable"])

        # series: episode navigation
        w2 = self.call("get", f"/api/watch/series/{sid}?episode={ep}").json["data"]
        self.assertEqual(w2["episode"]["episode_number"], 1)
        self.assertEqual(w2["next_episode"]["episode_number"], 2)
        self.assertFalse(w2["available"])

    def test_08_admin(self):
        admin = self.register("boss", "boss@example.com").json["data"]["token"]
        user = self.register("plain", "plain@example.com").json["data"]["token"]
        self.assertEqual(self.call("get", "/api/admin/stats", user).status_code, 403)
        self.assertEqual(self.call("get", "/api/admin/stats").status_code, 401)
        st = self.call("get", "/api/admin/stats", admin).json["data"]
        self.assertGreater(st["totals"]["movies"], 10)
        self.assertEqual(st["totals"]["users"], db.one("SELECT COUNT(*) AS c FROM profiles")["c"])
        self.assertEqual(st["health"]["database"]["status"], "ok")
        self.assertGreaterEqual(st["totals"]["premium_subscribers"], 1)
        self.assertEqual(self.call("get", "/api/admin/sync", admin).json["data"]["logs"][0]["status"], "success")

        # add / edit / delete a title, add a source
        add = self.call("post", "/api/admin/titles", admin, json={"media_type": "movie", "title": "Hand Added", "release_date": "2024-02-02", "genres": "Drama, Romance", "countries": ["KR"], "original_language": "ko"})
        self.assertEqual(add.status_code, 201, add.json)
        tid = add.json["data"]["id"]
        self.assertEqual(self.call("put", f"/api/admin/titles/movie/{tid}", admin, json={"title": "Hand Added 2", "rating": 8}).status_code, 200)
        self.assertEqual(self.call("post", f"/api/admin/titles/movie/{tid}/sources", admin, json={"url": "http://bad", "type": "hls"}).status_code, 422)
        src = self.call("post", f"/api/admin/titles/movie/{tid}/sources", admin, json={"url": "https://cdn.example/a.mp4", "type": "mp4", "quality": "720p"})
        self.assertEqual(src.status_code, 201)
        self.assertTrue(self.call("get", f"/api/movies/{tid}").json["data"]["playable"])
        self.assertEqual(self.call("get", f"/api/admin/titles?type=movie&q=hand", admin).json["data"]["total"], 1)
        self.assertEqual(self.call("delete", f"/api/admin/titles/movie/{tid}", admin).status_code, 200)
        self.assertEqual(self.call("get", f"/api/movies/{tid}").status_code, 404)
        self.assertEqual(db.one("SELECT COUNT(*) AS c FROM provider_sources WHERE media_type='movie' AND media_id=?", [tid])["c"], 0)

        # import from TMDB by id
        imp = self.call("post", "/api/admin/titles/import", admin, json={"media_type": "movie", "tmdb_id": 1101})
        self.assertEqual(imp.json["data"]["outcome"], "updated")

        # categories CRUD drives the homepage
        c = self.call("post", "/api/admin/categories", admin, json={"slug": "thai-hits", "name": "Thai Hits", "media_type": "all", "country": "TH", "position": 50})
        self.assertEqual(c.status_code, 201, c.json)
        self.assertEqual(self.call("post", "/api/admin/categories", admin, json={"slug": "thai-hits", "name": "x"}).status_code, 409)
        from utils.cache import cache
        cache.clear("home")
        self.assertIn("thai-hits", [r["slug"] for r in self.call("get", "/api/home").json["data"]["rows"]])
        cid = c.json["data"]["id"]
        self.assertEqual(self.call("delete", f"/api/admin/categories/{cid}", admin).status_code, 200)

        # users and subscriptions
        users = self.call("get", "/api/admin/users", admin).json["data"]
        plain_id = next(u["id"] for u in users["items"] if u["username"] == "plain")
        admin_id = next(u["id"] for u in users["items"] if u["username"] == "boss")
        self.assertEqual(self.call("put", f"/api/admin/users/{admin_id}", admin, json={"role": "user"}).status_code, 400)
        self.assertEqual(self.call("post", "/api/admin/subscriptions", admin, json={"user_id": plain_id, "plan": "monthly", "days": 10}).status_code, 201)
        self.assertEqual(self.call("get", "/api/premium/status", user).json["data"]["membership"]["tier"], "premium")
        subs = self.call("get", "/api/admin/subscriptions", admin).json["data"]["items"]
        sid = next(s["id"] for s in subs if s["user_id"] == plain_id)
        self.assertEqual(self.call("post", f"/api/admin/subscriptions/{sid}/cancel", admin).status_code, 200)
        self.assertEqual(self.call("get", "/api/premium/status", user).json["data"]["membership"]["tier"], "free")
        self.assertEqual(self.call("put", f"/api/admin/users/{plain_id}", admin, json={"is_active": False}).status_code, 200)
        self.assertEqual(self.call("get", "/api/users/profile", user).status_code, 401)  # disabled = signed out

    def test_09_sync_endpoint_and_misc(self):
        admin = self.call("post", "/api/auth/login", json={"identifier": "boss", "password": "Passw0rd!x"}).json["data"]["token"]
        r = self.call("post", "/api/admin/sync", admin, json={})
        self.assertEqual(r.status_code, 202)
        import time
        for _ in range(50):
            if not self.call("get", "/api/admin/sync", admin).json["data"]["running"]:
                break
            time.sleep(0.2)
        self.assertFalse(self.call("get", "/api/admin/sync", admin).json["data"]["running"])
        self.assertEqual(self.call("get", "/api/nope").status_code, 404)
        self.assertEqual(self.call("get", "/api/nope").json["success"], False)
        cors = self.call("options", "/api/movies", headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "GET"})
        self.assertEqual(cors.headers.get("Access-Control-Allow-Origin"), "http://localhost:8000")
        self.assertIsNone(self.call("get", "/api/movies", headers={"Origin": "http://evil.example"}).headers.get("Access-Control-Allow-Origin"))


if __name__ == "__main__":
    unittest.main()
