from .models import CarePlan
from .exceptions import ValidationError
import re
from datetime import datetime

# -----------------------------------------------------------------------------
# Input parsers — raw request data → structured Python dict
# -----------------------------------------------------------------------------

def parse_legacy_form(post_data) -> dict:
    """
    Extracts fields from a legacy form POST (request.POST).
    从旧版表单 POST 中提取字段。
    Source: views.py lines 133–136
    """
    return {
        'first_name': post_data.get('first_name', '').strip(),
        'last_name':  post_data.get('last_name', '').strip(),
        'medication': post_data.get('medication', '').strip(),
        'diagnosis':  post_data.get('diagnosis', '').strip(),
    }


def parse_create_order_body(body: dict) -> dict:
    """
    Extracts patient, provider, and order fields from a JSON request body.
    从 JSON 请求体中提取患者、提供者和医嘱字段。
    Source: views.py lines 211–236
    """
    patient_data  = body.get('patient', {})
    provider_data = body.get('provider')

    return {
        'patient': {
            'first_name':    patient_data.get('first_name', ''),
            'last_name':     patient_data.get('last_name', ''),
            'mrn':           patient_data.get('mrn'),
            'date_of_birth': patient_data.get('date_of_birth'),
        },
        'provider': {
            'first_name': provider_data.get('first_name', ''),
            'last_name':  provider_data.get('last_name', ''),
            'npi':        provider_data.get('npi'),
        } if provider_data is not None else None,
        'medication_name':      body.get('medication_name', ''),
        'primary_diagnosis':    body.get('primary_diagnosis', ''),
        'additional_diagnoses': body.get('additional_diagnoses', []),
        'medication_history':   body.get('medication_history', []),
        'patient_records':      body.get('patient_records', ''),
    }


# -----------------------------------------------------------------------------
# Response formatters — ORM objects → dict ready for JsonResponse
# -----------------------------------------------------------------------------

def serialize_legacy_careplan_response(order, care_plan) -> dict:
    """
    Formats the response for the legacy generate_careplan endpoint.
    Source: views.py lines 154–166
    """
    return {
        'message':    'Received',
        'careplan_id': care_plan.pk,
        'order_id':    order.pk,
        'care_plan': {
            'id':      care_plan.pk,
            'status':  care_plan.status,
            'content': care_plan.content,
        },
    }


def serialize_create_order_response(patient, provider, order, care_plan) -> dict:
    """
    Formats the full response for the api_create_order endpoint.
    Source: views.py lines 256–288
    """
    return {
        'message':    'Received',
        'careplan_id': care_plan.pk,
        'order_id':    order.pk,
        'patient': {
            'id':         patient.pk,
            'first_name': patient.first_name,
            'last_name':  patient.last_name,
            'mrn':        patient.mrn,
        },
        'provider': {
            'id':         provider.pk,
            'first_name': provider.first_name,
            'last_name':  provider.last_name,
            'npi':        provider.npi,
        },
        'medication_name':      order.medication_name,
        'primary_diagnosis':    order.primary_diagnosis,
        'additional_diagnoses': order.additional_diagnoses,
        'medication_history':   order.medication_history,
        'patient_records':      order.patient_records,
        'created_at':           order.created_at.isoformat(),
        'care_plan': {
            'id':         care_plan.pk,
            'status':     care_plan.status,
            'content':    care_plan.content,
            'created_at': care_plan.created_at.isoformat(),
            'updated_at': care_plan.updated_at.isoformat(),
        },
    }


def serialize_get_order_response(order) -> dict:
    """
    Formats the response for the api_get_order endpoint.
    Source: views.py lines 311–344
    """
    try:
        care_plan = order.care_plan
        care_plan_data = {
            'id':         care_plan.pk,
            'status':     care_plan.status,
            'content':    care_plan.content,
            'created_at': care_plan.created_at.isoformat(),
            'updated_at': care_plan.updated_at.isoformat(),
        }
    except CarePlan.DoesNotExist:
        care_plan_data = None

    return {
        'order_id': order.pk,
        'patient': {
            'id':            order.patient.pk,
            'first_name':    order.patient.first_name,
            'last_name':     order.patient.last_name,
            'mrn':           order.patient.mrn,
            'date_of_birth': str(order.patient.date_of_birth),
        },
        'provider': {
            'id':         order.provider.pk,
            'first_name': order.provider.first_name,
            'last_name':  order.provider.last_name,
            'npi':        order.provider.npi,
        },
        'medication_name':      order.medication_name,
        'primary_diagnosis':    order.primary_diagnosis,
        'additional_diagnoses': order.additional_diagnoses,
        'medication_history':   order.medication_history,
        'patient_records':      order.patient_records,
        'created_at':           order.created_at.isoformat(),
        'care_plan':            care_plan_data,
    }


def serialize_careplan_status_response(care_plan) -> dict:
    """
    Formats the response for the api_careplan_status endpoint.
    Source: views.py lines 361–370
    """
    payload = {
        'careplan_id': care_plan.pk,
        'status':      care_plan.status,
    }
    if care_plan.status == CarePlan.Status.COMPLETED:
        payload['content'] = care_plan.content
    elif care_plan.status == CarePlan.Status.FAILED:
        payload['error'] = care_plan.content
    return payload



def validate_order_input(data: dict):
    """
    验证 parse_create_order_body() 返回的数据。
    有任何问题就 raise ValidationError。
    """

    patient  = data.get('patient', {})
    provider = data.get('provider') or {}

    npi = provider.get('npi')
    mrn = patient.get('mrn')
    diagnosis = data.get('primary_diagnosis')
    additional_diagnoses = data.get('additional_diagnoses', [])

    patient_fname = patient.get('first_name')
    patient_lname = patient.get('last_name')
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