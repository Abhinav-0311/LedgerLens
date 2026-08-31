from __future__ import annotations

import unittest

from app.generator import build_demo_batch
from app.models import SourceRecord
from app.reconciliation import reconcile


class ReconciliationTests(unittest.TestCase):
    def test_demo_batch_has_over_100_records_and_measured_metrics(self) -> None:
        records, truth = build_demo_batch()
        report = reconcile(records, truth)
        self.assertGreaterEqual(report["records_processed"], 100)
        self.assertGreater(report["auto_match_rate"], 0)
        self.assertEqual(report["verified_matching_accuracy"], 1.0)
        self.assertGreater(report["unresolved_exceptions"], 0)

    def test_missing_reference_with_one_composite_candidate_matches_at_lower_confidence(self) -> None:
        records, truth = build_demo_batch()
        report = reconcile(records, truth)
        decision = next(item for item in report["decisions"] if item["source_id"] == "pay_demo_007")
        self.assertEqual(decision["status"], "matched")
        self.assertEqual(decision["rule_id"], "payment.amount.timestamp_window")
        self.assertLess(decision["confidence"], 0.8)

    def test_conflicting_candidates_never_auto_match(self) -> None:
        records, truth = build_demo_batch()
        report = reconcile(records, truth)
        decision = next(item for item in report["decisions"] if item["source_id"] == "pay_ambiguous_031")
        self.assertEqual(decision["status"], "ambiguous")
        self.assertIsNone(decision["target_id"])
        self.assertEqual(decision["exception_category"], "conflicting_candidates")

    def test_no_candidate_stays_unmatched(self) -> None:
        records, truth = build_demo_batch()
        report = reconcile(records, truth)
        decision = next(item for item in report["decisions"] if item["source_id"] == "pay_unmatched_999")
        self.assertEqual(decision["status"], "unmatched")
        self.assertEqual(decision["exception_category"], "no_candidate")

    def test_reference_without_target_is_an_exception(self) -> None:
        orphan = SourceRecord(
            id="set_orphan", source="bank_statement", record_type="settlement", amount_paise=900,
            currency="INR", occurred_at="2026-08-01T09:00:00+00:00", status="settled", payment_id="pay_missing",
        )
        report = reconcile([orphan])
        self.assertEqual(report["unresolved_exceptions"], 1)
        self.assertEqual(report["decisions"][0]["exception_category"], "missing_reference")


if __name__ == "__main__":
    unittest.main()

