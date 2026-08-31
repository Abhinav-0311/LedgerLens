from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from psycopg import connect
from psycopg.types.json import Jsonb

from .generator import build_demo_batch
from .models import GroundTruthLink, SourceRecord

DEMO_BATCH_ID = "00000000-0000-0000-0000-000000000004"
MAX_IMPORT_BYTES = 1_000_000
MAX_RECORDS = 5_000
REQUIRED_FIELDS = {"id", "source", "record_type", "amount_paise", "currency", "occurred_at", "status"}


def _connection():
    return connect(os.environ["DATABASE_URL"])


def _validate_record(raw: dict, index: int) -> SourceRecord:
    missing = REQUIRED_FIELDS - raw.keys()
    if missing:
        raise ValueError(f"record {index} is missing required fields: {', '.join(sorted(missing))}")
    try:
        record = SourceRecord(
            id=str(raw["id"]).strip(), source=str(raw["source"]).strip(), record_type=str(raw["record_type"]).strip(),
            amount_paise=int(raw["amount_paise"]), currency=str(raw["currency"]).strip().upper(),
            occurred_at=str(raw["occurred_at"]).strip(), status=str(raw["status"]).strip(),
            transaction_id=raw.get("transaction_id") or None, merchant_order_id=raw.get("merchant_order_id") or None,
            payment_id=raw.get("payment_id") or None, settlement_id=raw.get("settlement_id") or None,
            reference_id=raw.get("reference_id") or None,
            fee_paise=int(raw["fee_paise"]) if raw.get("fee_paise") not in (None, "") else None,
        )
        datetime.fromisoformat(record.occurred_at.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"record {index} has invalid field values: {exc}") from exc
    if not record.id or not record.source or not record.record_type or not record.status:
        raise ValueError(f"record {index} has an empty required value")
    if len(record.currency) != 3:
        raise ValueError(f"record {index} must use a three-letter currency code")
    return record


def parse_import(filename: str, content: str) -> tuple[str, list[SourceRecord], list[GroundTruthLink]]:
    if len(content.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise ValueError("Import exceeds the 1 MB synthetic-demo limit.")
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if suffix == "json":
            payload = json.loads(content)
            if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
                raise ValueError("JSON must be an object containing a records array.")
            label = str(payload.get("label") or "Imported synthetic batch").strip()
            raw_records = payload["records"]
            raw_truth = payload.get("ground_truth_links", [])
        elif suffix == "csv":
            reader = csv.DictReader(io.StringIO(content))
            if not reader.fieldnames:
                raise ValueError("CSV must include a header row.")
            label = f"Imported synthetic batch — {filename}"
            raw_records, raw_truth = list(reader), []
        else:
            raise ValueError("Only .json and .csv synthetic batch files are supported.")
    except (csv.Error, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not parse import: {exc}") from exc
    if not label:
        raise ValueError("Batch label cannot be empty.")
    if not 1 <= len(raw_records) <= MAX_RECORDS:
        raise ValueError(f"Import must contain between 1 and {MAX_RECORDS} records.")
    records = [_validate_record(raw, index + 1) for index, raw in enumerate(raw_records)]
    ids = [record.id for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError("Import contains duplicate record IDs.")
    known_ids = set(ids)
    truth: list[GroundTruthLink] = []
    for index, raw in enumerate(raw_truth, start=1):
        try:
            link = GroundTruthLink(left_id=str(raw["left_id"]), right_id=str(raw["right_id"]), relationship=str(raw["relationship"]))
        except (KeyError, TypeError) as exc:
            raise ValueError(f"ground truth link {index} is malformed") from exc
        if link.left_id not in known_ids or link.right_id not in known_ids:
            raise ValueError(f"ground truth link {index} references a record outside this import")
        truth.append(link)
    return label[:160], records, truth


def _insert_records(cursor, batch_id: str, records: list[SourceRecord], truth: list[GroundTruthLink]) -> None:
    for record in records:
        cursor.execute("""INSERT INTO source_records (id, batch_id, source, record_type, amount_paise, currency, occurred_at, status, transaction_id, merchant_order_id, payment_id, settlement_id, reference_id, fee_paise, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (record.id, batch_id, record.source, record.record_type, record.amount_paise, record.currency, record.occurred_at, record.status, record.transaction_id, record.merchant_order_id, record.payment_id, record.settlement_id, record.reference_id, record.fee_paise, Jsonb(record.to_dict())))
    for link in truth:
        cursor.execute("INSERT INTO ground_truth_links (id, batch_id, left_record_id, right_record_id, relationship) VALUES (%s, %s, %s, %s, %s)", (str(uuid4()), batch_id, link.left_id, link.right_id, link.relationship))


def _insert_batch(batch_id: str, label: str, records: list[SourceRecord], truth: list[GroundTruthLink]) -> None:
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO batches (id, label, source_kind, record_count) VALUES (%s, %s, 'synthetic', %s)", (batch_id, label, len(records)))
        _insert_records(cursor, batch_id, records, truth)


def ensure_demo_batch() -> str:
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM source_records WHERE batch_id = %s", (DEMO_BATCH_ID,))
        if cursor.fetchone()[0] > 0:
            return DEMO_BATCH_ID
    records, truth = build_demo_batch()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO batches (id, label, source_kind, record_count) VALUES (%s, %s, 'synthetic', %s) ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label, record_count = EXCLUDED.record_count", (DEMO_BATCH_ID, "August demo merchant batch — Synthetic data", len(records)))
        _insert_records(cursor, DEMO_BATCH_ID, records, truth)
    return DEMO_BATCH_ID


def import_batch(filename: str, content: str) -> dict:
    label, records, truth = parse_import(filename, content)
    batch_id = str(uuid4())
    try:
        _insert_batch(batch_id, label, records, truth)
    except Exception as exc:
        if "duplicate key" in str(exc).lower():
            raise HTTPException(status_code=422, detail="Import contains record IDs already used by another batch.") from exc
        raise
    return {"id": batch_id, "label": label, "record_count": len(records), "ground_truth_available": bool(truth)}


def list_batches() -> list[dict]:
    ensure_demo_batch()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id::text, label, source_kind, record_count, imported_at FROM batches ORDER BY imported_at DESC")
        return [{"id": row[0], "label": row[1], "source_kind": row[2], "record_count": row[3], "imported_at": row[4].isoformat()} for row in cursor.fetchall()]


def load_batch(batch_id: str) -> tuple[list[SourceRecord], list[GroundTruthLink], dict]:
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT label, record_count FROM batches WHERE id = %s", (batch_id,))
        batch = cursor.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="Selected batch was not found.")
        cursor.execute("SELECT raw_payload FROM source_records WHERE batch_id = %s ORDER BY id", (batch_id,))
        records = [SourceRecord(**row[0]) for row in cursor.fetchall()]
        cursor.execute("SELECT left_record_id, right_record_id, relationship FROM ground_truth_links WHERE batch_id = %s", (batch_id,))
        truth = [GroundTruthLink(*row) for row in cursor.fetchall()]
    return records, truth, {"id": batch_id, "label": batch[0], "record_count": batch[1], "ground_truth_available": bool(truth)}
