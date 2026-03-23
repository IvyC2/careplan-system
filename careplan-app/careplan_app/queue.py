import redis
from django.conf import settings


def get_redis():
    return redis.from_url(settings.REDIS_URL)


def enqueue_careplan(careplan_id: int) -> None:
    client = get_redis()
    client.lpush(settings.CAREPLAN_QUEUE_NAME, str(careplan_id))
