# LedgerLens

LedgerLens is a synthetic-data AI Finance Controller for the Razorpay AI Buildathon Track 04. It reconciles merchant orders, Razorpay-shaped payment exports, settlements, refunds, and fee adjustments. Deterministic rules are the authority; AI is reserved for bounded exception explanation in Phase 3.

> **Synthetic data only.** LedgerLens does not move money, use real financial data, or claim a Razorpay integration.

## Phase 1 status

- Docker scaffold: Next.js, FastAPI, PostgreSQL
- Reproducible generator with 130+ source records and hidden ground-truth links
- Deterministic matching with exact-ID and amount/timestamp fallback rules
- Safe unresolved outcomes for no-candidate and conflicting-candidate cases
- Dependency-free unit tests for reconciliation behavior
- Database schema for later batch persistence, approvals, AI analysis, and audit events

## Architecture

```text
Synthetic batch -> FastAPI import/reconciliation -> PostgreSQL audit model
                           |
                           +-> Next.js operations workspace (Phase 2)
                           +-> NVIDIA exception analysis (Phase 3, human-gated)
```

## Run the Phase 1 checks

```powershell
$env:PYTHONPATH = "backend"
C:\Users\Abhinav Jain\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s backend/tests -v
```

Generate a local demo JSON file (ignored by Git):

```powershell
$env:PYTHONPATH = "backend"
C:\Users\Abhinav Jain\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m app.generator
```

## Start the stack

```powershell
docker compose up --build
```

- Web shell: `http://localhost:3010`
- API docs: `http://localhost:8010/docs`
- API health: `http://localhost:8010/health`

## Evaluation methodology

`ground_truth_links` is generated separately from the UI-facing records. The engine reports:

- **Auto-match rate:** deterministic matched decisions / all reconcilable decisions.
- **Verified matching accuracy:** auto-matches that agree with hidden ground truth / all auto-matches.
- **Unresolved exceptions:** decisions intentionally left unmatched or ambiguous.
- **Throughput:** source records processed per second and elapsed processing time.

The demo includes missing IDs, duplicate candidates, delayed settlements, partial refunds, fee adjustments, timestamp drift, and unmatched entries. It prefers an honest exception over an unsafe match.

## Known Phase 1 limitations

- Persistence endpoints and batch upload UI are Phase 2 work.
- NVIDIA analysis, human approval, and audit-log UI are intentionally deferred to later phases.
- This project contains no live Razorpay integration.
