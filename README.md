# LedgerLens

LedgerLens is a synthetic-data AI Finance Controller for the Razorpay AI Buildathon Track 04. It reconciles merchant orders, Razorpay-shaped payment exports, settlements, refunds, and fee adjustments. Deterministic rules are the authority; AI is limited to bounded exception explanation.

> **Synthetic data only.** LedgerLens does not move money, use real financial data, or claim a Razorpay integration.

## Current implementation

- Docker scaffold: Next.js, FastAPI, PostgreSQL
- Reproducible generator with 130+ source records and hidden ground-truth links
- Deterministic matching with exact-ID and amount/timestamp fallback rules
- Safe unresolved outcomes for no-candidate and conflicting-candidate cases
- Unit and API-contract tests for reconciliation, import validation, AI boundaries, and resolution handling
- PostgreSQL-backed append-only audit events for reconciliation activity, AI availability, and reviewer decisions
- JSON/CSV synthetic-batch import with required-field, duplicate-ID, size, and malformed-file validation
- Persisted batch selection: imported records stay in PostgreSQL while their synthetic ground-truth mapping remains server-side
- Evaluation view for engine-only throughput, low-confidence auto-matches, and any incorrect auto-matches

## Operations workspace

- Operations workbench with a batch selector, real run action, metric strip, exception queue, and evidence inspector
- Empty, loading, error, selected, and reset states
- Next.js server-side API proxy keeps the browser isolated from the internal FastAPI hostname
- Responsive interface: the metric strip and review panels collapse without horizontal page overflow

## AI and review safeguards

- NVIDIA-hosted `openai/gpt-oss-20b` explains only unresolved rule-engine decisions
- Structured output is constrained to a classification, evidence-grounded explanation, recommendation, and confidence
- The analysis endpoint receives no hidden ground truth and cannot alter a match or financial record
- Missing credentials, network failures, and malformed model output produce an explicit unavailable state
- A reviewer must explicitly approve or reject an available AI recommendation; an unavailable recommendation cannot be approved
- Approval records the proposed follow-up only. It never changes a source financial record or a deterministic match.
- The server recomputes the unresolved exception before AI analysis and issues an advisory ID only for a stored available advisory. Resolution requests must reference that exact advisory ID, batch, and source record.
- The workbench exposes recent audit events and an expandable batch history so every conclusion remains inspectable.

## Architecture

```text
Synthetic JSON/CSV batch -> FastAPI validation -> PostgreSQL persisted batch -> deterministic reconciliation
                           |
                           +-> Next.js operations workspace
                           +-> NVIDIA exception analysis (advisory only)
                           +-> explicit reviewer approve/reject record
```

## Run the checks

```powershell
docker compose exec api python -m unittest discover -s tests -v
```

Run the checks after starting the stack. The default batch is seeded automatically on first use.

## Start the stack

```powershell
docker compose up --build
```

- Web shell: `http://localhost:3010`
- API docs: `http://localhost:8010/docs`
- API health: `http://localhost:8010/health`

## Import a synthetic batch

Use the **Import file** action in the workbench. LedgerLens accepts `.json` and `.csv` files up to 1 MB and up to 5,000 records. It is intentionally limited to synthetic data for this project.

For the walkthrough, download [the ready-to-import synthetic sample](frontend/public/ledgerlens-synthetic-sample.json) from the workbench or repository.

JSON supports records and an optional hidden evaluation mapping:

```json
{
  "label": "My synthetic merchant batch",
  "records": [{
    "id": "order_001",
    "source": "merchant_orders",
    "record_type": "order",
    "amount_paise": 12500,
    "currency": "INR",
    "occurred_at": "2026-08-01T09:00:00+00:00",
    "status": "paid",
    "merchant_order_id": "order_001"
  }],
  "ground_truth_links": []
}
```

CSV requires the same record fields as column headers. CSV has no ground-truth-link field, so its verified accuracy is shown as **Not supplied** rather than guessed.

## Evaluation methodology

`ground_truth_links` is generated separately from the UI-facing records. The engine reports:

- **Auto-match rate:** deterministic matched decisions / all reconcilable decisions.
- **Verified matching accuracy:** auto-matches that agree with hidden ground truth / all auto-matches.
- **Unresolved exceptions:** decisions intentionally left unmatched or ambiguous.
- **Engine throughput:** source records processed per second during deterministic rule evaluation. It intentionally excludes file upload, database persistence, audit writes, and optional AI latency.
- **Low-confidence cases:** deterministic auto-matches below 0.80 confidence are shown separately for review.
- **Incorrect matches:** only reported when synthetic ground truth exists; the UI shows examples rather than hiding them.

The demo includes missing IDs, duplicate candidates, delayed settlements, partial refunds, fee adjustments, timestamp drift, and unmatched entries. It prefers an honest exception over an unsafe match.

## Known limitations

- Reviewer identity is operator-entered and not authenticated. The audit event stream is append-only through this application, but not a tamper-proof compliance ledger.
- AI recommendations are advisory and do not persist as financial actions. They are unavailable if NVIDIA credentials or the provider are unavailable.
- This demo has no authenticated users or production-grade authorization; its approval gate is a workflow integrity control, not a multi-user access-control system.
- This project contains no live Razorpay integration.

## Short demo script

1. Start the stack, open `http://localhost:3010`, and select **August demo merchant batch** or import a synthetic JSON/CSV file.
2. Run reconciliation. Inspect the real batch metrics, evaluation evidence, and an unresolved or ambiguous exception.
3. Read the deterministic evidence first, then request an AI exception analysis. If the provider is unavailable, show the explicit safe fallback.
4. For an available advisory, choose **Approve follow-up** or **Reject**. The confirmation states that source financial records remain unchanged.
5. Open the audit panel to show the recorded reconciliation, exception, AI, and reviewer-decision events.

## Submission checklist

- [x] Synthetic data only; no live Razorpay integration or money movement
- [x] Deterministic reconciliation with inspectable evidence and exception handling
- [x] Hidden synthetic ground truth and honest batch metrics
- [x] Bounded, optional AI exception analysis with human-gated follow-up
- [x] Audit events for reconciliation, AI advice, and reviewer actions
