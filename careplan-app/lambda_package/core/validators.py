"""
core/validators.py — Framework-agnostic input validation.

Extracted from careplan_app/serializers.py: validate_order_input().
Only stdlib dependencies (re, datetime) + core.exceptions.
"""

import re
from datetime import datetime

from core.exceptions import ValidationError


def validate_order_input(data: dict) -> None:
    """
    验证 parse_create_order_body() 返回的数据。
    有任何问题就 raise ValidationError。
    """
    patient  = data.get('patient', {})
    provider = data.get('provider') or {}

    npi                  = provider.get('npi')
    mrn                  = patient.get('mrn')
    diagnosis            = data.get('primary_diagnosis')
    additional_diagnoses = data.get('additional_diagnoses', [])

    patient_fname  = patient.get('first_name')
    patient_lname  = patient.get('last_name')
    provider_fname = provider.get('first_name')
    provider_lname = provider.get('last_name')

    if not re.match(r'^\d{10}$', str(npi or '')):
        raise ValidationError("NPI must be exactly 10 digits", code="NPI_INVALID")

    if not re.match(r'^\d{6}$', str(mrn or '')):
        raise ValidationError("MRN must be exactly 6 digits", code="MRN_INVALID")

    if not re.match(r'^[A-Z]\d{2}(\.\d{1,4})?$', str(diagnosis or '')):
        raise ValidationError("ICD-10 format is incorrect", code="DIAGNOSIS_INVALID")

    for dx in additional_diagnoses:
        if not re.match(r'^[A-Z]\d{2}(\.\d{1,4})?$', str(dx or '')):
            raise ValidationError(f"Invalid ICD-10 code: {dx}", code="DIAGNOSIS_INVALID")

    patient_fname = (patient_fname or '').strip()
    if not re.match(r'^[A-Za-z\s]+$', str(patient_fname or '')):
        raise ValidationError("The patient's firstname should not be empty.", code="PATIENT_NAME_INVALID")

    patient_lname = (patient_lname or '').strip()
    if not re.match(r'^[A-Za-z\s]+$', str(patient_lname or '')):
        raise ValidationError("The patient's lastname should not be empty.", code="PATIENT_NAME_INVALID")

    provider_fname = (provider_fname or '').strip()
    if not re.match(r'^[A-Za-z\s]+$', str(provider_fname or '')):
        raise ValidationError("The provider's firstname should not be empty.", code="PROVIDER_NAME_INVALID")

    provider_lname = (provider_lname or '').strip()
    if not re.match(r'^[A-Za-z\s]+$', str(provider_lname or '')):
        raise ValidationError("The provider's lastname should not be empty.", code="PROVIDER_NAME_INVALID")

    dob = patient.get('date_of_birth')
    try:
        datetime.strptime(str(dob or ''), '%Y-%m-%d')
    except ValueError:
        raise ValidationError("date_of_birth must be in YYYY-MM-DD format", code="DOB_INVALID")
