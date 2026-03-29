import random
from .models import Patient, Provider, Order, CarePlan
from .tasks import generate_careplan_task


def get_or_create_default_provider():
    """
    Returns the default system provider, creating one if it doesn't exist.
    返回默认系统提供者，如果不存在则自动创建。
    """
    provider, _ = Provider.objects.get_or_create(
        npi="0000000000",
        defaults={
            "first_name": "System",
            "last_name": "Default",
        }
    )
    return provider


def get_or_create_patient(first_name, last_name, mrn=None, date_of_birth=None):
    """
    Finds an existing patient by MRN (if provided) or by name.
    Creates a new one if not found.
    优先按 MRN 查找患者，否则按姓名查找，找不到则自动创建。
    """
    if mrn:
        patient = Patient.objects.filter(mrn=mrn).first()
        if patient:
            return patient

    patient = Patient.objects.filter(
        first_name=first_name,
        last_name=last_name
    ).first()

    if not patient:
        if not mrn:
            while True:
                mrn = str(random.randint(100000, 999999))
                if not Patient.objects.filter(mrn=mrn).exists():
                    break

        patient = Patient.objects.create(
            first_name=first_name,
            last_name=last_name,
            mrn=mrn,
            date_of_birth=date_of_birth or "2000-01-01",
        )

    return patient


def get_or_create_provider(first_name, last_name, npi=None):
    """
    Finds an existing provider by NPI (if provided) or by name.
    Creates a new one if not found.
    优先按 NPI 查找提供者，否则按姓名查找，找不到则自动创建。
    """
    if npi:
        provider = Provider.objects.filter(npi=npi).first()
        if provider:
            return provider

    provider = Provider.objects.filter(
        first_name=first_name,
        last_name=last_name
    ).first()

    if not provider:
        if not npi:
            while True:
                npi = str(random.randint(1000000000, 9999999999))
                if not Provider.objects.filter(npi=npi).exists():
                    break

        provider = Provider.objects.create(
            first_name=first_name,
            last_name=last_name,
            npi=npi,
        )

    return provider


def create_order_and_careplan(patient, provider, medication_name, primary_diagnosis,
                               additional_diagnoses, medication_history, patient_records):
    """
    Creates an Order and a pending CarePlan, then enqueues the async generation task.
    创建医嘱和待处理护理计划，并将生成任务入队。
    """
    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name=medication_name,
        primary_diagnosis=primary_diagnosis,
        additional_diagnoses=additional_diagnoses,
        medication_history=medication_history,
        patient_records=patient_records,
    )
    care_plan = CarePlan.objects.create(
        order=order,
        status=CarePlan.Status.PENDING,
    )
    generate_careplan_task.delay(care_plan.pk)
    return order, care_plan
