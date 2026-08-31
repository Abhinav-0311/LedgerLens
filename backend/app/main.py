from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from .ai_analysis import analyze_exception
from .audit import list_events, record_event, record_reconciliation
from .generator import build_demo_batch
from .models import GroundTruthLink, MatchDecision, SourceRecord
from .reconciliation import reconcile

app = FastAPI(title="LedgerLens API", version="0.1.0")


class ReconciliationRequest(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1)
    ground_truth_links: list[dict[str, str]] = Field(default_factory=list)


class ExceptionAnalysisRequest(BaseModel):
    decision: dict[str, Any]


class ResolutionRequest(BaseModel):
    decision: dict[str, Any]
    analysis: dict[str, Any]
    action: str
    actor_label: str = Field(min_length=2, max_length=80)
    rationale: str = Field(min_length=2, max_length=500)


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
    report = reconcile(records, truth)
    record_reconciliation(report)
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
    record_event("ai_analysis_available" if analysis["status"] == "available" else "ai_analysis_unavailable", "match_decision", decision.source_id, analysis)
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
    review = record_event(f"resolution_{payload.action}", "match_decision", source_id, {
        "actor_label": payload.actor_label, "rationale": payload.rationale,
        "proposed_follow_up": payload.analysis["recommendation"], "analysis_confidence": payload.analysis.get("confidence"),
        "financial_records_changed": False,
    })
    return {"resolution": review, "message": "Human decision recorded. Source financial records were not altered."}


@app.get("/api/v1/audit-events")
def audit_events() -> dict[str, Any]:
    return {"events": list_events()}
