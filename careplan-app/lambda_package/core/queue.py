"""
core/queue.py — Queue abstraction layer.

CeleryQueue: dispatches via Celery (local / Django runtime)
SQSQueue   : dispatches via AWS SQS (Lambda runtime)
"""

import json
from abc import ABC, abstractmethod


class QueueInterface(ABC):

    @abstractmethod
    def enqueue(self, careplan_pk: int) -> None:
        """Enqueue a careplan generation job."""


class CeleryQueue(QueueInterface):
    """Dispatches via Celery. Suitable for local / Django-managed runtime."""

    def enqueue(self, careplan_pk: int) -> None:
        from careplan_app.tasks import generate_careplan_task
        generate_careplan_task.delay(careplan_pk)


class SQSQueue(QueueInterface):
    """
    Dispatches via AWS SQS. Suitable for Lambda runtime.

    Usage:
        import boto3
        queue = SQSQueue(queue_url="https://sqs.us-east-1.amazonaws.com/123/my-queue")
        # or pass a pre-built client for testing:
        queue = SQSQueue(queue_url="...", client=mock_sqs_client)
    """

    def __init__(self, queue_url: str, client=None):
        self._queue_url = queue_url
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        import boto3
        return boto3.client("sqs")

    def enqueue(self, careplan_pk: int) -> None:
        self._get_client().send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps({"careplan_id": careplan_pk}),
        )
