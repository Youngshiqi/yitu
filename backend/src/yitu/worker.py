from celery import Celery  # type: ignore[import-untyped]

from yitu.platform.config import get_settings

settings = get_settings()

celery_app = Celery(
    "yitu",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["yitu.platform.tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_default_exchange="yitu",
    task_default_queue="yitu",
    task_default_routing_key="yitu",
    task_serializer="json",
    worker_prefetch_multiplier=1,
)
