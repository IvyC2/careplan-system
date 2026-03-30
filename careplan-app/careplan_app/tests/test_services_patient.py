"""
Unit tests for services.get_or_create_patient — all 11 paths.
Target: 90%+ coverage of the duplicate-detection branch logic.
"""
import re
import pytest
from unittest.mock import patch

from careplan_app.models import Patient
from careplan_app.services import get_or_create_patient
from careplan_app.exceptions import WarningException


# ── P1: MRN given + patient found + name AND DOB match → return existing ──────

@pytest.mark.django_db
def test_mrn_match_exact_returns_existing(patient):
    result = get_or_create_patient(
        first_name="John",
        last_name="Doe",
        mrn="123456",
        date_of_birth="1980-05-15",
    )
    assert result.pk == patient.pk
    assert Patient.objects.count() == 1  # no new record created


# ── P2: MRN given + patient found + name mismatch → PATIENT_MRN_DATA_MISMATCH ─

@pytest.mark.django_db
def test_mrn_name_mismatch_raises_warning(patient):
    with pytest.raises(WarningException) as exc_info:
        get_or_create_patient(
            first_name="Jane",  # wrong first name
            last_name="Doe",
            mrn="123456",
            date_of_birth="1980-05-15",
        )
    assert exc_info.value.code == "PATIENT_MRN_DATA_MISMATCH"
    assert "name" in exc_info.value.message.lower()


# ── P2b: MRN given + patient found + DOB mismatch → PATIENT_MRN_DATA_MISMATCH ─

@pytest.mark.django_db
def test_mrn_dob_mismatch_raises_warning(patient):
    with pytest.raises(WarningException) as exc_info:
        get_or_create_patient(
            first_name="John",
            last_name="Doe",
            mrn="123456",
            date_of_birth="1990-01-01",  # wrong DOB
        )
    assert exc_info.value.code == "PATIENT_MRN_DATA_MISMATCH"
    assert "date_of_birth" in exc_info.value.message.lower()


# ── P2c: MRN given + both name AND DOB mismatched → message mentions both ─────

@pytest.mark.django_db
def test_mrn_name_and_dob_mismatch_mentions_both(patient):
    with pytest.raises(WarningException) as exc_info:
        get_or_create_patient(
            first_name="Jane",
            last_name="Smith",
            mrn="123456",
            date_of_birth="1999-12-31",
        )
    assert exc_info.value.code == "PATIENT_MRN_DATA_MISMATCH"
    msg = exc_info.value.message
    assert "name" in msg.lower()
    assert "date_of_birth" in msg.lower()


# ── P3: MRN given + not in DB + name+DOB conflict → PATIENT_MRN_CONFLICT ──────

@pytest.mark.django_db
def test_mrn_conflict_raises_warning(patient):
    # patient fixture has mrn=123456; try same name+DOB with different MRN
    with pytest.raises(WarningException) as exc_info:
        get_or_create_patient(
            first_name="John",
            last_name="Doe",
            mrn="999999",  # different MRN
            date_of_birth="1980-05-15",
        )
    assert exc_info.value.code == "PATIENT_MRN_CONFLICT"
    assert "123456" in exc_info.value.message  # existing MRN in message
    assert "999999" in exc_info.value.message  # provided MRN in message


# ── P4: MRN given + not in DB + no conflict → create new patient ──────────────

@pytest.mark.django_db
def test_mrn_new_patient_created():
    result = get_or_create_patient(
        first_name="Alice",
        last_name="Wonder",
        mrn="111111",
        date_of_birth="2000-01-01",
    )
    assert result.pk is not None
    assert result.mrn == "111111"
    assert Patient.objects.count() == 1


# ── P4b: MRN given + no DOB → default DOB "2000-01-01" applied ───────────────

@pytest.mark.django_db
def test_mrn_no_dob_uses_default():
    result = get_or_create_patient(
        first_name="Alice",
        last_name="Wonder",
        mrn="222222",
        date_of_birth=None,
    )
    assert str(result.date_of_birth) == "2000-01-01"


# ── P5: No MRN + name+DOB match → return existing ────────────────────────────

@pytest.mark.django_db
def test_no_mrn_name_dob_match_returns_existing(patient):
    result = get_or_create_patient(
        first_name="John",
        last_name="Doe",
        date_of_birth="1980-05-15",
    )
    assert result.pk == patient.pk
    assert Patient.objects.count() == 1


# ── P5b: No MRN + no DOB + name match → return existing ──────────────────────

@pytest.mark.django_db
def test_no_mrn_no_dob_name_match_returns_existing(patient):
    result = get_or_create_patient(first_name="John", last_name="Doe")
    assert result.pk == patient.pk


# ── P6: No MRN + no match → create with random 6-digit MRN ──────────────────

@pytest.mark.django_db
def test_no_mrn_no_match_creates_with_random_mrn():
    result = get_or_create_patient(
        first_name="Carol",
        last_name="New",
        date_of_birth="1995-07-07",
    )
    assert result.pk is not None
    assert re.match(r"^\d{6}$", result.mrn), f"MRN '{result.mrn}' is not 6 digits"


# ── P6b: MRN collision loop → retries until a free MRN is found ──────────────

@pytest.mark.django_db
def test_random_mrn_collision_retries():
    # Pre-occupy 111111 so the first random attempt collides
    Patient.objects.create(
        first_name="X", last_name="Y", mrn="111111", date_of_birth="2000-01-01"
    )
    with patch("careplan_app.services.random.randint", side_effect=[111111, 222222]):
        result = get_or_create_patient(
            first_name="New",
            last_name="Person",
            date_of_birth="1985-05-05",
        )
    assert result.mrn == "222222"


# ── Edge: DOB is None → treated as "match any DOB" for MRN lookup ─────────────

@pytest.mark.django_db
def test_mrn_match_with_none_dob_treated_as_match(patient):
    # dob_match = (date_of_birth is None or ...) → True when date_of_birth is None
    result = get_or_create_patient(
        first_name="John",
        last_name="Doe",
        mrn="123456",
        date_of_birth=None,
    )
    assert result.pk == patient.pk
