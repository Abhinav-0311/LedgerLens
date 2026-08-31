from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from psycopg import connect
from psycopg.types.json import Jsonb

DEMO_BATCH_ID = "00000000-0000-0000-0000-000000000004"


def _connection():
    return connect(os.environ["DATABASE_URL"])


def _ensure_batch(cursor) -> None:
    cursor.execute("""INSERT INTO batches (id, label, source_kind, record_count)
        VALUES (%s, %s, 'synthetic', 0) ON CONFLICT (id) DO NOTHING""",
        (DEMO_BATCH_ID, "August demo merchant batch — Synthetic data"))


def record_event(event_type: str, entity_type: str, entity_id: str, payload: dict) -> dict:
    event = {"id": str(uuid4()), "event_type": event_type, "entity_type": entity_type,
             "entity_id": entity_id, "payload": payload, "created_at": datetime.now(timezone.utc).isoformat()}
    with _connection() as connection, connection.cursor() as cursor:
        _ensure_batch(cursor)
        cursor.execute("""INSERT INTO audit_events (id, batch_id, event_type, entity_type, entity_id, payload, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (event["id"], DEMO_BATCH_ID, event_type, entity_type, entity_id, Jsonb(payload), event["created_at"]))
    return event


def record_reconciliation(report: dict) -> None:
    record_event("reconciliation_completed", "batch", DEMO_BATCH_ID, {
        "records_processed": report["records_processed"], "verified_matching_accuracy": report["verified_matching_accuracy"],
        "unresolved_exceptions": report["unresolved_exceptions"], "processing_time_ms": report["processing_time_ms"],
    })
    for decision in report["decisions"]:
        record_event("match_recorded" if decision["status"] == "matched" else "exception_recorded", "match_decision", decision["source_id"], decision)


def list_events(limit: int = 80) -> list[dict]:
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT id::text, event_type, entity_type, entity_id, payload, created_at
            FROM audit_events WHERE batch_id = %s ORDER BY created_at DESC LIMIT %s""", (DEMO_BATCH_ID, limit))
        return [{"id": row[0], "event_type": row[1], "entity_type": row[2], "entity_id": row[3], "payload": row[4], "created_at": row[5].isoformat()} for row in cursor.fetchall()]
