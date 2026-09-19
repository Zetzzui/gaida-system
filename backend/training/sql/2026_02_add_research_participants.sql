-- Adds a one-row-per-participant table for research demographics, so a
-- returning participant (same student number, or same anonymous code) is
-- never asked year level/program/gender/region more than once.
-- Run this in the Supabase SQL editor. Safe to re-run.
-- This is a SECOND migration — run 2026_add_research_support.sql first
-- if you haven't already.

CREATE TABLE IF NOT EXISTS research_participants (
    participant_id text PRIMARY KEY,  -- the real student number, or "anon_<code>"
    is_anonymous boolean NOT NULL DEFAULT false,
    year_level text,
    program text,
    gender text,
    region text,
    created_at timestamptz NOT NULL DEFAULT now()
);