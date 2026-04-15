import logging

import redis
from django.conf import settings
from django.db import transaction

from .llm import get_llm_service
from .models import CarePlan

logger = logging.getLogger(__name__)


def get_redis():
    return redis.from_url(settings.REDIS_URL)


def enqueue_careplan(careplan_id: int) -> None:
    client = get_redis()
    client.lpush(settings.CAREPLAN_QUEUE_NAME, str(careplan_id))


def process_one_careplan_task() -> bool:
    """
    Pull exactly one task from Redis and process it.
    从 Redis 取一个任务并处理。

    Returns True if one task was processed, otherwise False.
    """
    client = get_redis()
    raw_id = client.rpop(settings.CAREPLAN_QUEUE_NAME)
    if raw_id is None:
        return False

    careplan_id = int(raw_id)
    logger.info("Pulled task from Redis: careplan_id=%s", careplan_id)

    try:
        care_plan = CarePlan.objects.select_related("order__patient").get(pk=careplan_id)
    except CarePlan.DoesNotExist:
        # Task points to a removed/invalid row; skip gracefully.
        logger.warning("CarePlan not found for task: careplan_id=%s", careplan_id)
        return False

    # Mark as processing so DB clearly reflects in-flight work.
    care_plan.status = CarePlan.Status.PROCESSING
    care_plan.save(update_fields=["status", "updated_at"])

    order = care_plan.order
    patient = order.patient

    try:
        logger.info("Starting LLM call: careplan_id=%s", careplan_id)
        llm = get_llm_service()
        content = llm.generate(
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
        logger.info("CarePlan processed successfully: careplan_id=%s", careplan_id)
    except Exception as exc:
        with transaction.atomic():
            care_plan.content = str(exc)
            care_plan.status = CarePlan.Status.FAILED
            care_plan.save(update_fields=["content", "status", "updated_at"])
        logger.exception("CarePlan processing failed: careplan_id=%s", careplan_id)

    return True
