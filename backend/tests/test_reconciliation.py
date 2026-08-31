from __future__ import annotations

import unittest

from app.ai_analysis import analyze_exception
from app.batches import parse_import
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

    def test_unconfigured_ai_is_explicitly_unavailable(self) -> None:
        records, truth = build_demo_batch()
        report = reconcile(records, truth)
        decision_data = next(item for item in report["decisions"] if item["source_id"] == "pay_unmatched_999")
        from app.models import MatchDecision
        decision = MatchDecision(**{**decision_data, "evidence": tuple(decision_data["evidence"])})
        analysis = analyze_exception(decision, api_key="")
        self.assertEqual(analysis.status, "unavailable")
        self.assertIsNone(analysis.recommendation)

    def test_ai_timeout_leaves_exception_open_with_a_clear_retry_message(self) -> None:
        records, truth = build_demo_batch()
        report = reconcile(records, truth)
        decision_data = next(item for item in report["decisions"] if item["source_id"] == "pay_unmatched_999")
        from app.models import MatchDecision
        decision = MatchDecision(**{**decision_data, "evidence": tuple(decision_data["evidence"])})
        analysis = analyze_exception(decision, api_key="test-key", requester=lambda _request: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(analysis.status, "unavailable")
        self.assertIn("Retry analysis", analysis.limitation)
        self.assertIn("remains unresolved", analysis.limitation)

    def test_ai_analysis_accepts_only_bounded_structured_recommendations(self) -> None:
        records, truth = build_demo_batch()
        report = reconcile(records, truth)
        decision_data = next(item for item in report["decisions"] if item["source_id"] == "pay_unmatched_999")
        from app.models import MatchDecision
        decision = MatchDecision(**{**decision_data, "evidence": tuple(decision_data["evidence"])})
        response = '{"choices":[{"message":{"content":"{\\\"classification\\\":\\\"missing_reference\\\",\\\"explanation\\\":\\\"No deterministic order candidate exists.\\\",\\\"recommendation\\\":\\\"manual_investigation\\\",\\\"confidence\\\":0.4}"}}]}'
        analysis = analyze_exception(decision, api_key="test-key", requester=lambda _: response)
        self.assertEqual(analysis.status, "available")
        self.assertEqual(analysis.recommendation, "manual_investigation")

    def test_json_import_keeps_ground_truth_separate_from_records(self) -> None:
        content = """{"label":"Tiny synthetic batch","records":[{"id":"order_1","source":"merchant_orders","record_type":"order","amount_paise":1000,"currency":"INR","occurred_at":"2026-08-01T09:00:00+00:00","status":"paid"},{"id":"pay_1","source":"payments","record_type":"payment","amount_paise":1000,"currency":"INR","occurred_at":"2026-08-01T09:01:00+00:00","status":"captured","merchant_order_id":"order_1"}],"ground_truth_links":[{"left_id":"pay_1","right_id":"order_1","relationship":"payment_to_order"}]}"""
        label, records, truth = parse_import("tiny.json", content)
        self.assertEqual(label, "Tiny synthetic batch")
        self.assertEqual(len(records), 2)
        self.assertEqual(len(truth), 1)

    def test_malformed_csv_import_is_rejected_with_actionable_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            parse_import("bad.csv", "id,source\nrecord_1,merchant_orders\n")

    def test_accuracy_is_not_reported_without_ground_truth(self) -> None:
        record = SourceRecord(id="pay_only", source="payments", record_type="payment", amount_paise=100,
                              currency="INR", occurred_at="2026-08-01T09:00:00+00:00", status="captured")
        report = reconcile([record])
        self.assertIsNone(report["verified_matching_accuracy"])


if __name__ == "__main__":
    unittest.main()
