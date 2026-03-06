-- IdeaKache: Supabase table + RLS setup
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)

CREATE TABLE quotes (
  id int PRIMARY KEY,
  text text NOT NULL,
  author text NOT NULL,
  source text DEFAULT '',
  url text DEFAULT '',
  verified text DEFAULT 'true',
  verification_notes text DEFAULT '',
  concepts text[] DEFAULT '{}',
  needs_review boolean DEFAULT false
);

ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated read" ON quotes
  FOR SELECT
  TO authenticated
  USING (true);
