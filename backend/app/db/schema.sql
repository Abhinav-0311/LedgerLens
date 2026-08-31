CREATE TABLE batches (
  id UUID PRIMARY KEY,
  label TEXT NOT NULL,
  source_kind TEXT NOT NULL DEFAULT 'synthetic',
  imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  record_count INTEGER NOT NULL CHECK (record_count >= 0)
);

CREATE TABLE source_records (
  id TEXT PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES batches(id),
  source TEXT NOT NULL,
  record_type TEXT NOT NULL,
  amount_paise BIGINT NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'INR',
  occurred_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL,
  transaction_id TEXT,
  merchant_order_id TEXT,
  payment_id TEXT,
  settlement_id TEXT,
  reference_id TEXT,
  fee_paise BIGINT,
  raw_payload JSONB NOT NULL
);

CREATE TABLE reconciliation_runs (
  id UUID PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES batches(id),
  rule_version TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  metrics JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE match_decisions (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES reconciliation_runs(id),
  source_record_id TEXT NOT NULL REFERENCES source_records(id),
  target_record_id TEXT REFERENCES source_records(id),
  relationship TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('matched', 'unmatched', 'ambiguous', 'needs_review')),
  confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  rule_id TEXT,
  evidence JSONB NOT NULL,
  exception_category TEXT
);

-- Server-only evaluation data; never exposed by the UI/API read models.
CREATE TABLE ground_truth_links (
  id UUID PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES batches(id),
  left_record_id TEXT NOT NULL REFERENCES source_records(id),
  right_record_id TEXT NOT NULL REFERENCES source_records(id),
  relationship TEXT NOT NULL
);

CREATE TABLE ai_analyses (
  id UUID PRIMARY KEY,
  match_decision_id UUID NOT NULL REFERENCES match_decisions(id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('available', 'unavailable', 'failed')),
  classification TEXT,
  explanation TEXT,
  recommendation TEXT,
  confidence NUMERIC(4,3),
  evidence_snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE resolution_actions (
  id UUID PRIMARY KEY,
  match_decision_id UUID NOT NULL REFERENCES match_decisions(id),
  action TEXT NOT NULL CHECK (action IN ('approved', 'rejected', 'manual_resolution')),
  actor_label TEXT NOT NULL,
  rationale TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
  id UUID PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES batches(id),
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX source_records_batch_type_idx ON source_records(batch_id, record_type);
CREATE INDEX source_records_order_idx ON source_records(batch_id, merchant_order_id);
CREATE INDEX source_records_payment_idx ON source_records(batch_id, payment_id);

