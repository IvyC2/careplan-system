"""
lambdas/create_order.py

POST /orders

Request body (JSON):
{
    "patient": {
        "first_name": "John",
        "last_name":  "Doe",
        "mrn":        "123456",
        "date_of_birth": "1990-01-01"
    },
    "provider": {
        "first_name": "Jane",
        "last_name":  "Smith",
        "npi":        "1234567890"
    },
    "medication_name":      "IVIG",
    "primary_diagnosis":    "G70.01",
    "additional_diagnoses": [],
    "medication_history":   [],
    "patient_records":      "",
    "confirm":              false
}

Environment variables required:
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, SQS_QUEUE_URL
"""

import json
import logging
import os
import urllib.parse

import psycopg2
import psycopg2.extras

from core.db import PostgresDB
from core.exceptions import BlockError, ValidationError, WarningException
from core.queue import SQSQueue
from core.services import (
    create_order_and_careplan,
    get_or_create_default_provider,
    get_or_create_patient,
    get_or_create_provider,
)
from core.validators import validate_order_input

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Helpers (same DSN pattern as get_order.py)
# ---------------------------------------------------------------------------

def _get_conn():
    password = urllib.parse.quote(os.environ["DB_PASSWORD"], safe="")
    dsn = (
        f"postgresql://{os.environ['DB_USER']}:{password}"
        f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', 5432)}/{os.environ['DB_NAME']}"
        f"?connect_timeout=5&sslmode=require"
    )
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _resp(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handler(event, context):

    # ── 1. parse body ────────────────────────────────────────────────────────
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError as exc:
        return _resp(400, {
            "error":  "Invalid JSON body",
            "code":   "INVALID_JSON",
            "detail": str(exc),
        })

    confirm = bool(body.get("confirm", False))

    # ── 2. validate input ────────────────────────────────────────────────────
    try:
        validate_order_input(body)
    except ValidationError as exc:
        return _resp(400, {"error": exc.message, "code": exc.code})

    # ── 3. extract structured fields ─────────────────────────────────────────
    patient_data  = body.get("patient", {})
    provider_data = body.get("provider") or {}

    # ── 4. DB + business logic ───────────────────────────────────────────────
    conn = None
    try:
        conn  = _get_conn()
        db    = PostgresDB(conn)
        queue = SQSQueue(queue_url=os.environ["SQS_QUEUE_URL"])

        # --- patient (get or create, with MRN / DOB duplicate detection) ---
        patient = get_or_create_patient(
            db,
            first_name    = patient_data.get("first_name", ""),
            last_name     = patient_data.get("last_name", ""),
            mrn           = patient_data.get("mrn"),
            date_of_birth = patient_data.get("date_of_birth"),
        )

        # --- provider (get or create, with NPI conflict detection) ----------
        prov_first = provider_data.get("first_name", "")
        prov_last  = provider_data.get("last_name", "")
        prov_npi   = provider_data.get("npi")

        if prov_npi or prov_first or prov_last:
            provider = get_or_create_provider(db, prov_first, prov_last, npi=prov_npi)
        else:
            provider = get_or_create_default_provider(db)

        # --- order + careplan (duplicate check + INSERT + SQS enqueue) ------
        order, care_plan = create_order_and_careplan(
            db                   = db,
            queue                = queue,
            patient              = patient,
            provider             = provider,
            medication_name      = body.get("medication_name", ""),
            primary_diagnosis    = body.get("primary_diagnosis", ""),
            additional_diagnoses = body.get("additional_diagnoses", []),
            medication_history   = body.get("medication_history", []),
            patient_records      = body.get("patient_records", ""),
            confirm              = confirm,
        )

        logger.info("Order created: order_id=%s careplan_id=%s", order.pk, care_plan.pk)

        return _resp(200, {
            "message":    "Received",
            "order_id":    order.pk,
            "careplan_id": care_plan.pk,
            "patient": {
                "id":         patient.pk,
                "first_name": patient.first_name,
                "last_name":  patient.last_name,
                "mrn":        patient.mrn,
            },
            "provider": {
                "id":         provider.pk,
                "first_name": provider.first_name,
                "last_name":  provider.last_name,
                "npi":        provider.npi,
            },
        })

    # ── 5. business-rule errors ──────────────────────────────────────────────

    except BlockError as exc:
        # e.g. same-day duplicate order, NPI name conflict
        logger.warning("BlockError: %s [%s]", exc.message, exc.code)
        return _resp(409, {"error": exc.message, "code": exc.code})

    except WarningException as exc:
        # e.g. previous order for same medication, MRN data mismatch
        # caller should re-send with "confirm": true to proceed
        logger.warning("WarningException: %s [%s]", exc.message, exc.code)
        return _resp(200, {
            "warning": exc.message,
            "code":    exc.code,
            "hint":    'Re-send the request with "confirm": true to proceed anyway.',
        })

    # ── 6. infrastructure errors ─────────────────────────────────────────────

    except psycopg2.OperationalError as exc:
        logger.exception("Database connection failed")
        return _resp(500, {
            "error":  "Database connection failed",
            "code":   "DB_CONNECTION_ERROR",
            "detail": str(exc),
        })

    except psycopg2.Error as exc:
        logger.exception("Database query failed")
        return _resp(500, {
            "error":  "Database query failed",
            "code":   "DB_QUERY_ERROR",
            "detail": str(exc),
        })

    except Exception as exc:
        logger.exception("Unexpected error")
        return _resp(500, {
            "error":  "Internal server error",
            "code":   "INTERNAL_ERROR",
            "detail": str(exc),
        })

    finally:
        if conn is not None:
            conn.close()
