-- D-083 / write-ahead audit trail (production hardening step 2). See DEVIATIONS.md.
-- Fast-default add-column (PG 11+): no table rewrite, no lock beyond a brief metadata change, so
-- this is safe against a live, populated table. Existing rows keep their current meaning exactly
-- ('executed' is what every pre-migration row already was).
ALTER TABLE telemetry.agent_actions
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'executed';

-- The hot query this whole change exists to serve: "show me actions stuck mid-flight" (a crash
-- between the write-ahead insert and the outcome update). Partial index -- almost every row is not
-- 'executing', so this stays tiny regardless of table size.
CREATE INDEX IF NOT EXISTS agent_actions_executing_idx
  ON telemetry.agent_actions (ts) WHERE status = 'executing';
