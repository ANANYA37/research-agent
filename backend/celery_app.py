"""Celery application configuration for durable research jobs."""

import os

try:
    from celery import Celery
except ImportError:
    Celery = None


def create_celery_app():
    if Celery is None:
        return None

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    app = Celery(
        "research_agent",
        broker=os.getenv("CELERY_BROKER_URL", redis_url),
        backend=os.getenv("CELERY_RESULT_BACKEND", redis_url),
        include=["tasks"],
    )
    app.conf.update(
        task_track_started=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
    )
    return app


celery_app = create_celery_app()
