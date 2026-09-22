-- Adds server-side escalation tracking to counselor_alerts so an
-- unacknowledged Crisis/High alert is re-notified by email and marked
-- overdue/needs-supervisor by the background escalation monitor — and so the
-- dashboard can trust that state after a backend restart.
-- Run this in the Supabase SQL editor. Safe to re-run (idempotent).

ALTER TABLE counselor_alerts ADD COLUMN IF NOT EXISTS escalation_level text NOT NULL DEFAULT 'normal';
ALTER TABLE counselor_alerts ADD COLUMN IF NOT EXISTS needs_supervisor boolean NOT NULL DEFAULT false;
ALTER TABLE counselor_alerts ADD COLUMN IF NOT EXISTS age_minutes integer;

CREATE INDEX IF NOT EXISTS idx_counselor_alerts_pending
    ON counselor_alerts (status) WHERE status = 'pending';