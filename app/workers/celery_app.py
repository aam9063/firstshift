"""Celery application for FirstShift workers.

F01 scope: configuration only. Tasks (nudges, outbox relay, reconciliation)
arrive with the walking skeleton feature.
"""

import os

from celery import Celery

broker_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("firstshift", broker=broker_url, backend=broker_url)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
