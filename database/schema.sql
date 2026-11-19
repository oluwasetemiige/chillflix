-- =====================================================================
-- CHILLFLIX database schema (PostgreSQL / Supabase)
--
-- Supabase:  open SQL Editor -> paste this whole file -> Run.
-- Postgres:  psql "$DATABASE_URL" -f database/schema.sql
-- Safe to run more than once (everything uses IF NOT EXISTS).
-- =====================================================================

-- ---------- users ----------------------------------------------------
CREATE TABLE IF NOT EXISTS profiles (
  id             BIGSERIAL PRIMARY KEY,
  username       TEXT NOT NULL,
  email          TEXT NOT NULL,
  password_hash  TEXT NOT NULL,
  avatar_url     TEXT,
  role           TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  token_version  INTEGER NOT NULL DEFAULT 0,      -- bump to sign a user out everywhere
  is_active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_login_at  TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_email    ON profiles (LOWER(email));
CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_username ON profiles (LOWER(username));

CREATE TABLE IF NOT EXISTS password_resets (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  token_hash  TEXT NOT NULL UNIQUE,               -- sha256 of the emailed token
  expires_at  TIMESTAMPTZ NOT NULL,
  used_at     TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_preferences (
  user_id            BIGINT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
  favorite_genres    TEXT NOT NULL DEFAULT '[]',  -- JSON list of genre names
  autoplay_next      BOOLEAN NOT NULL DEFAULT TRUE,
  subtitle_language  TEXT NOT NULL DEFAULT 'en',
  default_quality    TEXT NOT NULL DEFAULT 'auto',
  accent_theme       TEXT NOT NULL DEFAULT 'violet',
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------- catalogue --------------------------------------------------
-- Each row of `categories` describes one homepage row / browse filter.
CREATE TABLE IF NOT EXISTS categories (
  id            BIGSERIAL PRIMARY KEY,
  slug          TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL,
  media_type    TEXT NOT NULL DEFAULT 'all' CHECK (media_type IN ('movie', 'series', 'all')),
  country       TEXT,            -- e.g. 'KR' or 'CN,TW,HK' (comma separated = any of)
  language      TEXT,            -- e.g. 'ja'
  genre         TEXT,            -- e.g. 'Romance' or 'Action,Adventure' (any of)
  exclude_genre TEXT,
  sort          TEXT NOT NULL DEFAULT 'popularity' CHECK (sort IN ('popularity', 'rating', 'recent', 'trending')),
  position      INTEGER NOT NULL DEFAULT 0,
  show_on_home  BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS movies (
  id               BIGSERIAL PRIMARY KEY,
  tmdb_id          BIGINT UNIQUE,
  title            TEXT NOT NULL,
  original_title   TEXT,
  overview         TEXT,
  release_date     DATE,
  year             INTEGER,
  rating           DOUBLE PRECISION NOT NULL DEFAULT 0,
  vote_count       INTEGER NOT NULL DEFAULT 0,
  popularity       DOUBLE PRECISION NOT NULL DEFAULT 0,
  poster_path      TEXT,
  backdrop_path    TEXT,
  runtime          INTEGER,
  genres           TEXT NOT NULL DEFAULT '[]',    -- JSON list of names
  countries        TEXT NOT NULL DEFAULT '[]',    -- JSON list of ISO codes
  original_language TEXT,
  cast_members     TEXT NOT NULL DEFAULT '[]',    -- JSON list
  directors        TEXT NOT NULL DEFAULT '[]',    -- JSON list of names
  trailer_key      TEXT,                          -- YouTube video key
  similar_tmdb_ids TEXT NOT NULL DEFAULT '[]',
  trending_rank    INTEGER,
  source           TEXT NOT NULL DEFAULT 'tmdb',  -- 'tmdb' or 'manual'
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_synced_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_movies_popularity ON movies (popularity DESC);
CREATE INDEX IF NOT EXISTS idx_movies_rating     ON movies (rating DESC);
CREATE INDEX IF NOT EXISTS idx_movies_release    ON movies (release_date DESC);
CREATE INDEX IF NOT EXISTS idx_movies_language   ON movies (original_language);
CREATE INDEX IF NOT EXISTS idx_movies_trending   ON movies (trending_rank);
CREATE INDEX IF NOT EXISTS idx_movies_year       ON movies (year);

CREATE TABLE IF NOT EXISTS series (
  id                 BIGSERIAL PRIMARY KEY,
  tmdb_id            BIGINT UNIQUE,
  title              TEXT NOT NULL,
  original_title     TEXT,
  overview           TEXT,
  release_date       DATE,                        -- first air date
  year               INTEGER,
  rating             DOUBLE PRECISION NOT NULL DEFAULT 0,
  vote_count         INTEGER NOT NULL DEFAULT 0,
  popularity         DOUBLE PRECISION NOT NULL DEFAULT 0,
  poster_path        TEXT,
  backdrop_path      TEXT,
  episode_runtime    INTEGER,
  number_of_seasons  INTEGER NOT NULL DEFAULT 0,
  number_of_episodes INTEGER NOT NULL DEFAULT 0,
  status             TEXT,
  genres             TEXT NOT NULL DEFAULT '[]',
  countries          TEXT NOT NULL DEFAULT '[]',
  original_language  TEXT,
  cast_members       TEXT NOT NULL DEFAULT '[]',
  directors          TEXT NOT NULL DEFAULT '[]',  -- creators
  trailer_key        TEXT,
  similar_tmdb_ids   TEXT NOT NULL DEFAULT '[]',
  trending_rank      INTEGER,
  source             TEXT NOT NULL DEFAULT 'tmdb',
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_synced_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_series_popularity ON series (popularity DESC);
CREATE INDEX IF NOT EXISTS idx_series_rating     ON series (rating DESC);
CREATE INDEX IF NOT EXISTS idx_series_release    ON series (release_date DESC);
CREATE INDEX IF NOT EXISTS idx_series_language   ON series (original_language);
CREATE INDEX IF NOT EXISTS idx_series_trending   ON series (trending_rank);
CREATE INDEX IF NOT EXISTS idx_series_year       ON series (year);

CREATE TABLE IF NOT EXISTS seasons (
  id            BIGSERIAL PRIMARY KEY,
  series_id     BIGINT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
  tmdb_id       BIGINT,
  season_number INTEGER NOT NULL,
  name          TEXT,
  overview      TEXT,
  air_date      DATE,
  episode_count INTEGER NOT NULL DEFAULT 0,
  poster_path   TEXT,
  UNIQUE (series_id, season_number)
);
CREATE INDEX IF NOT EXISTS idx_seasons_series ON seasons (series_id);

CREATE TABLE IF NOT EXISTS episodes (
  id             BIGSERIAL PRIMARY KEY,
  season_id      BIGINT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
  series_id      BIGINT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
  episode_number INTEGER NOT NULL,
  name           TEXT,
  overview       TEXT,
  air_date       DATE,
  runtime        INTEGER,
  still_path     TEXT,
  UNIQUE (season_id, episode_number)
);
CREATE INDEX IF NOT EXISTS idx_episodes_series ON episodes (series_id);

-- Playback sources. NEVER fabricated: they come from an authorised provider
-- or are added by an admin. media_type is 'movie' or 'series';
-- episode_id is 0 for movies / whole-title sources.
CREATE TABLE IF NOT EXISTS provider_sources (
  id              BIGSERIAL PRIMARY KEY,
  provider        TEXT NOT NULL,
  media_type      TEXT NOT NULL CHECK (media_type IN ('movie', 'series')),
  media_id        BIGINT NOT NULL,
  episode_id      BIGINT NOT NULL DEFAULT 0,
  source_url      TEXT NOT NULL,
  source_type     TEXT NOT NULL CHECK (source_type IN ('hls', 'mp4')),
  quality         TEXT NOT NULL DEFAULT 'auto',
  language        TEXT NOT NULL DEFAULT 'original',
  subtitles       TEXT NOT NULL DEFAULT '[]',     -- JSON [{lang,label,url}]
  premium_only    BOOLEAN NOT NULL DEFAULT FALSE,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  last_checked_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (provider, media_type, media_id, episode_id, source_url)
);
CREATE INDEX IF NOT EXISTS idx_sources_media ON provider_sources (media_type, media_id, episode_id);

CREATE TABLE IF NOT EXISTS synchronization_logs (
  id                BIGSERIAL PRIMARY KEY,
  trigger_type      TEXT NOT NULL DEFAULT 'manual',   -- manual | scheduled | cli
  status            TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'partial', 'failed')),
  started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at       TIMESTAMPTZ,
  titles_added      INTEGER NOT NULL DEFAULT 0,
  titles_updated    INTEGER NOT NULL DEFAULT 0,
  duplicates_skipped INTEGER NOT NULL DEFAULT 0,
  errors            INTEGER NOT NULL DEFAULT 0,
  details           TEXT,                              -- JSON summary / error messages
  triggered_by      BIGINT REFERENCES profiles(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_sync_started ON synchronization_logs (started_at DESC);

-- ---------- user activity ---------------------------------------------
CREATE TABLE IF NOT EXISTS watchlist (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'series')),
  media_id   BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, media_type, media_id)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS watch_history (
  id               BIGSERIAL PRIMARY KEY,
  user_id          BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  media_type       TEXT NOT NULL CHECK (media_type IN ('movie', 'series')),
  media_id         BIGINT NOT NULL,
  episode_id       BIGINT NOT NULL DEFAULT 0,        -- 0 = no episode (movies)
  position_seconds INTEGER NOT NULL DEFAULT 0,
  duration_seconds INTEGER NOT NULL DEFAULT 0,
  completed        BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, media_type, media_id, episode_id)
);
CREATE INDEX IF NOT EXISTS idx_history_user ON watch_history (user_id, updated_at DESC);

-- ---------- premium -----------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  reference  TEXT NOT NULL UNIQUE,
  provider   TEXT NOT NULL DEFAULT 'paystack',
  plan       TEXT NOT NULL,
  amount     INTEGER NOT NULL,                       -- minor units (kobo)
  currency   TEXT NOT NULL DEFAULT 'NGN',
  status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed')),
  channel    TEXT,
  paid_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS subscriptions (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  plan       TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled')),
  starts_at  TIMESTAMPTZ NOT NULL,
  ends_at    TIMESTAMPTZ NOT NULL,
  payment_id BIGINT REFERENCES payments(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions (user_id, status, ends_at);

-- ===== SUPABASE / ACCESS CONTROL (ignored by the local SQLite dev mode) =====
-- The Flask backend is the ONLY thing that talks to this database, using the
-- connection string in DATABASE_URL (a role that bypasses Row Level Security).
-- Row Level Security is switched on for every table WITHOUT any policy, so the
-- public Supabase REST API (anon / authenticated keys) can read or write nothing.
ALTER TABLE profiles             ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_resets      ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences     ENABLE ROW LEVEL SECURITY;
ALTER TABLE categories           ENABLE ROW LEVEL SECURITY;
ALTER TABLE movies               ENABLE ROW LEVEL SECURITY;
ALTER TABLE series               ENABLE ROW LEVEL SECURITY;
ALTER TABLE seasons              ENABLE ROW LEVEL SECURITY;
ALTER TABLE episodes             ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_sources     ENABLE ROW LEVEL SECURITY;
ALTER TABLE synchronization_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist            ENABLE ROW LEVEL SECURITY;
ALTER TABLE watch_history        ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments             ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions        ENABLE ROW LEVEL SECURITY;

-- Belt and braces: remove direct table access from Supabase's public roles.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated';
  END IF;
END
$$;
