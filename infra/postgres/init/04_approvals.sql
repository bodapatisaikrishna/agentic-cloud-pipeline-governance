-- Production trust core (v2, P1): human-approval queue for gated agent actions.
-- A pending row is a self-contained, re-executable ProposedAction awaiting sign-off (approval mode),
-- so approving it later can reconstruct and run the action without the original agent cycle.
CREATE TABLE IF NOT EXISTS telemetry.action_approvals (
  approval_id   BIGSERIAL PRIMARY KEY,
  experiment_run TEXT,
  agent         TEXT,
  action_type   TEXT,
  target        TEXT,
  params        JSONB,
  justification TEXT,
  confidence    DOUBLE PRECISION,
  policy_reason TEXT,
  status        TEXT DEFAULT 'pending',   -- pending | approved | rejected | executed | failed
  requested_ts  TIMESTAMPTZ DEFAULT now(),
  decided_ts    TIMESTAMPTZ,
  decided_by    TEXT,
  decision_note TEXT,
  outcome       TEXT
);

CREATE INDEX IF NOT EXISTS action_approvals_status_idx
  ON telemetry.action_approvals (status, requested_ts);
