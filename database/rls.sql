-- Supabase only. Run AFTER schema.sql.
--
-- How access control works in CHILLFLIX: the browser never talks to the database directly.
-- Only the Flask backend does, using the Postgres connection string (DATABASE_URL), which
-- connects as the owner role and is not affected by Row Level Security.
-- Turning RLS on with NO policies for the "anon" and "authenticated" roles means Supabase's
-- public REST API can read or write nothing, even though the anon key is public.

ALTER TABLE profiles             ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_resets      ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences     ENABLE ROW LEVEL SECURITY;
ALTER TABLE categories           ENABLE ROW LEVEL SECURITY;
ALTER TABLE movies               ENABLE ROW LEVEL SECURITY;
ALTER TABLE series               ENABLE ROW LEVEL SECURITY;
ALTER TABLE seasons              ENABLE ROW LEVEL SECURITY;
ALTER TABLE episodes             ENABLE ROW LEVEL SECURITY;
ALTER TABLE watch_history        ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist            ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments             ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_sources     ENABLE ROW LEVEL SECURITY;
ALTER TABLE synchronization_logs ENABLE ROW LEVEL SECURITY;

-- Intentionally no CREATE POLICY statements: deny-all for the public roles.
-- If you later query a table straight from the browser with the Supabase client,
-- add a policy for that table first, e.g. read-only catalogue:
--   CREATE POLICY "catalogue is public" ON movies FOR SELECT USING (true);
