from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from .ai_analysis import analyze_exception
from .audit import find_available_advisory, list_events, record_event, record_reconciliation
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
    source_id: str = Field(min_length=1, max_length=160)


class ResolutionRequest(BaseModel):
    batch_id: str
    source_id: str = Field(min_length=1, max_length=160)
    advisory_id: str = Field(min_length=1, max_length=80)
    action: str
    actor_label: str = Field(min_length=2, max_length=80)
    rationale: str = Field(min_length=2, max_length=500)


class ImportRequest(BaseModel):
    filename: str = Field(min_length=5, max_length=180)
    content: str = Field(min_length=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "release": "submission-ready"}


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
    records, truth, _ = load_batch(payload.batch_id)
    report = reconcile(records, truth)
    decision_data = next((item for item in report["decisions"] if item["source_id"] == payload.source_id), None)
    if not decision_data or decision_data["status"] == "matched":
        raise HTTPException(status_code=422, detail="AI analysis is available only for a current unresolved deterministic exception.")
    decision = MatchDecision(**{**decision_data, "evidence": tuple(decision_data["evidence"])})
    analysis = analyze_exception(decision).to_dict()
    event = record_event(payload.batch_id, "ai_analysis_available" if analysis["status"] == "available" else "ai_analysis_unavailable", "match_decision", decision.source_id, analysis)
    if analysis["status"] == "available":
        analysis["advisory_id"] = event["id"]
    return analysis


@app.post("/api/v1/resolutions")
def record_resolution(payload: ResolutionRequest) -> dict[str, Any]:
    if payload.action not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Resolution action must be approved or rejected.")
    advisory = find_available_advisory(payload.batch_id, payload.advisory_id, payload.source_id)
    if not advisory:
        raise HTTPException(status_code=422, detail="Resolution requires a matching server-recorded available AI advisory.")
    review = record_event(payload.batch_id, f"resolution_{payload.action}", "match_decision", payload.source_id, {
        "actor_label": payload.actor_label, "rationale": payload.rationale,
        "advisory_id": advisory["id"], "proposed_follow_up": advisory["payload"]["recommendation"],
        "analysis_confidence": advisory["payload"].get("confidence"), "financial_records_changed": False,
    })
    return {"resolution": review, "message": "Human decision recorded. Source financial records were not altered."}


@app.get("/api/v1/audit-events")
def audit_events(batch_id: str) -> dict[str, Any]:
    return {"events": list_events(batch_id)}
