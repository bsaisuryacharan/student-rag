# app/worker/celery_app.py
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "notebook_rag",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_track_started=True,        # gives us a STARTED state while running
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=600,            # hard cap per task (seconds)
)

