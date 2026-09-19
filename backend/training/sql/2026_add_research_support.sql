-- Adds research-data-collection support to the existing schema, for both
-- identified (default) and anonymous (opt-in) student participation.
-- Safe to run multiple times (IF NOT EXISTS guards throughout).
-- Run this in the Supabase SQL editor before deploying the research.py router.

-- 1. Tag sessions as research vs. real counseling sessions, whether the
--    participant chose to be identified or anonymous, and capture the
--    self-reported demographics your experts asked for.
--    All nullable — a normal student/counselor session leaves these blank.
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS is_research boolean DEFAULT false,
    ADD COLUMN IF NOT EXISTS is_anonymous boolean DEFAULT false,
    ADD COLUMN IF NOT EXISTS participant_code text,
    ADD COLUMN IF NOT EXISTS year_level text,
    ADD COLUMN IF NOT EXISTS program text,
    ADD COLUMN IF NOT EXISTS gender text,
    ADD COLUMN IF NOT EXISTS region text;

-- participant_code: shown to anonymous participants so they have something
-- to reference later (to withdraw, or to resume as "the same" pseudonymous
-- person next time) without it identifying them to anyone else.
-- For identified sessions this stays null — sessions.student_id (already
-- existing) is the real student number in that case.

-- 2. GAD-7 responses, one row per administration, tied to a session_id the
--    same way `interactions` and `consents` already are.
CREATE TABLE IF NOT EXISTS gad7_responses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id text NOT NULL,
    q1 smallint NOT NULL CHECK (q1 BETWEEN 0 AND 3),
    q2 smallint NOT NULL CHECK (q2 BETWEEN 0 AND 3),
    q3 smallint NOT NULL CHECK (q3 BETWEEN 0 AND 3),
    q4 smallint NOT NULL CHECK (q4 BETWEEN 0 AND 3),
    q5 smallint NOT NULL CHECK (q5 BETWEEN 0 AND 3),
    q6 smallint NOT NULL CHECK (q6 BETWEEN 0 AND 3),
    q7 smallint NOT NULL CHECK (q7 BETWEEN 0 AND 3),
    total_score smallint NOT NULL CHECK (total_score BETWEEN 0 AND 21),
    severity_band text NOT NULL CHECK (severity_band IN ('minimal', 'mild', 'moderate', 'severe')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gad7_session_id ON gad7_responses (session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_is_research ON sessions (is_research);