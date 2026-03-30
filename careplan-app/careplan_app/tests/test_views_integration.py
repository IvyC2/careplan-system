"""
Integration tests for all REST API endpoints.
Uses Django's test Client. Celery is suppressed by the autouse mock_celery_task fixture.
"""
import json
import datetime
import pytest
from django.utils import timezone

from careplan_app.models import Patient, Provider, Order, CarePlan


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/orders/
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
def test_create_order_success(api_client, valid_order_payload, mock_celery_task):
    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "Received"
    assert "order_id" in body
    assert "careplan_id" in body
    assert body["patient"]["mrn"] == "654321"
    assert body["provider"]["npi"] == "9876543210"
    assert body["care_plan"]["status"] == "pending"
    # Celery task was queued
    mock_celery_task.assert_called_once()


@pytest.mark.django_db
def test_create_order_invalid_json(api_client):
    response = api_client.post(
        "/api/orders/",
        data="not json{{",
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Invalid JSON"


@pytest.mark.django_db
def test_create_order_wrong_method(api_client):
    response = api_client.get("/api/orders/")
    assert response.status_code == 405


# ── Validation errors ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_create_order_invalid_npi(api_client, valid_order_payload):
    valid_order_payload["provider"]["npi"] = "123"
    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 400
    body = response.json()
    assert body["type"] == "VALIDATION_ERROR"
    assert body["code"] == "NPI_INVALID"


@pytest.mark.django_db
def test_create_order_invalid_mrn(api_client, valid_order_payload):
    valid_order_payload["patient"]["mrn"] = "12"
    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MRN_INVALID"


@pytest.mark.django_db
def test_create_order_invalid_diagnosis(api_client, valid_order_payload):
    valid_order_payload["primary_diagnosis"] = "bad-code"
    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "DIAGNOSIS_INVALID"


@pytest.mark.django_db
def test_create_order_invalid_patient_name(api_client, valid_order_payload):
    valid_order_payload["patient"]["first_name"] = "J0hn"
    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "PATIENT_NAME_INVALID"


@pytest.mark.django_db
def test_create_order_invalid_dob(api_client, valid_order_payload):
    valid_order_payload["patient"]["date_of_birth"] = "20-03-1990"
    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "DOB_INVALID"


@pytest.mark.django_db
def test_create_order_validation_fires_before_db_write(api_client, valid_order_payload):
    """Validation must reject before any Patient is written to the DB."""
    valid_order_payload["provider"]["npi"] = "BAD"
    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert Patient.objects.count() == 0  # no DB side effect


# ── Duplicate detection via API ────────────────────────────────────────────────

@pytest.mark.django_db
def test_create_order_same_day_duplicate_returns_409(api_client, valid_order_payload):
    # First request succeeds
    r1 = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert r1.status_code == 201

    # Second identical request → BlockError
    r2 = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert r2.status_code == 409
    body = r2.json()
    assert body["type"] == "BLOCK_ERROR"
    assert body["code"] == "DUPLICATE_ORDER_SAME_DAY"


@pytest.mark.django_db
def test_create_order_previous_day_duplicate_no_confirm_returns_warning(
    api_client, valid_order_payload, patient, provider
):
    yesterday = timezone.now() - datetime.timedelta(days=1)
    old = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name="Lisinopril",  # same as valid_order_payload
        primary_diagnosis="I10",
        additional_diagnoses=[],
        medication_history=[],
        patient_records="",
    )
    Order.objects.filter(pk=old.pk).update(created_at=yesterday)

    # Adjust payload to match existing patient
    valid_order_payload["patient"]["mrn"] = "123456"
    valid_order_payload["patient"]["first_name"] = "John"
    valid_order_payload["patient"]["last_name"] = "Doe"
    valid_order_payload["patient"]["date_of_birth"] = "1980-05-15"
    valid_order_payload["confirm"] = False

    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "WARNING"
    assert body["code"] == "DUPLICATE_ORDER_PREVIOUS"


@pytest.mark.django_db
def test_create_order_previous_day_duplicate_confirm_true_succeeds(
    api_client, valid_order_payload, patient, provider
):
    yesterday = timezone.now() - datetime.timedelta(days=1)
    old = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name="Lisinopril",
        primary_diagnosis="I10",
        additional_diagnoses=[],
        medication_history=[],
        patient_records="",
    )
    Order.objects.filter(pk=old.pk).update(created_at=yesterday)

    valid_order_payload["patient"]["mrn"] = "123456"
    valid_order_payload["patient"]["first_name"] = "John"
    valid_order_payload["patient"]["last_name"] = "Doe"
    valid_order_payload["patient"]["date_of_birth"] = "1980-05-15"
    valid_order_payload["confirm"] = True

    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 201


# ── Patient MRN data mismatch warning ────────────────────────────────────────

@pytest.mark.django_db
def test_create_order_patient_mrn_data_mismatch_returns_warning(
    api_client, valid_order_payload, patient
):
    # patient fixture has mrn=123456, name=John Doe, dob=1980-05-15
    valid_order_payload["patient"]["mrn"] = "123456"
    valid_order_payload["patient"]["first_name"] = "WrongName"  # mismatch
    valid_order_payload["patient"]["last_name"] = "Doe"
    valid_order_payload["patient"]["date_of_birth"] = "1980-05-15"

    response = api_client.post(
        "/api/orders/",
        data=json.dumps(valid_order_payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "WARNING"
    assert body["code"] == "PATIENT_MRN_DATA_MISMATCH"


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/orders/<id>/
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
def test_get_order_found(api_client, order, careplan):
    response = api_client.get(f"/api/orders/{order.pk}/")
    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == order.pk
    assert body["patient"]["mrn"] == "123456"
    assert body["care_plan"]["status"] == "pending"


@pytest.mark.django_db
def test_get_order_no_careplan(api_client, order):
    # order fixture exists but no CarePlan created
    response = api_client.get(f"/api/orders/{order.pk}/")
    assert response.status_code == 200
    assert response.json()["care_plan"] is None


@pytest.mark.django_db
def test_get_order_not_found(api_client):
    response = api_client.get("/api/orders/99999/")
    assert response.status_code == 404
    assert "not found" in response.json()["error"].lower()


@pytest.mark.django_db
def test_get_order_wrong_method(api_client, order):
    response = api_client.post(f"/api/orders/{order.pk}/")
    assert response.status_code == 405


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/careplan/<id>/status/
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
def test_careplan_status_pending(api_client, careplan):
    response = api_client.get(f"/api/careplan/{careplan.pk}/status/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert "content" not in body
    assert "error" not in body


@pytest.mark.django_db
def test_careplan_status_completed_includes_content(api_client, careplan):
    careplan.status = CarePlan.Status.COMPLETED
    careplan.content = "Care plan text here."
    careplan.save()

    response = api_client.get(f"/api/careplan/{careplan.pk}/status/")
    body = response.json()
    assert body["status"] == "completed"
    assert body["content"] == "Care plan text here."
    assert "error" not in body


@pytest.mark.django_db
def test_careplan_status_failed_includes_error(api_client, careplan):
    careplan.status = CarePlan.Status.FAILED
    careplan.content = "LLM call failed"
    careplan.save()

    response = api_client.get(f"/api/careplan/{careplan.pk}/status/")
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "LLM call failed"
    assert "content" not in body


@pytest.mark.django_db
def test_careplan_status_not_found(api_client):
    response = api_client.get("/api/careplan/99999/status/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_careplan_status_wrong_method(api_client, careplan):
    response = api_client.post(f"/api/careplan/{careplan.pk}/status/")
    assert response.status_code == 405
