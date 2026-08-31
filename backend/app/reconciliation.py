from __future__ import annotations

from collections import Counter
from datetime import timedelta
from time import perf_counter
from typing import Iterable

from .models import GroundTruthLink, MatchDecision, SourceRecord

FALLBACK_WINDOW = timedelta(minutes=10)


def _decision(source: SourceRecord, target: SourceRecord | None, relationship: str, status: str,
              confidence: float, rule_id: str | None, evidence: list[str], category: str | None = None) -> MatchDecision:
    return MatchDecision(source.id, target.id if target else None, relationship, status, confidence,
                         rule_id, tuple(evidence), category)


def _match_payment(payment: SourceRecord, orders: list[SourceRecord]) -> MatchDecision:
    exact = [order for order in orders if payment.merchant_order_id and order.merchant_order_id == payment.merchant_order_id]
    if len(exact) == 1 and exact[0].amount_paise == payment.amount_paise and payment.status == "captured":
        return _decision(payment, exact[0], "payment_to_order", "matched", 1.0, "payment.order_id.amount.status",
                         ["merchant order ID matched", "amount matched", "payment status is captured"])
    if len(exact) > 1:
        return _decision(payment, None, "payment_to_order", "ambiguous", 0.0, None,
                         ["merchant order ID matched multiple orders"], "duplicate_reference")

    candidates = [order for order in orders if order.amount_paise == payment.amount_paise
                  and abs(order.timestamp - payment.timestamp) <= FALLBACK_WINDOW]
    if len(candidates) == 1:
        return _decision(payment, candidates[0], "payment_to_order", "matched", 0.78,
                         "payment.amount.timestamp_window",
                         ["merchant order ID missing", "amount matched", "timestamp within 10 minutes"])
    if len(candidates) > 1:
        return _decision(payment, None, "payment_to_order", "ambiguous", 0.0, None,
                         ["merchant order ID missing", f"{len(candidates)} amount-and-time candidates found"],
                         "conflicting_candidates")
    return _decision(payment, None, "payment_to_order", "unmatched", 0.0, None,
                     ["no order satisfies the deterministic evidence rules"], "no_candidate")


def _match_reference(record: SourceRecord, targets: list[SourceRecord], relationship: str, reference_field: str) -> MatchDecision:
    reference = getattr(record, reference_field)
    candidates = [target for target in targets if target.id == reference]
    if len(candidates) == 1:
        return _decision(record, candidates[0], relationship, "matched", 1.0, f"{record.record_type}.{reference_field}",
                         [f"{reference_field} matched source record ID"])
    return _decision(record, None, relationship, "unmatched", 0.0, None,
                     [f"{reference_field} is missing or does not reference a known record"], "missing_reference")


def reconcile(records: Iterable[SourceRecord], truth: Iterable[GroundTruthLink] = ()) -> dict:
    started = perf_counter()
    all_records = list(records)
    orders = [record for record in all_records if record.record_type == "order"]
    payments = [record for record in all_records if record.record_type == "payment"]
    settlements = [record for record in all_records if record.record_type == "settlement"]
    refunds = [record for record in all_records if record.record_type == "refund"]
    adjustments = [record for record in all_records if record.record_type == "fee_adjustment"]

    decisions = [_match_payment(payment, orders) for payment in payments]
    decisions += [_match_reference(record, payments, "settlement_to_payment", "payment_id") for record in settlements]
    decisions += [_match_reference(record, payments, "refund_to_payment", "payment_id") for record in refunds]
    decisions += [_match_reference(record, settlements, "adjustment_to_settlement", "settlement_id") for record in adjustments]

    truth_pairs = {(link.left_id, link.right_id, link.relationship) for link in truth}
    auto_matches = [decision for decision in decisions if decision.status == "matched"]
    correct = [decision for decision in auto_matches if (decision.source_id, decision.target_id, decision.relationship) in truth_pairs]
    incorrect = [decision for decision in auto_matches if (decision.source_id, decision.target_id, decision.relationship) not in truth_pairs]
    categories = Counter(decision.exception_category for decision in decisions if decision.exception_category)
    elapsed_ms = round((perf_counter() - started) * 1000, 3)

    return {
        "records_processed": len(all_records),
        "reconcilable_items": len(decisions),
        "auto_match_rate": round(len(auto_matches) / len(decisions), 4) if decisions else 0.0,
        "verified_matching_accuracy": round(len(correct) / len(auto_matches), 4) if truth_pairs and auto_matches else None,
        "unresolved_exceptions": len([decision for decision in decisions if decision.status != "matched"]),
        "throughput_records_per_second": round(len(all_records) / (elapsed_ms / 1000), 2) if elapsed_ms else None,
        "processing_time_ms": elapsed_ms,
        "exception_categories": dict(categories),
        "low_confidence_cases": [decision.to_dict() for decision in decisions if 0 < decision.confidence < 0.8],
        "incorrect_match_examples": [decision.to_dict() for decision in incorrect[:5]],
        "decisions": [decision.to_dict() for decision in decisions],
    }
