from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from .ai_analysis import analyze_exception
from .audit import list_events, record_event, record_reconciliation
from .batches import ensure_demo_batch, import_batch, list_batches, load_batch
from .models import GroundTruthLink, MatchDecision, SourceRecord
from .reconciliation import reconcile

app = FastAPI(title="LedgerLens API", version="0.1.0")


class ReconciliationRequest(BaseModel):
    batch_id: str | None = None
    records: list[dict[str, Any]] | None = None
    ground_truth_links: list[dict[str, str]] = Field(default_factory=list)


class ExceptionAnalysisRequest(BaseModel):
    batch_id: str
    decision: dict[str, Any]


class ResolutionRequest(BaseModel):
    batch_id: str
    decision: dict[str, Any]
    analysis: dict[str, Any]
    action: str
    actor_label: str = Field(min_length=2, max_length=80)
    rationale: str = Field(min_length=2, max_length=500)


class ImportRequest(BaseModel):
    filename: str = Field(min_length=5, max_length=180)
    content: str = Field(min_length=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "phase": "5"}


@app.get("/api/v1/demo-batch")
def demo_batch() -> dict[str, Any]:
    batch_id = ensure_demo_batch()
    records, _, metadata = load_batch(batch_id)
    return {**metadata, "records": [record.to_dict() for record in records]}


@app.get("/api/v1/batches")
def batches() -> dict[str, Any]:
    return {"batches": list_batches()}


@app.post("/api/v1/batches/import", status_code=201)
def upload_synthetic_batch(payload: ImportRequest) -> dict[str, Any]:
    try:
        batch = import_batch(payload.filename, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Malformed import: {exc}") from exc
    record_event(batch["id"], "batch_imported", "batch", batch["id"], {"filename": payload.filename, **batch})
    return batch


@app.post("/api/v1/reconciliations")
def run_reconciliation(payload: ReconciliationRequest) -> dict[str, Any]:
    try:
        if payload.batch_id:
            records, truth, metadata = load_batch(payload.batch_id)
        elif payload.records:
            records = [SourceRecord(**record) for record in payload.records]
            truth = [GroundTruthLink(**link) for link in payload.ground_truth_links]
            metadata = {"id": ensure_demo_batch(), "label": "Legacy direct import", "ground_truth_available": bool(truth)}
        else:
            raise ValueError("A persisted batch_id is required.")
    except (TypeError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Malformed import: {exc}") from exc
    report = reconcile(records, truth)
    report.update({"batch_id": metadata["id"], "batch_label": metadata["label"], "ground_truth_available": metadata["ground_truth_available"]})
    record_reconciliation(metadata["id"], report)
    return report


@app.post("/api/v1/exception-analyses")
def run_exception_analysis(payload: ExceptionAnalysisRequest) -> dict[str, Any]:
    try:
        decision = MatchDecision(
            source_id=payload.decision["source_id"], target_id=payload.decision.get("target_id"),
            relationship=payload.decision["relationship"], status=payload.decision["status"],
            confidence=float(payload.decision["confidence"]), rule_id=payload.decision.get("rule_id"),
            evidence=tuple(payload.decision["evidence"]), exception_category=payload.decision.get("exception_category"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Malformed exception evidence: {exc}") from exc
    analysis = analyze_exception(decision).to_dict()
    record_event(payload.batch_id, "ai_analysis_available" if analysis["status"] == "available" else "ai_analysis_unavailable", "match_decision", decision.source_id, analysis)
    return analysis


@app.post("/api/v1/resolutions")
def record_resolution(payload: ResolutionRequest) -> dict[str, Any]:
    if payload.action not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Resolution action must be approved or rejected.")
    if payload.analysis.get("status") != "available" or not payload.analysis.get("recommendation"):
        raise HTTPException(status_code=422, detail="A valid AI advisory is required for an explicit resolution review.")
    source_id = payload.decision.get("source_id")
    if not source_id:
        raise HTTPException(status_code=422, detail="Resolution must identify the exception source record.")
    review = record_event(payload.batch_id, f"resolution_{payload.action}", "match_decision", source_id, {
        "actor_label": payload.actor_label, "rationale": payload.rationale,
        "proposed_follow_up": payload.analysis["recommendation"], "analysis_confidence": payload.analysis.get("confidence"),
        "financial_records_changed": False,
    })
    return {"resolution": review, "message": "Human decision recorded. Source financial records were not altered."}


@app.get("/api/v1/audit-events")
def audit_events(batch_id: str) -> dict[str, Any]:
    return {"events": list_events(batch_id)}
