"""
Unit tests for serializers.validate_order_input — all error branches and happy paths.
No database access required (pure Python logic).
"""
import pytest

from careplan_app.serializers import validate_order_input
from careplan_app.exceptions import ValidationError


# ── Shared base fixture ────────────────────────────────────────────────────────

@pytest.fixture
def valid_data():
    """Fully-valid input dict. Each test mutates only the field under test."""
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
        "medication_history": [],
        "patient_records": "",
    }


# ══════════════════════════════════════════════════════════════════════════════
# NPI validation
# ══════════════════════════════════════════════════════════════════════════════

def test_npi_none_raises(valid_data):
    valid_data["provider"]["npi"] = None
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "NPI_INVALID"


def test_npi_too_short_raises(valid_data):
    valid_data["provider"]["npi"] = "123456789"  # 9 digits
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "NPI_INVALID"


def test_npi_too_long_raises(valid_data):
    valid_data["provider"]["npi"] = "12345678901"  # 11 digits
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "NPI_INVALID"


def test_npi_with_letters_raises(valid_data):
    valid_data["provider"]["npi"] = "123456789A"
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "NPI_INVALID"


def test_npi_valid_passes(valid_data):
    validate_order_input(valid_data)  # should not raise


# ══════════════════════════════════════════════════════════════════════════════
# MRN validation
# ══════════════════════════════════════════════════════════════════════════════

def test_mrn_none_raises(valid_data):
    valid_data["patient"]["mrn"] = None
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "MRN_INVALID"


def test_mrn_five_digits_raises(valid_data):
    valid_data["patient"]["mrn"] = "12345"
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "MRN_INVALID"


def test_mrn_seven_digits_raises(valid_data):
    valid_data["patient"]["mrn"] = "1234567"
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "MRN_INVALID"


def test_mrn_with_letters_raises(valid_data):
    valid_data["patient"]["mrn"] = "A23456"
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "MRN_INVALID"


# ══════════════════════════════════════════════════════════════════════════════
# Primary diagnosis (ICD-10) validation
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bad_code", [
    "",            # empty
    "i10",         # lowercase
    "1I0",         # starts with digit
    "AB1",         # two letters at start
    "A1",          # missing third digit
    "A123.12345",  # decimal part too long (5 chars)
])
def test_primary_diagnosis_invalid(valid_data, bad_code):
    valid_data["primary_diagnosis"] = bad_code
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "DIAGNOSIS_INVALID"


@pytest.mark.parametrize("good_code", ["A00", "Z99", "E11.9", "J18.123", "I10"])
def test_primary_diagnosis_valid(valid_data, good_code):
    valid_data["primary_diagnosis"] = good_code
    validate_order_input(valid_data)  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# Additional diagnoses validation
# ══════════════════════════════════════════════════════════════════════════════

def test_additional_diagnoses_invalid_member_raises(valid_data):
    valid_data["additional_diagnoses"] = ["E11.9", "bad-code"]
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "DIAGNOSIS_INVALID"
    assert "bad-code" in exc.value.message


def test_additional_diagnoses_empty_list_passes(valid_data):
    valid_data["additional_diagnoses"] = []
    validate_order_input(valid_data)  # no exception


def test_additional_diagnoses_multiple_valid_passes(valid_data):
    valid_data["additional_diagnoses"] = ["A00", "Z99", "J18.9"]
    validate_order_input(valid_data)


# ══════════════════════════════════════════════════════════════════════════════
# Patient name validation
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bad_name,field", [
    ("", "first_name"),
    ("123", "first_name"),
    ("John2", "first_name"),
    ("O'Brien", "first_name"),   # apostrophe not in [A-Za-z\s]
    ("", "last_name"),
    ("Doe-Smith", "last_name"),  # hyphen not allowed
])
def test_patient_name_invalid(valid_data, bad_name, field):
    valid_data["patient"][field] = bad_name
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "PATIENT_NAME_INVALID"


def test_patient_name_spaces_allowed(valid_data):
    valid_data["patient"]["first_name"] = "Mary Ann"
    validate_order_input(valid_data)  # spaces are valid


# ══════════════════════════════════════════════════════════════════════════════
# Provider name validation
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bad_name,field", [
    ("", "first_name"),
    ("Dr3", "first_name"),
    ("", "last_name"),
    ("Smith-Jones", "last_name"),  # hyphen not in [A-Za-z\s]
])
def test_provider_name_invalid(valid_data, bad_name, field):
    valid_data["provider"][field] = bad_name
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "PROVIDER_NAME_INVALID"


def test_provider_name_spaces_allowed(valid_data):
    valid_data["provider"]["first_name"] = "Mary Ann"
    validate_order_input(valid_data)


# ══════════════════════════════════════════════════════════════════════════════
# Date of birth validation
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bad_dob", [
    "",
    "03-20-1990",   # MM-DD-YYYY
    "1990/03/20",   # slashes
    "19900320",     # no separators
    "not-a-date",
    None,
])
def test_dob_invalid(valid_data, bad_dob):
    valid_data["patient"]["date_of_birth"] = bad_dob
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "DOB_INVALID"


def test_dob_valid_passes(valid_data):
    valid_data["patient"]["date_of_birth"] = "2000-12-31"
    validate_order_input(valid_data)


# ══════════════════════════════════════════════════════════════════════════════
# Validation order: NPI checked before MRN
# ══════════════════════════════════════════════════════════════════════════════

def test_validation_order_npi_before_mrn(valid_data):
    valid_data["provider"]["npi"] = "bad"
    valid_data["patient"]["mrn"] = "bad"
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "NPI_INVALID"  # NPI check fires first


# ══════════════════════════════════════════════════════════════════════════════
# No provider in data (provider=None) → NPI_INVALID (default {} has no NPI)
# ══════════════════════════════════════════════════════════════════════════════

def test_no_provider_key_raises_npi_invalid(valid_data):
    valid_data["provider"] = None
    with pytest.raises(ValidationError) as exc:
        validate_order_input(valid_data)
    assert exc.value.code == "NPI_INVALID"
