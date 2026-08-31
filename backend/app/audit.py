from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from psycopg import connect
from psycopg.types.json import Jsonb


def _connection():
    return connect(os.environ["DATABASE_URL"])


def _new_event(event_type: str, entity_type: str, entity_id: str, payload: dict) -> dict:
    return {"id": str(uuid4()), "event_type": event_type, "entity_type": entity_type,
            "entity_id": entity_id, "payload": payload, "created_at": datetime.now(timezone.utc).isoformat()}


def _insert_event(cursor, batch_id: str, event: dict) -> None:
    cursor.execute("""INSERT INTO audit_events (id, batch_id, event_type, entity_type, entity_id, payload, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (event["id"], batch_id, event["event_type"], event["entity_type"], event["entity_id"], Jsonb(event["payload"]), event["created_at"]))


def record_event(batch_id: str, event_type: str, entity_type: str, entity_id: str, payload: dict) -> dict:
    event = _new_event(event_type, entity_type, entity_id, payload)
    with _connection() as connection, connection.cursor() as cursor:
        _insert_event(cursor, batch_id, event)
    return event


def record_reconciliation(batch_id: str, report: dict) -> None:
    events = [_new_event("reconciliation_completed", "batch", batch_id, {
        "records_processed": report["records_processed"], "verified_matching_accuracy": report["verified_matching_accuracy"],
        "unresolved_exceptions": report["unresolved_exceptions"], "processing_time_ms": report["processing_time_ms"],
    })]
    events.extend(_new_event("match_recorded" if decision["status"] == "matched" else "exception_recorded", "match_decision", decision["source_id"], decision) for decision in report["decisions"])
    with _connection() as connection, connection.cursor() as cursor:
        for event in events:
            _insert_event(cursor, batch_id, event)


def list_events(batch_id: str, limit: int = 80) -> list[dict]:
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT id::text, event_type, entity_type, entity_id, payload, created_at
            FROM audit_events WHERE batch_id = %s ORDER BY created_at DESC LIMIT %s""", (batch_id, limit))
        return [{"id": row[0], "event_type": row[1], "entity_type": row[2], "entity_id": row[3], "payload": row[4], "created_at": row[5].isoformat()} for row in cursor.fetchall()]


def find_available_advisory(batch_id: str, advisory_id: str, source_id: str) -> dict | None:
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT id::text, payload, created_at FROM audit_events
            WHERE id = %s AND batch_id = %s AND entity_id = %s AND event_type = 'ai_analysis_available'""",
            (advisory_id, batch_id, source_id))
        row = cursor.fetchone()
    if not row or not isinstance(row[1], dict) or row[1].get("status") != "available" or not row[1].get("recommendation"):
        return None
    return {"id": row[0], "payload": row[1], "created_at": row[2].isoformat()}
