-- Persists counselor-takeover state on the sessions row so a backend
-- restart / fresh reload rehydrates the session as counselor-held instead of
-- silently flipping the conversation back to GAIDA/student on both dashboards.
-- load_session_from_db() reads these two columns (with a counselor_alerts
-- fallback for rows created before this migration).
-- Run this in the Supabase SQL editor. Safe to re-run (idempotent).

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS counselor_active boolean NOT NULL DEFAULT false;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS assigned_counselor_id text;

CREATE INDEX IF NOT EXISTS idx_sessions_counselor_active
    ON sessions (counselor_active) WHERE counselor_active = true;