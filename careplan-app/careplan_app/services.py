import random
from .models import Patient, Provider, Order, CarePlan
from .tasks import generate_careplan_task
from .exceptions import BlockError, WarningException


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
    Finds or creates a patient with duplicate detection.
    - MRN match + name & DOB match → reuse
    - MRN match + name or DOB mismatch → WarningException
    - Name+DOB match + different MRN → WarningException
    """
    if mrn:
        existing = Patient.objects.filter(mrn=mrn).first()
        if existing:
            name_match = (existing.first_name == first_name and existing.last_name == last_name)
            dob_match = (date_of_birth is None or str(existing.date_of_birth) == str(date_of_birth))

            if name_match and dob_match:
                return existing  # perfect match, reuse

            mismatches = []
            if not name_match:
                mismatches.append(f"name (stored: {existing.first_name} {existing.last_name})")
            if not dob_match:
                mismatches.append(f"date_of_birth (stored: {existing.date_of_birth})")
            raise WarningException(
                f"MRN {mrn} is already registered with a different "
                + " and ".join(mismatches),
                code="PATIENT_MRN_DATA_MISMATCH",
            )

        # MRN not yet in DB — check for name+DOB conflict with existing patients
        if date_of_birth:
            conflict = Patient.objects.filter(
                first_name=first_name, last_name=last_name, date_of_birth=date_of_birth
            ).first()
            if conflict:
                raise WarningException(
                    f"Patient {first_name} {last_name} (DOB: {date_of_birth}) already exists "
                    f"with MRN {conflict.mrn}, but MRN {mrn} was provided",
                    code="PATIENT_MRN_CONFLICT",
                )

        return Patient.objects.create(
            first_name=first_name,
            last_name=last_name,
            mrn=mrn,
            date_of_birth=date_of_birth or "2000-01-01",
        )

    # No MRN provided — try name+DOB or name-only lookup
    if date_of_birth:
        existing = Patient.objects.filter(
            first_name=first_name, last_name=last_name, date_of_birth=date_of_birth
        ).first()
    else:
        existing = Patient.objects.filter(
            first_name=first_name, last_name=last_name
        ).first()

    if existing:
        return existing

    # No match found — create new patient with a random MRN
    while True:
        new_mrn = str(random.randint(100000, 999999))
        if not Patient.objects.filter(mrn=new_mrn).exists():
            break

    return Patient.objects.create(
        first_name=first_name,
        last_name=last_name,
        mrn=new_mrn,
        date_of_birth=date_of_birth or "2000-01-01",
    )


def get_or_create_provider(first_name, last_name, npi=None):
    """
    Finds an existing provider by NPI (if provided) or by name.
    Creates a new one if not found.
    优先按 NPI 查找提供者，否则按姓名查找，找不到则自动创建。
    """
    if npi:
        provider = Provider.objects.filter(npi=npi).first()
        if provider:
            if provider.first_name == first_name and provider.last_name == last_name:
                return provider
            else:
                raise BlockError(
                    f"NPI {npi} is already registered under a different name: "
                    f"{provider.first_name} {provider.last_name}",
                    code="PROVIDER_NPI_CONFLICT",
                )
        

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


def check_order_duplicate(patient, medication_name, confirm=False):
    """
    Checks for duplicate orders:
    - Same patient + same medication + same day → BlockError (409)
    - Same patient + same medication + different day → WarningException (unless confirm=True)
    """
    from django.utils import timezone
    today = timezone.now().date()

    same_day = Order.objects.filter(
        patient=patient,
        medication_name=medication_name,
        created_at__date=today,
    ).first()

    if same_day:
        raise BlockError(
            f"Duplicate order: {medication_name} was already ordered today "
            f"(Order #{same_day.pk}) for {patient}. Cannot create duplicate same-day order.",
            code="DUPLICATE_ORDER_SAME_DAY",
        )

    if not confirm:
        previous = Order.objects.filter(
            patient=patient,
            medication_name=medication_name,
        ).first()

        if previous:
            raise WarningException(
                f"{medication_name} was previously ordered for {patient} "
                f"(Order #{previous.pk}, created {previous.created_at.date()}). "
                f"Pass confirm=true to proceed anyway.",
                code="DUPLICATE_ORDER_PREVIOUS",
            )


def create_order_from_internal(internal_order, confirm=False):
    """
    接收 InternalOrder（来自 adapter），执行完整业务流程：
    患者/提供者查找或创建 → 重复检测 → 创建订单和护理计划。
    返回 (patient, provider, order, care_plan)。
    """
    parts = (internal_order.provider_name or '').split(' ', 1)
    provider_first = parts[0]
    provider_last  = parts[1] if len(parts) > 1 else ''

    patient = get_or_create_patient(
        first_name=internal_order.first_name,
        last_name=internal_order.last_name,
        mrn=internal_order.mrn,
        date_of_birth=internal_order.date_of_birth,
    )

    if internal_order.npi or provider_first or provider_last:
        provider = get_or_create_provider(
            first_name=provider_first,
            last_name=provider_last,
            npi=internal_order.npi,
        )
    else:
        provider = get_or_create_default_provider()

    order, care_plan = create_order_and_careplan(
        patient=patient,
        provider=provider,
        medication_name=internal_order.medication_name,
        primary_diagnosis=internal_order.primary_diagnosis,
        additional_diagnoses=internal_order.additional_diagnoses,
        medication_history=[],
        patient_records=internal_order.patient_records,
        confirm=confirm,
    )
    return patient, provider, order, care_plan


def create_order_and_careplan(patient, provider, medication_name, primary_diagnosis,
                               additional_diagnoses, medication_history, patient_records,
                               confirm=False):
    """
    Creates an Order and a pending CarePlan, then enqueues the async generation task.
    创建医嘱和待处理护理计划，并将生成任务入队。
    """
    check_order_duplicate(patient, medication_name, confirm=confirm)

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
