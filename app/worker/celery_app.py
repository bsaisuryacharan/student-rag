# app/worker/celery_app.py
import ssl
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "notebook_rag",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_soft_time_limit=1740,   # 29 min: raises SoftTimeLimitExceeded (catchable)
    task_time_limit=1800,        # 30 min: hard kill if soft wasn't caught
    task_ignore_result=True,     # status lives in Qdrant, not Celery result backend
)

# Upstash Redis uses TLS (rediss://) — set SSL options directly in config
# rather than as URL query params, which Celery's URL parser handles inconsistently
if settings.celery_broker_url.startswith("rediss://"):
    _ssl_opts = {"ssl_cert_reqs": ssl.CERT_NONE}
    celery_app.conf.broker_use_ssl = _ssl_opts
    celery_app.conf.redis_backend_use_ssl = _ssl_opts

# Filesystem broker needs to know which folders to use
if settings.celery_broker_url.startswith("filesystem://"):
    celery_app.conf.broker_transport_options = {
        "data_folder_in":  "/tmp/celery-broker",
        "data_folder_out": "/tmp/celery-broker",
    }

