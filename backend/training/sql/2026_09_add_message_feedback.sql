-- Adds per-message helpfulness feedback (thumbs up/down) from the student,
-- so GAIDA response quality can be audited on a per-reply basis rather than
-- only via the end-of-session wellbeing rating.
-- Run this in the Supabase SQL editor. Safe to re-run.

CREATE TABLE IF NOT EXISTS message_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id text NOT NULL,
    message_index integer NOT NULL DEFAULT 0,
    message_text text,
    rating text NOT NULL CHECK (rating IN ('helpful', 'not_helpful')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_message_feedback_session_id ON message_feedback (session_id);