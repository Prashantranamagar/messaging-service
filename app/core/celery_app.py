from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "messaging_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks_import",
        "app.workers.tasks_message",
        "app.workers.tasks_notify",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=4,
    task_default_queue="default",
    task_routes={
        "app.workers.tasks_import.*": {"queue": "imports"},
        "app.workers.tasks_message.*": {"queue": "messages"},
        "app.workers.tasks_notify.*": {"queue": "notifications"},
    },
    task_time_limit=600,       # hard kill after 10 min
    task_soft_time_limit=540,  # allow graceful cleanup 1 min before hard kill
    broker_connection_retry_on_startup=True,
    result_expires=86400,
    beat_schedule={
        # Safety net: recovers messages whose DB row was committed but whose
        # dispatch task never made it onto the broker (see sweep_stale_queued_messages
        # docstring in tasks_message.py for the failure mode this covers).
        "sweep-stale-queued-messages": {
            "task": "app.workers.tasks_message.sweep_stale_queued_messages",
            "schedule": 60.0,  # every 60 seconds
        },
    },
)