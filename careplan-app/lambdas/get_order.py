"""
lambdas/get_order.py

GET /orders/{order_id}

Environment variables required:
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

import json
import logging
import os
import urllib.parse

import psycopg2
import psycopg2.extras

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL = """
SELECT
    o.id                    AS order_id,
    o.medication_name,
    o.primary_diagnosis,
    o.additional_diagnoses,
    o.medication_history,
    o.patient_records,
    o.created_at,

    pt.id                   AS patient_id,
    pt.first_name           AS patient_first_name,
    pt.last_name            AS patient_last_name,
    pt.mrn                  AS patient_mrn,
    pt.date_of_birth        AS patient_dob,

    pv.id                   AS provider_id,
    pv.first_name           AS provider_first_name,
    pv.last_name            AS provider_last_name,
    pv.npi                  AS provider_npi,

    cp.id                   AS careplan_id,
    cp.status               AS careplan_status,
    cp.content              AS careplan_content,
    cp.created_at           AS careplan_created_at,
    cp.updated_at           AS careplan_updated_at

FROM careplan_app_order AS o
JOIN careplan_app_patient  AS pt ON pt.id = o.patient_id
JOIN careplan_app_provider AS pv ON pv.id = o.provider_id
LEFT JOIN careplan_app_careplan AS cp ON cp.order_id = o.id

WHERE o.id = %(order_id)s
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_conn():
    password = urllib.parse.quote(os.environ["DB_PASSWORD"], safe="")
    dsn = (
        f"postgresql://{os.environ['DB_USER']}:{password}"
        f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', 5432)}/{os.environ['DB_NAME']}"
        f"?connect_timeout=5"
    )
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),  # default=str handles date/datetime
    }


def _build_response(row: dict) -> dict:
    care_plan = None
    if row["careplan_id"] is not None:
        care_plan = {
            "id":         row["careplan_id"],
            "status":     row["careplan_status"],
            "content":    row["careplan_content"] or "",
            "created_at": row["careplan_created_at"].isoformat() if row["careplan_created_at"] else None,
            "updated_at": row["careplan_updated_at"].isoformat() if row["careplan_updated_at"] else None,
        }

    return {
        "order_id": row["order_id"],
        "patient": {
            "id":           row["patient_id"],
            "first_name":   row["patient_first_name"],
            "last_name":    row["patient_last_name"],
            "mrn":          row["patient_mrn"],
            "date_of_birth": str(row["patient_dob"]),
        },
        "provider": {
            "id":         row["provider_id"],
            "first_name": row["provider_first_name"],
            "last_name":  row["provider_last_name"],
            "npi":        row["provider_npi"],
        },
        "medication_name":      row["medication_name"],
        "primary_diagnosis":    row["primary_diagnosis"],
        "additional_diagnoses": row["additional_diagnoses"] or [],
        "medication_history":   row["medication_history"] or [],
        "patient_records":      row["patient_records"] or "",
        "created_at":           row["created_at"].isoformat(),
        "care_plan":            care_plan,
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handler(event, context):
    # --- parse order_id from path parameters ---
    path_params = event.get("pathParameters") or {}
    raw_id = path_params.get("order_id") or path_params.get("id")

    if not raw_id:
        return _json_response(400, {
            "error": "Missing path parameter: order_id",
            "code": "MISSING_PATH_PARAM",
        })

    try:
        order_id = int(raw_id)
    except (ValueError, TypeError):
        return _json_response(400, {
            "error": f"order_id must be an integer, got: {raw_id!r}",
            "code": "INVALID_PATH_PARAM",
        })

    # --- query ---
    conn = None
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(_SQL, {"order_id": order_id})
            row = cur.fetchone()

        if row is None:
            logger.info("Order not found: order_id=%s", order_id)
            return _json_response(404, {
                "error": f"Order {order_id} not found",
                "code": "ORDER_NOT_FOUND",
            })

        logger.info("Order fetched: order_id=%s", order_id)
        return _json_response(200, _build_response(dict(row)))

    except psycopg2.OperationalError as exc:
        logger.exception("Database connection failed")
        return _json_response(500, {
            "error": "Database connection failed",
            "code": "DB_CONNECTION_ERROR",
            "detail": str(exc),
        })

    except psycopg2.Error as exc:
        logger.exception("Database query failed: order_id=%s", order_id)
        return _json_response(500, {
            "error": "Database query failed",
            "code": "DB_QUERY_ERROR",
            "detail": str(exc),
        })

    finally:
        if conn is not None:
            conn.close()
