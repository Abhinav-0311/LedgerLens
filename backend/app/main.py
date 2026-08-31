from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from .generator import build_demo_batch
from .models import GroundTruthLink, SourceRecord
from .reconciliation import reconcile

app = FastAPI(title="LedgerLens API", version="0.1.0")


class ReconciliationRequest(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1)
    ground_truth_links: list[dict[str, str]] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "phase": "1"}


@app.get("/api/v1/demo-batch")
def demo_batch() -> dict[str, Any]:
    records, truth = build_demo_batch()
    return {"label": "August demo merchant batch — Synthetic data", "records": [record.to_dict() for record in records],
            "ground_truth_links": [link.__dict__ for link in truth]}


@app.post("/api/v1/reconciliations")
def run_reconciliation(payload: ReconciliationRequest) -> dict[str, Any]:
    try:
        records = [SourceRecord(**record) for record in payload.records]
        truth = [GroundTruthLink(**link) for link in payload.ground_truth_links]
    except (TypeError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Malformed import: {exc}") from exc
    return reconcile(records, truth)

