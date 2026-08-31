from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import GroundTruthLink, SourceRecord


def _time(index: int, minutes: int = 0) -> str:
    return (datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc) + timedelta(hours=index, minutes=minutes)).isoformat()


def build_demo_batch(case_count: int = 42) -> tuple[list[SourceRecord], list[GroundTruthLink]]:
    """Create deterministic synthetic merchant data with intentional reconciliation friction."""
    records: list[SourceRecord] = []
    truth: list[GroundTruthLink] = []

    for index in range(1, case_count + 1):
        order_id = f"order_demo_{index:03d}"
        payment_id = f"pay_demo_{index:03d}"
        settlement_id = f"set_demo_{index:03d}"
        amount = 10_000 + index * 137
        occurred_at = _time(index)
        payment_order_id = order_id
        payment_time = _time(index, 0)

        # Missing references and timestamp drift force controlled composite matching.
        if index in {7, 19}:
            payment_order_id = None
            payment_time = _time(index, 4)

        records.append(SourceRecord(
            id=order_id, source="merchant_orders", record_type="order", amount_paise=amount,
            currency="INR", occurred_at=occurred_at, status="paid", merchant_order_id=order_id,
        ))
        records.append(SourceRecord(
            id=payment_id, source="razorpay_like_payments", record_type="payment", amount_paise=amount,
            currency="INR", occurred_at=payment_time, status="captured", transaction_id=payment_id,
            merchant_order_id=payment_order_id,
        ))
        truth.append(GroundTruthLink(payment_id, order_id, "payment_to_order"))

        # Settlements are legitimately delayed, but their payment references remain authoritative.
        settlement_time = _time(index, 0) if index not in {11, 23, 37} else _time(index + 48, 0)
        fee = 250 + (index % 4) * 25
        records.append(SourceRecord(
            id=settlement_id, source="bank_statement", record_type="settlement", amount_paise=amount - fee,
            currency="INR", occurred_at=settlement_time, status="settled", payment_id=payment_id,
            settlement_id=settlement_id, fee_paise=fee,
        ))
        truth.append(GroundTruthLink(settlement_id, payment_id, "settlement_to_payment"))

        if index in {4, 15, 28, 39}:
            refund_id = f"refund_demo_{index:03d}"
            records.append(SourceRecord(
                id=refund_id, source="refund_export", record_type="refund", amount_paise=amount // 2,
                currency="INR", occurred_at=_time(index + 2), status="processed", payment_id=payment_id,
                reference_id=refund_id,
            ))
            truth.append(GroundTruthLink(refund_id, payment_id, "refund_to_payment"))

        if index in {9, 21, 34}:
            adjustment_id = f"adjustment_demo_{index:03d}"
            records.append(SourceRecord(
                id=adjustment_id, source="fee_adjustments", record_type="fee_adjustment", amount_paise=-75,
                currency="INR", occurred_at=_time(index + 1), status="posted", settlement_id=settlement_id,
                fee_paise=75,
            ))
            truth.append(GroundTruthLink(adjustment_id, settlement_id, "adjustment_to_settlement"))

    # A duplicate same-amount order creates an intentionally ambiguous fallback candidate.
    duplicate_for = 31
    records.append(SourceRecord(
        id="order_duplicate_031", source="merchant_orders", record_type="order",
        amount_paise=10_000 + duplicate_for * 137, currency="INR", occurred_at=_time(duplicate_for, 3),
        status="paid", merchant_order_id="order_duplicate_031",
    ))
    records.append(SourceRecord(
        id="pay_ambiguous_031", source="razorpay_like_payments", record_type="payment",
        amount_paise=10_000 + duplicate_for * 137, currency="INR", occurred_at=_time(duplicate_for, 4),
        status="captured", transaction_id="pay_ambiguous_031",
    ))
    records.append(SourceRecord(
        id="pay_unmatched_999", source="razorpay_like_payments", record_type="payment",
        amount_paise=99_999, currency="INR", occurred_at=_time(50), status="captured",
        transaction_id="pay_unmatched_999",
    ))

    return records, truth


def write_demo_batch(path: Path) -> None:
    records, truth = build_demo_batch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "label": "August demo merchant batch — Synthetic data",
        "records": [record.to_dict() for record in records],
        "ground_truth_links": [link.__dict__ for link in truth],
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    write_demo_batch(Path(__file__).resolve().parents[1] / "data" / "demo_batch.json")
