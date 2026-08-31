from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import MatchDecision

ALLOWED_RECOMMENDATIONS = {
    "request_reference",
    "verify_duplicate_reference",
    "review_settlement_timing",
    "manual_investigation",
}


@dataclass(frozen=True)
class ExceptionAnalysis:
    status: str
    provider: str
    model: str
    classification: str | None
    explanation: str | None
    recommendation: str | None
    confidence: float | None
    evidence_used: tuple[str, ...]
    limitation: str

    def to_dict(self) -> dict:
        result = asdict(self)
        result["evidence_used"] = list(self.evidence_used)
        return result


def _unavailable(model: str, reason: str, evidence: tuple[str, ...]) -> ExceptionAnalysis:
    return ExceptionAnalysis("unavailable", "nvidia", model, None, None, None, None, evidence, reason)


def _parse_json(text: str) -> dict:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("analysis response is not an object")
    if payload.get("recommendation") not in ALLOWED_RECOMMENDATIONS:
        raise ValueError("analysis response used an unsupported recommendation")
    confidence = float(payload["confidence"])
    if not 0 <= confidence <= 1:
        raise ValueError("analysis confidence is outside 0..1")
    for field in ("classification", "explanation"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"analysis response is missing {field}")
    return {**payload, "confidence": confidence}


def analyze_exception(decision: MatchDecision, api_key: str | None = None,
                      requester: Callable[[Request], str] | None = None) -> ExceptionAnalysis:
    """Explain a rule-engine exception. This function cannot produce a financial mutation."""
    model = os.getenv("NVIDIA_MODEL", "openai/gpt-oss-20b")
    evidence = decision.evidence
    key = api_key if api_key is not None else os.getenv("NVIDIA_API_KEY", "")
    if not key:
        return _unavailable(model, "AI analysis is unavailable because NVIDIA_API_KEY is not configured.", evidence)

    request_body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 280,
        "messages": [
            {"role": "system", "content": "You are a finance-ops exception explainer. You never approve, alter, create, or delete financial records. Use only the supplied evidence. Return JSON only with classification, explanation, recommendation, confidence. recommendation must be one of: request_reference, verify_duplicate_reference, review_settlement_timing, manual_investigation."},
            {"role": "user", "content": json.dumps({
                "source_record_id": decision.source_id,
                "candidate_record_id": decision.target_id,
                "relationship": decision.relationship,
                "rule_outcome": decision.status,
                "rule_exception_category": decision.exception_category,
                "rule_confidence": decision.confidence,
                "evidence": list(evidence),
            })},
        ],
    }
    request = Request(
        f"{os.getenv('NVIDIA_BASE_URL', 'https://integrate.api.nvidia.com/v1').rstrip('/')}/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST",
    )
    try:
        response_text = requester(request) if requester else urlopen(request, timeout=20).read().decode("utf-8")
        content = json.loads(response_text)["choices"][0]["message"]["content"]
        result = _parse_json(content)
        return ExceptionAnalysis("available", "nvidia", model, result["classification"], result["explanation"],
                                 result["recommendation"], result["confidence"], evidence,
                                 "AI analysis is advisory only. A human must approve any later resolution.")
    except (HTTPError, URLError, TimeoutError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _unavailable(model, f"AI analysis is unavailable: {type(exc).__name__}.", evidence)

