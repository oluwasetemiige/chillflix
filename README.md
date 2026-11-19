# CHILLFLIX

**Your World of Asian Entertainment.** A streaming-catalogue website for Korean dramas, Chinese dramas, Japanese movies, anime and more.

- **Frontend:** plain HTML, CSS and JavaScript (no build step) in `frontend/`
- **Backend:** Python Flask REST API in `backend/`
- **Database:** PostgreSQL / Supabase in production, SQLite on your laptop (automatic) in `database/schema.sql`
- **Movie data:** TMDB. **Playback:** only authorised sources, never invented links
- **Payments:** Paystack, verified on the server before Premium is granted

```
CHILLFLIX/
├── frontend/   HTML pages, css/, js/, assets/   (js/config.js holds API_BASE)
├── backend/    app.py, config.py, routes/, services/, utils/, tests/
├── database/   schema.sql, rls.sql (Supabase only)
└── README.md
```

---

## 1. Run it on your computer

You need Python 3.10+.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then open .env and fill it in (see section 3)
python app.py                      # API on http://127.0.0.1:5000
```

Open a second terminal for the website:

```bash
cd frontend
python -m http.server 8000         # site on http://127.0.0.1:8000
```

Check the API: open http://127.0.0.1:5000/api/health. You should see `"status": "ok"` or `"degraded"` (degraded just means TMDB or a provider is not set up yet).

With no `DATABASE_URL`, a local file `backend/chillflix.db` (SQLite) is created for you. Nothing else to install.

### Fill the catalogue

1. Get a free TMDB key at https://www.themoviedb.org/settings/api and put it in `backend/.env` as `TMDB_API_KEY`.
2. Put your own email in `ADMIN_EMAILS`, restart the API, then register on the site with that email. You become an admin.
   (Or run `python manage.py create-admin you@example.com yourname 'a-strong-password'`.)
3. Open **Admin → Synchronization → Sync catalogue now**. Titles, posters, cast, trailers and similar titles are imported. Running it again updates metadata and skips duplicates.
   (Or run `python manage.py sync` in the terminal.)

Until you sync, the home page shows an empty-catalogue message. That is intentional: CHILLFLIX does not ship fake movies.

---

## 2. Streaming sources (read this)

CHILLFLIX **never creates playback links**. A title is playable only when an authorised source exists for it:

- **Manual:** Admin → Catalogue → **Sources**. Add an `https://` HLS (`.m3u8`) or MP4 link you are licensed to stream.
- **Provider adapter:** `backend/services/providers/moviebox.py`. MovieBox has no public API we can rely on, so the adapter only calls an endpoint you are authorised to use. Set `MOVIEBOX_API_BASE` and `MOVIEBOX_API_KEY` in `.env` and adjust `find_sources()` to match that service's real response. Leave them empty and the site simply runs on TMDB metadata.
- **Another provider later:** copy `moviebox.py`, change `health()` and `find_sources()`, register it in `providers/__init__.py`. Nothing else changes.

A title with no source shows **"Streaming source currently unavailable."** and the player is not drawn.

---

## 3. Environment variables (`backend/.env`)

| Variable | What it is |
|---|---|
| `APP_ENV` | `development` locally, `production` when deployed |
| `SECRET_KEY` | Long random string. `python -c "import secrets;print(secrets.token_hex(32))"` |
| `FRONTEND_URL` | Your website address (reset links, Paystack return page) |
| `CORS_ORIGINS` | Website addresses allowed to call the API, comma separated |
| `TRUST_PROXY` | `true` on Render/Railway/Fly so rate limits see real visitor IPs |
| `DATABASE_URL` | `postgresql://USER:PASSWORD@HOST:5432/postgres`. Empty = local SQLite |
| `TMDB_API_KEY` | TMDB v3 key or v4 read token |
| `SYNC_PAGES`, `AUTO_SYNC_HOURS` | How much to import, and optional automatic sync (0 = off) |
| `MOVIEBOX_API_BASE`, `MOVIEBOX_API_KEY` | Optional provider (section 2) |
| `PAYSTACK_SECRET_KEY` | Paystack secret key (`sk_test_...` while testing) |
| `PAYMENT_CURRENCY`, `PLAN_MONTHLY_PRICE`, `PLAN_YEARLY_PRICE` | Prices in whole currency units |
| `ADMIN_EMAILS` | Emails that become admins when they register |
| `SMTP_*`, `MAIL_FROM` | Email for password recovery. Without SMTP, development mode shows the reset link on screen |

Never commit `.env`.

---

## 4. Database

**Local:** nothing to do.

**Supabase or PostgreSQL:**
1. Create the project/database.
2. Run `database/schema.sql` in the SQL editor (or `psql "$DATABASE_URL" -f database/schema.sql`). The API also creates missing tables on start.
3. **Supabase only:** run `database/rls.sql`. It turns on Row Level Security for every table with no public policies. The browser never talks to the database. Only the Flask API does, through `DATABASE_URL`, so Supabase's public REST keys cannot read passwords or payments.
4. Use the **connection string** (Project Settings → Database) as `DATABASE_URL`. No Supabase key goes in the frontend.

Tables: profiles, categories, movies, series, seasons, episodes, watch_history, watchlist, subscriptions, payments, user_preferences, provider_sources, synchronization_logs, password_resets.

---

## 5. Deploy

### Backend (Render, Railway, Fly, PythonAnywhere... any Python host)

Render example:
- New **Web Service**, root directory `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --workers 1 --threads 4`
  (keep **one worker**: rate limits, caching and the optional auto-sync loop live in memory)
- Add the environment variables from section 3 (`APP_ENV=production`, `TRUST_PROXY=true`, `FRONTEND_URL`, `CORS_ORIGINS`, `DATABASE_URL`, ...)
- Free hosts reset local files, so use PostgreSQL/Supabase in production, not SQLite.

### Frontend (Vercel or Netlify)

1. Open `frontend/js/config.js` and change the one line:
   ```js
   export const API_BASE = "https://YOUR-BACKEND-URL/api";
   ```
   That is the only place a backend address lives. `js/api.js` imports it and every page talks to the backend through `api.js`.
2. Deploy the `frontend` folder as a static site (no build command, output directory = `frontend`).
3. Put the live site address into the backend's `FRONTEND_URL` and `CORS_ORIGINS`, then redeploy the backend.

### Paystack

1. In the Paystack dashboard, set the webhook URL to `https://YOUR-BACKEND-URL/api/premium/webhook`.
2. Add `PAYSTACK_SECRET_KEY`. Upgrades happen only after the server verifies the payment with Paystack (by return page and by webhook).
3. Test with `sk_test_...` keys first.

---

## 6. API reference

All responses look like `{"success": true, "data": ...}` or `{"success": false, "error": {"code", "message", "details"}}`.
Send the login token as `Authorization: Bearer <token>`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/health` | | Database, TMDB and provider health |
| GET | `/api/home` | | Hero carousel and all home rows |
| GET | `/api/movies`, `/api/series`, `/api/catalog` | | Listings. Query: `page, limit, sort, genre, category, country, language, year, q` |
| GET | `/api/movies/trending`, `/api/movies/popular` | | Ranked movie lists |
| GET | `/api/movies/search?q=` | | Search (2+ letters). Optional `type=movie\|series` |
| GET | `/api/movies/:id`, `/api/series/:id` | optional | Details, cast, trailer, similar titles |
| GET | `/api/series/:id/seasons/:n` | | Episodes of a season |
| GET | `/api/categories`, `/api/genres` | | Categories and genre names |
| GET | `/api/watch/:type/:id?episode=` | optional | Playable sources, next/previous episode |
| POST | `/api/auth/register`, `/login`, `/logout`, `/forgot`, `/reset` | | Accounts and password recovery |
| GET / PUT | `/api/users/profile` | yes | Profile (username, picture) |
| PUT | `/api/users/preferences` | yes | Genres, autoplay, subtitles, quality, theme |
| POST | `/api/users/password` | yes | Change password |
| GET / POST / DELETE | `/api/watchlist`, `/api/watchlist/:id` | yes | Saved titles |
| GET / POST | `/api/history` | yes | Watch history and saved position |
| GET | `/api/recommendations` | yes | Personalised rows (deeper for Premium) |
| GET | `/api/premium/plans` | | Plans and feature lists |
| GET | `/api/premium/status`, `/payments` | yes | Membership and payment history |
| POST | `/api/premium/checkout` | yes | Start a Paystack payment |
| GET | `/api/premium/verify?reference=` | yes | Server-side payment check |
| POST | `/api/premium/webhook` | signature | Paystack webhook |
| GET / POST | `/api/admin/sync` | admin | Sync history, start a sync |
| GET | `/api/admin/stats` | admin | Totals, revenue, health, recent users |
| * | `/api/admin/titles`, `/titles/import`, `/titles/:type/:id`, `/sources`, `/categories`, `/users`, `/subscriptions` | admin | Catalogue, categories, users, subscriptions |

Security in place: PBKDF2-SHA256 password hashing (600,000 rounds), signed tokens that are revoked on logout or password change, per-route and global rate limits, input validation, CORS allow-list, 1 MB request cap.

---

## 7. Tests

```bash
cd backend
python -m unittest tests.test_api -v
```

The tests run the whole API offline: sync, listings, search, auth, watchlist, history, password reset, payments, providers, admin. TMDB and Paystack are replaced by fixtures that exist only inside the test database.

---

## 8. Page map

`index` · `movies` · `series` · `kdrama` · `cdrama` · `anime` · `details` · `watch` · `search` · `watchlist` · `premium` · `profile` (dashboard) · `admin` · `login` · `register` · `forgot-password` · `reset-password`
