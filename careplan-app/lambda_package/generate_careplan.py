"""
lambdas/generate_careplan.py

SQS trigger — processes care plan generation jobs.

SQS message body: {"careplan_id": 6}

Each Lambda invocation receives a batch of 1–10 SQS records.
Records are processed independently: a failure in one message does not
block the rest of the batch.

Failed message IDs are reported via batchItemFailures so SQS retries
only those messages (requires "Report batch item failures" enabled on
the event source mapping).

Status flow:
    pending → processing → completed
                        ↘ failed  (retried by SQS up to maxReceiveCount)

Environment variables required:
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    LLM_API_KEY
    LLM_PROVIDER   (claude | mock, default: claude)

Recommended Lambda configuration:
    Timeout : 300 s  (5 min — LLM calls can be slow)
    Memory  : 256 MB
"""

import json
import logging
import os
import urllib.parse

import psycopg2
import psycopg2.extras

from core.llm import get_llm_service

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL_FETCH = """
SELECT
    cp.id               AS careplan_id,
    cp.status           AS careplan_status,
    o.medication_name,
    o.primary_diagnosis,
    o.additional_diagnoses,
    o.medication_history,
    o.patient_records,
    pt.first_name,
    pt.last_name
FROM careplan_app_careplan AS cp
JOIN careplan_app_order   AS o  ON o.id  = cp.order_id
JOIN careplan_app_patient AS pt ON pt.id = o.patient_id
WHERE cp.id = %(careplan_id)s
"""

_SQL_SET_PROCESSING = """
UPDATE careplan_app_careplan
SET status = 'processing', updated_at = NOW()
WHERE id = %(careplan_id)s
"""

_SQL_SET_COMPLETED = """
UPDATE careplan_app_careplan
SET status = 'completed', content = %(content)s, updated_at = NOW()
WHERE id = %(careplan_id)s
"""

_SQL_SET_FAILED = """
UPDATE careplan_app_careplan
SET status = 'failed', updated_at = NOW()
WHERE id = %(careplan_id)s
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_conn():
    password = urllib.parse.quote(os.environ["DB_PASSWORD"], safe="")
    dsn = (
        f"postgresql://{os.environ['DB_USER']}:{password}"
        f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', 5432)}/{os.environ['DB_NAME']}"
        f"?connect_timeout=5&sslmode=require"
    )
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _mark_failed(careplan_id: int, conn) -> None:
    """Best-effort: update status to failed. Swallows its own errors."""
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL_SET_FAILED, {"careplan_id": careplan_id})
        conn.commit()
        logger.info("Marked careplan as failed: careplan_id=%s", careplan_id)
    except Exception:
        logger.exception("Could not mark careplan as failed: careplan_id=%s", careplan_id)


def _process_one(careplan_id: int, conn) -> None:
    """
    Fetch → mark processing → call LLM → mark completed.
    Raises on any error (caller handles marking as failed).
    """
    # 1. fetch careplan + order + patient in one query
    with conn.cursor() as cur:
        cur.execute(_SQL_FETCH, {"careplan_id": careplan_id})
        row = cur.fetchone()

    if row is None:
        # message points at a deleted row — nothing to do, don't retry
        logger.warning("CarePlan not found: careplan_id=%s — skipping", careplan_id)
        return

    # idempotency guard: skip if already completed by a previous attempt
    if row["careplan_status"] == "completed":
        logger.info("CarePlan already completed: careplan_id=%s — skipping", careplan_id)
        return

    logger.info(
        "Processing careplan_id=%s (status: %s, patient: %s %s)",
        careplan_id, row["careplan_status"], row["first_name"], row["last_name"],
    )

    # 2. mark processing
    with conn.cursor() as cur:
        cur.execute(_SQL_SET_PROCESSING, {"careplan_id": careplan_id})
    conn.commit()

    # 3. call LLM  (may raise — caller will mark as failed)
    llm = get_llm_service()
    content = llm.generate(
        patient_name=f"{row['first_name']} {row['last_name']}",
        medication=row["medication_name"],
        diagnosis=row["primary_diagnosis"],
        additional_diagnoses=row["additional_diagnoses"] or [],
        medication_history=row["medication_history"] or [],
        patient_records=row["patient_records"] or "",
    )

    # 4. mark completed
    with conn.cursor() as cur:
        cur.execute(_SQL_SET_COMPLETED, {"careplan_id": careplan_id, "content": content})
    conn.commit()

    logger.info("CarePlan completed: careplan_id=%s", careplan_id)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handler(event, context):
    """
    SQS event shape:
        {
            "Records": [
                {
                    "messageId": "abc-123",
                    "body": "{\"careplan_id\": 6}",
                    ...
                },
                ...
            ]
        }
    """
    failed_message_ids = []

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")

        # ── parse SQS message body ────────────────────────────────────────
        try:
            body = json.loads(record["body"])
            careplan_id = int(body["careplan_id"])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            # Malformed message — can never succeed; let it reach the DLQ
            logger.error(
                "Malformed SQS message: messageId=%s body=%r error=%s",
                message_id, record.get("body"), exc,
            )
            failed_message_ids.append(message_id)
            continue

        # ── process ──────────────────────────────────────────────────────
        conn = None
        try:
            conn = _get_conn()
            _process_one(careplan_id, conn)

        except psycopg2.OperationalError:
            # DB unreachable — don't mark failed (DB is down), just retry
            logger.exception("DB connection error: careplan_id=%s", careplan_id)
            failed_message_ids.append(message_id)

        except Exception:
            # LLM error, query error, etc. — mark failed then retry
            logger.exception("Error processing careplan: careplan_id=%s", careplan_id)
            if conn is not None:
                _mark_failed(careplan_id, conn)
            failed_message_ids.append(message_id)

        finally:
            if conn is not None:
                conn.close()

    # Return batchItemFailures so SQS retries only the failed messages.
    # Requires "Report batch item failures" enabled on the event source mapping.
    if failed_message_ids:
        return {
            "batchItemFailures": [
                {"itemIdentifier": mid} for mid in failed_message_ids
            ]
        }
