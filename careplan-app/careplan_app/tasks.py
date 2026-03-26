import logging

from celery import shared_task
from django.db import transaction

from .models import CarePlan

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def generate_careplan_task(self, careplan_id: int) -> dict:
    """
    Generate care plan content and persist status/content to DB.
    """
    care_plan = CarePlan.objects.select_related("order__patient").get(pk=careplan_id)

    care_plan.status = CarePlan.Status.PROCESSING
    care_plan.save(update_fields=["status", "updated_at"])

    order = care_plan.order
    patient = order.patient

    logger.info("Celery task started: careplan_id=%s", careplan_id)

    try:
        from .views import call_llm

        content = call_llm(
            patient_name=f"{patient.first_name} {patient.last_name}",
            medication=order.medication_name,
            diagnosis=order.primary_diagnosis,
            additional_diagnoses=order.additional_diagnoses,
            medication_history=order.medication_history,
            patient_records=order.patient_records,
        )
        with transaction.atomic():
            care_plan.content = content
            care_plan.status = CarePlan.Status.COMPLETED
            care_plan.save(update_fields=["content", "status", "updated_at"])
        logger.info("Celery task completed: careplan_id=%s", careplan_id)
        return {"careplan_id": careplan_id, "status": care_plan.status}
    except Exception:
        # Mark as failed for observability, then re-raise for Celery autoretry.
        with transaction.atomic():
            care_plan.status = CarePlan.Status.FAILED
            care_plan.save(update_fields=["status", "updated_at"])
        logger.exception(
            "Celery task failed, retrying if attempts remain: careplan_id=%s", careplan_id
        )
        raise
