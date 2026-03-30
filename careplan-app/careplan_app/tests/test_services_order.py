"""
Unit tests for services.check_order_duplicate and create_order_and_careplan.
"""
import datetime
import pytest
from django.utils import timezone

from careplan_app.models import Patient, Provider, Order, CarePlan
from careplan_app.services import check_order_duplicate, create_order_and_careplan
from careplan_app.exceptions import BlockError, WarningException


# ── O1: Same patient + medication + same day → DUPLICATE_ORDER_SAME_DAY ───────

@pytest.mark.django_db
def test_same_day_duplicate_raises_block_error(order, patient):
    # `order` fixture was just created today for "Metformin"
    with pytest.raises(BlockError) as exc_info:
        check_order_duplicate(patient, "Metformin")
    assert exc_info.value.code == "DUPLICATE_ORDER_SAME_DAY"
    assert "Metformin" in exc_info.value.message


# ── O2: Previous-day order + confirm=False → DUPLICATE_ORDER_PREVIOUS ─────────

@pytest.mark.django_db
def test_previous_day_duplicate_no_confirm_raises_warning(db, patient, provider):
    yesterday = timezone.now() - datetime.timedelta(days=1)
    old_order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name="Aspirin",
        primary_diagnosis="I10",
        additional_diagnoses=[],
        medication_history=[],
        patient_records="",
    )
    # Back-date by bypassing auto_now_add
    Order.objects.filter(pk=old_order.pk).update(created_at=yesterday)

    with pytest.raises(WarningException) as exc_info:
        check_order_duplicate(patient, "Aspirin", confirm=False)
    assert exc_info.value.code == "DUPLICATE_ORDER_PREVIOUS"
    assert "confirm=true" in exc_info.value.message.lower()


# ── O3: Previous-day order + confirm=True → no exception ──────────────────────

@pytest.mark.django_db
def test_previous_day_duplicate_with_confirm_passes(db, patient, provider):
    yesterday = timezone.now() - datetime.timedelta(days=1)
    old_order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name="Aspirin",
        primary_diagnosis="I10",
        additional_diagnoses=[],
        medication_history=[],
        patient_records="",
    )
    Order.objects.filter(pk=old_order.pk).update(created_at=yesterday)

    # Should return None without raising
    result = check_order_duplicate(patient, "Aspirin", confirm=True)
    assert result is None


# ── O4: Different patient, same medication + same day → no exception ──────────

@pytest.mark.django_db
def test_different_patient_no_duplicate(db, order, provider):
    other_patient = Patient.objects.create(
        first_name="Other",
        last_name="Person",
        mrn="777777",
        date_of_birth="2000-01-01",
    )
    # Should not raise — it's a different patient
    check_order_duplicate(other_patient, "Metformin")


# ── O5: No prior orders at all → no exception ────────────────────────────────

@pytest.mark.django_db
def test_no_prior_orders_passes(patient):
    check_order_duplicate(patient, "BrandNewDrug")  # no exception


# ── create_order_and_careplan: enqueues Celery task, returns PENDING plan ─────

@pytest.mark.django_db
def test_create_order_and_careplan_enqueues_task(patient, provider, mock_celery_task):
    order, care_plan = create_order_and_careplan(
        patient=patient,
        provider=provider,
        medication_name="NewMed",
        primary_diagnosis="J18.9",
        additional_diagnoses=[],
        medication_history=[],
        patient_records="",
    )
    assert care_plan.status == CarePlan.Status.PENDING
    mock_celery_task.assert_called_once_with(care_plan.pk)


# ── create_order_and_careplan: confirm=False on previous-day order → warning ──

@pytest.mark.django_db
def test_create_order_and_careplan_propagates_duplicate_warning(patient, provider):
    yesterday = timezone.now() - datetime.timedelta(days=1)
    old_order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name="Warfarin",
        primary_diagnosis="I48",
        additional_diagnoses=[],
        medication_history=[],
        patient_records="",
    )
    Order.objects.filter(pk=old_order.pk).update(created_at=yesterday)

    with pytest.raises(WarningException) as exc_info:
        create_order_and_careplan(
            patient=patient,
            provider=provider,
            medication_name="Warfarin",
            primary_diagnosis="I48",
            additional_diagnoses=[],
            medication_history=[],
            patient_records="",
            confirm=False,
        )
    assert exc_info.value.code == "DUPLICATE_ORDER_PREVIOUS"
