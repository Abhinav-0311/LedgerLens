from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai_analysis import ExceptionAnalysis
from app.generator import build_demo_batch
from app.main import app


class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.records, self.truth = build_demo_batch()
        self.metadata = {"id": "00000000-0000-0000-0000-000000000004", "label": "Synthetic test batch", "ground_truth_available": True}

    @patch("app.main.record_reconciliation")
    @patch("app.main.load_batch")
    def test_reconciliation_accepts_a_persisted_batch_id(self, load_batch, record_reconciliation) -> None:
        load_batch.return_value = (self.records, self.truth, self.metadata)
        response = self.client.post("/api/v1/reconciliations", json={"batch_id": self.metadata["id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["records_processed"], 136)
        record_reconciliation.assert_called_once()

    @patch("app.main.record_event")
    @patch("app.main.analyze_exception")
    @patch("app.main.load_batch")
    def test_analysis_is_derived_from_server_reconciliation(self, load_batch, analyze, record_event) -> None:
        load_batch.return_value = (self.records, self.truth, self.metadata)
        analyze.return_value = ExceptionAnalysis("available", "nvidia", "test-model", "no_candidate", "No candidate exists.", "manual_investigation", .4, ("no candidate",), "Advisory only.")
        record_event.return_value = {"id": "advisory-001"}
        response = self.client.post("/api/v1/exception-analyses", json={"batch_id": self.metadata["id"], "source_id": "pay_unmatched_999", "status": "matched"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["advisory_id"], "advisory-001")
        self.assertEqual(analyze.call_args.args[0].source_id, "pay_unmatched_999")

    @patch("app.main.record_event")
    @patch("app.main.find_available_advisory", return_value=None)
    def test_forged_advisory_cannot_create_a_resolution(self, find_advisory, record_event) -> None:
        response = self.client.post("/api/v1/resolutions", json={"batch_id": self.metadata["id"], "source_id": "pay_unmatched_999", "advisory_id": "forged", "action": "approved", "actor_label": "Reviewer", "rationale": "Attempting an invalid approval."})
        self.assertEqual(response.status_code, 422)
        record_event.assert_not_called()
        find_advisory.assert_called_once()


if __name__ == "__main__":
    unittest.main()
