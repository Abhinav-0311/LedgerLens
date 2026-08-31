from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    id: str
    source: str
    record_type: str
    amount_paise: int
    currency: str
    occurred_at: str
    status: str
    transaction_id: str | None = None
    merchant_order_id: str | None = None
    payment_id: str | None = None
    settlement_id: str | None = None
    reference_id: str | None = None
    fee_paise: int | None = None

    @property
    def timestamp(self) -> datetime:
        return datetime.fromisoformat(self.occurred_at.replace("Z", "+00:00"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GroundTruthLink:
    left_id: str
    right_id: str
    relationship: str


@dataclass(frozen=True)
class MatchDecision:
    source_id: str
    target_id: str | None
    relationship: str
    status: str
    confidence: float
    rule_id: str | None
    evidence: tuple[str, ...]
    exception_category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence"] = list(self.evidence)
        return result

