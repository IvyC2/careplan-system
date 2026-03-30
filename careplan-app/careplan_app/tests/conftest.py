import json
import pytest
from django.test import Client
from unittest.mock import patch

from careplan_app.models import Patient, Provider, Order, CarePlan


# ── Database fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def patient(db):
    return Patient.objects.create(
        first_name="John",
        last_name="Doe",
        mrn="123456",
        date_of_birth="1980-05-15",
    )


@pytest.fixture
def provider(db):
    return Provider.objects.create(
        first_name="Alice",
        last_name="Smith",
        npi="1234567890",
    )


@pytest.fixture
def order(db, patient, provider):
    return Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name="Metformin",
        primary_diagnosis="E11.9",
        additional_diagnoses=[],
        medication_history=[],
        patient_records="",
    )


@pytest.fixture
def careplan(db, order):
    return CarePlan.objects.create(order=order, status=CarePlan.Status.PENDING)


# ── Celery mock (autouse — suppresses .delay() in every test) ─────────────────

@pytest.fixture(autouse=True)
def mock_celery_task():
    with patch("careplan_app.tasks.generate_careplan_task.delay") as mock_delay:
        yield mock_delay


# ── HTTP client ───────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return Client()


# ── Valid order payload ────────────────────────────────────────────────────────

@pytest.fixture
def valid_order_payload():
    return {
        "patient": {
            "first_name": "Jane",
            "last_name": "Doe",
            "mrn": "654321",
            "date_of_birth": "1990-03-20",
        },
        "provider": {
            "first_name": "Bob",
            "last_name": "Jones",
            "npi": "9876543210",
        },
        "medication_name": "Lisinopril",
        "primary_diagnosis": "I10",
        "additional_diagnoses": ["E11.9"],
        "medication_history": ["Metformin 500mg"],
        "patient_records": "No known allergies.",
        "confirm": False,
    }
