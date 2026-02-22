"""
CareVerify - Extensions
Celery, Redis, and shared extension instances
"""

import logging
from flask import Flask

logger = logging.getLogger(__name__)

try:
    from celery import Celery
    celery_app = Celery("careverify")
    HAS_CELERY = True
except ImportError:
    logger.warning("Celery not found. Task queue features will be disabled.")
    celery_app = None
    HAS_CELERY = False


def init_extensions(app: Flask):
    """Initialize all extensions."""
    if HAS_CELERY and celery_app:
        try:
            # Configure Celery
            celery_app.conf.update(
                broker_url=app.config.get("REDIS_URL", "redis://localhost:6379/0"),
                result_backend=app.config.get("REDIS_URL", "redis://localhost:6379/0"),
                task_serializer="json",
                accept_content=["json"],
                result_serializer="json",
                timezone="UTC",
                enable_utc=True,
                task_routes={
                    "app.tasks.ai_tasks.*": {"queue": "ai_processing"},
                    "app.tasks.notification_tasks.*": {"queue": "notifications"},
                    "app.tasks.audit_tasks.*": {"queue": "audit"},
                },
                task_default_queue="default",
                task_default_exchange="default",
                task_default_routing_key="default",
                worker_prefetch_multiplier=1,
                task_acks_late=True,
            )

            class ContextTask(celery_app.Task):
                def __call__(self, *args, **kwargs):
                    with app.app_context():
                        return self.run(*args, **kwargs)

            celery_app.Task = ContextTask
            logger.info("Celery initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Celery: {e}")
    else:
        logger.info("Skipping Celery initialization.")
