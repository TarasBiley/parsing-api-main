from celery import Celery

from core.config import settings

celery_app = Celery(
    __name__,
    broker=settings.REDIS,
    backend=settings.REDIS,
    include=['tasks.tasks']
)
